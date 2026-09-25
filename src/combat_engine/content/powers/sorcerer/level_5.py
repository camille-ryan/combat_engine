"""Sorcerer, level 5: dailies.

Three shapes worth naming.

**A secondary attack that is an area** -- p5272 and p5274 both print one --
is rolled by hand against whoever is in the ring, because `c.strike()` rolls
the header's own branch against the header's own targets and the secondary
has neither.

**"At the start of each of the target's turns, you can ..." (save ends)** is
a `TurnStart` watch held `until=When.SAVE_ENDS` **on the target**, so the
saving throw that ends the offer is the target's own -- which is what the
printed line means and what a caster-held watch would have got wrong.

**Invisibility** is `c.invisible(to=...)`, a relation rather than a flag, so
"while you are invisible to it" is `c.is_hidden(from_=...)` and reads back.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    CHA,
    DAILY,
    EACH_CREATURE,
    FORT,
    INTERRUPT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    TurnStart,
    UpTo,
    When,
    ZoneEntered,
    both,
    enemy_within,
    power,
    would_hit_me,
)
from combat_engine.engine.triggers import Trigger

from .knives import dagger

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]

_HIT_FROM_CLOSE = "an enemy within 5 squares of you hits you"

#: p5848 picks its element once and reads it back on the second target.
_element: list[DamageType | None] = [None]


@power(
    "p12470",
    level=5,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(CHA, vs=REF),
)
def p12470(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.cha_mod, dtype=DamageType.FORCE)
    else:
        c.half_damage("2d10", c.cha_mod, dtype=DamageType.FORCE)
    c.immobilized()


@power(
    "p13428",
    level=5,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
    requires=dagger,
    requires_text="needs a dagger",
)
def p13428(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.cha_mod)
        c.blinded(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.cha_mod)
        c.penalty("attack", 2)


@power(
    "p13448",
    level=5,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[
        *ARCANE_IMPLEMENT,
        Keyword.PSYCHIC,
        Keyword.ILLUSION,
        Keyword.TELEPORTATION,
    ],
    attack=Attack(CHA, vs=WILL),
)
def p13448(c: Cast) -> None:
    """The Effect line lasts the encounter whichever way the attack went, and
    it asks the same question each time -- am I unseen by this one -- rather
    than remembering which branch armed it."""
    victim = c.target
    if c.strike():
        c.damage("2d12", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.invisible(to=victim, on=c.me, until=When.SAVE_ENDS)
    else:
        c.half_damage("2d12", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.invisible(to=victim, on=c.me, until=When.EONT)

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker != victim or not c.is_hidden(from_=victim):
            return
        c.flat(5, dtype=DamageType.PSYCHIC, on=victim)
        if c.may("blink away", who=c.me):
            c.teleport(5)

    c.watch(
        AttackDeclared, swung, until=When.ENCOUNTER, on=c.me,
        label=f"{c.ref} unseen",
    )


@power(
    "p3185",
    level=5,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=FORT),
)
def p3185(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.COLD)
    else:
        c.half_damage("2d8", c.cha_mod, dtype=DamageType.COLD)

    if not c.first:
        return
    me, bite = c.me, c.cha_mod
    c.bonus(AC, 2, on=me, until=When.ENCOUNTER)
    c.bonus(FORT, 2, on=me, until=When.ENCOUNTER)

    def chill(ev: AttackRolled) -> None:
        from combat_engine.engine import get

        p = get(ev.power)
        result = getattr(ev, "result", None)
        if ev.target != me or p is None or p.reach.kind != "melee":
            return
        if result is not None and result.hit:
            c.flat(bite, dtype=DamageType.COLD, on=ev.attacker)

    c.watch(AttackRolled, chill, until=When.ENCOUNTER, on=me, label=f"{c.ref} rime")


@power(
    "p3759",
    level=5,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=REF),
)
def p3759(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.FIRE)
        c.vulnerable(10, DamageType.COLD, until=When.SAVE_ENDS)
    else:
        c.half_damage("1d10", c.cha_mod, dtype=DamageType.FIRE)
        c.vulnerable(5, DamageType.COLD, until=When.EONT)


@power(
    "p5272",
    level=5,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID],
    attack=Attack(CHA, vs=FORT),
)
def p5272(c: Cast) -> None:
    """The primary's Hit line is only the slide -- its damage is on the
    Effect line and lands whether or not the attack did."""
    from combat_engine.engine import spread
    from combat_engine.engine.query import squares

    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.slide(3)
    c.damage("2d6", dtype=DamageType.ACID, on=victim)

    ring = spread(squares(c.world, victim), 1)
    for near in c.in_squares(ring, side="any"):
        if c.attack(c.cha_, REF, on=near):
            c.damage("2d6", dtype=DamageType.ACID, on=near)


@power(
    "p5273",
    level=5,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p5273(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        far = 3
    else:
        c.half_damage("3d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        far = 1

    def lead(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == victim and c.may("walk it", who=c.me):
            c.slide(far, on=victim)

    c.watch(
        TurnStart, lead, until=When.SAVE_ENDS, on=victim, label=f"{c.ref} leads"
    )


@power(
    "p5274",
    level=5,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=FORT),
)
def p5274(c: Cast) -> None:
    """The jump is a move that provokes nothing, and the secondary burst is
    measured from wherever it ended -- so the ring is read again rather than
    reusing the header's area."""
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.THUNDER)
    if not c.last:
        return

    c.no_provoke(until=When.EOT)
    c.move(c.speed_of() + c.cha_mod)
    for near in c.within(1, side="any"):
        if c.attack(c.cha_, FORT, on=near):
            c.damage("2d6", dtype=DamageType.THUNDER, on=near)
            c.push(1, on=near)


