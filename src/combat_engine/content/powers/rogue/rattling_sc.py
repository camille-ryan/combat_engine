"""Rogue: the three rows built on the rattling keyword.

`Keyword.RATTLING` is read in `c.damage`, which is where every power's damage
goes through and the only side that knows what the header declared. The whole
of the word is -2 to the target's attack rolls until the end of the attacker's
next turn, applied on a blow that actually took hit points off; `c.rattled`
asks it back, which is what the third row here selects on.

`c.rattling` is the other half: two of these rows hand the keyword to a
*creature's* attacks rather than declaring it on a power, so it is held as a
modifier that `c.damage` reads beside the header.

The Prerequisite lines gate taking these at character creation rather than
using them, so neither is declared as a `requires` -- the reading `level_2.py`
settled. `p10740`'s **Requirement** is a different thing and is declared.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    DEX,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    STANDARD,
    Attack,
    Cast,
    Keyword,
    MeleeOrRanged,
    When,
    World,
    power,
)
from combat_engine.engine.components import Gear

_GRIPS = ("light blade", "crossbow", "sling")


def _carries_a_rattler(world: World, eid: int) -> bool:
    """The printed Requirement: a crossbow, a light blade, or a sling."""
    gear = world.get(eid, Gear)
    return gear is not None and any(w.group in _GRIPS for w in gear.weapons)


@power(
    "p10740",
    level=1,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON, Keyword.RATTLING],
    attack=Attack(DEX, vs=AC),
    requires=_carries_a_rattler,
    requires_text="must be wielding a crossbow, a light blade, or a sling",
)
def p10740(c: Cast) -> None:
    """The header's own keyword rattles this blow; the Effect hands the word
    to every melee attack afterwards. The Effect is printed once for the
    whole power, so it goes behind `c.first` rather than per target."""
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    else:
        c.half_damage(c.w(2), c.dex_mod)
    if c.first:
        c.rattling(until=When.ENCOUNTER, melee=True)


@power(
    "p4499",
    level=10,
    cls="rogue",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p4499(c: Cast) -> None:
    c.stance(label="p4499")
    c.rattling(until=When.STANCE)


@power(
    "p2389",
    level=2,
    cls="rogue",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
)
def p2389(c: Cast) -> None:
    """"An enemy within line of sight that is taking the penalty from one of
    your rattling attacks" is `c.rattled`, which reads the hold this rogue
    applied rather than anybody else's -- which is what "one of *your*"
    says."""
    rattled = [e for e in c.enemies() if c.rattled(e) and c.can_see(e)]
    if not rattled:
        return
    victim = c.choose(sorted(rattled), "which rattled enemy")
    if victim is not None:
        c.grants_advantage(on=victim, until=When.EONT)
