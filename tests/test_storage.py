# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Round trips, the Markdown renderer and the repo-path gate."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from project_desk.errors import HttpError
from project_desk.storage.doc import parse_doc, split_frontmatter
from project_desk.storage.paths import resolve_repo_path
from project_desk.storage.render import commonmark_blocks, render_markdown
from project_desk.storage.yamlio import yaml_dump, yaml_load

from support import DECISION, DEMO, decision_path, make_repo

# --------------------------------------------------------------------------- round trip


def test_round_trip_is_byte_identical(repo: Path) -> None:
    p = decision_path(repo)
    original = p.read_bytes()
    doc = parse_doc(p)
    assert doc.render() == original
    assert doc.render(doc.fm) == original


def test_round_trip_keeps_crlf_and_bom(tmp_path: Path) -> None:
    text = "\ufeff" + DECISION.replace("\n", "\r\n")
    root = make_repo(tmp_path, text)
    p = decision_path(root)
    original = p.read_bytes()
    doc = parse_doc(p)
    assert doc.render() == original
    assert doc.data["id"] == "D-0001"


def test_ruamel_fallback_round_trip_is_identical() -> None:
    _, fm, _, _ = split_frontmatter(DECISION)
    assert yaml_dump(yaml_load(fm)) == fm


@pytest.mark.parametrize(
    "real",
    sorted((DEMO / "decisions").glob("D-*.md")) + sorted((DEMO / "qa" / "runs").glob("R-*.md")),
    ids=lambda p: p.name,
)
def test_demo_files_round_trip(real: Path, tmp_path: Path) -> None:
    copy = tmp_path / real.name
    shutil.copyfile(real, copy)
    original = copy.read_bytes()
    assert parse_doc(copy).render() == original


# --------------------------------------------------------------------------- markdown


def test_markdown_list_and_table_right_after_a_paragraph(repo: Path) -> None:
    text = "Intro:\n- one\n- two\n\nScores:\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    out = render_markdown(text, "decisions", repo)
    assert "<ul>" in out and "<li>one</li>" in out and "- one" not in out
    assert "<table>" in out


def test_markdown_keeps_code_fences_and_lazy_lines() -> None:
    text = "```\nIntro:\n- not a list\n```\n\n- item one\ncontinued\n- item two\n"
    fixed = commonmark_blocks(text)
    assert "Intro:\n- not a list" in fixed  # fenced code untouched
    assert "continued\n- item two" in fixed  # an open list is not split
    assert commonmark_blocks("a\n\n- b\n") == "a\n\n- b\n"


def test_markdown_links_point_at_previews(repo: Path) -> None:
    out = render_markdown("[notes](material/D-0001-notes.md) ![x](../design/x/preview.png)", "decisions", repo)
    assert 'href="/preview/decisions/material/D-0001-notes.md"' in out
    assert 'src="/preview/design/x/preview.png"' in out


def test_markdown_html_is_left_to_the_page_csp() -> None:
    """Bodies are repo files (trusted, like the code), so raw HTML passes through Markdown. The UI page's CSP
    is what stops a script in one: no inline scripts, no inline event handlers, no foreign origins, and no
    repo .js under /preview/ (an <iframe srcdoc> inherits the page's policy)."""
    from project_desk.server import index_csp

    csp = index_csp("127.0.0.1:4700")
    assert "script-src http://127.0.0.1:4700/static/;" in csp
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp


# --------------------------------------------------------------------------- paths


@pytest.mark.parametrize(
    "rel",
    [
        "../etc/passwd",
        "design/../../etc/passwd.png",
        "/etc/passwd",
        "//etc/passwd.png",
        "C:/Windows/win.ini",
        "design\\x\\preview.png",
        ".git/config",
        "design/.hidden.png",
        "design/x/./preview.png",
        "package.json",
        "design/x/preview.png\x00.md",
        "",
    ],
)
def test_resolve_rejects_traversal(repo: Path, rel: str) -> None:
    with pytest.raises(HttpError) as e:
        resolve_repo_path(repo, rel)
    assert e.value.code == 403


def test_resolve_rejects_symlink_escape(repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "secret.png"
    outside.write_bytes(b"secret")
    (repo / "design" / "link.png").symlink_to(outside)
    with pytest.raises(HttpError) as e:
        resolve_repo_path(repo, "design/link.png")
    assert e.value.code == 403


def test_resolve_allows_repo_files(repo: Path) -> None:
    assert resolve_repo_path(repo, "design/x/preview.png").name == "preview.png"
    assert resolve_repo_path(repo, "decisions/material/D-0001-notes.md").suffix == ".md"
    with pytest.raises(HttpError) as e:
        resolve_repo_path(repo, "design/x/nope.png")
    assert e.value.code == 404
