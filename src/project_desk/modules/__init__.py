# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The built-in content modules. Each is a package with a `module.py` that defines a Module subclass."""

from __future__ import annotations

BUILTINS = {
    "decisions": "project_desk.modules.decisions.module:DecisionsModule",
    "qa": "project_desk.modules.qa.module:QAModule",
    "plan": "project_desk.modules.plan.module:PlanModule",
}
# Zero config: the decisions desk always, and the plan and test desks when their files exist. The tabs are
# then ordered by each module's tab_order: Plan, Decision Desk, Test Desk.
AUTO = ("plan", "decisions", "qa")
