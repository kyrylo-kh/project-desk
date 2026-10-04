# Decisions

This folder is the **decision inbox**. The AI agent does not take a big, expensive or taste-dependent
decision on its own. It writes a *decision request* here, keeps working on anything the decision does
not block (or *parks* it on a default, see [Parking](#parking)), and applies the answer once the human
has made the call.

- **Browse and answer:** run `desk serve --open` (the Decision Desk tab of Project Desk, on http://127.0.0.1:4700). You
  can also edit the files by hand.
- **One file per decision:** `D-0001-short-slug.md`. The YAML frontmatter holds the structured data
  and the Markdown body holds the context.
- **History stays here.** Resolved decisions are not deleted. They record why things are the way they are.
- **Longer material** (research, write-ups) goes in `material/`. Material files are not decisions.

## When the AI must ask (instead of deciding)

- Visual or design direction, brand, naming.
- Product scope: what is in or out of a milestone, core flows, pricing.
- Data schemas and domain models, public API shapes.
- New architecture, new services or dependencies, anything costly to reverse.
- Anything that will consume a lot of effort before the human has seen the direction.

The AI still decides small, reversible, conventional things itself.

## Lifecycle

```
pending ──(human answers)──▶ answered ──(AI applies)──▶ resolved
   ▲                             │
   └────── needs-info ◀──────────┘   (the human asks a question instead of choosing)
withdrawn: the question became obsolete
```

When the AI processes an answer, it also **checks the answer**. If the chosen option carries a risk,
it says so in `resolution.summary` and, if needed, opens a follow-up decision.

## File format

`desk new` copies the first `markdown` block below, so edit it to change what new requests look like.

```markdown
---
id: D-0001
title: Visual direction for the app
group: design              # groups related decisions in the desk (e.g. product-definition, design, architecture)
type: design               # one of the types in .project-desk.toml ([decisions] types)
status: pending            # pending | answered | needs-info | resolved | withdrawn
priority: high             # high | medium | low
blocking: true             # true = some work depends on this answer (it waits unless parked)
created: 2026-01-15
asked_by: ai
question: Which visual direction should the app be built on?
about: |                   # what the question is about and why it matters: 1 to 2 plain sentences (rules below)
  How every screen of the app will look: colours, type and mood.
  Every page's design depends on it, so changing it later is expensive.
tldr: |                    # the short version: 2 to 4 short lines (rules below)
  Which visual direction to build on: Calm or Bold.
  I recommend a, Calm: quiet and easy to carry to every screen.
  It blocks page design until it is answered.
recommendation: a          # option id the AI recommends (optional)
default: null              # option id the AI works with until the human answers; set = parked (optional)
options:
  - id: a
    label: Calm
    summary: One-line description.
    pros: [Short point, Short point]
    cons: [Short point]
    previews: [decisions/material/calm.svg]
  - id: b
    label: Bold
    summary: ...
    pros: []
    cons: []
    previews: []
answer:                    # written by the human (desk UI or by hand)
  choice: null             # option id, or "other" (explain in comment)
  comment: ""
  answered_at: null
resolution:                # written by the AI after applying the answer
  summary: ""
  resolved_at: null
  links: []                # repo paths that now reflect the decision (docs, ADRs, specs)
followups: []              # ids of decisions spawned from this one
---

## Context
Why this decision exists, in 3 to 8 lines. What we know, and the evidence.

## What changes with each option
Concrete consequences, costs and what gets built.

## After you decide
What the AI will do next with the answer.
```

Rules for writing a request:

- Readable in **under 2 minutes**. Link to longer material instead of pasting it.
- Always write an `about`: what the question is about and why it matters, in 1 to 2 short plain
  sentences. It is not the recommendation (that is the `tldr`). Explain any term a non-expert would not
  know. The desk shows it under each title in the list and at the top of the decision. `validate` warns
  when an open decision (`pending`, `needs-info` or `answered`) has no `about`.
- Always write a `tldr`: the very short version the human reads first. 2 to 4 short lines, plain words.
  Line 1 says what is asked. The next lines say what the AI recommends and why, and what the decision
  blocks or what happens by default. `validate` warns when a `pending` or `needs-info` decision has no
  `tldr`, or when it is longer than 5 lines.
- Write `about` and `tldr` in the human's language; keep the rest of the file in the project's language.
- 2 to 4 real options. Each one is honest about its cons.
- `previews` are repo-relative paths. Images, HTML and Markdown files are shown inline in the desk.
- Mark the recommendation, but never hide the other options' strengths.

## Parking

The human does not have to answer everything before work can move. A `pending` decision with a
`default` is **parked**: the AI works with the default option until the human answers, instead of waiting.

- **Park** by setting `default` to an option id, usually the recommendation. Leave `status: pending` and
  leave `blocking` as it is: `blocking` says whether work depends on the answer, `default` says that this
  work goes ahead meanwhile.
- **The desk** shows a parked decision as parked and does not count it as blocking. `desk summary`
  lists it as `parked (default x)`, and `desk list` shows `parked (x)` in the BLOCKING column.
- **While parked**, the AI keeps the work built on the default easy to redo, and lists it in the body
  under `## Built on the default`, so the human can see what a different answer would change.
- **When the human answers** with the default, nothing is redone. With another option, the AI redoes
  what depended on the default and says what it redid in `resolution.summary`.
- **Do not park** a decision whose default would be expensive to undo or reaches outside the repo:
  spending money, anything public, messages to real people, legal or account changes.
