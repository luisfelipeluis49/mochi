// The app's view: given the model (hooks/useApp.ts) it picks what to show. No effects here, so it
// renders the same in the browser and in the renderToString tests.
//
// Order (section 3.0): mic gate -> reachability -> identity (onboarding) -> app shell.

import type { AppActions, AppModel } from "./hooks/useApp.ts";
import { buildAnalytics } from "./lib/analytics.ts";
import { micBlock } from "./lib/appState.ts";
import { buildDigest } from "./lib/digest.ts";
import { hintRemaining, liveHint, myWords } from "./lib/events.ts";
import { type FaceInput, SPEAK_QUIET_MS, faceOf, speakingUntil } from "./lib/face.ts";
import type { Fmt } from "./lib/format.ts";
import { t } from "./lib/i18n.ts";
import { secureUrl } from "./lib/mic.ts";
import { pathOf } from "./lib/routes.ts";
import { AnalyticsScreen } from "./screens/AnalyticsScreen.tsx";
import { DigestScreen } from "./screens/DigestScreen.tsx";
import { Loading, MicGate } from "./screens/MicGate.tsx";
import { Onboarding } from "./screens/Onboarding.tsx";
import { ProfileScreen } from "./screens/ProfileScreen.tsx";
import { SessionScreen } from "./screens/SessionScreen.tsx";
import { TrainingScreen } from "./screens/TrainingScreen.tsx";
import { Unreachable } from "./screens/Unreachable.tsx";
import { Banner } from "./ui/Banner.tsx";
import { Problem } from "./ui/Problem.tsx";
import { Avatar, Nav, linkClick } from "./ui/Nav.tsx";
import type { ChipState } from "./ui/StatusChip.tsx";

export interface AppProps {
  model: AppModel;
  actions: AppActions;
  /** the page URL (for the "Open the secure page" link) */
  href?: string;
}

/** Everything the face needs, from the store, the voice levels and the clock. */
export function faceInputOf(m: AppModel): FaceInput {
  const s = m.state;
  const live = s.live;
  const capturing = s.phase === "capturing" || s.phase === "stopping";
  const speakUntil = live.speak ? speakingUntil(live.speakAt, live.speak.text, m.voice.lastLoudAt) : 0;
  const loudUntil = m.voice.lastLoudAt ? m.voice.lastLoudAt + SPEAK_QUIET_MS : 0;
  return {
    lang: s.lang,
    displayName: s.user?.display_name ?? "",
    capturing,
    starting: s.phase === "starting",
    stoppedAt: s.stoppedAt,
    lastHearingAt: capturing ? m.voice.lastHearingAt : 0,
    lastResponseAt: Math.max(live.hintShownAt, live.speakAt),
    speakingUntil: capturing ? Math.max(speakUntil, loudUntil) : 0,
    hint: liveHint(live, m.now),
    lastStateChange: live.sessionChangedAt,
    problem: s.banner !== null,
    startedAt: s.startedAt,
    online: s.online && s.socket !== "retrying",
    proudAt: live.proudAt,
    excitedAt: live.excitedAt,
    used: live.used,
    volume: s.volume,
    volumePopAt: s.volumePopAt,
  };
}

export function App({ model, actions, href = "" }: AppProps) {
  const s = model.state;
  const lang = s.lang;

  if (s.gate.status === "checking") return <Loading lang={lang} />;
  if (s.gate.status === "prompt" || s.gate.status === "slow") {
    return <MicGate lang={lang} slow={s.gate.status === "slow"} onAllow={actions.retryGate} />;
  }
  if (s.gate.status === "failed") {
    return <ProblemGate model={model} actions={actions} href={href} />;
  }
  if (s.probe.status !== "ok") {
    const problem = s.probe.problem;
    return <Unreachable lang={lang} problem={problem} onRetry={actions.retryProbe} />;
  }
  if (!s.user) {
    return <Onboarding lang={lang} note={s.note} busy={model.onboarding.busy} error={model.onboarding.error} onSubmit={actions.submitName} />;
  }
  if (s.identity !== "ok") return <Loading lang={lang} />;
  return <Shell model={model} actions={actions} />;
}

