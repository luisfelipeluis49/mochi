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
        self.saved = {}

    def embed(self, audio):  # level 0.1 -> one direction, 0.2 -> another, 0.3 -> a third
        v = np.zeros(8, np.float32)
        v[int(round(float(np.mean(audio)) * 10))] = 1
        return v


def named(events):
    """What was reported about who is talking, leaving out the "could not tell yet" notes for the
    log and the per-stretch verdicts (see said())."""
    return [e[:2] for e in events if e[0] not in ("unsure", "said")]


def said(events):
    """The verdicts on each stretch of speech: (who, seconds of speech)."""
    return [(e[1], round(e[2], 1)) for e in events if e[0] == "said"]


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
        self.assertEqual(named(events), [("speaker", "Ana")])      # short turn: recognised only at the pause

    def test_a_new_sentence_does_not_make_the_speaker_unknown_again(self):
        """Seen on the device: the name was on the screen and Mochi still said it did not know the
        voice, because every new sentence began as "unknown" and the agent heard that first."""
        self.enrol("Ana", 0.1)
        talk(self.t, 0.1, 2)
        talk(self.t, 0, 1, speech=False)
        events = talk(self.t, 0.1, 0.5)                              # she starts her next sentence
        self.assertEqual(events, [])

    def test_unknown_voice_is_nobody(self):
        self.enrol("Ana", 0.1)
        events = talk(self.t, 0.3, 2) + talk(self.t, 0, 0.5, speech=False)
        self.assertEqual(named(events), [("speaker", None)])        # said once, at the pause

    def test_a_few_words_are_too_little_to_call_someone_a_stranger(self):
        self.enrol("Ana", 0.1)
        events = talk(self.t, 0.3, 1) + talk(self.t, 0, 0.5, speech=False)
        self.assertEqual(named(events), [])                          # whoever was talking stays
        self.assertEqual({e[0] for e in events if e[0] != "said"}, {"unsure"})         # ...and the log has the scores

    def test_keeps_trying_while_someone_talks_until_it_knows_them(self):
        self.enrol("Ana", 0.1)
        self.voices.min_score = 2                                    # the first guesses do not reach it
        events = talk(self.t, 0.1, 1.2)
        self.assertEqual([e[0] for e in events], ["unsure"])
        self.voices.min_score = 0.35
        events = talk(self.t, 0.1, 0.5)                              # 1.5 s of speech: asked again
        self.assertEqual(named(events), [("speaker", "Ana")])
        self.assertEqual(named(talk(self.t, 0.1, 3)), [])            # known: no more guessing who is talking

    def test_a_score_just_under_the_bar_does_not_take_a_recognition_back(self):
        self.enrol("Ana", 0.1)
        events = talk(self.t, 0.1, 2)
        self.assertEqual(named(events), [("speaker", "Ana")])
        self.voices.min_score = 1.05                                 # the read at the pause dips a little
        events = talk(self.t, 0, 0.5, speech=False)
        self.assertEqual(named(events), [])

    def test_a_clear_miss_on_the_whole_sentence_takes_an_early_guess_back(self):
        """The first 0.8 s named someone; the whole sentence says clearly not: the sentence wins."""
        self.enrol("Ana", 0.1)
        events = talk(self.t, 0.1, 2)
        self.assertEqual(named(events), [("speaker", "Ana")])
        self.voices.min_score = 2
        events = talk(self.t, 0, 0.5, speech=False)
        self.assertEqual(named(events), [("speaker", None)])

    def test_whoever_says_the_wake_phrase_is_known_from_the_start(self):
        self.enrol("Ana", 0.1)
        self.t.on = False                                            # no session yet
        self.assertEqual(self.t.calling(np.full(RATE, 0.1, np.float32))[0][:2], ("speaker", "Ana"))
        self.assertEqual(self.t.calling(np.full(RATE, 0.3, np.float32)), [])   # a stranger: nothing to say
        # someone else's sentence ran straight into the call: only the call itself is compared
        both = np.concatenate([np.full(4 * RATE, 0.3, np.float32), np.full(RATE, 0.1, np.float32)])
        self.assertEqual(self.t.calling(both)[0][:2], ("speaker", "Ana"))

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
        heard = talk(self.t, 0.1, 2)
        self.assertEqual([e for e in heard if e[0] != "over"], [])   # ("over": someone talking over Mochi, test_bargein.py)
        self.t.hold, self.t.on = False, False
        self.assertEqual(talk(self.t, 0.1, 2), [])

    def test_forget(self):
        self.enrol("Ana", 0.1)
        self.assertTrue(self.voices.forget("ana"))
        self.assertEqual(self.voices.people, {})


if __name__ == "__main__":
    unittest.main()


class VoiceSharingTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.voices = FakeVoices(Path(self.dir.name) / "voices.json")
        self.voices.people["Ana"] = np.array([1, 0, 0], np.float32)

    def test_export_gives_every_voice_with_its_vector(self):
        self.assertEqual(self.voices.export(), {"Ana": {"voiceprint": [1.0, 0.0, 0.0], "saved": None}})

    def test_merge_adds_only_voices_that_are_missing_and_saves_them(self):
        added = self.voices.merge([{"name": "ana", "voiceprint": [0, 1, 0]},
                                   {"name": "Ben", "voiceprint": [0, 1, 0], "saved": "2026-11-21 15:00"}])
        self.assertEqual(added, ["Ben"])
        self.assertEqual(list(self.voices.people["Ana"]), [1, 0, 0])  # never replaced
        self.assertEqual(self.voices.saved["Ben"], "2026-11-21 15:00")
        self.assertTrue(self.voices.store.exists())

    def test_merge_skips_a_vector_that_cannot_be_used(self):
        bad = [{"name": "Ben", "voiceprint": [0, 1]}, {"name": "Cy", "voiceprint": [float("nan"), 0, 0]},
               {"name": "Di", "voiceprint": None}, {"name": "", "voiceprint": [0, 1, 0]}]
        self.assertEqual(self.voices.merge(bad), [])
        self.assertEqual(list(self.voices.people), ["Ana"])
        self.assertFalse(self.voices.store.exists())

    def test_forgetting_a_voice_forgets_when_it_was_saved_too(self):
        self.voices.saved["Ana"] = "2026-11-21 15:00"
        self.assertTrue(self.voices.forget("ana"))
        self.assertEqual(self.voices.saved, {})


class WhoSaidEachStretchTest(unittest.TestCase):
    """("said", name, seconds, ended): each stretch between two pauses, judged on its own."""

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.voices = FakeVoices(Path(self.dir.name) / "voices.json")
        self.t = VoiceTracker(self.voices)
        self.t.on = True
        for name, level in (("Ana", 0.1), ("Ben", 0.2)):
            self.t.start_enroll(name)
            talk(self.t, level, 10)
            talk(self.t, 0, 1, speech=False)

    def tearDown(self):
        self.dir.cleanup()

    def test_a_stretch_is_reported_at_its_pause_with_who_and_how_long(self):
        events = talk(self.t, 0.1, 2) + talk(self.t, 0, 0.5, speech=False)
        self.assertEqual(said(events)[-1], ("Ana", 2.0))
        when = [e[3] for e in events if e[0] == "said"]
        self.assertTrue(when and all(isinstance(t, float) for t in when))  # time.monotonic()

    def test_someone_recognised_while_still_talking_is_reported_before_the_pause(self):
        events = talk(self.t, 0.2, 1.2)  # no pause yet
        self.assertEqual(said(events), [("Ben", 0.8)])

    def test_a_quick_answer_is_the_second_persons_not_the_firsts(self):
        """Half a second between two people is one "utterance" for the who-is-talking report,
        which then keeps the first name; the stretch verdict looks at the answer alone."""
        talk(self.t, 0.1, 2)
        talk(self.t, 0, 0.4, speech=False)             # shorter than the 0.7 s that ends an utterance
        events = talk(self.t, 0.2, 1.5) + talk(self.t, 0, 0.5, speech=False)
        self.assertEqual(said(events), [("Ben", 1.5)])

    def test_a_stranger_or_a_cough_gets_no_name(self):
        events = talk(self.t, 0.3, 2) + talk(self.t, 0, 0.5, speech=False)
        self.assertEqual(said(events), [(None, 2.0)])
        talk(self.t, 0, 1, speech=False)
        cough = talk(self.t, 0.1, 0.2) + talk(self.t, 0, 0.5, speech=False)
        self.assertEqual(said(cough), [])               # too little speech for a verdict

    def test_speech_that_never_pauses_still_gets_a_verdict_every_two_seconds(self):
        """In a room where other people are talking too, the voice detector never hears a pause:
        waiting for one left a whole meeting without a single verdict (22 in 100 sentences named)."""
        events = talk(self.t, 0.1, 4.5)                 # Ana, 4.5 s without a breath
        self.assertEqual(said(events), [("Ana", 0.8), ("Ana", 2.0), ("Ana", 2.0)])   # early, then every 2 s
        events = talk(self.t, 0.2, 2.1)                 # Ben takes over without a pause
        self.assertEqual(said(events)[-1][0], "Ben")

    def test_nothing_is_reported_while_mochi_itself_speaks(self):
        self.t.hold = True
        events = talk(self.t, 0.1, 2) + talk(self.t, 0, 0.5, speech=False)
        self.assertEqual(said(events), [])
