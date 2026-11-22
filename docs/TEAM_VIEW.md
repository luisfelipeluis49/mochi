# The company side of Mochi: data model, backend logic and API

**Status:** proposed on 2026-11-21 (DECISIONS D-45), built in `services/backend` and tested without devices. For whoever builds the team view and the personal analytics on the phone.

Mochi is sold to companies. A company wants to know whether its people are getting more at ease in the language they work in, and which words and mistakes come up at work. Each person wants their own progress and nobody reading over their shoulder. This document says what is stored, how each person's learning data is added up for administrators, and what the phone can ask for.

## 1. What is collected, and when

| When | What is written | Kept where |
|---|---|---|
| A session starts (`POST /api/sessions/{id}/start`) | a **session record**: meeting or review, start time, who was there | `company_sessions` |
| A sentence is finished | an **utterance**: the sentence and the person whose registered voice said it (or nobody) | `utterances` |
| A hint is shown or an answer is spoken | a **word moment**: who, which expression, why, when, and that person's own sentence; and, the first time, a **learning event** (the card) | `word_moments`, `learning_events` |
| The person says the word afterwards | the card moves on: `ASSISTED` in a meeting, `REINFORCED` in a review | `learning_events` |
| The session stops | every sentence's speaker is looked at once more (a report from the device can arrive after its sentence); the record is closed: end time and who said how much | `utterances`, `company_sessions` |
| A code switch is hinted, or an idiom or technical term is explained (D-52, D-53) | a **mark** on that sentence: what was said and what it means | `utterances` (in `body`) |
| A moment after the session stopped (D-54, D-55) | for each person who said three sentences or more, a **conversation report**: their sentences put right, the kinds of mistake, the words they needed; and a saved word they used with no hint moves to `USED_INDEPENDENTLY` | `conversation_reports`, `learning_events` |

Audio is **not** stored. The sentences are, since 2026-11-22 (D-46): each one with its speaker, readable by that person only. A sentence no known voice said (`user_id: null`) is stored and has no reader; it is there so that who-said-what can be checked while developing.

A learning event is one card per person and expression; showing "postpone" to Ana five times is still one card. A word moment is every one of the five. The team view needs both: cards say how far a word got, moments say how often it was needed and when.

**Who said a sentence** comes from the device: it judges each stretch of speech between two pauses on its own and reports who it was, how much speech and how long ago (`heard` in `POST /api/devices/home_pi_01/status`). A sentence is the person's who spoke most in the stretches that ended since the sentence before it; nobody's when two people shared it or the device could not tell. On recorded voices this named the right person for 95 sentences in 100 and a wrong person for none (D-46); a real room has not been measured.

**Who a moment belongs to** follows the hint: the person who said the sentence, when they are learning the language being spoken; else the only participant learning that language; else nobody (`user_id: null`). A moment with no person still counts for the company's totals and for how often an expression was needed, and for nobody's own numbers.

## 2. Tables

Postgres, created with `CREATE TABLE IF NOT EXISTS` at startup like the earlier ones (D-32); the statements are in `services/backend/src/mochi_backend/storage/schema.py`. `users`, `learning_events` and `voices` existed before and are unchanged.

```text
companies                      company_members                     users (existing)
  company_id  PK                 company_id  PK, FK companies         user_id  PK
  name                           user_id     PK, FK users             display_name
  created_at                     role        admin | member           comfortable_languages[]
                                 team        free text, nullable      target_language
                                 joined_at

company_sessions                                word_moments
  record_id    PK                                 moment_id        PK
  seq          insertion order                    seq              insertion order
  company_id   FK companies                       company_id       FK companies
  session_id   "demo" or a phone's id             record_id        the session it happened in (no FK)
  mode         meeting | review                   user_id          FK users, nullable
  started_at                                      expression
  ended_at     null while it runs                 target_language
  body jsonb   the SessionRecord                  reason           code_switch, look_alike, ...
                                                  at
  index (company_id, started_at)                  body jsonb       the WordMoment (also meaning, heard)

learning_events (existing)                        index (company_id, at)
  learning_event_id PK, user_id FK,               index (company_id, lower(expression))
  expression, learning_state, body jsonb
```

