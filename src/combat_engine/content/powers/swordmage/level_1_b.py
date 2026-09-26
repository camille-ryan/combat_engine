"""Swordmage, level 1, continued.

Two shapes worth naming. "Your melee attacks deal extra fire damage" is a
gate on the damage context, which carries `power` and not `attacker` -- so
the reach is looked up off the row that rolled. And the thrown-weapon rows
declare `thrown_by_hand`, because the printed Requirement is about what
leaves your hand rather than what you are holding.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    INT,
    INTERRUPT,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    Attack,
    Cast,
    CloseBlast,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    TurnEnd,
    When,
    both,
    by_melee,
    enemy_within,
    get,
    power,
    targets_me,
)

from . import beside

ARCANE_WEAPON = [Keyword.ARCANE, Keyword.WEAPON]
ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


def _is_melee(ctx: dict[str, Any]) -> bool:
    """A damage-context gate. The context has no `attacker` and no `ranged`,
    so "your melee attacks" is the reach of whichever row is rolling."""
    p = get(ctx.get("power") or "")
    return p is not None and p.reach.kind == "melee"


@power(
    "p1773",
    level=1,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.COLD],
    attack=Attack(INT, vs=AC),
)
def p1773(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(), c.int_mod, dtype=DamageType.COLD)
    victim = c.target
    bite = c.con_mod

    def sting(ev: Any) -> None:
        c.flat(bite, dtype=DamageType.COLD, on=victim)

    c.on_attack(sting, by=victim, until=When.SONT, label=c.ref)


@power(
    "p2078",
    level=1,
    cls="swordmage",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(INT, vs=FORT),
)
def p2078(c: Cast) -> None:
    """The Special is a precondition, not a consequence: with nowhere beside
    you to put the target, the row fails before it is rolled."""
    spot = beside(c)
    if spot is None:
        return
    if c.strike():
        c.damage("2d6" if c.level >= 21 else "1d6", c.int_mod, dtype=DamageType.LIGHTNING)
        c.pull(c.distance(), to=spot)


@power(
    "p3129",
    level=1,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.FORCE],
    attack=Attack(INT, vs=REF),
    thrown_by_hand=True,
    requires_text="you must throw your melee weapon at the target",
)
def p3129(c: Cast) -> None:
    """The weapon coming back is the Effect line and has no board state --
    `thrown_by_hand` in the header is the whole of it."""
    if c.strike():
        c.damage(c.w(), c.int_mod, dtype=DamageType.FORCE)
        c.mark()


@power(
    "p3130",
    level=1,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.FIRE, Keyword.TELEPORTATION],
    attack=Attack(INT, vs=AC),
)
def p3130(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(), c.int_mod, dtype=DamageType.FIRE)
    victim = c.target
    me = c.me

    def close(ev: TurnEnd) -> None:
        if ev.actor != victim or c.distance(victim) > 5:
            return
        if not c.may("close in", who=me):
            return
        spot = beside(c, victim)
        if spot is not None:
            c.teleport(c.distance(victim) + 1, who=me, to=spot)

    c.watch(TurnEnd, close, until=When.EOTNT, on=victim, once=True, label=c.ref)


@power(
    "p3137",
    level=1,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(INT, vs=REF),
)
def p3137(c: Cast) -> None:
    """The save-ends rider *is* the watch: one hold per target, carrying the
    subscription, so shaking it off takes the punishment with it."""
    victim = c.target
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.FORCE)
        bite = c.str_mod

        def stray(ev: TurnEnd) -> None:
            if ev.actor == victim and c.distance(victim) > 1:
                c.flat(bite, on=victim)

        c.watch(TurnEnd, stray, until=When.SAVE_ENDS, on=victim, label=c.ref)
    else:
        c.half_damage("1d8", c.int_mod, dtype=DamageType.FORCE)


@power(
    "p3138",
    level=1,
    cls="swordmage",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.POISON, Keyword.STANCE],
)
def p3138(c: Cast) -> None:
    """Both clauses pay off the same hit, and a marked target adjacent to
    itself is not a thing -- so a hit on my own mark can pay twice, once for
    its neighbours and once for itself, exactly as printed."""
    me = c.me
    bite = c.con_mod
    stance = c.stance(label=c.ref)

    def splash(ev: Hit) -> None:
        if ev.attacker != me or not by_melee(c.world, me, ev):
            return
        victim = ev.target
        for foe in c.within(1, of=victim, side="enemy"):
            if foe != victim:
                c.flat(bite, dtype=DamageType.POISON, on=foe)
        if c.marked(on=victim):
            c.flat(bite, dtype=DamageType.POISON, on=victim)

    rider = c.watch(Hit, splash, until=When.ENCOUNTER, on=me, label=c.ref)
    stance.on_end.append(lambda: c.world.effects.end(rider, "stance ended"))


@power(
    "p3326",
    level=1,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(INT, vs=REF),
)
def p3326(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.int_mod + c.str_mod, dtype=DamageType.FIRE)


@power(
    "p3327",
    level=1,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.FIRE],
    attack=Attack(INT, vs=AC),
)
def p3327(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.int_mod, dtype=DamageType.FIRE)
    if c.str_mod > 0:
        c.bonus(
            "damage", c.str_mod, on=c.me, until=When.ENCOUNTER, when=_is_melee
        )


@power(
    "p3328",
    level=1,
    cls="swordmage",
    usage=DAILY,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.COLD],
    attack=Attack(INT, vs=REF),
    trigger="an adjacent creature hits you",
    on=Trigger(Hit, both(targets_me, enemy_within(1)), "an adjacent creature hits you"),
)
def p3328(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.int_mod, dtype=DamageType.COLD)
    else:
        c.half_damage(c.w(3), c.int_mod, dtype=DamageType.COLD)


@power(
    "p3329",
    level=1,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(INT, vs=AC),
    thrown_by_hand=True,
    requires_text="you must throw your melee weapon at the target",
)
def p3329(c: Cast) -> None:
    """The Miss line is a chain of up to three more swings, each measured
    from the last creature missed rather than from the thrower."""
    if c.strike():
        c.damage(c.w(2), c.int_mod)
        return
    struck = [c.target]
    for _ in range(3):
        pool = [
            f
            for f in c.within(5, of=struck[-1], side="enemy")
            if f not in struck
        ]
        if not pool:
            return
        nxt = c.choose(sorted(pool), "the weapon carries on to")
        if nxt is None:
            return
        struck.append(nxt)
        if c.attack(c.int_, AC, on=nxt):
            c.damage(c.w(2), c.int_mod, on=nxt)
            return
