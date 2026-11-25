# The feat and item tail, triaged by facility

## The ruling that defines "done" -- 2026-11-24

Three rows could only be finished by ETL work, which the session order
defers until the tail is done, and the tail contained them. Camille,
asked whether to let ETL run for those three, take them out of the tail,
or decline them:

> *"2"*

-- take them out. So **"the engine tail is done" means the 39 rows
below**, not all 58 marked ones. The deferred families keep their
markers and are counted with the ETL batch:

```
total marked feat/item rows      58
  ETL / source-data deferred     13   f951 f1252 f1962 f2263 f2624 f3425
                                      f3768 i694x1 i1492p1 i1700x1
                                      i2611p1 i3475p1 i3560x1
  story deferred (#787)           4   f3447 i693x1 i1246x1 i1751p1
  ship deferred (#1387)           2   f979 f1071
  THE TAIL                       39
```

**I quoted "the other 55" when putting the options; the tail is 39.**
The 16 difference is the story and ship families, deferred by `#787` and
`#1387` before this ruling -- so 55 counted them as tail work when they
were not. The number to work against is 39.

### The deferred bucket is 7, not 13 -- re-measured 2026-11-25

The 13 above was right when written and is now nearly double the truth,
so do not plan an ETL batch off it. Measured by walking `dsl.REGISTRY`
for feat and item rows whose owed `todo`/`dropped` symbols start `etl.`
or `compendium.`:

```
f1962    etl.feat.associated_powers()    real -- #1481 specifies the store
i1700x1  etl.rules_break                 real -- #1471, ruled and queued
i2611p1  etl.item.second_base            arguable -- the form is in prose
f2263    etl.paragon_path                a scope exclusion, not a gap
f3425    compendium.associated_powers    source
i3475p1  compendium.creature_maker       source
i694x1   compendium.character_power_absent  source
```

Where the other six went. `f951`, `f1252` and `f3768` were cleared
earlier the same day. `i3560x1` was **never an ETL row** -- its species
is in no column the source carries, so no importer could have reached
it, and it is written now by gating on identity by ref. `i1492p1` moved
to `chargen.item_pairing`: its "pair" is two copies of one item, so
there is no edge to import. `f2624` is parked on `#1561`.

So **4 of the 8 `etl.*` rows I triaged were mislabelled**, all four by
the same mistake -- the measurement behind the marker had been run
against `data/game.db`, which is the built output and can only report
what ETL already takes. `#1590` carries that finding; `23ef1aa9` is the
correction.

What this does *not* change: the ruling still defers the bucket, and the
tail is still the number to work against. It means the batch, when it
runs, is **two real jobs** -- both "extract a table the compendium holds
into `game.db`", the shape `#1001` already built once for `rules_dc` --
and not thirteen.


Written 2026-11-24, after clearing five rows and finding that picking
rows one at a time has stopped paying. 60 feat/item rows carry a marker;
**43 are actionable** and the rest are in families deferred by ruling.

## What is deferred, and by what

| rows | family | why |
|---|---|---|
| 10 | ETL / compendium | the standing order defers ETL to one batch |
| 4 | story | `#787` |
| 2 | ship / vehicle | `#1387`, Camille: *"defer until we implement ship combat (if ever)"* |
| 1 | `f2624` | `#1561`, parked on a ruling -- the table is printed, the build is a mechanic family |

`f979` and `f1071` are the ship pair. An earlier count of mine put them
under "engine facility, actionable"; they are not.

## The stale-premise seam is mined out

Five rows cleared this session came from markers whose premise had
expired or named the wrong layer -- `i3320p1`, `f1945`, `f3568`,
`i2494x1`, `i3318p1`. **That seam is now closed**, measured rather than
assumed: every actionable symbol was checked mechanically for existing
already, and the only 15 that "exist" are `verb(param=)` requests where
the base verb exists and the parameter does not, which is what the
marker says. No stale premise remains in the actionable set.

Four rows were probed individually and are **correctly marked**, each
with an accurate and self-aware note -- do not re-derive these:

* `i1761p1` -- the crit rider's faces are summed inside a `Mod.roll()`
  closure during the modifier pass, so a reactive daily has nothing to
  rewrite. Its note already corrects itself about `i2299x1`.
* `i3470p1` -- *"nor through it"* is deliberately unwritten, because
  `can_hear` is not a line-of-effect test and sound goes round corners.
  The reader already consults `Zone.silences` for both parties.
* `f3626` -- waits on `cf:vampire-f0`, which is genuinely undeclared.
* `f3015b` -- `triage.json` records a `mis-marked` verdict that says
  **LEFT ALONE** and gives the reason; the live lead is
  `query.wearer_of()`, and the weapon branch would green on the wrong
  clause.

## What is left, grouped by the facility it wants

