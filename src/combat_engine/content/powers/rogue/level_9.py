"""Rogue, level 9: the daily attacks. All three want a light blade.

`p1426` prints "save ends both" over a condition and a damage line, which is
one effect and one saving throw -- applying the two separately would let the
victim shake off half of a thing the book says is one, the trap
`fighter/level_5.py` records.

`p1032`'s standing arrangement fires in the `Window.BEFORE` half of
`AttackDeclared`, which is the only place a "before making a melee attack
against it" rider can happen: by the reaction window the blow has landed.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    DEX,
    FORT,
    ONE_CREATURE,
    STANDARD,
    Attack,
    AttackDeclared,
    Cast,
    DamageApplied,
    DamageType,
    Gear,
    Keyword,
    Melee,
    Relation,
    When,
    Window,
    World,
    distance,
    get,
    power,
    spread,
)
from combat_engine.engine.query import squares as squares_of

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


def _light_blade(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.is_light_blade)


def _herd(c: Cast, victim: int, squares_: int) -> None:
    """Slide the victim to another square beside the rogue, near enough that
    the printed distance covers it."""
    standing = squares_of(c.world, victim)
    room = sorted(
        sq
        for sq in spread({c.here}, 1) - {c.here}
        if sq not in standing
        and c.world.grid.passable(sq)
        and c.world.grid.occupant(sq) is None
        and min(distance(sq, s) for s in standing) <= squares_
    )
    where = c.choose(room, "where the blade steers it")
    if where is not None:
        c.slide(squares_, on=victim, to=where)


@power(
    "p1010",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=FORT),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p1010(c: Cast) -> None:
    """"If the unconscious target takes any damage, this unconsciousness
    ends" -- a listener hung on the effect itself, so it goes when the sleep
    does rather than outliving it on a clock of its own. The blow that put
    the target under has already been dealt by then.
    """
    if not c.strike():
        c.half_damage(c.w(2), c.dex_mod)
        c.dazed()
        return
    c.damage(c.w(2), c.dex_mod)
    victim = c.target
    sleep = c.unconscious(until=When.SAVE_ENDS)
    if sleep is None or victim is None:
        return

    def roused(ev: DamageApplied) -> None:
        if ev.target == victim and ev.amount > 0:
            c.world.effects.end(sleep, "it took damage")

    sleep.subs.append(c.world.bus.on(DamageApplied, roused))


@power(
    "p1032",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p1032(c: Cast) -> None:
    """The opening slide is part of the attack line, so it happens whether or
    not the swing lands, and it names its destination: a free slide of three
    would wander, and the printed line says the target ends in a different
    square adjacent to the rogue.

    The standing slide is aimed the same way. Handing it to the decider would
    as soon walk the target out of the reach of the blow it is setting up.
    """
    victim = c.target
    if victim is None:
        return
    _herd(c, victim, 3)
    if c.strike():
        c.damage(c.w(3), c.dex_mod)

    def before(ev: AttackDeclared) -> None:
        row = get(ev.power)
        if ev.attacker != c.me or ev.target != victim or not c.adjacent(victim):
            return
        if row is None or row.reach.kind != "melee":
            return
        if c.may("slide it a square", who=c.me):
            _herd(c, victim, 1)

    c.watch(
        AttackDeclared,
        before,
        until=When.ENCOUNTER,
        window=Window.BEFORE,
        label=c.ref,
    )


@power(
    "p1426",
    level=9,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=FORT),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p1426(c: Cast) -> None:
    # The ongoing damage is the one place this row reads Strength.
    if not c.strike():
        c.half_damage(c.w(2), c.dex_mod)
        return
    c.damage(c.w(2), c.dex_mod)
    victim = c.target
    if victim is None:
        return
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=f"{c.ref} bleeding and open",
        ongoing=(5 + c.str_mod, DamageType.UNTYPED),
        relations=[(Relation.GRANTS_CA_TO, victim, c.me)],
    )
