/*
 * Mochi Pi bridge (M0).
 *
 * Joins one Agora channel, sends the M1A microphone into it, and plays the
 * audio it receives through the M1A speaker. Nothing else: no decisions,
 * no transcription, no UI (see AGENTS.md section 9.1).
 *
 *   mic  (ALSA, 16 kHz mono S16LE) -> agora_rtc_send_audio_data (SDK encodes Opus)
 *   on_audio_data (SDK decodes to PCM) -> ring buffer -> ALSA speaker
 *
 * Config comes from flags or environment variables; secrets are never logged.
 */
#include <alsa/asoundlib.h>
#include <getopt.h>
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#include "agora_rtc_api.h"

#define SAMPLE_RATE 16000
#define CHANNELS 1
#define FRAME_MS 20
#define FRAME_SAMPLES (SAMPLE_RATE * FRAME_MS / 1000) /* 320 */
#define FRAME_BYTES (FRAME_SAMPLES * 2 * CHANNELS)   /* 640 */
#define RING_BYTES (SAMPLE_RATE * 2 * 2)              /* 2 s of 16 kHz mono */
#define DEFAULT_DEVICE "plughw:CARD=M1A,DEV=0"

#define LOG(fmt, ...) fprintf(stderr, "[bridge] " fmt "\n", ##__VA_ARGS__)

static struct {
  const char *app_id, *token, *channel, *mic_dev, *spk_dev;
  uint32_t uid;
  bool aec, quiet_sdk, levels;
} cfg;

static volatile sig_atomic_t g_stop = 0;
static atomic_bool g_joined = false;
static connection_id_t g_conn;

/* counters for the once-a-second status line */
static atomic_uint_fast64_t g_sent_frames, g_recv_bytes, g_recv_cb, g_underruns;
static atomic_int g_last_recv_type = -1;

/* --- ring buffer: SDK callback thread writes, speaker thread reads --- */
static uint8_t ring[RING_BYTES];
static size_t ring_r, ring_w, ring_fill;
static pthread_mutex_t ring_mu = PTHREAD_MUTEX_INITIALIZER;

static void ring_push(const uint8_t *p, size_t n) {
  pthread_mutex_lock(&ring_mu);
  for (size_t i = 0; i < n; i++) {
    if (ring_fill == RING_BYTES) { /* full: drop oldest to keep latency bounded */
      ring_r = (ring_r + 1) % RING_BYTES;
      ring_fill--;
    }
    ring[ring_w] = p[i];
    ring_w = (ring_w + 1) % RING_BYTES;
    ring_fill++;
  }
  pthread_mutex_unlock(&ring_mu);
}

/* Fills out with n bytes; pads with silence. Returns bytes of real audio. */
static size_t ring_pop(uint8_t *out, size_t n) {
  pthread_mutex_lock(&ring_mu);
  size_t got = ring_fill < n ? ring_fill : n;
  got &= ~(size_t)1; /* keep 16-bit sample alignment */
  for (size_t i = 0; i < got; i++) {
    out[i] = ring[ring_r];
    ring_r = (ring_r + 1) % RING_BYTES;
  }
  ring_fill -= got;
  pthread_mutex_unlock(&ring_mu);
  memset(out + got, 0, n - got);
  return got;
}

/* --- ALSA helpers --- */
static snd_pcm_t *open_pcm(const char *dev, snd_pcm_stream_t dir) {
  snd_pcm_t *pcm = NULL;
  int err = snd_pcm_open(&pcm, dev, dir, 0);
  if (err < 0) {
    LOG("cannot open %s device '%s': %s", dir == SND_PCM_STREAM_CAPTURE ? "mic" : "speaker", dev,
        snd_strerror(err));
    return NULL;
  }
  /* 16 kHz mono S16LE, 20 ms periods, 160 ms buffer. plughw resamples for the speaker
   * (natively 48 kHz stereo). Explicit hw params on purpose: snd_pcm_set_params() leaves the
   * M1A capture stream returning EIO on the first read (verified on this Pi). */
  snd_pcm_hw_params_t *hw;
  snd_pcm_hw_params_alloca(&hw);
  unsigned rate = SAMPLE_RATE;
  snd_pcm_uframes_t period = FRAME_SAMPLES, buffer = FRAME_SAMPLES * 8;
  if ((err = snd_pcm_hw_params_any(pcm, hw)) < 0 ||
      (err = snd_pcm_hw_params_set_access(pcm, hw, SND_PCM_ACCESS_RW_INTERLEAVED)) < 0 ||
      (err = snd_pcm_hw_params_set_format(pcm, hw, SND_PCM_FORMAT_S16_LE)) < 0 ||
      (err = snd_pcm_hw_params_set_channels(pcm, hw, CHANNELS)) < 0 ||
      (err = snd_pcm_hw_params_set_rate_near(pcm, hw, &rate, 0)) < 0 ||
      (err = snd_pcm_hw_params_set_period_size_near(pcm, hw, &period, 0)) < 0 ||
      (err = snd_pcm_hw_params_set_buffer_size_near(pcm, hw, &buffer)) < 0 ||
      (err = snd_pcm_hw_params(pcm, hw)) < 0) {
    LOG("cannot configure '%s': %s", dev, snd_strerror(err));
    snd_pcm_close(pcm);
    return NULL;
  }
  if (rate != SAMPLE_RATE) {
    LOG("'%s' does not support %d Hz (got %u); use a plughw: device", dev, SAMPLE_RATE, rate);
    snd_pcm_close(pcm);
    return NULL;
  }
  return pcm;
}