The point of the grouping: these are **facility-sized**, not row-sized.
A parameter in a marker usually implies a mechanism -- `c.extra_action
(what=)` wants a restricted-action budget, not a keyword.

* **Scenery -- and this entry was WRONG when written; corrected after
  reading the rows.** It said one component, five-plus rows, the best
  leverage left. Measured instead:

  * `content.terrain.put` already constructs a `Scenery` **and** lays
    its printed defences by size off DMG page 65, and `story/objective.py`
    calls it for the destroy, carry and escort objectives. So the writer
    exists and boards really can hold scenery.
  * `Scenery.defences` is therefore **satisfied**, and `i1145p1` is still
    blocked -- its note names a *second* refusal that a field cannot fix:
    `Scenery` has no `Side`, ever, so it is outside `query.creatures` and
    a `target=ONE_CREATURE` row cannot aim at one.
  * `f3015b` was re-pointed (`#1562`): `c.place_scenery(kind=)` was wrong
    on two counts -- the writer exists and the row places nothing, since
    its Effect aims at an object already standing there. What is left is
    `Scenery.wielded_as`, the missing tie from a scenery object to a
    `Weapon` in somebody's `Gear`.
  * `query.wearer_of()` wants `Scenery.by`, which exists and which
    **nothing populates** -- `terrain.put(by=)` takes one and no caller
    passes it. Writing that clause green would buy something no board can
    fire, which is the trap `i1145p1`'s own note names.
  * `i3504p1`'s `terrain.dress(scenery=)` is the one accurate symbol in
    the group: the **arcade dresser** furnishes none, where objectives do.

  So the leverage is not a field. It is whether the dresser should
  furnish scenery, which is a board-design decision with balance
  consequences, and three of these rows were deliberately left unwritten
  rather than blocked on code.
* **Chargen** -- `f1843` (`IMPROVISED`), `f2580` (`power_swap(pool=)`,
  measured in `#1558`: the pool is derivable, the asymmetric trade and
  the provenance are the real gaps), `f3646` (`LADDER_SKIPS`),
  `i2345p1` (`power_choice(known=)`), `f1120`'s remaining
  `paragon_multiclass` (deliberately out of scope per
  `Character.multiclass`).
* **Action economy** -- `i2897p1` (a granted action restricted to one
  purpose), `i2208p2` (`actions.touch()`), `i1700x1`
  (`actions.break_object()`), `f1270` (`feint(for_ally=)` and
  `bluff_to_hide()`).
* **Movement** -- `f370` (`shift_becomes_move()`; note this needs a
  **consent point**, because a walk provokes where a shift does not, so
  it has a policy seam), `i839p1` (`double_granted_move(mode=)`),
  `i1839p1` (`c.steer()`).
* **A record nothing keeps** -- `i2359x1` (`Gear.owned`, shared with
  `cf:swordmage-f0`). Check reachability first: the clause penalises
  *another* creature wielding the owner's weapon, and if no board can
  pose that, writing it green is the
  `a-row-marked-for-a-restriction-the-engine-lacks` trap.
* **Singletons** worth reading before costing: `Damage.pick` and
  `query.speed(mode=)` (`i1066p1`), `Target.square` (`f3292`),
  `dsl.Power.energy_types` (`f3435`), `c.cast_through()` (`i2008p1`),
  `c.no_enter(zone)` (`i3305p1`), `c.decline_boon()` (`i2305p1`),
  `c.spare_death_trait()` (`i3142x1`), `c.transform_item()`
  (`i2611p1`), `c.floating_object()` (`i3221p2`), `c.zone_toll
  (check=, fail=)` (`i1481p1`), `c.offer_before_aim()` (`f1134`),
  `c.racial_row()` (`f2472`), `c.race_components()` (`f443`),
  `poisons.ingested` (`f1307`), `ammunition.nock(group_identity)`
  (`i469p1`), `c.struck_with(distinct=)` (`i724x1`), `c.deals(chosen=)`
  and `c.treat_as_enemy()` (`i509x1`), `c.form(mimics=)` (`f1555`),
  `forms.beast_row(creature)` (`f2880`), `resolve.attack(implement)`
  (`i2301x1`), `components.Companion` on a summon (`i2714p1`),
  `dsl.use(reaction_before_targeting)` and `dsl.area_of(spared_count)`
  (`i1997p1`), `p2473.live_area()` (`f1305`).

## Two process notes earned tonight

* **Three plants passed on first attempt for one reason**: the rule laid
  the clause itself to pose the engine, so emptying the row left it
  green. Any new rule for these rows wants an arm that goes **through
  the row**, read off `audit.board`.
* **A board arm about a filter is suspect** when the thing filtered out
  would be refused downstream anyway -- `#1553` is the worked case, and
  the fix was to assert the pool at unit level.

## Where it stands, end of 2026-11-25

