// The profile (/profile): name, languages, the interface language, and "Forget me on this device".
import type { User } from "../contracts.ts";
import { type UiLang, languageName, t } from "../lib/i18n.ts";
import { Avatar } from "../ui/Nav.tsx";

export function ProfileScreen({ lang, user, onLang, onForget }: { lang: UiLang; user: User; onLang: (l: UiLang) => void; onForget: () => void }) {
  return (
    <div className="screen profile-screen">
      <h1>{t(lang, "profile_title")}</h1>
      <section className="card profile-card">
        <Avatar name={user.display_name} size="l" />
        <div>
          <p className="profile-name">{user.display_name}</p>
          <dl className="profile-langs">
            <dt>{t(lang, "profile_speaks")}</dt><dd>{user.comfortable_languages.map((l) => languageName(lang, l)).join(", ")}</dd>
            <dt>{t(lang, "profile_learns")}</dt><dd>{languageName(lang, user.target_language)}</dd>
          </dl>
        </div>
      </section>
      <section className="card">
        <h2 id="ui-lang">{t(lang, "profile_ui_language")}</h2>
        <div className="segmented" role="group" aria-labelledby="ui-lang">
          <button type="button" aria-pressed={lang === "en"} onClick={() => onLang("en")} lang="en">{t(lang, "switch_en")}</button>
          <button type="button" aria-pressed={lang === "pt-BR"} onClick={() => onLang("pt-BR")} lang="pt-BR">{t(lang, "switch_pt")}</button>
        </div>
      </section>
      <section className="card">
        <button type="button" className="btn btn-secondary" onClick={onForget}>{t(lang, "profile_forget")}</button>
        <p className="muted small">{t(lang, "profile_forget_note")}</p>
      </section>
    </div>
  );
}
