"""Typed `Depends` aliases shared by the route modules."""

from typing import Annotated

from fastapi import Depends

from mochi_backend.gateway.container import AppContainer, get_container

ContainerDep = Annotated[AppContainer, Depends(get_container)]
