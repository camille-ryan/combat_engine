"""Warden, level 7: the encounter attacks.

`p9852` is the one with a declared trigger. "An enemy enters a square
adjacent to an ally" is `AdjacencyGained`, which names the creature that
actually moved -- without that field the row would also fire when the ally
walked up to the enemy, which is not the printed line.
"""

from __future__ import annotations

from combat_engine.engine import *
from combat_engine.engine.events import AdjacencyGained
from combat_engine.engine.query import distance_between, team

PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]


def _melee_attack(ctx: dict) -> bool:
    p = get(ctx.get("power", ""))
    return p is not None and p.reach.kind == "melee"


def _closed_on_my_ally(world: World, me: int, ev: AdjacencyGained) -> bool:
    mover = ev.mover
    if mover == me or not mover or team(world, mover) is team(world, me):
        return False
    ally = ev.other if ev.actor == mover else ev.actor
    return (
        ally != me
        and team(world, ally) is team(world, me)
        and distance_between(world, me, ally) <= 3
    )


@power(
    "p11077",
    level=7,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.FIRE],
    attack=Attack(STR, vs=AC),
)
def p11077(c: Cast) -> None:
    """The concealment the smoke leaves behind has no expression -- a zone
    blocks sight outright or not at all -- so only the attack is written."""
    if c.strike():
        c.damage(c.w(), c.str_mod)
        c.damage("1d12", dtype=DamageType.FIRE)


@power(
    "p16488",
    level=7,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.THUNDER],
    attack=Attack(STR, vs=FORT),
)
def p16488(c: Cast) -> None:
    """Shaking a burrower loose and barring it from burrowing again wants a
    way to take a movement mode away; `c.mode` only grants one."""
    if c.strike():
        c.damage(c.w(), c.str_mod, dtype=DamageType.THUNDER)
        c.slowed(until=When.EONT)


@power(
    "p5123",
    level=7,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p5123(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.heal(10, on=c.me)


@power(
    "p5124",
    level=7,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=FORT),
)
def p5124(c: Cast) -> None:
    """"Melee attack rolls" is read off the row doing the attacking: the
    modifier context has a power and no reach of its own."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        amount = 1 + c.con_mod if c.build("earthstrength") else 2
        c.penalty("attack", amount, until=When.EONT, when=_melee_attack)


@power(
    "p5125",
    level=7,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.POISON],
    attack=Attack(STR, vs=REF),
)
def p5125(c: Cast) -> None:
    """The secondary attack is the same line against the same defence, so
    it is the header's attack rolled again rather than a second one."""
    if not c.strike():
        return
    c.damage(c.w(), c.str_mod)
    primary = c.target
    for e in c.within(1, of=primary, side="enemy"):
        if e != primary and c.strike(on=e):
            c.flat(5, dtype=DamageType.POISON, on=e)


@power(
    "p5515",
    level=7,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PRIMAL,
        Keyword.WEAPON,
        Keyword.PSYCHIC,
        Keyword.FEAR,
    ],
    attack=Attack(STR, vs=AC),
)
def p5515(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    c.slide(1)
    victim = c.target
    others = [x for x in c.within(1, of=victim) if x not in (c.me, victim)]
    second = c.choose(others, "who it is shoved into", optional=True) if others else None
    if second is None:
        return
    c.slide(1, on=second)
    if c.build("wildblood"):
        c.flat(c.wis_mod, dtype=DamageType.PSYCHIC, on=victim)
        c.flat(c.wis_mod, dtype=DamageType.PSYCHIC, on=second)


@power(
    "p5519",
    level=7,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p5519(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod)
        if c.may("drag it closer rather than floor it"):
            c.pull(2 if c.build("earthstrength") else 1)
        else:
            c.prone()


@power(
    "p5565",
    level=7,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=WILL),
)
def p5565(c: Cast) -> None:
    """Only the warden's own marks are targets, and `Target` carries no
    filter for that, so the restriction is asked here."""
    if c.marked() and c.strike():
        c.damage(c.w(), c.str_mod)


@power(
    "p9852",
    level=7,
    cls="warden",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
    charges=True,
    trigger="an enemy enters a square adjacent to an ally within 3 squares of you",
    on=Trigger(
        AdjacencyGained,
        _closed_on_my_ally,
        "an enemy moves next to an ally within 3 squares of you",
    ),
)
def p9852(c: Cast) -> None:
    """`charges=True` is not "this is a charge" -- it is the only header
    field that makes the engine measure reach *after* the row's own move,
    and without it the row is refused in exactly the situation it is for.
    The printed move is a shift; `c.run_at` is the only thing that walks to
    a named creature, so the warden can be swung at on the way."""
    victim = getattr(c.trigger, "mover", None) or c.target
    if victim is None:
        return
    c.run_at(victim)
    if c.strike(on=victim):
        c.damage(c.w(), c.str_mod, on=victim)
        c.penalty("attack", 5, on=victim, until=When.EOTNT)


@power(
    "p9853",
    level=7,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9853(c: Cast) -> None:
    """Taking the blow means stepping into it before it is rolled, so the
    watch sits in the interrupt window of `AttackDeclared` and moves the
    target across after the two have changed places."""
    if c.strike():
        c.damage(c.w(), c.str_mod)
    if not c.first:
        return

    def step_in(ev: AttackDeclared) -> None:
        ally = ev.target
        if ally == c.me or ally not in c.allies() or not c.adjacent(ally):
            return
        if c.may("take the blow", who=c.me):
            c.swap(ally)
            ev.target = c.me

    c.watch(AttackDeclared, step_in, until=When.EONT, window=Window.BEFORE)


@power(
    "p9854",
    level=7,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.COLD],
    attack=Attack(STR, vs=AC),
)
def p9854(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod, dtype=DamageType.COLD)
    c.slowed(until=When.EONT)
    victim = c.target
    if not c.build("stormheart"):
        return

    def backlash(ev: AttackDeclared) -> None:
        if ev.target == c.me:
            return
        c.flat(c.con_mod, dtype=DamageType.COLD, on=victim)
        for e in c.enemies():
            if e != victim and c.marked(e):
                c.flat(c.con_mod, dtype=DamageType.COLD, on=e)

    c.on_attack(backlash, by=victim, until=When.EONT)


@power(
    "p9967",
    level=7,
    cls="warden",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=UpTo(2, "any"),
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9967(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.str_mod)
