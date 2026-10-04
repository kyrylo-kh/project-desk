# SPDX-FileCopyrightText: 2026 Kyrylo Kholodenko
# SPDX-License-Identifier: FSL-1.1-ALv2
"""The HTTP layer: routes, the security checks, and the files it serves."""

from __future__ import annotations

import json
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

from project_desk.desk import Desk
from project_desk.server import DeskServer, loopback_hosts, safe_join
from project_desk.storage.doc import parse_doc

from support import ABOUT, TLDR, decision_path, make_plan, post, request, serving, write_config


@pytest.fixture
def server(repo: Path) -> Iterator[DeskServer]:
    with serving(Desk(repo)) as srv:
        yield srv


@pytest.fixture
def qa_server(qa_repo: Path) -> Iterator[DeskServer]:
    with serving(Desk(qa_repo)) as srv:
        yield srv


def origin(srv: DeskServer) -> str:
    return f"http://127.0.0.1:{srv.port}"


# --------------------------------------------------------------------------- security


@pytest.mark.parametrize(
    "path",
    [
        "/preview/../../../etc/passwd",
        "/preview/%2e%2e/%2e%2e/etc/passwd",
        "/preview/..%2f..%2fetc%2fpasswd",
        "/preview//etc/passwd",
        "/preview/.git/config",
        "/preview/package.json",
        "/preview/design/x/%2e%2e/%2e%2e/%2e%2e/etc/hosts.png",
        "/api/material?path=../../etc/passwd.md",
        "/static/../pyproject.toml",
        "/static/%2e%2e/desk.py",
        "/static/modules/decisions/../../../desk.py",
        "/static/modules/../index.html",
    ],
)
def test_traversal_is_refused(server: DeskServer, path: str) -> None:
    status, _, body = request(server, "GET", path)
    assert status in (403, 404)
    assert b"root:" not in body and b"import" not in body


@pytest.mark.parametrize(
    "host",
    ["evil.example", "evil.example:80", "127.0.0.1", "127.0.0.1:1", "localhost.evil.example:{port}", ""],
)
def test_foreign_host_is_refused(server: DeskServer, host: str) -> None:
    """DNS rebinding: a page on evil.example that resolves to 127.0.0.1 still sends its own Host."""
    status, _, body = request(server, "GET", "/api/decisions", headers={"Host": host.format(port=server.port)})
    assert status == 403 and b"Pick a palette" not in body


@pytest.mark.parametrize("host", ["127.0.0.1:{port}", "localhost:{port}", "[::1]:{port}"])
def test_loopback_hosts_are_answered(server: DeskServer, host: str) -> None:
    status, _, _ = request(server, "GET", "/api/decisions", headers={"Host": host.format(port=server.port)})
    assert status == 200


def test_loopback_hosts_need_the_port_unless_it_is_80() -> None:
    assert "127.0.0.1" not in loopback_hosts(4700) and "localhost:4700" in loopback_hosts(4700)
    assert "localhost" in loopback_hosts(80)


@pytest.mark.parametrize(
    "bad_origin", ["http://evil.example", "null", "http://127.0.0.1:1", "https://127.0.0.1:{port}"]
)
def test_foreign_origin_cannot_write(server: DeskServer, repo: Path, bad_origin: str) -> None:
    before = decision_path(repo).read_bytes()
    status, _, _ = post(
        server, "/api/decisions/D-0001/answer", {"choice": "a"}, Origin=bad_origin.format(port=server.port)
    )
    assert status == 403
    assert decision_path(repo).read_bytes() == before


def test_writes_must_be_json_and_small(server: DeskServer, repo: Path) -> None:
    before = decision_path(repo).read_bytes()
    status, _, _ = request(
        server, "POST", "/api/decisions/D-0001/answer", {"choice": "a"}, {"Content-Type": "text/plain"}
    )
    assert status == 415  # a cross-site form cannot send application/json without a preflight
    big = {"choice": "a", "comment": "x" * (300 * 1024)}
    assert post(server, "/api/decisions/D-0001/answer", big)[0] == 413
    status, _, body = request(
        server,
        "POST",
        "/api/decisions/D-0001/answer",
        headers={"Content-Type": "application/json"},
        raw=b"{not json",
    )
    assert status == 400 and json.loads(body) == {"error": "invalid JSON"}
    assert post(server, "/api/decisions/D-0001/nope", {})[0] == 404
    assert post(server, "/api/decisions", {})[0] == 404
    assert decision_path(repo).read_bytes() == before


