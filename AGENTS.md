# Mochi — working context for the team and its coding agents

This file is the root `AGENTS.md` of the repository. It is written so that a coding agent can read it once and start work without reading anything else. Humans: give your agent this file plus one small task from Section 8.

- **Status:** hackathon MVP. Contracts **v0.7, proposed on 2026-11-21** with the product change below (DECISIONS D-43 to D-45) and waiting for the owners' sign-off; see the changelog at the end. Everything marked *proposed* in v0.5 and v0.6 that survived is still proposed.
- **What changed on 2026-11-21:** the product is now language learning for companies. Mochi sits in a company's meetings. There are two kinds of session, **Meeting** and **Review**, plus a **company view** for administrators. **The game (Describe & Guess, "Jogar") is gone**, and so is the three-way choice after the wake phrase.
- **What changed on 2026-11-22 (later, D-51 to D-55, proposed):** a meeting now has a **live transcript**; a **code switch** is marked in it for everyone; **idioms and technical terms** are explained to the people listening; after Stop each person gets a private **report** of what was wrong in what they said; and a saved word said later with no hint becomes **"Used on your own"**.
- **Older documents:** `Mochi_Product_MVP_Design_v2.1.md`, the deck "Mochi — Visão de Produto" and `vision/Mochi_Product_Vision.md` describe the earlier consumer product (three modes, a game, watch and glasses add-ons). Where they disagree with this file, this file wins.
- **One rule above all:** the contracts in Section 6 are shared. Do not rename, add, or remove a field, event, endpoint, or enum value on your own. Propose it to a human.

---

## 1. What Mochi is

Mochi helps people who work in a language they are still learning. It is a companion: the small device on the meeting table (Mochi Home), or a phone running the Mochi app. People register their voice in advance. In a meeting Mochi follows what each person says, notices when someone is stuck on a word, and shows that word, without a sound. Later each person looks at their own progress on their phone and goes over their words with Mochi. The company's administrators see how the team is doing as a whole.

| Session | What Mochi does | Who talks | Where |
|---|---|---|---|
| **Meeting** (`meeting`) | Listens while people work; shows a **one-word hint** when someone is stuck; speaks only when asked by name | colleagues ↔ colleagues | Mochi Home on the table, or one phone as the microphone |
| **Review** (`review`) | Brings back the words a person needed in their meetings, one at a time, as a conversation partner | one person ↔ Mochi | that person's phone |

Around the sessions:

- **My words / analytics** (phone): each person's saved words, how far each one got, and the moments they needed them.
- **Team view** (phone, administrators): every member's learning data added up: the expressions the team needs most, the mistakes it shares, who is active, how many words stick. This is also what makes Mochi better for a company over time: the words its people need at work are known.

It **remembers** the words each person needed. The core of the MVP is the meeting: it proves that Mochi follows a real conversation between people, tells them apart, acts at the right time and makes it useful.

The hackathon MVP supports **English and Brazilian Portuguese**, **one company** per deployment, and **one shared microphone** per session. The two demo people are always there; a company adds its own members (Section 6.7). Mochi AR (hints on glasses, `apps/glasses`) still works as before and is not part of the hackathon build.

Product rules that decide design arguments:

1. **Humans first.** In a meeting, help people talk to each other, never to Mochi. Talking to Mochi is the point only in a review, or when someone asks it something.
2. **Quiet by default.** In a meeting, say nothing unless someone asked Mochi by name, and put a word on the screen only when it is clearly worth it: a hint for someone who is stuck, or what an idiom or a technical term means (7.6). The live transcript (6.2) is the one thing shown all the time, small, and it can be switched off. When someone asked Mochi to speak for them (7.9) it says every sentence in the other language until someone says stop. The web app's quiet listener (D-62) may also explain an idiom or a wrong expression aloud, unasked, in a sentence or two; the device never does.
3. **Personal.** A saved word, what is kept of what a person said, and what Mochi noticed was wrong in it (their report, 7.7) belong to that person and are shown only to them. The company sees numbers: how many people needed an expression or share a kind of mistake, never who, and never anyone's sentences. *The live transcript is not a store:* a sentence is shown, as it is said, to the screens of the session it was said in (the people there heard it), and that is all.
4. **Only when started.** No audio leaves the device before the wake phrase ("Oi, Mochi" / "Hey, Mochi") or Start, and none after Stop. The Pi may listen **locally** for the wake phrase; that audio is not recorded or sent anywhere. No audio is stored. **Since 2026-11-22 (D-46) the sentences of a session are stored**, each with the person whose registered voice said it; a person can read their own, nobody can read another's, and a sentence no known voice said has no reader at all once the session is over (while it runs it is in the live transcript like any other).

## 2. The MVP as one walkthrough

Two example people are used everywhere, including in tests:

- **Ana** (`user_id: "ana"`): at home in Portuguese, working in English. She is the demo company's administrator.
- **Ben** (`user_id: "ben"`): at home in English.

The demo, which is also the acceptance test for the whole build:

1. **Register.** Before the meeting each person tells Mochi their name once ("Mochi, learn my voice. I'm Ana") and it learns the voice.
2. **Observe.** Someone says "Oi, Mochi!" or "Hey, Mochi!" (or taps Start on a phone). Mochi says one short line ("Hi! I'm listening. Call me if you need a word.") and the meeting begins. Ana and Ben talk in English. Mochi shows a listening face and stays silent.
3. **Help.** Ana says `I need to adiar my meeting tomorrow.` Mochi's screen shows **postpone**. Ana says `I forgot my guarda-chuva at the office.` Mochi's screen shows **umbrella**. Nothing is said aloud. Each hint is saved for Ana, with the moment she needed it.
4. **Remember.** Ana goes on: `Right, I need to postpone it.` After the meeting her phone shows two cards: *postpone — Used with help* and *umbrella — Hint shown*. Ben's phone shows neither.

   *Also, since D-51 to D-54 (proposed):* every sentence appears on the screens as it is said, and `adiar` is marked in Ana's with `postpone` next to it, for Ben too. When Ben says `Let's circle back on pricing after the launch.`, Mochi's screen shows **circle back**, *voltar ao assunto depois*. After Stop, Ana's phone (only hers) gets a report: `I finish the slides yesterday.` → `I finished the slides yesterday.`, with one line of why.
5. **Review.** Later Ana starts a review on her phone. Mochi asks for the word through its meaning ("Yesterday you needed the word for guarda-chuva. Do you remember it?"). Ana says "umbrella"; the card reads *Recalled in a review*.
6. **The company sees.** Ana, as administrator, opens the team view: two meetings this week, the expressions the team needed most, how many of them people went on to use. No names next to the words.

## 3. Glossary

| Term | Meaning |
|---|---|
| **Mochi** | The product: language learning for companies, in their own meetings. Also its companion, as people meet it: the device and the voice |
| **Mochi Home** | The device: Raspberry Pi 5, EMEET M1A speakerphone, 3.5-inch screen, printed shell |
| **Pi bridge** | The program on the Pi: it listens locally for the wake phrase, then sends the M1A microphone to Agora and plays Agora's audio back, follows the backend's device state, applies the device commands, and tells the backend whose registered voice it hears. It never decides when Mochi helps |
| **Agora agent** | Agora's Conversational AI Engine, started by our backend in "custom LLM" mode. It transcribes each finished sentence, calls our backend with the text, and speaks whatever text we return |
| **Turn** | One finished, transcribed sentence, delivered by Agora to our backend |
| **Session** | Start to Stop: a **meeting** or a **review** |
| **Backend** | Our one server process. It has two halves, `gateway` and `intelligence`, and the `team` package |
| **Gateway** | The half that talks to Agora, the Pi, and the screens |
| **Intelligence** | The half that decides: plain functions the gateway calls |
| **Hint** | One word or short expression shown on screen to help a stuck speaker |
| **Learning event** | A saved word with its history for one person. Shown to users as a card under "My words" |
| **Word moment** | One time someone needed a word. A learning event is one card per person and word; a moment is every occurrence |
| **Session record** | One session as the analytics keep it: when, who was there, how many sentences each recognised voice said |
| **Utterance** | One finished sentence of a session, stored with the person whose registered voice said it (or nobody) |
| **Company, member** | A company that uses Mochi and the people in it; a member is `admin` or `member` |
| **Team view** | The administrators' page: the members' learning data added up |
| **Transcript line** | One finished sentence as the screens of a session get it while it is said, with what Mochi noticed in it (**marks**) |
| **Mark** | Something noticed in a sentence: a code switch, or an idiom or technical term with what it means |
| **Conversation report** | What Mochi noticed was wrong in ONE person's speech in ONE session, written after Stop, for that person only |
| **Home view** | The web page shown on Mochi's own screen |
| **Mobile view** | The web page shown on a person's phone |
| **Audience view** | The web page shown on the projector |

## 4. Architecture

```text
 M1A mic/speaker                         a phone's microphone (its own session)
      |  audio                                |
 Pi bridge (Agora IoT SDK, C)                 |            owner: Matheus
      |  audio over an Agora channel          |
 Agora agent (speech-to-text, text-to-speech)              configured by: Luis
      |  HTTPS: one finished sentence ("turn")
 +----------------- BACKEND (one process) -----------------+
 | gateway.receive_turn()            Luis                  |
 |      -> intelligence.decide()     Kaue                  |
 |      -> intelligence.memory.apply()   Kaue              |
 |      -> team.journal (who spoke, who needed a word)     |
 | gateway.publish()                 Luis                  |
 | team: ledger + team view          (D-45)                |
 +---------------------------+-----------------------------+
            |  WebSocket events             |  HTTP: company routes
   Home view (Mochi)   Mobile view (phones)   Audience view (projector)
                             owner: Luis (was Tasnim)
