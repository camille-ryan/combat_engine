"""m678's answer to a melee weapon that misses it.

Left out because nothing took a weapon out of a hand. `c.disarm` does: the
weapon leaves `Gear` altogether and becomes an `Item` lying in the
creature's square, so what it was swinging is gone -- its `c.w()` drops to
an empty-handed d4 and a melee weapon branch it can no longer meet is
refused -- rather than being stowed on its belt, which is a minor action to
undo and is not what the card says.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    ONE_CREATURE,
    REACTION,
    REF,
    Attack,
    Cast,
    Melee,
    World,
    power,
)
from combat_engine.engine.events import Miss
from combat_engine.engine.query import adjacent
from combat_engine.engine.triggers import Trigger, by_melee

_MISSED_ME = "an adjacent enemy misses the m678 with a melee weapon attack"


def _missed_me_in_melee(world: World, me: int, ev: Miss) -> bool:
    return ev.target == me and adjacent(world, me, ev.attacker) and by_melee(world, me, ev)


@power(
    "m678a4",
    level=12,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=15),
    trigger=_MISSED_ME,
    on=Trigger(Miss, _missed_me_in_melee, _MISSED_ME),
)
def m678a4(c: Cast) -> None:
    foe = c.target if c.target is not None else getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.disarm(on=foe, weapon=c.struck_with())
