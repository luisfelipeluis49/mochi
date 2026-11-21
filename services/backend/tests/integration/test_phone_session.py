"""A session started on a phone (proposed, apps/web/PROPOSAL_phone_microphone.md).

The phone's own microphone stands in for the Pi: the phone gets the join block, the Pi stays out
(no join, no hints, no round on its screen). A session started on the device works as before, and
the phone cannot take its microphone.
"""

import pytest
from fastapi.testclient import TestClient

from mochi_backend.app import create_app
from mochi_backend.gateway.errors import ConflictError
from tests.harness import make_harness

ADIAR = "I need to adiar my meeting tomorrow."
STATE = "/api/devices/home_pi_01/state"
PHONE_AUDIO = "/api/sessions/demo/phone-audio"


async def test_a_phone_session_keeps_the_pi_out_and_gives_the_phone_the_join_block() -> None:
    harness = make_harness()
    await harness.container.sessions.start(source="phone")
    devices = harness.container.devices

    pi = devices.state("home_pi_01")
    assert pi.capturing is False and pi.agora is None and pi.commands == []

    join = devices.phone_join()
    assert join.uid == harness.container.settings.mochi_pi_uid  # the uid the agent listens to
    assert join.channel and join.token


async def test_a_hint_in_a_phone_session_does_not_reach_the_pi() -> None:
    harness = make_harness()
    await harness.container.sessions.start(source="phone")
    outcome = await harness.say(ADIAR)
    assert outcome.decision is not None and outcome.decision.hint is not None
    assert harness.container.devices.state("home_pi_01").commands == []


async def test_a_device_session_works_as_before_and_the_phone_cannot_take_its_microphone() -> None:
    harness = make_harness()
    await harness.container.sessions.start(woken_by="oi mochi")
    pi = harness.container.devices.state("home_pi_01")
    assert pi.capturing is True and pi.agora is not None
    with pytest.raises(ConflictError):
        harness.container.devices.phone_join()


async def test_a_second_start_keeps_the_running_sessions_source() -> None:
    harness = make_harness()
    await harness.container.sessions.start(woken_by="oi mochi")
    await harness.container.sessions.start(source="phone")  # a phone taps Start while the Pi runs
    assert harness.container.core.store.source == "device"
    with pytest.raises(ConflictError):
        harness.container.devices.phone_join()


async def test_stop_forgets_the_source() -> None:
    harness = make_harness()
    await harness.container.sessions.start(source="phone")
    await harness.container.sessions.stop()
    assert harness.container.core.store.source == "device"
    with pytest.raises(ConflictError):
        harness.container.devices.phone_join()


def test_the_http_routes_for_a_phone_session() -> None:
    harness = make_harness()
    client = TestClient(create_app(harness.container))

    assert client.get(PHONE_AUDIO).status_code == 409  # nothing running
    started = client.post("/api/sessions/demo/start", json={"source": "phone"})
    assert started.status_code == 200 and started.json()["capturing"] is True

    join = client.get(PHONE_AUDIO)
    assert join.status_code == 200
    assert set(join.json()) == {"app_id", "channel", "uid", "token"}
    assert client.get(STATE).json()["capturing"] is False  # the Pi stays out

    assert client.post("/api/sessions/demo/start", json={"source": "watch"}).status_code == 422
    client.post("/api/sessions/demo/stop")
    assert client.get(PHONE_AUDIO).status_code == 409


def test_a_start_without_a_body_is_still_a_device_session() -> None:
    harness = make_harness()
    client = TestClient(create_app(harness.container))
    client.post("/api/sessions/demo/start")
    assert client.get(STATE).json()["capturing"] is True
    assert client.get(PHONE_AUDIO).status_code == 409