function ProblemGate({ model, actions, href }: AppProps) {
  const s = model.state;
  if (s.gate.status !== "failed") return null;
  return (
    <Problem lang={s.lang} problem={{ type: "mic", kind: s.gate.problem }} onAction={actions.retryGate}
      onContinue={actions.continueWithoutMic} secureHref={href ? secureUrl(href) : undefined} />
  );
}

function Shell({ model, actions }: { model: AppModel; actions: AppActions }) {
  const s = model.state;
  const lang = s.lang;
  const user = s.user!;
  const f: Fmt = { lang, timeZone: model.timeZone };
  const screen = model.screen === "welcome" ? "session" : model.screen;
  const words = myWords(s.live);
  const connection = !s.online ? "offline" : s.socket === "retrying" ? "unreachable" : null;

  let body;
  if (screen === "session") {
    const input = faceInputOf(model);
    const face = faceOf(input, model.now);
    const chip: ChipState = !input.online ? "offline" : s.phase === "starting" ? "waking" : input.capturing ? "listening" : "asleep";
    const round = s.live.activity && s.live.activity.state !== "IDLE" ? s.live.activity.public_instruction : null;
    body = (
      <SessionScreen
        lang={lang} user={user} face={face} level={model.voice.level} hint={input.hint} hintRemaining={hintRemaining(s.live, model.now)}
        speak={s.live.speak} speaking={face.mode === "speaking"} sessionHints={s.live.sessionHints} phase={s.phase}
        elapsedMs={s.startedAt ? model.now - s.startedAt : 0} chip={chip} micBlocked={micBlock(s)} banner={s.banner} saved={s.saved}
        rejoin={s.rejoin} volume={s.volume} activityInstruction={round} reachable={s.probe.status === "ok"}
        onStart={actions.start} onStop={actions.stop} onRejoin={actions.rejoin} onFixMic={actions.retryGate} onVolume={actions.setVolume}
        onDismissBanner={actions.dismissBanner} onDismissSaved={actions.dismissSaved} onGoDigest={() => actions.navigate("digest")}
        mode={model.mode} onMode={actions.setMode}
      />
    );
  } else if (screen === "training") {
    body = (
      <TrainingScreen
        lang={lang} phase={s.phase} training={model.training} elapsedMs={s.startedAt ? model.now - s.startedAt : 0}
        micBlocked={micBlock(s)} banner={s.banner} reachable={s.probe.status === "ok"} hasWords={words.length > 0}
        onStart={() => actions.start("train")} onStop={actions.stop} onFixMic={actions.retryGate}
        onDismissBanner={actions.dismissBanner} onGoAnalytics={() => actions.navigate("analytics")} onGoSession={() => actions.navigate("session")}
      />
    );
  } else if (screen === "digest") {
    body = (
      <DigestScreen lang={lang} view={buildDigest(s.records, words, model.now, f, model.digestWeek)}
        onSelect={actions.selectWeek} onGoSession={() => actions.navigate("session")} />
    );
  } else if (screen === "analytics") {
    body = <AnalyticsScreen lang={lang} view={buildAnalytics(words, s.records, model.now, f)} f={f} />;
  } else {
    body = <ProfileScreen lang={lang} user={user} onLang={actions.setLang} onForget={actions.forget} />;
  }

  return (
    <div className="app-shell">
      <a className="skip-link" href="#main">{t(lang, "app_name")}</a>
      <Nav lang={lang} screen={screen} user={user} onNavigate={actions.navigate} />
      <div className="app-column">
        <header className="app-header">
          <span className="wordmark">{t(lang, "app_name")}</span>
          <a href={pathOf("profile")} className="header-avatar" onClick={linkClick(actions.navigate, "profile")} aria-label={t(lang, "profile_open", { name: user.display_name })} aria-current={screen === "profile" ? "page" : undefined}>
            <Avatar name={user.display_name} />
          </a>
        </header>
        {connection && (
          <div className="connection-banner">
            <Banner lang={lang} tone="problem" title={t(lang, `problem_${connection}_title`)}>{t(lang, `problem_${connection}_body`)}</Banner>
          </div>
        )}
        <main id="main" className="app-main" tabIndex={-1}>{body}</main>
      </div>
    </div>
  );
}
