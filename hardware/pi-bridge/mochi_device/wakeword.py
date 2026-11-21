"""Offline wake / goodbye phrase spotting for English and Brazilian Portuguese.

    mic frames -> voice activity (Silero VAD) -> phone recogniser (ZIPA) -> PhraseMatcher (phrases.py)

ZIPA writes speech as IPA phones for any language, so "hi Mochi" and "oi Mochi" need no per-language
model and no agreed spelling of "Mochi". Nothing runs while the room is silent; while someone is
talking, what they have said so far is re-read every few hundred ms.

Try it without Agora:  .venv/bin/python -m mochi_device.wakeword        (or --wav file.wav)
"""
from __future__ import annotations

import queue
import threading
import time
from collections import deque

import numpy as np
import sherpa_onnx

from .config import BRIDGE_DIR
from .phrases import Hit, PhraseMatcher, fold

MODEL_DIR = BRIDGE_DIR / "third_party" / "wake"
PHONES = MODEL_DIR / "zipa-small" / "model.int8.onnx"
TOKENS = MODEL_DIR / "zipa-small" / "tokens.txt"
VAD = MODEL_DIR / "silero_vad.onnx"

SAMPLE_RATE = 16000
WINDOW = 512                      # VAD step: 32 ms
PREROLL = 0.4                     # audio kept from before the VAD fires (soft starts: "oi", "hi")
PAUSE = 0.25                      # silence after which what was said is read as finished
END = 0.7                         # silence after which the next speech is a new utterance
FIRST_READ = 0.6                  # do not read less speech than this
READ_EVERY = 0.35                 # while talking: re-read this often during the first seconds...
HEAD = 3.0                        # ...of an utterance (the phrase usually opens it), then
TAIL_EVERY = 0.7                  # re-read only the last TAIL seconds, less often
TAIL = 2.5
REFRACTORY = 1.5                  # no second hit of the same kind within this many seconds


def _n(seconds: float) -> int:
    return int(seconds * SAMPLE_RATE)


def make_matcher(cfg: dict) -> PhraseMatcher:
    """cfg: the whole mochi.toml dict; uses [wake], [goodbye] and the optional [listening]."""
    opt = cfg.get("listening", {})
    return PhraseMatcher(
        {"wake": cfg["wake"]["phrases"], "goodbye": cfg["goodbye"]["phrases"]},
        name=opt.get("name", "mochi"), sounds=opt.get("sounds"),
        name_tolerance=opt.get("name_tolerance", 0.45), cue_tolerance=opt.get("cue_tolerance", 0.3),
        ignore=opt.get("ignore", ["mochila"]))