```

- Agora hears and speaks. The backend decides. The Pi and the web pages never decide anything.
- If Mochi should speak, the backend returns text to Agora, which says it through the M1A (or the phone). Most turns return nothing, and Mochi stays silent.
- The Pi recognises registered voices locally and tells the backend whose voice it hears; the backend puts that person on the turn (Section 6.5).
- The backend must be reachable at a public HTTPS address, because Agora's cloud calls it.

## 5. Repository layout and ownership

```text
mochi/
  AGENTS.md                         this file
  packages/contracts/               Matheus   example events (JSON), Python models, JSON Schema
  packages/fixtures/                Kaue      test sentences and expected decisions
  services/backend/app.py           Luis      process entry; wires gateway to intelligence
  services/backend/gateway/         Luis      Agora adapter, turn endpoint, session, devices, WebSocket, company routes
  services/backend/intelligence/    Luis      decide(), review rules, memory (was Kaue; Luis since 2026-11-22, D-68)
  services/backend/team/            (new, D-45: owner to be agreed)   ledger, session journal, team view
  services/backend/storage/         Luis      Postgres / local file / memory
  apps/web/                         Luis      (was Tasnim; Luis since 2026-11-22, D-68) the Mochi web app: Onboarding, Session, Training, Digest, Analytics (D-56, D-57)
  apps/glasses/                     Suhuai    Mochi AR (outside the hackathon build)
  hardware/pi-bridge/               Matheus   Agora IoT SDK audio bridge
  hardware/pi-setup/                Matheus   kiosk launch, device diagnostics
  scripts/                          Luis      start-dev.sh, say.sh, deploy.sh, reset-demo.sh
  docs/TEAM_VIEW.md                           the company data model and its API, for whoever builds the screens
