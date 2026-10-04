"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import en, { type DictKey } from "./dict.en";
import bn from "./dict.bn";
import { bnFeatureLabel } from "./feat";
import type { WhyItem } from "./types";

export type Lang = "en" | "bn";
type Params = Record<string, string | number>;

const LS_LANG = "upay-lang";
const read = (k: string) => { try { return localStorage.getItem(k); } catch { return null; } };
const write = (k: string, v: string) => { try { localStorage.setItem(k, v); } catch { /* storage unavailable */ } };

interface Fmt {
  num: (n: number, maxFrac?: number) => string;
  bdt: (n: number) => string;
  pct: (n: number, frac?: number) => string;
  date: (iso: string) => string;
  dateLong: (iso: string) => string;
  dateTiny: (iso: string) => string;
  axis: (iso: string) => string;
  signed: (n: number) => string;
}

interface I18n {
  lang: Lang; setLang: (l: Lang) => void;
  t: (key: DictKey, params?: Params) => string; fmt: Fmt;
  feature: (item: Pick<WhyItem, "feature" | "label">) => string;
  typeLabel: (locationType: string) => string;
}

const Ctx = createContext<I18n | null>(null);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>("en");
  useEffect(() => {
    const l = read(LS_LANG);
    if (l === "bn" || l === "en") setLangState(l);
  }, []);
  useEffect(() => { document.documentElement.lang = lang; }, [lang]);
  const setLang = useCallback((l: Lang) => { setLangState(l); write(LS_LANG, l); }, []);

  const value = useMemo<I18n>(() => {
    const dict: Record<string, string> = lang === "bn" ? bn : en;
    // Digits follow the language: Bangla UI shows Bengali digits (Intl bn-BD), English UI shows Latin digits.
    const numLocale = lang === "bn" ? "bn-BD" : "en-US";
    const dateLocale = lang === "bn" ? "bn-BD" : "en-GB";
    const num = (n: number, maxFrac = 0) => new Intl.NumberFormat(numLocale, { maximumFractionDigits: maxFrac }).format(n);
    const t = (key: DictKey, params?: Params) => {
      let s = dict[key] ?? en[key] ?? key;
      if (params) for (const [k, v] of Object.entries(params)) s = s.split(`{${k}}`).join(typeof v === "number" ? num(v, Number.isInteger(v) ? 0 : 2) : v);
      return s;
    };
    const parse = (iso: string) => new Date(`${iso}T00:00:00Z`);
    const df = (opts: Intl.DateTimeFormatOptions) => (iso: string) => new Intl.DateTimeFormat(dateLocale, { ...opts, timeZone: "UTC" }).format(parse(iso));
    const fmt: Fmt = {
      num, bdt: (n) => `৳${num(n)}`, pct: (n, frac = 0) => `${num(n, frac)}%`,
      date: df({ weekday: "short", day: "numeric", month: "short" }),
      dateLong: df({ weekday: "short", day: "numeric", month: "short", year: "numeric" }),
      dateTiny: df({ day: "numeric", month: "short" }),
      axis: df({ weekday: "short", day: "numeric" }),
      signed: (n) => `${n >= 0 ? "+" : "−"}${num(Math.abs(n))}`,
    };
    const feature = (item: Pick<WhyItem, "feature" | "label">) => (lang === "bn" ? bnFeatureLabel(item.feature) : undefined) ?? item.label;
    const typeLabel = (lt: string) => {
      const k = `unit.type.${lt}` as DictKey;
      return k in en ? t(k) : lt.replace(/_/g, " ");
    };
    return { lang, setLang, t, fmt, feature, typeLabel };
  }, [lang, setLang]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18n {
  const v = useContext(Ctx);
  if (!v) throw new Error("useI18n outside I18nProvider");
  return v;
}
