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
Agora's `join` accepted a `006` token built for the agent uid (tested 2026-11-20, see `VERIFIED.md`);
whether the Pi's IoT SDK accepts a `006` token is still untested.

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

## D-18: speech vendors are configurable end to end, default to Agora-managed

First real Agora call (2026-11-20) failed on managed `ares` (SKU) and showed that vendor `params` can be nested
(MiniMax `voice_setting`). Fixes: `VendorParams` became `dict[str, JsonValue]`; `credential_mode` is a setting for
ASR and TTS; empty `params` are omitted. Defaults moved from microsoft (needs an Azure key, budget is $0) to
ares/minimax; the working pair on this project is deepgram + minimax, set in `.env.example` and `render.yaml`.
Not a contract change (AGENTS 6 does not cover vendor settings).


## D-19: review fixes (Codex and Antigravity reviews, 2026-11-20)

Two outside reviews found real races and rule problems. Each fix has a regression test.

- **Session transitions are serialized.** `SessionStore.generation` is bumped synchronously by Stop and
  Reset. Start holds a lock (two taps create one agent) and, after Agora's `join` returns, drops the new
  agent if the generation moved. A turn compares the generation after `decide()` and drops its result, so a
  hint, card or spoken line can no longer appear after Stop or Reset.
- **Stop turns capture off before calling Agora's `/leave`**, so the Pi's next poll already sees
  `capturing=false`. Stop also returns the game to IDLE (published) and forgets the round secret.
- **A second `activity/start` during ACTIVE_ROUND returns 409** ("send result 'skipped' or reset"). This is a
  new error path on an AGENTS 6.4 endpoint, not a new field or event.
- **Hub:** publishing is serialized (sequences reach clients in order); each send has a 1 s timeout and a
  stalled client is dropped. The secret guard scans only free-text payload fields at word starts, so a
  secret such as "state" cannot block events and "umbrellas" still counts as a leak of "umbrella".
- **Case 8 (`look_alike`) needs the model's confirmation.** AGENTS 7.1 has a model judge cases 5-9 and 7.2
  says quiet by default; "I'm actually working from home" and "The children pretend to travel" are correct
  English. With no model (the $0 setup) case 8 never fires.
- **ASSISTED window reopens** each time a saved word's hint is shown again (no new card is created then).
- **Phrase search ignores accents** (speech-to-text drops them).
- **Docker and `.env`:** `deploy.sh` strips the shell quotes into a temp file before `docker --env-file`.

Deferred or not changed, with the reason:
- Model-only paths (`cancelar` and "talks around" sentences reaching the model, model-learned words in
  rounds, a reusable HTTP client) change nothing without a paid model key.
- Replaying saved cards and the private prompt when a client reconnects: AGENTS 8 puts reconnect/replay out
  of scope and 6.4's snapshot does not include them. Proposal for Tasnim and Matheus.
- No sign-in on the public control endpoints: AGENTS 8.
- `focus` stays `en` (the demo is Ana practising English).
- `packages/contracts/examples/learning_event.updated.json` shows `DISCOVERED` with one history entry; it
  belongs to Matheus, so it is flagged, not edited.
- **Cost guard:** `idle_timeout` is now sent on `join` (`MOCHI_AGENT_IDLE_TIMEOUT_SECONDS`, default 60). The docs do
  not say what happens when the Pi never joins, and Start is public (AGENTS 8: no sign-in), so a stray Start can hold
  an agent open. Proposal, not built: auto-Stop after a maximum session length (for example 30 minutes).

## D-20: second review round (post-fix audit, 2026-11-20)

Fixed, each with a regression test:
- **One commit lock** (`GatewayCore.commit`) is held while a turn publishes its results and while Stop, Reset,
  round start and round finish publish theirs. Nothing from an in-flight turn arrives after Stop or Reset, a round
  finish cannot bring a card back after Reset, and a turn that was deciding when a round started cannot cover the game
  screen (only a wake phrase may still speak). `activity/start` publishes the session state before the `/speak` call,
  which now runs outside the lock.
