# Contributing

Bug reports and pull requests are welcome. For a bigger change, open an issue first so we can agree
on the shape before you write the code.

## Setup

You need [uv](https://docs.astral.sh/uv/) and, for the browser render tests, Node 20.19+ or 22.7+.

```sh
make sync    # install the package and the dev tools into .venv
make check   # ruff, ruff format --check, mypy, pytest: the same as CI
make serve   # the demo project in your browser
```

## Guidelines

- Keep the files the source of truth: the desk writes only the human's fields, and edits stay
  surgical (see [docs/file-formats.md](docs/file-formats.md)).
- No build step, no CDN, no web fonts, no inline scripts or styles (the page CSP forbids them).
- New UI strings go into every file in `src/project_desk/locales/`; a test checks they match.
- New colours must pass WCAG AA in every theme; `tests/test_themes.py` checks this.
- Every source file starts with the SPDX header (`tests/test_licence.py`).

By contributing you agree that your contribution is licensed under the project's licence,
[FSL-1.1-ALv2](LICENSE.md), and that each release of it becomes Apache-2.0 two years later.

Security issues: see [SECURITY.md](SECURITY.md), do not open a public issue.
