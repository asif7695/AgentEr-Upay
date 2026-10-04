"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "./api";
import { useSim } from "./session";

export interface ApiState<T> { data: T | null; error: ApiError | null; loading: boolean; reload: () => void }

/** GET helper. Re-fetches when the path changes, when the simulation clock moves, or on reload().
 *  Keeps the previous data on screen while re-fetching (no flicker). Pass null to skip. */
export function useApi<T>(path: string | null, opts: { live?: boolean } = {}): ApiState<T> {
  const { version } = useSim();
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(path !== null);
  const [tick, setTick] = useState(0);
  const lastPath = useRef<string | null>(null);

  useEffect(() => {
    if (path === null) { setData(null); setLoading(false); return; }
    if (lastPath.current !== path) { setData(null); lastPath.current = path; }
    const ctrl = new AbortController();
    setLoading(true);
    api<T>(path, { signal: ctrl.signal })
      .then((d) => { setData(d); setError(null); setLoading(false); })
      .catch((e) => { if ((e as Error).name === "AbortError") return; setError(e as ApiError); setLoading(false); });
    return () => ctrl.abort();
  }, [path, tick, opts.live === false ? 0 : version]);  // eslint-disable-line react-hooks/exhaustive-deps

  const reload = useCallback(() => setTick((t) => t + 1), []);
  return { data, error, loading, reload };
}
