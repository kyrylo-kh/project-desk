# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""`desk init`: scaffold a project. It never overwrites a file; it reports what it created and kept."""

from __future__ import annotations

import json
import os
import tempfile
from importlib import resources
from pathlib import Path
from typing import Any

from .errors import DeskError

HOOK_COMMAND = 'cd "$CLAUDE_PROJECT_DIR" && desk summary || true'
HOOK_ENTRY = {"hooks": [{"type": "command", "command": HOOK_COMMAND, "timeout": 30}]}
HOOK_SNIPPET = json.dumps({"hooks": {"SessionStart": [HOOK_ENTRY]}}, indent=2)


def template(rel: str) -> str:
    return resources.files("project_desk").joinpath("templates", *rel.split("/")).read_text(encoding="utf-8")


def config_text(lang: str, modules: list[str]) -> str:
    listed = ", ".join(f'"{m}"' for m in modules)
    lines = [
        "# Project Desk settings. Every key is optional; see docs/configuration.md for the full list.",
        f'lang = "{lang}"            # UI and `desk brief` language: "en" or "uk"',
        '# theme = "auto"            # auto (follows the OS), light, dark, contrast, manila or terminal',
        f"modules = [{listed}]",
        "# port = 4700",
        '# open_hint = "desk serve --open"  # how `desk summary` tells the AI to open the desk',
        "",
        "[decisions]",
        '# dir = "decisions"',
        '# types = ["product", "design", "architecture", "data", "process", "brand"]',
        "# open_limit = 3              # `validate` warns when more decisions than this are open (0: off)",
    ]
    if "plan" in modules:
        lines += ["", "[plan]", '# file = "plan/roadmap.yaml"', '# actions_key = "actions"']
    if "qa" in modules:
        lines += ["", "[qa]", '# dir = "qa/runs"', "# max_cases = 15", '# note_key = "overall_note"']
    return "\n".join(lines) + "\n"


def _write_new(path: Path, text: str) -> bool:
    """Create `path` with `text`. False when it already exists (it is never touched)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(path, "x", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    except FileExistsError:
        return False
    return True


def merge_hook(settings: Path) -> str:
    """Add the SessionStart hook to a Claude Code settings file. Keeps every other key as it is."""
    data: dict[str, Any] = {}
    if settings.exists():
        try:
            data = json.loads(settings.read_text(encoding="utf-8") or "{}")
        except (OSError, json.JSONDecodeError) as e:
            raise DeskError(f"{settings}: cannot read it as JSON ({e}); add the hook by hand") from None
        if not isinstance(data, dict):
            raise DeskError(f"{settings}: not a JSON object; add the hook by hand")
    hooks = data.setdefault("hooks", {})
    if not isinstance(hooks, dict):
        raise DeskError(f"{settings}: 'hooks' is not an object; add the hook by hand")
    starts = hooks.setdefault("SessionStart", [])
    if not isinstance(starts, list):
        raise DeskError(f"{settings}: 'hooks.SessionStart' is not a list; add the hook by hand")
    for entry in starts:
        for h in entry.get("hooks", []) if isinstance(entry, dict) else []:
            if isinstance(h, dict) and "desk" in str(h.get("command", "")) and "summary" in str(h.get("command", "")):
                return "kept the SessionStart hook (a desk summary hook is already there)"
    starts.append(HOOK_ENTRY)
    settings.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{settings.name}.", suffix=".tmp", dir=settings.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, settings)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return f"added the SessionStart hook to {settings.name}"


def init_project(
    root: Path, *, plan: bool = False, qa: bool = False, skills: bool = False, lang: str = "en", hook: bool = False
) -> list[str]:
    if lang not in ("en", "uk"):
        raise DeskError(f"lang '{lang}' is not one of: en, uk")
    root.mkdir(parents=True, exist_ok=True)
    modules = (["plan"] if plan else []) + ["decisions"] + (["qa"] if qa else [])
    files: list[tuple[str, str]] = [
        (".project-desk.toml", config_text(lang, modules)),
        ("decisions/README.md", template("decisions/README.md")),
    ]
    if plan:
        files += [
            ("plan/README.md", template("plan/README.md")),
            ("plan/roadmap.yaml", template("plan/roadmap.yaml")),
        ]
    if qa:
        files += [("qa/README.md", template("qa/README.md"))]
    if skills:
        files += [(".claude/skills/decision-desk/SKILL.md", template("skills/decision-desk/SKILL.md"))]
        if qa:
            files += [(".claude/skills/test-desk/SKILL.md", template("skills/test-desk/SKILL.md"))]
    report = []
    for rel, text in files:
        created = _write_new(root / rel, text)
        report.append(f"{'created' if created else 'kept   '} {rel}" + ("" if created else " (exists)"))
    if qa:
        (root / "qa" / "runs").mkdir(parents=True, exist_ok=True)
    if hook:
        report.append(merge_hook(root / ".claude" / "settings.json"))
    return report
