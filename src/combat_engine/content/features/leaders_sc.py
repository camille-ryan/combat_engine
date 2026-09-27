"""The second of the warlord's three mutually exclusive leader features.

Its whole printed content is a +2 power bonus to initiative for the warlord
and every ally within 10 squares that can see and hear it.

`c.initiative` is how that is said now. `Initiative.bonus` is read inside
`_roll_initiative`, before the d20, and a trait is armed after the rolls --
so the number a trait sets can never reach the roll. `adjust_initiative`
moves the creature in the order instead, which is the same outcome, and it
splices during arming as well as during a round.

**The kind is lost.** `c.initiative` moves a number that has already been
rolled, so there is nothing for "power bonus" to stack against; the printed
word matters only where two bonuses meet, and initiative has no second one
anywhere in the tree.

Hearing is not modelled, so the printed "see and hear" is read as sight.

**Two other features print "this replaces" against this one**, and
`chargen.loadout` hands a class every level-0 row it has, so a warlord here
carries all three. Only one of the three has a leg in
`chargen.BUILDS["warlord"]` -- the shield -- so that is the one case where
the exclusivity can be said, and it is said here rather than there: a row
cannot switch another row off, but it can decline to fire.
`cf:warlord-marshal-f2` has no leg and so still overlaps, which is named in its
own docstring.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    NO_TARGET,
    ActionType,
    Cast,
    CloseBurst,
    Keyword,
    power,
)


@power(
    "cf:warlord-marshal-f3",
    level=0,
    cls="warlord",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(10),
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def warlord_initiative(c: Cast) -> None:
    if c.build("shielding"):
        return
    c.initiative(2, on=c.me)
    for ally in c.within(10, side="ally"):
        if ally != c.me and c.can_see(ally):
            c.initiative(2, on=ally)
