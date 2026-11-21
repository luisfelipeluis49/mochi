# Proposal: the phone as Mochi's microphone (owner of the idea: Tasnim; backend draft for Luís)

**Status:** PROPOSED. AGENTS.md section 8 lists "the phone as a microphone" as out of scope *unless a
human asks*. Tasnim asks for it here; Luís (gateway) and Matheus (contracts) decide.

## What it should do

Two kinds of session, kept apart:

| Started on | Who listens | Live hints show on | The phone during the session |
|---|---|---|---|
| **the phone** (Start on `/m`) | the phone's mic | that phone (and the Home/Audience views over WebSocket) | live hint and cards, as today |
| **the Pi** ("Oi, Mochi!") | the Pi's M1A | the Pi | nothing live; the analytics appear after Stop |

Use case: practising on the street, with no Pi nearby.

## Contract additions (all additive; nothing in 6.1–6.6 changes)

```text
POST /api/sessions/demo/start   body gains an optional "source": "device" | "phone"  (default "device")
                                 { "source": "phone" }  -> a phone session
                                 no body / { "woken_by": "oi mochi" } -> a device session, exactly as today
                                 any other source -> 422
GET  /api/sessions/demo/phone-audio
     -> { "app_id", "channel", "uid", "token" }   while a phone session runs (same shape as the device's "agora")
     -> 409                                        otherwise
GET  /api/devices/home_pi_01/state
     while a phone session runs: { "capturing": false, "agora": null, "speaker_muted": false }
     so the Pi bridge stays out (it joins nothing and gets no commands, hints included)
```

- The phone joins with the **Pi's uid** (`MOCHI_PI_UID`): the Agora agent listens to exactly one remote
  uid, so it needs no change. This is safe only because the Pi is kept out during a phone session
  (two clients with one uid in a channel would kick each other).
- A second Start while a session runs keeps the running session's source. Stop resets it to "device".
- The session/WebSocket events do not change. The Mobile view remembers locally (`sessionStorage`) whether
  *it* started the session, only to hide live words during a Pi session; who gets which event is still
  decided in the gateway.

## Known limits

- One phone session at a time (there is one session, `demo`).
- No speaker identification on a phone: hints go by the whose-word rule (AGENTS.md 7.3), like on the Pi.
- The phone's token is the same token the Pi gets; the route is open like `/start` (no sign-in in the MVP).
- iPhone/Android need **https** for the microphone (the Vercel link, not `http://<laptop-ip>:5173`).
- The web app loads the Agora Web SDK (`AgoraRTC_N-4.24.8.js`) from `download.agora.io` when the mic
  starts: no new npm dependency.
