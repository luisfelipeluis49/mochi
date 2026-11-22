"""A scripted phrase model. Example: `FakePhraseModel("I need to postpone my meeting.")`."""

from mochi_backend.intelligence.phrase_port import PhraseAnswer, PhraseRequest


class FakePhraseModel:
    """Implements `PhraseModel`. Suggests the scripted sentence (None: it has nothing to say)."""

    def __init__(self, sentence: str | None = None) -> None:
        self._sentence = sentence
        self.requests: list[PhraseRequest] = []

    async def phrase(self, request: PhraseRequest) -> PhraseAnswer | None:
        """Record the request, then answer as scripted."""
        self.requests.append(request)
        if self._sentence is None:
            return PhraseAnswer(decision="IGNORE")
        return PhraseAnswer(decision="SUGGEST", sentence=self._sentence)
