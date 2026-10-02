"""Swordmage, level 1, the last ten.

`p5737` is the shape to read first: "an attack that does not include you"
is `leaves_me_out`, which reads the whole target list off the declaration.
Checking `ev.target != me` instead would punish an enemy for a burst that
did catch me, on every other target's announcement.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    INT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    AttackDeclared,
    Cast,
    CloseBurst,
    DamageType,
    Hit,
    Keyword,
    Melee,
    MoveEnd,
    TurnStart,
    UpTo,
    When,
    by_melee,
    leaves_me_out,
    power,
)

ARCANE_WEAPON = [Keyword.ARCANE, Keyword.WEAPON]
ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p3830",
    level=1,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(INT, vs=REF),
)
def p3830(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("1d8", dtype=DamageType.LIGHTNING)
    victim = c.target
    jolt = c.int_mod
    spent: dict[str, bool] = {}

    def stirred(ev: MoveEnd) -> None:
        if ev.actor == victim and not spent.get("done"):
            spent["done"] = True
            c.flat(jolt, dtype=DamageType.LIGHTNING, on=victim)

    c.watch(MoveEnd, stirred, until=When.EOTNT, on=victim, label=c.ref)


@power(
    "p3892",
    level=1,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.TELEPORTATION],
    attack=Attack(INT, vs=AC),
)
def p3892(c: Cast) -> None:
    """"+4 instead of +2" is the standing +2 for combat advantage plus
    another +2, handed to each of my side separately -- a modifier lives on
    a creature, and the printed line means every attacker."""
    if not c.strike():
        return
    c.damage(c.w(), c.int_mod)
    victim = c.target
    if c.may("change places", who=c.me):
        c.swap(victim)
    if not c.build("ensnarement"):
        return
    for mate in [c.me, *c.allies()]:
        c.bonus(
            "attack",
            2,
            on=mate,
            until=When.EONT,
            when=lambda ctx, v=victim: ctx.get("target") == v and bool(ctx.get("advantage")),
        )


@power(
    "p3895",
    level=1,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*ARCANE_WEAPON, Keyword.COLD],
    attack=Attack(INT, vs=AC),
)
def p3895(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(), c.int_mod, dtype=DamageType.COLD)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(), c.int_mod, dtype=DamageType.COLD)
        c.immobilized()


@power(
    "p4795",
    level=1,
    cls="swordmage",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.COLD],
    attack=Attack(INT, vs=AC),
)
def p4795(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.int_mod, dtype=DamageType.COLD)
    victim = c.target
    slow = c.con_mod

    def chill(ev: TurnStart) -> None:
        if ev.actor == victim and not ev.ghost and c.adjacent(victim) and slow > 0:
            c.penalty("speed", slow, on=victim, until=When.EOTNT)

    c.watch(TurnStart, chill, until=When.EOTNT, on=victim, once=True, label=c.ref)


@power(
    "p4796",
    level=1,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.THUNDER, Keyword.TELEPORTATION],
    attack=Attack(INT, vs=FORT),
)
def p4796(c: Cast) -> None:
    """The blink sits between the roll and the damage, as printed, so the
    burn at the end catches whoever is beside me *after* the move."""
    landed = c.strike()
    if c.con_mod > 0:
        c.teleport(c.con_mod)
    if landed:
        c.damage(c.w(2), c.int_mod, dtype=DamageType.THUNDER)
    for foe in c.within(1, side="enemy"):
        c.ongoing(5, DamageType.THUNDER, on=foe)


@power(
    "p5737",
    level=1,
    cls="swordmage",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*ARCANE_WEAPON, Keyword.FORCE],
    attack=Attack(INT, vs=AC),
)
def p5737(c: Cast) -> None:
    """The aegis clause grants a whole extra immediate interrupt, which is a
    row the spec does not give an id for; the mark and its bite are here."""
    if not c.strike():
        return
    c.damage(c.w(), c.int_mod)
    c.mark()
    victim = c.target
    me = c.me
    bite = c.int_mod

    def punish(ev: AttackDeclared) -> None:
        if leaves_me_out(c.world, me, ev):
            c.flat(bite, dtype=DamageType.FORCE, on=victim)

    c.on_attack(punish, by=victim, until=When.EONT, label=c.ref)


@power(
    "p5738",
    level=1,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(INT, vs=WILL),
)
def p5738(c: Cast) -> None:
    """"Cannot make opportunity attacks" is a threatened reach of nothing --
    `c.cannot_attack` would take away its turn as well."""
    held = When.SAVE_ENDS if c.strike() else When.EONT
    if held is When.SAVE_ENDS:
        c.damage("1d8", c.int_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage("1d8", c.int_mod, dtype=DamageType.PSYCHIC)
    c.cannot_shift(until=held)
    c.threatens(0, on=c.target, until=held)


@power(
    "p6834",
    level=1,
    cls="swordmage",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(INT, vs=AC),
)
def p6834(c: Cast) -> None:
    """Two separate steps: the free one the Effect line gives, and the one
    on the hit that the target is dragged into."""
    if c.may("step first", who=c.me):
        c.shift(1)
    if c.strike():
        c.damage(c.w(2 if c.level >= 21 else 1))
        spot = c.here
        if c.shift(1):
            c.slide(1, to=spot)
    elif c.may("step after", who=c.me):
        c.shift(1)


@power(
    "p7379",
    level=1,
    cls="swordmage",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.COLD],
    attack=Attack(INT, vs=AC),
)
def p7379(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(2 if c.level >= 21 else 1), c.int_mod, dtype=DamageType.COLD)
    others = [
        f for f in c.within(3, side="enemy") if f != c.target and c.marked(on=f)
    ]
    if others:
        second = c.choose(sorted(others), "the cold also bites")
        if second is not None:
            c.flat(c.con_mod, dtype=DamageType.COLD, on=second)


@power(
    "p7427",
    level=1,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[*ARCANE_WEAPON, Keyword.FORCE],
    attack=Attack(INT, vs=AC),
)
def p7427(c: Cast) -> None:
    """The half of the Effect that bars the target from squares next to my
    allies has no `Cast` method behind it; the half an ally can act on --
    move in, hit it, shove it -- is a watch on my side's hits."""
    if not c.strike():
        return
    c.damage(c.w(), c.int_mod, dtype=DamageType.FORCE)
    c.slide(2)
    victim = c.target
    mine = c.allies()

    def shove(ev: Hit) -> None:
        if ev.target != victim or ev.attacker not in mine:
            return
        if by_melee(c.world, ev.attacker, ev) and c.may("shove", who=ev.attacker):
            c.push(1, on=victim, by=ev.attacker)

    c.watch(Hit, shove, until=When.EONT, on=c.me, label=c.ref)
