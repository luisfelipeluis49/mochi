// Every visible string of the app, in English and Brazilian Portuguese, with the same keys.
// The English object defines the keys; the Portuguese one is typed against it, so a missing or extra
// key is a type error (and i18n.test.ts checks the same at run time). Placeholders look like {n}.

import type { Language } from "../contracts.ts";
import { type KV, localStore, safeGet, safeSet } from "./storage.ts";

export type UiLang = Language;

const en = {
  app_name: "Mochi",
  loading: "Loading…",
  try_again: "Try again",
  dismiss: "Dismiss",
  nav_label: "Main navigation",
  nav_session: "Session",
  nav_training: "Training",
  nav_digest: "Digest",
  nav_analytics: "Analytics",
  profile_open: "Open your profile ({name})",
  lang_en: "English",
  "lang_pt-BR": "Portuguese",
  min_short: "{n} min",
  hints_one: "1 hint",
  hints_other: "{n} hints",
  sessions_one: "1 session",
  sessions_other: "{n} sessions",

  // Microphone gate (section 5)
  mic_wait_title: "Allow the microphone",
  mic_wait_body: "Your browser is asking if Mochi may use the microphone. Mochi only listens while a session is running.",
  mic_allow: "Allow microphone",
  mic_continue_without: "Continue without microphone",
  mic_open_secure: "Open the secure page",
  mic_fix: "Fix microphone",
  mic_insecure_title: "The microphone needs a secure link",
  mic_insecure_body: "This page was opened with http://, and browsers only allow the microphone on https:// pages. Open Mochi's https:// address.",
  mic_unsupported_title: "This browser can't use a microphone",
  mic_unsupported_body: "Open Mochi in a recent Chrome, Edge, Firefox or Safari. Browsers inside other apps (chat or social apps) often block the microphone.",
  mic_denied_title: "Microphone access is blocked",
  mic_denied_body: "Mochi needs to hear the conversation. Allow the microphone for this site: tap the lock or settings icon next to the address, set Microphone to Allow, then tap Try again.",
  mic_policy_title: "The microphone is turned off for this page",
  mic_policy_body: "This page is shown inside another site or app that does not allow the microphone. Open Mochi directly in your browser.",
  mic_no_device_title: "No microphone found",
  mic_no_device_body: "Connect a microphone or a headset, or check that your device's microphone is on, then tap Try again.",
  mic_busy_title: "The microphone is being used by something else",
  mic_busy_body: "Another app or tab (a call, a recorder) is using the microphone. Close it, then tap Try again.",
  mic_unknown_title: "The microphone didn't start",
  mic_unknown_body: "Something unexpected stopped the microphone. Tap Try again; if it keeps happening, reload the page.",

  // Backend and session problems (section 6)
  problem_offline_title: "You are offline",
  problem_offline_body: "Mochi will reconnect when your internet is back.",
  problem_waking_title: "Connecting to Mochi…",
  problem_waking_body: "The server was asleep. This takes up to a minute.",
  problem_unreachable_title: "Can't reach Mochi",
  problem_unreachable_body: "Check your internet connection. Mochi's server is not answering.",
  problem_session_full_title: "Mochi is busy right now",
  problem_session_full_body: "Too many conversations are running. Try again in a minute.",
  problem_agora_start_title: "Mochi couldn't join the conversation",
  problem_agora_start_body: "The voice service didn't start. Try again in a moment.",
  problem_agora_sdk_title: "The voice connection didn't load",
  problem_agora_sdk_body: "Something blocked Mochi's voice library (an ad or privacy blocker, or a firewall). Allow download.agora.io and try again.",
  problem_agora_join_title: "Couldn't connect your microphone to Mochi",
  problem_agora_join_body: "The voice channel refused the connection. Try again; if your network blocks calls (some office Wi-Fi does), try another network.",
  problem_session_ended_title: "The session ended",
  problem_session_ended_body: "Mochi had to end this conversation to make room. Start again when you're ready.",
  problem_profile_lost_title: "Mochi forgot this device's profile",
  problem_profile_lost_body: "Mochi forgot this device's profile (the server restarted). Tell it your name again.",
  problem_server_title: "Something went wrong",
  problem_server_body: "Mochi's server had a problem. Try again in a moment.",

  // Onboarding (3.1)
  welcome_title: "Welcome to Mochi",
  welcome_question: "Enter your name to set up your workspace.",
  welcome_name_label: "Your name",
  welcome_speak: "Your first language",
  welcome_learn: "Language you practise",
  welcome_submit: "Continue",
  welcome_sending: "Saving…",
  welcome_name_error: "Use 1 to 40 letters.",

  // Session (3.2)
  session_title: "Session",
  session_start: "Start session",
  session_mode_label: "How should Mochi listen?",
  session_mode_listen: "Quiet listener",
  session_mode_listen_note: "Stays quiet and shows hints. Speaks only when you ask, or to explain an expression.",
  session_mode_talk: "Conversation",
  session_mode_talk_note: "Talks with you and helps you practise.",
  session_start_line: "Mochi listens through your microphone only while a session runs.",
  session_waking: "Connecting…",
  session_stop: "Stop session",
  session_stopping: "Stopping…",
  chip_asleep: "Asleep",
  chip_waking: "Waking up",
  chip_listening: "Listening",
  chip_offline: "No connection",
  session_elapsed: "Session time",
  session_saved: "Session saved",
  session_see_digest: "See your digest",
  session_reload_banner: "Your session is still running, but this page is not listening.",
  session_listen_again: "Listen again",
  session_stop_short: "Stop",
  session_this_session: "This session",
  session_no_hints: "Words Mochi shows appear here.",
  session_volume: "Mochi's voice",
  session_volume_badge: "Volume {n}",
  session_mic_needed: "Start needs the microphone: {reason}",
  session_game: "Game",
  session_said: "Mochi said",
  hint_region: "Hint",
  hint_for_everyone: "For everyone",
  hint_used: "Word used",
  hint_time_left: "Time left for this hint",

  // Face (aria labels)
  face_sleeping: "Ready",
  face_waking: "Connecting",
  face_awake: "Listening",
  face_hearing: "Hearing {name}",
  face_thinking: "Processing",
  face_speaking: "Speaking",
  face_bye: "Session ended",
  face_offline: "No connection",

  // Training (3.4)
  training_title: "Training",
  "training_prompt_en": "How do you say this in English?",
  "training_prompt_pt-BR": "How do you say this in Portuguese?",
  training_answer_label: "Your answer",
  training_check: "Check",
  training_dont_know: "I don't know",
  training_say_it: "Say it",
  training_speech_note: "Uses your browser's speech service",
  training_listening: "Listening…",
  training_right: "Right!",
  training_almost: "Almost! It's spelled “{word}”.",
  training_wrong: "The word is “{word}”.",
  training_next: "Next",
  training_progress: "{i} / {n}",
  training_done: "{right} right · {review} to review",
  training_next_due: "Next word due {when}.",
  training_again: "Train again",
  training_caught_up: "All caught up! Next word due {when}.",
  training_no_words: "Training is made of the words Mochi showed you when you got stuck. None yet: in a session, say a word from your own language inside a sentence in the language you practise, and it appears here.",
  training_go_session: "Start a session",
  training_no_meaning_one: "1 word has no meaning yet and is not in training.",
  training_no_meaning_other: "{n} words have no meaning yet and are not in training.",

  // Digest (3.5)
  digest_title: "Weekly digest",
  digest_pick: "Week",
  digest_this_week: "This week",
  digest_sessions: "Sessions",
  digest_minutes: "Minutes practised",
  digest_active_days: "Active days",
  digest_new_words: "New words",
  digest_per_day: "Minutes per day",
  digest_delta_up: "{n} min more than the week before",
  digest_delta_down: "{n} min less than the week before",
  digest_delta_same: "Same as the week before",
  digest_new: "New words",
  digest_assisted: "Used with help",
  digest_reinforced: "Recalled in a game",
  digest_no_words: "No new words this week.",
  digest_practise_next: "Practise next",
  digest_practise_now: "Practise these now",
  digest_empty: "No sessions this week yet. Start a session and your weekly digest builds here.",
  digest_go_session: "Start a session",

  // Analytics (3.6)
  analytics_title: "Analytics",
  tile_words: "Words saved",
  tile_assisted: "Used with help",
  tile_reinforced: "Recalled in a game",
  tile_independent: "Used on your own",
  tile_independent_note: "Comes in a later version",
  tile_sessions: "Sessions",
  tile_minutes: "Total minutes",
  tile_streak: "Day streak",
  tile_accuracy: "Training accuracy",
  tile_accuracy_note: "On this device",
  chart_minutes: "Minutes per session",
  chart_date: "Date",
  chart_minutes_col: "Minutes",
  chart_states: "Where your words are",
  words_list: "Your words",
  filter_all: "All",
  state_path: "Progress",
  state_DISCOVERED: "Hint shown",
  state_ASSISTED: "Used with help",
  state_REINFORCED: "Recalled in a game",
  state_USED_INDEPENDENTLY: "Used on your own",
  state_not_reached: "not yet",
  analytics_empty: "Your progress appears after your first session.",

  // Profile
  profile_title: "Profile",
  profile_speaks: "Speaks",
  profile_learns: "Learning",
  profile_ui_language: "Interface language",
  switch_en: "English",
  switch_pt: "Português",
  profile_forget: "Forget me on this device",
  profile_forget_note: "This only clears this device. Nothing is deleted on Mochi's server, and your words stay there.",
};

