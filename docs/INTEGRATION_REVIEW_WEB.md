# Integration review: apps/web and the shared seams (2026-11-21)

Part of an integration review of the two apps merged after the first review (PR #2): Tasnim's web app (`202b1e0`)
and Suhuai's Mochi AR (PR #3). This file lists the findings for **apps/web, the CI job, `.gitignore`, PROVENANCE and README**; the other half is in `docs/INTEGRATION_REVIEW_GLASSES.md`.
Three read-only reviewers; claims marked **confirmed** were re-checked in the code. The merges changed only
`apps/`; none of the fixes from PR #2 was reverted. Bucket: **B** fixed in the PR, **C** needs a team decision
(written here, not coded), **A** the code is fine and a document should say so. Finding numbers are shared by both
files.

| # | Finding | Check | Bucket | Owner |
|---|---|---|---|---|
| 1 | Web demo uses user `sophie` (`/m?user=sophie`, mock, tests, README); the backend only knows `ana` and `ben`, so Sophie's phone is closed with 4400 and the web retries every 2 s forever | confirmed (roster, connections) | C (rename) + B (web stops retrying on 4400 and shows why) | Tasnim, Luis |
| 2 | Nothing starts a Describe & Guess round except `curl`: `activityStart` is defined but no view calls it, and no voice start exists | confirmed (no caller in the views) | C (demo step 3 cannot run from the UI) | Tasnim, Kauê |
| 3 | After a reconnect or reload during a round the Home view gets no private prompt (not in the snapshot) and stays on "turn me to you" with no way to finish | confirmed (snapshot has session, activity, hint only) | B | Luis |
| 4 | Audience stays on ROUND_RESULT for good: the gateway never goes back to IDLE and the view has no cutoff, so later hints never reach the projector | reported; the view has no timer (confirmed) | B (view returns to the face after a few seconds) | Tasnim |
| 5 | `?debug=1` prints every payload on every view, so the secret word shows on Mochi's screen before the describer taps | reported (Home receives the private prompt) | B (the panel hides secret words) | Tasnim |
| 6 | Hint expiry compares the server's `expires_at` with the device's clock; a Pi clock a few seconds ahead hides every hint | reported | C (use the server's `hint.cleared`) | Tasnim |
| 11 | `contracts.ts` (web) carries v0.5 items (`choosing`, `practice`, `practice_partner`, `session.summary.created`) that exist nowhere in `packages/contracts`; the summary page can never fill on the real backend | confirmed (proposal doc says mock-only) | C | Matheus |
| 12 | Hand-copied types: `Activity` nullable fields typed non-null | reported | B (small) | Tasnim |
| 13 | No `package-lock.json` or `.gitignore` in `apps/web`, no `node_modules/` in the root `.gitignore`: `npm ci` fails and `git add -A` after `npm install` would commit `node_modules` | confirmed | B | Tasnim, Luis |
| 14 | CI runs only `make verify`; nothing runs the apps' tests, `tsc` or `vite build` | confirmed (reviewer read the workflow) | B (a job) | Luis |
| 16 | Mochi AR is out of the hackathon build (AGENTS Section 1) and has no owner in Sections 5 and 9; PROVENANCE says `apps/web` is "not started here" and has no row for `apps/glasses` | confirmed | B (docs) | Luis |
| 19 | The Home view's second tap gets 409 if the round already ended and keeps re-revealing | reported | B (small) | Tasnim |
| 20 | `?mock=1` works on any deployed URL; `VITE_BACKEND_URL` is not documented and no static hosting exists in `render.yaml` | reported | C (where is the web app served from?) | Luis, Tasnim |
| 21 | Mobile "progress" and summary pages are out of scope in AGENTS v0.5 Section 8; only "My words" is in | confirmed (README) | C | team |

Not verified: a browser, the Pi's touch screen, the Rokid runtime, a Render cold start with the glasses, the CI job on GitHub.
