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


class MarkKind(StrEnum):
    """What Mochi noticed in a sentence of the live transcript (PROPOSAL, D-51 to D-53).

    `code_switch`: a word of the other language (the speaker also gets a hint for it).
    `idiom` and `technical_term`: something the people listening may not understand.
    """

    CODE_SWITCH = "code_switch"
    IDIOM = "idiom"
    TECHNICAL_TERM = "technical_term"


class SpeakReason(StrEnum):
    """Why Mochi speaks aloud."""

    ASKS_MOCHI = "asks_mochi"


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
    """The two kinds of session (Papear, v0.7).

    `meeting`: people talk to each other at work; Mochi listens, shows a hint when someone is
    stuck and speaks only when asked. `review`: one person goes over their saved words with Mochi
    on their phone.
    """

    MEETING = "meeting"
    REVIEW = "review"


class MemberRole(StrEnum):
    """What a person may see of their company: `admin` also sees the team view."""

    ADMIN = "admin"
    MEMBER = "member"


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
    LEARNING_EVENT_CREATED = "learning_event.created"
    LEARNING_EVENT_UPDATED = "learning_event.updated"
    AGENT_SPEAK_REQUESTED = "agent.speak.requested"
    TRANSCRIPT_LINE = "transcript.line"  # PROPOSAL (D-51): one finished sentence, as it is said
    CONVERSATION_REPORT_CREATED = "conversation.report.created"  # PROPOSAL (D-54)
    PHRASE_SUGGESTED = "phrase.suggested"  # PROPOSAL (D-59): the sentence someone was reaching for


class MistakeKind(StrEnum):
    """What kind of mistake a sentence had (PROPOSAL, DECISIONS D-54)."""

    GRAMMAR = "grammar"  # "Yesterday I send" -> "Yesterday I sent"
    WORD_CHOICE = "word_choice"  # "make a question" -> "ask a question"
    FALSE_FRIEND = "false_friend"  # "I pretend to" -> "I intend to"


class MistakeTopic(StrEnum):
    """The group a mistake belongs to, so the same mistake can be counted across sentences and
    people. A fixed list: the screen writes the label in the reader's language."""

    VERB_TENSE = "verb_tense"
    VERB_FORM = "verb_form"
    AGREEMENT = "agreement"
    ARTICLES = "articles"
    PREPOSITIONS = "prepositions"
    PRONOUNS = "pronouns"
    PLURALS = "plurals"
    WORD_ORDER = "word_order"
    WORD_CHOICE = "word_choice"
    FALSE_FRIEND = "false_friend"
    OTHER = "other"
