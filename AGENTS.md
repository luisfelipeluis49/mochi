# Mochi — working context for the team and its coding agents

Copy this file to the root of the Mochi repository as `AGENTS.md`. It is written so that a coding agent can read it once and start work without reading anything else. Humans: give your agent this file plus one small task from Section 8.

- **Status:** hackathon MVP, draft contracts v0.4. Roles and stack are proposals until kickoff confirms them.
- **Full spec (for humans):** `Mochi_Product_MVP_Design_v2.1.md`. If this file and the spec disagree, this file wins for the hackathon build.
- **One rule above all:** the contracts in Section 6 are shared. Do not rename, add, or remove a field, event, endpoint, or enum value on your own. Propose it to a human.

---

## 1. What Mochi is

Mochi is a small physical companion that helps **two people practice a language with each other**. They talk to each other, not to the device. Mochi listens during a session they start, shows a **one-word hint** when one of them gets stuck, can host a short **two-player game**, and **remembers** the words each person needed.

The hackathon MVP supports **English and Brazilian Portuguese**, exactly **two people**, and **one shared microphone**.

Product rules that decide design arguments:

1. **Humans first.** Help the two people talk to each other, never to Mochi.
2. **Quiet by default.** Say and show nothing unless a hint is clearly worth it.
3. **Personal.** A saved word belongs to one person and is shown only to them.
4. **Only when started.** The microphone is live only between Start and Stop.

## 2. The MVP as one walkthrough

Two example people are used everywhere, including in tests:

- **Ana** (`user_id: "ana"`): at home in Portuguese, practicing English.
- **Ben** (`user_id: "ben"`): at home in English.

The two-minute demo, which is also the acceptance test for the whole build:

1. **Observe.** The Operator taps Start on a phone. Ana and Ben talk in English. Mochi shows a listening face and stays silent.
2. **Help.** Ana says `I need to adiar my meeting tomorrow.` Mochi's screen shows **postpone**. Ana says `I forgot my guarda-chuva at the office.` Mochi's screen shows **umbrella**. Nothing is said aloud. Each hint is saved for Ana.
3. **Play.** A round of Describe & Guess starts. Ben turns Mochi toward himself and taps its screen; it shows the secret word **umbrella**. Ben describes it ("You open it when it rains"). Ana says "umbrella". Ben taps the screen again.
4. **Remember.** Ana's phone shows two cards: *umbrella — Recalled in a game* and *postpone — Used with help*.

## 3. Glossary

| Term | Meaning |
|---|---|
| **Mochi Home** | The device: Raspberry Pi 5, EMEET M1A speakerphone, 3.5-inch touch screen, printed shell |
| **Pi bridge** | A small program on the Pi that sends the M1A microphone to Agora and plays Agora's audio back. Nothing else |
| **Agora agent** | Agora's Conversational AI Engine, started by our backend in "custom LLM" mode. It transcribes each finished sentence, calls our backend with the text, and speaks whatever text we return |
| **Turn** | One finished, transcribed sentence, delivered by Agora to our backend |
| **Backend** | Our one server process. It has two halves: `gateway` and `intelligence` |
| **Gateway** | The half that talks to Agora, the Pi, and the screens |
| **Intelligence** | The half that decides: plain functions the gateway calls |
| **Hint** | One word or short expression shown on screen to help a stuck speaker |
| **Learning event** | A saved word with its history for one person. Shown to users as a card under "My words" |
| **Home view** | The web page shown on Mochi's own screen |
| **Mobile view** | The web page shown on a person's phone |
| **Audience view** | The web page shown on the projector. It never shows a secret word |

## 4. Architecture

```text
 M1A mic/speaker
      |  audio
 Pi bridge (Agora IoT SDK, C)                      owner: Matheus
      |  audio over an Agora channel
 Agora agent (speech-to-text, text-to-speech)      configured by: Luis
      |  HTTPS: one finished sentence ("turn")
 +----------------- BACKEND (one process) -----------------+
 | gateway.receive_turn()            Luis                  |
 |      -> intelligence.decide()     Kaue                  |
 |      -> intelligence.memory.apply()   Kaue              |
 | gateway.publish()                 Luis                  |
 +---------------------------+-----------------------------+
                             |  WebSocket events
        Home view (Mochi)   Mobile view (phones)   Audience view (projector)
                             owner: Tasnim
```

