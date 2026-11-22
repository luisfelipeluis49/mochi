// =============================================================================
// HeadsetFace.tsx  —  LANGUAGE: TypeScript + JSX (React)
// -----------------------------------------------------------------------------
// Mochi's face for the COMPANY version (the phone's Session tab): a calm, minimal face wearing a
// meeting headset, so it reads as "an assistant in your meeting" at a glance.
//   awake=false → eyes closed (no session yet)      talking → the mouth moves (Mochi is speaking)
// Drawn as SVG in the current text color (styles.css sets it), so it stays crisp at any size.
// Mochi's own screen (/home) keeps its original face (Face in HomeView.tsx).
// =============================================================================

export function HeadsetFace({ awake, talking = false, small = false }: { awake: boolean; talking?: boolean; small?: boolean }) {
  return (
    <svg className={`headset-face ${small ? "small" : ""} ${talking ? "talking" : ""}`} viewBox="0 0 160 124"
      role="img" aria-hidden="true">
      {/* the headband and the two ear cups */}
      <path d="M24 72 A56 56 0 0 1 136 72" fill="none" stroke="currentColor" strokeWidth="7" strokeLinecap="round" />
      <rect x="12" y="62" width="20" height="36" rx="8" fill="currentColor" />
      <rect x="128" y="62" width="20" height="36" rx="8" fill="currentColor" />
      {/* the microphone arm, from the right cup towards the mouth */}
      <path d="M134 96 Q130 112 108 112" fill="none" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />
      <circle className="headset-mic" cx="104" cy="112" r="5" />
      {/* the eyes: open while awake, closed lines before a session */}
      {awake ? (
        <>
          <rect x="58" y="58" width="12" height="24" rx="6" fill="currentColor" />
          <rect x="90" y="58" width="12" height="24" rx="6" fill="currentColor" />
        </>
      ) : (
        <>
          <rect x="55" y="70" width="18" height="5" rx="2.5" fill="currentColor" />
          <rect x="87" y="70" width="18" height="5" rx="2.5" fill="currentColor" />
        </>
      )}
      {/* the mouth: a calm line, or open while Mochi talks */}
      {talking
        ? <rect className="headset-mouth" x="72" y="90" width="16" height="10" rx="5" fill="currentColor" />
        : <rect x="70" y="94" width="20" height="4" rx="2" fill="currentColor" />}
    </svg>
  );
}
