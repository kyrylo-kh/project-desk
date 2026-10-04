# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""`python -m project_desk` is the `desk` (or `project-desk`) command."""

import sys

from .cli import main

sys.exit(main())
