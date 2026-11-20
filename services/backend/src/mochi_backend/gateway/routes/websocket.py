"""`/ws`: Mobile (?user=), Home (?device=) and Audience (?view=) connections."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from mochi_backend.gateway.connections import parse_target
from mochi_backend.gateway.routes.dependencies import ContainerDep

router = APIRouter()
BAD_QUERY_CLOSE_CODE = 4400
GONE_CLOSE_CODE = 1011


class SocketSender:
    """Adapts a Starlette WebSocket to the hub's `Sender` protocol."""

    def __init__(self, socket: WebSocket) -> None:
        self._socket = socket

    async def send_text(self, text: str) -> None:
        """Send, turning disconnects into ConnectionError so the hub drops the client."""
        try:
            await self._socket.send_text(text)
        except (WebSocketDisconnect, RuntimeError) as error:
            raise ConnectionError(str(error)) from error


@router.websocket("/ws")
async def websocket_endpoint(socket: WebSocket, container: ContainerDep) -> None:
    """Accept, send the snapshot, then keep the socket open until the client leaves."""
    await socket.accept()
    try:
        target = parse_target(dict(socket.query_params))
    except ValueError as error:
        await socket.close(code=BAD_QUERY_CLOSE_CODE, reason=str(error))
        return
    connection = await container.connections.accept(target, SocketSender(socket))
    if connection is None:
        await socket.close(code=GONE_CLOSE_CODE, reason="could not send the current state")
        return
    try:
        await _until_disconnected(socket)
    finally:
        container.connections.close(connection)  # whatever ended the socket, forget the client


async def _until_disconnected(socket: WebSocket) -> None:
    """Read and ignore anything the client sends (text or binary) until it leaves."""
    while True:
        message = await socket.receive()
        if message["type"] == "websocket.disconnect":
            return
