// =============================================================================
// i18n.ts  —  LANGUAGE: TypeScript
// -----------------------------------------------------------------------------
// ALL THE TEXT shown on the screens, in English and Brazilian Portuguese.
// ("i18n" is short for "internationalization": 18 letters between the i and the n.)
// To change a sentence on any screen, change it HERE, in both languages.
// Choose the language with ?lang=en or ?lang=pt-BR in the URL.
// =============================================================================

import type { Language, LearningState, SessionMode } from "../contracts.ts";
import type { MicProblem } from "./phoneMic.ts";

// ---- ENGLISH texts. Things like (d: string) => `...` are small functions that put a name in the sentence.
const en = {
  listening: "Listening",
  sleeping: "Mochi is resting",
  speaking: "Mochi is speaking",
  turnAndTap: (d: string) => `${d}, turn me to you and tap`,
  tapWhenGets: (g: string) => `Tap when ${g} gets it`,
  longPressSkip: "Hold to skip",
  waiting: "One moment…",
  gotIt: (g: string) => `${g} got it!`,
  skipped: "Skipped",
  noWords: "Words you needed will show up here.",
  describes: "describes",
  guesses: "guesses",
  word: "The word was",
  connected: "connected",
  disconnected: "reconnecting…",
  // The label on each word card, one per learning state (AGENTS.md §6.3)
  stateLabel: {
    DISCOVERED: "Hint shown",
    ASSISTED: "Used with help",
    REINFORCED: "Recalled in a game",
    USED_INDEPENDENTLY: "Used on your own",
  } as Record<LearningState, string>,
  // The fixed "next step" line at the bottom of each word card
  nextStep: {
    DISCOVERED: "Try using it in your next sentence.",
    ASSISTED: "It may come back in a game.",
    REINFORCED: "Next time, try it on your own.",
    USED_INDEPENDENTLY: "Great. Keep using it.",
  } as Record<LearningState, string>,
  requestFailed: "Could not reach Mochi. Try again.",
  micProblem: {
    unsupported: "This page can't use a microphone. Open the https:// link (not http://).",
    denied: "The microphone is blocked. Allow it (iPhone: Settings > Apps > Safari > Microphone), then tap Start again.",
    "no-agora": "Mochi did not send the audio details. Tap Stop, then Start again.",
    agora: "Could not connect this phone's audio to Mochi. Check the internet and try again.",
  } as Record<MicProblem, string>,
  // ---- New product vision: modes, hints for someone, session summary ----
  choosing: "What do you want to do today?",
  modeName: { together: "Company", activity: "Play", practice: "Practice", choosing: "Choosing" } as Record<SessionMode, string>,
  // Small label under Mochi's face, by mode
  modeFace: { together: "Listening", activity: "Game time", practice: "Practicing", choosing: "Listening" } as Record<SessionMode, string>,
  forName: (n: string) => `for ${n}`,
  progressTitle: "Your progress",
  statWords: "new words",
  statAssisted: "used with help",
  statRecalled: "recalled in a game",
  statMinutes: "minutes practiced",
  lastSessionTitle: "Your last session",
  sessionsTitle: "Sessions",
  minutesLabel: "of speaking practice",
  strengths: "Strong point",
  toReview: "To review",
  newExpressions: "New expressions",
  nextStepTitle: "Next step",
  noSummary: "When the session ends, your summary shows up here.",
  languageName: { en: "English", "pt-BR": "Portuguese" } as Record<Language, string>,
  consentNote: "Mochi only listens between Start session and Stop session. In meetings, let the others know it is listening.",
  // ---- Company version: the Session tab and the Analytics tab on a person's phone ----
  tabSession: "Session",
  tabAnalytics: "Analytics",
  tabsLabel: "Pages",
  startSession: "Start session",
  stopSession: "Stop session",
  readyTitle: "Ready for your meeting",
  readyText: "Mochi joins the conversation: it listens, shows a word when someone gets stuck, and answers when you call it (\"Hi Mochi\").",
  sessionLive: "Session in progress",
  analyticsTitle: "Analytics",
  analyticsNotice: "Session in progress. Its analytics show up here when you stop.",
  backToSession: "Back to the session",
  wordsToLearn: "Words to learn",
  // ---- Start page ("/") ----
  startSubtitle: "Your conversations, noticed by Mochi",
  firstTimeTitle: "First time on this phone",
  firstTimeText: "Open your own link once. This phone will remember it and always open your page.",
  yourName: "yourname",
  screensTitle: "Mochi's screens",
  screenDevice: "Mochi's screen (shows who is talking)",
  screenProjector: "Projector",
  mockTip: "No backend running? Add ?mock=1 to the address to see a demo.",
};

// "Copy" = the shape of the English texts. Portuguese must have exactly the same keys,
// so if you add a text in English and forget Portuguese, TypeScript shows an error.
type Copy = typeof en;

