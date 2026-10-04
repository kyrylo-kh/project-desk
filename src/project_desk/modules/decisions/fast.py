# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The decisions part of `summary` and `brief`: a line scan, no YAML import (it runs on every session start)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...storage.lines import TRUE_WORDS
from ...storage.quick import quick_fields, read_frontmatter_text
from .model import default_id, is_blocking_now, is_parked, pending_key

QUICK_KEYS = ("id", "title", "status", "priority", "blocking", "default", "about")


def quick_scan(folder: Path) -> list[dict[str, Any]]:
    """Every readable decision's QUICK_KEYS."""
    if not folder.is_dir():
        return []
    items = []
    for p in sorted(folder.glob("D-*.md")):
        try:
            fm = read_frontmatter_text(p)
        except (OSError, UnicodeDecodeError):
            continue
        if fm is None:
            continue
        f: dict[str, Any] = dict(quick_fields(fm, QUICK_KEYS))
        blocking = str(f.get("blocking") or "").lower() in TRUE_WORDS
        items.append(
            {**f, "id": f.get("id") or p.name[:6], "blocking": blocking, "status": f.get("status") or "pending"}
        )
    return items


def quick_counts(folder: Path) -> dict[str, int]:
    """Status counts. `blocking` counts only decisions where work waits; parked ones are counted apart."""
    counts = {"pending": 0, "blocking": 0, "parked": 0, "answered": 0, "needs-info": 0}
    for it in quick_scan(folder):
        if it["status"] in counts:
            counts[it["status"]] += 1
        counts["parked"] += is_parked(it)
        counts["blocking"] += is_blocking_now(it)
    return counts


def summary_text(folder: Path, open_hint: str, command: str) -> str:
    items = quick_scan(folder)
    pending = [it for it in items if it["status"] == "pending"]
    answered = sum(1 for it in items if it["status"] == "answered")
    needs_info = sum(1 for it in items if it["status"] == "needs-info")
    if not (pending or answered or needs_info):
        return ""
    blocking = sum(1 for it in pending if is_blocking_now(it))
    parked = sum(1 for it in pending if is_parked(it))
    parts = []
    if pending:
        extra = [f"{blocking} blocking"] if blocking else []
        extra += [f"{parked} parked"] if parked else []
        parts.append(f"{len(pending)} pending" + (f" ({', '.join(extra)})" if extra else ""))
    if answered:
        parts.append(f"{answered} answered awaiting AI processing")
    if needs_info:
        parts.append(f"{needs_info} needs-info (the human asked a question)")
    lines = ["Decision Desk: " + ", ".join(parts) + (f" — run `{open_hint}`" if pending else "")]
    for it in sorted(pending, key=pending_key):
        state = "blocking" if is_blocking_now(it) else f"parked (default {default_id(it)})" if is_parked(it) else ""
        lines.append(f"  {it['id']}  {it.get('title') or '(no title)'}" + (f" — {state}" if state else ""))
        if it.get("about"):
            lines.append(f"      about: {' '.join(str(it['about']).split())}")
    if parked:
        lines.append("Parked = the AI works with the default until the human answers; a later answer can mean rework.")
    if answered or needs_info:
        lines.append(f"AI: process these with the decision-desk skill (`{command} list --status answered,needs-info`).")
    return "\n".join(lines)
