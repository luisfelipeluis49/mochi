"""The object routes read their collaborators from (attached to the app in `create_app`)."""

from dataclasses import dataclass

from starlette.requests import HTTPConnection

from mochi_backend.gateway.activity_service import ActivityService
from mochi_backend.gateway.connections import ConnectionService
from mochi_backend.gateway.core import GatewayCore
from mochi_backend.gateway.demo_reset import DemoReset
from mochi_backend.gateway.device_service import DeviceService
from mochi_backend.gateway.session_service import SessionService
from mochi_backend.gateway.turn_pipeline import TurnPipeline
from mochi_backend.settings import Settings


@dataclass(frozen=True)
class AppContainer:
    """Every collaborator the HTTP/WebSocket edges use. Tests build one from fakes."""

    settings: Settings
    core: GatewayCore
    pipeline: TurnPipeline
    sessions: SessionService
    activity: ActivityService
    devices: DeviceService
    connections: ConnectionService
    demo_reset: DemoReset
    intelligence_name: str


def get_container(connection: HTTPConnection) -> AppContainer:
    """FastAPI provider: `Annotated[AppContainer, Depends(get_container)]`."""
    container: AppContainer = connection.app.state.container
    return container
