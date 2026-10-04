# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The plan module: plan/roadmap.yaml, its validation, its view and its part of summary."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from project_desk.cli import main
from project_desk.desk import Desk
from project_desk.modules.plan.model import plan_outline

from support import DECISION, PLAN, edited, errors, make_plan, make_repo, status, warnings, write_config


def plan(root: Path) -> Any:
    m = Desk(root).get("plan")
    assert m is not None, "the plan module is not on"
    return m


def plan_issues(root: Path) -> list[dict[str, str]]:
    return plan(root).validate().issues


def test_plan_json_serves_the_roadmap_and_decision_statuses(plan_repo: Path) -> None:
    p = plan(plan_repo).plan_json()
    assert p["exists"] is True and p["problems"] == []
    assert (p["updated"], p["now"]) == ("2026-09-20", "S1")
    assert [a["title"] for a in p["actions"]] == ["Знайти експерта", "Протестувати: анкету"]
    assert p["actions"][1]["when"] == "після S1" and p["actions"][0]["decisions"] == ["D-0001"]
    assert [ph["id"] for ph in p["phases"]] == ["P1", "P2", "P3"]
    p2 = p["phases"][1]
    assert p2["about"] == "Шлях людини від лендінгу." and p["phases"][2]["items"] == []
    s0, s1, s2, _ = p2["items"]
    assert s1["about"] == "Гість відповідає на 5 питань." and s2["title"] == "AI-розбір: коротко"
    assert [(x["kind"], x["exists"], x["url"]) for x in s0["links"]] == [
        ("image", True, "/preview/design/x/preview.png"),
        ("html", True, "/preview/design/x/preview.html"),
    ]
    assert p["phases"][0]["items"][1]["needs"] == "Твоя відповідь."
    assert p["decisions"] == {
        "D-0001": {
            "id": "D-0001",
            "title": "Pick a palette",
            "status": "pending",
            "parked": False,
            "blocking_now": True,
            "exists": True,
        }
    }


def test_actions_key_is_configurable(plan_repo: Path) -> None:
    make_plan(plan_repo, PLAN.replace("actions:", "founder_actions:"))
    write_config(plan_repo, '[plan]\nactions_key = "founder_actions"\n')
    p = plan(plan_repo).plan_json()
    assert len(p["actions"]) == 2 and plan_issues(plan_repo) == []
    assert "Asks for the human: 2" in Desk(plan_repo).summary_text()


def test_plan_is_off_without_a_plan_file_in_auto_mode(repo: Path) -> None:
    assert Desk(repo).get("plan") is None
    make_plan(repo)
    assert Desk(repo).get("plan") is not None


