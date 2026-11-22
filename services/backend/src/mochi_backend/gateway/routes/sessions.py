"""Session start/stop and the operator reset."""

from fastapi import APIRouter
from pydantic import BaseModel

from mochi_backend.gateway.container import AppContainer
from mochi_backend.gateway.errors import (
    ConflictError,
    InvalidRequestError,
    NotFoundError,
    UpstreamError,
)
from mochi_backend.gateway.roster import SESSION_ID
from mochi_backend.gateway.routes.dependencies import ContainerDep, SessionIdPath
from mochi_backend.gateway.session_service import AgoraJoin
from mochi_backend.gateway.session_store import SessionStore
from mochi_contracts import SessionMode, SessionState, User

router = APIRouter()


class StartBody(BaseModel):
    """Optional. `{"woken_by": "oi mochi"}`: the device heard its wake phrase and starts.

    `{"mode": "review", "user_id": "ana"}`: Ana goes over her saved words (her phone's session).
    Without `mode` it is a meeting; a `user_id` then names the web user the session is for, and
    it is theirs and `guest`'s (D-56).
    """

    woken_by: str | None = None
    mode: SessionMode = SessionMode.MEETING
    user_id: str | None = None


def _owner(container: AppContainer, session_id: str, body: StartBody) -> User | None:
    """The user a Start names, checked BEFORE the session is opened: opening may evict another
    session, and a bad user must not cost anyone theirs. A review's person may be unknown
    here: the service then answers 422 and names the people it knows."""
    if body.user_id is None:
        return None
    user = container.users.find(body.user_id) or container.roster.user(body.user_id)
    if body.mode is SessionMode.REVIEW:
        return user
    if session_id == SESSION_ID:
        raise ConflictError(f"session {SESSION_ID!r} is the device's; start another id")
    if user is None:
        raise NotFoundError(f"unknown user {body.user_id!r}; create one with POST /api/users")
    return user


@router.post("/api/sessions/{session_id}/start")
async def start_session(
    session_id: SessionIdPath, container: ContainerDep, body: StartBody | None = None
) -> SessionState:
    """Start the Agora agent; capturing becomes true.

    `demo` is the Pi's session. Any other id opens a session of its own (a phone's): its own
    channel, agent and hints, apart from every other session (DECISIONS D-41).
    A meeting by default; `mode: "review"` with a `user_id` is that person's review (422 when
    the person is not known). When the device was woken by its wake phrase, Mochi greets in
    that language. A meeting with a `user_id` is a web user's own: its participants are that
    user and `guest` (404 for an unknown user, 409 on the device's session).
    """
    asked = body or StartBody()
    user = _owner(container, session_id, asked)
    runtime = await container.registry.open(session_id)
    try:
        return await runtime.sessions.start(asked.woken_by, asked.mode, asked.user_id, user)
    except (InvalidRequestError, UpstreamError):
        if not runtime.core.store.capturing:
            container.registry.close(session_id)  # a start that failed leaves nothing behind
        raise


@router.post("/api/sessions/{session_id}/stop")
async def stop_session(session_id: SessionIdPath, container: ContainerDep) -> SessionState:
    """Stop the session's Agora agent; capturing becomes false. Another session is not touched."""
    runtime = container.registry.peek(session_id)
    if runtime is None:
        return SessionStore(container.roster).session_state()  # stopping nothing is fine
    state = await runtime.sessions.stop()
    container.registry.close(session_id)
    return state


class Interrupted(BaseModel):
    """`{"interrupted": true}` when a running agent was told to stop talking."""

    interrupted: bool


@router.post("/api/sessions/{session_id}/interrupt")
async def interrupt_session(session_id: SessionIdPath, container: ContainerDep) -> Interrupted:
    """Someone is talking over Mochi: it stops at once and goes back to just listening.

    Sent by the device (or a phone) when it hears a person while Mochi speaks. A session that is
    not running answers `{"interrupted": false}`: there is nothing to stop.
    """
    runtime = container.registry.peek(session_id)
    if runtime is None:
        return Interrupted(interrupted=False)
    return Interrupted(interrupted=await runtime.sessions.interrupt())


class Said(BaseModel):
    """`{"said": true}` when Mochi is now saying the suggested sentence."""

    said: bool


@router.post("/api/sessions/{session_id}/hints/{hint_id}/say")
async def say_suggestion(
    session_id: SessionIdPath, hint_id: SessionIdPath, container: ContainerDep
) -> Said:
    """One touch (D-59): Mochi says aloud the sentence it suggested after this hint, so the
    person does not have to. Once per suggestion, and only while it is fresh.

    Sent by the device when its screen is touched, or by a phone's "say it" button.
    `{"said": false}`: no such suggestion (any more), or no session running.
    """
    runtime = container.registry.peek(session_id)
    if runtime is None:
        return Said(said=False)
    return Said(said=await runtime.pipeline.say_suggestion(hint_id))


@router.get("/api/sessions/{session_id}/agora")
async def session_agora(session_id: SessionIdPath, container: ContainerDep) -> AgoraJoin:
    """Where a phone joins this session's channel to be its microphone (after Start)."""
    return container.registry.runtime(session_id).sessions.join_info()


@router.post("/api/demo/reset")
async def reset_demo(container: ContainerDep) -> SessionState:
    """Clear saved words and the learning history; capturing is left as it is."""
    await container.demo_reset.run()
    return container.core.store.session_state()
