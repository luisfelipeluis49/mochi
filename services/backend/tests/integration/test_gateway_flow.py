"""End-to-end through the real gateway and real intelligence, with fakes only at the edges."""

import pytest

from mochi_backend.gateway.agora.client_port import AgentAlreadyStoppedError, AgoraError
from mochi_backend.gateway.errors import ConflictError, NotFoundError, UpstreamError
from mochi_backend.gateway.intelligence_port import IntelligencePort
from mochi_contracts import (
    Activity,
    ActivityCommand,
    ActivityResult,
    Decision,
    DecisionKind,
    Language,
    LearningEvent,
    LearningState,
    PrivatePrompt,
    RoundResult,
    SessionContext,
    Turn,
)
from tests.harness import ANA, AUDIENCE, BEN, HOME, Harness, make_harness

ADIAR = "I need to adiar my meeting tomorrow."
GUARDA_CHUVA = "I forgot my guarda-chuva at the office."


async def _started(
    env: dict[str, str] | None = None, intelligence: IntelligencePort | None = None
) -> Harness:
    harness = make_harness(env=env, intelligence=intelligence)
    await harness.container.sessions.start()
    return harness


async def test_demo_sentence_reaches_ana_home_and_audience_but_never_ben() -> None:
    harness = await _started()
    ana, ben, home, audience = await harness.connect_all(ANA, BEN, HOME, AUDIENCE)
    outcome = await harness.say(ADIAR)
    assert outcome.reply == "" and outcome.decision.decision is DecisionKind.SHOW_HINT
    assert "hint.created" in ana.types() and "learning_event.created" in ana.types()
    assert "hint.created" in home.types() and "hint.created" in audience.types()
    assert "hint.created" not in ben.types() and "learning_event.created" not in ben.types()
    assert "learning_event.created" not in home.types()


async def test_ordinary_talk_publishes_nothing_and_replies_with_silence() -> None:
    harness = await _started()
    home = await harness.connect(HOME)
    before = len(home.texts)
    outcome = await harness.say("Did you watch the match yesterday?")
    assert outcome.reply == "" and len(home.texts) == before


async def test_asking_mochi_speaks_through_the_reply_and_tells_every_screen() -> None:
    harness = await _started()
    clients = [await harness.connect(t) for t in (ANA, BEN, HOME, AUDIENCE)]
    outcome = await harness.say("Oi Mochi, what's the word for fila?")
    assert outcome.reply == "You can say: queue."
    assert all("agent.speak.requested" in c.types() for c in clients)


async def test_turns_while_not_capturing_are_ignored_and_logged() -> None:
    harness = make_harness()
    home = await harness.connect(HOME)
    before = len(home.texts)
    outcome = await harness.say(ADIAR)
    assert outcome.reply == "" and len(home.texts) == before
    assert "turn_ignored_not_capturing" in harness.logger.names()


async def test_empty_text_is_ignored() -> None:
    harness = await _started()
    assert (await harness.say("   ")).decision.decision is DecisionKind.IGNORE


async def test_hint_expires_and_a_newer_hint_replaces_the_old_one() -> None:
    harness = await _started()
    home = await harness.connect(HOME)
    await harness.say(ADIAR)
    harness.clock.advance(8)
    await harness.scheduler.run_due()
    assert home.types()[-1] == "hint.cleared"
    await harness.say("That sounds busy.")
    await harness.say("Yes, very.")
    await harness.say(GUARDA_CHUVA)
    await harness.say("Oi Mochi, what's the word for fila?")  # wake phrase beats cooldown
    assert home.types()[-5:].count("hint.created") == 2


async def test_a_failing_or_slow_decide_means_silence() -> None:
    class Broken:
        async def decide(self, turn: Turn, context: SessionContext) -> Decision:
            raise RuntimeError("boom")

        def handle(self, command: ActivityCommand, context: SessionContext) -> ActivityResult:
            raise NotImplementedError

        def apply(self, proposals: list[LearningEvent]) -> list[LearningEvent]:
            return proposals

        def words_for(self, user_id: str) -> list[LearningEvent]:
            return []

        def reset(self) -> None:
            return None

        def session_started(self, woken: bool, language: Language | None = None) -> None:
            return None

        def device_status(
            self, volume: int | None, temperature: int | None, voices: list[str], who: str | None
        ) -> None:
            return None

    harness = await _started(intelligence=Broken())
    outcome = await harness.say(ADIAR)
    assert outcome.reply == "" and outcome.decision.decision is DecisionKind.IGNORE
    assert "decide_failed" in harness.logger.names()


