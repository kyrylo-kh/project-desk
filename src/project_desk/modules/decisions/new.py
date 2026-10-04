# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""`desk new`: scaffold the next decision file from the template in the decisions README."""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import tempfile
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ...errors import DeskError, EditError
from ...storage.doc import split_frontmatter, write_atomic
from ...storage.edits import replace_children, set_child, set_top, set_top_literal
from ...storage.yamlio import to_plain, yaml_load
from ...text import about_text, tldr_text
from .model import NUMBER_RE

TLDR_TODO = "TODO: 2 to 4 short lines: the ask, the AI's pick and why, what it blocks or the default."
ABOUT_TODO = (
    "TODO: 1 to 2 short plain sentences: what the question is about and why it matters "
    "(not the recommendation; explain any term a non-expert would not know)."
)
QUESTION_TODO = "TODO: the one question the human answers?"

BUILTIN_TEMPLATE = """---
id: D-0000
title: Title
group: general
type: product
status: pending
priority: medium
blocking: false
created: 2026-01-01
asked_by: ai
question: Question?
about: |
  What the question is about and why it matters.
tldr: |
  Short version.
recommendation: null
default: null
options:
  - id: a
    label: A
    summary: ""
    pros: []
    cons: []
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
Why this decision exists, in 3 to 8 lines. What we know, and the evidence.

## What changes with each option
Concrete consequences, costs and what gets built.

## After you decide
What the AI will do next with the answer.
"""


def readme_template(folder: Path) -> str | None:
    """The first ```markdown block of the decisions README: the project's own template."""
    try:
        text = (folder / "README.md").read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(r"^```markdown\n(.*?)^```", text, re.S | re.M)
    return m.group(1) if m else None


def slugify(title: str) -> str:
    s = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")
    if len(s) > 48:
        s = s[:48].rsplit("-", 1)[0] or s[:48]
    return s or "decision"


def scaffold(
    template: str,
    *,
    did: str,
    title: str,
    type_: str,
    group: str,
    priority: str,
    blocking: bool,
    asked_by: str,
    created: dt.date,
) -> str:
    head, fm, sep, body = split_frontmatter(template)
    lines = fm.split("\n")
    set_top(lines, "id", did, "ident")
    set_top(lines, "title", title)
    set_top(lines, "group", group)
    set_top(lines, "type", type_, "ident")
    set_top(lines, "status", "pending", "ident")
    set_top(lines, "priority", priority, "ident")
    set_top(lines, "blocking", blocking)
    set_top(lines, "created", created)
    set_top(lines, "asked_by", asked_by)
    set_top(lines, "question", QUESTION_TODO, "text")
    # Order in the file: question, about, tldr. A template missing either key gets it in that place.
    set_top_literal(lines, "about", [ABOUT_TODO], after="question")
    set_top_literal(lines, "tldr", [TLDR_TODO], after="about")
    set_top(lines, "recommendation", None)
    set_top(lines, "default", None)
    options = []
    for oid in ("a", "b"):
        options += [
            f"  - id: {oid}",
            f'    label: "TODO: option {oid}"',
            '    summary: "TODO: one line on what this option means."',
            "    pros: []",
            "    cons: []",
            "    previews: []",
        ]
    replace_children(lines, "options", options)
    set_child(lines, "answer", "choice", None)
    set_child(lines, "answer", "comment", "", "text")
    set_child(lines, "answer", "answered_at", None)
    set_child(lines, "resolution", "summary", "", "text")
    set_child(lines, "resolution", "resolved_at", None)
    set_child(lines, "resolution", "links", [])
    set_top(lines, "followups", [])
    new_fm = "\n".join(lines)
    data = to_plain(yaml_load(new_fm))
    if (
        data.get("id") != did
        or data.get("title") != title
        or len(data.get("options") or []) != 2
        or tldr_text(data) != TLDR_TODO
        or about_text(data) != ABOUT_TODO
    ):
        raise EditError("template did not produce the expected fields")
    return head + new_fm + sep + body


@contextmanager
def id_lock(root: Path) -> Iterator[None]:
    """Serialise `new` across processes so two agents never pick the same id."""
    try:
        import fcntl
    except ImportError:  # Windows: best effort; the exclusive write still refuses a clash
        yield
        return
    key = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    with open(Path(tempfile.gettempdir()) / f"project-desk-{key}.lock", "a") as fh:  # "a": never truncate
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def create_decision(
    root: Path,
    folder: Path,
    *,
    title: str,
    type_: str,
    group: str,
    priority: str = "medium",
    blocking: bool = False,
    asked_by: str = "ai",
    today: dt.date | None = None,
) -> Path:
    if not title.strip():
        raise DeskError("--title must not be empty")
    folder.mkdir(parents=True, exist_ok=True)
    with id_lock(root):
        numbers = [int(m.group(1)) for p in folder.iterdir() if (m := NUMBER_RE.match(p.name))]
        did = f"D-{max(numbers, default=0) + 1:04d}"
        path = folder / f"{did}-{slugify(title)}.md"
        created = today or dt.date.today()

        def build(template: str) -> str:
            return scaffold(
                template,
                did=did,
                title=title.strip(),
                type_=type_,
                group=group,
                priority=priority,
                blocking=blocking,
                asked_by=asked_by,
                created=created,
            )

        tmpl = readme_template(folder)
        try:
            text = build(tmpl) if tmpl else build(BUILTIN_TEMPLATE)
        except (EditError, DeskError):
            text = build(BUILTIN_TEMPLATE)
        write_atomic(path, text.encode("utf-8"), exclusive=True)
    return path
