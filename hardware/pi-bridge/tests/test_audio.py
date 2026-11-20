"""The microphone stream must survive a stall. Run:  .venv/bin/python -m unittest discover tests"""
import asyncio
import sys
import unittest

from mochi_device.audio import FRAME_BYTES, Mic

# Stand-ins for arecord: one writes audio for ever as fast as it can, one writes two frames and waits.
FLOOD = [sys.executable, "-c", "import sys\nwhile True: sys.stdout.buffer.write(bytes(65536))"]
TWO_FRAMES = [sys.executable, "-c",
              f"import sys, time\nsys.stdout.buffer.write(bytes({2 * FRAME_BYTES})); sys.stdout.flush(); time.sleep(30)"]


class MicTest(unittest.IsolatedAsyncioTestCase):
    async def test_frames_come_out_in_20_ms_pieces(self):
        mic = Mic("unused", TWO_FRAMES)
        await mic.start()
        self.assertEqual(len(await mic.frame()), FRAME_BYTES)
        self.assertEqual(len(await mic.frame()), FRAME_BYTES)
        await asyncio.wait_for(mic.stop(), 8)

    async def test_stop_returns_after_a_stall_left_audio_unread(self):
        """Seen on the Pi: nobody read for two seconds, the pipe filled up, and stop() never came back."""
        mic = Mic("unused", FLOOD)
        await mic.start()
        await asyncio.sleep(1.0)  # the stall: audio piles up unread
        await asyncio.wait_for(mic.stop(), 8)
        self.assertIsNone(mic.proc)

    async def test_the_microphone_can_be_started_again_after_a_stall(self):
        mic = Mic("unused", FLOOD)
        await mic.start()
        await asyncio.sleep(0.5)
        await asyncio.wait_for(mic.stop(), 8)
        mic.command = TWO_FRAMES
        await mic.start()
        self.assertEqual(len(await mic.frame()), FRAME_BYTES)
        await asyncio.wait_for(mic.stop(), 8)

    async def test_stopping_twice_or_before_starting_is_harmless(self):
        mic = Mic("unused", TWO_FRAMES)
        await mic.stop()
        await mic.start()
        await mic.stop()
        await mic.stop()


if __name__ == "__main__":
    unittest.main()
