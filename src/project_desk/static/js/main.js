// SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
// SPDX-License-Identifier: FSL-1.1-ALv2
/* Project Desk: the shell. Vanilla ES modules, no build step, no network beyond the desk's own origin.

   It reads /api/config (the UI language's strings and the enabled modules), adds one switch in the
   top bar and one root element per module, imports each module's tab.js and calls its
   createTab(ctx). The hash is the route: `#<module>/<rest>`; the first tab (the Plan, when it is on)
   is the default view. A hash that names no module goes whole to the first tab that claims it (so an
   old `#D-0001` link still opens that decision), else to the first tab.

   A tab is { route(rest, entering), load(), refresh(), keydown(e, typing), gKeys, help(), unsaved(),
   claims(hash) }, every member optional. See docs/architecture.md, "The frontend". */

import { api, postJson } from './api.js';
import { makeI18n } from './i18n.js';
import { esc, store } from './util.js';
import { createUi } from './ui.js';

const POLL_MS = 5000;
/** The themes, in the switcher's order; keep in step with THEMES in config.py and js/theme.js. */
export const THEMES = ['auto', 'light', 'dark', 'contrast', 'manila', 'terminal'];
const $ = (sel) => document.querySelector(sel);

const blankHtml = (title, ...paras) => `<div class="blank"><h2>${title}</h2>${paras.map((p) => `<p>${p}</p>`).join('')}</div>`;

function fatal(title, message) {
  const el = document.createElement('div');
  el.className = 'detail';
  el.innerHTML = blankHtml(esc(title), esc(message));
  $('#app').append(el);
}

