# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The local HTTP server: the UI's static files, the core routes, and each module's routes.

Security model (see SECURITY.md): it binds to 127.0.0.1 by default; it answers only requests whose Host
header names the loopback address and its port (this blocks DNS rebinding, also when bound to 0.0.0.0
in a container); a write must be same-origin JSON under 256 KB; repo files are served only through
`resolve_repo_path` with sandboxing CSPs; and nothing is ever sent anywhere.
"""

from __future__ import annotations

import html
import json
import re
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib import resources
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from .desk import Desk
from .errors import DeskError, HttpError
from .registry import Request, Route
from .storage.paths import MIME, resolve_repo_path

MAX_BODY = 256 * 1024
STATIC_EXTS = {".js", ".css", ".html", ".svg", ".json", ".woff2"}
# script-src is narrowed to /static/ at request time (index_csp): repo files under /preview/ are same-origin
# too, and raw HTML in a Markdown body (an <iframe srcdoc> inherits this policy) must not load them as scripts.
INDEX_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "frame-src 'self'; font-src 'self'; connect-src 'self'; object-src 'none'; "
    "base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
MATERIAL_CSP = (
    "default-src 'none'; style-src 'self'; img-src 'self' data:; font-src 'self'; base-uri 'none'; form-action 'none'"
)
HTML_PREVIEW_CSP = "sandbox allow-scripts allow-popups allow-forms"  # opaque origin: no API access
SVG_PREVIEW_CSP = "sandbox; default-src 'none'; style-src 'unsafe-inline'; img-src data:"
MATERIAL_PAGE = """<!doctype html>
<html lang="{lang}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title><link rel="stylesheet" href="/static/styles.css"></head>
<body class="standalone"><main class="prose standalone-prose">
<p class="standalone-path">{path}</p>
{body}
</main></body></html>
"""


def static_root() -> Path:
    return Path(str(resources.files("project_desk").joinpath("static")))


def safe_join(base: Path, rel: str) -> Path | None:
    """`base/rel` when rel is a plain relative path that stays inside base and names a file."""
    parts = rel.split("/")
    if not rel or "\x00" in rel or "\\" in rel or any(not p or p.startswith(".") for p in parts):
        return None
    base = base.resolve()
    full = base.joinpath(*parts).resolve()
    if not full.is_relative_to(base) or not full.is_file():
        return None
    return full


def index_csp(host: str) -> str:
    """INDEX_CSP with scripts limited to the desk's own /static/ tree. `host` is an allowed Host header."""
    return INDEX_CSP.replace("script-src 'self'", f"script-src http://{host}/static/")


def loopback_hosts(port: int) -> set[str]:
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}
    if port == 80:
        hosts |= {"127.0.0.1", "localhost", "[::1]"}
    return hosts


class DeskServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, addr: tuple[str, int], desk: Desk, verbose: bool = False) -> None:
        self.desk = desk
        self.verbose = verbose
        self.routes: list[Route] = [r for m in desk.modules for r in m.routes()]
        super().__init__(addr, Handler)

    @property
    def port(self) -> int:
        return int(self.server_address[1])


