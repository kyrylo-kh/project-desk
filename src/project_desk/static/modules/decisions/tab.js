// SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
// SPDX-License-Identifier: FSL-1.1-ALv2
/* The Decisions tab: the inbox of decision requests and the human's answer form.
   Route: #decisions/D-0001. State and events live here; the HTML comes from render.js. */

import { externalLinks, esc, store } from '../../js/util.js';
import {
  VIEWS,
  VIEW_KEYS,
  blankDetailHtml,
  detailHtml,
  emptyListHtml,
  groupsHtml,
  inView,
  isBlockingNow,
  listHtml,
  optionLabel,
  options,
  pickKeys,
  readOnly,
  tabsHtml,
  visibleItems as visible,
} from './render.js';

export function createTab(ctx) {
  const { i18n: i, ui, api, postJson } = ctx;
  const v = { i, cl: ctx.contentLang, lang: ctx.lang, MOD: ui.MOD, SHIFT: ui.SHIFT, dir: ctx.settings.dir || 'decisions' };
  const root = ctx.el;
  root.classList.add('main');
  root.innerHTML = `
    <aside class="sidebar" aria-label="${esc(ctx.label)}">
      <nav class="tabs" role="tablist" aria-label="${esc(i.t('dec.views'))}"></nav>
      <div class="filters">
        <label class="search">
          <span class="sr-only">${i.h('dec.filter_label')}</span>
          <input type="search" placeholder="${esc(i.t('dec.filter'))}" autocomplete="off" spellcheck="false">
          <kbd class="search-kbd">/</kbd>
        </label>
        <div class="groups" aria-label="${esc(i.t('dec.groups'))}"></div>
      </div>
      <div class="problems" hidden></div>
      <div class="list" role="listbox" aria-label="${esc(i.t('dec.list'))}" tabindex="-1"></div>
    </aside>
    <main class="detail" aria-live="polite"></main>`;
  const $ = (sel) => root.querySelector(sel);
  const tabsEl = $('.tabs');
  const groupsEl = $('.groups');
  const searchEl = $('input[type="search"]');
  const problemsEl = $('.problems');
  const listEl = $('.list');
  const detailEl = $('.detail');

  const savedView = store.get('view', 'inbox');
  const state = {
    list: [],
    counts: {},
    problems: [],
    view: VIEWS[savedView] ? savedView : 'inbox',
    group: null,
    query: '',
    selectedId: null,
    detail: null,
    form: null, // { id, choice, comment, dirty }
    drafts: store.get('drafts', {}) || {},
    busy: false,
    message: '',
    messageIsError: false,
    stale: false,
    gallery: [],
    loaded: false,
  };
  let selectToken = 0;

  const visibleItems = () => visible(state.list, state.view, state.group, state.query);

  // ---------------------------------------------------------------- data

  async function loadList() {
    const data = await api('/api/decisions');
    state.list = data.decisions;
    state.counts = data.counts;
    state.problems = data.problems || [];
    state.loaded = true;
    const pending = state.counts.pending || 0;
    const blocking = state.list.filter(isBlockingNow).length;
    ctx.setTitleCount(pending);
    ctx.setBadge(
      pending,
      blocking ? i.t('dec.badge_blocking', { n: pending, b: blocking }) : i.t('dec.badge_title', { n: pending }),
      blocking ? 'hot' : 'mark',
    );
    renderSidebar();
  }

  async function select(id, { scroll = true } = {}) {
    stashDraft();
    state.selectedId = id;
    ctx.setRoute(id || '');
    renderList();
    if (scroll) scrollRowIntoView(id);
    if (!id) {
      state.detail = null;
      state.form = null;
      renderDetail();
      return;
    }
    const token = ++selectToken;
    try {
      const d = await api('/api/decisions/' + encodeURIComponent(id));
      if (token !== selectToken) return;
      state.detail = d;
      state.form = initialForm(d);
      state.message = '';
      state.stale = false;
      renderDetail();
      detailEl.scrollTop = 0;
    } catch (err) {
      if (token !== selectToken) return;
      state.detail = null;
      renderDetail(err);
    }
  }

  async function reloadDetail({ keepForm = false } = {}) {
    if (!state.detail) return;
    const id = state.detail.id;
    const scroll = detailEl.scrollTop;
    const d = await api('/api/decisions/' + encodeURIComponent(id));
    if (!state.detail || state.detail.id !== id) return;
    state.detail = d;
    if (!keepForm) state.form = initialForm(d);
    state.stale = false;
    renderDetail();
    detailEl.scrollTop = scroll;
  }

  function initialForm(d) {
    const draft = state.drafts[d.id];
    if (draft && !readOnly(d)) return { id: d.id, choice: draft.choice ?? null, comment: draft.comment || '', dirty: true };
    const answer = d.data.answer || {};
    const choice = answer.choice == null ? null : String(answer.choice);
    if (d.status === 'answered') return { id: d.id, choice, comment: answer.comment || '', dirty: false };
    return { id: d.id, choice: readOnly(d) ? null : choice, comment: '', dirty: false };
  }

  /** Unsent answers survive switching decisions and reloads (per browser, in localStorage). */
  function stashDraft() {
    const f = state.form;
    if (!f || !state.detail || state.detail.id !== f.id) return;
    if (f.dirty && (f.comment.trim() || f.choice != null)) state.drafts[f.id] = { choice: f.choice, comment: f.comment };
    else delete state.drafts[f.id];
    store.set('drafts', state.drafts);
  }

  async function refresh() {
    await loadList();
    const cur = state.detail && state.list.find((d) => d.id === state.detail.id);
    if (cur && cur.etag !== state.detail.etag) {
      if (state.form && state.form.dirty) {
        state.stale = true;
        renderComposerMessage();
      } else {
        await reloadDetail().catch(() => {});
      }
    }
    if (!state.selectedId && ctx.isActive()) ensureSelection();
  }

  function ensureSelection() {
    if (state.selectedId && state.list.some((d) => d.id === state.selectedId)) return select(state.selectedId);
    const items = visibleItems();
    return select(items.length ? items[0].id : null);
  }

  // ---------------------------------------------------------------- sidebar

  function renderSidebar() {
    tabsEl.innerHTML = tabsHtml(state.list, state.view, i);
    groupsEl.innerHTML = groupsHtml(state.list, state.view, state.group);
    const files = [...new Set(state.problems.map((p) => p.file))];
    problemsEl.hidden = !files.length;
    if (files.length) problemsEl.innerHTML = i.nh('common.problems', files.length, { command: ctx.command });
    renderList();
  }

  function renderList() {
    if (!state.loaded) {
      listEl.innerHTML = '';
      return;
    }
    const items = visibleItems();
    listEl.innerHTML = items.length
      ? listHtml(items, state.selectedId, v)
      : emptyListHtml(state.list, state.view, !!(state.query || state.group), v);
    if (state.selectedId) listEl.setAttribute('aria-activedescendant', 'row-' + state.selectedId);
  }

  function scrollRowIntoView(id) {
    const row = id && document.getElementById('row-' + id);
    if (row) row.scrollIntoView({ block: 'nearest' });
  }

  function setView(view) {
    if (!VIEWS[view] || view === state.view) return;
    state.view = view;
    state.group = null;
    store.set('view', view);
    renderSidebar();
    const items = visibleItems();
    if (!items.some((d) => d.id === state.selectedId)) select(items.length ? items[0].id : null);
  }

  function move(delta) {
    const items = visibleItems();
    if (!items.length) return;
    const at = items.findIndex((d) => d.id === state.selectedId);
    const next = at < 0 ? (delta > 0 ? 0 : items.length - 1) : Math.min(items.length - 1, Math.max(0, at + delta));
    if (items[next].id !== state.selectedId) select(items[next].id);
  }

  /** Select a decision, switching the list view first when it is not in the current one. */
  function gotoDecision(id) {
    const item = state.list.find((x) => x.id === id);
    if (item && !inView(item, state.view)) setView(Object.keys(VIEWS).find((k) => k !== 'all' && inView(item, k)) || 'all');
    return select(id);
  }

  // ---------------------------------------------------------------- detail

  function renderDetail(error) {
    state.gallery = [];
    if (error) {
      detailEl.innerHTML = ctx.blankHtml(i.h('dec.open_failed'), esc(error.message));
      return;
    }
    const d = state.detail;
    if (!d) {
      detailEl.innerHTML = blankDetailHtml(state.loaded, state.list.length, v);
      return;
    }
    detailEl.innerHTML = detailHtml(d, readOnly(d) ? null : state.form, state.gallery, v);
    for (const prose of detailEl.querySelectorAll('.prose')) externalLinks(prose);
    // The body's first "## Context" heading repeats the section label.
    const first = detailEl.querySelector('.prose.body > h2:first-child');
    if (first && /^context$/i.test(first.textContent.trim())) first.remove();
    renderComposerMessage();
  }

  async function loadMaterial(details) {
    if (details.dataset.loaded) return;
    details.dataset.loaded = '1';
    const body = details.querySelector('.md-body');
    try {
      const m = await api('/api/material?path=' + encodeURIComponent(details.dataset.md));
      body.innerHTML = m.html;
      externalLinks(body);
    } catch (err) {
      delete details.dataset.loaded;
      body.innerHTML = `<p class="loading">${i.h('common.load_failed', { error: err.message })}</p>`;
    }
  }

  // ---------------------------------------------------------------- composer

  function renderChoice() {
    const el = root.querySelector('#choice-summary');
    if (!el || !state.detail) return;
    const choice = state.form && state.form.choice;
    if (choice == null) {
      el.className = 'choice is-empty';
      el.textContent = i.t('dec.nothing_picked', { keys: pickKeys(state.detail, i) });
    } else {
      el.className = 'choice';
      el.textContent = optionLabel(state.detail, choice, i);
    }
    for (const card of detailEl.querySelectorAll('.opt.is-pickable')) {
      const on = card.dataset.choice === choice;
      card.classList.toggle('is-chosen', on);
      card.setAttribute('aria-checked', String(on));
    }
  }

  function renderComposerMessage() {
    renderChoice();
    const el = root.querySelector('#composer-msg');
    if (!el) return;
    if (state.stale) {
      el.className = 'composer-msg is-error';
      el.innerHTML = i.h('dec.stale');
      return;
    }
    el.className = 'composer-msg' + (state.messageIsError ? ' is-error' : '');
    el.textContent = state.message || '';
    for (const b of root.querySelectorAll('#composer .btn')) b.disabled = state.busy;
  }

  function say(message, isError = false) {
    state.message = message;
    state.messageIsError = isError;
    renderComposerMessage();
  }

  function pick(choice) {
    const d = state.detail;
    if (!d || readOnly(d) || !state.form) return;
    state.form.choice = state.form.choice === choice ? null : choice;
    state.form.dirty = true;
    stashDraft();
    say('');
    if (choice === 'other' && state.form.choice === 'other') focusComment();
  }

  function pickIndex(n) {
    const opts = options(state.detail);
    if (n < opts.length) pick(opts[n].id);
    else if (n === opts.length) pick('other');
  }

  function focusComment() {
    const t = root.querySelector('#comment');
    if (!t) return;
    t.focus();
    t.setSelectionRange(t.value.length, t.value.length);
  }

  async function submit(needsInfo) {
    const d = state.detail;
    if (!d || readOnly(d) || state.busy || !state.form) return;
    const f = state.form;
    f.comment = (root.querySelector('#comment') || { value: f.comment }).value;
    const comment = f.comment.trim();
    if (needsInfo && !comment) {
      say(i.t('dec.err_question'), true);
      return focusComment();
    }
    if (!needsInfo && f.choice == null) return say(i.t('dec.err_pick', { keys: pickKeys(d, i) }), true);
    if (!needsInfo && f.choice === 'other' && !comment) {
      say(i.t('dec.err_other'), true);
      return focusComment();
    }
    const before = visibleItems().map((x) => x.id);
    state.busy = true;
    say(i.t('common.saving'));
    try {
      const saved = await postJson(`/api/decisions/${encodeURIComponent(d.id)}/answer`, {
        choice: f.choice,
        comment,
        needs_info: needsInfo,
        etag: state.stale ? undefined : d.etag,
      });
      delete state.drafts[d.id];
      store.set('drafts', state.drafts);
      state.busy = false;
      state.form.dirty = false;
      ui.toast(
        needsInfo
          ? i.t('dec.toast_asked', { id: d.id })
          : i.t('dec.toast_answered', { id: d.id, choice: optionLabel(saved, f.choice, i) }),
      );
      await loadList();
      if (visibleItems().some((x) => x.id === saved.id)) {
        state.detail = saved;
        state.form = initialForm(saved);
        state.message = '';
        renderDetail();
        return;
      }
      // It left this view (an answer moves it out of the inbox): go to its neighbour.
      const after = new Set(visibleItems().map((x) => x.id));
      const at = before.indexOf(d.id);
      const next = [...before.slice(at + 1), ...before.slice(0, at).reverse()].find((id) => after.has(id));
      state.form = null;
      state.detail = null;
      await select(next || null);
    } catch (err) {
      state.busy = false;
      if (err.status === 409) await reloadDetail({ keepForm: true }).catch(() => {});
      say(err.message || i.t('common.save_failed'), true);
    }
  }

  function openFirstPreview() {
    if (!state.gallery.length) return;
    const choice = state.form && state.form.choice;
    const o = options(state.detail).find((x) => x.id === choice);
    const first = o && (o.previews || []).find((p) => p.exists && (p.kind === 'image' || p.kind === 'html'));
    ui.openLightbox(state.gallery, first ? state.gallery.findIndex((g) => g.path === first.path) : 0);
  }

  // ---------------------------------------------------------------- events

  tabsEl.addEventListener('click', (e) => {
    const b = e.target.closest('[data-view]');
    if (b) setView(b.dataset.view);
  });

  groupsEl.addEventListener('click', (e) => {
    const b = e.target.closest('[data-group]');
    if (!b) return;
    state.group = state.group === b.dataset.group ? null : b.dataset.group;
    groupsEl.innerHTML = groupsHtml(state.list, state.view, state.group);
    renderList();
  });

  searchEl.addEventListener('input', (e) => {
    state.query = e.target.value;
    renderList();
  });
  searchEl.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const items = visibleItems();
      if (items.length) select(items[0].id);
      e.target.blur();
    }
  });

  listEl.addEventListener('click', (e) => {
    const row = e.target.closest('.row');
    if (row && row.dataset.id !== state.selectedId) select(row.dataset.id, { scroll: false });
  });

  detailEl.addEventListener('click', (e) => {
    const t = e.target;
    const g = t.closest('[data-gallery]');
    if (g) return ui.openLightbox(state.gallery, Number(g.dataset.gallery));
    const go = t.closest('[data-goto]');
    if (go) {
      e.preventDefault();
      return gotoDecision(go.dataset.goto);
    }
    const act = t.closest('[data-action]');
    if (act) {
      if (act.dataset.action === 'ask') return submit(true);
      if (act.dataset.action === 'reload') {
        state.stale = false;
        return reloadDetail({ keepForm: true }).catch(() => {});
      }
      return;
    }
    if (t.closest('a, button, summary, details, textarea, input, iframe')) return;
    const card = t.closest('.opt.is-pickable');
    if (card && !window.getSelection().toString()) pick(card.dataset.choice);
  });
  detailEl.addEventListener('submit', (e) => {
    e.preventDefault();
    submit(false);
  });
  detailEl.addEventListener('input', (e) => {
    if (e.target.id !== 'comment' || !state.form) return;
    state.form.comment = e.target.value;
    state.form.dirty = true;
    if (state.messageIsError) say('');
    stashDraft();
  });
  detailEl.addEventListener(
    'toggle',
    (e) => {
      if (e.target.matches && e.target.matches('details.md') && e.target.open) loadMaterial(e.target);
    },
    true,
  );

  function keydown(e, typing) {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      submit(e.shiftKey);
      return;
    }
    if (e.key === 'Escape') {
      if (typing) e.target.blur();
      return;
    }
    if (typing || e.metaKey || e.ctrlKey || e.altKey) return;
    switch (e.key) {
      case 'j':
        move(1);
        break;
      case 'k':
        move(-1);
        break;
      case 'o':
        pick('other');
        break;
      case 'c':
        focusComment();
        break;
      case 'v':
        openFirstPreview();
        break;
      case '/':
        searchEl.focus();
        break;
      default:
        if (/^[1-9]$/.test(e.key)) pickIndex(Number(e.key) - 1);
        else return;
    }
    e.preventDefault();
  }

  // `g i`, `g w`, `g h`, `g a`: open this tab on that view, from any tab.
  const gKeys = Object.fromEntries(
    Object.entries(VIEW_KEYS).map(([key, view]) => [
      key,
      () => {
        if (!ctx.isActive()) ctx.open();
        setView(view);
      },
    ]),
  );

  const help = () => [
    [['j', 'k'], i.t('dec.help_move')],
    [['1', '–', '9'], i.t('dec.help_pick')],
    [['o'], i.t('dec.help_other')],
    [['c'], i.t('dec.help_comment')],
    [[ui.MOD, '↵'], i.t('dec.help_save')],
    [[ui.MOD, ui.SHIFT, '↵'], i.t('dec.help_ask')],
    [['v'], i.t('dec.help_view')],
    ...Object.entries(VIEW_KEYS).map(([key, view]) => [['g', key], i.t('dec.view.' + view)]),
    [['/'], i.t('dec.help_filter')],
  ];

  return {
    /** An old-style `#D-0001` link (from before the tabs had names) is this tab's. */
    claims: (hash) => /^D-\d{4}$/.test(hash),
    /** `rest` is a decision id, or empty. */
    route(rest) {
      if (rest && rest !== state.selectedId) {
        if (state.loaded) gotoDecision(rest);
        else state.selectedId = rest; // load() opens it
        return;
      }
      if (state.selectedId) ctx.setRoute(state.selectedId);
      else if (state.loaded) ensureSelection();
    },
    async load() {
      try {
        await loadList();
      } catch (err) {
        detailEl.innerHTML = ctx.blankHtml(i.h('ui.offline_title'), esc(err.message), i.h('ui.offline_start', { command: ctx.command }));
        throw err;
      }
      const wanted = state.selectedId && state.list.find((d) => d.id === state.selectedId);
      if (wanted && !inView(wanted, state.view)) {
        state.view = Object.keys(VIEWS).find((k) => k !== 'all' && inView(wanted, k)) || 'all';
        renderSidebar();
      }
      if (!wanted) state.selectedId = null;
      await ensureSelection();
    },
    refresh,
    keydown,
    gKeys,
    help,
    unsaved() {
      stashDraft(); // drafts survive the reload; nothing to ask
      return false;
    },
  };
}