def _raw_exchange(srv: DeskServer, data: bytes) -> bytes:
    """Send raw bytes on one connection and read until the server closes it."""
    with socket.create_connection(("127.0.0.1", srv.port), timeout=5) as sock:
        try:
            sock.sendall(data)
        except (BrokenPipeError, ConnectionResetError):
            pass
        out = b""
        try:
            while chunk := sock.recv(65536):
                out += chunk
        except (ConnectionResetError, TimeoutError):
            pass
    return out


@pytest.mark.parametrize("case", ["too-large", "wrong-host"])
def test_an_unread_body_is_never_parsed_as_a_second_request(server: DeskServer, repo: Path, case: str) -> None:
    """A refused request whose body was not read closes the connection, so a request hidden in that body
    (same-origin Host, JSON, no Origin) cannot ride on it. A cross-site text/plain fetch could send one."""
    before = decision_path(repo).read_bytes()
    payload = json.dumps({"choice": "a", "comment": "smuggled"}).encode()
    inner = (
        f"POST /api/decisions/D-0001/answer HTTP/1.1\r\nHost: 127.0.0.1:{server.port}\r\n"
        f"Content-Type: application/json\r\nContent-Length: {len(payload)}\r\n\r\n"
    ).encode() + payload
    body = inner + b"A" * (300 * 1024) if case == "too-large" else inner
    host = f"127.0.0.1:{server.port}" if case == "too-large" else "evil.example"
    head = (
        f"POST /api/decisions/D-0001/answer HTTP/1.1\r\nHost: {host}\r\n"
        f"Content-Type: text/plain\r\nContent-Length: {len(body)}\r\n\r\n"
    ).encode()
    out = _raw_exchange(server, head + body)
    assert out.count(b"HTTP/1.1 ") == 1 and b"Connection: close" in out
    assert decision_path(repo).read_bytes() == before


@pytest.mark.parametrize(
    "headers",
    [{"Transfer-Encoding": "chunked"}, {"Content-Length": "-5"}],
)
def test_chunked_and_negative_lengths_are_refused(server: DeskServer, headers: dict[str, str]) -> None:
    head = f"POST /api/decisions/D-0001/answer HTTP/1.1\r\nHost: 127.0.0.1:{server.port}\r\n"
    head += "Content-Type: application/json\r\n" + "".join(f"{k}: {v}\r\n" for k, v in headers.items())
    out = _raw_exchange(server, head.encode() + b"\r\n")
    assert out.startswith(b"HTTP/1.1 400") and b"Connection: close" in out


def test_same_origin_write_and_no_origin_write(server: DeskServer, repo: Path) -> None:
    assert post(server, "/api/decisions/D-0001/answer", {"choice": "a"}, Origin=origin(server))[0] == 200
    assert post(server, "/api/decisions/D-0001/answer", {"choice": "b"})[0] == 200  # curl and scripts send none
    assert parse_doc(decision_path(repo)).data["answer"]["choice"] == "b"


def test_every_response_has_the_safety_headers(server: DeskServer) -> None:
    for path in ("/", "/api/decisions", "/nope", "/preview/design/x/preview.png"):
        _, headers, _ = request(server, "GET", path)
        assert headers["X-Content-Type-Options"] == "nosniff", path
        assert headers["Cache-Control"] == "no-store", path
        assert headers["Referrer-Policy"] == "no-referrer", path


def test_index_is_locked_down(server: DeskServer) -> None:
    status, headers, body = request(server, "GET", "/")
    assert status == 200 and headers["Content-Type"].startswith("text/html")
    csp = headers["Content-Security-Policy"]
    assert f"script-src http://127.0.0.1:{server.port}/static/;" in csp and "'self'; script" in csp
    assert "frame-ancestors 'none'" in csp and "unsafe-inline" not in csp
    assert b"/static/js/main.js" in body
    _, headers, _ = request(server, "GET", "/", headers={"Host": f"localhost:{server.port}"})
    assert f"script-src http://localhost:{server.port}/static/;" in headers["Content-Security-Policy"]


def test_repo_scripts_get_cors_only_as_preview_subresources(server: DeskServer, repo: Path) -> None:
    """A sandboxed HTML preview (opaque origin) loads modules and fonts with CORS; another site's fetch()
    must not be able to read repo source the same way."""
    (repo / "design" / "x" / "app.js").write_text("export const k = 1;\n")
    status, headers, _ = request(server, "GET", "/preview/design/x/app.js")
    assert status == 200 and "Access-Control-Allow-Origin" not in headers
    _, headers, _ = request(server, "GET", "/preview/design/x/app.js", headers={"Sec-Fetch-Dest": "empty"})
    assert "Access-Control-Allow-Origin" not in headers
    _, headers, _ = request(server, "GET", "/preview/design/x/app.js", headers={"Sec-Fetch-Dest": "script"})
    assert headers["Access-Control-Allow-Origin"] == "*"


