# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The `desk` command. Thin: it finds the project, builds a Desk and calls it."""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Any

import click

from . import __version__
from .config import find_root
from .errors import DeskError


def _desk(ctx: click.Context) -> Any:
    from .desk import Desk

    root = find_root(ctx.obj.get("root"))
    desk = Desk(root)
    if desk.config.deprecation:
        click.echo(f"desk: note: {desk.config.deprecation}", err=True)
    return desk


def _fail(e: DeskError) -> None:
    click.echo(f"desk: {e}", err=True)
    sys.exit(2)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--root",
    type=click.Path(file_okay=False, path_type=Path),
    help="Project root. Default: $PROJECT_DESK_ROOT, else the nearest folder with .project-desk.toml, "
    "[tool.project-desk], decisions/ or plan/roadmap.yaml.",
)
@click.version_option(__version__, prog_name="project-desk")
@click.pass_context
def cli(ctx: click.Context, root: Path | None) -> None:
    """Project Desk: a local desk where an AI agent and a human share the work.

    Three desks, one tab each: the Plan (plan/roadmap.yaml), the Decision Desk (decisions/D-0001-*.md)
    and the Test Desk (qa/runs/R-0001-*.md). The files are the source of truth; the desk shows them,
    checks them and saves the human's answers into them.
    """
    ctx.ensure_object(dict)
    ctx.obj["root"] = root


@cli.command()
@click.option("--port", type=int, default=None, help="Port. Default: the config's port (4700).")
@click.option(
    "--host",
    default=None,
    help="Address to listen on. Default 127.0.0.1. Use 0.0.0.0 only inside a container: the Host check still applies.",
)
@click.option("--open", "open_", is_flag=True, help="Open the browser.")
@click.option("--verbose", is_flag=True, help="Log every request.")
@click.pass_context
def serve(ctx: click.Context, port: int | None, host: str | None, open_: bool, verbose: bool) -> None:
    """Start the local UI."""
    from .server import make_server

    try:
        desk = _desk(ctx)
    except DeskError as e:
        _fail(e)
    host = desk.config.host if host is None else host
    port = desk.config.port if port is None else port
    try:
        server = make_server(desk, port, verbose, host)
    except OSError as e:
        click.echo(
            f"desk: cannot listen on {host}:{port} ({e.strerror}). Is the desk already running? Try --port {port + 1}.",
            err=True,
        )
        sys.exit(1)
    url = f"http://127.0.0.1:{server.port}"
    tabs = ", ".join(m.name for m in desk.modules)
    click.echo(f"Project Desk on {url}  ({tabs} in {desk.root})  Ctrl+C to stop")
    if host not in ("127.0.0.1", "localhost", "::1"):
        click.echo(
            f"Listening on {host}. Requests must still name 127.0.0.1, localhost or [::1] with port {server.port} "
            "in their Host header, so publish the port on the host's 127.0.0.1 only."
        )
    if open_:
        import webbrowser

        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        click.echo("\nProject Desk stopped.")
    finally:
        server.server_close()


@cli.command("list")
@click.option("--status", help="Filter, comma-separated: pending,answered,needs-info,resolved,withdrawn.")
@click.pass_context
def list_(ctx: click.Context, status: str | None) -> None:
    """Table of decisions."""
    from .modules.decisions.model import STATUSES, default_id, is_parked

    try:
        desk = _desk(ctx)
        module = desk.get("decisions")
        if module is None:
            raise DeskError("the decisions module is not enabled")
    except DeskError as e:
        _fail(e)
    wanted = None
    if status:
        wanted = {s.strip() for s in status.split(",") if s.strip()}
        bad = wanted - set(STATUSES)
        if bad:
            click.echo(f"desk: unknown status {', '.join(sorted(bad))} (use: {', '.join(STATUSES)})", err=True)
            sys.exit(2)
    docs, problems = module.load_all()
    rows = [("ID", "STATUS", "PRIORITY", "BLOCKING", "TITLE")]
    for doc in sorted(docs, key=lambda d: d.id):
        d = doc.data
        if wanted and d.get("status") not in wanted:
            continue
        blocking = f"parked ({default_id(d)})" if is_parked(d) else "yes" if d.get("blocking") else "no"
        rows.append(
            (doc.id, str(d.get("status") or "?"), str(d.get("priority") or "?"), blocking, str(d.get("title") or ""))
        )
    if len(rows) == 1:
        click.echo("No decisions" + (f" with status {status}." if wanted else "."))
    else:
        widths = [max(len(r[i]) for r in rows) for i in range(4)]
        for r in rows:
            click.echo("  ".join(r[i].ljust(widths[i]) for i in range(4)) + "  " + r[4])
    for p in problems:
        click.echo(f"! {p['file']}: {p['message']}", err=True)


