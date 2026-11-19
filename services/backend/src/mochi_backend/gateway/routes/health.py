"""Liveness and readiness."""

import os

from fastapi import APIRouter
from pydantic import BaseModel

from mochi_backend.gateway.routes.dependencies import ContainerDep

router = APIRouter()


class Health(BaseModel):
    """`/healthz`: alive, and which build."""

    status: str
    version: str


class Readiness(BaseModel):
    """`/readyz`: what is configured."""

    ready: bool
    agora_mode: str
    public_url_set: bool
    model_configured: bool
    intelligence: str
    silence_strategy: str


@router.get("/healthz")
async def healthz() -> Health:
    """Liveness. `version` is the git SHA when GIT_SHA is set at build time."""
    return Health(status="ok", version=os.environ.get("GIT_SHA", "dev"))


@router.get("/readyz")
async def readyz(container: ContainerDep) -> Readiness:
    """Readiness: Agora mode, public URL, model and intelligence implementation."""
    settings = container.settings
    public_url_set = settings.mochi_public_url.startswith("https://")
    return Readiness(
        ready=settings.mochi_agora_mode == "fake" or public_url_set,
        agora_mode=settings.mochi_agora_mode,
        public_url_set=public_url_set,
        model_configured=settings.model_configured,
        intelligence=container.intelligence_name,
        silence_strategy=settings.mochi_silence_strategy,
    )
