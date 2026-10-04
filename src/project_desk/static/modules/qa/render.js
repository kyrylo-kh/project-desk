// SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
// SPDX-License-Identifier: FSL-1.1-ALv2
/* The QA tab: pure HTML builders for GET /api/qa (the runs, with counts) and GET /api/qa/R-0001 (one
   run with its cases). No DOM access; the tests run them in Node.

   v = { i: the i18n object, cl: the content language, lang: the UI language } */

import { esc, linkText } from '../../js/util.js';

export const RESULTS = ['pass', 'fail', 'blocked', 'skip'];
export const MARK_KEYS = { pass: 'p', fail: 'f', blocked: 'b', skip: 's' };
const RUN_STATUSES = ['ready', 'in-progress', 'done', 'processed'];
const RUN_GROUPS = [
  ['qa.group_you', ['ready', 'in-progress']],
  ['qa.group_ai', ['done']],
  ['qa.group_processed', ['processed']],
];

/** The runs that wait on the human. */
export const waitingRuns = (qa) => ((qa && qa.runs) || []).filter((r) => r.status === 'ready' || r.status === 'in-progress');

/** The id of the first unmarked case after `afterId` (wrapping around), or null when all are marked. */
export function nextUnmarked(run, afterId) {
  const cases = (run && run.cases) || [];
  const at = cases.findIndex((c) => c.id === afterId);
  for (let n = 1; n <= cases.length; n++) {
    const c = cases[(at + n + cases.length) % cases.length];
    if (c && c.result == null && c.id !== afterId) return c.id;
  }
  return null;
}

/** Where the human starts: the first unmarked case, else the first case. */
export const firstCase = (run) => nextUnmarked(run, null) || ((run && run.cases && run.cases[0]) || {}).id || null;

function runChipHtml(status, i) {
  const label = RUN_STATUSES.includes(status) ? i.t('qa.run.' + status) : status || '?';
  return `<span class="pchip qa-st-${esc(status)}">${esc(label)}</span>`;
}

/** "8/12 marked", plus the fail and blocked counts when there are any. */
function runCountsHtml(r, i) {
  const c = r.counts || {};
  const parts = [`<span>${i.h('qa.marked', { marked: r.marked, total: r.total })}</span>`];
  if (c.fail) parts.push(`<span class="res-fail">${i.h('qa.count.fail', { n: c.fail })}</span>`);
  if (c.blocked) parts.push(`<span class="res-blocked">${i.h('qa.count.blocked', { n: c.blocked })}</span>`);
  return parts.join('');
}

function qaRowHtml(r, selectedId, i) {
  const selected = r.id === selectedId;
  const meta = [`<span class="mono">${esc(r.id)}</span>`];
  if (r.slice) meta.push(`<span class="mono">${esc(r.slice)}</span>`);
  meta.push(runCountsHtml(r, i));
  if (r.minutes && ['ready', 'in-progress'].includes(r.status)) meta.push(`<span>${i.h('qa.minutes', { n: r.minutes })}</span>`);
  if (r.issue_count) meta.push(`<span class="issue-dot" title="${esc(i.t('common.file_problems'))}">${i.h('common.needs_fixing')}</span>`);
  return `<div class="row qa-row${selected ? ' is-selected' : ''}${r.status === 'processed' ? ' is-closed' : ''}" role="option" aria-selected="${selected}" data-run="${esc(r.id)}" id="qa-row-${esc(r.id)}">
      <span class="si qa-si qa-si-${esc(r.status)}" aria-hidden="true"></span>
      <div class="row-main">
        <div class="row-title">${esc(r.title || r.id)}</div>
        <div class="row-meta">${meta.join('')}</div>
      </div>
      ${runChipHtml(r.status, i)}
    </div>`;
}

/** The runs list, grouped by whose turn it is. `qa` is the /api/qa payload. */
export function qaListHtml(qa, selectedId, v) {
  const { i } = v;
  const runs = (qa && qa.runs) || [];
  if (!runs.length) {
    return `<div class="empty"><strong>${i.h('qa.list_empty')}</strong>${i.h('qa.list_empty_text', { dir: (qa && qa.dir) || 'qa/runs' })}</div>`;
  }
  return RUN_GROUPS.map(([label, statuses]) => {
    const rows = runs.filter((r) => statuses.includes(r.status)).sort((a, b) => b.id.localeCompare(a.id));
    if (!rows.length) return '';
    return `<div class="section" role="presentation">${i.h(label)}<span class="n">${rows.length}</span></div>${rows.map((r) => qaRowHtml(r, selectedId, i)).join('')}`;
  }).join('');
}