// ---- BRAZILIAN PORTUGUESE texts (wording follows the team guide and the product vision slides)
const ptBR: Copy = {
  listening: "Ouvindo",
  sleeping: "Mochi está descansando",
  speaking: "Mochi está falando",
  turnAndTap: (d) => `${d}, me vire para você e toque`,
  tapWhenGets: (g) => `Toque quando ${g} acertar`,
  longPressSkip: "Segure para pular",
  waiting: "Um momento…",
  gotIt: (g) => `${g} acertou!`,
  skipped: "Pulou",
  noWords: "As palavras de que você precisou aparecem aqui.",
  describes: "descreve",
  guesses: "adivinha",
  word: "A palavra era",
  connected: "conectado",
  disconnected: "reconectando…",
  stateLabel: {
    DISCOVERED: "Dica mostrada",
    ASSISTED: "Usou com ajuda",
    REINFORCED: "Lembrou no jogo",
    USED_INDEPENDENTLY: "Usou por conta própria",
  },
  nextStep: {
    DISCOVERED: "Tente usar na sua próxima frase.",
    ASSISTED: "Ela pode voltar em um jogo.",
    REINFORCED: "Na próxima, tente usar sozinho(a).",
    USED_INDEPENDENTLY: "Ótimo. Continue usando.",
  },
  requestFailed: "Não foi possível falar com o Mochi. Tente de novo.",
  micProblem: {
    unsupported: "Esta página não consegue usar o microfone. Abra o link https:// (não http://).",
    denied: "O microfone está bloqueado. Permita o acesso (iPhone: Ajustes > Apps > Safari > Microfone) e toque em Iniciar de novo.",
    "no-agora": "O Mochi não mandou os dados do áudio. Toque em Parar e depois em Iniciar.",
    agora: "Não foi possível ligar o áudio do celular ao Mochi. Confira a internet e tente de novo.",
  },
  choosing: "O que você quer fazer hoje?",
  modeName: { together: "Companhia", activity: "Jogar", practice: "Praticar", choosing: "Escolhendo" },
  modeFace: { together: "Ouvindo", activity: "Hora do jogo", practice: "Praticando", choosing: "Ouvindo" },
  forName: (n) => `para ${n}`,
  progressTitle: "Seu progresso",
  statWords: "palavras novas",
  statAssisted: "usadas com ajuda",
  statRecalled: "lembradas no jogo",
  statMinutes: "minutos de prática",
  lastSessionTitle: "Sua última sessão",
  sessionsTitle: "Sessões",
  minutesLabel: "de prática de fala",
  strengths: "Ponto forte",
  toReview: "Para revisar",
  newExpressions: "Expressões novas",
  nextStepTitle: "Próximo passo",
  noSummary: "Quando a sessão terminar, seu resumo aparece aqui.",
  languageName: { en: "Inglês", "pt-BR": "Português" },
  consentNote: "O Mochi só ouve entre Iniciar sessão e Encerrar sessão. Em reuniões, avise as outras pessoas que ele está ouvindo.",
  tabSession: "Sessão",
  tabAnalytics: "Análises",
  tabsLabel: "Páginas",
  startSession: "Iniciar sessão",
  stopSession: "Encerrar sessão",
  readyTitle: "Pronto para a sua reunião",
  readyText: "O Mochi participa da conversa: ele ouve, mostra uma palavra quando alguém trava e responde quando você chama (\"Oi, Mochi\").",
  sessionLive: "Sessão em andamento",
  analyticsTitle: "Análises",
  analyticsNotice: "Sessão em andamento. As análises dela aparecem aqui quando você encerrar.",
  backToSession: "Voltar para a sessão",
  wordsToLearn: "Palavras para aprender",
  startSubtitle: "Suas conversas, percebidas pelo Mochi",
  firstTimeTitle: "Primeira vez neste celular",
  firstTimeText: "Abra o seu link uma vez. Este celular vai lembrar e sempre abrir a sua página.",
  yourName: "seunome",
  screensTitle: "Telas do Mochi",
  screenDevice: "Tela do Mochi (mostra quem está falando)",
  screenProjector: "Telão",
  mockTip: "Sem backend rodando? Coloque ?mock=1 no endereço para ver uma demonstração.",
};

/** Choose the language: ?lang= in the URL wins; otherwise the browser language (pt → Portuguese). */
export function pickLanguage(search: string, browserLang = ""): Language {
  const asked = new URLSearchParams(search).get("lang");
  if (asked === "pt-BR" || asked === "en") return asked;
  return browserLang.toLowerCase().startsWith("pt") ? "pt-BR" : "en";
}

/** Get all the texts for one language. Screens call this as `const t = copyFor(lang)`. */
export function copyFor(lang: Language): Copy {
  return lang === "pt-BR" ? ptBR : en;
}

/** "ana" → "Ana" for display. */
export function displayName(userId: string | null | undefined): string {
  if (!userId) return "";
  return userId.charAt(0).toUpperCase() + userId.slice(1);
}

/**
 * Font size that keeps a word on one line: shrink with the longest word's length.
 * Bold sans-serif letters are about 0.62em wide; we use `widthVw` of the screen width.
 */
export function fitFontSize(text: string, maxVh: number, widthVw = 90, wholeLine = false): string {
  // wholeLine = true: the text must stay on ONE line (e.g. "tomei muito sol"), so count every letter.
  const longest = wholeLine ? Math.max(1, text.length) : Math.max(1, ...text.split(/\s+/).map((w) => w.length));
  const vw = Math.floor((widthVw / (longest * 0.62)) * 10) / 10;
  return `min(${maxVh}vh, ${vw}vw)`;
}
