# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Validation of decision files. It runs on the raw data, because it must explain malformed files."""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ...errors import HttpError
from ...storage.doc import Doc
from ...storage.paths import resolve_repo_path
from ...text import Issue, about_text, is_date, issue, tldr_text
from .model import ABOUT_STATUSES, FILENAME_RE, ID_RE, PRIORITIES, REQUIRED, STATUSES, TLDR_MAX_LINES


def check_previews(root: Path, f: str, previews: Any, where: str) -> list[Issue]:
    out: list[Issue] = []
    if previews is None:
        return out
    if not isinstance(previews, list):
        return [issue(f, "error", f"{where} previews must be a list")]
    for p in previews:
        try:
            resolve_repo_path(root, str(p))
        except HttpError as e:
            level = "error"
            msg = f"{where} preview '{p}' {'does not exist' if e.code == 404 else 'is not allowed: ' + e.message}"
            if e.code == 403 and "type" in e.message and (root / str(p)).is_file():
                level, msg = "warning", f"{where} preview '{p}' exists but the desk cannot show this file type"
            out.append(issue(f, level, msg))
    return out


def check_decision(doc: Doc, f: str, root: Path, known: set[str], types: list[str]) -> list[Issue]:
    d = doc.data
    out: list[Issue] = []

    def err(msg: str) -> None:
        out.append(issue(f, "error", msg))

    def warn(msg: str) -> None:
        out.append(issue(f, "warning", msg))

    m = FILENAME_RE.match(doc.path.name)
    if not m:
        err("filename must look like D-0001-short-slug.md (lowercase slug)")
    for key in REQUIRED:
        if key not in d or d[key] is None or d[key] == "":
            err(f"missing required field '{key}'")
    did = d.get("id")
    if did is not None and not ID_RE.match(str(did)):
        err(f"id '{did}' must look like D-0001")
    elif did is not None and m and m.group(1) != str(did):
        err(f"id '{did}' does not match the filename ({m.group(1)})")
    for key in ("title", "question", "group"):
        if key in d and d[key] is not None and not isinstance(d[key], str):
            err(f"'{key}' must be text")
    allowed_sets: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("type", tuple(types)),
        ("status", STATUSES),
        ("priority", PRIORITIES),
    )
    for key, allowed in allowed_sets:
        if d.get(key) is not None and d.get(key) not in allowed:
            err(f"{key} '{d.get(key)}' is not one of: {', '.join(allowed)}")
    if "blocking" in d and d["blocking"] is not None and not isinstance(d["blocking"], bool):
        err("blocking must be true or false")
    created = d.get("created")
    if created is not None and not is_date(created):
        err(f"created '{created}' must be a date (YYYY-MM-DD)")

    opts = d.get("options")
    ids: list[str] = []
    if opts is not None and not isinstance(opts, list):
        err("options must be a list")
        opts = []
    for n, o in enumerate(opts or [], 1):
        if not isinstance(o, dict):
            err(f"option #{n} must be a mapping")
            continue
        oid = o.get("id")
        if oid is None or str(oid) == "":
            err(f"option #{n} has no id")
        else:
            oid = str(oid)
            if oid == "other":
                err("'other' is reserved; use a different option id")
            if oid in ids:
                err(f"option id '{oid}' is used twice")
            ids.append(oid)
        if not o.get("label"):
            err(f"option '{oid}' has no label")
        for key in ("pros", "cons", "previews"):
            if key in o and o[key] is not None and not isinstance(o[key], list):
                err(f"option '{oid}' {key} must be a list")
        out += check_previews(root, f, o.get("previews"), f"option '{oid}'")
    if isinstance(opts, list) and opts and not 2 <= len(opts) <= 4:
        warn(f"{len(opts)} options; aim for 2 to 4 real options")
    out += check_previews(root, f, d.get("previews"), "decision")

    for key in ("recommendation", "default"):
        v = d.get(key)
        if v is not None and str(v) not in ids:
            err(f"{key} '{v}' is not an option id ({', '.join(ids) or 'no options'})")

    status = d.get("status")
    answer = d.get("answer")
    if answer is not None and not isinstance(answer, dict):
        err("answer must be a mapping")
        answer = {}
    answer = answer or {}
    choice = answer.get("choice")
    if choice is not None and str(choice) != "other" and str(choice) not in ids:
        err(f"answer.choice '{choice}' is not an option id or 'other'")
    if status == "answered" and choice is None:
        err("status is answered but answer.choice is empty")
    if status == "answered" and not answer.get("answered_at"):
        warn("status is answered but answer.answered_at is empty")
    if str(choice) == "other" and not str(answer.get("comment") or "").strip():
        err("answer.choice is 'other' but answer.comment does not explain it")
    if status == "needs-info" and not str(answer.get("comment") or "").strip():
        err("status is needs-info but answer.comment (the human's question) is empty")

    res = d.get("resolution")
    if res is not None and not isinstance(res, dict):
        err("resolution must be a mapping")
        res = {}
    res = res or {}
    if status == "resolved" and not str(res.get("summary") or "").strip():
        err("status is resolved but resolution.summary is empty")
    if status == "resolved" and not res.get("resolved_at"):
        warn("status is resolved but resolution.resolved_at is empty")
    links = res.get("links")
    if links is not None and not isinstance(links, list):
        err("resolution.links must be a list")
    for link in links if isinstance(links, list) else []:
        s = str(link)
        if not re.match(r"^[a-z]+://", s) and not (root / s.split("#")[0]).exists():
            warn(f"resolution link '{s}' does not exist")

    fups = d.get("followups")
    if fups is not None and not isinstance(fups, list):
        err("followups must be a list")
    for fid in fups if isinstance(fups, list) else []:
        if not ID_RE.match(str(fid)):
            err(f"followup '{fid}' must look like D-0001")
        elif str(fid) not in known:
            warn(f"followup {fid} does not exist yet")

    tldr = d.get("tldr")
    if tldr is not None and not isinstance(tldr, str):
        warn("tldr should be a text block (tldr: | and 2 to 4 indented lines)")
    tldr_lines = [ln for ln in tldr_text(d).split("\n") if ln.strip()]
    if status in ("pending", "needs-info") and not tldr_lines:
        warn("no tldr: add 2 to 4 short lines (tldr: |) so the human gets it at a glance")
    if len(tldr_lines) > TLDR_MAX_LINES:
        warn(f"tldr has {len(tldr_lines)} lines; keep it to 2 to 4 short lines")

    about = d.get("about")
    if about is not None and not isinstance(about, str):
        err("about must be text (about: | and 1 to 2 short sentences)")
    elif status in ABOUT_STATUSES and not about_text(d):
        warn(
            "no about: add 1 to 2 plain sentences (about: |) on what the question is about "
            "and why it matters, so the human knows what they are deciding"
        )

    texts = [d.get("title"), d.get("question"), about_text(d), tldr_text(d)]
    texts += [o.get(k) for o in opts or [] if isinstance(o, dict) for k in ("label", "summary")]
    if status == "pending" and any("TODO" in str(t) for t in texts if t):
        warn("still has TODO placeholders")
    return out


