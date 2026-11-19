"""Routing table (AGENTS 6.2), hub, live hint, silence, SSE, settings, Agora REST adapter."""

import json

import pytest

from mochi_backend.gateway.agora.client_port import (
    AgentAlreadyStopped,
    AgentStartRequest,
    AgoraError,
    SpeechTuning,
)
from mochi_backend.gateway.agora.rest_client import AgoraRestClient, join_body
from mochi_backend.gateway.connections import parse_target
from mochi_backend.gateway.delivery_rules import is_recipient
from mochi_backend.gateway.event_hub import EventHub
from mochi_backend.gateway.live_hint import LiveHint
from mochi_backend.gateway.openai_sse import completion_json, parse_stream, sse_events
from mochi_backend.gateway.routes.agora_llm import (
    ChatMessage,
    ContentPart,
    last_user_text,
    presented_key,
)
from mochi_backend.gateway.silence_policy import SilencePolicy, Strategy
from mochi_backend.platform.http_client import HttpResponse, HttpTransportError
from mochi_backend.platform.ids import SequentialIdGenerator
from mochi_backend.settings import SettingsError, load_settings
from mochi_contracts import (
    Activity,
    EventPayload,
    EventType,
    GameState,
    HintCleared,
    Language,
    LearningEvent,
    LearningState,
    PrivatePrompt,
    Reason,
    SessionMode,
    SessionState,
    SessionStatus,
    Speak,
    SpeakReason,
    StateChange,
)
from tests.factories import make_hint
from tests.fakes.fake_clock import FakeClock
from tests.fakes.fake_http_client import FakeHttpClient
from tests.fakes.fake_scheduler import FakeScheduler
from tests.fakes.fake_sender import FakeEventLogger, FakeSender
from tests.harness import ANA, AUDIENCE, BEN, HOME

SESSION = SessionState(
    status=SessionStatus.ACTIVE,
    mode=SessionMode.TOGETHER,
    focus=Language.EN,
    capturing=True,
    participants=["ana", "ben"],
)
SPEAK = Speak(text="hi", language=Language.EN, reason=SpeakReason.ASKS_MOCHI)
PROMPT = PrivatePrompt(
    round_id="r", describer_user_id="ben", secret_word="umbrella", source_learning_event_id=None
)


def _card(user: str | None) -> LearningEvent:
    return LearningEvent(
        learning_event_id="l1",
        user_id=user,
        target_language=Language.EN,
        expression="x",
        meaning=None,
        detection_signal=Reason.CODE_SWITCH,
        hint_id=None,
        learning_state=LearningState.DISCOVERED,
        state_history=[
            StateChange(learning_state=LearningState.DISCOVERED, at="2026-11-19T16:00:00.000Z")
        ],
    )


def _activity(state: GameState, revealed: str | None = None, text: str = "go") -> Activity:
    return Activity(
        activity_id="describe_and_guess",
        round_id="r",
        state=state,
        describer_user_id="ben",
        guesser_user_id="ana",
        public_instruction=text,
        result=None,
        revealed_word=revealed,
        word_source=None,
    )


HINT_FOR_ANA = make_hint(0)
HINT_FOR_ALL = HINT_FOR_ANA.model_copy(update={"target_user_id": None})
TARGETS = {"ana": ANA, "ben": BEN, "home": HOME, "audience": AUDIENCE}


@pytest.mark.parametrize(
    ("event", "payload", "hint_user", "expected"),
    [
        (EventType.SESSION_STATE_CHANGED, SESSION, None, {"ana", "ben", "home", "audience"}),
        (EventType.HINT_CREATED, HINT_FOR_ANA, "ana", {"ana", "home", "audience"}),
        (EventType.HINT_CREATED, HINT_FOR_ALL, None, {"ana", "ben", "home", "audience"}),
        (EventType.HINT_CLEARED, HintCleared(hint_id="h"), "ana", {"ana", "home", "audience"}),
        (
            EventType.ACTIVITY_STATE_CHANGED,
            _activity(GameState.IDLE),
            None,
            {"ana", "ben", "home", "audience"},
        ),
        (EventType.ACTIVITY_PRIVATE_PROMPT, PROMPT, None, {"home"}),
        (EventType.LEARNING_EVENT_CREATED, _card("ana"), None, {"ana"}),
        (EventType.LEARNING_EVENT_UPDATED, _card("ben"), None, {"ben"}),
        (EventType.LEARNING_EVENT_CREATED, _card(None), None, set()),
        (EventType.AGENT_SPEAK_REQUESTED, SPEAK, None, {"ana", "ben", "home", "audience"}),
    ],
)
def test_routing_table_row(
    event: EventType, payload: EventPayload, hint_user: str | None, expected: set[str]
) -> None:
    got = {n for n, t in TARGETS.items() if is_recipient(event, payload, t, hint_user)}
    assert got == expected