- As with `learning_events`, `body` is the whole contract object, so a contract change needs no column change; the other columns are for indexes and for looking at a table by hand.
- A person can belong to several companies (`company_members` has a two-part key). Every fact row carries `company_id`. Today one deployment serves one company (`demo`), so the code attaches every session to it; serving several means choosing the company from the device or the person at Start, and nothing in the tables changes.
- `word_moments.record_id` is not a foreign key on purpose: writes are queued and retried in order (D-32), and a moment must not be lost because its session's row failed.
- `utterances` (added 2026-11-22, D-46): `utterance_id` (the turn's id), `company_id`, `record_id`, `user_id` (null when no known voice said it; `ON DELETE SET NULL`), `at`, and `body` (the `Utterance`, with the sentence). Indexed by `(record_id, seq)` for a session's transcript and by `(user_id, at)` for a person's own page. A row is written when the sentence arrives and written again if its speaker changes when the session ends. `POST /api/demo/reset` deletes them with the records and moments. They are loaded into memory at startup like the rest, which will stop being right long before the other tables do: an hour of meeting is some hundreds of rows.
- `conversation_reports` (added 2026-11-22, D-54): `report_id`, `company_id`, `record_id`, `user_id` (not null; `ON DELETE CASCADE`: a report has no reader but its person), `ended_at`, and `body` (the `ConversationReport`). Indexed by `(user_id, ended_at)`. Written once, never changed; deleted by `POST /api/demo/reset` with the rest of the history. Its SQL, like the other company tables', has not run against a real Postgres yet (AGENTS 12.7).
- Without `DATABASE_URL` the same rows live in the local JSON file (`MOCHI_LOCAL_DATA`, fake mode) or in memory.

The backend loads these tables once at startup and answers from memory; writes go to the database on a worker thread (the same arrangement as saved words). The aggregation in section 4 is therefore Python over lists, not SQL. That is right for one company and thousands of rows. When it stops being right, the same numbers are a few `GROUP BY` queries over `word_moments` (the indexes above are for them) and the code to replace is one module, `team/team_view.py`.

## 3. API

There is no sign-in in the MVP. `viewer` is the `user_id` of the person looking, the same kind of claim as `user` on `/ws?user=ana`. The role rules are enforced; the proof of identity is what is missing, and it goes in one place (`gateway/team_service.py`, `_allow`) when sign-in exists.

| Route | Who | Answer |
|---|---|---|
| `GET /api/companies/{company_id}/members?viewer=` | any member | `TeamMember[]` |
| `POST /api/companies/{company_id}/members?viewer=` | admin | the `TeamMember` that was added or changed |
| `GET /api/companies/{company_id}/insights?viewer=&days=30` | admin | `TeamInsights` |
| `GET /api/companies/{company_id}/sessions?viewer=` | admin | `SessionRecord[]`, newest first |
| `GET /api/users/{user_id}/moments?viewer=` | that person only | `WordMoment[]`, newest first |
| `GET /api/users/{user_id}/utterances?viewer=` | that person only | `Utterance[]`: what they said, newest first |
| `GET /api/users/{user_id}/reports?viewer=` | that person only | `ConversationReport[]`: what was wrong in what they said, one per session, newest first |
| `GET /dev/sessions/{id}/transcript` | development only (`MOCHI_ENABLE_DEV_ROUTES`) | `Utterance[]` of the running session, every speaker |

Errors: 403 when the viewer is not a member (or not an admin where one is needed, or asks for someone else's moments), 404 for an unknown company, 422 for a body or id that does not fit. `days` is 1 to 365.

Adding a person:

```json
POST /api/companies/demo/members?viewer=ana
{ "user": { "user_id": "caio", "display_name": "Caio",
            "comfortable_languages": ["pt-BR"], "target_language": "en" },
  "role": "member", "team": "Sales" }
```

From then on `caio` is in every meeting's `participants`, can open `/ws?user=caio`, can start a review, and a voice registered on the device under the name "Caio" is his (the name is matched to `display_name`, any case). Sending the same `user_id` again changes the person.

The JSON Schema of every shape is in `packages/contracts/schema/` (`TeamInsights.json`, `TeamMember.json`, `SessionRecord.json`, `WordMoment.json`, `Company.json`, `Member.json`), with one example each in `packages/contracts/examples/payloads/`.

## 4. The team view: how the members' data is added up

`GET .../insights` returns one object. The period (`days`, default 30) applies to sessions and moments; saved words are counted over all time, because a card's progress has no period.

```json
{
  "company": { "company_id": "demo", "name": "Mochi Demo" },
  "generated_at": "2026-11-21T12:00:00.000Z",
  "period_days": 30,
  "totals": { "members": 4, "active_members": 3, "meetings": 6, "reviews": 2,
              "meeting_minutes": 185, "moments": 21, "words": 12 },
  "funnel": { "discovered": 12, "assisted": 7, "reinforced": 3, "used_independently": 0 },
  "signals": [ { "reason": "code_switch", "times": 12, "share": 0.571 },
               { "reason": "says_unknown", "times": 5, "share": 0.238 },
               { "reason": "look_alike", "times": 4, "share": 0.19 } ],
  "shared_gaps": [ { "expression": "postpone", "meaning": "adiar", "target_language": "en",
                     "people": 3, "times": 5,
                     "reasons": [ { "reason": "code_switch", "times": 4, "share": 0.8 },
                                  { "reason": "says_unknown", "times": 1, "share": 0.2 } ],
                     "last_at": "2026-11-19T16:00:04.700Z" } ],
  "false_friends": [ { "expression": "intend", "meaning": "pretender", "target_language": "en",
                       "people": 2, "times": 2,
                       "reasons": [ { "reason": "look_alike", "times": 2, "share": 1.0 } ],
                       "last_at": "2026-11-18T14:10:00.000Z" } ],
  "weekly": [ { "week_start": "2026-11-09", "meetings": 2, "moments": 8, "people": 2, "new_words": 5 },
              { "week_start": "2026-11-16", "meetings": 4, "moments": 13, "people": 3, "new_words": 7 } ],
  "members": [ { "user_id": "ana", "display_name": "Ana", "role": "admin", "team": "Product",
                 "target_language": "en", "meetings": 6, "reviews": 2, "speaking_turns": 80,
                 "moments": 9, "words": 6, "assisted": 4, "reinforced": 2,
                 "last_active_at": "2026-11-19T16:30:00.000Z" } ],
  "highlights": [ { "kind": "shared_gap", "expression": "postpone", "people": 3, "times": 5, "share": null },
                  { "kind": "words_sticking", "expression": null, "people": null, "times": null, "share": 0.583 } ]
}
```

What each part answers, and how it is computed:

| Part | The administrator's question | Computed from |
|---|---|---|
| `totals` | Is Mochi being used? | Records and moments in the period. `active_members`: members whose voice was recognised in a session, who did a review, or who needed a word. `meeting_minutes`: finished meetings only. `words`: different expressions needed |
| `funnel` | Do the words stick? | Every member's cards, all time: how many were ever at least `DISCOVERED` / `ASSISTED` / `REINFORCED` / `USED_INDEPENDENTLY` (a card's whole history counts, not only where it is now) |
| `signals` | How do our people get stuck? | Moments in the period by `reason`: switching language, saying they do not know, false friends, trailing off... `share` is of all moments |
| `shared_gaps` | Which words does the team need for its work? | Moments in the period, without the false friends, grouped by expression and language: how many **people**, how many **times**, why, and when last. The ones most people share come first; ten at most |
| `mistakes` | What do we get wrong when we speak? | The members' conversation reports in the period, grouped by `topic` and `kind`: how many **people** and how many **times**. A kind of mistake fewer than three people made is never listed, whatever `MOCHI_TEAM_MIN_PEOPLE` is: one would name that person, and two would tell each of them about the other. The two-person demo company therefore shows none until a third member has a report. Ten at most |
| `explained` | Which of our own expressions are hard on learners? | The marks of kind `idiom` and `technical_term` on the period's sentences, grouped by expression: `meaning`, `kind`, `times`, `last_at`. Who said it and who needed it are not kept |
| `false_friends` | Which mistakes do we share? | The same for `look_alike` moments ("pretend" for "intend"). These are errors, not missing words, so they are a list of their own |
| `weekly` | Is it getting better? | One row per week of the period, quiet weeks included: meetings, moments, people who needed a word, cards first saved that week. Fewer moments per meeting over the weeks is the sign to look for |
| `members` | Who is taking part? | One row per member, by name: meetings their voice was recognised in or that held one of their moments (a phone's microphone recognises nobody), reviews, sentences spoken, moments, cards, and how many cards got to `ASSISTED` and to `REINFORCED`. **Counts only** |
| `highlights` | What should I look at? | At most one of each kind, see below |

`highlights` are a kind plus numbers; the screen writes the sentence, in the reader's language:

| `kind` | When | Fields | A sentence the screen could write |
|---|---|---|---|
| `shared_gap` | an expression at least two people needed | `expression`, `people`, `times` | "3 people needed *postpone* this month." |
| `repeated_gap` | needed three times or more, and no one has used it afterwards | `expression`, `people`, `times` | "*deadline* keeps coming up and has not stuck yet." |
| `false_friend` | the false friend made most often | `expression`, `people`, `times` | "*pretend* was used for *intend* twice." |
| `words_sticking` | there is at least one card | `times` (cards used afterwards), `share` | "58% of the words people needed, they went on to use." |
| `review_backlog` | cards not yet recalled in a review | `people`, `times` (cards) | "12 words are waiting for a review, across 3 people." |

### What an administrator cannot see

- **Who needed a word.** `shared_gaps` and `false_friends` carry `people` as a number. With a very small team a list can still point at one person ("the only one learning English needed *postpone*"); `MOCHI_TEAM_MIN_PEOPLE` leaves out every expression fewer people than that needed. Its default is 1, which shows everything and suits the two-person demo; a real company should run with 2 or 3.
- **Anyone's sentences.** `WordMoment.heard` and the `Utterance`s are returned to that person only (`/api/users/{id}/moments`, `/api/users/{id}/utterances`). Nothing in the team view, the sessions list or a member's row carries a sentence.
- **Which words a member has.** A member's row has how many, not which.
- **Anyone's report.** `GET /api/users/{id}/reports` answers that person only. `mistakes` in the team view is counts per kind of mistake, from at least three people.

Whether an administrator should see per-person rows at all is a product decision that has not been made; they are in because the request was to add up "each individual person's learning data". Taking them out is deleting one field.

## 5. Each person's own data

- Their cards arrive on `/ws?user=<id>` as before (`learning_event.created` / `.updated`, all saved ones on connect).
- `GET /api/users/{id}/moments?viewer={id}` lists every time they needed a word, with `heard` (their sentence), `reason` and `record_id`. "You needed *postpone* four times, in three meetings" is a count over this list.
- `GET /api/users/{id}/utterances?viewer={id}` lists what they said, sentence by sentence, with `record_id` (which session) and `at`. What the others in the meeting said is never in it.
- A review is `POST /api/sessions/{phone session}/start` with `{"mode": "review", "user_id": "<id>"}`; the phone joins that session's channel as its microphone (`GET /api/sessions/{id}/agora`), as it does for a meeting on the phone.

- `GET /api/users/{id}/reports?viewer={id}` lists their conversation reports (D-54), and each new one arrives on `/ws?user=<id>` as `conversation.report.created` a moment after Stop (the five newest also on connect). A report is the sketch of `apps/web/PROPOSAL_contracts_v0.5.md` 3b made real, with the differences listed in section 6.
- Their utterances now carry `marks`: the code switches and the explained expressions in their own sentences.

Not built: `session.summary.created` from the same proposal (minutes practised, next step). A report's `strengths`, `focus_next` and `speaking_minutes` cover most of it.

## 6. For the web app: what v0.7 changes

*Since D-56 to D-58 the web app is a new one (Onboarding, Session, Training, Digest, Analytics) with users and sessions of its own; it accepts the modes `meeting` and `review` and ignores events it does not know. The table below was written for the app it replaced; the second table ("Added on 2026-11-22") is what the new app can pick up. The company's table is `company_sessions`: `session_records` is the web app's own (one row per finished web session of a person, `GET /api/users/{id}/sessions`).*

`apps/web` still speaks contracts v0.4 and was not touched. With this backend:

| Was | Now |
|---|---|
| `schema_version: "0.4"` | `"0.7"` (the app warns once and carries on) |
| session `mode`: `together`, `activity` | `meeting`, `review` |
| `activity.state.changed`, `activity.private_prompt` | not sent any more; nothing on connect either |
| `POST /api/sessions/{id}/activity/start` and `/result` | 404 |
| Speak `reason` `activity_host` | never sent |
| label "Recalled in a game" for `REINFORCED` | "Recalled in a review" |
| `/ws?user=` accepted only `ana` and `ben` | any person the company added |
| Start had only `woken_by` | also `mode` and `user_id` (a review) |

New to use: the routes in section 3.

### Added on 2026-11-22 (D-51 to D-55, proposed); nothing in `apps/web` was changed

The app ignores event types it does not know, so it keeps working as it is. To show the new things:

| What | How |
|---|---|
| **Live transcript** | `transcript.line` on every `/ws` of the session (not on `surface=ar`, and never in a review). Keep lines by `utterance_id`; a line that comes again replaces the one you have (its `marks` grew). `user_id` null: no known voice. Nothing is replayed on connect |
| **Marks** | each `{ kind, text, gloss, plain }`. Find `text` in the sentence (ignore case; if it is not there, show the mark after the sentence) and show `gloss` beside it. `code_switch`: `text` is the word said in the other language, `gloss` the word in the language being spoken. `idiom`, `technical_term`: `gloss` is the meaning in the other language, `plain` the same in everyday words |
| **One-touch assistance (D-59)** | `phrase.suggested` `{ hint_id, target_user_id, language, text, expires_at }` arrives a moment after a hint, on the screens that got the hint. Show `text` with a "say it" button until `expires_at`; the button is `POST /api/sessions/{id}/hints/{hint_id}/say` → `{ "said": true }`, and Mochi says the sentence (an `agent.speak.requested` follows) |
| **Reports** | `conversation.report.created` (that person's phone only) and `GET /api/users/{id}/reports?viewer={id}`. Against the v0.5 sketch: `mode` (`meeting` \| `review`) replaces `context`; there is no `title`; `topic` is one of `verb_tense`, `verb_form`, `agreement`, `articles`, `prepositions`, `pronouns`, `plurals`, `word_order`, `word_choice`, `false_friend`, `other` (the app writes the label); `mistakes[].explanation` is one line in the person's own language; `my_sentences[]` has `utterance_id`; `company_id` and `record_id` are new |
| **Used on your own** | arrives as `learning_event.updated` with `learning_state: "USED_INDEPENDENTLY"` a moment after a meeting stops |
| **Team view** | `insights.mistakes` and `insights.explained` |

To see the events without building anything: run the backend with `MOCHI_AGORA_MODE=fake MOCHI_ENABLE_DEV_ROUTES=true`, start a session, `scripts/say.sh "Let's circle back on pricing after the launch."`, and open any view with `?debug=1`; or `GET /dev/sessions/demo/transcript`, which shows each sentence with its marks.

## 7. Using the data to make Mochi better for a company (not built)

The reason to collect moments per company is that the words its people need at work become known. Three uses, in the order they would pay off:

1. **Tell the ears.** The speech recogniser is given a list of words to expect (`MOCHI_ASR_KEYWORDS` plus the lexicon). A company's most needed expressions, in both languages, belong on that list; they are exactly the words said in the wrong language mid-sentence. Caution from D-35 and D-36: a recogniser primed with words also hears them in unclear audio, so this needs measuring before it is switched on.
2. **Grow the lexicon.** A hint for a word in the built-in lexicon is instant and needs no model; a word outside it costs a model call and can be wrong. Expressions that many people needed, with the meaning they were given, are candidates for a company lexicon.
3. **Choose what a review brings back.** Today a review takes a person's newest cards. It could put first the expressions the whole team keeps needing.

## 8. Where the code is

| Path | What |
|---|---|
| `packages/contracts/python/mochi_contracts/models.py` | `Company`, `Member`, `TeamMember`, `SessionRecord`, `WordMoment`, `TeamInsights` and its parts |
| `services/backend/src/mochi_backend/storage/schema.py`, `postgres_team.py` | the tables and their reads and writes |
| `services/backend/src/mochi_backend/team/ledger.py` | the company's history in memory, written behind |
| `.../team/journal.py` | writes one session into the ledger as it runs |
| `.../team/team_view.py`, `gaps.py`, `progress.py`, `highlights.py`, `facts.py` | the aggregation: pure functions, facts in, `TeamInsights` out |
| `.../gateway/team_service.py`, `gateway/routes/companies.py` | roles and routes |
| `.../gateway/live_transcript.py` | publishes `transcript.line`, the device's `caption` and `explain` cards (D-51 to D-53) |
| `.../gateway/after_session.py` | after Stop: the reports and "used on your own" (D-54, D-55) |
| `.../intelligence/explaining.py`, `openai_explain_model.py` | when an idiom or a term is explained, and the model's instructions |
| `.../intelligence/speech_report.py`, `openai_coach_model.py` | what goes into a report, and the coach's instructions |
| `.../team/speech.py` | `mistakes` and `explained` of the team view |
| `.../gateway/roster.py` | the people the backend knows; the demo company and its two members |