export type CopyKey = keyof typeof en;
export type Copy = { [K in CopyKey]: string };

const ptBR: Copy = {
  app_name: "Mochi",
  loading: "Carregando…",
  try_again: "Tentar de novo",
  dismiss: "Fechar",
  nav_label: "Navegação principal",
  nav_session: "Sessão",
  nav_training: "Treino",
  nav_digest: "Resumo",
  nav_analytics: "Análises",
  profile_open: "Abrir seu perfil ({name})",
  lang_en: "Inglês",
  "lang_pt-BR": "Português",
  min_short: "{n} min",
  hints_one: "1 dica",
  hints_other: "{n} dicas",
  sessions_one: "1 sessão",
  sessions_other: "{n} sessões",

  mic_wait_title: "Libere o microfone",
  mic_wait_body: "Seu navegador está perguntando se o Mochi pode usar o microfone. O Mochi só ouve enquanto uma sessão está ativa.",
  mic_allow: "Permitir microfone",
  mic_continue_without: "Continuar sem microfone",
  mic_open_secure: "Abrir a página segura",
  mic_fix: "Arrumar o microfone",
  mic_insecure_title: "O microfone precisa de um link seguro",
  mic_insecure_body: "Esta página foi aberta com http://, e os navegadores só liberam o microfone em páginas https://. Abra o endereço https:// do Mochi.",
  mic_unsupported_title: "Este navegador não consegue usar o microfone",
  mic_unsupported_body: "Abra o Mochi em um Chrome, Edge, Firefox ou Safari recente. Navegadores dentro de outros apps (de conversa ou redes sociais) costumam bloquear o microfone.",
  mic_denied_title: "O acesso ao microfone está bloqueado",
  mic_denied_body: "O Mochi precisa ouvir a conversa. Libere o microfone para este site: toque no cadeado ou no ícone de configurações ao lado do endereço, escolha Permitir em Microfone e toque em Tentar de novo.",
  mic_policy_title: "O microfone está desligado para esta página",
  mic_policy_body: "Esta página está dentro de outro site ou app que não permite o microfone. Abra o Mochi direto no navegador.",
  mic_no_device_title: "Nenhum microfone encontrado",
  mic_no_device_body: "Conecte um microfone ou um fone com microfone, ou confira se o microfone do aparelho está ligado, e toque em Tentar de novo.",
  mic_busy_title: "O microfone está sendo usado por outro app",
  mic_busy_body: "Outro app ou aba (uma chamada, um gravador) está usando o microfone. Feche-o e toque em Tentar de novo.",
  mic_unknown_title: "O microfone não começou",
  mic_unknown_body: "Algo inesperado impediu o microfone. Toque em Tentar de novo; se continuar, recarregue a página.",

  problem_offline_title: "Você está sem internet",
  problem_offline_body: "O Mochi volta a se conectar quando a internet voltar.",
  problem_waking_title: "Conectando ao Mochi…",
  problem_waking_body: "O servidor estava dormindo. Isso leva até um minuto.",
  problem_unreachable_title: "Não foi possível falar com o Mochi",
  problem_unreachable_body: "Confira sua conexão com a internet. O servidor do Mochi não está respondendo.",
  problem_session_full_title: "O Mochi está ocupado agora",
  problem_session_full_body: "Há muitas conversas acontecendo. Tente de novo em um minuto.",
  problem_agora_start_title: "O Mochi não conseguiu entrar na conversa",
  problem_agora_start_body: "O serviço de voz não iniciou. Tente de novo daqui a pouco.",
  problem_agora_sdk_title: "A conexão de voz não carregou",
  problem_agora_sdk_body: "Algo bloqueou a biblioteca de voz do Mochi (um bloqueador de anúncios ou de privacidade, ou um firewall). Libere download.agora.io e tente de novo.",
  problem_agora_join_title: "Não foi possível ligar seu microfone ao Mochi",
  problem_agora_join_body: "O canal de voz recusou a conexão. Tente de novo; se a sua rede bloqueia chamadas (algumas redes de escritório bloqueiam), tente outra rede.",
  problem_session_ended_title: "A sessão terminou",
  problem_session_ended_body: "O Mochi precisou encerrar esta conversa para abrir espaço. Comece de novo quando quiser.",
  problem_profile_lost_title: "O Mochi esqueceu o perfil deste aparelho",
  problem_profile_lost_body: "O Mochi esqueceu o perfil deste aparelho (o servidor reiniciou). Diga seu nome de novo.",
  problem_server_title: "Algo deu errado",
  problem_server_body: "O servidor do Mochi teve um problema. Tente de novo daqui a pouco.",

  welcome_title: "Bem-vindo ao Mochi",
  welcome_question: "Informe seu nome para configurar seu espaço.",
  welcome_name_label: "Seu nome",
  welcome_speak: "Seu primeiro idioma",
  welcome_learn: "Idioma que você pratica",
  welcome_submit: "Continuar",
  welcome_sending: "Salvando…",
  welcome_name_error: "Use de 1 a 40 letras.",

  session_title: "Sessão",
  session_start: "Começar sessão",
  session_mode_label: "Como o Mochi deve ouvir?",
  session_mode_listen: "Ouvinte silencioso",
  session_mode_listen_note: "Fica quieto e mostra dicas. Só fala quando você pede, ou para explicar uma expressão.",
  session_mode_talk: "Conversa",
  session_mode_talk_note: "Conversa com você e ajuda a praticar.",
  session_start_line: "O Mochi só ouve pelo seu microfone enquanto uma sessão está ativa.",
  session_waking: "Conectando…",
  session_stop: "Encerrar sessão",
  session_stopping: "Encerrando…",
  chip_asleep: "Dormindo",
  chip_waking: "Acordando",
  chip_listening: "Ouvindo",
  chip_offline: "Sem conexão",
  session_elapsed: "Tempo de sessão",
  session_saved: "Sessão salva",
  session_see_digest: "Ver seu resumo",
  session_reload_banner: "Sua sessão continua ativa, mas esta página não está ouvindo.",
  session_listen_again: "Ouvir de novo",
  session_stop_short: "Encerrar",
  session_this_session: "Esta sessão",
  session_no_hints: "As palavras que o Mochi mostrar aparecem aqui.",
  session_volume: "Voz do Mochi",
  session_volume_badge: "Volume {n}",
  session_mic_needed: "Para começar, o Mochi precisa do microfone: {reason}",
  session_game: "Jogo",
  session_said: "O Mochi disse",
  hint_region: "Dica",
  hint_for_everyone: "Para todos",
  hint_used: "Palavra usada",
  hint_time_left: "Tempo restante desta dica",

  face_sleeping: "Pronto",
  face_waking: "Conectando",
  face_awake: "Ouvindo",
  face_hearing: "Ouvindo {name}",
  face_thinking: "Processando",
  face_speaking: "Falando",
  face_bye: "Sessão encerrada",
  face_offline: "Sem conexão",

  training_title: "Treino",
  "training_prompt_en": "Como se diz isso em inglês?",
  "training_prompt_pt-BR": "Como se diz isso em português?",
  training_answer_label: "Sua resposta",
  training_check: "Conferir",
  training_dont_know: "Não sei",
  training_say_it: "Falar",
  training_speech_note: "Usa o serviço de voz do navegador",
  training_listening: "Ouvindo…",
  training_right: "Isso!",
  training_almost: "Quase! Escreve-se “{word}”.",
  training_wrong: "A palavra é “{word}”.",
  training_next: "Próxima",
  training_progress: "{i} / {n}",
  training_done: "{right} certas · {review} para revisar",
  training_next_due: "Próxima palavra {when}.",
  training_again: "Treinar de novo",
  training_caught_up: "Tudo em dia! Próxima palavra {when}.",
  training_no_words: "O Treino é feito das palavras que o Mochi mostrou quando você travou. Ainda não há nenhuma: em uma sessão, diga uma palavra do seu idioma dentro de uma frase no idioma que você pratica, e ela aparece aqui.",
  training_go_session: "Começar uma sessão",
  training_no_meaning_one: "1 palavra ainda não tem significado e não está no treino.",
  training_no_meaning_other: "{n} palavras ainda não têm significado e não estão no treino.",

  digest_title: "Resumo semanal",
  digest_pick: "Semana",
  digest_this_week: "Esta semana",
  digest_sessions: "Sessões",
  digest_minutes: "Minutos praticados",
  digest_active_days: "Dias ativos",
  digest_new_words: "Palavras novas",
  digest_per_day: "Minutos por dia",
  digest_delta_up: "{n} min a mais que na semana anterior",
  digest_delta_down: "{n} min a menos que na semana anterior",
  digest_delta_same: "Igual à semana anterior",
  digest_new: "Palavras novas",
  digest_assisted: "Usadas com ajuda",
  digest_reinforced: "Lembradas em um jogo",
  digest_no_words: "Nenhuma palavra nova nesta semana.",
  digest_practise_next: "Pratique a seguir",
  digest_practise_now: "Praticar agora",
  digest_empty: "Nenhuma sessão nesta semana ainda. Comece uma sessão e o resumo semanal aparece aqui.",
  digest_go_session: "Começar uma sessão",

  analytics_title: "Análises",
  tile_words: "Palavras salvas",
  tile_assisted: "Usadas com ajuda",
  tile_reinforced: "Lembradas em um jogo",
  tile_independent: "Usadas sem ajuda",
  tile_independent_note: "Chega em uma versão futura",
  tile_sessions: "Sessões",
  tile_minutes: "Minutos no total",
  tile_streak: "Dias seguidos",
  tile_accuracy: "Acertos no treino",
  tile_accuracy_note: "Neste aparelho",
  chart_minutes: "Minutos por sessão",
  chart_date: "Data",
  chart_minutes_col: "Minutos",
  chart_states: "Onde estão suas palavras",
  words_list: "Suas palavras",
  filter_all: "Todas",
  state_path: "Progresso",
  state_DISCOVERED: "Dica mostrada",
  state_ASSISTED: "Usada com ajuda",
  state_REINFORCED: "Lembrada em um jogo",
  state_USED_INDEPENDENTLY: "Usada sem ajuda",
  state_not_reached: "ainda não",
  analytics_empty: "Seu progresso aparece depois da primeira sessão.",

  profile_title: "Perfil",
  profile_speaks: "Fala",
  profile_learns: "Aprendendo",
  profile_ui_language: "Idioma da interface",
  switch_en: "English",
  switch_pt: "Português",
  profile_forget: "Esquecer-me neste aparelho",
  profile_forget_note: "Isso só limpa este aparelho. Nada é apagado no servidor do Mochi, e suas palavras continuam lá.",
};