def _hub() -> tuple[EventHub, FakeEventLogger]:
    logger = FakeEventLogger()
    return EventHub(FakeClock(), SequentialIdGenerator(), logger), logger


async def test_hub_sets_every_envelope_field_and_counts_up_by_one() -> None:
    hub, _ = _hub()
    first = await hub.publish(EventType.SESSION_STATE_CHANGED, SESSION)
    second = await hub.publish(EventType.AGENT_SPEAK_REQUESTED, SPEAK)
    assert (first.schema_version, first.session_id) == ("0.4", "demo")
    assert first.emitted_at == "2026-11-19T16:00:00.000Z"
    assert (first.sequence, second.sequence) == (1, 2)
    assert first.event_id != second.event_id


async def test_hub_drops_a_dead_socket_without_breaking_the_broadcast() -> None:
    hub, logger = _hub()
    dead, alive = FakeSender(), FakeSender()
    dead.broken = True
    hub.register(ANA, dead)
    hub.register(BEN, alive)
    await hub.publish(EventType.SESSION_STATE_CHANGED, SESSION)
    await hub.publish(EventType.SESSION_STATE_CHANGED, SESSION)
    assert len(alive.texts) == 2 and "connection_dropped" in logger.names()


async def test_hub_strips_a_revealed_word_from_an_active_round() -> None:
    hub, logger = _hub()
    sender = FakeSender()
    hub.register(AUDIENCE, sender)
    await hub.publish(
        EventType.ACTIVITY_STATE_CHANGED, _activity(GameState.ACTIVE_ROUND, "umbrella")
    )
    [event] = sender.events
    assert isinstance(event.payload, Activity) and event.payload.revealed_word is None
    assert "secret_leak_blocked" in logger.names()


async def test_hub_blocks_the_secret_from_the_audience_until_the_result() -> None:
    hub, _ = _hub()
    audience, home = FakeSender(), FakeSender()
    hub.register(AUDIENCE, audience)
    hub.register(HOME, home)
    await hub.publish(EventType.ACTIVITY_PRIVATE_PROMPT, PROMPT)
    leaky = _activity(GameState.ACTIVE_ROUND, text="Find the umbrella")
    await hub.publish(EventType.ACTIVITY_STATE_CHANGED, leaky)
    assert all("umbrella" not in t for t in audience.texts)
    assert home.types() == ["activity.private_prompt", "activity.state.changed"]
    await hub.publish(
        EventType.ACTIVITY_STATE_CHANGED, _activity(GameState.ROUND_RESULT, "umbrella")
    )
    assert "umbrella" in audience.texts[-1]


async def test_live_hint_expires_on_schedule_and_is_replaced_by_a_newer_one() -> None:
    clock = FakeClock()
    hub = EventHub(clock, SequentialIdGenerator(), FakeEventLogger())
    scheduler = FakeScheduler(clock)
    live, sender = LiveHint(hub, clock, scheduler), FakeSender()
    hub.register(HOME, sender)
    first, second = make_hint(0), make_hint(0.0).model_copy(update={"hint_id": "hint_b"})
    await live.show(first)
    await live.show(second)  # replaces the first immediately
    assert sender.types() == ["hint.created", "hint.cleared", "hint.created"]
    clock.advance(8)
    assert await scheduler.run_due() == 1  # only the second hint's expiry is still pending
    assert sender.types()[-1] == "hint.cleared" and live.current is None


@pytest.mark.parametrize(
    ("strategy", "idle", "speaking"), [("empty_reply", False, False), ("mute_speaker", True, False)]
)
def test_silence_policy_strategies(strategy: Strategy, idle: bool, speaking: bool) -> None:
    clock = FakeClock()
    policy = SilencePolicy(strategy, clock, 0.6, 0.45)
    assert policy.speaker_muted() is idle
    policy.begin_speaking("You can say: queue.")
    assert policy.speaker_muted() is speaking
    if strategy == "mute_speaker":
        clock.advance(0.6 + 0.45 * 4 + 0.1)  # 4 words, window over
        assert policy.speaker_muted() is True


def test_mute_window_can_be_closed_early() -> None:
    policy = SilencePolicy("mute_speaker", FakeClock(), 0.6, 0.45)
    policy.begin_speaking("hello there")
    assert policy.speaker_muted() is False
    policy.finished_speaking()
    assert policy.speaker_muted() is True


def test_sse_empty_reply_and_spoken_reply_parse_back() -> None:
    assert parse_stream("".join(sse_events(""))) == ("", True)
    assert parse_stream("".join(sse_events("You can say: queue."))) == ("You can say: queue.", True)
    assert completion_json("hi")["choices"][0]["message"]["content"] == "hi"  # type: ignore[index]


def test_last_user_text_reads_strings_and_parts() -> None:
    messages = [
        ChatMessage(role="system", content="be quiet"),
        ChatMessage(role="user", content="first"),
        ChatMessage(role="assistant", content="ok"),
        ChatMessage(role="user", content=[ContentPart(type="text", text="I need to adiar it")]),
    ]
    assert last_user_text(messages) == "I need to adiar it"
    assert last_user_text([]) == ""


