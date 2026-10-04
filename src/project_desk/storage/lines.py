# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Line-level YAML helpers shared by the fast reader (`quick`) and the surgical editor (`edits`)."""

from __future__ import annotations

import json
import re

FM_RE = re.compile(r"\A(---[ \t]*\n)(.*?)(^---[ \t]*(?:\n|\Z))", re.S | re.M)
KEY_RE = re.compile(r"^(?P<indent> *)(?P<key>[A-Za-z_][\w-]*)[ \t]*:(?P<rest>(?:[ \t].*)?)$")
BLOCK_HEADER_RE = re.compile(r"^[|>](?:[1-9][+-]?|[+-][1-9]?)?$")
TRUE_WORDS = ("true", "yes", "on")


def split_value_comment(rest: str) -> tuple[str, str]:
    """Split the text after 'key:' into (value, comment). The comment keeps its leading spaces."""
    quote_ch = None
    i, n = 0, len(rest)
    while i < n:
        c = rest[i]
        if quote_ch == '"':
            if c == "\\":
                i += 2
                continue
            if c == '"':
                quote_ch = None
        elif quote_ch == "'":
            if c == "'":
                if i + 1 < n and rest[i + 1] == "'":
                    i += 2
                    continue
                quote_ch = None
        elif c in "\"'" and not rest[:i].strip():
            quote_ch = c
        elif c == "#" and (i == 0 or rest[i - 1] in " \t"):
            j = i
            while j > 0 and rest[j - 1] in " \t":
                j -= 1
            return rest[:j], rest[j:]
        i += 1
    return rest, ""


def indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def significant(lines: list[str], i: int) -> int:
    """Index of the next line that is not blank and not a comment (len(lines) at the end)."""
    while i < len(lines) and (not lines[i].strip() or lines[i].lstrip().startswith("#")):
        i += 1
    return i


def quick_scalar(value: str) -> str | None:
    """A flow scalar as text, without a YAML import. Good enough for the summary, never for writes."""
    v = value.strip()
    if v in ("", "~") or v.lower() == "null":
        return None
    if len(v) >= 2 and v[0] == v[-1] == '"':
        try:
            out = json.loads(v)
        except ValueError:
            return v[1:-1]
        return out if isinstance(out, str) else v[1:-1]
    if len(v) >= 2 and v[0] == v[-1] == "'":
        return v[1:-1].replace("''", "'")
    return v


def is_dash(line: str) -> bool:
    s = line.strip()
    return s == "-" or s.startswith("- ")
