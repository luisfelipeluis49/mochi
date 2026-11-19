"""Enforces the engineering rules in services/backend/AGENTS.md that linters cannot.

Each failure names the file, line and limit so it can be fixed without hunting.
"""

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[2] / "src" / "mochi_backend"
MAX_BODY_LINES = 20
MAX_FILE_LINES = 500
MAX_NESTING = 2
BANNED_NAMES = {"data", "handler"}
NESTING_NODES = (ast.If, ast.For, ast.AsyncFor, ast.While, ast.Try, ast.With, ast.AsyncWith)
FunctionNode = ast.FunctionDef | ast.AsyncFunctionDef


def _source_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _functions(tree: ast.Module) -> Iterator[FunctionNode]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            yield node


def _body_without_docstring(func: FunctionNode) -> list[ast.stmt]:
    first = func.body[0]
    is_doc = isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant)
    return func.body[1:] if is_doc and isinstance(first.value.value, str) else func.body  # type: ignore[attr-defined]


def _body_line_count(func: FunctionNode) -> int:
    body = _body_without_docstring(func)
    if not body:
        return 0
    return (body[-1].end_lineno or body[-1].lineno) - body[0].lineno + 1


def _max_depth(stmts: list[ast.stmt], depth: int = 0) -> int:
    deepest = depth
    for stmt in stmts:
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue  # nested defs are checked as their own functions
        inner = depth + 1 if isinstance(stmt, NESTING_NODES) else depth
        for block in _child_blocks(stmt):
            deepest = max(deepest, _max_depth(block, inner))
        deepest = max(deepest, inner)
    return deepest


def _child_blocks(stmt: ast.stmt) -> list[list[ast.stmt]]:
    blocks: list[list[ast.stmt]] = []
    for field in ("body", "orelse", "finalbody"):
        value = getattr(stmt, field, None)
        if isinstance(value, list):
            blocks.append([item for item in value if isinstance(item, ast.stmt)])
    for handler in getattr(stmt, "handlers", []):
        blocks.append(handler.body)
    return blocks


def _where(path: Path, line: int) -> str:
    return f"{path.relative_to(SRC.parent.parent)}:{line}"


def test_source_tree_is_not_empty() -> None:
    assert _source_files(), f"no python files found under {SRC}; the rules would pass vacuously"


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: p.name)
def test_file_is_under_size_limit(path: Path) -> None:
    lines = len(path.read_text(encoding="utf-8").splitlines())
    assert lines < MAX_FILE_LINES, f"{_where(path, 1)}: {lines} lines; limit is {MAX_FILE_LINES}"


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: p.name)
def test_function_bodies_are_short(path: Path) -> None:
    for func in _functions(_parse(path)):
        count = _body_line_count(func)
        assert count <= MAX_BODY_LINES, (
            f"{_where(path, func.lineno)}: {func.name}() body is {count} lines; "
            f"limit is {MAX_BODY_LINES}"
        )


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: p.name)
def test_nesting_is_shallow(path: Path) -> None:
    for func in _functions(_parse(path)):
        depth = _max_depth(_body_without_docstring(func))
        assert depth <= MAX_NESTING, (
            f"{_where(path, func.lineno)}: {func.name}() nests {depth} levels; "
            f"limit is {MAX_NESTING}; use early returns"
        )


def _bad_name(name: str) -> bool:
    return name in BANNED_NAMES or "Manager" in name


def _declared_names(tree: ast.Module) -> Iterator[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            yield node.name, node.lineno
        if isinstance(node, ast.arg):
            yield node.arg, node.lineno
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            yield node.id, node.lineno


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: p.name)
def test_no_vague_names(path: Path) -> None:
    for name, line in _declared_names(_parse(path)):
        assert not _bad_name(name), (
            f"{_where(path, line)}: identifier {name!r} is too vague; "
            f"avoid 'data', 'handler' and anything containing 'Manager'"
        )


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: p.name)
def test_public_functions_have_docstrings(path: Path) -> None:
    for func in _functions(_parse(path)):
        if func.name.startswith("_"):
            continue
        assert ast.get_docstring(func), (
            f"{_where(path, func.lineno)}: public function {func.name}() has no docstring; "
            f"add intent plus one usage example"
        )


def _imported_modules(tree: ast.Module) -> Iterator[tuple[str, int]]:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            yield ("." * node.level) + node.module, node.lineno
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno


def _package_files(package: str) -> list[Path]:
    return sorted((SRC / package).rglob("*.py"))


def test_intelligence_never_imports_gateway() -> None:
    for path in _package_files("intelligence"):
        for module, line in _imported_modules(_parse(path)):
            assert "gateway" not in module.split("."), (
                f"{_where(path, line)}: imports {module!r}; intelligence must not import gateway"
            )


def test_gateway_reaches_intelligence_only_through_the_port() -> None:
    allowed = {"intelligence_port.py"}
    for path in _package_files("gateway"):
        for module, line in _imported_modules(_parse(path)):
            assert "intelligence" not in module.split(".") or path.name in allowed, (
                f"{_where(path, line)}: imports {module!r}; gateway may import intelligence "
                f"only inside {sorted(allowed)}"
            )