function qaCaseHtml(c, run, ui, v) {
  const { i } = v;
  const open = c.id === ui.current;
  const ro = run.status === 'processed';
  const note = ui.notes && Object.prototype.hasOwnProperty.call(ui.notes, c.id) ? ui.notes[c.id] : c.note;
  const res = c.result || 'none';
  const head = `<button type="button" class="qa-case-head" id="qa-head-${esc(c.id)}" data-open="${esc(c.id)}" aria-expanded="${open}" aria-controls="qa-body-${esc(c.id)}">
        <span class="qa-n mono">${esc(c.id)}</span>
        <span class="qa-title" lang="${esc(v.cl)}">${esc(c.title)}</span>
        <span class="qa-res res-${esc(res)}">${c.result ? i.h('qa.result.' + c.result) : `<span class="sr-only">${i.h('qa.unmarked')}</span>`}</span>
      </button>`;
  if (!open) {
    const peek = [
      c.note ? `<p class="qa-peek">${esc(c.note)}</p>` : '',
      c.ai ? `<p class="qa-peek qa-peek-ai">AI: ${esc(c.ai)}</p>` : '',
    ].join('');
    return `<li class="qa-case res-${esc(res)}" id="qa-case-${esc(c.id)}" data-case="${esc(c.id)}">${head}${peek}</li>`;
  }
  const where = c.where
    ? /^https?:\/\//i.test(c.where)
      ? `<p class="qa-where"><a href="${esc(c.where)}" target="_blank" rel="noopener">${esc(c.where)} ↗</a></p>`
      : `<p class="qa-where mono">${esc(c.where)}</p>`
    : '';
  const marks = RESULTS.map((r) => {
    const on = c.result === r;
    return `<button type="button" class="qa-mark res-${r}${on ? ' is-on' : ''}" id="qa-mark-${esc(c.id)}-${r}" data-mark="${r}" data-case="${esc(c.id)}" aria-pressed="${on}"${ro ? ' disabled' : ''}>${i.h('qa.mark.' + r)} <kbd>${MARK_KEYS[r]}</kbd></button>`;
  }).join('');
  const placeholder = i.t(c.result === 'fail' ? 'qa.note_fail' : c.result === 'blocked' ? 'qa.note_blocked' : 'qa.note_default');
  return `<li class="qa-case is-open res-${esc(res)}" id="qa-case-${esc(c.id)}" data-case="${esc(c.id)}" aria-current="step">
      ${head}
      <div class="qa-case-body" id="qa-body-${esc(c.id)}">
        ${c.why ? `<p class="qa-why" lang="${esc(v.cl)}">${esc(c.why)}</p>` : ''}
        ${where}
        <div class="qa-cols" lang="${esc(v.cl)}">
          <div><div class="qa-label" lang="${esc(v.lang)}">${i.h('qa.steps')}</div><ol class="qa-steps">${(c.steps || []).map((s) => `<li>${linkText(s)}</li>`).join('')}</ol></div>
          <div><div class="qa-label" lang="${esc(v.lang)}">${i.h('qa.expected')}</div><ul class="qa-expected">${(c.expected || []).map((s) => `<li>${linkText(s)}</li>`).join('')}</ul></div>
        </div>
        <div class="qa-marks" role="group" aria-label="${esc(i.t('qa.marks_label', { id: c.id }))}">${marks}</div>
        <label class="sr-only" for="qa-note-${esc(c.id)}">${i.h('qa.note_label', { id: c.id })}</label>
        <textarea class="qa-text qa-note${c.result === 'fail' && !String(note || '').trim() ? ' is-inviting' : ''}" id="qa-note-${esc(c.id)}" data-note="${esc(c.id)}" rows="2" placeholder="${esc(placeholder)}"${ro ? ' readonly' : ''}>${esc(note)}</textarea>
        ${c.ai ? `<div class="qa-ai"><span class="qa-ai-label">AI:</span> ${linkText(c.ai)}</div>` : ''}
      </div>
    </li>`;
}

/** One run. `ui` = { current: the open case id, notes: {case id: unsaved text}, overall: unsaved text or
    null, message, isError }. */
