// =============================================================================
// i18n.ts  —  LANGUAGE: TypeScript
// -----------------------------------------------------------------------------
// ALL THE TEXT shown on the screens, in English and Brazilian Portuguese.
// ("i18n" is short for "internationalization": 18 letters between the i and the n.)
// To change a sentence on any screen, change it HERE, in both languages.
// Choose the language with ?lang=en or ?lang=pt-BR in the URL.
// =============================================================================

import type { ConversationContext, Language, LearningState, MistakeKind, SessionMode } from "../contracts.ts";

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
  start: "Start",
  stop: "Stop",
  startGame: "Start a game",
  liveHint: "Hint for you",
  sessionOn: "Mochi is listening",
  sessionOff: "Mochi is not listening",
  myWords: "My words",
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
  // ---- New product vision: modes, hints for someone, session summary ----
  choosing: "What do you want to do today?",
  modeName: { together: "Company", activity: "Play", practice: "Practice", choosing: "Choosing" } as Record<SessionMode, string>,
  // Small label under Mochi's face, by mode
  modeFace: { together: "Listening", activity: "Game time", practice: "Practicing", choosing: "Listening" } as Record<SessionMode, string>,
  mode: "Mode",
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
  // ---- "My conversations" page (/me): Mochi's analysis of real conversations ----
  insightsTitle: "My conversations",
  insightsSubtitle: "What Mochi noticed while you talked",
  statConversations: "conversations",
  statSpeaking: "minutes speaking",
  statUnknown: "words you needed",
  statMistakes: "mistakes noticed",
  trendTitle: "Mistakes per 10 minutes",
  improved: (p: number) => `${p}% fewer mistakes than in your first conversation`,
  worse: (p: number) => `${p}% more mistakes than in your first conversation`,
  commonMistakes: "Your most common mistakes",
  timesIn: (n: number, c: number) => `${n}× in ${c} ${c === 1 ? "conversation" : "conversations"}`,
  kindName: { grammar: "Grammar", word_choice: "Word choice", false_friend: "False friend" } as Record<MistakeKind, string>,
  youSaid: "You said",
  better: "Better",
  wordsTitle: "Words you didn't know",
  saidInstead: (x: string) => `you said “${x}”`,
  timesNeeded: (n: number) => `needed ${n}×`,
  conversationsTitle: "Conversations",
  contextName: { meeting: "Meeting", conversation: "Conversation", practice: "Practice" } as Record<ConversationContext, string>,
  convLine: (min: number, m: number, w: number) => `${min} min · ${m} ${m === 1 ? "mistake" : "mistakes"} · ${w} new ${w === 1 ? "word" : "words"}`,
  practiceTitle: "Practice next",
  strengthsTitle: "Going well",
  noReports: "When Mochi listens to a conversation, its report shows up here.",
  consentNote: "Mochi only listens between Start and Stop. In meetings, let the others know it is listening.",
  recordTitle: "Record a conversation",
  recordHint: "Press it when a conversation starts. Each recording is saved as its own conversation.",
  recording: "Recording",
  stopRecording: "Stop and save",
  onlyYou: "Only your sentences are saved. What the other person says is not.",
  historyTitle: "Conversation history",
  backToAll: "← All conversations",
  whatYouSaid: "What you said",
  wordsThisConv: "Words you needed",
  untitled: (time: string) => `Conversation at ${time}`,
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
  start: "Iniciar",
  stop: "Parar",
  startGame: "Iniciar um jogo",
  liveHint: "Dica para você",
  sessionOn: "Mochi está ouvindo",
  sessionOff: "Mochi não está ouvindo",
  myWords: "Minhas palavras",
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
  choosing: "O que você quer fazer hoje?",
  modeName: { together: "Companhia", activity: "Jogar", practice: "Praticar", choosing: "Escolhendo" },
  modeFace: { together: "Ouvindo", activity: "Hora do jogo", practice: "Praticando", choosing: "Ouvindo" },
  mode: "Modo",
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
  insightsTitle: "Minhas conversas",
  insightsSubtitle: "O que o Mochi percebeu enquanto você falava",
  statConversations: "conversas",
  statSpeaking: "minutos falando",
  statUnknown: "palavras que faltaram",
  statMistakes: "erros percebidos",
  trendTitle: "Erros a cada 10 minutos",
  improved: (p) => `${p}% menos erros que na sua primeira conversa`,
  worse: (p) => `${p}% mais erros que na sua primeira conversa`,
  commonMistakes: "Seus erros mais comuns",
  timesIn: (n, c) => `${n}× em ${c} ${c === 1 ? "conversa" : "conversas"}`,
  kindName: { grammar: "Gramática", word_choice: "Escolha de palavra", false_friend: "Falso cognato" },
  youSaid: "Você disse",
  better: "Melhor",
  wordsTitle: "Palavras que você não sabia",
  saidInstead: (x) => `você disse “${x}”`,
  timesNeeded: (n) => `precisou ${n}×`,
  conversationsTitle: "Conversas",
  contextName: { meeting: "Reunião", conversation: "Conversa", practice: "Prática" },
  convLine: (min, m, w) => `${min} min · ${m} ${m === 1 ? "erro" : "erros"} · ${w} ${w === 1 ? "palavra nova" : "palavras novas"}`,
  practiceTitle: "Para praticar agora",
  strengthsTitle: "Indo bem",
  noReports: "Quando o Mochi ouvir uma conversa, o relatório aparece aqui.",
  consentNote: "O Mochi só ouve entre Iniciar e Parar. Em reuniões, avise as outras pessoas que ele está ouvindo.",
  recordTitle: "Gravar conversa",
  recordHint: "Aperte quando a conversa começar. Cada gravação fica salva como uma conversa separada.",
  recording: "Gravando",
  stopRecording: "Parar e salvar",
  onlyYou: "Só as suas frases são guardadas. O que a outra pessoa fala, não.",
  historyTitle: "Histórico de conversas",
  backToAll: "← Todas as conversas",
  whatYouSaid: "O que você disse",
  wordsThisConv: "Palavras que faltaram",
  untitled: (time) => `Conversa das ${time}`,
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
