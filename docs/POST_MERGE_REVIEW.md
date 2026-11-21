# Post-merge review of d2594e6 (2026-11-21)

Scope: Suhuai's merge (#1: Pi hardware, Mochi's character, quiet hints; 92 files). Method: four read-only
reviewers (Haiku) for hardware, gateway, intelligence and config/docs; every claim then re-checked here by reading the
code or running it. Reference documents: `AGENTS.md` (v0.4) and the product deck "Mochi — Visão de Produto"
(November 2026, called "the deck" below).

Status of each claim: **confirmed** (seen in the code or run), **partial**, **refuted**, **unverified** (needs a
device or a live service; stays open).

## 1. What the deck changes about "bug" versus "feature"

The deck is a voice-first product: the session starts with "Oi, Mochi!", then the person picks a mode (Praticar,
Companhia, Jogar). In Praticar Mochi is a conversation partner. In Companhia it listens and helps in silence. In
Jogar it hosts Describe & Guess and the roles swap each round. Mobile is an after-the-session summary; AR and Watch
are add-ons. So some of what the reviewers called a conflict with AGENTS.md v0.4 is what the deck asks for.

| Bucket | Meaning |
|---|---|
| A | Code matches the deck. AGENTS.md was behind. Not reverted; AGENTS.md updated (v0.5, proposed). |
| B | A bug under both documents. Fixed in this PR with a failing test first. |
| C | Needs a team decision. Written down, not coded. |

## 2. Findings

