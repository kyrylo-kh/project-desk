# Plan

`roadmap.yaml` is where the work is: phases, their items, what is being done now, and what the human
needs to do. Project Desk shows it in the Plan tab, its first tab (`desk serve --open`, then `g p`), and
`desk summary` / `desk brief` print a short "Now / Next / Waiting on you" digest from it.

The AI keeps it current. Every change of status (an item starts, is done, or waits on the human) also
updates `status`, `now` and `updated` here, and runs `desk validate`. The human reads it and never has
to edit it.

## Format

```yaml
updated: 2026-01-15          # date of the last change
now: B2                      # the id of the item whose status is doing

actions:                     # what the human needs to do; shown under "Waiting on you"
  - title: Review the onboarding copy
    about: One or two plain lines on what and why.
    note: Optional: where, how, any caveat.
    when: this week          # optional, free text
    decisions: [D-0001]      # optional: decisions this action is about
    links: [docs/onboarding.md]  # optional: repo paths or http(s) links

phases:
  - id: P1
    title: Foundations
    status: done             # done | doing | next | later | waiting
    about: One plain line.
    items:
      - id: B1
        title: Repository and tooling
        status: done
        about: One plain line.
      - id: B2
        title: Sign-in
        status: doing
        about: One plain line.
      - id: B3
        title: Payments
        status: waiting
        needs: D-0002, the payment provider   # required for waiting: what it waits for
        about: One plain line.
```

Keep one key per line in block style, as above: `desk summary` reads this file with a fast line
scanner, and `validate` warns when the scanner and YAML disagree.
