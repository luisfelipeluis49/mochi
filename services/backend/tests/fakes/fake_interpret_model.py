"""A scripted interpreter. Example: `FakeInterpretModel({"adiar o lançamento": "postpone it"})`."""

from mochi_backend.intelligence.interpret_port import Interpretation, InterpretRequest


class FakeInterpretModel:
    """Implements `InterpretModel`: says the scripted sentence for a sentence that contains the
    scripted words, and NOTHING for any other."""

    def __init__(
        self, sentences: dict[str, str] | None = None, answers_in: str | None = None
    ) -> None:
        self._sentences = sentences or {}
        self._answers_in = answers_in  # the language it says its sentences are in, when it says
        self.requests: list[InterpretRequest] = []

    async def interpret(self, request: InterpretRequest) -> Interpretation | None:
        """Record the request, then answer as scripted."""
        self.requests.append(request)
        for words, sentence in self._sentences.items():
            if words in request.text.lower():
                return Interpretation(decision="SAY", sentence=sentence, language=self._answers_in)
        return Interpretation(decision="NOTHING")
