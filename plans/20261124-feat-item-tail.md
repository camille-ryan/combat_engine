# The feat and item tail, triaged by facility

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

## Owed

6 commits unpushed, all touching `engine/` or `scripts/audit.py`, so a
wide sweep is owed before the next push. ETL and the rebuild stay
deferred per the standing order.
