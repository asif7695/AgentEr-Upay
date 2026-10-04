"use client";
import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError, tokenStore } from "./api";
import type { PipelineStep, SimState, User } from "./types";

/* ---------------------------------- auth ---------------------------------- */
interface AuthCtx {
  user: User | null; ready: boolean;
  login: (username: string, password: string) => Promise<User>; logout: () => void;
}
const AuthC = createContext<AuthCtx | null>(null);

/* ------------------------------- sim clock -------------------------------- */
interface SimCtx {
  sim: SimState | null; version: number; busy: boolean; playing: boolean; lastPipeline: PipelineStep | null;
  advance: () => Promise<void>; jump: (date: string) => Promise<void>; togglePlay: () => void; refresh: () => Promise<void>; bump: () => void;
}
const SimC = createContext<SimCtx | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [ready, setReady] = useState(false);
  const [sim, setSim] = useState<SimState | null>(null);
  const [version, setVersion] = useState(0);
  const [busy, setBusy] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [lastPipeline, setLastPipeline] = useState<PipelineStep | null>(null);
  const simDate = useRef<string | null>(null);

  const applySim = useCallback((s: SimState) => {
    setSim(s);
    if (simDate.current !== s.date) { simDate.current = s.date; setVersion((v) => v + 1); }
  }, []);

  const refresh = useCallback(async () => {
    try { applySim(await api<SimState>("/sim/state")); } catch (e) { if (e instanceof ApiError && e.status === 401) setUser(null); }
  }, [applySim]);

  useEffect(() => {
    (async () => {
      if (tokenStore.get()) {
        try { setUser(await api<User>("/me")); } catch { tokenStore.clear(); }
      }
      setReady(true);
    })();
  }, []);

  // keep the sim date in sync across tabs/devices (admin advances, agent screen follows)
  useEffect(() => {
    if (!user) { setSim(null); simDate.current = null; return; }
    refresh();
    const id = setInterval(refresh, 4000);
    return () => clearInterval(id);
  }, [user, refresh]);

  const login = useCallback(async (username: string, password: string) => {
    const r = await api<{ access_token: string; user: User }>("/auth/login", { method: "POST", body: { username, password } });
    tokenStore.set(r.access_token);
    setUser(r.user);
    return r.user;
  }, []);
  const logout = useCallback(() => { tokenStore.clear(); setUser(null); setPlaying(false); setLastPipeline(null); }, []);

  const run = useCallback(async (path: string, body?: unknown) => {
    setBusy(true);
    try {
      const r = await api<{ state: SimState; pipeline: PipelineStep }>(path, { method: "POST", body });
      applySim(r.state); setLastPipeline(r.pipeline); setVersion((v) => v + 1);
    } finally { setBusy(false); }
  }, [applySim]);
  const advance = useCallback(() => run("/sim/advance"), [run]);
  const jump = useCallback((date: string) => run("/sim/jump", { date }), [run]);
  const bump = useCallback(() => setVersion((v) => v + 1), []);

  // auto-play: one simulated night every 3 s, stops at the end of the data or on error
  const advanceRef = useRef(advance);
  useEffect(() => { advanceRef.current = advance; }, [advance]);
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(() => { advanceRef.current().catch(() => setPlaying(false)); }, 3000);
    return () => clearInterval(id);
  }, [playing]);
  useEffect(() => { if (sim && !sim.can_advance) setPlaying(false); }, [sim]);

  return (
    <AuthC.Provider value={{ user, ready, login, logout }}>
      <SimC.Provider value={{ sim, version, busy, playing, lastPipeline, advance, jump, togglePlay: () => setPlaying((p) => !p), refresh, bump }}>
        {children}
      </SimC.Provider>
    </AuthC.Provider>
  );
}

export function useAuth(): AuthCtx { const v = useContext(AuthC); if (!v) throw new Error("useAuth outside SessionProvider"); return v; }
export function useSim(): SimCtx { const v = useContext(SimC); if (!v) throw new Error("useSim outside SessionProvider"); return v; }
