# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Validation of the plan file."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ...errors import HttpError
from ...storage.paths import WEB_LINK_RE, repo_path_exists, resolve_repo_path
from ...text import Issue, as_list, is_date, issue, one_line
from .model import NODE_REQUIRED, REQUIRED, STATUSES

DECISION_ID_PATTERN = r"^D-\d{4}$"


def ref_issues(
    f: str, where: str, entry: dict[str, Any], root: Path, known: set[str] | None, decisions_where: str
) -> list[Issue]:
    """`decisions` must name existing decisions; `links` must be repo paths the desk can open (or http(s))."""
    import re

    out: list[Issue] = []
    decisions = entry.get("decisions")
    if decisions is not None and not isinstance(decisions, list):
        out.append(issue(f, "error", f"{where}: decisions must be a list, like [D-0001]"))
    for did in as_list(decisions):
        s = str(did)
        if not re.match(DECISION_ID_PATTERN, s):
            out.append(issue(f, "error", f"{where}: decision '{s}' must look like D-0001"))
        elif known is not None and s not in known:
            out.append(issue(f, "error", f"{where}: decision {s} does not exist in {decisions_where}"))
    links = entry.get("links")
    if links is not None and not isinstance(links, list):
        out.append(issue(f, "error", f"{where}: links must be a list of repo paths"))
    for link in as_list(links):
        s = str(link)
        if WEB_LINK_RE.match(s):
            continue
        try:
            resolve_repo_path(root, s)  # the same gate as /preview/
        except HttpError as e:
            if e.code == 404 or "type" in e.message:
                if repo_path_exists(root, s):  # a folder, or a file type the desk does not serve
                    out.append(issue(f, "warning", f"{where}: link '{s}' exists but the desk cannot open it"))
                else:
                    out.append(issue(f, "error", f"{where}: link '{s}' does not exist"))
            else:
                out.append(issue(f, "error", f"{where}: link '{s}' is not allowed: {e.message}"))
    return out


def plan_issues(
    data: dict[str, Any], f: str, root: Path, known: set[str] | None, decisions_where: str, actions_key: str
) -> list[Issue]:
    out: list[Issue] = []

    def err(msg: str) -> None:
        out.append(issue(f, "error", msg))

    def warn(msg: str) -> None:
        out.append(issue(f, "warning", msg))

    def refs(where: str, entry: dict[str, Any]) -> None:
        out.extend(ref_issues(f, where, entry, root, known, decisions_where))

    for key in REQUIRED:
        if key not in data or data[key] is None or data[key] == "":
            err(f"missing required key '{key}'")
    updated = data.get("updated")
    if updated not in (None, "") and not is_date(updated):
        err(f"updated '{updated}' must be a date (YYYY-MM-DD)")

    actions = data.get(actions_key)
    if actions is not None and not isinstance(actions, list):
        err(f"{actions_key} must be a list")
    for n, a in enumerate(as_list(actions), 1):
        if not isinstance(a, dict):
            err(f"action #{n} must be a mapping")
            continue
        where = f"action #{n}"
        if not one_line(a.get("title")):
            err(f"{where} has no title")
        refs(where, a)

    seen: dict[str, str] = {}
    items: dict[str, dict[str, Any]] = {}
    phase_ids: set[str] = set()

    def node(entry: dict[str, Any], where: str, place: str) -> str:
        for key in NODE_REQUIRED:
            if not one_line(entry.get(key)):
                err(f"{where} has no {key}")
        nid = one_line(entry.get("id"))
        if nid in seen:
            err(f"duplicate id {nid} (in {seen[nid]} and in {place})")
        elif nid:
            seen[nid] = place
        status = entry.get("status")
        if status not in (None, "") and status not in STATUSES:
            err(f"{where}: status '{status}' is not one of: {', '.join(STATUSES)}")
        if not one_line(entry.get("about")):
            warn(f"{where} has no about: add one plain line so the human knows what it is")
        refs(where, entry)
        return nid

    phases = data.get("phases")
    if phases is not None and not isinstance(phases, list):
        err("phases must be a list")
    for n, p in enumerate(as_list(phases), 1):
        if not isinstance(p, dict):
            err(f"phase #{n} must be a mapping")
            continue
        pid = one_line(p.get("id"))
        pwhere = f"phase {pid}" if pid else f"phase #{n}"
        if node(p, pwhere, pwhere):
            phase_ids.add(pid)
        kids = p.get("items")
        if kids is not None and not isinstance(kids, list):
            err(f"{pwhere}: items must be a list")
        mine: list[tuple[str, dict[str, Any]]] = []
        for m, it in enumerate(as_list(kids), 1):
            if not isinstance(it, dict):
                err(f"{pwhere}: item #{m} must be a mapping")
                continue
            iid = one_line(it.get("id"))
            iwhere = f"item {iid}" if iid else f"{pwhere} item #{m}"
            node(it, iwhere, f"the items of {pwhere}")
            if it.get("status") == "waiting" and not one_line(it.get("needs")):
                warn(f"{iwhere} is waiting but has no needs: say what it waits for")
            if iid:
                items.setdefault(iid, it)
            mine.append((iid or f"#{m}", it))
        status = p.get("status")
        if status == "done":
            open_ = [i for i, it in mine if it.get("status") not in ("done", "waiting")]
            if open_:
                verb = "is" if len(open_) == 1 else "are"
                warn(f"{pwhere} is done but {', '.join(open_)} {verb} not done or waiting")
        elif status in ("next", "later"):
            started = [i for i, it in mine if it.get("status") == "doing"]
            if started:
                verb = "is" if len(started) == 1 else "are"
                warn(f"{pwhere} is {status} but {', '.join(started)} {verb} doing; mark the phase doing")

    now = one_line(data.get("now"))
    if now:
        if now in items:
            status = items[now].get("status")
            if status != "doing":
                err(f"now '{now}' has status {status}; now must point at the item whose status is doing")
        elif now in phase_ids:
            err(f"now '{now}' is a phase; point it at the item being worked on")
        else:
            err(f"now '{now}' is not the id of any item in phases")
    return out