class Handler(BaseHTTPRequestHandler):
    server_version = "ProjectDesk"
    sys_version = ""
    protocol_version = "HTTP/1.1"
    timeout = 30  # a client that stops sending must not hold a thread forever
    server: DeskServer

    def log_message(self, format: str, *args: Any) -> None:
        if self.server.verbose:
            super().log_message(format, *args)

    # ------------------------------------------------------------ plumbing

    def _send(self, code: int, body: bytes, ctype: str, headers: dict[str, str] | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, code: int, obj: Any) -> None:
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self._send(code, body, "application/json; charset=utf-8")

    def _fail(self, code: int, message: str) -> None:
        # An error can come before the request body is read (wrong Host, too large). Close the connection,
        # or the unread body would be parsed as the next request on it: a smuggled request that passes
        # every check.
        self.close_connection = True
        headers = {"Connection": "close"}
        if self.path.startswith("/api/"):
            body = json.dumps({"error": message}, ensure_ascii=False).encode("utf-8")
            self._send(code, body, "application/json; charset=utf-8", headers)
        else:
            self._send(code, f"{code} {message}\n".encode(), "text/plain; charset=utf-8", headers)

    def _host_ok(self) -> bool:
        """Only answer requests addressed to the loopback host (blocks DNS rebinding)."""
        return (self.headers.get("Host") or "") in loopback_hosts(self.server.port)

    def _dispatch(self, method: str) -> None:
        try:
            if not self._host_ok():
                raise HttpError(403, "unexpected Host header")
            if self.headers.get("Transfer-Encoding"):
                raise HttpError(400, "chunked requests are not supported")
            if method != "POST" and self.headers.get("Content-Length", "0") != "0":
                raise HttpError(400, "a GET request has no body")
            if method == "POST":
                self._post()
            else:
                self._get()
        except HttpError as e:
            self._fail(e.code, e.message)
        except DeskError as e:
            self._fail(422, str(e))
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as e:
            print(f"desk: error handling {self.command} {self.path}: {e!r}", file=sys.stderr)
            self._fail(500, "internal error; see the terminal running the desk")

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_HEAD(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def _module_route(self, method: str, path: str) -> tuple[Route, re.Match[str]] | None:
        for r in self.server.routes:
            if r.method == method:
                m = r.regex.fullmatch(path)
                if m:
                    return r, m
        return None

    # ------------------------------------------------------------ routes

    def _get(self) -> None:
        url = urlsplit(self.path)
        path = url.path
        desk = self.server.desk
        if path in ("/", "/index.html"):
            csp = index_csp(self.headers["Host"])
            return self._static_file(static_root() / "index.html", {"Content-Security-Policy": csp})
        if path.startswith("/static/modules/"):
            return self._module_static(path[len("/static/modules/") :])
        if path.startswith("/static/"):
            full = safe_join(static_root(), path[len("/static/") :])
            if full is None or full.suffix.lower() not in STATIC_EXTS:
                raise HttpError(404, "not found")
            return self._static_file(full)
        if path == "/api/config":
            return self._json(200, desk.client_config())
        if path == "/api/material":
            return self._material(parse_qs(url.query, keep_blank_values=True))
        if path.startswith("/preview/"):
            return self._preview(unquote(path[len("/preview/") :]), parse_qs(url.query, keep_blank_values=True))
        if path == "/favicon.ico":
            return self._send(204, b"", "image/x-icon")
        found = self._module_route("GET", path)
        if found:
            route, m = found
            return self._json(200, route.handler(Request(m, parse_qs(url.query, keep_blank_values=True))))
        raise HttpError(404, "not found")

    def _static_file(self, full: Path, headers: dict[str, str] | None = None) -> None:
        ctype = MIME.get(full.suffix.lower())
        if ctype is None:
            raise HttpError(404, "not found")
        self._send(200, full.read_bytes(), ctype, headers)

    def _module_static(self, rest: str) -> None:
        name, _, file = rest.partition("/")
        module = self.server.desk.get(name)
        full = safe_join(module.static_dir(), file) if module else None
        if full is None or full.suffix.lower() not in STATIC_EXTS:
            raise HttpError(404, "not found")
        self._static_file(full)

    def _material(self, query: dict[str, list[str]]) -> None:
        from .storage.render import render_markdown

        desk = self.server.desk
        rel = (query.get("path") or [""])[0]
        full = resolve_repo_path(desk.root, rel, {".md"})
        text = full.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"^#\s+(.+)$", text, re.M)
        self._json(
            200,
            {
                "path": rel,
                "title": m.group(1).strip() if m else full.name,
                "html": render_markdown(text, str(PurePosixPath(rel).parent), desk.root),
            },
        )

    def _preview(self, rel: str, query: dict[str, list[str]]) -> None:
        desk = self.server.desk
        full = resolve_repo_path(desk.root, rel)
        ext = full.suffix.lower()
        headers: dict[str, str] = {}
        if ext == ".md" and "raw" not in query:
            from .storage.render import render_markdown

            text = full.read_text(encoding="utf-8", errors="replace")
            body = render_markdown(text, str(PurePosixPath(rel).parent), desk.root)
            page = MATERIAL_PAGE.format(
                lang=html.escape(desk.config.content_lang),
                title=html.escape(full.name),
                path=html.escape(rel),
                body=body,
            )
            headers["Content-Security-Policy"] = MATERIAL_CSP
            return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8", headers)
        if ext == ".html":
            headers["Content-Security-Policy"] = HTML_PREVIEW_CSP
        elif ext == ".svg":
            headers["Content-Security-Policy"] = SVG_PREVIEW_CSP
        elif ext in (".woff2", ".css", ".js") and self.headers.get("Sec-Fetch-Dest") in ("script", "style", "font"):
            # Sandboxed HTML previews have an opaque origin, so their module scripts and fonts need CORS.
            # Only for those loads: a page's fetch() sends Sec-Fetch-Dest "empty" and cannot read the file.
            headers["Access-Control-Allow-Origin"] = "*"
        self._send(200, full.read_bytes(), MIME[ext], headers)

    def _post(self) -> None:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise HttpError(400, "bad Content-Length") from None
        if length < 0:
            raise HttpError(400, "bad Content-Length")
        if length > MAX_BODY:
            raise HttpError(413, "request too large")
        raw = self.rfile.read(length) if length > 0 else b""
        port = self.server.port
        origin = self.headers.get("Origin")
        if origin and origin not in {f"http://{h}" for h in loopback_hosts(port)}:
            raise HttpError(403, "cross-origin requests are not allowed")
        if not (self.headers.get("Content-Type") or "").startswith("application/json"):
            raise HttpError(415, "send application/json")
        found = self._module_route("POST", urlsplit(self.path).path)
        if not found:
            raise HttpError(404, "not found")
        try:
            payload = json.loads(raw or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            raise HttpError(400, "invalid JSON") from None
        route, m = found
        self._json(200, route.handler(Request(m, {}, payload)))


def make_server(desk: Desk, port: int | None = None, verbose: bool = False, host: str | None = None) -> DeskServer:
    return DeskServer(
        (desk.config.host if host is None else host, desk.config.port if port is None else port), desk, verbose
    )
