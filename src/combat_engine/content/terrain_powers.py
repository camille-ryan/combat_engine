"""Terrain powers: rows the board owns, that any creature by them may use.

The compendium's `terrain` table holds **24** rows of `kind = 'terrain
power'`, and before `#980` none of them could be written at all. They are
not anybody's powers: nothing casts them, no creature has one in its
`Powers.all`, and `dsl.usable` refused every one on the *"not known"* gate.
What they are is a thing on the floor with an action attached.

The printed shape, which is the same on all 24:

    <Single-Use | At-Will> Terrain
    <Standard | Move | Minor | Free> Action
    Requirement: You must be adjacent to / in / within N squares of <it>
    Check: <skill> check (<band> DC) to <do the thing>
    Success: <it happens, and usually makes an attack>
    Target:  ...
    Attack:  ...

So the mechanism is three parts and `#980` built the first: a region
carries a ref (`Zone.power`), the action menu offers it to whoever is
standing near enough (`actions._terrain`), and `perform` runs it through
`dsl.use(board=True)`. `content/terrain.py`'s `lay` is the writer.

**This module holds two rows, and the gaps that held the other 22 are
closed.** Writing a facility with no caller is
how `c.zone(hindering=)` sat unused from `#952` until `#1039` -- the field
was recorded and burned nobody -- so the mechanism gets a live caller in
the same commit that builds it. What the remaining 23 want is measured on
`#980`:

* ~~**`Attack(level + N)` has no header form**~~ -- **built**, `#1105`.
  `Attack(level_plus=3)` is the user's level plus three, resolved in
  `bonus_for` with no `scaling.trim`: `printed=` is a finished total whose
  level gets taken back out, and `ability=` would add a proficiency and an
  ability modifier a patch of ground has not got. 12 terrain powers print
  it **and so do 2 traps**, which `#1105` had flagged as its own unchecked
  question.
* ~~**A `Check:` that gates the attack cannot be rolled in the body**~~ --
  **built**, `#1106`. `Check(skill, band)` is a header field rolled once in
  `dsl.use` before any target is walked; a failure runs no body, still
  reports the power used, and still emits `PowerResolved`. The body runs
  **once per target**, so a check rolled there is rolled once per creature
  caught and a failure on the first cannot stop the second.

**The `Check:` census here was wrong and is worth the correction.** This
said *"21 of 24 print one"*. It is **14**, and 11 of those print an
`Attack:` beside it -- the specs are a single run of text rather than
lines, so a line-anchored count and a run-anchored one give different
answers. `drivers.terrain_check` asserts both figures so they cannot drift
back.

`x2_124` needed neither field, which is why it was the first row here:
`target=SELF`, so the body runs exactly once and the check is correct in
it, and it has no attack line at all. `x2_125` is the live caller for both
-- the shortest of the 11, with one target and one effect.
"""

from __future__ import annotations

from typing import Any

from combat_engine.dc import dc
from combat_engine.engine.cast import Cast
from combat_engine.engine.dsl import (
    ONE_CREATURE,
    PERSONAL,
    SELF,
    Attack,
    Check,
    Ranged,
    power,
)
from combat_engine.engine.durations import When
from combat_engine.engine.events import Hit, Miss, Moved
from combat_engine.engine.types import ActionType, Condition, Defense, Usage
from combat_engine.engine.zones import Zone


