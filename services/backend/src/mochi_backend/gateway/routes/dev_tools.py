"""Development route: a typed sentence handled exactly like a turn from Agora."""

from fastapi import APIRouter
from pydantic import BaseModel

from mochi_backend.gateway.routes.dependencies import ContainerDep, SessionIdPath
from mochi_contracts import Decision

router = APIRouter()


class TurnBody(BaseModel):
    """`{"text": "..."}`."""

    text: str


class TurnResponse(BaseModel):
    """What the Agora endpoint would have replied, plus the decision."""

    reply: str
    decision: Decision


@router.post("/dev/sessions/{session_id}/turn")
async def dev_turn(
    session_id: SessionIdPath, body: TurnBody, container: ContainerDep
) -> TurnResponse:
    """Same pipeline as `/agora/llm/...`; enabled only with MOCHI_ENABLE_DEV_ROUTES=true."""
    outcome = await container.registry.runtime(session_id).pipeline.handle_turn(body.text)
    return TurnResponse(reply=outcome.reply, decision=outcome.decision)
