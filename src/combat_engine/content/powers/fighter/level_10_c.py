"""Fighter, level 10: handing a blow that missed you on to somebody else."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    INTERRUPT,
    PERSONAL,
    SELF,
    Cast,
    Defense,
    Event,
    Keyword,
    Miss,
    Trigger,
    World,
    get,
    power,
)
from combat_engine.engine.query import distance_between


def _missed_my_ac_or_reflex(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "target", None) == me and getattr(ev, "vs", None) in (
        Defense.AC,
        Defense.REF,
    )


@power(
    "p12198",
    level=10,
    cls="fighter",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    trigger="an attack against your AC or Reflex misses you",
    on=Trigger(
        Miss,
        _missed_my_ac_or_reflex,
        "an attack against your AC or Reflex misses you",
    ),
)
def p12198(c: Cast) -> None:
    """"Within range of the triggering attack" is measured against that row's
    own range line, which is the only number there is to check it with. The
    attacker is one of the choices, as printed; I am not, since the blow has
    already missed me and pointing it back would be no effect at all."""
    ev = c.trigger
    foe = getattr(ev, "attacker", None)
    if foe is None:
        return
    p = get(getattr(ev, "power", "") or "")
    far = p.reach_of(getattr(ev, "branch", 0)).size if p is not None else 1
    pool = [
        w
        for w in c.within(2)
        if w != c.me and distance_between(c.world, foe, w) <= far
    ]
    victim = c.choose(pool, "who the attack is repeated against")
    if victim is None:
        return
    c.grant_attack(foe, on=victim, ref=getattr(ev, "power", ""), reentrant=True)
