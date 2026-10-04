# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""A Markdown file with YAML frontmatter, kept byte-exact so an unchanged save is a no-op."""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..errors import DeskError
from .lines import FM_RE
from .yamlio import to_plain, yaml_load


@dataclass
class Doc:
    path: Path
    raw: bytes
    bom: str
    newline: str
    head: str
    fm: str
    sep: str
    body: str
    data: dict[str, Any]

    @property
    def etag(self) -> str:
        """A short content hash. A save that carries a different etag is refused (409)."""
        return hashlib.sha256(self.raw).hexdigest()[:16]

    @property
    def id(self) -> str:
        return str(self.data.get("id") or self.path.name[:6])

    def render(self, fm: str | None = None) -> bytes:
        """Reassemble the file. With no changes this returns the original bytes."""
        text = self.head + (self.fm if fm is None else fm) + self.sep + self.body
        if self.newline != "\n":
            text = text.replace("\n", self.newline)
        return (self.bom + text).encode("utf-8")


def split_frontmatter(text: str) -> tuple[str, str, str, str]:
    m = FM_RE.match(text)
    if not m:
        raise DeskError("missing YAML frontmatter (the file must start with a '---' line and close it with another)")
    return m.group(1), m.group(2), m.group(3), text[m.end() :]


def parse_doc(path: Path) -> Doc:
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise DeskError("file is not valid UTF-8") from None
    bom = ""
    if text.startswith("﻿"):
        bom, text = "﻿", text[1:]
    newline = "\r\n" if "\r\n" in text else "\n"
    if newline != "\n":
        text = text.replace("\r\n", "\n")
    head, fm, sep, body = split_frontmatter(text)
    loaded = yaml_load(fm)
    if not isinstance(loaded, dict):
        raise DeskError("frontmatter must be a YAML mapping")
    return Doc(path, raw, bom, newline, head, fm, sep, body, to_plain(loaded))


def write_atomic(path: Path, data: bytes, exclusive: bool = False) -> None:
    """Write via a temp file in the same directory, then rename (or hard-link when exclusive)."""
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
        os.chmod(tmp, mode)
        if exclusive:
            os.link(tmp, path)  # fails if the file already exists
            os.unlink(tmp)
        else:
            os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def load_docs(paths: list[Path], rel: Callable[[Path], str]) -> tuple[list[Doc], list[dict[str, str]]]:
    """Parse every path. Unreadable files become error issues (named by `rel(path)`), removed ones are skipped."""
    from ..text import issue

    docs, problems = [], []
    for p in paths:
        try:
            docs.append(parse_doc(p))
        except FileNotFoundError:
            continue  # removed while we were reading
        except DeskError as e:
            problems.append(issue(rel(p), "error", str(e)))
    return docs, problems


def find_doc(paths: list[Path], doc_id: str) -> Doc | None:
    """The document whose `id` is doc_id. Files named after the id are tried first."""
    candidates = [p for p in paths if p.name.startswith(f"{doc_id}-")]
    candidates += [p for p in paths if p not in candidates]
    for p in candidates:
        try:
            doc = parse_doc(p)
        except (DeskError, FileNotFoundError):
            continue
        if doc.id == doc_id:
            return doc
    return None
