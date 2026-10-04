# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Where the desk's files are and how it behaves: `.project-desk.toml`, or `[tool.project-desk]` in
`pyproject.toml`. The pre-rename names, `.desk.toml` and `[tool.desk]`, still work, with a deprecation note.

Zero config works: a project with a `decisions/` folder or a `plan/roadmap.yaml` gets its desks, in
English, on 127.0.0.1:4700. Top-level keys are scalars; every table is the settings of the module with
that name.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import DeskError

CONFIG_FILE = ".project-desk.toml"
TOOL_KEY = "project-desk"  # [tool.project-desk] in pyproject.toml
LEGACY_CONFIG_FILE = ".desk.toml"  # the names before the rename to Project Desk; read, with a note
LEGACY_TOOL_KEY = "desk"
PLAN_MARKER = "plan/roadmap.yaml"  # zero config: a project with only a plan is a desk project too
LANGS = ("en", "uk")
THEMES = ("auto", "light", "dark", "contrast", "manila", "terminal")
# PROJECT_DESK_ROOT first; DESK_ROOT and DECISION_DESK_ROOT are the names older versions read.
ROOT_ENV = ("PROJECT_DESK_ROOT", "DESK_ROOT", "DECISION_DESK_ROOT")
DEFAULTS: dict[str, Any] = {
    "lang": "en",
    "theme": "auto",
    "content_lang": None,
    "port": 4700,
    "host": "127.0.0.1",
    "modules": None,  # None = auto: decisions, plus each optional module whose files exist
    "open_hint": "desk serve --open",
    "command": "desk",
}
_TYPES: dict[str, tuple[type, ...]] = {
    "lang": (str,),
    "theme": (str,),
    "content_lang": (str,),
    "port": (int,),
    "host": (str,),
    "modules": (list,),
    "open_hint": (str,),
    "command": (str,),
}


@dataclass
class Config:
    root: Path
    source: Path | None = None  # the file the settings came from; None for zero config
    lang: str = "en"
    theme: str = "auto"
    content_lang: str = "en"
    port: int = 4700
    host: str = "127.0.0.1"
    modules: list[str] | None = None
    open_hint: str = "desk serve --open"
    command: str = "desk"
    sections: dict[str, dict[str, Any]] = field(default_factory=dict)
    deprecation: str | None = None  # a note when the settings came from a pre-rename name

    def section(self, name: str) -> dict[str, Any]:
        return dict(self.sections.get(name) or {})


def _tool_table(pyproject: Path) -> tuple[dict[str, Any], str] | None:
    """The `[tool.project-desk]` table (or the legacy `[tool.desk]`) and its key; None when neither is there."""
    try:
        data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None  # not ours to complain about
    tool = data.get("tool")
    if not isinstance(tool, dict):
        return None
    for key in (TOOL_KEY, LEGACY_TOOL_KEY):
        if isinstance(tool.get(key), dict):
            return tool[key], key
    return None


def is_desk_root(d: Path) -> bool:
    if any((d / name).is_file() for name in (CONFIG_FILE, LEGACY_CONFIG_FILE, PLAN_MARKER)):
        return True
    if (d / "decisions").is_dir():
        return True
    pyproject = d / "pyproject.toml"
    return pyproject.is_file() and _tool_table(pyproject) is not None


def find_root(explicit: str | os.PathLike[str] | None = None, cwd: Path | None = None) -> Path:
    """The project root: --root, then $PROJECT_DESK_ROOT (or $DESK_ROOT), then the nearest ancestor of cwd
    with a desk config (`.project-desk.toml`, `[tool.project-desk]` in pyproject.toml, or a legacy name),
    a `decisions/` folder or a `plan/roadmap.yaml`."""
    if explicit:
        return Path(explicit).expanduser().resolve()
    for name in ROOT_ENV:
        env = os.environ.get(name)
        if env:
            return Path(env).expanduser().resolve()
    start = (cwd or Path.cwd()).resolve()
    for d in (start, *start.parents):
        if is_desk_root(d):
            return d
    raise DeskError(
        "cannot find the project root: no .project-desk.toml, [tool.project-desk], decisions/ or "
        "plan/roadmap.yaml here or above. "
        "Run `desk init` to start one, or pass --root"
    )


