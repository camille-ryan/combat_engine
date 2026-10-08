# ETL

Compendium → `data/game.db` + `localization/names.json`. **Extraction, never
rules.** This component decides what a row's numbers *are*; it never decides
what a row *does*. That is Content's job and the two share no code.

Global rules are in the root `CLAUDE.md`. This file is what is different
here.

## This is where the legal boundary is enforced

Everything an author is ever shown passes through `sanitise.py`. Two files
come out and **neither is redistributable**:

* `data/game.db` — numbers, plus the mechanical text each row was written
  from.
* `localization/names.json` — the names and flavour, kept out of the engine
  entirely.

So the rule that binds this component specifically: **a printed name must
reach `localization/` and nowhere else.** Not a column, not a spec, not a
ref. `scripts/leaks.py` checks both halves —

```
uv run scripts/leaks.py            has a name got into tracked source
uv run scripts/leaks.py --specs    ...or into a spec or a vocabulary column
```

— and the second half exists because a name sat in `item.slot` for months:
the column held 15 printed reward titles ("Divine Boon", "Grandmaster
Training") because `_slot` echoed the printed label. The fix was an
**allow-list** of the words the column may hold, because writing the deny
list would itself have been the leak.

## Rules

* **The build is destructive and idempotent.** `data/game.db` is recreated
  from scratch every run, so the only way to change what is in it is to
  change a parser. Never patch the database.
* **Parse, or store nothing.** A number you cannot read is `NULL`, not a
  guess. `trap.perception_dc` is the worked example: 356 of 631 rows print
  one and the other 275 are `NULL`, read as "cannot be noticed in advance".
  Storing `0` would have meant "everybody notices it".
* **Never derive a number the page prints.** Measured on the same table:
  level-1 traps print Perception DCs from 9 to 22 and the per-level median
  wanders from `level + 3.5` to `level + 18`. A formula would have been
  wrong by ten, silently, on the number that decides what a player sees.
* **Two `spec` columns are parsed for numbers, and nine are not.** "A spec is
  prose and reaches no rule" is in three commit messages and is **false**:

  ```
  race.spec       -> chargen/__init__.py:1331   speed, fly speed, skill
                                                bonuses, the surge step
  companion.spec  -> content/loader.py:260      the whole stat block
  ```

  The other nine (`power`, `monster_power`, `class_feature`, `build_option`,
  `feat`, `item`, `item_block`, `racial_trait`, `trap`) are read by
  `api/wire.py:264` for display and by `scripts/spec.py` for a brief, and by
  nothing that decides an outcome. So "the spec moved, therefore no rule moved"
  is a safe inference for nine tables and a wrong one for two — and the two are
  every character and every companion in the game. #442.
* **Two HTML dialects, always.** The compendium holds a later layout
  (`<table class="bodytable">`, `<h2>` action headings) and an earlier one
  (everything in one `<p class="flavor">`), roughly half the heroic monsters
  in each. Parse both and record which a row came from.
* **A printed cross-reference is a ref, not prose.** Nineteen extraction
  faults have been the same shape: a name the database could already resolve
  reaching an author as prose. If a page names another row, resolve it.
* **Prefer the id to the name when the page gives one.** Feat pages link
  their Associated Powers as `href="power.php?id=NNNN"`, and that id *is*
  the engine's `pNNNN`. `_links_resolve` asserts the name resolver against
  those links — currently 478/478 — so a regression shows up as a number
  rather than as prose that quietly stopped matching.

## Seam

* **`etl` → `content` is zero imports**, and must stay zero. Content reads
  the built database; ETL knows nothing about rows.
* `etl` → `engine` is six function-local imports, all pulling enums
  (`DamageType`, `Ability`, `Keyword`, `SKILLS`). Keep them function-local:
  `feat.py` records that a top-level import "pulls in the whole rules
  kernel".
* **Nothing imports ETL to *read* the database any more.** `game()` and
  `localisation()` live in `src/combat_engine/db.py`, below every component,
  and ETL imports them like everybody else. So this file used to warn that
  `content` and `api/wire.py` import from ETL and that an ETL change therefore
  reached `engine` transitively through `content/loader.py` — that route is
  gone. The one remaining import of this package from outside it is
  `scripts/build.py`, which calls `build()`, the writer. #334.

  What a schema change still reaches is every **reader** of the column, which
  is the honest version of the old warning: the tables are shared, the module
  is not. `lint.py` fails if `db.py` ever imports from `combat_engine`, because
  the moment it does, one of the five readers is reaching through another for a
  sqlite file again.

## Checking

```
uv run scripts/build.py     rebuild; read the report it prints
uv run scripts/leaks.py     and --specs
uv run scripts/mm3.py       published MM3 maths against what the books printed
```

The build report is the instrument: parse coverage per table, the worst-parsed
rows, and `assoc links 478/478`. A number moving there is the signal.

**Rebuilding is slow and everything downstream reads the result** — so after
a rebuild, run `replay.py verify`. A parser change that moves a number moves
every fight.
