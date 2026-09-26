"""Warlord, level 7: making an enemy swing again, somewhere worse."""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    ONE_CREATURE,
    REACTION,
    Cast,
    CloseBurst,
    Event,
    Keyword,
    Miss,
    Trigger,
    World,
    get,
    power,
)
from combat_engine.engine.query import allies, enemies, line_of_effect, unseen_by


def _missed_one_of_mine(world: World, me: int, ev: Event) -> bool:
    """An enemy missed me, or an ally I can see, with a melee or ranged swing.

    Close and area attacks are left out, which the printed trigger says and
    the row needs: "the target of its original attack" is one creature, and
    a burst has no such thing.
    """
    foe = getattr(ev, "attacker", None)
    who = getattr(ev, "target", None)
    if foe is None or who is None or foe not in enemies(world, me):
        return False
    if who != me and not (
        who in allies(world, me)
        and line_of_effect(world, me, who)
        and not unseen_by(world, me, who)
    ):
        return False
    p = get(getattr(ev, "power", "") or "")
    if p is None:
        return False
    return p.reach_of(getattr(ev, "branch", 0)).kind in ("melee", "ranged")


@power(
    "p11725",
    level=7,
    cls="warlord",
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL],
    trigger="an enemy misses you or an ally you can see with a melee or ranged attack",
    on=Trigger(
        Miss,
        _missed_one_of_mine,
        "an enemy misses you or an ally you can see with a melee or ranged attack",
    ),
)
def p11725(c: Cast) -> None:
    """The enemy is read off the trigger rather than aimed at -- the printed
    target is "the triggering enemy". The repeat is that creature's own row
    run a second time, so it keeps its own numbers; `reentrant` is what lets
    it re-enter the use whose miss is being answered. "The new target must
    still be legal" is left to `use`, which refuses one out of reach."""
    ev = c.trigger
    foe = getattr(ev, "attacker", None)
    was = getattr(ev, "target", None)
    if foe is None or was is None:
        return
    # The original target is offered last: it is within 2 squares of itself
    # and so a legal choice, but the sentence exists to point the blow
    # somewhere else, and a decider that takes the first option should get
    # somewhere else wherever there is one.
    nearby = [*(w for w in c.within(2, of=was) if w != was), was]
    victim = c.choose(nearby, "who the enemy swings at instead")
    if victim is None:
        return
    c.grant_attack(foe, on=victim, ref=getattr(ev, "power", ""), reentrant=True)
