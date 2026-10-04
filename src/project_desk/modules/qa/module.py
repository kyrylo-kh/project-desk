# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The QA module: manual test runs the AI writes and the human walks and marks, one tab."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any, ClassVar

from ...errors import HttpError
from ...registry import Ask, Brief, Module, Request, Route, Validation
from ...storage.doc import Doc, find_doc, load_docs, parse_doc, write_atomic
from ...text import Issue, as_list, clean_text, one_line
from .model import ID_RE, RESULTS, STATUSES, Run


class QAModule(Module):
    name = "qa"
    label_key = "tab.qa"
    hotkey = "t"
    tab_order = 30
    summary_order = 20
    defaults: ClassVar[dict[str, Any]] = {"dir": "qa/runs", "max_cases": 15, "note_key": "overall_note"}

    def __init__(self, desk: Any, settings: dict[str, Any]) -> None:
        super().__init__(desk, settings)
        self.dir = str(settings["dir"]).rstrip("/")
        self.folder = self.root / self.dir
        self.max_cases = int(settings["max_cases"])
        self.note_key = str(settings["note_key"])
        self.ref_where = f"{self.dir}/"
        parent = PurePosixPath(self.dir).parent
        self.readme = f"{parent}/README.md" if str(parent) != "." else f"{self.dir}/README.md"

    @classmethod
    def detect(cls, root: Path, settings: dict[str, Any]) -> bool:
        return (root / str(settings["dir"])).is_dir()

    # ---------------------------------------------------------------- files

    def paths(self) -> list[Path]:
        if not self.folder.is_dir():
            return []
        return sorted(p for p in self.folder.glob("R-*.md") if p.is_file())

    def load_all(self) -> tuple[list[Doc], list[Issue]]:
        return load_docs(self.paths(), self.desk.rel)

    def find(self, rid: str) -> Doc:
        doc = find_doc(self.paths(), rid) if ID_RE.match(rid) else None
        if doc is None:
            raise HttpError(404, f"no run {rid}")
        return doc

    def run(self, doc: Doc) -> Run:
        return Run(doc, self.root, self.desk.rel(doc.path), self.note_key)

    def ids(self) -> set[str]:
        return {d.id for d in self.load_all()[0]}

    # ---------------------------------------------------------------- validation

    def _plan(self) -> Any:
        return self.desk.get("plan")

    def validate_docs(self) -> tuple[list[Doc], list[Issue]]:
        from .fast import quick_run_fields
        from .rules import check_folder, check_run

        docs, issues = self.load_all()
        plan = self._plan()
        plan_ids = plan.ids() if plan else None
        for d in docs:
            issues += check_run(
                d,
                self.desk.rel(d.path),
                plan_ids=plan_ids,
                plan_file=plan.file if plan else "",
                max_cases=self.max_cases,
                note_key=self.note_key,
                readme=self.readme,
                quick_outline=quick_run_fields,
            )
        issues += check_folder(docs, self.desk.rel, self.folder)
        return docs, issues

    def validate(self) -> Validation:
        _, issues = self.validate_docs()
        n = len(self.paths())
        return Validation(f"{n} QA run(s)" if n else "", issues)

    def run_issues(self, doc: Doc) -> list[Issue]:
        _, issues = self.validate_docs()
        return [i for i in issues if i["file"] == self.desk.rel(doc.path)]

    # ---------------------------------------------------------------- views

    def qa_json(self) -> dict[str, Any]:
        docs, issues = self.validate_docs()
        items = [self.run(d).summary_json() for d in docs]
        counts = {s: 0 for s in STATUSES}
        for it in items:
            counts[it["status"]] = counts.get(it["status"], 0) + 1
        errors = [i for i in issues if i["level"] == "error"]
        for it in items:
            it["issue_count"] = sum(1 for i in errors if i["file"] == it["file"])
        return {"dir": self.dir, "runs": items, "counts": counts, "problems": errors}

    def detail_json(self, doc: Doc) -> dict[str, Any]:
        return self.run(doc).detail_json(self.desk.rel(doc.path.parent), self.run_issues(doc))

    # ---------------------------------------------------------------- the human's marks

    def _for_edit(self, rid: str, payload: Any) -> Doc:
        if not isinstance(payload, dict):
            raise HttpError(400, "expected a JSON object")
        doc = self.find(rid)
        etag = payload.get("etag")
        if etag and etag != doc.etag:
            raise HttpError(
                409, "this run changed on disk since you opened it; it was reloaded, check it and mark again"
            )
        if doc.data.get("status") == "processed":
            raise HttpError(409, f"{rid} is processed and read-only; the AI writes a re-test run for what failed")
        return doc

    def _write(
        self, doc: Doc, top: dict[str, Any], case_id: str | None = None, case: dict[str, Any] | None = None
    ) -> Doc:
        from .edits import run_frontmatter

        new_fm = run_frontmatter(doc.fm, doc.data, top, case_id, case, self.note_key)
        write_atomic(doc.path, doc.render(new_fm))
        return parse_doc(doc.path)

    def mark_case(self, rid: str, cid: str, payload: Any) -> Doc:
        """Write one case's result (null un-marks it), note and `at`. The first mark moves ready -> in-progress."""
        with self.desk.lock:
            doc = self._for_edit(rid, payload)
            case = next(
                (c for c in as_list(doc.data.get("cases")) if isinstance(c, dict) and one_line(c.get("id")) == cid),
                None,
            )
            if case is None:
                raise HttpError(404, f"{rid} has no case {cid}")
            raw = payload.get("result")
            result = None if raw in (None, "") else str(raw)
            if result is not None and result not in RESULTS:
                raise HttpError(400, f"result must be one of: {', '.join(RESULTS)}, or null to un-mark")
            status = doc.data.get("status")
            if result is None and status == "done":
                raise HttpError(400, f"{rid} is finished: every case keeps a result (pick another one instead)")
            fields: dict[str, Any] = {"result": result}
            if "note" in payload:
                fields["note"] = clean_text(payload.get("note"))
            same = result is not None and result == case.get("result") and case.get("at")
            fields["at"] = (one_line(case.get("at")) if same else self.desk.timestamp()) if result else None
            top = {"status": "in-progress"} if status == "ready" and result else {}
            return self._write(doc, top, cid, fields)

    def save_note(self, rid: str, payload: Any) -> Doc:
        """The human's note on the whole run."""
        with self.desk.lock:
            doc = self._for_edit(rid, payload)
            return self._write(doc, {self.note_key: clean_text(payload.get("note"))})

    def finish(self, rid: str, payload: Any) -> Doc:
        """ready/in-progress -> done, only when every case has a result."""
        with self.desk.lock:
            doc = self._for_edit(rid, payload)
            if doc.data.get("status") == "done":
                return doc
            unmarked = [
                one_line(c.get("id"))
                for c in as_list(doc.data.get("cases"))
                if isinstance(c, dict) and c.get("result") not in RESULTS
            ]
            if unmarked:
                verb = "has" if len(unmarked) == 1 else "have"
                raise HttpError(400, f"mark every case first: {', '.join(unmarked)} {verb} no result")
            return self._write(doc, {"status": "done"})

    # ---------------------------------------------------------------- HTTP

    def routes(self) -> list[Route]:
        def listing(_: Request) -> Any:
            return self.qa_json()

        def detail(r: Request) -> Any:
            return self.detail_json(self.find(r.match.group(1)))

        def mark(r: Request) -> Any:
            return self.detail_json(self.mark_case(r.match.group(1), r.match.group(2), r.payload))

        def note(r: Request) -> Any:
            return self.detail_json(self.save_note(r.match.group(1), r.payload))

        def finish(r: Request) -> Any:
            return self.detail_json(self.finish(r.match.group(1), r.payload))

        return [
            Route("GET", r"/api/qa", listing),
            Route("GET", r"/api/qa/(R-\d{4})", detail),
            Route("POST", r"/api/qa/(R-\d{4})/case/([A-Za-z0-9_-]{1,32})", mark),
            Route("POST", r"/api/qa/(R-\d{4})/note", note),
            Route("POST", r"/api/qa/(R-\d{4})/finish", finish),
        ]

    def client_settings(self) -> dict[str, Any]:
        return {"dir": self.dir, "max_cases": self.max_cases}

    # ---------------------------------------------------------------- summary and brief (fast path)

    def summary(self) -> str:
        from .fast import quick_runs, summary_text

        tab = self.desk.i18n.t(self.label_key)
        return summary_text(quick_runs(self.folder), self.desk.config.open_hint, tab, self.readme)

    def brief(self, b: Brief) -> None:
        from .fast import quick_runs

        i = self.desk.i18n
        runs = quick_runs(self.folder)
        waiting = [r for r in runs if r["status"] in ("ready", "in-progress")]
        for r in waiting:
            minutes = i.t("brief.run_minutes", minutes=r["minutes"]) if r["minutes"] else ""
            text = i.t("brief.run", id=r["id"], minutes=minutes, marked=r["marked"], total=r["total"], title=r["title"])
            b.asks.append(Ask(10, text, {str(r["id"])}))
        if not runs:
            b.status.append(i.t("brief.runs_none"))
            return
        done = sum(1 for r in runs if r["status"] == "done")
        processed = sum(1 for r in runs if r["status"] == "processed")
        where = (
            i.t("brief.runs_where", open_hint=self.desk.config.open_hint, tab=i.t(self.label_key)) if waiting else ""
        )
        b.status.append(i.t("brief.runs", waiting=len(waiting), done=done, processed=processed, where=where))
