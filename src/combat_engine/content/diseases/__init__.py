"""Diseases: one row per disease, branching on the stage it is at. #948.

A disease page prints **one card with a paragraph per stage**, so a row here
is the whole disease and `c.stage` says which paragraph applies. The ref is
the disease's own -- `x5_11` -- which is what lets
`turns.arm_afflictions` run the right row with no lookup table.

## The one rule a stage body must obey

**Lay a standing effect; never charge a one-time cost.** The dispatcher
arms the row at the start of **every** fight, off the stage the `Sheet`
carried in -- that is how a disease gets a lifetime longer than a `World`,
which does not outlive its fight. So:

    "While affected by stage 1, the target loses a healing surge"
      -> a standing reduction while diseased
      -> NOT c.surge(), which would take one surge per fight

An effect laid `until=When.ENCOUNTER` is re-laid next fight and stops being
laid when the disease is cured, which is exactly the printed "while
affected by stage N".

## The shape

    @power("x5_94", cls="disease", level=3, usage=AT_WILL,
           action=ActionType.NONE, target=NO_TARGET, reach=Melee(0))
    def x5_94(c: Cast) -> None:
        if c.stage >= 2:
            c.penalty(AC, 2, on=c.me)

`action=NONE` and no declared trigger, like a trait: the dispatcher calls
it directly rather than waiting for anything. `on=c.me` on everything --
the disease is happening to the character, and `target=NO_TARGET` means a
bare call would act on nobody.

**Stage 0 is never passed in.** `affliction.tick` deletes a ref that
reaches 0 and `arm_afflictions` skips a stage of 0, so the page's *"the
target recovers"* paragraph needs no branch.

## Scope

15 of the 69 printed diseases are written here: the ones that are both
**tickable** (`affliction.printed()` -- a fixed DC pair and a single check
skill) and **inflicted** by a row in this tree, at heroic level. The rest
would be rows nothing can give a character, which is the shape `#948`
twice refused to ship. `affliction.refused()` names each exclusion with a
reason.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from combat_engine.engine.components import Health

if TYPE_CHECKING:
    from combat_engine.engine import Cast


def lost_surges(c: Cast, count: int) -> None:
    """"The target loses `count` healing surges", as a standing reduction.

    **Here rather than in one of the modules, because three write it and 54
    more rows are coming.** It landed in `low_heroic.py` first and the
    middle band imported it from there, which works and reads as an
    accident; the package root is the honest home for the one technique
    every disease module needs.

    Nothing on `Cast` moves the surge ceiling, so the field pair is the
    route -- `f131` writes the opposite sentence the same way.

    ## Clamped, never decremented, and the difference is a real bug

    `story._wear` runs **before** `turns.arm_afflictions` and carries
    `sheet.surges` back clamped against the ceiling this row has not
    lowered yet. So a decrement takes a surge, has it handed back by the
    next `_wear`, and takes another -- one a fight, which is exactly the
    repeating cost this package forbids. Measured at level 7 over four
    boards with `harvest` between and **no rest**:

        no disease              12,12  12,12  12,12  12,12
        `surges -= count`       11,11  11,10  11, 9  11, 8
        clamped, as below       11,11  11,11  11,11  11,11

    **Two things hide it**, and both were in the first attempt at this:
    `max_surges` alone is stable under either spelling, and a
    `party.rest()` between boards refills the pool. So a check has to read
    **both** fields over three or more boards with no rest -- two fights
    back to back is a case the story engine supports (`#947`).

    `once_per_board` on the caster, because the sentence is about the sheet
    and the row is armed once per encounter anyway: the guard is what stops
    a second arming within one board from lowering it twice.
    """
    health = c.world.get(c.me, Health)
    if health is None or not c.once_per_board(c.me):
        return
    health.max_surges = max(0, health.max_surges - count)
    health.surges = min(health.surges, health.max_surges)
