# The phone as Mochi's microphone (owner: Tasnim, `apps/web` only)

**No backend change.** AGENTS.md section 8 lists "the phone as a microphone" as out of scope unless a
human asks; Tasnim asks. Use case: practising on the street, with no Pi nearby.

| Started on | Who listens | Live hints | The phone during the session |
|---|---|---|---|
| **the phone** (Iniciar on `/m`, or Record on `/me`) | the phone's mic | on that phone | live hint and cards |
| **the Pi** ("Oi, Mochi!") | the Pi's M1A | on the Pi | nothing live; the analytics appear after Stop |

## How (only routes that exist today)

1. Iniciar (`/m`) or Record a conversation (`/me`) → `POST /api/sessions/demo/start` (no body, exactly as today).
2. `GET /api/devices/home_pi_01/state` → its `agora` block `{ app_id, channel, uid, token }`.
3. The phone joins that Agora channel with its mic (Agora Web SDK `AgoraRTC_N-4.24.8.js` from
   `download.agora.io`, loaded only then: no new npm dependency) and plays Mochi's voice.
4. Parar / Stop and save → leaves the channel, then `POST /api/sessions/demo/stop`.

The Mobile view remembers locally (`sessionStorage`) whether *it* started the session, only to hide live
words during a session started on the Pi.

## Limits (each needs a backend change to remove — Luís decides)

- **The Pi must be off during a phone session.** The phone joins with the Pi's uid because Mochi's agent
  listens to that one uid. If the Pi is on, it sees `capturing: true`, joins with the same uid, the two
  kick each other out, and the Pi also shows the hints. Fix: a start that says it came from a phone and a
  device state that keeps the Pi out.
- One session at a time (`demo`). No speaker identification on a phone (AGENTS.md 7.3 decides).
- iPhone/Android need **https** for the mic (the Vercel link, not `http://<laptop-ip>:5173`).

## Update (D-41): the limits above are gone

The backend now keeps one session per phone (`/api/sessions/<id>/...`, its own Agora channel and turn
endpoint). The phone no longer reads the Pi's device state; it joins with `GET /api/sessions/<id>/agora`.
The Pi can be on during a phone session, and a phone's Stop never stops the Pi. `?session=demo` on `/m`
makes a phone the Pi's remote control (no microphone). See docs/DECISIONS.md D-41.
