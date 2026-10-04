# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The thin CLI: each command's output and exit code, on the demo project and on fixtures."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from project_desk import __version__
from project_desk.cli import main

from support import DEMO, add_decision, parked, status, write_config


def run(capsys: pytest.CaptureFixture[str], *args: str) -> tuple[int, str, str]:
    code = main(list(args))
    out = capsys.readouterr()
    return code, out.out, out.err


@pytest.fixture
def demo(tmp_path: Path) -> Path:
    root = tmp_path / "demo"
    shutil.copytree(DEMO, root)
    return root


def test_list(capsys: pytest.CaptureFixture[str], demo: Path) -> None:
    code, out, _ = run(capsys, "--root", str(demo), "list")
    assert code == 0
    lines = out.splitlines()
    assert lines[0].split() == ["ID", "STATUS", "PRIORITY", "BLOCKING", "TITLE"]
    assert lines[1].split()[:4] == ["D-0001", "pending", "high", "yes"]
    assert "parked (b)" in lines[2]
    code, out, _ = run(capsys, "--root", str(demo), "list", "--status", "answered,needs-info")
    assert [ln.split()[0] for ln in out.splitlines()[1:]] == ["D-0003", "D-0004"]


def test_list_shows_parked(capsys: pytest.CaptureFixture[str], repo: Path) -> None:
    (repo / "decisions" / "D-0001-pick-a-palette.md").write_text(parked(default="a"), encoding="utf-8")
    _, out, _ = run(capsys, "--root", str(repo), "list")
    assert "parked (a)" in out


def test_list_rejects_an_unknown_status(capsys: pytest.CaptureFixture[str], repo: Path) -> None:
    code, _, err = run(capsys, "--root", str(repo), "list", "--status", "done")
    assert code != 0 and "done" in err


def test_summary_and_validate_on_the_demo(capsys: pytest.CaptureFixture[str], demo: Path) -> None:
    code, out, _ = run(capsys, "--root", str(demo), "summary")
    assert code == 0
    assert out.startswith("Decision Desk: 2 pending (1 blocking, 1 parked)")
    assert "Test Desk: 1 waiting for the human" in out and "Now: B3 — Notes" in out
    code, out, _ = run(capsys, "--root", str(demo), "validate")
    assert (code, out.strip()) == (
        0,
        "validate: 4 decision file(s) and 1 QA run(s) and plan/roadmap.yaml, 0 error(s), 0 warning(s)",
    )


def test_summary_is_empty_and_quiet_with_nothing_open(capsys: pytest.CaptureFixture[str], repo: Path) -> None:
    (repo / "decisions" / "D-0001-pick-a-palette.md").write_text(status(parked(), "resolved"), encoding="utf-8")
    code, out, _ = run(capsys, "--root", str(repo), "summary")
    assert code == 0 and "pending" not in out


def test_validate_fails_on_errors(capsys: pytest.CaptureFixture[str], repo: Path) -> None:
    add_decision(repo, "D-0002", priority="urgent")
    code, out, _ = run(capsys, "--root", str(repo), "validate")
    assert code == 1 and "decisions/D-0002-x.md: error:" in out and "priority" in out


def test_new_scaffolds_the_next_id(capsys: pytest.CaptureFixture[str], repo: Path) -> None:
    code, out, _ = run(
        capsys,
        "--root",
        str(repo),
        "new",
        "--title",
        "Pick a font",
        "--type",
        "design",
        "--group",
        "design",
        "--blocking",
    )
    assert (code, out.strip()) == (0, "decisions/D-0002-pick-a-font.md")
    text = (repo / "decisions" / "D-0002-pick-a-font.md").read_text(encoding="utf-8")
    assert "id: D-0002" in text and "blocking: true" in text and "status: pending" in text


def test_new_refuses_an_unknown_type(capsys: pytest.CaptureFixture[str], repo: Path) -> None:
    write_config(repo, '[decisions]\ntypes = ["product"]\n')
    code, _, err = run(capsys, "--root", str(repo), "new", "--title", "X", "--type", "design", "--group", "g")
    assert code == 2 and "design" in err and not list(repo.glob("decisions/D-0002-*"))


def test_a_bad_config_is_one_clear_line(capsys: pytest.CaptureFixture[str], repo: Path) -> None:
    write_config(repo, 'lang = "fr"\n')
    code, _, err = run(capsys, "--root", str(repo), "validate")
    assert code == 2 and err.strip() == "desk: .project-desk.toml: lang 'fr' is not one of: en, uk"
    # The SessionStart hook still exits 0, and tells the AI in one line.
    code, out, _ = run(capsys, "--root", str(repo), "summary")
    assert code == 0 and out.startswith("Project Desk: .project-desk.toml: lang 'fr'") and "desk validate" in out


def test_a_legacy_config_name_gets_a_note_on_stderr(capsys: pytest.CaptureFixture[str], repo: Path) -> None:
    (repo / ".desk.toml").write_text('lang = "en"\n')
    code, out, err = run(capsys, "--root", str(repo), "validate")
    assert code == 0 and out.startswith("validate:")
    assert (
        err.strip()
        == "desk: note: .desk.toml is deprecated: rename it to .project-desk.toml (the contents stay the same)"
    )
    code, out, err = run(capsys, "--root", str(repo), "summary")  # the AI's hook stays as it was
    assert code == 0 and err == ""


def test_summary_outside_a_project_is_silent(
    capsys: pytest.CaptureFixture[str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    assert run(capsys, "summary") == (0, "", "")


def test_version_and_help(capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "--version")
    assert code == 0 and __version__ in out
    code, out, _ = run(capsys, "--help")
    assert code == 0 and all(c in out for c in ("brief", "init", "list", "new", "serve", "summary", "validate"))


def test_python_dash_m(demo: Path) -> None:
    out = subprocess.run(
        [sys.executable, "-m", "project_desk", "--root", str(demo), "validate"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert out.returncode == 0 and "0 error(s)" in out.stdout
