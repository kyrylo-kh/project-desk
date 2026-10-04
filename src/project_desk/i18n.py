# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""UI and `brief` strings. English is the default; Ukrainian is a full second locale.

Locales are flat JSON files in `locales/`, shared with the browser (served by /api/config). A value is
a string with `{name}` placeholders, a list (weekday and month names), or a plural table
{"one", "few", "many", "other"} picked by `plural_category`.
"""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any

from .errors import DeskError

FALLBACK = "en"


@cache
def load_locale(lang: str) -> dict[str, Any]:
    try:
        text = resources.files("project_desk").joinpath("locales", f"{lang}.json").read_text(encoding="utf-8")
    except FileNotFoundError:
        raise DeskError(f"no locale '{lang}'") from None
    data = json.loads(text)
    if not isinstance(data, dict):
        raise DeskError(f"locale '{lang}' must be a JSON object")
    return data


def plural_category(lang: str, n: int) -> str:
    """CLDR cardinal categories for whole numbers, for the languages the desk ships."""
    n = abs(n)
    if lang == "uk":
        if n % 10 == 1 and n % 100 != 11:
            return "one"
        if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
            return "few"
        return "many"
    return "one" if n == 1 else "other"


class Translator:
    def __init__(self, lang: str = FALLBACK) -> None:
        self.lang = lang
        self.strings = load_locale(lang)
        self.fallback = load_locale(FALLBACK) if lang != FALLBACK else self.strings

    def raw(self, key: str) -> Any:
        if key in self.strings:
            return self.strings[key]
        if key in self.fallback:
            return self.fallback[key]
        raise KeyError(f"missing i18n key '{key}'")

    def t(self, key: str, **params: Any) -> str:
        value = self.raw(key)
        if not isinstance(value, str):
            raise TypeError(f"i18n key '{key}' is not a string")
        return value.format(**params) if params else value

    def n(self, key: str, count: int, **params: Any) -> str:
        table = self.raw(key)
        if not isinstance(table, dict):
            raise TypeError(f"i18n key '{key}' is not a plural table")
        cat = plural_category(self.lang, count)
        text = table.get(cat) or table.get("other") or table.get("many") or next(iter(table.values()))
        return str(text).format(n=count, **params)

    def seq(self, key: str) -> list[str]:
        value = self.raw(key)
        if not isinstance(value, list):
            raise TypeError(f"i18n key '{key}' is not a list")
        return [str(v) for v in value]
