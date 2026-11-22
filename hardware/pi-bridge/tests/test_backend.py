"""MochiBackend against a small local copy of the backend's HTTP surface (AGENTS.md 6.4).

Run:  .venv/bin/python -m unittest discover tests
"""
import asyncio
import contextlib
import io
import json
import threading
import time
import subprocess
import unittest
import unittest.mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import AsyncMock, MagicMock

from mochi_device.backends import TAG, Body, JoinInfo, MochiBackend, TestAgentBackend, WithFallback
from mochi_device.game import RoundScreen
from mochi_device.main import Supervisor, hint_more, hint_note

JOIN = {"app_id": "app", "channel": "mochi-demo", "uid": 1001, "token": "tok"}


class FakeBackend:
    """Answers start, stop and the device state the way services/backend does."""

    def __init__(self):
        self.capturing = self.speaker_muted = self.broken = False
        self.posts: list[str] = []      # session calls: "start" / "stop"
        self.bodies: list[dict] = []    # what each of those carried
        self.statuses: list[dict] = []  # what the device reported about itself
        self.voices: list[dict] = []    # voices it said it learned
        self.remote_voices: list[dict] = []  # what GET .../voices answers (its database)
        self.puts: list[tuple[str, dict]] = []  # voiceprints sent: (path, body)
        self.commands: list[dict] = []  # what Mochi wants its body to do
        self.auth: dict[str, list] = {}  # Authorization header seen, per POST action (and "state" for the GET)
        self.rounds: list[tuple] = []   # Describe & Guess calls: ("start" | "result", body)
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
                if "/activity/" in self.path:
                    fake.rounds.append((action, body))
                    return self.reply({"detail": "no active round"}, 409) if fake.broken else self.reply({})
                fake.posts.append(action)
                fake.bodies.append(body)
                fake.capturing = action == "start"
                self.reply({})

            def do_PUT(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                fake.puts.append((self.path, body))
                fake.auth.setdefault("put", []).append(self.headers.get("Authorization"))
                self.reply({})

            def do_GET(self):
                fake.auth.setdefault("state", []).append(self.headers.get("Authorization"))
                if fake.broken:
                    return self.reply({"detail": "boom"}, 500)
                if self.path.endswith("/voices"):
                    fake.auth.setdefault("list", []).append(self.headers.get("Authorization"))
                    return self.reply(fake.remote_voices)
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

    async def test_who_is_talking_is_reported_at_once(self):
        """The backend writes Mochi's reply about a second after a sentence ends: who said it must
        be there by then, not at the next once-a-second report."""
        self.backend.STATUS_EVERY_S = 3600
        self.backend.set_voices(["Ana"], None)
        await self.backend.start()
        self.backend.set_voices(["Ana"], "Ana")
        self.assertTrue(await until(lambda: len(self.fake.statuses) == 2))
        self.assertEqual(self.fake.statuses[-1]["speaker"], "Ana")
        await self.backend.stop()

    async def test_a_round_ends_with_a_touch_and_another_can_be_asked_for(self):
        self.assertTrue(await self.backend.round_result("guessed"))
        self.assertTrue(await self.backend.next_round())
        self.assertEqual(self.fake.rounds, [("result", {"result": "guessed"}), ("start", {})])
        self.fake.broken = True
        self.assertFalse(await self.backend.round_result("skipped"))   # said so: the screen can be touched again

    async def test_a_round_that_left_the_state_is_taken_off_the_screen(self):
        """Reset on the backend, or a result too old to show: no card comes, so its absence is the news."""
        await self.backend.start()
        self.fake.commands = [{"command_id": "round_1:ACTIVE_ROUND", "kind": "round", "value": json.dumps(CARD)}]
        self.assertTrue(await until(lambda: ("round", CARD) in self.events))
        self.fake.commands = []
        self.assertTrue(await until(lambda: ("round", {"state": "IDLE"}) in self.events))
        await asyncio.sleep(0.1)
        self.assertEqual(self.events.count(("round", {"state": "IDLE"})), 1)
        await self.backend.stop()

    async def test_a_lost_report_of_who_is_talking_is_sent_again(self):
        """Who is talking stays the same for many sentences now: a report that failed would never be repaired."""
        self.backend.STATUS_EVERY_S = 0.05
        await self.backend.start()
        sent = self.backend._req

        def flaky(method, path, *args, **kwargs):
            if path.endswith("/status") and not self.fake.statuses[-1].get("speaker") and flaky.fail:
                flaky.fail = False
                raise OSError("timed out")
            return sent(method, path, *args, **kwargs)
        flaky.fail = True
        self.backend._req = flaky
        self.backend.set_voices(["Ana"], "Ana")
        self.assertTrue(await until(lambda: self.fake.statuses[-1].get("speaker") == "Ana"))
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
        self.assertEqual(set(self.fake.auth["state"]), {"Bearer s3cret"})  # a round's secret word needs it

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

    def test_off_when_the_config_does_not_say(self):
        import os
        from unittest.mock import patch

        from mochi_device.backends import make_backend
        cfg = self._cfg()
        del cfg["backend"]["fallback"]
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

    async def voice_enrolled(self, name, lang, learned, voiceprint=None):
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

    async def test_a_start_cancelled_in_flight_can_still_be_stopped(self):
        backend, own = Runner("mochi-demo"), Runner("mochi-test")

        async def never(wake_phrase=None):
            await asyncio.sleep(3600)
        backend.start = never
        both = WithFallback(backend, own)
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(both.start("hi mochi"), 0.1)
        await both.stop()
        self.assertEqual(backend.calls, ["stop"])  # its POST may have gone through
        self.assertEqual(own.calls, [])

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
        sup.face.show_for.assert_called_once_with(10, word="fork", note="English · garfo", more="")
        sup.on_agent_event("show", "queue")           # a bare word clears an older note
        sup.face.show_for.assert_called_with(10, word="queue", note="", more="")

    def test_other_words_that_fit_are_a_third_line(self):
        """Someone who stopped at "I forgot my" may need more than the first guess (D-42)."""
        card = {"word": "umbrella", "language": "en", "meaning": "guarda-chuva", "candidates": ["raincoat", "jacket", "hat"]}
        self.assertEqual(hint_more(card), "raincoat · jacket")  # two: the screen is small
        self.assertEqual(hint_more({"word": "fork"}), "")       # an older backend sends none
        self.assertEqual(hint_more({"word": "fork", "candidates": "raincoat"}), "")
        self.assertEqual(hint_more({"word": "fork", "candidates": [None, 3, "spoon"]}), "spoon")
        sup = Supervisor.__new__(Supervisor)
        sup.face = MagicMock()
        sup.on_agent_event("hint", card)
        sup.face.show_for.assert_called_once_with(10, word="umbrella", note="English · guarda-chuva",
                                                  more="raincoat · jacket")


class KeptConnectionTest(unittest.TestCase):
    """The device state is read over one connection that stays open: a hint is on the screen only
    once the next read is back, and a new TLS handshake for every read cost 0.3 to 0.65 s."""

    def setUp(self):
        self.connections = 0
        self.fail_next = False
        test = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"  # keeps the connection open, as a real backend does

            def setup(self):
                test.connections += 1
                super().setup()

            def do_GET(self):
                if test.fail_next:
                    test.fail_next = False
                    self.close_connection = True
                    return self.wfile.close()  # the far end hangs up without answering
                data = json.dumps({"capturing": False, "agora": None, "commands": []}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.backend = MochiBackend(f"http://127.0.0.1:{self.server.server_port}", "home_pi_01")

    def tearDown(self):
        self.backend._drop_line()
        self.server.shutdown()
        self.server.server_close()

    def test_three_reads_use_one_connection(self):
        for _ in range(3):
            self.assertEqual(self.backend._state(3)["capturing"], False)
        self.assertEqual(self.connections, 1)

    def test_a_connection_the_far_end_closed_does_not_cost_the_read(self):
        self.backend._state(3)
        self.fail_next = True
        self.assertEqual(self.backend._state(3)["capturing"], False)  # read again, the old way
        self.assertEqual(self.backend._state(3)["capturing"], False)  # and on a new kept one after
        self.assertEqual(self.connections, 3)  # the kept one, the fresh one, a new kept one
        self.assertIsNotNone(self.backend._line)

    def test_a_stop_closes_it(self):
        self.backend._state(3)
        self.assertIsNotNone(self.backend._line)
        asyncio.run(self.backend.stop())
        self.assertIsNone(self.backend._line)


class RestoredVoicesTest(unittest.TestCase):
    def test_voices_from_the_backend_are_handed_to_the_listener(self):
        sup = Supervisor.__new__(Supervisor)
        sup.kws = MagicMock()
        voices = [{"name": "Ana", "voiceprint": [0.1, 0.2]}]
        sup.on_agent_event("voices", voices)
        sup.kws.merge_voices.assert_called_once_with(voices)

    def test_an_enrolled_voice_sends_its_vector_with_the_announcement(self):
        sup = Supervisor.__new__(Supervisor)
        sup.kws, sup.face, sup.enrol_lang = MagicMock(), MagicMock(), "pt"
        sup.kws.voiceprints.return_value = {"Ana": {"voiceprint": [0.1], "saved": None}}
        sup.backend = MagicMock(voice_enrolled=AsyncMock())

        async def run():
            sup.on_voice_event(("enrolled", "Ana", 9.0))
            await asyncio.sleep(0)

        asyncio.run(run())
        sup.backend.voice_enrolled.assert_awaited_once_with("Ana", "pt", True, {"voiceprint": [0.1], "saved": None})


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
        sup.face.show_for.assert_called_once_with(5, word="fork", note="★ you used it!", more="", mood="proud")
        sup.on_agent_event("used", {"word": "carteira", "language": "pt-BR"})
        sup.face.show_for.assert_called_with(5, word="carteira", note="★ você usou!", more="", mood="proud")


class GoodbyeTest(unittest.IsolatedAsyncioTestCase):
    """Mochi says goodbye ([bye]): the session ends once the goodbye has been heard out."""

    def _supervisor(self):
        now = time.monotonic()
        sup = Supervisor.__new__(Supervisor)  # no microphone, models or screen
        sup.cfg = {"session": {"inactivity_timeout_s": 30, "max_session_s": 600}, "audio": {"chimes": False}}
        sup.kws = MagicMock(last_voice=now)
        sup.kws.feed.return_value = None
        sup.kws.voice_events.return_value = []
        sup.face, sup.game = MagicMock(), RoundScreen()
        sup.dev, sup.alerts, sup.told, sup.owed, sup.online, sup.hot, sup.language, sup.net = "null", {"speak": False}, {}, None, True, False, "en", {}
        sup.loss_said = False
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


CARD = {"round_id": "round_1", "state": "ACTIVE_ROUND", "describer_user_id": "ben", "guesser_user_id": "ana",
        "secret_word": "umbrella", "result": None, "revealed_word": None, "language": "en"}
RESULT = {**CARD, "state": "ROUND_RESULT", "secret_word": None, "result": "guessed", "revealed_word": "umbrella"}


class RoundScreenTest(unittest.TestCase):
    """Describe & Guess on Mochi's own screen (AGENTS.md 7.5)."""

    def test_tap_turns_the_word_over_and_the_next_tap_means_guessed(self):
        g = RoundScreen()
        g.show(CARD, 100)
        self.assertEqual(g.view(), {"tone": "ask", "big": "Ben", "small": "turn me towards you and tap"})
        self.assertNotIn("umbrella", json.dumps(g.view()))        # the page does not have the word yet
        self.assertIsNone(g.touched("tap", 101))
        self.assertEqual(g.view()["big"], "umbrella")
        self.assertIn("Ana", g.view()["small"])
        self.assertIsNone(g.touched("tap", 101.4))                # the same touch bouncing: not "guessed"
        self.assertEqual(g.touched("tap", 110), "guessed")
        self.assertIsNone(g.touched("tap", 110.2))                # sent: a second tap does nothing

    def test_a_long_press_skips(self):
        g = RoundScreen()
        g.show(CARD, 100)
        g.touched("long", 101)                                    # holding to turn it over only turns it over
        self.assertEqual(g.touched("long", 105), "skipped")

    def test_the_result_then_a_tap_for_another_round(self):
        g = RoundScreen()
        g.show(RESULT, 100)
        self.assertEqual(g.view(), {"tone": "result", "big": "umbrella", "small": "Ana got it! Tap for another round."})
        self.assertEqual(g.touched("tap", 103), "next")
        g.show(RESULT, 100)
        self.assertTrue(g.over(109))
        self.assertIsNone(g.touched("tap", 109))                  # the face is back: a tap is just a tap

    def test_a_refused_touch_can_be_made_again(self):
        g = RoundScreen()
        g.show(CARD, 100)
        g.touched("tap", 101)
        self.assertEqual(g.touched("tap", 105), "guessed")
        g.refused(106)                                            # the backend could not be reached
        self.assertEqual(g.touched("tap", 108), "guessed")

    def test_portuguese(self):
        g = RoundScreen()
        g.show({**CARD, "language": "pt-BR"}, 100)
        self.assertEqual(g.view()["small"], "vire-me para você e toque")

    def test_a_round_without_its_word_can_still_be_left(self):
        """No device key, no word: the round would otherwise sit there, and hints stay off meanwhile."""
        g = RoundScreen()
        g.show({**CARD, "secret_word": None}, 100)
        self.assertEqual(g.view(), {"tone": "ask", "big": "Ben", "small": "I cannot see the word\nhold to skip"})
        self.assertIsNone(g.touched("tap", 101))
        self.assertEqual(g.stage, "hidden")                       # nothing to turn over
        self.assertEqual(g.touched("long", 102), "skipped")
        g.refused(103)
        self.assertEqual(g.stage, "hidden")

    def test_a_round_that_is_gone_leaves_the_screen(self):
        g = RoundScreen()
        g.show(CARD, 100)
        g.touched("tap", 101)
        g.show({"state": "IDLE"}, 102)                            # reset on the backend
        self.assertIsNone(g.view())


class RoundOnTheDeviceTest(unittest.IsolatedAsyncioTestCase):
    def _supervisor(self):
        now = time.monotonic()
        sup = Supervisor.__new__(Supervisor)
        sup.cfg = {"session": {"inactivity_timeout_s": 30, "max_session_s": 600}, "audio": {"chimes": False}}
        sup.face, sup.game = MagicMock(), RoundScreen()
        sup.dev, sup.alerts, sup.told, sup.owed, sup.online, sup.hot, sup.language, sup.net = "null", {"speak": False}, {}, None, True, False, "en", {}
        sup.loss_said = False
        sup.backend = MagicMock(spec=["round_result", "next_round"], round_result=AsyncMock(return_value=True),
                                next_round=AsyncMock(return_value=True))
        sup.state, sup.last_speech = "ACTIVE", now - 20
        return sup

    async def test_the_card_reaches_the_supervisor_and_the_word_is_not_logged(self):
        events = []
        await Body(FakeSpeaker(), lambda kind, value: events.append((kind, value))).act("round", json.dumps(CARD))
        await Body(FakeSpeaker(), lambda kind, value: events.append((kind, value))).act("round", "{}")
        self.assertEqual(events, [("round", CARD)])
        sup, printed = self._supervisor(), io.StringIO()
        with contextlib.redirect_stdout(printed):
            sup.on_agent_event("round", CARD)
        self.assertNotIn("umbrella", printed.getvalue())
        sup.face.keep.assert_called_with(round={"tone": "ask", "big": "Ben", "small": "turn me towards you and tap"})

    async def test_two_taps_tell_the_backend_it_was_guessed(self):
        sup = self._supervisor()
        sup.on_agent_event("round", CARD)
        sup.on_tap("tap")
        self.assertEqual(sup.face.keep.call_args.kwargs["round"]["big"], "umbrella")
        self.assertGreater(sup.last_speech, time.monotonic() - 1)  # playing counts as being there
        sup.game.since -= 2                                        # ...some describing later
        sup.on_tap("tap")
        await asyncio.sleep(0)
        sup.backend.round_result.assert_awaited_once_with("guessed")
        sup.on_agent_event("round", RESULT)
        sup.face.show_for.assert_called_with(8.0, round={"tone": "result", "big": "umbrella",
                                                        "small": "Ana got it! Tap for another round."})
        sup.on_tap("tap")
        await asyncio.sleep(0)
        sup.backend.next_round.assert_awaited_once()

    async def test_a_touch_outside_a_round_or_a_session_is_nothing(self):
        sup = self._supervisor()
        sup.on_tap("tap")
        sup.state = "IDLE"
        sup.game.show(CARD, time.monotonic())
        sup.on_tap("tap")
        await asyncio.sleep(0)
        sup.backend.round_result.assert_not_awaited()
        self.assertEqual(sup.game.stage, "hidden")

    async def test_a_result_the_backend_did_not_take_can_be_sent_again(self):
        sup = self._supervisor()
        sup.backend.round_result = AsyncMock(return_value=False)
        sup.on_agent_event("round", CARD)
        sup.on_tap("tap")
        sup.game.since -= 2
        sup.on_tap("long")
        await asyncio.sleep(0.01)
        sup.backend.round_result.assert_awaited_once_with("skipped")
        self.assertEqual(sup.game.stage, "shown")


class FaceTapTest(unittest.IsolatedAsyncioTestCase):
    async def test_the_page_reports_touches_and_a_kept_round_outlives_an_old_timer(self):
        from mochi_device.face import Face
        face, taps = Face({"port": 0}), []
        face.on_tap = taps.append
        face._server = await asyncio.start_server(face._serve, "127.0.0.1", 0)
        port = face._server.sockets[0].getsockname()[1]
        for path in ("/tap?kind=tap", "/tap?kind=long"):
            reader, writer = await asyncio.open_connection("127.0.0.1", port)
            writer.write(f"GET {path} HTTP/1.1\r\nHost: x\r\n\r\n".encode())
            self.assertIn(b"204", await reader.readline())
            writer.close()
        self.assertEqual(taps, ["tap", "long"])
        face.show_for(0.05, round={"tone": "result"})            # a result on its way out...
        face.keep(round={"tone": "ask"})                          # ...and the next round begins
        await asyncio.sleep(0.1)
        self.assertEqual(face.state["round"], {"tone": "ask"})
        face._server.close()


class SharingVoiceprintsTest(unittest.IsolatedAsyncioTestCase):
    """[voices].share_with_backend = false: no voiceprint leaves the Pi."""

    def _supervisor(self, share):
        sup = Supervisor.__new__(Supervisor)
        sup.share_voices, sup.enrol_lang = share, "en"
        sup.kws = MagicMock(known_voices=["Ana"])
        sup.kws.voiceprints.return_value = {"Ana": {"voiceprint": [0.1, 0.2], "saved": "2026-11-21 10:00"}}
        sup.face = MagicMock()
        sup.backend = MagicMock(spec=["voice_enrolled", "set_voices"], voice_enrolled=AsyncMock())
        return sup

    async def test_a_learned_voice_goes_to_the_backend_only_when_sharing_is_on(self):
        for share, sent in ((True, {"voiceprint": [0.1, 0.2], "saved": "2026-11-21 10:00"}), (False, None)):
            sup = self._supervisor(share)
            sup.on_voice_event(("enrolled", "Ana", 7.0))
            await asyncio.sleep(0)
            sup.backend.voice_enrolled.assert_awaited_once_with("Ana", "en", True, sent)

    def test_with_sharing_off_the_backend_link_is_never_given_the_voices(self):
        backend = MochiBackend("http://127.0.0.1:9", "home_pi_01", FakeSpeaker(), None)
        self.assertIsNone(backend._local_voices)      # sync_voices() then does nothing at session start


class LookingAfterItselfTest(unittest.IsolatedAsyncioTestCase):
    """Mochi's face always knows how warm Mochi is, and says when the connection is gone."""

    def _supervisor(self, answers):
        sup = Supervisor.__new__(Supervisor)
        sup.face, sup.online = MagicMock(), True
        sup.net = {"hosts": ["192.0.2.1:9"], "timeout_s": 0.1}
        sup.dev, sup.state, sup.alerts, sup.told, sup.owed, sup.hot, sup.language = "null", "IDLE", {"speak": False}, {}, None, False, "en"
        sup.loss_said = False
        sup.cfg, sup.pinged, sup.backend = {"backend": {}}, -1e9, MagicMock(spec=["ping"], ping=AsyncMock(return_value=True))
        patch = unittest.mock.patch("mochi_device.main.reachable", side_effect=answers)
        patch.start()
        self.addCleanup(patch.stop)
        return sup

    async def test_one_failed_look_is_not_a_lost_connection_two_are(self):
        sup = self._supervisor([True, False, False, True])
        with unittest.mock.patch("mochi_device.main.cpu_temperature", return_value=61.6):
            misses = await sup._look_once(0)
            sup.face.set.assert_called_with(temp=62, hot=False, online=True)
            misses = await sup._look_once(misses)                  # the hotspot hiccups once
            self.assertTrue(sup.online)
            misses = await sup._look_once(misses)                  # ...and is really gone
            sup.face.set.assert_called_with(temp=62, hot=False, online=False)
            await sup._look_once(misses)
            sup.face.set.assert_called_with(temp=62, hot=False, online=True)  # back at once

    def _awake_to_alerts(self, sup):
        sup.dev, sup.state, sup.language = "null", "IDLE", "en"
        sup.alerts, sup.told, sup.owed, sup.hot, sup.loss_said = {"hot_at": 80, "every_s": 120}, {}, None, False, False
        said = []

        async def fake_say(device, what, language="en"):
            said.append((what, language))
            return True
        patch = unittest.mock.patch("mochi_device.main.say", fake_say)
        patch.start()
        self.addCleanup(patch.stop)
        return said

    async def test_losing_the_connection_is_said_aloud_and_so_is_its_return(self):
        sup = self._supervisor([False, False, True, False, False])
        said = self._awake_to_alerts(sup)
        with unittest.mock.patch("mochi_device.main.cpu_temperature", return_value=60.0):
            misses = await sup._look_once(0)
            self.assertEqual(said, [])                               # one failed look: nothing yet
            misses = await sup._look_once(misses)
            await asyncio.sleep(0)
            self.assertEqual(said, [("offline", "en")])
            misses = await sup._look_once(misses)
            await asyncio.sleep(0)
            self.assertEqual(said, [("offline", "en"), ("online", "en")])
            misses = await sup._look_once(misses)
            misses = await sup._look_once(misses)                    # a hotspot that comes and goes...
            await asyncio.sleep(0)
            self.assertEqual(len(said), 2)                           # ...is not announced every time

    async def test_too_warm_is_said_once_until_it_has_cooled_down(self):
        sup = self._supervisor([True] * 8)
        said = self._awake_to_alerts(sup)
        sup.language, sup.alerts["every_s"] = "pt", 0
        for temp in (79.0, 81.0, 83.0, 78.0, 81.0, 74.0):
            with unittest.mock.patch("mochi_device.main.cpu_temperature", return_value=temp):
                await sup._look_once(0)
        await asyncio.sleep(0)
        self.assertEqual(said, [("hot", "pt")])                      # 81 after 78 is the same heat, not news
        sup.face.set.assert_called_with(temp=74, hot=False, online=True)
        with unittest.mock.patch("mochi_device.main.cpu_temperature", return_value=82.0):
            await sup._look_once(0)
        await asyncio.sleep(0)
        self.assertEqual(said, [("hot", "pt"), ("hot", "pt")])
        sup.face.set.assert_called_with(temp=82, hot=True, online=True)

    async def test_during_a_session_it_waits_and_says_it_afterwards_if_still_true(self):
        sup = self._supervisor([False, False])
        said = self._awake_to_alerts(sup)
        sup.state = "ACTIVE"
        with unittest.mock.patch("mochi_device.main.cpu_temperature", return_value=60.0):
            await sup._look_once(await sup._look_once(0))
        await asyncio.sleep(0)
        self.assertEqual((said, sup.owed), ([], "offline"))          # the speaker is Mochi's voice now
        sup.state = "IDLE"
        sup._tell_what_is_owed()
        await asyncio.sleep(0)
        self.assertEqual(said, [("offline", "en")])
        sup.owed, sup.online = "offline", True                       # owed, but the connection came back
        sup._tell_what_is_owed()
        await asyncio.sleep(0)
        self.assertEqual(len(said), 1)

    async def test_called_without_a_connection_mochi_says_so_instead_of_trying(self):
        sup = self._supervisor([False])                              # it looks once more, to be sure
        said = self._awake_to_alerts(sup)
        sup.cfg, sup.online, sup.told = {"audio": {"chimes": False}}, False, {"offline": time.monotonic()}
        sup.kws, sup.game = MagicMock(known_voices=[]), RoundScreen()
        sup.bridge = MagicMock(start=AsyncMock(), stop=AsyncMock())
        sup.backend = MagicMock(spec=["start", "stop", "set_voices"], stop=AsyncMock(), start=AsyncMock())
        sup.state, sup.backend_end, sup.bye_asked, sup.start_timeout_s = "STARTING", None, None, 5
        await sup.start_session("oi mochi")
        await asyncio.sleep(0)
        sup.backend.start.assert_not_awaited()
        self.assertEqual((sup.state, said), ("IDLE", [("offline", "en")]))   # said again although just said

    async def test_a_hosted_backend_is_kept_awake_while_mochi_sleeps(self):
        sup = self._supervisor([True] * 4)
        sup.cfg = {"backend": {"keep_awake_s": 240}}
        with unittest.mock.patch("mochi_device.main.cpu_temperature", return_value=60.0):
            await sup._look_once(0)
            await sup._look_once(0)                                  # five seconds later: not again yet
            await asyncio.sleep(0)
            self.assertEqual(sup.backend.ping.await_count, 1)
            sup.pinged -= 300
            sup.state = "ACTIVE"                                     # a session keeps it awake by itself
            await sup._look_once(0)
            sup.state, sup.cfg = "IDLE", {"backend": {}}             # a backend on this machine: never
            await sup._look_once(0)
            await asyncio.sleep(0)
            self.assertEqual(sup.backend.ping.await_count, 1)

    async def test_the_look_can_be_switched_off_and_a_missing_thermometer_is_no_error(self):
        sup = self._supervisor([False])
        sup.net = {"check": False}
        with unittest.mock.patch("mochi_device.main.cpu_temperature", return_value=None):
            await sup._look_once(0)
        sup.face.set.assert_called_with(temp=None, hot=False, online=True)


class OwnAgentVoicesTest(unittest.IsolatedAsyncioTestCase):
    """Mochi's own agent is told who is talking by updating its instructions over the network."""

    def _agent(self):
        agent = TestAgentBackend.__new__(TestAgentBackend)
        agent.cfg = {"instructions": "You are Mochi."}
        agent.device = MagicMock(min_volume=20)
        agent.known_voices, agent.speaker = [], None
        agent._told, agent._told_text, agent._telling, agent._untold = (80, 50), "", asyncio.Lock(), False
        agent._started, agent._session = True, MagicMock()
        return agent

    async def test_updates_arrive_in_order_and_end_on_what_is_true(self):
        agent, sent = self._agent(), []

        async def update(change):  # the first update is slow on the network, the next ones are not
            await asyncio.sleep(0.05 if not sent else 0)
            sent.append(change["llm"]["system_messages"][0]["content"])
        agent._session.update = update
        agent.set_voices(["Ana"], None)               # someone talks...
        await asyncio.sleep(0.01)                     # (that update is on its way)
        agent.set_voices(["Ana"], "Ana")              # ...and is recognised
        agent.set_voices(["Ana"], "Ana")
        await asyncio.sleep(0.2)
        self.assertEqual(len(sent), 2)                # one after the other, nothing twice
        self.assertIn("have not recognised", sent[0])
        self.assertIn("right now is Ana", sent[1])

    async def test_nothing_is_sent_before_the_agent_is_up(self):
        agent = self._agent()
        agent._started, agent._session.update = False, AsyncMock()
        agent.set_voices(["Ana"], "Ana")
        await asyncio.sleep(0.05)
        agent._session.update.assert_not_awaited()    # start() tells it, once the agent can be told

    async def test_a_failed_update_is_owed(self):
        agent = self._agent()
        agent._session.update = AsyncMock(side_effect=OSError("timed out"))
        agent.set_voices(["Ana"], "Ana")
        await asyncio.sleep(0.01)
        self.assertTrue(agent._untold)                # the watcher sends it again
        agent._session.update = AsyncMock()
        await agent._tell((80, 50))
        self.assertFalse(agent._untold)
        self.assertIn("right now is Ana", agent._told_text)

    async def test_an_unrecognised_voice_is_not_a_no(self):
        agent = self._agent()
        agent.known_voices = ["Ana"]
        self.assertIn("ask them to say a little more", agent._instructions((80, 50)))


class SupervisorTest(unittest.IsolatedAsyncioTestCase):
    async def test_the_voice_that_called_is_known_when_the_session_starts(self):
        sup = Supervisor.__new__(Supervisor)
        sup.cfg = {"audio": {"chimes": False}, "goodbye": {"phrases": ["tchau mochi"]}}
        sup.kws = MagicMock(known_voices=["Ana"])
        sup.kws.feed.return_value = ("wake", "OI MOCHI")
        sup.kws.voice_events.return_value = [("speaker", "Ana", 0.6)]
        sup.face = MagicMock()
        sup.game = RoundScreen()
        sup.dev, sup.alerts, sup.told, sup.owed, sup.online, sup.hot, sup.language, sup.net = "null", {"speak": False}, {}, None, True, False, "en", {}
        sup.loss_said = False
        sup.bridge = MagicMock(start=AsyncMock(), stop=AsyncMock())
        sup.backend = MagicMock(spec=["start", "stop", "set_voices"], stop=AsyncMock(),
                                start=AsyncMock(return_value=JoinInfo("app", "mochi-test", 1001, "tok")))
        sup.state, sup.backend_end, sup.bye_asked, sup.start_timeout_s = "IDLE", None, None, 5
        sup.bye_until = sup.agent_voice_at = sup.heard_at = 0.0
        await sup.on_frame(b"\0" * 640)
        await sup._start_task
        sup.backend.set_voices.assert_called_once_with(["Ana"], "Ana")   # before the agent is started
        sup.backend.start.assert_awaited_once_with("OI MOCHI")
        self.assertEqual(sup.state, "ACTIVE")

    async def test_a_forgotten_voice_is_forgotten_by_the_agent_at_once(self):
        sup = Supervisor.__new__(Supervisor)
        sup.kws = MagicMock(known_voices=["Ana", "Ben"])
        sup.backend = MagicMock(spec=["set_voices"])
        sup.on_agent_event("forget", "ana")
        sup.kws.forget.assert_called_once_with("ana")
        sup.backend.set_voices.assert_called_once_with(["Ben"], None)

    async def test_a_failed_start_leaves_no_caller_and_no_round_behind(self):
        sup = Supervisor.__new__(Supervisor)
        sup.cfg = {"audio": {"chimes": False}}
        sup.kws, sup.face, sup.game = MagicMock(known_voices=[]), MagicMock(), RoundScreen()
        sup.dev, sup.alerts, sup.told, sup.owed, sup.online, sup.hot, sup.language, sup.net = "null", {"speak": False}, {}, None, True, False, "en", {}
        sup.loss_said = False
        sup.game.show(CARD, 1)                        # the backend already had a round on
        sup.bridge = MagicMock(start=AsyncMock(side_effect=OSError("no bridge")), stop=AsyncMock())
        sup.backend = MagicMock(spec=["start", "stop", "set_voices"], stop=AsyncMock(),
                                start=AsyncMock(return_value=JoinInfo("app", "mochi-test", 1001, "tok")))
        sup.state, sup.backend_end, sup.bye_asked, sup.start_timeout_s = "STARTING", None, None, 5
        await sup.start_session("hi mochi")
        self.assertEqual(sup.state, "IDLE")
        self.assertIsNone(sup.game.stage)
        sup.face.keep.assert_called_with(round=None)
        sup.kws.voice_events.assert_called()          # whoever called this one is not the next one's caller

    async def test_what_mochi_says_is_not_sent_to_the_recogniser(self):
        """Seen live: Mochi's greeting came back through the microphone and was transcribed as
        "Where is my chave?", a sentence nobody said, and Mochi answered it."""
        now = time.monotonic()
        sup = Supervisor.__new__(Supervisor)
        sup.cfg = {"session": {"inactivity_timeout_s": 30, "max_session_s": 600}, "audio": {"chimes": False}}
        sup.kws = MagicMock(last_voice=now, known_voices=[])
        sup.kws.feed.return_value = None
        sup.kws.voice_events.return_value = []
        sup.face, sup.game = MagicMock(), RoundScreen()
        sup.dev, sup.alerts, sup.told, sup.owed, sup.online, sup.hot, sup.language, sup.net = "null", {"speak": False}, {}, None, True, False, "en", {}
        sup.loss_said = False
        sup.bridge = MagicMock(running=True, stop=AsyncMock())
        sup.backend = MagicMock(spec=["stop"], stop=AsyncMock())
        sup.state, sup._start_task, sup.backend_end, sup.bye_asked = "ACTIVE", None, None, None
        sup.session_started = sup.last_speech = now
        sup.heard_at, sup.bye_until = 0.0, 0.0
        frame = b"\x01\x02" * 320
        sup.agent_voice_at = now                               # Mochi is speaking
        await sup.on_frame(frame)
        sup.bridge.send.assert_called_with(bytes(640))         # silence goes out
        sup.kws.feed.assert_called_with(frame)                 # the Pi itself still hears "tchau Mochi"
        sup.agent_voice_at = now - 2                           # ...and has stopped
        await sup.on_frame(frame)
        sup.bridge.send.assert_called_with(frame)
        sup.cfg["audio"]["hear_while_speaking"] = True         # a microphone that does not hear the speaker
        sup.agent_voice_at = time.monotonic()
        await sup.on_frame(frame)
        sup.bridge.send.assert_called_with(frame)

    async def test_mochis_own_voice_does_not_make_the_speaker_unknown(self):
        """While Mochi talks its voice reaches the microphone too: that is not a stranger."""
        now = time.monotonic()
        sup = Supervisor.__new__(Supervisor)
        sup.cfg = {"session": {"inactivity_timeout_s": 30, "max_session_s": 600}, "audio": {"chimes": False}}
        sup.kws = MagicMock(last_voice=now, known_voices=["Ana"])
        sup.kws.feed.return_value = None
        sup.kws.voice_events.return_value = []
        sup.face, sup.game = MagicMock(), RoundScreen()
        sup.dev, sup.alerts, sup.told, sup.owed, sup.online, sup.hot, sup.language, sup.net = "null", {"speak": False}, {}, None, True, False, "en", {}
        sup.loss_said = False
        sup.bridge = MagicMock(running=True, stop=AsyncMock())
        sup.backend = MagicMock(spec=["stop", "set_voices"], stop=AsyncMock())
        sup.state, sup._start_task, sup.backend_end, sup.bye_asked = "ACTIVE", None, None, None
        sup.session_started = sup.last_speech = now
        sup.agent_voice_at, sup.heard_at, sup.bye_until = now, 0.0, 0.0
        await sup.on_frame(b"\0" * 640)
        sup.backend.set_voices.assert_not_called()
        sup.on_voice_event(("unsure", None, 0.2))
        sup.backend.set_voices.assert_not_called()
        sup.on_voice_event(("speaker", None, 0.1))                        # a stranger, heard out
        sup.backend.set_voices.assert_called_once_with(["Ana"], None)

    async def test_a_backend_that_never_answers_cannot_keep_mochi_starting(self):
        sup = Supervisor.__new__(Supervisor)
        sup.cfg = {"audio": {"chimes": False}}
        sup.kws, sup.face, sup.game = MagicMock(), MagicMock(), RoundScreen()
        sup.dev, sup.alerts, sup.told, sup.owed, sup.online, sup.hot, sup.language, sup.net = "null", {"speak": False}, {}, None, True, False, "en", {}
        sup.loss_said = False
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

    async def test_when_mochis_agent_leaves_the_call_the_session_ends(self):
        """Seen live: the agent was gone after 99 s and the face stayed awake for another minute."""
        now = time.monotonic()
        sup = Supervisor.__new__(Supervisor)
        sup.cfg = {"session": {"inactivity_timeout_s": 30, "max_session_s": 600}, "audio": {"chimes": False}}
        sup.kws = MagicMock(last_voice=now)
        sup.kws.feed.return_value = None
        sup.kws.voice_events.return_value = []
        sup.face, sup.game = MagicMock(), RoundScreen()
        sup.dev, sup.alerts, sup.told, sup.owed, sup.online, sup.hot, sup.language, sup.net = "null", {"speak": False}, {}, None, True, False, "en", {}
        sup.loss_said = False
        sup.bridge = MagicMock(running=True, stop=AsyncMock())
        sup.backend = MagicMock(spec=["stop"], stop=AsyncMock())
        sup.state, sup._start_task, sup.backend_end, sup.bye_asked = "ACTIVE", None, None, None
        sup.session_started = sup.last_speech = now
        sup.agent_voice_at = sup.heard_at = sup.bye_until = 0.0
        sup.on_agent_left(1002)
        await sup.on_frame(b"\0" * 640)
        self.assertEqual(sup.state, "IDLE")
        sup.backend.stop.assert_awaited_once()
        sup.backend_end = None
        sup.on_agent_left(1002)                        # asleep: nothing to end
        self.assertIsNone(sup.backend_end)

    async def test_the_bridge_says_when_the_other_side_leaves(self):
        from mochi_device.bridge import BridgeProcess
        left = []
        bridge = BridgeProcess("null", None, left.append)

        class Lines:
            def __init__(self, lines): self.lines = iter(lines)
            def __aiter__(self): return self
            async def __anext__(self):
                try: return next(self.lines)
                except StopIteration: raise StopAsyncIteration from None
        bridge.proc = MagicMock(stderr=Lines([b"[bridge] remote user 1002 joined\n", b"[bridge] remote user 1002 left (0)\n"]))
        with contextlib.redirect_stdout(io.StringIO()):
            await bridge._relay_log()
        self.assertEqual(left, [1002])

    async def test_leaves_the_channel_when_the_backend_stopped_the_session(self):
        now = time.monotonic()
        sup = Supervisor.__new__(Supervisor)  # no microphone, models or screen
        sup.cfg = {"session": {"inactivity_timeout_s": 30, "max_session_s": 600}, "audio": {"chimes": False}}
        sup.kws = MagicMock(last_voice=now)
        sup.kws.feed.return_value = None
        sup.kws.voice_events.return_value = []
        sup.face, sup.game = MagicMock(), RoundScreen()
        sup.dev, sup.alerts, sup.told, sup.owed, sup.online, sup.hot, sup.language, sup.net = "null", {"speak": False}, {}, None, True, False, "en", {}
        sup.loss_said = False
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


PRINT = {"voiceprint": [0.1, 0.2, 0.3], "saved": "2026-11-21 15:00"}


class VoiceSyncTest(unittest.IsolatedAsyncioTestCase):
    """The Pi and the backend's database share voices: only ever adding, never removing."""

    def setUp(self):
        self.fake = FakeBackend()
        self.events = []
        self.backend = MochiBackend(self.fake.url, "home_pi_01", None, lambda k, v: self.events.append((k, v)),
                                    device_key="s3cret")
        self.here = {"Ana": PRINT}
        self.backend.use_voices(lambda: self.here)

    def tearDown(self):
        self.fake.close()

    async def test_a_learned_voice_sends_its_voiceprint_after_the_announcement(self):
        await self.backend.voice_enrolled("Ana", "pt", True, PRINT)
        self.assertEqual(self.fake.voices, [{"name": "Ana", "language": "pt", "learned": True}])
        self.assertEqual(self.fake.puts, [("/api/devices/home_pi_01/voices/Ana/voiceprint",
                                           {"language": "pt", **PRINT})])
        self.assertEqual(self.fake.auth["put"], ["Bearer s3cret"])

    async def test_a_voice_that_did_not_work_sends_no_voiceprint(self):
        await self.backend.voice_enrolled("Ana", "pt", False, None)
        self.assertEqual(self.fake.puts, [])

    async def test_a_replaced_pi_gets_its_voices_back(self):
        self.here = {}
        self.fake.remote_voices = [{"name": "Ana", "user_id": "ana", "language": "pt", **PRINT}]
        await self.backend.sync_voices()
        self.assertEqual(self.events, [("voices", self.fake.remote_voices)])
        self.assertEqual(self.fake.puts, [])
        self.assertEqual(self.fake.auth["list"], ["Bearer s3cret"])

    async def test_voices_only_this_pi_has_go_to_the_backend(self):
        self.fake.remote_voices = [{"name": "ana", "user_id": "ana", "language": "pt", "voiceprint": None}]
        await self.backend.sync_voices()
        self.assertEqual(self.events, [])
        self.assertEqual(self.fake.puts[0][1]["language"], "pt")  # keeps the language the backend knew

    async def test_an_empty_backend_removes_nothing_here(self):
        await self.backend.sync_voices()
        self.assertEqual(self.events, [])
        self.assertEqual(self.here, {"Ana": PRINT})
        self.assertEqual(len(self.fake.puts), 1)  # it fills the backend instead

    async def test_a_backend_that_is_down_is_not_a_problem(self):
        self.fake.broken = True
        self.fake.close()
        await self.backend.sync_voices()
        self.assertEqual(self.events, [])
