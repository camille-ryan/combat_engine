"""Psion, level 7. Each row buys its augment with `augment`; the clauses that
rewrite the header are named per row and recorded in `docs/blocked.json`."""

from __future__ import annotations

from combat_engine.content.powers.augment import augment
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    FORT,
    INT,
    NO_TARGET,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Augment,
    Cast,
    CloseBurst,
    DamageType,
    Keyword,
    Position,
    Ranged,
    TurnEnd,
    TurnStart,
    UpTo,
    When,
    power,
    spread,
)
from combat_engine.engine.events import ActionSpent

PSIONIC_IMPLEMENT = [Keyword.PSIONIC, Keyword.IMPLEMENT]
PSIONIC_FORCE = [Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.FORCE]
PSIONIC_PSYCHIC = [Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.PSYCHIC]

_REFLEX_ACTIONS = (
    ActionType.OPPORTUNITY,
    ActionType.IMMEDIATE_INTERRUPT,
    ActionType.IMMEDIATE_REACTION,
)


@power(
    "p11319",
    level=7,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_FORCE,
    attack=Attack(INT, vs=FORT),
)
def p11319(c: Cast) -> None:
    """Both augments splash force damage onto everything standing next to the
    target. Augment 2 dazes rather than trips: its Hit line is printed in full
    and the prone is not in it."""
    spent = augment(c)
    victim = c.target
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.FORCE)
        if spent == 2:
            c.dazed(until=When.EONT)
        else:
            c.prone()
        if spent:
            splash = 5 + c.wis_mod if spent == 2 else c.wis_mod
            for who in c.within(1, of=victim):
                if who != victim:
                    c.flat(splash, dtype=DamageType.FORCE, on=who)


@power(
    "p11320",
    level=7,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_FORCE,
    attack=Attack(INT, vs=FORT),
)
def p11320(c: Cast) -> None:
    """Augment 1 pulls by Wisdom *instead of* sliding; Augment 2 raises the
    dice and keeps the slide, at Wisdom squares."""
    spent = augment(c)
    if c.strike():
        c.damage("2d10" if spent == 2 else "1d10", c.int_mod, dtype=DamageType.FORCE)
        if spent == 1:
            c.pull(c.wis_mod)
        else:
            c.slide(c.wis_mod if spent == 2 else 1)


@power(
    "p13331",
    level=7,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.ACID,
        Keyword.CONJURATION,
    ],
)
def p13331(c: Cast) -> None:
    """"Any enemy that enters the servant's space" is dropped rather than
    written as a dead zone: `c.conjure` occupies its square, so nothing can
    ever be standing in it. The minor-action burst made through the servant is
    `p13331b`, which the importer now gives a ref of its own; Augment 2 is
    that block's dice, so it belongs to that row rather than this one.

    Augment 1 slows whoever starts its turn in or beside the servant. The
    servant's own square is in the ring, so "in or adjacent to" is one
    `spread` and needs no special case for a space nothing can stand in."""
    spent = augment(c, 1)
    servant = c.conjure(until=When.EONT, sustain=None, aura=1 if spent else 0)
    if not servant or not spent:
        return

    def creep(ev: TurnStart) -> None:
        pos = c.world.get(servant, Position)
        if pos is None or ev.actor == c.me:
            return
        if ev.actor in c.in_squares(spread({pos.square}, 1), side="enemy"):
            c.slowed(on=ev.actor, until=When.EONT)

    c.watch(TurnStart, creep, until=When.EONT, label=c.ref)


@power(
    "p13333",
    level=7,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.PSYCHIC,
        Keyword.FEAR,
    ],
    attack=Attack(INT, vs=WILL),
)
def p13333(c: Cast) -> None:
    """No dice unaugmented -- the printed Hit is the modifier alone, and only
    Augment 2 adds a die. Both augments add the saving-throw penalty."""
    spent = augment(c)
    if c.strike():
        c.damage("1d8" if spent == 2 else 0, c.int_mod, dtype=DamageType.PSYCHIC)
        c.penalty("attack", 2, until=When.EONT)
        for defence in (AC, FORT, REF, WILL):
            c.penalty(defence, 2, until=When.EONT)
        if spent:
            c.penalty("save", 2, until=When.EONT)


