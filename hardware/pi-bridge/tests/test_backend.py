"""MochiBackend against a small local copy of the backend's HTTP surface (AGENTS.md 6.4).

Run:  .venv/bin/python -m unittest discover tests
"""
import asyncio
import json
import threading
import time
import subprocess
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import AsyncMock, MagicMock

from mochi_device.backends import TAG, Body, JoinInfo, MochiBackend, WithFallback
from mochi_device.main import Supervisor, hint_note

JOIN = {"app_id": "app", "channel": "mochi-demo", "uid": 1001, "token": "tok"}


class FakeBackend:
    """Answers start, stop and the device state the way services/backend does."""

    def __init__(self):
        self.capturing = self.speaker_muted = self.broken = False
        self.posts: list[str] = []      # session calls: "start" / "stop"
        self.bodies: list[dict] = []    # what each of those carried
        self.statuses: list[dict] = []  # what the device reported about itself
        self.voices: list[dict] = []    # voices it said it learned
        self.commands: list[dict] = []  # what Mochi wants its body to do
        self.auth: dict[str, list] = {}  # Authorization header seen, per POST action
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def reply(self, body: dict, code: int = 200):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                action = self.path.rsplit("/", 1)[1]
                fake.auth.setdefault(action, []).append(self.headers.get("Authorization"))
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                if action in ("status", "voices"):
                    (fake.statuses if action == "status" else fake.voices).append(body)
                    return self.reply({})
                fake.posts.append(action)
                fake.bodies.append(body)
                fake.capturing = action == "start"
                self.reply({})

            def do_GET(self):
                if fake.broken:
                    return self.reply({"detail": "boom"}, 500)
                self.reply({"capturing": fake.capturing, "agora": JOIN if fake.capturing else None,
                            "speaker_muted": fake.speaker_muted, "commands": fake.commands})

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class FakeSpeaker:
    """Mochi's body, as far as the backend path needs it."""

    def __init__(self):
        self.muted = False
        self.changes = 0
        self.level = 100
        self.degrees = 52.4

    def set_muted(self, muted: bool):
        self.muted = muted
        self.changes += 1

    def volume(self):
        return self.level

    def set_volume(self, percent: int):
        self.level = percent
        return self.level

    def temperature(self):
        return self.degrees


async def until(condition, seconds: float = 3) -> bool:
    """Waits for condition() to become true; says whether it did."""
    for _ in range(int(seconds / 0.02)):
        if condition():
            return True
        await asyncio.sleep(0.02)
    return condition()


class MochiBackendTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.fake = FakeBackend()
        self.addCleanup(self.fake.close)
        self.speaker = FakeSpeaker()
        self.events: list[tuple] = []
        self.backend = MochiBackend(self.fake.url, "home_pi_01", self.speaker,
                                    lambda kind, value: self.events.append((kind, value)),
                                    poll_interval_s=0.02)

    async def test_start_returns_what_the_bridge_joins_with(self):
        join = await self.backend.start()
        self.assertEqual((join.app_id, join.channel, join.uid, join.token), ("app", "mochi-demo", 1001, "tok"))
        await self.backend.stop()
        self.assertEqual(self.fake.posts, ["start", "stop"])

    async def test_session_stopped_elsewhere_is_noticed_and_not_stopped_again(self):
        await self.backend.start()
        await asyncio.sleep(0.1)
        self.assertEqual(self.events, [])  # still capturing: nothing to report
        self.fake.capturing = False  # someone pressed Stop in the web app
        self.assertTrue(await until(lambda: self.events))
        self.assertEqual(self.events[0][0], "stopped")
        await self.backend.stop()
        self.assertEqual(self.fake.posts, ["start"])  # no second stop: it could end a newer session

    async def test_next_session_after_a_backend_stop_is_stopped_normally(self):
        await self.backend.start()
        self.fake.capturing = False
        self.assertTrue(await until(lambda: self.events))
        await self.backend.stop()
        await self.backend.start()
        await self.backend.stop()
        self.assertEqual(self.fake.posts, ["start", "start", "stop"])

    async def test_speaker_follows_speaker_muted(self):
        await self.backend.start()
        self.fake.speaker_muted = True
        self.assertTrue(await until(lambda: self.speaker.muted))
        self.fake.speaker_muted = False
        self.assertTrue(await until(lambda: not self.speaker.muted))
        self.assertEqual(self.speaker.changes, 2)  # only when it changes, not on every poll

    async def test_speaker_is_never_left_muted_after_a_session(self):
        await self.backend.start()
        self.fake.speaker_muted = True
        self.assertTrue(await until(lambda: self.speaker.muted))
        await self.backend.stop()
        self.assertFalse(self.speaker.muted)

    async def test_failed_polls_do_not_end_the_session(self):
        await self.backend.start()
        self.fake.broken = True
        await asyncio.sleep(0.2)
        self.fake.broken = False
        await asyncio.sleep(0.1)
        self.assertEqual(self.events, [])
        await self.backend.stop()

    async def test_the_wake_phrase_is_passed_on(self):
        await self.backend.start("oi mochi")
        await self.backend.stop()
        await self.backend.start()
        await self.backend.stop()
        self.assertEqual(self.fake.bodies, [{"woken_by": "oi mochi"}, {}, {}, {}])

    async def test_commands_are_carried_out_once_each(self):
        await self.backend.start()
        self.fake.commands = [{"command_id": "cmd_1", "kind": "mood", "value": "Cool"},
                              {"command_id": "cmd_2", "kind": "volume", "value": "60"}]
        self.assertTrue(await until(lambda: len(self.events) == 2))
        self.fake.commands = self.fake.commands + [{"command_id": "cmd_3", "kind": "enroll", "value": "ana pt"},
                                                   {"command_id": "cmd_4", "kind": "temp", "value": ""}]
        self.assertTrue(await until(lambda: len(self.events) == 4))
        await asyncio.sleep(0.1)  # more polls of the same state: nothing is done twice
        self.assertEqual(self.events, [("mood", "cool"), ("volume", 60), ("enroll", ("Ana", "pt")), ("temp", 52.4)])
        self.assertEqual(self.speaker.level, 60)
        await self.backend.stop()

    async def test_the_backend_is_told_about_mochis_body_when_it_changes(self):
        self.backend.STATUS_EVERY_S = 0.05
        self.backend.set_voices(["Ana"], None)
        await self.backend.start()
        first = {"volume": 100, "temperature": 52, "voices": ["Ana"], "speaker": None}
        self.assertEqual(self.fake.statuses, [first])  # before the session starts
        await asyncio.sleep(0.2)
        self.assertEqual(len(self.fake.statuses), 1)   # nothing changed: nothing sent
        self.backend.set_voices(["Ana"], "Ana")
        self.assertTrue(await until(lambda: len(self.fake.statuses) == 2))
        self.speaker.level = 60
        self.assertTrue(await until(lambda: len(self.fake.statuses) == 3))
        self.assertEqual(self.fake.statuses[-1], {"volume": 60, "temperature": 52, "voices": ["Ana"], "speaker": "Ana"})
        await self.backend.stop()

    async def test_a_learned_voice_is_reported(self):
        await self.backend.voice_enrolled("Ana", "pt", True)
        await self.backend.voice_enrolled("Ben", "en", False)
        self.assertEqual(self.fake.voices, [{"name": "Ana", "language": "pt", "learned": True},
                                            {"name": "Ben", "language": "en", "learned": False}])

    async def test_unreachable_backend_fails_start_but_never_stop(self):
        await asyncio.to_thread(self.fake.close)
        with self.assertRaises(OSError):
            await self.backend.start()
        await self.backend.stop()  # must not raise: the supervisor has to get back to listening


