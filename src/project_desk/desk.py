# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The desk: one project root, its config, and the content modules that are switched on."""

from __future__ import annotations

import datetime as dt
import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .config import Config, load_config, module_settings
from .errors import DeskError
from .i18n import Translator
from .registry import Ask, Brief, Module, Validation, resolve
from .text import Issue

BRIEF_ASKS = 5  # lines under "Waiting on you"
BRIEF_COMMITS = 8  # lines under "Last 7 days"
BRIEF_WIDTH = 100  # longer lines are clipped


def clip(s: str, width: int = BRIEF_WIDTH) -> str:
    return s if len(s) <= width else s[: width - 1].rstrip() + "…"


def git_subjects(root: Path) -> list[str] | None:
    """Commit subjects of the last 7 days; None when git is missing or this is not a repo."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "log", "--since=7.days", "--format=%s"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if out.returncode != 0:
        return None
    return [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]


class Desk:
    def __init__(self, root: Path, config: Config | None = None) -> None:
        self.root = root.resolve()
        self.config = config or load_config(self.root)
        self.i18n = Translator(self.config.lang)
        self.lock = threading.Lock()
        self.now: Callable[[], str] | None = None  # tests pin the clock; None means the local time
        self.modules: list[Module] = self._load_modules()

    # ---------------------------------------------------------------- modules

    def _load_modules(self) -> list[Module]:
        names = self.config.modules
        auto = names is None
        if names is None:
            from .modules import AUTO

            names = list(AUTO)
        seen: set[str] = set()
        out: list[Module] = []
        for spec in names:
            cls = resolve(spec)
            if cls.name in seen:
                raise DeskError(f"module '{cls.name}' is listed twice")
            seen.add(cls.name)
            where = f"[{cls.name}]"
            settings = module_settings(cls.name, cls.defaults, self.config.section(cls.name), where)
            if auto and cls.name != "decisions" and not cls.detect(self.root, settings):
                continue
            out.append(cls(self, settings))
        unknown = set(self.config.sections) - {m.name for m in out}
        if not auto and unknown:
            # A table for a module that is not on is most likely a typo in `modules`.
            raise DeskError(f"settings for module(s) that are not enabled: {', '.join(sorted(unknown))}")
        return sorted(out, key=lambda m: m.tab_order)

    def by_summary(self) -> list[Module]:
        """The modules in `summary` and `validate` order: what the AI must act on first comes first."""
        return sorted(self.modules, key=lambda m: m.summary_order)

    def get(self, name: str) -> Module | None:
        return next((m for m in self.modules if m.name == name), None)

    def rel(self, p: Path) -> str:
        return p.resolve().relative_to(self.root).as_posix()

    def timestamp(self) -> str:
        from .text import now_iso

        return self.now() if self.now else now_iso()

    # ---------------------------------------------------------------- whole-desk views

    def validate_all(self) -> tuple[list[Validation], list[Issue]]:
        results = [m.validate() for m in self.by_summary()]
        issues = [i for r in results for i in r.issues]
        return results, issues

    def validate_text(self) -> tuple[str, int]:
        """`validate`'s output and its exit code (1 when there is any error)."""
        results, issues = self.validate_all()
        lines = [
            f"{i['file']}: {i['level']}: {i['message']}"
            for i in sorted(issues, key=lambda i: (i["file"], i["level"] != "error"))
        ]
        errors = sum(1 for i in issues if i["level"] == "error")
        warnings = len(issues) - errors
        labels = " and ".join(r.label for r in results if r.label) or "nothing"
        lines.append(f"validate: {labels}, {errors} error(s), {warnings} warning(s)")
        return "\n".join(lines), 1 if errors else 0

    def summary_text(self) -> str:
        """The AI-facing status for a SessionStart hook. A broken module never hides the others."""
        parts = []
        for m in self.by_summary():
            try:
                parts.append(m.summary())
            except Exception:  # never break a session start
                pass
        return "\n".join(p for p in parts if p)

    def brief_text(self, today: dt.date | None = None, commits: list[str] | None = None) -> str:
        """One terminal screen for the human, in the UI language: now and next, what waits on them, the week."""
        i = self.i18n
        today = today or dt.date.today()
        lines = [
            i.t(
                "brief.today",
                weekday=i.seq("date.weekdays")[today.weekday()],
                day=today.day,
                month=i.seq("date.months_of")[today.month - 1],
                year=today.year,
            )
        ]
        b = Brief()
        for m in self.modules:
            try:
                m.brief(b)
            except Exception:
                pass
        lines += [clip(s) for s in b.head]
        asks = sorted(b.asks, key=lambda a: a.rank)
        listed = {x for a in asks if not a.dedupe for x in a.ids}
        kept: list[Ask] = []
        for a in asks:
            if a.dedupe and any(_names(a.text, x) for x in listed):
                continue  # an action that points at something already listed above
            kept.append(a)
        lines.append(i.t("brief.waiting") + ("" if kept else i.t("brief.nothing")))
        lines += [clip(f"  • {a.text}") for a in kept[:BRIEF_ASKS]]
        if len(kept) > BRIEF_ASKS:
            lines.append(i.t("brief.more", n=len(kept) - BRIEF_ASKS))
        lines += [clip(s) for s in b.status]
        commits = git_subjects(self.root) if commits is None else commits
        if commits is not None:
            lines.append(i.t("brief.week") + ("" if commits else i.t("brief.no_commits")))
            lines += [clip(f"  • {c}") for c in commits[:BRIEF_COMMITS]]
            if len(commits) > BRIEF_COMMITS:
                lines.append(i.t("brief.more", n=len(commits) - BRIEF_COMMITS))
        return "\n".join(lines)

    def client_config(self) -> dict[str, Any]:
        """GET /api/config: what the browser needs to build the tabs and speak the UI language."""
        from .i18n import load_locale

        return {
            "lang": self.config.lang,
            "theme": self.config.theme,
            "content_lang": self.config.content_lang,
            "root": self.root.name,
            "command": self.config.command,
            "strings": load_locale("en") | load_locale(self.config.lang),
            "modules": [m.client() for m in self.modules],
        }


def _names(text: str, ident: str) -> bool:
    """Does `text` mention `ident` as a whole word?"""
    import re

    return re.search(rf"(?<![\w-]){re.escape(ident)}(?![\w-])", text) is not None
