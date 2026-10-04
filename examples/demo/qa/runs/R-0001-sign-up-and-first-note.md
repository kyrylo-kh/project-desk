---
id: R-0001
title: "Sign-up and the first note"
slice: B2
status: in-progress
created: 2026-01-15
asked_by: ai
minutes: 15
setup: |
  Start the app and open http://localhost:3000.
  Use a new email address for every sign-up.
overall_note: ""
cases:
  - id: T01
    title: A new visitor signs up
    why: The first impression of the product.
    where: http://localhost:3000/
    steps:
      - Click "Get started".
      - Enter a new email address and submit.
      - Type the code from the email.
    expected:
      - After the code, the empty notes screen opens.
      - The screen says what to do first.
    result: pass
    note: ""
    at: "2026-01-15T10:02:00+00:00"
    ai: ""
  - id: T02
    title: A wrong code is explained
    where: http://localhost:3000/sign-in
    steps:
      - Ask for a code, then type a different one.
    expected:
      - The form says the code is wrong and how to get a new one.
    result: fail
    note: "It only said 'Error'."
    at: "2026-01-15T10:06:00+00:00"
    ai: ""
  - id: T03
    title: The first note
    why: Is it obvious how to start writing?
    where: http://localhost:3000/notes
    steps:
      - Click "New note".
      - Type a title and a line of text.
      - Reload the page.
    expected:
      - The note is still there after the reload.
    result: null
    note: ""
    at: null
    ai: ""
  - id: T04
    title: It works on a phone
    why: Many people will try it on a phone first.
    where: http://localhost:3000/ on a phone
    steps:
      - Repeat T03 on a phone.
    expected:
      - Every button can be reached without zooming.
    result: null
    note: ""
    at: null
    ai: ""
---

## Context

Sign-up is done. This run checks it end to end, plus the first note.