class PollResilienceTest(unittest.IsolatedAsyncioTestCase):
    """One failing step in the poll loop must not end it (the microphone would keep streaming)."""

    def setUp(self):
        self.fake = FakeBackend()
        self.addCleanup(self.fake.close)
        self.speaker = FakeSpeaker()
        self.events: list[tuple] = []
        self.backend = MochiBackend(self.fake.url, "home_pi_01", self.speaker,
                                    lambda kind, value: self.events.append((kind, value)),
                                    poll_interval_s=0.02)
        self.backend.STATUS_EVERY_S = 0.05

    async def test_a_mixer_timeout_does_not_end_the_poller(self):
        broken = {"on": True}
        real = self.speaker.set_muted

        def set_muted(muted):
            if broken["on"]:
                raise subprocess.TimeoutExpired("amixer", 5)
            real(muted)
        self.speaker.set_muted = set_muted
        await self.backend.start()
        self.fake.speaker_muted = True
        await asyncio.sleep(0.2)
        self.assertFalse(self.backend._poller.done())
        broken["on"] = False
        self.assertTrue(await until(lambda: self.speaker.muted))  # it keeps trying
        self.fake.capturing = False                               # and still notices Stop
        self.assertTrue(await until(lambda: ("stopped", "backend stopped capturing") in self.events))
        await self.backend.stop()

    async def test_a_failing_status_read_does_not_end_the_poller(self):
        def volume():
            raise subprocess.TimeoutExpired("amixer", 5)
        self.speaker.volume = volume
        await self.backend.start()
        await asyncio.sleep(0.3)
        self.assertFalse(self.backend._poller.done())
        self.fake.capturing = False
        self.assertTrue(await until(lambda: self.events))
        await self.backend.stop()

    async def test_a_failing_command_does_not_end_the_poller(self):
        async def act(kind, value):
            raise RuntimeError("boom")
        self.backend.body.act = act
        await self.backend.start()
        self.fake.commands = [{"command_id": "c1", "kind": "mood", "value": "happy"}]
        await asyncio.sleep(0.2)
        self.assertFalse(self.backend._poller.done())
        await self.backend.stop()

    async def test_if_the_poller_dies_the_supervisor_is_told_so_the_mic_stops(self):
        async def boom(*a):
            raise MemoryError("unexpected")  # not caught by a step's own handler
        self.backend._sleep = boom
        await self.backend.start()
        self.assertTrue(await until(lambda: any(e[0] == "stopped" for e in self.events)))
        await self.backend.stop()
        self.assertEqual(self.fake.posts, ["start", "stop"])  # the backend session is still ended


class DeviceKeyTest(unittest.IsolatedAsyncioTestCase):
    """Once the backend asks for it, status and voices carry Authorization: Bearer <device key>."""

    def setUp(self):
        self.fake = FakeBackend()
        self.addCleanup(self.fake.close)

    async def test_the_key_is_sent_on_status_and_voices(self):
        backend = MochiBackend(self.fake.url, "home_pi_01", FakeSpeaker(), None, 0.02, device_key="s3cret")
        await backend.start()
        await backend.voice_enrolled("Ana", "en", True)
        await backend.stop()
        self.assertEqual(self.fake.auth["status"][0], "Bearer s3cret")
        self.assertEqual(self.fake.auth["voices"][0], "Bearer s3cret")
        self.assertEqual(self.fake.auth["start"], [None])  # the other calls do not carry it

    async def test_without_a_key_no_header_is_sent(self):
        backend = MochiBackend(self.fake.url, "home_pi_01", FakeSpeaker(), None, 0.02)
        await backend.start()
        await backend.voice_enrolled("Ana", "en", True)
        await backend.stop()
        self.assertEqual(self.fake.auth["status"], [None])
        self.assertEqual(self.fake.auth["voices"], [None])

    def test_make_backend_takes_the_key_from_the_environment_and_never_prints_it(self):
        import io
        import os
        from contextlib import redirect_stdout
        from unittest.mock import patch

        from mochi_device import config
        from mochi_device.backends import make_backend

        cfg = config.load()
        cfg["backend"].update(kind="mochi_backend", fallback="none")
        with patch.dict(os.environ, {"MOCHI_DEVICE_KEY": "s3cret"}), redirect_stdout(io.StringIO()) as out:
            backend = make_backend(cfg)
        self.assertEqual(backend.device_key, "s3cret")
        self.assertNotIn("s3cret", out.getvalue())
        self.assertNotIn("s3cret", repr(backend))


