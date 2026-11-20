"""The device state the Pi bridge polls, and what the device reports about itself."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from mochi_backend.gateway.device_link import require_device
from mochi_backend.gateway.device_service import DeviceState
from mochi_backend.gateway.routes.dependencies import ContainerDep
from mochi_contracts import Language

router = APIRouter()


class DeviceReport(BaseModel):
    """What the device knows about itself right now. Send it again whenever something changes."""

    volume: int | None = None  # speaker level, 0-100
    temperature: float | None = None  # the processor's, degrees Celsius
    voices: list[str] = []  # whose voices it knows
    speaker: str | None = None  # whose voice it hears now, when it recognises it


class VoiceResult(BaseModel):
    """How learning one person's voice ended (after Mochi wrote `[enroll NAME LANG]`)."""

    name: str
    language: Literal["en", "pt"] = "en"
    learned: bool


@router.get("/api/devices/{device_id}/state")
async def device_state(device_id: str, container: ContainerDep) -> DeviceState:
    """Example: `/api/devices/home_pi_01/state` -> `{capturing, agora, speaker_muted}`."""
    return container.devices.state(device_id)


@router.post("/api/devices/{device_id}/status", status_code=204)
async def device_status(device_id: str, body: DeviceReport, container: ContainerDep) -> None:
    """The device says how loud it is, how warm, whose voices it knows and who is talking.

    Example: `{"volume": 80, "temperature": 52.4, "voices": ["Ana"], "speaker": "Ana"}`.
    """
    require_device(device_id)
    container.device_link.report(body.volume, body.temperature, body.voices, body.speaker)


@router.post("/api/devices/{device_id}/voices", status_code=204)
async def device_voice(device_id: str, body: VoiceResult, container: ContainerDep) -> None:
    """The device learned a voice (or could not); Mochi says so out loud.

    Example: `{"name": "Ana", "language": "pt", "learned": true}`.
    """
    require_device(device_id)
    language = Language.PT_BR if body.language == "pt" else Language.EN
    await container.device_link.voice_learned(body.name, language, body.learned)
