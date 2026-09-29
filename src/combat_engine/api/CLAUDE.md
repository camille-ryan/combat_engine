# Wire

Engine state → DTOs → the page. `app.py` (endpoints), `session.py` (one
encounter held across requests), `dto.py` (what crosses the wire),
`render.py` (state → what the page draws), `wire.py` (ids → names).

Global rules are in the root `CLAUDE.md`.

## The one place the name rule is crossed on purpose

`wire.py` is the boundary where refs become printed names, reading
`localization/names.json`. It is the only component allowed to do that, which
makes it the one to be careful in:

* Everything user-facing goes through `wire.power()`, `wire.label()`,
  `wire.printed()`. Never read the localisation file directly.
* `CE_NAMES=off` must serve refs instead of names, and `api_smoke.py` checks
  it. Any new field carrying a name has to honour it — a trap label was
  added this way and only the check caught that it needed testing both ways.
* A **new id namespace** is sometimes required, not stylistic.
  `Wire._creatures` filters on `Health`, so `wire.id()` returns `None` for a
  trap, a zone, a conjuration or scenery. `Wire.zone()` and `Wire.thing()`
  exist for that reason; an `npc_*` id for a trap would be a lie.

## Do not recompute what the engine already decided

`render.py` holds real presentation rules — where a power may be aimed, what
each aim square would cover, where a creature may walk. The failure mode is
**painting a square the server will then refuse**, and it has happened three
ways at once: a prone creature drawn a full movement range, a "shift 2 as a
move action" stance drawn as one square, and running drawn not at all. One
algorithm, three wrong answers, because `render` was passing its own
arguments instead of reading the engine's options.

So: **build from the engine's own option list.** Every square the board
paints must be a square some option accepts, or a click resolves to an error
the player cannot act on.

The corollary bit too. `PowerDTO.squares` carries three jobs at once — what
to light, what a click accepts, and whether the row is offered — so a
display-only answer needs its **own** field (`shows`) rather than borrowing
that one.

## Rules

* **A DTO field is a contract with `web/`.** There is no generated client and
  no shared schema: `web/app.js` reads field names by hand. Renaming one is a
  two-component change; adding one is not.
* **`session.py` holds the turn machinery.** A question asked from inside
  somebody else's action cannot be answered, because the answer arrives on a
  request this one is blocking. `_theirs` guards it, and the rule is that the
  guard must cover **everything that runs while it is not the player's move**
  — two `advance()` calls sat just outside it and deadlocked the API.
* **Encounter setup is duplicated** between `session.py` and
  `scripts/fight.py`, with the six replay fixtures pinning the *scripts*
  copy. Change composition in one and the other silently diverges and
  `replay` will not notice. Filed; this is the Story Engine's job.
* `/api/day` is a deliberate `501`. The adventuring day is not built.

## Seam

* **Nothing imports `api/` in Python** — `web/` reaches it over HTTP and the
  scripts launch it as a subprocess. This is the cleanest boundary in the
  repo. Keep it that way: do not import from `api/` anywhere in `src/`.
* `api/` imports engine, content and etl. It is the only component that
  touches all of them, which makes it the integration point by default
  rather than by design. Prefer pushing a rule down into the engine over
  adding a fourth thing this layer knows.

## Checking

```
uv run scripts/api_smoke.py    play an encounter over HTTP, check the wire
uv run scripts/browser.py      and the page that reads it
```

`api_smoke` starts a real server on a spare port. Both harnesses now spawn it
in its own process group and kill the group — `terminate()` on the `uv`
wrapper left the server running, and 69 of them had accumulated over three
and a half days.
