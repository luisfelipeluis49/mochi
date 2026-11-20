"""Who starts and stops the Agora session once the wake phrase is heard.

The supervisor only needs `await start(wake_phrase) -> JoinInfo` and `await stop()`. Two implementations:

- TestAgentBackend: Mochi's own agent, started directly at Agora (managed STT/LLM/TTS): its
  character, bilingual, with a face, able to change the speaker volume, tell its temperature and
  learn voices. Everything in [test_agent]. Needs AGORA_APP_ID + AGORA_APP_CERTIFICATE.
- MochiBackend: the session belongs to Luis's backend (AGENTS.md 6.4). The Pi asks it to start and
  stop (POST /api/sessions/demo/start|stop) and keeps reading GET /api/devices/{device_id}/state:
  the backend can end the session. Who talks is [backend].agent:
    "character": Mochi's own agent (the TestAgentBackend above) does the talking, and every
                 sentence it hears is reported to the backend (POST /api/devices/{id}/turns), which
                 decides the hints and saved words for the other screens.
    "backend":   the backend's agent talks (quiet by default), and the Pi joins the channel the
                 device state names.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import urllib.request
import warnings
from dataclasses import dataclass

from .device import Device

warnings.filterwarnings("ignore", category=UserWarning)  # agora-agents pydantic v1-style config


@dataclass
class JoinInfo:
    app_id: str
    channel: str
    uid: int
    token: str | None


# What the stand-in agent is told about its body, on top of [test_agent].instructions. The agent runs
# in Agora's cloud and cannot reach the Pi, so it acts by writing silent tags that the TTS skips
# (skip_patterns) and the Pi picks up from the conversation history about a second later.
ABILITIES = """

You are heard through a small speaker, not read. You understand and speak English and Brazilian
Portuguese: follow the language of the person who just spoke, even when it changes mid-conversation.

Mixing languages. Your voice pronounces each sentence in one language, so a Portuguese word dropped
into an English sentence comes out with an English accent (and the other way round). Mix the way a
bilingual friend does, sentence by sentence: give the other-language word a short sentence of its
own, in its own language, with at least three or four words around it.
- Not "Window is janela in Portuguese."  but "Window? Em português a gente fala janela."
- Not "Fila é queue em inglês."          but "Fila? In English we say queue."
- Not "Try saying obrigado to Ana."      but "Now thank Ana. Fala obrigado pra ela!"

What you hear is a machine transcript of speech, and it stumbles exactly where people mix languages:
a word of the other language is often written as something that only sounds like it ("guardy shoe"
for guarda-chuva, "the fair" for a feira, "desfila" for diz fila). Read odd words by their sound,
work out what the person meant from the rest of the sentence, and answer that. If you cannot tell,
ask them to say the word again.

Silent commands. Text in square brackets is never spoken; it moves your body. Put commands at the
very start of a reply, never mention them, and use square brackets for nothing else.
- [mood X] Begin EVERY reply with the feeling that fits it. X must be one of exactly these: happy,
  excited, love, laughing, surprised, curious, proud, oops, cool, sleepy. Vary it; it shows on your
  face, and they are looking at it. "oops" is only for your own mistakes: when a learner slips, your
  face stays encouraging (happy, curious, proud of the try).
- [show WORD] Whenever you teach, confirm or correct a word or short expression, also show it on your
  screen: the word in the language being learned, at most three words, e.g. [show umbrella].
  Never show a word while you are still giving a clue for it: that gives the answer away.
- [volume N] Changes how loud you speak. N is the new level from {min_volume} (quietest) to 100
  (loudest). "Louder" or "mais alto" means about 20 more than now, "quieter" or "mais baixo" about 20
  less. Then confirm in a few words.
