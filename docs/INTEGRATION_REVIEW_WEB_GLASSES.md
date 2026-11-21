# Integration review of apps/web and apps/glasses (2026-11-21)

Scope: Tasnim's web app (`202b1e0`) and Suhuai's Mochi AR (`31184c7`, PR #3), merged on top of the first review
(PR #2). Three read-only reviewers (web, glasses, merge/docs); claims marked **confirmed** were re-checked in the
code here. Both apps' own tests pass (web 28, glasses 25); the web app was never type-checked or built (no lockfile,
no installed compiler). CI `verify` was green on all four merges.

Bottom line: the merges changed only `apps/`; none of our PR #2 fixes was reverted. The risks are at the seams
between the apps and the backend.

## Findings

Bucket: **B** fixed in the fix PR, **C** needs a team decision (written here, not coded), **A** the code is fine and
AGENTS.md or a doc should say so.

| # | Finding | Check | Bucket | Owner |
|---|---|---|---|---|
| 1 | Web demo uses user `sophie` (`/m?user=sophie`, mock, tests, README); the backend only knows `ana` and `ben`, so Sophie's phone is closed with 4400 and the web retries every 2 s forever | confirmed (roster, connections) | C (rename) + B (web stops retrying on 4400 and shows why) | Tasnim, Luis |
| 2 | Nothing starts a Describe & Guess round except `curl`: `activityStart` is defined but no view calls it, and no voice start exists | confirmed (no caller in the views) | C (demo step 3 cannot run from the UI) | Tasnim, Kauê |
| 3 | After a reconnect or reload during a round the Home view gets no private prompt (not in the snapshot) and stays on "turn me to you" with no way to finish | confirmed (snapshot has session, activity, hint only) | B | Luis |
| 4 | Audience stays on ROUND_RESULT for good: the gateway never goes back to IDLE and the view has no cutoff, so later hints never reach the projector | reported; the view has no timer (confirmed) | B (view returns to the face after a few seconds) | Tasnim |
| 5 | `?debug=1` prints every payload on every view, so the secret word shows on Mochi's screen before the describer taps | reported (Home receives the private prompt) | B (the panel hides secret words) | Tasnim |
| 6 | Hint expiry compares the server's `expires_at` with the device's clock; a Pi clock a few seconds ahead hides every hint | reported | C (use the server's `hint.cleared`) | Tasnim |
| 7 | `surface=ar` is ignored by the backend: the glasses are a full phone connection and receive the wearer's learning events and every hint | confirmed (no handling in `parse_target`, delivery rules) | B (hints only, proposed in AGENTS 6.6) | Luis, Suhuai |
| 8 | A bad `?user=` is accepted, then closed with 4400; the glasses reset their backoff on open, so they reconnect every second forever, with no cause shown | confirmed (`attempts = 0` on open) | B | Suhuai |
| 9 | Hints addressed to nobody (`target_user_id` null) reach every pair of glasses; the client does not compare with the wearer | reported | B (show only hints for the wearer, or for nobody) | Suhuai |
| 10 | The glasses expect `candidates` and `context` on a Hint; the contract model forbids extra fields and nothing emits them (only the mock does). The web splits `expression` on " · " but the glasses do not | reported (backend emits none: confirmed) | C (one agreed rule) | Suhuai, Tasnim, Matheus |
| 11 | `contracts.ts` (web) carries v0.5 items (`choosing`, `practice`, `practice_partner`, `session.summary.created`) that exist nowhere in `packages/contracts`; the summary page can never fill on the real backend | confirmed (proposal doc says mock-only) | C | Matheus |
| 12 | Hand-copied types: `Activity` nullable fields typed non-null | reported | B (small) | Tasnim |
| 13 | No `package-lock.json` or `.gitignore` in `apps/web`, no `node_modules/` in the root `.gitignore`: `npm ci` fails and `git add -A` after `npm install` would commit `node_modules` | confirmed | B | Tasnim, Luis |
| 14 | CI runs only `make verify`; nothing runs the apps' tests, `tsc` or `vite build` | confirmed (reviewer read the workflow) | B (a job) | Luis |
| 15 | `apps/glasses/AGENTS.md` exists next to the root `AGENTS.md`, states `surface=ar` and three suggestions as settled, and does not mention the root rules | confirmed | B (one line pointing to the root file) | Suhuai |
| 16 | Mochi AR is out of the hackathon build (AGENTS Section 1) and has no owner in Sections 5 and 9; PROVENANCE says `apps/web` is "not started here" and has no row for `apps/glasses` | confirmed | B (docs) | Luis |
| 17 | The glasses' tests overclaim (the mock gates on `surface`, the real gateway does not); the mock accepts any user and sends no `activity.state.changed` or `hint.cleared` | reported | C | Suhuai |
| 18 | No connect timeout (a Render free-plan cold start leaves CONNECTING forever); bad URL loops silently; build for Ana worn by Ben | reported | B (timeout, scheme check) / C | Suhuai |
| 19 | The Home view's second tap gets 409 if the round already ended and keeps re-revealing | reported | B (small) | Tasnim |
| 20 | `?mock=1` works on any deployed URL; `VITE_BACKEND_URL` is not documented and no static hosting exists in `render.yaml` | reported | C (where is the web app served from?) | Luis, Tasnim |
| 21 | Mobile "progress" and summary pages are out of scope in AGENTS v0.5 Section 8; only "My words" is in | confirmed (README) | C | team |

Checked and fine: HTTP paths and bodies for start, stop and activity/result match the routes; sequence dedupe
tolerates the snapshot's fresh sequence numbers; no secrets in either app; no microphone or camera use in the
glasses (`INTERNET` only); the backend image excludes `apps/`; the secret word never reaches the Audience or the
phones through the normal path.

Not verified: real touch on the 3.5-inch panel, Rokid runtime WebSocket behaviour, a Render cold start with the
glasses, `vite build`, and anything against the live backend.