@power("x2_124", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=PERSONAL, target=SELF)
def x2_124(c: Cast) -> None:
    """Burrow into the loose sand: fall prone, and be unseen until you stir.

    The first terrain power in the tree and the mechanism's live caller.
    `Zone.power = "x2_124"` with `power_uses=0` -- the card's heading reads
    `At-Will Terrain`, so the feature is not spent by being used -- and
    `power_reach=1`, which is the printed *"you must be in a square of the
    dune"*: a creature standing in the region is within 1 of its own
    square, so the same reach serves both that wording and the 16 rows that
    say *adjacent*.

    **The check is rolled here and that is only sound because `target` is
    `SELF`.** `dsl.use` runs a body once per target, so a row with a blast
    would roll this once per creature caught -- see the module docstring and
    `#1106`. One target, one roll, and the printed failure is simply that
    nothing happens.

    `dc(c.level, "easy")` rather than a number: the card prints a *band*,
    not a DC, and 15 of the 24 rows do the same. `combat_engine/dc.py` is
    the 90-number table those bands index, and its own docstring already
    named `terrain` as a waiting consumer -- this is the first row to take
    it up.

    **"Total concealment until you move or attack" is two ends and neither
    is a `When`.** So the encounter clock is the outer bound and both ends
    are taken off by hand, which is the idiom `i3296p1` and
    `_unseen_until_it_stirs` already use.

    **`Moved` and not `MoveStart`, and this row is the sharpest case for
    that choice in the tree.** It was written as `MoveStart` on the
    reasoning that a creature climbing out of the sand has broken cover by
    *starting* to move. A control caught it: the same body makes the
    creature **prone**, a prone creature cannot walk at all, so the very
    first attempted walk was **refused** -- 0 squares covered, still on its
    own square -- and `MoveStart` had already ended the concealment. The
    buried creature lost its cover for a move that never happened, and
    nothing would have reported it: the effect ending is exactly what the
    card says should happen, just for the wrong reason.

    `Moved` is what the printed *"until you move"* means and it is also
    `i3296p1`'s reading, whose note says its dust "should survive a move
    that is refused". Two rows, two cards, same answer -- the original
    argument for splitting them was mine and it was wrong.

    `Hit` and `Miss` both, because an attack that misses is still an
    attack. `once=True` on each watch and a shared `spent` guard anyway:
    three watches against one effect, and ending an effect twice is a
    second `EffectEnded` nothing printed.

    `c.conceal(total=True)` and **not** `c.invisible` or `c.hide`. The
    printed words are *"total concealment"*, which is a -5 to attacks
    against you; being hidden or invisible is a different rule -- it
    changes whether you can be targeted at all, and grants combat
    advantage, neither of which this card says. The two rows above reach
    for `c.invisible` because their cards print *"unseen"*.
    """
    if not c.check("athletics", dc(c.level, "easy")):
        return
    c.prone()
    buried = c.conceal(total=True, until=When.ENCOUNTER)
    if buried is None:
        return
    me = c.me
    spent: list[bool] = []

    def stirs(ev: Any) -> None:
        if spent:
            return
        who = getattr(ev, "attacker", None)
        if who is None:
            who = getattr(ev, "actor", None)
        if who != me:
            return
        spent.append(True)
        c.world.effects.end(buried, "it moved or attacked")

    for event in (Hit, Miss, Moved):
        c.watch(event, stirs, until=When.ENCOUNTER, on=me, once=True,
                label=f"{c.ref} buried")


@power("x2_125", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=Ranged(10), target=ONE_CREATURE,
       check=Check("nature", "hard"),
       attack=Attack(level_plus=3, vs=Defense.REF))
def x2_125(c: Cast) -> None:
    """Spot a deeper patch in the silt and put somebody in it.

    **The live caller for both header fields `#980` was waiting on**, and
    the reason it is this row of the eleven: it is the shortest -- 331
    characters of spec -- with one target, one effect and no Requirement
    line, so the two new fields are the only interesting thing in it.

    `check=Check("nature", "hard")` is the printed `Check: Nature check
    (hard DC)`, and it is a **header** field because `dsl.use` runs a body
    once per target: rolled in the body it would be rolled once per
    creature caught, and a failure on the first could not stop the second.
    This row has one target so the difference is invisible here -- which is
    exactly why the eleven that have several needed it. `#1106`.

    `attack=Attack(level_plus=3, ...)` is the printed `Attack: Level + 3`,
    which is the **user's** level plus three. Not `printed=`, whose level
    is already inside the number and gets trimmed back out, and not
    `ability=`, which would add a proficiency and an ability modifier a
    patch of silt does not have. `#1105`.

    **The region is the range, and that is why the body gates on it.** The
    printed Target is *"one creature you choose within a silt pool"* --
    which names no distance, so `Ranged(10)` is the aiming envelope and
    the pool is the real bound. `world.zones.occupants` answers it, and the
    gate is per target, which is correct: membership is a property of each
    creature where the check was a property of the use.

    A `save ends` restraint rather than `until=When.EONT`: the card prints
    "(save ends)" and `c.condition` takes the window, so there is no
    shorthand to reach for -- `Cast` has `slowed`, `immobilized` and
    `weakened` and no `restrained`, which is left alone rather than added,
    because a new `Cast` member owes a `symbols` regeneration for one use.
    """
    pool = next(
        (eid for eid, zone in c.world.each(Zone) if zone.power == c.ref),
        None,
    )
    if pool is None:
        return
    if c.target not in c.world.zones.occupants(pool):
        return
    if c.strike():
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)
