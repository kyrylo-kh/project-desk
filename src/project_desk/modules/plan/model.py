# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The plan: one YAML file (default `plan/roadmap.yaml`) with phases, items, `now` and the human's actions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...errors import DeskError
from ...text import as_list, one_line

STATUSES = ("done", "doing", "next", "later", "waiting")
REQUIRED = ("updated", "now", "phases")
NODE_REQUIRED = ("id", "title", "status")  # every phase and every item


def load_plan(path: Path, actions_key: str) -> dict[str, Any] | None:
    """The plan as plain data, or None when there is no plan file. Raises DeskError when unreadable."""
    from ...storage.yamlio import to_plain, yaml_load_file

    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as e:
        raise DeskError(f"cannot read the file ({e.strerror})") from None
    try:
        text = raw.decode("utf-8").lstrip("﻿")
    except UnicodeDecodeError:
        raise DeskError("file is not valid UTF-8") from None
    data = yaml_load_file(text, "plan")
    if not isinstance(data, dict):
        raise DeskError(f"the plan must be a YAML mapping (updated, now, {actions_key}, phases)")
    plain: dict[str, Any] = to_plain(data)
    return plain


def plan_outline(data: Any, actions_key: str) -> dict[str, Any]:
    """What the summary needs from a plan: ids, titles, statuses. Also compares ruamel and the line reader."""
    data = data if isinstance(data, dict) else {}

    def node(e: dict[str, Any]) -> dict[str, Any]:
        return {k: one_line(e.get(k)) for k in ("id", "title", "status")}

    return {
        "updated": one_line(data.get("updated")),
        "now": one_line(data.get("now")),
        "actions": [one_line(a.get("title")) for a in as_list(data.get(actions_key)) if isinstance(a, dict)],
        "phases": [
            node(p) | {"items": [node(it) for it in as_list(p.get("items")) if isinstance(it, dict)]}
            for p in as_list(data.get("phases"))
            if isinstance(p, dict)
        ],
    }


def node_ids(data: dict[str, Any]) -> set[str]:
    """Every phase and item id."""
    ids = set()
    for p in as_list(data.get("phases")):
        if isinstance(p, dict):
            ids.add(one_line(p.get("id")))
            ids |= {one_line(it.get("id")) for it in as_list(p.get("items")) if isinstance(it, dict)}
    return ids - {""}


def now_and_next(outline: dict[str, Any]) -> tuple[str, str]:
    """("ID — title" of the item being worked on, "; "-joined next items), with "—" for nothing."""
    items = [it for p in outline["phases"] for it in p["items"]]
    by_id = {it["id"]: it for it in items}
    now = outline["now"]
    upcoming = [f"{it['id']} — {it['title']}" for it in items if it["status"] == "next"]
    return (f"{now} — {by_id[now]['title']}" if now in by_id else (now or "—")), ("; ".join(upcoming) or "—")
