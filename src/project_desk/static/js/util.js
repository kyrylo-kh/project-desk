// SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
// SPDX-License-Identifier: FSL-1.1-ALv2
/* Project Desk: small pure helpers shared by the shell and the tabs. No DOM access except where a
   function says so; the tests import this file in Node. */

/** Escape text for HTML (element content and quoted attributes). */
export const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

/** Tiny inline Markdown for option text: `code`, **bold**, *em*. The input is escaped first. */
export const inline = (s) =>
  esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\s][^*]*)\*/g, '$1<em>$2</em>');

/** A YAML value that may be one string or a list, as a list of strings. */
export const asList = (v) => (Array.isArray(v) ? v : v == null || v === '' ? [] : [v]).map(String);

export const own = (obj, key) => !!obj && Object.prototype.hasOwnProperty.call(obj, key);

/** Plain text with its http(s) links clickable (new tab). Everything is escaped. */
export function linkText(s) {
  const text = String(s ?? '');
  const re = /https?:\/\/[^\s<>"'«»]+/g;
  let out = '';
  let last = 0;
  for (let m; (m = re.exec(text)); ) {
    const url = m[0].replace(/[.,;:!?)]+$/, '');
    out += esc(text.slice(last, m.index)) + `<a href="${esc(url)}" target="_blank" rel="noopener">${esc(url)}</a>`;
    last = m.index + url.length;
    re.lastIndex = last;
  }
  return out + esc(text.slice(last));
}

export function parseDate(s) {
  if (!s) return null;
  const d = /^\d{4}-\d{2}-\d{2}$/.test(s) ? new Date(s + 'T00:00:00') : new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

/** A short date for list rows: "Jan 5", with the year when it is not this year. */
export function fmtDay(s, lang) {
  const d = parseDate(s);
  if (!d) return '';
  const opts = { month: 'short', day: 'numeric' };
  if (d.getFullYear() !== new Date().getFullYear()) opts.year = 'numeric';
  return d.toLocaleDateString(lang, opts);
}

/** A date with the time when the value has one. Anything unreadable comes back as is. */
export function fmtWhen(s, lang) {
  const d = parseDate(s);
  if (!d) return String(s || '');
  const opts = { month: 'short', day: 'numeric', year: 'numeric' };
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s)) Object.assign(opts, { hour: '2-digit', minute: '2-digit' });
  return d.toLocaleString(lang, opts);
}

/** Per-viewer conveniences in localStorage (a remembered view, the theme, unsent drafts). Never required.
    Keys are `project-desk:<key>`; a value saved before the rename (`decision-desk:<key>`) is still read. */
export const store = {
  get(key, fallback) {
    try {
      let v = localStorage.getItem('project-desk:' + key);
      if (v == null) v = localStorage.getItem('decision-desk:' + key);
      return v == null ? fallback : JSON.parse(v);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem('project-desk:' + key, JSON.stringify(value));
    } catch {
      /* private mode or blocked storage: drafts just won't survive a reload */
    }
  },
};

/** DOM: links in rendered Markdown open in a new tab, except in-page anchors. */
export function externalLinks(el) {
  for (const a of el.querySelectorAll('a[href]')) {
    if (!(a.getAttribute('href') || '').startsWith('#')) {
      a.target = '_blank';
      a.rel = 'noopener';
    }
  }
}