```

Default stack: Python 3 + FastAPI for the backend; React + TypeScript (Vite) for the web app; C with the Agora IoT SDK on the Pi. **Do not use the Agora Python RTC SDK on the Pi; it crashes there.** (The Pi may use `agora-agents`, a REST client for the Conversational AI Engine, only as an explicit, off-by-default fallback.)

**Since 2026-11-22 (D-68) `services/backend/intelligence/` and `apps/web/` are Luís's, together with `gateway/`, `storage/` and `scripts/`; the Kauê and Tasnim columns and guides below are history.** **An agent edits only the directory of the person who started it.** If the task seems to need a change elsewhere, stop and report what is needed.

## 6. Contracts (draft v0.7, proposed)

`packages/contracts` is the source of truth; this section mirrors it. **v0.7 is a breaking change for the web app** (it removes the game's events and renames the session modes): `apps/web` still speaks v0.4 until its owners move it (the list of what changes for it is in `docs/TEAM_VIEW.md`, "For the web app").

### 6.1 Event envelope

Every WebSocket message is one event. Only the gateway publishes; it sets every envelope field.

```json
{
  "schema_version": "0.7",
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
| `session.state.changed` | Session | every connection of that session |
| `hint.created` | Hint | Home view, Audience view, and the target user's Mobile view |
| `hint.cleared` | `{ "hint_id" }` | same as the hint |
| `learning_event.created` / `learning_event.updated` | LearningEvent | that user's Mobile view only |
| `agent.speak.requested` | Speak | every connection (so the Home view can show "speaking") |
| `transcript.line` *(proposed, D-51)* | TranscriptLine | every connection of that session except AR glasses; meetings only, never a review |
| `conversation.report.created` *(proposed, D-54)* | ConversationReport | that user's Mobile view only, whichever session it follows |
| `phrase.suggested` *(proposed, D-59)* | SuggestedPhrase | same as the hint it follows |

`activity.state.changed` and `activity.private_prompt` no longer exist (v0.7).

```json
// Session
{ "status": "active", "mode": "meeting", "focus": "en", "capturing": true,
  "participants": ["ana", "ben"] }

// Hint
{ "hint_id": "hint_015", "target_user_id": "ana", "target_language": "en",
  "expression": "postpone", "meaning": "adiar",
  "example": "I need to postpone my meeting.",
  "reason": "code_switch", "expires_at": "2026-11-19T16:00:12.700Z" }

// LearningEvent
{ "learning_event_id": "learn_002", "user_id": "ana", "target_language": "en",
  "expression": "umbrella", "meaning": "guarda-chuva",
  "detection_signal": "code_switch", "hint_id": "hint_016",
  "learning_state": "DISCOVERED",
  "state_history": [ { "learning_state": "DISCOVERED", "at": "2026-11-19T16:00:20.000Z" } ] }

// Speak
{ "text": "You can say: queue.", "language": "en", "reason": "asks_mochi" }

// TranscriptLine (proposed, D-51): one finished sentence, sent when its turn has been handled
{ "utterance_id": "seg_009", "user_id": "ana", "text": "I need to adiar my meeting tomorrow",
  "at": "2026-11-19T16:00:04.500Z",
  "marks": [ { "kind": "code_switch", "text": "adiar", "gloss": "postpone", "plain": null } ] }

// SuggestedPhrase (proposed, D-59): the whole sentence a stuck speaker was reaching for; see 7.8
{ "hint_id": "hint_017", "target_user_id": "ana", "language": "en",
  "text": "We need to unblock the authentication process.", "expires_at": "2026-11-19T16:00:26.700Z" }

// ConversationReport (proposed, D-54): one person, one session; see 7.7
{ "report_id": "rep_001", "company_id": "demo", "record_id": "rec_001", "user_id": "ana",
  "target_language": "en", "mode": "meeting",
  "started_at": "2026-11-19T16:00:00.000Z", "ended_at": "2026-11-19T16:30:00.000Z", "speaking_minutes": 6.5,
  "my_sentences": [ { "utterance_id": "seg_014", "at": "2026-11-19T16:04:10.000Z",
                      "text": "I finish the slides yesterday.", "better": "I finished the slides yesterday.", "topic": "verb_tense" } ],
  "mistakes": [ { "kind": "grammar", "topic": "verb_tense", "said": "I finish the slides yesterday.",
                  "better": "I finished the slides yesterday.", "explanation": "Com \"yesterday\" o verbo vai para o passado: finished.", "count": 1 } ],
  "unknown_words": [ { "expression": "postpone", "meaning": "adiar", "said_instead": "I need to adiar my meeting tomorrow", "times": 1 } ],
  "strengths": ["Você explica bem o seu trabalho."], "focus_next": ["Passado dos verbos regulares: finished, sent."] }
```

- A `transcript.line` with an `utterance_id` a screen already has replaces that line: it is sent a second time when an idiom or a term in it was explained (`marks` grew). `user_id` is `null` when no known voice said it. Lines are not replayed on connect.
- A mark's `text` is the part of the sentence it is about; `gloss` is what to show next to it (a code switch: the word in the language being spoken; an idiom or term: its meaning in the other language); `plain`, for an idiom or term, says it in everyday words of the language spoken.
- On connect a phone also gets its person's five newest reports as `conversation.report.created`; the rest is `GET /api/users/{id}/reports`.

- In the device's meeting `participants` is the company's members; in a web user's session it is that user and `guest`; in a review it is the one person reviewing. `focus` is English in the device's meeting, else the language that person is learning.
- `target_user_id` and `user_id` may be `null` when Mochi cannot tell whose word it is. A hint with no target is shown to everyone; a learning event with no user is stored but shown to nobody.
- `example` and `meaning` may be `null`.
- Screens remove a hint at `expires_at` (default: 8 seconds after it is created).

### 6.3 Canonical names

Use these spellings everywhere: code, tests, prompts, UI state.

| Thing | Values |
|---|---|
| Decision | `IGNORE`, `SHOW_HINT`, `SPEAK` |
| `reason` / `detection_signal` | `code_switch`, `says_unknown`, `asks_partner`, `asks_mochi`, `trails_off`, `talks_around`, `restarts`, `look_alike`, `not_understood` |
| Speak `reason` | `asks_mochi` |
| Language | `en`, `pt-BR` |
| Session `status` | `created`, `active`, `paused`, `ended` |
| Session `mode` | `meeting`, `review` |
| Member `role` | `admin`, `member` |
| `learning_state` | `DISCOVERED`, `ASSISTED`, `REINFORCED`, `USED_INDEPENDENTLY` |
| Mark `kind` *(proposed)* | `code_switch`, `idiom`, `technical_term` |
| Mistake `kind` *(proposed)* | `grammar`, `word_choice`, `false_friend` |
| Mistake `topic` *(proposed)* | `verb_tense`, `verb_form`, `agreement`, `articles`, `prepositions`, `pronouns`, `plurals`, `word_order`, `word_choice`, `false_friend`, `other` |

Removed in v0.7: session modes `together` and `activity`, Speak reason `activity_host`, and the game's `state`, `result` and `word_source` values.

UI labels for `learning_state`: `DISCOVERED` "Hint shown", `ASSISTED` "Used with help", `REINFORCED` "Recalled in a review", `USED_INDEPENDENTLY` "Used on your own".

### 6.4 HTTP and WebSocket (simplest form, enough for the demo)

The session with id `demo` always exists: it is Mochi Home's. Any other id is a session a phone opens (D-41). There is no sign-in.

```text
WebSocket
GET  /ws?user=<user_id>              Mobile view for that person (any known person, not only ana and ben)
GET  /ws?device=home_pi_01           Home view on Mochi
GET  /ws?view=audience               Audience view on the projector
     On connect the server sends the current session state, any live hint, and that person's saved words.

Session
POST /api/sessions/{id}/start        start the Agora agent; capturing = true. Body (optional):
                                     { "woken_by": "oi mochi" }                 the device heard its wake phrase
                                     { "mode": "review", "user_id": "ana" }     Ana's review; without `mode`: a meeting
                                     A review for an unknown or missing user_id: 422.
POST /api/sessions/{id}/stop         stop the Agora agent; capturing = false
POST /api/sessions/{id}/interrupt    someone is talking over Mochi: its voice stops at once and it just listens (D-50)
                                     -> { "interrupted": true | false }
POST /api/sessions/{id}/hints/{hint_id}/say    one touch: Mochi says aloud the sentence suggested after that hint (D-59)
                                     -> { "said": true | false }   once per suggestion, while it is fresh (20 s)
GET  /api/sessions/{id}/agora        where a phone joins that session's channel as its microphone

Device
GET  /api/devices/home_pi_01/state   polled by the Pi bridge a few times a second
     -> { "capturing": true, "agora": { "app_id", "channel", "uid", "token" }, "speaker_muted": false, "commands": [] }
     With no live session: capturing false, agora null. The bridge then sends nothing.

Company (Section 6.7)
GET  /api/companies/{company_id}/members?viewer=<user_id>
POST /api/companies/{company_id}/members?viewer=<user_id>
GET  /api/companies/{company_id}/insights?viewer=<user_id>&days=30
GET  /api/companies/{company_id}/sessions?viewer=<user_id>
POST /api/users                      a person of the web app (6.6, D-56); GET /api/users/{user_id}, .../words, .../sessions
GET  /api/users/{user_id}/moments?viewer=<user_id>
GET  /api/users/{user_id}/utterances?viewer=<user_id>
GET  /api/users/{user_id}/reports?viewer=<user_id>      that person's conversation reports, newest first (D-54)

Called by Agora only
POST /agora/llm/{id}/chat/completions      the turn endpoint; OpenAI-compatible, streamed reply;
                                           reject requests without our shared key

Development and operator
POST /dev/sessions/{id}/turn  { "text" }   handle a typed sentence exactly like a turn from Agora
POST /api/demo/reset                       clear saved words, session records and word moments; back to the start
```

The game's routes (`POST /api/sessions/{id}/activity/start|result`) no longer exist. Which connection gets what is enforced in the gateway, never by hiding things in the browser.

### 6.5 Functions the gateway calls (the Luís → Kauê interface)

```python
# services/backend/intelligence/
async def decide(turn: Turn, context: SessionContext) -> Decision: ...
def apply(proposals: list[LearningEvent]) -> list[LearningEvent]: ...   # create or update; returns stored records
def words_for(user_id: str) -> list[LearningEvent]: ...                 # newest first
```

`handle()` (the game) is gone.

Four more, proposed with D-53 to D-55 and D-59 (the port has eleven methods now):

```python
async def explain(turn: Turn, context: SessionContext) -> TranscriptMark | None: ...   # an idiom or term in the sentence; asked AFTER the turn was handled
async def suggest(turn: Turn, context: SessionContext, hint: Hint) -> str | None: ...   # the whole sentence the speaker was reaching for; asked AFTER the turn was handled
async def coach(draft: ConversationReport, person: Participant) -> ConversationReport | None: ...   # after Stop; None: no report
def used_alone(said: list[Utterance], shown: list[str], began: str) -> list[LearningEvent]: ...   # after a meeting; `shown`: every word a screen showed in it; proposals for apply()
```

```json
// Turn: built by the gateway from Agora's request (text = the last user message)
{ "segment_id": "seg_009", "text": "I need to adiar my meeting tomorrow",
  "received_at": "2026-11-19T16:00:04.500Z", "speaker_user_id": "ana" }

// SessionContext
{ "session_id": "demo", "mode": "meeting", "focus": "en",
  "participants": [
    { "user_id": "ana", "comfortable_languages": ["pt-BR"], "target_language": "en" },
    { "user_id": "ben", "comfortable_languages": ["en"], "target_language": "pt-BR" } ],
  "recent_turns": [], "recent_hints": [],
  "learning_events": { "ana": [], "ben": [] } }

// Decision
{ "decision": "SHOW_HINT", "hint": { ...Hint }, "speak": null,
  "learning_events": [ { ...LearningEvent } ] }
```

- A turn arrives with **no language**. `speaker_user_id` (proposed, D-44, D-46) is the person whose registered voice said the sentence, worked out by the gateway from the stretches of speech the device reports (`heard` in the device status, below); `null` when no known voice said it, when two people shared the sentence, or on a phone's microphone, which does not recognise voices. In a review it is always the reviewer.
- `IGNORE`: `hint` and `speak` are null. `SHOW_HINT`: `hint` set. `SPEAK`: `speak` set, and `hint` may also be set.
- For `IGNORE` and `SHOW_HINT` the gateway returns an **empty reply** to Agora so Mochi stays silent. For `SPEAK` it returns `speak.text`.
- `decide()` creates `hint_id` and `learning_event_id` (any unique string). The gateway creates `segment_id` and all envelope fields.

### 6.6 Additions from v0.5 and v0.6 that remain (proposed; owners: Matheus for the shapes, Luís for the gateway)

```text
POST /api/devices/home_pi_01/status  { "volume": 80, "temperature": 52.4, "voices": ["Ana"], "speaker": "Ana" }
POST /api/devices/home_pi_01/voices  { "name": "Ana", "language": "en" | "pt", "learned": true }
GET  /api/devices/home_pi_01/voices                      every registered voice with its voiceprint
PUT  /api/devices/home_pi_01/voices/{name}/voiceprint    the Pi uploads the voiceprint it made
DELETE /api/devices/home_pi_01/voices/{name}
     These need `Authorization: Bearer <MOCHI_DEVICE_KEY>` and validate their inputs.
GET  /api/devices/home_pi_01/state   carries "commands": [ { "command_id", "kind", "value" } ]
```

- Command kinds: `mood`, `show`, `volume`, `temp`, `enroll`, `forget`, `bye`, `hint` (value is a JSON card: `word`, `language`, `meaning`, `example`, `why` (the hint's `reason`; a `code_switch` is drawn so that it catches the eye, D-52), and `candidates` when `Hint.candidates` has more than the one word, D-42), `used` (value `{ "word", "language" }`: someone said a word they were given), and, proposed with D-51 and D-53, `suggest` (value `{ "hint_id", "text", "language" }`: the sentence suggested after a hint; the device shows it, and a touch on its screen calls `.../hints/{hint_id}/say`, D-59), `caption` (value `{ "who", "text" }`: a sentence of the live transcript, `who` the speaker's name or null) and `explain` (value `{ "word", "meaning", "plain", "kind" }`: an idiom or a technical term that was just said; not queued while a hint is on screen). A device does each `command_id` once. The gateway drops a command after 30 seconds. **The `round` kind is gone**, and `GET /state` no longer does anything with the device key.
- **Registering a voice.** A person says "Mochi, learn my voice, I'm Ana"; Mochi writes `[enroll Ana pt]`, the Pi learns the voice and reports it (`/voices`), and from then on names it in `/status` as `speaker` whenever it hears it. A voice name is tied to the person whose `display_name` it equals (any case).
- `session_started(conversing, language)`: the intelligence port's method. `conversing` is true for a review (one person talks with Mochi) and false for a meeting; `language` is the one Mochi greeted in.
- Mochi's silent commands `[listen]` and `[chat]` (never sent to the device) still switch it between watching and taking part. `[play]` is gone.
- **Many sessions at once (D-41).** `demo` stays the Pi's session. Any other id is a session a client opens (a phone's), with its own channel, agent and hints; nothing is shared between sessions except what is stored (saved words, the company's history). `&session=<id>` on `/ws?user=`, `?user=&surface=ar` and `?view=audience` follows that session (default `demo`). At most 8 live; a full house stops the oldest phone session. Unknown session: 404.
- **Web app users and sessions (D-56).** `POST /api/users` `{ "display_name", "comfortable_language"?, "target_language"? }` → 201 `User` (id = slug-xxxxxx); `GET /api/users/{user_id}` (`guest` is reserved: 404); `GET /api/users/{user_id}/words` (newest first); `GET /api/users/{user_id}/sessions` → the web's own session records, newest first (`record_id`, `session_id`, `user_id`, `started_at`, `ended_at`, `minutes`, `hint_count`, `learning_event_ids`: a different shape from the company's `SessionRecord` of 6.7, see D-58). `POST /api/sessions/{id}/start` with a `user_id` and no `mode`: the session is that person's; its participants are the user and `guest` (the user's languages the other way round, so the whose-word rule still finds one learner) and `focus` is the user's target language; 409 on `demo`, 404 for an unknown user. It leaves a web session record when it ends. Such a session uses Agora's default interruption: speaking over Mochi cuts it off (D-57).
- **Interrupting Mochi (D-50, D-57, D-67).** In every session a sentence said while Mochi is thinking drops the answer under way (Agora's default interruption); the gateway reads the abandoned sentence again together with the new one (`MOCHI_CANCEL_STALE_TURNS=true`), so a correction gets the only answer and a colleague's remark does not lose it. A web session has this whatever is configured; the Pi's `demo` session has what `MOCHI_INTERRUPTION` says, which is empty since D-67 (`append`, D-38 and D-40, made Mochi finish the old answer and then answer the correction). While Mochi's voice is playing the Pi sends no microphone (D-35), so talking over it is noticed on the Pi itself, which silences its speaker and calls `POST /api/sessions/{id}/interrupt` (D-50).
- **In a web user's own session (D-57, D-60 to D-62).** Started with its wake phrase it is a conversation with Mochi; started without, a quiet listener that may explain an expression aloud. A word the rules would give to `guest` goes to the person, the two sides swapped. A phrase Mochi teaches (`[phrase: text | meaning]`, never spoken) is saved as a card.
- **Who is who (D-58).** The *roster* is the company's members: they are the participants of the device's meetings and the owners of its voices. The *user directory* also knows the people the web app made. `/ws?user=`, `GET /api/users/{id}` and a review accept a person from either; `guest` never.
- The intelligence port has eleven methods: the three in 6.5 plus `reset`, `session_started`, `interrupted` and `device_status`, and `explain`, `suggest`, `coach` and `used_alone` (6.5; `gateway/intelligence_port.py` is the source).
- The Pi starts a session itself when it hears the wake phrase; Start on a phone does the same through `/start`. `GET /state` is polled only while a session runs.
- `/agora/llm/...` accepts the shared key as `Authorization: Bearer` (case-insensitive).
- `GET /ws?user=ana&surface=ar` (owner Suhuai): AR glasses; the gateway sends that user only `session.state.changed` and `hint.created`/`hint.cleared` for hints aimed at them or at nobody; an unknown `surface` closes 4400.
- **Hint** has `candidates: [{ "expression", "meaning" }] | None` and `context: string | None` (owner: Luís, D-31). Set only for trails_off, restarts and talks_around, where no single word is known; every other reason leaves both `null`.

### 6.7 The company and its team view (proposed in v0.7, D-45)

The full description, with the tables and one example of every answer, is `docs/TEAM_VIEW.md`. In short:

```json
// Company                     // Member
{ "company_id": "demo",        { "company_id": "demo", "user_id": "ana",
  "name": "Mochi Demo" }         "role": "admin", "team": "Product" }

// TeamMember: what the members routes return and accept
{ "user": { "user_id": "caio", "display_name": "Caio", "comfortable_languages": ["pt-BR"], "target_language": "en" },
  "role": "member", "team": "Sales" }

// SessionRecord: one session, Start to Stop. Its sentences are Utterances.
{ "record_id": "rec_001", "company_id": "demo", "session_id": "demo", "mode": "meeting",
  "started_at": "2026-11-19T16:00:00.000Z", "ended_at": "2026-11-19T16:30:00.000Z",
  "participants": ["ana", "ben"],
  "speaking": [ { "user_id": "ana", "turns": 14, "words": 162 }, { "user_id": null, "turns": 2, "words": 9 } ] }

// WordMoment: one time someone needed a word (one per hint shown or answer spoken)
{ "moment_id": "mom_001", "company_id": "demo", "record_id": "rec_001", "user_id": "ana",
  "expression": "postpone", "meaning": "adiar", "target_language": "en", "reason": "code_switch",
  "at": "2026-11-19T16:00:04.700Z", "heard": "I need to adiar my meeting tomorrow" }

// Utterance: one finished sentence and who said it (proposed, D-46)
{ "utterance_id": "seg_009", "company_id": "demo", "record_id": "rec_001", "user_id": "ana",
  "text": "I need to adiar my meeting tomorrow", "at": "2026-11-19T16:00:04.500Z" }

// HeardPhrase: in the device status, one per stretch of speech between two pauses (proposed, D-46)
// POST /api/devices/home_pi_01/status  { ..., "heard": [ { "speaker": "Ana", "seconds": 2.4, "ago_ms": 380 } ] }
```

- **Who said each sentence (D-46).** The device judges every stretch of speech between two pauses on its own and reports who it was (`speaker`: the registered name, `null` for nobody known or unclear), how much speech, and how long ago it ended. The gateway gives a sentence to the person who spoke most in the stretches that ended since the sentence before it; when the session stops it looks at every sentence again, because a report can arrive after its sentence. `GET /api/users/{user_id}/utterances?viewer=` returns a person's own sentences (that person only); `GET /dev/sessions/{id}/transcript` (dev routes only) returns the running session's sentences with their speakers, for checking.

- `viewer` is the `user_id` of the person looking, as `user` is on `/ws`: there is no sign-in yet, so it is a claim, not a proof. The rules are real: `members` for any member of that company; `POST members`, `insights` and `sessions` for an `admin` only (403 otherwise; unknown company 404); `moments` and `utterances` only for the person themselves.
- **TeamInsights** (`GET .../insights`) has `totals`, `funnel` (how many saved words got as far as each learning state), `signals` (how people get stuck, by `reason`), `shared_gaps` (expressions needed, with `people` and `times`), `false_friends` (the `look_alike` ones), `mistakes` (kinds of mistake at least three people made, from their reports: `topic`, `kind`, `people`, `times`; proposed, D-54), `explained` (idioms and technical terms explained in meetings, with `times`; proposed, D-53), `weekly`, `members` (one row of counts per member) and `highlights`. An expression never says who needed it; a member's row has counts only. `MOCHI_TEAM_MIN_PEOPLE` (default 1) leaves out expressions fewer people needed.
- A session record and its moments are written by the gateway as the session runs (`team/journal.py`); the team view is computed from them and from every member's learning events (`team/team_view.py`). Both are kept in Postgres with the saved words (D-32).
- The demo company `demo` is seeded with Ana as `admin` and Ben as `member`. One company per deployment for now; every stored row carries `company_id`.

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
- The model call takes longer than two seconds. A slow reply from Mochi's character voice never delays a hint.

Match Mochi's name loosely when someone asks it something during a session: speech-to-text writes "Moshi", "Mochie", "Motchi". (What starts a session is a greeting to Mochi, heard on the Pi itself: "Oi, Mochi" / "Hey, Mochi", D-65.)

### 7.3 Whose word is it

1. When the device recognised the voice that said the sentence (`Turn.speaker_user_id`), that person is in the session **and is learning the language being spoken**, the word is theirs. A meeting has more than two people, and several may be learning the same language: only the voice tells them apart. *(Proposed, D-44.)*
2. Otherwise, when exactly one participant is learning the language being spoken, a word from that person's comfortable language belongs to them. A Portuguese word inside English speech is Ana's, also when the device thought it heard Ben: the report of who is talking can be a moment late, and someone at home in a language is not the one searching for its words.
3. If neither applies, return the hint with `target_user_id: null` and the learning event with `user_id: null`.

In a **review** there is one person, and every word is theirs, whichever language they ask in.

### 7.4 Learning states

| When | New `learning_state` |
|---|---|
| A hint is shown or an answer is spoken | `DISCOVERED` (create the learning event now) |
| In a meeting, the expression is said within the next three turns | `ASSISTED` |
| In a review, the person says a saved word (`DISCOVERED` or `ASSISTED`) by themselves | `REINFORCED` |

| After a meeting: a word saved in an **earlier** session was said in this one by its person's own recognised voice, was shown to nobody during it (as a hint or as one of the other words on a hint's card), and was not a repeat of a colleague's word (said by someone else in one of the two sentences before) | `USED_INDEPENDENTLY` *(proposed, D-55)* |

