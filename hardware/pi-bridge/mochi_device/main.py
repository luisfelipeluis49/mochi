"""Mochi device supervisor.

    IDLE ──"Oi Mochi" (offline)──► STARTING ──agent+bridge up──► ACTIVE
      ▲                                                            │
      └──── STOPPING ◄── goodbye phrase (offline) / Mochi said goodbye / inactivity / max time /
                         bridge died / the backend stopped the session

While IDLE, the microphone only feeds the local keyword spotter: no Agora session exists and no
audio leaves the Pi. Run: scripts/mochi.sh   (Ctrl-C to quit; any live session is ended first)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import signal
import time

from dotenv import load_dotenv

from . import config as config_mod
from .audio import Mic, chime
from .backends import make_backend
from .bridge import BridgeProcess
from .face import MOODS, Face
from .wakeword import KeywordSpotter


LANGUAGE_NAMES = {"en": "English", "pt-BR": "Português", "pt": "Português"}


def hint_note(card: dict) -> str:
    """The small line under a hint: the word's language, and the word it stands for.

    Example: {"word": "fork", "language": "en", "meaning": "garfo"} -> "English · garfo".
    """
    language = LANGUAGE_NAMES.get(str(card.get("language")), "")
    meaning = str(card.get("meaning") or "")
    return " · ".join(part for part in (language, meaning) if part)[:40]


def log(msg: str) -> None:
    print(f"[mochi] {time.strftime('%H:%M:%S')} {msg}", flush=True)


class Supervisor:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.dev = cfg["audio"]["device"]
        self.kws = KeywordSpotter(cfg)
        self.face = Face(cfg.get("face"))
        self.backend = make_backend(cfg, self.on_agent_event)
        self.mic = Mic(self.dev)
        self.bridge = BridgeProcess(self.dev, self.on_agent_voice)
        self.state = "IDLE"
        self.quit = asyncio.Event()
        self._start_task: asyncio.Task | None = None
        self.session_started = self.last_speech = 0.0
        self.agent_voice_at = self.heard_at = self.bye_until = 0.0
        self.enrol_lang = "en"
        self.backend_end: str | None = None  # set when the backend ended the session itself
        self.bye_asked: float | None = None  # when Mochi said goodbye ([bye]): the session ends after it

    # --- the face on Mochi's screen ---------------------------------------------------------
    def on_agent_voice(self, level: int) -> None:
        if level:
            self.agent_voice_at = time.monotonic()
        self.face.set(level=level)

    def on_agent_event(self, kind: str, value) -> None:
        """Things the agent did or asked for (see backends.py): shown on the face."""
        if kind == "mood" and value in MOODS:
            self.face.show_for(12, mood=value)
        elif kind == "show":
            self.face.show_for(10, word=str(value)[:28], note="")
        elif kind == "hint":  # a word someone needed: say which language it is in and what it means
            self.face.show_for(10, word=str(value.get("word", ""))[:28], note=hint_note(value))
        elif kind in ("volume", "temp"):
            self.face.pop(kind, value)
        elif kind == "enroll":  # "learn my voice": the next ~10 s of speech become their voiceprint
            name, self.enrol_lang = value
            log(f"learning {name}'s voice")
            self.kws.enroll(name)
            self.face.show_for(30, who=f"{name} ...")
        elif kind == "forget":
            log(f"forgetting {value}'s voice")
            self.kws.forget(value)
        elif kind == "stopped":  # the session was ended elsewhere: on_frame leaves the channel
            self.backend_end = str(value)
        elif kind == "bye":  # Mochi is saying goodbye: on_frame ends the session once it has
            self.bye_asked = time.monotonic()

    def _goodbye_said(self, now: float) -> bool:
        """Mochi wrote [bye]: leave once its goodbye has been heard out, or after 8 s at the latest."""
        if self.bye_asked is None:
            return False
        heard_out = self.agent_voice_at > self.bye_asked and now - self.agent_voice_at > 0.8
        return heard_out or now - self.bye_asked > 8

    def on_voice_event(self, event: tuple) -> None:
        """What the voice tracker noticed (speakers.py)."""
        kind, name, amount = event
        tell = getattr(self.backend, "set_voices", lambda known, speaker: None)
        if kind == "speaker":
            if name:
                self.face.show_for(5, who=name)
            tell(self.kws.known_voices, name)
        elif kind == "enrolled":
            log(f"learned {name}'s voice from {amount:.0f} s of speech")
            self.face.show_for(6, who=name, mood="proud")
            tell(self.kws.known_voices, name)
            asyncio.create_task(self.backend.voice_enrolled(name, self.enrol_lang, True))
        elif kind == "enroll_failed":
            log(f"could not learn {name}'s voice: only {amount:.0f} s of speech")
            self.face.set(who="")
            asyncio.create_task(self.backend.voice_enrolled(name, self.enrol_lang, False))

    def _face_mode(self, now: float) -> str:
        if self.state == "IDLE":
            return "bye" if now < self.bye_until else "sleeping"
        if self.state != "ACTIVE":
            return "waking"
        if now - self.agent_voice_at < 0.4:
            return "speaking"
        if now - self.kws.last_voice < 0.5:
            self.heard_at = now
            return "hearing"
        if self.heard_at > self.agent_voice_at and now - self.heard_at < 6:
            return "thinking"  # someone finished talking and Mochi has not answered yet
        return "awake"

    def _chime(self, rising: bool) -> None:
        if self.cfg["audio"].get("chimes", True):
            asyncio.create_task(chime(self.dev, rising))

    async def run(self) -> None:
        await self.mic.start()
        await self.face.start()
        log(f"listening offline for {self.cfg['wake']['phrases']} (backend: {self.cfg['backend']['kind']})")
        try:
            while not self.quit.is_set():
                try:
                    frame = await asyncio.wait_for(self.mic.frame(), timeout=2)
                except (asyncio.IncompleteReadError, asyncio.TimeoutError):
                    log("microphone stopped delivering audio; restarting it")
                    await self.mic.stop()
                    await asyncio.sleep(1)  # unplugged or not there yet at boot: do not spin
                    await self.mic.start()
                    continue
                await self.on_frame(frame)
        finally:
            await self.end_session("shutdown")
            await self.mic.stop()
            self.kws.close()

    async def on_frame(self, frame: bytes) -> None:
        hit = self.kws.feed(frame)
        now = time.monotonic()
        self.face.set(mode=self._face_mode(now))

        if self.state == "IDLE":
            if hit and hit[0] == "wake":
                log(f"wake phrase heard: {hit[1]!r} -> starting session")
                self.state = "STARTING"
                self._chime(rising=True)
                self.session_started = self.last_speech = now
                self._start_task = asyncio.create_task(self.start_session(hit[1]))
            return

        self.last_speech = max(self.last_speech, self.kws.last_voice)  # a voice, not just loudness

        if self.state == "ACTIVE":
            self.bridge.send(frame)
            # who is talking? (not while Mochi itself is: its own voice is not a person)
            mochi_talking = now - self.agent_voice_at < 0.6
            self.kws.track_voices(True, hold=mochi_talking)
            if mochi_talking and now - self.kws.last_voice < 0.2 and hasattr(self.backend, "set_voices"):
                self.backend.set_voices(self.kws.known_voices, None)  # someone talks over Mochi: not known who
            for event in self.kws.voice_events():
                self.on_voice_event(event)
            reason = None
            if hit and hit[0] == "goodbye":
                reason = f"goodbye phrase {hit[1]!r}"
            elif self.backend_end:
                reason = self.backend_end
            elif self._goodbye_said(now):
                reason = "Mochi said goodbye"
            elif now - self.last_speech > self.cfg["session"]["inactivity_timeout_s"]:
                reason = f"{self.cfg['session']['inactivity_timeout_s']} s without speech"
            elif now - self.session_started > self.cfg["session"]["max_session_s"]:
                reason = "max session time reached"
            elif not self.bridge.running:
                reason = "bridge exited"
            if reason:
                await self.end_session(reason)

    async def start_session(self, wake_phrase: str) -> None:
        t0 = time.monotonic()
        self.backend_end = self.bye_asked = None
        try:
            if hasattr(self.backend, "set_voices"):
                self.backend.set_voices(self.kws.known_voices, None)
            join = await self.backend.start(wake_phrase)
            await self.bridge.start(join)
            self.state = "ACTIVE"
            self.last_speech = time.monotonic()
            log(f"session active in channel {join.channel!r} after {self.last_speech - t0:.1f} s; "
                f"say {self.cfg['goodbye']['phrases'][0]!r} to end")
        except Exception as e:
            log(f"could not start session: {e}")
            await self.backend.stop()
            self.state = "IDLE"
            self.kws.reset()
            self._chime(rising=False)

    async def end_session(self, reason: str) -> None:
        if self.state == "IDLE":
            return
        if self._start_task and not self._start_task.done():
            await self._start_task  # let a half-started session finish so it can be stopped cleanly
        self.state = "STOPPING"
        log(f"ending session: {reason}")
        await self.bridge.stop()
        await self.backend.stop()
        self.kws.reset()
        self.state = "IDLE"
        self.kws.track_voices(False)
        self.bye_until = time.monotonic() + 3
        self.face.set(level=0, word="", note="", mood="neutral", who="")
        self._chime(rising=False)
        log("back to offline listening (no audio leaves the Pi)")


async def amain() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(config_mod.DEFAULT_CONFIG))
    args = ap.parse_args()
    load_dotenv(config_mod.BRIDGE_DIR / ".env")
    sup = Supervisor(config_mod.load_with_local(config_mod.Path(args.config)))
    loop = asyncio.get_running_loop()
    for s in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(s, sup.quit.set)
    await sup.run()
    # Everything of ours is stopped. After a session some task can remain that never finishes when
    # cancelled, and asyncio.run() would wait on it for ever: give leftovers a moment, then leave.
    left = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for t in left:
        t.cancel()
    if left:
        _done, stuck = await asyncio.wait(left, timeout=2)
        if stuck:
            log("leaving with tasks still pending: " + ", ".join(sorted({t.get_coro().__qualname__ for t in stuck})))
            os._exit(0)


def main() -> None:
    asyncio.run(amain())


if __name__ == "__main__":
    main()
