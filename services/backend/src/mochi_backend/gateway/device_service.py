"""The device state the Pi bridge polls a few times a second (AGENTS 6.4)."""

from datetime import timedelta

from pydantic import BaseModel

from mochi_backend.gateway.agora.client_port import RtcTokenIssuer
from mochi_backend.gateway.errors import NotFoundError
from mochi_backend.gateway.roster import HOME_DEVICE_ID
from mochi_backend.gateway.session_service import SessionConfig
from mochi_backend.gateway.session_store import SessionStore
from mochi_backend.gateway.silence_policy import SilencePolicy
from mochi_backend.platform.clock import Clock

# Re-issue the Pi token when this little of its life is left, so a poll never returns a dead one.
REFRESH_MARGIN = timedelta(minutes=5)


class AgoraJoinInfo(BaseModel):
    """Where and how the bridge joins the channel."""

    app_id: str
    channel: str
    uid: int
    token: str


class DeviceState(BaseModel):
    """Response of `GET /api/devices/home_pi_01/state`. With no live session: agora is null."""

    capturing: bool
    agora: AgoraJoinInfo | None
    speaker_muted: bool


class DeviceService:
    """Builds the device state; caches the Pi token until it is near expiry."""

    def __init__(
        self,
        *,
        store: SessionStore,
        tokens: RtcTokenIssuer,
        silence: SilencePolicy,
        config: SessionConfig,
        clock: Clock,
    ) -> None:
        self._store = store
        self._tokens = tokens
        self._silence = silence
        self._config = config
        self._clock = clock

    def state(self, device_id: str) -> DeviceState:
        """Example: while capturing -> `capturing=True` and a join block; else `agora=None`."""
        if device_id != HOME_DEVICE_ID:
            raise NotFoundError(f"unknown device {device_id!r}; expected {HOME_DEVICE_ID!r}")
        if not self._store.capturing:
            return DeviceState(capturing=False, agora=None, speaker_muted=False)
        return DeviceState(
            capturing=True, agora=self._join_info(), speaker_muted=self._silence.speaker_muted()
        )

    def _join_info(self) -> AgoraJoinInfo:
        return AgoraJoinInfo(
            app_id=self._config.app_id,
            channel=self._config.channel,
            uid=self._config.pi_uid,
            token=self._fresh_token(),
        )

    def _fresh_token(self) -> str:
        expires = self._store.pi_token_expires_at
        token = self._store.pi_token
        if (
            token is not None
            and expires is not None
            and expires - self._clock.now() > REFRESH_MARGIN
        ):
            return token
        ttl = self._config.token_ttl_seconds
        token = self._tokens.issue(self._config.channel, self._config.pi_uid, ttl)
        self._store.pi_token = token
        self._store.pi_token_expires_at = self._clock.now() + timedelta(seconds=ttl)
        return token
