"""Wizard, level 5: the daily attacks.

Three of the four leave something on the board -- a conjuration and two
zones -- and all three of those are built from `c.area()`, which reads the
aim point off the `Cast`. The caveat in `level_1.py` still holds: a caller
that lets the engine pick the aim gets a burst centred near the caster.

`c.hazard` cannot say "blocks line of sight", so the obscuring zone is made
with `c.zone(..., blocks_sight=True)` and given its teeth separately with
`c.burns` -- the two halves `c.hazard` is.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    EACH_CREATURE,
    FORT,
    INT,
    MINOR,
    ONE_CREATURE,
    REF,
    STANDARD,
    AreaBurst,
    Attack,
    Cast,
    Condition,
    DamageType,
    Keyword,
    MoveEnd,
    Ranged,
    Relation,
    When,
    power,
    spread,
)
from combat_engine.engine.components import Conjuration

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p1195",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    # "One creature adjacent to the hand" -- the hand is placed next to
    # whoever was picked, which is the same thing said from the other end.
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.CONJURATION],
    attack=Attack(INT, vs=REF),
)
def p1195(c: Cast) -> None:
    """The hand occupies a square, swings with its maker's numbers from its
    own position, and is walked six squares with a move action -- all of
    which `c.conjure` is.

    The grab is the caster's rather than the hand's. A conjuration holds no
    relations of its own, and the printed escape line already rolls against
    the caster's defences, so this is where the clause was pointing anyway.

    Two clauses have no vocabulary and are left off rather than guessed at:
    that commanding it again is barred while it has hold of somebody, and
    that the caster may let go as a free action.
    """
    if not c.first:
        return
    victim = c.target
    room = [
        sq
        for sq in sorted(spread({c.there}, 1) - {c.there})
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    ]
    hand = c.conjure(
        c.choose(room, "where the hand stands"),
        label="p1195",
        until=When.SUSTAIN,
        sustain=MINOR,
        speed=6,
    )
    if not hand:
        return
    # It appears swinging.
    if victim is not None and c.strike(from_=hand):
        c.damage("2d8", c.int_mod, dtype=DamageType.COLD)
        c.grab()

    def squeeze() -> None:
        for caught in c.world.relations.targets(Relation.GRABBED_BY, c.me):
            c.damage("1d8", c.int_mod, dtype=DamageType.COLD, on=caught)

    conj = c.world.get(hand, Conjuration)
    c.on_sustain(c.world.effects.live.get(conj.effect) if conj else None, squeeze)


@power(
    "p1553",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(3, within=20),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(INT, vs=REF),
)
def p1553(c: Cast) -> None:
    if c.strike():
        c.damage("4d6", c.int_mod, dtype=DamageType.FIRE)
    else:
        c.half_damage("4d6", c.int_mod, dtype=DamageType.FIRE)


@power(
    "p259",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=20),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ZONE],
    attack=Attack(INT, vs=REF),
)
def p259(c: Cast) -> None:
    """No damage anywhere on the row: the hit line is the condition, and the
    ground it leaves behind keeps applying the same one.

    A creature already held is not held twice -- stacking a second save-ends
    copy on every step it finishes in the mud would need two saves to undo
    one effect, and the printed line reads as one condition, reapplied.
    """
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    c.zone(area, label="p259", until=When.ENCOUNTER, difficult=True)

    def caught(ev: MoveEnd) -> None:
        if ev.actor in c.in_squares(area) and not c.is_(Condition.IMMOBILIZED, on=ev.actor):
            c.immobilized(until=When.SAVE_ENDS, on=ev.actor)

    c.watch(MoveEnd, caught, until=When.ENCOUNTER, label="p259")


@power(
    "p67",
    level=5,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=20),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON, Keyword.ZONE],
    attack=Attack(INT, vs=FORT),
)
def p67(c: Cast) -> None:
    """"Heavily obscured" is line of sight, which is a zone's business and
    not a hazard's, so the cloud and its teeth are built in two steps.

    Walking the zone six squares with a move action has no expression -- a
    zone's squares are fixed where they were laid -- so the cloud stands.
    """
    if c.strike():
        c.damage("1d10", c.int_mod, dtype=DamageType.POISON)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    cloud = c.zone(area, label="p67", until=When.EONT, blocks_sight=True)
    c.burns(cloud, 5 + c.int_mod, DamageType.POISON)
