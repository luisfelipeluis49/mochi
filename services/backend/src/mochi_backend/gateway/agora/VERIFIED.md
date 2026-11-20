# Agora facts verified for this build

Checked on **2026-11-19** through the Agora docs MCP (`docs_portal_en` index) and the docs pages
below. The docs pages show no version number or last-updated date ("Documentation version: Main").
Re-check before the demo; update this file when anything changes.

## Verified (field names are used in `rest_client.py`)

| Topic | Fact | Source |
|---|---|---|
| Start agent | `POST https://api.agora.io/api/conversational-ai-agent/v2/projects/{appid}/join`; body `name` (unique) + `properties`; reply has `agent_id` | https://docs.agora.io/en/api-reference/api-ref/conversational-ai/join |
| Stop agent | `POST .../agents/{agentId}/leave`, no body, 200 empty | https://docs.agora.io/en/api-reference/api-ref/conversational-ai/leave |
| REST auth | `Authorization: Basic base64(customer_id:customer_secret)` (Console "RESTful API Keys") | https://docs.agora.io/en/api-reference/api-ref/conversational-ai/authentication |
| Custom LLM | `properties.llm.url` (our endpoint), `api_key` ("verification key", default ""), `headers` (object: "custom headers to include in requests to the LLM"), `style` `openai`, `max_history` | join page (search index, 2026-11-19) |
| Custom LLM request | OpenAI Chat Completions format; `stream` defaults to **true**; samples answer 400 when `stream` is false; roles system/user/assistant/tool; user content is a string or parts | https://docs.agora.io/en/ai/build/custom-model-integration/custom-llm |
| Custom LLM reply | SSE: `data: <json chunk>` + blank line per chunk, ending `data: [DONE]` | same page |
| Agent id | field `agent_id` in the join reply | join page |
| Agent / device uids | `properties.agent_rtc_uid` (string), `properties.remote_rtc_uids` (array of strings, one) | join page |
| Speak without a turn | `POST .../agents/{agentId}/speak` `{text (max 512 bytes), priority INTERRUPT|APPEND|IGNORE, interruptable}` | https://docs.agora.io/en/api-reference/api-ref/conversational-ai/speak |
| Silence off | `parameters.silence_config.timeout_ms` default 0; greeting/failure message omitted | join page |
| Turn detection | `turn_detection.config.end_of_speech.mode = vad`, `vad_config.silence_duration_ms` | join page |

## How the shared key reaches us (decision)

The docs do not say which header carries `api_key`. We therefore send the key two ways and accept both:
`llm.api_key` (whatever header Agora uses for it, probably `Authorization: Bearer`) and our own
header `X-Mochi-Key` through `llm.headers`. **Unverified:** that `llm.headers` values arrive as given.

## Not verified (settle on real hardware or with Agora support)

1. **Empty reply keeps the agent silent** (AGENTS 12.1). Not documented. Fallback: `MOCHI_SILENCE_STRATEGY=mute_speaker`.
2. **en + pt-BR in one session** (AGENTS 12.2). `asr.language` is one BCP-47 tag (default `en-US`); no documented multi-language or code-switching option. Vendor parameter pages were not read. Configure through `MOCHI_ASR_VENDOR`, `MOCHI_ASR_LANGUAGE`, `MOCHI_ASR_PARAMS`.
3. **TTS voices for en and pt-BR.** Not found; set `MOCHI_TTS_VENDOR` and `MOCHI_TTS_PARAMS`.
4. **Semantic end-of-speech** supports en/zh only per the docs (the page contradicts itself); we use VAD with `MOCHI_END_OF_SPEECH_SILENCE_MS`.
5. **Which uid the `properties.token` must be built for.** We build it for the agent uid.
6. **Finished-speaking signal.** Webhooks carry no "speaking finished" event; the client toolkit has `AGENT_SPEAKING_CHANGED` (needs RTM, client side only). So the mute fallback ends its window by the word-count formula.
7. **Barge-in:** `properties.interruption` (`enable`, default true) exists; not tuned.

## Tested against real Agora (2026-11-20, from a local backend in real mode)

Observed, not just read in docs:
- `POST .../join` with Basic auth (REST key/secret) and a `006` RTC token **returned 200 with an agent id**;
  `.../leave` worked; a second Start/Stop cycle worked. So the `006` token and the agent-uid token were accepted.
- **Managed `ares` ASR is rejected** on our project: `vendor 'ares' is not available for the current SKU when
  credential_mode is 'managed'` (HTTP 400, `InvalidFieldValue`). Docs list ARES as managed; this project cannot use it.
- **Managed `deepgram` ASR (`nova-3`, `language: multi`) and managed `minimax` TTS (`speech-2.8-turbo`) were accepted.**
  Accepted is not the same as working: that the agent transcribes pt-BR, or speaks pt-BR, is still unverified (needs a mic).
- `POST .../speak` (activity host line) raised no error. Azure/Microsoft needs your own Azure key (BYOK) and was not tried.
- Pricing page: first 300 agent minutes free, then $0.10/min, even with BYOK (https://docs.agora.io/en/ai/reference/pricing).
  Keep agent sessions short while testing.
- `asr.params` is omitted when empty and `credential_mode` is sent only when set (nested JSON params are allowed).

## Idle timeout and lifetime (docs, 2026-11-20)

`properties.idle_timeout` (integer seconds, 0 to 259200, documented default 30): after all users in
`remote_rtc_uids` have left, the agent exits once this much idle time passes; 0 means never. A session also
ends after 72 hours whatever the value (https://docs.agora.io/en/api-reference/api-ref/conversational-ai/join).
We send it from `MOCHI_AGENT_IDLE_TIMEOUT_SECONDS` (default 60). Not documented: what happens when none of the
listed users ever joins. A Start with no Pi can therefore keep an agent (and its billed minutes) alive until we
call Stop; see the auto-stop proposal in DECISIONS D-19.

## RTC tokens

The Agora tutorial (https://docs.agora.io/en/ai/build/build-server-client) uses the PyPI package
`agora-token-builder` (pinned in `uv.lock`; installed 1.0.0). It exposes
`RtcTokenBuilder.buildTokenWithUid(appId, cert, channel, uid, role, privilegeExpiredTs)` and, on this
machine, produces **`006`-prefixed (AccessToken v1) tokens**, not AccessToken2 (`007`). Tested 2026-11-20:
Agora's `join` accepted the agent-uid `006` token (see "Tested against real Agora" above). Not checked: whether
a `007` builder is on PyPI, and whether the Pi's IoT SDK accepts a `006` token for the Pi uid.
This is not the Agora Python RTC *SDK* that AGENTS forbids on the Pi (that rule is about the Pi; the backend only builds tokens).

## Conflicts with AGENTS.md

- AGENTS 6.4 says Agora authenticates with "our shared key" without naming the header; the docs do not
  say either (see above). No contract change needed.
- AGENTS 9.2 assumes an empty reply is possible; the docs' samples always stream at least one chunk. Our
  empty reply is a stream with one empty-content chunk, a stop chunk and `[DONE]`.
