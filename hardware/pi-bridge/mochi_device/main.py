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
from .audio import Mic, chime, say
from .backends import make_backend
from .bargein import LevelWatch
from .bridge import BridgeProcess
from .device import LOOK_AT, cpu_temperature, reachable
from .face import MOODS, Face
from .wakeword import KeywordSpotter


LANGUAGE_NAMES = {"en": "English", "pt-BR": "Português", "pt": "Português"}


def hint_note(card: dict) -> str:
    """The small line under a hint: the word's language, and the word it stands for.

    Example: {"word": "fork", "language": "en", "meaning": "garfo"} -> "English · garfo".
    A code switch ("why": "code_switch") reads as what happened, so that the others at the table
    see which word was said and what it is in the language of the meeting: "garfo → English".
    """
    language = LANGUAGE_NAMES.get(str(card.get("language")), "")
    meaning = str(card.get("meaning") or "")
    if card.get("why") == "code_switch" and meaning and language:
        return f"{meaning} → {language}"[:40]
    return " · ".join(part for part in (language, meaning) if part)[:40]


def hint_flag(card: dict) -> str:
    """How the card is drawn: "switch" for a code switch (it should catch everyone's eye), else ""."""
    return "switch" if card.get("why") == "code_switch" and card.get("meaning") else ""


SENTENCE_S = 12  # how long a suggested sentence stays on the screen


def translation_seconds(text: str) -> float:
    """How long a sentence Mochi says for someone stays on the screen: about as long as it takes
    to say and to read. Example: eight words -> 6.1 s; a short one -> 6 s at least."""
    return max(6.0, 2.5 + 0.45 * len(text.split()))
CAPTION_CHARS = 84  # what fits in two small lines on the 3.5-inch screen


def caption_line(card: dict) -> str:
    """One sentence of the live transcript, with who said it when the voice was recognised.

    Example: {"who": "Ana", "text": "I need to adiar my meeting"} -> "Ana: I need to adiar my meeting".
    A long sentence keeps its end: the last words are the ones just said.
    """
    text = " ".join(str(card.get("text") or "").split())
    who = str(card.get("who") or "")
    room = CAPTION_CHARS - (len(who) + 2 if who else 0)
    if len(text) > room:
        text = "…" + text[-(room - 1):]
    return f"{who}: {text}" if who else text


def hint_more(card: dict) -> str:
    """The third line of a hint: the other words that fit, when the person named none.

    Example: {"word": "umbrella", "candidates": ["raincoat", "jacket"]} -> "raincoat · jacket".
    Anything that is not a list of words (an older backend sends no "candidates") gives "".
    """
    others = card.get("candidates")
    if not isinstance(others, list):
        return ""
    words = [str(word)[:20] for word in others if isinstance(word, str) and word][:2]
    return " · ".join(words)


USED_NOTES = {"en": "★ you used it!", "pt-BR": "★ você usou!", "pt": "★ você usou!"}


def log(msg: str) -> None:
    print(f"[mochi] {time.strftime('%H:%M:%S')} {msg}", flush=True)


