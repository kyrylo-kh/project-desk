# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Modules: built-ins, plugins named as `package.module:Class`, and the errors around them."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from project_desk.desk import Desk
from project_desk.errors import DeskError
from project_desk.registry import Module, available_modules, resolve

from support import make_plan, request, serving, write_config

PLUGIN = '''
from pathlib import Path

from project_desk.registry import Ask, Brief, Module, Route, Validation


class Notes(Module):
    """A tiny module: counts the files in notes/ and serves them as JSON."""

    name = "notes"
    label_key = ""          # no i18n key: the tab is labelled with the name
    hotkey = "n"
    summary_order = 40
    defaults = {"dir": "notes"}

    def files(self):
        d = self.root / self.settings["dir"]
        return sorted(p.name for p in d.glob("*.txt")) if d.is_dir() else []

    def routes(self):
        return [Route("GET", r"/api/notes", lambda req: {"files": self.files()})]

    def validate(self):
        return Validation(f"{len(self.files())} note(s)", [])

    def summary(self):
        return f"Notes: {len(self.files())}"

    def brief(self, b: Brief):
        b.asks.append(Ask(rank=5, text="Read the notes"))

    def static_dir(self):
        return Path(__file__).parent / "notes_static"
'''


@pytest.fixture
def plugin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    pkg = tmp_path / "plugins"
    (pkg / "notes_static").mkdir(parents=True)
    (pkg / "desk_notes.py").write_text(textwrap.dedent(PLUGIN))
    (pkg / "notes_static" / "tab.js").write_text("export function createTab() { return {}; }\n")
    monkeypatch.syspath_prepend(str(pkg))
    return "desk_notes:Notes"


def test_builtins_are_available() -> None:
    found = available_modules()
    assert list(found)[:3] == ["decisions", "qa", "plan"]
    assert resolve("plan").name == "plan"


def test_a_plugin_module_needs_no_core_change(repo: Path, plugin: str) -> None:
    (repo / "notes").mkdir()
    (repo / "notes" / "a.txt").write_text("x")
    write_config(repo, f'modules = ["decisions", "{plugin}"]\n\n[notes]\ndir = "notes"\n')
    desk = Desk(repo)
    assert [m.name for m in desk.modules] == ["decisions", "notes"]
    assert "Notes: 1" in desk.summary_text()
    assert desk.validate_text()[0].endswith("validate: 1 decision file(s) and 1 note(s), 0 error(s), 0 warning(s)")
    assert "Read the notes" in desk.brief_text(commits=[])
    tab = desk.client_config()["modules"][1]
    assert tab == {
        "name": "notes",
        "label": "notes",
        "hotkey": "n",
        "script": "/static/modules/notes/tab.js",
        "settings": {},
    }
    with serving(desk) as srv:
        status, _, body = request(srv, "GET", "/api/notes")
        assert status == 200 and json.loads(body) == {"files": ["a.txt"]}
        status, headers, body = request(srv, "GET", "/static/modules/notes/tab.js")
        assert status == 200 and b"createTab" in body and headers["Content-Type"].startswith("text/javascript")


def test_a_module_that_is_off_serves_nothing(repo: Path) -> None:
    with serving(Desk(repo)) as srv:
        assert request(srv, "GET", "/static/modules/plan/tab.js")[0] == 404
        assert request(srv, "GET", "/api/plan")[0] == 404


@pytest.mark.parametrize(
    ("modules", "message"),
    [
        ('["decisions", "nope"]', "unknown module 'nope'"),
        ('["decisions", "no_such_pkg:Thing"]', "cannot load module 'no_such_pkg:Thing'"),
        ('["decisions", "project_desk.errors:DeskError"]', "is not a project_desk.registry.Module subclass"),
        ('["decisions", "decisions"]', "module 'decisions' is listed twice"),
    ],
)
def test_bad_modules_are_refused(repo: Path, modules: str, message: str) -> None:
    write_config(repo, f"modules = {modules}\n")
    with pytest.raises(DeskError, match=message):
        Desk(repo)


def test_settings_for_a_module_that_is_off_are_a_typo(repo: Path) -> None:
    write_config(repo, 'modules = ["decisions"]\n\n[plan]\nfile = "x.yaml"\n')
    with pytest.raises(DeskError, match="settings for module\\(s\\) that are not enabled: plan"):
        Desk(repo)


def test_auto_mode_ignores_settings_for_a_module_whose_files_are_missing(repo: Path) -> None:
    write_config(repo, "[qa]\nmax_cases = 20\n")
    assert [m.name for m in Desk(repo).modules] == ["decisions"]


def test_auto_mode_reads_a_module_from_its_configured_place(repo: Path) -> None:
    make_plan(repo)
    (repo / "plan" / "roadmap.yaml").rename(repo / "roadmap.yaml")
    assert [m.name for m in Desk(repo).modules] == ["decisions"]
    write_config(repo, '[plan]\nfile = "roadmap.yaml"\n')
    assert [m.name for m in Desk(repo).modules] == ["plan", "decisions"]


def test_a_module_without_a_name_is_refused(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "nameless.py").write_text("from project_desk.registry import Module\nclass X(Module):\n    pass\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    with pytest.raises(DeskError, match="has no name"):
        resolve("nameless:X")
    assert Module.name == ""
