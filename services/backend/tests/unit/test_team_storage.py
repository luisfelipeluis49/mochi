"""The company tables in each storage: the local file, the write-behind queue, the startup read."""

from pathlib import Path

from mochi_backend.gateway.roster import DEMO_COMPANY, DEMO_MEMBERS, DEMO_USERS
from mochi_backend.storage.factory import Seed, StorageStart, TeamStart, storage_for
from mochi_backend.storage.local_file import LocalFileStorage
from mochi_backend.storage.port import NullStorage
from mochi_backend.storage.postgres_team import _member, _moment, _record, _report, _utterance
from mochi_backend.storage.write_behind import WriteBehindStorage
from mochi_contracts import Member, MemberRole, Utterance
from tests.fakes.fake_sender import FakeEventLogger
from tests.fakes.fake_storage import FakeStorage
from tests.unit.test_speech_report import draft
from tests.unit.test_team_view import moment, record

SEED = Seed(DEMO_USERS, DEMO_COMPANY, DEMO_MEMBERS)
SAID = Utterance(
    utterance_id="seg_1",
    company_id="demo",
    record_id="rec_1",
    user_id=None,
    text="I need to adiar my meeting",
    at="2026-11-19T16:00:04.500Z",
)


def test_the_company_and_its_history_survive_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "mochi.json"
    first = LocalFileStorage(path, FakeEventLogger())
    SEED.into(first)
    first.save_record(record())
    first.save_record(record().model_copy(update={"ended_at": None}))  # replaced, same place
    first.save_moment(moment("postpone", "ana"))
    first.save_utterance(SAID)
    first.save_utterance(SAID.model_copy(update={"user_id": "ana"}))  # its speaker became known
    caio = DEMO_USERS[0].model_copy(update={"user_id": "caio", "display_name": "Caio"})
    first.save_user(caio)
    first.save_member(Member(company_id="demo", user_id="caio", role=MemberRole.MEMBER))
    again = TeamStart.read(LocalFileStorage(path, FakeEventLogger()))
    assert again.companies == [DEMO_COMPANY]
    assert [m.user_id for m in again.members] == ["ana", "ben", "caio"]
    assert [r.ended_at for r in again.records] == [None]
    assert [m.expression for m in again.moments] == ["postpone"]
    assert [(u.text, u.user_id) for u in again.utterances] == [(SAID.text, "ana")]
    assert "caio" in [u.user_id for u in LocalFileStorage(path, FakeEventLogger()).load_users()]


def test_seeding_never_overwrites_a_changed_role(tmp_path: Path) -> None:
    store = LocalFileStorage(tmp_path / "m.json", FakeEventLogger())
    SEED.into(store)
    store.save_member(Member(company_id="demo", user_id="ben", role=MemberRole.ADMIN))
    SEED.into(store)
    roles = {m.user_id: m.role for m in store.load_members()}
    assert roles == {"ana": MemberRole.ADMIN, "ben": MemberRole.ADMIN}


def test_clearing_the_history_keeps_the_people(tmp_path: Path) -> None:
    store = LocalFileStorage(tmp_path / "m.json", FakeEventLogger())
    SEED.into(store)
    store.save_record(record())
    store.save_moment(moment("postpone", "ana"))
    store.save_utterance(SAID)
    store.clear_history()
    assert store.load_records() == [] and store.load_moments() == []
    assert store.load_utterances() == []
    assert len(store.load_members()) == 2 and store.load_companies() == [DEMO_COMPANY]


def test_a_local_start_reads_the_company_tables_once(tmp_path: Path) -> None:
    start = storage_for("", FakeEventLogger(), SEED, str(tmp_path / "m.json"))
    assert start.team.companies == [DEMO_COMPANY] and len(start.team.members) == 2
    assert isinstance(start.storage, WriteBehindStorage)
    assert StorageStart().team == TeamStart() and TeamStart.read(NullStorage()) == TeamStart()


def test_team_writes_are_queued_in_order_and_a_reset_drops_what_was_waiting() -> None:
    inner = FakeStorage()
    behind = WriteBehindStorage(inner, FakeEventLogger())
    inner.broken = True
    behind.save_record(record())
    behind.save_moment(moment("postpone", "ana"))
    behind.save_utterance(SAID)
    behind.flush()
    assert behind.unsaved_writes() == 3 and inner.moments == {}
    inner.broken = False
    behind.clear_history()  # newer than both: they must not come back after it
    behind.flush()
    assert behind.unsaved_writes() == 0 and inner.records == {} and inner.moments == {}
    assert inner.utterances == {} and behind.load_utterances() == []
    behind.save_utterance(SAID)
    behind.flush()
    assert list(inner.utterances) == ["seg_1"]
    behind.save_user(DEMO_USERS[0])
    behind.save_member(DEMO_MEMBERS[0])
    behind.flush()
    assert inner.calls[-2:] == ["save_user", "save_member"]
    assert behind.load_companies() == [] and behind.load_members() == [DEMO_MEMBERS[0]]
    assert behind.load_records() == [] and behind.load_moments() == []


def test_postgres_rows_parse_back_into_the_contract() -> None:
    kept, said = record(), moment("postpone", "ana")
    assert _record((kept.record_id, kept.model_dump_json())) == kept
    assert _moment((said.moment_id, said.model_dump_json())) == said
    assert _utterance((SAID.utterance_id, SAID.model_dump_json())) == SAID
    assert _member(("demo", "ana", "admin", None)) == DEMO_MEMBERS[0]
    assert _member(("demo", "ben", "member", "Sales")).team == "Sales"


def test_no_database_means_nothing_is_kept_and_nothing_fails() -> None:
    nothing = NullStorage()
    nothing.save_user(DEMO_USERS[0])
    nothing.seed_company(DEMO_COMPANY, DEMO_MEMBERS)
    nothing.save_member(DEMO_MEMBERS[0])
    nothing.save_record(record())
    nothing.save_moment(moment("postpone", "ana"))
    nothing.save_utterance(SAID)
    nothing.clear_history()
    assert nothing.load_utterances() == []
    assert nothing.load_companies() == [] and nothing.load_members() == []


def test_reports_are_kept_with_the_history_and_go_with_it(tmp_path: Path) -> None:
    report = draft()
    path = tmp_path / "m.json"
    first = LocalFileStorage(path, FakeEventLogger())
    SEED.into(first)
    first.save_report(report)
    first.save_report(report.model_copy(update={"strengths": ["changed"]}))  # never rewritten
    again = LocalFileStorage(path, FakeEventLogger())
    assert again.load_reports() == [report] and TeamStart.read(again).reports == [report]
    again.clear_history()
    assert again.load_reports() == []
    inner = FakeStorage()
    behind = WriteBehindStorage(inner, FakeEventLogger())
    behind.save_report(report)
    behind.flush()
    assert behind.load_reports() == [report]
    behind.clear_history()
    behind.flush()
    assert inner.reports == {}
    nothing = NullStorage()
    nothing.save_report(report)
    assert nothing.load_reports() == []
    assert _report((report.report_id, report.model_dump_json())) == report
