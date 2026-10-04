// Bangla labels for model features (English labels come from the server, i.e. liquidity_forecaster.FEATURE_LABELS).
const BASE: Record<string, string> = {
  is_salary_week: "বেতন সপ্তাহ (৭–১০ তারিখ)", is_post_salary_week: "বেতন-পরবর্তী সপ্তাহ (১১–১৬ তারিখ)", is_month_end_week: "মাসের শেষ সপ্তাহ",
  days_to_month_end: "মাসের শেষ পর্যন্ত দিন", day_of_month: "মাসের দিন", day_of_week: "সপ্তাহের দিন", is_friday: "শুক্রবার",
  is_weekend: "সাপ্তাহিক ছুটি (শুক্র/শনি)", is_holiday: "সরকারি ছুটি", is_working_day: "কার্যদিবস", closed_days_ahead: "সামনে বন্ধের দিন",
  is_eid_day: "ঈদের দিন", is_pre_eid_fitr: "ঈদুল ফিতরের আগের কেনাকাটার সময়", is_pre_eid_adha: "ঈদুল আযহার আগের কেনাকাটার সময়",
  is_eid_bonus_week: "ঈদ বোনাস সপ্তাহ", days_to_nearest_eid: "নিকটতম ঈদ পর্যন্ত দূরত্ব", is_ramadan: "রমজান",
  is_semester_start: "বিশ্ববিদ্যালয়ের সেমিস্টার শুরু", month: "বছরের মাস", h: "পূর্বাভাসের দূরত্ব",
  urban: "শহুরে এলাকা", garment: "গার্মেন্ট এলাকা", remittance: "রেমিটেন্স এলাকা", agri: "কৃষি এলাকা", university: "বিশ্ববিদ্যালয় এলাকা",
  logcap_cash: "এজেন্টের নগদ ধারণক্ষমতা", logcap_ef: "এজেন্টের ই-ফ্লোট ধারণক্ষমতা", log_co_ci_scale: "ক্যাশ-আউট বনাম ক্যাশ-ইনের ভারসাম্য",
};
const FLOW: Record<string, string> = { co: "ক্যাশ-আউট", ci: "ক্যাশ-ইন" };
const HIST: Record<string, (f: string) => string> = {
  logscale: (f) => `সাধারণ ${f} স্তর (২৮ দিন)`, last_r: (f) => `গতকালের ${f}`, roll7_r: (f) => `গত ৭ দিনের ${f}`,
  lag7_r: (f) => `গত সপ্তাহের একই বারের ${f}`, lag14_r: (f) => `২ সপ্তাহ আগের একই বারের ${f}`, lag21_r: (f) => `৩ সপ্তাহ আগের একই বারের ${f}`,
  dowmean_r: (f) => `একই বারের গড় ${f}`,
};
const TRAIT: Record<string, string> = {
  urban: "শহুরে এজেন্ট", garment: "গার্মেন্ট এলাকার এজেন্ট", remittance: "রেমিটেন্স এলাকার এজেন্ট", agri: "কৃষি এলাকার এজেন্ট", university: "বিশ্ববিদ্যালয় এলাকার এজেন্ট",
};
const EVENT: Record<string, string> = {
  is_salary_week: "বেতন সপ্তাহ", is_post_salary_week: "বেতন-পরবর্তী সপ্তাহ", is_month_end_week: "মাসের শেষ সপ্তাহ", is_eid_bonus_week: "ঈদ বোনাস সপ্তাহ",
  pre_eid_any: "ঈদ-পূর্ব কেনাকাটার সময়", is_semester_start: "সেমিস্টার শুরু", is_ramadan: "রমজান",
};

export function bnFeatureLabel(feature: string | null): string | undefined {
  if (!feature) return undefined;
  if (BASE[feature]) return BASE[feature];
  let m = feature.match(/^(co|ci)_(logscale|last_r|roll7_r|lag7_r|lag14_r|lag21_r|dowmean_r)$/);
  if (m) return HIST[m[2]](FLOW[m[1]]);
  m = feature.match(/^x_(urban|garment|remittance|agri|university)_(.+)$/);
  if (m && EVENT[m[2]]) return `${TRAIT[m[1]]} × ${EVENT[m[2]]}`;
  return undefined;
}
