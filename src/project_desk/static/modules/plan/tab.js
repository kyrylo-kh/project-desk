// SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
// SPDX-License-Identifier: FSL-1.1-ALv2
/* The Plan tab: a read-only view of the plan file (the AI edits the file; the desk shows it).
   Route: #plan. Polls with the other tabs (its badge shows the
   current item), and re-renders only when the plan changed. */

import { esc } from '../../js/util.js';
import { planHtml } from './render.js';

export function createTab(ctx) {
  const { i18n: i, ui, api } = ctx;
  const v = { i, command: ctx.command, links: ctx.hasModule('decisions') && ctx.settings.decisions !== false };
  const root = ctx.el;
  root.classList.add('plan');
  root.setAttribute('aria-labelledby', 'plan-title');

  let plan = null;
  let key = '';
  const open = {}; // phase id -> expanded: the viewer's own clicks (defaults come from render.js)

  function render() {
    const a = document.activeElement;
    const toggle = a && root.contains(a) ? a.closest('[data-phase]') : null;
    const phase = toggle ? toggle.dataset.phase : null;
    root.innerHTML = planHtml(plan, open, v);
    if (phase) {
      const again = root.querySelector(`[data-phase="${CSS.escape(phase)}"]`);
      if (again) again.focus();
    }
  }

  async function load() {
    let data;
    try {
      data = await api('/api/plan');
    } catch (err) {
      if (!plan) root.innerHTML = ctx.blankHtml(i.h('ui.offline_title'), esc(err.message));
      throw err;
    }
    const k = JSON.stringify(data);
    if (k === key) return; // polls re-render only on change: no flicker, focus and scroll kept
    plan = data;
    key = k;
    const now = (data && data.now) || '';
    ctx.setBadge(now, now ? i.t('ui.badge_plan', { id: now }) : '', 'label');
    render();
  }

  root.addEventListener('click', (e) => {
    const toggle = e.target.closest('[data-phase]');
    if (toggle) {
      open[toggle.dataset.phase] = toggle.getAttribute('aria-expanded') !== 'true';
      return render();
    }
    // A plain click on an image, page or doc link opens the desk's viewer; with a modifier, the browser's tab.
    const link = e.target.closest('a[data-view]');
    if (!link || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    const links = [...root.querySelectorAll('a[data-view]')].filter((a) => !a.closest('[hidden]')); // expanded phases only
    const items = links.map((a) => ({ path: a.dataset.path, url: a.getAttribute('href'), kind: a.dataset.view, label: a.dataset.label }));
    ui.openLightbox(items, links.indexOf(link));
  });

  return {
    route(_rest, entering) {
      ctx.setRoute('');
      if (entering) load().catch(() => {});
    },
    load, // a prefetch at start, so the tab opens without a blank moment
    refresh: load, // also while closed: the tab's badge shows the current item
  };
}
