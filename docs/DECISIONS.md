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
**Update 2026-11-21:** pt-PT was chosen because "ARES has no Brazilian Portuguese", which was never really tested.
The earlier `en-US,pt-BR` attempt also sent `credential_mode: managed`, and that caused the 400. A live probe
without `credential_mode` and with 24 keywords was ACCEPTED (HTTP 200) for both `en-US,pt-BR` and `pt-BR,en-US`.
Recognition quality is still unmeasured, and the default stays `en-US,pt-PT` until the ARES arm of
`docs/LATENCY_TEST_PLAN.md` passes.

## D-23: Mochi's character lives in the backend; a device channel for its body (2026-11-20)

The hardware owner's stand-in agent (personality, face moods, volume by voice, temperature, learning voices)
answered every sentence, which breaks "quiet by default". Its character is now part of the one agent the
backend runs, and only speaks when Mochi is spoken to.

**Behaviour (intelligence).** Unchanged without `MODEL_API_KEY`. With it:
- A sentence with the wake phrase is answered by a model in character (`intelligence/character.md`, the
  stand-in's prompt), also when no word is asked ("Mochi, speak louder"). When the rules found a word, the hint
  is shown as before and the model is told to teach exactly that word; if the model fails or takes longer than
  `MOCHI_CHARACTER_TIMEOUT_SECONDS`, the fixed line is spoken.
- For `MOCHI_FOLLOW_UP_SECONDS` after Mochi spoke, the next sentence is also given to the model, so a person can
  answer Mochi without saying its name. The model replies `[quiet]` when the sentence was not for it, and the
  normal rules then run. Never during a game round.
- The turn timeout grows by the character timeout (`Settings.turn_timeout_seconds`); the hint model keeps its own.

**Contract proposals (AGENTS 6.4), all additive:**
- `GET /api/devices/home_pi_01/state` gains `commands: [{command_id, kind, value}]`: what Mochi wrote in square
  brackets (`mood`, `show`, `volume`, `temp`, `enroll`, `forget`), stripped from the spoken text, plus `show`
  for a hint's word. The device does each `command_id` once. The list is cleared when a session starts or stops.
- `POST /api/devices/home_pi_01/status {volume, temperature, voices, speaker}`: the device reports itself; it
  goes into the model's prompt. `POST /api/devices/home_pi_01/voices {name, language, learned}`: a voice was
  learned (or not); Mochi says so through Agora's speak endpoint.
- `POST /api/sessions/demo/start` takes an optional `{"woken_by": "<wake phrase>"}`: Mochi greets in that
  language (`llm.greeting_message`) and the next sentence is for it. Without a body nothing changes.
- `IntelligencePort` gains `called()` and `device_status(...)`.

**Verified in live sessions with synthetic speech (`VERIFIED.md`):** silence when nobody calls Mochi, the
greeting, in-character replies with a real model, and `mood` / `volume` / `temp` commands reaching the device.
A sentence with Mochi's name but no greeting ("Oi Mochi" is often heard as "Wait, Mochi.") is also given to the
model, which may answer `[quiet]`. **Not verified:** a person at the microphone; whether the device hears its own
voice as a new turn; the first sound comes 3.3 to 4.2 s after the person stops (the reply is not streamed).
**Not done:**
who is speaking is only told to the model, not used for "whose word is it" (AGENTS 7.3, a `Turn` has no speaker).
The prompt exists twice (here and in `hardware/pi-bridge/config/mochi.toml` for the Pi's stand-in mode).

## D-24: what the first spoken conversation changed in Mochi's character (2026-11-20)

One person talked with Mochi for five minutes. Three things were wrong and came from the prompt, not the code:
it sent the person to "Ana" and "Ben" who were not there, it answered English questions in Portuguese (copying a
Portuguese example), and it put Portuguese words inside English sentences, which the voice reads with an
English accent.
- The prompt no longer names anyone or assumes a second person, and its examples give the turn back to the
  speaker. Names come only from what was said or from a recognised voice.
- The backend tells the model the language of each sentence (`language_guess.spoken_language`; unclear ones
  follow the last sentence answered) and asks for the reply in that language, with a taught word as a sentence
  of its own. An example word in that note gets repeated by the model, so the note has none.
- `IntelligencePort.called()` became `session_started(woken)`: in a session the device was woken for, a sentence
  without Mochi's name is most likely still for it; in one the operator started, Mochi leans to `[quiet]`.
  Fillers and unfinished starts get `[quiet]` in both.
- Speed: the hint model and Mochi's reply are asked at the same time when both are needed, and
  `HttpxClient` keeps its connection open between sentences.
The same prompt changes went into the Pi's stand-in (`hardware/pi-bridge/config/mochi.toml`).
**Still imperfect** (seen in replays with the real model): an occasional word of the other language inside a
sentence, and the hint model inventing hints in a talk with Mochi ("hamburger", reason `asks_partner`).

## D-25: ears and reply model chosen from measurements (2026-11-20)

The hardware owner compared recognisers on 16 synthetic sentences with one word of the other language
(`~/.cache/mochi-wake-eval/cs` on the Pi) and chose:
- **Ears, first choice: OpenAI `gpt-4o-transcribe`** through Agora (`asr.vendor: openai`), main language `en`, with
  a prompt saying the speakers mix both languages plus the lexicon's words. **Fallback: ARES** with the same words
  as `keywords`. ARES is used when there is no `MODEL_API_KEY`, and `SessionService` retries with it when Agora
  refuses the first request (`AgoraRejectedError`, a 4xx). A timeout is not retried (the first agent may be
  running). Not covered: OpenAI failing during a session; Mochi is then deaf until `MOCHI_ASR_VENDOR=ares`.
- **Replies: `gpt-5.4-mini`** with `reasoning_effort: none` (median 0.7 s against 1.0 s for `gpt-4.1-mini` on the
  same sentences). The request now sends `max_completion_tokens`; a failed model call is logged
  (`character_model_failed`). `gpt-5-mini` needs a verified OpenAI organisation.
- **Voice: MiniMax stays.** `gpt-4o-mini-tts` did not pronounce embedded words better (table in `VERIFIED.md`).

Numbers (`VERIFIED.md` has the tables): mixed-in word kept in 13/16 with `gpt-4o-transcribe` through Agora, 10/16
with ARES + keywords, 7/16 with ARES and only "Mochi". The price is delay: a sentence reaches the backend 1.5 s
after speech ends with `gpt-4o-transcribe`, 1.1 s with ARES (both include the 0.6 s end-of-speech wait).
`gpt-transcribe` and `gpt-live-transcribe` scored lower: they tidy the mixed-in word into the sentence's language.
`gpt-4o-transcribe` is deprecated by OpenAI (shutdown 2027-02-26).
The model key is sent to Agora in the start request. Not a contract change.

## D-26: goodbye ends the session; a woken Mochi keeps listening; echoed prompts are removed (2026-11-20)

From a second spoken conversation:
- The person said "I need to go, tchau tchau!", Mochi said goodbye, and the session stayed open (only the
  device's offline phrase "tchau mochi" ended one). New silent command `[bye]`: Mochi writes it when someone
  says goodbye to it or tells it to sleep, and the device ends the session once the goodbye has been heard
  (8 s at most). Added to `commands` in the device state (D-23); no other contract change.
- A minute later "Are you still there?" got silence: the follow-up window had passed. In a session the device
  was woken for, every sentence is now given to Mochi (which may still answer `[quiet]`). In a session the
  operator started, the window stays as it was.
- OpenAI transcription pasted its prompt's word list into a transcript; see `VERIFIED.md` and
  `gateway/prompt_echo.py`.

## D-27: the main promise end to end: just listen, silent hints for any word (2026-11-20)

Asked for by the hardware owner; it changes intelligence code (Kauê's), so it is recorded here.
- **Detection.** With perfect hearing the rules found the right hint in 6 of 16 mixed sentences: a word outside
  the 20-word lexicon has no mark they can see. While two people talk and Mochi only watches, the hint model now
  judges every sentence of three words or more (`IntelligenceSettings.judge_every_sentence`), with instructions
  that the hint is the word the person needed; a reply that returns the word they said is swapped or dropped
  (`_needed_word`). Result: 16 of 16, no hint on 12 ordinary sentences (names, grammar slips, serious talk).
  `scripts/eval-intelligence.sh`: 68/75 before, 82/85 now with ten new `beyond_lexicon` fixtures; the three
  failures are the false friends that failed before. Adding false-friend examples to the instructions fixed two
  and caused two wrong hints, so it was taken out again: silence matters more.
  Cost: one model call per sentence in that mode. Hints stay limited to words, never grammar (AGENTS 7.2).
- **Getting there from the wake phrase.** Someone who woke Mochi has its attention. `[listen]` (written by Mochi
  when it is asked to just listen, or told that people will talk to each other) makes it only watch; its name
  still gets an answer; `[chat]` brings it back. Both are read in `MochiTalk`, not sent to the device.
- **Live** (real Agora, real models, spoken clips): woken, told to just listen, then "Can you pass me the garfo,
  please?" gave silence and `show fork` on the device; two ordinary sentences gave nothing; "Eu esqueci minha
  wallet em casa." gave `show carteira`; "Hey Mochi, how do you say fila in English?" was answered aloud.
- **Not built:** escalation when a hint is not enough (to be agreed with the team); using the device's speaker
  recognition to choose whose hint it is.

## D-28: fixes from the first spoken test of the quiet hints (2026-11-20)

One person tried the mode from D-27 by voice; the log was read back and the sentences replayed.
- **Asked word.** "...adiar our meeting. How do I say garfo in English?" gave "postpone": the rules took any
  lexicon word in the turn. `clear_cases.asked_term` finds what the question names; the rules search only that,
  the hint model gets it as `asked_about`, and a language the question names (`wanted_language`) is the hint's
  language and decides whose hint it is.
- **Stale memory.** `SessionService._begin` clears `turns` and `hints`: a hint from an earlier session had put
  the new session's first sentence under the cooldown.
- **Cooldown.** Unchanged for unasked hints (AGENTS 7.2). A turn that asks how to say something is exempt.
  **Open, for the team:** two turns is about 20 seconds of real talk, and it still silenced a second, different
  word ("...eu esqueci minha wallet em casa." two turns after another hint). Proposal: hold a new hint back only
  while the previous one is still on screen.
- **"I mean"** at the start of a turn is not a self-correction (`quiet_rules._SELF_CORRECTION`).
- **Split questions.** "Como se fala..." and "Carteira em inglês." arrive as two turns because of the pause; a
  turn that follows an unfinished question within 20 s is read together with it (`_with_its_question`). The hint
  model is told not to guess a word nobody mentioned.
- **Hint card.** The device's `commands` carry a hint as `hint` with a JSON card (`word`, `language`, `meaning`,
  `example`) instead of `show` with the bare word; Mochi's face shows the language and meaning under the word.
- The decision log line now names the hint and its meaning.
`scripts/eval-intelligence.sh` is unchanged at 82/85.

## D-29: the hint judge, second pass: measured on what was really heard (2026-11-20)

Yardstick: 72 sentences as the recognisers actually wrote them (gpt-4o-transcribe and ARES, including
the mangled ones), sentences from a real conversation on the Pi, and 26 sentences written afterwards
and never used for tuning. Each has the hint it should or should not produce.

| | before (D-28) | now |
|---|---|---|
| the first 46 sentences | 38 right, 7 wrong hints, 1 missed | 43 right, 1 to 2 wrong hints, 1 to 2 missed (all mangled words) |
| the 26 new sentences | not measured | 26 right |
| answer time, median | 0.84 s (gpt-4.1-mini) | 0.68 s (gpt-5.4-mini, `reasoning_effort: none`) |
| `scripts/eval-intelligence.sh` | 82/85 | 92/95 (ten rows added; the three false friends still fail) |

Live, real Agora and gpt-4o-transcribe, spoken test clips: the hint reached the device 1.2 s and 2.1 s
after the sentence ended; Mochi stayed silent.

What changed, all in `intelligence/`:
- **Instructions** (`openai_hint_model.SYSTEM_PROMPT`): who the two people are, each reason spelled out, a
  list of what is never a hint (greetings and exclamations in the other language, names, a word being
  tried out, grammar), how a transcript mangles foreign words, and "when in doubt, IGNORE". The example is
  the person's own sentence said right (a recast), not a dictionary sentence. IGNORE is answered as
  `{"decision": "IGNORE"}`, which is most answers and a third of the tokens.
- **Checks on the answer** (`decision_flow._accepted`): the model reports `confidence`, and the language of
  both words. No hint when it is unsure (`hint_min_confidence`), when the hint is not in the language being
  practised, when a "code switch" is a word of the same language (a synonym), when the word they "said" is
  not in the sentence, when the hint only extends the word they said, or when the whole turn is just the
  word itself (someone trying it out). A false friend the rules did not spot first (`look_alike` from the
  model alone) is dropped: it was the label the model put on its wildest guesses.
- **Language of a sentence** (`language_guess`): more common words on both sides, "um" is no longer
  Portuguese (English speech is full of it), and a capital at the start of a sentence is not a name.
- **Questions**: "Limpar em inglês?" counts as asking (`_short_ask`), but only when the word is not already
  in the language named: "Can we talk in English?" asks for nothing. The model is sent only the sentence
  that asks (`question_itself`). `asks_partner` needs a name; otherwise the reason is `says_unknown`.
- **Model**: `MOCHI_MODEL_REASONING_EFFORT` (`OpenAiHintModel.thinking`). Compared on the yardstick:
  gpt-4.1-mini 1.05 s, gpt-4.1 0.86 s, gpt-5.4 1.15 s, gpt-5.4-mini 0.68 s at the same accuracy; gpt-5.4-nano
  misses a third of the mixed sentences. The code default is unchanged; this Pi runs gpt-5.4-mini.
- **Slow answers** (`hedged.first_answer`): when the first request has not answered after 1 s a second one
  is sent and the first answer wins; the 2 s limit of AGENTS 7.2 stays. Two answers in a row hit the limit
  in one run, which cost two hints.
- **Cooldown, optional** (`MOCHI_HINT_COOLDOWN=while_shown`): an unasked hint waits only until the earlier
  one has left the screen, and the same word is never shown twice in a row. The default is still the
  team's two turns; this Pi runs `while_shown`. **For the team to decide.**
- **"You used it"**: when a card goes to `ASSISTED` the device gets a `used` command (`{"word", "language"}`)
  and Mochi's face shows the word with a star for five seconds, without a sound.
- The device reads its state every 0.15 s (was 0.3 s).

**After an independent review of the first version** (same day), with a test for each:
- "Limpar em inglês?" counts as a question only for a bare word or a short name of a thing. "Was the meeting
  in Portuguese?" and "A reunião foi em inglês?" had shown a hint, and skipped the cooldown doing so.
- A question that names no language ("Como se diz saudade?") is asked in one language for a word of the
  other: there the model's own label decides the hint's language (`CaseMatch.language`) instead of being
  held against it. Labels are read loosely ("EN", "en-US", "English").
- "I forgot the word for chave." names its word, so the next turn is no longer read as its second half.
  "How do you say that?" names nothing, so the whole turn goes to the model.
- A round, a serious talk, thinking aloud and names keep Mochi quiet also when the cooldown does not
  (`lasting_quiet_reason`); the cooldown is one separate decision (`_held_back`). `while_shown` now really
  waits for the screen, and "the same word twice" looks only at the last two turns.
- "um" is Portuguese again, except before a pause ("Um, good question"); only small sentence-building
  words count for the language of a sentence, not nouns, which are what people borrow.
- The word a code switch names may be in another form ("garfos", "adiei"). The instructions no longer ask
  the model to reconstruct mangled words: such a guess was dropped by this check anyway.
- An error in the model adapter is raised again (it reaches the log as `decide_failed`); a wrong field in
  the model's JSON (a list as reason, 95 as confidence) no longer costs the answer.
- The cheer is for a word shown in this session, and not next to a new hint.
Not changed: a card saved in an earlier session can still go to `ASSISTED` on a later session's first
turns (`learning_rules`, as before); it is only no longer cheered.

Still wrong: a word the recogniser turned into a non-word ("postone", "guardy shoe") is sometimes guessed
at. A word list for both languages would settle it (is the "said" word a word at all?), which means adding
data files; not done. False friends (case 8) are unchanged at 0 of 3 beyond the lexicon.

## D-30: asked how a word sounds, Mochi says it (2026-11-20)

Seen in a conversation on the Pi: the hint "cortar o cabelo" was shown, then "você pode pronunciar para
mim?" got silence, three times. A word on a screen does not tell how it sounds.
- **Rule** (`intelligence/aloud.py`, `DecisionFlow._said_aloud`): a turn that asks about the sound of a word
  ("pronounce", "pronúncia", "say it for me", "fala pra mim", "em voz alta") makes Mochi say the hint shown
  last (at most two minutes after it left the screen) and show it again. A word in quotes is said as it
  is, unless it is what that hint stands for. A turn that both needs a word and asks for its sound gets
  the hint and the sound.
- **What it says:** only the word, twice ("cortar o cabelo. cortar o cabelo."), with no model call: nothing
  else for the voice to mispronounce, and no wait.
- **This is the one time Mochi speaks without its name**, which goes beyond AGENTS 7.1 case 4. Kept narrow:
  not "say that again" (people say that to each other), not when the partner is asked by name, not during
  a round, and not while Mochi is part of the talk (it answers in its own words then). **For the team.**
From the same conversation:
- "How do you say feijoada in English?" was asked four times and got nothing: the dish rule
  (`deliberate_switch`) silenced it. A question is not a dish dropped in on purpose; the model is told to
  answer with a short description when there is no word ("black bean stew"). "How to say ..." counts as
  asking, and "how do you say feijoada in" (cut off before the language) names "feijoada".
- "The reunião will atrasar." got nothing: its two borrowed words made it count as Portuguese. The small
  words of a sentence decide its language now; lexicon words only break a tie (`language_guess._evidence`).
- The answer checks moved to `intelligence/answer_checks.py` (file size rule).
Not changed, seen in the same log: "I need to adiar a reunião." five seconds after another hint got
nothing, because that hint was still on the screen (`while_shown`).

## D-31: up to three candidate words, for Mochi AR (2026-11-21)

Asked for by the team: when the speaker named no single word (reasons trails_off, restarts,
talks_around; AGENTS 7.1 cases 5-6), give up to three plausible completions instead of one guess,
so `apps/glasses` (Mochi AR, PR #3) can show real choices instead of its own mock backend's two
scripted words. Every other reason keeps one known word — code_switch, says_unknown, asks_partner
and asks_mochi already know which word is needed, so a second or third guess would be invented,
not found.

**Contract PROPOSAL, additive and optional (needs Matheus's sign-off):** `Hint` gains
`candidates: [{expression, meaning}] | None` (the primary word repeated as the first entry, so a
client that reads `candidates` never also needs the top-level `expression`) and
`context: string | None` (the sentence the speaker stopped in). Both `None` for every other
reason, so a client that does not know them (today's Mobile and Home views) is unaffected.
`packages/contracts/schema` regenerated (`make contracts-schema`); the three examples that embed
a `Hint` updated to the now-explicit `null`s. This is exactly the shape `apps/glasses/README.md`
already proposed and tests against — no change needed on the glasses side.

**Intelligence** (`model_port.CandidateSuggestion`, `openai_hint_model.SYSTEM_PROMPT`,
`decision_flow._extra_candidates`): the model is asked for `candidates` only for the three open
reasons; a malformed entry (not an object, no string `expression`) is dropped, never costing the
primary hint (same defensiveness as the rest of `_suggestion`). Candidates are deduplicated
against the primary and each other and capped at three. The lexicon-only path (the curated
10-word list) still returns one word: there is no second translation for "umbrella" to offer.
Fixtures: `trails_off-67`, `restarts-68`, `talks_around-69` (beyond the lexicon, scripted model).

**Not done:** anything in `gateway/` — none is needed, since the gateway already forwards the
whole `Hint` payload unchanged (`LiveHint.show`). `&surface=ar` itself arrived separately on `main`
(AGENTS 6.6, `gateway/connections.py`): the glasses get session state and that user's hints only. **Not verified:** a real multi-word
suggestion reaching real Rokid Glasses (only the two-word, one-hesitation mock backend has run on
the hardware so far, per PR #3).

## D-32: durable storage in Postgres (2026-11-21)

Words were lost on every deploy, restart and (on Render's free plan) every idle spin-down. Luís now owns
storage and chose Render Postgres (free plan). **Proposal for the team** (AGENTS 8 listed a database as out of
scope; Kauê's `memory_store.py` and Matheus's contracts are touched, additively).
- **Stored:** `users` (seeded with ana and ben from `gateway/roster.py`, never overwritten), `learning_events`
  (the whole `LearningEvent` as `jsonb`, plus id, user, word and state columns; first-saved order kept) and
  `voices` (name, user, language and the voiceprint vector). **Not stored:** turns and transcripts (privacy),
  session, game, live hint, device commands, tokens (all re-derived or short-lived), `agent_id`.
- **Shape:** `storage/` holds a `Storage` port, `PostgresStorage` (psycopg 3, one short connection per call,
  `CREATE TABLE IF NOT EXISTS`, no migration tool) and `WriteBehindStorage`. Reads happen once at startup and
  are served from memory; writes go to one worker thread, so a slow or broken database never delays a turn.
  A failed write is logged (`storage_write_failed`, no values) and dropped.
- **Intelligence stays socket-free:** `MemoryStore` takes the restored events and an `EventSink` protocol;
  `composition.py` connects it to storage (`Intelligence.keep_words_in`).
- **No `DATABASE_URL`, or the database does not answer at startup:** memory only, as before, with
  `storage_memory_only` / `storage_unavailable` logged. `/readyz` shows `storage: postgres|memory`.
- **Voiceprints are biometric.** Only device-key routes read or write them (`GET /api/devices/home_pi_01/voices`,
  `PUT .../voices/{name}/voiceprint`, `DELETE .../voices/{name}`); they never appear in an event, a log line or
  a non-device response. The Pi keeps its own copy. Mochi's written `[forget NAME]` (`turn_pipeline`) also
  deletes the server copy; **a forget that starts on the Pi itself still needs the Pi to call DELETE** (not
  done: hardware is out of this change). `POST .../voices` with
  `learned: true` links the name to a user; `learned: false` stores nothing.
- **Reset** (`/api/demo/reset`) clears learning events only; users and voices survive.
- **Speaker-based word ownership is not changed** (AGENTS 7.3): the Pi's `speaker` is not used yet.
- **Free Render Postgres expires 30 days after creation** (created 2026-11-21, expires ~2026-12-21, deleted
  ~14 days later): upgrade it to a paid plan before then. After expiry Mochi starts from memory and logs
  `storage_unavailable`.
- **Contracts (additive):** `User`, `VoiceProfile`, `VoiceprintUpload` with examples and schema.
- Test helper `make_harness` takes one more switch (`storage`), hence a `noqa: PLR0913` on it.

## D-33: the clients use the stored data; local file storage for fake mode; failures are visible (2026-11-21)

Follow-up to D-32 after a review of the Pi, the web apps and the failure modes. Luís asked that the Pi and the
apps really use what the database holds. **Touches `hardware/pi-bridge` (Matheus) at his owner's request.**
- **Phones get their words back.** The `?user=` WebSocket snapshot now also sends that person's saved words as
  `learning_event.created` (oldest first), through the same delivery rules (nobody else's, never to the
  projector, the Home view or glasses). No new event type; the web store upserts by `learning_event_id`.
- **The Pi uses the stored voices.** After learning a voice it `PUT`s the vector (order: `POST .../voices`, then
  `PUT`). At each session start (the backend is awake by then) it runs `sync_voices`: voices the backend has with a
  vector and the Pi lacks are added on the listener thread (`Voices.merge`, a command like `enroll`); voices the
  Pi has and the backend lacks are sent. **Union only: nothing is ever deleted by a sync**, so an empty or
  memory-only backend cannot wipe `voices.json`. Known gap: a `[forget NAME]` command the Pi missed (it expires
  after 30 s) can be undone by the next sync.
- **Local file storage (fake mode only).** `MOCHI_LOCAL_DATA=<file>` keeps users, words and voices in one JSON
  file (`storage/local_file.py`, written atomically, mode 0600 because it holds voiceprints) when `DATABASE_URL`
  is empty. `DATABASE_URL` wins. **Refused in real mode** (a container's disk is wiped on each deploy).
  Off by default, so tests write no files; `scripts/start-dev.sh` turns it on (`.local/`, git-ignored).
  `/readyz` then shows `storage: local_file`.
- **Failures are visible and healed.** A failed write is kept (newest per record) and retried before the next
  write, in order; a write that comes after a failed one waits behind it without trying (one timeout per write at
  most). A reset drops the older waiting word saves and goes to the end, so a retry cannot undo a later delete or reset. `/readyz` has `storage_unsaved`
  (writes waiting); `ready` is **not** changed, because the memory fallback is meant to look healthy to
  `smoke.sh` and `deploy.sh`. Startup tries the database 3 times, 2 s apart, and every statement has a 10 s
  timeout. A database still down after that means memory only until the next restart (logged
  `storage_unavailable` per attempt and `storage_fallback`).
- **Validation:** a voice name needs at least one letter; `VoiceprintUpload.saved` is at most 64 characters
  (contract change, schema regenerated).
- **Reset** still keeps users and voices (so a reset does not make Mochi forget who is who).

## D-34: the Pi tells who is talking, and which language it was called in, in time (2026-11-21)

Two things seen on the Pi. "Oi Mochi" was answered in English; and Mochi showed a learned name on its
screen while saying it did not recognise the voice.
- **Greeting language** (`mochi_device/phrases.py`): the phone recogniser writes a Brazilian "oi" as "uei"
  or "uai", the sounds of "hey" and "hi" behind a rounded vowel. On the test clips 48% of the Portuguese
  greetings that woke Mochi were reported as an English phrase. "oi" and "olá" now have those
  pronunciations, and an h-less "hey"/"hi" right after "u"/"o" costs what a glued consonant costs: 10%
  wrong (most of the rest are English voices reading "Oy"), English unchanged at 1%, the same detection
  and false-wake numbers as before.
- **Who is talking** (`mochi_device/speakers.py`, `main.py`, `backends.py`): every new sentence began as
  "unknown", and so did every moment Mochi's own voice reached the microphone. The name came back 0.8 s
  into a sentence at the earliest and otherwise at the pause, which the Pi notices 0.2 to 0.4 s late
  (measured), while Agora starts the reply after 0.48 s: the agent answered with the old "unknown". Now the
  speaker stays until someone else is recognised or a stranger has spoken for 1.5 s; whoever says the wake
  phrase is recognised from it; guesses repeat at 0.8, 1.5 and 2.5 s; updates to the stand-in agent go out
  one at a time; the backend is told on the next poll, not within a second; a report that failed is sent
  again; forgetting a voice is reported at once; and the scores are logged. The price, accepted: a few
  words from someone unknown, or an answer that follows within a second, keep the last name.
  The model itself is fine: with one known voice and room noise, 1.5 s of speech is never missed at 0.35
  and a stranger passes 3.5% of the time (30 speakers of the test corpus).

## D-35: sentences nobody said: Mochi's own voice and a recogniser primed with the lexicon (2026-11-21)

Seen in the first conversation of two people with the three modes (Mateus and Tasnim): Mochi taught
"postpone" and "key" several times although nobody had said "adiar" or "chave". The backend log has them
as the first sentence of a turn, right after Mochi spoke: "Where is my chave?" arrived 4.6 s after the
session started, while the greeting was still playing; "I need to adiar the meeting. Posso praticar com
você?" had only its second sentence said by a person.
- **Two causes together.** The recogniser (`gpt-4o-transcribe`) is given the lexicon as "words that may
  come up" (`composition.vocabulary`), and it writes unclear audio as those words. And unclear audio is
  what it gets while Mochi speaks: a clip played on the M1A comes back in its own microphone (loudness
  envelope match 0.59 at the expected delay, 0.29 at the 95th percentile elsewhere), at about the level of
  the room.
- **Built (Pi, `hardware/pi-bridge`):** while Mochi's voice is playing, and for 0.6 s after, silence is sent
  on instead of the microphone (`[audio] hear_while_speaking = false`, the default). The price: Mochi
  cannot be interrupted by talking over it; "tchau Mochi" is still heard, on the Pi itself.
- **Not solved, for Luís and Kauê:** background speech does the same. In a noisy room, with nobody talking
  to Mochi, the recogniser produced "My chave atrasar." and the lexicon rule answered with "key". Options:
  give the recogniser only "Mochi" (and measure what that costs "adiar" and "guarda-chuva", AGENTS 12.2,
  with the code-switch clips of the test kit), or have a lexicon word in an otherwise odd sentence
  confirmed by the hint model before it is shown.
- **Also from that conversation:** "eu perguntei explicitamente como se pronuncia", said to the partner,
  made Mochi say the last hint aloud; telling someone that one asked no longer counts as asking
  (`intelligence/aloud.py`). In listen mode "Como você diz coffee?" shows the word and says nothing, as
  designed (D-30); the two people expected to hear it. **For the team:** say the word once when someone
  asks outright, and keep unasked hints silent?

## D-36: the recogniser is no longer told the lexicon's words on the deployed backend (2026-11-21)

D-35 left open that background speech is written down as the lexicon's words. It happened again in the
first spoken test through the deployed backend: two seconds after "Can I practice English with you?" the
log has "I forgot my guarda-chuva." and "Meeting"; the Pi scored the voice of those seconds as unknown
(0.12 to 0.17, the speaker's own 0.4 to 0.6). Mochi taught "umbrella" on top of its own answer and the
word was saved for Ana.
- **Measured** on the Pi's backend (real Agora, `gpt-4o-transcribe`, one run each; 16 mixed-language
  sentences, and 10 real recordings made faint and distant as background):

  | | lexicon named (as before) | only "Mochi" |
  |---|---|---|
  | faint background written as a lexicon sentence, with a hint | 1 of 10 ("People don't like to adiar reuniões, but sometimes it's necessary." -> postpone) | 0 of 10 |
  | adiar, guarda-chuva, garfo, feira, presente, geladeira, umbrella, wallet, traffic jam, obrigado | all written down | all written down |
  | "postpone" in a Portuguese sentence | "postpone" | "postone" (hint "poste") |
  | "supermarket", "salt" in a Portuguese sentence | kept | translated ("supermercado", "sal") |

- **Built:** `MOCHI_ASR_LEXICON_WORDS` (default true: nothing changes for anyone who does not set it).
  Set to false on the deployed backend (`render.yaml`) and on the Pi's own. **For Luís and Kauê:** make
  false the default? The cost seen is English words inside Portuguese sentences.
- **Not solved by this:** background speech that is clear enough is still written down as what it is
  (4 of the 10 faint recordings became sentences either way) and, while someone practises alone with
  Mochi, answered. Telling it apart needs who is speaking for each sentence; the Pi's verdict came 2 to
  4 seconds after those sentences, and the speaker's own first second often scores as low as a
  stranger's. Not built.
- **Also:** Agora ended the agent by itself 99 seconds into that session (no reason given, the backend
  had not asked); the Pi now ends the session when the agent leaves instead of staying awake.


## D-37: latency levers, each behind its own flag (2026-11-21)

Asked for as "D-32"; that number (and D-33 to D-36) was already taken, so this is D-37. Measured
before (Agora Turns data): a spoken reply takes about 3.0-3.2 s at the median: `asr_ttlw` ~1.17 s,
our `llm_ttft` ~1.3-1.6 s (decide() ~1.08 s median, ~0.2 s transit, plus lock queueing), `tts_ttfb`
~0.32 s; `llm_ftfs` of 3-9 ms shows the reply leaves in one chunk. **Every default below is the
behaviour before the lever existed**, so merging changes nothing; the test arms set the flags.

| Flag (default) | What it does | Expected saving (confidence) |
|---|---|---|
| `model_usage` log line (always on) | One line per model call that answered: `model`, `kind` (`hint`/`character`), `prompt_tokens`, `completion_tokens`, `cached_tokens` (0 when absent), `latency_ms`. Never text. | none; it prices the other levers |
| `MOCHI_CANCEL_STALE_TURNS` (false) | A newer Agora request cancels the decide() and model calls of an older one still deciding; one still waiting for the lock is skipped; with the flag the route also watches the ASGI `http.disconnect` and cancels on hang-up. Only deciding is cancelled (nothing is applied or published before the commit); the cancelled turn answers empty, and `last_heard` is restored so the newer request's cumulative text covers it. A turn that has already said words is never cancelled. Log: `turn_dropped_stale` (`why`: superseded / disconnected). | p95 only, 0.4-1.0 s (golden turn 4 waited ~400 ms behind abandoned turns) |
| `MOCHI_CHARACTER_HEDGE_SECONDS` (0 = off) | After that long without an answer, Mochi's reply request is sent a second time (`intelligence/hedged.first_answer`, as the hint model does); first answer wins, the other is cancelled. Log: `character_hedge_used`. **Costs more:** every call slower than the value is paid twice. Not applied to the streamed path. | p95 ~0.5-1.0 s |
| `MOCHI_STREAM_REPLY` (false) | Mochi's free-chat line (wake phrase, no lexicon or asked-for word, no round) goes to Agora in several SSE deltas as the model writes it; every other turn is one chunk as before. | 0.15-0.3 s likely (one estimate says up to 0.4-1 s) |

How the stream stays safe (`gateway/spoken_release.py`, `intelligence/streamed_line.py`):
- The turn runs in a task the pipeline owns (holding the turn lock as before); the route only reads
  pieces from a queue, so Agora hanging up never cuts a commit in half.
- Nothing inside an unfinished `[` is released and every bracket is removed with `split_commands`,
  so commands never reach the voice; the first piece waits for `. , ? !` or six words.
- `[quiet]` anywhere stops passing text on (the line is then not remembered); `[play]` holds the
  rest, and the commit says it after `_with_round` and the secret check (the prompt puts `[play]`
  first, so in practice nothing streams). A Stop, Reset or round starting ends the release.
- `[listen]`/`[chat]`, `_remember`, learning events, device commands, `agent.speak.requested` and the
  `reply` log run on the full text at the commit, exactly as before; the commit's reply minus what
  was already said is sent last. A mid-stream failure ends with stop + `[DONE]`, never another line.
- Off with `MOCHI_SILENCE_STRATEGY=mute_speaker` (the speaker is unmuted only at the commit).
- The model is asked with `stream: true` and `stream_options.include_usage` (for `model_usage`).
- Reading the numbers: with streaming on, `decision.latency_ms` and `arrived_to_decided_ms` cover
  the whole streamed line, so they grow; the gain shows in `reply_first_byte` and Agora's `llm_ttft`.

**Proposal (contract-adjacent, internal):** `gateway/intelligence_port.py` gains `StreamingDecider`
(`decide_streaming(turn, context, sink)`, returning the same `Decision`), implemented by
`Intelligence`; the sink type is `platform/text_sink.TextSink`. AGENTS 6.5 and `packages/contracts`
are unchanged.

**Not covered / open for a human:**
- After "Oi Mochi" wakes it, most later sentences go through `_watching`/`_follow_up`, not
  `_answer_mochi`; as specified, only wake-phrase turns stream. Extending it to follow-ups is a
  small change in `decision_flow._follow_up` if the arm shows a gain.
- Not verified with Agora: that it speaks several content deltas as one reply (the custom-LLM page
  describes OpenAI SSE chunks, VERIFIED.md), and that it closes the connection of a request it
  abandons (if it does not, only the newer-request path cancels).
- If `[play]` were written after words (against the prompt), words said before it cannot be
  unsaid when the drawn word happens to be among them.
- A cancelled or timed-out decide can leave Mochi's own talk history updated (as the existing
  timeout already can).
- `HttpxClient.post_lines` is not covered by a test (it needs a network or an injected transport).

## D-38: practising alone with Mochi: an answer is no longer thrown away, and Mochi is a partner first (2026-11-21)

In the first spoken practice session Mochi's voice kept breaking off: three answers went out in three
seconds. Measured on the Pi's backend (real Agora, a question and 0.9 s later a sentence by another voice):
- **Agora's default drops the answer under way** when another sentence follows: only the answer to the
  second sentence was spoken, so the person's question got none. Staying silent on the second sentence
  (tried, and removed) left no answer at all in 2 of 3 runs.
- **`MOCHI_INTERRUPTION=append`** (`interruption.enable` false, `disabled_config.strategy` "append" in the
  join body; default "" = Agora's default): both answers were spoken in full, in order. Set on the Pi's
  backend; **not yet on the deployed one**. "ignore" would discard speech while Mochi thinks, which loses
  quick replies between two people, so it is not used.
- **`character.md`, practising with Mochi:** asking to practise is the choice (no list of the three things
  again); react and ask one question; talk at the person's level; a challenge to use a word only right after
  giving it; no praise for ordinary sentences; a goodbye that names one thing from the talk. Compared with
  the real model on three scripted conversations.
- **`append` while two people talk** (Mochi only watching, empty replies), two runs: every sentence was
  heard and decided, nothing was spoken, nothing was lost. `render.yaml` and `.env.example` now carry it.
- **The goodbye names a word.** The history holds four exchanges, so a goodbye after a longer talk had
  forgotten the word. `MochiTalk` keeps the last three words Mochi handed over in the session (the word it
  was told to teach, or one it wrote in `[show]`), `CharacterRequest.given` carries them, and a note next
  to the sentence offers them for a goodbye only. Real model, 3 of 3: "Bye! You used postpone well today.";
  no mention of the word in the turns between. When Mochi taught a word without `[show]`, nothing is kept.
  While a round is on the words are withheld: the round's secret is the newest word Mochi taught.
- **Not solved:** a voice in the room is still answered when its sentence is clear, and when it follows
  within the end-of-speech pause Agora joins it to the person's own sentence. That needs who is speaking.

## D-39: the revised product vision in code: Mochi asks what to do, and Play works by voice on Mochi's own screen (2026-11-21)

(This entry was D-31 on the `hardware` branch and went missing from `main` when the entry for the AR candidates, also numbered D-31, was merged. It is restored here unchanged under a new number; the code it describes has been on `main` since PR #12.)

`vision/Mochi_Product_Vision.md` (revised 2026-11-20): after its name Mochi asks "What would you like to
do today?" and the person picks, in ordinary words, Practice with Mochi, Practice with a Partner, or Play
(Describe & Guess). Practice and Partner already existed as `attentive` and `[listen]` (D-26, D-27). Built
on the `hardware` branch at Suhuai's request, in all three owners' directories; **for the team to accept
or change.**
- **Greeting** (`settings.py`): "Hi! What would you like to do today?" / "Oi! O que você quer fazer hoje?",
  in the language of the wake phrase as before. `character.md` tells Mochi it asked that, so a one-word
  answer ("Play.") is for it, and what the three things are. Secret Missions and the Fluency Helper are
  named only as needing the watch and the glasses.
- **The language Mochi was called in is the tie-breaker** for an answer that could be either language
  (`session_started(woken, language)`, an optional second argument on the intelligence port). Seen with the
  real model: "Play." after "hi Mochi" was answered in Portuguese, the last session's language.
- **`[play]`**, a silent command like `[listen]` (it rides in `Speak.text`; not a contract value): the turn
  that carries it starts a round inside its own commit (`TurnPipeline._with_round` ->
  `ActivityService.start_in_turn`), and the host's line follows Mochi's in the same reply ("Yay, let's
  play! Ben describes. Ana guesses!"). Starting it afterwards through `/speak` would cut Mochi's own
  sentence off (`priority: INTERRUPT`). Once playing, Mochi is out of the talk as after `[listen]`.
- **The round on the device**: a command of kind `round` in `GET /api/devices/home_pi_01/state`, built on
  every poll from the round itself (`DeviceService._round`), not queued: a round lasts longer than the 30 s
  a queued command lives, and a restarted device finds it again. Its `command_id` is
  `<round_id>:<state>`, so the device acts once per state. The value uses the Activity field names plus
  `secret_word` and `language`. **`secret_word` is only there when the reader sent the device key**: the
  route itself stays open (6.4), and `scripts/test-client` reads it from the public URL.
- **The result is said aloud** ("Ana got it!"): `RoundEngine._finish` returns a `Speak`, announced by
  `ActivityService.finish`. Mochi does not judge the guess from what it hears: a turn has no speaker, so
  the describer saying the word would count as a guess. The describer's tap decides (AGENTS 7.5).
- **Roles swap** from round to round (`round_engine._names` reads the round before). Names only: the
  language of a round still follows the session focus, which is English (`session_store.py`). AGENTS 7.5
  ("the describer's target language") and M4 ("a word the guesser needed") disagree here. **For the team.**
- **Fixed on the way:** a finished round still counted as a round in `DecisionFlow._follow_up` and
  `_may_be_heard`, so after one round Mochi only answered "Oi Mochi ..." until Stop.
- **Not built:** the Home view in `apps/web` (the Pi draws the round itself, `hardware/pi-setup/face.html`;
  AGENTS 9.1 puts the Home view in `apps/web`, which is still empty); the names on the screen are the demo
  roster (`ana`, `ben`), not the voices the Pi knows; a spoken "skip".
- **From an independent review of this change, fixed before it was first tried:** the reply that starts a
  round was screened for the secret word before the round existed, so "[play] ... umbrella ..." could be
  said while "umbrella" was the word (now screened again once the word is drawn: only the host's line is
  said); a round ended by Reset stayed on the device's screen (its absence from the state now clears it);
  a result card was served for the rest of the session (now for 30 s); `.env.example` still had the old
  greetings. **Left as they are, for the team:** `/ws?device=home_pi_01` has no key and receives the
  private prompt, so the device key guards the state route only; a round can only be left by a touch or
  Stop, and while it runs hints are off; the host's lines are English whatever language Mochi was called in.
Checked with the real model through a scratch backend (fake Agora): "Let's play a game.", "Vamos jogar!",
"Play.", "I want to practise with you.", "Just listen while we talk, please.", "A gente vai conversar, fica
só ouvindo.", "What can you do?", "Can we play Secret Missions?" each got the right mode; a whole game
(reveal, guessed, next round swapped, skipped by a long press) ran through the Pi's own code and the face
page in a headless browser. **Not yet done with a person, a finger on the panel and Agora's voice.**

## D-40: Mochi Home runs the LIKELY configuration with "append" (2026-11-21)

`latency-performance` (D-37) is merged into `hardware`, and its `likely` preset is the configuration: ARES
`en-US,pt-BR` with the lexicon named as keywords, the Cartesia voice, `MOCHI_CANCEL_STALE_TURNS=true`,
`MOCHI_CHARACTER_HEDGE_SECONDS=1.0`, together with `MOCHI_INTERRUPTION=append` (D-38). `render.yaml`
carries these values; settings defaults are unchanged. Suhuai tried it by voice on the device and chose it.

Measured on the Pi (test backend on the Pi, channel `mochi-test`, the same 14 recorded sentences per arm, a
woken session; "first sound" = end of the speech to Mochi's first audio arriving at the Pi; medians):

| Arm | Pi first sound | Agora e2e | asr_ttlw | tts_ttfb |
|---|---|---|---|---|
| main, first / last run | 4.10 s / 3.75 s | - | - | - |
| branch, flags off | 4.08 s | 2926 ms | 1032 | 251 |
| safe | 3.91 s | 2821 ms | 1139 | 229 |
| ares | 3.64 s | 2332 ms | 647 | 243 |
| cartesia | 3.95 s | 2621 ms | 1038 | 101 |
| stream | 3.83 s | 2853 ms | 1104 | 247 |
| likely | 3.23 s | 2240 ms | 677 | 90 |
| stretch | 3.20 s | 2114 ms | 567 | 146 |

- The two runs of `main` differ by 0.35 s: smaller differences are noise. Only `likely` and `stretch` are
  beyond it; `stretch`'s 480 ms pause adds nothing visible, so it is not taken.
- The Pi hears Mochi 1.0 to 1.15 s after Agora's e2e in every arm (the plan estimated 0.25 s). Not explained.
- `stream` cannot gain in a woken session: only sentences with the wake phrase stream.
- **ARES hears a Portuguese word inside English only when it is named.** Same clips, `en-US,pt-BR` both
  times, three runs each: without the list "adiar" was "adjust" 3/3 and "guarda-chuva" "guarded shoe" 3/3;
  with it both were right 3/3. Words not on the list (garfo, feira, presente, trânsito) were wrong either
  way. So hints work for the lexicon's words and not for others a learner says; gpt-4o-transcribe needs
  no list but garbled these sentences in about a third of the runs.
- **Open:** D-36's risk (named words "heard" in faint background talk) was not measured for ARES; the
  Cartesia voice has one language per session ("en"), so Portuguese is spoken by an English voice; its
  billing under Agora's managed key is undocumented; real voices were tried informally, not scored 10/10.
- Also seen, on `main` too: in a woken session "How do you say X in Portuguese?" is a race between the
  hint model and Mochi's line (`_model_before_line`); when the hint wins Mochi shows the word and says
  nothing (typed, 12 each: `main` 7 silent, the branch 2). Not fixed here.

## D-41: many sessions at once; the phone no longer turns the Pi off (2026-11-21)

**Why.** There was one session, `demo`, for everybody. The phone as a microphone (PR #16) started it,
read the Pi's join block (the Pi's channel and uid) and joined with it; the Pi saw the same state and
joined too, and Agora kicked one of them out. And a phone's Stop was the Pi's Stop: it ended the one
agent, and since #15 the Pi leaves when its agent does. A sentence from either came to the same turn
endpoint, the same hint history and the same cooldown. AGENTS section 8 lists "multiple sessions" as
out of scope unless a human asks; Luís asked ("multiple connections that do not interact").
- **A session is its own world:** store, hub view, live hint, silence policy, turn pipeline, game, Mochi's
  conversation (`Intelligence.another_conversation()`), Agora channel `<MOCHI_CHANNEL>-<id>` and Agora
  agent. `demo` is the Pi's and is built at start-up exactly as before, so the bridge, `/api/devices/
  home_pi_01/state` and every existing route behave the same. Any other id (`^[A-Za-z0-9_-]{1,40}$`) is
  opened by its first Start and forgotten at its Stop. At most 8 live (each holds a paid Agora agent);
  a ninth Start is a 409.
- **The id is in the path.** `POST /api/sessions/{id}/start|stop|activity/start|activity/result`,
  `POST /dev/sessions/{id}/turn`, and Agora's turn endpoint `POST /agora/llm/{id}/chat/completions`
  (each agent is started with its own session in the URL; that is what keeps sentences apart).
  Unknown session: 404 (turn, game, join). Stopping what is not running is a 200.
- **New:** `GET /api/sessions/{id}/agora` is the phone's join block for its own channel. The phone
  never reads the Pi's device state again.
- **WebSocket:** an optional `&session=<id>` on `?user=`, `?user=&surface=ar` and `?view=audience`
  (default `demo`, so nothing existing changes). Connecting before Start opens nothing: the client
  sees an idle session, and the real events once the session starts. Mochi's own screen is the Pi's.
- **Delivery.** An event reaches only the connections that follow its session. The exception is a
  learning event: it belongs to a person, so it reaches that person's phone in every session.
  `sequence` is still one counter for the whole process (a client ignores one it has applied; gaps
  are allowed).
- **Source of truth.** Saved words, users and voices are the one thing the sessions share, and they
  are in the database (D-32, D-33): every session's brain writes to the same `MemoryStore` and sink.
  The live parts (hints, game, who is on air) stay in memory, as D-32 decided.
- **Not built, for the team:**
  - A game in a phone session: the secret word goes to the Home view only, and a phone session has
    none. Starting a round there is allowed but nobody sees the word.
  - More than one Pi (device ids): `home_pi_01` is still the only device, and it follows `demo`.
  - Persisting live sessions in Postgres (a restart ends every session; the Pi starts a new one).
  - A phone session whose agent Agora ended by itself stays "capturing" until its Stop or 8 are used.
  - `POST /api/demo/reset` still clears everybody's words (they are shared); it resets the demo session.
- **Owners:** gateway (Luís). `Intelligence.another_conversation` and `MochiTalk.character` are in
  Kauê's directory (a copy of one object, no behaviour change). The web change is Tasnim's and is
  kept in its own commit.

## D-42: stuck without asking: hints before anyone says "how do you say" (2026-11-21)

Asked for by Suhuai ("we only get a hint when we explicitly ask; detect the difficulty in advance, and make
the analysis faster"). It changes `intelligence/` and `packages/fixtures` (Kauê's), one constant in
`platform/` and two lines of `composition.py` (Luís's): **for the owners to accept or change**, as D-27 and
D-29 were. No contract changes: `ModelRequest` is internal to `intelligence/`.

**Yardstick** (`~/.cache/mochi-wake-eval/hint_bench/implicit.json` on the Pi, 145 sentences written the way
the recogniser writes them, real gpt-5.4-mini, Mochi only watching): 63 where someone is stuck and does not
ask (stops before the word with no "…", describes the thing, starts the sentence over, looks for the word
aloud, uses a false friend, or the listener did not understand), 82 that must stay silent (ordinary
sentences that look the same: "It's the place where I grew up.", "Can you pass me the", "Who are you going
with?"). 37 of the 145 were never used for tuning. The same sentence can flip between runs, so every number
is from two or three runs (the third "now" run with the real 2 s limit, the others with 6 s so that a
slow network on the Pi is not counted as a wrong answer).

| | before | now |
|---|---|---|
| stuck, right word shown (63) | 12 and 21 | 54, 55 and 55 |
| of those, never tuned on (19) | 5 and 8 | 16, 15 and 16 |
| ordinary, stayed silent (82) | 81 | 82, 82 and 82 |
| D-29's set of 72 (as heard, explicit asks, code switches) | 67 and 69 | 68, 68 and 69 |
| `scripts/eval_intelligence.py` | 141/146 | 174/178 (142 of the same 146; 32 rows added) |
| one judge call, first token / IGNORE / whole hint | 0.56 / 0.61 / 0.76 s | 0.60 / 0.65 / 0.79 s (inside the run-to-run spread) |

While someone talks WITH Mochi nothing changes: its own spoken reply already names or hints at the word in
most of these sentences (same set, `--woken`), so the silent judge is still not asked there.

What changed, all in `intelligence/`:
- **The instructions** (`openai_hint_model.SYSTEM_PROMPT`) did most of it. They now say that most stuck
  people never ask; that a turn ends when the speaker pauses, so a sentence that simply stops was stopped
  there; and they spell out trails_off, restarts, talks_around and not_understood with examples on both
  sides, with one test for a stopped sentence: would most listeners fill in the same word, or one of two or
  three? ("I need to cut this paper. Do you have a" yes; "Can you pass me the" no.) The model judges
  `sentence` only, never something in `recent`. IGNORE is still the answer for everything else.
- **Signs** (`stuck_signs.py`, no model): `stops_short`, `starts_over`, `describes`, `searches`,
  `partner_lost`. They are sent with the sentence as `noticed`, as clues (without them 105 of the first 117
  were right, with them 109; the gain is the mid-sentence "como é que fala"), and they are a check on the
  answer (`answer_screen.unseen`): a "trails_off" needs a sentence that stops short, a "restarts" one that
  starts over, a "not_understood" a listener who says so. "A what?" is two words and still goes to the
  model when a sentence came before it.
- **False friends** were found by the lexicon and then lost: the confirming call was not told what was
  suspected and had to name the same word unprompted ("I pretend to travel in July." got nothing). The
  suspicion now goes with the request (`ModelRequest.suspect`, instructions in `SUSPECT_NOTE`, sent only
  then), and the model's word must still be the rule's (`same_family`). Whether a word is used with its
  look-alike's meaning needs a moment of thought: answering at once the model was right 20 times in 27
  (it confirmed "sensible" for someone who never cries, and let "I pretend to travel" pass), with
  `reasoning_effort: low` 26 in 27, for 0.14 s more. Only a request with a suspect is asked that way.
  Four more entries (assist/watch, sensible/sensitive, fabric/factory, excitado/animado), each triggered
  by a collocation, not the bare word: with a bare "sensible" the model confirmed "He's a sensible guy, I
  trust him." four times in six. "pretender que" and "realizei que" were tried and taken out: the model
  did not confirm them. A false friend the rules did not suspect is still dropped (D-29). Suspects are not
  followed up while someone who woke Mochi talks with it (`attentive`): its reply puts the word right,
  and a silent hint there races that reply (D-40). The false-friend instructions are not in the standing
  prompt: there, their example sentence made the model answer about a "pretend" two sentences back.
- **Smaller fixes found on the way:** a hint after "A what?" is in the language of the sentence that was
  not understood, whatever language the listener answered in, and never a word that sentence already had
  ("...go to the beach tomorrow?", "Sorry, what?" had got "beach"); "the, how do you say, ..." in the middle of
  a sentence is a search for the missing word, not a question about what follows; a hint the model repeats
  as its own "meaning" is kept without a meaning; the question itself is never the word ("Como se fala..."
  got "How do you say"); the lexicon's describing rule no longer shows "receipt" for a sentence that says
  receipt. The checks on the answer moved to `answer_screen.py` (`decision_flow.py` was at its size limit).
- **Changed on purpose:** "I wanted to go, but..." (fixture `trails_off-67`, D-31) is now IGNORE with the
  real model: nothing before the stop points to a word. The unit fixture with the scripted model still
  passes. **For Kauê and the glasses:** if candidates after a bare "but..." are wanted, say so.

**Speed.** One judge call takes 0.55 to 0.65 s to its first token from this Pi whatever the instructions'
length (a one-line prompt: 0.64 s in the same minute; the instructions grew from 1.5 k to 2.6 k tokens at no cost), and OpenAI's priority
tier gave nothing. So the call itself is at its floor from here; what was slow around it:
- **The first sentence of a session** paid for a new connection, twice when the hedge fired (1.6 s on the
  deployed backend against 0.8 s later). `Intelligence.session_started` now opens two connections for each
  model in the background (`warm_start.py`: a GET for the model's name, no tokens).
- **After a lull** the same: connections were dropped after 30 s idle. Measured against the API, one idle
  for 120 s was still reused; `KEEP_ALIVE_SECONDS` is 90, with a margin (it holds for every `HttpxClient`).
- IGNORE is answered as `{"decision": "IGNORE"}` and nothing else, and a candidate list no longer repeats
  the first word.
- **Not done, with reasons:** releasing a hint before the model has finished writing it would save about
  0.2 s and lose the example sentence; skipping the model for sentences with no sign would be instant and
  free but loses every description without a general word ("He is the doctor for the teeth.").
- **Where the rest of the time is** (not touched): the 600 ms pause that ends a turn and the recogniser
  (0.65 s with ARES).
- **From the decision to Mochi's own screen** (`hardware/`): the Pi opened a new connection for every
  read of its state, which to the hosted backend is a TLS handshake each time. `MochiBackend._state` now
  keeps one open (measured from this Pi to Render: 0.24 s a read instead of 0.38 s; if the kept one fails
  the read is made the old way), and this Pi reads every 0.15 s again instead of 0.3 s (its untracked
  `mochi.local.toml`). A hint is on the screen about 0.3 s sooner on average.

**Limits, for the team:**
- **A pause is not always a problem.** Someone who stops for half a second and then finds the word alone
  still gets the hint a moment later, and with it a card; saying the word then counts as "Used with help"
  (7.4). A wrong guess is a card too, and from M4 a card can be drawn as a round's secret word. The newer
  sentence only cancels the older one's judging while that is still running (D-37). How often this
  happens in real talk is **not measured**: the yardstick has single sentences, and two typed pairs.
- **No speaker in a turn** (6.5): Ben trailing off in his own English gets a hint that is filed as Ana's.
  The Pi knows who is talking (D-34); it is not passed to `decide()`.
- **Mochi's own screen showed one word**, the glasses all of them. **Proposal (owners: Matheus for the
  shape, Luís for the gateway):** the device's `hint` card gains `candidates`, the other words that fit,
  only when there are any (`gateway/turn_pipeline.hint_card`, AGENTS 6.6); the face draws up to two of
  them as a third line under the word (`face.html`, `mochi_device.main.hint_more`). An older backend
  sends none and an older device ignores the field.
- The yardstick is typed text. How ARES writes a sentence that trails off was seen in two real
  transcripts ("...não entendi..."), not measured. `hint_cooldown` and every setting are unchanged.

## D-43: Papear: Mochi for a company's meetings; two modes; the game is removed (2026-11-21)

**Why.** The team changed the product on 2026-11-21: Papear is language learning for companies. Mochi
(the device, or a phone with the app) sits in the company's meetings; people register their voice in
advance; when one of them is stuck a word appears; afterwards each person checks their progress and
does a review on their phone; administrators get a company view. Two kinds of session only, meeting
and review. "Since we will have only two main modes, we will delete the play mode, anything related
to games should be erased." The web app is being changed by its owners; this is everything else.
- **Removed, outside `apps/web`:** contracts `Activity`, `PrivatePrompt`, `ActivityCommand`,
  `ActivityResult`, the enums `GameState`, `RoundResult`, `WordSource`, events `activity.state.changed`
  and `activity.private_prompt`, Speak reason `activity_host`; `intelligence/round_engine.py` and
  `handle()` on the port; `gateway/activity_service.py`, `routes/activity.py`, `secret_guard.py`,
  `secret_screen.py` and every use of them in the hub, the pipeline, the store and Stop; the `round`
  device command and the device key's role on `GET /state`; `[play]`; the round rules in the quiet
  rules and the wake phrase ("Thanks, Mochi" no longer has a round to stay out of); on the Pi
  `mochi_device/game.py`, the round card on the face page and touch reporting (nothing else used a
  touch; the face still hops when touched).
- **Session modes are `meeting` and `review`** (were `together` and `activity`; `practice` and
  `choosing` were never in the backend's contract). The schema version is 0.7. **This breaks
  `apps/web` as it is today**; what it has to change is listed in `docs/TEAM_VIEW.md`, section 6.
- **Waking Mochi starts a meeting.** It says one line ("Hi! I'm listening. Call me if you need a
  word." / "Oi! Estou ouvindo. Me chama se precisar de uma palavra.", `MOCHI_GREETING_EN|PT`) and then
  only watches. It no longer asks what to do, and the sentence after the greeting is the meeting's,
  not an answer to Mochi. It still answers when called by name, and for a short while after it spoke.
- **Mochi's character** (`intelligence/character.md`) keeps its voice, moods and silent commands; the
  part about three things to do is replaced by the two sessions, and it is told with every sentence
  which one this is. In a meeting it answers what was asked and hands the talk back.
- **Kept on purpose:** `[listen]` and `[chat]`; the stand-in agent on the Pi (`backend.kind =
  "test_agent"`), reworded only where it named the game or the three modes; `LearningState.REINFORCED`
  (D-44 gives it a new way in); the Audience view's connection; `MOCHI_AGENTS.md` (the original v0.4
  text) and `vision/` (the earlier vision), as history.
- **Open, for the team:**
  - `apps/web` (Home view game states, "Play", `activityStart`/`activityResult`, the mock's demo).
  - The Pi ends a session after ten minutes, or 30 seconds without a voice (`[session]` in
    `hardware/pi-bridge/config/mochi.toml`), and the Agora agent leaves 60 seconds after the Pi
    (`MOCHI_AGENT_IDLE_TIMEOUT_SECONDS`). A meeting needs more; more costs Agora minutes. Not changed.
  - The stand-in agent's prompt is still a near copy of `character.md` written for two friends; whether
    a meeting wants a quieter stand-in is a product call.
  - Whether the app is still called Mochi anywhere a customer sees it. Code, routes, variables and
    the wake phrase keep the name; only the documents say Papear.
- **Owners:** contracts and `hardware/` (Matheus's directories); gateway (Luís) and intelligence
  (Kauê) are changed too, by deleting what served the game. Needs their yes.

## D-44: who said it: the recognised voice on each turn; a review brings a word back (2026-11-21)

**Why.** A turn had no speaker (AGENTS 6.5), and the whose-word rule (7.3) only works for two people
learning each other's language. In a meeting several people learn the same language; then every hint
had `target_user_id: null`, reached everybody's phone and was saved for nobody. And with the game gone
nothing could move a card to `REINFORCED`.
- **`Turn.speaker_user_id`** (additive, optional). The Pi already tells the backend whose registered
  voice it hears (`POST .../status`, `speaker`, sent when it changes and kept until the next one). The
  gateway keeps the person that name belongs to (`Roster.named`, matched to `display_name`) and puts
  them on each turn. `null` when no voice is recognised, and for a phone's microphone.
- **Rule 7.3 gains a first step:** the recognised speaker owns the word when they are in the session
  and are learning the language being spoken; otherwise the old rule; otherwise nobody
  (`intelligence/word_owner.py`). The condition keeps the two-person demo safe from a late report:
  "ben" on Ana's "I need to adiar my meeting" still files postpone for Ana.
- **A review** is a session with `mode: "review"` and a `user_id` (`POST .../start`; 422 for an
  unknown person). Its one participant is that person, its focus the language they are learning, and
  Mochi is their partner from the first sentence (`session_started(conversing=True)`; the parameter
  was called `woken`). Mochi is given up to six of their cards that are `DISCOVERED` or `ASSISTED`,
  newest first (`learning_rules.words_to_review`, `REVIEW_NOTE`), and asks for each through its
  meaning. A card whose expression the person says moves to `REINFORCED`
  (`learning_rules.recalled_updates`), unless that word was shown as a hint in the last few turns.
  The UI label for `REINFORCED` becomes "Recalled in a review".
- **People are no longer only Ana and Ben.** `gateway/roster.py` holds the people known (the stored
  users, else the two demo people); sessions, the WebSocket (`?user=`) and saved words use it.
  Members are added through the company routes (D-45).
- **Limits, for the team:**
  - **Timing is not measured.** The turn carries the last speaker the Pi reported. A report that
    arrives after the turn, or two people speaking in quick succession, can file a word for the
    wrong one of two people learning the same language. Nobody has tried it with two voices yet.
  - Someone stuck in the language they are at home in (Ben trailing off in English) still gets a
    hint that is filed for the learner, as before (D-42's limit stands for that case).
  - A phone's microphone recognises nobody: its meetings fall back to the old rule.
  - The review counts a word as recalled when it is in the sentence. A word Mochi itself gave away
    in a free reply (not as a hint) is not excluded. Reviews were tested with typed sentences and a
    scripted model only.
  - `USED_INDEPENDENTLY` is still never set.
- **Owners:** contract shape (Matheus), gateway (Luís), `intelligence/` (Kauê: `word_owner.py`,
  `learning_rules.py`, `mochi_talk.py`, `decision_flow.py`, the character prompt). Needs their yes.

## D-45: the company: members, session records, word moments and the team view (2026-11-21)

**Why.** Administrators are to see how their people are doing, and Papear is to learn which words
and mistakes come up in a company's work. The request: "design the database and backend logic for
that part too, namely how we can aggregate each individual person's learning data and have an
insightful analysis for the administrators". The whole design, with the tables and an example of
every answer, is `docs/TEAM_VIEW.md`; this entry is the decisions in it.
- **Two new kinds of fact.** A learning event is one card per person and word, so it cannot say how
  often a word was needed. A **word moment** is written for every hint shown or answer spoken; a
  **session record** for every session (when, who, how many sentences each recognised voice said).
  The same word shown again within a minute is one moment ("say it again?").
- **Four tables:** `companies`, `company_members`, `session_records`, `word_moments`, created at
  start-up like the others (D-32), each fact row with `company_id` and its contract object in a
  `jsonb` body. Loaded once, answered from memory, written behind: the same arrangement as saved
  words, in a new package `mochi_backend/team/` that imports neither half of the backend.
- **The team view is computed, not stored** (`team/team_view.py`, pure functions): totals, how far
  saved words got, how people get stuck, the expressions the team needed (by how many people and how
  often), false friends as a list of their own, a row per week, a row of counts per member, and a
  few highlights as kind-plus-numbers for the screen to phrase.
- **What an administrator cannot see:** who needed a word, anyone's sentences, or which words a
  member has. `MOCHI_TEAM_MIN_PEOPLE` (default 1, for the two-person demo) leaves out expressions
  fewer people needed.
- **Routes** (`gateway/routes/companies.py`): members (list, add), insights, sessions, and a person's
  own moments. `viewer=<user_id>` says who is looking; the roles are enforced (admin, member, self),
  but without sign-in it is a claim, exactly like `/ws?user=`.
- **Not stored:** the meeting's sentences (only the one a person was stuck in, with their moment)
  and audio. AGENTS rule 4 says so now.
- **`POST /api/demo/reset`** also clears session records and word moments. People, companies and
  voices stay.
- **Open, for the team:**
  - **Per-member rows for administrators.** They are in because each person's data was to be added
    up; whether a manager should see "Ana: 9 moments" is a product and privacy decision. A company
    that records meetings also needs the consent of the people in them.
  - **Sign-in.** Until there is one, anyone who knows the address and a `user_id` can read that
    person's words (already true of `/ws?user=`) and, as `viewer=ana`, the team view.
  - **One company per deployment.** The demo company `demo` (Ana admin, Ben member) is seeded and
    every session is attached to it. The tables are ready for more; choosing a session's company is not.
  - **The written summary after a meeting and grammar corrections** (`apps/web/PROPOSAL_contracts_
    v0.5.md`) are not built; the moments are the facts they would start from.
  - **Using the data** (the recogniser's keywords, a company lexicon, what a review picks): described
    in `docs/TEAM_VIEW.md` section 7, not built.
  - The database on Render is a free one that expires on 2026-12-21 (D-32).
- **Owners:** to be agreed. It adds to the contracts (Matheus), `gateway/` and `storage/` (Luís); the
  aggregation is closest to Kauê's side. Needs their yes.

## D-46: who said each sentence: stretches of speech matched by time; sentences are stored (2026-11-22)

**Asked for:** see whether each speaker and what they said in a meeting can be told apart correctly, and
record it in the database.

**Measured first** (`~/.cache/mochi-wake-eval/spk/meeting_sim.py` on the Pi: real recorded voices from the
kit's corpus, three people registered and two strangers, 60 stretches of 1 to 6 s per meeting with 0.3 to 3 s
between them, the Pi's real voice-activity detector and `VoiceTracker`; the backend's delays modelled):

| | right person | wrong person | no name |
|---|---|---|---|
| Each stretch judged on its own audio, true boundaries (what the voice model can do) | 295 of 300 | 0 | 5 |
| D-44 as built: the speaker last reported when the sentence arrives (sentences with one speaker) | 331 of 368 | 35 | 2 |
| This entry (sentences with one speaker) | 351 of 368 | 0 | 17 |
| This entry, sentences two people shared (no right answer exists; "right" is whoever spoke most) | 28 of 46 | 11 | 7 |

The voice model was never the problem. The wrong names came from two places: the tracker judges a whole
utterance, and someone who answers within about 0.7 s is still "the same utterance", so the answer went to the
person before; and "the speaker last reported" is whoever was named last, however long ago.

**Decided:**

- **The Pi reports every stretch of speech** (`speakers.py`, event `said`): the speech between two pauses of
  0.25 s, judged on that stretch alone, with who it was (a registered name, or nobody), how much speech, and
  when it ended. Someone recognised while still talking is reported at once as well. The who-is-talking
  report for Mochi's face and character (`speaker`) is unchanged. `MochiBackend` sends the stretches with the
  next status as `heard: [{speaker, seconds, ago_ms}]` (how long ago, so the two clocks need not agree) and
  sends them again when a report failed.
- **The gateway matches by time** (`team/timeline.py`, `team/journal.py`): a sentence is the person's who
  spoke most in the stretches that ended since the sentence before it and at least 0.3 s before it arrived
  (a turn arrives about a second after its speech). At least 60 % of the named speech must be theirs, and
  "could not tell" speech does not outvote a name unless there is more than twice as much of it. With no
  stretch in that time the sentence is nobody's: a wrong name is worse than none. A device that reports no
  stretches at all (older code) keeps the D-44 behaviour.
- **A second look at Stop:** a report can arrive after its sentence, so every sentence of the session is
  matched again when the session ends, and the record's speaking counts are made from that.
- **Sentences are stored** (contract `Utterance`, table `utterances`): each with its speaker. This reverses
  what D-45 said ("not stored: the meeting's sentences") because it was asked for. `GET /api/users/{id}/
  utterances?viewer=` gives a person their own; nobody gets another's; the team view carries none.
  `GET /dev/sessions/{id}/transcript` (dev routes only) shows a running session's sentences with speakers.
- `Turn.received_at` is now when the sentence reached the backend, not when its turn came up behind the one
  before it (they differ by the time the earlier turn took to decide).

**Not done, and what the numbers do not say:**

- **A real meeting has not been measured.** The recordings are read speech, close to the microphone, one
  voice at a time. A room, people talking over each other and Agora's own turn timing will cost something;
  the live check is two or three registered people talking through the Pi with the backend's dev routes on,
  reading `/dev/sessions/demo/transcript`.
- **Two people in one sentence.** Agora closes a turn after 0.6 s of silence; a quick answer lands in the
  same turn and the text cannot be split (no word timings reach us). Such a sentence goes to whoever spoke
  most, or to nobody.
- **A hint's owner is decided when the sentence arrives** and is not changed by the second look.
- **Consent and retention.** Storing what people say at work needs their agreement and a rule for how long it
  is kept; there is neither yet. A sentence no known voice said is stored and nobody can read it.
- **Owners:** contracts (Matheus), `gateway/` and `storage/` (Luís), `hardware/` (Matheus). Needs their yes.

## D-47: the hint judge is told it is a meeting; sessions may last an hour (2026-11-22)

- **The hint judge's instructions** (`intelligence/openai_hint_model.py`) no longer say that two people are
  practising with each other: "several people talk to each other" in a work meeting, some learning English,
  some Portuguese, and it does not know who is speaking. Two other mentions of "the other person" were
  reworded the same way. Measured before and after with `JUDGE_TIMEOUT=6` on the two yardsticks (D-29, D-42):
  "stuck without asking" 138 of 145 before, 136 and 136 after; "as really heard" 68 of 72 before, 67 and 67
  after; no unwanted hint in any run. Of the sentences that differ, all but two flip between runs of the
  same wording; "take money from the machine" (ATM) was lost in both runs after, and "passar o salt" was
  gained in both. Within what one run to the next differs by, and the instructions are no longer wrong
  about who is in the room.
- **Session length:** `[session] max_session_s` is 3600 (was 600), and the Agora tokens live two hours
  (`MOCHI_TOKEN_TTL_SECONDS` default 7200, was 3600; the stand-in agent's tokens too) so that a token does
  not end a meeting at the hour. `inactivity_timeout_s` is still 30: a meeting with half a minute of
  silence ends. Not tried: a session that really lasts an hour.

## D-48: a session starts with "vamos papear" or "let's chat" (2026-11-22)

**Asked for:** the wake expression is "vamos papear", with its English equivalent.

- **The matcher finds a phrase by its own last word** (`hardware/pi-bridge/mochi_device/phrases.py`): until now
  every phrase had to end in the one name ("mochi"). A phrase with the name in it is still found by the name
  ("tchau mochi"); any other by its last word, with the words before it as the cue. `[wake] phrases` is now
  `["vamos papear", "let's chat", "let's papear"]`; the greetings ("oi mochi", ...) no longer start a session
  and come back by adding them to that list. Goodbye phrases are unchanged, and so is asking Mochi something
  by name during a session (that is the backend reading the transcript, not the Pi).
- **How the recogniser writes it** was taken from 458 spoken clips made for this (the kit's voices;
  `~/.cache/mochi-wake-eval/papear/`): the v of "vamos" is the least reliable sound (heard as b, d, z, l or
  not at all, and its a as o), so the cue is also accepted from its vowel on; "papear" is written papea,
  papia, papie, papiar, and with a t for its second p.
- **Measured through the real streaming listener** (clean, and "far": room reverb with noise 15 dB under the
  speech):

  | | heard, clean | heard, far | woke on something else |
  |---|---|---|---|
  | "vamos papear" (Portuguese voices) | 74 of 90 | 72 of 90 | 0 of 258 near-misses ("vamos passear", "vamos parar", "gosto de papear", ...) |
  | "let's chat" (English voices) | 48 of 66 | 22 of 66 | "Let's shut the door" 4 of 5 times; "That's a chat app" once |
  | for comparison, "oi/olá mochi" and "hi/hey mochi" on the kit's older clips (whole-clip scoring) | 80 of 105, 115 of 126 | 72 of 105, 97 of 126 | |

  "let's papear" could not be judged: the synthetic English voices do not say "papear" the way a person would.
- **Nothing else started a session** in 2.34 hours of real recorded speech (the kit's FLEURS English and
  Brazilian Portuguese, 780 recordings, through the streaming listener): 0 wake hits, 0 goodbye hits.
- **Greeting language:** "vamos" / "vamo" count as Portuguese on the Pi and in the backend, so "vamos papear"
  is greeted in Portuguese and "let's chat" in English.
- **Open:** "let's chat" is short and ordinary: it is missed more in noise and has look-alikes that start a
  session nobody asked for ("let's shut ..."). Restricting the start to registered voices, or a longer
  English phrase, would cut that; neither is done. Nobody has said either phrase to the device yet.

## D-50: someone talking over Mochi stops it at once (2026-11-22)

**The bug:** when a person started to speak while Mochi was still talking, Mochi talked on. The cause is
D-35: while Mochi speaks the Pi sends silence instead of the microphone (its own voice comes back in the
microphone and was written down as sentences), so nothing upstream could notice the person.

**Built:**

- **The Pi notices it itself** (`hardware/pi-bridge/mochi_device/bargein.py`, `[barge_in]` in `mochi.toml`):
  - by loudness: the level of Mochi's own voice in the microphone is learned while it speaks (D-35 measured
    it at about the level of the room); a voice `level_ratio` (3.5) times louder than that, and at least
    `level_floor`, for 240 ms of 400 ms, with the voice detector agreeing, is a person;
  - by voice: the tracker goes on listening while Mochi speaks and reports a registered person it
    recognises in what it hears (event `over`, after about 0.8 s of speech). Mochi's own voice is nobody's.
- **Then, at once:** the speaker is silenced on the Pi (no waiting for the network), the backend is told
  (`POST /api/sessions/{id}/interrupt`), and the microphone is sent on again so the person is heard. The
  speaker is given back when Mochi's voice has stopped arriving, or after 4 s.
- **The backend** calls Agora's `POST .../agents/{id}/interrupt` ("the agent stops talking and thinking
  immediately") and tells intelligence (`interrupted()`, a seventh port method): in a meeting Mochi goes
  back to just listening, so what the person says next is not taken as an answer to it (it waits for its
  name again); in a review the person keeps its attention and gets an answer to what they said.
- The stand-in agent on the Pi is interrupted through its SDK session.

**Tested:** the detector, the tracker event, the supervisor's sequence (hush, interrupt, microphone back,
speaker back, once per stretch) and the backend route, with fakes. **Not tested:** with a real voice at the
real device, and the Agora call against the real service. Two things to watch at the first try:

- Mochi cutting itself off with nobody talking (its own voice louder in the microphone than assumed):
  raise `level_ratio`, or set `enabled = false`.
- Not stopping when talked over: lower `level_ratio` (2.5). Registered voices are caught by the second way
  regardless, about a second in.
- The first quarter second of what the person says is not sent on (it was said before the Pi noticed), so
  the recogniser may miss their first word.

## D-49: a noisy room: what holds, what does not, and two things built for it (2026-11-22)

**Asked:** can the demo work where there is noise?

**Measured** (offline, on the Pi; recorded voices, the delays between Pi, Agora and backend modelled):

- **Starting a session.** "vamos papear" is heard 72 times of 90 with room reverb and noise 15 dB under the
  speech, 74 of 90 without (D-48). "let's chat": 22 of 66 and 48 of 66. Nothing else started a session in
  2.34 hours of other speech.
- **Who said each sentence** (`spk/meeting_sim.py`, three meetings, 134 sentences with one speaker each;
  "voices" are three other people talking all the time in the background, so many dB under the meeting):

  | | right | wrong person | no name |
  |---|---|---|---|
  | quiet | 124 | 0 | 10 |
  | room reverb and noise | 121 | 1 | 12 |
  | the same, voices registered close up | 118 | 3 | 13 |
  | background voices, 15 dB under | 102 | 11 | 21 |
  | background voices, 10 dB under | 95 | 9 | 30 |
  | background voices, 5 dB under | 70 | 8 | 56 |
  | room and background voices, 10 dB under | 95 | 9 | 30 |

  The same sentences with the rule of D-44 (the speaker last reported): 116, 104, 100, 34, 34, 26, 36 right.

**Built for it:**

- **A verdict every two seconds of unbroken speech** (`speakers.py`, `SAID_EVERY`). D-46 judged a stretch
  when it paused; with other people talking in the room the voice detector never hears a pause, and a whole
  meeting went by with hardly a verdict (30 of 134 right with background voices, as measured before this
  change). It also helps in a reverberant room, where one person's echo ran into the next person's words
  (108 right and 12 wrong before, 121 and 1 after).
- **`MOCHI_MEETING_VOICES=registered`** (default `all`): in a meeting on the device, a sentence no
  registered voice clearly said is neither looked at nor stored. The people at the next table then get no
  hints, no cards and no place in the database. The price is that a member's sentence the device could not
  name is dropped too (the "no name" column above), so it is a setting for a noisy room, not the default.

**What a noisy room still breaks, and nothing here fixes:**

- **The recogniser writes down what it hears.** In the earlier live test (D-36) 4 of 10 faint background
  recordings came back as sentences. With `registered` they are dropped when the Pi does not know the voice;
  without it they are judged like anyone's.
- **Turns.** Agora ends a turn after 0.6 s of silence. With people talking nearby there may be no silence,
  so sentences arrive late or several at once. Not measured; the simulation above cuts turns where the
  meeting's own speech pauses, which is kinder than Agora will be.
- **Agora's own filter** (`advanced_features.enable_sal` with `sal.sal_mode`, Beta; join page read
  2026-11-22) locks onto ONE speaker and blocks other voices: right for a review on a phone, wrong for a
  meeting, where it would shut out the colleagues. Not used.
- **Steady noise is the easy case** (fans, traffic, a hum): everything above holds up in it. Other people's
  speech is the hard one.

**For the demo:** put Mochi close to the people speaking and away from other tables; register the voices
on the spot, in that room; run the backend with `MOCHI_MEETING_VOICES=registered`; start with "vamos papear"
or the phone's Start rather than "let's chat". And try it there before showing it: none of this has been
heard through a real room yet.


## D-51: the live transcript: every finished sentence goes to the screens of its session (2026-11-22)

**Asked:** show what is being said during a meeting, as it is said.

**Proposed, built:** a new event, `transcript.line`, with one finished sentence (`TranscriptLine`:
`utterance_id`, `user_id` or null, `text`, `at`, `marks`). The gateway publishes it when the sentence's
turn is committed, to every connection of that session except AR glasses, and hands the device a
`caption` command that the Pi draws as a small strip under the face for eight seconds
(`[face] captions` in `mochi.toml`). `MOCHI_LIVE_TRANSCRIPT=false` switches both off.

**Why at the commit and not the moment the sentence arrives:** a turn can be dropped after it arrived (a
Stop, a Reset, or with `MOCHI_CANCEL_STALE_TURNS` a newer request from Agora that covers the same speech
again under a new id, D-37). Published earlier, such a sentence would show twice, or after Stop. The price
is the time the hint judge takes, usually under a second.

**"Live" means per sentence.** Agora gives the backend finished sentences. Word-by-word captions would
have to come from Agora's own interim transcripts inside the channel, read by the Pi and by each phone;
not built.

**What it changes in the product rules (AGENTS section 1):** rule 3 said a person's sentences are shown
only to them. What is *stored* still is (the `Utterance`, D-46). The live line is shown, while it is being
said, to the screens of the session it was said in. Rule 2 ("show nothing unless a hint is worth it") now
names the transcript as the one thing always shown.

**Meetings only.** In a review one person talks to Mochi on their phone; nobody else heard it, so no line
and no caption is sent for it.

**Open, for the team:**
- **Who can read it.** There is no sign-in: anyone who opens `/ws?user=<a known id>` or `?view=audience`
  on a running session reads the meeting, where before they saw a hint now and then. Until sign-in exists
  the switch is the only protection. Is on-by-default right for the deployed backend?
- A sentence no registered voice said is in the transcript too (on a phone's microphone that is every
  sentence). `MOCHI_MEETING_VOICES=registered` (D-49) already drops those before anything sees them.
- Serious or personal talk (7.2) keeps Mochi from hinting, and is captioned like anything else.
- Lines are not replayed to a screen that connects mid-meeting.

## D-52: a code switch is marked for everyone; the hint stays the speaker's (2026-11-22)

**Asked:** make people take notice when someone switches language.

**Proposed, built:** when a sentence gets a `code_switch` hint, its transcript line carries a mark: the
word that was said and the word in the language being spoken (`adiar` → `postpone`). The device's hint card
carries `why` (the hint's reason), and Mochi's screen draws a code switch with an amber frame and the line
"adiar → English" instead of "English · adiar". Still no sound.

**Considered and not done:** sending the `code_switch` hint itself to every phone. The web app shows any
hint it receives as the phone owner's, so Ben's phone would have presented Ana's word as his, and AGENTS
6.2 and the 9.2 test ("not on `?user=ben`") would no longer hold. The mark reaches everyone without that.

**Open:** only a switch the hint rules catch is marked: a word of the other language inside a sentence,
said by someone learning the language of the sentence. A whole sentence in the other language is not a
"code switch" to the rules, so it is captioned and nothing else; translating it for the others is not built.

## D-53: idioms and technical terms are explained to the people listening (2026-11-22)

**Asked:** explain idioms and hard technical terms.

**Proposed, built:** a second model, the *explainer* (`intelligence/explaining.py`,
`openai_explain_model.py`), reads a sentence and names at most one expression an intermediate learner
would not understand, with its meaning in the listeners' language and the same in plain words. The result
is a mark on the sentence's transcript line (`kind` `idiom` or `technical_term`; the line is published a
second time) and an `explain` card on Mochi's screen. A new port method, `explain(turn, context)`.

**It is not a hint, on purpose.** The first design made it a `Hint` with two new `reason` values, so that
every existing screen would show it unchanged. A review of that plan found what it would have cost: an
explanation would sit in the session's five remembered hints and count for the cooldown, for "the same
word was just shown", for "used with help" and for every sum in the team view, each needing its own
exception; and the hint judge accepts any `reason` it is given back. So nothing in `Hint`, `Reason`,
`decide()` or the hint judge's instructions changed.

**It never makes anything wait.** The gateway asks for an explanation after the turn is committed, in a
task of its own, and only for a sentence that got no hint and no answer. The result is shown only if the
session is still the same one, and its card is not queued while a hint is on screen.

**When it is asked** (AGENTS 7.6): a meeting, five words or more, someone other than the speaker learning
that sentence's language, not serious talk, not for Mochi, not while someone talks with
Mochi, 20 s since the last explanation; each expression once per session; confidence at least 0.75 and the
expression really in the sentence.

**Tried** (2026-11-22, `gpt-5.4-mini`, no thinking, 24 written sentences of my own, 12 with an idiom or a
term in English or Portuguese and 12 ordinary ones, among them a code switch and a company name): 24 of 24
right, 0.74 s on average. Not a measurement: no machine transcripts, no real meeting, one run.

**Cost:** one more model call for every sentence of five words or more that needed nothing else, about the
size of the hint judge's. `MOCHI_EXPLAIN_TERMS=false` switches it off.

**Kept for the company:** the mark is stored with the sentence (`Utterance.marks`), and the team view lists
what was explained and how often (`TeamInsights.explained`): a company's own jargon, as its learners meet
it. Who said it is not in the list.

**Open:** an explained expression is saved as nobody's word (a learner might want to keep it); what
"intermediate" should mean per person; a company's own terms (product names, internal abbreviations) are
not known to the model.

## D-54: what was wrong in what someone said: a private report after the session (2026-11-22)

**Asked:** some analysis of a person's speech when they say something wrong or inaccurate; not shown in
the meeting, kept in their learning profile.

**Proposed, built:** when a session stops, in the background, each person whose recognised voice said
three sentences or more gets a `ConversationReport` (AGENTS 6.2 and 7.7). It follows the shape the web
app's owner proposed for v0.5 (`apps/web/PROPOSAL_contracts_v0.5.md`, 3b), with these differences: `mode`
(`meeting` | `review`) instead of `context`; no `title`; `topic` is one of a fixed list instead of free
text, so that the same mistake can be counted across people; each mistake has an `explanation`; sentences
carry their `utterance_id`; `company_id` and `record_id` are there.

**Why at Stop, once, and not sentence by sentence:** who said a sentence is settled only when the session
ends (D-46), and a report built earlier could put one person's sentence into another's; one call per
person is cheap and sees the whole of what they said; and nothing here is wanted during the meeting.

**How:** the gateway builds a draft from the stored sentences and the session's word moments
(`gateway/after_session.py`); a new port method `coach(draft, person)` has a third model, the *coach*
(`openai_coach_model.py`), put the wrong sentences right; `intelligence/speech_report.py` keeps only
corrections that hold up (a real sentence, a real change, a kind we know, a sentence in the language the
person is learning) and groups them. No answer from the model means no report.

**Who sees it:** the person. Their phone gets `conversation.report.created` (and the five newest on
connect), and `GET /api/users/{id}/reports?viewer={id}` refuses anyone else. The team view counts kinds of
mistake (`TeamInsights.mistakes`) only when **at least three people** made them: a kind one person makes
names that person, and one that two people make tells whichever of them is looking about the other. The
two-person demo company therefore shows none. A report's `unknown_words[].said_instead` is the person's
sentence only when their own voice said it: a word can be theirs although a colleague's voice said the
sentence (AGENTS 7.3, rule 2), and that sentence is not theirs to read.

**Tried** (same model, thinking "low", twelve written sentences): six mistakes, all real (tense,
agreement, an uncountable noun, a false friend, two wrong constructions), with fillers, a Portuguese
sentence and a code switch left alone. It missed "until Friday" for "by Friday". One run, written
sentences.

**Open:**
- **The same leak exists in what D-45 built and was not touched here:** `GET /api/users/{id}/moments`
  returns `WordMoment.heard`, the sentence the word was needed in, whoever's voice said it. When the hint
  went to the only learner of the language and not to the speaker, that is a colleague's sentence. The
  fix is the one used for reports (keep `heard` only when the moment's person said it); it changes
  D-45's stored rows, so it is left for the team to decide.
- With few people a count can still be worked back to a person (a one-day period and a meeting of three).
- **A misheard word looks like a mistake.** The instructions say to skip what looks misheard; how often a
  real transcript still gets someone blamed for the recogniser's error is unmeasured (AGENTS 12.9).
- A session on a phone's microphone recognises no voice, so nobody gets a report there; a review does
  (every sentence is the reviewer's).
- A session that ends without Stop being called gets no report.
- The first 150 sentences of a person are looked at; an hour-long meeting can hold more.
- `MOCHI_REPORT_MODEL_NAME` lets reports use a stronger model than the hint judge's; which one is worth
  its price has not been compared.

## D-55: "Used on your own": a saved word said later with no hint (2026-11-22)

**Asked:** optionally, more help during a meeting. This one is the last state of AGENTS 7.4, which was
listed as not built, so the funnel in the team view always ended in a zero.

**Proposed, built:** when a meeting stops, a card moves to `USED_INDEPENDENTLY` when its person's own
recognised voice said the word in that meeting, the card was last touched before the meeting began, the
word was on no screen during it (as a hint, or as one of the other words on a hint's card; the journal
keeps that list, `words_shown`), and the sentence did not follow someone else saying the word (one of
the two sentences before). A new port method, `used_alone(said, shown, began)`; the gateway publishes
`learning_event.updated` as for any other change.

**Why at Stop and not as it is said:** the first design moved the card live and had the device cheer.
The change cannot be undone, and the speaker of a sentence is provisional until the session ends (in a
noisy room the first verdict is wrong one time in ten, D-49). So it is decided with the final speakers,
and there is no cheer on the device for it.

**A fix that came with it:** `ASSISTED` ("said within the next three turns") counted turns from the
current session only, so a card from last week said in the first sentences of a new meeting became "used
with help" with no hint in sight, and would then never count as used on its own. The hint must now also
be at most three minutes old.

**Open:** it needs a recognised voice, so it never happens on a phone's microphone; a common word
("return") will move the first time its person says it, which is what the state says but may feel cheap.

**Not built, from the same question:** translating a whole sentence said in the other language for the
others; word-by-word captions; asking Mochi "what did she just say?".

## D-56: the web app has its own users and sessions; session records (2026-11-21)

*Written on `main` as D-42 (PR #22) while this file's D-42 to D-55 were being written on `hardware`; renumbered when the two were merged (D-58). `apps/web` and the commits of that PR still say D-42.*

**Why.** Luís asked for `apps/web` to be rebuilt as one app that does in a browser what Mochi Home does on the
Pi, for any person and not only `ana` and `ben`. That needs people the backend can create, a session that
belongs to one person, and a record of each session that survives a restart (Render's free plan spins the
backend down when idle). He also asked for the edits in `storage/` and in Tasnim's `apps/web`; the web side is
made by a second builder, in its own commits, against the same written contract.
- **New endpoints.** `POST /api/users` (`{display_name, comfortable_language = "pt-BR", target_language =
  "en"}` -> 201 `User`; 422 for an empty, over-40-character or control-character name, an unknown language, or
  two equal languages), `GET /api/users/{id}`, `GET /api/users/{id}/words` (newest first, the
  `learning_event.created` payloads) and `GET /api/users/{id}/sessions` (newest first by `ended_at`, at most 50).
  The id is `slug + "-" + 6 random hex` (NFKD to ASCII, lowercase, runs of anything else as one `-`, 20
  characters at most, `user` when empty), so it always matches `^[a-z0-9-]{3,27}$` and is never `ana`, `ben` or
  `guest`; a taken id is drawn again. `ana` and `ben` work on every endpoint; `guest` is 404 everywhere.
- **Changed.** `POST /api/sessions/{id}/start` takes an optional `user_id`: 409 on `demo` (the Pi's), 404 for an
  unknown or reserved user (checked **before** the session is opened, because opening can evict another
  session), 409 for another user than the one a running session is for, 200 and the current state for the same
  user or none. `/ws?user=` accepts any registered user (unknown users and `guest` still close 4400), and its
  snapshot now sends only that user's saved words; the order is unchanged (session, activity, live hint,
  words oldest first). Everything else in D-41 is unchanged; without a `user_id`, a Start is exactly as before.
- **The guest and the focus (AGENTS 7.3).** A web session's participants are the user and `guest`, with the
  user's languages the other way round, and `focus` is the user's target language. So exactly one participant
  learns the spoken language, and a word from the user's own language is the user's. The participants, focus
  and user live in the session's `SessionStore` (set when the Start succeeds, so a failed Start leaves nothing);
  `build_context` and the round's secret check loop over them instead of `USER_IDS`. `guest` is seeded with
  the demo users, so its learning events satisfy the foreign key; they are stored and shown to nobody.
- **Voices stay with the Pi's people.** `VoiceDirectory` is given `ana` and `ben` first and never `guest` or a
  web user, so a web user called "Ana" cannot take Ana's voice.
- **Storage.** The port gains `save_user`, `load_sessions` and `save_session`, in all four storages and the
  fake. `save_user` runs on the write-behind worker like every other write, so a user row is always written
  before that user's first learning event (`learning_events.user_id` references `users`); a failed user write
  holds the event behind it. Postgres has a new `session_records` table (`body` is the whole record as `jsonb`,
  `ON DELETE CASCADE` with its user), the local file a `"sessions"` list. A demo reset deletes neither users
  nor records.
- **Session records.** `{record_id, session_id, user_id, started_at, ended_at, minutes, hint_count,
  learning_event_ids}`: `minutes` rounded to one decimal, `hint_count` every `hint.created` the session
  published, `learning_event_ids` the user's words created or updated in it (first order, once each; an id
  may point at a word a later reset deleted). Written once, by `SessionService.stop()`, so a Stop, an eviction
  and a `sendBeacon` stop all leave one; a session started without a user (`demo`, an old phone) leaves none.
  `SessionRecord` is a gateway/storage model in `storage/session_record.py`, **proposed** to move to
  `packages/contracts` (Matheus) in v0.5.
- **Tests.** The existing tests pass unchanged, except `test_postgres_storage.py`'s fixture, which now also drops
  `session_records` (the new table references `users`, so `DROP TABLE users` alone would fail). The 4400 close
  reason still contains `user=ana|ben` (it now reads `user=ana|ben|<user_id>`). `FakeStorage` can fail one call
  and check the foreign key. New: `tests/unit/test_web_users.py`, `tests/unit/test_session_storage.py`,
  `tests/integration/test_web_users.py`, and a Postgres round trip (run against a throwaway `postgres:17`).
- **Not built, for the team:**
  - Training results stay in the browser, so nothing produces `USED_INDEPENDENTLY` yet.
  - No game in a web session: the secret word goes to the Home view only.
  - No sign-in. Anyone who knows a user id can read that user's words and sessions. Acceptable for the
    hackathon; listed as a risk.
  - Eviction can end another person's web session (8 live at most, D-41).
  - The intelligence was not checked with a pt-BR focus (Kauê).
  - `asks_partner` matches names only for `ana` and `ben`.
- **Owners:** gateway and storage (Luís); web (Tasnim's directory, rebuilt at Luís's request).

## D-57: Papear for companies: barge-in, a weekly digest, a sober look (2026-11-22)

*Written on `main` as D-43 (PR #23); renumbered when it was merged with `hardware` (D-58). `apps/web` still says D-43.*

**Why.** The web app (D-56) is now meant for companies, and a first round of use found four problems.
- **Barge-in.** Web sessions inherited the Pi's `MOCHI_INTERRUPTION=append` (D-40): Papear finished its answer and
  then answered the sentence that was meant to cut it off. `SessionConfig.for_session` now gives every non-demo
  session Agora's default interruption (`""`), on the first and the fallback ears. The Pi's `demo` session keeps
  `append`. Cost: the dropped-answer behaviour D-38 measured can return in a web session when someone speaks over a
  question. Unverified: with laptop speakers (no headphones) the browser's echo cancellation must keep Papear's own
  voice from cutting itself off; the mic track asks for it (`AEC`) but nobody has tried it on speakers.
- **Training.** Not reproduced. A default user (pt-BR, learning English) gets words with a meaning and the right
  owner (checked on the fake backend), and a Training round works end to end in a DOM (jsdom, typed answer, Check,
  Next). What the code can do wrong, and now does not: Training used to refresh the words only on Digest and
  Analytics; the word list was hidden when the sessions list failed or when one item was unknown; both are fixed.
  Still possible and not fixed: a hint model that answers with `meaning: null` (such words are not trainable and the
  screen says so in one small line), and words owned by the invented `guest` when the person speaks the guest's
  language (the whose-word rule, AGENTS 7.3, is Kauê's; handing those words to the person would teach them words in
  their own first language, so it was tried and left out). Needs the live `decision` log lines to settle.
- **Digest is weekly.** `/digest` is a wrap-up of one calendar week (Monday to Sunday, the browser's time zone) across
  all the person's sessions: sessions, minutes, active days, minutes per day, the change against the week before,
  words by state, and what to practise next. It uses only data the backend already stores (D-56).
- **Name and look.** The web product is **Papear**. The cartoon face became a sober status panel (monogram, state text,
  audio meter); corners and shadows are flatter. The backend, the Pi and Mochi's own lines keep "Mochi": the wake phrase
  and `asks_mochi` match only "Mochi", and the character prompt (`intelligence/`) still names itself Mochi. Whether
  Papear should answer to its own name is a decision for Kauê and the team.
- **Not built.** A company account (several people, an admin view, team totals) needs sign-in; today anyone who knows a
  user id can read that person's words (D-56). The digest is per person, not per team.

## D-58: `hardware` and `main` are one again: what was decided where they disagreed (2026-11-22)

**What happened.** While D-43 to D-55 were built on `hardware`, `main` got a rebuilt web app and, in the
backend, web users, per-user sessions and their records (PRs #22 and #23, D-56 and D-57). Both sides had
changed the same 22 backend files, and three things could not both stay as they were. Suhuai asked for the
two to be reconciled now; these are the choices, each one open to the owners' veto.

- **Session modes.** The backend says `meeting` and `review` (D-43). The web app's type guard accepted only
  `together` and `activity`, so its Start would have failed. `apps/web/src/contracts.ts` now also accepts
  `meeting` and `review` (the type and the guard, nothing else: the app never reads the mode). That is the
  only change made in `apps/web`. The game's events are still typed there and are simply never sent; the
  web app never called the game's routes.
- **Two tables called `session_records`.** The web's (one row per finished web session of a person) was
  deployed first and keeps the name. The company's (one row per meeting or review, D-45) is now
  `company_sessions`. Its contract is still called `SessionRecord`, and so is the web's Python class in
  `storage/session_record.py`: two different shapes with one name. Files that need both import the web's
  as `WebSessionRecord`. Renaming one of them for good is for Matheus and Luís.
- **Who is in a meeting.** D-44 made a meeting's participants "everyone the backend knows". With web users
  that would put every person who ever opened the web app, and `guest`, into the device's meetings. The
  roster (meeting participants, voice owners) is now the company's members; the user directory (D-56)
  knows everybody. A web user's session has its own two people (the user and `guest`), a review its one.
  `/ws?user=`, `GET /api/users/{id}` and a review accept a person from either.
- **`Storage.save_user`** replaces a user that exists (a member's languages or name can be changed, D-45);
  on `main` it left an existing user alone. No caller on `main` relied on that (a new web user always gets
  a fresh id), and the two tests that asserted it were changed.
- **The snapshot on connect** sends only the connecting person's words (D-56) and newest reports (D-54),
  no longer everyone's filtered by the hub. No `activity.state.changed` on connect: three tests of D-56
  that waited for one were changed.
- **A web user's session** is also written into the company's history (a `company_sessions` row, its
  sentences and word moments) under the one company there is. The team view counts its moments in the
  totals and the gaps; its member rows are members only. Whether a web user should belong to a company is
  the question D-57 already asks ("a company account needs sign-in").
- **Decision numbers.** `main`'s two entries were renumbered D-56 and D-57, because `hardware` had fourteen
  entries and their references in code against two.

**Checked:** the merged backend passes both sides' tests (1701) with lint, strict types and the schema
check. **Not checked here:** the web app's own tests (no Node on the Pi; CI runs them), and every company
table's SQL against a real Postgres (AGENTS 12.7), which now includes the renamed one.
