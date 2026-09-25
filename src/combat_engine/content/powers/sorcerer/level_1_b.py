"""Sorcerer, level 1: the rest of the attack rows.

Two shapes appear here and are reused at every later level.

**A ring of fire around somebody** -- "any enemy that enters a square
adjacent to the target or starts its turn there takes 1d6, once per turn" --
is exactly `c.hazard`, which carries all three clauses including the latch.
The ring is `ground.ringing`, taken where the row is used; it does not
follow the creature, which is the one place this falls short of the card.

**"Reduce the damage you take"** is declared on `DamageRolled` rather than
on the printed `Hit`: the amount rides that event and is read back once the
window closes, so a reaction can empty it. `warlock/level_10.py` uses the
same seam.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    CHA,
    DAILY,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Event,
    Hit,
    Keyword,
    Ranged,
    Trigger,
    TurnStart,
    UpTo,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.events import DamageRolled

from .ground import ringing

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]

_HIT_AND_HURT = "an enemy within 10 squares hits you"


def _hurt_me_from_afar(world: World, me: int, ev: Event) -> bool:
    """"An enemy in the area hits you with an attack", measured by the blow.

    `DamageRolled` names the dealer `source` and carries the row in
    `detail`, which is what tells an attack apart from a burn.
    """
    from combat_engine.engine.query import distance_between, team

    who = getattr(ev, "source", None)
    return (
        getattr(ev, "target", None) == me
        and getattr(ev, "amount", 0) > 0
        and who is not None
        and who != me
        and team(world, who) is not team(world, me)
        and get(getattr(ev, "detail", "")) is not None
        and distance_between(world, who, me) <= 10
    )


@power(
    "p3718",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=REF),
)
def p3718(c: Cast) -> None:
    """The ring is laid where the target is standing when it is hit. It does
    not follow the target afterwards -- a zone has no anchor, and an aura
    belongs to a creature rather than to an enemy of its maker."""
    if not c.strike():
        return
    c.damage("2d8", c.cha_mod, dtype=DamageType.FIRE)
    ring = ringing(c, c.target)
    if ring:
        c.hazard(
            ring, "1d6", DamageType.FIRE,
            label=c.ref, until=When.SONT, sustain=None,
        )


@power(
    "p5114",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=FORT),
)
def p5114(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.cha_mod, dtype=DamageType.THUNDER)
        c.push(3)


@power(
    "p5259",
    level=1,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID],
    attack=Attack(CHA, vs=REF),
)
def p5259(c: Cast) -> None:
    """"Can be used as a ranged basic attack" -- see p10319."""
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.ACID)


@power(
    "p5260",
    level=1,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p5260(c: Cast) -> None:
    """The whole secondary chain is the Wild Magic clause and goes with the
    fork; the primary is what every sorcerer gets."""
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.PSYCHIC)


@power(
    "p5261",
    level=1,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER],
    attack=Attack(CHA, vs=FORT),
)
def p5261(c: Cast) -> None:
    """"Before or after the attack" is a choice with no consequence here --
    the shift is one square and nothing is resolved between the two -- so it
    is taken afterwards."""
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.THUNDER)
    c.shift(1)


@power(
    "p5262",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=UpTo(2),
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p5262(c: Cast) -> None:
    """The Wild Magic clause -- a slide instead of the push -- goes with the
    fork."""
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.push(c.dex_mod)


@power(
    "p5263",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=FORT),
)
def p5263(c: Cast) -> None:
    if c.strike():
        c.damage("3d6", c.cha_mod, dtype=DamageType.COLD)
        c.penalty(REF, 2)


@power(
    "p5264",
    level=1,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=WILL),
)
def p5264(c: Cast) -> None:
    """The Wild Magic clause -- a save-ends penalty to attacks against you
    -- goes with the fork."""
    if c.strike():
        c.damage("6d6", c.cha_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage("6d6", c.cha_mod, dtype=DamageType.RADIANT)


@power(
    "p5265",
    level=1,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON],
    attack=Attack(CHA, vs=FORT),
)
def p5265(c: Cast) -> None:
    """The Miss line is the full damage again rather than half of it, which
    is what the card prints -- only the burn is lost."""
    if c.strike():
        c.damage("2d8", c.cha_mod)
        c.ongoing(5, DamageType.POISON)
    else:
        c.damage("2d8", c.cha_mod)


@power(
    "p5266",
    level=1,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(CHA, vs=REF),
)
def p5266(c: Cast) -> None:
    """The Dragon Magic clause -- 5 lightning on top of the shove -- goes
    with the fork."""
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.LIGHTNING)
    else:
        c.half_damage("3d8", c.cha_mod, dtype=DamageType.LIGHTNING)

    if not c.first:
        return
    me = c.me

    def shove(ev: Hit) -> None:
        p = get(ev.power)
        if ev.target == me and p is not None and p.reach.kind == "melee":
            c.push(1, on=ev.attacker, anchor=c.here)

    c.watch(Hit, shove, until=When.EONT, on=me, label=f"{c.ref} recoil")


@power(
    "p5840",
    level=1,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT, Keyword.FIRE, Keyword.ZONE],
    attack=Attack(CHA, vs=REF),
)
def p5840(c: Cast) -> None:
    """The burning ground is the whole Cosmic Magic clause and goes with the
    fork; the burst itself is what every sorcerer gets."""
    if c.strike():
        c.damage("1d4", c.cha_mod, dtype=DamageType.RADIANT)


@power(
    "p5841",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(CHA, vs=REF),
)
def p5841(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.LIGHTNING)
        c.prone()
        c.slowed()


@power(
    "p5842",
    level=1,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=WILL),
)
def p5842(c: Cast) -> None:
    """"Cannot shift" is `c.rooted` rather than immobilised -- the target
    still walks. The Cosmic Magic attack penalty goes with the fork."""
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.COLD)
        c.rooted(until=When.EOTNT)


@power(
    "p5843",
    level=1,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p5843(c: Cast) -> None:
    """The rider is rolled; the Cosmic Magic clause that lets it be chosen
    instead goes with the fork. "The power gains the radiant keyword" is a
    header field and cannot be turned on mid-run, so the burn is radiant and
    the keyword line is not written."""
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)

    face = c.roll("1d6")
    if face <= 2:
        c.ongoing(5, DamageType.RADIANT)
    elif face <= 4:
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.dazed(until=When.SAVE_ENDS)


@power(
    "p5844",
    level=1,
    cls="sorcerer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(CHA, vs=REF),
)
def p5844(c: Cast) -> None:
    """The standing crackle is an aura for the board to draw plus a watch on
    turn starts: the printed line bites only on a creature *starting* its
    turn adjacent, where `c.burns` would also bite on arrival.

    "You can dismiss the effect as a free action" is not written -- nothing
    offers ending one's own effect except `drop_cost`, which `c.aura` does
    not take.
    """
    if c.strike():
        c.damage("3d6", c.cha_mod, dtype=DamageType.LIGHTNING)
        c.pull(c.dex_mod)

    if not c.first:
        return
    c.aura(1, label=c.ref, until=When.ENCOUNTER)
    me, bite = c.me, c.dex_mod

    def crackle(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if c.adjacent(ev.actor):
            c.flat(bite, dtype=DamageType.LIGHTNING, on=ev.actor)

    c.watch(TurnStart, crackle, until=When.ENCOUNTER, on=me, label=f"{c.ref} arc")


@power(
    "p7405",
    level=1,
    cls="sorcerer",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=REF),
)
def p7405(c: Cast) -> None:
    """"Any enemy providing the target cover against this attack" is asked of
    the grid one creature at a time: `Grid.cover` takes the squares to treat
    as blockers, so an enemy provides cover exactly when its own space is
    enough to spoil the line."""
    from combat_engine.engine.query import squares
    from combat_engine.engine.types import Cover

    victim = c.target
    if not c.strike():
        return
    c.damage("1d8", c.cha_mod, dtype=DamageType.FIRE)
    here, there = c.here, c.there
    for foe in c.enemies():
        if foe == victim:
            continue
        blocks = squares(c.world, foe)
        if c.world.grid.cover(here, there, blockers=set(blocks)) is not Cover.NONE:
            c.flat(c.cha_mod, dtype=DamageType.FIRE, on=foe)


@power(
    "p7426",
    level=1,
    cls="sorcerer",
    usage=DAILY,
    action=REACTION,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
    trigger=_HIT_AND_HURT,
    on=Trigger(DamageRolled, when=_hurt_me_from_afar, text=_HIT_AND_HURT),
)
def p7426(c: Cast) -> None:
    """The Effect line runs before the attack, and the blow it softens is
    still on the event as a mutable number."""
    ev = c.trigger
    if ev is not None:
        ev.amount = max(0, getattr(ev, "amount", 0) - c.cha_mod)

    foe = getattr(ev, "source", None) or c.target
    if foe is None:
        return
    if c.strike(on=foe):
        c.damage("1d10", c.cha_mod, on=foe)
        c.slowed(until=When.SAVE_ENDS, on=foe)
        c.slide(2, on=foe)
    else:
        c.half_damage("1d10", c.cha_mod, on=foe)
        c.slide(1, on=foe)
