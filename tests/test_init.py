# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""`desk init`: scaffolds a working project, never overwrites, and touches settings.json only with --hook."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from project_desk.cli import main
from project_desk.desk import Desk
from project_desk.errors import DeskError
from project_desk.scaffold import HOOK_COMMAND, init_project, merge_hook


def files(root: Path) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file())


def test_minimal_init_is_a_valid_empty_desk(tmp_path: Path) -> None:
    report = init_project(tmp_path)
    assert report == ["created .project-desk.toml", "created decisions/README.md"]
    assert files(tmp_path) == [".project-desk.toml", "decisions/README.md"]
    desk = Desk(tmp_path)
    assert [m.name for m in desk.modules] == ["decisions"]
    assert desk.validate_text() == ("validate: 0 decision file(s), 0 error(s), 0 warning(s)", 0)


def test_full_init_validates_clean(tmp_path: Path) -> None:
    init_project(tmp_path, plan=True, qa=True, skills=True, lang="uk")
    assert files(tmp_path) == [
        ".claude/skills/decision-desk/SKILL.md",
        ".claude/skills/test-desk/SKILL.md",
        ".project-desk.toml",
        "decisions/README.md",
        "plan/README.md",
        "plan/roadmap.yaml",
        "qa/README.md",
    ]
    assert (tmp_path / "qa" / "runs").is_dir()
    desk = Desk(tmp_path)
    assert desk.config.lang == "uk"
    assert [m.name for m in desk.modules] == ["plan", "decisions", "qa"]
    text, code = desk.validate_text()
    assert code == 0 and "0 error(s), 0 warning(s)" in text
    assert not (tmp_path / ".claude" / "settings.json").exists()  # only with --hook


def test_init_never_overwrites(tmp_path: Path) -> None:
    (tmp_path / "decisions").mkdir()
    (tmp_path / "decisions" / "README.md").write_text("mine\n")
    (tmp_path / ".project-desk.toml").write_text('lang = "uk"\n')
    report = init_project(tmp_path, plan=True)
    assert "kept    .project-desk.toml (exists)" in report and "kept    decisions/README.md (exists)" in report
    assert "created plan/roadmap.yaml" in report
    assert (tmp_path / "decisions" / "README.md").read_text() == "mine\n"
    assert (tmp_path / ".project-desk.toml").read_text() == 'lang = "uk"\n'
    again = init_project(tmp_path, plan=True)
    assert all(line.startswith("kept") for line in again)


def test_hook_merge_keeps_other_settings(tmp_path: Path) -> None:
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir()
    other = {"type": "command", "command": "echo hi"}
    settings.write_text(
        json.dumps({"permissions": {"allow": ["Bash(ls)"]}, "hooks": {"SessionStart": [{"hooks": [other]}]}})
    )
    assert merge_hook(settings).startswith("added")
    data = json.loads(settings.read_text())
    assert data["permissions"] == {"allow": ["Bash(ls)"]}
    starts = data["hooks"]["SessionStart"]
    assert starts[0] == {"hooks": [other]} and starts[1]["hooks"][0]["command"] == HOOK_COMMAND
    before = settings.read_text()
    assert merge_hook(settings).startswith("kept")  # idempotent
    assert settings.read_text() == before


@pytest.mark.parametrize("text", ["[1, 2]", "{not json", '{"hooks": []}', '{"hooks": {"SessionStart": {}}}'])
def test_hook_merge_refuses_what_it_cannot_read(tmp_path: Path, text: str) -> None:
    settings = tmp_path / "settings.json"
    settings.write_text(text)
    with pytest.raises(DeskError, match="add the hook by hand"):
        merge_hook(settings)
    assert settings.read_text() == text


def test_cli_init_prints_the_hook_snippet_without_touching_settings(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--root", str(tmp_path), "init", "--qa"]) == 0
    out = capsys.readouterr().out
    assert "created qa/README.md" in out and '"SessionStart"' in out and HOOK_COMMAND.replace('"', '\\"') in out
    assert not (tmp_path / ".claude").exists()


def test_cli_init_with_hook(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--root", str(tmp_path), "init", "--all", "--hook"]) == 0
    out = capsys.readouterr().out
    assert "added the SessionStart hook to settings.json" in out and '"SessionStart"' not in out
    assert json.loads((tmp_path / ".claude" / "settings.json").read_text())["hooks"]["SessionStart"]
