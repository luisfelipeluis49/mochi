"""Someone talking over Mochi is noticed by loudness (bargein.py) and, when they are known, by voice.
Run:  .venv/bin/python -m unittest discover tests"""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from mochi_device.bargein import LevelWatch, loudness
from mochi_device.speakers import RATE, WINDOW, VoiceTracker

try:  # run by discovery (the tests folder is on the path) or as tests.test_bargein
    from test_speakers import FakeVoices, talk
except ImportError:
    from tests.test_speakers import FakeVoices, talk


def frame(level: float) -> bytes:
    """A 20 ms frame whose RMS is `level`."""
    return np.full(320, level, np.int16).tobytes()


def frames(watch: LevelWatch, level: float, ms: int, voiced: bool = True) -> list[bool]:
    return [watch.heard(frame(level), voiced) for _ in range(ms // 20)]


class LevelWatchTest(unittest.TestCase):
    def test_loudness_is_the_rms(self):
        self.assertEqual(loudness(frame(500)), 500.0)
        self.assertEqual(loudness(b""), 0.0)

    def test_mochis_own_voice_alone_never_stops_it(self):
        watch = LevelWatch()
        heard = frames(watch, 400, 300) + frames(watch, 600, 2000) + frames(watch, 300, 2000)
        self.assertFalse(any(heard))                    # louder and softer, as a voice is: still Mochi

    def test_a_person_talking_over_it_is_noticed_within_a_third_of_a_second(self):
        watch = LevelWatch()
        frames(watch, 400, 1000)                        # Mochi alone: its level is learned
        heard = frames(watch, 3000, 500)                # someone at the table starts to talk
        self.assertTrue(any(heard))
        self.assertLessEqual(heard.index(True) * 20, 300)
        self.assertEqual(sum(heard), 1)                 # said once per stretch of Mochi's speech

    def test_a_cough_or_a_noise_is_not_someone_talking(self):
        watch = LevelWatch()
        frames(watch, 400, 1000)
        self.assertFalse(any(frames(watch, 5000, 120)))           # too short
        frames(watch, 400, 600)
        self.assertFalse(any(frames(watch, 5000, 600, voiced=False)))   # loud, but no voice in it

    def test_a_quiet_room_needs_a_real_voice_not_just_more_than_nothing(self):
        watch = LevelWatch()
        frames(watch, 5, 1000)                          # no echo to speak of
        self.assertFalse(any(frames(watch, 120, 600)))  # many times louder than 5, and still nothing
        self.assertTrue(any(frames(watch, 2500, 600)))

    def test_the_learned_level_is_kept_for_mochis_next_sentence(self):
        watch = LevelWatch()
        frames(watch, 400, 1000)
        watch.begin()                                   # Mochi starts its next sentence
        heard = frames(watch, 3000, 400)                # and is talked over from its first word
        self.assertTrue(any(heard))

    def test_it_follows_mochi_getting_louder(self):
        watch = LevelWatch()
        frames(watch, 300, 1000)
        for level in range(300, 900, 20):               # the volume is turned up while it speaks
            self.assertFalse(any(frames(watch, level, 200)), level)


class KnownVoiceOverMochiTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.t = VoiceTracker(FakeVoices(Path(self.dir.name) / "voices.json"))
        self.t.on = True
        self.t.start_enroll("Ana")
        talk(self.t, 0.1, 10)
        talk(self.t, 0, 1, speech=False)

    def tearDown(self):
        self.dir.cleanup()

    def over(self, events):
        return [e[:2] for e in events if e[0] == "over"]

    def test_a_known_person_talking_while_mochi_does_is_reported(self):
        self.t.hold = True                              # Mochi is speaking
        self.assertEqual(self.over(talk(self.t, 0.1, 0.7)), [])            # not enough yet
        self.assertEqual(self.over(talk(self.t, 0.1, 0.3)), [("over", "Ana")])

    def test_mochis_own_voice_and_strangers_are_not(self):
        self.t.hold = True
        events = talk(self.t, 0.3, 3)                   # a voice nobody registered: Mochi's, or a guest's
        self.assertEqual(self.over(events), [])
        self.assertEqual([e for e in events if e[0] in ("speaker", "said")], [])   # and nothing else is said of it

    def test_what_was_heard_under_mochi_is_forgotten_when_it_stops(self):
        self.t.hold = True
        talk(self.t, 0.1, 0.7)
        self.t.hold = False
        talk(self.t, 0, 0.3, speech=False)
        self.assertEqual(self.t.over, [])
        self.assertEqual(self.t.over_next, self.t.OVER_FIRST)
