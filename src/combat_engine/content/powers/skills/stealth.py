"""Skill powers for `cls="stealth"`: hiding, and the cover that allows it.

Seven rows, levels 2/6/10. What they have in common is the pair of readers
every one of them leans on -- `query.sheltered_from` for *"while you have
cover or concealment against it"*, and `c.hide(check=True)` for the printed
Stealth check that turns that shelter into being unseen. The two are the
whole of this skill's vocabulary and both already existed.

Every printed Trigger is declared with `on=`; every printed Requirement is a
`requires=` predicate rather than an early return, so a row the board cannot
set up is **refused** instead of firing and doing nothing.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    INTERRUPT,
    MINOR,
    MOVE,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    SELF,
    AttackDeclared,
    Cast,
    CloseBurst,
    Condition,
    Cover,
    Relation,
    Trigger,
    When,
    both,
    by_melee,
    by_ranged,
    power,
    targets_me,
)
from combat_engine.engine.ecs import World
from combat_engine.engine.events import Miss, Moved
from combat_engine.engine.query import (
    concealment_of,
    enemies,
    sheltered_from,
    squares,
)
from combat_engine.engine.types import Light


def _unlit(world: World, me: int) -> bool:
    """`c.unlit` asked of a `requires=` gate, which gets no `Cast`.

    Same read as the verb -- any square of the footprint below bright light
    -- written out here because a Requirement is checked by `can_branch`
    with `(world, eid)` in hand and nothing else.
    """
    from combat_engine.engine.query import light_level

    return any(
        light_level(world, sq) is not Light.BRIGHT for sq in squares(world, me)
    )


def _sheltered_from_somebody(world: World, me: int) -> bool:
    """"You must have cover or concealment" -- from anybody at all."""
    return any(sheltered_from(world, me, foe) for foe in enemies(world, me))


def _marked_and_concealed(world: World, me: int) -> bool:
    """Marked, and concealed from whoever did it.

    Concealment is not a pairing in this engine -- `query.concealment_of` is
    a property of the creature alone, and `sheltered_from`'s own docstring
    says why -- so "from the creature that marked you" narrows nothing here
    and the mark is the half that does.
    """
    if concealment_of(world, me) is Cover.NONE:
        return False
    return bool(world.relations.sources(Relation.MARKED_BY, me))


def _missed_me_from_shelter(world: World, me: int, ev: Any) -> bool:
    """An enemy's melee or ranged swing missing me while I am sheltered.

    `by_melee` and `by_ranged` read the reach off the row behind the event,
    so both answer on a `Miss`; the shelter is asked now rather than
    snapshotted, because the window the card leaves open is this moment.
    """
    foe = getattr(ev, "attacker", None)
    if foe is None or getattr(ev, "target", None) != me:
        return False
    if not (by_melee(world, me, ev) or by_ranged(world, me, ev)):
        return False
    return sheltered_from(world, me, foe)


def _restricted_to(c: Cast, reach: int, test: Callable[[int], bool]) -> int | None:
    """The target the printed line allows, where `Target` cannot say it.

    `Target` filters on side, count and size and not on what a creature can
    see or stand behind, so the chooser may hand this row somebody its own
    target line forbids. Re-aimed rather than thrown away, which is the
    settled answer across the tree.
    """
    foe = c.target
    if foe is not None and test(foe) and c.distance(foe) <= reach:
        return foe
    return next(
        (f for f in c.enemies() if test(f) and c.distance(f) <= reach), None
    )


def _shields_me(c: Cast, shooter: int, body: int) -> bool:
    """Is `body` standing in the way of `shooter`'s shot at the caster?

    Asked the way `query.cover_granters` asks it: trace with that one
    creature as the only blocker and compare against the bare board.
    `Grid.cover` unions the terrain in on every call, so without the
    subtraction a single wall would make every bystander a shield -- which
    is the fault #651 found in the reader this copies.
    """
    mine = squares(c.world, c.me)
    theirs = squares(c.world, shooter)
    its = squares(c.world, body)
    if not (mine and theirs and its):
        return False

    def traced(blockers: set) -> Cover:
        best = Cover.SUPERIOR
        for src in theirs:
            for dst in mine:
                best = min(best, c.world.grid.cover(src, dst, blockers=blockers))
        return best

    return traced(set(its)) > traced(set())


@power(
    "p16491",
    level=2,
    cls="stealth",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    todo=("c.unseen_by(sense=)",),
)
def p16491(c: Cast) -> None:
    """All three of the named faculties are on the board and none of them is
    a *bypass* for this row to take away.

    `c.darkvision`, `c.blindsight` and `c.tremorsense` grant them and
    `query.has_sense` asks after them, but they only answer the **light**
    question through `query.sees_in`: `query.sees_through` consults
    see-invisible and truesight and nothing else, so a creature with any of
    the three already needs line of sight exactly as this card demands.
    There is no model of detection-without-sight to narrow, which is
    `i2413x1`'s gap verbatim and why this waits on the same symbol."""