- Agora hears and speaks. The backend decides. The Pi and the web pages never decide anything.
- If Mochi should speak, the backend returns text to Agora, which says it through the M1A. Most turns return nothing, and Mochi stays silent.
- The backend must be reachable at a public HTTPS address, because Agora's cloud calls it.

## 5. Repository layout and ownership

```text
mochi/
  AGENTS.md                         this file
  packages/contracts/               Matheus   example events (JSON), Python models, TypeScript types
  packages/fixtures/                Kaue      test sentences and expected decisions
  services/backend/app.py           Luis      process entry; wires gateway to intelligence
  services/backend/gateway/         Luis      Agora adapter, turn endpoint, session, devices, WebSocket
  services/backend/intelligence/    Kaue      decide(), game engine, memory
  apps/web/                         Tasnim    one web app: Home, Mobile, and Audience views
  hardware/pi-bridge/               Matheus   Agora IoT SDK audio bridge
  hardware/pi-setup/                Matheus   kiosk launch, device diagnostics
  scripts/                          Luis      start-dev.sh, say.sh, deploy.sh, reset-demo.sh
```

Default stack: Python 3 + FastAPI for the backend; React + TypeScript (Vite) for the web app; C with the Agora IoT SDK on the Pi. **Do not use the Agora Python SDK on the Pi; it crashes there.**

**An agent edits only the directory of the person who started it.** If the task seems to need a change elsewhere, stop and report what is needed.

## 6. Contracts (draft v0.4)

`packages/contracts` is the source of truth once it exists; this section is its starting content.

### 6.1 Event envelope

Every WebSocket message is one event. Only the gateway publishes; it sets every envelope field.

```json
{
  "schema_version": "0.4",
  "event_id": "evt_001",
  "type": "hint.created",
  "session_id": "demo",
  "emitted_at": "2026-11-19T16:00:04.700Z",
  "sequence": 42,
  "payload": {}
}
```

`sequence` increases by one. A client ignores an event whose `sequence` it has already applied.

### 6.2 Events

| `type` | Payload (below) | Sent to |
|---|---|---|
| `session.state.changed` | Session | every connection |
| `hint.created` | Hint | Home view, Audience view, and the target user's Mobile view |
| `hint.cleared` | `{ "hint_id" }` | same as the hint |
| `activity.state.changed` | Activity | every connection |
| `activity.private_prompt` | PrivatePrompt | **the Home view connection only** |
| `learning_event.created` / `learning_event.updated` | LearningEvent | that user's Mobile view only |
| `agent.speak.requested` | Speak | every connection (so the Home view can show "speaking") |

```json
// Session
{ "status": "active", "mode": "together", "focus": "en", "capturing": true,
  "participants": ["ana", "ben"] }

// Hint
{ "hint_id": "hint_015", "target_user_id": "ana", "target_language": "en",
  "expression": "postpone", "meaning": "adiar",
  "example": "I need to postpone my meeting.",
  "reason": "code_switch", "expires_at": "2026-11-19T16:00:12.700Z" }

// Activity
{ "activity_id": "describe_and_guess", "round_id": "round_001",
  "state": "ACTIVE_ROUND", "describer_user_id": "ben", "guesser_user_id": "ana",
  "public_instruction": "Ben describes. Ana guesses!",
  "result": null, "revealed_word": null, "word_source": "learning_event" }

// PrivatePrompt
{ "round_id": "round_001", "describer_user_id": "ben", "secret_word": "umbrella",
  "source_learning_event_id": "learn_002" }

// LearningEvent
{ "learning_event_id": "learn_002", "user_id": "ana", "target_language": "en",
  "expression": "umbrella", "meaning": "guarda-chuva",
  "detection_signal": "code_switch", "hint_id": "hint_016",
  "learning_state": "DISCOVERED",
  "state_history": [ { "learning_state": "DISCOVERED", "at": "2026-11-19T16:00:20.000Z" } ] }

// Speak
{ "text": "You can say: queue.", "language": "en", "reason": "asks_mochi" }
```