export function qaRunHtml(run, ui = {}, v) {
  const { i } = v;
  if (!run) return '';
  const ro = run.status === 'processed';
  const c = run.counts || {};
  const meta = [`<span class="d-id">${esc(run.id)}</span>`];
  if (run.slice) meta.push(`<span class="chip">${esc(run.slice)}</span>`);
  if (run.minutes) meta.push(`<span>${i.h('qa.minutes', { n: run.minutes })}</span>`);
  meta.push(`<span class="status-pill">${runChipHtml(run.status, i)}</span>`);
  const byline = [
    run.asked_by ? i.h('qa.written_by', { who: run.asked_by }) : '',
    run.created ? esc(i.day(run.created)) : '',
    `<span class="mono">${esc(run.file)}</span>`,
  ].filter(Boolean);
  const errors = (run.issues || []).filter((x) => x.level === 'error');
  const banner =
    run.status === 'done'
      ? `<div class="callout is-open"><div class="callout-label">${i.h('qa.done_label')}</div><p>${i.h('qa.done_text')}</p></div>`
      : ro
        ? `<div class="callout"><div class="callout-label">${i.h('qa.run.processed')}</div><p>${i.h('qa.processed_text')}</p></div>`
        : '';
  const overall = ui.overall != null ? ui.overall : run.overall_note;
  const segs = (run.cases || [])
    .map((x) => `<span class="qa-seg res-${esc(x.result || 'none')}${x.id === ui.current ? ' is-current' : ''}" title="${esc(x.id)}"></span>`)
    .join('');
  const all = run.total > 0 && run.marked === run.total;
  const action =
    run.status === 'ready' || run.status === 'in-progress'
      ? `<button type="button" class="btn btn-primary" id="qa-finish" data-action="finish"${all ? '' : ' disabled aria-disabled="true"'}>${i.h('qa.finish')}</button>`
      : '';
  const hint = all || action === '' ? '' : i.t('qa.left', { n: run.total - run.marked });
  return `<article class="doc qa-doc">
        <header class="d-head">
          <div class="d-meta">${meta.join('')}</div>
          <h1 class="d-question" lang="${esc(v.cl)}">${esc(run.title || run.id)}</h1>
          <div class="d-byline">${byline.join(' · ')}</div>
        </header>
        ${banner}
        ${errors.length ? `<div class="callout is-problem"><div class="callout-label">${i.h('common.file_problems')}</div><ul>${errors.map((x) => `<li>${esc(x.message)}</li>`).join('')}</ul></div>` : ''}
        ${run.setup ? `<section class="qa-setup" aria-labelledby="qa-setup-label"><div class="about-label" id="qa-setup-label">${i.h('qa.setup')}</div><div class="qa-setup-text" lang="${esc(v.cl)}">${linkText(run.setup)}</div></section>` : ''}
        ${String(run.body_html || '').trim() ? `<div class="prose body qa-body" lang="${esc(v.cl)}">${run.body_html}</div>` : ''}
        <label class="section-label" for="qa-overall">${i.h('qa.overall')}</label>
        <textarea class="qa-text" id="qa-overall" rows="2" placeholder="${esc(i.t('qa.overall_placeholder'))}"${ro ? ' readonly' : ''}>${esc(overall)}</textarea>
        <div class="section-label">${i.h('qa.cases')} <span class="hint">${i.h('qa.cases_hint')}</span></div>
        <ol class="qa-cases">${(run.cases || []).map((x) => qaCaseHtml(x, run, ui, v)).join('')}</ol>
      </article>
      <div class="composer qa-foot">
        <div class="composer-inner">
          <div class="qa-progress" role="img" aria-label="${esc(i.t('qa.progress', { marked: run.marked, total: run.total }))}">${segs}</div>
          <div class="composer-bottom">
            <span class="qa-count"><span>${i.h('qa.marked', { marked: run.marked, total: run.total })}</span>${RESULTS.filter((r) => c[r]).map((r) => `<span class="res-${r}">${i.h('qa.count.' + r, { n: c[r] })}</span>`).join('')}</span>
            <span class="composer-msg${ui.isError ? ' is-error' : ''}" id="qa-msg" aria-live="polite">${esc(ui.message || hint)}</span>
            ${action}
          </div>
        </div>
      </div>`;
}
