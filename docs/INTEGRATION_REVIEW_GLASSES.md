# Integration review: apps/glasses (Mochi AR) (2026-11-21)

Part of an integration review of the two apps merged after the first review (PR #2): Tasnim's web app (`202b1e0`)
and Suhuai's Mochi AR (PR #3). This file lists the findings for **apps/glasses and the `surface=ar` connection**; the other half is in `docs/INTEGRATION_REVIEW_WEB.md`.
Three read-only reviewers; claims marked **confirmed** were re-checked in the code. The merges changed only
`apps/`; none of the fixes from PR #2 was reverted. Bucket: **B** fixed in the PR, **C** needs a team decision
(written here, not coded), **A** the code is fine and a document should say so. Finding numbers are shared by both
files.

| # | Finding | Check | Bucket | Owner |
|---|---|---|---|---|
| 7 | `surface=ar` is ignored by the backend: the glasses are a full phone connection and receive the wearer's learning events and every hint | confirmed (no handling in `parse_target`, delivery rules) | B (hints only, proposed in AGENTS 6.6) | Luis, Suhuai |
| 8 | A bad `?user=` is accepted, then closed with 4400; the glasses reset their backoff on open, so they reconnect every second forever, with no cause shown | confirmed (`attempts = 0` on open) | B | Suhuai |
| 9 | Hints addressed to nobody (`target_user_id` null) reach every pair of glasses; the client does not compare with the wearer | reported | B (show only hints for the wearer, or for nobody) | Suhuai |
| 10 | The glasses expect `candidates` and `context` on a Hint; the contract model forbids extra fields and nothing emits them (only the mock does). The web splits `expression` on " · " but the glasses do not | reported (backend emits none: confirmed) | C (one agreed rule) | Suhuai, Tasnim, Matheus |
| 15 | `apps/glasses/AGENTS.md` exists next to the root `AGENTS.md`, states `surface=ar` and three suggestions as settled, and does not mention the root rules | confirmed | B (one line pointing to the root file) | Suhuai |
| 17 | The glasses' tests overclaim (the mock gates on `surface`, the real gateway does not); the mock accepts any user and sends no `activity.state.changed` or `hint.cleared` | reported | C | Suhuai |
| 18 | No connect timeout (a Render free-plan cold start leaves CONNECTING forever); bad URL loops silently; build for Ana worn by Ben | reported | B (timeout, scheme check) / C | Suhuai |

Not verified: a browser, the Pi's touch screen, the Rokid runtime, a Render cold start with the glasses, the CI job on GitHub.

## Live check (real WebSocket, local backend in fake-Agora mode)

| Connection | Result |
|---|---|
| `?user=sophie&surface=ar` | closed 4400, reason names the allowed values |
| `?user=ana&surface=vr` | closed 4400, "unknown surface 'vr'" |
| Ana's glasses after "I need to adiar my meeting tomorrow." | `hint.created` only; no learning event |
| Ana's phone, same turn | `learning_event.created` and `hint.created` |
| Ben's glasses | nothing |

Left for the team: one rule for `candidates` / `context` / " · " options (Matheus, Suhuai, Tasnim), and the glasses'
mock still accepts the rejected-user case only as a scripted scenario. Not verified: the Rokid runtime, a Render
cold start with the glasses.
