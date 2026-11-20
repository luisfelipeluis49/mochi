"""Voice tracking logic with a stand-in for the embedding model: a "voice" here is just the level of
a constant signal. Run:  .venv/bin/python -m unittest discover tests"""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from mochi_device.speakers import RATE, WINDOW, Voices, VoiceTracker


class FakeVoices(Voices):
    def __init__(self, store):
        self.min_score, self.min_margin, self.store, self.people = 0.35, 0.08, store, {}

    def embed(self, audio):  # level 0.1 -> one direction, 0.2 -> another, 0.3 -> a third
        v = np.zeros(8, np.float32)
        v[int(round(float(np.mean(audio)) * 10))] = 1
        return v


def named(events):
    """Who was recognised, leaving out the "someone starts talking" notices."""
    return [e[:2] for e in events if e[0] != "speaker" or e[2] > 0]


def talk(tracker, level, seconds, speech=True):
    events = []
    for _ in range(int(seconds * RATE / WINDOW)):
        events += tracker.step(np.full(WINDOW, level, np.float32), speech)
    return events


class VoiceTrackerTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.voices = FakeVoices(Path(self.dir.name) / "voices.json")
        self.t = VoiceTracker(self.voices)
        self.t.on = True

    def tearDown(self):
        self.dir.cleanup()

    def enrol(self, name, level):
        self.t.start_enroll(name)
        events = talk(self.t, level, 10)
        talk(self.t, 0, 1, speech=False)
        return events

    def test_learns_a_voice_from_ten_seconds_of_speech(self):
        events = self.enrol("Ana", 0.1)
        self.assertEqual(named(events)[0], ("enrolled", "Ana"))   # then it recognises her straight away
        self.assertEqual(set(named(events)[1:]), {("speaker", "Ana")})
        self.assertIn("Ana", self.voices.people)
        self.assertTrue(self.voices.store.exists())

    def test_says_who_is_talking_early_and_at_the_pause(self):
        self.enrol("Ana", 0.1)
        self.enrol("Ben", 0.2)
        events = talk(self.t, 0.2, 2) + talk(self.t, 0, 0.5, speech=False)
        self.assertEqual(named(events), [("speaker", "Ben"), ("speaker", "Ben")])
        events = talk(self.t, 0, 0.5, speech=False) + talk(self.t, 0.1, 0.6) + talk(self.t, 0, 0.5, speech=False)
        self.assertEqual(events[0], ("speaker", None, 0.0))        # a new voice starts: not Ben any more
        self.assertEqual(named(events), [("speaker", "Ana")])      # short turn: recognised only at the pause

    def test_unknown_voice_is_nobody(self):
        self.enrol("Ana", 0.1)
        events = talk(self.t, 0.3, 2) + talk(self.t, 0, 0.5, speech=False)
        self.assertEqual({e[1] for e in events if e[0] == "speaker"}, {None})

    def test_gives_up_when_nobody_talks(self):
        self.t.start_enroll("Ana")
        events = talk(self.t, 0.1, 2) + talk(self.t, 0, 50, speech=False)
        self.assertEqual(named(events), [("enroll_failed", "Ana")])
        self.assertNotIn("Ana", self.voices.people)

    def test_short_enrolment_is_accepted_once_they_stop(self):
        self.t.start_enroll("Ana")
        events = talk(self.t, 0.1, 5) + talk(self.t, 0, 3, speech=False)
        self.assertEqual(named(events), [("enrolled", "Ana")])

    def test_enrolment_finishes_even_while_mochi_answers(self):
        self.t.start_enroll("Ana")
        talk(self.t, 0.1, 5)
        self.t.hold = True      # Mochi replies to what she said; its voice is not collected
        events = talk(self.t, 0.3, 3)
        self.assertEqual(named(events), [("enrolled", "Ana")])

    def test_silent_while_mochi_speaks_or_no_session(self):
        self.enrol("Ana", 0.1)
        self.t.hold = True
        self.assertEqual(talk(self.t, 0.1, 2), [])
        self.t.hold, self.t.on = False, False
        self.assertEqual(talk(self.t, 0.1, 2), [])

    def test_forget(self):
        self.enrol("Ana", 0.1)
        self.assertTrue(self.voices.forget("ana"))
        self.assertEqual(self.voices.people, {})


if __name__ == "__main__":
    unittest.main()
