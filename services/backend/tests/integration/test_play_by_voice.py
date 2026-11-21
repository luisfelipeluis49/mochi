"""Play, the third thing to do with Mochi: asked for by voice, played on Mochi's own screen.

Someone says "let's play", Mochi writes `[play]`, a round starts in that same turn, and the device
finds the round in its state on every poll (the secret word only with the device key).
"""

import json

from fastapi.testclient import TestClient

from mochi_backend.app import create_app
from mochi_backend.settings import DEV_DEVICE_KEY
from mochi_contracts import GameState, RoundResult, SessionMode
from tests.fakes.fake_character_model import FakeCharacterModel
from tests.harness import ANA, AUDIENCE, HOME, Harness, make_harness

STATE = "/api/devices/home_pi_01/state"
KEY = {"Authorization": f"Bearer {DEV_DEVICE_KEY}"}
LETS_PLAY = "[mood excited][play] Yay, let's play!"


async def _woken(*lines: str) -> Harness:
    harness = make_harness(character=FakeCharacterModel(*lines))
    await harness.container.sessions.start(woken_by="hi mochi")
    return harness


def _round(client: TestClient, headers: dict[str, str] | None = None) -> dict[str, str | None]:
    commands = client.get(STATE, headers=headers or {}).json()["commands"]
    cards = [c["value"] for c in commands if c["kind"] == "round"]
    assert len(cards) == 1
    card: dict[str, str | None] = json.loads(cards[0])
    return card


async def test_asked_to_play_mochi_starts_a_round_and_hosts_it_in_the_same_breath() -> None:
    harness = await _woken(LETS_PLAY)
    home, audience = await harness.connect(HOME), await harness.connect(AUDIENCE)
    outcome = await harness.say("Let's play a game.")
    assert outcome.reply == "Yay, let's play! Ben describes. Ana guesses!"
    store = harness.container.core.store
    assert store.activity.state is GameState.ACTIVE_ROUND and store.mode is SessionMode.ACTIVITY
    assert "activity.private_prompt" in home.types()
    assert "activity.private_prompt" not in audience.types()
    assert harness.agora.spoken == []  # one reply through the turn, no second line cutting it off
    kinds = [c.kind for c in harness.container.devices.state("home_pi_01").commands]
    assert "play" not in kinds and "mood" in kinds  # [play] is not for the device


async def test_once_playing_mochi_stays_out_until_called() -> None:
    harness = await _woken(LETS_PLAY, "[mood happy] Hello!")
    await harness.say("Let's play a game.")
    described = await harness.say("You open it when it rains.")
    assert described.reply == ""  # said to the guesser, not to Mochi


async def test_asking_again_while_a_round_runs_does_not_start_a_second_one() -> None:
    harness = await _woken(LETS_PLAY)
    await harness.say("Let's play a game.")
    first = harness.container.core.store.activity.round_id
    again = await harness.say("Hi Mochi, let's play!")
    assert again.reply == "Yay, let's play!"
    assert harness.container.core.store.activity.round_id == first
    assert "play_not_started" in [event for event, _fields in harness.logger.lines]


async def test_the_device_finds_the_round_in_its_state_and_the_word_needs_the_key() -> None:
    harness = await _woken(LETS_PLAY)
    client = TestClient(create_app(harness.container))
    await harness.say("Let's play a game.")
    card = _round(client, KEY)
    assert card["state"] == "ACTIVE_ROUND" and card["secret_word"] == "umbrella"
    assert (card["describer_user_id"], card["guesser_user_id"]) == ("ben", "ana")
    assert card["language"] == "en" and card["revealed_word"] is None
    assert _round(client)["secret_word"] is None  # the route is open: no key, no word
    assert "umbrella" not in client.get(STATE).text
    assert _round(client, {"Authorization": "Bearer wrong"})["secret_word"] is None


async def test_the_round_outlives_a_queued_command_and_is_found_again() -> None:
    harness = await _woken(LETS_PLAY)
    client = TestClient(create_app(harness.container))
    await harness.say("Let's play a game.")
    first = client.get(STATE, headers=KEY).json()["commands"]
    harness.clock.advance(120)  # two minutes of describing; queued commands live for thirty seconds
    later = client.get(STATE, headers=KEY).json()["commands"]
    assert [c["kind"] for c in later] == ["round"]
    ids = [c["command_id"] for c in first if c["kind"] == "round"]
    assert ids == [c["command_id"] for c in later]  # the same round: the device acts on it once


async def test_the_result_is_said_aloud_and_shown_then_the_roles_swap() -> None:
    harness = await _woken(LETS_PLAY)
    client = TestClient(create_app(harness.container))
    await harness.say("Let's play a game.")
    active = client.get(STATE, headers=KEY).json()["commands"][-1]["command_id"]
    await harness.container.activity.finish(RoundResult.GUESSED)
    assert harness.agora.spoken[-1][1] == "Ana got it!"
    card = _round(client)  # after the round the word is public
    assert card["state"] == "ROUND_RESULT" and card["result"] == "guessed"
    assert card["revealed_word"] == "umbrella" and card["secret_word"] is None
    assert client.get(STATE).json()["commands"][-1]["command_id"] != active
    await harness.container.activity.start()  # the next round: the guesser describes
    card = _round(client, KEY)
    assert (card["describer_user_id"], card["guesser_user_id"]) == ("ana", "ben")
    assert harness.agora.spoken[-1][1] == "Ana describes. Ben guesses!"


