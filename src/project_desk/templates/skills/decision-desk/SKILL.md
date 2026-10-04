---
name: decision-desk
description: Use when a choice belongs to the human rather than the AI, meaning design or brand or naming, product scope or core flows, pricing, data schemas or domain models, public API shapes, new architecture, services or dependencies, costly or irreversible work, or a big exploration before the human has seen the direction. Also use when the session-start summary reports answered or needs-info decisions, or when anyone mentions decisions/, a D-XXXX id or the Decision Desk. Covers writing a decision request with `desk new` and processing the human's answers (challenge, apply, resolve).
---

# Decision Desk (part of Project Desk)

The human makes the calls that shape the product. You write a decision request in `decisions/`, keep
working, and apply the answer later. The format contract is `decisions/README.md`: read it once per
session before writing. The tool is `desk` (run it from the project root).

## When a request is mandatory

Never decide these silently. Write a request first:

- Visual or design direction, brand, naming.
- Product scope (what is in or out of a milestone), core user flows, pricing.
- Data schemas and domain models. Public API shapes.
- New architecture, new services or new dependencies.
- Anything costly or hard to reverse.
- Any big exploration or build-out before the human has seen the direction.

Decide small, reversible, conventional things yourself, and record them where the project records
decisions. If the honest answer depends on data nobody has yet (how real users behave), do not ask:
use the recommended option, write down when to revisit it, and move on. `validate` warns when more
decisions are open than `[decisions] open_limit` allows (3 by default): close or decide one first.

## Write one

1. Scaffold it: `desk new --title "..." --type <a configured type> --group <e.g. product-definition> [--priority high] [--blocking] [--asked-by <you>]`.
   It prints the new path (the next free `D-XXXX`, `status: pending`, today's date).
2. Fill it in **immediately and in one pass**. The human's inbox shows it as soon as it exists.
   - `question`: one sentence the human can answer.
   - `about`: what the question is about and why it matters, in 1 to 2 short plain sentences. Not
     your recommendation. Explain every term a non-expert would not know.
   - `tldr`: 2 to 4 short lines: what you ask, what you recommend and why, what it blocks or what
     happens by default.
   - **2 to 4 real options**, each with a `label`, a one-line `summary`, and honest `pros` and `cons`.
     Never add a strawman option.
   - `recommendation`: your pick. Set `default` to the option you proceed with meanwhile (this
     **parks** the decision), unless it must not be parked.
   - Body: `## Context`, `## What changes with each option`, `## After you decide`.
   - Readable in **under 2 minutes**. Longer material goes in `decisions/material/` and is linked.
3. Add `previews` wherever seeing beats reading: repo-relative images, self-contained `.html`
   mockups, or `.md` material. The desk renders them inline.
4. Run `desk validate` and fix every error. A warning about leftover `TODO` placeholders or a missing
   `about` or `tldr` means the request is not finished.
5. Tell the human in one line that a decision is waiting (`desk serve --open`).

## Meanwhile: parking

Keep working on everything the decision does not block. A `pending` decision with a `default` is
**parked**: you work with the default until the human answers.

- Build on a parked default in a way that is easy to redo, and list each piece of work in the body
  under `## Built on the default`.
- **Do not park** when the default would be expensive to undo or reaches outside the repo: spending
  money, anything public, messages to real people, legal or account changes. Leave `default: null`.
- When the answer is the default, nothing is redone. When it is another option, redo what depended on
  the default and say so in `resolution.summary`.

## Process answers

At session start when the summary mentions answered or needs-info decisions, and before starting
work in an area a decision touches:

1. `desk list --status answered,needs-info`.
2. For each `answered` decision, read the whole file, including `answer.choice` and `answer.comment`.
   `choice: other` means the comment *is* the decision.
3. **Assess the answer before applying it.** Check for conflicts with earlier decisions, hidden cost,
   scope creep, UX, security or data problems, and misread options. State any risk plainly in
   `resolution.summary`; if it needs the human's call, open a follow-up decision and add its id to
   `followups`. Still apply the answer unless it is clearly harmful.
4. Apply it wherever it belongs (docs, specs, code, config).
5. Close it by editing only these frontmatter lines: `resolution.summary` (1 to 4 sentences),
   `resolution.resolved_at` (an ISO datetime), `resolution.links`, `followups`, then `status: resolved`.
6. `desk validate`.

## needs-info

The human asked a question instead of choosing; it is in `answer.comment`.

1. Answer it in the body under a new `## Follow-up` section. Quote the question first (their next save
   overwrites `answer.comment`). If the answer changes the options, keep the option ids stable and say
   what changed. Update `about` and `tldr` to match.
2. Set `status: pending`. Leave the `answer` block as it is.
3. `desk validate`.

## Rules

- `answer.*` holds only the human's call, never yours. If they answer in chat, record exactly what they
  said, name the source in `answer.comment`, and set `status: answered`.
- Edit frontmatter surgically, one line at a time. Never reformat or reorder a decision file.
- Never delete decisions. Use `withdrawn` (with a `resolution.summary` that says why) when a question
  becomes obsolete.
- The desk re-reads files on every request, so editing while it is open is safe. If a file changes
  under an open form, the human's save is refused and their view reloads.
