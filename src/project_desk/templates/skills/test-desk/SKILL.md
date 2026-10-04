---
name: test-desk
description: Manual QA runs for the human (qa/runs/R-XXXX-*.md, the Test Desk tab of Project Desk). Use when a feature is ready for the human to check by hand, when writing test cases for the human, when the session-start summary reports a QA run that is done, when the human reports bugs or impressions from clicking through the app, or when anyone mentions qa/, R-XXXX, a test run or test cases.
---

# Test Desk: manual QA runs

The human checks what was built by hand. You write the cases, the human walks them in the Test Desk tab
and marks each one, and you process the result. The format and the writing rules are the contract in
`qa/README.md`: read it once per session before writing a run.

## Write a run

1. **When:** the feature's automated checks are green and the work is committed. Also as a re-test
   after a fix wave (only the cases that failed).
2. **Ground every line in the code.** Read the routes, the copy and the specs. UI labels appear
   exactly as the app shows them. Expected values come from the code or the specs, never from a guess.
3. **Spend the human's time on judgement.** Automated tests already prove the mechanics. Ask what only
   a person can answer: is it clear, what would I do next, does it work on my phone. Put the question
   in `why`.
4. **Stay inside the limits:** at most 15 cases and about 30 minutes. Set `minutes` honestly.
5. **File it** as `qa/runs/R-XXXX-<slug>.md` (the next free number), `status: ready`, then run
   `desk validate`.
6. If the project has a plan, point the matching action at the run id. Tell the human in one line:
   the run id, the minutes, and how to open it (`desk serve --open`, QA runs tab).

## Process a finished run

When the session-start summary reports a `done` run:

1. Read the whole run, including the overall note and every case's `note`. A `pass` with a note can
   hold a finding too.
2. For each `fail` and `blocked` case, reproduce it from the steps first, then pick one path and write
   it in the case's `ai` (one or two lines):
   - **Bug:** fix it with a failing-then-passing test. Write `fixed in <short sha>` after committing.
   - **Missing or wrong rule:** plan the change and write where it is tracked.
   - **Product or taste question:** a decision (the decision-desk skill). Write `decision: D-XXXX`.
   - **Not a bug, or won't fix:** say why in plain words.
3. Notes that ask for a change get the same treatment. Record them in the run's body under
   `## Findings from notes`, one line each with the outcome.
4. Set `status: processed` (edit that one line), run `desk validate`, and write the re-test run with
   only the failed cases.
5. Tell the human in two or three lines: what failed, what you fixed, and which re-test run is waiting.

## Rules

- `result`, `note`, `at` and the overall note are the human's. Never fill them in yourself. If the
  human reports results in chat, record their words in `note` with "(from chat)".
- Edit run files surgically, one line at a time. Never reformat a run or reorder its cases.
- Never delete runs. They are the record of what was checked.
- A run tests what is built. Never write a case for something not built yet.