@cli.command()
@click.pass_context
def summary(ctx: click.Context) -> None:
    """Status for the AI, for a SessionStart hook. Silent when there is nothing to say or no project."""
    try:
        root = find_root(ctx.obj.get("root"))
    except DeskError:
        return  # not a desk project: nothing to say
    try:
        from .desk import Desk

        text = Desk(root).summary_text()
    except DeskError as e:  # a broken config is worth one line to the AI; it still exits 0
        text = f"Project Desk: {e}. Fix it, then run `desk validate`."
    except Exception:  # never break a session start
        return
    if text:
        click.echo(text)


@cli.command()
@click.pass_context
def brief(ctx: click.Context) -> None:
    """One screen for the human, in the UI language: now and next, what waits on them, the last 7 days."""
    try:
        click.echo(_desk(ctx).brief_text())
    except DeskError as e:
        _fail(e)


@cli.command()
@click.pass_context
def validate(ctx: click.Context) -> None:
    """Check every file of every enabled module. Exit 1 on errors."""
    try:
        text, code = _desk(ctx).validate_text()
    except DeskError as e:
        _fail(e)
    click.echo(text)
    sys.exit(code)


@cli.command()
@click.option("--title", required=True, help="Short title of the decision.")
@click.option("--type", "type_", required=True, help="One of the configured types ([decisions] types).")
@click.option("--group", required=True, help="A free grouping label, e.g. product-definition, design.")
@click.option("--priority", default="medium", type=click.Choice(["high", "medium", "low"]), show_default=True)
@click.option("--blocking", is_flag=True, help="Some work is waiting on this answer.")
@click.option("--asked-by", default="ai", show_default=True, help="Who is asking (agent or workflow name).")
@click.pass_context
def new(ctx: click.Context, title: str, type_: str, group: str, priority: str, blocking: bool, asked_by: str) -> None:
    """Scaffold the next D-XXXX decision file from the decisions README template."""
    try:
        desk = _desk(ctx)
        module = desk.get("decisions")
        if module is None:
            raise DeskError("the decisions module is not enabled")
        path = module.create(
            title=title, type_=type_, group=group, priority=priority, blocking=blocking, asked_by=asked_by
        )
    except DeskError as e:
        _fail(e)
    click.echo(desk.rel(path))


@cli.command()
@click.option("--plan", is_flag=True, help="Also scaffold the plan (plan/roadmap.yaml and its README).")
@click.option("--qa", is_flag=True, help="Also scaffold the Test Desk (qa/README.md and qa/runs/).")
@click.option("--skills", is_flag=True, help="Also add the Claude Code skills under .claude/skills/.")
@click.option("--all", "all_", is_flag=True, help="Everything above.")
@click.option("--lang", type=click.Choice(["en", "uk"]), default="en", show_default=True, help="UI language.")
@click.option("--hook", is_flag=True, help="Also add the SessionStart hook to .claude/settings.json.")
@click.pass_context
def init(ctx: click.Context, plan: bool, qa: bool, skills: bool, all_: bool, lang: str, hook: bool) -> None:
    """Set up a project. Never overwrites a file that exists."""
    from .scaffold import HOOK_SNIPPET, init_project

    root = (ctx.obj.get("root") or Path.cwd()).resolve()
    try:
        report = init_project(root, plan=plan or all_, qa=qa or all_, skills=skills or all_, lang=lang, hook=hook)
    except DeskError as e:
        _fail(e)
    for line in report:
        click.echo(line)
    if not hook:
        click.echo("\nTo show the desk's status at the start of every Claude Code session, add this to")
        click.echo(".claude/settings.json (or run `desk init --hook`):\n")
        click.echo(HOOK_SNIPPET)
    click.echo(
        "\nNext: `desk serve --open`, and `desk new --title ... --type product --group general` for a first request."
    )


def main(argv: list[str] | None = None) -> int:
    try:
        cli.main(args=argv, prog_name="desk", standalone_mode=True)
    except SystemExit as e:
        return int(e.code or 0) if not isinstance(e.code, str) else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