- `target_user_id` and `user_id` may be `null` when Mochi cannot tell whose word it is. A hint with no target is shown to everyone; a learning event with no user is stored but shown to nobody.
- `example` and `meaning` may be `null`.
- Screens remove a hint at `expires_at` (default: 8 seconds after it is created).
- **The secret word never appears in `activity.state.changed` while the round is active.** `revealed_word` is set only in `ROUND_RESULT`.

### 6.3 Canonical names

Use these spellings everywhere: code, tests, prompts, UI state.

| Thing | Values |
|---|---|
| Decision | `IGNORE`, `SHOW_HINT`, `SPEAK` |
| `reason` / `detection_signal` | `code_switch`, `says_unknown`, `asks_partner`, `asks_mochi`, `trails_off`, `talks_around`, `restarts`, `look_alike`, `not_understood` |
| Speak `reason` | `asks_mochi`, `activity_host` |
| Language | `en`, `pt-BR` |
| Session `status` | `created`, `active`, `paused`, `ended` |
| Session `mode` | `together`, `activity` |
| Game `state` | `IDLE`, `ACTIVE_ROUND`, `ROUND_RESULT` |
| Round `result` | `guessed`, `skipped` |
| `word_source` | `learning_event`, `stock` |
| `learning_state` | `DISCOVERED`, `ASSISTED`, `REINFORCED`, `USED_INDEPENDENTLY` |

UI labels for `learning_state`: `DISCOVERED` "Hint shown", `ASSISTED` "Used with help", `REINFORCED` "Recalled in a game", `USED_INDEPENDENTLY` "Used on your own".

### 6.4 HTTP and WebSocket (simplest form, enough for the demo)

There is one session, with id `demo`, that always exists. There is no sign-in.

```text
WebSocket
GET  /ws?user=ana | ?user=ben        Mobile view for that person
GET  /ws?device=home_pi_01           Home view on Mochi (also receives activity.private_prompt)
GET  /ws?view=audience               Audience view on the projector (public events only)
     On connect the server sends the current session state, activity state, and any live hint.

Session
POST /api/sessions/demo/start        start the Agora agent; capturing = true
POST /api/sessions/demo/stop         stop the Agora agent; capturing = false

Game
POST /api/sessions/demo/activity/start
POST /api/sessions/demo/activity/result  { "result": "guessed" | "skipped" }
     sent by the Home view: second tap = guessed, long press = skipped
     (the first tap only reveals the word on Mochi's screen and is not sent)

Device
GET  /api/devices/home_pi_01/state   polled by the Pi bridge a few times a second
     -> { "capturing": true, "agora": { "app_id", "channel", "uid", "token" }, "speaker_muted": false }
     With no live session: capturing false, agora null. The bridge then sends nothing.

Called by Agora only
POST /agora/llm/demo/chat/completions      the turn endpoint; OpenAI-compatible, streamed reply;
                                           reject requests without our shared key

Development and operator
POST /dev/sessions/demo/turn  { "text" }   handle a typed sentence exactly like a turn from Agora
POST /api/demo/reset                       clear saved words and any game; back to the start
```

Which connection gets what is enforced in the gateway, never by hiding things in the browser.

### 6.5 Functions the gateway calls (the Luís → Kauê interface)

```python
# services/backend/intelligence/
async def decide(turn: Turn, context: SessionContext) -> Decision: ...
def handle(command: ActivityCommand, context: SessionContext) -> ActivityResult: ...
def apply(proposals: list[LearningEvent]) -> list[LearningEvent]: ...   # create or update; returns stored records
def words_for(user_id: str) -> list[LearningEvent]: ...                 # newest first
```

```json
// Turn: built by the gateway from Agora's request (text = the last user message)
{ "segment_id": "seg_009", "text": "I need to adiar my meeting tomorrow",
  "received_at": "2026-11-19T16:00:04.500Z" }

// SessionContext
{ "session_id": "demo", "mode": "together", "focus": "en",
  "participants": [
    { "user_id": "ana", "comfortable_languages": ["pt-BR"], "target_language": "en" },
    { "user_id": "ben", "comfortable_languages": ["en"], "target_language": "pt-BR" } ],
  "recent_turns": [], "recent_hints": [], "activity": null,
  "learning_events": { "ana": [], "ben": [] } }

// Decision
{ "decision": "SHOW_HINT", "hint": { ...Hint }, "speak": null,
  "learning_events": [ { ...LearningEvent } ] }
```

