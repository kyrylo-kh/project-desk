# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Markdown bodies to HTML, with relative links pointed at the desk's /preview/ route."""

from __future__ import annotations

import html
import os
import re
from pathlib import Path
from urllib.parse import quote

from ..errors import HttpError
from .paths import resolve_repo_path

LIST_ITEM_RE = re.compile(r"^ {0,3}(?:[-*+]|\d{1,9}[.)])[ \t]+\S")
TABLE_SEP_RE = re.compile(r"^ {0,3}\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$")
FENCE_RE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
URL_ATTR_RE = re.compile(r'(\s(?:src|href)=")([^"]*)(")')


def render_markdown(text: str, base_rel: str, root: Path) -> str:
    import markdown

    out = markdown.markdown(commonmark_blocks(text), extensions=["extra", "sane_lists"], output_format="html")
    return rewrite_urls(out, base_rel, root)


def commonmark_blocks(text: str) -> str:
    """Insert the blank line Python-Markdown needs before a list or table that follows a paragraph.

    CommonMark (GitHub, editors, most AI output) lets a list interrupt a paragraph; Python-Markdown
    would otherwise render "Intro:\\n- a\\n- b" as one paragraph with literal dashes.
    """
    lines = text.split("\n")
    out: list[str] = []
    fence: str | None = None
    in_block = False  # inside a list or table that already started
    for i, line in enumerate(lines):
        m = FENCE_RE.match(line)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence):
                fence = None
            out.append(line)
            continue
        if m:
            fence, in_block = m.group(1), False
            out.append(line)
            continue
        prev = out[-1] if out else ""
        is_list = bool(LIST_ITEM_RE.match(line))
        is_table = line.lstrip().startswith("|") and i + 1 < len(lines) and bool(TABLE_SEP_RE.match(lines[i + 1]))
        if (is_list or is_table) and prev.strip() and not in_block and not prev.startswith((" ", "\t")):
            out.append("")
        if not line.strip():
            in_block = False
        elif is_list or is_table:
            in_block = True
        out.append(line)
    return "\n".join(out)


def rewrite_urls(markup: str, base_rel: str, root: Path) -> str:
    """Point relative src/href at /preview/ so repo files render inside the desk."""

    def fix(m: re.Match[str]) -> str:
        url = html.unescape(m.group(2))
        if not url or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:|^[/#?]", url):
            return m.group(0)
        path, _, frag = url.partition("#")
        path = path.split("?", 1)[0]
        for cand in (os.path.normpath(os.path.join(base_rel, path)), os.path.normpath(path)):
            cand = cand.replace(os.sep, "/")
            try:
                resolve_repo_path(root, cand)
            except HttpError:
                continue
            new = "/preview/" + quote(cand, safe="/") + (f"#{frag}" if frag else "")
            return m.group(1) + html.escape(new, quote=True) + m.group(3)
        return m.group(0)

    return URL_ATTR_RE.sub(fix, markup)
