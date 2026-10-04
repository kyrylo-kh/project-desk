# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Validation of QA run files."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from ...storage.doc import Doc
from ...text import Issue, is_date, issue, one_line, text_value
from .model import CASE_ID_RE, CASE_REQUIRED, FILENAME_RE, ID_RE, REQUIRED, RESULTS, STATUSES, run_outline


def check_run(
    doc: Doc,
    f: str,
    *,
    plan_ids: set[str] | None,
    plan_file: str,
    max_cases: int,
    note_key: str,
    readme: str,
    quick_outline: Callable[[str], dict[str, Any]],
) -> list[Issue]:
    d = doc.data
    out: list[Issue] = []

    def err(msg: str) -> None:
        out.append(issue(f, "error", msg))

    def warn(msg: str) -> None:
        out.append(issue(f, "warning", msg))

    m = FILENAME_RE.match(doc.path.name)
    if not m:
        err("filename must look like R-0001-short-slug.md (lowercase slug)")
    for key in REQUIRED:
        if key not in d or d[key] is None or d[key] == "":
            err(f"missing required field '{key}'")
    rid = d.get("id")
    if rid is not None and not ID_RE.match(str(rid)):
        err(f"id '{rid}' must look like R-0001")
    elif rid is not None and m and m.group(1) != str(rid):
        err(f"id '{rid}' does not match the filename ({m.group(1)})")
    for key in ("title", "slice", "setup", note_key):
        if d.get(key) is not None and not isinstance(d[key], str):
            err(f"'{key}' must be text")
    status = d.get("status")
    if status is not None and status not in STATUSES:
        err(f"status '{status}' is not one of: {', '.join(STATUSES)}")
    created = d.get("created")
    if created is not None and not is_date(created):
        err(f"created '{created}' must be a date (YYYY-MM-DD)")
    minutes = d.get("minutes")
    if minutes is not None and (isinstance(minutes, bool) or not isinstance(minutes, int) or minutes <= 0):
        err(f"minutes '{minutes}' must be a whole number of minutes")
    slice_ = one_line(d.get("slice"))
    if slice_ and plan_ids is not None and slice_ not in plan_ids:
        err(f"slice '{slice_}' is not an id in {plan_file}")

    cases = d.get("cases")
    if cases is not None and not isinstance(cases, list):
        err("cases must be a list")
        cases = []
    elif isinstance(cases, list) and not cases:
        err("cases is empty: a run needs at least one case")
    cases = cases or []
    ids: list[str] = []
    for n, c in enumerate(cases, 1):
        if not isinstance(c, dict):
            err(f"case #{n} must be a mapping")
            continue
        cid = one_line(c.get("id"))
        where = f"case {cid}" if cid else f"case #{n}"
        for key in CASE_REQUIRED:
            if c.get(key) in (None, "", []):
                err(f"{where} has no {key}")
        if cid:
            if not CASE_ID_RE.match(cid):
                err(f"{where}: id must be letters, digits, '-' or '_' (like T01)")
            if cid in ids:
                err(f"case id {cid} is used twice")
            ids.append(cid)
        for key in ("steps", "expected"):
            if c.get(key) not in (None, "") and not isinstance(c.get(key), list):
                err(f"{where}: {key} must be a list")
        result = c.get("result")
        if result is not None and result not in RESULTS:
            err(f"{where}: result '{result}' is not one of: null, {', '.join(RESULTS)}")
    if max_cases and len(cases) > max_cases:
        warn(
            f"{len(cases)} cases; keep a run to at most {max_cases} (about 30 minutes) and split the rest "
            "into another run"
        )
    good = [c for c in cases if isinstance(c, dict)]
    if status == "done":
        unmarked = [one_line(c.get("id")) or "?" for c in good if c.get("result") is None]
        if unmarked:
            warn(f"run is done but {', '.join(unmarked)} {'has' if len(unmarked) == 1 else 'have'} no result")
    if status == "processed":
        todo = [
            f"{one_line(c.get('id')) or '?'} ({c.get('result')})"
            for c in good
            if c.get("result") in ("fail", "blocked") and not text_value(c.get("ai"))
        ]
        if todo:
            warn(
                f"run is processed but {', '.join(todo)} {'has' if len(todo) == 1 else 'have'} no ai: "
                "write what was done about each fail and blocked case"
            )
    try:
        if quick_outline(doc.fm) != run_outline(d):
            warn(
                "the summary's line scanner reads this file differently from YAML; keep one key per line in "
                f"block style, as in {readme}"
            )
    except Exception:  # the cross-check must never break validate
        pass
    return out


def check_folder(docs: list[Doc], rel: Callable[[Path], str], folder: Path) -> list[Issue]:
    out: list[Issue] = []
    seen: dict[str, list[Doc]] = {}
    for d in docs:
        seen.setdefault(d.id, []).append(d)
    for rid, group in seen.items():
        if len(group) > 1:
            names = ", ".join(rel(d.path) for d in group)
            for d in group:
                out.append(issue(rel(d.path), "error", f"duplicate run id {rid} (also in: {names})"))
    for p in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        if not p.name.startswith("R-"):
            out.append(issue(rel(p), "warning", "not a run file name (R-0001-slug.md); ignored"))
    return out
