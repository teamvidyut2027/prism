// Minimal stroke icon set (24px grid).
import type { ReactNode } from "react";

const I = (p: { children: ReactNode }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} strokeLinecap="round" strokeLinejoin="round">
    {p.children}
  </svg>
);

export const Icon = {
  overview: () => <I><rect x="3" y="3" width="7" height="9" rx="1.5" /><rect x="14" y="3" width="7" height="5" rx="1.5" /><rect x="14" y="12" width="7" height="9" rx="1.5" /><rect x="3" y="16" width="7" height="5" rx="1.5" /></I>,
  factory: () => <I><path d="M3 21V10l6 4V10l6 4V6l6 3v12z" /><path d="M7 17h2M12 17h2M17 17h2" /></I>,
  data: () => <I><ellipse cx="12" cy="5.5" rx="8" ry="3" /><path d="M4 5.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /><path d="M4 11.5v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" /></I>,
  eval: () => <I><path d="M4 19V5" /><path d="M4 19h16" /><path d="m7 15 4-4 3 3 5-6" /></I>,
  compare: () => <I><path d="M8 4v16M16 4v16" /><path d="M4 8h8M12 16h8" /></I>,
  method: () => <I><path d="M12 3 21 20H3Z" /><path d="M12 10v4M12 17h.01" /></I>,
  bars: () => <I><path d="M4 20V10M10 20V4M16 20v-7M21 20H3" /></I>,
  lines: () => <I><path d="M3 20h18" /><path d="m4 15 5-6 4 4 7-8" /></I>,
  shapes: () => <I><circle cx="7" cy="7" r="3.5" /><rect x="13.5" y="3.5" width="7" height="7" rx="1" /><path d="m7 13.5 4 7H3z" /><path d="m17 13.5 1.3 2.7 3 .4-2.2 2.1.5 3-2.6-1.4-2.6 1.4.5-3-2.2-2.1 3-.4z" /></I>,
  clocks: () => <I><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3.5 2" /></I>,
  mazes: () => <I><rect x="3" y="3" width="18" height="18" rx="2" /><path d="M9 3v8M15 21v-8M3 15h6M21 9h-6" /></I>,
  tables: () => <I><rect x="3" y="4" width="18" height="16" rx="2" /><path d="M3 9h18M3 14h18M9 4v16" /></I>,
  check: () => <I><path d="m5 12 4.5 4.5L19 7" /></I>,
  x: () => <I><path d="M6 6l12 12M18 6 6 18" /></I>,
  shuffle: () => <I><path d="M16 3h5v5M4 20 21 3M21 16v5h-5M15 15l6 6M4 4l5 5" /></I>,
  play: () => <I><path d="M7 4v16l13-8z" /></I>,
  sun: () => <I><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" /></I>,
  moon: () => <I><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" /></I>,
  spark: () => <I><path d="M12 3v4M12 17v4M3 12h4M17 12h4M5.6 5.6l2.8 2.8M15.6 15.6l2.8 2.8M5.6 18.4l2.8-2.8M15.6 8.4l2.8-2.8" /></I>,
  shield: () => <I><path d="M12 3 4 6v6c0 4.5 3.4 8.3 8 9 4.6-.7 8-4.5 8-9V6z" /><path d="m8.5 12 2.5 2.5 4.5-5" /></I>,
  trash: () => <I><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3" /></I>,
  back: () => <I><path d="m15 18-6-6 6-6" /></I>,
};

export const familyIcon = (name: string) => {
  const f = (Icon as Record<string, () => JSX.Element>)[name];
  return f ? f() : Icon.spark();
};