- A turn arrives with **no speaker and no language**. One microphone is one voice as far as Agora knows.
- `IGNORE`: `hint` and `speak` are null. `SHOW_HINT`: `hint` set. `SPEAK`: `speak` set, and `hint` may also be set.
- For `IGNORE` and `SHOW_HINT` the gateway returns an **empty reply** to Agora so Mochi stays silent. For `SPEAK` it returns `speak.text`.
- `handle()` is a pure function. It returns the new round state; the gateway keeps it in memory and passes it back in `context.activity`.
- `decide()` and `handle()` create `hint_id`, `learning_event_id`, and `round_id` (any unique string). The gateway creates `segment_id` and all envelope fields.

## 7. Behavior rules

### 7.1 Nine ways a person gets stuck on a word

`decide()` looks for these. Cases 1–4 are clear and are built first, with rules. Cases 5–9 are subtle and are added next, with one fast model call judging the sentence in context.

| # | `reason` | Case | Example turn | Result |
|---|---|---|---|---|
| 1 | `code_switch` | Switches language mid-sentence | `I need to adiar my meeting.` | hint **postpone** |
| 2 | `says_unknown` | Says they do not know the word | `How do you say… the thing for the rain?` | hint **umbrella** |
| 3 | `asks_partner` | Asks their partner | `Ben, como se diz recibo?` | hint **receipt** |
| 4 | `asks_mochi` | Asks Mochi ("Hi Mochi" / "Oi Mochi") | `Oi Mochi, what's the word for fila?` | `SPEAK` + hint **queue** |
| 5 | `trails_off` | Trails off | `It's raining and I forgot my… um…` | hint **umbrella** |
| 6 | `talks_around` | Describes the word instead of saying it | `The paper they give you when you pay.` | hint **receipt** |
| 7 | `restarts` | Keeps restarting | `We should… we need to… make it later.` | hint **postpone** |
| 8 | `look_alike` | Uses a false friend | `I pretend to travel in July.` | hint **intend** |
| 9 | `not_understood` | The partner did not understand | previous turn unclear, then `Sorry, what do you mean?` | hint: the word the speaker was reaching for |

### 7.2 When to return `IGNORE`

- Someone is just thinking, or corrects themselves in the same turn.
- A deliberate language switch: a name, a dish, a place.
- A small slip that did not block understanding. The MVP helps with words and short expressions, not grammar.
- The conversation is personal or serious.
- A hint was shown for one of the last two turns (cooldown).
- A game round is active, unless the turn is a wake phrase.
- The model call takes longer than two seconds.

Match the wake phrase loosely: speech-to-text writes "Moshi", "Mochie", "Motchi".

### 7.3 Whose word is it

When exactly one participant is learning the language being spoken, a word from that person's comfortable language belongs to them. A Portuguese word inside English speech is Ana's. If the rule does not apply, return the hint with `target_user_id: null` and the learning event with `user_id: null`.

### 7.4 Learning states

| When | New `learning_state` |
|---|---|
| A hint is shown or an answer is spoken | `DISCOVERED` (create the learning event now) |
| In `together` mode, the expression is said within the next three turns | `ASSISTED` |
| A game round using that word ends with `guessed` | `REINFORCED` |

Every change appends to `state_history`. There is no "mastered" state and no score.

### 7.5 Describe & Guess, on Mochi's touch screen

Mochi's screen takes touch, but it is a basic panel: **the only control is a tap anywhere on the screen, plus a long press.** No small buttons.

| Game `state` | Home view shows | Input |
|---|---|---|
| `IDLE` | face | — |
| `ACTIVE_ROUND`, word hidden | "Ben, turn me to you and tap" | tap → reveal |
| `ACTIVE_ROUND`, word revealed | the secret word + "tap when Ana gets it" | tap → guessed; long press → skipped |
| `ROUND_RESULT` | the word + "Ana got it!" for a few seconds, then back to the face | — |

