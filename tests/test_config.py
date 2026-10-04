# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Settings: zero config, `.project-desk.toml`, `[tool.project-desk]` in pyproject.toml, the legacy names,
root discovery and validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from project_desk.config import find_root, load_config
from project_desk.desk import Desk
from project_desk.errors import DeskError

from support import make_plan, make_run, write_config


def names(root: Path) -> list[str]:
    return [m.name for m in Desk(root).modules]


def test_zero_config_is_decisions_in_english_on_loopback(repo: Path) -> None:
    c = load_config(repo)
    assert (c.source, c.lang, c.content_lang, c.port, c.host, c.modules) == (None, "en", "en", 4700, "127.0.0.1", None)
    assert c.command == "desk" and c.open_hint == "desk serve --open" and c.theme == "auto"
    assert names(repo) == ["decisions"]


def test_zero_config_turns_on_the_modules_whose_files_exist(repo: Path) -> None:
    make_plan(repo)
    assert names(repo) == ["plan", "decisions"]  # the Plan is the first tab when its file exists
    make_run(repo)
    assert names(repo) == ["plan", "decisions", "qa"]  # in tab order, not discovery order
    assert [m.name for m in Desk(repo).by_summary()] == ["decisions", "qa", "plan"]  # what the AI acts on first


def test_explicit_modules_keep_the_tab_order(repo: Path) -> None:
    make_plan(repo)
    write_config(repo, 'modules = ["qa", "decisions", "plan"]\n')
    assert names(repo) == ["plan", "decisions", "qa"]
    write_config(repo, 'modules = ["decisions", "qa"]\n')  # each desk can be turned off
    assert names(repo) == ["decisions", "qa"]


def test_a_project_with_only_a_plan_is_found(tmp_path: Path) -> None:
    make_plan(tmp_path)
    deep = tmp_path / "plan"
    assert find_root(cwd=deep) == tmp_path.resolve()
    assert names(tmp_path) == ["plan", "decisions"]


def test_desk_toml(repo: Path) -> None:
    write_config(
        repo,
        'lang = "uk"\ncontent_lang = "en"\nport = 4800\nmodules = ["decisions", "plan"]\n'
        'open_hint = "make decisions"\n\n[plan]\nfile = "docs/plan.yaml"\nactions_key = "founder_actions"\n',
    )
    c = load_config(repo)
    assert c.source == repo / ".project-desk.toml" and c.deprecation is None
    assert (c.lang, c.content_lang, c.port, c.modules, c.open_hint) == (
        "uk",
        "en",
        4800,
        ["decisions", "plan"],
        "make decisions",
    )
    plan = Desk(repo).get("plan")
    assert plan is not None and plan.settings == {"file": "docs/plan.yaml", "actions_key": "founder_actions"}


def test_content_lang_follows_lang(repo: Path) -> None:
    write_config(repo, 'lang = "uk"\n')
    assert load_config(repo).content_lang == "uk"


def test_pyproject_tool_project_desk(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\n\n[tool.project-desk]\nlang = "uk"\n\n[tool.project-desk.decisions]\nopen_limit = 5\n'
    )
    c = load_config(tmp_path)
    assert c.source == tmp_path / "pyproject.toml" and c.lang == "uk" and c.deprecation is None
    assert Desk(tmp_path).get("decisions").settings["open_limit"] == 5  # type: ignore[union-attr]
    assert find_root(cwd=tmp_path) == tmp_path.resolve()
    with pytest.raises(DeskError, match=r"\[tool.project-desk\]: lang 'fr'"):
        (tmp_path / "pyproject.toml").write_text('[tool.project-desk]\nlang = "fr"\n')
        load_config(tmp_path)
    # .project-desk.toml wins over pyproject.toml.
    write_config(tmp_path, 'lang = "en"\n')
    assert load_config(tmp_path).lang == "en"


