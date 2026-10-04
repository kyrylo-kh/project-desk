# Architecture

Project Desk is a small Python package with a browser UI. It has three desks, each a built-in
module with one tab: the Plan (`plan`), the Decision Desk (`decisions`) and the Test Desk (`qa`).
The files in the user's repo are the source of truth. The desk reads them on every request and
keeps no database and no cache that could go stale. It writes only the human's part of a file.

```
src/project_desk/
  cli.py            thin Click CLI: parse arguments, call the desk, print
  server.py         thin stdlib HTTP server: security checks, static files, core routes, module routes
  desk.py           Desk: one root, its Config, the enabled modules; summary, brief, validate, /api/config
  config.py         .project-desk.toml / [tool.project-desk] (and the legacy names): defaults, types, root discovery
  registry.py       the Module interface (+ Route, Request, Validation, Brief, Ask) and module loading
  i18n.py           Translator over locales/*.json (shared with the browser)
  scaffold.py       desk init: templates, never overwrite, the SessionStart hook merge
  text.py, errors.py
  storage/          files: frontmatter docs, surgical YAML edits, the fast line reader, paths, Markdown
  modules/
    decisions/      model, rules, answer (writes), new (desk new), fast (summary/brief), module
    qa/             model, rules, edits (writes), fast, module
    plan/           model, rules, module (read-only)
  static/           index.html, styles.css, js/ (the shell), modules/<name>/ (one tab each)
  locales/          en.json, uk.json
  templates/        the READMEs, the plan template, the Claude Code skills that `init` copies
```

## Layers

Each layer depends only on the layers below it.

1. **Storage** (`storage/`). This layer knows how files look on disk, not what they mean.
   - `Doc` is a Markdown file with YAML frontmatter, held byte for byte. It has an `etag`, which is
     a content hash.
   - `edits` changes one scalar in place and leaves every other byte alone.
   - `yamlio` is the ruamel round trip, used as the fallback. It keeps comments.
   - `quick` and `lines` read the block-style YAML subset that the files use, without importing
     a YAML library.
   - `paths` is the one resolver for repo-relative paths. It refuses anything that leaves the root.
   - `render` turns Markdown into HTML and points relative links at `/preview/`.
2. **Domain models and rules** (`modules/*/model.py`, `rules.py`). This layer covers what a decision,
   run or plan is. The models are typed dataclasses built from raw data. The rules validate the
   *raw* data, so they can explain a malformed file instead of crashing on it.
3. **Services** (`modules/*/module.py`, `answer.py`, `qa/edits.py`, `new.py`). Each module's
   `Module` subclass holds its use cases: list, detail, save an answer, mark a case, finish a run,
   validate, summary and brief. These run the same way from the CLI, the HTTP server and the
   tests. A stale etag raises `HttpError(409)` from the service itself.
4. **Interfaces.** `cli.py` and `server.py` contain no business logic. They parse input, call a
   service and serialise the result.

## Modules and the registry

`registry.Module` is the whole contract between the core and a kind of content:

| Member | Used by |
|---|---|
| `name`, `label_key`, `hotkey`, `defaults` | config, the tab bar |
| `tab_order` | the tab bar; the first tab is the default view (Plan 10, Decision Desk 20, Test Desk 30) |
| `summary_order` | `summary` and `validate`: what the agent must act on first comes first (decisions, tests, plan) |
| `detect(root, settings)` | zero config: is this module on when `modules` is not set? |
| `routes()` | the server mounts each `Route(method, regex, handler)` |
| `validate()` | `desk validate` |
| `ids()` | cross-references, such as plan items that name decisions |
| `summary()` / `brief(b)` | `desk summary` (English, for the agent) and `desk brief` (UI language) |
| `static_dir()`, `client()`, `client_settings()` | the browser tab |

`Desk._load_modules` resolves each entry in `modules`. An entry is a built-in name, an entry point
in `project_desk.modules`, or `package.module:Class`. The loader then type-checks each module's
`[table]` against `defaults` and sorts the modules by `tab_order`; `Desk.by_summary()` gives them in
`summary_order`. Without `modules`, it loads `decisions` and each other module whose `detect` says its
files exist. Listing modules in `modules` turns the others off, whatever order they are listed in.

Modules talk to each other only through `desk.get(name)` and duck-typed methods. For example, the
plan asks the decisions module to `describe(ids)` for its decision chips. Every such call handles
the case where the other module is off.

## The fast path

A SessionStart hook runs `desk summary` at the start of every agent session. `desk brief` runs in a
terminal. Both must be quick and must never fail:

- They import neither `ruamel.yaml` nor `markdown`. A test checks this in a subprocess.
- Each module's `fast.py` reads its files with `storage.quick`. `validate` warns when the quick reader
  and ruamel disagree about a file, so drift shows up at once.
- `Desk.summary_text` and `brief_text` catch any error from one module, so a broken module never hides
  the others. `desk summary` always exits 0.

## Writes

Only the human's fields are written. That means a decision's `status` and `answer.*`, and a QA run's
`status`, the run note and each case's `result`, `note` and `at`. A write takes these steps:

1. The service loads the `Doc` under `desk.lock`, which serialises writes in the threaded server.
2. If the request carries an etag that differs from the file's, the service raises 409.
3. `storage.edits` replaces each value in place. The result is parsed again and compared with the
   intended data. On any mismatch, the write goes through a ruamel round trip instead.
4. The file is written atomically: a temporary file in the same folder, then `os.replace`.

## HTTP

