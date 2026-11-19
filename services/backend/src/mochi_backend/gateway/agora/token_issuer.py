"""RTC tokens through the official `agora-token-builder` package, behind our own protocol."""

from agora_token_builder import RtcTokenBuilder

from mochi_backend.platform.clock import Clock

PUBLISHER_ROLE = 1  # both the Pi bridge and the agent publish audio


class AgoraTokenIssuer:
    """Implements `RtcTokenIssuer`. Example: `AgoraTokenIssuer(app, cert, clock).issue("c", 1, 60)`.

    NOTE: this package builds `006` (AccessToken v1) tokens; see VERIFIED.md for the open check.
    """

    def __init__(self, app_id: str, app_certificate: str, clock: Clock) -> None:
        self._app_id = app_id
        self._certificate = app_certificate
        self._clock = clock

    def issue(self, channel: str, uid: int, ttl_seconds: int) -> str:
        """A token for `uid` in `channel`, valid for `ttl_seconds`."""
        expires_at = int(self._clock.now().timestamp()) + ttl_seconds
        token = RtcTokenBuilder.buildTokenWithUid(
            self._app_id, self._certificate, channel, uid, PUBLISHER_ROLE, expires_at
        )
        return str(token)