def test_a_symlink_cannot_lead_to_a_hidden_file(server: DeskServer, repo: Path) -> None:
    (repo / ".env").write_text("TOKEN=secret\n")
    (repo / "design" / "x" / "notes.md").symlink_to(repo / ".env")
    (repo / "design" / "x" / "app.js").symlink_to(repo / ".env")
    for path in ("/preview/design/x/notes.md?raw", "/preview/design/x/app.js"):
        status, _, body = request(server, "GET", path)
        assert status == 403 and b"secret" not in body, path


def test_preview_ok_and_sandboxed(server: DeskServer) -> None:
    status, headers, _ = request(server, "GET", "/preview/design/x/preview.png")
    assert status == 200 and headers["Content-Type"] == "image/png"
    status, headers, _ = request(server, "GET", "/preview/design/x/preview.html")
    assert status == 200 and headers["Content-Security-Policy"].startswith("sandbox")
    status, headers, body = request(server, "GET", "/preview/decisions/material/D-0001-notes.md")
    assert status == 200 and b"<h1>Notes</h1>" in body and "default-src 'none'" in headers["Content-Security-Policy"]
    assert b'<html lang="en">' in body
    status, headers, body = request(server, "GET", "/preview/decisions/material/D-0001-notes.md?raw")
    assert status == 200 and body.startswith(b"# Notes")


def test_material_is_rendered(server: DeskServer) -> None:
    status, _, body = request(server, "GET", "/api/material?path=decisions/material/D-0001-notes.md")
    data = json.loads(body)
    assert status == 200 and data["title"] == "Notes" and "<h1>Notes</h1>" in data["html"]
    assert request(server, "GET", "/api/material?path=design/x/preview.png")[0] == 403


def test_head_and_unknown_paths(server: DeskServer) -> None:
    status, headers, body = request(server, "HEAD", "/api/decisions")
    assert status == 200 and body == b"" and int(headers["Content-Length"]) > 0
    status, _, body = request(server, "GET", "/api/nope")
    assert status == 404 and json.loads(body) == {"error": "not found"}
    assert request(server, "GET", "/favicon.ico")[0] == 204


def test_safe_join(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "b.js").write_text("x")
    assert safe_join(tmp_path, "a/b.js") == (tmp_path / "a" / "b.js").resolve()
    for rel in ("", "a", "../a/b.js", "a/../a/b.js", "/a/b.js", "a\\b.js", ".a/b.js", "a//b.js", "a/b.js\x00"):
        assert safe_join(tmp_path, rel) is None, rel


# --------------------------------------------------------------------------- the client config and static files


def test_config_names_the_enabled_modules(server: DeskServer) -> None:
    status, _, body = request(server, "GET", "/api/config")
    cfg = json.loads(body)
    assert status == 200 and cfg["lang"] == "en" and cfg["content_lang"] == "en" and cfg["theme"] == "auto"
    assert [m["name"] for m in cfg["modules"]] == ["decisions"]
    m = cfg["modules"][0]
    assert m["label"] == "Decision Desk" and m["hotkey"] == "d" and m["script"] == "/static/modules/decisions/tab.js"
    assert m["settings"]["types"][0] == "product"
    assert cfg["strings"]["tab.qa"] == "Test Desk"


def test_config_in_ukrainian(repo: Path) -> None:
    write_config(repo, 'lang = "uk"\ncontent_lang = "en"\ntheme = "terminal"\n')
    make_plan(repo)
    with serving(Desk(repo)) as srv:
        cfg = json.loads(request(srv, "GET", "/api/config")[2])
    assert (cfg["lang"], cfg["content_lang"], cfg["theme"]) == ("uk", "en", "terminal")
    assert [m["label"] for m in cfg["modules"]] == ["План", "Рішення"]  # the Plan is the first tab
    assert cfg["strings"]["tab.qa"] == "Тести"


def test_static_files_and_module_scripts(server: DeskServer) -> None:
    for path, ctype in (
        ("/static/styles.css", "text/css"),
        ("/static/js/main.js", "text/javascript"),
        ("/static/modules/decisions/tab.js", "text/javascript"),
        ("/static/modules/decisions/render.js", "text/javascript"),
    ):
        status, headers, _ = request(server, "GET", path)
        assert status == 200 and headers["Content-Type"].startswith(ctype), path
    # A module that is not on serves nothing.
    assert request(server, "GET", "/static/modules/plan/tab.js")[0] == 404
    assert request(server, "GET", "/static/modules/qa/tab.js")[0] == 404


# --------------------------------------------------------------------------- decisions over HTTP


