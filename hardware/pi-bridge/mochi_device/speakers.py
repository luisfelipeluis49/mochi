"""Whose voice is this? Voiceprints of the people Mochi has met, kept on the Pi only.

A speaker-embedding model (3D-Speaker CAM++, through sherpa-onnx) turns a stretch of speech into a
vector; a person is the average vector of the speech they gave when Mochi learned their voice.
Someone is recognised when a new stretch of speech is clearly closer to one known person than to
anyone else. Works the same in English and Portuguese: it listens to the voice, not the words.

VoiceTracker is fed the same 32 ms windows and voice-activity flags as the wake-phrase listener
(wakeword.py) and reports:
    ("speaker", name, score)             a known person is talking: said as soon as it is clear
                                         (from ~0.8 s of speech on) and again at each pause
    ("speaker", None, score)             a stranger is talking: said at a pause, and only after
                                         enough speech to be sure it is nobody known
    ("unsure", None, score)              listened, and could not tell yet: whoever was talking
                                         before is still taken to be talking (for the log)
    ("enrolled", name, seconds)          finished learning a voice
    ("enroll_failed", name, seconds)     gave up: not enough speech

Between those reports nothing changes: a new sentence does not make the speaker unknown again. The
agent is told who is talking over the network, which takes longer than a short sentence lasts, so
"unknown until proven again" made Mochi answer "I don't recognise you" to someone whose name was
already on its screen.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import sherpa_onnx

from .config import BRIDGE_DIR

MODEL = BRIDGE_DIR / "third_party" / "voice" / "3dspeaker_campplus_zh_en.onnx"
STORE = BRIDGE_DIR / "data" / "voices.json"
RATE, WINDOW = 16000, 512


class Voices:
    """The voiceprints and the comparing."""

    def __init__(self, cfg: dict | None = None, store: Path = STORE, threads: int = 2):
        cfg = cfg or {}
        self.min_score = cfg.get("min_score", 0.35)    # how alike a voice must be to its match (0-1)
        self.min_margin = cfg.get("min_margin", 0.08)  # ...and how much more alike than to the next person
        self.store = store
        self.model = sherpa_onnx.SpeakerEmbeddingExtractor(
            sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(MODEL), num_threads=threads))
        self.people: dict[str, np.ndarray] = {}
        if store.exists():
            self.people = {name: np.array(p["voiceprint"], np.float32) for name, p in json.loads(store.read_text()).items()}

    def embed(self, audio: np.ndarray) -> np.ndarray:
        stream = self.model.create_stream()
        stream.accept_waveform(RATE, audio)
        stream.input_finished()
        v = np.array(self.model.compute(stream), np.float32)
        return v / (np.linalg.norm(v) + 1e-9)

    def identify(self, audio: np.ndarray) -> tuple[str | None, float]:
        """(name, score); name is None when nobody known is clearly the one talking."""
        if not self.people:
            return None, 0.0
        v = self.embed(audio)
        scores = sorted(((float(v @ p), name) for name, p in self.people.items()), reverse=True)
        best, name = scores[0]
        runner_up = scores[1][0] if len(scores) > 1 else -1.0
        if best < self.min_score or best - runner_up < self.min_margin:
            return None, best
        return name, best

    def learn(self, name: str, audio: np.ndarray) -> float:
        """Make (or replace) name's voiceprint from their speech. Returns the seconds actually used."""
        chunk = 2 * RATE
        vecs = np.stack([self.embed(audio[i:i + chunk]) for i in range(0, len(audio) - chunk + 1, chunk)])
        # someone else may have spoken in between: keep the pieces that agree with the rest
        centre = vecs.mean(0)
        keep = vecs[vecs @ (centre / np.linalg.norm(centre)) >= 0.45]
        if len(keep) >= 2:
            vecs = keep
        print_ = vecs.mean(0)
        self.people[name] = print_ / np.linalg.norm(print_)
        self._save()
        return len(vecs) * 2.0

    def forget(self, name: str) -> bool:
        found = next((n for n in self.people if n.lower() == name.lower()), None)
        if found:
            del self.people[found]
            self._save()
        return bool(found)

    def _save(self) -> None:
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text(json.dumps({
            name: {"voiceprint": [round(float(x), 5) for x in p], "saved": time.strftime("%Y-%m-%d %H:%M")}
            for name, p in self.people.items()}))
        self.store.chmod(0o600)


