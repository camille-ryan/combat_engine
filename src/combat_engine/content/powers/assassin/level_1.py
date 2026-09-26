"""Assassin, level 1.

The class's signature resource -- the shrouds it stacks on a victim -- has
no representation in the engine: nothing counts them, nothing applies them,
and no `Cast` method names them. Where a row's shroud clause is a rider on
top of a complete attack it is dropped and said so in the docstring; where
it is the whole of the row, the row is not here at all.

The two builds are the class table's two secondaries: `second-cha` is the
one whose rider keys off Charisma, `second-con` the one whose rider keys off
Constitution.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    DEX,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    CloseBlast,
    Condition,
    DamageApplied,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    TurnStart,
    When,
    power,
)

SHADOW_WEAPON = [Keyword.SHADOW, Keyword.WEAPON]


@power(
    "p9403",
    level=1,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.SHADOW, Keyword.IMPLEMENT, Keyword.FORCE],
    attack=Attack(DEX, vs=FORT),
)
def p9403(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.dex_mod, dtype=DamageType.FORCE)
        c.pull(2)
        c.slowed(until=When.EONT)


@power(
    "p9404",
    level=1,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=SHADOW_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p9404(c: Cast) -> None:
    """"Melee weapon +2 reach" is written as a reach of 3 -- the header takes
    a number, not a weapon-relative offset. No ability modifier on the damage,
    as printed."""
    if c.strike(ignore_cover=True):
        c.damage(c.w())


@power(
    "p9405",
    level=1,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=SHADOW_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p9405(c: Cast) -> None:
    """The extra damage per uninvoked shroud is dropped: shrouds are not
    modelled, so there is no count to read."""
    if c.strike():
        c.damage(c.w(), c.dex_mod)


@power(
    "p9406",
    level=1,
    cls="assassin",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=SHADOW_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p9406(c: Cast) -> None:
    """"Each creature adjacent to the target" counts everybody but the target
    itself, the caster included -- which is the printed sentence."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        crowd = len([e for e in c.within(1, of=victim) if e != victim])
        c.damage(c.w(), c.dex_mod + crowd)


@power(
    "p9407",
    level=1,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=SHADOW_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p9407(c: Cast) -> None:
    """The invisibility is unconditional here: "while within 2 squares of the
    target" would need a distance gate on `c.invisible`, which takes none."""
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.invisible(to=c.target, on=c.me, until=When.EONT)


@power(
    "p9408",
    level=1,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.SHADOW],
    attack=Attack(DEX, vs=WILL),
)
def p9408(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("2d8", c.dex_mod, dtype=DamageType.PSYCHIC)
        c.grants_advantage(until=When.EONT)
        if c.build("second-cha") and c.cha_mod > 0:
            c.bonus(
                "damage",
                c.cha_mod,
                on=c.me,
                until=When.EONT,
                when=lambda ctx: ctx.get("target") == victim,
            )


@power(
    "p9409",
    level=1,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT, Keyword.SHADOW],
    attack=Attack(DEX, vs=REF),
)
def p9409(c: Cast) -> None:
    """Three rolls resolved as one hit. Each roll goes through `c.strike`, so
    three attacks are announced against the one target; the damage is dealt
    once and sized by how many of them landed."""
    landed = sum(1 for _ in range(3) if c.strike())
    if landed:
        c.damage(f"{landed}d8", dtype=DamageType.COLD)


@power(
    "p9410",
    level=1,
    cls="assassin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.SHADOW, Keyword.WEAPON],
    attack=Attack(DEX, vs=AC),
)
def p9410(c: Cast) -> None:
    if c.strike():
        extra = c.con_mod if c.build("second-con") else 0
        c.damage(c.w(2), c.dex_mod + extra)
        c.slowed(until=When.EONT)


@power(
    "p9411",
    level=1,
    cls="assassin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=SHADOW_WEAPON,
    attack=Attack(DEX, vs=AC),
)
def p9411(c: Cast) -> None:
    """The prone rider watches for the ongoing damage landing rather than for
    the save, which is what "whenever the target takes this ongoing damage"
    says. The Effect line is a bonus gated on shrouds and is dropped."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.ongoing(5, until=When.SAVE_ENDS)

        def tipped(ev: DamageApplied) -> None:
            if ev.target == victim and "ongoing" in ev.detail:
                c.prone(on=victim)

        c.watch(DamageApplied, tipped, until=When.ENCOUNTER)
    else:
        c.half_damage(c.w(2), c.dex_mod)


@power(
    "p9412",
    level=1,
    cls="assassin",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=SHADOW_WEAPON,
    attack=Attack(DEX, vs=FORT),
)
def p9412(c: Cast) -> None:
    """"Until the target saves against this power" is read as "while it is
    still immobilized by it" -- the immobilisation is the save-ends hold, so
    the two end together."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(), c.dex_mod)
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.UNTYPED),
        )
    else:
        c.half_damage(c.w(), c.dex_mod)
        c.immobilized(until=When.SAVE_ENDS)

    def reel(ev: TurnStart) -> None:
        if ev.actor == c.me and c.is_(Condition.IMMOBILIZED, on=victim):
            c.pull(3, on=victim)

    c.watch(TurnStart, reel, until=When.ENCOUNTER)


@power(
    "p9413",
    level=1,
    cls="assassin",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT, Keyword.SHADOW],
    attack=Attack(DEX, vs=WILL),
)
def p9413(c: Cast) -> None:
    """The Effect line doubles the shrouds the class feature lays down, and
    the feature does not exist here, so it is dropped."""
    if c.strike():
        c.damage("3d8", c.dex_mod, dtype=DamageType.COLD)
    else:
        c.half_damage("3d8", c.dex_mod, dtype=DamageType.COLD)


@power(
    "p9414",
    level=1,
    cls="assassin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.SHADOW],
    attack=Attack(DEX, vs=WILL),
)
def p9414(c: Cast) -> None:
    """One header target, so the primary is the declared one and the secondary
    attacks are rolled in the body with `c.strike(on=...)` -- the same attack
    line, which is what the printed secondary is. The primary's "adjacent to
    you" restriction has no header field and is not enforced."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("2d8", c.dex_mod, dtype=DamageType.PSYCHIC)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d8", c.dex_mod, dtype=DamageType.PSYCHIC)
        c.immobilized(until=When.EONT)
    for other in c.in_squares(c.area(), side="enemy"):
        if other != victim:
            c.push(4 if c.strike(on=other) else 2, on=other)