- The Audience view shows who describes and who guesses, and the word only in `ROUND_RESULT`.
- Whether the word is currently revealed is local state of the Home view; the server only needs the second tap.
- Word choice: first a stock list of tangible words (umbrella, suitcase, corkscrew). From M4, the newest **describable** word in the guesser's learning events; the partner describes it and the learner guesses.

## 8. Milestones: what to build, in order

Every milestone after M0 is a complete demo. All four owners build the same milestone at the same time. A milestone is reached only when it has been seen working on the real devices.

| | **M0 It hears us** | **M1 Mochi helps** | **M2 Mochi remembers** | **M3 Mochi plays** | **M4 The word comes back** |
|---|---|---|---|---|---|
| **Matheus** `hardware/` | Bridge sends M1A audio to an Agora channel and plays audio back. A web page shows on the Pi's screen | Bridge polls the device state; microphone on only while `capturing` | Runs the real path after every change | Touch events from the Pi's screen reach the page reliably | Printed shell if ready |
| **Luís** `gateway/` | Agora agent whose turns reach the backend log; empty reply keeps Mochi silent. `/dev/.../turn` and `scripts/say.sh` | Start/Stop, device state, WebSocket routing per connection, reset | Publish learning events to the right Mobile view | Activity endpoints; private prompt to the Home view only; one spoken line through Agora | Operator commands; one log line per turn, decision, and event |
| **Kauê** `intelligence/` | One-rule `decide()`: text contains "adiar" → hint "postpone" | Cases 1–4, the quiet rules, whose-word rule; then cases 5–9 | `apply()` and `words_for()`; `DISCOVERED` on every hint; `ASSISTED` upgrade | `handle()` with three states and a stock word | Word from the guesser's learning events; `REINFORCED` on `guessed` |
| **Tasnim** `apps/web/` | Home and Mobile views each show one real `hint.created` | Start/Stop on Mobile; listening face and expiring hint on Home | "My words" page, updating live | Game states on Home with tap and long press; Audience view | State path on each card; projector layout |
| **Seen working when** | A sentence spoken into the M1A puts a word on Mochi's screen and a phone | Start, say both demo sentences, see both hints; ordinary talk shows nothing; Stop, and the Pi sends nothing | Both hints appear as cards on Ana's phone and not on Ben's | A round runs on Mochi's screen from tap to result | The game brings back "umbrella" and its card reads "Recalled in a game" |

Build the simplest thing that satisfies the row. Not in scope unless a human asks: sign-in, access tokens, a database (keep state in memory), reconnect and replay, pause and resume, multiple sessions, the phone as a microphone, smart glasses, solo practice, grammar correction, fluency scores.

## 9. Starting guides, one per owner

### 9.1 Matheus — `hardware/pi-bridge`, `hardware/pi-setup`, `packages/contracts`

- **First task (M0):** a C program using the Agora IoT SDK that joins a channel given on the command line, sends the M1A microphone, and plays received audio through the M1A. Then a kiosk script that opens the Home view full screen on the 3.5-inch display with screen blanking off.
- **M1:** poll `GET /api/devices/home_pi_01/state`; join and send only while `capturing` is true; leave the channel otherwise; respect `speaker_muted`.
- **Test:** speak into the M1A and see the sentence in the backend log; trigger a spoken reply and hear it; confirm Mochi's own voice does not come back as a new turn.
- **Do not:** put decisions, transcription, or UI in the bridge. Do not use the Agora Python SDK.
- **Contracts:** keep `packages/contracts` equal to Section 6: one JSON example per event, Python models, TypeScript types, and a test in each language that loads every example.

### 9.2 Luís — `services/backend/gateway`, `services/backend/app.py`, `scripts/`

- **First task (M0):** start an Agora Conversational AI agent in custom-LLM mode pointed at `POST /agora/llm/demo/chat/completions`, with greeting, failure message, and silence prompt off. In that endpoint, log the last user message and return an empty streamed reply. Add `POST /dev/sessions/demo/turn` and `scripts/say.sh "<sentence>"`.
- **Every turn, in order:** check the shared key → take the text → `await decide()` → `apply()` any learning events → publish events to the right connections → reply to Agora with `speak.text` or nothing.
- **Test:** `scripts/say.sh "I need to adiar my meeting tomorrow"` produces a `hint.created` on a connected `?user=ana` socket and not on `?user=ben`'s private stream.
- **Do not:** write rules about when Mochi helps, or store learning events yourself. Keep every Agora call in one adapter module with a mock mode.
- **Unknown to settle first:** whether an empty reply keeps the agent silent. If it does not, set `speaker_muted` in the device state except while a `SPEAK` reply is playing.