def _read_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        raise DeskError(f"{path.name}: invalid TOML: {e}") from None
    except (OSError, UnicodeDecodeError) as e:
        raise DeskError(f"{path.name}: cannot read it ({e})") from None


def raw_settings(root: Path) -> tuple[dict[str, Any], Path | None, str]:
    """The settings table, the file it came from and how messages name it.

    Order: `.project-desk.toml`, `[tool.project-desk]`, then the legacy `.desk.toml` and `[tool.desk]`."""
    own = root / CONFIG_FILE
    if own.is_file():
        return _read_toml(own), own, own.name
    pyproject = root / "pyproject.toml"
    table = _tool_table(pyproject) if pyproject.is_file() else None
    if table is not None and table[1] == TOOL_KEY:
        return table[0], pyproject, f"[tool.{TOOL_KEY}]"
    legacy = root / LEGACY_CONFIG_FILE
    if legacy.is_file():
        return _read_toml(legacy), legacy, legacy.name
    if table is not None:
        return table[0], pyproject, f"[tool.{LEGACY_TOOL_KEY}]"
    return {}, None, "config"


def deprecation_note(where: str) -> str | None:
    """What to tell the human when the settings use a name from before the rename."""
    if where == LEGACY_CONFIG_FILE:
        return f"{LEGACY_CONFIG_FILE} is deprecated: rename it to {CONFIG_FILE} (the contents stay the same)"
    if where == f"[tool.{LEGACY_TOOL_KEY}]":
        return f"[tool.{LEGACY_TOOL_KEY}] in pyproject.toml is deprecated: rename the table to [tool.{TOOL_KEY}]"
    return None


def load_config(root: Path) -> Config:
    raw, source, where = raw_settings(root)
    values: dict[str, Any] = dict(DEFAULTS)
    sections: dict[str, dict[str, Any]] = {}
    for key, value in raw.items():
        if isinstance(value, dict):
            sections[key] = value
            continue
        if key not in DEFAULTS:
            known = ", ".join(DEFAULTS)
            raise DeskError(f"{where}: unknown setting '{key}' (known: {known}; module settings go in a [table])")
        if isinstance(value, bool) or not isinstance(value, _TYPES[key]):
            raise DeskError(f"{where}: '{key}' must be {_TYPES[key][0].__name__}")
        values[key] = value
    if values["lang"] not in LANGS:
        raise DeskError(f"{where}: lang '{values['lang']}' is not one of: {', '.join(LANGS)}")
    if values["theme"] not in THEMES:
        raise DeskError(f"{where}: theme '{values['theme']}' is not one of: {', '.join(THEMES)}")
    modules = values["modules"]
    if modules is not None and not all(isinstance(m, str) and m for m in modules):
        raise DeskError(f"{where}: modules must be a list of module names")
    port = values["port"]
    if not 0 <= port <= 65535:
        raise DeskError(f"{where}: port {port} is out of range")
    return Config(
        root=root,
        source=source,
        lang=values["lang"],
        theme=values["theme"],
        content_lang=values["content_lang"] or values["lang"],
        port=port,
        host=values["host"],
        modules=list(modules) if modules is not None else None,
        open_hint=values["open_hint"],
        command=values["command"],
        sections=sections,
        deprecation=deprecation_note(where),
    )


def module_settings(name: str, defaults: dict[str, Any], given: dict[str, Any], where: str = "") -> dict[str, Any]:
    """A module's settings: its defaults overlaid with its config table, type-checked against the defaults."""
    where = where or f"[{name}]"
    out = dict(defaults)
    for key, value in given.items():
        if key not in defaults:
            known = ", ".join(defaults) or "none"
            raise DeskError(f"{where}: unknown setting '{key}' (known: {known})")
        want = defaults[key]
        if want is not None and (
            isinstance(value, bool) != isinstance(want, bool) or not isinstance(value, type(want))
        ):
            raise DeskError(f"{where}: '{key}' must be {type(want).__name__}")
        out[key] = value
    return out
