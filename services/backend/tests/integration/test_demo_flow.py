"""The demo (AGENTS section 2), real app: a meeting, then a review, then the team view.

Turns go over HTTP (`/dev/sessions/{id}/turn`), and so do the review and the team view; the
screens are fake WebSocket clients on the real hub. No model key: rules only, default
`two_turns` cooldown.
"""

from collections.abc import AsyncIterator

import httpx
import pytest

from mochi_backend.app import create_app
from mochi_contracts import DecisionKind, Hint, LearningEvent, LearningState
from tests.fakes.fake_sender import FakeSender
from tests.harness import ANA, BEN, Harness, make_harness

ADIAR = "I need to adiar my meeting tomorrow."
GUARDA_CHUVA = "I forgot my guarda-chuva at the office."


@pytest.fixture
async def demo() -> AsyncIterator[tuple[httpx.AsyncClient, Harness]]:
    harness = make_harness(env={"MOCHI_ENABLE_DEV_ROUTES": "true"})
    transport = httpx.ASGITransport(app=create_app(harness.container))
    async with httpx.AsyncClient(transport=transport, base_url="http://demo") as client:
        assert (await client.post("/api/sessions/demo/start")).status_code == 200
        yield client, harness


async def _say(
    client: httpx.AsyncClient, harness: Harness, text: str, gap: float = 1.0
) -> tuple[DecisionKind, str]:
    """One turn over HTTP, `gap` seconds after the last (the cooldown counts time and turns)."""
    harness.clock.advance(gap)
    reply = await client.post("/dev/sessions/demo/turn", json={"text": text})
    assert reply.status_code == 200
    body = reply.json()
    return DecisionKind(body["decision"]["decision"]), str(body["decision"].get("hint"))


def _payloads(sender: FakeSender, kind: str) -> list[object]:
    return [e.payload for e in sender.events if e.type.value == kind]


async def test_scripted_demo_from_hint_to_recalled_in_a_review(
    demo: tuple[httpx.AsyncClient, Harness],
) -> None:
    client, harness = demo
    ana, ben = await harness.connect_all(ANA, BEN)

    assert (await _say(client, harness, ADIAR))[0] is DecisionKind.SHOW_HINT
    assert (await _say(client, harness, "Oh, why? What's going on?"))[0] is DecisionKind.IGNORE
    assert (await _say(client, harness, "Right, I'll postpone it to Friday."))[
        0
    ] is DecisionKind.IGNORE
    assert (await _say(client, harness, GUARDA_CHUVA))[0] is DecisionKind.SHOW_HINT

    hints = [p for p in _payloads(ana, "hint.created") if isinstance(p, Hint)]
    assert [(h.expression, h.target_user_id) for h in hints] == [
        ("postpone", "ana"),
        ("umbrella", "ana"),
    ]
    assert "hint.created" not in ben.types() and "learning_event.created" not in ben.types()
    brain = harness.container.core.intelligence
    postpone = next(w for w in brain.words_for("ana") if w.expression == "postpone")
    assert postpone.learning_state is LearningState.ASSISTED
    assert (await client.post("/api/sessions/demo/stop")).status_code == 200

    await _review_brings_umbrella_back(client, harness)
    _assert_umbrella_reinforced(brain.words_for("ana"), brain.words_for("ben"))
    await _assert_the_company_sees_numbers_only(client)


async def _review_brings_umbrella_back(client: httpx.AsyncClient, harness: Harness) -> None:
    """Later, on her phone: Ana's own session, in review mode."""
    review = {"mode": "review", "user_id": "ana"}
    started = await client.post("/api/sessions/p-ana/start", json=review)
    assert started.status_code == 200
    assert (started.json()["mode"], started.json()["participants"]) == ("review", ["ana"])
    harness.clock.advance(60)
    said = await client.post(
        "/dev/sessions/p-ana/turn", json={"text": "I left my umbrella at the office."}
    )
    assert said.status_code == 200
    assert (await client.post("/api/sessions/p-ana/stop")).status_code == 200


