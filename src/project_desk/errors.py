# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The three kinds of failure the desk distinguishes."""

from __future__ import annotations


class DeskError(Exception):
    """A user-facing problem: a bad file, bad input or a bad config. The CLI prints it and exits 2."""


class HttpError(Exception):
    """A refused request or action, with the HTTP status the server answers with.

    Services raise it too (a stale etag is 409 whether the caller is HTTP or a test)."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class EditError(Exception):
    """A surgical text edit could not be applied; the caller falls back to a ruamel round trip."""
