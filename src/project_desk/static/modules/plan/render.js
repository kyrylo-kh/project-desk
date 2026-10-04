// SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
// SPDX-License-Identifier: FSL-1.1-ALv2
/* The Plan tab: pure HTML builders for GET /api/plan (the plan file as plain JSON, plus `decisions`,
   an id -> state lookup). No DOM access; the tests run them in Node.

   v = { i: the i18n object, command: the CLI name, links: is the Decisions tab on (decision chips
         link to it) } */

import { html } from '../../js/i18n.js';
import { esc } from '../../js/util.js';

const PLAN_STATUSES = ['done', 'doing', 'next', 'later', 'waiting'];
const DECISION_STATUSES = ['pending', 'needs-info', 'answered', 'resolved', 'withdrawn'];

const planItems = (plan) => ((plan && plan.phases) || []).flatMap((p) => p.items || []);

/** A waiting item that waits on the human (not on the outside world): it shares a decision with one
    of the plan's actions for the human, or one of its decisions is still pending. */
export function waitsOnHuman(item, plan) {
  if (!item || item.status !== 'waiting') return false;
  const asked = new Set(((plan && plan.actions) || []).flatMap((a) => a.decisions || []));
  const lookup = (plan && plan.decisions) || {};
  return (item.decisions || []).some((id) => asked.has(id) || (lookup[id] && lookup[id].status === 'pending'));
}

export function planChipHtml(status, { here = false, human = false } = {}, i) {
  if (here) return `<span class="pchip is-here">${i.h('plan.here')}<span class="sr-only">${i.h('plan.here_sr', { status: i.t('plan.status.doing') })}</span></span>`;
  const label =
    status === 'waiting' && human ? i.t('plan.waiting_on_you') : PLAN_STATUSES.includes(status) ? i.t('plan.status.' + status) : status || '?';
  return `<span class="pchip pchip-${esc(status)}${status === 'waiting' && human ? ' is-you' : ''}">${esc(label)}</span>`;
}

/** A decision id as a chip that opens it in the Decisions tab, with its state when we know it. */
export function decisionChipHtml(id, lookup, v) {
  const { i } = v;
  const d = (lookup || {})[id];
  if (!d || d.exists === false) {
    return `<span class="dchip is-missing" title="${esc(i.t('plan.no_decision', { id }))}"><span class="mono">${esc(id)}</span></span>`;
  }
  const cls = d.blocking_now ? ' is-blocking' : d.parked ? ' is-parked' : '';
  const word = d.parked ? i.t('plan.decision_parked') : DECISION_STATUSES.includes(d.status) ? i.t('plan.decision.' + d.status) : d.status;
  const inner = `<span class="si si-${esc(d.status)}${cls}" aria-hidden="true"></span><span class="mono">${esc(id)}</span><span class="sr-only">: ${esc(d.title)}, ${esc(word)}</span>`;
  const title = `${esc(id)} · ${esc(d.title)} — ${esc(word)}`;
  if (v.links === false) return `<span class="dchip" title="${title}">${inner}</span>`;
  return `<a class="dchip" href="#decisions/${esc(id)}" data-decision="${esc(id)}" title="${title}">${inner}</a>`;
}

/** A repo file from `links`. Images, HTML and Markdown open in the desk's viewer on a plain click (the
    href still opens a new tab); a missing path shows as such. */
export function planLinkHtml(link, label, i) {
  const path = String((link && link.path) || '');
  const short = path.split('/').filter(Boolean).slice(-2).join('/') || path;
  if (link && link.kind === 'web') {
    return `<a class="plink" href="${esc(link.url)}" target="_blank" rel="noopener" title="${esc(path)}">${esc(short)} ↗</a>`;
  }
  if (!link || !link.exists) {
    const why = link && link.in_repo ? i.h('plan.link_cannot_open') : i.h('plan.link_missing');
    return `<span class="plink is-missing" title="${esc(path)}"><span class="mono">${esc(short)}</span> · ${why}</span>`;
  }
  const view = ['image', 'html', 'markdown'].includes(link.kind) ? ` data-view="${esc(link.kind)}"` : '';
  return `<a class="plink" href="${esc(link.url)}" target="_blank" rel="noopener"${view} data-path="${esc(path)}" data-label="${esc(label)}" title="${esc(path)}"><span class="mono">${esc(short)}</span></a>`;
}

