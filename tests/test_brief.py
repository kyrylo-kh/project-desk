# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""`brief` (the human's one screen, in the UI language) and the fast path both it and `summary` keep."""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from pathlib import Path

import pytest

from project_desk.cli import main
from project_desk.desk import BRIEF_WIDTH, Desk

from support import DEMO, add_decision, make_repo, write_config


def uk(root: Path) -> None:
    write_config(root, 'lang = "uk"\nopen_hint = "make decisions"\n')


def test_summary_and_brief_never_import_yaml_or_markdown(qa_repo: Path) -> None:
    code = (
        "import sys; from pathlib import Path\n"
        "from project_desk.desk import Desk\n"
        f"d = Desk(Path({str(qa_repo)!r})); assert d.summary_text() and d.brief_text(commits=[])\n"
        "print(sorted(k for k in sys.modules if k.split('.')[0] in ('ruamel', 'markdown', 'click')))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"


def test_brief_shape_in_ukrainian(qa_repo: Path) -> None:
    uk(qa_repo)
    add_decision(qa_repo, "D-0002", title="Друге", priority="high", default="b")
    add_decision(qa_repo, "D-0003", title="Питання AI", status="needs-info")
    commits = [f"feat: крок {n}" for n in range(1, 11)]
    text = Desk(qa_repo).brief_text(today=dt.date(2026, 10, 3), commits=commits)
    lines = text.splitlines()
    assert lines[0] == "Сьогодні субота, 3 жовтня 2026"
    assert lines[1] == "Зараз: S1 — Анкета → результат"
    assert lines[2] == "Далі: S2 — AI-розбір: коротко"
    assert lines[3] == "Від тебе:"
    asks = lines[4:9]
    assert asks[0] == "  • Тест R-0001, ~25 хв, позначено 0/3: «C1: весь шлях»"  # runs first
    assert asks[1] == "  • Рішення D-0001 «Pick a palette» (блокує роботу)"  # then pending decisions
    assert asks[2] == "  • Рішення D-0002 «Друге» (запарковано)"
    assert asks[3] == "  • Знайти експерта"  # then the plan's actions
    assert asks[4] == "  • Протестувати: анкету (після S1)"
    assert "Питання AI" not in text  # needs-info is the AI's turn
    assert lines[9] == "Тести: чекають на тебе 1, на обробці в AI 0, оброблено 0 (make decisions, вкладка Тести)"
    assert lines[10] == "За 7 днів:" and lines[11] == "  • feat: крок 1" and lines[18] == "  • feat: крок 8"
    assert lines[19] == "  і ще 2" and len(lines) == 20
    assert all(len(ln) <= BRIEF_WIDTH for ln in lines) and "\x1b" not in text


def test_brief_shape_in_english(qa_repo: Path) -> None:
    add_decision(qa_repo, "D-0002", title="Second", priority="high", default="b")
    text = Desk(qa_repo).brief_text(today=dt.date(2026, 10, 3), commits=[])
    assert text.splitlines() == [
        "Today is Saturday, 3 October 2026",
        "Now: S1 — Анкета → результат",
        "Next: S2 — AI-розбір: коротко",
        "Waiting on you:",
        "  • Test run R-0001, ~25 min, marked 0/3: “C1: весь шлях”",
        "  • Decision D-0001 “Pick a palette” (blocks work)",
        "  • Decision D-0002 “Second” (parked)",
        "  • Знайти експерта",
        "  • Протестувати: анкету (після S1)",
        "Test Desk: waiting on you 1, with the AI 0, processed 0 (desk serve --open, tab Test Desk)",
        "Last 7 days: no commits",
    ]


def test_brief_skips_a_plan_action_that_names_a_listed_item(qa_repo: Path) -> None:
    uk(qa_repo)
    plan = qa_repo / "plan" / "roadmap.yaml"
    plan.write_text(
        plan.read_text().replace(
            "actions:\n", "actions:\n  - title: Пройти тест-ран R-0001\n  - title: Відповісти на D-0001\n", 1
        )
    )
    text = Desk(qa_repo).brief_text(today=dt.date(2026, 10, 3), commits=[])
    assert "Тест R-0001" in text and "Пройти тест-ран R-0001" not in text
    assert "Рішення D-0001" in text and "Відповісти на D-0001" not in text


def test_brief_survives_an_unreadable_plan(qa_repo: Path) -> None:
    uk(qa_repo)
    (qa_repo / "plan" / "roadmap.yaml").write_bytes(b"updated: \xff\n")
    text = Desk(qa_repo).brief_text(today=dt.date(2026, 10, 3), commits=[])
    assert "План: plan/roadmap.yaml не читається (desk validate)" in text and "Тест R-0001" in text


def test_brief_caps_asks_and_survives_no_git_and_no_plan(tmp_path: Path) -> None:
    root = make_repo(tmp_path)
    write_config(root, 'lang = "uk"\nmodules = ["decisions", "qa"]\n')
    for n in range(2, 8):
        add_decision(root, f"D-000{n}", title=f"Питання {n} " + "дуже довге " * 12)
    lines = Desk(root).brief_text(today=dt.date(2026, 1, 5)).splitlines()
    assert lines[0] == "Сьогодні понеділок, 5 січня 2026"
    assert lines[1] == "Від тебе:" and lines[7] == "  і ще 2"
    assert lines[2] == "  • Рішення D-0001 «Pick a palette» (блокує роботу)"  # blocking first
    assert lines[3].endswith("…") and len(lines[3]) <= BRIEF_WIDTH  # long lines are clipped
    assert lines[8] == "Тести: ранів ще немає"
    assert len(lines) == 9  # tmp_path is no git repo: no "За 7 днів"


def test_brief_with_nothing_waiting(tmp_path: Path) -> None:
    root = tmp_path / "r"
    (root / "decisions").mkdir(parents=True)
    assert Desk(root).brief_text(today=dt.date(2026, 1, 5), commits=[]).splitlines() == [
        "Today is Monday, 5 January 2026",
        "Waiting on you: nothing",
        "Last 7 days: no commits",
    ]


def test_brief_command_prints(qa_repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(qa_repo), "brief"]) == 0
    assert capsys.readouterr().out.startswith("Today is ")
    uk(qa_repo)
    assert main(["--root", str(qa_repo), "brief"]) == 0
    assert capsys.readouterr().out.startswith("Сьогодні ")


def test_summary_survives_a_broken_module(qa_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from project_desk.modules.qa.module import QAModule

    def boom(self: object) -> str:
        raise RuntimeError("boom")

    monkeypatch.setattr(QAModule, "summary", boom)
    text = Desk(qa_repo).summary_text()
    assert text.startswith("Decision Desk:") and "Plan (" in text and "Test Desk" not in text


def test_the_demo_brief() -> None:
    lines = Desk(DEMO).brief_text(today=dt.date(2026, 1, 16), commits=[]).splitlines()
    assert lines[:3] == ["Today is Friday, 16 January 2026", "Now: B3 — Notes", "Next: B6 — Hosting"]
    assert "  • Test run R-0001, ~15 min, marked 2/4: “Sign-up and the first note”" in lines
    assert not any("Walk the QA run R-0001" in ln for ln in lines)  # names a run listed above
