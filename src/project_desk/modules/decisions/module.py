# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The decisions module: `decisions/D-0001-slug.md`, the human's answers, and the Decisions tab."""

from __future__ import annotations

import datetime as dt
from pathlib import Path
from typing import Any, ClassVar

from ...errors import DeskError, HttpError
from ...registry import Ask, Brief, Module, Request, Route, Validation
from ...storage.doc import Doc, find_doc, load_docs, parse_doc, write_atomic
from ...text import Issue
from .model import DEFAULT_TYPES, ID_RE, PRIORITIES, STATUSES, Decision, is_blocking_now, is_parked, pending_key


class DecisionsModule(Module):
    name = "decisions"
    label_key = "tab.decisions"
    hotkey = "d"  # `g d`; `g i` / `g w` / `g h` / `g a` also jump to its views
    tab_order = 20
    summary_order = 10
    ref_where = "decisions/"
    defaults: ClassVar[dict[str, Any]] = {"dir": "decisions", "types": list(DEFAULT_TYPES), "open_limit": 3}

    def __init__(self, desk: Any, settings: dict[str, Any]) -> None:
        super().__init__(desk, settings)
        self.folder = self.root / str(settings["dir"])
        self.types = [str(t) for t in settings["types"]]
        if not self.types:
            raise DeskError("[decisions] types must not be empty")
        self.open_limit = int(settings["open_limit"])
        self.ref_where = f"{str(settings['dir']).rstrip('/')}/"

    @classmethod
    def detect(cls, root: Path, settings: dict[str, Any]) -> bool:
        return True

    # ---------------------------------------------------------------- files

    def paths(self) -> list[Path]:
        """Every decision file. Subfolders (like material/) are not decisions."""
        if not self.folder.is_dir():
            return []
        return sorted(p for p in self.folder.glob("D-*.md") if p.is_file())

    def load_all(self) -> tuple[list[Doc], list[Issue]]:
        return load_docs(self.paths(), self.desk.rel)

    def find(self, did: str) -> Doc:
        doc = find_doc(self.paths(), did) if ID_RE.match(did) else None
        if doc is None:
            raise HttpError(404, f"no decision {did}")
        return doc

    def decision(self, doc: Doc) -> Decision:
        return Decision(doc, self.root, self.desk.rel(doc.path))

    # ---------------------------------------------------------------- validation

    def validate_docs(self) -> tuple[list[Doc], list[Issue]]:
        from .rules import check_decision, check_folder

        docs, issues = self.load_all()
        known = {d.id for d in docs}
        for d in docs:
            issues += check_decision(d, self.desk.rel(d.path), self.root, known, self.types)
        issues += check_folder(docs, self.desk.rel, self.folder, self.ref_where, self.open_limit)
        return docs, issues

    def validate(self) -> Validation:
        _, issues = self.validate_docs()
        return Validation(f"{len(self.paths())} decision file(s)", issues)

    def ids(self) -> set[str]:
        return {d.id for d in self.load_all()[0]}

    def describe(self, ids: set[str]) -> dict[str, dict[str, Any]]:
        """For other modules' views: each id's title and state, or exists: false."""
        by_id = {d.id: d for d in self.load_all()[0]}
        out: dict[str, dict[str, Any]] = {}
        for did in sorted(ids):
            doc = by_id.get(did)
            if doc is None:
                out[did] = {"id": did, "exists": False}
                continue
            s = self.decision(doc).summary_json()
            out[did] = {k: s[k] for k in ("id", "title", "status", "parked", "blocking_now")} | {"exists": True}
        return out

    # ---------------------------------------------------------------- views

    def list_json(self) -> dict[str, Any]:
        docs, issues = self.validate_docs()
        items = [self.decision(d).summary_json() for d in docs]
        counts = {s: 0 for s in STATUSES}
        for it in items:
            counts[it["status"]] = counts.get(it["status"], 0) + 1
        counts["blocking"] = sum(1 for it in items if it["blocking_now"])  # parked ones are not waiting
        counts["parked"] = sum(1 for it in items if it["parked"])
        errors = [i for i in issues if i["level"] == "error"]
        for it in items:
            it["issue_count"] = sum(1 for i in errors if i["file"] == it["file"])
        return {"root": self.root.name, "decisions": items, "counts": counts, "problems": errors}

    def detail_json(self, doc: Doc) -> dict[str, Any]:
        _, issues = self.validate_docs()
        rel = self.desk.rel(doc.path)
        mine = [i for i in issues if i["file"] == rel]
        return self.decision(doc).detail_json(self.desk.rel(doc.path.parent), mine)

    # ---------------------------------------------------------------- the answer

    def save_answer(self, did: str, payload: Any) -> Doc:
        from .answer import answer_frontmatter, check_answer

        if not isinstance(payload, dict):
            raise HttpError(400, "expected a JSON object")
        with self.desk.lock:
            doc = self.find(did)
            etag = payload.get("etag")
            if etag and etag != doc.etag:
                raise HttpError(409, "this decision changed on disk since you opened it; review it and save again")
            status, choice, comment = check_answer(doc, did, payload)
            new_fm = answer_frontmatter(doc.fm, doc.data, status, choice, comment, self.desk.timestamp())
            write_atomic(doc.path, doc.render(new_fm))
            return parse_doc(doc.path)

    def create(
        self,
        *,
        title: str,
        type_: str,
        group: str,
        priority: str = "medium",
        blocking: bool = False,
        asked_by: str = "ai",
        today: dt.date | None = None,
    ) -> Path:
        from .new import create_decision

        if type_ not in self.types:
            raise DeskError(f"type '{type_}' is not one of: {', '.join(self.types)} ([decisions] types)")
        if priority not in PRIORITIES:
            raise DeskError(f"priority '{priority}' is not one of: {', '.join(PRIORITIES)}")
        return create_decision(
            self.root,
            self.folder,
            title=title,
            type_=type_,
            group=group,
            priority=priority,
            blocking=blocking,
            asked_by=asked_by,
            today=today,
        )

    # ---------------------------------------------------------------- HTTP

    def routes(self) -> list[Route]:
        def listing(_: Request) -> Any:
            return self.list_json()

        def detail(r: Request) -> Any:
            return self.detail_json(self.find(r.match.group(1)))

        def answer(r: Request) -> Any:
            return self.detail_json(self.save_answer(r.match.group(1), r.payload))

        return [
            Route("GET", r"/api/decisions", listing),
            Route("GET", r"/api/decisions/(D-\d{4})", detail),
            Route("POST", r"/api/decisions/(D-\d{4})/answer", answer),
        ]

    def client_settings(self) -> dict[str, Any]:
        return {"dir": self.ref_where.rstrip("/"), "types": self.types, "open_limit": self.open_limit}

    # ---------------------------------------------------------------- summary and brief (fast path)

    def summary(self) -> str:
        from .fast import summary_text

        return summary_text(self.folder, self.desk.config.open_hint, self.desk.config.command)

    def brief(self, b: Brief) -> None:
        from .fast import quick_scan

        i = self.desk.i18n
        pending = [it for it in quick_scan(self.folder) if it["status"] == "pending"]
        for it in sorted(pending, key=pending_key):
            state = (
                i.t("brief.decision_blocking")
                if is_blocking_now(it)
                else i.t("brief.decision_parked")
                if is_parked(it)
                else ""
            )
            text = i.t("brief.decision", id=it["id"], title=it.get("title") or "?", state=state)
            b.asks.append(Ask(20, text, {str(it["id"])}))
