"""Process entry: `create_app(container)` builds FastAPI; `app_from_env` is the uvicorn factory."""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from mochi_backend.composition import build_container, default_adapters
from mochi_backend.gateway.container import AppContainer
from mochi_backend.gateway.errors import GatewayError
from mochi_backend.gateway.routes import (
    agora_llm,
    companies,
    dev_tools,
    devices,
    health,
    sessions,
    users,
    voices,
    websocket,
)
from mochi_backend.settings import load_settings


async def _gateway_error(request: Request, error: Exception) -> JSONResponse:
    status = error.status_code if isinstance(error, GatewayError) else 500
    return JSONResponse(status_code=status, content={"detail": str(error)})


def create_app(container: AppContainer) -> FastAPI:
    """Attach the container and mount the routes. Dev routes only when enabled."""
    app = FastAPI(title="Mochi backend")
    app.state.container = container
    app.add_middleware(
        CORSMiddleware,
        allow_origins=container.settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_exception_handler(GatewayError, _gateway_error)
    for module in (health, sessions, users, companies, devices, voices, agora_llm, websocket):
        app.include_router(module.router)
    if container.settings.mochi_enable_dev_routes:
        app.include_router(dev_tools.router)
    return app


def app_from_env() -> FastAPI:
    """uvicorn `--factory` entry: settings from the environment, real adapters."""
    settings = load_settings()
    return create_app(build_container(settings, default_adapters(settings)))
