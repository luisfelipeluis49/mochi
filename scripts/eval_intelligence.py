"""Score the decision fixtures with the real model. Run through scripts/eval-intelligence.sh."""

import asyncio
import os
import sys

from tests.fixture_support import DecisionFixture, decide_fixture, load_fixtures, matches

from mochi_backend.intelligence.model_port import HintModel
from mochi_backend.intelligence.openai_hint_model import OpenAiHintModel
from mochi_backend.platform.http_client import HttpxClient

MODEL_TIMEOUT_SECONDS = 2.0


def real_model() -> HintModel:
    """The OpenAI-compatible model from the environment (exits with a message when unset)."""
    key = os.environ.get("MODEL_API_KEY", "")
    if not key:
        sys.exit("MODEL_API_KEY is not set; export it or put it in .env")
    base = os.environ.get("MOCHI_MODEL_BASE_URL", "https://api.openai.com/v1")
    name = os.environ.get("MOCHI_MODEL_NAME", "gpt-4o-mini")
    return OpenAiHintModel(HttpxClient(), base, name, key, MODEL_TIMEOUT_SECONDS)


async def passed(fixture: DecisionFixture, model: HintModel) -> bool:
    """Run one fixture; the scripted `model` field is ignored so the real model decides."""
    decision = await decide_fixture(fixture, model)
    return matches(decision, fixture.expect)


async def main() -> int:
    """Print PASS/FAIL per fixture and the overall rate; exit 1 when any fixture fails."""
    model = real_model()
    # case "model" rows script the fake model's answer and share texts with opposite expectations,
    # so a real model cannot satisfy them all; they are unit tests, not an eval.
    scored = [f for f in load_fixtures() if f.case != "model"]
    results = [(f, await passed(f, model)) for f in scored]
    for fixture, ok in results:
        print(("PASS  " if ok else "FAIL  ") + f"{fixture.id}: {fixture.text}")
    wins = sum(1 for _, ok in results if ok)
    print(f"\n{wins}/{len(results)} passed ({100 * wins / len(results):.0f}%)")
    return 0 if wins == len(results) else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
