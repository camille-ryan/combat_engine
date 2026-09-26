"""Swordmage, level 9: the first seven dailies.

Three of these print an Effect the `Cast` surface can only say part of, and
each says so in its own docstring rather than quietly looking finished.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    FORT,
    INT,
    ONE_CREATURE,
    STANDARD,
    WILL,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    TurnStart,
    When,
    power,
)

from . import beside

ARCANE_WEAPON = [Keyword.ARCANE, Keyword.WEAPON]
ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p10433",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.FORCE],
    attack=Attack(INT, vs=FORT),
)
def p10433(c: Cast) -> None:
    """The standing move action is a teleport mode of 1. Its other half --
    spending that move action on the *target* instead of yourself -- has no
    method behind it, so only my own step is here."""
    if c.strike():
        c.damage(c.w(2), c.int_mod, dtype=DamageType.FORCE)
    else:
        c.half_damage(c.w(2), c.int_mod, dtype=DamageType.FORCE)
    c.mode("teleport", 1, until=When.ENCOUNTER, on=c.me)


@power(
    "p16014",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(INT, vs=WILL),
)
def p16014(c: Cast) -> None:
    """The printed Effect cuts the target out of its own side for the
    purpose of powers and auras. Nothing on the board can change whose side
    a creature counts as, so the hold is named and the damage is the row."""
    if not c.marked():
        return
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.FORCE)
        c.effect(f"{c.ref} alone", until=When.ENCOUNTER)
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.FORCE)
        c.effect(f"{c.ref} alone", until=When.EONT)


@power(
    "p3364",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE_WEAPON,
    attack=Attack(INT, vs=AC),
)
def p3364(c: Cast) -> None:
    """The light is a sight rule, not a combat effect, so it is a note."""
    if c.strike():
        c.damage(c.w(), c.int_mod)
        c.blinded(until=When.SAVE_ENDS)
        c.note(f"{c.ref}: the target sheds bright light and cannot hide in it")


@power(
    "p3365",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.TELEPORTATION, Keyword.RELIABLE],
    attack=Attack(INT, vs=AC),
)
def p3365(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.int_mod)
        c.teleport(5, who=c.target)


@power(
    "p3366",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.CONJURATION],
    attack=Attack(INT, vs=AC),
)
def p3366(c: Cast) -> None:
    """The duplicate is a conjuration that stands in the way. The rest of
    the printed block -- sharing my actions, swinging from its square -- is
    a second body on the board, which a conjuration is not."""
    if c.strike():
        c.damage(c.w(), c.int_mod)
    spot = beside(c, c.target) if c.target is not None else None
    if spot is not None:
        c.conjure(at=spot, label=c.ref, until=When.ENCOUNTER, sustain=None)


@power(
    "p3952",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*ARCANE_WEAPON, Keyword.HEALING],
    attack=Attack(INT, vs=AC),
)
def p3952(c: Cast) -> None:
    """Regeneration while bloodied is a heal at the top of each of my turns,
    checked then rather than now -- the printed line is about the state I am
    in when the turn comes round, not the state I am in as this lands."""
    me = c.me
    tick = 2 + c.con_mod
    if c.strike():
        c.damage(c.w(2), c.int_mod)

        def mend(ev: TurnStart) -> None:
            if ev.actor == me and not ev.ghost and c.bloodied(on=me):
                c.heal(tick, on=me)

        c.watch(TurnStart, mend, until=When.ENCOUNTER, on=me, label=c.ref)
    else:
        c.half_damage(c.w(2), c.int_mod)
        c.heal(tick, on=me)


@power(
    "p4803",
    level=9,
    cls="swordmage",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(INT, vs=AC),
)
def p4803(c: Cast) -> None:
    """The printed Effect is a marker that walks the board on its own,
    catching whoever stands on it and moving a square a round when nobody
    does. Nothing puts an unowned, self-moving token on the board, so the
    burn is the row and the wandering flame is not written."""
    if c.strike():
        c.damage("1d10", c.int_mod, dtype=DamageType.FIRE)
        c.ongoing(5, DamageType.FIRE)
    else:
        c.half_damage("1d10", c.int_mod, dtype=DamageType.FIRE)
