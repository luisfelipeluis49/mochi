"""The committed JSON Schema matches the models (the web app generates TypeScript from it)."""

from pathlib import Path

from mochi_contracts.export_schema import stale_files

SCHEMA_DIR = Path(__file__).resolve().parents[4] / "packages" / "contracts" / "schema"


def test_committed_schema_is_not_stale() -> None:
    assert stale_files(SCHEMA_DIR) == [], "run `make contracts-schema` and commit the result"
