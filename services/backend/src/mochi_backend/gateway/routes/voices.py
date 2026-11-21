"""Learned voices and their voiceprints. Device key required on every route: biometric data."""

from typing import Annotated

from fastapi import APIRouter, HTTPException, Path

from mochi_backend.gateway.device_link import require_device
from mochi_backend.gateway.routes.dependencies import ContainerDep
from mochi_backend.gateway.routes.devices import NAME_LIMIT, DeviceKey, PersonName
from mochi_backend.gateway.voice_directory import InvalidVoiceprintError
from mochi_contracts import VoiceprintUpload, VoiceProfile

router = APIRouter()
VoiceName = Annotated[str, Path(max_length=NAME_LIMIT), PersonName]


@router.get("/api/devices/{device_id}/voices", dependencies=[DeviceKey])
async def list_voices(device_id: str, container: ContainerDep) -> list[VoiceProfile]:
    """Every learned voice with its vector, so a new Pi can get its voices back.

    Example: `[{"name": "Ana", "user_id": "ana", "language": "pt", "voiceprint": [...]}]`.
    """
    require_device(device_id)
    return container.voices.all()


@router.put("/api/devices/{device_id}/voices/{name}/voiceprint", dependencies=[DeviceKey])
async def put_voiceprint(
    device_id: str, name: VoiceName, body: VoiceprintUpload, container: ContainerDep
) -> VoiceProfile:
    """Keep the voiceprint the Pi made for `name` (replaces an earlier one).

    Example: `PUT .../voices/Ana/voiceprint` with `{"language": "pt", "voiceprint": [0.01, ...]}`.
    The answer carries `user_id` (who the name belongs to) and echoes the vector.
    """
    require_device(device_id)
    try:
        return container.voices.store_vector(name, body)
    except InvalidVoiceprintError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@router.delete("/api/devices/{device_id}/voices/{name}", status_code=204, dependencies=[DeviceKey])
async def forget_voice(device_id: str, name: VoiceName, container: ContainerDep) -> None:
    """Delete the server copy of a voice (call it when the Pi forgets that person).

    Example: `DELETE /api/devices/home_pi_01/voices/Ana`. Deleting an unknown name is fine.
    """
    require_device(device_id)
    container.voices.forget(name)