class FallbackConfigTest(unittest.TestCase):
    """The Pi-side agent holds the App Certificate and decides on the device: opt-in only."""

    def _cfg(self, **backend):
        from mochi_device import config
        cfg = config.load()
        cfg["backend"].update(kind="mochi_backend", **backend)
        return cfg

    def test_off_by_default(self):
        import os
        from unittest.mock import patch

        from mochi_device.backends import make_backend
        cfg = self._cfg()
        with patch.dict(os.environ, {"AGORA_APP_ID": "a", "AGORA_APP_CERTIFICATE": "c"}):
            self.assertIsInstance(make_backend(cfg), MochiBackend)

    def test_available_when_switched_on(self):
        import os
        from unittest.mock import patch

        from mochi_device.backends import make_backend
        cfg = self._cfg(fallback="test_agent")
        with patch.dict(os.environ, {"AGORA_APP_ID": "a", "AGORA_APP_CERTIFICATE": "c"}):
            self.assertIsInstance(make_backend(cfg), WithFallback)


class Runner:
    """Stands in for either backend; `broken` makes start fail."""

    def __init__(self, channel: str, broken: bool = False):
        self.channel, self.broken = channel, broken
        self.calls: list = []

    async def start(self, wake_phrase=None):
        self.calls.append(("start", wake_phrase))
        if self.broken:
            raise OSError("connection refused")
        return JoinInfo("app", self.channel, 1001, "tok")

    async def stop(self):
        self.calls.append("stop")

    def set_voices(self, known, speaker):
        self.calls.append(("voices", known, speaker))

    async def voice_enrolled(self, name, lang, learned):
        self.calls.append(("enrolled", name))


class WithFallbackTest(unittest.IsolatedAsyncioTestCase):
    async def test_the_backend_runs_the_session_when_it_can(self):
        backend, own = Runner("mochi-demo"), Runner("mochi-test")
        both = WithFallback(backend, own)
        self.assertEqual((await both.start("oi mochi")).channel, "mochi-demo")
        await both.voice_enrolled("Ana", "pt", True)
        await both.stop()
        self.assertEqual(backend.calls, [("start", "oi mochi"), ("enrolled", "Ana"), "stop"])
        self.assertEqual(own.calls, [])

    async def test_mochis_own_agent_takes_the_session_when_the_backend_cannot(self):
        backend, own = Runner("mochi-demo", broken=True), Runner("mochi-test")
        both = WithFallback(backend, own)
        self.assertEqual((await both.start("hi mochi")).channel, "mochi-test")
        await both.stop()
        self.assertEqual(own.calls, [("start", "hi mochi"), "stop"])
        self.assertEqual(backend.calls, [("start", "hi mochi"), "stop"])  # its half-started session is ended once
        backend.broken = False  # the backend is back: the next session is its again
        self.assertEqual((await both.start()).channel, "mochi-demo")

    async def test_a_backend_that_failed_after_its_post_is_stopped_before_the_own_agent_starts(self):
        backend, own = Runner("mochi-demo", broken=True), Runner("mochi-test")

        async def stop():
            backend.calls.append("stop")
            raise OSError("stop failed too")  # must be swallowed
        backend.stop = stop
        both = WithFallback(backend, own)
        self.assertEqual((await both.start("hi mochi")).channel, "mochi-test")
        self.assertEqual(backend.calls, [("start", "hi mochi"), "stop"])
        self.assertEqual(own.calls, [("start", "hi mochi")])

    async def test_both_are_told_whose_voices_are_known(self):
        backend, own = Runner("a"), Runner("b")
        WithFallback(backend, own).set_voices(["Ana"], "Ana")
        self.assertEqual(backend.calls, own.calls)
        self.assertEqual(own.calls, [("voices", ["Ana"], "Ana")])


