"""Sorcerer, level 9: dailies.

**"First Failed Saving Throw"** is `escalate`, which runs on the first
failed save and on no other -- p2383 chains three targets through it.

**A conjuration's bite** is a hand-written `TurnStart` watch rather than
`c.conjure(burn=...)`: the printed line catches a creature *starting* its
turn beside the thing, and `c.burns` also bites on arrival. `c.adjacent_to`
asks the question of a conjuration, which `c.adjacent` cannot.

One row of this level is left out; see the report and `docs/blocked.json`.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    CHA,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Effect,
    Keyword,
    Ranged,
    TurnStart,
    UpTo,
    When,
    power,
)
from combat_engine.engine.events import MoveEnd
from combat_engine.engine.query import distance_between

from .knives import dagger

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p13430",
    level=9,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.WEAPON, Keyword.FORCE],
    attack=Attack(CHA, vs=AC),
    requires=dagger,
    requires_text="needs a dagger",
)
def p13430(c: Cast) -> None:
    """"If only one target was in the blast" is a question about the target
    list, not about how many were hit."""
    alone = len(c.targets) == 1
    if c.strike():
        c.damage(c.w(2), c.cha_mod, dtype=DamageType.FORCE)
        if alone:
            c.damage(c.w(3), dtype=DamageType.FORCE)
    else:
        c.half_damage(c.w(2), c.cha_mod, dtype=DamageType.FORCE)


@power(
    "p2383",
    level=9,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(CHA, vs=REF),
)
def p2383(c: Cast) -> None:
    """Two links, and they are measured from different places: the secondary
    is "within 5 squares of **you**", the tertiary "within 5 squares of the
    secondary target". Each is hung on the one before with `escalate`, which
    runs on the first failed save and no other.
    """

    def tertiary(second: int) -> object:
        def worse(_eff: Effect) -> None:
            pool = sorted(
                f for f in c.within(5, of=second, side="enemy") if f != second
            )
            third = c.choose(pool, f"{c.ref}: where it runs next") if pool else None
            if third is not None:
                c.condition(
                    until=When.SAVE_ENDS, on=third,
                    ongoing=(5, DamageType.LIGHTNING),
                )

        return worse

    def secondary(_eff: Effect) -> None:
        pool = sorted(f for f in c.enemies() if c.distance(f) <= 5)
        second = c.choose(pool, f"{c.ref}: where it runs") if pool else None
        if second is not None:
            c.condition(
                until=When.SAVE_ENDS, on=second,
                ongoing=(5, DamageType.LIGHTNING),
                escalate=tertiary(second),
            )

    landed = bool(c.strike())
    c.damage("2d8", c.cha_mod, dtype=DamageType.LIGHTNING)
    if landed:
        c.condition(
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.LIGHTNING),
            escalate=secondary,
        )


@power(
    "p3039",
    level=9,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=FORT),
)
def p3039(c: Cast) -> None:
    if c.strike():
        c.damage("3d8", c.cha_mod)
        c.push(3)
    else:
        c.half_damage("3d8", c.cha_mod)
        c.push(1)
    if c.first:
        c.mode("fly", c.speed_of(), on=c.me, until=When.EONT)


@power(
    "p3041",
    level=9,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.CONJURATION],
    attack=Attack(CHA, vs=REF),
)
def p3041(c: Cast) -> None:
    """The stalagmite's own numbers -- AC 5, Reflex 5, Fortitude 21, resist
    cold 10, 40 hit points -- are not written: a conjuration is an entity
    with a position and no health or defences, so there is nothing for an
    attack against it to read. Dismissing it as a free action has no door
    either; it lasts the encounter.
    """
    if not c.strike():
        return
    c.damage("1d12", c.cha_mod, dtype=DamageType.COLD)
    was = c.there
    c.slide(1)
    if c.world.grid.occupant(was) is not None:
        return

    spike = c.conjure(
        at=was, label=c.ref, until=When.ENCOUNTER, sustain=None, aura=1
    )
    bite = c.cha_mod

    def chill(ev: TurnStart) -> None:
        if not ev.ghost and c.adjacent_to(spike, ev.actor):
            c.flat(bite, dtype=DamageType.COLD, on=ev.actor)

    c.watch(
        TurnStart, chill, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} rime"
    )


@power(
    "p3769",
    level=9,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=FORT),
)
def p3769(c: Cast) -> None:
    """The burn lands on both branches; only the damage is lost on a miss.
    The Dragon Magic clause that sizes the AC bonus off Strength goes with
    the fork."""
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.THUNDER)
    c.ongoing(5, DamageType.THUNDER)
    if c.first:
        c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER)


@power(
    "p3771",
    level=9,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=FORT),
)
def p3771(c: Cast) -> None:
    """The Effect line is per target and lands whether or not the attack
    did, so the trap is armed outside the branch."""
    victim = c.target
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.FIRE)
    if victim is None:
        return

    def flares(_ev: object) -> None:
        c.damage("2d8", dtype=DamageType.FIRE, on=victim)

    c.on_attack(
        flares, by=victim, until=When.SONT, once=True, label=f"{c.ref} punishes"
    )


@power(
    "p5279",
    level=9,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON],
    attack=Attack(CHA, vs=FORT),
)
def p5279(c: Cast) -> None:
    """The hold is `until=When.SAVE_ENDS` **on the target**, so the target's
    own saving throw is what takes the watch away with it."""
    victim = c.target
    if c.strike():
        c.damage("2d10", c.cha_mod, dtype=DamageType.POISON)
    if victim is None:
        return
    c.slide(c.cha_mod)

    def reeks(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == victim or ev.actor not in c.enemies():
            return
        if distance_between(c.world, ev.actor, victim) <= 1:
            c.damage("1d10", dtype=DamageType.POISON, on=ev.actor)

    c.watch(
        TurnStart, reeks, until=When.SAVE_ENDS, on=victim, label=f"{c.ref} reeks"
    )


@power(
    "p5280",
    level=9,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p5280(c: Cast) -> None:
    """Hung on `MoveEnd` rather than `MoveStart`: the printed line knocks the
    target down *during* the movement, and `MoveStart` fires where nothing
    has happened yet."""
    victim = c.target
    if not c.strike():
        c.half_damage("3d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.prone()
        return
    c.damage("3d8", c.cha_mod, dtype=DamageType.PSYCHIC)

    def tripped(ev: MoveEnd) -> None:
        if ev.actor == victim and c.may("trip it", who=c.me):
            c.prone(on=victim)

    c.watch(
        MoveEnd, tripped, until=When.EONT, on=c.me, once=True,
        label=f"{c.ref} trips",
    )


@power(
    "p5856",
    level=9,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER, Keyword.ZONE],
    attack=Attack(CHA, vs=FORT),
)
def p5856(c: Cast) -> None:
    """"As a move action, you can move the zone 6 squares" is not written --
    a zone has no speed and nothing offers moving one. The same gap p3034
    and p5850 record."""
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.THUNDER)
        c.slide(c.dex_mod)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    swirl = c.zone(area, label=c.ref, until=When.EONT)

    def whirl(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(swirl):
            c.slide(2, on=ev.actor)

    c.watch(TurnStart, whirl, until=When.EONT, on=c.me, label=f"{c.ref} whirls")


@power(
    "p5857",
    level=9,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p5857(c: Cast) -> None:
    """"It cannot take immediate actions or opportunity actions" is not
    written: `Rules.no_reactions` is reachable only through DAZED and
    STUNNED, each of which carries a great deal else. The burn is an Effect
    line and lands on a miss too."""
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.PSYCHIC)
    c.ongoing(5, DamageType.PSYCHIC)
