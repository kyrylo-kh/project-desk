# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Every source file carries the SPDX licence header, and the package metadata says the same."""

import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPDX = "SPDX-License-Identifier: FSL-1.1-ALv2"
SOURCE = (".py", ".js", ".css", ".html")


def source_files() -> list[Path]:
    files = [p for p in (REPO / "src").rglob("*") if p.suffix in SOURCE and "templates" not in p.parts]
    files += list((REPO / "tests").rglob("*.py"))
    return sorted(p for p in files if "__pycache__" not in p.parts)


def test_every_source_file_has_the_spdx_header() -> None:
    files = source_files()
    assert len(files) > 40
    missing = [str(p.relative_to(REPO)) for p in files if SPDX not in "".join(p.read_text().splitlines(True)[:4])]
    assert missing == []


def test_the_files_scaffolded_into_a_project_carry_no_header() -> None:
    # The templates become the user's files, under the user's licence.
    templates = [p for p in (REPO / "src/project_desk/templates").rglob("*") if p.is_file()]
    assert templates and not [p for p in templates if "SPDX" in p.read_text()]


def test_the_metadata_and_the_licence_text_agree() -> None:
    project = tomllib.loads((REPO / "pyproject.toml").read_text())["project"]
    assert project["license"] == "FSL-1.1-ALv2"
    assert project["license-files"] == ["LICENSE.md"]
    text = (REPO / "LICENSE.md").read_text()
    assert text.startswith("# Functional Source License, Version 1.1, ALv2 Future License")
    assert "Copyright 2026 Kyrylo Kholodenko" in text and "${" not in text
