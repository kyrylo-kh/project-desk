# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The plan module: a read-only view of the roadmap file. The AI edits the file; the desk shows and checks it."""

from __future__ import annotations

from pathlib import Path
from typing import Any, ClassVar

from ...errors import DeskError
from ...registry import Ask, Brief, Module, Request, Route, Validation
from ...storage.paths import link_json
from ...text import Issue, as_list, issue, one_line
from .model import load_plan, node_ids, now_and_next, plan_outline


class PlanModule(Module):
    name = "plan"
    label_key = "tab.plan"
    hotkey = "p"
    tab_order = 10
    summary_order = 30
    defaults: ClassVar[dict[str, Any]] = {"file": "plan/roadmap.yaml", "actions_key": "actions"}

    def __init__(self, desk: Any, settings: dict[str, Any]) -> None:
        super().__init__(desk, settings)
        self.file = str(settings["file"])
        self.path = self.root / self.file
        self.actions_key = str(settings["actions_key"])
        self.ref_where = self.file

    @classmethod
    def detect(cls, root: Path, settings: dict[str, Any]) -> bool:
        return (root / str(settings["file"])).is_file()

    def load(self) -> dict[str, Any] | None:
        return load_plan(self.path, self.actions_key)

    def outline(self, data: Any) -> dict[str, Any]:
        return plan_outline(data, self.actions_key)

    # ---------------------------------------------------------------- cross-references

    def _decisions(self) -> Any:
        return self.desk.get("decisions")

    def ids(self) -> set[str] | None:
        """Every phase and item id; None when there is no readable plan."""
        try:
            data = self.load()
        except DeskError:
            return None
        return None if data is None else node_ids(data)

    # ---------------------------------------------------------------- validation

    def issues(self, data: dict[str, Any], known: set[str] | None) -> list[Issue]:
        from .rules import plan_issues

        dec = self._decisions()
        return plan_issues(data, self.file, self.root, known, dec.ref_where if dec else "", self.actions_key)

    def validate(self) -> Validation:
        label = self.file if self.path.is_file() else ""
        try:
            data = self.load()
        except DeskError as e:
            return Validation(label, [issue(self.file, "error", str(e))])
        if data is None:
            return Validation(label, [])
        dec = self._decisions()
        out = self.issues(data, dec.ids() if dec else None)
        try:
            if self.quick_outline() != self.outline(data):
                out.append(
                    issue(
                        self.file,
                        "warning",
                        "the summary's line scanner reads this file differently from YAML; keep one key per line "
                        "in block style, as the rest of the file",
                    )
                )
        except Exception:  # the cross-check must never break validate
            pass
        return Validation(label, out)

    # ---------------------------------------------------------------- the view

    def plan_json(self) -> dict[str, Any]:
        """GET /api/plan: the plan as plain data, re-read on every call, plus the state of every decision it
        mentions. `exists: false` when there is no plan file; `error` when it cannot be read."""
        try:
            data = self.load()
        except DeskError as e:
            return {"file": self.file, "exists": True, "error": str(e)}
        if data is None:
            return {"file": self.file, "exists": False}

        def refs(entry: dict[str, Any]) -> dict[str, Any]:
            return {
                "decisions": [str(x) for x in as_list(entry.get("decisions"))],
                "links": [link_json(self.root, x) for x in as_list(entry.get("links"))],
            }

        def node(entry: dict[str, Any]) -> dict[str, Any]:
            return {key: one_line(entry.get(key)) for key in ("id", "title", "status", "about", "needs")} | refs(entry)

        actions = [
            {key: one_line(a.get(key)) for key in ("title", "about", "note", "when")} | refs(a)
            for a in as_list(data.get(self.actions_key))
            if isinstance(a, dict)
        ]
        phases = [
            node(p) | {"items": [node(it) for it in as_list(p.get("items")) if isinstance(it, dict)]}
            for p in as_list(data.get("phases"))
            if isinstance(p, dict)
        ]
        mentioned = {
            did for e in [*actions, *phases, *(i for p in phases for i in p["items"])] for did in e["decisions"]
        }
        dec = self._decisions()
        decisions = dec.describe(mentioned) if dec else {}
        issues = self.issues(data, dec.ids() if dec else None)
        return {
            "file": self.file,
            "exists": True,
            "updated": one_line(data.get("updated")),
            "now": one_line(data.get("now")),
            "actions": actions,
            "phases": phases,
            "decisions": decisions,
            "problems": [i for i in issues if i["level"] == "error"],
        }

    def routes(self) -> list[Route]:
        def view(_: Request) -> Any:
            return self.plan_json()

        return [Route("GET", r"/api/plan", view)]

    def client_settings(self) -> dict[str, Any]:
        return {"file": self.file, "decisions": self._decisions() is not None}

    # ---------------------------------------------------------------- summary and brief (fast path)

    def quick_data(self) -> Any:
        """The plan read by the line reader, without a YAML import; None when there is no plan file."""
        from ...storage.quick import mini_load

        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
        return mini_load(text)

    def quick_outline(self) -> dict[str, Any] | None:
        data = self.quick_data()
        return None if data is None else self.outline(data)

    def summary(self) -> str:
        plan = self.quick_outline()
        if not plan:
            return ""
        now, upcoming = now_and_next(plan)
        updated = f", updated {plan['updated']}" if plan["updated"] else ""
        return "\n".join(
            [
                f"Plan ({self.file}{updated}):",
                f"  Now: {now}",
                f"  Next: {upcoming}",
                f"  Asks for the human: {len(plan['actions'])}",
            ]
        )

    def brief(self, b: Brief) -> None:
        i = self.desk.i18n
        try:
            data = self.quick_data()
        except (OSError, UnicodeDecodeError, RecursionError):
            b.head.append(i.t("brief.plan_unreadable", file=self.file, command=self.desk.config.command))
            return
        if data is None:
            return
        now, upcoming = now_and_next(self.outline(data))
        b.head.append(i.t("brief.now", now=now))
        b.head.append(i.t("brief.next", next=upcoming))
        if isinstance(data, dict):
            for a in as_list(data.get(self.actions_key)):
                title = one_line(a.get("title")) if isinstance(a, dict) else ""
                if title:
                    when = one_line(a.get("when"))
                    b.asks.append(Ask(30, title + (f" ({when})" if when else ""), dedupe=True))
