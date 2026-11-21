# Mochi AR — what's built, what's missing, plan to close the gap

Written against the spec given by the team (2026-11-21): Mochi Home hears, `intelligence.decide()`
decides, the glasses are a private screen for one person that never listens and never decides.
Builds on D-31 (`docs/DECISIONS.md`) and the session that produced it.

## 1. Verdict: is `candidates`/`context` (D-31) the right shape?

**Yes, matches the spec exactly, no logic change needed:**

| Spec says | What D-31 built |
|---|---|
| One word when the word is already known (code switch, "how do you say", asked of partner/Mochi) | `code_switch`, `says_unknown`, `asks_partner`, `asks_mochi` never get `candidates` |
| Up to three when nothing was named: trails_off, restarts, talks_around | Exactly these three reasons, nothing else, get `candidates` (max 3, deduplicated, primary first) |
| Those three also show `context`, the sentence where she stopped | `context` is set only alongside `candidates`, same three reasons |
| Glasses never decide, never listen, just another screen for that person | Unchanged by D-31: `apps/glasses` still only reads `?user=<id>&surface=ar`; the gateway still republishes the whole `Hint` it is given |

Nothing to remove either: no case outside the three got candidates, no gateway or glasses code
was touched to make this work (verified live, see the session log — a hint reached a
`?user=ana&surface=ar` connection over a public ngrok tunnel with `candidates`/`context` in the
payload, with zero gateway or glasses changes).

## 2. The seven gaps from the spec, status today