```
feat/item rows owed       49      (51 at the start of the day)
  THE TAIL               34
  deferred by ruling     15       etl/source 8, story 4, ship 2, parked 1
```

Finished: `f443`, `f3768`, `f951`, `f1252`, `i2008p1`, `i2359x1`,
`i3305p1`, **`i1066p1`**, **`i3560x1`**. Six markers re-pointed to the
right layer, and one engine bug found behind them -- `#1591`, 47 stat
blocks that could not move.

### The mis-marking seam is mined out, and this is the measurement

**21 of the 34 tail notes were read end to end.** Early on the hit rate
was extraordinary -- 4 of the first 8 `etl.*` symbols were really source
or chargen gaps (`#1590`), and two rows were writable as they stood. It
then went to zero: every one of the last dozen is accurately marked and
wants a genuine engine feature. Worked examples, so nobody re-reads them:

| row | verdict on the marker |
|---|---|
| `i2305p1` | correct -- needs a pre-event substitution door |
| `i2208p2` | correct -- no action by which a creature *touches* a thing |
| `i1761p1` | correct -- the crit rider's faces die inside a `Mod.roll()` closure |
| `f3292` | correct -- `Target` has no side for a square |
| `i3470p1` | correct, and unbuildable as named: *"or through it"* is a **line**, and `query.can_hear` is deliberately not a line test |
| `i509x1` | correct **and moot** -- `i509p1` carries `defect=`, so `dsl.entry_defect` drops the whole item and the facility would not make the row reachable |
| `f2472` | correct -- the row plays; the missing tie has nothing to stop, since `rt:r20-t2` is `_inert` |
| `f1555` | correct -- nothing records *which* creature a shape mimics |
| `f1134`, `f1307` | correct, each re-aimed several times already |
| `f2580` | triage.json says `mis-marked`; the row's **newer** note refutes it with three sub-gaps |
| `i1145p1`, `x2_117` | `Scenery.defences` is *satisfied* (`#1563`); the real blockers are no `Side` and the region interface (`#1393`) |
| `i2714p1` | correct, and the obvious fix is wrong -- adding `Companion` would strip the creature's turn |

So **do not plan another triage pass.** The remaining tail is one engine
facility per row, each owing a WIDE audit. `query.speed(mode=)` was the
last shared lever and it is spent.

### The ETL batch is three jobs, and none of them is cheap

| | shape | `#` |
|---|---|---|
| `f1962` | a queryable `feat_power` edge table | `#1481` |
| `i1700x1` | a `rules_break` table, as `#1001` built `rules_dc` | `#1471`, ruled |
| `f3435` | `varies` in `etl/power.py`'s `_KEYWORDS` | `#1592` |

All three are "extract something the compendium already holds into
`game.db`", so **one rebuild covers all three** -- which is the whole
argument for doing them together.

**I filed the third as "one list entry is the whole fix" and that was
wrong.** The entry is one line; the job is not, and the reason is worth
having before anybody picks it up:

```
 1 line   `"varies"` in `etl/power.py:_KEYWORDS`
 1 line   `Keyword.VARIES` in `engine/types.py`   (54 members, no VARIES)
19 edits  `keywords=[...]`, across 13 FILES
 1        rebuild
```

`scripts/keywords.py` is **scoped to `power._KEYWORDS`**, so widening that
list widens the instrument: every row whose card prints the word and whose
header does not declare it reports as omitting a printed keyword. And
`keywords.json` is the baseline shape that *may shrink and never grow*, so
it cannot absorb them -- the 19 have to be declared.

Two things that *are* settled, so nobody re-derives them:

* **the entry is safe.** `_head` reads only the first `powerstat` block, so
  the match is the keyword line and not prose -- and the word is never in a
  range slot: **68 of 68** occurrences sit after the semicolon, which is the
  damage-type position (`Daily Arcane , Implement ; Varies`).
* **no baseline write is owed.** `Power.score` reads `spec`, `reach` and
  whether the spec has a newline -- **not** keywords -- so this does not
  move the chargen draw and costs no `replay` re-record.

And note what it buys: `f3435` becomes **writable**, not finished. Its body
is still to write on top.

## Owed

Clean and pushed at `3f3e9e62`. Nothing is unpushed.

Two instruments are red and **neither is a regression**:
`bonuses` with the same 5 rows for eleven sweeps (`#1554`), and `audit`
on the `cf:warlord-marshal-f3` fork, which `audit.py`'s own comment
records as alternating every run -- the list has two states and the row
has three, so either choice reddens half the time and the baseline
records what is true today.

Adding a `drivers` rule means running the **suite**, not the rule: a new
key passing says nothing about the registry it was added to. `--tries 40`
is the per-commit size.

ETL and the rebuild stay deferred per the standing order and `#1471`.
