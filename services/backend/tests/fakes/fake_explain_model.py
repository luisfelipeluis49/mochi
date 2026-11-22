"""A scripted explainer. Example: `FakeExplainModel({"circle back": "voltar ao assunto"})`."""

import asyncio

from mochi_backend.intelligence.explain_port import ExplainRequest, Explanation


class FakeExplainModel:
    """Implements `ExplainModel`: explains the first scripted idiom found in a sentence."""

    def __init__(self, idioms: dict[str, str] | None = None, confidence: float = 0.9) -> None:
        self._idioms = idioms or {}
        self._confidence = confidence
        self.requests: list[ExplainRequest] = []

    async def explain(self, request: ExplainRequest) -> Explanation | None:
        """Record the request; EXPLAIN when a scripted idiom is in the sentence, else IGNORE."""
        self.requests.append(request)
        for idiom, meaning in self._idioms.items():
            if idiom in request.text.lower():
                return Explanation(
                    decision="EXPLAIN",
                    kind="idiom",
                    expression=idiom,
                    meaning=meaning,
                    plain="say it simply",
                    confidence=self._confidence,
                )
        return Explanation(decision="IGNORE")


class GatedExplainModel(FakeExplainModel):
    """Answers like `FakeExplainModel`, but only once `gate` is set: for answers that cross."""

    def __init__(self, idioms: dict[str, str] | None = None) -> None:
        super().__init__(idioms)
        self.gate = asyncio.Event()

    async def explain(self, request: ExplainRequest) -> Explanation | None:
        """Wait for the gate, then answer as scripted."""
        await self.gate.wait()
        return await super().explain(request)
