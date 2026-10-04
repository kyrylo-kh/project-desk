// SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
// SPDX-License-Identifier: FSL-1.1-ALv2
/* The Decisions tab: pure HTML builders. No DOM access: every function takes plain data (the
   /api/decisions payloads) and a view context `v` and returns a string. The tests run them in Node.

   v = { i: the i18n object (js/i18n.js), cl: the content language (for lang=""), lang: the UI language,
         MOD, SHIFT: the modifier key names, dir: the decisions folder } */

import { html } from '../../js/i18n.js';
import { asList, esc, fmtDay, fmtWhen, inline } from '../../js/util.js';

export const STATUS_ORDER = ['pending', 'needs-info', 'answered', 'resolved', 'withdrawn'];
export const VIEWS = {
  inbox: ['pending'],
  waiting: ['needs-info', 'answered'],
  history: ['resolved', 'withdrawn'],
  all: STATUS_ORDER,
};
export const VIEW_KEYS = { i: 'inbox', w: 'waiting', h: 'history', a: 'all' };
const PRIORITY_RANK = { high: 0, medium: 1, low: 2 };
export const CLOSED = new Set(['resolved', 'withdrawn']);

/** The tldr's lines (the server already trimmed trailing spaces and blank edges). */
export const tldrLines = (d) => String((d && d.tldr) || '').split('\n');
export const tldrFirst = (d) => tldrLines(d).find((l) => l.trim()) || '';

/** Parked: still pending, but the AI works with `default` until the human answers. */
export const isParked = (d) => !!d && d.status === 'pending' && d.default != null && String(d.default) !== '';
/** Work is actually waiting on the human: pending, blocking, and nothing to work with meanwhile. */
export const isBlockingNow = (d) => !!d && d.status === 'pending' && !!d.blocking && !isParked(d);

export const inView = (d, view) => (VIEWS[view] || STATUS_ORDER).includes(d.status);
export const readOnly = (d) => CLOSED.has(d.status);
export const options = (d) => (d && d.data && Array.isArray(d.data.options) ? d.data.options : []);

/** List order: by status; open ones blocking first, then by priority and age; closed ones newest first. */
export function compare(a, b) {
  const s = STATUS_ORDER.indexOf(a.status) - STATUS_ORDER.indexOf(b.status);
  if (s) return s;
  if (CLOSED.has(a.status)) return b.id.localeCompare(a.id);
  if (isBlockingNow(a) !== isBlockingNow(b)) return isBlockingNow(a) ? -1 : 1;
  const p = (PRIORITY_RANK[a.priority] ?? 3) - (PRIORITY_RANK[b.priority] ?? 3);
  if (p) return p;
  return String(a.created || '').localeCompare(String(b.created || '')) || a.id.localeCompare(b.id);
}

/** What the list shows for a view, a group and a filter text. */
export function visibleItems(list, view, group, query) {
  const q = String(query || '').trim().toLowerCase();
  return (list || [])
    .filter((d) => inView(d, view))
    .filter((d) => !group || d.group === group)
    .filter((d) => !q || [d.id, d.title, d.question, d.about, d.tldr, d.group, d.type].join(' ').toLowerCase().includes(q))
    .sort(compare);
}

/** "a · Label" for an option id; "Other" for other. */
export function optionLabel(d, id, i) {
  if (id == null) return '';
  if (id === 'other') return i.t('dec.other');
  const o = options(d).find((x) => x.id === String(id));
  return o ? `${o.id} · ${o.label || o.id}` : String(id);
}

/** The number keys that pick an option: "1–3", or "a number" when there are no options. */
export const pickKeys = (d, i) => {
  const n = Math.min(options(d).length, 9);
  return n ? `1–${n}` : i.t('dec.a_number');
};

// ---------------------------------------------------------------- the list

export function statusIcon(d, i) {
  const cls = isBlockingNow(d) ? ' is-blocking' : isParked(d) ? ' is-parked' : '';
  const note = isBlockingNow(d) ? i.t('dec.icon_blocking') : isParked(d) ? i.t('dec.icon_parked', { id: d.default }) : '';
  return `<span class="si si-${esc(d.status)}${cls}" title="${esc(i.t('dec.status.' + d.status))}${esc(note)}"></span>`;
}

