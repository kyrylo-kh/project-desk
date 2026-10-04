# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Surgical frontmatter edits: change one value in place and leave every other byte alone.

Comments, alignment, quoting and key order survive. Every caller verifies an edit by re-parsing the
result and comparing it with the data it expects; on any doubt it falls back to a ruamel round trip
(`edit_frontmatter`), which still keeps comments but may re-indent.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable
from typing import Any

from ..errors import DeskError, EditError
from .lines import KEY_RE, indent_of, is_dash, quick_scalar, significant, split_value_comment
from .yamlio import to_plain, yaml_dump, yaml_load, yaml_rt

PLAIN_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]*$")
RESERVED_WORDS = {"null", "true", "false", "yes", "no", "on", "off", "y", "n", "~"}

# How a value is written: "ident" for ids and statuses, "text" for free text (a literal block when it
# has line breaks, else double-quoted), "auto" for a plain scalar when it reads back the same.
Style = str


def yaml_double_quoted(s: str) -> str:
    out = ['"']
    for ch in s:
        o = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif o < 0x20 or o == 0x7F or 0x80 <= o < 0xA0 or o in (0x2028, 0x2029, 0xFEFF):
            out.append(f"\\u{o:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def literal_ok(s: str) -> bool:
    """Can this text be written as a `|-` literal block and read back unchanged?"""
    if "\n" not in s or s[:1].isspace() or s.endswith("\n"):
        return False
    return all(
        ch in "\n\t"
        or (
            ord(ch) >= 0x20
            and ord(ch) != 0x7F
            and not 0x80 <= ord(ch) < 0xA0
            and ord(ch) not in (0x2028, 0x2029, 0xFEFF)
        )
        for ch in s
    )


def plain_or_quoted(s: str) -> str:
    """A plain scalar when it reads back as the same string, otherwise double-quoted."""
    if (
        s
        and "\n" not in s
        and s == s.strip()
        and s[0] not in "-?:,[]{}#&*!|>'\"%@`"
        and ": " not in s
        and " #" not in s
        and not s.endswith(":")
        and s.lower() not in RESERVED_WORDS
    ):
        try:
            back = to_plain(yaml_rt().load(f"k: {s}\n"))
            if back == {"k": s}:
                return s
        except Exception:  # any parse doubt means "quote it"
            pass
    return yaml_double_quoted(s)


def render_value(value: Any, indent: int, style: Style = "auto") -> list[str]:
    """Render a scalar for 'key: <value>'. Returns [inline part, *continuation lines]."""
    if value is None:
        return ["null"]
    if isinstance(value, bool):
        return ["true" if value else "false"]
    if isinstance(value, list):
        if value:
            raise EditError("only empty lists are rendered inline")
        return ["[]"]
    if isinstance(value, dt.date | dt.datetime):
        return [value.isoformat()]
    s = str(value)
    if style == "ident":
        ok = PLAIN_IDENT_RE.match(s) and s.lower() not in RESERVED_WORDS
        return [s if ok else yaml_double_quoted(s)]
    if style == "text":
        if literal_ok(s):
            pad = " " * (indent + 2)
            return ["|-", *[(pad + line) if line else "" for line in s.split("\n")]]
        return [yaml_double_quoted(s)]
    return [plain_or_quoted(s)]


def find_key(lines: list[str], key: str, start: int, end: int, indent: int) -> int | None:
    for i in range(start, end):
        m = KEY_RE.match(lines[i])
        if m and m["key"] == key and len(m["indent"]) == indent:
            return i
    return None


def value_end(lines: list[str], i: int, indent: int) -> int:
    """Exclusive end of the value whose key is on line i. Trailing blank lines stay outside."""
    last, j = i, i + 1
    while j < len(lines):
        if not lines[j].strip():
            j += 1
            continue
        if indent_of(lines[j]) > indent:
            last = j
            j += 1
            continue
        break
    return last + 1


def _key_match(line: str) -> re.Match[str]:
    m = KEY_RE.match(line)
    if m is None:
        raise EditError(f"not a key line: {line!r}")
    return m


def set_line_value(lines: list[str], i: int, value_lines: list[str]) -> None:
    m = _key_match(lines[i])
    indent = len(m["indent"])
    _, comment = split_value_comment(m["rest"])
    end = value_end(lines, i, indent)
    head = f"{m['indent']}{m['key']}: {value_lines[0]}"
    if comment:
        mark = comment.lstrip()
        col = len(lines[i]) - len(mark)  # keep trailing comments aligned where they were
        head = head + " " * max(1, col - len(head)) + mark
    lines[i:end] = [head, *value_lines[1:]]


def set_top(lines: list[str], key: str, value: Any, style: Style = "auto") -> None:
    i = find_key(lines, key, 0, len(lines), 0)
    if i is None:
        raise EditError(f"no top-level '{key}:'")
    set_line_value(lines, i, render_value(value, 0, style))


def set_top_literal(lines: list[str], key: str, text_lines: list[str], after: str) -> None:
    """Set a top-level `key: |` literal block. When the key is missing, insert it after `after`."""
    block = ["|", *[f"  {ln}" if ln else "" for ln in text_lines]]
    i = find_key(lines, key, 0, len(lines), 0)
    if i is not None:
        set_line_value(lines, i, block)
        return
    j = find_key(lines, after, 0, len(lines), 0)
    if j is None:
        raise EditError(f"no top-level '{after}:' to put '{key}:' after")
    end = value_end(lines, j, 0)
    lines[end:end] = [f"{key}: {block[0]}", *block[1:]]


def _block(lines: list[str], parent: str) -> tuple[int, int, int]:
    p = find_key(lines, parent, 0, len(lines), 0)
    if p is None:
        raise EditError(f"no top-level '{parent}:'")
    value, _ = split_value_comment(_key_match(lines[p])["rest"])
    if value.strip():
        raise EditError(f"'{parent}' is not a block mapping")
    end = value_end(lines, p, 0)
    child = next((indent_of(ln) for ln in lines[p + 1 : end] if ln.strip() and not ln.lstrip().startswith("#")), 2)
    if child == 0 or any(ln.lstrip().startswith("- ") for ln in lines[p + 1 : end] if indent_of(ln) == child):
        raise EditError(f"'{parent}' is not a block mapping")
    return p, end, child


def set_child(lines: list[str], parent: str, key: str, value: Any, style: Style = "auto") -> None:
    p, end, child = _block(lines, parent)
    rendered = render_value(value, child, style)
    j = find_key(lines, key, p + 1, end, child)
    if j is None:
        lines[end:end] = [f"{' ' * child}{key}: {rendered[0]}", *rendered[1:]]
    else:
        set_line_value(lines, j, rendered)


def replace_children(lines: list[str], key: str, children: list[str]) -> None:
    """Replace everything under a top-level key with `children` (already indented)."""
    i = find_key(lines, key, 0, len(lines), 0)
    if i is None:
        raise EditError(f"no top-level '{key}:'")
    end = value_end(lines, i, 0)
    _, comment = split_value_comment(_key_match(lines[i])["rest"])
    lines[i:end] = [f"{key}:{comment}", *children]


def set_top_or_insert(lines: list[str], key: str, value: Any, style: Style, before: str) -> None:
    """Set a top-level key; when it is missing, insert it right before the top-level `before:` key."""
    rendered = render_value(value, 0, style)
    i = find_key(lines, key, 0, len(lines), 0)
    if i is not None:
        set_line_value(lines, i, rendered)
        return
    j = find_key(lines, before, 0, len(lines), 0)
    if j is None:
        raise EditError(f"no top-level '{before}:' to put '{key}:' before")
    lines[j:j] = [f"{key}: {rendered[0]}", *rendered[1:]]


def item_span(lines: list[str], list_key: str, item_id: str) -> tuple[int, int, int]:
    """(first line, exclusive end, key column) of the item with `id: item_id` in a top-level block list.
    Handles indented and indentless lists, and `- id: T01` as well as a bare `-` line."""
    c = find_key(lines, list_key, 0, len(lines), 0)
    if c is None:
        raise EditError(f"no top-level '{list_key}:'")
    if split_value_comment(_key_match(lines[c])["rest"])[0].strip():
        raise EditError(f"'{list_key}' is not a block list")
    end = c + 1
    for j in range(c + 1, len(lines)):
        s = lines[j]
        if s.strip() and indent_of(s) == 0 and not is_dash(s) and not s.startswith("#"):
            break  # the next top-level key
        if s.strip():
            end = j + 1
    dash: int | None = None
    starts = []
    for i in range(c + 1, end):
        s = lines[i].strip()
        if not s or s.startswith("#"):
            continue
        if dash is None:
            if not is_dash(lines[i]):
                raise EditError(f"'{list_key}' is not a block list")
            dash = indent_of(lines[i])
        if indent_of(lines[i]) == dash and is_dash(lines[i]):
            starts.append(i)
    for n, start in enumerate(starts):
        assert dash is not None
        stop = starts[n + 1] if n + 1 < len(starts) else end
        body = lines[start].strip()[1:]
        if body.strip():
            col = dash + 1 + len(body) - len(body.lstrip())
        else:
            nxt = significant(lines, start + 1)
            col = indent_of(lines[nxt]) if nxt < stop else dash + 2
        virtual = [" " * col + lines[start][col:], *lines[start + 1 : stop]]  # the dash read as a space
        k = find_key(virtual, "id", 0, len(virtual), col)
        if k is not None and quick_scalar(split_value_comment(_key_match(virtual[k])["rest"])[0]) == item_id:
            return start, stop, col
    raise EditError(f"no item {item_id} in '{list_key}'")


def set_item_key(lines: list[str], list_key: str, item_id: str, key: str, value: Any, style: Style) -> None:
    """Set one key of one list item in place. A missing key is added at the end of that item."""
    start, end, col = item_span(lines, list_key, item_id)
    prefix = lines[start][:col]
    lines[start] = " " * col + lines[start][col:]  # so the first key reads like the others
    try:
        rendered = render_value(value, col, style)
        j = find_key(lines, key, start, end, col)
        if j is None:
            last = max((i for i in range(start, end) if lines[i].strip()), default=start)
            lines[last + 1 : last + 1] = [f"{' ' * col}{key}: {rendered[0]}", *rendered[1:]]
        else:
            set_line_value(lines, j, rendered)
    finally:
        lines[start] = prefix + lines[start][col:]


def edit_frontmatter(
    fm: str,
    expected: dict[str, Any],
    surgical: Callable[[list[str]], None],
    fallback: Callable[[Any], None],
) -> str:
    """New frontmatter text. `surgical` edits the lines in place; the result must parse to `expected`.
    Otherwise `fallback` edits ruamel's round-trip data, which is dumped back."""
    try:
        lines = fm.split("\n")
        surgical(lines)
        new_fm = "\n".join(lines)
        if to_plain(yaml_load(new_fm)) == expected:
            return new_fm
    except (EditError, DeskError):
        pass
    data = yaml_load(fm)
    fallback(data)
    return yaml_dump(data)


def styled(value: Any, style: Style) -> Any:
    """A value dressed for a ruamel dump in the same style the surgical edit would use."""
    from ruamel.yaml.scalarstring import DoubleQuotedScalarString, LiteralScalarString

    if value is None or style == "ident" or not isinstance(value, str):
        return value
    return LiteralScalarString(value) if literal_ok(value) else DoubleQuotedScalarString(value)
