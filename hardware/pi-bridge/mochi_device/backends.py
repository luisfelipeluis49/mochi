"""Who starts and stops the Agora session once the wake phrase is heard.

The supervisor only needs `await start(wake_phrase) -> JoinInfo` and `await stop()`. Two implementations:

- TestAgentBackend: starts a stand-in Agora agent directly (managed STT/LLM/TTS), bilingual, able
  to change the speaker volume and tell its temperature. For testing and demos before Luis's
  backend exists. Needs AGORA_APP_ID + AGORA_APP_CERTIFICATE.
- MochiBackend: the real path. Calls Luis's endpoints from AGENTS.md 6.4
  (POST /api/sessions/demo/start|stop), reads the join info from
  GET /api/devices/{device_id}/state, and keeps reading that state while the session runs: the
  backend can end the session, silence the speaker, and move Mochi's body (the `commands` in the
  state: face, volume, temperature, voices). The Pi reports its volume, temperature and the voices
  it knows (POST .../status, .../voices). No agent logic here: that stays in services/backend.
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
- Not "Try saying obrigado to me."       but "Now thank me. Fala obrigado pra mim!"
- Not "Now tell me qual é o seu favorito!" but "Now tell me. Qual é o seu favorito?"
When someone asks how a word is pronounced, or says you said it wrong, say just that word or phrase
again as a short sentence of its own, in its language ("Molho para salada."). Never spell sounds out
with hyphens or capital letters: your voice would read the letters.

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
  write the command only once you have it. Examples: "[mood excited][enroll Ana pt] Oba, Ana! Me
  conta como foi o seu dia, uns dez segundinhos, pra eu aprender a sua voz." (she spoke Portuguese)
  "[mood excited][enroll Ben en] Nice, Ben! Tell me about your day for about ten seconds, so I can
  learn your voice." (he spoke English)
- [forget NAME] When someone asks you to forget their voice.
Further down you are told whose voices you know and, when you recognise it, who is talking right
now. Use the name now and then, the way a friend would, not in every sentence.
Examples: "[mood cool][volume 80] Louder it is!"
"[mood sleepy][temp] I'm at fifty-two degrees, nice and warm." (asked in English)
"[mood sleepy][temp] Estou com cinquenta e dois graus, quentinho." (asked in Portuguese)
"""
STATUS = """Right now your speaker volume is {volume} of 100 and your temperature is {temp} degrees Celsius.
{voices}

Before every reply, check three things:
1. It starts with [mood ...].
2. It is in the language of the sentence you just heard. A Portuguese sentence gets a Portuguese
   reply even if everything before it was English, and an English sentence gets an English reply.
3. It is at most two short sentences, and it does not ask anyone to repeat a corrected sentence.
4. No sentence mixes the two languages: a word or phrase from the other language is a short sentence
   of its own, in that language.
5. It uses a name only if you were told it or recognise the voice, and it does not send anyone to a
   partner you do not know is there."""
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


def read_status(device) -> tuple[int | None, int | None]:
    """(speaker volume 0-100, temperature in whole degrees); None for what cannot be read."""
    temp = device.temperature()
    return device.volume(), None if temp is None else round(temp)


class Body:
    """Carries out what Mochi asks of its body (the silent commands) and tells the supervisor,
    which shows it on the face. Used whoever runs the agent."""

    def __init__(self, device: Device, on_event=None):
        """on_event(kind, value): kind is "mood" | "show" | "volume" | "temp" |
        "enroll" (value: (name, "pt" | "en")) | "forget"."""
        self.device = device
        self.on_event = on_event or (lambda kind, value: None)

    async def act(self, kind: str, value: str) -> None:
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


