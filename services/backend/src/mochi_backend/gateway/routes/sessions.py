"""Session start/stop and the operator reset."""

from fastapi import APIRouter
from pydantic import BaseModel

from mochi_backend.gateway.container import AppContainer
from mochi_backend.gateway.errors import ConflictError, NotFoundError, UpstreamError
from mochi_backend.gateway.roster import SESSION_ID
from mochi_backend.gateway.routes.dependencies import ContainerDep, SessionIdPath
from mochi_backend.gateway.session_service import AgoraJoin
from mochi_backend.gateway.session_store import SessionStore
from mochi_contracts import SessionState, User

router = APIRouter()


class StartBody(BaseModel):
    """Optional. `{"woken_by": "oi mochi"}`: the device heard its wake phrase and starts.

    `user_id` (D-42): the web user the session is for; it is then theirs and `guest`'s.
    """

    woken_by: str | None = None
    user_id: str | None = None


def _owner(container: AppContainer, session_id: str, body: StartBody | None) -> User | None:
    """The user a Start names, checked BEFORE the session is opened: opening may evict another
    session, and a bad user must not cost anyone theirs."""
    if body is None or body.user_id is None:
        return None
    if session_id == SESSION_ID:
        raise ConflictError(f"session {SESSION_ID!r} is the device's; start another id")
    user = container.users.find(body.user_id)
    if user is None:
        raise NotFoundError(f"unknown user {body.user_id!r}; create one with POST /api/users")
    return user


@router.post("/api/sessions/{session_id}/start")
async def start_session(
    session_id: SessionIdPath, container: ContainerDep, body: StartBody | None = None
) -> SessionState:
    """Start the Agora agent; capturing becomes true.

    `demo` is the Pi's session. Any other id opens a session of its own (a phone's): its own
    channel, agent, hints and game, apart from every other session (DECISIONS D-41).
    When the device was woken by its wake phrase, Mochi greets in that language and the next
    sentence is meant for it. With a `user_id`, the participants are that user and `guest`.
    """
    user = _owner(container, session_id, body)
    runtime = await container.registry.open(session_id)
    try:
        return await runtime.sessions.start(woken_by=body.woken_by if body else None, user=user)
    except UpstreamError:
        if not runtime.core.store.capturing:
            container.registry.close(session_id)  # a start that failed leaves nothing behind
        raise


@router.post("/api/sessions/{session_id}/stop")
async def stop_session(session_id: SessionIdPath, container: ContainerDep) -> SessionState:
    """Stop the session's Agora agent; capturing becomes false. Another session is not touched."""
    runtime = container.registry.peek(session_id)
    if runtime is None:
        return SessionStore().session_state()  # stopping what is not running is fine
    state = await runtime.sessions.stop()
    container.registry.close(session_id)
    return state


@router.get("/api/sessions/{session_id}/agora")
async def session_agora(session_id: SessionIdPath, container: ContainerDep) -> AgoraJoin:
    """Where a phone joins this session's channel to be its microphone (after Start)."""
    return container.registry.runtime(session_id).sessions.join_info()


@router.post("/api/demo/reset")
async def reset_demo(container: ContainerDep) -> SessionState:
    """Clear saved words and any game; capturing is left as it is."""
    await container.demo_reset.run()
    return container.core.store.session_state()