Every change appends to `state_history`. There is no "mastered" state and no score. A word shown as a hint a moment ago does not count as recalled: reading it off the screen is not remembering it. `USED_INDEPENDENTLY` is decided when the meeting stops, not while it runs: only then is it settled who said each sentence (D-46). It needs a recognised voice, so a meeting on a phone's microphone never gives it. `ASSISTED` also needs the hint to be at most three minutes old: three turns were counted from this session's turns alone, so last week's card said in a new meeting's first sentence looked "used with help".

### 7.5 The review session (a training, D-68)

A review is a session of its own on a person's phone (`POST /api/sessions/{id}/start` with `{"mode": "review", "user_id": ...}`; the phone is the microphone, D-41). The web app calls it **Training**.

- Mochi is the person's scene partner from the first sentence: every sentence is for it, with no wake phrase. It plays a colleague in a short work role-play, in the language the person is learning.
- The scene is **new every time** but built from the person's history in the database: the moments where they needed a word (with what they said) and the mistakes in their reports. Never the same people, topic or sentences.
- The target words are up to four saved words not yet `REINFORCED`, fixed when the training starts. Mochi steers the scene so they come up and never says one first.
- **No hints and no second tries.** No hint is shown or spoken, no clue, translation or correction while the scene runs, and a missed word is not asked for again.
- Saying a target word moves its card to `REINFORCED` (7.4). The phone gets `learning_event.updated` as in a meeting.
- It lasts about five minutes, and the next training can start at once (no waiting, no schedule): from minute four Mochi ends the scene and gives **positive feedback** by voice: what went well and what is improving, each unused target word as an example to try next time, at most one thing to improve. The gateway stops the session after seven minutes at the latest.
- With no words to train, Mochi says so and chats about the person's work day instead, still with no hints.
- Mochi's screen is not involved in a review. (In a meeting a touch on it has one use: saying a suggested sentence, 7.8.)