class Listener:
    """The pipeline itself, synchronous: feed float32 audio, get Hits. One instance per thread."""

    def __init__(self, matcher: PhraseMatcher, threads: int = 2, on_heard=None):
        for f in (PHONES, TOKENS, VAD):
            if not f.exists():
                raise SystemExit(f"wake model file missing: {f}\nrun scripts/fetch-wake-model.sh")
        self.matcher = matcher
        self.on_heard = on_heard  # callback(phones, final, hit) for the test tool
        self.rec = sherpa_onnx.OfflineRecognizer.from_zipformer_ctc(
            model=str(PHONES), tokens=str(TOKENS), num_threads=threads)
        self.vad = sherpa_onnx.VadModel.create(sherpa_onnx.VadModelConfig(
            silero_vad=sherpa_onnx.SileroVadModelConfig(
                model=str(VAD), threshold=0.5, min_silence_duration=0.1, min_speech_duration=0.1),
            sample_rate=SAMPLE_RATE, num_threads=1))
        self.pending = np.zeros(0, np.float32)
        self.clock = 0  # samples seen
        self.voiced = False  # set whenever the VAD hears a voice; the owner clears it
        self.tracker = None  # speakers.VoiceTracker, when voices are recognised too
        self.voice_events: list[tuple] = []
        self.last_hit: dict[str, int] = {}
        self.reset()

    def reset(self) -> None:
        self.pre: deque[np.ndarray] = deque(maxlen=_n(PREROLL) // WINDOW + 1)
        self.utt: list[np.ndarray] | None = None
        self.total = self.silence = self.unread = self.since_read = 0
        self.trimmed = False

    def phones(self, audio: np.ndarray) -> str:
        st = self.rec.create_stream()
        st.accept_waveform(SAMPLE_RATE, audio)
        self.rec.decode_stream(st)
        return st.result.text.strip()

    def feed(self, samples: np.ndarray) -> list[Hit]:
        hits = []
        self.pending = np.concatenate([self.pending, samples])
        while len(self.pending) >= WINDOW:
            w, self.pending = self.pending[:WINDOW], self.pending[WINDOW:]
            self.clock += WINDOW
            hit = self._step(w)
            if hit and self.clock - self.last_hit.get(hit.group, -10**9) > _n(REFRACTORY):
                self.last_hit[hit.group] = self.clock
                hits.append(hit)
        return hits

    def _step(self, w: np.ndarray) -> Hit | None:
        speech = self.vad.is_speech(w)
        self.voiced = self.voiced or speech
        if self.tracker:
            self.voice_events += self.tracker.step(w, speech)
        if self.utt is None:
            self.pre.append(w)
            if not speech:
                return None
            self.utt, self.total = list(self.pre), len(self.pre) * WINDOW
            self.silence = self.unread = self.since_read = 0
            self.trimmed = False
            return None
        self.utt.append(w)
        self.total += WINDOW
        self.since_read += WINDOW
        if speech:
            self.silence = 0
            self.unread += WINDOW
        else:
            self.silence += WINDOW
        if self.total > _n(HEAD + TAIL):  # long monologue: keep only what can still matter
            keep = _n(TAIL) // WINDOW
            self.utt, self.total, self.trimmed = self.utt[-keep:], keep * WINDOW, True

        hit = None
        if self.silence == _n(PAUSE) // WINDOW * WINDOW and self.unread:
            hit = self._read(final=True)
        elif speech and self.total >= _n(FIRST_READ):
            in_head = not self.trimmed and self.total <= _n(HEAD)
            if self.since_read >= _n(READ_EVERY if in_head else TAIL_EVERY):
                hit = self._read(final=False)
        if hit and hit.group == "wake" and self.tracker:
            # whose voice called: known before the session starts, so Mochi's first answer has it
            try:
                self.voice_events += self.tracker.calling(np.concatenate(self.utt))
            except Exception as e:  # an extra: it must never cost the wake phrase itself
                print(f"[mochi] could not tell who called: {e!r}", flush=True)
        if hit or self.silence >= _n(END):
            # after a hit, whatever follows ("...como se diz fila?") is not read again as part of it
            self.utt = None
            self.pre.clear()
        return hit

    def _read(self, final: bool) -> Hit | None:
        audio = np.concatenate(self.utt)
        from_start = not self.trimmed and self.total <= _n(HEAD)
        if not from_start:
            audio = audio[-_n(TAIL + PAUSE):]
        self.since_read = 0
        if final:
            self.unread = 0
        heard = self.phones(audio)
        hit = self.matcher.match(heard, final=final, from_start=from_start)
        if self.on_heard:
            self.on_heard(heard, final, hit)
        return hit


class KeywordSpotter:
    """What the supervisor uses: feed 20 ms int16 mic frames, get ("wake" | "goodbye", phrase) or None.

    Recognition runs on its own thread so a read (50-250 ms) never holds up audio going to Agora.
    """

    def __init__(self, cfg: dict):
        self.matcher = make_matcher(cfg)
        self._in: queue.Queue = queue.Queue()
        self._out: queue.Queue = queue.Queue()
        self._ready = threading.Event()
        self._error: BaseException | None = None
        self.last_voice = 0.0  # time.monotonic() when a human voice was last heard
        # recognising who is talking (speakers.py); off when the model is not there or [voices] says so
        self._voices_cfg = cfg.get("voices", {})
        self._voice_out: queue.Queue = queue.Queue()
        self._voice_flags = {"track": False, "hold": False}
        self.known_voices: list[str] = []
        threads = cfg.get("listening", {}).get("threads", 2)
        self._thread = threading.Thread(target=self._run, args=(threads,), daemon=True)
        self._thread.start()
        self._ready.wait()
        if self._error:
            raise self._error

    def _run(self, threads: int) -> None:
        try:
            listener = Listener(self.matcher, threads)
            voices = None
            if self._voices_cfg.get("enabled", True):
                from . import speakers
                if speakers.MODEL.exists():
                    voices = speakers.Voices(self._voices_cfg)
                    listener.tracker = speakers.VoiceTracker(voices)
                    self.known_voices = sorted(voices.people)
                else:
                    print(f"[mochi] voices off: {speakers.MODEL} missing (scripts/fetch-wake-model.sh)", flush=True)
        except BaseException as e:  # missing model files: surface it in the caller's thread
            self._error = e
            return
        finally:
            self._ready.set()
        while True:
            item = self._in.get()
            if item is None:
                return
            if item == "reset":
                listener.reset()
                continue
            if isinstance(item, tuple):  # a command for the voice tracker
                if listener.tracker:
                    what, arg = item
                    if what == "track":
                        listener.tracker.on = arg
                    elif what == "hold":
                        listener.tracker.hold = arg
                    elif what == "enroll":
                        listener.tracker.start_enroll(arg)
                    elif what == "forget" and voices.forget(arg):
                        self.known_voices = sorted(voices.people)
                continue
            # if recognition fell behind (busy CPU), catch up on everything queued in one go
            frames = [item]
            while True:
                try:
                    nxt = self._in.get_nowait()
                except queue.Empty:
                    break
                if not isinstance(nxt, bytes):
                    self._in.put(nxt)
                    break
                frames.append(nxt)
            audio = np.frombuffer(b"".join(frames), dtype=np.int16).astype(np.float32) / 32768.0
            hits = []
            try:
                hits = listener.feed(audio)
            except Exception as e:  # never let one bad read end listening for good
                print(f"[mochi] wake recogniser error, carrying on: {e!r}", flush=True)
                listener.reset()
            if listener.voiced:
                listener.voiced = False
                self.last_voice = time.monotonic()
            for event in listener.voice_events:
                if event[0] == "enrolled":
                    self.known_voices = sorted(voices.people)
                self._voice_out.put(event)
            listener.voice_events = []
            for hit in hits:  # after the voice events: who said a wake phrase is there when the hit is read
                self._out.put(hit)

    def feed(self, pcm16: bytes) -> tuple[str, str] | None:
        """Never blocks. A hit comes back on a later call than the frame that completed it."""
        self._in.put(pcm16)
        try:
            hit = self._out.get_nowait()
        except queue.Empty:
            return None
        return hit.group, hit.phrase.upper()

    # --- voices ---------------------------------------------------------------------------------
    def track_voices(self, on: bool, hold: bool = False) -> None:
        """on: recognise who is talking (only during a session). hold: Mochi itself is speaking."""
        for what, value in (("track", on), ("hold", hold)):
            if self._voice_flags[what] != value:
                self._voice_flags[what] = value
                self._in.put((what, value))

    def enroll(self, name: str) -> None:
        """Learn name's voice from the speech that follows."""
        self._in.put(("enroll", name))

    def forget(self, name: str) -> None:
        self._in.put(("forget", name))

    def voice_events(self) -> list[tuple]:
        """("speaker", name | None, score), ("unsure", None, score), ("enrolled", name, seconds),
        ("enroll_failed", name, seconds): see speakers.py."""
        events = []
        while True:
            try:
                events.append(self._voice_out.get_nowait())
            except queue.Empty:
                return events

    def reset(self) -> None:
        """Forget the utterance in progress and any hits not collected yet."""
        self._in.put("reset")
        while not self._out.empty():
            try:
                self._out.get_nowait()
            except queue.Empty:
                break

    def close(self) -> None:
        self._in.put(None)
        self._thread.join(timeout=2)


def main() -> None:
    """Listen (or read a wav) and print what was heard, to check phrases and tune [listening]."""
    import argparse
    import subprocess
    import wave
    from pathlib import Path

    from . import config as config_mod

    ap = argparse.ArgumentParser(description=main.__doc__)
    ap.add_argument("--config", default=str(config_mod.DEFAULT_CONFIG))
    ap.add_argument("--wav", help="16 kHz mono 16-bit file to read instead of the microphone")
    ap.add_argument("--quiet", action="store_true", help="print hits only, not everything heard")
    ap.add_argument("--chime", action="store_true", help="beep on a match: rising = wake, falling = goodbye")
    args = ap.parse_args()
    cfg = config_mod.load(Path(args.config))

    def heard(phones: str, final: bool, hit: Hit | None) -> None:
        if hit and args.chime and not args.wav:
            from .audio import _tone_file
            tones = [660, 990] if hit.group == "wake" else [990, 660]
            subprocess.Popen(["aplay", "-q", "-D", cfg["audio"]["device"], _tone_file(tones)])
        if hit:
            print(f"\r{time.strftime('%H:%M:%S')}  >>> {hit.group.upper()}: {hit.phrase!r}  "
                  f"(heard {hit.heard!r}, score {hit.score})" + " " * 20, flush=True)
        elif not args.quiet:
            # the folded form is what phrases are matched against; use it for [listening.sounds]
            print(f"\r{time.strftime('%H:%M:%S')}  heard {fold(phones)!r}" + " " * 20,
                  end="\n" if final else "", flush=True)

    listener = Listener(make_matcher(cfg), cfg.get("listening", {}).get("threads", 2), on_heard=heard)
    if args.wav:
        with wave.open(args.wav) as w:
            assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (SAMPLE_RATE, 1, 2), "need 16 kHz mono s16"
            audio = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(np.float32) / 32768.0
        listener.feed(np.concatenate([audio, np.zeros(_n(END + 0.1), np.float32)]))
        return
    dev = cfg["audio"]["device"]
    print(f"listening on {dev} for {cfg['wake']['phrases']} / {cfg['goodbye']['phrases']}  (Ctrl-C to stop)")
    mic = subprocess.Popen(["arecord", "-q", "-D", dev, "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", "1", "-t", "raw"],
                           stdout=subprocess.PIPE)
    try:
        while chunk := mic.stdout.read(640):
            listener.feed(np.frombuffer(chunk, np.int16).astype(np.float32) / 32768.0)
    except KeyboardInterrupt:
        pass
    finally:
        mic.terminate()


if __name__ == "__main__":
    main()
