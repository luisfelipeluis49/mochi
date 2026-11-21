"""Export JSON Schema from the models so the web app can generate TypeScript types.

Usage: `python -m mochi_contracts.export_schema <out_dir> [--check]`.
`--check` fails if the committed files differ from the models (stale schema).
"""

import json
import sys
from pathlib import Path

from pydantic import BaseModel

from mochi_contracts import models
from mochi_contracts.envelope import Envelope

EXPORTED: list[type[BaseModel]] = [
    Envelope,
    models.SessionState,
    models.Hint,
    models.HintCleared,
    models.Activity,
    models.PrivatePrompt,
    models.LearningEvent,
    models.Speak,
    models.Turn,
    models.SessionContext,
    models.Decision,
    models.ActivityCommand,
    models.ActivityResult,
    models.User,
    models.VoiceProfile,
    models.VoiceprintUpload,
]


def render_schemas() -> dict[str, str]:
    """Return `{filename: json_text}` for every exported model.

    Example: `render_schemas()["Hint.json"]` starts with `{`.
    """
    return {
        f"{model.__name__}.json": json.dumps(model.model_json_schema(), indent=2, sort_keys=True)
        + "\n"
        for model in EXPORTED
    }


def stale_files(out_dir: Path) -> list[str]:
    """Names of schema files that are missing or differ from the models."""
    stale: list[str] = []
    for name, text in render_schemas().items():
        path = out_dir / name
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            stale.append(name)
    return stale


def write_schemas(out_dir: Path) -> None:
    """Write every schema file into `out_dir`."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in render_schemas().items():
        (out_dir / name).write_text(text, encoding="utf-8")


def main(argv: list[str]) -> int:
    """CLI entry. Returns the process exit code."""
    out_dir = Path(argv[1])
    if "--check" in argv:
        stale = stale_files(out_dir)
        if stale:
            print(f"stale schema files in {out_dir}: {stale}; run `make contracts-schema`")
            return 1
        return 0
    write_schemas(out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