### 7.6 The live transcript, code switches and explanations (proposed, D-51 to D-53)

- **Every finished sentence of a meeting** is published as `transcript.line` once its turn has been handled (so a turn that is dropped leaves no line), and handed to the device as a `caption`. Not in a review: what one person says to Mochi on their phone was heard by nobody else and is shown to nobody else. `MOCHI_LIVE_TRANSCRIPT=false` switches both off. "Live" is per finished sentence, about a second after it ends; word by word is not built.
- **A code switch** (7.1 case 1) still gives its speaker the hint, privately, as before. What is new is that the others see it too: the line carries a mark (`adiar` → `postpone`), and Mochi's screen draws that card so that it catches the eye, with the word that was said (`adiar → English`). Nothing is said aloud.
- **An idiom or a technical term** the people listening may not know gets a mark on its line (`circle back` → *voltar ao assunto depois*, plain: *talk about it again later*) and a card on Mochi's screen. It is **not a hint**: nobody was stuck, no word is saved for anyone, it does not count for the cooldown of 7.2, and it never covers a hint. It is looked for by a second model call, made **after** the turn was handled, so no hint and no answer waits for it.
- It is looked for only in a meeting, in a sentence of five words or more that got no hint and no answer, when someone other than the speaker is learning that sentence's language, not in serious talk or a sentence for Mochi, and not while someone is talking with Mochi. At most one per sentence, each expression once per session, and at least 8 seconds between two (as long as a card is shown; it was 20 until D-69). While a hint is on Mochi's screen the explanation is marked in the transcript only: its card would cover the stuck speaker's word. `MOCHI_EXPLAIN_TERMS=false` switches it off; without a model key there is none.

### 7.7 What was wrong in what someone said (proposed, D-54)

