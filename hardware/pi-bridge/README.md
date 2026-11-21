# Pi bridge

Sends the EMEET M1A microphone into an Agora channel and plays what the channel sends back
through the M1A. No decisions, no transcription, no UI (AGENTS.md §9.1). Built on the Agora
IoT SDK (RTSA Lite) v1.9.7, aarch64-linux-gnu, C API.

```text
M1A mic  --ALSA 16 kHz mono-->  agora_rtc_send_audio_data  (SDK encodes Opus)
M1A spk  <--ALSA (plughw)----  ring buffer  <--  on_audio_data (SDK decodes to PCM)
```

## Setup (once)

```bash
sudo apt install libasound2-dev     # already on the Mochi Pi
./scripts/fetch-sdk.sh              # downloads the SDK into third_party/ (gitignored, ~21 MB)
cp .env.example .env                # fill in AGORA_APP_ID (and AGORA_TOKEN if certificate is on)
make
```

## Run

```bash
./scripts/m1a-test.sh               # no Agora: record 5 s, play it back
./scripts/run.sh                    # loads .env, builds, joins $AGORA_CHANNEL
./scripts/run.sh -c other-channel --sdk-aec
```

Once a second it prints a status line:

```text
[bridge] joined | sent 50 frames/s | recv 50 cb/s 32000 B/s (type 100) | speaker silence 0/50
```

- `sent 50 frames/s`: microphone is flowing (20 ms frames).
- `recv ... (type 100)`: decoded PCM from the channel is arriving and being played.
- `speaker silence 50/50` while nobody talks is normal.

## M0 test (no backend needed)

1. Run the bridge on channel `mochi-test`.
2. On a laptop, open the [Agora web demo](https://webdemo-global.agora.io/example/quickStart/videoAndVoiceCalling/index.html),
   enter the same App ID and channel, join. **Wear headphones on the laptop.**
3. Talk into the M1A, hear it on the laptop. Talk on the laptop, hear it from the M1A.
4. Check echo: while the laptop talks, the laptop should not hear itself back from the M1A.
   If it does, retry with `--sdk-aec`.

Then join the channel Luís's Agora agent uses: speech into the M1A should show up in the backend log.

## Wake phrases (offline)

`./scripts/mochi.sh` runs the supervisor: the Pi listens locally, starts an Agora session when it
hears a wake phrase ("oi Mochi", "hi Mochi", ...) and ends it on a goodbye phrase or a timeout.
Phrases and tolerances are in `config/mochi.toml`.

```text
mic -> Silero VAD -> ZIPA phone recogniser -> phrase matcher     (mochi_device/wakeword.py, phrases.py)
```

Speech is recognised as sounds, not words (`haɪmoʊtʃi`, `ojmɔtɕi`), so English and Brazilian
Portuguese share one 71 MB model and the spelling of "Mochi" never matters.

```bash
./scripts/fetch-wake-model.sh       # once; mochi.sh also does it when the files are missing
./scripts/wake-test.sh              # no Agora: prints what the Pi hears and every match
.venv/bin/python -m unittest discover tests
```

To keep it running (starts at boot, restarts if it stops), install it as a user service:

```bash
../pi-setup/mochi-service.sh        # undo with --remove
journalctl --user-unit mochi -f       # live log: every wake, session start and end
systemctl --user restart mochi      # after editing config/mochi.toml or .env
```

Who runs the session is `[backend].kind` in the config (`mochi_device/backends.py`). To choose
for one device without touching the shared file, put only the keys that differ in
`config/mochi.local.toml` (not in git), for example `[backend]` / `kind = "mochi_backend"`.

- `mochi_backend`: Luís's backend runs the session and decides what Mochi says (quiet unless it
  is spoken to; with a model key there, in Mochi's character). The Pi asks it to start
  (`POST /api/sessions/demo/start`, with the wake phrase it heard), joins with what
  `GET /api/devices/home_pi_01/state` returns, and keeps reading that state every
  `poll_interval_s`:
  - `capturing` false: the Pi leaves the channel.
  - `speaker_muted` true: the speaker is silent.
  - `commands`: what Mochi wants its body to do, each once: `mood` and `show` go to the face,
    `volume` to the speaker, `temp` shows the temperature, `enroll` / `forget` learn and forget a
    voice.
  The Pi reports its volume, temperature, the voices it knows and who is talking
  (`POST .../status`) whenever one changes, and how learning a voice ended (`POST .../voices`).
  Set `mochi_backend_url` to where the backend runs. If the backend cannot start a session (down,
  unreachable), the session does not start (`fallback = "none"`, the default: the Pi decides
  nothing and holds no App Certificate). To let Mochi's own agent take that session instead, set
  `fallback = "test_agent"` in `[backend]` (needs `AGORA_APP_ID` and `AGORA_APP_CERTIFICATE` on the
  Pi; the agent then decides on the device, so use it for demos only).
  When the backend requires a device key, put it in `.env` as `MOCHI_DEVICE_KEY` (or `device_key` in
  `[backend]`); it is sent as `Authorization: Bearer <key>` on `POST .../status` and `.../voices`
  and never logged. A wake-up that has not produced a session after `[session] start_timeout_s`
  (25 s) is given up and Mochi goes back to listening.
- `test_agent` (the default): a stand-in agent, for working without the backend.

The stand-in's character and the way it helps (clue first, the word in a sentence,
"your turn", saying a slip back the right way, nudging the two people toward each other) are the
`instructions` in `config/mochi.toml`. It understands and speaks English and Brazilian Portuguese
and greets in the language of the wake phrase.

