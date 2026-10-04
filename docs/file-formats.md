# File formats

Every file is Markdown or YAML that you can also edit by hand. `desk init` puts a README with the
full format and writing rules into each folder; [`examples/demo`](../examples/demo) has one of each.

## Decision: `decisions/D-0001-slug.md`

YAML frontmatter plus a Markdown body with the context.

| Field | |
|---|---|
| `id`, `title`, `group`, `type` | identity; `type` is one of the configured types |
| `status` | `pending`, `answered`, `needs-info`, `resolved` or `withdrawn` |
| `priority`, `blocking` | how urgent, and whether work waits on it |
| `question`, `about`, `tldr` | the question, why it matters, a 2–4 line summary |
| `recommendation` | the agent's pick |
| `default` | set means *parked*: the agent keeps working on this option until you answer |
| `options` | each with `id`, `label`, `summary`, `pros`, `cons`, `previews` |
| `answer`, `resolution`, `followups` | your answer, and what the agent did with it |

Previews are repo paths. Images, HTML and Markdown show inline.

```
pending ──(human answers)──▶ answered ──(AI applies)──▶ resolved
   ▲                             │
   └────── needs-info ◀──────────┘   (the human asked a question instead)
```

Full format: [`templates/decisions/README.md`](../src/project_desk/templates/decisions/README.md).

## Plan: `plan/roadmap.yaml`

`updated`, `now` (the item in progress), `actions` (what the human needs to do) and `phases` with
`items`. Each item has a `status`: `done`, `doing`, `next`, `later` or `waiting`. The UI only reads
the plan; the agent keeps it current.

Full format: [`templates/plan/README.md`](../src/project_desk/templates/plan/README.md).

## Test run: `qa/runs/R-0001-slug.md`

`status` (`ready`, `in-progress`, `done` or `processed`), `setup`, `minutes`, `overall_note`, and
`cases`, each with `steps`, `expected`, `result`, `note` and `ai`.

Full format: [`templates/qa/README.md`](../src/project_desk/templates/qa/README.md).

## What the desk writes

Only the human's part of a file:

- decisions: `status`, `answer.choice`, `answer.comment`, `answer.answered_at`;
- test runs: `status`, each case's `result`, `note` and `at`, and the run note.

Edits change those values in place; comments, quoting, key order and the body stay byte for byte.
Each edit is checked by parsing the result again, with a comment-preserving ruamel.yaml round trip as
the fallback. Writes are atomic (temp file, then rename). Every save carries the file's etag, so if
the agent changed the file meanwhile, the save is refused and the UI offers to reload.
