"""MochiBackend against a small local copy of the backend's HTTP surface (AGENTS.md 6.4).

Run:  .venv/bin/python -m unittest discover tests
"""
import asyncio
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import AsyncMock, MagicMock

from mochi_device.backends import JoinInfo, MochiBackend, WithFallback
from mochi_device.main import Supervisor

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
        self.assertEqual(backend.calls, [("start", "hi mochi")])  # never asked to stop what it never ran
        backend.broken = False  # the backend is back: the next session is its again
        self.assertEqual((await both.start()).channel, "mochi-demo")

    async def test_both_are_told_whose_voices_are_known(self):
        backend, own = Runner("a"), Runner("b")
        WithFallback(backend, own).set_voices(["Ana"], "Ana")
        self.assertEqual(backend.calls, own.calls)
        self.assertEqual(own.calls, [("voices", ["Ana"], "Ana")])


class SupervisorTest(unittest.IsolatedAsyncioTestCase):
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
        sup.state, sup._start_task, sup.backend_end = "ACTIVE", None, None
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