class VoiceTracker:
    """Follows the microphone window by window and says who is talking. Not thread-safe: it lives on
    the listener's thread; start_enroll / forget arrive there as commands."""

    EARLY = (0.8, 1.5, 2.5)  # seconds of speech in an utterance after which a guess is made, until one names someone
    PAUSE = 0.25 * RATE      # a pause this long: decide on the whole utterance
    END = 0.7 * RATE         # silence this long: the next speech is a new utterance
    KEEP = 8 * RATE          # an utterance is judged on its last 8 s at most
    STRANGER = 1.5 * RATE    # speech needed before "nobody I know" is believed (shorter stretches score low for anyone)
    CLEARLY_NOT = 0.10       # this far under min_score, a whole utterance outweighs a name guessed from its start
    ENROLL = 7 * RATE        # speech wanted to learn a voice ("talk for ten seconds" has pauses)...
    ENROLL_MIN = 4 * RATE    # ...and the least that will do once they have stopped for a moment
    ENROLL_QUIET = 1.5 * RATE
    ENROLL_PATIENCE = 45 * RATE

    def __init__(self, voices: Voices):
        self.voices = voices
        self.on = False        # only while a session is active
        self.hold = False      # Mochi itself is speaking: do not listen to that
        self.enrolling: str | None = None
        self.reset()

    def reset(self) -> None:
        self.utt: list[np.ndarray] = []
        self.voiced = self.silence = 0
        self.guesses = 0       # early guesses made in this utterance
        self.named = False     # someone was recognised in this utterance

    def start_enroll(self, name: str) -> None:
        self.enrolling, self.enroll_audio, self.enroll_waited, self.enroll_quiet = name, [], 0, 0
        self.reset()

    CALL = int(1.2 * RATE)   # a wake phrase is about a second long

    def calling(self, audio: np.ndarray) -> list[tuple]:
        """Who said the wake phrase, if their voice is known: the session then starts knowing them.

        audio ends with the phrase; only its end is compared, because what came before it in the
        same breath may be someone else's sentence.
        """
        name, score = self.voices.identify(audio[-self.CALL:])
        return [("speaker", name, score)] if name else []

    def _listen(self, final: bool) -> list[tuple]:
        """Compare the utterance so far with the known voices.

        A name is reported as soon as it is found. "Nobody known" is reported only at a pause and
        after enough speech. A name already found in this utterance is taken back only by a score
        clearly under the bar: a score just under it must not undo a recognition, but the first
        0.8 s must not outweigh the whole sentence either.
        """
        name, score = self.voices.identify(self._audio())
        if name:
            self.named = True
            return [("speaker", name, score)]
        clearly_not = score < self.voices.min_score - self.CLEARLY_NOT
        if final and self.voiced >= self.STRANGER and (clearly_not or not self.named):
            self.named = False
            return [("speaker", None, score)]
        return [("unsure", None, score)]

    def _enroll_step(self, w: np.ndarray, speech: bool) -> list[tuple]:
        """Collect the learner's speech; finish when there is enough, or they have stopped."""
        self.enroll_waited += WINDOW
        if speech and not self.hold:
            self.enroll_audio.append(w)
            self.enroll_quiet = 0
        else:
            self.enroll_quiet += WINDOW
        got = len(self.enroll_audio) * WINDOW
        gave_up = self.enroll_waited > self.ENROLL_PATIENCE
        if got >= self.ENROLL or (got >= self.ENROLL_MIN and (gave_up or self.enroll_quiet >= self.ENROLL_QUIET)):
            name, self.enrolling = self.enrolling, None
            return [("enrolled", name, self.voices.learn(name, np.concatenate(self.enroll_audio)))]
        if gave_up:
            name, self.enrolling = self.enrolling, None
            return [("enroll_failed", name, got / RATE)]
        return []

    def step(self, w: np.ndarray, speech: bool) -> list[tuple]:
        if not self.on:
            if self.utt:
                self.reset()
            return []
        events = self._enroll_step(w, speech) if self.enrolling else []
        if self.hold:
            if self.utt:
                self.reset()
            return events
        if speech:
            self.utt.append(w)
            self.voiced += WINDOW
            self.silence = 0
            due = self.guesses < len(self.EARLY) and self.voiced >= self.EARLY[self.guesses] * RATE
            if due and not self.named and not self.enrolling:
                self.guesses += 1
                events += self._listen(final=False)
        else:
            self.silence += WINDOW
            if not self.utt:
                return events
            self.utt.append(w)
            if self.silence == int(self.PAUSE) // WINDOW * WINDOW and self.voiced >= 0.5 * RATE and not self.enrolling:
                events += self._listen(final=True)
            if self.silence >= self.END:
                self.reset()
        return events

    def _audio(self) -> np.ndarray:
        return np.concatenate(self.utt)[-int(self.KEEP):]
