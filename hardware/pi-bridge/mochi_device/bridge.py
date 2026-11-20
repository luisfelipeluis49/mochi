"""Runs the C bridge (build/mochi-bridge) for one session, feeding it mic frames on stdin."""
from __future__ import annotations

import asyncio
import os
import signal

from .backends import JoinInfo
from .config import BRIDGE_DIR

BRIDGE_BIN = BRIDGE_DIR / "build" / "mochi-bridge"


class BridgeProcess:
    def __init__(self, speaker: str, on_voice=None):
        """on_voice(level 0-100): called as the loudness of the agent's voice changes."""
        self.speaker = speaker
        self.on_voice = on_voice
        self.proc: asyncio.subprocess.Process | None = None
        self._log_task: asyncio.Task | None = None

    async def start(self, join: JoinInfo) -> None:
        env = dict(os.environ)  # token goes through the environment, never the command line
        env.update(AGORA_APP_ID=join.app_id, AGORA_CHANNEL=join.channel, AGORA_UID=str(join.uid))
        if join.token:
            env["AGORA_TOKEN"] = join.token
        else:
            env.pop("AGORA_TOKEN", None)
        self.proc = await asyncio.create_subprocess_exec(
            str(BRIDGE_BIN), "--mic", "-", "--speaker", self.speaker, "--levels",
            stdin=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, env=env,
        )
        self._log_task = asyncio.create_task(self._relay_log())

    async def _relay_log(self) -> None:
        assert self.proc and self.proc.stderr
        async for line in self.proc.stderr:
            text = line.decode(errors="replace").rstrip()
            if text.startswith("[bridge] voice "):
                if self.on_voice:
                    self.on_voice(int(text.rsplit(" ", 1)[1]))
                continue
            # keep the once-a-second status lines out of the supervisor log unless they show trouble
            if "| sent" in text and "not joined" not in text:
                continue
            print(text, flush=True)

    @property
    def running(self) -> bool:
        return self.proc is not None and self.proc.returncode is None

    def send(self, frame: bytes) -> None:
        if self.running and self.proc.stdin and not self.proc.stdin.is_closing():
            self.proc.stdin.write(frame)

    async def stop(self) -> None:
        if not self.proc:
            return
        if self.proc.stdin and not self.proc.stdin.is_closing():
            self.proc.stdin.close()  # unblocks the bridge's stdin reader
        if self.proc.returncode is None:
            self.proc.send_signal(signal.SIGINT)
            try:
                await asyncio.wait_for(self.proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                self.proc.kill()
                await self.proc.wait()
        if self._log_task:
            await self._log_task
        self.proc = None
