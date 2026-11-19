"""A scripted language model. Example: `FakeHintModel(ModelSuggestion(decision="IGNORE"))`."""

from mochi_backend.intelligence.model_port import ModelRequest, ModelSuggestion


class FakeHintModel:
    """Implements `HintModel`. Returns the scripted answer, or raises the scripted error."""

    def __init__(self, scripted: ModelSuggestion | TimeoutError | None = None) -> None:
        self._scripted = scripted
        self.requests: list[ModelRequest] = []

    async def suggest(self, request: ModelRequest) -> ModelSuggestion | None:
        """Record the request, then answer as scripted."""
        self.requests.append(request)
        if isinstance(self._scripted, TimeoutError):
            raise self._scripted
        return self._scripted