export const copy: { en: Copy; "pt-BR": Copy } = { en, "pt-BR": ptBR };

/** One string, with {placeholders} filled in. */
export function t(lang: UiLang, key: CopyKey, vars: Record<string, string | number> = {}): string {
  return fill(copy[lang][key], vars);
}

export function fill(text: string, vars: Record<string, string | number>): string {
  return text.replace(/\{(\w+)\}/g, (m, k: string) => (k in vars ? String(vars[k]) : m));
}

/** "1 hint" / "3 hints", from a pair of keys ending in _one and _other. */
export function plural(lang: UiLang, base: "hints" | "sessions" | "training_no_meaning", n: number): string {
  return t(lang, n === 1 ? `${base}_one` : `${base}_other`, { n });
}

/** The name of a language in the UI language: en -> "English" / "Inglês". */
export function languageName(ui: UiLang, lang: Language): string {
  return t(ui, lang === "en" ? "lang_en" : "lang_pt-BR");
}

export const LANG_KEY = "mochi.lang";

export function parseLang(v: string | null | undefined): UiLang | null {
  if (!v) return null;
  const low = v.toLowerCase();
  if (low.startsWith("pt")) return "pt-BR";
  if (low.startsWith("en")) return "en";
  return null;
}

/** The UI language: ?lang= first, then localStorage "mochi.lang", then the browser language
 *  (anything starting with "pt" is pt-BR, anything else English). */
export function detectLang(input: { search?: string; stored?: string | null; navigatorLanguage?: string | null }): UiLang {
  const q = new URLSearchParams(input.search ?? "").get("lang");
  return parseLang(q) ?? parseLang(input.stored) ?? (input.navigatorLanguage?.toLowerCase().startsWith("pt") ? "pt-BR" : "en");
}

export function storedLang(s: KV | null = localStore()): string | null {
  return safeGet(s, LANG_KEY);
}

export function storeLang(lang: UiLang, s: KV | null = localStore()): void {
  safeSet(s, LANG_KEY, lang);
}

/** What a web Start sends as woken_by (THE SHARED CONTRACT, C4): Mochi greets in the UI language. */
export function wokenBy(lang: UiLang): "oi mochi" | "hey mochi" {
  return lang === "pt-BR" ? "oi mochi" : "hey mochi";
}

/** Intl locale for formatting: en-GB for the English UI (21 Nov, 24 h), pt-BR for Portuguese. */
export function intlLocale(lang: UiLang): string {
  return lang === "pt-BR" ? "pt-BR" : "en-GB";
}
