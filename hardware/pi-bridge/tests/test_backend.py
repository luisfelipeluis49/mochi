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

from types import SimpleNamespace

from mochi_device.backends import HeardTurns, JoinInfo, MochiBackend
from mochi_device.main import Supervisor

JOIN = {"app_id": "app", "channel": "mochi-demo", "uid": 1001, "token": "tok"}


class FakeBackend:
    """Answers start, stop and the device state the way services/backend does."""

    def __init__(self):
        self.capturing = self.speaker_muted = self.broken = False
        self.posts: list[str] = []
        self.bodies: list[dict] = []   # what each POST carried
        self.heard: list[str] = []     # sentences reported to /turns
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
                if action == "turns":
                    fake.heard.append(body["text"])
                    return self.reply({"decision": {"decision": "SHOW_HINT", "hint": {"expression": "postpone"}}})
                fake.posts.append(action)
                fake.bodies.append(body)
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


def said(role: str, text: str, started: int | None, ended: int | None = None):
    """One entry of the agent's conversation history."""
    return SimpleNamespace(role=role, content=text, speech_start_ms=started, speech_end_ms=ended)


class HeardTurnsTest(unittest.TestCase):
    def test_each_finished_sentence_once(self):
        heard = HeardTurns()
        history = [said("assistant", "Hi!", 1, 2), said("user", " Como se diz fila? ", 3, 4)]
        self.assertEqual(heard.new(history), ["Como se diz fila?"])
        history.append(said("assistant", "[mood happy] Fila?", 5))
        self.assertEqual(heard.new(history), [])
        history.append(said("user", "Queue!", 6, 7))
        self.assertEqual(heard.new(history), ["Queue!"])

    def test_a_sentence_still_being_said_waits(self):
        heard = HeardTurns()
        self.assertEqual(heard.new([said("user", "How do", 3)]), [])
        self.assertEqual(heard.new([said("user", "How do you say window?", 3, 9)]), ["How do you say window?"])

    def test_survives_the_history_dropping_its_oldest_entries(self):
        heard = HeardTurns()
        first, second = said("user", "one", 1, 2), said("user", "two", 3, 4)
        self.assertEqual(heard.new([first, second]), ["one", "two"])
        self.assertEqual(heard.new([second, said("user", "three", 5, 6)]), ["three"])


class FakeAgent:
    """Stands in for TestAgentBackend: Mochi's own agent."""

    def __init__(self):
        self.on_turn = None
        self.calls: list = []

    async def start(self, wake_phrase=None):
        self.calls.append(("start", wake_phrase))
        return JoinInfo("own-app", "mochi-test", 1001, "own-token")

    async def stop(self):
        self.calls.append("stop")

    def set_voices(self, known, speaker):
        self.calls.append(("voices", known, speaker))

    async def voice_enrolled(self, name, lang, learned):
        self.calls.append(("enrolled", name, lang, learned))


class OwnAgentTest(unittest.IsolatedAsyncioTestCase):
    """kind = "mochi_backend", agent = "character": Mochi's own agent talks, the backend listens in."""

    def setUp(self):
        self.fake = FakeBackend()
        self.addCleanup(self.fake.close)
        self.agent = FakeAgent()
        self.events: list[tuple] = []
        self.backend = MochiBackend(self.fake.url, "home_pi_01", FakeSpeaker(),
                                    lambda kind, value: self.events.append((kind, value)),
                                    poll_interval_s=0.02, agent=self.agent)

    async def test_backend_starts_no_agent_and_the_bridge_joins_mochis_own(self):
        join = await self.backend.start("oi mochi")
        self.assertEqual(self.fake.bodies, [{"agent": "device"}])
        self.assertEqual((join.app_id, join.channel), ("own-app", "mochi-test"))
        self.assertEqual(self.agent.calls, [("start", "oi mochi")])
        await self.backend.stop()
        self.assertEqual(self.agent.calls[-1], "stop")
        self.assertEqual(self.fake.posts, ["start", "stop"])

    async def test_every_sentence_is_reported_in_order(self):
        await self.backend.start()
        for sentence in ("Eu preciso adiar a reunião.", "Postpone!", "Thank you."):
            self.agent.on_turn(sentence)
        self.assertTrue(await until(lambda: len(self.fake.heard) == 3))
        self.assertEqual(self.fake.heard, ["Eu preciso adiar a reunião.", "Postpone!", "Thank you."])
        await self.backend.stop()

    async def test_voices_reach_mochis_own_agent(self):
        self.backend.set_voices(["Ana"], "Ana")
        await self.backend.voice_enrolled("Ana", "pt", True)
        self.assertEqual(self.agent.calls, [("voices", ["Ana"], "Ana"), ("enrolled", "Ana", "pt", True)])

    async def test_backend_can_still_end_the_session(self):
        await self.backend.start()
        self.fake.capturing = False
        self.assertTrue(await until(lambda: self.events))
        await self.backend.stop()
        self.assertEqual(self.agent.calls[-1], "stop")
        self.assertEqual(self.fake.posts, ["start"])

    async def test_mochi_talks_even_when_the_backend_is_down(self):
        await asyncio.to_thread(self.fake.close)
        join = await self.backend.start("hi mochi")
        self.assertEqual(join.channel, "mochi-test")
        self.agent.on_turn("Nobody is told this.")
        await self.backend.stop()
        self.assertEqual(self.agent.calls, [("start", "hi mochi"), "stop"])


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
