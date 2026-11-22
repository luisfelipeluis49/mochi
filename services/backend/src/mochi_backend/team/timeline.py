"""Who was heard when, as the device reports it, and whose a sentence therefore is (D-46).

The device hears stretches of speech between pauses and says who each one was; a sentence comes
from the speech recogniser about a second later with no name on it. The two are matched by time:
a sentence is the person's who spoke most in the stretches that ended since the sentence before.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

# A sentence arrives about a second after its speech ended (0.6 s of silence ends a turn, then
# the recogniser writes), and the device's "how long ago" is late by the network's delay. A
# stretch that ended in the last 0.3 s before a sentence arrived belongs to the next one: at 0.5
# stretches of the sentence itself fell out of its window, and into the next person's.
ARRIVAL_LAG = timedelta(seconds=0.3)
CLEAR_SHARE = 0.6  # of the speech of people it knows; under it, two people shared the sentence
# "Could not tell" is common for a short stretch of someone it named a moment before, so it does
# not outvote a name; but a name does not stand against more than twice as much unknown speech.
UNKNOWN_WEIGHT = 0.5


@dataclass(frozen=True)
class Phrase:
    """One stretch of speech: who (None: nobody known, or unclear), how long, when it ended."""

    user_id: str | None
    seconds: float
    ended_at: datetime


@dataclass(frozen=True)
class Verdict:
    """Whose a sentence is. `heard` False: the device said nothing about that time."""

    heard: bool
    user_id: str | None


class SpeakerTimeline:
    """Example: `timeline.add(Phrase("ana", 2.4, at))`, then `timeline.between(start, end)`."""

    def __init__(self) -> None:
        self._phrases: list[Phrase] = []

    def add(self, phrase: Phrase) -> None:
        """Keep one stretch the device heard."""
        self._phrases.append(phrase)

    def __len__(self) -> int:
        return len(self._phrases)

    def between(self, after: datetime, until: datetime) -> Verdict:
        """Who spoke most in the stretches that ended in (after, until].

        Example: Ana 2.4 s and Ben 0.4 s -> Ana. Ana 1.0 s and Ben 1.0 s -> nobody (heard, but
        two people shared it). Ana 0.8 s and 0.5 s it could not tell -> Ana. No stretch at all
        -> not heard.
        """
        spoken: dict[str | None, float] = {}
        for phrase in self._phrases:
            if after < phrase.ended_at <= until:
                spoken[phrase.user_id] = spoken.get(phrase.user_id, 0.0) + phrase.seconds
        if not spoken:
            return Verdict(heard=False, user_id=None)
        unknown = spoken.pop(None, 0.0)
        return Verdict(heard=True, user_id=_clear_winner(spoken, unknown))


def _clear_winner(named: dict[str | None, float], unknown: float) -> str | None:
    """The person who spoke most, when that is clear; None otherwise.

    Example: `_clear_winner({"ana": 0.8}, 0.5)` is "ana"; `_clear_winner({"ana": 0.8}, 3.0)` is
    None (mostly a voice it does not know).
    """
    if not named:
        return None
    who, most = max(named.items(), key=lambda pair: pair[1])
    clear = most >= CLEAR_SHARE * sum(named.values()) and most >= UNKNOWN_WEIGHT * unknown
    return who if clear else None
