# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from support import NOW, make_plan, make_repo, make_run


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path)


@pytest.fixture
def plan_repo(repo: Path) -> Path:
    make_plan(repo)
    return repo


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin the time every write stamps."""
    import project_desk.text

    monkeypatch.setattr(project_desk.text, "now_iso", lambda: NOW)


@pytest.fixture
def qa_repo(plan_repo: Path, clock: None) -> Path:
    make_run(plan_repo)
    return plan_repo


@pytest.fixture(autouse=True)
def _no_root_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("PROJECT_DESK_ROOT", "DESK_ROOT", "DECISION_DESK_ROOT"):
        monkeypatch.delenv(name, raising=False)
