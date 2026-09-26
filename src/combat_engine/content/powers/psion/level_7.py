"""Psion, level 7. Augment 0 throughout; dropped augments are named per row."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
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
    Cast,
    CloseBurst,
    DamageType,
    Keyword,
    Ranged,
    TurnEnd,
    When,
    power,
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
    """Augment 1 (splash onto adjacent creatures) and Augment 2 (a daze and a
    bigger splash) are dropped."""
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.FORCE)
        c.prone()


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
    """Augment 1 (a pull instead) and Augment 2 (bigger dice, longer slide)
    are dropped."""
    if c.strike():
        c.damage("1d10", c.int_mod, dtype=DamageType.FORCE)
        c.slide(1)


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
    printed as a second block under this same id and so has no ref of its own.
    Augment 1 (a slow around it) is dropped."""
    c.conjure(until=When.EONT, sustain=None)


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
    """No dice at Augment 0 -- the printed Hit is the modifier alone. Augment 1
    (a saving-throw penalty too) and Augment 2 are dropped."""
    if c.strike():
        c.damage(0, c.int_mod, dtype=DamageType.PSYCHIC)
        c.penalty("attack", 2, until=When.EONT)
        for defence in (AC, FORT, REF, WILL):
            c.penalty(defence, 2, until=When.EONT)


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
)
def p13334(c: Cast) -> None:
    """The defence bonus is inside the Hit line, so it goes up on the first
    creature struck; re-applying it on a second is harmless, since two power
    bonuses of the same size do not add. Augment 1 (enemies only) and
    Augment 2 are dropped."""
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.FORCE)
        c.push(1)
        for defence in (AC, FORT, REF, WILL):
            c.bonus(defence, 2, on=c.me, until=When.SONT, kind="power")


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
    """Augment 1 (enemies only) and Augment 2 (bigger dice) are dropped."""
    if c.first:
        zone = c.zone(c.area(), until=When.EONT)
        bite = c.cha_mod

        def lingered(ev: TurnEnd) -> None:
            if ev.actor in c.world.zones.occupants(zone):
                c.flat(bite, on=ev.actor)

        c.watch(TurnEnd, lingered, until=When.EONT, label=c.ref)
    if c.strike():
        c.damage("1d8", c.int_mod)


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
    `ActionSpent`, latched so only the first one costs it. Augment 1 (move
    actions too) is dropped."""
    victim = c.target
    if not c.strike():
        return
    c.damage("1d8", c.int_mod, dtype=DamageType.PSYCHIC)
    bite = c.cha_mod
    spent = [False]

    def flinch(ev: ActionSpent) -> None:
        if spent[0] or ev.actor != victim or ev.cost not in _REFLEX_ACTIONS:
            return
        spent[0] = True
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
)
def p8239(c: Cast) -> None:
    """Augment 1 (a second, adjacent target) and Augment 2 are dropped."""
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.FORCE)
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
    """Augments 1 and 2 (a flat 5, and stripping psychic resistance) are
    dropped, as is the Special making the unaugmented form a ranged basic
    attack -- there is no header field for that."""
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.PSYCHIC)
        c.vulnerable(
            c.cha_mod, DamageType.PSYCHIC, until=When.EONT
        )
