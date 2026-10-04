# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""A small block-style YAML reader for the fast path (summary and brief), with no YAML import.

It reads maps, lists, `[a, b]` flow lists, and plain, quoted and block scalars: the subset the desk's
files use. It is never used for writes. `validate` warns when it and ruamel disagree about a file, so a
file that drifts outside the subset is caught.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .lines import (
    BLOCK_HEADER_RE,
    FM_RE,
    KEY_RE,
    indent_of,
    quick_scalar,
    significant,
    split_value_comment,
)


def quick_fields(fm: str, keys: Iterable[str]) -> dict[str, str | None]:
    """The top-level `keys` of a frontmatter, read line by line (plain, quoted and block scalars)."""
    wanted = set(keys)
    lines = fm.split("\n")
    out: dict[str, str | None] = {}
    i = 0
    while i < len(lines):
        km = KEY_RE.match(lines[i])
        i += 1
        if not km or km["indent"] or km["key"] not in wanted:
            continue
        value = split_value_comment(km["rest"])[0].strip()
        more = []
        while i < len(lines) and (not lines[i].strip() or lines[i][:1] in " \t"):
            more.append(lines[i].strip())
            i += 1
        if BLOCK_HEADER_RE.match(value):
            text = " ".join(ln for ln in more if ln)  # only one-line output needs these
            out[km["key"]] = text or None
        else:
            out[km["key"]] = quick_scalar(" ".join([value, *(ln for ln in more if ln)]))
    return out


def read_frontmatter_text(path: Path) -> str | None:
    """The raw frontmatter of a Markdown file, or None when it has none. Raises OSError/UnicodeDecodeError."""
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text.lstrip("﻿").replace("\r\n", "\n"))
    return m.group(2) if m else None


def _flow_list(text: str) -> list[Any]:
    inner, out, cur, quote = text.strip()[1:-1], [], "", ""
    for ch in inner:
        if quote:
            cur += ch
            quote = "" if ch == quote else quote
        elif ch in "\"'":
            cur, quote = cur + ch, ch
        elif ch == ",":
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [quick_scalar(x) for x in out if x.strip()]


def _value(lines: list[str], i: int, col: int, rest: str) -> tuple[Any, int]:
    """The value after `key:` (text `rest`) on line i-1, whose key sits at column `col`."""
    v = split_value_comment(rest)[0].strip()
    if BLOCK_HEADER_RE.match(v):
        more = []
        while i < len(lines) and (not lines[i].strip() or indent_of(lines[i]) > col):
            more.append(lines[i].strip())
            i += 1
        return " ".join(ln for ln in more if ln) or None, i
    if v == "":
        j = significant(lines, i)
        if j < len(lines):
            ind, s = indent_of(lines[j]), lines[j].strip()
            dash = s == "-" or s.startswith("- ")
            if (ind > col and (dash or KEY_RE.match(lines[j]))) or (ind == col and dash):
                return _block(lines, j)
            if ind > col:  # a plain scalar that starts on the next line
                return _value(lines, j + 1, col, " " + s)
        return None, i
    more = [v]
    while i < len(lines) and (not lines[i].strip() or indent_of(lines[i]) > col):
        if not lines[i].lstrip().startswith("#"):
            more.append(split_value_comment(lines[i])[0].strip() if v.startswith("[") else lines[i].strip())
        i += 1
    text = " ".join(x for x in more if x)
    if text.startswith("[") and text.endswith("]"):
        return _flow_list(text), i
    return quick_scalar(text), i


def _block(lines: list[str], i: int) -> tuple[Any, int]:
    """A block mapping or sequence starting at line i (a significant line)."""
    col, s = indent_of(lines[i]), lines[i].strip()
    if s == "-" or s.startswith("- "):
        seq: list[Any] = []
        while True:
            i = significant(lines, i)
            if i >= len(lines) or indent_of(lines[i]) != col:
                return seq, i
            s = lines[i].strip()
            if not (s == "-" or s.startswith("- ")):
                return seq, i
            body = s[1:].lstrip()
            value: Any
            if not body or body.startswith("#"):
                value, i = _value(lines, i + 1, col, "")
            elif KEY_RE.match(body):  # "- key: value" opens a mapping at the body's column
                lines[i] = " " * (len(lines[i]) - len(lines[i].lstrip()) + len(s) - len(body)) + body
                value, i = _block(lines, i)
            else:
                value, i = _value(lines, i + 1, col, " " + body)
            seq.append(value)
    mapping: dict[str, Any] = {}
    while True:
        i = significant(lines, i)
        if i >= len(lines) or indent_of(lines[i]) != col:
            return mapping, i
        km = KEY_RE.match(lines[i])
        if not km:
            return mapping, i
        mapping[km["key"]], i = _value(lines, i + 1, col, km["rest"])


def mini_load(text: str) -> Any:
    """Block-style YAML text read by the small reader above (never for writes)."""
    lines = [ln.rstrip() for ln in text.lstrip("﻿").replace("\r\n", "\n").replace("\t", "  ").split("\n")]
    start = significant(lines, 0)
    return _block(lines, start)[0] if start < len(lines) else {}
