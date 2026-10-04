# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The decisions module: saving answers, validation, `new`, parking and the summary."""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path
from typing import Any

import pytest

from project_desk.desk import Desk
from project_desk.errors import DeskError, HttpError
from project_desk.modules.decisions.fast import QUICK_KEYS
from project_desk.modules.decisions.model import default_id, is_blocking_now, is_parked
from project_desk.modules.decisions.new import ABOUT_TODO, BUILTIN_TEMPLATE, TLDR_TODO, scaffold
from project_desk.scaffold import template
from project_desk.storage.doc import parse_doc
from project_desk.storage.quick import quick_fields
from project_desk.text import about_text, tldr_text

from support import (
    ABOUT,
    ABOUT_BLOCK,
    DECISION,
    DEMO,
    TLDR,
    TLDR_BLOCK,
    about_block,
    add_decision,
    dec,
    decision_path,
    errors,
    make_repo,
    parked,
    status,
    tldr_block,
    warnings,
)


def issues_of(root: Path) -> list[dict[str, str]]:
    return dec(root).validate_docs()[1]


def summary(root: Path) -> str:
    return Desk(root).summary_text()


def with_readme(root: Path) -> None:
    (root / "decisions" / "README.md").write_text(template("decisions/README.md"), encoding="utf-8")


# --------------------------------------------------------------------------- saving


def test_save_changes_only_status_and_answer(repo: Path) -> None:
    p = decision_path(repo)
    before = p.read_text(encoding="utf-8")
    doc = parse_doc(p)

    dec(repo).save_answer(
        "D-0001", {"choice": "b", "comment": "Cool, but warmer greys.\nSecond line.", "etag": doc.etag}
    )

    after = p.read_text(encoding="utf-8")
    new = parse_doc(p).data
    old = doc.data

    # Data: only status and the three answer fields changed.
    assert new["status"] == "answered"
    assert new["answer"]["choice"] == "b"
    assert new["answer"]["comment"] == "Cool, but warmer greys.\nSecond line."
    dt.datetime.fromisoformat(new["answer"]["answered_at"])
    for key in old:
        if key not in ("status", "answer"):
            assert new[key] == old[key], key

    # Text: everything outside the status line and the answer block is byte-for-byte the same.
    b_lines, a_lines = before.split("\n"), after.split("\n")

    def outside(lines: list[str]) -> list[str]:
        start = lines.index("answer:")
        end = lines.index("resolution:")
        return [ln for ln in lines[:start] if not ln.startswith("status:")] + lines[end:]

    assert outside(a_lines) == outside(b_lines)
    status_line = next(ln for ln in a_lines if ln.startswith("status:"))
    assert status_line == "status: answered         # pending | answered | needs-info | resolved | withdrawn"
    assert after.endswith(before[before.index("\nresolution:") :])  # body untouched


def test_save_stamps_the_desk_clock(repo: Path) -> None:
    d = Desk(repo)
    d.now = lambda: "2026-01-02T03:04:05+00:00"
    d.get("decisions").save_answer("D-0001", {"choice": "a"})  # type: ignore[union-attr]
    assert parse_doc(decision_path(repo)).data["answer"]["answered_at"] == "2026-01-02T03:04:05+00:00"


def test_save_needs_info_and_other(repo: Path) -> None:
    m = dec(repo)
    m.save_answer("D-0001", {"needs_info": True, "comment": "What does cool cost us on dark mode?"})
    data = parse_doc(decision_path(repo)).data
    assert data["status"] == "needs-info"
    assert data["answer"]["choice"] is None
    assert data["answer"]["comment"] == "What does cool cost us on dark mode?"

    m.save_answer("D-0001", {"choice": "other", "comment": "Neither: use the brand orange."})
    data = parse_doc(decision_path(repo)).data
    assert data["status"] == "answered"
    assert data["answer"]["choice"] == "other"


@pytest.mark.parametrize(
    "payload, code",
    [
        ({"choice": "z"}, 400),  # not an option
        ({"choice": "other", "comment": ""}, 400),  # other needs an explanation
        ({"needs_info": True, "comment": ""}, 400),  # a question needs text
        ({}, 400),  # nothing picked
        ([], 400),  # not an object
        ({"choice": "a", "etag": "stale"}, 409),  # changed on disk since it was opened
    ],
)
def test_save_rejects_bad_answers(repo: Path, payload: Any, code: int) -> None:
    before = decision_path(repo).read_bytes()
    with pytest.raises(HttpError) as e:
        dec(repo).save_answer("D-0001", payload)
    assert e.value.code == code
    assert decision_path(repo).read_bytes() == before