function refsHtml(entry, plan, label, v) {
  const chips = (entry.decisions || []).map((id) => decisionChipHtml(id, plan.decisions, v));
  const links = (entry.links || []).map((l) => planLinkHtml(l, label, v.i));
  return chips.length || links.length ? `<div class="refs">${chips.join('')}${links.join('')}</div>` : '';
}

const reached = (node) =>
  node.status === 'done' || node.status === 'doing' || (node.status === 'waiting' && node.phaseStatus === 'done');

function planItemHtml(item, plan, seg, v) {
  const { i } = v;
  const here = item.id === plan.now && item.status === 'doing';
  const human = waitsOnHuman(item, plan);
  const cls = `item node st-${esc(item.status)}${here ? ' is-here' : ''} seg-${seg}`;
  return `<li class="${cls}" id="plan-item-${esc(item.id)}"${here ? ' aria-current="step"' : ''}>
      <div class="item-head"><span class="item-id mono">${esc(item.id)}</span><span class="item-title">${esc(item.title)}</span>${planChipHtml(item.status, { here, human }, i)}</div>
      ${item.about ? `<p class="item-about">${esc(item.about)}</p>` : ''}
      ${item.needs ? `<p class="item-needs"><span class="needs-label">${i.h('plan.needs')}</span> ${esc(item.needs)}</p>` : ''}
      ${refsHtml(item, plan, item.title, v)}
    </li>`;
}

function planPhaseHtml(phase, plan, isOpen, segs, v) {
  const { i } = v;
  const items = phase.items || [];
  const done = items.filter((x) => x.status === 'done').length;
  const hasNow = items.some((x) => x.id === plan.now);
  const count = items.length
    ? `<span class="count" aria-hidden="true">${done}/${items.length}</span><span class="sr-only">${i.h('plan.done_of', { done, total: items.length })}</span>`
    : '';
  const title = `<span class="phase-title">${esc(phase.title)}</span>`;
  const heading = items.length
    ? `<button type="button" class="phase-toggle" aria-expanded="${isOpen}" aria-controls="plan-items-${esc(phase.id)}" data-phase="${esc(phase.id)}">${title}<span class="chev" aria-hidden="true"></span></button>`
    : title;
  const list = items.length
    ? `<ol class="items" id="plan-items-${esc(phase.id)}"${isOpen ? '' : ' hidden'}>${items.map((it, n) => planItemHtml(it, plan, segs[n + 1] || 'dotted', v)).join('')}</ol>`
    : '';
  return `<li class="phase st-${esc(phase.status)}${hasNow ? ' has-here' : ''}">
      <div class="phase-head node st-${esc(phase.status)} seg-${segs[0]}">
        <div class="phase-line"><h3 class="phase-h">${heading}</h3><span class="phase-meta">${count}${planChipHtml(phase.status, {}, i)}</span></div>
        ${phase.about ? `<p class="phase-about">${esc(phase.about)}</p>` : ''}
        ${refsHtml(phase, plan, phase.title, v)}
      </div>
      ${list}
    </li>`;
}

/** Is this phase expanded? Done and later phases start collapsed (the trail stays short), except the
    one holding `now`; `open` (phase id -> bool, the viewer's clicks) wins. */
export function phaseOpen(phase, plan, open) {
  if (open && Object.prototype.hasOwnProperty.call(open, phase.id)) return !!open[phase.id];
  return !['done', 'later'].includes(phase.status) || (phase.items || []).some((x) => x.id === plan.now);
}