| # | Finding | Check | Bucket | Owner |
|---|---|---|---|---|
| 1 | `.env.example` corrupted: stray line `anaged,` (line 76) and five duplicated ASR keys; the last wins so the ears become ARES | confirmed | B | Luis |
| 2 | `render.yaml` says `plan: starter`; the live service is `free` | confirmed (file); live plan is free, so nothing bills | B | Luis |
| 3 | `POST /api/devices/{id}/status` and `/voices` have no auth; `VoiceResult.name` has no length limit; `/voices` makes Mochi speak that text | confirmed | B | Luis |
| 3b | CORS `*` is not the hole (curl ignores CORS); the missing device key is | refuted as a CORS bug | B | Luis |
| 4 | Secret word reachable during a round: a wake phrase bypasses the round quiet rule, `_answer_mochi` never reads `context.activity`, `SPEAK` is let through, and only the Audience view is guarded | confirmed (code) | B | Luis, Kauê |
| 5 | "Oi Mochi, como se diz abacaxi?": `_answer_mochi` rebuilds `CaseMatch` and drops the model's language, so the hint takes the spoken focus and the owner can be the wrong person (7.3) | partial: the language drop is in the code; the end-to-end wrong owner is proven by the red test | B | Kauê |
| 6 | `wants_to_hear("Fala pra mim como foi a viagem")` is True, so Mochi repeats the last hint aloud uninvited | confirmed (run) | B | Kauê |
| 7 | The hint waits for the character reply (`gather` in `_by_rules` path, up to 6 s); AGENTS 7.2 says 2 s | confirmed (code) | B | Kauê |
| 8 | `confidence` missing or not a number counts as sure (`_doubtful`) | confirmed | B | Kauê |
| 9 | Hint-model failures return `None` with no log line | confirmed | B | Kauê |
| 10 | `Device.set_volume` always sends `unmute`, so a volume command un-mutes a muted speaker | confirmed | B | Matheus |
| 11 | In `_poll`, `_mute`, `_obey` and `_report` are outside the `try`; an exception ends the poller and the mic keeps streaming after Stop | confirmed (code) | B | Matheus |
| 12 | `WithFallback.start`: if the backend POST succeeds but start fails later, the fallback starts its own agent and the backend session is never stopped | confirmed (code) | B | Matheus |
| 13 | Fallback to a Pi-side agent is on by default (`fallback = "test_agent"`, `kind = "test_agent"`) | confirmed | B (default off) | Matheus |
| 14 | `commands` stay in the device state (last 20) for the whole session; the Pi's dedupe set is in memory, so a Pi restart replays `bye` and ends the session | confirmed (code); the restart itself is unverified on a device | B | Luis |
| 15 | Mochi can be deaf while STARTING (no wake handling; start has long waits) | partial: STARTING does not handle wake (confirmed); the 8.5 min figure is unverified | B | Matheus |
| 16 | `ActivityService.start` has no `capturing` check | reported, same pattern as the rest of the activity code | B | Luis |
| 17 | `session_service.start` takes only `_start_lock`; Stop's `_commit` section can interleave with a Start | reported; plausible, not reproduced | C | Luis |
| 18 | Sequence numbers are per hub, so one client sees gaps (6.1 says "increases by one") | confirmed (design) | C | Luis |
| 19 | `SPEAK` replies reuse `SpeakReason.ASKS_MOCHI` for voice confirmations and interrupts | confirmed | C | Luis |
| 20 | Judge on every sentence of 3+ words, `judge_every_sentence` not settable by env, hedged second call after 1 s, no call cap | confirmed (code) | C (cost vs. quality) | Kauê |
| 21 | No maximum session length; `idle_timeout` only fires after the Pi leaves | confirmed | C | Luis |
| 22 | Full transcripts in the `turn` and `ears_prompt_echo` log lines | confirmed | C (D-26 wants them for debugging) | Luis |
| 23 | `MODEL_API_KEY` is sent to Agora in the join body; Agora's 4xx text (200 bytes) is logged | key in body: confirmed (documented choice); echo in 4xx: unverified | C | Luis |
| 24 | App Certificate in `hardware/pi-bridge/.env.example` (the device could mint tokens for any channel) | confirmed | C | Matheus |
| 25 | Pi starts and ends sessions on the wake phrase; AGENTS 6.4 has the Operator's Start | confirmed | A | Matheus |
| 26 | The Pi runs the `agora-agents` Python package (Conversational AI REST client), not the RTC SDK | confirmed; AGENTS 5 only bans the Agora Python SDK on the Pi, and that package is a REST wrapper | A (wording) | Matheus |
| 27 | Wake-word and voice ID run on the Pi, mic open locally while IDLE | confirmed; audio leaves the Pi only after the wake phrase (see main.py docstring) | A (rule 4 reworded) | Matheus |
| 28 | Mochi talks when woken (D-26) and says a hint on request (D-30) | confirmed | A (deck: Praticar, "Mochi, how do I say…") | Kauê |
| 29 | New routes, `commands`, `woken_by`, `speaker`, 7-method intelligence port | confirmed | A (listed as proposed in v0.5) | Matheus, Luis |
| 30 | Prompt injection from speech into device commands (`[volume]`, `[enroll]`, `[bye]`) | reported; clamp not found in gateway | C | Luis, Matheus |
| 31 | Portuguese gaps: "como é que se diz" misses the ask pattern; "do" counted as Portuguese; ASR language `en` for Portuguese speech | reported | C (Portuguese is the next demo step) | Kauê |
| 32 | Docs: runbook still asks the Deepgram question, README "Unverified" list, ARCHITECTURE "five methods", PROVENANCE has no hardware rows | confirmed | B | Luis |

Correction to an earlier remark in this session: commits `aa8f23c` and `f4c0920` are in `main`
(they were deeper than the 12 lines of `git log` shown); nothing was lost.

## 3. Not changed here (team decisions)

- Renaming `ben` to `sophie`: the deck uses Sophie. It touches fixtures, contracts and the walkthrough; `user_id: "ben"` stays.
- Grammar feedback: the deck's Praticar mode saves `go → went`. AGENTS lists grammar as out of scope.
- Multi-expression hints (the deck shows two phrases at once): the contract has one `expression`.
- Cost switches for the judge and transcription, session length cap, and the App Certificate on the Pi.
- Mobile "learning summary" and the AR and Watch add-ons: out of the hackathon build.
- Sequence numbers per connection; Start/Stop interleaving.

## 4. Unverified (need a device, a live session or Agora)

Echo of Mochi's voice into the mic, touch, whether an empty reply keeps Agora silent, Agora's LLM timeout, whether
Agora echoes request bodies in a 4xx, the Pi restart replay, the 8.5-minute figure, live latency and billing.
