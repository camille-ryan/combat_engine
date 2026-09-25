"""The avenger's oath, and the two questions the rest of the class asks of it.

Sixty of the hundred and forty rows below read "your oath of enmity target",
and nothing in the engine held one. `c.quarry` and `c.curse` are the same
relational shape -- one creature, named by one striker, asked about later --
but both are hard-wired to a `Relation` of their own (`QUARRY_OF`,
`CURSED_BY`) and there is no third. Borrowing the ranger's would make
`c.is_quarry()` true for an avenger, which is a different sentence.

So the oath is held as a named effect instead: `c.effect` is "a named hold
with no mechanical content of its own", and `c.suffering(label)` already
answers "everyone carrying an effect **I** applied", which is the per-avenger
part. `swear` and `sworn` are the only two things the level files use.

The benefit is the other half. "You make two attack rolls and use either
result" is not a bonus and there is no `c.strike(twice=True)`; what there is
is the live `AttackResult` riding on `AttackRolled`, and the engine deciding
hit or miss **from the result** after that event has been announced -- which
is what `c.reroll_attack` is built on. `better_of_two` raises the die in that
window, so a second roll is a second roll and not a +2.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AT_WILL,
    MINOR,
    ONE_CREATURE,
    AttackRolled,
    Cast,
    Keyword,
    Ranged,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.query import enemies

#: The label the hold carries. Substring-matched by `c.suffering`.
OATH = "oath of enmity"


def swear(c: Cast, victim: int | None = None) -> None:
    """Name a creature, releasing whoever was named before.

    "Replacing your current oath of enmity target if you have one" is
    printed on every row that re-swears, so the release is here rather than
    in each of them.
    """
    who = c.target if victim is None else victim
    if who is None:
        return
    for held in list(c.suffering(OATH, include_self=True)):
        for effect in list(c.world.effects.of(held)):
            if effect.source == c.me and OATH in effect.label:
                c.world.effects.end(effect, "sworn anew")
    c.effect(OATH, until=When.ENCOUNTER, on=who)


def sworn(world: World, me: int, who: int | None) -> bool:
    """Is that creature the oath target of *this* avenger?"""
    if who is None:
        return False
    return any(
        effect.source == me and OATH in effect.label
        for effect in world.effects.of(who)
    )


def is_oath(c: Cast, who: int | None = None) -> bool:
    """"If the target is your oath of enmity target"."""
    return sworn(c.world, c.me, c.target if who is None else who)


def oath_target(c: Cast) -> int | None:
    """Whoever is sworn against, for the rows that target them outright."""
    for eid in c.suffering(OATH):
        if sworn(c.world, c.me, eid):
            return eid
    return None


def better_of_two(c: Cast, ev: Any) -> None:
    """Roll the attack a second time and keep whichever is better.

    Mutates the live result the way `c.reroll_attack` does. Safe only in the
    `AttackRolled` window: `resolve.attack` re-reads `result.natural` after
    announcing the roll, and decides hit, miss and critical from it.
    """
    result = getattr(ev, "result", None)
    if result is None:
        return
    fresh = c.world.rng.d20().total
    if fresh > result.natural:
        result.total += fresh - result.natural
        result.natural = fresh


def _melee(ev: Any) -> bool:
    declared = get(getattr(ev, "power", ""))
    if declared is None:
        return False
    return declared.reach_of(getattr(ev, "branch", 0)).kind == "melee"


@power(
    "cf:avenger-oath",
    level=0,
    cls="avenger",
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.DIVINE],
)
def avenger_oath(c: Cast) -> None:
    """Swear against one enemy; swing at it alone and you roll twice.

    The watcher asks who is sworn at the moment the die lands rather than
    closing over the creature, because half a dozen rows re-swear mid-fight
    and a closure would go on paying out against the old one. It is armed
    once: this is an at-will minor action, and a second arming would be a
    third roll.
    """
    victim = c.target
    if victim is None:
        return
    swear(c, victim)

    me, label = c.me, f"{c.ref} twice"
    if any(label in effect.label for effect in c.world.effects.of(me)):
        return

    def twice(ev: AttackRolled) -> None:
        if ev.attacker != me or not sworn(c.world, me, ev.target) or not _melee(ev):
            return
        others = [
            foe
            for foe in enemies(c.world, me)
            if foe != ev.target and c.adjacent(foe)
        ]
        if not others:
            better_of_two(c, ev)

    c.watch(AttackRolled, twice, until=When.ENCOUNTER, on=me, label=label)
