import { useEffect, useState } from "react";
import { Icon } from "./components/icons";
import { TourPanel, TourProvider, useTour } from "./components/Tour";
import Compare from "./pages/Compare";
import DatasetDetail from "./pages/DatasetDetail";
import Datasets from "./pages/Datasets";
import Factory from "./pages/Factory";
import Method from "./pages/Method";
import Overview from "./pages/Overview";
import RunDetail from "./pages/RunDetail";
import Runs from "./pages/Runs";

export interface Route {
  parts: string[];
  query: Record<string, string>;
  qs: string;
}

function parse(): Route {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const [path, qs = ""] = raw.split("?");
  const parts = (path || "overview").split("/").map(decodeURIComponent);
  const query = Object.fromEntries(new URLSearchParams(qs));
  return { parts, query, qs };
}

function useRoute() {
  const [route, setRoute] = useState(parse);
  useEffect(() => {
    let last = window.location.hash.split("?")[0];
    const h = () => {
      const page = window.location.hash.split("?")[0];
      if (page !== last) window.scrollTo({ top: 0 });
      last = page;
      setRoute(parse());
    };
    window.addEventListener("hashchange", h);
    return () => window.removeEventListener("hashchange", h);
  }, []);
  return route;
}

export const go = (path: string) => { window.location.hash = "#/" + path; };

const NAV = [
  { id: "overview", label: "Overview", icon: Icon.overview },
  { id: "factory", label: "Task Factory", icon: Icon.factory },
  { id: "datasets", label: "Datasets", icon: Icon.data },
  { id: "runs", label: "Evaluations", icon: Icon.eval },
  { id: "compare", label: "Compare models", icon: Icon.compare },
  { id: "method", label: "Methodology", icon: Icon.method },
];

function useTheme() {
  const [theme, setTheme] = useState<string>(() => {
    try { return localStorage.getItem("prism-theme") ?? "auto"; } catch { return "auto"; }
  });
  useEffect(() => {
    const el = document.documentElement;
    if (theme === "auto") el.removeAttribute("data-theme"); else el.setAttribute("data-theme", theme);
    try { localStorage.setItem("prism-theme", theme); } catch { /* storage blocked */ }
  }, [theme]);
  const dark = theme === "dark" || (theme === "auto" && window.matchMedia?.("(prefers-color-scheme: dark)").matches);
  return { dark, toggle: () => setTheme(dark ? "light" : "dark") };
}

export function Logo({ size = 22 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden>
      <defs>
        <linearGradient id="pg" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#6d5efc" /><stop offset=".55" stopColor="#14b8c4" /><stop offset="1" stopColor="#f59e0b" />
        </linearGradient>
      </defs>
      <path d="M32 8 56 52H8Z" fill="none" stroke="url(#pg)" strokeWidth="6" strokeLinejoin="round" />
      <path d="M32 26 42 46H22Z" fill="url(#pg)" />
    </svg>
  );
}

function DemoButton({ compact }: { compact?: boolean }) {
  const tour = useTour();
  return (
    <button className={`btn ${compact ? "sm ghost" : "primary tour-start"}`} onClick={() => tour.start()} title="Step-by-step walkthrough for judges">
      <Icon.play /> {compact ? "Demo" : "Guided demo"}
    </button>
  );
}

function Shell() {
  const route = useRoute();
  const theme = useTheme();
  const tour = useTour();
  const [page, ...rest] = route.parts;
  const active = page === "dataset" ? "datasets" : page === "run" ? "runs" : page;

  useEffect(() => { if (route.query.tour !== undefined && !tour.active) tour.start(Number(route.query.tour) || 0); }, [route.query.tour]); // eslint-disable-line react-hooks/exhaustive-deps

  let body;
  switch (page) {
    case "factory": body = <Factory key={route.qs} preset={route.query} />; break;
    case "datasets": body = <Datasets />; break;
    case "dataset": body = <DatasetDetail name={rest[0]} />; break;
    case "runs": body = <Runs />; break;
    case "run": body = <RunDetail key={rest[0] + route.qs} id={rest[0]} preset={route.query} />; break;
    case "compare": body = <Compare />; break;
    case "method": body = <Method />; break;
    default: body = <Overview />;
  }

  return (
    <div className={`shell ${tour.active ? "touring" : ""}`}>
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Logo /></div>
          <div>
            <div className="brand-name">Prism</div>
            <div className="brand-sub">Visual Task Factory</div>
          </div>
        </div>
        <nav className="nav">
          {NAV.map((n) => (
            <a key={n.id} href={`#/${n.id}`} className={active === n.id ? "active" : ""}>
              <n.icon /> {n.label}
            </a>
          ))}
        </nav>
        <div className="sidebar-foot">
          <DemoButton />
          <button className="btn sm" onClick={theme.toggle}>
            {theme.dark ? <Icon.sun /> : <Icon.moon />} {theme.dark ? "Light mode" : "Dark mode"}
          </button>
          <div className="tiny muted">Innodata AI Hackathon 2026 · Challenge 02</div>
        </div>
      </aside>
      <div>
        <nav className="topbar">
          {NAV.map((n) => (
            <a key={n.id} href={`#/${n.id}`} className={active === n.id ? "active" : ""}>{n.label}</a>
          ))}
          <DemoButton compact />
          <button className="btn sm ghost" onClick={theme.toggle} aria-label="Toggle theme">{theme.dark ? <Icon.sun /> : <Icon.moon />}</button>
        </nav>
        <main className="main">{body}</main>
      </div>
      <TourPanel />
    </div>
  );
}

export default function App() {
  return (
    <TourProvider>
      <Shell />
    </TourProvider>
  );
}
