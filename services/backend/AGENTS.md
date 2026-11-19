# Backend engineering rules

Product and contracts live in the root `AGENTS.md`. This file is the engineering rulebook for
`services/backend`. Run `make verify` before every commit.

## Local instructions
- Read every more-specific `AGENTS.md` that applies to the files you change. `apps/web/AGENTS.md`
  (when Tasnim adds it) holds the web app's framework rules.

## Code style
- **Function length:** 4-20 body lines (signature and docstring excluded). Split anything longer.
- **File size:** under 500 lines. Split by responsibility.
- **SRP:** one thing per function, one responsibility per module.
- **Names:** specific and unique; never `data`, `handler` or `*Manager*`. Prefer names with
  fewer than 5 grep hits.
- **Types:** explicit everywhere. `mypy --strict` with no `Any` (`disallow_any_explicit`,
  `disallow_any_generics`, Ruff `ANN401`). No bare `dict` payloads: use Pydantic models,
  `TypedDict`, or `Mapping[K, V]` with concrete types. Every function fully annotated.
- **No duplication.** Extract shared logic.
- **Early returns**, at most 2 indentation levels inside a function body.
- **Exception messages** include the offending value and the expected shape, e.g.
  `f"unknown connection query {query!r}; expected one of user=ana|ben, device=home_pi_01, view=audience"`.

## Comments
- Keep existing comments; they carry intent and provenance. Write WHY, not WHAT.
- Public functions get a docstring: intent plus one usage example.
- Reference the source of upstream constraints, e.g.
  `# Agora custom LLM expects SSE ending in [DONE] - see gateway/agora/VERIFIED.md`.

## Tests
- `make verify` = format check, lint, mypy strict, architecture rules, pytest, schema check.
  `make test` = pytest only.
- Every new function gets a test; every bug fix gets a regression test.
- External I/O (Agora, LLM, HTTP, filesystem, time) is replaced by **named fakes** in
  `tests/fakes/` (`FakeAgoraClient`, `FakeHintModel`, `FakeClock`, `FakeScheduler`, ...).
  No inline stubs, no `MagicMock`.
- F.I.R.S.T.: no network, no real sleeps (inject clock and scheduler), no shared mutable state.

## Dependencies
- Inject through constructors/parameters. No module-level singletons or global state. FastAPI routes
  get collaborators from the container attached in `create_app`, via typed `Depends` providers.
- Wrap every third-party library behind a project-owned `Protocol` (Agora REST, token builder,
  LLM API, HTTP, time, ids, logger).

## Structure
- FastAPI conventions: `routes/` (HTTP/WS edges) -> services -> domain. Small modules, predictable paths.
- `intelligence` never imports `gateway`. `gateway` reaches intelligence only through
  `gateway/intelligence_port.py`. Enforced by `tests/architecture/test_code_rules.py`.

## Formatting and logging
- `ruff format` and `ruff check` (E, F, I, B, UP, ANN, SIM, RET, PL, N, S, C90; max-complexity 8).
- Structured JSON logs through `platform/json_logging.py`. Plain text only for `scripts/` output.
  Never log keys or tokens.

## Where the rules bend
Every ruff ignore or exception is recorded in `docs/DECISIONS.md` when it is added.