/* --mic -: read 16 kHz mono S16LE from stdin (the wake-word supervisor owns the M1A mic). */
static void *stdin_mic_thread(void *arg) {
  (void)arg;
  uint8_t buf[FRAME_BYTES];
  audio_frame_info_t info = { .data_type = AUDIO_DATA_TYPE_PCM };
  while (!g_stop) {
    if (fread(buf, 1, FRAME_BYTES, stdin) != FRAME_BYTES) {
      LOG("mic stdin closed; stopping");
      g_stop = 1;
      break;
    }
    if (!atomic_load(&g_joined)) continue;
    int rc = agora_rtc_send_audio_data(g_conn, buf, FRAME_BYTES, &info);
    if (rc < 0) LOG("send_audio_data: %s", agora_rtc_err_2_str(rc));
    else atomic_fetch_add(&g_sent_frames, 1);
  }
  return NULL;
}

static void *mic_thread(void *arg) {
  (void)arg;
  if (strcmp(cfg.mic_dev, "-") == 0) return stdin_mic_thread(NULL);
  snd_pcm_t *pcm = open_pcm(cfg.mic_dev, SND_PCM_STREAM_CAPTURE);
  if (!pcm) { g_stop = 1; return NULL; }
  int16_t buf[FRAME_SAMPLES * CHANNELS];
  audio_frame_info_t info = { .data_type = AUDIO_DATA_TYPE_PCM };

  while (!g_stop) {
    snd_pcm_sframes_t n = snd_pcm_readi(pcm, buf, FRAME_SAMPLES);
    if (n < 0) {
      n = snd_pcm_recover(pcm, (int)n, 1);
      if (n < 0) { LOG("mic read failed: %s; stopping", snd_strerror((int)n)); g_stop = 1; break; }
      continue;
    }
    if (n != FRAME_SAMPLES || !atomic_load(&g_joined)) continue;
    int rc = agora_rtc_send_audio_data(g_conn, buf, FRAME_BYTES, &info);
    if (rc < 0) LOG("send_audio_data: %s", agora_rtc_err_2_str(rc));
    else atomic_fetch_add(&g_sent_frames, 1);
  }
  snd_pcm_close(pcm);
  return NULL;
}

static void *speaker_thread(void *arg) {
  (void)arg;
  snd_pcm_t *pcm = open_pcm(cfg.spk_dev, SND_PCM_STREAM_PLAYBACK);
  if (!pcm) { g_stop = 1; return NULL; }
  uint8_t buf[FRAME_BYTES];
  int peak = 0, frames = 0, last_level = 0;
  while (!g_stop) {
    /* Always write a frame (silence if nothing arrived) so ALSA paces this loop
     * at real time and the device never underruns. */
    size_t got = ring_pop(buf, FRAME_BYTES);
    if (got < FRAME_BYTES) atomic_fetch_add(&g_underruns, 1);
    if (cfg.levels) { /* --levels: loudness of the voice being played, every 80 ms, for Mochi's mouth */
      const int16_t *pcm16 = (const int16_t *)buf;
      for (size_t i = 0; i < got / 2; i++) {
        int v = pcm16[i] < 0 ? -pcm16[i] : pcm16[i];
        if (v > peak) peak = v;
      }
      if (++frames == 4) {
        int level = peak * 100 / 32768;
        if (level < 2) level = 0;
        if (level != last_level) { LOG("voice %d", level); last_level = level; }
        peak = 0; frames = 0;
      }
    }
    snd_pcm_sframes_t n = snd_pcm_writei(pcm, buf, FRAME_SAMPLES);
    if (n < 0 && snd_pcm_recover(pcm, (int)n, 1) < 0) {
      LOG("speaker write failed: %s", snd_strerror((int)n));
      break;
    }
  }
  snd_pcm_drop(pcm);
  snd_pcm_close(pcm);
  return NULL;
}