- [temp] Add this when you tell your temperature. You can feel your own temperature (your
  processor's), given below, in degrees Celsius. It is not the room or the weather.
- [enroll NAME LANG] You can learn to recognise a voice. When someone asks you to learn, remember or
  save their voice and you know their name, write this command (LANG is pt or en, the language
  they are speaking) and ask them to keep talking to you for about ten seconds, for example about
  their day, so you can learn how they sound. If they did not say their name, ask for it first and
  write the command only once you have it. Example: "[mood excited][enroll Ana pt] Oba, Ana! Me
  conta como foi o seu dia, uns dez segundinhos, pra eu aprender a sua voz."
- [forget NAME] When someone asks you to forget their voice.
Further down you are told whose voices you know and, when you recognise it, who is talking right
now. Use the name now and then, the way a friend would, not in every sentence.
Examples: "[mood cool][volume 80] Louder it is!"   "[mood sleepy][temp] Estou com cinquenta e dois graus, quentinho."
"""
STATUS = """Right now your speaker volume is {volume} of 100 and your temperature is {temp} degrees Celsius.
{voices}

Before every reply, check three things:
1. It starts with [mood ...].
2. It is in the language of the sentence you just heard. A Portuguese sentence gets a Portuguese
   reply even if everything before it was English, and an English sentence gets an English reply.
3. It is at most two short sentences, and it does not ask anyone to repeat a corrected sentence."""
TAG = re.compile(r"\[\s*(volume|mood|show|temp|enroll|forget)\b\s*:?\s*([^\]]*?)\s*\]", re.I)
PORTUGUESE_CUES = {"oi", "ola", "olá", "alo", "alô", "e", "bom", "boa", "tchau"}


def _moved(now: tuple[int | None, int | None], told: tuple[int | None, int | None]) -> bool:
    """Worth telling the agent again: the volume changed, or it warmed / cooled by 2 degrees."""
    (volume, temp), (told_volume, told_temp) = now, told
    if volume != told_volume:
        return True
    if temp is None or told_temp is None:
        return temp != told_temp
    return abs(temp - told_temp) >= 2


class HeardTurns:
    """Picks what people said out of the agent's conversation history: each sentence once, and only
    when it is finished (the history gives every sentence the moment its speech started)."""

    def __init__(self):
        self._reported: set[int] = set()

    def new(self, items) -> list[str]:
        """items: the history, oldest first. Returns the sentences not returned before."""
        fresh = []
        for i, item in enumerate(items):
            started = getattr(item, "speech_start_ms", None)
            if str(item.role) != "user" or not item.content or started is None or started in self._reported:
                continue
            if getattr(item, "speech_end_ms", None) is None and i == len(items) - 1:
                continue  # still being said
            self._reported.add(started)
            fresh.append(item.content.strip())
        return fresh


class TestAgentBackend:
    """Mochi's own agent, started directly at Agora. Alone it is the stand-in for Luis's backend;
    inside MochiBackend it is the one who talks while the backend runs the session."""

    def __init__(self, cfg: dict, device: Device, on_event=None, on_turn=None):
        """on_event(kind, value): told what the agent did or asked for.
        kind is "mood" | "show" | "volume" | "temp" | "enroll" (value: (name, "pt" | "en")) | "forget".
        on_turn(text): told every finished sentence a person said."""
        self.cfg = cfg  # the [test_agent] table
        self.device = device
        self.on_event = on_event or (lambda kind, value: None)
        self.on_turn = on_turn
        self.app_id = os.environ.get("AGORA_APP_ID")
        self.cert = os.environ.get("AGORA_APP_CERTIFICATE")
        if not self.app_id or not self.cert:
            raise SystemExit("Set AGORA_APP_ID and AGORA_APP_CERTIFICATE in hardware/pi-bridge/.env")
        self._session = None
        self._watcher: asyncio.Task | None = None
        self.known_voices: list[str] = []   # set_voices(): whose voices the Pi knows...
        self.speaker: str | None = None     # ...and who it hears right now
        self._told: tuple[int | None, int | None] = (None, None)

    def _status(self) -> tuple[int | None, int | None]:
        temp = self.device.temperature()
        return self.device.volume(), None if temp is None else round(temp)

    def _instructions(self, status: tuple[int | None, int | None]) -> str:
        volume, temp = status
        if not self.known_voices:
            voices = "You do not know anyone's voice yet."
        else:
            voices = f"Voices you know: {', '.join(self.known_voices)}. " + (
                f"The person talking to you right now is {self.speaker}." if self.speaker
                else "You do not recognise the voice talking right now.")
        return (self.cfg["instructions"].rstrip() + ABILITIES.format(min_volume=self.device.min_volume)
                + STATUS.format(volume="unknown" if volume is None else volume,
                                temp="unknown" if temp is None else temp, voices=voices))

    # --- voices: the Pi recognises who is talking (speakers.py) and tells the agent here -----
    def set_voices(self, known: list[str], speaker: str | None) -> None:
        """Called whenever the Pi recognises a (different) speaker or learns / forgets a voice."""
        if (known, speaker) == (self.known_voices, self.speaker):
            return
        self.known_voices, self.speaker = list(known), speaker
        if self._session:
            asyncio.create_task(self._tell(self._told))

    async def _tell(self, status: tuple[int | None, int | None]) -> None:
        """Give the agent its current instructions (they end with what is true right now)."""
        try:
            await self._session.update({"llm": {"system_messages": [
                {"role": "system", "content": self._instructions(status)}]}})
            self._told = status
        except Exception as e:
            print(f"[mochi] could not update the agent: {e!r}"[:300], flush=True)

    async def voice_enrolled(self, name: str, lang: str, learned: bool) -> None:
        """Say out loud that a voice was learned (or that it did not work)."""
        lines = {(True, "pt"): "Pronto, {name}! Agora eu conheço a sua voz.",
                 (True, "en"): "Got it, {name}! I know your voice now.",
                 (False, "pt"): "Desculpa, {name}, não ouvi o bastante. Pede de novo e fala um pouquinho mais.",
                 (False, "en"): "Sorry, {name}, I didn't hear enough. Ask me again and talk a little longer."}
        try:
            await self._session.say(lines[(learned, "pt" if lang == "pt" else "en")].format(name=name), priority="APPEND")
        except Exception as e:
            print(f"[mochi] could not say it: {e!r}"[:300], flush=True)

    def _stt(self):
        """The ears. Agora-managed choices: Deepgram nova-3 / nova-2, or Agora's own ARES."""
        from agora_agent.agentkit.vendors import AresSTT, DeepgramSTT
        c = self.cfg
        if c.get("stt_vendor", "deepgram") == "ares":  # its languages go in turn_detection (see start)
            return AresSTT(keywords=c.get("stt_keywords"))
        # "multi": one recogniser for English and Portuguese, also when they mix in a sentence
        return DeepgramSTT(model=c.get("stt_model", "nova-3"), language=c.get("stt_language", "multi"),
                           keyterm=c.get("stt_keyterm"), additional_params=c.get("stt_params"))

    def _tts(self):
        """The voice. Agora-managed choices: MiniMax speech-2.6 / 2.8-turbo, or OpenAI tts-1.
        skip_patterns 4: text in [square brackets] (the silent commands) is not spoken."""
        from agora_agent.agentkit.vendors import MiniMaxTTS, OpenAITTS
        c = self.cfg
        if c.get("tts_vendor", "minimax") == "openai":
            return OpenAITTS(model="tts-1", voice=c.get("voice", "nova"), skip_patterns=[4])
        return MiniMaxTTS(model=c.get("tts_model", "speech_2_6_turbo"),
                          voice_id=c.get("voice", "English_captivating_female1"),
                          language_boost=c.get("tts_language_boost", "auto"), skip_patterns=[4])

    async def start(self, wake_phrase: str | None = None) -> JoinInfo:
        from agora_agent import Area, AsyncAgora
        from agora_agent.agentkit import Agent
        from agora_agent.agentkit.token import generate_convo_ai_token
        from agora_agent.agentkit.vendors import OpenAI

        c = self.cfg
        channel, bridge_uid = c["channel"], int(c["bridge_uid"])
        # greet in the language Mochi was called in
        cue = (wake_phrase or "").lower().split()[:1]
        greeting = c.get("greeting_pt", "Oi! Pode falar.") if cue and cue[0] in PORTUGUESE_CUES else c.get("greeting", "Yes?")
        token = generate_convo_ai_token(app_id=self.app_id, app_certificate=self.cert,
                                        channel_name=channel, uid=bridge_uid, token_expire=3600)
        client = AsyncAgora(area=Area.US, app_id=self.app_id, app_certificate=self.cert)
        status = self._told = self._status()
        turn_detection = {"config": {
            "speech_threshold": 0.5,
            "start_of_speech": {"mode": "vad", "vad_config": {"interrupt_duration_ms": 160, "prefix_padding_ms": 300}},
            "end_of_speech": {"mode": "vad", "vad_config": {"silence_duration_ms": 480}},
        }}
        if c.get("stt_vendor", "deepgram") == "ares":
            turn_detection["language"] = [x.strip() for x in c.get("stt_language", "en-US,pt-BR").split(",")]
        agent = (
            Agent(
                client=client,
                instructions=self._instructions(status),
                greeting=greeting,
                failure_message="Sorry, one moment.",
                max_history=20,
                # Same voice-activity settings as Agora's official quickstart.
                turn_detection=turn_detection,
                parameters={"enable_error_message": True},
            )
            .with_stt(self._stt())
            .with_llm(OpenAI(model=c.get("llm_model", "gpt-4o-mini"), greeting_message=greeting,
                             failure_message="Sorry, one moment.", max_history=20,
                             max_tokens=256, temperature=0.7))
            .with_tts(self._tts())
        )
        self._session = agent.create_async_session(
            channel=channel, agent_uid=str(c["agent_uid"]), remote_uids=[str(bridge_uid)],
            enable_string_uid=False, idle_timeout=30, expires_in=3600,
        )
        agent_id = await self._session.start()
        print(f"[mochi] test agent {agent_id} started in '{channel}'", flush=True)
        self._watcher = asyncio.create_task(self._watch())
        return JoinInfo(self.app_id, channel, bridge_uid, token)

    async def _act(self, kind: str, value: str) -> None:
        """Carry out one silent command the agent wrote."""
        if kind == "volume":
            if not value.isdigit():
                return
            now = await asyncio.to_thread(self.device.set_volume, int(value))
            print(f"[mochi] volume -> {now} (agent asked for {value})", flush=True)
            self.on_event("volume", now)
        elif kind == "temp":
            self.on_event("temp", await asyncio.to_thread(self.device.temperature))
        elif kind == "enroll":
            words = value.split()
            lang = words.pop().lower() if len(words) > 1 and words[-1].lower() in ("pt", "en") else "en"
            if words:
                self.on_event("enroll", (" ".join(words).title(), lang))
        elif value:
            self.on_event(kind, value.lower() if kind == "mood" else value)

    async def _watch(self) -> None:
        """While the session runs: carry out the commands in the agent's latest reply, and keep the
        agent's idea of its volume and temperature current."""
        reply, done = "", set()  # the reply being read (it grows while it is generated), commands done
        heard = HeardTurns()
        complained = False
        while True:
            await asyncio.sleep(0.7)
            try:
                history = await self._session.get_history()
                if self.on_turn:
                    for sentence in heard.new(history.contents or []):
                        self.on_turn(sentence)
                last = next((m.content for m in reversed(history.contents or [])
                             if str(m.role) == "assistant" and m.content), "")
                if last != reply:
                    if not (reply and last.startswith(reply)):
                        done = set()  # a new reply, not more of the same one
                    reply = last
                    for tag in TAG.finditer(last):
                        if tag.group(0) not in done:
                            done.add(tag.group(0))
                            await self._act(tag.group(1).lower(), tag.group(2))
                status = await asyncio.to_thread(self._status)
                if _moved(status, self._told):
                    await self._tell(status)
                complained = False
            except asyncio.CancelledError:
                raise
            except Exception as e:  # a failed poll must not end the session; say so once
                if not complained:
                    print(f"[mochi] agent watcher: {e!r}"[:300], flush=True)
                    complained = True

    async def stop(self) -> None:
        if self._watcher:
            self._watcher.cancel()
            try:
                await self._watcher
            except BaseException:
                pass
            self._watcher = None
        if self._session:
            try:
                await self._session.stop()
            except Exception as e:  # already gone (idle timeout etc.)
                print(f"[mochi] agent stop: {e}", flush=True)
            self._session = None


class MochiBackend:
    """The session belongs to Luis's backend (AGENTS.md 6.4): the Pi asks it to start one, then reads
    the device state a few times a second and does what it says.

    - capturing false (someone stopped the session elsewhere): on_event("stopped", why), and the
      supervisor leaves the channel.
    - speaker_muted: the speaker is silenced until it is false again (the backend's fallback for
      keeping its own agent quiet).

    With `agent` (a TestAgentBackend) Mochi's own agent does the talking: the backend starts none,
    and is told every sentence the agent hears, so it can decide hints and saved words. Mochi then
    also talks when the backend cannot be reached, just without those.
    """

    def __init__(self, base_url: str, device_id: str, device: Device | None = None, on_event=None,
                 poll_interval_s: float = 0.3, session_id: str = "demo", agent: TestAgentBackend | None = None):
        self.base = base_url.rstrip("/")
        self.device_id = device_id
        self.device = device
        self.on_event = on_event or (lambda kind, value: None)
        self.poll_interval_s = poll_interval_s
        self.session_id = session_id
        self.agent = agent
        if agent:
            agent.on_turn = self._heard
        self._poller: asyncio.Task | None = None
        self._reporter: asyncio.Task | None = None
        self._sentences: asyncio.Queue[str] = asyncio.Queue()
        self._muted = False
        self._linked = False  # the backend knows about this session
        self._stopped_by_backend = False

    def _req(self, method: str, path: str, timeout: float = 10, body: dict | None = None) -> dict:
        payload = json.dumps(body or {}).encode() if method == "POST" else None
        req = urllib.request.Request(self.base + path, method=method,
                                     headers={"Content-Type": "application/json"}, data=payload)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            reply = r.read()
            return json.loads(reply) if reply else {}

    def _state(self, timeout: float = 10) -> dict:
        return self._req("GET", f"/api/devices/{self.device_id}/state", timeout)

    async def _capturing(self) -> dict:
        """Waits up to ~10 s for the backend to say the session is on; returns the device state."""
        for _ in range(50):
            state = await asyncio.to_thread(self._state)
            if state.get("capturing") and state.get("agora"):
                return state
            await asyncio.sleep(0.2)
        raise RuntimeError("backend did not report capturing=true with agora join info")

    async def start(self, wake_phrase: str | None = None) -> JoinInfo:
        self._stopped_by_backend = self._linked = False
        path = f"/api/sessions/{self.session_id}/start"
        if not self.agent:
            await asyncio.to_thread(self._req, "POST", path)
            a = (await self._capturing())["agora"]
            self._linked = True
            self._poller = asyncio.create_task(self._poll())
            return JoinInfo(a["app_id"], a["channel"], int(a["uid"]), a.get("token"))
        try:  # Mochi's own agent talks; the backend only has to know the session is on
            await asyncio.to_thread(self._req, "POST", path, 10, {"agent": "device"})
            await self._capturing()
            self._linked = True
        except Exception as e:
            print(f"[mochi] backend not reachable, talking without it (no hints on other screens): {e!r}"[:300],
                  flush=True)
        join = await self.agent.start(wake_phrase)
        if self._linked:
            self._poller = asyncio.create_task(self._poll())
            self._reporter = asyncio.create_task(self._report())
        return join

    # --- with Mochi's own agent: what the supervisor tells it, and what it hears ---------------
    def set_voices(self, known: list[str], speaker: str | None) -> None:
        if self.agent:
            self.agent.set_voices(known, speaker)

    async def voice_enrolled(self, name: str, lang: str, learned: bool) -> None:
        if self.agent:
            await self.agent.voice_enrolled(name, lang, learned)

    def _heard(self, sentence: str) -> None:
        if self._linked:
            self._sentences.put_nowait(sentence)

    async def _report(self) -> None:
        """Tell the backend each finished sentence, in order. It answers with what it decided."""
        failing = False
        while True:
            sentence = await self._sentences.get()
            try:
                reply = await asyncio.to_thread(self._req, "POST", f"/api/devices/{self.device_id}/turns", 5,
                                                {"text": sentence})
                decision = reply.get("decision") or {}
                hint = (decision.get("hint") or {}).get("expression")
                print(f"[mochi] backend heard {sentence!r}: {decision.get('decision')}"
                      + (f", hint {hint!r}" if hint else ""), flush=True)
                failing = False
            except Exception as e:  # a lost sentence must not end the session; say so once
                if not failing:
                    print(f"[mochi] backend turns: {e!r}"[:300], flush=True)
                    failing = True

    async def _mute(self, muted: bool) -> None:
        if muted != self._muted:
            self._muted = muted
            if self.device:
                await asyncio.to_thread(self.device.set_muted, muted)

    async def _poll(self) -> None:
        """While the session runs: follow the device state."""
        failing = False
        while True:
            await asyncio.sleep(self.poll_interval_s)
            try:
                state = await asyncio.to_thread(self._state, 3)
            except Exception as e:  # a failed poll must not end the session; say so once
                if not failing:
                    print(f"[mochi] backend state: {e!r}"[:300], flush=True)
                    failing = True
                continue
            if failing:
                print("[mochi] backend state: reachable again", flush=True)
                failing = False
            if not (state.get("capturing") and state.get("agora")):
                self._stopped_by_backend = True
                self.on_event("stopped", "backend stopped capturing")
                return
            await self._mute(bool(state.get("speaker_muted")))

    async def stop(self) -> None:
        for task in (self._poller, self._reporter):
            if task:
                task.cancel()
                try:
                    await task
                except BaseException:
                    pass
        self._poller = self._reporter = None
        self._sentences = asyncio.Queue()
        await self._mute(False)  # never leave the speaker silent after a session
        if self.agent:
            await self.agent.stop()
        if self._stopped_by_backend or (self.agent and not self._linked):
            # Already stopped there (asking again could end a session someone has just started),
            # or it never knew about this one.
            self._stopped_by_backend = False
            return
        try:
            await asyncio.to_thread(self._req, "POST", f"/api/sessions/{self.session_id}/stop")
        except Exception as e:  # unreachable: the supervisor must still get back to listening
            print(f"[mochi] backend stop: {e!r}"[:300], flush=True)


def make_backend(cfg: dict, on_event=None):
    b = cfg["backend"]
    if b["kind"] == "test_agent":
        return TestAgentBackend(cfg["test_agent"], Device(cfg["audio"]), on_event)
    if b["kind"] == "mochi_backend":
        device, agent = Device(cfg["audio"]), None
        if b.get("agent", "character") == "character":
            agent = TestAgentBackend(cfg["test_agent"], device, on_event)
        elif b["agent"] != "backend":
            raise SystemExit(f"unknown backend.agent {b['agent']!r}")
        return MochiBackend(b["mochi_backend_url"], b["device_id"], device, on_event,
                            float(b.get("poll_interval_s", 0.3)), agent=agent)
    raise SystemExit(f"unknown backend.kind {b['kind']!r}")
