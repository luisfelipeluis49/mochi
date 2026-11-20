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

from mochi_device.backends import MochiBackend
from mochi_device.main import Supervisor

JOIN = {"app_id": "app", "channel": "mochi-demo", "uid": 1001, "token": "tok"}


class FakeBackend:
    """Answers start, stop and the device state the way services/backend does."""

    def __init__(self):
        self.capturing = self.speaker_muted = self.broken = False
        self.posts: list[str] = []
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
                fake.posts.append(action)
                fake.capturing = action == "start"
                self.reply({})

            def do_GET(self):
                if fake.broken:
                    return self.reply({"detail": "boom"}, 500)
                self.reply({"capturing": fake.capturing, "agora": JOIN if fake.capturing else None,
                            "speaker_muted": fake.speaker_muted})

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class FakeSpeaker:
    def __init__(self):
        self.muted = False
        self.changes = 0

    def set_muted(self, muted: bool):
        self.muted = muted
        self.changes += 1


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

    async def test_unreachable_backend_fails_start_but_never_stop(self):
        await asyncio.to_thread(self.fake.close)
        with self.assertRaises(OSError):
            await self.backend.start()
        await self.backend.stop()  # must not raise: the supervisor has to get back to listening


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
