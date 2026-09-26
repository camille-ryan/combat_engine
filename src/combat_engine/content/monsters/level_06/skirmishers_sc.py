"""Monster abilities, level 6: the row whose whole Hit is ruining a thing.

A stat block's numbers load from `game.db`; this is only its behaviour.

`c.destroy` is the printed sentence: the item comes off `Gear` and does not
come back, so the target swings without it from the next roll on. "A rusting
item" is read as the magic item in hand -- the only item the model tells
apart from an ordinary one, and the one the printed target line means.

The residuum clause is not a combat effect and is not written. The printed
"Recharge if the power misses" sits on top of the 6+ the database files, the
way `_recharge_on` puts every other printed recharge sentence.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.engine import (
    ONE_CREATURE,
    REF,
    STANDARD,
    Attack,
    Cast,
    Melee,
    Miss,
    Usage,
    power,
)
from combat_engine.engine.components import Gear


@power(
    "m3062a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
)
def m3062a2(c: Cast) -> None:
    """The printed target line is "wearing or wielding a rusting item" and the
    engine has no rust, so the thing in hand is read as the one -- named
    outright rather than left to `c.destroy`'s default, which picks a magic
    item and no chassis in `chargen` carries one."""
    me, ref = c.me, c.ref
    _recharge_on(
        c, Miss, lambda ev: ev.attacker == me and ev.power == ref
    )
    if c.strike():
        gear = c.world.get(c.target, Gear)
        c.destroy(weapon=gear.main if gear else None)
