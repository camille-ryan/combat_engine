"""Battlemind, level 3."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    CON,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    DamageApplied,
    DamageType,
    Keyword,
    Melee,
    When,
    power,
)
from combat_engine.engine.events import AdjacencyGained

from . import PSIONIC_WEAPON, shift_beside, teleport_beside


@power(
    "p11163",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p11163(c: Cast) -> None:
    """Base form. Augment 1 (adjacency no longer ends it) and Augment 2 (every
    ally, not one) are dropped: no power points. "Until the target is adjacent
    to him" is the `AdjacencyGained` half."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage(c.w(), c.con_mod)
    mates = [a for a in c.within(5, side="ally") if a != c.me]
    if not mates:
        return
    mate = c.choose(mates, "who goes unseen")
    if mate is None:
        return
    hidden = c.invisible(to=victim, on=mate, until=When.EONT)

    def closed(ev: AdjacencyGained) -> None:
        if hidden is not None and {ev.actor, ev.other} == {mate, victim}:
            c.world.effects.end(hidden, "the target is adjacent")

    c.watch(AdjacencyGained, closed, until=When.EONT, on=c.me)


@power(
    "p11164",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=REF),
)
def p11164(c: Cast) -> None:
    """Base form, which is the bare attack. Both augments turn on defeating
    insubstantiality and both are dropped: no power points."""
    if c.strike():
        c.damage(c.w(), c.con_mod)


@power(
    "p12422",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.FORCE],
    attack=Attack(CON, vs=AC),
)
def p12422(c: Cast) -> None:
    """Base form. Both augments only lengthen the reach, and both are dropped.
    The slide is anchored on the caster's square, which is what "to a square
    adjacent to you" means."""
    if c.strike():
        c.damage(c.w(), c.con_mod, dtype=DamageType.FORCE)
        c.slide(1, anchor=c.here)


@power(
    "p13039",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.TELEPORTATION],
    attack=Attack(CON, vs=AC),
)
def p13039(c: Cast) -> None:
    """Base form. Augment 1 (+1 reach) and Augment 2 (2[W], and a second
    recall when it runs) are dropped: no power points."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(), c.con_mod)
        teleport_beside(c, victim, c.me)


@power(
    "p13040",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.TELEPORTATION],
    attack=Attack(CON, vs=AC),
)
def p13040(c: Cast) -> None:
    """Base form. Augment 1 (Constitution added) and Augment 2 (2[W], and a
    blink on any damage at all) are dropped: no power points."""
    if not c.strike():
        return
    c.damage(c.w())

    def blink(ev: DamageApplied) -> None:
        if ev.target != c.me or ev.source is None:
            return
        if ev.source in c.enemies() and not c.adjacent(ev.source):
            c.teleport(2)

    c.watch(DamageApplied, blink, until=When.SONT, on=c.me)


@power(
    "p13041",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=WILL),
)
def p13041(c: Cast) -> None:
    """Base form. Augment 1 and 2 (reach 5, a longer pull, prone) are dropped.
    "The target can move only to squares adjacent to you" is dropped too:
    nothing on `Cast` constrains where a creature may walk."""
    if c.strike():
        c.damage(0, c.con_mod)
        c.pull(1)


@power(
    "p13042",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p13042(c: Cast) -> None:
    """Base form. Augment 1 (shift your speed) and Augment 2 (a free charge)
    are dropped: no power points."""
    victim = c.target
    if c.strike():
        c.damage(c.w(), c.con_mod)
    if not c.last:
        return
    others = [e for e in c.enemies() if e != victim]
    if others:
        shift_beside(c, 2, min(others, key=c.distance))


@power(
    "p13466",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p13466(c: Cast) -> None:
    """Base form; this row prints no Augment 1, only an Augment 2 (2[W], and
    the concealment extended to adjacent allies), which is dropped. The
    concealment itself is dropped too -- nothing on `Cast` grants it."""
    if c.strike():
        c.damage(c.w(), c.con_mod)


@power(
    "p2626",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PSIONIC_WEAPON,
    attack=Attack(CON, vs=AC),
)
def p2626(c: Cast) -> None:
    """Base form. Augment 1 (a Charisma penalty to its melee and close
    attacks) and Augment 2 (immobilised) are dropped: no power points."""
    if c.strike():
        c.damage(c.w(), c.con_mod)
        c.grants_advantage(until=When.EONT, to="allies")


@power(
    "p2627",
    level=3,
    cls="battlemind",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSIONIC, Keyword.WEAPON, Keyword.FEAR],
    attack=Attack(CON, vs=AC),
)
def p2627(c: Cast) -> None:
    """Base form. Augment 1 (a Charisma push, and every later shove longer by
    a square) and Augment 2 (the neighbours slid too) are dropped."""
    if c.strike():
        c.damage(c.w(), c.con_mod)
        c.push(2)
