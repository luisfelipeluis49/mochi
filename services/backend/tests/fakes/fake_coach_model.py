"""A scripted coach. Example: `FakeCoachModel(CoachAnswer(corrections=[...]))`."""

from mochi_backend.intelligence.coach_port import CoachAnswer, CoachRequest


class FakeCoachModel:
    """Implements `CoachModel`. Returns the scripted answer (None: the model did not answer)."""

    def __init__(self, scripted: CoachAnswer | None = None) -> None:
        self._scripted = scripted
        self.requests: list[CoachRequest] = []

    async def review(self, request: CoachRequest) -> CoachAnswer | None:
        """Record the request, then answer as scripted."""
        self.requests.append(request)
        return self._scripted