def check_folder(
    docs: list[Doc],
    rel: Callable[[Path], str],
    folder: Path,
    folder_rel: str,
    open_limit: int,
) -> list[Issue]:
    """Rules across files: duplicate ids, stray file names, and how many decisions are open at once."""
    out: list[Issue] = []
    seen: dict[str, list[Doc]] = {}
    for d in docs:
        seen.setdefault(d.id, []).append(d)
    for did, group in seen.items():
        if len(group) > 1:
            names = ", ".join(rel(d.path) for d in group)
            for d in group:
                out.append(issue(rel(d.path), "error", f"duplicate id {did} (also in: {names})"))
    for p in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        if p.name != "README.md" and not p.name.startswith("D-"):
            out.append(issue(rel(p), "warning", "not a decision file name (D-0001-slug.md); ignored"))
    from .model import OPEN

    open_ = sorted(d.id for d in docs if d.data.get("status") in OPEN)
    if open_limit and len(open_) > open_limit:
        out.append(
            issue(
                folder_rel,
                "warning",
                f"{len(open_)} decisions are open for the human ({', '.join(open_)}: pending or needs-info, "
                f"parked or not); the open limit is {open_limit} (decisions.open_limit). Resolve, merge or "
                "withdraw some before asking more",
            )
        )
    return out
