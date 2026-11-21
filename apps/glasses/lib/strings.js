// The few words the glasses show themselves, in the MVP's two languages:
// English and Brazilian Portuguese. Status labels are short by design.

const STRINGS = {
  en: {
    listening: 'LISTENING',
    micOff: 'NOT LISTENING',
    connecting: 'CONNECTING',
    reconnecting: 'RECONNECTING',
    demo: 'DEMO',
  },
  'pt-BR': {
    listening: 'OUVINDO',
    micOff: 'SEM OUVIR',
    connecting: 'CONECTANDO',
    reconnecting: 'RECONECTANDO',
    demo: 'DEMO',
  },
};

// First preferred language that Mochi's labels cover; English otherwise.
export function pickLocale(languages) {
  const list = Array.isArray(languages) ? languages : [];
  for (const tag of list) {
    if (typeof tag !== 'string') continue;
    const primary = tag.toLowerCase().split('-')[0];
    if (primary === 'pt') return 'pt-BR';
    if (primary === 'en') return 'en';
  }
  return 'en';
}

export function getStrings(locale) {
  return STRINGS[locale] || STRINGS.en;
}