@power(
    "p9338",
    level=2,
    cls="stealth",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_marked_and_concealed,
    requires_text="you must be marked, and concealed from whoever marked you",
)
def p9338(c: Cast) -> None:
    """`c.cure` takes the condition off and leaves the effect that carried
    it standing, which is the printed operation: the mark ends, and nothing
    says the rest of whatever laid it does."""
    c.cure(Condition.MARKED, on=c.me)


@power(
    "p11593",
    level=6,
    cls="stealth",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_sheltered_from_somebody,
    requires_text="you must have cover or concealment",
)
def p11593(c: Cast) -> None:
    """"You make a Stealth check" is the hide *action*, bought here for a
    minor instead of being folded into a move -- so `check=True`, which is
    the one call that rolls it and charges the movement penalty."""
    c.hide(check=True)


@power(
    "p9339",
    level=6,
    cls="stealth",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy misses you with a melee or a ranged attack while you"
    " have cover or concealment from it",
    on=Trigger(Miss, _missed_me_from_shelter, "an enemy misses you"),
)
def p9339(c: Cast) -> None:
    c.shift(1)


@power(
    "p11594",
    level=10,
    cls="stealth",
    usage=AT_WILL,
    action=MOVE,
    reach=CloseBurst(20),
    target=ONE_CREATURE,
)
def p11594(c: Cast) -> None:
    """`c.arm_trigger` rather than `c.watch`, because the printed clause is
    an immediate reaction and that is what makes it once a round and not
    while dazed -- a declared trigger is header data and this row's header
    belongs to the move action that arms it.

    The move is aimed with `toward=`: the destinations otherwise go to the
    decider unordered, and a power for keeping up with somebody that walks
    the other way is the #381 shape. It is a **ranking**, not a
    compulsion -- a real decider still sees every square the card allows --
    so the free move is nudged toward following rather than narrowed to it.
    Being left with cover is then asked at the end of the move, where the
    card asks it. Driven: the armed reaction fires on the target's move and
    the hide lands."""
    victim = _restricted_to(
        c, 20, lambda f: c.can_see(f) and sheltered_from(c.world, c.me, f)
    )
    if victim is None:
        return
    spent = {"once": False}

    def shadow(ev: Moved) -> None:
        if spent["once"]:
            return
        spent["once"] = True
        c.move(c.speed_of(), toward=victim)
        if sheltered_from(c.world, c.me, victim):
            c.hide(from_=victim, check=True)

    c.arm_trigger(
        Moved,
        shadow,
        when=lambda ev: getattr(ev, "actor", None) == victim,
        until=When.SONT,
        on=c.me,
    )


@power(
    "p16484",
    level=10,
    cls="stealth",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_unlit,
    requires_text="you must be in dim light or darkness",
)
def p16484(c: Cast) -> None:
    """Two of the three endings cost nothing to write.

    `until=When.SONT` is the clock, and *"until you attack"* is already the
    engine's behaviour -- `resolve.attack` clears `Relation.HIDDEN_FROM` for
    whoever swung, which is the relation `c.invisible` holds. Only entering
    bright light needs a watch, and it is the same read as the Requirement
    taken again after each step."""
    veil = c.invisible(on=c.me, until=When.SONT)

    def stepped(ev: Moved) -> None:
        if getattr(ev, "actor", None) == c.me and not c.unlit():
            c.end_effect(veil, why="walked into bright light")

    c.watch(Moved, stepped, until=When.SONT, on=c.me)


@power(
    "p9340",
    level=10,
    cls="stealth",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger="an enemy makes a ranged attack roll against you",
    on=Trigger(
        AttackDeclared,
        both(targets_me, by_ranged),
        "an enemy makes a ranged attack against you",
    ),
    dropped=("c.reroll_attack(against=)",),
)
def p9340(c: Cast) -> None:
    """Declared on `AttackDeclared`, which is where an interrupt lives: the
    cover has to be standing when `resolve.attack` traces it, and by
    `AttackRolled` the modifiers have already been summed.

    `cover_between` counts only the **target's own side** as bodies, so an
    enemy in the line never shelters anybody -- which is exactly what this
    card changes. It cannot be said by extending that trace, so the cover is
    carried instead: `c.cover` lays the modifier `query._carried_cover`
    reads, gated on this shooter, and handed back in the `AttackDeclared`
    AFTER window once the whole attack is past.

    Dropped: the reroll against one of the shields. `c.redirect` moves an
    attack and `c.reroll_attack` rolls it again, and neither does the
    printed thing -- rolling a *fresh* attack against a creature that was
    never targeted, after the first one has already been announced a miss.
    """
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    shields = [
        other
        for other in c.enemies()
        if other != foe and c.adjacent(other) and _shields_me(c, foe, other)
    ]
    if not shields:
        return
    carried = c.cover(
        on=c.me,
        until=When.EOT,
        when=lambda ctx: ctx.get("attacker") == foe,
    )

    def past(ev: AttackDeclared) -> None:
        c.end_effect(carried, why="the triggering attack is resolved")

    c.watch(AttackDeclared, past, until=When.EOT, once=True, on=c.me)
