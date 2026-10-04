# Configuration

Zero config works. The Decision Desk is always on. The Plan and Test Desk tabs turn on when their
files exist (`plan/roadmap.yaml`, `qa/runs/`). The UI is in English on 127.0.0.1:4700.

Settings go in `.project-desk.toml` at the project root, or in `[tool.project-desk]` in
`pyproject.toml`. If both exist, `.project-desk.toml` wins. Unknown keys and wrong types are errors,
so a typo never fails silently.

```toml
lang = "en"                  # UI and `desk brief` language: "en" or "uk"
content_lang = "en"          # language of the files' prose, for the HTML lang attribute (default: lang)
port = 4700
host = "127.0.0.1"           # use 0.0.0.0 only inside a container (see Docker below)
modules = ["plan", "decisions", "qa"]   # leave a desk out to turn it off
open_hint = "desk serve --open"         # how `summary` and `brief` tell people to open the desk
command = "desk"             # how messages name the CLI, e.g. "uvx desk"
theme = "auto"               # auto (follows the OS), light, dark, contrast, manila, terminal

[decisions]
dir = "decisions"
types = ["product", "design", "architecture", "data", "process", "brand"]
open_limit = 3               # `validate` warns when more decisions than this are open (0: off)

[plan]
file = "plan/roadmap.yaml"
actions_key = "actions"      # the top-level list of what the human needs to do

[qa]
dir = "qa/runs"
max_cases = 15               # `validate` warns above this many cases per run
note_key = "overall_note"    # the run-level free-text field the human fills in
```

`plan` is the Plan tab, `decisions` the Decision Desk and `qa` the Test Desk. If `modules` is set, a
table for a module that is not listed is an error.

The root is `--root DIR`, else `$PROJECT_DESK_ROOT`, else the nearest folder upwards with
`.project-desk.toml`, `[tool.project-desk]` in `pyproject.toml`, a `decisions/` folder or a
`plan/roadmap.yaml`.

The old names `.desk.toml` and `[tool.desk]` are still read, with a note to rename them.

## Commands

| Command | What it does |
|---|---|
| `desk serve [--open] [--port N] [--host H]` | Start the UI. Binds to 127.0.0.1. |
| `desk brief` | One terminal screen for the human. |
| `desk summary` | Status for the agent, for a SessionStart hook. Silent outside a desk project, always exits 0. |
| `desk list [--status pending,answered]` | Table of decisions. |
| `desk new --title … --type … --group … [--priority high] [--blocking]` | Create the next `D-XXXX` file. |
| `desk validate` | Check every file. Exits 1 on errors. |
| `desk init [--plan] [--qa] [--skills] [--all] [--lang uk] [--hook]` | Set up a project. Never overwrites a file. |

`project-desk` and `python -m project_desk` are the same program.

## Keyboard

Press `?` in the UI for the full list.

| Keys | Where | Action |
|---|---|---|
| `g p`, `g d`, `g t` | everywhere | Plan, Decision Desk, Test Desk |
| `j` / `k` | Decision Desk, Test Desk | Next / previous item |
| `1`–`9`, `o` | Decision Desk | Pick an option, or "Other" |
| `c`, `⌘↵`, `⌘⇧↵` | Decision Desk | Comment, save the answer, ask for more info |
| `v` | Decision Desk | View previews full size |
| `/` | Decision Desk | Filter |
| `g i` / `g w` / `g h` / `g a` | Decision Desk | Inbox, waiting on the AI, history, all |
| `p` `f` `b` `s` | Test Desk | Pass, fail, blocked, skip (again to clear) |
| `c`, `⌘↵` | Test Desk | Note on the case, save and go to the next one |

On Linux and Windows, `Ctrl` stands in for `⌘`.

## Themes

Light, dark, high contrast, manila and terminal, picked in the top bar and remembered per browser.
`theme` in the config sets the default. Every theme passes WCAG AA; `tests/test_themes.py` checks
each colour pair.

| [Light](screenshots/light.png) | [Dark](screenshots/dark.png) | [High contrast](screenshots/contrast.png) | [Manila](screenshots/manila.png) | [Terminal](screenshots/terminal.png) | [Phone](screenshots/light-390.png) |
|---|---|---|---|---|---|

## Claude Code

`desk init --hook` adds a SessionStart hook to `.claude/settings.json`, so the agent sees the open
decisions, answers and test runs at the start of every session. Without `--hook`, `init` prints the
snippet instead:

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [{ "type": "command", "command": "cd \"$CLAUDE_PROJECT_DIR\" && desk summary || true", "timeout": 30 }] }
    ]
  }
}
```

`desk init --skills` adds `.claude/skills/decision-desk/SKILL.md` and, with `--qa`,
`.claude/skills/test-desk/SKILL.md`. They tell the agent when to ask, how to write a request and how
to process answers.

## Docker

Mount your project at `/repo`, run as your own user so saved files keep your ownership, and publish
the port on the host's loopback only. Keep the host and container port the same: the desk checks the
`Host` header, port included.

```sh
docker build -t project-desk:local .
docker run --rm -p 127.0.0.1:4700:4700 --user "$(id -u):$(id -g)" -v "$PWD:/repo" \
  project-desk:local serve --host 0.0.0.0 --port 4700
```

Do not publish the port beyond `127.0.0.1` (`-p 4700:4700` exposes it to your network). The Host
check stops browsers, not other machines, and the desk has no login.

Compose:

```yaml
services:
  desk:
    build: https://github.com/kyrylo-kh/project-desk.git   # or image: project-desk:local
    command: ["serve", "--host", "0.0.0.0", "--port", "${DESK_PORT:-4700}"]
    environment:
      DESK_PORT: ${DESK_PORT:-4700}       # read by the image's healthcheck
    user: "${UID:-1000}:${GID:-1000}"     # saved files keep your ownership
    working_dir: /repo
    volumes:
      - .:/repo
    ports:
      - "127.0.0.1:${DESK_PORT:-4700}:${DESK_PORT:-4700}"   # loopback only, same port on both sides
```
