# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The themes: every theme in styles.css declares the same tokens, and every text/background pair the UI
uses reaches WCAG AA (4.5:1 for text, 3:1 for controls and focus). Also: the theme lists agree, and the
page stays inside the strict CSP (no inline script or style, no external fonts)."""

import re
from pathlib import Path

import pytest

from project_desk.config import THEMES

STATIC = Path(__file__).resolve().parent.parent / "src" / "project_desk" / "static"
CSS = (STATIC / "styles.css").read_text(encoding="utf-8")
NAMED = [t for t in THEMES if t != "auto"]

BACKGROUNDS = ("bg", "surface", "sunken", "rail", "selected", "hover")
SOFT = ("accent-soft", "parked-soft", "pass-soft", "fail-soft")


def _pairs() -> list[tuple[str, str, float]]:
    pairs = [(fg, bg, 4.5) for fg in ("text", "text-2", "text-3", "accent") for bg in BACKGROUNDS]
    pairs += [(fg, soft, 4.5) for fg in ("text", "text-2") for soft in SOFT]
    pairs += [("accent", "accent-soft", 4.5), ("on-accent", "accent", 4.5), ("on-accent", "accent-hover", 4.5)]
    pairs += [("on-mark", "mark", 4.5)]
    for state in ("parked", "pass", "fail"):
        pairs += [(state, bg, 4.5) for bg in ("bg", "surface", "rail", "selected", f"{state}-soft")]
    pairs += [("on-fill", fill, 4.5) for fill in ("pass", "fail", "parked", "text-2")]
    pairs += [(ui, bg, 3.0) for ui in ("control", "focus", "mark-line") for bg in ("bg", "surface", "sunken", "rail")]
    return pairs


PAIRS = _pairs()
TOKENS = sorted({name for pair in PAIRS for name in pair[:2]} | {"line", "line-strong"})


def _block(selector_pattern: str, css: str = CSS) -> dict[str, str]:
    match = re.search(selector_pattern + r"\s*\{([^}]*)\}", css)
    assert match, f"no block for {selector_pattern}"
    return dict(re.findall(r"--([\w-]+):\s*([^;]+);", match.group(1)))


def theme_tokens(theme: str) -> dict[str, str]:
    if theme == "light":
        return _block(r':root,\s*:root\[data-theme="light"\]')
    return _block(r':root\[data-theme="' + theme + r'"\]')


def _luminance(hex_colour: str) -> float:
    r, g, b = (int(hex_colour[i : i + 2], 16) / 255 for i in (1, 3, 5))

    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_the_contrast_formula() -> None:
    assert round(contrast("#000000", "#ffffff"), 1) == 21.0
    assert round(contrast("#777777", "#ffffff"), 2) == 4.48  # the classic just-fails grey


@pytest.mark.parametrize("theme", NAMED)
def test_every_theme_declares_every_pair_token_as_opaque_hex(theme: str) -> None:
    tokens = theme_tokens(theme)
    missing = [t for t in TOKENS if t not in tokens]
    assert missing == []
    not_hex = [t for t in TOKENS if not re.fullmatch(r"#[0-9a-fA-F]{6}", tokens[t].strip())]
    assert not_hex == []


@pytest.mark.parametrize("theme", NAMED)
def test_every_text_and_ui_pair_passes_wcag_aa(theme: str) -> None:
    tokens = theme_tokens(theme)
    low = [
        f"{fg} on {bg}: {contrast(tokens[fg].strip(), tokens[bg].strip()):.2f} < {need}"
        for fg, bg, need in PAIRS
        if contrast(tokens[fg].strip(), tokens[bg].strip()) < need
    ]
    assert low == []


def test_auto_dark_is_the_dark_theme() -> None:
    media = re.search(r"@media \(prefers-color-scheme: dark\)\s*\{(.*?\})\s*\}", CSS, re.S)
    assert media, "no prefers-color-scheme block"
    assert _block(r":root:not\(\[data-theme\]\)", media.group(1)) == theme_tokens("dark")


def test_the_theme_lists_agree() -> None:
    main = (STATIC / "js" / "main.js").read_text(encoding="utf-8")
    early = (STATIC / "js" / "theme.js").read_text(encoding="utf-8")
    listed = re.search(r"export const THEMES = \[([^\]]*)\]", main)
    assert listed and re.findall(r"'([a-z]+)'", listed.group(1)) == list(THEMES)
    named = re.search(r"var THEMES = \[([^\]]*)\]", early)
    assert named and re.findall(r"'([a-z]+)'", named.group(1)) == NAMED
    for theme in THEMES:
        assert f'"theme.{theme}"' in (STATIC.parent / "locales" / "en.json").read_text(encoding="utf-8")


def test_the_page_keeps_the_strict_csp() -> None:
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    scripts = re.findall(r"<script([^>]*)>(.*?)</script>", html, re.S)
    assert scripts and all('src="/static/' in attrs and not body.strip() for attrs, body in scripts)
    assert "<style" not in html and " style=" not in html and not re.search(r"\son[a-z]+=", html)
    for path in STATIC.rglob("*.css"):  # system font stacks only, nothing fetched from elsewhere
        text = path.read_text(encoding="utf-8")
        assert "@import" not in text and "@font-face" not in text and "url(" not in text