/** Under a title in the list: the plain "about" line, or the tldr's first line when there is none. */
export function rowAboutHtml(d, cl) {
  const text = String((d && d.about) || '').trim() || tldrFirst(d);
  return text ? `<div class="row-about" lang="${esc(cl)}">${esc(text)}</div>` : '';
}

/** Row meta badge for a parked decision. */
export function parkedBadgeHtml(d, i) {
  if (!isParked(d)) return '';
  return `<span class="parked" title="${esc(i.t('dec.parked_title', { id: d.default }))}">${i.h('dec.parked_badge', { id: d.default })}</span>`;
}

export function rowHtml(d, selectedId, v) {
  const { i } = v;
  const selected = d.id === selectedId;
  const closed = CLOSED.has(d.status);
  const meta = [`<span class="mono">${esc(d.id)}</span>`];
  if (d.group) meta.push(`<span>${esc(d.group)}</span>`);
  if (d.priority === 'high' && !closed) meta.push(`<span class="pri-high">${i.h('dec.high')}</span>`);
  if (isBlockingNow(d)) meta.push(`<span class="blocking">${i.h('dec.blocking')}</span>`);
  if (isParked(d)) meta.push(parkedBadgeHtml(d, i));
  if (d.status === 'answered' && d.choice != null) meta.push(`<span>${i.h('dec.chose', { choice: d.choice })}</span>`);
  if (d.issue_count) meta.push(`<span class="issue-dot" title="${esc(i.t('common.file_problems'))}">${i.h('common.needs_fixing')}</span>`);
  const date = closed ? d.resolved_at || d.answered_at || d.created : d.status === 'pending' ? d.created : d.answered_at || d.created;
  return `<div class="row${selected ? ' is-selected' : ''}${closed ? ' is-closed' : ''}" role="option" aria-selected="${selected}" data-id="${esc(d.id)}" id="row-${esc(d.id)}">
      ${statusIcon(d, i)}
      <div class="row-main">
        <div class="row-title">${esc(d.title || d.question || d.id)}</div>
        ${rowAboutHtml(d, v.cl)}
        <div class="row-meta">${meta.join('')}</div>
      </div>
      <span class="row-date">${esc(fmtDay(date, v.lang))}</span>
    </div>`;
}

/** The list for what `visibleItems` returned, in status sections. */
export function listHtml(items, selectedId, v) {
  return STATUS_ORDER.map((status) => {
    const rows = items.filter((d) => d.status === status);
    if (!rows.length) return '';
    return `<div class="section" role="presentation">${v.i.h('dec.status.' + status)}<span class="n">${rows.length}</span></div>${rows.map((d) => rowHtml(d, selectedId, v)).join('')}`;
  }).join('');
}

export function emptyListHtml(list, view, filtered, v) {
  const { i } = v;
  const box = (title, text) => `<div class="empty"><strong>${title}</strong>${text}</div>`;
  if (filtered) return box(i.h('dec.empty_filter'), i.h('dec.empty_filter_text'));
  if (view === 'inbox') {
    const waiting = (list || []).filter((d) => inView(d, 'waiting')).length;
    return box(i.h('dec.empty_inbox'), waiting ? i.nh('dec.empty_inbox_waiting', waiting) : i.h('dec.empty_inbox_text'));
  }
  if (view === 'waiting') return box(i.h('dec.empty_waiting'), i.h('dec.empty_waiting_text'));
  if (view === 'history') return box(i.h('dec.empty_history'), i.h('dec.empty_history_text'));
  return box(i.h('dec.empty_all'), i.h('dec.empty_all_text', { dir: v.dir }));
}

export function tabsHtml(list, current, i) {
  return Object.keys(VIEWS)
    .map((key) => {
      const n = (list || []).filter((d) => inView(d, key)).length;
      const hot = key === 'inbox' && n > 0;
      const active = key === current;
      return `<button type="button" role="tab" class="tab${active ? ' is-active' : ''}" aria-selected="${active}" data-view="${key}">${i.h('dec.view.' + key)}<span class="count${hot ? ' is-hot' : ''}">${n}</span></button>`;
    })
    .join('');
}

