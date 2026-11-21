# Mochi AR

Mochi turns conversations into language practice. Mochi AR is its smart-glasses add-on, and it has one job, the Fluency Helper: when the wearer hesitates while speaking, one to three suggested words or phrases appear privately in their view, each with a short meaning.

## How to work

- Stay quiet. Show nothing but a small status line until suggestions arrive.
- Show at most three suggestions, and an optional short line of where the speaker stopped. Suggestions are options, not a script.
- Remove them when their time is up, or at once when the wearer taps.
- Never decide what to show or when. Suggestions come from the Mochi backend over `GET /ws?user=<id>&surface=ar`; whatever arrives for this person is shown, and nothing else.
- Never listen. The glasses' microphone and camera are not used; Mochi Home hears the conversation.

## Pages

- `pages/fluency/index` (entry): the Fluency Helper. Enter (temple tap) dismisses the suggestions; back closes the agent.

## Capabilities

- Permissions: `INTERNET` (WebSocket to the Mochi backend).
- Without a configured backend, the page runs in demo mode and replays example suggestions.