@power(
    "p554",
    level=5,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(CHA, vs=REF),
)
def p554(c: Cast) -> None:
    """"Ignores cover and concealment, but not superior cover or total
    concealment" is `ignore_cover`, which drops the penalty the grid works
    out; superior cover is not separately exempted here."""
    if c.strike(ignore_cover=True):
        c.damage("3d10", c.cha_mod, dtype=DamageType.LIGHTNING)
    else:
        c.half_damage("3d10", c.cha_mod, dtype=DamageType.LIGHTNING)


@power(
    "p5847",
    level=5,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON, Keyword.ACID],
    attack=Attack(CHA, vs=FORT),
)
def p5847(c: Cast) -> None:
    """The burn is an Effect line and lands on a miss too."""
    if c.strike():
        c.damage("2d10", c.cha_mod, dtype=DamageType.POISON)
    c.ongoing(5, DamageType.ACID)


@power(
    "p5848",
    level=5,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.RADIANT],
    attack=Attack(CHA, vs=REF),
)
def p5848(c: Cast) -> None:
    """The spec prints a rider for cold and none for radiant, so radiant is
    damage alone.

    The element is chosen once for the whole power and read again on the
    second target -- the body runs once per target and a second `c.choose`
    would ask a player the same question twice. `_IN_FLIGHT` keeps a row out
    of its own re-entry, so a single slot is enough to carry it.

    "Slowed and cannot shift (save ends both)" is one `c.condition` call so
    that one saving throw answers both, rather than two effects and two.
    """
    if c.first:
        _element[0] = c.choose(
            [DamageType.COLD, DamageType.RADIANT], f"{c.ref}: which element"
        )
    kind = _element[0] or DamageType.COLD

    if c.strike():
        c.damage("3d6", c.cha_mod, dtype=kind)
        if kind is DamageType.COLD:
            c.condition(Condition.SLOWED, Condition.ROOTED, until=When.SAVE_ENDS)
    else:
        c.half_damage("3d6", c.cha_mod, dtype=kind)


@power(
    "p5849",
    level=5,
    cls="sorcerer",
    usage=DAILY,
    action=INTERRUPT,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.TELEPORTATION],
    attack=Attack(CHA, vs=WILL),
    trigger=_HIT_FROM_CLOSE,
    on=Trigger(
        AttackRolled, when=both(would_hit_me, enemy_within(5)), text=_HIT_FROM_CLOSE
    ),
)
def p5849(c: Cast) -> None:
    """Declared on the roll rather than on the landing: `would_hit_me` reads
    the result while the defence is still to be re-read, which is the window
    an interrupt owns."""
    foe = getattr(c.trigger, "attacker", None) or c.target
    c.teleport(c.speed_of())
    if foe is None:
        return
    if c.strike(on=foe):
        c.damage("2d10", c.cha_mod, dtype=DamageType.PSYCHIC, on=foe)
    else:
        c.half_damage("2d10", c.cha_mod, dtype=DamageType.PSYCHIC, on=foe)


@power(
    "p5850",
    level=5,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT, Keyword.ZONE],
    attack=Attack(CHA, vs=REF),
)
def p5850(c: Cast) -> None:
    """The Insight and Perception bonus is narrative -- nothing rolls either
    -- and "as a move action you can move the zone 3 squares" is the gap
    every zone row of this class records."""
    if c.strike():
        c.damage("3d6", c.cha_mod, dtype=DamageType.RADIANT)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    light = c.zone(area, label=c.ref, until=When.EONT)

    def expose(who: int) -> None:
        if who in c.enemies():
            c.grants_advantage(on=who, to="allies", until=When.EONT)

    for foe in c.in_squares(area, side="enemy"):
        expose(foe)

    def walked_in(ev: ZoneEntered) -> None:
        if ev.zone == light:
            expose(ev.actor)

    c.watch(ZoneEntered, walked_in, until=When.EONT, on=c.me, label=f"{c.ref} glare")