`server.py` is `http.server.ThreadingHTTPServer` and nothing else. It handles each request in
this order:

1. **Host check.** It answers only `127.0.0.1:PORT`, `localhost:PORT` and `[::1]:PORT`, which blocks
   DNS rebinding, even on `0.0.0.0`.
2. **POST only:**
   - an `Origin`, if present, must be the desk's own;
   - the body must be `application/json` and at most 256 KB.
3. **Core routes:**
   - `/`: `index.html` with the strict CSP;
   - `/static/...`;
   - `/static/modules/<name>/...`: from that module's `static_dir()`, and 404 if the module is off;
   - `/api/config`;
   - `/api/material?path=`: a Markdown file rendered to HTML;
   - `/preview/<path>`: a repo file with a per-type sandbox CSP. `?raw` sends Markdown as text.
4. **Module routes**, the first full regex match. Errors map as follows:
   - `HttpError(code)` → that code;
   - `DeskError` → 422;
   - anything else → 500, with the details printed to the terminal only.

Every response carries `Cache-Control: no-store`, `X-Content-Type-Options: nosniff` and
`Referrer-Policy: no-referrer`.

## The frontend

Plain ES modules with no build step. `index.html` loads one script, `static/js/main.js`, which is the
shell:

1. It fetches `/api/config`, which carries the UI language's strings (English merged with the
   language) and the enabled modules.
2. It translates the static markup through `data-i18n` and `data-i18n-aria`.
3. For each module, it adds a tab switch and a `<div class="tab-root">`, imports the module's
   `tab.js` and calls `createTab(ctx)`.
4. It routes on the hash, which is `#<module>/<rest>`. An empty hash opens the first tab. A hash that
   names no module goes whole to the first tab whose `claims(hash)` says it is its own (so an old
   `#D-0001` link still opens the decision), else to the first tab.
5. It owns the global keys:
   - `g` + a tab's hotkey;
   - `?` for help;
   - the preview viewer's keys.

   It passes every other key to the active tab's `keydown`.
6. Every 5 seconds, and when the window gets focus, it calls each tab's `refresh()`. The tab bar
   shows "synced" or "offline". A tab sets the badge on its switch with `ctx.setBadge(value, title,
   kind)`: `mark` (waits on the human), `hot` (waits and blocks work) or `label` (information, like
   the Plan's current item). The Plan refreshes while closed too, to keep its badge current.
7. Before the page closes, it asks each tab's `unsaved()`.

A tab is split in two:

- **`render.js`** holds pure functions from API data to HTML strings. It has no DOM access, so the
  tests import it in Node and check the output in both languages, including XSS cases. Every value
  from a file goes through `esc()`. Locale strings are trusted markup. `i18n.h()` escapes every
  parameter unless the caller wraps it in `html()`.
- **`tab.js`** holds the state, events, keys and API calls. It renders with `render.js`.

The CSP (`script-src http://<host>/static/; style-src 'self'`) forbids inline scripts, inline styles,
event handler attributes and scripts from anywhere but the desk's own `/static/`. The UI uses delegated listeners on `data-action` attributes instead.

`js/` holds what the tabs share:

- `util.js`: escaping, link detection, dates, `localStorage` under a `project-desk:` prefix (values
  saved under the old `decision-desk:` prefix are still read);
- `i18n.js`: lookup, plurals in the same CLDR rules as `i18n.py`, and `day()`;
- `api.js`: `fetch` with errors that carry `.status`;
- `ui.js`: toast, the preview lightbox, the help overlay;
- `theme.js`: a classic (non-module) script in `<head>` that applies the viewer's saved theme before
  the first paint. `main.js` then fills the switcher and applies the config's `theme` when the viewer
  has not picked one.

### Themes

`styles.css` starts with one block of tokens per theme: `:root, :root[data-theme="light"]`, a
`prefers-color-scheme: dark` copy of the dark block for `auto` (no `data-theme` attribute), and
`:root[data-theme="dark|contrast|manila|terminal"]`. The rest of the file uses only the tokens. Pair
tokens (backgrounds, text, `accent`, `mark`, the state colours and their `on-*` partners) are opaque
hex, so `tests/test_themes.py` can compute the WCAG contrast of every pair in every theme: 4.5:1 for
text, 3:1 for `control`, `focus` and `mark-line`. It also checks that the auto-dark block equals the
dark one and that the theme lists in `config.py`, `main.js`, `theme.js` and the locales agree. To add
a theme, add its block, its name to those lists and `theme.<name>` to each locale; the test then
tells you which pairs fail.

## i18n

`locales/en.json` and `uk.json` are flat maps. A value is one of:

- a string with `{name}` placeholders;
- a list, such as month names;
- a plural table: `{one, other}` in English, `{one, few, many}` in Ukrainian.

The browser and `brief` use the same files. `summary` is always English, because it is written for
the agent. Tests check that both locales have the same keys, kinds and placeholders, and that every
key used in `static/` and in the Python code exists.

## Testing

`tests/support.py` holds deliberately awkward fixtures: aligned comments, quoted and folded scalars,
indentless lists, and non-ASCII text. Each test works on copies under `tmp_path`. The groups:

- **Storage:** round trips and byte-exact edits.
- **Modules:** every validation rule, and each module's services.
- **Server:** a real `DeskServer` on port 0, with raw `http.client` requests, so the Host, Origin,
  content-type and path checks run against real bytes.
- **Frontend:** `node_eval` imports the ES modules in Node and returns the rendered HTML.
- **Config, registry, init, CLI:** each has its own file.
