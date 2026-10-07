// The dataset is a replay of 2025. So the demo reads as "today", every DATE SHOWN is moved forward by a whole number of weeks
// (weekdays stay correct) until the simulation start (1 Sep 2025) lands next to the real current date. The data, the API and the
// calendar features (public holidays, Eid) stay on the 2025 dates; only the display and the date inputs convert.
const DAY = 86_400_000;
const ANCHOR = Date.UTC(2025, 8, 1);                       // the default simulation start

export const SHIFT_DAYS = Math.round((Date.now() - ANCHOR) / (7 * DAY)) * 7;

const move = (iso: string, days: number) => {
  const t = new Date(`${iso}T00:00:00Z`).getTime();
  return Number.isFinite(t) ? new Date(t + days * DAY).toISOString().slice(0, 10) : iso;
};

/** data date (2025 replay) -> date shown to the user */
export const shown = (iso: string) => move(iso, SHIFT_DAYS);
/** date typed or picked by the user -> data date */
export const toData = (iso: string) => move(iso, -SHIFT_DAYS);