- **Nothing of this is shown in a meeting.** After Stop, in the background, each person whose recognised voice said three sentences or more gets one `ConversationReport`: their own sentences (with the speakers as settled at the end, D-46), each wrong one put right (`better`) with its `topic`; `mistakes` grouped by kind and topic with one example, one line of why in the person's own language, and a count; the words they needed (`unknown_words`, from the session's word moments; `said_instead` is their sentence only when their own voice said it, else null); and two short lists, `strengths` and `focus_next`.
- One model call per person and session. A mistake is what a teacher would correct in speech: grammar, a wrong word, a false friend. Not fillers, half sentences, informal speech, punctuation, or a sentence said in the person's own language. A correction that changes nothing, or of a sentence that does not exist, is dropped.
- It is stored (`conversation_reports`), sent to that person's phone (`conversation.report.created`), and read at `GET /api/users/{id}/reports?viewer={id}`. No one else can read it. The team view counts kinds of mistake that **at least three people** made, never fewer, whatever `MOCHI_TEAM_MIN_PEOPLE` says: with two, whichever of them is looking learns the other's. (So the two-person demo company shows none.)
- No report when the model did not answer ("nothing was wrong" is never said for "nobody looked"), for a session on a microphone that recognises no voice, or with `MOCHI_SPEECH_REPORTS=false`.

### 7.8 One-touch assistance: the sentence, and Mochi saying it (proposed, D-59)

A hint gives a stuck speaker the word. Sometimes the word is not enough:

> Ben: `Why is the integration delayed?`
> Ana: `Because we need to… como é que fala… destravar a autenticação.`

- Mochi's screen shows **unblock** as before. A moment later it also shows the whole sentence she was reaching for, **"Because we need to unblock the authentication process."**, and her phone gets it as `phrase.suggested`. It goes exactly where her hint went.
- **One touch** on Mochi's screen (or a "say it" button on her phone: `POST /api/sessions/{id}/hints/{hint_id}/say`) and Mochi says that sentence aloud, once, so everyone understands and the meeting goes on. Without a touch nothing is said: quiet by default holds. The touch works for 20 seconds (`MOCHI_SUGGESTION_TTL_SECONDS`).
- The sentence is written by one more model call, made **after** the turn was handled (so the hint is never later for it), from her sentence, the sentences just before it (the question she is answering) and the word of her hint. It says what she meant and nothing she did not say, without the asides in which she looked for the word, in at most about sixteen words.
- Only in a meeting, only after a silent hint (someone who asked Mochi by name is answered aloud already), only for a sentence of four words or more. A suggestion is dropped when it is what she said already, is not in the language she was speaking, or is too long. `MOCHI_SUGGEST_PHRASES=false` switches it off; without a model key there is none.
- Mochi saying the sentence does not move her card: it was Mochi who said the word, not she.

### 7.9 Speak for me (proposed, D-64; a two-way interpreter since D-69)

For people who do not share a language well enough yet, and have something to say to each other.

- **On.** Someone says, by name, `Hey Mochi, speak for me` (or `Mochi, translate for us`, `Oi Mochi, fala por mim`, `Mochi, traduz pra gente`). Anyone may ask; no registered voice is needed. Mochi confirms in one line and names the way out.
- **While it is on.** Mochi is the meeting's interpreter. A sentence said in Portuguese it says aloud in English, a sentence said in English it says in Portuguese, whoever said it ("A gente precisa adiar o lançamento" → "We need to postpone the launch"; "Is there a problem with the supplier?" → "Há um problema com o fornecedor?"): what was said, in the first person, nothing added. So one person says a sentence or two, Mochi says them in the other language, the colleague or client answers, and Mochi says that too. A sentence with Mochi's name in it is for Mochi, not for the room. The live transcript goes on as before.
- **Off.** `Mochi, stop` or `Mochi, pode parar` (also `Stop, Mochi`, `Mochi, stop translating`, `Mochi, para`, `Mochi, chega`, `Mochi, I'll speak myself`), from anyone. The short stop words count where a sentence ends ("Mochi, quando chega o relatório?" and "Mochi, how do you say stop sign?" are questions). The words that turn it on with a no in the sentence ("Mochi, don't translate for us", "não precisa falar por mim") turn it off. The name misheard still stops it ("Moji, pode parar"). It is also off at the start of every session.
- **Which way a sentence goes** is decided by the language it is in, not by who said it: the backend guesses from the sentence's small words, and the model that translates has the last word (a short sentence, "Quanto custa?", has no small word to go by). A sentence that is what Mochi itself just said (its voice coming back through a microphone) is neither translated nor taken as a command.
- **No hints while it is on:** a sentence that is translated gets no hint, since the room hears it in full in the other language. Nothing is saved as a word.
- One model call per sentence; it must answer within the limit of 7.2 or nothing is said. Only in a meeting. `MOCHI_SPEAK_FOR_ME=false` switches it off; without a model key the mode turns on and says nothing.
- *Until D-69* it spoke for one person only, the one whose registered voice had asked, and only their sentences in their own language. That needed the device to know every voice in time; the first real test was a voice registered under a name that is not a member, so no sentence had a speaker at all.

## 8. Milestones: what to build, in order

Every milestone after M0 is a complete demo. All owners build the same milestone at the same time. A milestone is reached only when it has been seen working on the real devices. M0 to M2 were reached before the product change; the game milestones (old M3 and M4) are replaced.

| | **M0 It hears us** | **M1 Mochi helps** | **M2 Mochi remembers** | **M3 Mochi knows who** | **M4 The word comes back** | **M5 The company sees** |
|---|---|---|---|---|---|---|
| **Matheus** `hardware/` | Bridge sends M1A audio to an Agora channel and plays audio back | Bridge polls the device state; microphone on only while `capturing` | Runs the real path after every change | Voices registered in advance; `speaker` reported in time for each sentence | — | — |
| **Luís** `gateway/` | Agora agent whose turns reach the backend log; empty reply keeps Mochi silent | Start/Stop, device state, WebSocket routing per connection, reset | Publish learning events to the right Mobile view | The recognised speaker on each turn; session records and word moments written | Start with `mode: review`; the reviewer's phone as microphone | Company routes; roles |
| **Kauê** `intelligence/` | One-rule `decide()` | Cases 1–4, the quiet rules, whose-word rule; then cases 5–9 | `apply()` and `words_for()`; `DISCOVERED` on every hint; `ASSISTED` upgrade | Whose-word rule 7.3 with the speaker | Review rules 7.5; `REINFORCED` on a recalled word | Review `team/team_view.py`: are these the right numbers? |
| **Tasnim** `apps/web/` | Home and Mobile views each show one real `hint.created` | Start/Stop on Mobile; listening face and expiring hint on Home | "My words" page, updating live | Move to contracts v0.7 (no game, modes `meeting` / `review`) | Review start on the phone; "Recalled in a review" | Team view page for administrators |
| **Seen working when** | A sentence spoken into the M1A puts a word on Mochi's screen and a phone | Start, say both demo sentences, see both hints; ordinary talk shows nothing; Stop, and the Pi sends nothing | Both hints appear as cards on Ana's phone and not on Ben's | In a meeting of three, a hint lands on the phone of the person who was stuck | Ana recalls "umbrella" in a review and its card reads "Recalled in a review" | Ana opens the team view and sees this week's meetings and the words the team needed |

The backend side of M3 to M5 is built (proposed, D-43 to D-45) and tested without devices; none of the three has been seen working with real voices yet.

Build the simplest thing that satisfies the row. Not in scope unless a human asks: sign-in and access tokens, more than one company per deployment, a transcript of a meeting that anyone but its speakers' own pages can read afterwards, correcting someone's grammar *during* a meeting, fluency scores, pause and resume, reconnect and replay, the watch add-on.

## 9. Starting guides, one per owner

### 9.1 Matheus — `hardware/pi-bridge`, `hardware/pi-setup`, `packages/contracts`

