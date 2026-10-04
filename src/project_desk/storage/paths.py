# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Repo-relative paths: what the desk may serve, and how a preview or link is described to the UI."""

from __future__ import annotations

import re
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import quote

from ..errors import HttpError

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
PREVIEW_EXTS = IMAGE_EXTS | {".html", ".css", ".js", ".woff2", ".md"}
MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".woff2": "font/woff2",
    ".md": "text/plain; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}
WEB_LINK_RE = re.compile(r"^https?://", re.I)  # links that are not repo paths
_DRIVE_RE = re.compile(r"^[A-Za-z]:")


def _parts(rel: str) -> list[str] | None:
    """Raw segments of a safe repo-relative path, or None. PurePosixPath would drop "." and "//"."""
    if not rel or "\x00" in rel or "\\" in rel or rel.startswith("/") or _DRIVE_RE.match(rel):
        return None
    parts = rel.split("/")
    if any(not p or p.startswith(".") for p in parts):
        return None
    return parts


def resolve_repo_path(root: Path, rel: str, exts: set[str] | None = None) -> Path:
    """Resolve a repo-relative path for serving. Raises HttpError 403/404."""
    exts = PREVIEW_EXTS if exts is None else exts
    if not rel or "\x00" in rel or "\\" in rel or rel.startswith("/") or _DRIVE_RE.match(rel):
        raise HttpError(403, "only repo-relative paths are allowed")
    parts = _parts(rel)
    if parts is None:
        raise HttpError(403, "path traversal and hidden files are not allowed")
    if PurePosixPath(rel).suffix.lower() not in exts:
        raise HttpError(403, "file type not allowed")
    root = root.resolve()
    full = root.joinpath(*parts).resolve()
    if not full.is_relative_to(root):
        raise HttpError(403, "path escapes the repo")
    # A symlink inside the repo must not lead to a hidden file or another type (notes.md -> ../.env).
    if any(p.startswith(".") for p in full.relative_to(root).parts) or full.suffix.lower() not in exts:
        raise HttpError(403, "path traversal and hidden files are not allowed")
    if not full.is_file():
        raise HttpError(404, "file not found")
    return full


def repo_path_exists(root: Path, rel: str) -> bool:
    """A repo-relative file or folder that exists and stays inside the repo. Same rules as
    resolve_repo_path, minus the extension check. Never raises."""
    parts = _parts(rel.rstrip("/"))
    if parts is None:
        return False
    root = root.resolve()
    full = root.joinpath(*parts).resolve()
    if not full.is_relative_to(root) or any(p.startswith(".") for p in full.relative_to(root).parts):
        return False
    return full.exists()


def preview_kind(path: str) -> str:
    ext = PurePosixPath(path).suffix.lower()
    if ext in IMAGE_EXTS:
        return "image"
    return {".html": "html", ".md": "markdown"}.get(ext, "file")


def preview_json(root: Path, p: Any) -> dict[str, Any]:
    """A preview path as the UI shows it. `exists` means the desk can serve it under /preview/."""
    path = str(p)
    try:
        resolve_repo_path(root, path)
        exists = True
    except HttpError:
        exists = False
    return {
        "path": path,
        "name": PurePosixPath(path).name,
        "kind": preview_kind(path),
        "url": "/preview/" + quote(path, safe="/"),
        "exists": exists,
    }


def link_json(root: Path, link: Any) -> dict[str, Any]:
    """A plan link: a web URL, or a repo path that may or may not be servable."""
    s = str(link)
    if WEB_LINK_RE.match(s):
        return {"path": s, "name": s, "kind": "web", "url": s, "exists": True, "in_repo": False}
    out = preview_json(root, s)
    out["in_repo"] = out["exists"] or repo_path_exists(root, s)
    return out