def test_the_legacy_names_still_work_with_a_note(tmp_path: Path) -> None:
    (tmp_path / ".desk.toml").write_text('lang = "uk"\n')
    c = load_config(tmp_path)
    assert c.source == tmp_path / ".desk.toml" and c.lang == "uk"
    assert c.deprecation == ".desk.toml is deprecated: rename it to .project-desk.toml (the contents stay the same)"
    assert find_root(cwd=tmp_path) == tmp_path.resolve()
    with pytest.raises(DeskError, match=r"^\.desk\.toml: lang 'fr'"):
        (tmp_path / ".desk.toml").write_text('lang = "fr"\n')
        load_config(tmp_path)
    (tmp_path / ".desk.toml").unlink()
    (tmp_path / "pyproject.toml").write_text('[tool.desk]\nlang = "uk"\n')
    c = load_config(tmp_path)
    assert c.lang == "uk" and c.deprecation is not None and "[tool.project-desk]" in c.deprecation
    # The new names win over the legacy ones.
    (tmp_path / ".desk.toml").write_text('lang = "uk"\n')
    (tmp_path / "pyproject.toml").write_text('[tool.project-desk]\nlang = "en"\n\n[tool.desk]\nlang = "uk"\n')
    c = load_config(tmp_path)
    assert c.lang == "en" and c.deprecation is None
    write_config(tmp_path, 'lang = "uk"\n')
    assert load_config(tmp_path).source == tmp_path / ".project-desk.toml"


def test_a_pyproject_without_tool_desk_is_ignored(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("this is [not toml")
    assert load_config(tmp_path).source is None


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ('langg = "en"\n', "unknown setting 'langg'"),
        ('lang = "fr"\n', "lang 'fr' is not one of: en, uk"),
        ('theme = "neon"\n', "theme 'neon' is not one of: auto, light, dark, contrast, manila, terminal"),
        ('port = "80"\n', "'port' must be int"),
        ("port = 70000\n", "port 70000 is out of range"),
        ("modules = [1]\n", "modules must be a list of module names"),
        ("open_hint = true\n", "'open_hint' must be str"),
        ("lang = \n", "invalid TOML"),
        ("[decisions]\nopen_limt = 2\n", "[decisions]: unknown setting 'open_limt'"),
        ('[decisions]\nopen_limit = "2"\n', "[decisions]: 'open_limit' must be int"),
        ("[decisions]\nopen_limit = true\n", "[decisions]: 'open_limit' must be int"),
    ],
)
def test_bad_settings_are_refused(repo: Path, text: str, message: str) -> None:
    write_config(repo, text)
    with pytest.raises(DeskError, match=message.replace("[", r"\[").replace("]", r"\]")):
        Desk(repo)


def test_find_root(tmp_path: Path, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    deep = repo / "decisions" / "material"
    assert find_root(cwd=deep) == repo  # nearest folder with decisions/... which is repo itself
    assert find_root(explicit=str(tmp_path)) == tmp_path.resolve()
    monkeypatch.setenv("PROJECT_DESK_ROOT", str(tmp_path))
    assert find_root(cwd=deep) == tmp_path.resolve()
    monkeypatch.delenv("PROJECT_DESK_ROOT")
    monkeypatch.setenv("DESK_ROOT", str(tmp_path))
    assert find_root(cwd=deep) == tmp_path.resolve()
    monkeypatch.delenv("DESK_ROOT")
    monkeypatch.setenv("DECISION_DESK_ROOT", str(repo))
    assert find_root(cwd=tmp_path) == repo.resolve()
    monkeypatch.delenv("DECISION_DESK_ROOT")
    other = tmp_path / "other" / "sub"
    other.mkdir(parents=True)
    (tmp_path / "other" / ".project-desk.toml").write_text("")
    assert find_root(cwd=other) == (tmp_path / "other").resolve()


def test_find_root_fails_clearly(tmp_path: Path) -> None:
    lone = tmp_path / "lone"
    lone.mkdir()
    with pytest.raises(DeskError, match="desk init"):
        find_root(cwd=lone)
