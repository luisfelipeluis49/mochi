"""Canonical names from AGENTS.md section 6.3. Spell them exactly like this everywhere."""

from enum import StrEnum


class DecisionKind(StrEnum):
    """What `decide()` wants done with a turn."""

    IGNORE = "IGNORE"
    SHOW_HINT = "SHOW_HINT"
    SPEAK = "SPEAK"


class Reason(StrEnum):
    """Why a hint was made (`reason` / `detection_signal`)."""

    CODE_SWITCH = "code_switch"
    SAYS_UNKNOWN = "says_unknown"
    ASKS_PARTNER = "asks_partner"
    ASKS_MOCHI = "asks_mochi"
    TRAILS_OFF = "trails_off"
    TALKS_AROUND = "talks_around"
    RESTARTS = "restarts"
    LOOK_ALIKE = "look_alike"
    NOT_UNDERSTOOD = "not_understood"


class SpeakReason(StrEnum):
    """Why Mochi speaks aloud."""

    ASKS_MOCHI = "asks_mochi"
    ACTIVITY_HOST = "activity_host"


class Language(StrEnum):
    """The two MVP languages."""

    EN = "en"
    PT_BR = "pt-BR"


class SessionStatus(StrEnum):
    """Session lifecycle."""

    CREATED = "created"
    ACTIVE = "active"
    PAUSED = "paused"
    ENDED = "ended"


class SessionMode(StrEnum):
    """Whether people talk freely or play a game."""

    TOGETHER = "together"
    ACTIVITY = "activity"


class GameState(StrEnum):
    """Describe & Guess states."""

    IDLE = "IDLE"
    ACTIVE_ROUND = "ACTIVE_ROUND"
    ROUND_RESULT = "ROUND_RESULT"


class RoundResult(StrEnum):
    """How a round ended."""

    GUESSED = "guessed"
    SKIPPED = "skipped"


class WordSource(StrEnum):
    """Where a round's secret word came from."""

    LEARNING_EVENT = "learning_event"
    STOCK = "stock"


class LearningState(StrEnum):
    """Progress of one saved word. There is no mastered state and no score."""

    DISCOVERED = "DISCOVERED"
    ASSISTED = "ASSISTED"
    REINFORCED = "REINFORCED"
    USED_INDEPENDENTLY = "USED_INDEPENDENTLY"


class EventType(StrEnum):
    """WebSocket event types (AGENTS 6.2)."""

    SESSION_STATE_CHANGED = "session.state.changed"
    HINT_CREATED = "hint.created"
    HINT_CLEARED = "hint.cleared"
    ACTIVITY_STATE_CHANGED = "activity.state.changed"
    ACTIVITY_PRIVATE_PROMPT = "activity.private_prompt"
    LEARNING_EVENT_CREATED = "learning_event.created"
    LEARNING_EVENT_UPDATED = "learning_event.updated"
    AGENT_SPEAK_REQUESTED = "agent.speak.requested"
