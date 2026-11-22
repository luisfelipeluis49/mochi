"""Web users and session records (D-42): ids, directory, participants, records, socket query."""

import re
from datetime import timedelta

import pytest

from mochi_backend.gateway.connections import parse_target
from mochi_backend.gateway.delivery_rules import ConnectionTarget
from mochi_backend.gateway.errors import ConflictError
from mochi_backend.gateway.session_history import SessionHistory
from mochi_backend.gateway.user_directory import (
    UserDirectory,
    is_web_user,
    session_participants,
    slug_of,
    voice_owners,
)
from mochi_backend.storage.session_record import SessionRecord, SessionTally, build_record
from mochi_contracts import Language, User
from tests.fakes.fake_clock import START
from tests.fakes.fake_storage import FakeStorage
from tests.fakes.fake_suffixes import ScriptedSuffixes, SeededSuffixes

ID_SHAPE = re.compile(r"^[a-z0-9-]{3,27}$")


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Luís Felipe", "luis-felipe"),
        ("李", "user"),
        ("Ana", "ana"),
        ("  --Zoë   O'Brien!!  ", "zoe-o-brien"),
        ("a" * 60, "a" * 20),
        ("abcdefghijklmnopqrs tuv", "abcdefghijklmnopqrs"),  # cut at a dash: no trailing "-"
        ("Ünïcødé 123", "unicde-123"),
    ],
)
def test_slug_of_folds_lowercases_dashes_and_cuts(name: str, slug: str) -> None:
    assert slug_of(name) == slug


def test_a_slug_never_starts_or_ends_with_a_dash() -> None:
    for name in ("-a-", "!!x!!", "  y  ", "a" * 19 + " b"):
        made = slug_of(name)
        assert not made.startswith("-") and not made.endswith("-")


def _directory(suffixes: ScriptedSuffixes | SeededSuffixes | None = None) -> UserDirectory:
    return UserDirectory(FakeStorage(), [], suffixes or SeededSuffixes(1))


def test_200_random_names_all_make_ids_of_the_promised_shape() -> None:
    directory = _directory(SeededSuffixes(42))
    alphabet = "abcXYZ ãéíõü-_.!李0123456789"
    picker = SeededSuffixes(7)
    for number in range(200):
        size = 1 + number % 45
        name = "".join(alphabet[int(picker.suffix(), 16) % len(alphabet)] for _ in range(size))
        user = directory.create(name.strip() or "x", Language.PT_BR, Language.EN)
        assert ID_SHAPE.fullmatch(user.user_id), user.user_id
        assert user.user_id not in ("ana", "ben", "guest") and is_web_user(user.user_id)


def test_create_saves_and_finds_the_user_and_ana_is_never_taken() -> None:
    storage = FakeStorage()
    directory = UserDirectory(storage, [], ScriptedSuffixes("3f9c1a"))
    user = directory.create("Ana", Language.PT_BR, Language.EN)
    assert user.user_id == "ana-3f9c1a" and user.comfortable_languages == [Language.PT_BR]
    assert directory.find("ana-3f9c1a") == user and storage.users == [user]
    assert directory.find("ana") is not None and directory.find("ana") != user


def test_guest_is_reserved_and_unknown_users_are_not_found() -> None:
    directory = UserDirectory(FakeStorage(), [_user("guest")], SeededSuffixes(1))
    assert directory.find("guest") is None and not directory.may_connect("guest")
    assert directory.find("nobody") is None and not directory.may_connect("nobody")
    assert directory.may_connect("ana") and directory.may_connect("ben")


def test_a_taken_id_is_drawn_again() -> None:
    suffixes = ScriptedSuffixes("aaaaaa", "aaaaaa", "bbbbbb")
    directory = _directory(suffixes)
    first = directory.create("Luís", Language.PT_BR, Language.EN)
    second = directory.create("Luis", Language.PT_BR, Language.EN)
    assert (first.user_id, second.user_id) == ("luis-aaaaaa", "luis-bbbbbb")
    assert suffixes.drawn == 3