async def _assert_the_company_sees_numbers_only(client: httpx.AsyncClient) -> None:
    refused = await client.get("/api/companies/demo/insights", params={"viewer": "ben"})
    assert refused.status_code == 403  # Ben is a member, not an administrator
    reply = await client.get("/api/companies/demo/insights", params={"viewer": "ana"})
    assert reply.status_code == 200
    view = reply.json()
    assert (view["totals"]["meetings"], view["totals"]["reviews"]) == (1, 1)
    assert [(g["expression"], g["people"], g["times"]) for g in view["shared_gaps"]] == [
        ("postpone", 1, 1),
        ("umbrella", 1, 1),
    ]
    assert view["funnel"] == {
        "discovered": 2,
        "assisted": 2,
        "reinforced": 1,
        "used_independently": 0,
    }
    assert "adiar my meeting" not in reply.text  # no sentence leaves a person's own page
    mine = await client.get("/api/users/ana/moments", params={"viewer": "ana"})
    assert [m["heard"] for m in mine.json()] == [GUARDA_CHUVA, ADIAR]
    assert (await client.get("/api/users/ana/moments", params={"viewer": "ben"})).status_code == 403


def _assert_umbrella_reinforced(
    ana_words: list[LearningEvent], ben_words: list[LearningEvent]
) -> None:
    assert [w.expression for w in ana_words] == ["umbrella", "postpone"]  # newest first
    umbrella = ana_words[0]
    assert umbrella.learning_state is LearningState.REINFORCED
    assert [s.learning_state for s in umbrella.state_history] == [
        LearningState.DISCOVERED,
        LearningState.REINFORCED,
    ]
    assert ben_words == []


async def test_back_to_back_demo_sentences_hit_the_cooldown(
    demo: tuple[httpx.AsyncClient, Harness],
) -> None:
    """Documents the rule: a hint silences the next two turns, so script filler between them."""
    client, harness = demo
    assert (await _say(client, harness, ADIAR))[0] is DecisionKind.SHOW_HINT
    assert (await _say(client, harness, GUARDA_CHUVA))[0] is DecisionKind.IGNORE


@pytest.fixture
async def shown_demo() -> AsyncIterator[tuple[httpx.AsyncClient, Harness]]:
    """The Render deploy runs MOCHI_HINT_COOLDOWN=while_shown (DECISIONS D-29)."""
    env = {"MOCHI_ENABLE_DEV_ROUTES": "true", "MOCHI_HINT_COOLDOWN": "while_shown"}
    harness = make_harness(env=env)
    transport = httpx.ASGITransport(app=create_app(harness.container))
    async with httpx.AsyncClient(transport=transport, base_url="http://demo") as client:
        assert (await client.post("/api/sessions/demo/start")).status_code == 200
        yield client, harness


async def _four_line_script(
    client: httpx.AsyncClient, harness: Harness, gap: float
) -> DecisionKind:
    """The approved script with `gap` seconds between lines; the decision on the last line."""
    await _say(client, harness, ADIAR, gap)
    await _say(client, harness, "Oh, why? What's going on?", gap)
    await _say(client, harness, "Right, I'll postpone it to Friday.", gap)
    return (await _say(client, harness, GUARDA_CHUVA, gap))[0]


async def test_while_shown_approved_script_shows_the_umbrella_hint(
    shown_demo: tuple[httpx.AsyncClient, Harness],
) -> None:
    """On Render (while_shown) the four-line script still ends in the umbrella hint."""
    client, harness = shown_demo
    for gap in (1.0, 3.0):  # the gap is a fake-clock step; the result must not depend on it
        assert await _four_line_script(client, harness, gap) is DecisionKind.SHOW_HINT


async def test_while_shown_back_to_back_sentences_are_still_held(
    shown_demo: tuple[httpx.AsyncClient, Harness],
) -> None:
    """Pacing rule on Render too: the umbrella line needs filler turns after the postpone hint."""
    client, harness = shown_demo
    assert (await _say(client, harness, ADIAR))[0] is DecisionKind.SHOW_HINT
    assert (await _say(client, harness, GUARDA_CHUVA))[0] is DecisionKind.IGNORE