async def test_snapshot_on_connect_respects_visibility() -> None:
    harness = await _started()
    await harness.say(ADIAR)
    ana, ben, audience = await harness.connect_all(ANA, BEN, AUDIENCE)
    assert ana.types() == [
        "session.state.changed",
        "activity.state.changed",
        "hint.created",
        "learning_event.created",  # her saved word, replayed (words survive a restart)
    ]
    assert ben.types() == ["session.state.changed", "activity.state.changed"]
    assert audience.types()[-1] == "hint.created"


async def test_sequence_counts_up_by_one_on_the_global_stream() -> None:
    harness = await _started()
    home = await harness.connect(HOME)
    await harness.say(ADIAR)
    await harness.container.demo_reset.run()
    numbers = [e.sequence for e in home.events]
    assert numbers == sorted(numbers) and numbers[-1] > numbers[0]
    assert len(set(numbers)) == len(numbers)


async def test_session_start_and_stop_are_idempotent_and_drive_device_state() -> None:
    harness = make_harness()
    devices = harness.container.devices
    assert devices.state("home_pi_01").agora is None
    await harness.container.sessions.start()
    await harness.container.sessions.start()
    assert len(harness.agora.started) == 1
    state = devices.state("home_pi_01")
    assert state.capturing and state.agora is not None and state.agora.uid == 1001
    assert state.speaker_muted is False
    await harness.container.sessions.stop()
    await harness.container.sessions.stop()
    after = devices.state("home_pi_01")
    assert (after.capturing, after.agora) == (False, None)
    assert harness.agora.stopped == ["agent-1"]


async def test_the_agent_gets_the_turn_endpoint_and_our_key() -> None:
    harness = await _started()
    request = harness.agora.started[0]
    assert request.llm_url.endswith("/agora/llm/demo/chat/completions")
    assert request.llm_key == "k" and request.agent_uid == 1002 and request.remote_uid == 1001


async def test_pi_token_is_cached_until_near_expiry() -> None:
    harness = await _started()
    devices = harness.container.devices
    first = devices.state("home_pi_01").agora
    again = devices.state("home_pi_01").agora
    assert first is not None and again is not None and first.token == again.token
    harness.clock.advance(3600 - 60)  # inside the 5-minute refresh margin
    refreshed = devices.state("home_pi_01").agora
    assert refreshed is not None and first is not None and refreshed.token != first.token


async def test_unknown_device_is_not_found() -> None:
    with pytest.raises(NotFoundError, match="unknown device 'pi_99'"):
        make_harness().container.devices.state("pi_99")


async def test_agora_start_failure_is_a_502_and_leaves_no_partial_state() -> None:
    harness = make_harness()
    harness.agora.start_error = AgoraError("POST /join returned 401")
    with pytest.raises(UpstreamError, match="could not start the Agora agent"):
        await harness.container.sessions.start()
    store = harness.container.core.store
    assert not store.capturing and store.agent_id is None and store.pi_token is None
    assert harness.container.devices.state("home_pi_01").agora is None


async def test_stop_tolerates_an_agent_that_is_already_gone() -> None:
    harness = await _started()
    harness.agora.stop_error = AgentAlreadyStoppedError("gone")
    state = await harness.container.sessions.stop()
    assert state.capturing is False and state.status.value == "ended"


async def test_stop_still_stops_locally_when_agora_is_unreachable() -> None:
    harness = await _started()
    harness.agora.stop_error = AgoraError("timeout")
    assert (await harness.container.sessions.stop()).capturing is False


async def test_mute_speaker_strategy_mutes_except_while_speaking() -> None:
    harness = await _started(env={"MOCHI_SILENCE_STRATEGY": "mute_speaker"})
    devices = harness.container.devices
    assert devices.state("home_pi_01").speaker_muted is True
    await harness.say("Oi Mochi, what's the word for fila?")
    assert devices.state("home_pi_01").speaker_muted is False
    harness.clock.advance(5)
    assert devices.state("home_pi_01").speaker_muted is True


async def test_empty_reply_strategy_never_mutes() -> None:
    harness = await _started()
    await harness.say("Oi Mochi, what's the word for fila?")
    assert harness.container.devices.state("home_pi_01").speaker_muted is False


