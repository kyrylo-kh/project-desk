# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Small, dependency-free helpers for values read from frontmatter."""

from __future__ import annotations

import datetime as dt
from typing import Any

from .errors import HttpError

Issue = dict[str, str]


def issue(file: str, level: str, message: str) -> Issue:
    """One validation finding. `level` is "error" or "warning"."""
    return {"file": file, "level": level, "message": message}


def as_list(v: Any) -> list[Any]:
    return v if isinstance(v, list) else []


def one_line(v: Any) -> str:
    """Any scalar (or list of them) as one plain line: line breaks and runs of spaces become one space."""
    if v is None:
        return ""
    if isinstance(v, list):
        v = " ".join(str(x) for x in v if x is not None)
    return " ".join(str(v).split())


def text_value(v: Any) -> str:
    """Free text (a note, `setup`, `ai`) with its line breaks: no trailing spaces, no blank edges. None is ""."""
    if v is None:
        return ""
    if isinstance(v, list):
        v = "\n".join(str(x) for x in v if x is not None)
    return "\n".join(ln.rstrip() for ln in str(v).replace("\r\n", "\n").split("\n")).strip("\n")


def tldr_text(data: dict[str, Any]) -> str:
    """The optional `tldr` as plain text: one line per line, no trailing spaces, no blank edges."""
    return text_value(data.get("tldr"))


def about_text(data: dict[str, Any]) -> str:
    """The optional `about` as one plain line."""
    return one_line(data.get("about"))


def clean_text(v: Any, limit: int = 20000) -> str:
    """Human input from the UI: normalised line breaks, trimmed, and bounded."""
    s = str(v or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    if len(s) > limit:
        raise HttpError(400, "the text is too long")
    return s


def now_iso() -> str:
    """The local time as an ISO 8601 string with its offset, to the second."""
    return dt.datetime.now().astimezone().replace(microsecond=0).isoformat()


def is_date(v: Any) -> bool:
    try:
        dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return False
    return True