/* --- Agora callbacks (run on SDK threads: keep them short) --- */
static void on_join(connection_id_t c, uint32_t uid, int ms) {
  LOG("joined channel '%s' as uid %u in %d ms", cfg.channel, uid, ms);
  (void)c;
  atomic_store(&g_joined, true);
}
static void on_rejoin(connection_id_t c, uint32_t uid, int ms) { on_join(c, uid, ms); }
static void on_lost(connection_id_t c) { (void)c; LOG("connection lost"); atomic_store(&g_joined, false); }
static void on_reconnecting(connection_id_t c) { (void)c; LOG("reconnecting..."); }
static void on_error(connection_id_t c, int code, const char *msg) {
  (void)c;
  LOG("error %d: %s", code, msg ? msg : "");
}
static void on_license_fail(connection_id_t c, int reason) {
  (void)c;
  LOG("license validation failed (%d); stopping", reason);
  g_stop = 1;
}
static void on_user_joined(connection_id_t c, uint32_t uid, int ms) { (void)c; (void)ms; LOG("remote user %u joined", uid); }
static void on_user_offline(connection_id_t c, uint32_t uid, int reason) { (void)c; LOG("remote user %u left (%d)", uid, reason); }
static void on_token_expire(connection_id_t c, const char *t) { (void)c; (void)t; LOG("token will expire soon"); }

static void on_audio(connection_id_t c, uint32_t uid, uint16_t ts, const void *data, size_t len,
                     const audio_frame_info_t *info) {
  (void)c; (void)uid; (void)ts;
  atomic_store(&g_last_recv_type, info ? (int)info->data_type : -1);
  atomic_fetch_add(&g_recv_cb, 1);
  atomic_fetch_add(&g_recv_bytes, len);
  if (info && info->data_type != AUDIO_DATA_TYPE_PCM) return; /* only play decoded PCM */
  ring_push(data, len);
}

/* --- setup --- */
static void usage(const char *argv0) {
  fprintf(stderr,
          "Usage: %s -c <channel> [options]\n"
          "  -i, --app-id <id>      Agora App ID (default: $AGORA_APP_ID)\n"
          "  -t, --token <token>    RTC token (default: $AGORA_TOKEN; omit if the project has no certificate)\n"
          "  -c, --channel <name>   channel to join (default: $AGORA_CHANNEL)\n"
          "  -u, --uid <n>          numeric uid, 0 = let Agora pick (default: $AGORA_UID or 0)\n"
          "  -m, --mic <alsa|->     capture device, or - for 16 kHz mono S16LE on stdin (default: %s)\n"
          "  -s, --speaker <alsa>   playback device (default: %s)\n"
          "      --sdk-aec          enable the SDK's downlink echo canceller (M1A also has hardware AEC)\n"
          "      --sdk-logs         let the SDK print its own logs\n"
          "      --levels           print \"voice N\" (0-100) as the loudness of what is played changes\n",
          argv0, DEFAULT_DEVICE, DEFAULT_DEVICE);
}

static const char *env_or(const char *name, const char *fallback) {
  const char *v = getenv(name);
  return (v && *v) ? v : fallback;
}

static void handle_sig(int s) { (void)s; g_stop = 1; }