| # | Gap | Status after this session | Owner | Effort |
|---|---|---|---|---|
| 1 | Backend not reachable over HTTPS; glasses never opened the socket over Wi-Fi | **Partially closed for dev**: `scripts/tunnel.sh` (ngrok) gives a real public HTTPS/WSS URL, verified end to end (section 3). Not production: ngrok free tier's URL is not stable, and nobody has pointed a **packaged, installed** glasses build at any backend yet — only local file edits so far | Matheus (device), shared infra for Render | Render: already specified in `render.yaml`, needs `MOCHI_DEVICE_KEY`/`MODEL_API_KEY` set in the dashboard (`sync: false`, cannot come from a push) |
| 2 | `userId` fixed per package; no pairing/login | Unchanged, correctly out of scope per the spec itself | — | Out of scope (explicit) |
| 3 | No auth on `/ws?user=ana` | Unchanged; consistent with AGENTS 8 ("no sign-in on public endpoints") for the whole project, not just glasses | Luís | Out of scope for the hackathon (explicit) |
| 4 | Latency never measured | **Measured this session** (section 3): the backend+network leg is small; the real risk is the ASR+model legs upstream, already measured separately (D-25, D-29) and estimated below | Kauê (model leg), Matheus (ASR leg) | Already have the numbers; a live end-to-end timing with real speech is the only thing not done |
| 5 | `candidates`/`context` need Matheus's sign-off; `&surface=ar` not implemented in the gateway | `candidates`/`context`: proposed, recorded (D-31, AGENTS 6.6), **waiting on Matheus**. `&surface=ar`: **now on `main`** (`gateway/connections.py`, AGENTS 6.6): the glasses get session state and that user's hints only | Matheus (sign-off) | Sign-off: 0 (a decision) |
| 6 | No exit gesture defined or shown on screen | Unchanged. `apps/glasses/README.md` already claims "back closes the agent" but this was never verified on the hardware, and the screen gives no hint of it | whoever owns `apps/glasses` (undecided, see D-31/PR #3) | Small, but needs a real device to verify the gesture first |
| 7 | AGENTS.md section 1 still lists Mochi AR as not part of the hackathon build | Unchanged on purpose (D-31's changelog note): a team decision, not mine to make | the team | 0 (a decision) |

## 3. Latency, measured this session

Measured the leg this project controls: from the turn reaching the backend to `hint.created`
landing on a `?user=ana&surface=ar` connection, over the same public ngrok tunnel a real device
would use (`scripts/tunnel.sh`), for the lexicon-only path (no model call):

```
162.9 ms / 201.0 ms / 272.2 ms  (three runs, "I need to adiar my meeting tomorrow")
```

That leg is not the risk. The risk is upstream, from numbers the team already measured for other
reasons:

| Leg | Measured | Source |
|---|---|---|
| Speech ends → turn reaches the backend (ASR) | 1.1 s (ARES) to 1.5 s (`gpt-4o-transcribe`), includes a 0.6 s end-of-speech wait | D-25 |
| Hint model answers (needed for trails_off/restarts/talks_around; NOT needed for code_switch) | 0.68 s median (gpt-5.4-mini) to 1.05 s (gpt-4.1-mini); a hedge retry adds up to 1 s more if the first call is slow | D-29 |
| decide() → glasses socket (this session's measurement) | 0.16-0.27 s |

**Estimated total for the harder case this feature exists for** (trails_off/restarts/talks_around,
which always needs the model): **~2.0-2.9 s typical**, with a worst case over 4 s if the hedge
retry fires. The spec's own target is "1 to 2 seconds." **This is very likely too slow as built**,
and nothing in D-31 can fix it: the time is in ASR and the model call, not in the candidates logic.
Not yet measured: a real spoken "I wanted to go, but…" end to end (only typed-turn timing exists).

## 4. Plan, phased by who can do it without new hardware or a human decision

### Phase A — software, can start now, no device needed
1. **Measure the real number** (closes most of gap 4): a scripted spoken test, as D-25/D-29 did for
   other sentences, but for `trails_off`/`restarts`/`talks_around` specifically, with
   `MODEL_API_KEY` set. Tells us whether Phase B's ordering matters.
2. ~~**`&surface=ar` in the gateway**~~ **Done on `main`** (connection routing). Still open: whether
   `candidates` should reach only the glasses and not the phone. Was: **only if the team wants AR-exclusive
   suggestions** (today a hint with `candidates` also reaches that person's phone, which may be
   fine — Companhia's Mobile view is already personal). Small: `gateway/delivery_rules.py` would
   gate on `candidates is not None` the same way it already gates on `target_user_id`. Luís's
   file; I can draft it if the team wants it, but I should not edit `gateway/` unasked.
3. **On-screen exit hint** (closes the visible half of gap 6): a small status line
   ("back to close") in `pages/fluency/index.ink`. Low risk, but the gesture itself needs
   verifying on the real glasses first (see Phase B.2) — doing the screen text before that risks
   telling the wearer something untrue.

### Phase B — needs the physical glasses or Render, can't be done from here
1. **A real public URL that survives more than a dev session**: either Render (set
   `MOCHI_DEVICE_KEY` and `MODEL_API_KEY` in its dashboard first — the one hard blocker, already
   called out when PR #2 merged) or a paid/reserved tunnel. ngrok's free URL from this session
   will rotate; whoever repackages needs the current one.
2. **The exact steps already named in the spec**: put the URL in `config.js` (Studio's Code tab),
   `Package AIX`, update through Hi Rokid, then `scripts/say.sh "I wanted to go, but..."` — this
   is the actual first time a real suggestion reaches the device, not the ngrok test from this
   session (that only proved the Mac-to-cloud leg, not the installed package).
3. **Verify the exit gesture** ("back") actually closes the agent on this hardware, and only then
   add the on-screen hint from Phase A.3.

### Phase C — needs a team decision, not code
1. Matheus's sign-off on `Hint.candidates`/`context` (gap 5).
2. Whether Mochi AR is in the hackathon demo at all (gap 7) — AGENTS.md section 1 still says no.
3. Whether `&surface=ar` should actually suppress the phone's copy of the hint (feeds Phase A.2).
4. Pairing/login and `/ws` auth (gaps 2, 3) — explicitly out of scope per the spec itself; listed
   here only so the team sees it was not forgotten, not dropped silently.

## 5. What this session already closed, for the record
- D-31: `candidates`/`context`, gated to the three reasons with no single known word; fixtures,
  unit tests, `make verify` green (1103 tests after rebasing on `main`).
- Verified live: the whole chain (gateway → public tunnel → a glasses-shaped WebSocket connection)
  needs zero changes in `gateway/` or `apps/glasses/` for the new fields to arrive correctly.
- Measured the one leg this project fully controls (section 3).
