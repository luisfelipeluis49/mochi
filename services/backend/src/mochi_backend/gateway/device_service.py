"""The device state the Pi bridge polls a few times a second (AGENTS 6.4)."""

import json
from datetime import timedelta

from pydantic import BaseModel

from mochi_backend.gateway.agora.client_port import RtcTokenIssuer
from mochi_backend.gateway.device_commands import COMMAND_LIFETIME, DeviceCommand
from mochi_backend.gateway.errors import NotFoundError
from mochi_backend.gateway.roster import HOME_DEVICE_ID
from mochi_backend.gateway.session_service import SessionConfig
from mochi_backend.gateway.session_store import SessionStore
from mochi_backend.gateway.silence_policy import SilencePolicy
from mochi_backend.platform.clock import Clock
from mochi_contracts import Activity, GameState

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
    commands: list[DeviceCommand] = []  # what Mochi wants its body to do; each one once


def round_card(activity: Activity, secret_word: str | None, language: str) -> str:
    """What the device shows for a round, as JSON, in the names of the Activity contract.

    `secret_word` is the describer's word; None for a reader that may not see it, and after the
    round (then `revealed_word` has it). Example: `{"round_id": "round_1", "state":
    "ACTIVE_ROUND", "describer_user_id": "ben", "guesser_user_id": "ana", "secret_word":
    "umbrella", "result": null, "revealed_word": null, "language": "en"}`.
    """
    card = {
        "round_id": activity.round_id,
        "state": activity.state.value,
        "describer_user_id": activity.describer_user_id,
        "guesser_user_id": activity.guesser_user_id,
        "secret_word": secret_word,
        "result": activity.result.value if activity.result else None,
        "revealed_word": activity.revealed_word,
        "language": language,
    }
    return json.dumps(card, ensure_ascii=False)


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

    def state(self, device_id: str, trusted: bool = False) -> DeviceState:
        """Example: while capturing -> `capturing=True` and a join block; else `agora=None`.

        `trusted`: the reader sent the device key. Only then does a round carry its secret word:
        this route is open, and the word is for the describer's eyes on Mochi's own screen.
        """
        if device_id != HOME_DEVICE_ID:
            raise NotFoundError(f"unknown device {device_id!r}; expected {HOME_DEVICE_ID!r}")
        if not self._store.capturing:
            return DeviceState(capturing=False, agora=None, speaker_muted=False)
        return DeviceState(
            capturing=True,
            agora=self._join_info(),
            speaker_muted=self._silence.speaker_muted(),
            commands=[*self._store.fresh_commands(self._clock.now()), *self._round(trusted)],
        )

    def _round(self, trusted: bool) -> list[DeviceCommand]:
        """The round as a command, on every poll while there is one (a round outlasts the 30 s
        a queued command lives, and a restarted device must find it again). Its id changes with
        the round's state, so the device acts once on each. A result is news for as long as any
        other command: a device that joins later must not be shown an old one."""
        activity = self._store.activity
        if activity.state is GameState.IDLE or activity.round_id is None or self._stale_result():
            return []
        playing = activity.state is GameState.ACTIVE_ROUND and self._store.round_secrets
        secret = self._store.round_secrets[0] if playing and trusted else None
        card = round_card(activity, secret, self._store.session_state().focus.value)
        command_id = f"{activity.round_id}:{activity.state.value}"
        return [DeviceCommand(command_id=command_id, kind="round", value=card)]

    def _stale_result(self) -> bool:
        ended = self._store.round_ended_at
        return ended is not None and self._clock.now() - ended > COMMAND_LIFETIME

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