@power(
    "p13334",
    level=7,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=PSIONIC_FORCE,
    attack=Attack(INT, vs=FORT),
    augments=(
        Augment(1, target=EACH_ENEMY),
        Augment(2, reach=CloseBurst(2), target=EACH_ENEMY),
    ),
)
def p13334(c: Cast) -> None:
    """The defence bonus is inside the Hit line, so it goes up on the first
    creature struck; re-applying it on a second is harmless, since two power
    bonuses of the same size do not add.

    Both augments are the header. Augment 1 narrows the burst to enemies --
    a target line, and now declared as one rather than approximated by a
    body that leaves the allies it was already aimed at alone. Augment 2
    widens the burst to 2 as well, doubles the dice, shoves by Wisdom and
    holds the defences a turn longer."""
    spent = augment(c, 1, 2)
    if c.strike():
        c.damage("2d6" if spent == 2 else "1d6", c.int_mod, dtype=DamageType.FORCE)
        c.push(max(1, c.wis_mod) if spent == 2 else 1)
        held = When.EONT if spent == 2 else When.SONT
        for defence in (AC, FORT, REF, WILL):
            c.bonus(defence, 2, on=c.me, until=held, kind="power")


@power(
    "p13335",
    level=7,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.IMPLEMENT, Keyword.ZONE],
    attack=Attack(INT, vs=FORT),
)
def p13335(c: Cast) -> None:
    """Augment 1 narrows the zone's bite to enemies -- asked live rather than
    off a snapshot, since who is standing in it is the whole question.
    Augment 2 raises the dice and leaves the zone alone."""
    spent = augment(c)
    if c.first:
        zone = c.zone(c.area(), until=When.EONT)
        bite = c.cha_mod

        def lingered(ev: TurnEnd) -> None:
            if ev.actor not in c.world.zones.occupants(zone):
                return
            if spent == 1 and ev.actor not in c.enemies():
                return
            c.flat(bite, on=ev.actor)

        c.watch(TurnEnd, lingered, until=When.EONT, label=c.ref)
    if c.strike():
        c.damage("2d8" if spent == 2 else "1d8", c.int_mod)


@power(
    "p13444",
    level=7,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[
        Keyword.PSIONIC,
        Keyword.IMPLEMENT,
        Keyword.PSYCHIC,
        Keyword.FEAR,
    ],
    attack=Attack(INT, vs=WILL),
)
def p13444(c: Cast) -> None:
    """"The first time it uses an opportunity or immediate action" is
    `ActionSpent`, latched so only the first one costs it. Augment 1 adds the
    move action to that list -- the row prints no Augment 2."""
    watched = (
        (*_REFLEX_ACTIONS, ActionType.MOVE) if augment(c, 1) else _REFLEX_ACTIONS
    )
    victim = c.target
    if not c.strike():
        return
    c.damage("1d8", c.int_mod, dtype=DamageType.PSYCHIC)
    bite = c.cha_mod
    bitten = [False]

    def flinch(ev: ActionSpent) -> None:
        if bitten[0] or ev.actor != victim or ev.cost not in watched:
            return
        bitten[0] = True
        c.flat(bite, dtype=DamageType.PSYCHIC, on=victim)

    c.watch(ActionSpent, flinch, until=When.EONT, on=victim, label=c.ref)


@power(
    "p8239",
    level=7,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_FORCE,
    attack=Attack(INT, vs=FORT),
    augments=(
        Augment(1, target=UpTo(2)),
        Augment(2, target=UpTo(2)),
    ),
    dropped=("dsl.Target.adjacent_to_each_other",),
)
def p8239(c: Cast) -> None:
    """Both augments are target lines, and a target line is read before the
    body is called, so both are declared in the header. With the second
    target declared, Augment 2's stronger hit -- 2[W] and immobilised
    rather than slowed -- is writable below, which it was not on its own.

    The `dropped` clause is the *shape* of Augment 1's pair: "one creature
    or two creatures adjacent to each other". `Target` caps a count and
    filters a side and cannot say that the two chosen must stand together,
    so Augment 1 is offered as any two, which is Augment 2's line at a
    cheaper price."""
    spent = augment(c, 1, 2)
    if c.strike():
        c.damage("2d8" if spent == 2 else "1d8", c.int_mod, dtype=DamageType.FORCE)
        if spent == 2:
            c.immobilized(until=When.EONT)
        else:
            c.slowed(until=When.EONT)


@power(
    "p8240",
    level=7,
    cls="psion",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=PSIONIC_PSYCHIC,
    attack=Attack(INT, vs=WILL),
)
def p8240(c: Cast) -> None:
    """Augment 2 raises the dice and the vulnerability. Augment 1 is not
    offered: its second sentence strips the target's psychic resistance and
    nothing takes a resistance away, so writing the first sentence alone would
    be half a clause. The Special making the unaugmented form a ranged basic
    attack still has no header field."""
    spent = augment(c, 2)
    if c.strike():
        c.damage("2d8" if spent else "1d8", c.int_mod, dtype=DamageType.PSYCHIC)
        c.vulnerable(
            5 + c.cha_mod if spent else c.cha_mod, DamageType.PSYCHIC, until=When.EONT
        )