def test_presented_key_prefers_our_header_then_bearer() -> None:
    assert presented_key("mine", "Bearer other") == "mine"
    assert presented_key(None, "Bearer other") == "other"
    assert presented_key(None, None) == ""


def test_parse_target_accepts_the_three_shapes_and_explains_the_rest() -> None:
    assert parse_target({"user": "ana"}) == ANA
    assert parse_target({"device": "home_pi_01"}) == HOME
    assert parse_target({"view": "audience"}) == AUDIENCE
    with pytest.raises(ValueError, match=r"unknown connection query .*'zed'.*user=ana\|ben"):
        parse_target({"user": "zed"})


def test_settings_fake_mode_gets_a_dev_key() -> None:
    assert load_settings({"MOCHI_AGORA_MODE": "fake"}).mochi_turn_key == "dev-turn-key"


def test_settings_real_mode_names_what_is_missing() -> None:
    with pytest.raises(SettingsError, match="AGORA_APP_ID"):
        load_settings({"MOCHI_AGORA_MODE": "real"})


def test_settings_errors_mask_secrets_and_name_the_variable() -> None:
    with pytest.raises(SettingsError) as raised:
        load_settings({"MOCHI_AGORA_MODE": "fake", "MOCHI_PI_UID": "abc"})
    assert "MOCHI_PI_UID" in str(raised.value) and "'abc'" in str(raised.value)
    with pytest.raises(SettingsError) as masked:
        load_settings({"MOCHI_AGORA_MODE": "fake", "MODEL_API_KEY": "s3cret", "MOCHI_PI_UID": "x"})
    assert "s3cret" not in str(masked.value)


REQUEST = AgentStartRequest(
    "chan", 1002, 1001, "tok", "https://x/agora/llm/demo/chat/completions", "k", SpeechTuning()
)


def _client(*replies: HttpResponse | HttpTransportError) -> tuple[AgoraRestClient, FakeHttpClient]:
    http = FakeHttpClient(list(replies))
    return AgoraRestClient(http, "APPID", "rk", "rest-secret-xyz", SequentialIdGenerator()), http


def test_join_body_uses_the_verified_field_names() -> None:
    body = join_body(REQUEST, "mochi_001")
    assert isinstance(body, dict) and body["name"] == "mochi_001"
    props = body["properties"]
    assert isinstance(props, dict)
    assert props["agent_rtc_uid"] == "1002" and props["remote_rtc_uids"] == ["1001"]
    llm = props["llm"]
    assert (
        isinstance(llm, dict) and llm["headers"] == {"X-Mochi-Key": "k"} and llm["api_key"] == "k"
    )
    assert "greeting_message" not in llm and "failure_message" not in llm
    assert props["parameters"] == {"silence_config": {"timeout_ms": 0}}


async def test_start_agent_posts_to_join_with_basic_auth_and_returns_the_id() -> None:
    client, http = _client(HttpResponse(200, json.dumps({"agent_id": "A1", "status": "RUNNING"})))
    assert await client.start_agent(REQUEST) == "A1"
    post = http.posts[0]
    assert post.url == "https://api.agora.io/api/conversational-ai-agent/v2/projects/APPID/join"
    assert post.headers["Authorization"].startswith("Basic ")
    assert "rest-secret-xyz" not in json.dumps(
        post.payload
    )  # the REST secret never goes in the body


async def test_start_agent_retries_once_on_5xx_then_fails_with_a_readable_error() -> None:
    client, http = _client(
        HttpResponse(502, "bad gateway"), HttpResponse(200, '{"agent_id": "A2"}')
    )
    assert await client.start_agent(REQUEST) == "A2" and len(http.posts) == 2
    failing, _ = _client(HttpResponse(400, '{"detail":"bad"}'))
    with pytest.raises(AgoraError, match=r"returned 400; expected 200"):
        await failing.start_agent(REQUEST)
    down, _ = _client(HttpTransportError("down"), HttpTransportError("down"))
    with pytest.raises(AgoraError, match="failed twice"):
        await down.start_agent(REQUEST)


async def test_stop_and_speak_use_the_documented_endpoints() -> None:
    client, http = _client(HttpResponse(200, ""), HttpResponse(200, "{}"), HttpResponse(404, ""))
    await client.stop_agent("A1")
    await client.speak("A1", "x" * 600)
    with pytest.raises(AgentAlreadyStopped):
        await client.stop_agent("A1")
    assert http.posts[0].url.endswith("/agents/A1/leave") and http.posts[0].payload is None
    assert http.posts[1].url.endswith("/agents/A1/speak")
    assert (
        isinstance(http.posts[1].payload, dict) and len(str(http.posts[1].payload["text"])) == 512
    )
