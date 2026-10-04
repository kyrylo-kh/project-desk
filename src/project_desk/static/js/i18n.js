// SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
// SPDX-License-Identifier: FSL-1.1-ALv2
/* Project Desk: UI strings. The server sends the English strings merged with the UI language's
   (GET /api/config, from src/project_desk/locales/*.json); this file only looks them up.

   t(key, params)  plain text: for textContent, titles and values that are escaped later.
   h(key, params)  HTML: the string itself is trusted markup from the package, every param is escaped.
   n / nh          the same with a plural table {"one", "few", "many", "other"} and {n} = count.
   A param made with html(markup) goes into h() and nh() as is: for markup the caller built and escaped. */

import { esc } from './util.js';

/** CLDR cardinal categories for whole numbers, for the languages the desk ships (as in i18n.py). */
export function pluralCategory(lang, count) {
  const n = Math.abs(Math.trunc(Number(count) || 0));
  if (lang === 'uk') {
    if (n % 10 === 1 && n % 100 !== 11) return 'one';
    if (n % 10 >= 2 && n % 10 <= 4 && !(n % 100 >= 12 && n % 100 <= 14)) return 'few';
    return 'many';
  }
  return n === 1 ? 'one' : 'other';
}

/** Mark a param of h() or nh() as markup that is already safe. */
export const html = (markup) => ({ __html: String(markup) });
const encode = (p) => (p && typeof p === 'object' && '__html' in p ? p.__html : esc(p));
const plain = (p) => (p && typeof p === 'object' && '__html' in p ? p.__html : String(p));

export function makeI18n(strings, lang = 'en') {
  const raw = (key) => {
    if (strings && Object.prototype.hasOwnProperty.call(strings, key)) return strings[key];
    if (typeof console !== 'undefined') console.warn(`project-desk: missing i18n key '${key}'`);
    return key;
  };
  const fill = (s, params, enc) => String(s).replace(/\{(\w+)\}/g, (m, k) => (params && k in params ? enc(params[k]) : m));
  const pick = (key, count) => {
    const table = raw(key);
    if (!table || typeof table !== 'object') return String(table);
    const cat = pluralCategory(lang, count);
    return table[cat] ?? table.other ?? table.many ?? Object.values(table)[0];
  };
  const seq = (key) => {
    const v = raw(key);
    return Array.isArray(v) ? v.map(String) : [];
  };
  return {
    lang,
    t: (key, params) => fill(raw(key), params, plain),
    h: (key, params) => fill(raw(key), params, encode),
    n: (key, count, params) => fill(pick(key, count), { n: count, ...params }, plain),
    nh: (key, count, params) => fill(pick(key, count), { n: count, ...params }, encode),
    seq,
    /** "2026-09-24" -> "24 September" / "24 вересня". Anything else comes back as is. */
    day(s) {
      const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(s || ''));
      const month = m && seq('date.months_of')[Number(m[2]) - 1];
      return month ? `${Number(m[3])} ${month}` : String(s || '');
    },
  };
}
