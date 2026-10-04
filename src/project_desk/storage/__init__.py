# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""Reading and writing Markdown files with YAML frontmatter, and plain YAML files.

Nothing here imports ruamel.yaml or markdown at module level: the summary and brief run on every
agent session start and use only `lines` and `quick`.
"""
