"""The two-minute demo (AGENTS section 2, scripted per INTELLIGENCE_PLAN 4), real app.

Turns and the game go over HTTP (`/dev/sessions/demo/turn`, the activity endpoints); the screens are
fake WebSocket clients on the real hub. No model key: rules only, default `two_turns` cooldown.
"""

from collections.abc import AsyncIterator

import httpx
import pytest

from mochi_backend.app import create_app
from mochi_contracts import (
    Activity,
    DecisionKind,
    GameState,
    Hint,
    LearningEvent,
    LearningState,
    PrivatePrompt,
)
from tests.fakes.fake_sender import FakeSender
from tests.harness import ANA, AUDIENCE, BEN, HOME, Harness, make_harness

ADIAR = "I need to adiar my meeting tomorrow."
GUARDA_CHUVA = "I forgot my guarda-chuva at the office."


@pytest.fixture
async def demo() -> AsyncIterator[tuple[httpx.AsyncClient, Harness]]:
    harness = make_harness(env={"MOCHI_ENABLE_DEV_ROUTES": "true"})
    transport = httpx.ASGITransport(app=create_app(harness.container))
    async with httpx.AsyncClient(transport=transport, base_url="http://demo") as client:
        assert (await client.post("/api/sessions/demo/start")).status_code == 200
        yield client, harness


async def _say(client: httpx.AsyncClient, harness: Harness, text: str) -> tuple[DecisionKind, str]:
    """One turn over HTTP, one second after the last (the cooldown counts time and turns)."""
    harness.clock.advance(1.0)
    reply = await client.post("/dev/sessions/demo/turn", json={"text": text})
    assert reply.status_code == 200
    body = reply.json()
    return DecisionKind(body["decision"]["decision"]), str(body["decision"].get("hint"))


def _payloads(sender: FakeSender, kind: str) -> list[object]:
    return [e.payload for e in sender.events if e.type.value == kind]


async def test_scripted_demo_from_hint_to_recalled_in_a_game(
    demo: tuple[httpx.AsyncClient, Harness],
) -> None:
    client, harness = demo
    ana, ben, home, audience = await harness.connect_all(ANA, BEN, HOME, AUDIENCE)

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

    cut = len(audience.texts)
    assert (await client.post("/api/sessions/demo/activity/start")).status_code == 200
    prompts = [
        p for p in _payloads(home, "activity.private_prompt") if isinstance(p, PrivatePrompt)
    ]
    assert [p.secret_word for p in prompts] == ["umbrella"]
    # umbrella is also a stock word, so a saved-word link proves the word came from Ana's card.
    assert prompts[0].source_learning_event_id is not None
    _assert_secret_hidden_while_active(audience, ana, ben, home, cut)

    done = await client.post("/api/sessions/demo/activity/result", json={"result": "guessed"})
    assert done.status_code == 200
    assert done.json()["revealed_word"] == "umbrella"
    _assert_umbrella_reinforced(brain.words_for("ana"), brain.words_for("ben"))


def _assert_secret_hidden_while_active(
    audience: FakeSender, ana: FakeSender, ben: FakeSender, home: FakeSender, cut: int
) -> None:
    for watcher in (audience, ana, ben):
        assert "activity.private_prompt" not in watcher.types()
    for watcher in (audience, ana, ben, home):
        for event in watcher.events:
            if event.type.value != "activity.state.changed":
                continue
            assert isinstance(event.payload, Activity)
            if event.payload.state is GameState.ACTIVE_ROUND:
                assert event.payload.revealed_word is None
    assert all("umbrella" not in text for text in audience.texts[cut:])


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