class HintCardTest(unittest.IsolatedAsyncioTestCase):
    """A hint from the backend shows the word, its language and what it means."""

    async def test_the_card_reaches_the_face_with_its_language_and_meaning(self):
        events = []
        body = Body(FakeSpeaker(), lambda kind, value: events.append((kind, value)))
        await body.act("hint", '{"word": "fork", "language": "en", "meaning": "garfo", "example": null}')
        await body.act("hint", "not a card")          # ignored, not an error
        await body.act("hint", '{"language": "en"}')  # no word: nothing to show
        self.assertEqual(events, [("hint", {"word": "fork", "language": "en", "meaning": "garfo", "example": None})])

    def test_the_small_line_names_the_language_and_the_meaning(self):
        self.assertEqual(hint_note({"word": "fork", "language": "en", "meaning": "garfo"}), "English · garfo")
        self.assertEqual(hint_note({"word": "carteira", "language": "pt-BR", "meaning": "wallet"}), "Português · wallet")
        self.assertEqual(hint_note({"word": "fork", "language": "en", "meaning": None}), "English")
        self.assertEqual(hint_note({"word": "fork"}), "")

    def test_the_supervisor_shows_it(self):
        sup = Supervisor.__new__(Supervisor)
        sup.face = MagicMock()
        sup.on_agent_event("hint", {"word": "fork", "language": "en", "meaning": "garfo"})
        sup.face.show_for.assert_called_once_with(10, word="fork", note="English · garfo")
        sup.on_agent_event("show", "queue")           # a bare word clears an older note
        sup.face.show_for.assert_called_with(10, word="queue", note="")


class UsedWordTest(unittest.IsolatedAsyncioTestCase):
    """Someone says a word they were just given: the face cheers, silently."""

    async def test_the_card_reaches_the_supervisor(self):
        events = []
        body = Body(FakeSpeaker(), lambda kind, value: events.append((kind, value)))
        await body.act("used", '{"word": "fork", "language": "en"}')
        await body.act("used", "{}")                  # no word: nothing to cheer
        self.assertEqual(events, [("used", {"word": "fork", "language": "en"})])

    def test_the_face_cheers_in_the_language_of_the_word(self):
        sup = Supervisor.__new__(Supervisor)
        sup.face = MagicMock()
        sup.on_agent_event("used", {"word": "fork", "language": "en"})
        sup.face.show_for.assert_called_once_with(5, word="fork", note="★ you used it!", mood="proud")
        sup.on_agent_event("used", {"word": "carteira", "language": "pt-BR"})
        sup.face.show_for.assert_called_with(5, word="carteira", note="★ você usou!", mood="proud")