- **The bridge:** a C program using the Agora IoT SDK that joins a channel, sends the M1A microphone, and plays received audio through the M1A; a supervisor that listens locally for the wake phrase, polls `GET /api/devices/home_pi_01/state`, joins and sends only while `capturing` is true, and respects `speaker_muted`.
- **Voices:** learn a voice when Mochi asks (`enroll`), keep and upload its voiceprint, and report `speaker` in `/status` as soon as a registered voice is recognised, so the sentence being said can be given to the right person.
- **Test:** speak into the M1A and see the sentence in the backend log; trigger a spoken reply and hear it; confirm Mochi's own voice does not come back as a new turn; with two registered voices, confirm each sentence's speaker in the `turn` log line or in `GET /dev/sessions/demo/transcript`.
- **Do not:** put decisions about hints or learning in the bridge, and do not use the Agora Python RTC SDK. Local wake-phrase spotting and voice identification are allowed (Section 6.6); full transcription is not. Never keep the Agora App Certificate on the device if the backend can give a token. Never send audio before the wake phrase or after Stop.
- **Session limits:** `[session] max_session_s = 3600` in `config/mochi.toml`: a session ends after one hour at the latest (it was ten minutes; changed on 2026-11-22 for meetings), and the Agora tokens live two hours (`MOCHI_TOKEN_TTL_SECONDS=7200`) so they outlast it. **Still open:** `inactivity_timeout_s = 30` ends a session after 30 seconds without a voice, which a meeting with a silent pause (reading a slide) will hit.
- **Contracts:** keep `packages/contracts` equal to Section 6: one JSON example per event and payload, the Python models, the exported JSON Schema, and a test that loads every example.

### 9.2 Luís — `services/backend/gateway`, `services/backend/app.py`, `scripts/`

- **Every turn, in order:** check the shared key → take the text → put the recognised speaker on the turn → `await decide()` → `apply()` any learning events → publish events to the right connections → reply to Agora with `speak.text` or nothing → note the sentence and any word moment in the session's journal.
- **Test:** `scripts/say.sh "I need to adiar my meeting tomorrow"` produces a `hint.created` on a connected `?user=ana` socket and not on `?user=ben`'s private stream.
- **Do not:** write rules about when Mochi helps, or store learning events yourself. Keep every Agora call in one adapter module with a mock mode.

### 9.3 Intelligence (Kauê until 2026-11-22, now Luís) — `services/backend/intelligence`, `packages/fixtures`

- **`decide()`:** cases 1–9 from Section 7.1; the quiet rules in 7.2; the whose-word rule in 7.3; the learning states in 7.4, including the review.
- **Fixtures:** for every case, at least three sentences that should produce a hint and three near-misses that should not. Include both demo sentences.
- **Test:** everything runs with `pytest` on a laptop. No server, no Agora, no microphone.
- **Do not:** import from `gateway`, open sockets, or call Agora.

### 9.4 Web app (Tasnim until 2026-11-22, now Luís) — `apps/web`

Rebuilt in November 2026 (D-56) and reshaped for companies (D-57; it was called Papear until D-65): one responsive app (phone, tablet, desktop) that does in a browser what Mochi Home does on the Pi, through the same backend. It runs in Docker (nginx) as the Render service `mochi-web`. Read `apps/web/README.md`.

- **Screens:**
  - **Onboarding** (`/welcome`): asks for a name only and creates the user with `POST /api/users`. The id is kept in `localStorage`.
  - **Session** (`/session`): Start is the wake phrase. It starts the person's own session and uses the browser's microphone through Agora. A sober status panel (state, audio meter), the hint card, what Mochi says and who is talking are live. Speaking over Mochi cuts it off (D-57).
  - **Training** (`/training`): a five-minute role-play with Mochi built from the person's history (7.5, D-68): Start, a clock, Finish. Nothing is written: Mochi's feedback is spoken, and starting another training never waits.
  - **Digest** (`/digest`): a weekly digest of the person's conversations at work (Monday to Sunday, with a week picker): their sessions, the words they needed and how those words moved. It is not a to-do list: no "practise next".
  - **Analytics** (`/analytics`): progress, each word's state path, and minutes per session.
