# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The human's marks on a run: the only writes the desk makes to a run file.

It writes `status` (ready -> in-progress on the first mark, -> done on finish), the run-level note and
each case's `result`, `note` and `at`, and nothing else.
"""

from __future__ import annotations

import copy
from typing import Any

from ...storage.edits import edit_frontmatter, set_item_key, set_top_or_insert, styled
from ...text import as_list, one_line

CASE_STYLES = {"result": "ident", "note": "text", "at": "text"}


def run_frontmatter(
    fm: str,
    data: dict[str, Any],
    top: dict[str, Any],
    case_id: str | None = None,
    case: dict[str, Any] | None = None,
    note_key: str = "overall_note",
) -> str:
    """New frontmatter text with only the `top` keys and one case's `case` keys changed. The line edit is
    re-parsed and checked; on any doubt, a ruamel round trip."""
    case = case or {}
    top_styles = {"status": "ident", note_key: "text"}
    expected = copy.deepcopy(data)
    expected.update(top)
    if case_id is not None:
        for c in as_list(expected.get("cases")):
            if isinstance(c, dict) and one_line(c.get("id")) == case_id:
                c.update(case)
                break

    def surgical(lines: list[str]) -> None:
        for key, value in top.items():
            set_top_or_insert(lines, key, value, top_styles[key], before="cases")
        if case_id is not None:
            for key, value in case.items():
                set_item_key(lines, "cases", case_id, key, value, CASE_STYLES[key])

    def fallback(doc: Any) -> None:
        for key, value in top.items():
            doc[key] = styled(value, top_styles[key])
        for c in as_list(doc.get("cases")):
            if case_id is not None and isinstance(c, dict) and one_line(c.get("id")) == case_id:
                for key, value in case.items():
                    c[key] = styled(value, CASE_STYLES[key])
                break

    return edit_frontmatter(fm, expected, surgical, fallback)
