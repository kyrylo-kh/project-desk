# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""A decision request: the contract of `decisions/D-0001-slug.md` (see the decisions README template)."""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from ...storage.doc import Doc
from ...storage.paths import preview_json
from ...text import about_text, tldr_text

DEFAULT_TYPES = ["product", "design", "architecture", "data", "process", "brand"]
STATUSES = ("pending", "answered", "needs-info", "resolved", "withdrawn")
PRIORITIES = ("high", "medium", "low")
REQUIRED = ("id", "title", "group", "type", "status", "priority", "blocking", "created", "question", "options")
OPEN = ("pending", "needs-info")  # open for the human, parked or not
ABOUT_STATUSES = ("pending", "needs-info", "answered")  # `validate` warns when these have no `about`
TLDR_MAX_LINES = 5  # `validate` warns above this; the contract asks for 2 to 4 short lines

ID_RE = re.compile(r"^D-\d{4}$")
FILENAME_RE = re.compile(r"^(D-\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
NUMBER_RE = re.compile(r"^D-(\d{4})")


def default_id(data: dict[str, Any]) -> str | None:
    v = data.get("default")
    return None if v is None or str(v) == "" else str(v)


def is_parked(data: dict[str, Any]) -> bool:
    """Parked: still pending, but the AI works with `default` until the human answers."""
    return (data.get("status") or "pending") == "pending" and default_id(data) is not None


def is_blocking_now(data: dict[str, Any]) -> bool:
    """Work is actually waiting: pending, `blocking: true` and no default to work with meanwhile."""
    return (data.get("status") or "pending") == "pending" and bool(data.get("blocking")) and not is_parked(data)


def option_ids(data: dict[str, Any]) -> list[str]:
    opts = data.get("options")
    if not isinstance(opts, list):
        return []
    return [str(o.get("id")) for o in opts if isinstance(o, dict) and o.get("id") is not None]


def pending_key(it: dict[str, Any]) -> tuple[bool, int, str]:
    """Sort key for pending decisions: work-blocking first, then priority, then id."""
    rank = {p: n for n, p in enumerate(PRIORITIES)}
    return (not is_blocking_now(it), rank.get(str(it.get("priority")), 3), str(it["id"]))


class Decision:
    """A parsed decision file and the JSON views the UI reads."""

    def __init__(self, doc: Doc, root: Path, rel: str) -> None:
        self.doc = doc
        self.root = root
        self.rel = rel

    @property
    def id(self) -> str:
        return self.doc.id

    @property
    def data(self) -> dict[str, Any]:
        return self.doc.data

    @property
    def status(self) -> str:
        return str(self.data.get("status") or "pending")

    def summary_json(self) -> dict[str, Any]:
        d = self.data
        answer: dict[str, Any] = d["answer"] if isinstance(d.get("answer"), dict) else {}
        res: dict[str, Any] = d["resolution"] if isinstance(d.get("resolution"), dict) else {}
        return {
            "id": self.id,
            "title": d.get("title") or "",
            "question": d.get("question") or "",
            "about": about_text(d),
            "tldr": tldr_text(d),
            "group": d.get("group") or "",
            "type": d.get("type") or "",
            "status": self.status,
            "priority": d.get("priority") or "medium",
            "blocking": bool(d.get("blocking")),
            "blocking_now": is_blocking_now(d),
            "default": default_id(d),
            "parked": is_parked(d),
            "created": d.get("created"),
            "choice": answer.get("choice"),
            "answered_at": answer.get("answered_at"),
            "resolved_at": res.get("resolved_at"),
            "file": self.rel,
            "etag": self.doc.etag,
        }

    def detail_json(self, base_rel: str, issues: list[dict[str, str]] | None = None) -> dict[str, Any]:
        from ...storage.render import render_markdown

        d = copy.deepcopy(self.data)
        for o in d.get("options") or []:
            if isinstance(o, dict):
                o["id"] = str(o.get("id"))
                o["previews"] = [preview_json(self.root, p) for p in o.get("previews") or []]
        previews = d.get("previews")
        d["previews"] = [preview_json(self.root, p) for p in previews] if isinstance(previews, list) else []
        return {
            **self.summary_json(),
            "data": d,
            "body_html": render_markdown(self.doc.body, base_rel, self.root),
            "issues": issues or [],
        }
