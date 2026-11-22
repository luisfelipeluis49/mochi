"""Development route: a typed sentence handled exactly like a turn from Agora."""

from fastapi import APIRouter
from pydantic import BaseModel

from mochi_backend.gateway.routes.dependencies import ContainerDep, SessionIdPath
from mochi_contracts import Decision, Utterance

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


@router.get("/dev/sessions/{session_id}/transcript")
async def dev_transcript(session_id: SessionIdPath, container: ContainerDep) -> list[Utterance]:
    """The running session's sentences, each with the speaker it was given, in order.

    For checking who-said-what while developing (only with MOCHI_ENABLE_DEV_ROUTES=true): in
    production nobody reads another person's sentences.
    """
    return container.registry.runtime(session_id).core.journal.transcript()