int main(int argc, char **argv) {
  cfg.app_id = env_or("AGORA_APP_ID", NULL);
  cfg.token = env_or("AGORA_TOKEN", NULL);
  cfg.channel = env_or("AGORA_CHANNEL", NULL);
  cfg.uid = (uint32_t)strtoul(env_or("AGORA_UID", "0"), NULL, 10);
  cfg.mic_dev = env_or("MOCHI_MIC", DEFAULT_DEVICE);
  cfg.spk_dev = env_or("MOCHI_SPEAKER", DEFAULT_DEVICE);
  cfg.quiet_sdk = true;

  static const struct option opts[] = {
    { "app-id", 1, 0, 'i' }, { "token", 1, 0, 't' }, { "channel", 1, 0, 'c' }, { "uid", 1, 0, 'u' },
    { "mic", 1, 0, 'm' }, { "speaker", 1, 0, 's' }, { "sdk-aec", 0, 0, 'A' }, { "sdk-logs", 0, 0, 'L' },
    { "levels", 0, 0, 'V' },
    { "help", 0, 0, 'h' }, { 0, 0, 0, 0 } };
  int o;
  while ((o = getopt_long(argc, argv, "i:t:c:u:m:s:h", opts, NULL)) != -1) {
    switch (o) {
    case 'i': cfg.app_id = optarg; break;
    case 't': cfg.token = optarg; break;
    case 'c': cfg.channel = optarg; break;
    case 'u': cfg.uid = (uint32_t)strtoul(optarg, NULL, 10); break;
    case 'm': cfg.mic_dev = optarg; break;
    case 's': cfg.spk_dev = optarg; break;
    case 'A': cfg.aec = true; break;
    case 'L': cfg.quiet_sdk = false; break;
    case 'V': cfg.levels = true; break;
    default: usage(argv[0]); return o == 'h' ? 0 : 2;
    }
  }
  if (!cfg.app_id || !cfg.channel) {
    LOG("App ID and channel are required");
    usage(argv[0]);
    return 2;
  }

  signal(SIGINT, handle_sig);
  signal(SIGTERM, handle_sig);

  LOG("Agora RTSA SDK %s; channel '%s'; token %s; mic '%s'; speaker '%s'; sdk aec %s",
      agora_rtc_get_version(), cfg.channel, cfg.token ? "set" : "none", cfg.mic_dev, cfg.spk_dev,
      cfg.aec ? "on" : "off");

  agora_rtc_event_handler_t eh = { 0 };
  eh.on_join_channel_success = on_join;
  eh.on_rejoin_channel_success = on_rejoin;
  eh.on_connection_lost = on_lost;
  eh.on_reconnecting = on_reconnecting;
  eh.on_error = on_error;
  eh.on_license_validation_failure = on_license_fail;
  eh.on_user_joined = on_user_joined;
  eh.on_user_offline = on_user_offline;
  eh.on_token_privilege_will_expire = on_token_expire;
  eh.on_audio_data = on_audio;

  rtc_service_option_t so = { 0 };
  so.area_code = 0xFFFFFFFF; /* global */
  so.log_cfg.log_disable = cfg.quiet_sdk;
  so.log_cfg.log_path = "/tmp/mochi-bridge-sdk-logs";
  const char *lic = getenv("AGORA_LICENSE");
  if (lic) snprintf(so.license_value, sizeof(so.license_value), "%s", lic);

  int rc = agora_rtc_init(cfg.app_id, &eh, &so);
  if (rc < 0) { LOG("agora_rtc_init: %s", agora_rtc_err_2_str(rc)); return 1; }
  rc = agora_rtc_create_connection(&g_conn);
  if (rc < 0) { LOG("create_connection: %s", agora_rtc_err_2_str(rc)); agora_rtc_fini(); return 1; }

  rtc_channel_options_t co = { 0 };
  co.auto_subscribe_audio = true;
  co.auto_subscribe_video = false;
  co.enable_audio_jitter_buffer = true; /* smooth network jitter before playback */
  co.enable_audio_decode = true;        /* deliver received audio as PCM */
  co.enable_audio_downlink_aec = cfg.aec;
  co.audio_codec_opt.audio_codec_type = AUDIO_CODEC_TYPE_OPUS;
  co.audio_codec_opt.pcm_sample_rate = SAMPLE_RATE;
  co.audio_codec_opt.pcm_channel_num = CHANNELS;
  co.audio_codec_opt.pcm_duration = FRAME_MS;

  rc = agora_rtc_join_channel(g_conn, cfg.channel, cfg.uid, cfg.token, &co);
  if (rc < 0) {
    LOG("join_channel: %s", agora_rtc_err_2_str(rc));
    agora_rtc_destroy_connection(g_conn);
    agora_rtc_fini();
    return 1;
  }

  pthread_t mic_t, spk_t;
  pthread_create(&mic_t, NULL, mic_thread, NULL);
  pthread_create(&spk_t, NULL, speaker_thread, NULL);

  /* status line once a second so the log shows audio flowing both ways */
  while (!g_stop) {
    sleep(1);
    uint64_t sent = atomic_exchange(&g_sent_frames, 0);
    uint64_t rbytes = atomic_exchange(&g_recv_bytes, 0);
    uint64_t rcb = atomic_exchange(&g_recv_cb, 0);
    uint64_t under = atomic_exchange(&g_underruns, 0);
    LOG("%s | sent %llu frames/s | recv %llu cb/s %llu B/s (type %d) | speaker silence %llu/50",
        atomic_load(&g_joined) ? "joined" : "not joined", (unsigned long long)sent,
        (unsigned long long)rcb, (unsigned long long)rbytes, atomic_load(&g_last_recv_type),
        (unsigned long long)under);
  }

  LOG("stopping");
  pthread_join(mic_t, NULL);
  pthread_join(spk_t, NULL);
  agora_rtc_leave_channel(g_conn);
  agora_rtc_destroy_connection(g_conn);
  agora_rtc_fini();
  return 0;
}
