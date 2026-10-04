---
id: D-0002
title: Database for the first release
group: architecture
type: architecture
status: pending
priority: medium
blocking: true
created: 2026-01-13
asked_by: ai
question: Should the first release store its data in SQLite or in PostgreSQL?
about: |
  Where the app keeps its data. It decides how the app is hosted and backed up,
  and moving the data later is a separate piece of work.
tldr: |
  SQLite or PostgreSQL for the first release.
  I recommend b, PostgreSQL: the hosting we plan to use offers it ready-made.
  Parked on b: the data layer is built for PostgreSQL meanwhile.
recommendation: b
default: b
options:
  - id: a
    label: SQLite
    summary: One file next to the app; nothing else to run.
    pros: [Nothing to operate, Fast for one server]
    cons: [Harder to run more than one app server]
    previews: []
  - id: b
    label: PostgreSQL
    summary: A managed database service.
    pros: [Ready-made backups on the planned hosting, Scales to several app servers]
    cons: [One more service to configure]
    previews: []
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
The data layer is the next piece of work. Both options are well supported by the framework.

## What changes with each option
- **SQLite:** simpler local setup; backups are a file copy we schedule ourselves.
- **PostgreSQL:** the hosting runs backups; local development needs a container.

## After you decide
The AI writes the migrations for the chosen database.

## Built on the default
- The data layer and its migrations target PostgreSQL.
