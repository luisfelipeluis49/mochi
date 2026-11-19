# Decisions

Short ADR-style entries for choices the build prompt left open.

## D-01 Ruff ignores for tests
`tests/**` ignores S101 (assert), PLR2004 (magic numbers) and ANN001/ANN201/ANN202 (pytest fixtures
and tiny test helpers) and S105/S106 (the game's `secret_word` field is not a password). Tests assert by nature and compare against literal expected values.

## D-02 uv installed with the official installer
No `pipx` and no `python3-venv` on this machine, so uv 0.13.9 was installed with Astral's official
installer into `~/.local/bin` (profile untouched). Nothing in the repo requires this exact install method.

## D-03 Nullable round fields on Activity (contract proposal)
AGENTS 6.2 shows only an active-round Activity. To publish `IDLE` the fields `round_id`,
`describer_user_id`, `guesser_user_id`, `public_instruction` and `word_source` are nullable.
Needs human approval; revert to non-null plus a sentinel if the team prefers.

## D-04 Root CLAUDE.md is not a single line
The prompt asked for exactly `@AGENTS.md`. The file also carries the advisor rule the user asked for
(consult the advisor before locking a plan, after the same error twice, before calling a task done).

## D-05 Timestamps are validated strings
`IsoTimestamp` is a regex-constrained string (`...T16:00:04.700Z`) so JSON round-trips are exact and the
format is identical for every language that reads the schema.

## D-06 Hint cooldown vs the demo walkthrough
AGENTS 7.2 suppresses a hint when one was shown in either of the last two turns. The two demo sentences
therefore need at least two non-hint turns between them in the integration test and `smoke.sh`.
Cooldown is implemented exactly as written.

## D-07 Intelligence is an object; round secrets live inside it
AGENTS 6.5 shows module-level functions. The build prompt forbids module singletons, so `Intelligence`
(clock, ids, model injected) exposes `decide`, `handle`, `apply`, `words_for` and `reset`.
`handle()` is not strictly pure: the public `Activity` never holds the secret word, so the
`RoundEngine` remembers each round's `PrivatePrompt` until the result arrives.

## D-08 Cooldown is computed from timestamps
`SessionContext` has no link between turns and hints. A hint belongs to a turn when it was created after
that turn arrived (`expires_at - ttl`), so tests must advance the clock between turns.

## D-09 ASSISTED rides along with `decide()`
`apply()` only receives proposals, so `decide()` returns ASSISTED upgrades in `Decision.learning_events`
even when the decision is IGNORE.

## D-10 Rules first, model second
Lexicon cues and markers resolve cases 1-9 without a model; the model is asked only when a marker or an
ask-for-word pattern could not be resolved (or a foreign word appears in an otherwise focus-language turn).

## D-11 The shared key is sent two ways
Agora's docs do not name the header that carries `llm.api_key`. We send the key as `llm.api_key` and also as
`X-Mochi-Key` through `llm.headers`; the endpoint accepts either (constant-time compare). See `VERIFIED.md`.

## D-12 Intelligence `reset` and the device-state models (contract proposals)
`IntelligencePort.reset()` is needed by `POST /api/demo/reset`. The device-state response models
(`DeviceState`, `AgoraJoinInfo`) live in the gateway; they could move to `packages/contracts`.

## D-13 `agora-token-builder` produces `006` tokens
The package named in Agora's own tutorial builds AccessToken v1. Kept because it is the documented path;
whether Agora and the Pi's IoT SDK accept `006` is untested (see `VERIFIED.md`).

## D-14 Dev routes are off by default
`MOCHI_ENABLE_DEV_ROUTES` defaults to `false` (the route is not mounted). `scripts/start-dev.sh` turns it on;
`render.yaml` leaves it off.

## D-15 Milestone commits are combined
The gateway and intelligence were built in one pass across M0-M4, so the history has one commit per area
(scaffold, contracts, intelligence, gateway, deploy, docs) instead of one per milestone.

## D-16 Learning events are published before the hint
AGENTS 9.2 orders the chain "apply learning events, then publish". A client therefore sees
`learning_event.created` before `hint.created` for the same turn.

## D-17 Inventory of every rule exception (for the final report, section 13.8)
Rules that were bent, and where:
- **Ruff ignores for tests** (`tests/**`: S101, S105, S106, PLR2004, ANN001, ANN201, ANN202): see D-01.
- **mypy override** for `agora_token_builder` (`ignore_missing_imports`): the package ships no types; it is
  wrapped by `gateway/agora/token_issuer.py` behind `RtcTokenIssuer`.
- **`type: ignore[attr-defined]`** in `tests/architecture/test_code_rules.py` (one line): `ast` types the
  docstring constant loosely.
- **Function-length rule:** several long argument lists were bundled into dataclasses (`PipelineDeps`,
  `GatewayCore`, `IntelligenceSettings`) rather than ignoring PLR0913.
- **Fixed instead of ignored:** HTTP status literals became named constants (`HTTP_OK` ...); the exception is
  named `AgentAlreadyStoppedError` (N818); a dead `noqa: BLE001` was removed (BLE is not selected).
- **Bare `except Exception`** in `TurnPipeline._decide` is deliberate: one bad turn must not stop the
  session; it is logged as `decide_failed` and the turn is treated as IGNORE.
- **No `Any`:** none in `src`. `JsonValue` is a recursive alias; Agora and model replies are parsed with
  Pydantic models.