class TestAgentBackend:
    """Stand-in for Luis's agent. TESTING AND DEMO ONLY."""

    def __init__(self, cfg: dict, device: Device, on_event=None):
        """on_event(kind, value): told what the agent did or asked for.
        kind is "mood" | "show" | "volume" | "temp" | "enroll" (value: (name, "pt" | "en")) | "forget"."""
        self.cfg = cfg  # the [test_agent] table
        self.device = device
        self.on_event = on_event or (lambda kind, value: None)
        self.body = Body(device, self.on_event)
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
        return read_status(self.device)

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
        await self.body.act(kind, value)

    async def _watch(self) -> None:
        """While the session runs: carry out the commands in the agent's latest reply, and keep the
        agent's idea of its volume and temperature current."""
        reply, done = "", set()  # the reply being read (it grows while it is generated), commands done
        complained = False
        while True:
            await asyncio.sleep(0.7)
            try:
                history = await self._session.get_history()
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
    """Real path via Luis's backend (AGENTS.md 6.4). The backend owns the session and decides what
    Mochi says: the Pi asks it to start one, then reads the device state a few times a second and
    does what it says.

    - capturing false (someone stopped the session elsewhere): on_event("stopped", why), and the
      supervisor leaves the channel.
    - speaker_muted: the speaker is silenced until it is false again (the backend's fallback for
      keeping the agent quiet).
    - commands: what Mochi wants its body to do (mood, show, volume, temp, enroll, forget), each
      carried out once (see Body).

    The other way, the Pi reports its volume, temperature, the voices it knows and who is talking
    whenever one changes, and how learning a voice ended.
    """

    STATUS_EVERY_S = 1.0  # how often the volume and temperature are read while a session runs

    def __init__(self, base_url: str, device_id: str, device: Device | None = None, on_event=None,
                 poll_interval_s: float = 0.3, session_id: str = "demo"):
        self.base = base_url.rstrip("/")
        self.device_id = device_id
        self.device = device
        self.on_event = on_event or (lambda kind, value: None)
        self.body = Body(device, self.on_event)
        self.poll_interval_s = poll_interval_s
        self.session_id = session_id
        self._poller: asyncio.Task | None = None
        self._muted = False
        self._stopped_by_backend = False
        self._done: set[str] = set()  # commands already carried out in this session
        self._voices: tuple[list[str], str | None] = ([], None)
        self._told = None  # the last status the backend was given
        self._status_failing = False

    def _req(self, method: str, path: str, timeout: float = 10, body: dict | None = None) -> dict:
        payload = json.dumps(body or {}).encode() if method == "POST" else None
        req = urllib.request.Request(self.base + path, method=method,
                                     headers={"Content-Type": "application/json"}, data=payload)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            reply = r.read()
            return json.loads(reply) if reply else {}

    def _state(self, timeout: float = 10) -> dict:
        return self._req("GET", f"/api/devices/{self.device_id}/state", timeout)

    async def start(self, wake_phrase: str | None = None) -> JoinInfo:
        self._stopped_by_backend = False
        self._done, self._told = set(), None
        await self._report()  # so Mochi's first words already know how loud and warm it is
        body = {"woken_by": wake_phrase} if wake_phrase else {}
        await asyncio.to_thread(self._req, "POST", f"/api/sessions/{self.session_id}/start", 10, body)
        for _ in range(50):  # wait up to ~10 s for the backend to publish join info
            state = await asyncio.to_thread(self._state)
            if state.get("capturing") and state.get("agora"):
                a = state["agora"]
                self._poller = asyncio.create_task(self._poll())
                return JoinInfo(a["app_id"], a["channel"], int(a["uid"]), a.get("token"))
            await asyncio.sleep(0.2)
        raise RuntimeError("backend did not report capturing=true with agora join info")

    # --- what the Pi tells the backend ------------------------------------------------------
    def set_voices(self, known: list[str], speaker: str | None) -> None:
        """Called whenever the Pi recognises a (different) speaker or learns / forgets a voice."""
        self._voices = (list(known), speaker)

    async def voice_enrolled(self, name: str, lang: str, learned: bool) -> None:
        """Learning a voice ended; the backend has Mochi say so."""
        body = {"name": name, "language": "pt" if lang == "pt" else "en", "learned": learned}
        try:
            await asyncio.to_thread(self._req, "POST", f"/api/devices/{self.device_id}/voices", 5, body)
        except Exception as e:
            print(f"[mochi] backend voices: {e!r}"[:300], flush=True)

    async def _report(self) -> None:
        """Tell the backend the volume, temperature and voices, if any of them changed."""
        volume, temp = await asyncio.to_thread(read_status, self.device) if self.device else (None, None)
        known, speaker = self._voices
        status = {"volume": volume, "temperature": temp, "voices": known, "speaker": speaker}
        told = self._told
        if told and (known, speaker) == (told["voices"], told["speaker"]) \
                and not _moved((volume, temp), (told["volume"], told["temperature"])):
            return
        try:
            await asyncio.to_thread(self._req, "POST", f"/api/devices/{self.device_id}/status", 5, status)
            self._status_failing = False
        except Exception as e:  # not worth a session: Mochi just knows a little less about itself
            if not self._status_failing:
                print(f"[mochi] backend status: {e!r}"[:300], flush=True)
            self._status_failing = True
        self._told = status  # either way: try again only when something changes

    async def _obey(self, commands: list[dict]) -> None:
        for command in commands:
            if command.get("command_id") in self._done:
                continue
            self._done.add(command.get("command_id"))
            await self.body.act(str(command.get("kind", "")).lower(), str(command.get("value", "")))

    async def _mute(self, muted: bool) -> None:
        if muted != self._muted:
            self._muted = muted
            if self.device:
                await asyncio.to_thread(self.device.set_muted, muted)

    async def _poll(self) -> None:
        """While the session runs: follow the device state, and keep the backend up to date."""
        failing, since_status = False, 0.0
        while True:
            await asyncio.sleep(self.poll_interval_s)
            since_status += self.poll_interval_s
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
            await self._obey(state.get("commands") or [])
            if since_status >= self.STATUS_EVERY_S:
                since_status = 0.0
                await self._report()

    async def stop(self) -> None:
        if self._poller:
            self._poller.cancel()
            try:
                await self._poller
            except BaseException:
                pass
            self._poller = None
        await self._mute(False)  # never leave the speaker silent after a session
        if self._stopped_by_backend:
            # It is already stopped there. Asking again could end a session someone has just started.
            self._stopped_by_backend = False
            return
        try:
            await asyncio.to_thread(self._req, "POST", f"/api/sessions/{self.session_id}/stop")
        except Exception as e:  # unreachable: the supervisor must still get back to listening
            print(f"[mochi] backend stop: {e!r}"[:300], flush=True)