/** Group chips, only when the decisions use two groups or more. */
export function groupsHtml(list, view, current) {
  const all = new Set((list || []).map((d) => d.group).filter(Boolean));
  if (all.size < 2) return '';
  const counts = new Map();
  for (const d of list) if (inView(d, view) && d.group) counts.set(d.group, (counts.get(d.group) || 0) + 1);
  if (current && !counts.has(current)) counts.set(current, 0);
  return [...counts.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(
      ([g, n]) =>
        `<button type="button" class="group-chip${g === current ? ' is-active' : ''}" data-group="${esc(g)}" aria-pressed="${g === current}">${esc(g)}<span class="n">${n}</span></button>`,
    )
    .join('');
}

// ---------------------------------------------------------------- the detail

/** Top of the detail view: what the question is about and why it matters. */
export function aboutHtml(d, v) {
  const about = String((d && d.about) || '').trim();
  if (!about) return '';
  return `<section class="about" aria-labelledby="about-label">
      <div class="about-label" id="about-label">${v.i.h('dec.about')}</div>
      <p class="about-text" lang="${esc(v.cl)}">${esc(about)}</p>
    </section>`;
}

/** The human's at-a-glance version. One block per line keeps the author's line breaks. */
export function tldrHtml(d, v) {
  if (!tldrFirst(d)) return '';
  const lines = tldrLines(d)
    .map((l) => (l.trim() ? `<p class="tldr-line">${esc(l)}</p>` : '<p class="tldr-gap" aria-hidden="true"></p>'))
    .join('');
  return `<section class="tldr" aria-labelledby="tldr-label">
      <div class="tldr-label" id="tldr-label">${v.i.h('dec.tldr')}</div>
      <div class="tldr-text" lang="${esc(v.cl)}">${lines}</div>
    </section>`;
}

/** Detail line for a parked decision. `label` is the default option's "id · label". */
export function parkedLineHtml(d, label, i) {
  if (!isParked(d)) return '';
  return `<p class="parked-line">${i.h('dec.parked_line', { option: label || d.default })}</p>`;
}

export function headHtml(d, v) {
  const { i } = v;
  const data = d.data || {};
  const meta = [`<span class="d-id">${esc(d.id)}</span>`];
  if (d.group) meta.push(`<span class="chip">${esc(d.group)}</span>`);
  if (d.type && d.type !== d.group) meta.push(`<span>${esc(d.type[0].toUpperCase() + d.type.slice(1))}</span>`);
  meta.push('<span class="dot"></span>');
  const pri = ['high', 'medium', 'low'].includes(d.priority) ? i.h('dec.priority.' + d.priority) : esc(d.priority);
  meta.push(d.priority === 'high' ? `<span class="pri-high">${pri}</span>` : `<span>${pri}</span>`);
  if (isParked(d)) meta.push(`<span class="parked">${i.h('dec.parked')}</span>`);
  else if (d.blocking) meta.push(`<span class="blocking">${i.h('dec.blocking_work')}</span>`);
  const byline = [];
  if (data.asked_by) byline.push(i.h('dec.asked_by', { who: data.asked_by }));
  if (d.created) byline.push(esc(fmtWhen(d.created, v.lang)));
  byline.push(`<span class="mono">${esc(d.file)}</span>`);
  return `<header class="d-head">
      <div class="d-meta">${meta.join('')}<span class="status-pill">${statusIcon(d, i)}${i.h('dec.status.' + d.status)}</span></div>
      ${d.title && d.title !== d.question ? `<p class="d-title">${esc(d.title)}</p>` : ''}
      <h1 class="d-question">${esc(d.question || d.title)}</h1>
      <div class="d-byline">${byline.join(' · ')}</div>
    </header>`;
}

/** Where the decision stands: the human's question, the saved answer, or the AI's resolution. */
export function bannerHtml(d, v) {
  const { i } = v;
  const data = d.data || {};
  const a = data.answer || {};
  const r = data.resolution || {};
  const when = (s) => fmtWhen(s, v.lang);
  const chose = a.choice != null ? `<b>${esc(optionLabel(d, a.choice, i))}</b>` : i.h('dec.no_option');
  if (d.status === 'needs-info') {
    return `<div class="callout is-open"><div class="callout-label">${i.h('dec.asked_label', { when: when(a.answered_at) })}</div>
        <p class="quote">${esc(a.comment)}</p>
        <p class="muted">${i.h('dec.asked_text')}</p></div>`;
  }
  if (d.status === 'answered') {
    return `<div class="callout"><div class="callout-label">${i.h('dec.answered_label', { when: when(a.answered_at) })}</div>
        <p>${i.h('dec.you_chose', { choice: html(chose) })}</p>${a.comment ? `<p class="quote muted">${esc(a.comment)}</p>` : ''}
        <p class="muted">${i.h('dec.answered_text')}</p></div>`;
  }
  if (CLOSED.has(d.status)) {
    const links = asList(r.links);
    const fups = asList(data.followups);
    const linkHtml = (l) =>
      /^https?:\/\//i.test(l) ? `<a href="${esc(l)}" target="_blank" rel="noopener">${esc(l)}</a>` : `<span class="mono">${esc(l)}</span>`;
    const label = i.h(d.status === 'resolved' ? 'dec.status.resolved' : 'dec.status.withdrawn');
    const youChose = a.answered_at
      ? i.h('dec.you_chose_on', { choice: html(chose), when: when(a.answered_at) })
      : i.h('dec.you_chose', { choice: html(chose) });
    return `<div class="callout"><div class="callout-label">${label}${r.resolved_at ? ' ' + esc(when(r.resolved_at)) : ''}</div>
        ${a.choice != null ? `<p>${youChose}</p>` : ''}
        ${a.comment ? `<p class="quote muted">${esc(a.comment)}</p>` : ''}
        ${r.summary ? `<p class="summary">${esc(r.summary)}</p>` : `<p class="muted">${i.h('dec.no_summary')}</p>`}
        ${links.length ? `<ul>${links.map((l) => `<li>${linkHtml(l)}</li>`).join('')}</ul>` : ''}
        ${fups.length ? `<p class="muted">${i.h('dec.followups')} ${fups.map((f) => `<a href="#decisions/${esc(f)}" data-goto="${esc(f)}">${esc(f)}</a>`).join(', ')}</p>` : ''}
      </div>`;
  }
  return '';
}

export function issuesHtml(d, i) {
  const errors = (d.issues || []).filter((x) => x.level === 'error');
  if (!errors.length) return '';
  return `<div class="callout is-problem"><div class="callout-label">${i.h('common.file_problems')}</div>
      <ul>${errors.map((x) => `<li>${esc(x.message)}</li>`).join('')}</ul></div>`;
}

/** Image and HTML previews join `gallery` (the viewer pages through it); Markdown opens inline. */
export function previewsHtml(previews, label, gallery, v) {
  const { i } = v;
  if (!previews || !previews.length) return '';
  const indexFor = (p) => {
    const at = gallery.findIndex((g) => g.path === p.path);
    if (at >= 0) return at;
    gallery.push({ path: p.path, url: p.url, kind: p.kind, label });
    return gallery.length - 1;
  };
  const parts = previews.map((p) => {
    if (!p.exists) {
      return `<div class="thumb is-missing"><div class="thumb-frame">${i.h('dec.missing')}</div><div class="thumb-cap"><span class="mono" title="${esc(p.path)}">${esc(p.name)}</span></div></div>`;
    }
    if (p.kind === 'image' || p.kind === 'html') {
      const inner =
        p.kind === 'image'
          ? `<img src="${esc(p.url)}" alt="${esc(label ? label + ': ' : '')}${esc(p.name)}" loading="lazy">`
          : `<iframe src="${esc(p.url)}" sandbox="allow-scripts" loading="lazy" tabindex="-1" title="${esc(i.t('dec.live_title', { name: p.name }))}" aria-hidden="true"></iframe><span class="live">${i.h('dec.live')}</span>`;
      return `<div class="thumb">
          <button type="button" class="thumb-frame" data-gallery="${indexFor(p)}" title="${esc(i.t('dec.open_path', { path: p.path }))}">${inner}</button>
          <div class="thumb-cap"><span class="mono" title="${esc(p.path)}">${esc(p.name)}</span><a href="${esc(p.url)}" target="_blank" rel="noopener" title="${esc(i.t('ui.open_new_tab'))}">${i.h('dec.new_tab')}</a></div>
        </div>`;
    }
    if (p.kind === 'markdown') {
      const kind = /(^|\/)material\//.test(p.path) ? 'dec.kind_material' : 'dec.kind_notes';
      return `<details class="md" data-md="${esc(p.path)}">
          <summary><span class="mono">${esc(p.name)}</span><span class="md-kind">${i.h(kind)}</span><a href="${esc(p.url)}" target="_blank" rel="noopener">${i.h('ui.open_new_tab')} ↗</a></summary>
          <div class="md-body prose"><p class="loading">${i.h('common.loading')}</p></div>
        </details>`;
    }
    return `<div class="thumb"><a class="thumb-frame" href="${esc(p.url)}" target="_blank" rel="noopener"></a><div class="thumb-cap"><span class="mono">${esc(p.name)}</span></div></div>`;
  });
  return `<div class="previews">${parts.join('')}</div>`;
}

function optionHtml(d, o, n, form, gallery, v) {
  const { i } = v;
  const data = d.data || {};
  const ro = readOnly(d);
  const chosen = !ro && !!form && form.choice === o.id;
  const answer = data.answer || {};
  const answered = answer.choice != null && String(answer.choice) === o.id && (ro || d.status === 'answered');
  const flags = [];
  if (answered) flags.push(`<span class="flag flag-chosen">${i.h('dec.your_answer')}</span>`);
  if (data.recommendation != null && String(data.recommendation) === o.id) flags.push(`<span class="flag flag-rec">${i.h('dec.ai_recommends')}</span>`);
  if (data.default != null && String(data.default) === o.id) flags.push(`<span class="flag">${i.h('dec.default_meanwhile')}</span>`);
  const pros = asList(o.pros);
  const cons = asList(o.cons);
  const pc =
    pros.length || cons.length
      ? `<div class="pc">
            <div class="pros"><div class="pc-label">${i.h('dec.for')}</div><ul>${pros.map((p) => `<li>${inline(p)}</li>`).join('') || '<li class="none">—</li>'}</ul></div>
            <div class="cons"><div class="pc-label">${i.h('dec.against')}</div><ul>${cons.map((c) => `<li>${inline(c)}</li>`).join('') || '<li class="none">—</li>'}</ul></div>
          </div>`
      : '';
  const key = !ro && n < 9 ? `<kbd class="opt-key">${n + 1}</kbd>` : '';
  return `<div class="opt${ro ? '' : ' is-pickable'}${chosen ? ' is-chosen' : ''}" ${ro ? '' : `role="radio" aria-checked="${chosen}"`} data-choice="${esc(o.id)}" lang="${esc(v.cl)}">
      <div class="opt-head">${key}<span class="opt-id mono">${esc(o.id)}</span><span class="opt-label">${esc(o.label || o.id)}</span><span class="opt-flags" lang="${esc(v.lang)}">${flags.join('')}</span></div>
      ${o.summary ? `<p class="opt-summary">${inline(o.summary)}</p>` : ''}
      <div class="opt-body">${pc}${previewsHtml(o.previews || [], o.label || o.id, gallery, v)}</div>
    </div>`;
}

function otherHtml(form, ro, i) {
  const chosen = !ro && !!form && form.choice === 'other';
  return `<div class="opt opt-other${ro ? '' : ' is-pickable'}${chosen ? ' is-chosen' : ''}" ${ro ? '' : `role="radio" aria-checked="${chosen}"`} data-choice="other">
      <div class="opt-head">${ro ? '' : '<kbd class="opt-key">o</kbd>'}<span class="opt-label">${i.h('dec.other')}</span>${ro ? `<span class="opt-flags"><span class="flag flag-chosen">${i.h('dec.your_answer')}</span></span>` : ''}</div>
      <p class="opt-summary">${i.h('dec.other_text')}</p>
    </div>`;
}

/** The option cards (and "Other"). `form` is the open answer ({ choice }), null when read-only. */
export function optionsHtml(d, form, gallery, v) {
  const { i } = v;
  const opts = options(d);
  const ro = readOnly(d);
  const n = Math.min(opts.length, 9);
  const hint = ro ? '' : `<span class="hint">${n ? i.h('dec.options_hint_keys', { keys: `1–${n}` }) : ''}${i.h('dec.options_hint_other')}</span>`;
  const cards = opts.map((o, k) => optionHtml(d, o, k, form, gallery, v)).join('');
  const answer = (d.data && d.data.answer) || {};
  const other = ro ? (answer.choice === 'other' ? otherHtml(form, true, i) : '') : otherHtml(form, false, i);
  return `<div class="section-label">${i.h('dec.options')} ${hint}</div><div class="options" role="radiogroup" aria-label="${esc(i.t('dec.options'))}">${cards}${other}</div>`;
}

export function composerHtml(d, form, v) {
  const { i } = v;
  const f = form || { choice: null, comment: '' };
  return `<form class="composer" id="composer" autocomplete="off">
      <div class="composer-inner">
        <div class="composer-top">
          <span class="label">${i.h('dec.your_call')}</span>
          <span class="choice" id="choice-summary"></span>
          <span class="file mono">${i.h('dec.saves_to', { file: d.file })}</span>
        </div>
        <label class="sr-only" for="comment">${i.h('dec.comment')}</label>
        <textarea id="comment" name="comment" rows="2" placeholder="${esc(i.t('dec.comment_placeholder'))}">${esc(f.comment)}</textarea>
        <div class="composer-bottom">
          <span class="composer-msg" id="composer-msg" aria-live="polite"></span>
          <button type="button" class="btn" data-action="ask">${i.h('dec.ask_more')} <kbd>${esc(v.MOD)}${esc(v.SHIFT)}↵</kbd></button>
          <button type="submit" class="btn btn-primary" data-action="save">${i.h(d.status === 'answered' ? 'dec.update_answer' : 'dec.save_answer')} <kbd>${esc(v.MOD)}↵</kbd></button>
        </div>
      </div>
    </form>`;
}

/** The whole detail view. `form` is the open answer, `gallery` collects the previews for the viewer. */
export function detailHtml(d, form, gallery, v) {
  const { i } = v;
  const data = d.data || {};
  const top = Array.isArray(data.previews) ? data.previews : [];
  return `
      <article class="doc">
        ${aboutHtml(d, v)}
        ${tldrHtml(d, v)}
        ${parkedLineHtml(d, optionLabel(d, d.default, i), i)}
        ${headHtml(d, v)}
        ${bannerHtml(d, v)}
        ${issuesHtml(d, i)}
        ${String(d.body_html || '').trim() ? `<div class="section-label">${i.h('dec.context')}</div><div class="prose body" lang="${esc(v.cl)}">${d.body_html}</div>` : ''}
        ${top.length ? `<div class="section-label">${i.h('dec.material')}</div><div class="material">${previewsHtml(top, '', gallery, v)}</div>` : ''}
        ${optionsHtml(d, form, gallery, v)}
      </article>
      ${readOnly(d) ? '' : composerHtml(d, form, v)}`;
}

export function blankDetailHtml(loaded, count, v) {
  const { i } = v;
  if (!loaded) return '';
  if (!count) {
    return `<div class="blank"><h2>${i.h('dec.none_title')}</h2><p>${i.h('dec.none_text', { dir: v.dir })}</p><p>${i.h('dec.none_by_hand')}</p></div>`;
  }
  return `<div class="blank"><h2>${i.h('dec.nothing_selected')}</h2><p>${i.h('dec.nothing_selected_text')}</p></div>`;
}