async def test_no_round_no_card_and_a_stopped_session_forgets_the_round() -> None:
    harness = await _woken(LETS_PLAY)
    client = TestClient(create_app(harness.container))
    assert [c["kind"] for c in client.get(STATE, headers=KEY).json()["commands"]] == []
    await harness.say("Let's play a game.")
    await harness.container.sessions.stop()
    await harness.container.sessions.start()
    assert [c["kind"] for c in client.get(STATE, headers=KEY).json()["commands"]] == []
    await harness.container.activity.start()
    assert _round(client, KEY)["describer_user_id"] == "ben"  # a new session starts as the first


async def test_the_secret_word_is_never_logged() -> None:
    harness = await _woken(LETS_PLAY)
    client = TestClient(create_app(harness.container))
    await harness.say("Let's play a game.")
    client.get(STATE, headers=KEY)
    logged = json.dumps([[event, dict(fields)] for event, fields in harness.logger.lines])
    assert "umbrella" not in logged


async def test_after_a_round_mochi_answers_follow_ups_again() -> None:
    """A finished round used to count as a round: Mochi then only answered "Oi Mochi" until Stop."""
    harness = await _woken(LETS_PLAY, "[mood happy] Sure!", "[mood happy] It was fun!")
    await harness.say("Let's play a game.")
    await harness.container.activity.finish(RoundResult.SKIPPED)
    assert (await harness.say("Hi Mochi, can we talk?")).reply == "Sure!"
    assert (await harness.say("Did you like the game?")).reply == "It was fun!"  # no name needed


async def test_a_short_answer_is_answered_in_the_language_mochi_was_called_in() -> None:
    """Seen with the real model: after "hi Mochi", "Play." got a Portuguese reply, because a
    sentence that could be either language followed the last session's language."""
    mochi = FakeCharacterModel("[mood happy] Ok!")
    harness = make_harness(character=mochi)
    await harness.container.sessions.start(woken_by="oi mochi")
    await harness.say("Ok.")
    await harness.container.sessions.stop()
    await harness.container.sessions.start(woken_by="hi mochi")
    await harness.say("Ok.")
    assert [request.language.value for request in mochi.requests] == ["pt-BR", "en"]


async def test_the_reply_that_starts_a_round_cannot_say_its_word() -> None:
    """Mochi writes its line before the word is drawn. Found in review: "[play] Umbrella weather!"
    was said, shown and logged while "umbrella" was the round's secret."""
    harness = await _woken("[mood happy][play][show umbrella] Umbrella weather! Let's play!")
    client = TestClient(create_app(harness.container))
    ana = await harness.connect(ANA)
    outcome = await harness.say("Let's play a game.")
    assert outcome.reply == "Ben describes. Ana guesses!"  # the host's line alone
    assert harness.container.core.store.activity.state is GameState.ACTIVE_ROUND
    assert "umbrella" not in "".join(ana.texts).lower()
    assert "umbrella" not in client.get(STATE).text.lower()
    logged = json.dumps([[event, dict(fields)] for event, fields in harness.logger.lines])
    assert "umbrella" not in logged.lower() and "secret_leak_blocked" in logged


async def test_an_old_result_is_not_shown_to_a_device_that_looks_later() -> None:
    harness = await _woken(LETS_PLAY)
    client = TestClient(create_app(harness.container))
    await harness.say("Let's play a game.")
    await harness.container.activity.finish(RoundResult.GUESSED)
    assert _round(client)["state"] == "ROUND_RESULT"
    harness.clock.advance(31)
    assert [c["kind"] for c in client.get(STATE).json()["commands"]] == []
    await harness.container.activity.start()  # ...and the next round is there again
    assert _round(client, KEY)["describer_user_id"] == "ana"


async def test_a_reset_takes_the_round_off_the_device() -> None:
    harness = await _woken(LETS_PLAY)
    client = TestClient(create_app(harness.container))
    await harness.say("Let's play a game.")
    await harness.container.demo_reset.run()
    state = client.get(STATE, headers=KEY).json()
    assert state["capturing"] is True
    assert "round" not in [
        c["kind"] for c in state["commands"]
    ]  # the device then clears its screen


async def test_a_round_started_by_voice_is_found_again_by_a_home_that_reconnects() -> None:
    """The web PR re-sends the private prompt to a Home view that joins mid-round; a round that
    Mochi started from "let's play" must be remembered the same way as one started by the route."""
    harness = await _woken(LETS_PLAY)
    await harness.say("Let's play a game.")
    home, audience = await harness.connect(HOME), await harness.connect(AUDIENCE)
    assert "activity.private_prompt" in home.types()
    assert "activity.private_prompt" not in audience.types()
    await harness.container.activity.finish(RoundResult.GUESSED)
    assert "activity.private_prompt" not in (await harness.connect(HOME)).types()