class WithFallback:
    """The backend runs the session when it can. When it cannot start one (it is down, or cannot be
    reached), Mochi's own agent runs that session instead, so Mochi always answers when called."""

    def __init__(self, backend, own_agent):
        self.backend, self.own_agent = backend, own_agent
        self.active = None  # whoever runs the current session

    async def start(self, wake_phrase: str | None = None) -> JoinInfo:
        try:
            join = await self.backend.start(wake_phrase)
            self.active = self.backend
            return join
        except Exception as e:
            print(f"[mochi] the backend could not start a session ({e!r}); Mochi's own agent takes this one"[:300],
                  flush=True)
        self.active = self.own_agent
        return await self.own_agent.start(wake_phrase)

    async def stop(self) -> None:
        active, self.active = self.active, None
        if active:
            await active.stop()

    def set_voices(self, known: list[str], speaker: str | None) -> None:
        self.backend.set_voices(known, speaker)
        self.own_agent.set_voices(known, speaker)

    async def voice_enrolled(self, name: str, lang: str, learned: bool) -> None:
        if self.active:
            await self.active.voice_enrolled(name, lang, learned)


def make_backend(cfg: dict, on_event=None):
    b = cfg["backend"]
    if b["kind"] == "test_agent":
        return TestAgentBackend(cfg["test_agent"], Device(cfg["audio"]), on_event)
    if b["kind"] == "mochi_backend":
        device = Device(cfg["audio"])
        backend = MochiBackend(b["mochi_backend_url"], b["device_id"], device, on_event,
                               float(b.get("poll_interval_s", 0.3)))
        if b.get("fallback", "test_agent") != "test_agent":
            return backend
        if not (os.environ.get("AGORA_APP_ID") and os.environ.get("AGORA_APP_CERTIFICATE")):
            print("[mochi] no fallback: Mochi's own agent needs AGORA_APP_ID and AGORA_APP_CERTIFICATE in .env",
                  flush=True)
            return backend
        return WithFallback(backend, TestAgentBackend(cfg["test_agent"], device, on_event))
    raise SystemExit(f"unknown backend.kind {b['kind']!r}")
