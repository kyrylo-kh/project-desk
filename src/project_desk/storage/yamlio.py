# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Round-trip YAML through ruamel.yaml, imported lazily (the fast path never pays for it)."""

from __future__ import annotations

import datetime as dt
import io
from typing import Any

from ..errors import DeskError


def yaml_rt() -> Any:
    """Round-trip YAML configured to match the house style of the desk's files."""
    from ruamel.yaml import YAML

    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    y.representer.add_representer(type(None), lambda rep, _: rep.represent_scalar("tag:yaml.org,2002:null", "null"))
    return y


def yaml_load(text: str) -> Any:
    """Parse YAML text into ruamel's round-trip objects. Raises DeskError with the first line of the problem."""
    from ruamel.yaml.error import YAMLError

    try:
        return yaml_rt().load(text)
    except YAMLError as e:
        raise DeskError(f"invalid YAML frontmatter: {str(e).strip().splitlines()[0]}") from None


def yaml_load_file(text: str, what: str) -> Any:
    """Parse a whole YAML file. Errors name the line: "invalid YAML at line 3: ..."."""
    from ruamel.yaml.error import YAMLError

    try:
        return yaml_rt().load(text)
    except YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" at line {mark.line + 1}" if mark is not None else ""
        problem = getattr(e, "problem", None) or str(e).strip().splitlines()[0]
        raise DeskError(f"invalid YAML{where}: {problem}") from None


def yaml_dump(data: Any) -> str:
    buf = io.StringIO()
    yaml_rt().dump(data, buf)
    return buf.getvalue()


def to_plain(obj: Any) -> Any:
    """ruamel objects -> JSON-safe plain Python."""
    if isinstance(obj, bool) or type(obj).__name__ == "ScalarBoolean":
        return bool(obj)
    if obj is None or isinstance(obj, int | float):
        return obj
    if isinstance(obj, str):
        return str(obj)
    if isinstance(obj, dict):
        return {str(k): to_plain(v) for k, v in obj.items()}
    if isinstance(obj, list | tuple):
        return [to_plain(v) for v in obj]
    if isinstance(obj, dt.date | dt.datetime):
        return obj.isoformat()
    return str(obj)
