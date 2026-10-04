const BN_DIGITS = "০১২৩৪৫৬৭৮৯";

/** Accept Bengali digits and thousands separators; return NaN for anything that is not a plain number. */
export function parseAmount(raw: string): number {
  const s = raw.trim().replace(/[০-৯]/g, (d) => String(BN_DIGITS.indexOf(d))).replace(/[,\s৳]/g, "");
  return /^-?\d+(\.\d+)?$/.test(s) ? Number(s) : NaN;
}
