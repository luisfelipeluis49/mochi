"""M1A microphone as a stream of 20 ms frames (via arecord), plus local chimes."""
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
    def __init__(self, device: str):
        self.device = device
        self.proc: asyncio.subprocess.Process | None = None

    async def start(self) -> None:
        self.proc = await asyncio.create_subprocess_exec(
            "arecord", "-q", "-D", self.device, "-f", "S16_LE", "-r", str(SAMPLE_RATE), "-c", "1",
            "-t", "raw", "--buffer-time=200000", "--period-time=20000",
            stdout=asyncio.subprocess.PIPE,
        )

    async def frame(self) -> bytes:
        assert self.proc and self.proc.stdout
        return await self.proc.stdout.readexactly(FRAME_BYTES)

    async def stop(self) -> None:
        if self.proc and self.proc.returncode is None:
            self.proc.terminate()
            await self.proc.wait()


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


async def chime(device: str, rising: bool) -> None:
    """Rising two-tone = awake, falling = going back to sleep. Fire and forget."""
    path = _tone_file([660, 990] if rising else [990, 660])
    proc = await asyncio.create_subprocess_exec("aplay", "-q", "-D", device, path)
    await proc.wait()
