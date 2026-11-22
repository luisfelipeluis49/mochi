// =============================================================================
// CompanyFace.tsx  —  LANGUAGE: TypeScript + JSX (React)
// -----------------------------------------------------------------------------
// Mochi's face for the COMPANY version (the phone's Session tab): calm and polished rather than
// cute. A soft navy head (a rounded square, like an app icon) with light eyes and a gentle mouth.
//   awake=false → eyes closed, no glow (no session yet)
//   awake       → eyes open, a soft teal glow breathes around the head (Mochi is listening)
//   talking     → the mouth opens and closes (Mochi is speaking)
// Drawn as SVG, so it stays sharp at any size. Mochi's own screen (/home) keeps its original face.
// =============================================================================

import { useId } from "react";

export function CompanyFace({ awake, talking = false, small = false }: { awake: boolean; talking?: boolean; small?: boolean }) {
  const id = useId().replace(/:/g, ""); // unique ids for the gradients (several faces can be on a page)
  return (
    <svg className={`company-face ${small ? "small" : ""} ${awake ? "awake" : "asleep"} ${talking ? "talking" : ""}`}
      viewBox="0 0 200 200" role="img" aria-hidden="true">
      <defs>
        <linearGradient id={`head${id}`} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#1E293B" />
          <stop offset="1" stopColor="#0F172A" />
        </linearGradient>
        <radialGradient id={`shine${id}`} cx="0.3" cy="0.2" r="0.7">
          <stop offset="0" stopColor="#ffffff" stopOpacity="0.16" />
          <stop offset="1" stopColor="#ffffff" stopOpacity="0" />
        </radialGradient>
        <radialGradient id={`glow${id}`} cx="0.5" cy="0.5" r="0.5">
          <stop offset="0.6" stopColor="#14B8A6" stopOpacity="0.28" />
          <stop offset="1" stopColor="#14B8A6" stopOpacity="0" />
        </radialGradient>
      </defs>

      {/* the listening glow, behind the head */}
      {awake && <circle className="company-glow" cx="100" cy="100" r="98" fill={`url(#glow${id})`} />}

      {/* the head: a rounded square with a soft light from the top left */}
      <rect x="34" y="34" width="132" height="132" rx="44" fill={`url(#head${id})`} />
      <rect x="34" y="34" width="132" height="132" rx="44" fill={`url(#shine${id})`} />

      {/* the eyes: open capsules with a small highlight, or calm closed arcs */}
      {awake ? (
        <g className="company-eyes">
          <rect x="70" y="80" width="16" height="28" rx="8" fill="#E6FFFA" />
          <rect x="114" y="80" width="16" height="28" rx="8" fill="#E6FFFA" />
          <circle cx="81" cy="87" r="2.6" fill="#0F172A" opacity="0.35" />
          <circle cx="125" cy="87" r="2.6" fill="#0F172A" opacity="0.35" />
        </g>
      ) : (
        <g fill="none" stroke="#E6FFFA" strokeWidth="5" strokeLinecap="round">
          <path d="M68 96 Q78 103 88 96" />
          <path d="M112 96 Q122 103 132 96" />
        </g>
      )}

      {/* the mouth: a gentle line with the slightest smile, or open while Mochi talks */}
      {talking
        ? <rect className="company-mouth" x="88" y="124" width="24" height="14" rx="7" fill="#5EEAD4" />
        : <path d="M88 130 Q100 137 112 130" fill="none" stroke="#5EEAD4" strokeWidth="5" strokeLinecap="round" />}
    </svg>
  );
}
