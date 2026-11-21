"""Print Agora's per-turn latency for one agent. Run through scripts/agora-turns.sh.

Usage: agora_turns.py [AGENT_ID]   (else MOCHI_AGENT_ID, else `agent_started` on stdin)
Needs AGORA_APP_ID, AGORA_REST_KEY, AGORA_REST_SECRET. Read-only.
"""

import asyncio
import json
import os
import sys

from mochi_backend.gateway.agora.rest_client import AgoraTurnsClient
from mochi_backend.gateway.agora.turns_client import TurnsError, markdown_table
from mochi_backend.platform.http_client import HttpTransportError, HttpxClient


def agent_id_from_log(lines: list[str]) -> str:
    """The `agent_id` of the last `agent_started` JSON log line, or ""."""
    found = ""
    for line in lines:
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and record.get("event") == "agent_started":
            found = str(record.get("agent_id", ""))
    return found


def main(argv: list[str]) -> int:
    """Fetch and print the table; returns the exit code."""
    agent_id = argv[1] if len(argv) > 1 else os.environ.get("MOCHI_AGENT_ID", "")
    if not agent_id and not sys.stdin.isatty():
        agent_id = agent_id_from_log(sys.stdin.read().splitlines())
    names = ("AGORA_APP_ID", "AGORA_REST_KEY", "AGORA_REST_SECRET")
    missing = [name for name in names if not os.environ.get(name)]
    if missing or not agent_id:
        print(f"need an agent id (argument, MOCHI_AGENT_ID, or piped log) and env: {missing}")
        return 2
    client = AgoraTurnsClient(
        HttpxClient(),
        os.environ["AGORA_APP_ID"],
        os.environ["AGORA_REST_KEY"],
        os.environ["AGORA_REST_SECRET"],
    )
    try:
        turns = asyncio.run(client.turns(agent_id))
    except (TurnsError, HttpTransportError) as error:
        print(f"could not read turns: {error}")
        return 1
    # Agora answers 404 while the agent runs: turns are readable only after it leaves.
    print(
        markdown_table(turns)
        if turns
        else "No turns found (agent still running, unknown, or silent)."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