function planTopHtml(plan, v) {
  const { i } = v;
  const items = planItems(plan);
  const phaseOf = (id) => (plan.phases || []).find((p) => (p.items || []).some((x) => x.id === id));
  const now = items.find((x) => x.id === plan.now);
  const also = items.filter((x) => x.status === 'doing' && x.id !== plan.now);
  const next = items.filter((x) => x.status === 'next').slice(0, 2);
  const asks = plan.actions || [];
  const entry = (x) =>
    `<p class="box-title"><span class="mono">${esc(x.id)}</span> ${esc(x.title)}</p>${x.about ? `<p class="box-about">${esc(x.about)}</p>` : ''}`;
  const nowPhase = now && phaseOf(now.id);
  const nowMeta = [
    nowPhase ? i.h('plan.phase_of', { title: nowPhase.title }) : '',
    also.length ? `${i.h('plan.in_parallel')} ${also.map((x) => `<span class="mono">${esc(x.id)}</span> ${esc(x.title)}`).join(', ')}` : '',
  ].filter(Boolean);
  const ask = (a) => `<li class="ask">
        <div class="ask-head"><h3 class="ask-title">${esc(a.title)}</h3>${a.when ? `<span class="when">${esc(a.when)}</span>` : ''}</div>
        ${a.about ? `<p class="ask-about">${esc(a.about)}</p>` : ''}
        ${a.note ? `<p class="ask-note">${esc(a.note)}</p>` : ''}
        ${refsHtml(a, plan, a.title, v)}
      </li>`;
  return `<div class="plan-top">
      <section class="box box-now" aria-labelledby="box-now">
        <h2 class="box-label" id="box-now">${i.h('plan.now')}</h2>
        ${now ? entry(now) + (nowMeta.length ? `<p class="box-meta">${nowMeta.join(' · ')}</p>` : '') : `<p class="box-empty">${i.h('plan.now_empty')}</p>`}
      </section>
      <section class="box box-next" aria-labelledby="box-next">
        <h2 class="box-label" id="box-next">${i.h('plan.next')}</h2>
        ${next.length ? next.map(entry).join('') : `<p class="box-empty">${i.h('plan.next_empty')}</p>`}
      </section>
      <section class="box box-you${asks.length ? ' has-asks' : ''}" aria-labelledby="box-you">
        <h2 class="box-label" id="box-you">${i.h('plan.from_you')}${asks.length ? ` <span class="n">${asks.length}</span>` : ''}</h2>
        ${asks.length ? `<ol class="asks">${asks.map(ask).join('')}</ol>` : `<p class="box-empty">${i.h('plan.from_you_empty')}</p>`}
      </section>
    </div>`;
}

/** The whole tab. `plan` is the /api/plan payload (null while loading); `open` is phaseOpen's override. */
export function planHtml(plan, open, v) {
  const { i } = v;
  if (!plan) return '';
  const file = `<code>${esc(plan.file || 'plan/roadmap.yaml')}</code>`;
  const validate = `<code>${esc(v.command || 'desk')} validate</code>`;
  if (plan.exists === false) {
    return `<div class="blank"><h2>${i.h('plan.none_title')}</h2><p>${i.h('plan.none_text', { file: html(file) })}</p></div>`;
  }
  if (plan.error) {
    return `<div class="blank"><h2>${i.h('plan.error_title')}</h2><p>${file}: ${esc(plan.error)}</p><p>${i.h('plan.error_text', { validate: html(validate) })}</p></div>`;
  }
  const phases = plan.phases || [];
  // One flat trail: every phase head, then its items when expanded. The line below a node is solid
  // when both of its ends are reached (done or in progress), dotted otherwise.
  const opened = phases.map((p) => phaseOpen(p, plan, open));
  const nodes = [];
  phases.forEach((p, n) => {
    nodes.push(p);
    if (opened[n]) for (const it of p.items || []) nodes.push({ ...it, phaseStatus: p.status });
  });
  const segOf = (k) => (k === nodes.length - 1 ? 'end' : reached(nodes[k]) && reached(nodes[k + 1]) ? 'solid' : 'dotted');
  let k = 0;
  const trail = phases
    .map((p, n) => {
      const segs = [segOf(k++)];
      if (opened[n]) for (let m = 0; m < (p.items || []).length; m++) segs.push(segOf(k++));
      return planPhaseHtml(p, plan, opened[n], segs, v);
    })
    .join('');
  const problems = (plan.problems || []).length;
  return `<div class="plan-inner">
      <header class="plan-head">
        <h1 class="plan-h" id="plan-title">${i.h('tab.plan')}</h1>
        ${plan.updated ? `<p class="plan-updated">${i.h('plan.updated', { date: html(`<time datetime="${esc(plan.updated)}">${esc(i.day(plan.updated))}</time>`) })}</p>` : ''}
      </header>
      ${problems ? `<p class="plan-problems">${i.nh('plan.problems', problems, { validate: html(validate) })}</p>` : ''}
      ${planTopHtml(plan, v)}
      <section class="trail-wrap" aria-labelledby="trail-label">
        <h2 class="plan-label" id="trail-label">${i.h('plan.phases')}</h2>
        ${phases.length ? `<ol class="trail">${trail}</ol>` : `<p class="box-empty">${i.h('plan.phases_empty')}</p>`}
      </section>
    </div>`;
}
