"""Session start/stop and the operator reset."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from mochi_backend.gateway.routes.dependencies import ContainerDep
from mochi_contracts import SessionState

router = APIRouter()


class StartBody(BaseModel):
    """Optional. `{"agent": "device"}`: the device runs the agent itself; none is started here."""

    agent: Literal["backend", "device"] = "backend"


@router.post("/api/sessions/demo/start")
async def start_session(container: ContainerDep, body: StartBody | None = None) -> SessionState:
    """Start the Agora agent (unless the device runs its own); capturing becomes true."""
    on_device = body is not None and body.agent == "device"
    return await container.sessions.start(agent_on_device=on_device)


@router.post("/api/sessions/demo/stop")
async def stop_session(container: ContainerDep) -> SessionState:
    """Stop the Agora agent; capturing becomes false."""
    return await container.sessions.stop()


@router.post("/api/demo/reset")
async def reset_demo(container: ContainerDep) -> SessionState:
    """Clear saved words and any game; capturing is left as it is."""
    await container.demo_reset.run()
    return container.core.store.session_state()
