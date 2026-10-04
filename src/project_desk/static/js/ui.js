// SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
// SPDX-License-Identifier: FSL-1.1-ALv2
/* Project Desk: the shell's shared widgets (the preview viewer, the help sheet, the toast and the
   sync label). Tabs reach them through ctx.ui. */

import { esc } from './util.js';

const $ = (sel) => document.querySelector(sel);

export const IS_MAC = /Mac|iPhone|iPad|iPod/.test(navigator.platform || navigator.userAgent || '');
export const MOD = IS_MAC ? '⌘' : 'Ctrl';
export const SHIFT = IS_MAC ? '⇧' : 'Shift';

export function createUi(i18n) {
  let viewer = [];
  let index = 0;
  let toastTimer = null;

  /** Open the viewer on items[i]. Items: { path, url, kind: 'image' | 'html' | 'markdown', label }. */
  function openLightbox(items, i = 0) {
    if (!items || !items.length) return;
    viewer = items;
    index = (i + items.length) % items.length;
    const item = items[index];
    $('#lightbox-title').textContent = (item.label ? item.label + ' · ' : '') + item.path;
    $('#lightbox-count').textContent = items.length > 1 ? `${index + 1} / ${items.length}` : '';
    $('#lightbox-open').href = item.url;
    $('#lightbox-stage').innerHTML =
      item.kind === 'image'
        ? `<img src="${esc(item.url)}" alt="${esc(item.path)}">`
        : `<iframe src="${esc(item.url)}" sandbox="allow-scripts allow-popups" title="${esc(item.path)}"></iframe>`;
    for (const b of document.querySelectorAll('.lightbox-nav')) b.hidden = items.length < 2;
    $('#lightbox').hidden = false;
  }

  function closeLightbox() {
    $('#lightbox').hidden = true;
    $('#lightbox-stage').innerHTML = '';
  }

  const step = (delta) => openLightbox(viewer, index + delta);

  $('#lightbox').addEventListener('click', (e) => {
    const nav = e.target.closest('[data-nav]');
    if (nav) return step(Number(nav.dataset.nav));
    if (e.target.closest('[data-close]') || e.target.id === 'lightbox-stage') closeLightbox();
  });

  /** Keys while the viewer is open. True when the viewer took the key. */
  function lightboxKey(e) {
    if ($('#lightbox').hidden) return false;
    if (e.key === 'Escape') closeLightbox();
    else if (e.key === 'ArrowRight' || e.key === 'l') step(1);
    else if (e.key === 'ArrowLeft' || e.key === 'h') step(-1);
    else return true; // the viewer is modal: other keys do nothing
    e.preventDefault();
    return true;
  }

  /** sections: [{ title, rows: [[keys[], text], ...] }]. A key '–' is drawn as a dash between keys. */
  function openHelp(sections) {
    $('#help-keys').innerHTML = sections
      .filter((s) => s.rows.length)
      .map(
        (s) =>
          `<h3 class="keys-h">${esc(s.title)}</h3>` +
          s.rows
            .map(
              ([keys, what]) =>
                `<div class="key-row"><span>${esc(what)}</span><span class="combo">${keys
                  .map((k) => (k === '–' ? '–' : `<kbd>${esc(k)}</kbd>`))
                  .join('')}</span></div>`,
            )
            .join(''),
      )
      .join('');
    $('#help').hidden = false;
  }
  const closeHelp = () => ($('#help').hidden = true);
  $('#help').addEventListener('click', (e) => {
    if (e.target.id === 'help' || e.target.closest('[data-close]')) closeHelp();
  });

  /** Keys while the help sheet is open. True when the sheet took the key. */
  function helpKey(e) {
    if ($('#help').hidden) return false;
    if (e.key === 'Escape' || e.key === '?') {
      e.preventDefault();
      closeHelp();
    }
    return true;
  }

  function toast(message) {
    const el = $('#toast');
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => (el.hidden = true), 3200);
  }

  function setSync(ok, command) {
    const el = $('#sync');
    el.classList.toggle('is-offline', !ok);
    el.textContent = ok
      ? i18n.t('ui.synced', { time: new Date().toLocaleTimeString(i18n.lang, { hour: '2-digit', minute: '2-digit' }) })
      : i18n.t('ui.offline', { command });
  }

  return { openLightbox, closeLightbox, lightboxKey, openHelp, closeHelp, helpKey, toast, setSync, MOD, SHIFT };
}
