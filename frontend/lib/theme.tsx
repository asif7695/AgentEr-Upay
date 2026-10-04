"use client";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

export type ThemeMode = "system" | "light" | "dark";
const LS = "upay-theme";

// Inline script (see layout.tsx) applies the saved theme before first paint to avoid a flash.
export const THEME_INIT_SCRIPT = `try{var m=localStorage.getItem("${LS}");if(m==="light"||m==="dark")document.documentElement.setAttribute("data-theme",m)}catch(e){}`;

interface ThemeCtx { mode: ThemeMode; resolved: "light" | "dark"; setMode: (m: ThemeMode) => void; cycle: () => void }
const Ctx = createContext<ThemeCtx | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setModeState] = useState<ThemeMode>("system");
  const [sysDark, setSysDark] = useState(false);

  useEffect(() => {
    try { const m = localStorage.getItem(LS); if (m === "light" || m === "dark") setModeState(m); } catch { /* storage unavailable */ }
    const mq = window.matchMedia("(prefers-color-scheme: dark)");
    setSysDark(mq.matches);
    const h = (e: MediaQueryListEvent) => setSysDark(e.matches);
    mq.addEventListener("change", h);
    return () => mq.removeEventListener("change", h);
  }, []);

  useEffect(() => {
    const el = document.documentElement;
    if (mode === "system") el.removeAttribute("data-theme"); else el.setAttribute("data-theme", mode);
  }, [mode]);

  const setMode = useCallback((m: ThemeMode) => {
    setModeState(m);
    try { if (m === "system") localStorage.removeItem(LS); else localStorage.setItem(LS, m); } catch { /* storage unavailable */ }
  }, []);
  const resolved = mode === "system" ? (sysDark ? "dark" : "light") : mode;
  const cycle = useCallback(() => setMode(resolved === "dark" ? "light" : "dark"), [resolved, setMode]);
  return <Ctx.Provider value={{ mode, resolved, setMode, cycle }}>{children}</Ctx.Provider>;
}

export function useTheme(): ThemeCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useTheme outside ThemeProvider");
  return v;
}