async def test_reset_clears_words_game_and_hint_but_keeps_capturing() -> None:
    harness = await _started()
    ana, home = await harness.connect(ANA), await harness.connect(HOME)
    await harness.say(ADIAR)
    await harness.container.activity.start()
    await harness.container.demo_reset.run()
    assert harness.container.core.intelligence.words_for("ana") == []
    assert harness.container.core.store.capturing
    assert harness.container.core.live_hint.current is None
    assert home.types()[-2:] == ["session.state.changed", "activity.state.changed"]
    last = ana.events[-1].payload
    assert isinstance(last, Activity) and last.state.value == "IDLE"


async def test_activity_conflicts_are_409s() -> None:
    harness = await _started()
    with pytest.raises(ConflictError, match="expected ACTIVE_ROUND"):
        await harness.container.activity.finish(RoundResult.GUESSED)


async def test_the_full_walkthrough_from_agents_section_2() -> None:
    harness = make_harness()
    await harness.container.sessions.start()
    ana, ben = await harness.connect(ANA), await harness.connect(BEN)
    home, audience = await harness.connect(HOME), await harness.connect(AUDIENCE)
    before = len(home.texts)
    ordinary = await harness.say("Did you watch the match yesterday?")
    assert ordinary.decision.decision is DecisionKind.IGNORE and ordinary.decision.hint is None
    assert ordinary.reply == "" and len(home.texts) == before  # nothing was published
    await harness.say(ADIAR)
    await harness.say("That sounds stressful.")
    await harness.say(
        "Yes, I will postpone it until Thursday."
    )  # filler turns respect the cooldown
    await harness.say(GUARDA_CHUVA)
    cut = len(audience.texts)
    await harness.container.activity.start()
    prompt = [e for e in home.events if e.type.value == "activity.private_prompt"][0]
    assert isinstance(prompt.payload, PrivatePrompt)
    assert prompt.payload.secret_word == "umbrella"
    for watcher in (ana, ben, audience):
        assert "activity.private_prompt" not in watcher.types()
    assert all("umbrella" not in t for t in audience.texts[cut:])
    await harness.container.activity.finish(RoundResult.GUESSED)
    assert "umbrella" in "".join(audience.texts[-3:])  # the result, the session, Mochi's line
    assert harness.agora.spoken[-1][1] == "Ana got it!"  # the host confirms it out loud
    words = {
        e.expression: e.learning_state for e in harness.container.core.intelligence.words_for("ana")
    }
    assert words == {"umbrella": LearningState.REINFORCED, "postpone": LearningState.ASSISTED}
    assert harness.container.core.intelligence.words_for("ben") == []
    assert [e.type.value for e in ben.events].count("hint.created") == 0
    await harness.container.sessions.stop()
    assert harness.container.devices.state("home_pi_01").capturing is False


async def test_home_reconnecting_mid_round_gets_the_private_prompt_and_nobody_else_does() -> None:
    harness = make_harness()
    await harness.container.sessions.start()
    await harness.container.activity.start()
    home, audience, ana, ben = await harness.connect_all(HOME, AUDIENCE, ANA, BEN)
    prompts = [e for e in home.events if e.type.value == "activity.private_prompt"]
    assert len(prompts) == 1 and isinstance(prompts[0].payload, PrivatePrompt)
    assert home.types().index("activity.private_prompt") > home.types().index(
        "activity.state.changed"
    )
    secret = prompts[0].payload.secret_word
    for watcher in (audience, ana, ben):
        assert "activity.private_prompt" not in watcher.types()
        assert all(secret not in text for text in watcher.texts)


async def test_no_private_prompt_after_the_round_ends_or_the_session_stops() -> None:
    harness = make_harness()
    await harness.container.sessions.start()
    await harness.container.activity.start()
    await harness.container.activity.finish(RoundResult.GUESSED)
    assert "activity.private_prompt" not in (await harness.connect(HOME)).types()
    await harness.container.activity.start()
    await harness.container.sessions.stop()
    assert "activity.private_prompt" not in (await harness.connect(HOME)).types()
    await harness.container.sessions.start()
    await harness.container.activity.start()
    await harness.container.demo_reset.run()
    assert "activity.private_prompt" not in (await harness.connect(HOME)).types()
