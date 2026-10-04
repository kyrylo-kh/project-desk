# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Shared fixture data and helpers. Every test works on temporary copies under tmp_path."""

from __future__ import annotations

import http.client
import json
import os
import re
import shutil
import subprocess
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from project_desk.desk import Desk
from project_desk.server import DeskServer, make_server

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
DEMO = PROJECT / "examples" / "demo"
STATIC = PROJECT / "src" / "project_desk" / "static"
NODE = shutil.which("node")

# The render tests import the ES modules straight from static/, which has no package.json, so Node must
# detect ES module syntax on its own: unflagged in Node 20.19 and 22.7 (21.x and 22.0-22.6 lack it).
NODE_MIN = "20.19+ or 22.7+"


def _node_problem() -> str | None:
    """Why the render tests cannot run with the `node` on PATH, or None when they can."""
    if NODE is None:
        return "node is not on PATH"
    try:
        out = subprocess.run([NODE, "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError) as e:
        return f"node --version failed: {e}"
    m = re.match(r"v(\d+)\.(\d+)", out)
    if m is None:
        return f"cannot read the node version from {out!r}"
    major, minor = int(m[1]), int(m[2])
    if (major, minor) >= (22, 7) or (major == 20 and minor >= 19):
        return None
    return f"node {out} is too old: the render tests need Node {NODE_MIN}"


# Why the render tests are skipped (None: they run). CI sets DESK_REQUIRE_NODE=1 so that they fail instead.
NODE_SKIP = _node_problem()
if NODE_SKIP and os.environ.get("DESK_REQUIRE_NODE") == "1":
    raise RuntimeError(f"DESK_REQUIRE_NODE=1 but {NODE_SKIP}")

# Deliberately awkward formatting: aligned trailing comments, quoted and flow scalars, a folded block,
# a literal block with a comment on its header and a '#' inside it, and a body with a table. Saving must
# keep all of it. The about and tldr are Ukrainian on purpose: non-ASCII text must survive byte for byte.
ABOUT_BLOCK = """\
about: |
  Яку палітру матиме застосунок: теплу чи холодну («палітра» = набір кольорів).
  Від неї залежить настрій усіх екранів: "лапки" і # лишаються.
"""
ABOUT = (
    "Яку палітру матиме застосунок: теплу чи холодну («палітра» = набір кольорів). "
    'Від неї залежить настрій усіх екранів: "лапки" і # лишаються.'
)
TLDR_BLOCK = """\
tldr: |                  # 2 to 4 lines
  Питання: тепла чи холодна палітра?
  Раджу b: спокійніше. # це не коментар
  Блокує дизайн сторінок; "лапки" і 'апострофи' лишаються.
"""
TLDR = (
    "Питання: тепла чи холодна палітра?\n"
    "Раджу b: спокійніше. # це не коментар\n"
    "Блокує дизайн сторінок; \"лапки\" і 'апострофи' лишаються."
)
DECISION = (
    """\
---
id: D-0001
title: Pick a palette      # short, human
group: design
type: design
status: pending          # pending | answered | needs-info | resolved | withdrawn
priority: high
blocking: true
created: 2026-09-01
asked_by: design-workflow
question: "Which palette should the app use: warm or cool?"
"""
    + ABOUT_BLOCK
    + TLDR_BLOCK
    + """\
recommendation: b
default: null
options:
  - id: a
    label: Warm
    summary: >-
      Folded summary
      over two lines.
    pros: [Friendly, 'Quoted: yes']
    cons:
      - Busy
    previews: [design/x/preview.png]
  - id: b
    label: Cool
    summary: Calm and quiet.
    pros: []
    cons: []
    previews:
      - design/x/preview.html
      - decisions/material/D-0001-notes.md
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
Some *context* with a table:

| a | b |
|---|---|
| 1 | 2 |
"""
)


def make_repo(tmp_path: Path, text: str = DECISION, name: str = "D-0001-pick-a-palette.md") -> Path:
    root = tmp_path / "repo"
    (root / "decisions" / "material").mkdir(parents=True)
    (root / "design" / "x").mkdir(parents=True)
    (root / "design" / "x" / "preview.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 16)
    (root / "design" / "x" / "preview.html").write_text("<!doctype html><p>hi</p>", encoding="utf-8")
    (root / "decisions" / "material" / "D-0001-notes.md").write_text("# Notes\n\nLong-form material.\n")
    (root / "decisions" / name).write_bytes(text.encode("utf-8"))
    (root / "package.json").write_text("{}")
    return root


def write_config(root: Path, text: str) -> None:
    (root / ".project-desk.toml").write_text(text, encoding="utf-8")


def decision_path(root: Path) -> Path:
    return next((root / "decisions").glob("D-0001-*.md"))


def errors(issues: list[dict[str, str]]) -> list[str]:
    return [i["message"] for i in issues if i["level"] == "error"]


def warnings(issues: list[dict[str, str]]) -> list[str]:
    return [i["message"] for i in issues if i["level"] == "warning"]


def tldr_block(text: str) -> str:
    """The raw `tldr:` lines of a decision file, exactly as written."""
    start = text.index("\ntldr:") + 1
    return text[start : text.index("\nrecommendation:", start) + 1]


def about_block(text: str) -> str:
    """The raw `about:` lines of a decision file, exactly as written."""
    start = text.index("\nabout:") + 1
    return text[start : text.index("\ntldr:", start) + 1]


def parked(text: str = DECISION, default: str = "a") -> str:
    """The fixture with a default set, so the pending decision is parked."""
    return text.replace("default: null", f"default: {default}", 1)


def status(text: str, new: str) -> str:
    """The fixture with another status, keeping the comment column."""
    return text.replace("status: pending  ", f"status: {new}".ljust(17), 1)


def dec(root: Path) -> Any:
    return Desk(root).get("decisions")


OTHER = """\
---
id: {id}
title: {title}
status: {status}
priority: {priority}
blocking: {blocking}
default: {default}
{about}---
"""


def add_decision(
    root: Path,
    did: str,
    *,
    title: str = "Another one",
    status: str = "pending",
    priority: str = "medium",
    blocking: str = "false",
    default: str = "null",
    about: str = "",
) -> None:
    text = OTHER.format(
        id=did, title=title, status=status, priority=priority, blocking=blocking, default=default, about=about
    )
    (root / "decisions" / f"{did}-x.md").write_text(text, encoding="utf-8")


# --------------------------------------------------------------------------- the plan

# Mixed YAML styles on purpose: comments, an indentless list, flow and block lists, folded and literal
# blocks, quoted titles with ':' in them. The summary's line reader must agree with ruamel on all of it.
PLAN = """\
# The plan. status: done | doing | next | later | waiting
updated: 2026-09-20
now: S1   # the item being worked on

actions:
  - title: Знайти експерта
    about: Людина з професії.
    decisions: [D-0001]
    note: AI може написати запит.
  - title: "Протестувати: анкету"
    about: Пройти шлях.
    when: після S1

phases:
  - id: P1
    title: Фундамент
    status: done
    about: Готова основа.
    items:
      - id: F1
        title: Огляд
        status: done
        about: Що працювало.
        links: [decisions/material/D-0001-notes.md]
      - id: F2
        title: Палітра
        status: waiting
        about: Чекає на відповідь.
        decisions: [D-0001]
        needs: Твоя відповідь.
  - id: P2
    title: Основний цикл
    status: doing
    about: >-
      Шлях людини
      від лендінгу.
    items:
    - id: S0            # an indentless list
      title: Основа
      status: done
      about: Лендінг.
      links:
        - design/x/preview.png
        - design/x/preview.html
    - id: S1
      title: Анкета → результат
      status: doing
      about: |
        Гість відповідає
        на 5 питань.
    - id: S2
      title: 'AI-розбір: коротко'
      status: next
      about: Після результату.
    - id: S3
      title: Акаунти
      status: later
      about: Вхід.

  - id: P3
    title: Після запуску
    status: later
    about: Потім.
    items: []
"""


def make_plan(root: Path, text: str = PLAN) -> Path:
    path = root / "plan" / "roadmap.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def edited(old: str, new: str, text: str = PLAN) -> str:
    assert old in text, old
    return text.replace(old, new, 1)


# --------------------------------------------------------------------------- QA runs

# Awkward on purpose, like DECISION: aligned trailing comments, a quoted title with ':' in it, a literal
# block, an indentless case list, a case with no result/note/at keys and a case that opens with a bare '-'.
RUN = """\
---
id: R-0001
title: "C1: весь шлях"      # plain words
slice: S1                   # plan item id
status: ready               # ready | in-progress | done | processed
created: 2026-10-03
asked_by: ai
minutes: 25                 # the AI's estimate
setup: |                    # how to start
  Запусти застосунок. Відкрий http://localhost:3000.
  Пошта: http://localhost:8025 # not a comment
overall_note: ""            # human: overall impression
cases:
- id: T01
  title: Гість проходить анкету
  why: Перше враження.
  where: http://localhost:3000/
  steps:
    - Натисни «Get started».
    - "Пройди 5 питань: обери «Option A»."
  expected:
    - Одразу відкривається результат.
  result: null              # human: null | pass | fail | blocked | skip
  note: ""                  # human
  at: null                  # set by the desk
  ai: ""                    # AI
- id: T02
  title: Вхід кодом
  steps: [Натисни «Save».]
  expected:
  - Код приходить на пошту.
-
  id: T03
  title: Тиждень
  steps:
    - Відкрий /week.
  expected:
    - Видно кроки.
  result: null
---

## Context
Перший ран. Таблиця:

| a | b |
|---|---|
"""

NOW = "2026-10-03T10:00:00+03:00"
RUN_NAME = "R-0001-c1-path.md"


def make_run(root: Path, text: str = RUN, name: str = RUN_NAME) -> Path:
    path = root / "qa" / "runs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
    return path


def run_edited(old: str, new: str, text: str = RUN) -> str:
    assert old in text, old
    return text.replace(old, new, 1)


def run_text(root: Path, name: str = RUN_NAME) -> str:
    return (root / "qa" / "runs" / name).read_text(encoding="utf-8")


def qa(root: Path) -> Any:
    return Desk(root).get("qa")


def run_issues(root: Path) -> list[dict[str, str]]:
    return qa(root).validate_docs()[1]


# --------------------------------------------------------------------------- HTTP


@contextmanager
def serving(desk: Desk) -> Iterator[DeskServer]:
    srv = make_server(desk, port=0)
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    t.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()


def request(
    srv: DeskServer,
    method: str,
    path: str,
    body: Any = None,
    headers: dict[str, str] | None = None,
    raw: bytes | None = None,
) -> tuple[int, dict[str, str], bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", srv.port, timeout=5)
    h = {"Host": f"127.0.0.1:{srv.port}"}
    h.update(headers or {})
    conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)  # raw path, no normalisation
    for k, v in h.items():
        conn.putheader(k, v)
    data = raw if raw is not None else json.dumps(body).encode() if body is not None else b""
    if body is not None or raw is not None:
        conn.putheader("Content-Length", str(len(data)))
    conn.endheaders(data or None)
    res = conn.getresponse()
    out = res.status, dict(res.getheaders()), res.read()
    conn.close()
    return out


def post(srv: DeskServer, path: str, body: Any, **headers: str) -> tuple[int, dict[str, str], bytes]:
    return request(srv, "POST", path, body, {"Content-Type": "application/json", **headers})


# --------------------------------------------------------------------------- the browser code (Node)


def node_eval(imports: dict[str, str], calls: dict[str, str], data: Any, prelude: str = "") -> dict[str, Any]:
    """Import ES modules from the static folder and print {name: result} for each `name: js expression`.

    `imports` maps a local name to a path under static/ (`{"R": "modules/qa/render.js"}`); the data is
    available to the expressions as `D`, after `prelude` (statements) has run."""
    assert NODE is not None and NODE_SKIP is None, NODE_SKIP
    lines = [f"import * as {name} from {json.dumps((STATIC / rel).as_uri())};" for name, rel in imports.items()]
    exprs = ",".join(f"{json.dumps(k)}: ({v})" for k, v in calls.items())
    lines.append("const D = JSON.parse(process.argv[1]);")
    lines.append(prelude)
    lines.append(f"process.stdout.write(JSON.stringify({{{exprs}}}));")
    out = subprocess.run(
        [NODE, "--input-type=module", "-e", "\n".join(lines), json.dumps(data)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)
