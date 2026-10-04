# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Content modules: each kind of file the desk shows (decisions, the plan, QA runs) is one module.

A module owns its files, its validation, its HTTP routes, its part of `summary` and `brief`, and one
tab in the UI. The core knows only this interface. Adding a kind of content is a new module plus a
line of config; see docs/modules.md.
"""

from __future__ import annotations

import importlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib.metadata import entry_points
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar

from .errors import DeskError
from .text import Issue

if TYPE_CHECKING:
    from .desk import Desk

ENTRY_POINT_GROUP = "project_desk.modules"  # plugins register modules here


@dataclass
class Request:
    """What a route handler gets: the path match, the query string and, for POST, the JSON body."""

    match: re.Match[str]
    query: dict[str, list[str]] = field(default_factory=dict)
    payload: Any = None


@dataclass
class Route:
    method: str  # "GET" or "POST"
    pattern: str  # a full-match regex on the URL path, like r"/api/plan"
    handler: Callable[[Request], Any]  # returns a JSON-able value; raises HttpError to refuse

    def __post_init__(self) -> None:
        self.regex = re.compile(self.pattern)


@dataclass
class Validation:
    label: str  # how `validate` names what it checked: "3 decision file(s)"; "" when nothing exists
    issues: list[Issue]


@dataclass
class Ask:
    """One line under "Waiting on you" in `brief`. Lower rank comes first; equal ranks keep their order."""

    rank: int
    text: str
    ids: set[str] = field(default_factory=set)  # the ids this line is about
    dedupe: bool = False  # skip this line when it names an id that another line already lists


@dataclass
class Brief:
    """The parts of `brief` that modules fill. The core adds the date and the last 7 days of commits."""

    head: list[str] = field(default_factory=list)
    asks: list[Ask] = field(default_factory=list)
    status: list[str] = field(default_factory=list)


class Module:
    """Base class. Subclasses set the class attributes and override what they use."""

    name: ClassVar[str] = ""
    label_key: ClassVar[str] = ""  # the i18n key of the tab label
    hotkey: ClassVar[str | None] = None  # `g` then this key opens the tab
    tab_order: ClassVar[int] = 50  # place in the tab bar; the first tab is the default view
    summary_order: ClassVar[int] = 50  # place in `summary` and `validate`
    defaults: ClassVar[dict[str, Any]] = {}  # the module's settings and their defaults
    ref_where: str = ""  # how messages name where this module's ids live, like "decisions/"

    def __init__(self, desk: Desk, settings: dict[str, Any]) -> None:
        self.desk = desk
        self.settings = settings

    @classmethod
    def detect(cls, root: Path, settings: dict[str, Any]) -> bool:
        """Is this module on when the config does not list modules? Usually: do its files exist."""
        return False

    @property
    def root(self) -> Path:
        return self.desk.root

    def routes(self) -> list[Route]:
        return []

    def validate(self) -> Validation:
        return Validation("", [])

    def ids(self) -> set[str] | None:
        """Every id this module knows (for other modules' cross-references); None when it cannot tell."""
        return None

    def summary(self) -> str:
        """This module's part of `summary` (English, for the AI). Must not import ruamel or markdown."""
        return ""

    def brief(self, b: Brief) -> None:
        """Add this module's lines to `brief` (the human's language). Same fast-path rule as summary."""

    def static_dir(self) -> Path:
        """Where the tab's `tab.js` (and anything it imports) lives; served at /static/modules/<name>/."""
        return Path(__file__).resolve().parent / "static" / "modules" / self.name

    def client(self) -> dict[str, Any]:
        """What the browser needs to mount the tab."""
        return {
            "name": self.name,
            "label": self.desk.i18n.t(self.label_key) if self.label_key else self.name,
            "hotkey": self.hotkey,
            "script": f"/static/modules/{self.name}/tab.js",
            "settings": self.client_settings(),
        }

    def client_settings(self) -> dict[str, Any]:
        return {}


def builtin_modules() -> dict[str, str]:
    from .modules import BUILTINS

    return dict(BUILTINS)


def available_modules() -> dict[str, str]:
    """Module name -> "package.module:Class", built-ins first, then installed plugins."""
    found = builtin_modules()
    try:
        for ep in entry_points(group=ENTRY_POINT_GROUP):
            found.setdefault(ep.name, ep.value)
    except Exception:  # a broken plugin's metadata never stops the desk
        pass
    return found


def resolve(spec: str) -> type[Module]:
    """Load "package.module:Class" (or a bare built-in name)."""
    target = builtin_modules().get(spec) or (spec if ":" in spec else available_modules().get(spec, spec))
    if ":" not in target:
        raise DeskError(
            f"unknown module '{spec}' (built-in: {', '.join(builtin_modules())}; or use 'package.module:Class')"
        )
    mod_name, _, attr = target.partition(":")
    try:
        obj = getattr(importlib.import_module(mod_name), attr)
    except (ImportError, AttributeError) as e:
        raise DeskError(f"cannot load module '{spec}' ({target}): {e}") from None
    if not (isinstance(obj, type) and issubclass(obj, Module)):
        raise DeskError(f"module '{spec}' ({target}) is not a project_desk.registry.Module subclass")
    if not obj.name:
        raise DeskError(f"module '{spec}' ({target}) has no name")
    return obj
