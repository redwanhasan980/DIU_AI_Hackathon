// Number & date formatting. Money uses Bangladeshi lakh grouping: ৳1,20,000 (RULES.md R-CODE-6).
import type { Lang } from "../api/types";

const BN_DIGITS = "০১২৩৪৫৬৭৮৯";

export function toBnDigits(s: string): string {
  return s.replace(/[0-9]/g, (d) => BN_DIGITS[Number(d)]);
}

export function lakh(n: number): string {
  const neg = n < 0;
  const s = String(Math.round(Math.abs(n)));
  if (s.length <= 3) return (neg ? "-" : "") + s;
  let head = s.slice(0, -3);
  const tail = s.slice(-3);
  const groups: string[] = [];
  while (head.length > 2) {
    groups.unshift(head.slice(-2));
    head = head.slice(0, -2);
  }
  if (head) groups.unshift(head);
  return (neg ? "-" : "") + groups.join(",") + "," + tail;
}

export function taka(n: number, lang: Lang = "en"): string {
  const s = "৳" + lakh(n);
  return lang === "bn" ? toBnDigits(s) : s;
}

/** Compact money for axes and tiles: ৳1.2L (lakh), ৳3.4Cr (crore). */
export function takaShort(n: number, lang: Lang = "en"): string {
  const a = Math.abs(n);
  let s: string;
  if (a >= 1e7) s = `${(n / 1e7).toFixed(a >= 1e8 ? 0 : 1)}Cr`;
  else if (a >= 1e5) s = `${(n / 1e5).toFixed(a >= 1e6 ? 0 : 1)}L`;
  else if (a >= 1e3) s = `${Math.round(n / 1e3)}k`;
  else s = String(Math.round(n));
  s = "৳" + s;
  return lang === "bn" ? toBnDigits(s) : s;
}

export function num(n: number, lang: Lang = "en"): string {
  const s = n.toLocaleString("en-IN");
  return lang === "bn" ? toBnDigits(s) : s;
}

export function pct(p: number, lang: Lang = "en", digits = 0): string {
  const s = `${(p * 100).toFixed(digits)}%`;
  return lang === "bn" ? toBnDigits(s) : s;
}

const BN_MONTHS = ["জানু", "ফেব্রু", "মার্চ", "এপ্রি", "মে", "জুন", "জুলা", "আগ", "সেপ্টে", "অক্টো", "নভে", "ডিসে"];
const EN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function shortDate(iso: string, lang: Lang = "en"): string {
  const [, m, d] = iso.split("-").map(Number);
  return lang === "bn" ? `${toBnDigits(String(d))} ${BN_MONTHS[m - 1]}` : `${d} ${EN_MONTHS[m - 1]}`;
}

export function weekday(iso: string, lang: Lang = "en"): string {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString(lang === "bn" ? "bn-BD" : "en-GB", { weekday: "short" });
}

export function addDays(iso: string, days: number): string {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}
