"""Typed `Depends` aliases shared by the route modules."""

from typing import Annotated

from fastapi import Depends, Path

from mochi_backend.gateway.container import AppContainer, get_container
from mochi_backend.gateway.session_registry import SESSION_ID_PATTERN

ContainerDep = Annotated[AppContainer, Depends(get_container)]

# The session in the path: `demo` is the Pi's; any other id is a session a client opened.
SessionIdPath = Annotated[str, Path(pattern=SESSION_ID_PATTERN)]

# A user in the path (D-42): the same shape as a session id; a bad one is a 422.
UserIdPath = Annotated[str, Path(pattern=SESSION_ID_PATTERN)]
