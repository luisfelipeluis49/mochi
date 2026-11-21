"""Whose voice is this? Voiceprints of the people Mochi has met, kept on the Pi only.

A speaker-embedding model (3D-Speaker CAM++, through sherpa-onnx) turns a stretch of speech into a
vector; a person is the average vector of the speech they gave when Mochi learned their voice.
Someone is recognised when a new stretch of speech is clearly closer to one known person than to
anyone else. Works the same in English and Portuguese: it listens to the voice, not the words.

VoiceTracker is fed the same 32 ms windows and voice-activity flags as the wake-phrase listener
(wakeword.py) and reports:
    ("speaker", name | None, score)      who is talking: None as someone starts, then a name after
                                         ~0.8 s of speech and again at each pause (if recognised)
    ("enrolled", name, seconds)          finished learning a voice
    ("enroll_failed", name, seconds)     gave up: not enough speech
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
        self.saved: dict[str, str] = {}  # when each voice was learned
        if store.exists():
            kept = json.loads(store.read_text())
            self.people = {name: np.array(p["voiceprint"], np.float32) for name, p in kept.items()}
            self.saved = {name: p["saved"] for name, p in kept.items() if p.get("saved")}

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
        self.saved[name] = time.strftime("%Y-%m-%d %H:%M")
        self._save()
        return len(vecs) * 2.0

    def export(self) -> dict[str, dict]:
        """Every voice as the backend keeps it: name -> {"voiceprint": [...], "saved": text | None}."""
        return {name: {"voiceprint": [round(float(x), 5) for x in p], "saved": self.saved.get(name)}
                for name, p in self.people.items()}

    def merge(self, profiles: list[dict]) -> list[str]:
        """Add the voices from the backend that this Pi does not have (any letter case). Never
        replaces or removes one, and skips a vector of the wrong size. Returns the names added."""
        added = []
        for profile in profiles:
            name, vector = str(profile.get("name", "")).strip(), profile.get("voiceprint")
            known = any(n.lower() == name.lower() for n in self.people)
            if name and not known and self._fits(vector):
                self.people[name] = np.array(vector, np.float32)
                self.saved[name] = str(profile.get("saved") or time.strftime("%Y-%m-%d %H:%M"))
                added.append(name)
        if added:
            self._save()
        return added

    def _fits(self, vector) -> bool:
        """A usable voiceprint: numbers, finite, and as long as the ones already here."""
        if not isinstance(vector, list) or not vector or len(vector) > 1024:
            return False
        if not all(isinstance(x, (int, float)) and np.isfinite(x) for x in vector):
            return False
        sizes = {len(p) for p in self.people.values()}
        return sizes == {len(vector)} if sizes else len(vector) == getattr(self.model, "dim", len(vector))

    def forget(self, name: str) -> bool:
        found = next((n for n in self.people if n.lower() == name.lower()), None)
        if found:
            del self.people[found]
            self.saved.pop(found, None)
            self._save()
        return bool(found)

    def _save(self) -> None:
        self.store.parent.mkdir(parents=True, exist_ok=True)
        self.store.write_text(json.dumps({
            name: {"voiceprint": [round(float(x), 5) for x in p],
                   "saved": self.saved.get(name) or time.strftime("%Y-%m-%d %H:%M")}
            for name, p in self.people.items()}))
        self.store.chmod(0o600)


class VoiceTracker:
    """Follows the microphone window by window and says who is talking. Not thread-safe: it lives on
    the listener's thread; start_enroll / forget arrive there as commands."""

    EARLY = 0.8 * RATE       # first guess after this much speech in an utterance
    PAUSE = 0.25 * RATE      # a pause this long: decide on the whole utterance
    END = 0.7 * RATE         # silence this long: the next speech is a new utterance
    KEEP = 8 * RATE          # an utterance is judged on its last 8 s at most
    ENROLL = 7 * RATE        # speech wanted to learn a voice ("talk for ten seconds" has pauses)...
    ENROLL_MIN = 4 * RATE    # ...and the least that will do once they have stopped for a moment
    ENROLL_QUIET = 1.5 * RATE
    ENROLL_PATIENCE = 45 * RATE

    def __init__(self, voices: Voices):
        self.voices = voices
        self.on = False        # only while a session is active
        self.hold = False      # Mochi itself is speaking: do not listen to that
        self.enrolling: str | None = None
        self.said: str | None = None  # the last name reported
        self.reset()

    def reset(self) -> None:
        self.utt: list[np.ndarray] = []
        self.voiced = self.silence = 0
        self.guessed = False

    def start_enroll(self, name: str) -> None:
        self.enrolling, self.enroll_audio, self.enroll_waited, self.enroll_quiet = name, [], 0, 0
        self.reset()

    def _say(self, name: str | None, score: float) -> tuple:
        self.said = name
        return "speaker", name, score

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
            if not self.utt and self.said is not None:
                events.append(self._say(None, 0.0))  # someone starts talking: not known who, yet
            self.utt.append(w)
            self.voiced += WINDOW
            self.silence = 0
            if not self.guessed and self.voiced >= self.EARLY and not self.enrolling:
                self.guessed = True
                events.append(self._say(*self.voices.identify(self._audio())))
        else:
            self.silence += WINDOW
            if not self.utt:
                return events
            self.utt.append(w)
            if self.silence == int(self.PAUSE) // WINDOW * WINDOW and self.voiced >= 0.5 * RATE and not self.enrolling:
                events.append(self._say(*self.voices.identify(self._audio())))
            if self.silence >= self.END:
                self.reset()
        return events

    def _audio(self) -> np.ndarray:
        return np.concatenate(self.utt)[-int(self.KEEP):]
