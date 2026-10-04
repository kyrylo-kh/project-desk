---
id: D-0004
title: Product analytics
group: product-definition
type: data
status: needs-info
priority: low
blocking: false
created: 2026-01-14
asked_by: ai
question: Should the first release collect product analytics?
about: |
  Whether the app records which screens people use, so we can see where they get stuck.
  It affects the privacy notice and what we can learn from the first users.
tldr: |
  Collect product analytics in the first release, or not yet.
  I recommend b, not yet: talking to the first users teaches more for now.
recommendation: b
default: null
options:
  - id: a
    label: Collect page views
    summary: A privacy-friendly analytics service, page views only.
    pros: [See where people drop off]
    cons: [Needs a privacy notice update]
    previews: []
  - id: b
    label: Not yet
    summary: No analytics; learn from interviews first.
    pros: [Nothing to disclose or maintain]
    cons: [No numbers on how the app is used]
    previews: []
answer:
  choice: null
  comment: "Which services did you look at, and do any of them work without cookies?"
  answered_at: "2026-01-15T17:05:00+00:00"
resolution:
  summary: ""
  resolved_at: null
  links: []
followups: []
---

## Context
The first users arrive soon. Analytics would show where they get stuck.

## What changes with each option
- **Collect page views:** one script on every page and a line in the privacy notice.
- **Not yet:** nothing changes now.

## After you decide
The AI adds the service, or records the choice and when to revisit it.
