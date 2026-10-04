# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""A QA run: `qa/runs/R-0001-slug.md`, a short list of manual test cases the human walks and marks."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ...storage.doc import Doc
from ...text import as_list, one_line, text_value

STATUSES = ("ready", "in-progress", "done", "processed")
RESULTS = ("pass", "fail", "blocked", "skip")  # or null: not marked yet
REQUIRED = ("id", "title", "status", "created", "cases")
CASE_REQUIRED = ("id", "title", "steps", "expected")
ID_RE = re.compile(r"^R-\d{4}$")
FILENAME_RE = re.compile(r"^(R-\d{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md$")
CASE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")


def run_outline(data: Any) -> dict[str, Any]:
    """What the summary needs from a run. Also compares ruamel and the line reader."""
    data = data if isinstance(data, dict) else {}
    cases = [c for c in as_list(data.get("cases")) if isinstance(c, dict)]
    return {
        **{k: one_line(data.get(k)) for k in ("id", "title", "slice", "status", "minutes")},
        "results": [one_line(c.get("result")) for c in cases],
    }


class Run:
    """A parsed run file and the JSON views the UI reads."""

    def __init__(self, doc: Doc, root: Path, rel: str, note_key: str) -> None:
        self.doc = doc
        self.root = root
        self.rel = rel
        self.note_key = note_key

    @property
    def data(self) -> dict[str, Any]:
        return self.doc.data

    def cases(self) -> list[dict[str, Any]]:
        return [c for c in as_list(self.data.get("cases")) if isinstance(c, dict)]

    def summary_json(self) -> dict[str, Any]:
        d = self.data
        cases = self.cases()
        counts = {r: 0 for r in RESULTS} | {"unmarked": 0}
        for c in cases:
            result = c.get("result")
            counts[result if isinstance(result, str) and result in RESULTS else "unmarked"] += 1
        minutes = d.get("minutes")
        return {
            "id": self.doc.id,
            "title": one_line(d.get("title")),
            "slice": one_line(d.get("slice")),
            "status": one_line(d.get("status")) or "ready",
            "created": d.get("created"),
            "minutes": minutes if isinstance(minutes, int) and not isinstance(minutes, bool) else None,
            "total": len(cases),
            "marked": len(cases) - counts["unmarked"],
            "counts": counts,
            "file": self.rel,
            "etag": self.doc.etag,
        }

    def detail_json(self, base_rel: str, issues: list[dict[str, str]] | None = None) -> dict[str, Any]:
        from ...storage.render import render_markdown

        d = self.data

        def lines(v: Any) -> list[str]:
            if isinstance(v, list):
                return [one_line(x) for x in v if one_line(x)]
            return [x for x in [one_line(v)] if x]

        cases = [
            {
                "id": one_line(c.get("id")),
                "title": one_line(c.get("title")),
                "why": one_line(c.get("why")),
                "where": one_line(c.get("where")),
                "steps": lines(c.get("steps")),
                "expected": lines(c.get("expected")),
                "result": c.get("result") if c.get("result") in RESULTS else None,
                "note": text_value(c.get("note")),
                "at": one_line(c.get("at")) or None,
                "ai": text_value(c.get("ai")),
            }
            for c in self.cases()
        ]
        return {
            **self.summary_json(),
            "asked_by": one_line(d.get("asked_by")),
            "setup": text_value(d.get("setup")),
            "overall_note": text_value(d.get(self.note_key)),
            "cases": cases,
            "body_html": render_markdown(self.doc.body, base_rel, self.root),
            "issues": issues or [],
        }
