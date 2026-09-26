"""Swordmage, level 10: the utilities.

`p5753` undoes a condition rather than applying one, and there is no method
for that -- so it reaches into the live effects and ends the hold that is
carrying the prone. Everything else here is a stance or a blink.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    PERSONAL,
    REF,
    SELF,
    WILL,
    Cast,
    Condition,
    ConditionApplied,
    Hit,
    Keyword,
    Trigger,
    When,
    World,
    both,
    by_melee,
    by_ranged,
    hits_me,
    power,
    targets_me,
)
from combat_engine.engine.dsl import get

from . import beside


def _prone_on_me(world: World, me: int, ev: Any) -> bool:
    """`ConditionApplied` names its subject `target`, so `about_me` would be
    false here forever. `targets_me` is the half of this that is ready-made;
    the condition itself has no predicate of its own."""
    return targets_me(world, me, ev) and getattr(ev, "condition", None) is Condition.PRONE


@power(
    "p10437",
    level=10,
    cls="swordmage",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.STANCE],
)
def p10437(c: Cast) -> None:
    """One bonus, sized by the build. Written as a +1 plus a gated +1 it
    would come to +1 forever, since two power bonuses do not add."""
    me = c.me
    step = 2 if c.build("assault") else 1
    stance = c.stance(label=c.ref)

    def guard(ev: Hit) -> None:
        if ev.attacker != me or not by_melee(c.world, me, ev):
            return
        p = get(ev.power or "")
        if p is None or Keyword.WEAPON not in p.keywords:
            return
        for what in (AC, FORT, REF, WILL):
            c.bonus(what, step, on=me, until=When.SONT)

    rider = c.watch(Hit, guard, until=When.ENCOUNTER, on=me, label=c.ref)
    stance.on_end.append(lambda: c.world.effects.end(rider, "stance ended"))


@power(
    "p3368",
    level=10,
    cls="swordmage",
    usage=DAILY,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
    trigger="an enemy within 20 squares of you hits you with a ranged attack",
    on=Trigger(
        Hit,
        both(hits_me, by_ranged),
        "an enemy within 20 squares of you hits you with a ranged attack",
    ),
)
def p3368(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    spot = beside(c, foe)
    if spot is not None:
        c.teleport(c.distance(foe) + 1, to=spot)


@power(
    "p3957",
    level=10,
    cls="swordmage",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.STANCE],
)
def p3957(c: Cast) -> None:
    """The three skill bonuses are not board state; the speed and the rough
    ground are."""
    me = c.me
    stance = c.stance(label=c.ref)
    for rider in (
        c.bonus("speed", 2, on=me, until=When.ENCOUNTER),
        c.ignores_difficult(on=me, until=When.ENCOUNTER),
    ):
        if rider is not None:
            stance.on_end.append(lambda r=rider: c.world.effects.end(r, "stance ended"))


@power(
    "p3958",
    level=10,
    cls="swordmage",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def p3958(c: Cast) -> None:
    """The whole printed Effect is an Athletics check with a bonus. Jumping
    is not modelled as movement, so this is deliberately inert."""
    c.note(f"{c.ref}: a running jump, +10, as far as the check allows")


@power(
    "p5753",
    level=10,
    cls="swordmage",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
    trigger="you are knocked prone or fall",
    on=Trigger(ConditionApplied, _prone_on_me, "you are knocked prone"),
)
def p5753(c: Cast) -> None:
    """A free action answers after the fact, so the prone has landed by the
    time this runs and has to be taken off again. Falling damage is not
    modelled, so the other half of the printed line has nothing to stop."""
    for eff in list(c.world.effects.of(c.me)):
        if Condition.PRONE in eff.conditions:
            c.world.effects.end(eff, c.ref)


@power(
    "p3367",
    level=10,
    cls="swordmage",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p3367(c: Cast) -> None:
    """Left out of the first pass: the +2 is worked out inside
    `query.has_combat_advantage` from the board, so no modifier reached it
    until that read a key. `c.no_advantage` shuts all four routes, which is
    what "to any of your enemies" means."""
    c.no_advantage(until=When.EONT)
