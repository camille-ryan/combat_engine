# The engine tail: 241 rows, and why ETL waits

Camille's sequencing, 2026-11-21: *"Defer etl changes until the engine tail
is done. Then do all ETL in one batch. Then rebuild. Avoid doing a wide
sweep until EVERYTHING is done, and then push."*

## Why this ordering is worth the discipline

Two mechanisms get confused and only one of them is about the map's life:

| | voids the map | can the map narrow it |
|---|---|---|
| `engine/` edit | no | **yes -- the only path it speaks for** |
| `chargen/`, `story/` edit | no | no, refused by design |
| `etl/` edit | no | no -- **and its rebuild voids the map** |
| `scripts/build.py` run | **yes** | -- |

`impact.NARROWABLE` is `('src/combat_engine/engine/',)`, one path, and
`check.py`'s own note says it: *"`WIDE` is `engine/`, `etl/`, `chargen/`
and `scripts/audit.py`; the map speaks for the first and for none of the
rest."* Validity is a **content digest** of `data/game.db` (`#1193`), so
nothing but a rebuild whose contents differ can void a recording.

So deferring **ETL** is the whole of the win: it defers the rebuild.
Deferring `chargen/` protects nothing -- it was never narrowable. On
2026-11-20 I rebuilt four times, voiding the map each time; batched that is
one rebuild and one recording.

**The operative rule: no `scripts/build.py` until the engine tail is
finished.** It is the only route to a void.

## What is left

```
heroic feat/item rows declared      5,027
  complete                          4,748   94.4%
  still marked                        279

of the 279, by where the fix lands
  not deferred (engine + content)     241 rows over 205 symbols
  deferred (etl/chargen/story/...)     38 rows
```

Of the 205 non-deferred symbols, **39 serve two or more rows** -- 84 rows
between them, 2.2 each -- and **166 serve exactly one**. That is the honest
shape: a long tail of distinct facilities, not a backlog of writing, which
is why a batch lands a handful and not fifty.

## Order of work

1. **The 39 multi-row clusters, biggest first.** 84 rows. Best ratio
   available and the only place a single facility pays more than once.
2. **The content-ref symbols** (`cf:vampire-f0`, `rt:r16-t1`, and the
   `cf:` singletons). These are `content/`, so they gate **narrow by file**
   -- no wide audit, no map needed. Cheapest rows in the tail and the right
   thing to reach for whenever the map is unavailable.
3. **The 166 singletons**, read before costed.

## The lesson that governs step 1

Cost the symbol by **reading it**, never by its spelling. `#1196`'s
counter-example: `c.ignores_difficult(squares=)` reads like a keyword
argument and is a pathfinding change -- `World.crossing` hands one pricing
closure to `step`, `reachable` *and* `costs`, so a budget counter would
decrement across candidate paths inside Dijkstra. A triage that classified
51 symbols as "cheap parameter additions" was sorting by shape.

Five times now the marker has been one layer off the real gap: `c.on_save()`
wanted a field, `SavingThrow.power` wanted the granter, `class_skill.build`
wanted a column, `c.ability_check(purpose=)` wanted an action,
`query.knocked_prone()` wanted a sentence the ETL had truncated. Read the
row's own docstring first -- it has been right more often than the symbol.

## The ETL batch, when it comes

Already known and filed, so it does not need re-deriving:

* `#1419` -- 609 item blocks in never-dealt slots. **Parked on Camille**,
  tagged `question` with a plain-language ask as the last comment. This is
  the one large lever left and it is a design decision, not a volume of
  work.
* the 8 remaining ETL-shaped row symbols in the deferred set.

Then: one rebuild, the 15 spec-table diffs, the five leak gates, **one**
wide sweep, the baselines each in their own commit, and the push.

## Batch 4, designed while the map recorded: `c.ignore_requirement(ref)`

Three rows, one facility, and the reading that matters is that all three
are the **same** sentence:

| row | what satisfies the Requirement |
|---|---|
| `f2931` | being bloodied |
| `f2933` | the creature that triggered `p8278` |
| `f2338` | a crossbow standing in for a light blade |

`p9401` prints *"Requirement: You must be adjacent to a creature"* and
`f2338`'s associated powers demand a light blade. So none of the three is a
new gate -- each says a named row's existing Requirement is met by
something its predicate will not accept.

**One gate reads it.** `Power.can_branch` is the only place
`requires_of(branch)` is asked: `if gate is not None and not gate(world,
actor): return False`. It already has the world and the actor, so a
standing waiver on the creature is readable there.

**Per-ref and conditional, never blanket**, which is not a preference but
the existing argument. `usable`'s own note on the one waiver it already
allows: *"Fail-closed, which is the direction that matters: waiving the
whole requirement would make every `requires=` a suggestion for anybody
willing to route through `use_power`."* A named ref plus the printed
condition keeps that property.

```
c.ignore_requirement(ref, *, on=None, until=When.ENCOUNTER, when=None)
```

The plant is the fail-closed direction: waive `p9401` and confirm a
*different* row's Requirement still refuses, and that `p9401` refuses again
once the condition does not hold.

## Two clusters that look like engine and are not

Found by reading rather than by the symbol's spelling, which is this
plan's own rule applied to itself:

* **`c.item_set()`** -- 4 rows, all paired items. `game.db` carries **no
  set table at all** (`#1412`'s triage, re-stated on `#1419`), so this is
  an import gap. **Deferred.**
* **`c.grant_inline()`** -- 3 rows. `i1188p1`'s note is explicit: the
  `…b` second-card convention is minted by the ETL and `item_block`
  carries **none**, so declaring one would be a row against a card the
  database does not have. **Deferred.**

Both are spelled `c.…` and neither is a `Cast` gap. 7 rows move from the
engine tail to the ETL batch.

## What the recording actually cost, and a correction

```
23,885 rows in 7,794s -- 2.17 hours, 3.1 rows/s
937 functions carry a ref list, 346 are wide (> 7,165 rows)
```

**Inside** the 1.3-2.8 hour range the root `CLAUDE.md` states, and the rate
sits between the two clusters that file names (2.3-2.7 and 4.8 rows/s).

I said mid-run that it was tracking 3.1 **hours** and would overrun that
range. That was wrong, and wrong the same way as taking a rate off the
front of a sorted corpus: I extrapolated `~8182s left` from a stretch under
load and quoted it as the total. A progress line's own estimate is not a
measurement -- wait for the summary.
