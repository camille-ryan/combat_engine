# UI

The page. Vanilla JS as ES modules, no build step, no framework, no
dependencies. `app.js` (state and rendering), `card.js` (hover cards),
`anim.js`, `coords.js`, `dom.js`, `index.html`, `style.css`.

Global rules are in the root `CLAUDE.md`.

## What holds this together, and what does not

* **`lint.py` never looks at `web/`.** It is ruff over Python only, so the
  JavaScript here is unlinted. `node --check <file>` is the minimum before
  committing; it catches a syntax error and nothing else.
* **`scripts/browser.py` is the entire cover** — headless Chromium, clicks
  the real page, reads the DOM back. It is the slowest instrument in the
  suite and it earns its seconds: an event stream under the wrong frame name
  and an animation keyed to a spelling nothing emitted were both invisible to
  every other check, because the JSON was perfectly correct and the page
  ignored it.
* **The DTO field names are a hand-maintained contract** with `api/dto.py`.
  No generated client, no schema. A rename is a two-component change and
  nothing will tell you if you miss a site.

## Rules

* **Pin the seed for any check that depends on the kit.** The fight the page
  opens with used to be drawn fresh, so whether the acting creature carried
  an area power was a coin toss: runs counted 40, 47, then 48 checks, and one
  reported `47 passed, 2 failed` while the next passed. **A count that moves
  hides a failure as easily as a skip.** `START_SEED`, `BLAST_SEED`,
  `AIMLESS_SEED` and `TRAP_SEED` exist for this.
* **Assert the absence, not just the presence.** A dead board and a board the
  server refused are indistinguishable in the DOM, so a check that a click
  does nothing must assert that **no `/aim` or `/act` call was made**, not
  merely that no token moved.
* **Ask whether a control is enabled before clicking it.** Playwright retries
  a disabled button for thirty seconds and then raises, so a real regression
  reports itself as a harness timeout — true, and useless to read.
* **The server decides the rules; the page draws them.** Which squares a
  burst covers, what a blast catches, whether a creature may walk somewhere —
  all come over the wire. Do not reimplement a rule here, even a simple one.
* **Three overlay layers**, same size, absolutely positioned: `#board`
  (tiles, zones, things, tokens), `#movement` (range, pending answers),
  `#highlights` (aim, hit, path, origin). Append into `#board` between the
  zone loop and the token loop so a creature standing on something still
  wins the hover. `renderBoard` clears and redraws everything each render —
  nothing here is incremental.
* **`browser.py` asserts on class names**, so renaming a CSS class is a
  two-file change. Adding nodes is safe.

## Seam

`web/` reaches `api/` over HTTP and nothing else. It imports no Python and no
Python imports it. Nine endpoint paths are hardcoded in `app.js`.

The settings panel keeps two things in `localStorage` that change behaviour
enough to matter when reproducing a bug: `dnd4e.freeform` (clicking the board
to target, off by default) and `dnd4e.speed`.