def test_a_source_that_only_repeats_is_a_clear_conflict() -> None:
    directory = _directory(ScriptedSuffixes("aaaaaa"))
    directory.create("Luís", Language.PT_BR, Language.EN)
    with pytest.raises(ConflictError, match="no free user id"):
        directory.create("Luís", Language.PT_BR, Language.EN)


def test_users_stored_before_a_restart_are_known() -> None:
    stored = _user("luis-felipe-3f9c1a")
    directory = UserDirectory(FakeStorage(), [stored], SeededSuffixes(1))
    assert directory.find(stored.user_id) == stored


def _user(user_id: str, home: Language = Language.PT_BR, name: str = "") -> User:
    target = Language.EN if home is Language.PT_BR else Language.PT_BR
    return User(
        user_id=user_id,
        display_name=name or user_id,
        comfortable_languages=[home],
        target_language=target,
    )


def test_the_guest_has_the_users_languages_the_other_way_round() -> None:
    own, guest = session_participants(_user("luis-3f9c1a"))
    assert own.user_id == "luis-3f9c1a" and own.target_language is Language.EN
    assert guest.user_id == "guest"
    assert guest.comfortable_languages == [Language.EN] and guest.target_language is Language.PT_BR
    _, other = session_participants(_user("sam-000001", Language.EN))
    assert other.comfortable_languages == [Language.PT_BR] and other.target_language is Language.EN


def test_voices_belong_to_the_pis_people_not_to_web_users_or_the_guest() -> None:
    stored = [_user("ana-3f9c1a", name="Ana"), _user("guest"), _user("ana", name="Ana")]
    owners = [user.user_id for user in voice_owners(stored)]
    assert owners == ["ana", "ben"]


def test_parse_target_accepts_a_created_user_and_refuses_guest() -> None:
    directory = _directory(ScriptedSuffixes("3f9c1a"))
    user = directory.create("Luís", Language.PT_BR, Language.EN)
    query = {"user": user.user_id, "session": "w-1a2b3c4d"}
    expected = ConnectionTarget("mobile", user_id=user.user_id, session_id="w-1a2b3c4d")
    assert parse_target(query, directory.may_connect) == expected
    assert parse_target({"user": "ana"}, directory.may_connect).user_id == "ana"
    assert parse_target({"user": "ben"}, directory.may_connect).user_id == "ben"
    with pytest.raises(ValueError, match="user=ana\\|ben\\|<user_id>"):
        parse_target({"user": "guest"}, directory.may_connect)


def test_parse_target_without_a_directory_knows_only_ana_and_ben() -> None:
    with pytest.raises(ValueError, match="unknown connection query"):
        parse_target({"user": "luis-3f9c1a"})


def _record(user_id: str, ended_seconds: float, ids: list[str] | None = None) -> SessionRecord:
    tally = SessionTally(user_id, START, 1, ids or [])
    return build_record(
        f"rec_{ended_seconds:g}", "w-1", tally, START + timedelta(seconds=ended_seconds)
    )


def test_a_record_rounds_minutes_and_keeps_each_id_once_in_first_order() -> None:
    record = _record("luis", 750, ["learn_2", "learn_1", "learn_2", "learn_3", "learn_1"])
    assert record.minutes == 12.5
    assert record.learning_event_ids == ["learn_2", "learn_1", "learn_3"]
    assert record.started_at == "2026-11-19T16:00:00.000Z"
    assert record.ended_at == "2026-11-19T16:12:30.000Z"
    assert _record("luis", 92).minutes == 1.5 and _record("luis", 3).minutes == 0.1


def test_history_is_per_user_newest_first_capped_and_saved() -> None:
    storage = FakeStorage()
    history = SessionHistory(storage, [_record("luis", 10)])
    for seconds in range(20, 20 + 60):
        history.add(_record("luis", seconds))
    history.add(_record("sam", 5000))
    mine = history.for_user("luis")
    assert len(mine) == 50 and mine[0].ended_at > mine[1].ended_at
    assert [r.user_id for r in history.for_user("sam")] == ["sam"]
    assert len(storage.sessions) == 61  # the restored one was already stored
