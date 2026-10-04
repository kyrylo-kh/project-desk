# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The QA module: run files, their validation, the human's marks and the summary."""

from __future__ import annotations

from pathlib import Path

import pytest

from project_desk.cli import main
from project_desk.desk import Desk
from project_desk.errors import HttpError
from project_desk.modules.qa.fast import quick_run_fields
from project_desk.modules.qa.model import run_outline
from project_desk.storage.doc import parse_doc

from support import (
    DECISION,
    DEMO,
    NOW,
    RUN,
    RUN_NAME,
    errors,
    make_repo,
    make_run,
    qa,
    run_edited,
    run_issues,
    run_text,
    status,
    warnings,
    write_config,
)


def test_run_fixture_is_clean_and_counted_by_validate(qa_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert run_issues(qa_repo) == []
    assert main(["--root", str(qa_repo), "validate"]) == 0
    assert capsys.readouterr().out.splitlines()[-1] == (
        "validate: 1 decision file(s) and 1 QA run(s) and plan/roadmap.yaml, 0 error(s), 0 warning(s)"
    )


def test_run_round_trip_and_json(qa_repo: Path) -> None:
    k = qa(qa_repo)
    doc = k.find("R-0001")
    assert doc.render() == RUN.encode("utf-8")
    s = k.run(doc).summary_json()
    assert (s["status"], s["slice"], s["minutes"], s["total"], s["marked"]) == ("ready", "S1", 25, 3, 0)
    assert s["counts"] == {"pass": 0, "fail": 0, "blocked": 0, "skip": 0, "unmarked": 3}
    d = k.detail_json(doc)
    assert d["setup"].splitlines()[1] == "Пошта: http://localhost:8025 # not a comment"
    assert d["overall_note"] == ""
    t1, t2, t3 = d["cases"]
    assert t1["steps"] == ["Натисни «Get started».", "Пройди 5 питань: обери «Option A»."]
    assert t2["steps"] == ["Натисни «Save»."] and t2["result"] is None and t2["note"] == ""
    assert t3["id"] == "T03" and t3["expected"] == ["Видно кроки."]
    assert "<table>" in d["body_html"]
    q = k.qa_json()
    assert q["counts"]["ready"] == 1 and q["problems"] == [] and q["runs"][0]["issue_count"] == 0


@pytest.mark.parametrize(
    "old,new,needle",
    [
        ('title: "C1: весь шлях"      # plain words\n', "", "missing required field 'title'"),
        ("slice: S1  ", "slice: S9  ", "slice 'S9' is not an id in plan/roadmap.yaml"),
        ("status: ready    ", "status: started  ", "status 'started' is not one of"),
        ("result: null              #", "result: passed            #", "case T01: result 'passed' is not one of"),
        ("- id: T02\n", "- id: T01\n", "case id T01 is used twice"),
        ("  steps: [Натисни «Save».]\n", "", "case T02 has no steps"),
        ("  expected:\n    - Видно кроки.\n", "", "case T03 has no expected"),
        ("id: R-0001\n", "id: R-0002\n", "id 'R-0002' does not match the filename (R-0001)"),
        ("id: R-0001\n", "id: Run-1\n", "id 'Run-1' must look like R-0001"),
        ("minutes: 25 ", "minutes: ~25", "minutes '~25' must be a whole number of minutes"),
        ("created: 2026-10-03\n", "created: soon\n", "created 'soon' must be a date"),
        ('overall_note: ""  ', "overall_note: [x]", "'overall_note' must be text"),
    ],
)
def test_run_validation_errors(plan_repo: Path, old: str, new: str, needle: str) -> None:
    make_run(plan_repo, run_edited(old, new))
    assert any(needle in m for m in errors(run_issues(plan_repo))), errors(run_issues(plan_repo))


def test_run_validation_more_errors(plan_repo: Path) -> None:
    make_run(plan_repo, RUN[: RUN.index("cases:")] + "cases: []\n---\n")
    assert "cases is empty: a run needs at least one case" in errors(run_issues(plan_repo))
    make_run(plan_repo, name="R-0001-Bad_Name.md")
    assert any("filename must look like R-0001-short-slug.md" in m for m in errors(run_issues(plan_repo)))


def test_run_validation_duplicate_ids_and_stray_files(qa_repo: Path) -> None:
    make_run(qa_repo, name="R-0001-copy.md")
    (qa_repo / "qa" / "runs" / "notes.md").write_text("# scratch\n")
    issues = run_issues(qa_repo)
    dupes = [m for m in errors(issues) if m.startswith("duplicate run id R-0001")]
    assert len(dupes) == 2
    assert any("not a run file name" in m for m in warnings(issues))


def test_run_slice_is_not_checked_without_a_plan(repo: Path) -> None:
    make_run(repo, run_edited("slice: S1  ", "slice: S9  "))
    assert run_issues(repo) == []


def test_run_slice_is_optional(plan_repo: Path) -> None:
    make_run(plan_repo, run_edited("slice: S1                   # plan item id\n", ""))
    assert run_issues(plan_repo) == []


def test_run_validation_warnings(plan_repo: Path) -> None:
    case = "- id: T{n:02d}\n  title: Кейс\n  steps: [Крок.]\n  expected: [Видно.]\n  result: {result}\n  ai: {ai}\n"
    head = RUN[: RUN.index("cases:")] + "cases:\n"

    def run(state: str, results: list[str], ai: str = '""') -> str:
        cases = "".join(case.format(n=n, result=r, ai=ai) for n, r in enumerate(results, 1))
        return head.replace("status: ready  ", f"status: {state}  ".ljust(len("status: ready  ")), 1) + cases + "---\n"

    make_run(plan_repo, run("ready", ["null"] * 16))
    assert any("16 cases; keep a run to at most 15" in m for m in warnings(run_issues(plan_repo)))
    make_run(plan_repo, run("done", ["pass", "null", "null"]))
    assert "run is done but T02, T03 have no result" in warnings(run_issues(plan_repo))
    make_run(plan_repo, run("processed", ["pass", "fail", "blocked"]))
    assert any(
        m.startswith("run is processed but T02 (fail), T03 (blocked) have no ai")
        for m in warnings(run_issues(plan_repo))
    )
    make_run(plan_repo, run("processed", ["pass", "fail"], ai="fixed in abc123"))
    assert run_issues(plan_repo) == []
    write_config(plan_repo, "[qa]\nmax_cases = 1\n")
    assert any("2 cases; keep a run to at most 1" in m for m in warnings(run_issues(plan_repo)))


def test_validate_checks_runs_with_one_exit_code(plan_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_run(plan_repo, run_edited("status: ready    ", "status: started  "))
    assert main(["--root", str(plan_repo), "validate"]) == 1
    out = capsys.readouterr().out
    assert "qa/runs/R-0001-c1-path.md: error: status 'started'" in out
    assert out.splitlines()[-1].endswith("and 1 QA run(s) and plan/roadmap.yaml, 1 error(s), 0 warning(s)")


def test_run_scanner_matches_yaml(qa_repo: Path) -> None:
    doc = parse_doc(qa_repo / "qa" / "runs" / RUN_NAME)
    assert quick_run_fields(doc.fm) == run_outline(doc.data)
    assert quick_run_fields(doc.fm)["results"] == ["", "", ""]


def test_run_scanner_matches_yaml_on_the_demo() -> None:
    for p in sorted((DEMO / "qa" / "runs").glob("R-*.md")):
        doc = parse_doc(p)
        assert quick_run_fields(doc.fm) == run_outline(doc.data), p.name


# ------------------------------------------------------------ marking


def test_mark_changes_only_its_lines(qa_repo: Path) -> None:
    k = qa(qa_repo)
    etag = k.find("R-0001").etag
    k.mark_case("R-0001", "T01", {"etag": etag, "result": "fail", "note": "Кнопка не працює.\nДругий рядок: «так»"})
    expected = (
        RUN.replace("status: ready               #", "status: in-progress         #", 1)
        .replace("  result: null              # human", "  result: fail              # human", 1)
        .replace(
            '  note: ""                  # human\n',
            "  note: |-                  # human\n    Кнопка не працює.\n    Другий рядок: «так»\n",
            1,
        )
        .replace("  at: null                  #", f'  at: "{NOW}" #', 1)
    )
    assert run_text(qa_repo) == expected


def test_mark_appends_missing_keys_and_handles_a_bare_dash(qa_repo: Path) -> None:
    k = qa(qa_repo)
    k.mark_case("R-0001", "T02", {"result": "pass"})
    k.mark_case("R-0001", "T03", {"result": "skip", "note": "Не встиг"})
    text = run_text(qa_repo)
    assert '  - Код приходить на пошту.\n  result: pass\n  at: "' + NOW + '"\n-\n  id: T03\n' in text
    assert '  result: skip\n  note: "Не встиг"\n  at: "' + NOW + '"\n---\n' in text
    assert text.endswith(RUN[RUN.index("---\n\n## Context") :])
    d = k.detail_json(k.find("R-0001"))
    assert [c["result"] for c in d["cases"]] == [None, "pass", "skip"] and d["status"] == "in-progress"
    assert run_issues(qa_repo) == []


def test_mark_keeps_note_and_time_and_unmarks(qa_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import project_desk.text

    k = qa(qa_repo)
    k.mark_case("R-0001", "T01", {"result": "fail", "note": "Зламано"})
    monkeypatch.setattr(project_desk.text, "now_iso", lambda: "2026-10-03T11:00:00+03:00")
    doc = k.mark_case("R-0001", "T01", {"result": "fail"})  # same result, no note: both kept
    c = k.detail_json(doc)["cases"][0]
    assert (c["result"], c["note"], c["at"]) == ("fail", "Зламано", NOW)
    doc = k.mark_case("R-0001", "T01", {"result": None})  # un-mark
    c = k.detail_json(doc)["cases"][0]
    assert (c["result"], c["note"], c["at"]) == (None, "Зламано", None)
    assert doc.data["status"] == "in-progress"  # never back to ready


def test_finish_treats_an_invalid_result_as_unmarked(qa_repo: Path) -> None:
    path = next((qa_repo / "qa" / "runs").glob("R-0001-*.md"))
    path.write_text(path.read_text().replace("result: null", "result: passed"))
    with pytest.raises(HttpError) as e:
        qa(qa_repo).finish("R-0001", {})
    assert e.value.code == 400 and "T01" in str(e.value)


def test_finish_needs_every_case_marked(qa_repo: Path) -> None:
    k = qa(qa_repo)
    k.mark_case("R-0001", "T01", {"result": "pass"})
    with pytest.raises(HttpError) as e:
        k.finish("R-0001", {})
    assert e.value.code == 400 and "T02, T03 have no result" in str(e.value)
    k.mark_case("R-0001", "T02", {"result": "fail"})
    k.mark_case("R-0001", "T03", {"result": "blocked"})
    doc = k.finish("R-0001", {"etag": k.find("R-0001").etag})
    assert doc.data["status"] == "done"
    assert run_text(qa_repo).count("status: done                #") == 1
    assert k.finish("R-0001", {}).etag == doc.etag  # finishing twice changes nothing
    with pytest.raises(HttpError) as e:
        k.mark_case("R-0001", "T01", {"result": None})
    assert e.value.code == 400  # a done run keeps a result on every case
    assert k.mark_case("R-0001", "T01", {"result": "skip"}).data["status"] == "done"


def test_marks_refuse_stale_etags_processed_runs_and_bad_input(qa_repo: Path) -> None:
    k = qa(qa_repo)
    stale = k.find("R-0001").etag
    k.mark_case("R-0001", "T01", {"result": "pass"})
    for call in (
        lambda: k.mark_case("R-0001", "T02", {"etag": stale, "result": "pass"}),
        lambda: k.save_note("R-0001", {"etag": stale, "note": "x"}),
        lambda: k.finish("R-0001", {"etag": stale}),
    ):
        with pytest.raises(HttpError) as e:
            call()
        assert e.value.code == 409
    for payload, code in (({"result": "great"}, 400), ([], 400)):
        with pytest.raises(HttpError) as e:
            k.mark_case("R-0001", "T01", payload)
        assert e.value.code == code
    with pytest.raises(HttpError) as e:
        k.mark_case("R-0001", "T99", {"result": "pass"})
    assert e.value.code == 404

    make_run(qa_repo, run_edited("status: ready    ", "status: processed"))
    before = run_text(qa_repo)
    for call in (
        lambda: k.mark_case("R-0001", "T01", {"result": "pass"}),
        lambda: k.save_note("R-0001", {"note": "x"}),
        lambda: k.finish("R-0001", {}),
    ):
        with pytest.raises(HttpError) as e:
            call()
        assert e.value.code == 409 and "processed" in str(e.value)
    assert run_text(qa_repo) == before


def test_overall_note_is_saved_in_place(qa_repo: Path) -> None:
    k = qa(qa_repo)
    k.save_note("R-0001", {"note": "Загалом зрозуміло.\nАле довго."})
    assert run_text(qa_repo) == RUN.replace(
        'overall_note: ""            # human: overall impression\n',
        "overall_note: |-            # human: overall impression\n  Загалом зрозуміло.\n  Але довго.\n",
        1,
    )
    k.save_note("R-0001", {"note": ""})
    assert run_text(qa_repo) == RUN


def test_note_key_is_configurable(qa_repo: Path) -> None:
    make_run(qa_repo, RUN.replace("overall_note:", "founder_note:"))
    write_config(qa_repo, '[qa]\nnote_key = "founder_note"\n')
    k = qa(qa_repo)
    k.save_note("R-0001", {"note": "Добре"})
    assert 'founder_note: "Добре"' in run_text(qa_repo) and "overall_note" not in run_text(qa_repo)
    assert k.detail_json(k.find("R-0001"))["overall_note"] == "Добре"


def test_run_edits_fall_back_to_ruamel_for_flow_cases(plan_repo: Path, clock: None) -> None:
    flow = RUN[: RUN.index("cases:")] + "cases: [{id: T01, title: A, steps: [x], expected: [y], result: null}]\n---\n"
    make_run(plan_repo, flow)
    doc = qa(plan_repo).mark_case("R-0001", "T01", {"result": "pass", "note": "ok"})
    c = doc.data["cases"][0]
    assert (c["result"], c["note"], c["at"], doc.data["status"]) == ("pass", "ok", NOW, "in-progress")
    assert doc.data["setup"] == parse_doc(make_run(plan_repo / "x", RUN)).data["setup"]


# ------------------------------------------------------------ summary


def test_summary_lists_qa_runs_between_decisions_and_plan(qa_repo: Path) -> None:
    make_run(
        qa_repo,
        run_edited("status: ready    ", "status: done     ")
        .replace("result: null              #", "result: fail              #", 1)
        .replace("  result: null\n", "  result: blocked\n", 1)
        .replace("id: R-0001", "id: R-0002", 1)
        .replace('title: "C1: весь шлях"', "title: Повтор", 1),
        name="R-0002-retest.md",
    )
    lines = Desk(qa_repo).summary_text().splitlines()
    i = lines.index(
        "Test Desk: 1 waiting for the human, 1 done awaiting AI processing — run `desk serve --open` (tab Test Desk)"
    )
    assert lines[i + 1] == "  R-0001  C1: весь шлях — ready, 0/3 marked, ~25 min"
    assert lines[i + 2] == "  R-0002  Повтор — done: 1 fail, 1 blocked"
    assert lines[i + 3].startswith("AI: process done runs per qa/README.md")
    assert lines[i - 1].startswith("AI: process these") or lines[i - 1].startswith("  ")  # decisions come first
    assert lines[i + 4].startswith("Plan (plan/roadmap.yaml")


def test_summary_is_silent_about_processed_runs(tmp_path: Path) -> None:
    root = make_repo(tmp_path, status(DECISION, "resolved"))
    make_run(root, run_edited("status: ready    ", "status: processed"))
    assert Desk(root).summary_text() == ""


def test_qa_is_off_without_a_runs_folder_in_auto_mode(repo: Path) -> None:
    assert Desk(repo).get("qa") is None
    make_run(repo)
    assert Desk(repo).get("qa") is not None