### 9.3 Kauê — `services/backend/intelligence`, `packages/fixtures`

- **First task (M0):** `decide()` that returns `SHOW_HINT` "postpone" for a turn containing "adiar" and `IGNORE` otherwise, with a test for each.
- **M1:** cases 1–4 from Section 7.1 with rules; the quiet rules in 7.2; the whose-word rule in 7.3. One model call (behind an adapter, two-second limit) writes `expression`, `meaning`, and `example`. Then add cases 5–9, one at a time, each with fixtures.
- **Fixtures:** for every case, at least three sentences that should produce a hint and three near-misses that should not. Include both demo sentences.
- **Test:** everything runs with `pytest` on a laptop. No server, no Agora, no microphone.
- **Do not:** import from `gateway`, open sockets, or call Agora.

### 9.4 Tasnim — `apps/web`

- **First task (M0):** a page at `/home` and a page at `/m` that open the WebSocket and render a `hint.created` event. Keep a small mock source in the app that replays the example events from `packages/contracts`, for working when the backend is down.
- **Home view (`/home?device=home_pi_01`):** 3.5-inch screen. A few static full-screen states with very large text and no animation: listening face, hint (the `expression` only), speaking, the game states in Section 7.5. Input is a tap anywhere and a long press.
- **Mobile view (`/m?user=ana`):** Start and Stop; a live hint with meaning and example; "My words" cards with the state label, the state path, and a fixed next-step line.
- **Audience view (`/audience`):** a large version of Mochi's screen for the projector that never shows a secret word before `ROUND_RESULT`.
- **Also:** `?debug=1` on any view lists the last ten events received. English and Brazilian Portuguese copy.
- **Do not:** implement AI, speech, or storage. Do not decide visibility in the browser.

## 10. Rules for coding agents

1. One small task per run, taken from the current milestone. Do not build ahead.
2. Edit only your owner's directory. Never edit `packages/contracts` unless your owner is Matheus and the task says so.
3. Import types from `packages/contracts`. Never redefine an event shape locally.
4. Use the names in Section 6.3 exactly.
5. Every change comes with a test or a one-command way to see it work.
6. No secrets in code, commits, or logs. Read keys from environment variables.
7. Do not add dependencies, services, or build steps without saying so in your report.
8. If a requirement is unclear or seems to conflict with this file, stop and ask. Do not guess and do not redesign.
9. Finish with a short report: files changed, how to run it, what you tested, what is still open.

## 11. Running and testing

```text
scripts/start-dev.sh            start the backend and the web app locally
scripts/say.sh "<sentence>"     send a typed sentence to the backend as if Agora had heard it
scripts/reset-demo.sh           clear saved words and any game
pytest services/backend         backend and intelligence tests
npm test --prefix apps/web      web app tests
```

Environment variables (names are proposals): `AGORA_APP_ID`, `AGORA_APP_CERTIFICATE`, `AGORA_REST_KEY`, `AGORA_REST_SECRET`, `MOCHI_TURN_KEY`, `MODEL_API_KEY`, `MOCHI_PUBLIC_URL`.

When the real path breaks, find the last step that left a trace: bridge log (Matheus) → backend log line for the turn (Luís) → decision line (Kauê) → published-event line (Luís) → `?debug=1` list and the screen (Tasnim).

## 12. Things nobody has verified yet

Do not write code that assumes these work. If your task depends on one, say so in your report.

1. **Silent replies.** That an empty reply from the turn endpoint keeps the Agora agent silent.
2. **Mixed-language transcription.** That `adiar` and `guarda-chuva` survive speech-to-text inside English sentences.
3. **Audio both ways on the Pi**, without Mochi hearing its own voice.
4. **Touch.** That a tap anywhere on the 3.5-inch screen registers every time in the kiosk browser.
