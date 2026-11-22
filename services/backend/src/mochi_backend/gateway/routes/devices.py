"""The device state the Pi bridge polls, and what the device reports about itself."""

import hmac
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field, StringConstraints

from mochi_backend.gateway.device_link import require_device
from mochi_backend.gateway.device_service import DeviceState
from mochi_backend.gateway.routes.dependencies import ContainerDep
from mochi_contracts import HeardPhrase, Language

router = APIRouter()
NAME_LIMIT = 40
VOICES_LIMIT = 8
HEARD_LIMIT = 60  # a second of reports holds two or three; this only stops runaway bodies
NAME_PATTERN = r"^[ '\-]*\p{L}[\p{L} '\-]*$"  # at least one letter
PersonName = Annotated[str, StringConstraints(pattern=NAME_PATTERN, max_length=NAME_LIMIT)]
BoundedText = Annotated[str, StringConstraints(max_length=NAME_LIMIT)]


def has_device_key(container: ContainerDep, authorization: str | None) -> bool:
    """True when `authorization` is `Bearer <MOCHI_DEVICE_KEY>`.

    Example: `has_device_key(container, "Bearer dev-device-key")` is True in fake mode.
    """
    scheme, _, given = (authorization or "").partition(" ")
    wanted = container.settings.mochi_device_key.encode()
    return scheme.lower() == "bearer" and hmac.compare_digest(given.encode(), wanted)


def require_device_key(
    container: ContainerDep, authorization: Annotated[str | None, Header()] = None
) -> None:
    """401 unless `Authorization: Bearer <MOCHI_DEVICE_KEY>` was sent.

    Example: `Authorization: Bearer dev-device-key` passes in fake mode.
    """
    if not has_device_key(container, authorization):
        raise HTTPException(
            status_code=401, detail="missing or wrong device key; send Bearer <key>"
        )


DeviceKey = Depends(require_device_key)


class DeviceReport(BaseModel):
    """What the device knows about itself right now. Send it again whenever something changes."""

    volume: int | None = None  # speaker level, 0-100
    temperature: float | None = None  # the processor's, degrees Celsius
    voices: list[BoundedText] = Field(default=[], max_length=VOICES_LIMIT)  # whose voices it knows
    speaker: BoundedText | None = None  # whose voice it hears now, when it recognises it
    # The stretches of speech heard since the last report, each with who said it (D-46).
    heard: list[HeardPhrase] = Field(default=[], max_length=HEARD_LIMIT)


class VoiceResult(BaseModel):
    """How learning one person's voice ended (after Mochi wrote `[enroll NAME LANG]`)."""

    name: PersonName
    language: Literal["en", "pt"] = "en"
    learned: bool


@router.get("/api/devices/{device_id}/state")
async def device_state(device_id: str, container: ContainerDep) -> DeviceState:
    """Example: `/api/devices/home_pi_01/state` -> `{capturing, agora, speaker_muted}`.

    Open to anyone, as in AGENTS 6.4 (a device key sent along is ignored).
    """
    return container.devices.state(device_id)


@router.post("/api/devices/{device_id}/status", status_code=204, dependencies=[DeviceKey])
async def device_status(device_id: str, body: DeviceReport, container: ContainerDep) -> None:
    """The device says how loud it is, how warm, whose voices it knows and who is talking.

    Example: `{"volume": 80, "temperature": 52.4, "voices": ["Ana"], "speaker": "Ana",
    "heard": [{"speaker": "Ana", "seconds": 2.4, "ago_ms": 380}]}`.
    """
    require_device(device_id)
    container.device_link.report(body.volume, body.temperature, body.voices, body.speaker)
    container.device_link.heard(body.heard)


@router.post("/api/devices/{device_id}/voices", status_code=204, dependencies=[DeviceKey])
async def device_voice(device_id: str, body: VoiceResult, container: ContainerDep) -> None:
    """The device learned a voice (or could not); Mochi says so out loud.

    Example: `{"name": "Ana", "language": "pt", "learned": true}`.
    """
    require_device(device_id)
    language = Language.PT_BR if body.language == "pt" else Language.EN
    if body.learned:
        container.voices.link(body.name, body.language)
    await container.device_link.voice_learned(body.name, language, body.learned)
