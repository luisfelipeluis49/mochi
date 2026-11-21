"""Session start/stop and the operator reset."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from mochi_backend.gateway.device_service import AgoraJoinInfo
from mochi_backend.gateway.routes.dependencies import ContainerDep
from mochi_contracts import SessionState

router = APIRouter()


class StartBody(BaseModel):
    """Optional. `{"woken_by": "oi mochi"}`: the device heard its wake phrase and starts.

    `{"source": "phone"}` (proposed): a phone starts, and its own microphone is Mochi's ears.
    """

    woken_by: str | None = None
    source: Literal["device", "phone"] = "device"


@router.post("/api/sessions/demo/start")
async def start_session(container: ContainerDep, body: StartBody | None = None) -> SessionState:
    """Start the Agora agent; capturing becomes true.

    When the device was woken by its wake phrase, Mochi greets in that language and the next
    sentence is meant for it.
    """
    if body is None:
        return await container.sessions.start()
    return await container.sessions.start(woken_by=body.woken_by, source=body.source)


@router.get("/api/sessions/demo/phone-audio")
async def phone_audio(container: ContainerDep) -> AgoraJoinInfo:
    """Where the phone that started the session joins the channel (proposed).

    Example: after `POST /start {"source": "phone"}` -> `{"app_id", "channel", "uid", "token"}`;
    409 when no phone session runs (for example, the Pi started it).
    """
    return container.devices.phone_join()


@router.post("/api/sessions/demo/stop")
async def stop_session(container: ContainerDep) -> SessionState:
    """Stop the Agora agent; capturing becomes false."""
    return await container.sessions.stop()


@router.post("/api/demo/reset")
async def reset_demo(container: ContainerDep) -> SessionState:
    """Clear saved words and any game; capturing is left as it is."""
    await container.demo_reset.run()
    return container.core.store.session_state()