class Supervisor:
    # someone talking over Mochi (see __init__ and _watch_for_talking_over); off until configured
    barge_in = barge_by_voice = was_talking = False
    barged_at: float | None = None
    level_watch: LevelWatch | None = None

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.dev = cfg["audio"]["device"]
        self.kws = KeywordSpotter(cfg)
        self.face = Face(cfg.get("face"))
        self.captions = bool((cfg.get("face") or {}).get("captions", True))  # the live transcript
        self.net = cfg.get("network", {})  # how the connection is watched (see _look_after_itself)
        self.online = True
        # what Mochi says by itself, from recordings (no connection needed): see _tell
        self.alerts = cfg.get("alerts", {})
        self.language = str(self.alerts.get("language", "en"))  # then the language of the last wake phrase
        self.hot = False                       # warmer than [alerts].hot_at right now
        self.told: dict[str, float] = {}       # when each thing was last said
        self.loss_said = False                 # "no connection" was said, so its return will be too
        self.pinged = -1e9                     # when the backend was last touched to keep it awake
        self.owed: str | None = None           # something to say once the session has ended
        self.backend = make_backend(cfg, self.on_agent_event)
        # [voices].share_with_backend: voiceprints are biometric; off, none leaves this Pi and none is fetched
        self.share_voices = bool(cfg.get("voices", {}).get("share_with_backend", True))
        if self.share_voices and hasattr(self.backend, "use_voices"):
            self.backend.use_voices(self.kws.voiceprints)  # so the backend's database and this Pi share voices
        self.mic = Mic(self.dev)
        self.bridge = BridgeProcess(self.dev, self.on_agent_voice, self.on_agent_left)
        self.state = "IDLE"
        self.quit = asyncio.Event()
        self._start_task: asyncio.Task | None = None
        # one wake-up may take this long (backend, Agora, bridge); then it is given up and Mochi listens again
        self.start_timeout_s = float(cfg.get("session", {}).get("start_timeout_s", 25))
        self.session_started = self.last_speech = 0.0
        self.agent_voice_at = self.heard_at = self.bye_until = 0.0
        # [barge_in]: someone talking over Mochi stops it (bargein.py); barged = it was just stopped
        # and its voice has not run out yet (the speaker is silent, the microphone is sent on again)
        over = cfg.get("barge_in", {})
        self.barge_in = bool(over.get("enabled", True))
        self.barge_by_voice = bool(over.get("by_voice", True))
        self.level_watch = LevelWatch(float(over.get("level_ratio", 3.5)), float(over.get("level_floor", 300)),
                                      int(over.get("need_ms", 240)))
        self.barged_at: float | None = None
        self.was_talking = False
        self.enrol_lang = "en"
        self.backend_end: str | None = None  # set when the backend ended the session itself
        self.bye_asked: float | None = None  # when Mochi said goodbye ([bye]): the session ends after it

    # --- the face on Mochi's screen ---------------------------------------------------------
    def on_agent_voice(self, level: int) -> None:
        if level:
            self.agent_voice_at = time.monotonic()
        self.face.set(level=level)

    def on_agent_left(self, uid: int) -> None:
        """Mochi's agent left the call (the service ended it, or it failed): nobody would answer any
        more, so the session ends instead of sitting awake and deaf. Seen live: it left after 99 s
        and Mochi stayed "awake" for another minute while the person kept talking to it."""
        if self.state == "ACTIVE":
            self.backend_end = "Mochi's agent left the call"

    def on_agent_event(self, kind: str, value) -> None:
        """Things the agent did or asked for (see backends.py): shown on the face."""
        if kind == "mood" and value in MOODS:
            self.face.show_for(12, mood=value)
        elif kind == "show":
            self.face.show_for(10, word=str(value)[:28], note="", more="", flag="")
        elif kind == "hint":  # a word someone needed: say which language it is in and what it means
            self.face.show_for(10, word=str(value.get("word", ""))[:28], note=hint_note(value),
                               more=hint_more(value), flag=hint_flag(value))
        elif kind == "used":  # they said the word they were given: cheer, without a sound
            note = USED_NOTES.get(str(value.get("language")), "★")
            self.face.show_for(5, word=str(value.get("word", ""))[:28], note=note, more="", flag="", mood="proud")
        elif kind == "explain":  # an idiom or a term that was just said: what it means, for those listening
            self.face.show_for(10, word=str(value.get("word", ""))[:28], note=str(value.get("meaning") or "")[:40],
                               more=str(value.get("plain") or "")[:40], flag="explain")
        elif kind == "suggest":  # the whole sentence someone was reaching for: shown, to read (no touch, D-70)
            self.face.show_for(SENTENCE_S, say=str(value.get("text", ""))[:120], aloud=False)
        elif kind == "translation":  # what Mochi is saying in the other language (speak for me, D-70)
            text = str(value.get("text", ""))
            self.face.show_for(translation_seconds(text), say=text[:140], aloud=True)
        elif kind == "caption":  # the live transcript: the sentence that was just said
            if getattr(self, "captions", True):
                self.face.show_for(8, caption=caption_line(value))
        elif kind in ("volume", "temp"):
            self.face.pop(kind, value)
        elif kind == "enroll":  # "learn my voice": the next ~10 s of speech become their voiceprint
            name, self.enrol_lang = value
            log(f"learning {name}'s voice")
            self.kws.enroll(name)
            self.face.show_for(30, who=f"{name} ...")
        elif kind == "voices":  # voices the backend has and this Pi lacks (a replaced Pi): add them
            log("restoring voices from the backend: " + ", ".join(str(v.get("name")) for v in value))
            self.kws.merge_voices(value)
        elif kind == "forget":
            log(f"forgetting {value}'s voice")
            self.kws.forget(value)
            if hasattr(self.backend, "set_voices"):  # at once: nothing else would say so for a while
                left = [v for v in self.kws.known_voices if v.lower() != str(value).lower()]
                self.backend.set_voices(left, None)
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
        kind, name, amount = event[:3]
        if kind == "over":  # a known person is talking while Mochi is: it stops and listens
            if self.barge_by_voice:
                self._barge_in(f"{name} is talking (score {amount:.2f})")
            return
        tell = getattr(self.backend, "set_voices", lambda known, speaker: None)
        if kind == "speaker":  # a known person, or (None) a stranger; until the next one it stays so
            log(f"voice: {name or 'nobody I know'} (score {amount:.2f})")
            if name:
                self.face.show_for(5, who=name)
            tell(self.kws.known_voices, name)
        elif kind == "said":  # a stretch of speech and who said it: the backend names sentences with these
            heard = getattr(self.backend, "heard", None)
            if heard:
                heard(name, amount, event[3])
        elif kind == "unsure":  # for the log only: the scores tell whether [voices] min_score fits
            log(f"voice: not sure yet (score {amount:.2f})")
        elif kind == "enrolled":
            log(f"learned {name}'s voice from {amount:.0f} s of speech")
            self.face.show_for(6, who=name, mood="proud")
            tell(self.kws.known_voices, name)
            mine = self.kws.voiceprints().get(name) if getattr(self, "share_voices", True) else None
            asyncio.create_task(self.backend.voice_enrolled(name, self.enrol_lang, True, mine))
        elif kind == "enroll_failed":
            log(f"could not learn {name}'s voice: only {amount:.0f} s of speech")
            self.face.set(who="")
            asyncio.create_task(self.backend.voice_enrolled(name, self.enrol_lang, False))

    def _face_mode(self, now: float) -> str:
        if self.state == "IDLE":
            return "bye" if now < self.bye_until else "sleeping"
        if self.state != "ACTIVE":
            return "waking"
        if now - self.agent_voice_at < 0.4 and self.barged_at is None:
            return "speaking"
        if now - self.kws.last_voice < 0.5:
            self.heard_at = now
            return "hearing"
        if self.heard_at > self.agent_voice_at and now - self.heard_at < 6:
            return "thinking"  # someone finished talking and Mochi has not answered yet
        return "awake"

    # --- how warm Mochi is and whether it has a connection, for its face --------------------------
    async def _look_after_itself(self) -> None:
        """Every few seconds, for as long as Mochi runs."""
        misses = 0
        while True:
            misses = await self._look_once(misses)
            await asyncio.sleep(float(self.net.get("every_s", 5)))

    async def _look_once(self, misses: int) -> int:
        """One look. Returns how many looks in a row found no connection (one alone is not a loss)."""
        temp = cpu_temperature()
        found = not self.net.get("check", True) or await asyncio.to_thread(
            reachable, tuple(self.net.get("hosts", LOOK_AT)), float(self.net.get("timeout_s", 2)))
        misses = 0 if found else misses + 1
        online = misses < 2
        if online != self.online:
            log("the connection is back" if online else "no connection to the internet (Wi-Fi or hotspot?)")
            self.online = online
            self._tell("online" if online else "offline")
        self._feel(temp)
        self.face.set(temp=None if temp is None else round(temp), hot=self.hot, online=online)
        self._keep_backend_awake(online)
        return misses

    def _keep_backend_awake(self, online: bool) -> None:
        """[backend].keep_awake_s: touch the backend this often while Mochi sleeps (0 = never)."""
        every = float(self.cfg.get("backend", {}).get("keep_awake_s", 0))
        now = time.monotonic()
        if not every or not online or self.state != "IDLE" or now - self.pinged < every:
            return
        self.pinged = now
        if hasattr(self.backend, "ping"):
            asyncio.create_task(self.backend.ping())

    def _feel(self, temp: float | None) -> None:
        """Too warm is said once; again only after Mochi has cooled down by five degrees in between."""
        limit = float(self.alerts.get("hot_at", 80))
        if temp is None:
            return
        if temp >= limit and not self.hot:
            self.hot = True
            log(f"too warm: {temp:.0f} degrees")
            self._tell("hot")
        elif temp < limit - 5:
            self.hot = False

    def _tell(self, what: str) -> None:
        """Say it out loud, from a recording: "offline" | "online" | "hot".

        Not during a session (the speaker is Mochi's voice then): it is owed, and said when the
        session ends if it is still true. Not twice within [alerts].every_s. "online" only after
        "offline" was really said: a return nobody was told about needs no announcement.
        """
        now = time.monotonic()
        if not self.alerts.get("speak", True):
            return
        if what == "online" and not self.loss_said:
            return
        if self.state != "IDLE":
            self.owed = what
            return
        if what != "online" and now - self.told.get(what, -1e9) < float(self.alerts.get("every_s", 120)):
            return
        self.told[what] = now
        self.loss_said = what == "offline" or (self.loss_said and what != "online")
        asyncio.create_task(say(self.dev, what, self.language))

    def _tell_what_is_owed(self) -> None:
        """After a session: what could not be said during it, if it still holds."""
        owed, self.owed = self.owed, None
        still = {"offline": not self.online, "online": self.online, "hot": self.hot}
        if owed and still.get(owed):
            self._tell(owed)

    def _chime(self, rising: bool) -> None:
        if self.cfg["audio"].get("chimes", True):
            asyncio.create_task(chime(self.dev, rising))

    async def run(self) -> None:
        await self.mic.start()
        await self.face.start()
        vitals = asyncio.create_task(self._look_after_itself())
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
            vitals.cancel()
            await self.end_session("shutdown")
            await self.mic.stop()
            self.kws.close()

    async def on_frame(self, frame: bytes) -> None:
        hit = self.kws.feed(frame)
        now = time.monotonic()
        self.face.set(mode=self._face_mode(now))

        if self.state == "IDLE":
            if hit and hit[0] == "wake":
                # whose voice said it, when the Pi knows it (reported just before the hit itself)
                caller = next((e[1] for e in reversed(self.kws.voice_events()) if e[0] == "speaker" and e[1]), None)
                log(f"wake phrase heard: {hit[1]!r}{f' from {caller}' if caller else ''} -> starting session")
                self.language = "pt" if hit[1].lower().split()[0] in ("oi", "olá", "ola", "vamos", "vamo") else "en"
                self.state = "STARTING"
                self._chime(rising=True)
                self.session_started = self.last_speech = now
                self._start_task = asyncio.create_task(self.start_session(hit[1], caller))
            return

        self.last_speech = max(self.last_speech, self.kws.last_voice)  # a voice, not just loudness
        if self.state != "ACTIVE":
            self.kws.voice_events()  # a wake phrase said again while starting is not the next session's caller

        if self.state == "ACTIVE":
            # who is talking? (not while Mochi itself is: its own voice is not a person)
            mochi_talking = now - self.agent_voice_at < 0.6
            self._watch_for_talking_over(frame, now, mochi_talking)
            # Mochi's voice comes back through the microphone, and the recogniser writes it down as
            # something a person said (seen live: the greeting arrived as "Where is my chave?", and
            # Mochi answered it). While Mochi speaks, what is sent on is silence. Not once someone
            # has talked over it: the speaker is silent then, and that person must be heard.
            deaf = mochi_talking and self.barged_at is None and not self.cfg["audio"].get("hear_while_speaking", False)
            self.bridge.send(bytes(len(frame)) if deaf else frame)
            self.kws.track_voices(True, hold=mochi_talking and self.barged_at is None)
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

    # --- someone talks over Mochi: it stops at once and listens ------------------------------------
    BARGE_GIVE_UP_S = 4.0  # Mochi's voice still coming this long after it was told to stop: let it be heard again

    def _watch_for_talking_over(self, frame: bytes, now: float, mochi_talking: bool) -> None:
        """Every frame of a session: notice a person over Mochi's voice, and end the hush once its voice has stopped."""
        if self.barged_at is not None:
            if not mochi_talking or now - self.barged_at > self.BARGE_GIVE_UP_S:
                self.barged_at = None
                asyncio.create_task(self._hush(False))
        elif mochi_talking and self.barge_in and self.level_watch:
            if not self.was_talking:
                self.level_watch.begin()
            if self.level_watch.heard(frame, voiced=now - self.kws.last_voice < 0.4):
                self._barge_in("a voice louder than Mochi's own")
        self.was_talking = mochi_talking

    def _barge_in(self, why: str) -> None:
        """Stop Mochi now: its speaker goes silent here at once, its agent is told to stop, and the
        microphone is sent on again so the person is heard."""
        now = time.monotonic()
        if not self.barge_in or self.state != "ACTIVE" or self.barged_at is not None or now - self.agent_voice_at >= 0.6:
            return
        log(f"talked over: {why} -> Mochi stops and listens")
        self.barged_at = now
        self.heard_at = now
        asyncio.create_task(self._hush(True))
        interrupt = getattr(self.backend, "interrupt", None)
        if interrupt:
            asyncio.create_task(interrupt())

    async def _hush(self, quiet: bool) -> None:
        hush = getattr(self.backend, "hush_speaker", None)
        if hush:
            try:
                await hush(quiet)
            except Exception as e:  # a mixer that does not answer: Mochi's sentence then runs out by itself
                log(f"speaker {'hush' if quiet else 'back'} failed: {e!r}")

    async def start_session(self, wake_phrase: str, caller: str | None = None) -> None:
        """caller: whose voice said the wake phrase, when the Pi recognised it."""
        t0 = time.monotonic()
        self.backend_end = self.bye_asked = None
        try:
            if hasattr(self.backend, "set_voices"):
                self.backend.set_voices(self.kws.known_voices, caller)
            if caller:
                self.face.show_for(5, who=caller)
            join = await asyncio.wait_for(self._bring_up(wake_phrase), self.start_timeout_s)
            self.state = "ACTIVE"
            self.last_speech = time.monotonic()
            log(f"session active in channel {join.channel!r} after {self.last_speech - t0:.1f} s; "
                f"say {self.cfg['goodbye']['phrases'][0]!r} to end")
        except Exception as e:  # includes the timeout
            log(f"could not start session: {e!r}")
            for stop in (self.bridge.stop, self.backend.stop):  # whatever got half-started
                try:
                    await stop()
                except Exception as stop_error:
                    log(f"cleanup after a failed start: {stop_error!r}")
            self.state = "IDLE"
            self.kws.reset()
            self.kws.voice_events()
            if isinstance(e, ConnectionError):  # called while there is no connection: say so, in words
                self.told.pop("offline", None)
                self._tell("offline")
            else:
                self._chime(rising=False)

    async def _bring_up(self, wake_phrase: str):
        if not self.online and not await asyncio.to_thread(reachable, tuple(self.net.get("hosts", LOOK_AT))):
            raise ConnectionError("no connection to the internet")  # looked again, to be sure: still none
        join = await self.backend.start(wake_phrase)
        await self.bridge.start(join)
        return join

    async def end_session(self, reason: str) -> None:
        if self.state == "IDLE":
            return
        if self._start_task and not self._start_task.done():
            await self._start_task  # let a half-started session finish so it can be stopped cleanly
        self.state = "STOPPING"
        log(f"ending session: {reason}")
        if self.barged_at is not None:  # never leave the speaker silent after a session
            self.barged_at = None
            await self._hush(False)
        await self.bridge.stop()
        await self.backend.stop()
        self.kws.reset()
        self.state = "IDLE"
        self.kws.track_voices(False)
        self.kws.voice_events()  # whoever spoke last in this session is not the next one's caller
        self.bye_until = time.monotonic() + 3
        self.face.set(level=0, word="", note="", more="", flag="", caption="", say="", aloud=False, mood="neutral", who="")
        self._chime(rising=False)
        self._tell_what_is_owed()
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
