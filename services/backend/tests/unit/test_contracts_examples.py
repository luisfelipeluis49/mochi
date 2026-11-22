"""Every committed example loads into its model and round-trips unchanged."""

import json
from pathlib import Path

import pytest
from pydantic import BaseModel, ValidationError

from mochi_contracts import (
    Company,
    ConversationReport,
    Decision,
    Envelope,
    EventType,
    HeardPhrase,
    Hint,
    HintCleared,
    LearningEvent,
    Member,
    SessionContext,
    SessionRecord,
    SessionState,
    Speak,
    SuggestedPhrase,
    TeamInsights,
    TeamMember,
    TranscriptLine,
    Turn,
    User,
    Utterance,
    VoiceprintUpload,
    VoiceProfile,
    WordMoment,
)

EXAMPLES = Path(__file__).resolve().parents[4] / "packages" / "contracts" / "examples"
PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "session": SessionState,
    "hint": Hint,
    "hint_cleared": HintCleared,
    "learning_event": LearningEvent,
    "speak": Speak,
    "turn": Turn,
    "session_context": SessionContext,
    "decision": Decision,
    "user": User,
    "voice_profile": VoiceProfile,
    "voiceprint_upload": VoiceprintUpload,
    "company": Company,
    "member": Member,
    "team_member": TeamMember,
    "session_record": SessionRecord,
    "word_moment": WordMoment,
    "utterance": Utterance,
    "heard_phrase": HeardPhrase,
    "team_insights": TeamInsights,
    "transcript_line": TranscriptLine,
    "conversation_report": ConversationReport,
    "suggested_phrase": SuggestedPhrase,
}


@pytest.mark.parametrize("name", sorted(PAYLOAD_MODELS))
def test_payload_example_round_trips(name: str) -> None:
    raw = json.loads((EXAMPLES / "payloads" / f"{name}.json").read_text())
    model = PAYLOAD_MODELS[name].model_validate(raw)
    assert json.loads(model.model_dump_json()) == raw


@pytest.mark.parametrize("path", sorted((EXAMPLES / "events").glob("*.json")), ids=lambda p: p.stem)
def test_event_example_round_trips(path: Path) -> None:
    raw = json.loads(path.read_text())
    envelope = Envelope.model_validate(raw)
    assert json.loads(envelope.model_dump_json()) == raw
    assert envelope.type.value == raw["type"]


def test_every_event_type_has_an_example() -> None:
    names = {p.stem for p in (EXAMPLES / "events").glob("*.json")}
    assert names == {event.value for event in EventType}


def test_unknown_field_is_rejected() -> None:
    raw = json.loads((EXAMPLES / "payloads" / "hint.json").read_text())
    with pytest.raises(ValidationError):
        Hint.model_validate({**raw, "surprise": 1})


def test_payload_must_match_event_type() -> None:
    raw = json.loads((EXAMPLES / "events" / "hint.created.json").read_text())
    raw["type"] = "agent.speak.requested"
    with pytest.raises(ValidationError, match="needs a Speak payload"):
        Envelope.model_validate(raw)