def test_save_refuses_resolved(tmp_path: Path) -> None:
    root = make_repo(tmp_path, status(DECISION, "resolved"))
    with pytest.raises(HttpError) as e:
        dec(root).save_answer("D-0001", {"choice": "a"})
    assert e.value.code == 409


def test_save_inserts_missing_answer_block(tmp_path: Path) -> None:
    text = DECISION.replace('answer:\n  choice: null\n  comment: ""\n  answered_at: null\n', "")
    root = make_repo(tmp_path, text)
    dec(root).save_answer("D-0001", {"choice": "a", "comment": ""})
    new = parse_doc(decision_path(root))
    assert new.data["answer"]["choice"] == "a"
    assert new.data["options"][0]["summary"] == "Folded summary over two lines."
    assert new.body == parse_doc(decision_path(make_repo(tmp_path / "x", text))).body


@pytest.mark.parametrize(
    "payload",
    [
        {"choice": "b", "comment": "Cool.\nSecond line."},
        {"choice": "other", "comment": "Neither: brand orange."},
        {"needs_info": True, "comment": "What does cool cost on dark mode?"},
    ],
)
def test_save_leaves_tldr_and_about_byte_identical(repo: Path, payload: dict[str, Any]) -> None:
    p = decision_path(repo)
    before = p.read_text(encoding="utf-8")
    assert tldr_block(before) == TLDR_BLOCK
    assert about_block(before) == ABOUT_BLOCK

    dec(repo).save_answer("D-0001", payload)

    after = p.read_text(encoding="utf-8")
    assert tldr_block(after) == TLDR_BLOCK
    assert about_block(after) == ABOUT_BLOCK
    assert parse_doc(p).data["tldr"] == TLDR + "\n"
    assert about_text(parse_doc(p).data) == ABOUT


def test_save_via_ruamel_fallback_keeps_tldr(tmp_path: Path) -> None:
    # No answer block: the surgical edit cannot apply, so the save goes through ruamel.
    text = DECISION.replace('answer:\n  choice: null\n  comment: ""\n  answered_at: null\n', "")
    root = make_repo(tmp_path, text)
    dec(root).save_answer("D-0001", {"choice": "a"})
    after = decision_path(root).read_text(encoding="utf-8")
    assert tldr_block(after) == TLDR_BLOCK
    assert about_block(after) == ABOUT_BLOCK


