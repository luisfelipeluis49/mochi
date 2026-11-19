"""The device state the Pi bridge polls."""

from fastapi import APIRouter

from mochi_backend.gateway.device_service import DeviceState
from mochi_backend.gateway.routes.dependencies import ContainerDep

router = APIRouter()


@router.get("/api/devices/{device_id}/state")
async def device_state(device_id: str, container: ContainerDep) -> DeviceState:
    """Example: `/api/devices/home_pi_01/state` -> `{capturing, agora, speaker_muted}`."""
    return container.devices.state(device_id)
