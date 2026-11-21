"""M1A microphone as a stream of 20 ms frames (via arecord), plus local chimes and Mochi's own few words."""
import asyncio
import math
import struct
import tempfile
import wave
from array import array
from pathlib import Path

SAMPLE_RATE = 16000
FRAME_BYTES = 640  # 20 ms of 16 kHz mono int16


class Mic:
    def __init__(self, device: str, command: list[str] | None = None):
        """command: what to run instead of arecord; it must write 16 kHz mono int16 to stdout (tests)."""
        self.device = device
        self.command = command or [
            "arecord", "-q", "-D", device, "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", "1",
            "-t", "raw", "--buffer-time=200000", "--period-time=20000",
        ]
        self.proc: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        self.proc = await asyncio.create_subprocess_exec(*self.command, stdout=asyncio.subprocess.PIPE)

    async def frame(self) -> bytes:
        assert self.proc and self.proc.stdout
        return await self.proc.stdout.readexactly(FRAME_BYTES)

    async def stop(self) -> None:
        """Stops the recorder, and never waits for ever doing it.

        After a stall there is more audio in the pipe than anyone read, and asyncio only reports the
        process as gone once its output was read to the end: so read it out, with a time limit. (Without
        this, one stall left Mochi deaf until the service was restarted.)
        """
        proc, self.proc = self.proc, None
        if proc is None:
            return
        if proc.returncode is None:
            proc.terminate()
        try:
            await asyncio.wait_for(proc.stdout.read(), timeout=3)  # to the end: lets wait() finish
            await asyncio.wait_for(proc.wait(), timeout=3)
        except asyncio.TimeoutError:
            if proc.returncode is None:
                proc.kill()  # it ignored the polite request; do not wait for it any longer


def _tone_file(freqs: list[float], ms_each: int = 90) -> str:
    path = Path(tempfile.gettempdir()) / f"mochi-chime-{'-'.join(str(int(f)) for f in freqs)}.wav"
    if not path.exists():
        frames = bytearray()
        n = SAMPLE_RATE * ms_each // 1000
        for f in freqs:
            for i in range(n):
                env = min(1.0, i / 160, (n - i) / 160)  # 10 ms fade in/out, no clicks
                frames += struct.pack("<h", int(9000 * env * math.sin(2 * math.pi * f * i / SAMPLE_RATE)))
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SAMPLE_RATE)
            w.writeframes(bytes(frames))
    return str(path)


SOUNDS = Path(__file__).resolve().parents[1] / "sounds"  # recorded sentences: {what}_{en|pt}.wav


async def say(device: str, what: str, language: str = "en") -> bool:
    """Mochi says one of its recorded sentences from its own speaker: no connection is needed.

    what: "offline" | "online" | "hot". False when there is no such recording or the speaker is busy.
    Example: `await say(dev, "offline", "pt")` plays sounds/offline_pt.wav ("Estou sem conexão.").
    """
    path = SOUNDS / f"{what}_{'pt' if language.startswith('pt') else 'en'}.wav"
    if not path.exists():
        return False
    proc = await asyncio.create_subprocess_exec("aplay", "-q", "-D", device, str(path),
                                                stderr=asyncio.subprocess.DEVNULL)
    return await proc.wait() == 0


async def chime(device: str, rising: bool) -> None:
    """Rising two-tone = awake, falling = going back to sleep. Fire and forget."""
    path = _tone_file([660, 990] if rising else [990, 660])
    proc = await asyncio.create_subprocess_exec("aplay", "-q", "-D", device, path)
    await proc.wait()
