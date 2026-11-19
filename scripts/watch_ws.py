"""Print every event a connection receives.

Usage: scripts/watch_ws.py --as user=ana | user=ben | device=home_pi_01 | view=audience
Run with: uv run --project services/backend python scripts/watch_ws.py --as user=ana
"""

import argparse
import asyncio
import json
import os

from websockets.asyncio.client import connect


def websocket_url(base_url: str, query: str) -> str:
    """Example: ("http://localhost:8000", "user=ana") -> "ws://localhost:8000/ws?user=ana"."""
    scheme = "wss" if base_url.startswith("https") else "ws"
    host = base_url.split("://", 1)[1].rstrip("/")
    return f"{scheme}://{host}/ws?{query}"


def one_line(raw: str) -> str:
    """Summarise an envelope: sequence, type and payload."""
    event = json.loads(raw)
    payload = json.dumps(event["payload"], ensure_ascii=False)
    return f"#{event['sequence']:>4} {event['type']:<26} {payload}"


async def watch(url: str) -> None:
    """Connect and print until interrupted or closed."""
    async with connect(url) as socket:
        print(f"connected: {url}")
        async for message in socket:
            print(one_line(str(message)), flush=True)


def main() -> None:
    """CLI entry."""
    parser = argparse.ArgumentParser(description="Watch Mochi WebSocket events.")
    parser.add_argument(
        "--as", dest="query", required=True, help="user=ana | device=home_pi_01 | view=audience"
    )
    parser.add_argument(
        "--base-url", default=os.environ.get("MOCHI_BASE_URL", "http://localhost:8000")
    )
    args = parser.parse_args()
    try:
        asyncio.run(watch(websocket_url(args.base_url, args.query)))
    except KeyboardInterrupt:
        print("bye")


if __name__ == "__main__":
    main()
