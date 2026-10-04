# QA runs

This folder holds **manual test runs** for the human. The AI writes a run of short, concrete test
cases. The human walks them in the real app and marks each case, and the AI then processes every failure.

Automated tests answer "does the code work". A QA run answers what only a person can: does the flow
make sense, is the copy clear, would I show this to a user. A run never repeats what the automated
tests already prove.

- **Walk and mark:** `desk serve --open`, then the Test Desk tab (`g t`). You can also edit the files by hand.
- **One file per run:** `qa/runs/R-0001-short-slug.md`, with the cases in the YAML frontmatter.
- **History stays.** Processed runs are not deleted. They record what was checked and what was found.

## Lifecycle

```
ready ──(human marks a case)──▶ in-progress ──(human: Finish run)──▶ done ──(AI processes)──▶ processed
```

- `ready`: written by the AI, waiting for the human.
- `in-progress`: the desk sets it when the first case is marked.
- `done`: the human pressed **Finish run**. Every case has a result.
- `processed`: the AI handled every `fail` and `blocked` case and wrote `ai` on each one.

## File format

```markdown
---
id: R-0001
title: "Sign-up, from the landing page to the first screen"
slice: B2 # optional: the plan item this run checks (an id in plan/roadmap.yaml)
status: ready # ready | in-progress | done | processed
created: 2026-01-15
asked_by: ai
minutes: 20 # the AI's estimate of the whole run
setup: | # how to start, which URLs, which test data. Short.
  Start the app and open http://localhost:3000.
overall_note: "" # the human: overall impression of the run, free text
cases:
  - id: T01
    title: A new visitor signs up # what is being checked
    why: The first impression of the product. # optional, one line: why this matters
    where: http://localhost:3000/
    steps: # one action per line, real UI labels in quotes
      - Click "Get started".
      - Enter a new email address and submit.
    expected: # observable results, never "works fine"
      - The next screen asks for the code from the email.
    result: null # the human: null | pass | fail | blocked | skip
    note: "" # the human: what was wrong, or anything noticed
    at: null # set by the desk when the case is marked
    ai: "" # the AI: what was done about a fail or blocked case
---

## Context

Optional, 2 to 5 lines: what changed since the last run and what to pay attention to.
```

## Rules for writing a run

- **Short.** At most 15 cases and about 30 minutes per run. Split a bigger check into two runs.
- **Concrete.** Each step is one action, with the exact URL, button label and test data. Each
  `expected` line is something the human can see. Never "everything works" or "looks good".
- **Judgement, not mechanics.** Prefer cases a test cannot judge: is this copy clear, does this screen
  say what to do next, does it work on a phone. Name the question in `why`.
- **Independent.** A case should not need an earlier case to pass, or it says so in its steps.
- **No invented numbers.** Expected values come from the code or the specs, never from a guess.
- Keep one key per line in block style, as above: `desk summary` reads runs with a fast line scanner.

## Processing a finished run

For each `fail` or `blocked` case, the AI decides and writes `ai` on the case in one or two lines:

- **Bug, small:** fix it (with a test) and write `fixed in <commit>`.
- **Behaviour change:** plan the change and write where it is tracked.
- **Product question:** open a decision and write `decision: D-XXXX`.
- **Not a bug or won't fix:** write why, plainly. The human can disagree in the next run.

When every `fail` and `blocked` case has `ai`, set `status: processed`, then write a re-test run of only
those cases once the fixes are in. Read `overall_note` too: it often holds the most useful finding.
