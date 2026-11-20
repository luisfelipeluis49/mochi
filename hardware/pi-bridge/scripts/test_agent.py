#!/usr/bin/env python3
"""Start the stand-in Agora agent by hand (no wake word). TESTING ONLY.

Uses the same agent as the supervisor (mochi_device.backends.TestAgentBackend, settings from
config/mochi.toml [test_agent]) and writes the bridge's join settings to .env.session so that
scripts/run.sh can join. Normally you want scripts/mochi.sh instead, which does all of this
automatically after "Oi Mochi".

  terminal 1:  .venv/bin/python scripts/test_agent.py [--stt-language multi] [--mode echo]
  terminal 2:  ./scripts/run.sh
"""
import argparse
import asyncio
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dotenv import load_dotenv  # noqa: E402
from mochi_device import config  # noqa: E402
from mochi_device.backends import TestAgentBackend  # noqa: E402
from mochi_device.device import Device  # noqa: E402

ECHO = ("You are a microphone test. After every user turn, reply with exactly: 'I heard:' followed by "
        "the user's words, word for word, including any non-English words. Never add anything else.")


async def main() -> int:
    cfg = config.load()["test_agent"]
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--channel", default=cfg["channel"])
    ap.add_argument("--stt-language", default=cfg.get("stt_language", "multi"))
    ap.add_argument("--mode", choices=["echo", "chat"], default="echo")
    args = ap.parse_args()
    cfg.update(channel=args.channel, stt_language=args.stt_language)
    if args.mode == "echo":
        cfg.update(instructions=ECHO, greeting="Mochi test agent ready.")

    load_dotenv(config.BRIDGE_DIR / ".env")
    backend = TestAgentBackend(cfg, Device(config.load()["audio"]))
    join = await backend.start()
    env = config.BRIDGE_DIR / ".env.session"
    env.write_text(f"AGORA_CHANNEL={join.channel}\nAGORA_UID={join.uid}\nAGORA_TOKEN={join.token}\n")
    env.chmod(0o600)
    print(f"Mode {args.mode}, STT {args.stt_language}. Bridge settings in .env.session; run ./scripts/run.sh. "
          "Ctrl-C stops the agent.", flush=True)

    stop = asyncio.Event()
    for s in (signal.SIGINT, signal.SIGTERM):
        asyncio.get_running_loop().add_signal_handler(s, stop.set)
    await stop.wait()
    print("Stopping agent...", flush=True)
    await backend.stop()
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
