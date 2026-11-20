"""The device state the Pi bridge polls, and the sentences a device reports."""

from fastapi import APIRouter
from pydantic import BaseModel

from mochi_backend.gateway.device_service import DeviceState
from mochi_backend.gateway.routes.dependencies import ContainerDep
from mochi_contracts import Decision

router = APIRouter()


class HeardTurn(BaseModel):
    """`{"text": "..."}`: one finished sentence the device's own agent transcribed."""

    text: str


class HeardReply(BaseModel):
    """What was decided for the sentence (the hint and saved words are already published)."""

    decision: Decision


@router.get("/api/devices/{device_id}/state")
async def device_state(device_id: str, container: ContainerDep) -> DeviceState:
    """Example: `/api/devices/home_pi_01/state` -> `{capturing, agora, speaker_muted}`."""
    return container.devices.state(device_id)


@router.post("/api/devices/{device_id}/turns")
async def device_turn(device_id: str, body: HeardTurn, container: ContainerDep) -> HeardReply:
    """A sentence heard by a device that runs its own agent (`start` with `agent: device`).

    Same pipeline as a turn from Agora, except that nothing is spoken: the device's agent answers.
    Example: `POST /api/devices/home_pi_01/turns {"text": "Eu preciso adiar a reunião."}`.
    """
    container.devices.require(device_id)
    outcome = await container.pipeline.handle_turn(body.text)
    return HeardReply(decision=outcome.decision)