- **WebSocket connect is atomic** (`EventHub.connect`): snapshot, send and register under the hub lock, so a client
  sees each event once and in order; a dead client is dropped at its first failed send; a snapshot never changes
  which secrets are protected. The route frees the client in `finally` and tolerates binary frames.
- **`/join` and `/speak` are not retried** (a retried join after a read timeout could create a second billed agent);
  `/leave` still is.
- **SSE chunks** carry `id`, `object`, `created`, `model`; the empty reply is an empty-content chunk plus a stop
  chunk plus `[DONE]`. `Bearer` matches case-insensitively. We could not confirm Agora needs these fields; they are
  the standard OpenAI shape.
- **Silence:** the speaking window never shortens; Stop and Reset close it (matters for `mute_speaker`).
- **Quiet by default without a model:** cues match whole words ("training" and "the rainbow" no longer mean
  umbrella); a wake phrase must carry an ask or a foreign word ("Oi Mochi, it's raining outside" stays quiet);
  serious topics match with accents dropped. The `marker_for` docstring example was wrong, not the rule.
- **Eval:** rows marked `eval: false` (no-model unit tests) are skipped; an empty list exits with a message.

Not changed, with the reason:
- `_look_alike` and `_stock_word` for `focus = pt-BR`: `focus` is fixed to `en` for the demo.
- Token refresh margin when the TTL is 300 s or less, and extra `Settings` bounds: the default TTL is 3600 s and
  the values are operator-set.
- Docker env edge cases (`export`, inline comments, CRLF): the project `.env` uses none of them.
- Rule edge cases off the demo path (grave accents, proper-noun stripping, partner-name escaping).
- `/join` failure detail echoes the Agora URL: the App ID is already public through the device-state endpoint.
- `_hint_users` growth: bounded by hints per session and cleared on Reset.
- Contract-side items (`IsoTimestamp` regex, `export_schema` arguments, `learning_event.updated.json`) belong to
  Matheus: proposals only.

## D-21: Portuguese groundwork and the real-turn test client

- **The practised language is decided per turn** (`intelligence/spoken_focus.py`), not once per session: a sentence
  practises the language it is mostly in; a question practises the opposite of the asked word's language ("Ben, como
  se diz recibo?" is Ana asking for an English word). `Session.focus` in the contract is unchanged, and hints and
  Speak lines already carry their own language, so there is no contract change. Touches Kauê's `intelligence/`.
- **Open, depends on a real session:** whether Deepgram `nova-3` with `language: multi` transcribes English and
  Portuguese together (the Agora and Deepgram docs disagree), and whether MiniMax can speak Portuguese
  (`language_boost` is a MiniMax parameter, not documented by Agora for managed mode). ASR language cannot be
  changed while an agent runs (the documented update endpoint covers only token, LLM messages and LLM params).
- **Not built yet:** rounds that alternate language (round 2: Ana describes, Ben guesses in Portuguese). The round
  engine takes its language from the session focus; waiting for the team to confirm the demo script
  (`docs/REAL_TURN_RUNBOOK.md`, section 4).
- **New dependency:** `scripts/test-client/index.html` loads the Agora Web SDK from a CDN. Development only.

## D-22: ears are ARES instead of Deepgram (hardware branch, 2026-11-20)

Defaults, `.env.example` and `render.yaml` now use `ares` with `en-US,pt-PT` and the keyword `Mochi`. D-18's
"managed `ares` is not available on our SKU" was the `credential_mode`, not the project: on a second Agora
project the same request failed with that exact message when `credential_mode` was `managed` and returned 200
without it (`VERIFIED.md`). Several languages are one comma-separated string (`en-US,pt-PT`) in both
`asr.language` and `turn_detection.language`, which is what Agora's own SDK sends; a list is accepted but then
only English is recognised (seen in a live session).
`MOCHI_ASR_KEYWORDS` is new. On mixed English and
Portuguese ARES made far fewer mistakes than Deepgram `nova-3` `multi` in the hardware owner's tests.
**Not verified:** that ARES is accepted on the Render project (expected, same request); the Deepgram settings
are kept as a comment in `.env.example`. Not a contract change (AGENTS 6 does not cover vendor settings).
