// SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
// SPDX-License-Identifier: FSL-1.1-ALv2
/* The QA tab: the AI writes runs in the runs folder; the human marks each case here.
   Route: #qa/R-0001. Every mark and note is saved at once (notes on blur), through one queue so each
   write carries the etag of the write before it. */

import { esc, externalLinks, own } from '../../js/util.js';
import { RESULTS, firstCase, nextUnmarked, qaListHtml, qaRunHtml, waitingRuns } from './render.js';

const MARKS = { p: 'pass', f: 'fail', b: 'blocked', s: 'skip' };

export function createTab(ctx) {
  const { i18n: i, ui, api, postJson } = ctx;
  const v = { i, cl: ctx.contentLang, lang: ctx.lang };
  const root = ctx.el;
  root.classList.add('main', 'qa-main');
  root.innerHTML = `
    <aside class="sidebar" aria-label="${esc(ctx.label)}">
      <div class="problems" hidden></div>
      <div class="list" role="listbox" aria-label="${esc(i.t('qa.list'))}" tabindex="-1"></div>
    </aside>
    <main class="detail"></main>`;
  const problemsEl = root.querySelector('.problems');
  const listEl = root.querySelector('.list');
  const detailEl = root.querySelector('.detail');

  const state = {
    qa: null, // GET /api/qa
    key: '',
    runId: null,
    run: null, // GET /api/qa/R-0001
    current: null, // the expanded case
    draft: { overall: null, notes: {} }, // typed but not saved yet (saved on blur)
    message: '',
    isError: false,
    conflictPath: null,
  };
  let token = 0;
  let queue = Promise.resolve(); // writes go one at a time, each with the newest etag
  let inFlight = 0;

  // ---------------------------------------------------------------- data

  async function loadQa() {
    const qa = await api('/api/qa');
    const key = JSON.stringify(qa);
    if (key === state.key) return;
    state.qa = qa;
    state.key = key;
    const n = waitingRuns(qa).length;
    ctx.setBadge(n, i.t('qa.badge_title', { n }));
    if (ctx.isActive()) {
      renderList();
      ensureRun();
    }
  }

  /** Keep the right run open: the one in the route, else the first one waiting on the human, else the
      newest. Reload it when its file changed on disk and no write of ours is in flight. */
  function ensureRun() {
    const runs = (state.qa && state.qa.runs) || [];
    if (!state.qa) return;
    const has = (id) => runs.some((r) => r.id === id);
    const waiting = waitingRuns(state.qa).sort((a, b) => a.id.localeCompare(b.id));
    const newest = [...runs].sort((a, b) => b.id.localeCompare(a.id));
    const id = has(state.runId) ? state.runId : (waiting[0] || newest[0] || {}).id || null;
    if (!state.run || state.run.id !== id) return selectRun(id);
    const cur = runs.find((r) => r.id === id);
    if (cur && cur.etag !== state.run.etag && !inFlight) reloadRun().catch(() => {});
  }

  async function selectRun(id) {
    state.runId = id;
    ctx.setRoute(id || '');
    renderList();
    if (!id) {
      state.run = null;
      return renderRun();
    }
    const mine = ++token;
    try {
      const run = await api('/api/qa/' + encodeURIComponent(id));
      if (mine !== token) return;
      const same = state.run && state.run.id === run.id;
      state.run = run;
      if (!same) {
        state.current = firstCase(run);
        state.draft = { overall: null, notes: {} };
        state.message = '';
        state.isError = false;
      }
      renderRun();
      if (!same) detailEl.scrollTop = 0;
    } catch (err) {
      if (mine !== token) return;
      state.run = null;
      detailEl.innerHTML = ctx.blankHtml(i.h('qa.open_failed'), esc(err.message));
    }
  }

  async function reloadRun() {
    if (!state.run) return;
    const id = state.run.id;
    const run = await api('/api/qa/' + encodeURIComponent(id));
    if (!state.run || state.run.id !== id) return;
    state.run = run;
    if (!run.cases.some((c) => c.id === state.current)) state.current = firstCase(run);
    renderRun();
  }

  // ---------------------------------------------------------------- render

  function renderList() {
    if (!state.qa) return;
    listEl.innerHTML = qaListHtml(state.qa, state.runId, v);
    if (state.runId) listEl.setAttribute('aria-activedescendant', 'qa-row-' + state.runId);
    const files = [...new Set((state.qa.problems || []).map((p) => p.file))];
    problemsEl.hidden = !files.length;
    if (files.length) problemsEl.innerHTML = i.nh('common.problems', files.length, { command: ctx.command });
  }

  /** Re-render the open run, keeping focus, the caret and the scroll position. */
  function renderRun() {
    const run = state.run;
    if (!run) {
      detailEl.innerHTML =
        state.qa && !(state.qa.runs || []).length
          ? ctx.blankHtml(i.h('qa.none_title'), i.h('qa.none_text', { dir: state.qa.dir || 'qa/runs' }))
          : '';
      return;
    }
    const active = document.activeElement;
    const focusId = active && active.id && detailEl.contains(active) ? active.id : null;
    const caret = focusId && active.matches('textarea') ? [active.selectionStart, active.selectionEnd] : null;
    const scroll = detailEl.scrollTop;
    detailEl.innerHTML = qaRunHtml(
      run,
      { current: state.current, notes: state.draft.notes, overall: state.draft.overall, message: state.message, isError: state.isError },
      v,
    );
    for (const prose of detailEl.querySelectorAll('.prose')) externalLinks(prose);
    const first = detailEl.querySelector('.qa-body > h2:first-child'); // "## Context" repeats nothing useful here
    if (first && /^context$/i.test(first.textContent.trim())) first.remove();
    detailEl.scrollTop = scroll;
    const again = focusId && document.getElementById(focusId);
    if (again) {
      again.focus({ preventScroll: true });
      if (caret) again.setSelectionRange(caret[0], caret[1]);
    }
  }

  function say(message, isError = false) {
    state.message = message;
    state.isError = isError;
    const el = root.querySelector('#qa-msg');
    if (!el) return;
    el.className = 'composer-msg' + (isError ? ' is-error' : '');
    if (message) el.textContent = message;
    else renderRun();
  }

  function showCase(id, { focus = false } = {}) {
    if (!id || !state.run) return;
    state.current = id;
    renderRun();
    const li = document.getElementById('qa-case-' + id);
    if (li) li.scrollIntoView({ block: 'nearest' });
    if (focus) {
      const head = li && li.querySelector('.qa-case-head');
      if (head) head.focus({ preventScroll: true });
    }
  }

  function moveCase(delta) {
    const cases = (state.run && state.run.cases) || [];
    if (!cases.length) return;
    const at = cases.findIndex((c) => c.id === state.current);
    const next = at < 0 ? 0 : Math.min(cases.length - 1, Math.max(0, at + delta));
    showCase(cases[next].id, { focus: true });
  }

  function focusNote() {
    const t = state.current && document.getElementById('qa-note-' + state.current);
    if (!t || t.readOnly) return;
    t.focus();
    t.setSelectionRange(t.value.length, t.value.length);
  }

  // ---------------------------------------------------------------- writes

  /** POST to /api/qa/<run>/<path>. `body` is called when the write's turn comes, so it sees the newest state. */
  function write(path, body) {
    const rid = state.run && state.run.id;
    if (!rid) return Promise.resolve(null);
    inFlight++;
    const job = async () => {
      try {
        const cur = state.run && state.run.id === rid ? state.run : null;
        const saved = await postJson(`/api/qa/${encodeURIComponent(rid)}/${path}`, { ...body(cur), etag: cur ? cur.etag : undefined });
        if (state.run && state.run.id === saved.id) state.run = saved;
        // A conflict message stays until the write it names succeeds, so a lost mark is never hidden.
        if (state.isError && (!state.conflictPath || state.conflictPath === path)) {
          state.message = '';
          state.isError = false;
          state.conflictPath = null;
        }
        return saved;
      } catch (err) {
        if (err.status === 409) {
          await reloadRun().catch(() => {});
          state.conflictPath = path;
          const what = path.startsWith('case/') ? i.t('qa.conflict_mark', { id: decodeURIComponent(path.slice(5)) }) : i.t('qa.conflict_change');
          state.message = i.t('qa.conflict', { what });
        } else {
          state.message = err.message || i.t('common.save_failed');
        }
        state.isError = true;
        return null;
      } finally {
        inFlight--;
        if (state.run && state.run.id === rid) renderRun();
        loadQa().catch(() => {});
      }
    };
    queue = queue.then(job, job);
    return queue;
  }

  /** p/f/b/s: mark the open case (the same key again un-marks it). Pass and skip move on to the next
      unmarked case; fail and blocked stay and invite a note. */
  function mark(result, caseId = state.current) {
    const run = state.run;
    const c = run && run.cases.find((x) => x.id === caseId);
    if (!c || run.status === 'processed') return;
    const next = c.result === result ? null : result;
    if (next == null && run.status === 'done') return say(i.t('qa.err_unmark_done'), true);
    const hasDraft = own(state.draft.notes, c.id);
    const note = hasDraft ? state.draft.notes[c.id] : undefined;
    // Optimistic: the server's answer replaces this a moment later.
    c.result = next;
    run.marked = run.cases.filter((x) => x.result != null).length;
    run.counts = Object.fromEntries(RESULTS.map((r) => [r, run.cases.filter((x) => x.result === r).length]));
    state.current = c.id;
    write('case/' + encodeURIComponent(c.id), () => (hasDraft ? { result: next, note } : { result: next })).then((saved) => {
      if (saved && hasDraft && state.draft.notes[c.id] === note) delete state.draft.notes[c.id];
    });
    if (next === 'pass' || next === 'skip') {
      const after = nextUnmarked(run, c.id);
      if (after) return showCase(after, { focus: true });
      renderRun();
      const btn = root.querySelector('#qa-finish');
      if (btn && !btn.disabled) btn.focus({ preventScroll: true });
      return;
    }
    renderRun();
    if (next === 'fail' || next === 'blocked') focusNote();
  }

  function saveNote(cid) {
    const run = state.run;
    if (!run || run.status === 'processed' || !own(state.draft.notes, cid)) return;
    const note = state.draft.notes[cid];
    const c = run.cases.find((x) => x.id === cid);
    if (!c) return;
    if (note.trim() === (c.note || '').trim()) {
      delete state.draft.notes[cid];
      return;
    }
    write('case/' + encodeURIComponent(cid), (cur) => {
      const now = cur && cur.cases.find((x) => x.id === cid);
      return { result: now ? now.result : c.result, note };
    }).then((saved) => {
      if (saved && state.draft.notes[cid] === note) delete state.draft.notes[cid];
      if (saved) ui.toast(i.t('qa.toast_note', { id: cid }));
    });
  }

  function saveOverall() {
    const run = state.run;
    const text = state.draft.overall;
    if (!run || run.status === 'processed' || text == null) return;
    if (text.trim() === (run.overall_note || '').trim()) {
      state.draft.overall = null;
      return;
    }
    write('note', () => ({ note: text })).then((saved) => {
      if (saved && state.draft.overall === text) state.draft.overall = null;
      if (saved) ui.toast(i.t('qa.toast_overall'));
    });
  }

  async function finishRun() {
    if (!state.run) return;
    const saved = await write('finish', () => ({}));
    if (saved && saved.status === 'done') {
      const bad = (saved.counts.fail || 0) + (saved.counts.blocked || 0);
      ui.toast(i.t('qa.toast_finished', { id: saved.id }) + (bad ? ' ' + i.t('qa.toast_finished_bad') : ''));
    }
  }

  // ---------------------------------------------------------------- events

  listEl.addEventListener('click', (e) => {
    const row = e.target.closest('[data-run]');
    if (row && row.dataset.run !== state.runId) selectRun(row.dataset.run);
  });

  detailEl.addEventListener('click', (e) => {
    const m = e.target.closest('[data-mark]');
    if (m) return mark(m.dataset.mark, m.dataset.case);
    const open = e.target.closest('[data-open]');
    if (open && open.dataset.open === state.current) {
      state.current = null; // a second click folds it
      return renderRun();
    }
    if (open) return showCase(open.dataset.open, { focus: true });
    const act = e.target.closest('[data-action]');
    if (act && act.dataset.action === 'finish' && !act.disabled) finishRun();
  });
  detailEl.addEventListener('input', (e) => {
    const t = e.target;
    if (t.id === 'qa-overall') state.draft.overall = t.value;
    else if (t.dataset.note) {
      state.draft.notes[t.dataset.note] = t.value;
      t.classList.remove('is-inviting');
    }
  });
  detailEl.addEventListener('focusout', (e) => {
    const t = e.target;
    if (t.id === 'qa-overall') return saveOverall();
    if (!t.dataset || !t.dataset.note) return;
    // A click on a result button saves the note together with the result (see mark).
    const to = e.relatedTarget;
    if (to && to.closest && to.closest(`[data-mark][data-case="${CSS.escape(t.dataset.note)}"]`)) return;
    saveNote(t.dataset.note);
  });

  function keydown(e, typing) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      // In a note: save it and go to the next unmarked case.
      if (!typing) return;
      e.preventDefault();
      const cid = e.target.dataset && e.target.dataset.note;
      e.target.blur();
      if (cid) {
        const after = nextUnmarked(state.run, cid);
        if (after) showCase(after, { focus: true });
      }
      return;
    }
    if (e.key === 'Escape') {
      if (typing) e.target.blur();
      return;
    }
    if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
    if (MARKS[e.key]) mark(MARKS[e.key]);
    else if (e.key === 'j') moveCase(1);
    else if (e.key === 'k') moveCase(-1);
    else if (e.key === 'c') focusNote();
    else return;
    e.preventDefault();
  }

  const help = () => [
    [['p', 'f', 'b', 's'], i.t('qa.help_mark')],
    [['j', 'k'], i.t('qa.help_move')],
    [['c'], i.t('qa.help_note')],
    [[ui.MOD, '↵'], i.t('qa.help_save_note')],
  ];

  return {
    /** `rest` is a run id, or empty. */
    route(rest) {
      if (rest) state.runId = rest;
      if (state.qa) {
        renderList();
        ensureRun();
      }
      loadQa().catch(() => {});
    },
    async load() {
      try {
        await loadQa();
      } catch (err) {
        if (!state.qa) detailEl.innerHTML = ctx.blankHtml(i.h('ui.offline_title'), esc(err.message));
        throw err;
      }
    },
    refresh: loadQa, // in every tab: the switch shows how many runs wait on the human
    keydown,
    help,
    unsaved: () => state.draft.overall != null || Object.keys(state.draft.notes).length > 0 || inFlight > 0,
  };
}
