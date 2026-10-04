# Writing a module

A *module* is one kind of content: its files, its validation, its HTTP routes, its lines in
`summary` and `brief`, and one tab in the UI. The three desks (`plan`, `decisions`, `qa`) are built-in
modules that use the same interface a plugin uses. Adding one needs no change to the core.

1. **Python.** Subclass `project_desk.registry.Module`:

   ```python
   from pathlib import Path
   from project_desk.registry import Ask, Brief, Module, Route, Validation


   class Notes(Module):
       name = "notes"  # also the [notes] config table and the URL prefix
       label_key = ""  # an i18n key for the tab label; "" uses the name
       hotkey = "n"  # `g n` opens the tab
       tab_order = 40  # place in the tab bar (Plan 10, Decision Desk 20, Test Desk 30)
       summary_order = 40  # place in summary and validate
       defaults = {"dir": "notes"}  # settings, type-checked against these defaults

       @classmethod
       def detect(cls, root, settings):  # on by default when its files exist
           return (root / settings["dir"]).is_dir()

       def files(self):
           return sorted((self.root / self.settings["dir"]).glob("*.md"))

       def routes(self):
           return [Route("GET", r"/api/notes", lambda req: {"files": [p.name for p in self.files()]})]

       def validate(self):
           return Validation(f"{len(self.files())} note(s)", [])

       def summary(self):  # English, for the agent; keep it import-free and fast
           return f"Notes: {len(self.files())}"

       def brief(self, b: Brief):
           b.asks.append(Ask(rank=5, text="Read the new notes"))

       def static_dir(self):  # served at /static/modules/notes/
           return Path(__file__).parent / "static"
   ```

   A route handler gets a `Request` (`match`, `query`, `payload`), returns anything JSON-able, and
   raises `HttpError(status, message)` to refuse. POST routes get the Host, Origin, content-type and
   size checks automatically.

2. **The tab.** `static/tab.js` exports `createTab(ctx)` and returns the hooks the shell calls. Every
   hook is optional:

   ```js
   export function createTab(ctx) {
     ctx.el.className = 'plan';
     return {
       async load() {                           // the first time the tab opens
         const data = await ctx.api('/api/notes');
         ctx.el.textContent = data.files.join(', ');
       },
       refresh() { return this.load(); },       // every 5 s and on window focus
       route(rest, entering) {},                // #notes/<rest>
       keydown(e, typing) { return false; },    // true when handled
       help() { return [[['j', 'k'], 'Next / previous note']]; },  // rows for the ? overlay
       unsaved() { return false; },             // true asks before the page closes
     };
   }
   ```

   `ctx` gives you `el`, `api`, `postJson`, `i18n` (`t`, `h`, `n`, `day`), `ui` (toast and the
   preview viewer), `settings` (your module's `client_settings()`), `setBadge`, `setRoute` and
   `isActive`. Reuse the classes in `styles.css` to match the look.

3. **Turn it on.** Either list it by import path:

   ```toml
   modules = ["plan", "decisions", "my_package.notes:Notes"]

   [notes]
   dir = "docs/notes"
   ```

   or register an entry point in your package so that `modules = ["decisions", "notes"]` works:

   ```toml
   [project.entry-points."project_desk.modules"]
   notes = "my_package.notes:Notes"
   ```

[architecture.md](architecture.md) describes the layers and the request flow in more detail.