def test_missing_plan_is_not_a_problem_when_listed(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    write_config(repo, 'modules = ["decisions", "plan"]\n')
    m = plan(repo)
    assert m.plan_json() == {"file": "plan/roadmap.yaml", "exists": False}
    assert m.validate().issues == []
    assert main(["--root", str(repo), "validate"]) == 0
    assert capsys.readouterr().out.strip() == "validate: 1 decision file(s), 0 error(s), 0 warning(s)"
    assert "Plan (" not in Desk(repo).summary_text() and m.quick_outline() is None


def test_unreadable_plan_is_reported_not_raised(repo: Path) -> None:
    make_plan(repo, "updated: 2026-09-20\nphases: [\n")
    m = plan(repo)
    p = m.plan_json()
    assert p["exists"] is True and p["error"].startswith("invalid YAML")
    issues = m.validate().issues
    assert len(issues) == 1 and issues[0]["file"] == "plan/roadmap.yaml" and "invalid YAML" in issues[0]["message"]
    make_plan(repo, "- just\n- a list\n")
    assert "must be a YAML mapping" in m.plan_json()["error"]
    assert Desk(repo).summary_text().startswith("Decision Desk: 1 pending")  # the decisions part survives


def test_validate_plan_is_clean_on_a_good_plan(plan_repo: Path) -> None:
    assert plan_issues(plan_repo) == []


@pytest.mark.parametrize(
    "old, new, needle",
    [
        (
            "status: later\n      about: Вхід.",
            "status: soon\n      about: Вхід.",
            "item S3: status 'soon' is not one of: done, doing, next, later, waiting",
        ),
        (
            "decisions: [D-0001]\n        needs",
            "decisions: [D-0099]\n        needs",
            "item F2: decision D-0099 does not exist in decisions/",
        ),
        (
            "decisions: [D-0001]\n    note",
            "decisions: [D-0042]\n    note",
            "action #1: decision D-0042 does not exist in decisions/",
        ),
        (
            "decisions: [D-0001]\n        needs",
            "decisions: [nope]\n        needs",
            "item F2: decision 'nope' must look like D-0001",
        ),
        (
            "links: [decisions/material/D-0001-notes.md]",
            "links: [decisions/material/gone.md]",
            "item F1: link 'decisions/material/gone.md' does not exist",
        ),
        (
            "links: [decisions/material/D-0001-notes.md]",
            "links: [../outside.md]",
            "item F1: link '../outside.md' is not allowed: path traversal",
        ),
        (
            "links: [decisions/material/D-0001-notes.md]",
            "links: decisions/material/D-0001-notes.md",
            "item F1: links must be a list",
        ),
        ("now: S1 ", "now: S9 ", "now 'S9' is not the id of any item in phases"),
        ("now: S1 ", "now: P2 ", "now 'P2' is a phase; point it at the item being worked on"),
        ("now: S1 ", "now: S2 ", "now 'S2' has status next; now must point at the item whose status is doing"),
        ("- id: S3", "- id: F1", "duplicate id F1 (in the items of phase P1 and in the items of phase P2)"),
        ("- id: P3", "- id: S0", "duplicate id S0"),
        ("updated: 2026-09-20\n", "", "missing required key 'updated'"),
        ("updated: 2026-09-20\n", "updated: soon\n", "updated 'soon' must be a date (YYYY-MM-DD)"),
        ("      title: Акаунти\n", "", "item S3 has no title"),
        ("    title: Після запуску\n", "", "phase P3 has no title"),
        ("actions:\n  - title: Знайти експерта\n", "actions:\n  - when: soon\n", "action #1 has no title"),
        ("actions:\n  - title", "actions: 5\nold:\n  - title", "actions must be a list"),
    ],
)
def test_validate_plan_errors_name_the_item(repo: Path, old: str, new: str, needle: str) -> None:
    make_plan(repo, edited(old, new))
    found = errors(plan_issues(repo))
    assert any(needle in m for m in found), found


def test_plan_decision_refs_are_not_checked_without_the_decisions_module(repo: Path) -> None:
    make_plan(repo, edited("decisions: [D-0001]\n    note", "decisions: [D-0042]\n    note"))
    write_config(repo, 'modules = ["plan"]\n')
    assert errors(plan_issues(repo)) == []
    assert plan(repo).plan_json()["decisions"] == {}


@pytest.mark.parametrize(
    "old, new, needle",
    [
        ("        needs: Твоя відповідь.\n", "", "item F2 is waiting but has no needs"),
        (
            "        status: done\n        about: Що працювало.",
            "        status: doing\n        about: Що працювало.",
            "phase P1 is done but F1 is not done or waiting",
        ),
        ("      about: Вхід.\n", "", "item S3 has no about"),
        (
            "links: [decisions/material/D-0001-notes.md]",
            "links: [design/x]",
            "item F1: link 'design/x' exists but the desk cannot open it",
        ),
    ],
)
def test_validate_plan_warnings(repo: Path, old: str, new: str, needle: str) -> None:
    make_plan(repo, edited(old, new))
    issues = plan_issues(repo)
    assert errors(issues) == [] and any(needle in m for m in warnings(issues)), issues


def test_validate_plan_warns_when_a_later_phase_has_work_in_progress(repo: Path) -> None:
    make_plan(
        repo,
        PLAN.replace(
            "    items: []\n",
            "    items:\n      - id: X1\n        title: Рано\n        status: doing\n        about: Почали.\n",
        ),
    )
    assert any("phase P3 is later but X1 is doing" in m for m in warnings(plan_issues(repo)))


def test_validate_command_checks_the_plan(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    make_plan(repo, edited("now: S1 ", "now: S9 "))
    assert main(["--root", str(repo), "validate"]) == 1
    out = capsys.readouterr().out.splitlines()
    assert "plan/roadmap.yaml: error: now 'S9' is not the id of any item in phases" in out
    assert out[-1] == "validate: 1 decision file(s) and plan/roadmap.yaml, 1 error(s), 0 warning(s)"


def test_summary_appends_where_the_plan_is(plan_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    lines = Desk(plan_repo).summary_text().splitlines()
    assert lines[0].startswith("Decision Desk: 1 pending")  # the decisions part comes first
    assert lines[-4:] == [
        "Plan (plan/roadmap.yaml, updated 2026-09-20):",
        "  Now: S1 — Анкета → результат",
        "  Next: S2 — AI-розбір: коротко",
        "  Asks for the human: 2",
    ]
    assert main(["--root", str(plan_repo), "summary"]) == 0
    assert capsys.readouterr().out.rstrip("\n").splitlines() == lines


def test_summary_plan_only_and_several_next(tmp_path: Path) -> None:
    root = make_repo(tmp_path, status(DECISION, "resolved"))
    make_plan(
        root,
        PLAN.replace("status: later\n      about: Вхід.", "status: next\n      about: Вхід.").replace(
            "actions:", "old_actions:"
        ),
    )
    assert Desk(root).summary_text().splitlines() == [
        "Plan (plan/roadmap.yaml, updated 2026-09-20):",
        "  Now: S1 — Анкета → результат",
        "  Next: S2 — AI-розбір: коротко; S3 — Акаунти",
        "  Asks for the human: 0",
    ]


@pytest.mark.parametrize(
    "text",
    [
        PLAN,
        PLAN.replace("\n", "\r\n"),
        'updated: 2026-01-02\nnow: A1\nactions: []\nphases:\n- id: P1\n  title: "Лапки: \\"так\\""\n'
        "  status: doing\n  items:\n  - id: A1\n    title: >\n      Два\n      рядки\n    status: doing\n"
        "    links:\n    - a.md\n  - {id: A2, title: flow, status: next}\n",
        "updated: 2026-01-02\nnow: A1\nphases:\n  - id: P1\n    title: Plain # comment\n    status: doing\n"
        "    about:\n      starts on the next line\n    items:\n      -   id: A1\n          title: wide dash\n"
        "          status: doing\n",
    ],
    ids=["fixture", "crlf", "flow-and-folded", "odd-spacing"],
)
def test_quick_plan_matches_yaml(tmp_path: Path, text: str) -> None:
    root = tmp_path / "r"
    (root / "decisions").mkdir(parents=True)
    make_plan(root, text)
    m = plan(root)
    data = m.load()
    if "{id: A2" in text:  # flow mappings are outside the line reader's subset: validate says so
        assert m.quick_outline() != plan_outline(data, "actions")
        assert any("reads this file differently" in w for w in warnings(m.validate().issues))
        return
    assert m.quick_outline() == plan_outline(data, "actions")


def test_quick_plan_matches_yaml_on_the_demo() -> None:
    from support import DEMO

    m = plan(DEMO)
    assert m.quick_outline() == plan_outline(m.load(), "actions")
