---
id: D-0003
title: Sign-in method
group: product-definition
type: product
status: answered
priority: medium
blocking: false
created: 2026-01-10
asked_by: ai
question: How should people sign in?
about: |
  How a person proves who they are when they come back to the app.
  It shapes the first screen every returning user sees.
tldr: |
  Email code or password for sign-in.
  I recommend a, email code: nothing to remember and no password resets to build.
recommendation: a
default: null
options:
  - id: a
    label: Email code
    summary: We email a short code; the person types it in.
    pros: [Nothing to remember, No password storage]
    cons: [Needs a working email provider]
    previews: []
  - id: b
    label: Password
    summary: Classic email and password.
    pros: [Familiar, Works without email delivery]
    cons: [Password resets and storage to build]
    previews: []
answer:
  choice: a
  comment: "Email code, but let me also sign in with a passkey later."
  answered_at: "2026-01-11T09:30:00+00:00"
resolution:
  summary: ""
  resolved_at: null
  links: []
followups: []
---

## Context
Returning users need a way back in. Both options fit the current plan.

## What changes with each option
- **Email code:** an email provider is needed before launch.
- **Password:** reset and storage flows need to be built and tested.

## After you decide
The AI builds the chosen sign-in flow.
