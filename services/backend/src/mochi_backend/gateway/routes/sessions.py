"""Session start/stop and the operator reset."""

from fastapi import APIRouter
from pydantic import BaseModel

from mochi_backend.gateway.routes.dependencies import ContainerDep
from mochi_contracts import SessionState

router = APIRouter()


class StartBody(BaseModel):
    """Optional. `{"woken_by": "oi mochi"}`: the device heard its wake phrase and starts."""

    woken_by: str | None = None


@router.post("/api/sessions/demo/start")
async def start_session(container: ContainerDep, body: StartBody | None = None) -> SessionState:
    """Start the Agora agent; capturing becomes true.

    When the device was woken by its wake phrase, Mochi greets in that language and the next
    sentence is meant for it.
    """
    return await container.sessions.start(woken_by=body.woken_by if body else None)


@router.post("/api/sessions/demo/stop")
async def stop_session(container: ContainerDep) -> SessionState:
    """Stop the Agora agent; capturing becomes false."""
    return await container.sessions.stop()


@router.post("/api/demo/reset")
async def reset_demo(container: ContainerDep) -> SessionState:
    """Clear saved words and any game; capturing is left as it is."""
    await container.demo_reset.run()
    return container.core.store.session_state()
