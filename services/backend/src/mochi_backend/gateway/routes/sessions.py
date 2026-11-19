"""Session start/stop and the operator reset."""

from fastapi import APIRouter

from mochi_backend.gateway.routes.dependencies import ContainerDep
from mochi_contracts import SessionState

router = APIRouter()


@router.post("/api/sessions/demo/start")
async def start_session(container: ContainerDep) -> SessionState:
    """Start the Agora agent; capturing becomes true."""
    return await container.sessions.start()


@router.post("/api/sessions/demo/stop")
async def stop_session(container: ContainerDep) -> SessionState:
    """Stop the Agora agent; capturing becomes false."""
    return await container.sessions.stop()


@router.post("/api/demo/reset")
async def reset_demo(container: ContainerDep) -> SessionState:
    """Clear saved words and any game; capturing is left as it is."""
    await container.demo_reset.run()
    return container.core.store.session_state()