async function boot() {
  let cfg;
  try {
    cfg = await api('/api/config');
  } catch (err) {
    fatal('Desk server not reachable', err.message);
    return;
  }
  const i18n = makeI18n(cfg.strings, cfg.lang);
  document.documentElement.lang = cfg.lang;
  for (const el of document.querySelectorAll('[data-i18n]')) el.textContent = i18n.t(el.dataset.i18n);
  for (const el of document.querySelectorAll('[data-i18n-aria]')) el.setAttribute('aria-label', i18n.t(el.dataset.i18nAria));
  const ui = createUi(i18n);
  $('#root-name').textContent = cfg.root || '';
  setupThemes(i18n, cfg.theme);

  const tabs = [];
  let active = null;

  function updateTitle() {
    const n = tabs.reduce((sum, t) => sum + (t.count || 0), 0);
    const where = active && active !== tabs[0] ? `${active.label} · ` : '';
    document.title = `${n ? `(${n}) ` : ''}${where}Project Desk`;
  }

  const hashOf = (t, rest) => `#${t.name}${rest ? '/' + rest : ''}`;

  function ctxFor(t) {
    return {
      name: t.name,
      label: t.label,
      settings: t.settings || {},
      el: t.el,
      i18n,
      ui,
      api,
      postJson,
      lang: cfg.lang,
      contentLang: cfg.content_lang || cfg.lang,
      command: cfg.command || 'desk',
      blankHtml,
      isActive: () => active === t,
      hasModule: (name) => tabs.some((x) => x.name === name),
      /** Remember this tab's place (`#<name>/<rest>`); the address bar shows it while the tab is open. */
      setRoute(rest) {
        t.rest = rest || '';
        t.link.setAttribute('href', hashOf(t, t.rest));
        if (active === t) history.replaceState(null, '', hashOf(t, t.rest));
      },
      /** Open this tab where it was left. */
      open() {
        location.hash = hashOf(t, t.rest);
      },
      /** The badge on the tab: a count or a short label ('' or 0 hides it). kind: 'mark' (waits on
          the human, the default), 'hot' (waits on the human and blocks work) or 'label' (information). */
      setBadge(value, title = '', kind = 'mark') {
        const b = t.link.querySelector('.desk-n');
        b.hidden = !value;
        b.textContent = value ? String(value) : '';
        b.className = 'desk-n ' + (kind === 'mark' ? 'mark' : 'is-' + kind);
        t.link.title = value ? title : '';
      },
      /** What waits on the human in this tab; the page title starts with the sum, as "(2) ". */
      setTitleCount(n) {
        t.count = n || 0;
        updateTitle();
      },
    };
  }

  for (const m of cfg.modules || []) {
    const el = document.createElement('div');
    el.className = 'tab-root';
    el.id = 'tab-' + m.name;
    el.hidden = true;
    $('#app').append(el);
    const link = document.createElement('a');
    link.className = 'desk';
    link.dataset.mode = m.name;
    link.href = '#' + m.name;
    link.innerHTML = `<span class="desk-label">${esc(m.label)}</span><span class="desk-n" hidden></span>`;
    $('#modes').append(link);
    tabs.push({ ...m, el, link, rest: '', count: 0, tab: null });
  }

  await Promise.all(
    tabs.map(async (t) => {
      try {
        const mod = await import(t.script);
        t.tab = mod.createTab(ctxFor(t)) || {};
      } catch (err) {
        console.error(`project-desk: the ${t.name} tab failed to load`, err);
        t.el.className = 'tab-root detail';
        t.el.innerHTML = blankHtml(i18n.h('ui.tab_failed', { tab: t.label }), esc(err.message));
      }
    }),
  );

  function activate(t, rest) {
    const entering = active !== t;
    active = t;
    for (const x of tabs) {
      x.el.hidden = x !== t;
      if (x === t) x.link.setAttribute('aria-current', 'page');
      else x.link.removeAttribute('aria-current');
    }
    updateTitle();
    if (t.tab && t.tab.route) t.tab.route(rest, entering);
  }

  function route() {
    if (!tabs.length) return;
    const h = decodeURIComponent(location.hash.slice(1));
    const [head, ...more] = h.split('/');
    const named = tabs.find((x) => x.name === head);
    if (named) return activate(named, more.join('/'));
    const claimed = h && tabs.find((x) => x.tab && x.tab.claims && x.tab.claims(h));
    activate(claimed || tabs[0], claimed ? h : '');
  }

  function openHelp() {
    const sections = tabs
      .filter((t) => t.tab && t.tab.help)
      .map((t) => ({ title: t.label, rows: t.tab.help() }));
    const general = tabs.filter((t) => t.hotkey).map((t) => [['g', t.hotkey], i18n.t('ui.help_go', { tab: t.label })]);
    general.push(
      [['←', '→'], i18n.t('ui.help_viewer')],
      [['Esc'], i18n.t('ui.help_esc')],
      [['?'], i18n.t('ui.help_help')],
    );
    ui.openHelp([...sections, { title: i18n.t('ui.help_general'), rows: general }]);
  }
  $('#help-button').addEventListener('click', openHelp);

  let gPending = false;
  let gTimer = null;

  /** `g` then a key: a tab's hotkey opens that tab; otherwise a tab's own g-keys (like the decision views). */
  function goKey(key) {
    const target = tabs.find((t) => t.hotkey === key);
    if (target) {
      location.hash = target.link.getAttribute('href');
      return true;
    }
    for (const t of tabs) {
      const fn = t.tab && t.tab.gKeys && t.tab.gKeys[key];
      if (fn) {
        fn();
        return true;
      }
    }
    return false;
  }

  document.addEventListener('keydown', (e) => {
    if (ui.lightboxKey(e) || ui.helpKey(e)) return;
    const t = e.target;
    const typing = t instanceof HTMLElement && (t.matches('input, textarea, select') || t.isContentEditable);
    const plain = !typing && !e.metaKey && !e.ctrlKey && !e.altKey;
    if (gPending && plain) {
      gPending = false;
      clearTimeout(gTimer);
      if (goKey(e.key)) e.preventDefault();
      return;
    }
    if (plain && e.key === 'g') {
      gPending = true;
      gTimer = setTimeout(() => (gPending = false), 1200);
      e.preventDefault();
      return;
    }
    if (plain && e.key === '?') {
      e.preventDefault();
      openHelp();
      return;
    }
    if (active && active.tab && active.tab.keydown) active.tab.keydown(e, typing);
  });

  /** Network failures (no HTTP status) turn the sync label red; an HTTP error is the tab's to show. */
  async function settle(calls) {
    const results = await Promise.allSettled(calls);
    const offline = results.some((r) => r.status === 'rejected' && !(r.reason && r.reason.status));
    ui.setSync(!offline, cfg.command || 'desk');
  }
  const refreshAll = () => settle(tabs.map((t) => t.tab && t.tab.refresh && t.tab.refresh()));

  window.addEventListener('hashchange', route);
  window.addEventListener('focus', refreshAll);
  window.addEventListener('beforeunload', (e) => {
    // Every tab gets the call (a tab may stash a draft here); any unsaved work asks before leaving.
    const unsaved = tabs.map((t) => !!(t.tab && t.tab.unsaved && t.tab.unsaved()));
    if (unsaved.some(Boolean)) e.preventDefault();
  });
  setInterval(() => {
    if (document.visibilityState === 'visible') refreshAll();
  }, POLL_MS);

  route();
  await settle(tabs.map((t) => t.tab && t.tab.load && t.tab.load()));
}

/** The theme switcher. The viewer's saved choice wins; without one, the config's default. "auto" removes
    data-theme, so the stylesheet follows the OS. js/theme.js already applied a saved choice before paint. */
function setupThemes(i18n, fallback) {
  const saved = store.get('theme', null);
  const apply = (name) => {
    if (name === 'auto') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.setAttribute('data-theme', name);
  };
  const current = THEMES.includes(saved) ? saved : THEMES.includes(fallback) ? fallback : 'auto';
  apply(current);
  const select = $('#theme');
  select.innerHTML = THEMES.map((n) => `<option value="${n}">${i18n.h('theme.' + n)}</option>`).join('');
  select.value = current;
  select.addEventListener('change', () => {
    apply(select.value);
    store.set('theme', select.value);
  });
}

boot();
