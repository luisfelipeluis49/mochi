"""Shell helpers the scripts share. Runs bash on temp files only (no Docker, no network)."""

import subprocess
from pathlib import Path

LIB = Path(__file__).resolve().parents[4] / "scripts" / "_lib.sh"


def _docker_env(source: str, tmp_path: Path) -> str:
    src, dest = tmp_path / "in.env", tmp_path / "out.env"
    src.write_text(source, encoding="utf-8")
    command = f'. "{LIB}"; docker_env_file "{src}" "{dest}"'
    subprocess.run(["bash", "-c", command], check=True)  # noqa: S603, S607
    return dest.read_text(encoding="utf-8")


def test_docker_env_file_strips_the_shell_quotes_around_json_values(tmp_path: Path) -> None:
    got = _docker_env('A=1\nB=\'{"x":{"y":1}}\'\nC="two words"\n# note\nD=plain\n', tmp_path)
    assert got == 'A=1\nB={"x":{"y":1}}\nC=two words\n# note\nD=plain\n'


def test_docker_env_file_leaves_unquoted_and_inner_quotes_alone(tmp_path: Path) -> None:
    assert _docker_env("E=it's\nF=a=b\n", tmp_path) == "E=it's\nF=a=b\n"