class GoodbyeTest(unittest.IsolatedAsyncioTestCase):
    """Mochi says goodbye ([bye]): the session ends once the goodbye has been heard out."""

    def _supervisor(self):
        now = time.monotonic()
        sup = Supervisor.__new__(Supervisor)  # no microphone, models or screen
        sup.cfg = {"session": {"inactivity_timeout_s": 30, "max_session_s": 600}, "audio": {"chimes": False}}
        sup.kws = MagicMock(last_voice=now)
        sup.kws.feed.return_value = None
        sup.kws.voice_events.return_value = []
        sup.face = MagicMock()
        sup.bridge = MagicMock(running=True, stop=AsyncMock())
        sup.backend = MagicMock(spec=["stop"], stop=AsyncMock())
        sup.state, sup._start_task, sup.backend_end, sup.bye_asked = "ACTIVE", None, None, None
        sup.session_started = sup.last_speech = now
        sup.agent_voice_at = sup.heard_at = sup.bye_until = 0.0
        return sup

    async def test_the_command_reaches_the_supervisor(self):
        events = []
        await Body(FakeSpeaker(), lambda kind, value: events.append((kind, value))).act("bye", "")
        self.assertEqual(events, [("bye", None)])
        self.assertEqual(TAG.findall("[mood happy][bye] Tchau tchau!"), [("mood", "happy"), ("bye", "")])

    async def test_mochi_finishes_its_goodbye_before_leaving(self):
        sup = self._supervisor()
        sup.on_agent_event("bye", None)
        sup.bye_asked -= 3                              # the command came three seconds ago
        await sup.on_frame(b"\0" * 640)
        self.assertEqual(sup.state, "ACTIVE")          # the goodbye has not been spoken yet
        sup.on_agent_voice(40)                          # Mochi is saying it
        await sup.on_frame(b"\0" * 640)
        self.assertEqual(sup.state, "ACTIVE")
        sup.agent_voice_at = time.monotonic() - 1.0     # ...and has been quiet for a second
        await sup.on_frame(b"\0" * 640)
        self.assertEqual(sup.state, "IDLE")
        sup.backend.stop.assert_awaited_once()

    async def test_without_any_voice_it_still_leaves_after_a_few_seconds(self):
        sup = self._supervisor()
        sup.on_agent_event("bye", None)
        sup.bye_asked = time.monotonic() - 9
        await sup.on_frame(b"\0" * 640)
        self.assertEqual(sup.state, "IDLE")


class SupervisorTest(unittest.IsolatedAsyncioTestCase):
    async def test_a_backend_that_never_answers_cannot_keep_mochi_starting(self):
        sup = Supervisor.__new__(Supervisor)
        sup.cfg = {"audio": {"chimes": False}}
        sup.kws = MagicMock()
        sup.bridge = MagicMock(start=AsyncMock(), stop=AsyncMock())

        async def never(wake_phrase=None):
            await asyncio.sleep(3600)
        sup.backend = MagicMock(spec=["start", "stop", "set_voices"], stop=AsyncMock(), start=never)
        sup.state, sup.backend_end, sup.bye_asked = "STARTING", None, None
        sup.start_timeout_s = 0.1
        await asyncio.wait_for(sup.start_session("hi mochi"), timeout=2)
        self.assertEqual(sup.state, "IDLE")
        sup.backend.stop.assert_awaited_once()
        sup.bridge.stop.assert_awaited_once()  # anything half-started is stopped

    async def test_leaves_the_channel_when_the_backend_stopped_the_session(self):
        now = time.monotonic()
        sup = Supervisor.__new__(Supervisor)  # no microphone, models or screen
        sup.cfg = {"session": {"inactivity_timeout_s": 30, "max_session_s": 600}, "audio": {"chimes": False}}
        sup.kws = MagicMock(last_voice=now)
        sup.kws.feed.return_value = None
        sup.kws.voice_events.return_value = []
        sup.face = MagicMock()
        sup.bridge = MagicMock(running=True, stop=AsyncMock())
        sup.backend = MagicMock(spec=["stop"], stop=AsyncMock())
        sup.state, sup._start_task, sup.backend_end, sup.bye_asked = "ACTIVE", None, None, None
        sup.session_started = sup.last_speech = now
        sup.agent_voice_at = sup.heard_at = sup.bye_until = 0.0

        await sup.on_frame(b"\0" * 320)
        self.assertEqual(sup.state, "ACTIVE")
        sup.on_agent_event("stopped", "backend stopped capturing")
        await sup.on_frame(b"\0" * 320)
        self.assertEqual(sup.state, "IDLE")
        sup.bridge.stop.assert_awaited_once()
        sup.backend.stop.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
