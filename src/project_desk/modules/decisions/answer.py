# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The human's answer: the only write the desk makes to a decision file."""

from __future__ import annotations

import copy
from typing import Any

from ...errors import HttpError
from ...storage.doc import Doc
from ...storage.edits import edit_frontmatter, literal_ok, set_child, set_top
from .model import option_ids

COMMENT_LIMIT = 20000


def answer_frontmatter(fm: str, data: dict[str, Any], status: str, choice: Any, comment: str, answered_at: str) -> str:
    """New frontmatter text with only status and answer.{choice,comment,answered_at} changed."""
    expected = copy.deepcopy(data)
    expected["status"] = status
    answer = dict(expected.get("answer") or {}) if isinstance(expected.get("answer"), dict) else {}
    answer.update({"choice": choice, "comment": comment, "answered_at": answered_at})
    expected["answer"] = answer

    def surgical(lines: list[str]) -> None:
        set_top(lines, "status", status, "ident")
        set_child(lines, "answer", "choice", choice, "ident")
        set_child(lines, "answer", "comment", comment, "text")
        set_child(lines, "answer", "answered_at", answered_at, "text")

    def fallback(doc: Any) -> None:
        from ruamel.yaml.comments import CommentedMap
        from ruamel.yaml.scalarstring import DoubleQuotedScalarString, LiteralScalarString

        doc["status"] = status
        ans = doc.get("answer")
        if not isinstance(ans, dict):
            ans = CommentedMap()
            keys = list(doc.keys())
            pos = keys.index("resolution") if "resolution" in keys else len(keys)
            if "answer" in doc:
                doc["answer"] = ans
            else:
                doc.insert(pos, "answer", ans)
        ans["choice"] = choice
        ans["comment"] = LiteralScalarString(comment) if literal_ok(comment) else DoubleQuotedScalarString(comment)
        ans["answered_at"] = DoubleQuotedScalarString(answered_at)

    return edit_frontmatter(fm, expected, surgical, fallback)


def check_answer(doc: Doc, did: str, payload: dict[str, Any]) -> tuple[str, str | None, str]:
    """(new status, choice, comment) from the UI's payload, or HttpError. The etag is checked by the caller."""
    status = doc.data.get("status")
    if status in ("resolved", "withdrawn"):
        raise HttpError(409, f"{did} is {status}; open a follow-up decision instead")
    needs_info = bool(payload.get("needs_info"))
    raw_choice = payload.get("choice")
    choice = None if raw_choice in (None, "") else str(raw_choice)
    comment = str(payload.get("comment") or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(comment) > COMMENT_LIMIT:
        raise HttpError(400, "comment is too long")
    if choice is not None and choice != "other" and choice not in option_ids(doc.data):
        raise HttpError(400, f"'{choice}' is not an option of {did}")
    if needs_info:
        if not comment:
            raise HttpError(400, "write your question in the comment")
    else:
        if choice is None:
            raise HttpError(400, "pick an option (or Other)")
        if choice == "other" and not comment:
            raise HttpError(400, "explain 'Other' in the comment")
    return ("needs-info" if needs_info else "answered"), choice, comment
