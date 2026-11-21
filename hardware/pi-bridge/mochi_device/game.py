"""Describe & Guess on Mochi's own screen (AGENTS.md 7.5): what the screen shows for a round, and
what a touch means. The backend runs the game; this only follows the round it sends (the `round`
command in the device state) and turns touches into "guessed", "skipped" or "another round".

    stage     the screen shows                               a touch
    hidden    "Ben" / "turn me towards you and tap"          tap or hold -> the word is shown
    shown     the secret word / "tap when Ana gets it"       tap -> guessed, hold -> skipped
    sent      the same, while the backend takes the result   nothing
    result    the word / "Ana got it!" for a few seconds     tap -> another round

Whether the word is showing is known only here: the backend needs just the last touch.
"""
from __future__ import annotations

TEXT = {
    "en": {"turn": "turn me towards you and tap", "tap": "tap when {g} gets it\nhold to skip",
           "guessed": "{g} got it!", "skipped": "Skipped.", "again": "Tap for another round.",
           "no_word": "I cannot see the word\nhold to skip"},
    "pt-BR": {"turn": "vire-me para você e toque", "tap": "toque quando {g} acertar\nsegure para pular",
              "guessed": "{g} acertou!", "skipped": "Pulou.", "again": "Toque para jogar de novo.",
              "no_word": "Não consigo ver a palavra\nsegure para pular"},
}


class RoundScreen:
    REVEAL_GUARD_S = 1.5  # a second touch this soon after the reveal is the same touch, not "guessed"
    RESULT_S = 8.0        # how long the result stays before the face comes back

    def __init__(self):
        self.clear()

    def clear(self) -> None:
        self.stage: str | None = None
        self.card: dict = {}
        self.since = 0.0  # when the current stage began

    def show(self, card: dict, now: float) -> None:
        """A round card from the backend: a new round (ACTIVE_ROUND) or how it ended (ROUND_RESULT)."""
        state = card.get("state")
        if state == "ACTIVE_ROUND":
            self.stage, self.card, self.since = "hidden", card, now
        elif state == "ROUND_RESULT":
            self.stage, self.card, self.since = "result", card, now
        else:
            self.clear()

    def touched(self, kind: str, now: float) -> str | None:
        """kind: "tap" or "long". Returns what to tell the backend: "guessed", "skipped", "next" or None."""
        if self.stage == "hidden":
            if self.card.get("secret_word"):
                self.stage, self.since = "shown", now
            elif kind == "long":  # no word arrived (the device key): the round can still be left
                self.stage, self.since = "sent", now
                return "skipped"
        elif self.stage == "shown" and now - self.since >= self.REVEAL_GUARD_S:
            self.stage, self.since = "sent", now
            return "skipped" if kind == "long" else "guessed"
        elif self.stage == "result" and not self.over(now):
            self.stage = "sent"
            return "next"
        return None

    def refused(self, now: float) -> None:
        """The backend did not take the last touch: the screen can be touched again."""
        if self.stage == "sent":
            active = self.card.get("state") == "ACTIVE_ROUND"
            self.stage = ("shown" if self.card.get("secret_word") else "hidden") if active else "result"
            self.since = now

    def over(self, now: float) -> bool:
        """The result has been shown long enough: back to the face."""
        return self.stage == "result" and now - self.since > self.RESULT_S

    def view(self) -> dict | None:
        """What the face page draws: {"tone", "big", "small"}, or None for no round."""
        if self.stage is None:
            return None
        c, text = self.card, TEXT.get(str(self.card.get("language")), TEXT["en"])
        describer, guesser = (str(c.get(k) or "").title() for k in ("describer_user_id", "guesser_user_id"))
        if self.stage == "hidden" or not (c.get("secret_word") or c.get("state") == "ROUND_RESULT"):
            return {"tone": "ask", "big": describer, "small": text["turn" if c.get("secret_word") else "no_word"]}
        if c.get("state") == "ACTIVE_ROUND":
            return {"tone": "secret", "big": str(c.get("secret_word") or ""), "small": text["tap"].format(g=guesser)}
        how = text["guessed"].format(g=guesser) if c.get("result") == "guessed" else text["skipped"]
        return {"tone": "result", "big": str(c.get("revealed_word") or ""), "small": f"{how} {text['again']}"}