Ears and voice are Agora-managed services chosen in `[test_agent]` (no keys of our own):

- **Speech recognition:** Agora's ARES with `en-US,pt-PT`. On 14 ordinary English and Portuguese
  sentences it made no mistakes where Deepgram nova-3 `multi` made 5 % word errors (it also spells
  "Mochi" right), and on learner-style mixed sentences 20 % against 67 %. A foreign word inside a
  sentence is still its weak spot ("guarda-chuva" -> "guardy shoe"), so the agent is told to read
  odd words by their sound.
- **Voice:** MiniMax `speech_2_8_turbo`. No managed voice pronounces a Portuguese word natively
  inside an English sentence (or the reverse), but whole sentences come out right, so the agent
  mixes languages sentence by sentence: "Window? Em português a gente fala janela."

The agent runs in Agora's cloud and cannot reach the Pi, so it acts through silent tags at the start
of a reply, which the speech synthesis skips and the Pi reads from the conversation history about a
second later:

| Tag | What the Pi does |
|---|---|
| `[mood happy]` | expression on the face (happy, excited, love, laughing, surprised, curious, proud, oops, cool, sleepy) |
| `[show umbrella]` | shows the word big under the face for ten seconds |
| `[volume 60]` | sets the speaker level (`mochi_device/device.py`; never below `min_volume`) |
| `[temp]` | shows the processor temperature it is telling |

## Voices: who is talking

Mochi can learn a voice by being asked, in either language, during a session:

```text
"Mochi, learn my voice. I'm Ben."      -> Mochi asks him to keep talking for about ten seconds
"Mochi, aprende a minha voz. Eu sou a Ana."   ... then says "Got it, Ben!" / "Pronto, Ana!"
"Mochi, forget my voice."
```

From then on the Pi recognises who is talking about 0.8 s into each turn (`mochi_device/speakers.py`:
3D-Speaker CAM++ embeddings through sherpa-onnx, about 50 ms per check), shows the name on the
screen and tells the agent, which then knows whether it is talking to Ana or Ben. An unknown voice
stays unknown. The Pi keeps its voiceprints in `data/voices.json`, and with `kind = "mochi_backend"` it also
sends each one to the backend's database (`PUT .../voices/{name}/voiceprint`, device key required) after
learning it. At the start of each session it adds the voices the backend has and it lacks, so a replaced
or reflashed Pi gets its voices back, and sends the ones the backend lacks. It only ever adds: a failed or
empty answer never deletes anything here. To forget someone for good, ask Mochi ("forget my voice"): that
deletes both copies; deleting `data/voices.json` alone only forgets them until the next session. Anything else that has a recording, such as a phone app later, can enrol through
the same `Voices.learn(name, audio)`. Tolerances are under `[voices]` in the config.

Limits: a turn with less than half a second of speech is not attributed, nor is someone talking over
Mochi; a voice learned in one language is recognised less surely in the other, so it helps to say
something in both while enrolling.

| Tag | What the Pi does |
|---|---|
| `[enroll Ana pt]` | learns Ana's voice from the next ~7 s of speech, then confirms aloud in that language |
| `[forget Ana]` | drops that voiceprint |

## Mochi's face

`hardware/pi-setup/face.html` is the page on Mochi's own screen (`kiosk.sh` opens it by default). The
supervisor tells it what Mochi is doing over server-sent events on `127.0.0.1:8765`
(`mochi_device/face.py`): asleep, waking, listening, thinking, speaking (the mouth follows the
loudness of the voice, reported by the bridge with `--levels`), saying goodbye. Without the
supervisor the face just sleeps and reconnects by itself.

```bash
../pi-setup/display-setup.sh        # once: screen upside down for the shell + 30 Hz (see the script)
../pi-setup/kiosk-autostart.sh      # once: open the face when the desktop starts
../pi-setup/kiosk.sh "file://$PWD/../pi-setup/face.html?demo=1"   # walk through every expression
../pi-setup/kiosk.sh off            # black page for the night; ../pi-setup/kiosk.sh brings the face back
```

A session ends on a goodbye phrase, after `inactivity_timeout_s` without a voice, or at
`max_session_s`. Stop the service before running `wake-test.sh` or `mochi.sh` by hand: only one
program can hold the microphone.

If Mochi misses someone, run `wake-test.sh`, have them say the phrase, and look at the `heard` line:
raise `name_tolerance`, or add how they say a word under `[listening.sounds]`.

## Notes

- The ALSA device defaults to `plughw:CARD=M1A,DEV=0` (by name, so the card number can change).
  The M1A mic is natively 16 kHz mono; its speaker is 48 kHz stereo, so `plughw` resamples.
- Use explicit ALSA hw params: `snd_pcm_set_params()` makes the M1A capture return EIO on the first read.
- SDK logs are off by default (`--sdk-logs` turns them on, written under `/tmp/mochi-bridge-sdk-logs`).
- The SDK runs on a free trial license; set `AGORA_LICENSE` if we ever get a real one.
- Not done yet (M1): polling `GET /api/devices/home_pi_01/state`, joining only while `capturing`, `speaker_muted`.
