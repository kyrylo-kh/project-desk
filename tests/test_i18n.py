# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The locales: same keys, same placeholders, real plural tables, and no key the code uses is missing."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from project_desk.errors import DeskError
from project_desk.i18n import Translator, load_locale, plural_category

from support import PROJECT, STATIC

SRC = PROJECT / "src" / "project_desk"
PLURAL_FORMS = {"en": {"one", "other"}, "uk": {"one", "few", "many"}}
PREFIXES = ("ui", "theme", "common", "dec", "plan", "qa", "tab", "date", "brief")


def placeholders(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set().union(*(placeholders(v) for v in value.values()))
    if isinstance(value, list):
        return set()
    return set(re.findall(r"\{(\w+)\}", str(value)))


def test_locales_have_the_same_keys() -> None:
    en, uk = load_locale("en"), load_locale("uk")
    assert set(en) == set(uk)


def test_values_match_in_kind_and_placeholders() -> None:
    en, uk = load_locale("en"), load_locale("uk")
    bad = []
    for key in sorted(en):
        a, b = en[key], uk.get(key)
        same = type(a) is type(b) and placeholders(a) == placeholders(b)
        if isinstance(a, dict):
            same = same and set(a) == PLURAL_FORMS["en"] and set(b) == PLURAL_FORMS["uk"]  # type: ignore[arg-type]
        if isinstance(a, list):
            same = same and len(a) == len(b)  # type: ignore[arg-type]
        if not same:
            bad.append(key)
    assert bad == []


def test_plural_rules() -> None:
    assert [plural_category("en", n) for n in (0, 1, 2)] == ["other", "one", "other"]
    uk = {n: plural_category("uk", n) for n in (1, 2, 4, 5, 11, 12, 14, 21, 22, 25, 111)}
    assert uk == {1: "one", 2: "few", 4: "few", 5: "many", 11: "many", 12: "many", 14: "many",
                  21: "one", 22: "few", 25: "many", 111: "many"}  # fmt: skip


def test_translator() -> None:
    uk = Translator("uk")
    assert uk.n("common.problems", 3, command="desk").startswith("У 3 файлах")
    assert uk.t("qa.minutes", n=5) == "~5 хв"
    assert len(uk.seq("date.months_of")) == 12 and len(uk.seq("date.weekdays")) == 7
    with pytest.raises(KeyError):
        uk.t("no.such.key")
    with pytest.raises(DeskError):
        load_locale("xx")


def _static_files() -> list[Path]:
    return sorted([*STATIC.rglob("*.js"), STATIC / "index.html"])


def test_every_key_the_browser_uses_exists() -> None:
    en = load_locale("en")
    alternatives = "|".join(PREFIXES)
    quoted = re.compile(r"""['"`]((?:""" + alternatives + r""")\.[a-z0-9_.-]+)['"`]""")
    used: set[str] = set()
    prefixes: set[str] = set()
    for f in _static_files():
        for key in quoted.findall(f.read_text(encoding="utf-8")):
            (prefixes if key.endswith(".") else used).add(key)
    assert len(used) > 150  # the scan works
    assert sorted(k for k in used if k not in en) == []
    # Keys built at run time ('dec.status.' + status) need at least one entry under the prefix.
    assert sorted(p for p in prefixes if not any(k.startswith(p) for k in en)) == []


def test_every_key_the_python_side_uses_exists() -> None:
    en = load_locale("en")
    call = re.compile(r"""\.(?:t|n|seq)\(\s*["']([a-z_.-]+)["']""")
    label = re.compile(r"""label_key[^=]*=\s*["']([a-z_.-]+)["']""")
    used = set()
    for f in SRC.rglob("*.py"):
        text = f.read_text(encoding="utf-8")
        used |= set(call.findall(text)) | set(label.findall(text))
    assert {"brief.today", "tab.decisions"} <= used
    assert sorted(k for k in used if k not in en) == []
