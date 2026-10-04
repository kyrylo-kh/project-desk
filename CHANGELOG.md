# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). The version numbers
follow [Semantic Versioning](https://semver.org/).

## [0.1.0] - 2026-10-04

First public release.

- Three desks as tabs: Plan, Decision Desk and Test Desk.
- CLI: `serve`, `brief`, `summary`, `list`, `new`, `validate`, `init`.
- Claude Code SessionStart hook and skills (`desk init --hook --skills`).
- Config in `.project-desk.toml` or `[tool.project-desk]`; unknown keys are errors.
- English and Ukrainian UI.
- Five themes (light, dark, high contrast, manila, terminal), all WCAG AA.
- Plugin modules by import path or the `project_desk.modules` entry point.
- Dockerfile and a Compose example.
- Licence: FSL-1.1-ALv2 (each release becomes Apache-2.0 two years later).
