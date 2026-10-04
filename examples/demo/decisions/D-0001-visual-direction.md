---
id: D-0001
title: Visual direction for the app
group: design
type: design
status: pending
priority: high
blocking: true
created: 2026-01-12
asked_by: ai
question: Which visual direction should the app be built on?
about: |
  How every screen of the app will look: colours, type and overall mood.
  Every page's design depends on it, so changing it later means redoing them.
tldr: |
  Which visual direction to build on: Calm or Bold.
  I recommend a, Calm: it stays readable on dense screens and is easy to extend.
  Page design waits for this answer.
recommendation: a
default: null
options:
  - id: a
    label: Calm
    summary: Warm paper background, one accent colour, generous spacing.
    pros: [Reads well on dense screens, Easy to extend to new pages]
    cons: [Less memorable at first sight]
    previews: [decisions/material/calm.svg, decisions/material/D-0001-mockup.html]
  - id: b
    label: Bold
    summary: Dark surfaces, large type and a bright accent.
    pros: [Memorable, Strong on the landing page]
    cons: [Harder to keep readable on forms and tables]
    previews: [decisions/material/bold.svg]
answer:
  choice: null
  comment: ""
  answered_at: null
resolution:
  summary: ""
  resolved_at: null
  links: []
followups: []
---

## Context
The first screens are ready to be designed, and every one of them needs a direction first.
Both options were sketched on the same home screen so they can be compared side by side.
More notes: [the comparison](material/D-0001-visual-directions.md).

## What changes with each option
- **Calm:** the components stay simple; the landing page needs more work to stand out.
- **Bold:** the landing page is easy; forms and tables need extra care for contrast.

## After you decide
The AI turns the chosen direction into design tokens and redoes the home screen with them.
