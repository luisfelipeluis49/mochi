"""Models that count how often they were asked to open their connections. No network."""

from collections.abc import Mapping

from mochi_backend.platform.http_client import HttpResponse, HttpTransportError
from tests.fakes.fake_character_model import FakeCharacterModel
from tests.fakes.fake_hint_model import FakeHintModel


class WarmedHintModel(FakeHintModel):
    """A `FakeHintModel` that implements `WarmsUp`. Example: `WarmedHintModel().warm_ups`."""

    warm_ups = 0

    async def warm_up(self) -> None:
        """Count the call."""
        self.warm_ups += 1


class WarmedCharacterModel(FakeCharacterModel):
    """A `FakeCharacterModel` that implements `WarmsUp`."""

    warm_ups = 0

    async def warm_up(self) -> None:
        """Count the call."""
        self.warm_ups += 1


class UnreachableGetter:
    """Implements `HttpGetter`. Every GET fails, as with no network."""

    def __init__(self) -> None:
        self.urls: list[str] = []

    async def get(
        self, url: str, headers: Mapping[str, str], timeout_seconds: float
    ) -> HttpResponse:
        """Record the call, then fail."""
        self.urls.append(url)
        raise HttpTransportError(f"GET {url} failed: no network; expected a reply")