- **Microphone:** the browser asks for it on the first visit. Every way the microphone can fail has its own screen and message, and so does a backend that cannot be reached.
- **Not built:** the Home view (`/home`) and the Audience view (`/audience`) of the old app are not in the new build. Mochi's own screen is `hardware/pi-setup/face.html`.
- **Contracts:** the app still types contracts v0.4. Since D-58 its guard also accepts the session modes `meeting` and `review`; it drops event types it does not know, so it shows none of the things below until they are built.
- **Proposed, not built in the app (D-51 to D-54, D-59):** the live transcript (`transcript.line`: a line replaced when it comes again, each mark drawn in its sentence with its `gloss`), a suggested sentence with a "say it" button (`phrase.suggested`, `POST /api/sessions/{id}/hints/{hint_id}/say`), the person's reports (`conversation.report.created`, `GET /api/users/{id}/reports`), and the team view for administrators (`GET /api/companies/{id}/insights`; `docs/TEAM_VIEW.md`).
- **Do not:** implement AI or speech recognition, decide visibility in the browser, or store learning events.

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
scripts/reset-demo.sh           clear saved words and the learning history
pytest services/backend         backend and intelligence tests
npm test --prefix apps/web      web app tests
```

Environment variables: `AGORA_APP_ID`, `AGORA_APP_CERTIFICATE`, `AGORA_REST_KEY`, `AGORA_REST_SECRET`, `MOCHI_TURN_KEY`, `MOCHI_DEVICE_KEY`, `MODEL_API_KEY`, `MOCHI_PUBLIC_URL`, `DATABASE_URL`; the full list is in `README.md`.

When the real path breaks, find the last step that left a trace: bridge log (Matheus) → backend log line for the turn (Luís) → decision line (Kauê) → published-event line (Luís) → `?debug=1` list and the screen (Tasnim).

## 12. Things nobody has verified yet

Do not write code that assumes these work. If your task depends on one, say so in your report.

1. **Silent replies.** Seen working in live sessions (`VERIFIED.md`); the fallback `MOCHI_SILENCE_STRATEGY=mute_speaker` stays.
2. **Mixed-language transcription.** `adiar` and `guarda-chuva` survive with the current ears; background speech is still written as lexicon words now and then (D-35, D-36).
3. **Audio both ways on the Pi**, without Mochi hearing its own voice.
4. **Who said it, in a real room.** Measured offline on 2026-11-22 with recorded voices (D-46): sentences with one speaker got the right person 95 times in 100 and a wrong person never; before the change a wrong person 9 or 10 times in 100. With room reverb and noise it stays near 9 in 10; with other people talking in the background it falls to 7 in 10 and to half when they are nearly as loud as the meeting (D-49). Not yet measured: a real meeting through Agora (far from the microphone, people talking over each other, Agora's own turn timing).
5. **A review by voice.** The review rules are tested with typed sentences and a scripted model; nobody has done one by voice.
6. **A long meeting.** Sessions so far lasted minutes. An hour-long meeting (Agora's agent, the Pi's session limits, the cost) has not been tried.
7. **The company tables in a real Postgres.** Run on 2026-11-22 against a throwaway PostgreSQL 17 on the Pi (D-58): `tests/integration/test_postgres_storage.py` passes (7 tests, with `MOCHI_TEST_DATABASE_URL`), and a database holding `main`'s tables and a web session was opened by this code, which created `companies`, `company_members`, `company_sessions`, `word_moments`, `utterances` and `conversation_reports`, wrote one row to each and read them back after a restart. Not yet seen: the same on Render's own database, with its real rows.
8. **The hint judge in a work meeting.** Its instructions now describe a meeting of several people (D-47) and score the same on the hint yardstick as before, but the yardstick's sentences are everyday talk between two learners. It has not been measured on what people say in work meetings.
9. **The live transcript, the explainer and the reports with real voices.** Built and tested with typed sentences and scripted models (D-51 to D-55). On 2026-11-22 the explainer's instructions were tried on 24 written sentences with the real model (12 with an idiom or term, 12 ordinary): all 24 right, 0.7 s each; the coach's on 12 sentences: six real mistakes found, none invented. That is a look, not a measurement: nobody has seen a caption, a marked code switch or an explanation on Mochi's screen in a real meeting, and no report has been written from a machine transcript of real speech, where a misheard word can look like a mistake.
10. **Who reads the live transcript.** There is no sign-in, so anyone who opens `/ws?user=<a known id>` or `?view=audience` on a running session gets its lines, as they already got its hints. The transcript says much more than a hint does. `MOCHI_LIVE_TRANSCRIPT=false` is the switch until sign-in exists.
11. **One-touch assistance with a finger and a voice.** Built and tested with typed sentences and scripted models (D-59); see D-59 for what was tried with the real model and a real session. Nobody has touched Mochi's real screen in a real meeting yet, and whether Mochi's own sentence comes back as a turn through a real room's microphone is item 3 above.
12. **Speak for me in a real meeting.** The one-person form was tried in real sessions with spoken clips (D-64); the two-way interpreter (D-69) with typed sentences and the real model only. Not seen: two real people taking turns with Mochi's voice between them (the wait, people talking over it, a sentence in mixed language sent the wrong way), nor whether Mochi's own sentence comes back as a turn (item 3; it is ignored when the recogniser writes it as it was said).
13. **Interrupting Mochi on the device.** The Pi's session has Agora's default interruption since D-67, tested with typed sentences and the fake Agora only: a question abandoned while Mochi thinks is read again with what followed it. Not seen with real voices: how often a colleague speaking in the half second between the answer being written and being spoken loses it (the case D-38 measured, then without `MOCHI_CANCEL_STALE_TURNS`), and the Pi's own stop when talked over (D-50) has not been tried at the real device either. Speak for me (7.9) has not been tried with it: a person who goes on talking drops the translation under way, which `append` did not (D-67). The deployed backend still has `append` until the variable is changed on Render by hand.

## 13. Changelog

- **Mochi can be interrupted on the Pi as on the web (2026-11-22, D-67).** The deployed `MOCHI_INTERRUPTION` is empty (it was `append`): a sentence said while Mochi thinks drops the answer under way, and the gateway reads the abandoned sentence again with the new one (6.6). No code path, field, event or route is new. `main`'s three performance changes are merged (D-66; `main` calls that entry D-64).

- **After the first real meeting on the device (2026-11-22, D-69, proposed).** Speak for me is a two-way interpreter with no speaker lock (7.9). Fixed: "I'll say it again" made Mochi say the last hint aloud; a sentence left to ask for its word ("We need to, como é que fala, destravar a autenticação?") lost its hint and its one-touch sentence; explanations 15 s apart were dropped (the pause is 8 s now, was 20). No field, event, route or enum value changes.

- **The name is Mochi again (2026-11-22, D-65).** The product was called Papear from D-43 to D-64; the team went back to **Mochi**, for the product, the web app and the companion alike. Nothing else changes: no field, event, route or enum value. A session starts with a greeting to Mochi again ("oi Mochi", "olá Mochi", "hi Mochi", "hey Mochi", "hello Mochi"), not "vamos papear" / "let's chat" (D-48). The demo company is "Mochi Demo". Older entries below still say Papear; they are history.

- **v0.7, speak for me (proposed, 2026-11-22, D-64).** "Mochi, speak for me": a person with a registered voice talks in their own language and Mochi says each sentence aloud in the meeting's, until "Mochi, stop speaking for me" (7.9). No new event, route or enum value: what Mochi says is an ordinary `agent.speak.requested`. `MOCHI_SPEAK_FOR_ME`.

- **v0.7, one-touch assistance (proposed, 2026-11-22, D-59).** After a silent hint the whole sentence the speaker was reaching for is suggested (`phrase.suggested`, device command `suggest`); one touch on Mochi's screen, or `POST /api/sessions/{id}/hints/{hint_id}/say`, and Mochi says it aloud. Port method `suggest` (eleven now). `MOCHI_SUGGEST_PHRASES`, `MOCHI_SUGGESTION_TTL_SECONDS`.

- **v0.7, merged with `main` (2026-11-22, D-58).** `main`'s web users, per-user sessions and web session records (D-56, D-57; they were D-42 and D-43 there) and this file's D-43 to D-55 are one tree. The company's table is `company_sessions` (the web's keeps `session_records`); a meeting's participants are the company's members, no longer everyone known; `apps/web` accepts the modes `meeting` and `review`.

- **v0.7, the meeting beyond the stuck word (proposed, 2026-11-22, D-51 to D-55).** New events `transcript.line` (every finished sentence, with marks: a code switch, an explained idiom or technical term) and `conversation.report.created` (a person's private report after Stop). New: `TranscriptLine`, `TranscriptMark`, `ConversationReport` and its parts, `Utterance.marks`, `TeamInsights.mistakes` and `.explained`, `GET /api/users/{id}/reports`, device commands `caption` and `explain`, `why` in the hint card, port methods `explain`, `coach` and `used_alone`, table `conversation_reports`. `USED_INDEPENDENTLY` is built (decided at Stop). `ASSISTED` needs a hint at most three minutes old. Product rules 2 to 4 reworded for the live transcript. Switches: `MOCHI_LIVE_TRANSCRIPT`, `MOCHI_EXPLAIN_TERMS`, `MOCHI_SPEECH_REPORTS` (all on by default). Nothing in `apps/web` was changed; it ignores the two new events until its owners use them (`docs/TEAM_VIEW.md`, "For the web app").

- **v0.7, more of 2026-11-22 (proposed, D-48 to D-50).** A session starts with "vamos papear" or "let's chat" instead of a greeting to Mochi (D-48). Someone talking over Mochi stops it at once: `POST /api/sessions/{id}/interrupt`, a seventh port method `interrupted()`, `[barge_in]` on the Pi (D-50). For a noisy room: the Pi judges unbroken speech every two seconds, and `MOCHI_MEETING_VOICES=registered` drops what no registered voice said (D-49).
- **v0.7, additions of 2026-11-22 (proposed, D-46, D-47).** Every sentence of a session is stored with the person who said it (`Utterance`, `GET /api/users/{id}/utterances`, `GET /dev/sessions/{id}/transcript`); the device reports each stretch of speech with who said it (`heard` in the device status) and the gateway matches sentences to them by time. Rule 4 and 6.7 changed accordingly. The hint judge is told it is a meeting. A session may last an hour (`max_session_s = 3600`, tokens two hours).
- **v0.7 (proposed, 2026-11-21): Papear.** The product is language learning for companies; Mochi sits in their meetings. Two session modes, `meeting` and `review` (were `together` and `activity`); the game is removed everywhere outside `apps/web` (events `activity.*`, routes `/activity/*`, `handle()`, the `round` device command, `[play]`, Speak reason `activity_host`, the secret-word guards). `REINFORCED` now means "recalled in a review". New: `Turn.speaker_user_id` and the speaker-first whose-word rule (D-44); people beyond the two demo users; companies, members, session records, word moments and the team view (6.7, D-45, `docs/TEAM_VIEW.md`). On wake Mochi says one line and the meeting begins; it no longer asks what to do. **Breaking for `apps/web`**, which still speaks v0.4. Open for the team: every item under "Open" in D-43 to D-45.
- **v0.6 (proposed, 2026-11-21).** Mochi asked "What would you like to do today?" after its name; Play started by voice and ran on Mochi's own screen; the Pi tells who is talking in time, shows its temperature and a lost connection and says both; the ears can be left untold of the lexicon. D-34 to D-39. *The mode question and Play were removed in v0.7.*
- **v0.5 (proposed, 2026-11-21), addition.** Many sessions at once (6.6, D-41): the phone's session no longer turns the Pi's off.
- **v0.5 (proposed, 2026-11-21).** Local wake-phrase listening allowed by the privacy rule; the device channel (status, voices, commands); `Hint.candidates`/`context` (D-31); a character reply cannot delay a hint.
