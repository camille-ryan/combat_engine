"""m3064's two abilities about the gear its victims are carrying.

Both were left out for the same reason: `Weapon` recorded no enhancement
bonus, so "the enhancement bonus is reduced by 1" had no number to reduce
and "the decaying magic item is destroyed" had nothing to pick out of a
creature's hands. `Weapon.enhancement` is that number -- it adds to the
attack roll and to the damage roll, so reducing it is felt -- and
`Target(holding="magic")` is the printed target line asking for it.

**Item level is not modelled**, so "a decaying magic item of 15th level or
lower" is checked as far as the engine can: the creature is holding
something with an enhancement bonus.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    FREE,
    NO_TARGET,
    PERSONAL,
    REF,
    STANDARD,
    Attack,
    Cast,
    Melee,
    Target,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.events import Hit
from combat_engine.engine.query import holding
from combat_engine.engine.triggers import Trigger

_STRUCK_BY_MAGIC = "the m3064 is hit by an attack that uses a magic implement or weapon"


def _hit_by_magic(world: World, me: int, ev: Hit) -> bool:
    return ev.target == me and bool(holding(world, ev.attacker, "magic"))


@power(
    "m3064a2",
    level=11,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=Target("enemy", 1, holding="magic"),
    attack=Attack(vs=REF, printed=14),
)
def m3064a2(c: Cast) -> None:
    """"Miss: the power is not expended" is `c.restore_use`, which is what a
    reliable weapon power already does. The recharge die is not printed on
    the card this was written from -- see the report."""
    if c.strike():
        c.destroy()
    else:
        c.restore_use(c.ref, on=c.me)


@power(
    "m3064a3",
    level=11,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_STRUCK_BY_MAGIC,
    on=Trigger(Hit, _hit_by_magic, _STRUCK_BY_MAGIC),
)
def m3064a3(c: Cast) -> None:
    """The hold is laid on the creature holding the item and its ending puts
    the bonus back, which is the printed "returns to normal at the end of
    the encounter". Each use takes another point off, to a minimum of 0."""
    who = getattr(c.trigger, "attacker", None)
    if who is None:
        return
    c.decay(on=who, weapon=c.struck_with(), until=When.ENCOUNTER)
