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

## D-42: the web app has its own users and sessions; session records (2026-11-21)

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
