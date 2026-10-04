# Security

## Reporting a vulnerability

Please do not open a public issue. Use GitHub's
[private vulnerability reporting](https://github.com/kyrylo-kh/project-desk/security/advisories/new)
instead. I will reply within a week. Fixes go into the latest release only.

## Security model

Project Desk is a local tool that reads and writes files in your repo. The main threat is a web page
you visit trying to use it. The desk defends against that as follows.

- **Loopback only.** It binds to `127.0.0.1` by default.
- **Host allow-list.** A request must carry `Host: 127.0.0.1:PORT`, `localhost:PORT` or
  `[::1]:PORT`. This blocks DNS rebinding, also when the desk listens on `0.0.0.0` in a container.
- **Writes are same-origin JSON.** A POST with a foreign `Origin` is refused. It must be
  `application/json` and at most 256 KB, so a cross-site form or a simple `fetch()` cannot send it.
  A refused request closes the connection, so nothing hidden in its body is read as a second request.
- **No lost edits.** Every save carries the file's etag. If the file changed on disk, the save is
  refused (409).
- **Path safety.** Repo files are served through one resolver. It refuses `..`, absolute paths,
  dotfiles, and anything that resolves outside the repo or, through a symlink, to a hidden file.
- **Locked-down pages.** The UI has a strict CSP: scripts only from the desk's own `/static/`, no
  inline scripts or styles, `frame-ancestors 'none'`. HTML previews run in a sandbox with an opaque
  origin, so they cannot call the API. SVG and Markdown previews get their own restrictive CSPs.
- **Nothing is sent anywhere.** No telemetry, CDN or web fonts. The desk makes no outbound requests.
  (An HTML preview from your repo can, like any page you open.)

## What you must trust

- **Your repo's files.** Markdown is rendered with raw HTML allowed, as on GitHub. The CSP stops
  scripts in it, but do not point the desk at a repo whose files you do not trust.
- **Your config.** `modules = ["pkg.module:Class"]` in `.project-desk.toml` or `pyproject.toml`
  imports and runs that Python code, also from `desk summary` in the SessionStart hook. Treat the
  config like code.
- **Your network.** The desk has no login. Never expose its port beyond loopback: with
  `--host 0.0.0.0` outside a container, or `docker run -p 4700:4700`, anyone on your network can read
  and answer your decisions.
