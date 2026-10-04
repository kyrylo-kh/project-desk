# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The QA part of `summary` and `brief`: run files read by the line reader, no YAML import."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...storage.quick import mini_load, read_frontmatter_text
from .model import RESULTS, run_outline


def quick_run_fields(fm: str) -> dict[str, Any]:
    return run_outline(mini_load(fm))


def quick_runs(folder: Path) -> list[dict[str, Any]]:
    """run_outline() of every readable R-*.md, plus counts."""
    if not folder.is_dir():
        return []
    runs = []
    for p in sorted(folder.glob("R-*.md")):
        try:
            fm = read_frontmatter_text(p)
            if fm is None:
                continue
            r = quick_run_fields(fm)
        except (OSError, UnicodeDecodeError, RecursionError):
            continue
        counts = {k: r["results"].count(k) for k in RESULTS}
        runs.append(
            {
                **r,
                "id": r["id"] or p.name[:6],
                "status": r["status"] or "ready",
                "counts": counts,
                "total": len(r["results"]),
                "marked": sum(counts.values()),
            }
        )
    return runs


def summary_text(runs: list[dict[str, Any]], open_hint: str, tab: str, readme: str) -> str:
    waiting = [r for r in runs if r["status"] in ("ready", "in-progress")]
    done = [r for r in runs if r["status"] == "done"]
    if not (waiting or done):
        return ""
    parts = [f"{len(waiting)} waiting for the human"] if waiting else []
    parts += [f"{len(done)} done awaiting AI processing"] if done else []
    lines = ["Test Desk: " + ", ".join(parts) + (f" — run `{open_hint}` (tab {tab})" if waiting else "")]
    for r in waiting:
        minutes = f", ~{r['minutes']} min" if r["minutes"] else ""
        lines.append(
            f"  {r['id']}  {r['title'] or '(no title)'} — {r['status']}, {r['marked']}/{r['total']} marked{minutes}"
        )
    for r in done:
        bad = [f"{r['counts'][k]} {k}" for k in ("fail", "blocked") if r["counts"][k]]
        lines.append(f"  {r['id']}  {r['title'] or '(no title)'} — done: {', '.join(bad) or 'nothing failed'}")
    if done:
        lines.append(
            f"AI: process done runs per {readme} (write `ai` on every fail and blocked case, "
            "then set status: processed)."
        )
    return "\n".join(lines)
