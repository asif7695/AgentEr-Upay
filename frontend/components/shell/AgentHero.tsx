"use client";
import { createContext, useContext, useEffect } from "react";

/** A page can put a greeting into the agent's blue header band (the Home screen does); the first card then overlaps the band. */
export type Hero = { title: string; sub?: string } | null;
export const HeroCtx = createContext<(h: Hero) => void>(() => {});

export function useAgentHero(hero: Hero) {
  const set = useContext(HeroCtx);
  const key = hero ? `${hero.title}|${hero.sub ?? ""}` : "";
  useEffect(() => { set(hero); return () => set(null); }, [key]);   // eslint-disable-line react-hooks/exhaustive-deps
}
