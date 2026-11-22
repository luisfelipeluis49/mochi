"""`/ws`: Mobile (?user=), Home (?device=) and Audience (?view=) connections.

`?user=` is any person of the company, or one `POST /api/users` made; an unknown user or `guest`
is accepted, then closed with 4400 (D-56).
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from mochi_backend.gateway.routes.dependencies import ContainerDep

router = APIRouter()
BAD_QUERY_CLOSE_CODE = 4400
GONE_CLOSE_CODE = 1011
MAX_CLOSE_REASON_BYTES = 123  # RFC 6455: control frame payload 125 bytes, 2 taken by the code
FALLBACK_REASON = (
    "unknown query; expected one of user=ana|ben|<user_id>[&surface=ar], device=home_pi_01, "
    "view=audience"
)


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
    # Parse first. The close still follows accept(): a server that closes before accepting answers
    # the handshake with HTTP 403, and a browser then sees code 1006 with no reason.
    try:
        target = container.connections.target_for(dict(socket.query_params))
    except ValueError as error:
        await socket.accept()
        await socket.close(code=BAD_QUERY_CLOSE_CODE, reason=_legal_reason(str(error)))
        return
    await socket.accept()
    connection = await container.connections.accept(target, SocketSender(socket))
    if connection is None:
        await socket.close(code=GONE_CLOSE_CODE, reason="could not send the current state")
        return
    try:
        await _until_disconnected(socket)
    finally:
        container.connections.close(connection)  # whatever ended the socket, forget the client


def _legal_reason(reason: str) -> str:
    """A close reason over 123 bytes breaks the close frame; fall back to a short fixed one."""
    return reason if len(reason.encode()) <= MAX_CLOSE_REASON_BYTES else FALLBACK_REASON


async def _until_disconnected(socket: WebSocket) -> None:
    """Read and ignore anything the client sends (text or binary) until it leaves."""
    while True:
        message = await socket.receive()
        if message["type"] == "websocket.disconnect":
            return