def test_save_writes_atomically_without_leftovers(repo: Path) -> None:
    dec(repo).save_answer("D-0001", {"choice": "a"})
    leftovers = [p.name for p in (repo / "decisions").iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


# --------------------------------------------------------------------------- validate


def test_validate_passes_clean_repo(repo: Path) -> None:
    assert errors(issues_of(repo)) == []


def test_validate_passes_the_demo() -> None:
    text, code = Desk(DEMO).validate_text()
    assert code == 0 and text.endswith("0 error(s), 0 warning(s)"), text


def test_validate_catches_bad_option_reference(tmp_path: Path) -> None:
    root = make_repo(tmp_path, DECISION.replace("recommendation: b", "recommendation: z"))
    errs = errors(issues_of(root))
    assert errs and any("recommendation" in m and "'z'" in m for m in errs), errs


def test_validate_catches_bad_answer_choice(tmp_path: Path) -> None:
    text = status(DECISION, "answered").replace("choice: null", "choice: q")
    assert any("answer.choice" in m for m in errors(issues_of(make_repo(tmp_path, text))))


@pytest.mark.parametrize(
    "old, new, needle",
    [
        ("type: design", "type: vibes", "type"),
        ("priority: high", "priority: urgent", "priority"),
        ("id: D-0001", "id: D-0009", "D-0009"),  # id must match the filename
        ("design/x/preview.png", "design/x/missing.png", "missing.png"),
        ("design/x/preview.png", "../outside.png", "outside.png"),
        ('question: "Which palette should the app use: warm or cool?"\n', "", "question"),
    ],
)
def test_validate_catches_schema_errors(tmp_path: Path, old: str, new: str, needle: str) -> None:
    root = make_repo(tmp_path, DECISION.replace(old, new, 1))
    assert any(needle in m for m in errors(issues_of(root))), issues_of(root)


def test_validate_types_come_from_the_config(tmp_path: Path) -> None:
    root = make_repo(tmp_path, DECISION.replace("type: design", "type: vibes", 1))
    (root / ".project-desk.toml").write_text('[decisions]\ntypes = ["vibes", "design"]\n')
    assert errors(issues_of(root)) == []


def test_validate_is_quiet_about_a_good_tldr(repo: Path) -> None:
    assert not [m for m in warnings(issues_of(repo)) if "tldr" in m]


@pytest.mark.parametrize(
    "state, tldr, needle",
    [
        ("pending", "", "no tldr"),  # missing
        ("needs-info", "", "no tldr"),
        ("pending", 'tldr: ""\n', "no tldr"),  # empty
        ("pending", "tldr: |\n\n", "no tldr"),  # empty block
        ("pending", "tldr: |\n" + "".join(f"  Рядок {n}.\n" for n in range(6)), "6 lines"),
        ("resolved", "tldr: |\n" + "".join(f"  Рядок {n}.\n" for n in range(6)), "6 lines"),
        ("pending", "tldr: [Один, Два]\n", "text block"),  # not a block string
    ],
)
def test_validate_warns_about_tldr(tmp_path: Path, state: str, tldr: str, needle: str) -> None:
    text = status(DECISION.replace(TLDR_BLOCK, tldr), state)
    if state == "needs-info":
        text = text.replace('comment: ""', 'comment: "A question?"')
    if state == "resolved":
        text = text.replace('summary: ""', 'summary: "Done."')
    issues = issues_of(make_repo(tmp_path, text))
    assert any(needle in m for m in warnings(issues)), issues
    assert not [m for m in errors(issues) if "tldr" in m]  # never an error


@pytest.mark.parametrize("state", ["answered", "resolved", "withdrawn"])
def test_validate_allows_no_tldr_once_answered(tmp_path: Path, state: str) -> None:
    text = status(DECISION.replace(TLDR_BLOCK, ""), state)
    text = text.replace("choice: null", "choice: a").replace('summary: ""', 'summary: "Done."')
    assert not [m for m in warnings(issues_of(make_repo(tmp_path, text))) if "tldr" in m]


def test_validate_duplicate_ids(repo: Path) -> None:
    shutil.copyfile(decision_path(repo), repo / "decisions" / "D-0001-copy.md")
    assert any("duplicate id" in m for m in errors(issues_of(repo)))


def test_material_files_are_not_decisions(repo: Path) -> None:
    (repo / "decisions" / "material" / "D-0002-notes.md").write_text("# Not a decision\n")
    docs, issues = dec(repo).validate_docs()
    assert [d.id for d in docs] == ["D-0001"]
    assert not [i for i in issues if "material" in i["file"]]


def test_list_tolerates_broken_and_new_files(repo: Path) -> None:
    m = dec(repo)
    assert len(m.list_json()["decisions"]) == 1
    (repo / "decisions" / "D-0002-half-written.md").write_text("---\nid: [unclosed\n")
    listing = m.list_json()
    assert [x["id"] for x in listing["decisions"]] == ["D-0001"]
    assert any("D-0002" in p["file"] for p in listing["problems"])


def test_validate_warns_above_the_open_limit(repo: Path) -> None:
    add_decision(repo, "D-0002", default="a")  # parked still counts
    add_decision(repo, "D-0003", status="needs-info")
    add_decision(repo, "D-0004", status="answered")  # the AI's turn: not counted
    assert not any("open for the human" in m for m in warnings(issues_of(repo)))
    add_decision(repo, "D-0005")
    found = [m for m in warnings(issues_of(repo)) if "open for the human" in m]
    assert found and found[0].startswith("4 decisions are open for the human (D-0001, D-0002, D-0003, D-0005")


def test_open_limit_comes_from_the_config_and_zero_turns_it_off(repo: Path) -> None:
    add_decision(repo, "D-0002")
    (repo / ".project-desk.toml").write_text("[decisions]\nopen_limit = 1\n")
    assert any("2 decisions are open for the human" in m for m in warnings(issues_of(repo)))
    (repo / ".project-desk.toml").write_text("[decisions]\nopen_limit = 0\n")
    assert not any("open for the human" in m for m in warnings(issues_of(repo)))


# --------------------------------------------------------------------------- new


def test_new_scaffolds_next_decision(repo: Path) -> None:
    with_readme(repo)
    m = dec(repo)
    path = m.create(
        title="Which charts ship first?", type_="product", group="product-definition", today=dt.date(2026, 9, 23)
    )
    assert path.name == "D-0002-which-charts-ship-first.md"
    data = parse_doc(path).data
    assert (data["id"], data["status"], data["created"], data["group"]) == (
        "D-0002",
        "pending",
        "2026-09-23",
        "product-definition",
    )
    assert tldr_text(data) == TLDR_TODO
    text = path.read_text(encoding="utf-8")
    assert "\ntldr: |" in text and f"\n  {TLDR_TODO}\n" in text
    mine = [i for i in issues_of(repo) if "D-0002" in i["file"]]
    assert errors(mine) == []
    assert any("TODO" in w for w in warnings(mine))  # the tldr placeholder counts as unfinished
    assert m.create(title="Another", type_="data", group="g").name.startswith("D-0003-")


def test_new_refuses_unknown_type_and_priority(repo: Path) -> None:
    with pytest.raises(DeskError, match="type 'vibes' is not one of"):
        dec(repo).create(title="X", type_="vibes", group="g")
    with pytest.raises(DeskError, match="priority"):
        dec(repo).create(title="X", type_="data", group="g", priority="urgent")
    with pytest.raises(DeskError, match="title"):
        dec(repo).create(title="  ", type_="data", group="g")


def test_new_scaffolds_tldr_from_builtin_or_old_template(repo: Path) -> None:
    # No decisions/README.md in this repo: the builtin template is used.
    path = dec(repo).create(title="Built in", type_="product", group="g")
    assert tldr_text(parse_doc(path).data) == TLDR_TODO
    # A template from before `tldr` existed gets it inserted right after `about`.
    old = BUILTIN_TEMPLATE.replace("tldr: |\n  Short version.\n", "")
    text = scaffold(
        old,
        did="D-0009",
        title="Old",
        type_="data",
        group="g",
        priority="low",
        blocking=False,
        asked_by="ai",
        created=dt.date(2026, 9, 23),
    )
    assert f"\ntldr: |\n  {TLDR_TODO}\nrecommendation: null\n" in text


def test_new_scaffolds_about_before_tldr(repo: Path) -> None:
    with_readme(repo)
    path = dec(repo).create(title="Which charts?", type_="product", group="g")
    text = path.read_text(encoding="utf-8")
    assert about_text(parse_doc(path).data) == ABOUT_TODO
    assert text.index("\nquestion:") < text.index("\nabout: |") < text.index("\ntldr: |")
    about_line = next(ln for ln in text.split("\n") if ln.startswith("about:"))
    assert about_line.startswith("about: |") and "# what the question is about" in about_line  # comment kept
    assert f"\n  {ABOUT_TODO}\ntldr: |" in text
    assert not [m for m in errors(issues_of(repo)) if "D-0002" in m]


@pytest.mark.parametrize(
    "strip",
    [
        "about: |\n  What the question is about and why it matters.\n",  # has tldr, no about
        "about: |\n  What the question is about and why it matters.\ntldr: |\n  Short version.\n",  # neither
        "tldr: |\n  Short version.\n",  # has about, no tldr
    ],
)
def test_new_puts_about_and_tldr_in_place_for_old_templates(strip: str) -> None:
    old = BUILTIN_TEMPLATE.replace(strip, "")
    assert old != BUILTIN_TEMPLATE
    text = scaffold(
        old,
        did="D-0009",
        title="Old",
        type_="data",
        group="g",
        priority="low",
        blocking=False,
        asked_by="ai",
        created=dt.date(2026, 9, 23),
    )
    assert f"\nabout: |\n  {ABOUT_TODO}\ntldr: |\n  {TLDR_TODO}\nrecommendation: null\n" in text


def test_new_falls_back_to_the_builtin_template_when_the_readme_one_is_broken(repo: Path) -> None:
    (repo / "decisions" / "README.md").write_text("# Decisions\n\n```markdown\n---\nid: [broken\n---\n```\n")
    path = dec(repo).create(title="Fallback", type_="data", group="g")
    assert parse_doc(path).data["title"] == "Fallback"


# --------------------------------------------------------------------------- about and tldr


def test_tldr_is_empty_when_absent(tmp_path: Path) -> None:
    m = dec(make_repo(tmp_path, DECISION.replace(TLDR_BLOCK, "")))
    assert m.list_json()["decisions"][0]["tldr"] == ""
    assert tldr_text({"tldr": "  Один  \r\n\n  Два\n\n"}) == "  Один\n\n  Два"


def test_about_text_is_one_plain_line() -> None:
    assert about_text({}) == ""
    assert about_text({"about": None}) == ""
    assert about_text({"about": "  Перше речення.\n\n  Друге   речення.\n"}) == "Перше речення. Друге речення."
    assert about_text({"about": ["Одне.", None, "Два."]}) == "Одне. Два."


@pytest.mark.parametrize("state", ["pending", "needs-info", "answered"])
def test_validate_warns_when_open_decision_has_no_about(tmp_path: Path, state: str) -> None:
    text = status(DECISION.replace(ABOUT_BLOCK, ""), state)
    text = text.replace("choice: null", "choice: a" if state == "answered" else "choice: null")
    text = text.replace('comment: ""', 'comment: "A question?"')
    issues = issues_of(make_repo(tmp_path, text))
    assert any("no about" in m for m in warnings(issues)), issues
    assert not [m for m in errors(issues) if "about" in m]  # a missing about is never an error


@pytest.mark.parametrize("state", ["resolved", "withdrawn"])
def test_validate_allows_no_about_once_closed(tmp_path: Path, state: str) -> None:
    text = status(DECISION.replace(ABOUT_BLOCK, ""), state).replace('summary: ""', 'summary: "Done."')
    assert not [m for m in warnings(issues_of(make_repo(tmp_path, text))) if "about" in m]


@pytest.mark.parametrize("value", ["about: [Одне, Два]\n", "about: 5\n", "about:\n  key: value\n"])
def test_validate_about_must_be_text(tmp_path: Path, value: str) -> None:
    issues = issues_of(make_repo(tmp_path, DECISION.replace(ABOUT_BLOCK, value)))
    assert any("about must be text" in m for m in errors(issues)), issues


def test_validate_is_quiet_about_a_good_about_and_flags_todo(tmp_path: Path, repo: Path) -> None:
    assert not [m for m in warnings(issues_of(repo)) if "about" in m]
    text = DECISION.replace(ABOUT_BLOCK, "about: |\n  TODO: пояснити.\n")
    assert any("TODO" in m for m in warnings(issues_of(make_repo(tmp_path / "todo", text))))


# --------------------------------------------------------------------------- parking


def test_parked_decision_in_json(tmp_path: Path) -> None:
    item = dec(make_repo(tmp_path, parked(DECISION, "b"))).list_json()
    d = item["decisions"][0]
    assert (d["parked"], d["default"], d["blocking"], d["blocking_now"]) == (True, "b", True, False)
    assert (item["counts"]["blocking"], item["counts"]["parked"]) == (0, 1)


def test_blocking_decision_without_default_is_not_parked(repo: Path) -> None:
    item = dec(repo).list_json()
    d = item["decisions"][0]
    assert (d["parked"], d["default"], d["blocking_now"]) == (False, None, True)
    assert (item["counts"]["blocking"], item["counts"]["parked"]) == (1, 0)


@pytest.mark.parametrize("state", ["answered", "needs-info", "resolved", "withdrawn"])
def test_only_pending_decisions_are_parked(state: str) -> None:
    data = {"status": state, "default": "a", "blocking": True}
    assert not is_parked(data) and not is_blocking_now(data)
    assert is_parked({"status": "pending", "default": "a"})
    assert not is_parked({"status": "pending", "default": ""})


def test_describe_names_missing_ids(repo: Path) -> None:
    assert dec(repo).describe({"D-0001", "D-0042"}) == {
        "D-0001": {
            "id": "D-0001",
            "title": "Pick a palette",
            "status": "pending",
            "parked": False,
            "blocking_now": True,
            "exists": True,
        },
        "D-0042": {"id": "D-0042", "exists": False},
    }


# --------------------------------------------------------------------------- summary (the AI's view)


def test_summary_is_silent_when_nothing_is_open(tmp_path: Path) -> None:
    assert summary(make_repo(tmp_path, status(DECISION, "resolved"))) == ""


def test_summary_counts(repo: Path) -> None:
    text = summary(repo)
    assert "1 pending" in text and "1 blocking" in text


def test_summary_lists_pending_with_about_and_parking(repo: Path) -> None:
    add_decision(
        repo,
        "D-0002",
        title="Parked high one",
        priority="high",
        blocking="true",
        default="b",
        about='about: "Друге питання: \\"важливе\\"."\n',
    )
    add_decision(repo, "D-0003", title="Plain low one", priority="low", about="about: Просте пояснення без лапок\n")
    add_decision(repo, "D-0004", title="Closed one", status="resolved", about="about: Не показувати.\n")
    add_decision(repo, "D-0005", title="Waiting on AI", status="answered", default="a")

    lines = summary(repo).splitlines()
    assert lines[0] == (
        "Decision Desk: 3 pending (1 blocking, 1 parked), 1 answered awaiting AI processing — run `desk serve --open`"
    )
    # Blocking first, then by priority: high, medium, low.
    assert lines[1] == "  D-0001  Pick a palette — blocking"
    assert lines[2] == f"      about: {ABOUT}"
    assert lines[3] == "  D-0002  Parked high one — parked (default b)"
    assert lines[4] == '      about: Друге питання: "важливе".'
    assert lines[5] == "  D-0003  Plain low one"
    assert lines[6] == "      about: Просте пояснення без лапок"
    assert lines[7].startswith("Parked = the AI works with the default until the human answers")
    assert lines[8] == "AI: process these with the decision-desk skill (`desk list --status answered,needs-info`)."
    assert "Closed one" not in "\n".join(lines) and "Waiting on AI" not in "\n".join(lines)


def test_summary_uses_the_configured_open_hint_and_command(repo: Path) -> None:
    add_decision(repo, "D-0002", status="answered")
    (repo / ".project-desk.toml").write_text('open_hint = "make decisions"\ncommand = "uvx desk"\n')
    text = summary(repo)
    assert "— run `make decisions`" in text and "(`uvx desk list --status answered,needs-info`)" in text


def test_summary_without_about_prints_only_the_item(tmp_path: Path) -> None:
    root = make_repo(tmp_path, parked(DECISION.replace(ABOUT_BLOCK, "")).replace("\n", "\r\n"))
    lines = summary(root).splitlines()
    assert lines[:2] == [
        "Decision Desk: 1 pending (1 parked) — run `desk serve --open`",
        "  D-0001  Pick a palette — parked (default a)",  # the trailing comment is dropped
    ]
    assert "about:" not in "\n".join(lines)


@pytest.mark.parametrize(
    "fm, expected",
    [
        ("about: Plain words\n", "Plain words"),
        ("about: Plain words   # a comment\n", "Plain words"),
        ('about: "Quoted: with \\"escapes\\" and \\u00e9"\n', 'Quoted: with "escapes" and é'),
        ("about: 'It''s single'\n", "It's single"),
        ("about: |\n  Line one.\n  Line two # kept.\n", "Line one. Line two # kept."),
        ("about: >-   # folded\n  Folded one\n\n  folded two\n", "Folded one folded two"),
        ("about: Plain that\n  continues here\n", "Plain that continues here"),
        ("about: null\n", None),
        ("about:\n", None),
    ],
)
def test_quick_fields_reads_scalar_styles(fm: str, expected: str | None) -> None:
    assert quick_fields("id: D-0001\n" + fm + "status: pending\n", ("id", "about", "status")) == {
        "id": "D-0001",
        "about": expected,
        "status": "pending",
    }


@pytest.mark.parametrize("real", sorted((DEMO / "decisions").glob("D-*.md")), ids=lambda p: p.name)
def test_quick_fields_match_yaml_on_the_demo(real: Path) -> None:
    doc = parse_doc(real)
    quick = quick_fields(doc.fm, QUICK_KEYS)
    assert (quick.get("about") or "") == about_text(doc.data)
    assert quick.get("title") == doc.data.get("title")
    assert quick.get("status") == doc.data.get("status")
    assert default_id(quick) == default_id(doc.data)