def test_list_detail_and_answer(server: DeskServer, repo: Path) -> None:
    status, _, body = request(server, "GET", "/api/decisions")
    listing = json.loads(body)
    assert status == 200 and listing["counts"]["pending"] == 1 and listing["counts"]["blocking"] == 1

    status, _, body = request(server, "GET", "/api/decisions/D-0001")
    detail = json.loads(body)
    assert status == 200 and "<table>" in detail["body_html"]

    status, _, body = post(
        server,
        "/api/decisions/D-0001/answer",
        {"choice": "a", "comment": "ok", "etag": detail["etag"]},
        Origin=origin(server),
    )
    assert status == 200, body
    assert parse_doc(decision_path(repo)).data["status"] == "answered"

    status, _, body = post(server, "/api/decisions/D-0001/answer", {"choice": "b", "etag": detail["etag"]})
    assert status == 409 and "changed on disk" in json.loads(body)["error"]
    assert request(server, "GET", "/api/decisions/D-0009")[0] == 404


def test_tldr_and_about_are_served(server: DeskServer) -> None:
    listing = json.loads(request(server, "GET", "/api/decisions")[2])
    assert listing["decisions"][0]["tldr"] == TLDR and listing["decisions"][0]["about"] == ABOUT
    detail = json.loads(request(server, "GET", "/api/decisions/D-0001")[2])
    assert detail["tldr"] == TLDR and detail["about"] == ABOUT
    assert detail["data"]["tldr"] == TLDR + "\n"  # the raw frontmatter value is passed through too
    assert detail["data"]["about"].startswith("Яку палітру")


# --------------------------------------------------------------------------- plan over HTTP


def test_plan_rereads_the_file(repo: Path) -> None:
    write_config(repo, 'modules = ["decisions", "plan"]\n')
    with serving(Desk(repo)) as srv:
        status, headers, body = request(srv, "GET", "/api/plan")
        assert status == 200 and headers["Content-Type"].startswith("application/json")
        assert json.loads(body) == {"file": "plan/roadmap.yaml", "exists": False}  # no plan yet: friendly, not 404
        make_plan(repo)
        assert json.loads(request(srv, "GET", "/api/plan")[2])["now"] == "S1"
        from support import PLAN

        make_plan(repo, PLAN.replace("now: S1", "now: S2").replace("status: next", "status: doing"))
        assert json.loads(request(srv, "GET", "/api/plan")[2])["now"] == "S2"


def test_plan_route_is_absent_when_the_module_is_off(server: DeskServer) -> None:
    assert request(server, "GET", "/api/plan")[0] == 404


# --------------------------------------------------------------------------- QA over HTTP


def test_qa_list_detail_mark_and_finish(qa_server: DeskServer) -> None:
    status, _, body = request(qa_server, "GET", "/api/qa")
    assert status == 200
    qa = json.loads(body)
    assert [r["id"] for r in qa["runs"]] == ["R-0001"] and qa["runs"][0]["marked"] == 0

    status, _, body = request(qa_server, "GET", "/api/qa/R-0001")
    run = json.loads(body)
    assert status == 200 and len(run["cases"]) == 3 and run["etag"]

    status, _, body = post(qa_server, "/api/qa/R-0001/case/T01", {"etag": run["etag"], "result": "fail", "note": "x"})
    assert status == 200
    run2 = json.loads(body)
    assert run2["status"] == "in-progress" and run2["cases"][0]["result"] == "fail" and run2["etag"] != run["etag"]

    assert post(qa_server, "/api/qa/R-0001/case/T02", {"etag": run["etag"], "result": "pass"})[0] == 409

    status, _, body = post(qa_server, "/api/qa/R-0001/finish", {"etag": run2["etag"]})
    assert status == 400 and "T02, T03" in json.loads(body)["error"]

    status, _, body = post(qa_server, "/api/qa/R-0001/note", {"etag": run2["etag"], "note": "Добре"})
    assert status == 200 and json.loads(body)["overall_note"] == "Добре"

    for cid in ("T02", "T03"):
        assert post(qa_server, f"/api/qa/R-0001/case/{cid}", {"result": "pass"})[0] == 200
    status, _, body = post(qa_server, "/api/qa/R-0001/finish", {})
    assert status == 200 and json.loads(body)["status"] == "done"

    assert request(qa_server, "GET", "/api/qa/R-0009")[0] == 404
    assert post(qa_server, "/api/qa/R-0001/case/T01", {"result": "nope"})[0] == 400
    assert post(qa_server, "/api/qa/R-0001/case/T01", {"result": "pass"}, Origin="http://evil.example")[0] == 403
    assert post(qa_server, "/api/qa/R-0001/close", {})[0] == 404
