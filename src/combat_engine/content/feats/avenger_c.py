"""Avenger feats, the third batch: the godsworn boons and a longsword.

Nine of the sixteen are one family. Each prints the same two sentences
-- a Religion bonus and a rider on any critical hit -- and differs only
in what the critical buys. They are hand-written rather than minted,
because the riders are nine different verbs and a table of them would
hide that.

"You can benefit from only one godsworn boon as a result of any given
critical hit" is a budget across *different feats*, which no header
field spans; each row hands out exactly one thing per firing, which is
the half of the sentence a row can say about itself. `avenger_b.f2738`
makes the same note.

"Your Dexterity or Intelligence modifier" is the avenger's choice of
secondary ability and the character has both, so the rows take the
larger: an option a character would never decline is not a decision.

`oath.sworn` and `oath.oath_target` are imported, as in `avenger_b` --
the oath is a labelled hold and its test is not re-derived here.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.chargen import LONGSWORD
from combat_engine.content.powers.avenger.oath import oath_target, sworn
from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Cast,
    Condition,
    DamageType,
    Dropped,
    Hit,
    Miss,
    Trigger,
    When,
    power,
)
from combat_engine.engine.components import Position
from combat_engine.engine.grid import distance, neighbours
from combat_engine.engine.query import allies

#: Every defence, for the boons that print "all defenses".
DEFENCES = (AC, FORT, REF, WILL)
#: The associated-power rows, keyed by the feat that lists them.
_ASSOCIATED = {
    "f2925": ("p5332", "p839", "p835"),
    "f2927": ("p5333", "p6834"),
    "f2928": ("p1725", "p7380"),
    "f2929": ("p6834", "p3423"),
}


def _boon(c: Cast) -> int:
    """"Your Dexterity or Intelligence modifier", chosen the only way a
    character with both would choose it."""
    return max(c.dex_mod, c.int_mod)


def _religion(c: Cast) -> None:
    c.bonus("skill:religion", 2, on=c.me, until=When.ENCOUNTER, kind="feat")


def _on_crit(c: Cast, fn: Callable[[Any], None]) -> None:
    """Arm the boon half of a row that also carries a standing bonus.

    The nine rows below print both a skill bonus and a rider on any
    critical hit, and a row declares one or the other: a modifier laid
    in the body of a declared trigger is laid only when the trigger
    fires, which for a bonus that should be up all fight is never.
    """
    me = c.me

    def boon(ev: Hit) -> None:
        if ev.attacker == me and ev.critical:
            fn(ev)

    c.watch(Hit, boon, until=When.ENCOUNTER, on=me, label=f"{c.ref} boon")


def _longsword(c: Cast, ev: Any) -> bool:
    """One of this feat's own rows, hit, with the printed base weapon."""
    if ev.attacker != c.me or ev.power not in _ASSOCIATED[c.ref]:
        return False
    arm = c.struck_with(ev)
    return arm is not None and arm.ref == LONGSWORD.ref


def _toward(c: Cast, foe: int, reach: int) -> None:
    """Shift up to `reach`, ending "closer to or adjacent to" a creature.

    Both halves of the printed constraint: an avenger already standing
    beside the sworn enemy has no square that is *nearer*, and refusing
    the shift there would make the row inert exactly where it is meant
    to be used.
    """
    here = c.world.get(foe, Position)
    options = c.world.reachable_squares(c.me, reach)
    if here is None or not options:
        return
    now = distance(c.here, here.square)
    ok = [
        sq
        for sq in options
        if distance(sq, here.square) < now or distance(sq, here.square) <= 1
    ]
    if ok:
        c.shift(reach, to=min(ok, key=lambda sq: distance(sq, here.square)))


def _defences(c: Cast, who: int) -> None:
    """"A +2 bonus to all defenses" prints no type word, so it is
    untyped and stacks."""
    for defence in DEFENCES:
        c.bonus(defence, 2, on=who, until=When.EONT)


# -- the godsworn boons ----------------------------------------------------


@power("f2740", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2740(c: Cast) -> None:
    """The push names a distance and not a direction, so the decider
    picks the line."""
    _religion(c)
    _on_crit(c, lambda ev: c.push(_boon(c), on=ev.target))


@power("f2741", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2741(c: Cast) -> None:
    _religion(c)
    _on_crit(c, lambda ev: _defences(c, c.me))


@power("f2742", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2742(c: Cast) -> None:
    """The same untyped +2, handed to one visible ally instead. The set
    is read when the blow lands rather than when the feat is armed,
    because both the avenger and the party have moved by then."""
    _religion(c)
    me = c.me

    def boon(ev: Any) -> None:
        near = [a for a in allies(c.world, me) if a != me and c.can_see(a)]
        if near:
            _defences(c, near[0])

    _on_crit(c, boon)


@power("f2743", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2743(c: Cast) -> None:
    """"Necrotic or cold" is a choice made when the feat is taken and
    nothing records it, so the first of the two is dealt. `c.flat`
    rather than `c.damage`: a critical maxes dice, and this is a flat
    number rather than another die to max."""
    _religion(c)
    _on_crit(
        c, lambda ev: c.flat(_boon(c), dtype=DamageType.NECROTIC, on=ev.target)
    )


@power("f2744", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2744(c: Cast) -> None:
    _religion(c)
    _on_crit(c, lambda ev: c.conceal(on=c.me, until=When.EONT))


@power("f2745", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2745(c: Cast) -> None:
    _religion(c)
    _on_crit(
        c, lambda ev: c.flat(_boon(c), dtype=DamageType.PSYCHIC, on=ev.target)
    )


@power("f2746", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2746(c: Cast) -> None:
    _religion(c)
    _on_crit(
        c, lambda ev: c.flat(_boon(c), dtype=DamageType.RADIANT, on=ev.target)
    )


@power("f2747", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2747(c: Cast) -> None:
    """"Any unoccupied square adjacent to your oath target" names the
    destination, so the square is chosen here rather than left to the
    decider -- `c.teleport(to=)` exists for exactly that. Five squares
    is the limit and the nearest qualifying square is taken."""
    _religion(c)

    def boon(ev: Any) -> None:
        foe = oath_target(c)
        here = None if foe is None else c.world.get(foe, Position)
        if here is None:
            return
        spots = [
            sq
            for sq in neighbours(here.square)
            if c.world.grid.passable(sq)
            and c.world.grid.occupant(sq) is None
            and distance(sq, c.here) <= 5
        ]
        if spots:
            c.teleport(5, to=min(spots, key=lambda sq: distance(sq, c.here)))

    _on_crit(c, boon)


@power("f2748", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2748(c: Cast) -> None:
    _religion(c)
    _on_crit(c, lambda ev: c.shift(_boon(c)))


# -- the oath, read rather than re-derived ---------------------------------


def _oath_missed_me(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.target == me and sworn(world, me, ev.attacker)


@power("f2754", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="your oath target misses you",
       on=Trigger(Miss, _oath_missed_me, "your oath target misses you"))
def f2754(c: Cast) -> None:
    """"Closer to or adjacent to the target" is a constraint on where
    the shift ends, so the square is picked here and the shift is
    declined when no reachable square is nearer than this one."""
    _toward(c, c.trigger.attacker, 1)


def _dropped_my_oath(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.source == me and sworn(world, me, ev.actor)


@power("f2758", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you drop your oath target",
       on=Trigger(Dropped, _dropped_my_oath, "you drop your oath target"))
def f2758(c: Cast) -> None:
    """`Dropped` carries `actor` and `source` and no target, so the
    creature that fell is `actor`. The allies are those beside *it* at
    the moment it goes down, which is what "adjacent to the target"
    fixes -- the body cannot wait, because the corpse is about to be
    taken off the board."""
    me, fallen = c.me, c.trigger.actor
    c.bonus("save", 2, on=me, until=When.EONT)
    for mate in allies(c.world, me):
        if mate != me and c.adjacent_to(mate, fallen):
            c.bonus("save", 2, on=mate, until=When.EONT)


@power("f2911", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.no_provoke(when=)",))
def f2911(c: Cast) -> None:
    """A charge at the sworn enemy draws no openings on the way in.
    `c.no_provoke` is a standing veto on the opportunity window with no
    gated form, so "during this charge" cannot be said and a bare call
    would cover every step the avenger takes all fight. Same symbol
    f1119 names."""


# -- the longsword family --------------------------------------------------


@power("f2925", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2925(c: Cast) -> None:
    """"Even if you are restrained or immobilized" is `ignore_condition`
    rather than `c.cure`: the condition is still standing afterwards,
    which is the difference between walking out of a hold and breaking
    it. The once-a-turn latch is a round stamp, as `c.on_attack` keeps
    for `once_per_round`."""
    me, seen = c.me, {}

    def on_hit(ev: Hit) -> None:
        if not _longsword(c, ev) or seen.get(0) == c.world.round:
            return
        seen[0] = c.world.round
        c.ignore_condition(
            Condition.RESTRAINED, Condition.IMMOBILIZED, on=me, until=When.EOT
        )
        c.move(2, who=me)

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me, label=f"{c.ref} riders")
    c.bonus("skill:athletics", 2, on=me, until=When.ENCOUNTER, kind="feat")


@power("f2927", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2927(c: Cast) -> None:
    """A climb speed is a movement mode, which `c.mode` grants for a
    duration -- `Movement.modes` on its own says what a creature could
    always do."""
    me = c.me

    def on_hit(ev: Hit) -> None:
        if _longsword(c, ev):
            c.mode("climb", max(c.speed_of(me) - 2, 0), on=me, until=When.EOT)

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me, label=f"{c.ref} riders")
    c.bonus("skill:athletics", 2, on=me, until=When.ENCOUNTER, kind="feat")


@power("f2928", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("Moved.squares", "c.moved_this_turn()"))
def f2928(c: Cast) -> None:
    """The five lands; the ten is dropped.

    "If you ended your turn more than 2 squares from where you started"
    is a distance travelled over a whole turn, and nothing keeps it:
    `Moved` carries `from_` and `to` for one step and no running total,
    so a row adding them up would miss a teleport, a push and a shift
    each resetting the pair.
    """
    me, seen = c.me, {}

    def on_hit(ev: Hit) -> None:
        if not _longsword(c, ev) or seen.get(0) == c.world.round:
            return
        seen[0] = c.world.round
        c.temp_hp(5, on=me)

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me, label=f"{c.ref} riders")
    c.bonus("skill:endurance", 2, on=me, until=When.ENCOUNTER, kind="feat")


@power("f2929", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.ignores_difficult(while_shifting=)",))
def f2929(c: Cast) -> None:
    """The terrain is ignored; the narrowing to shifts is dropped.

    `c.ignores_difficult` is a property of the creature and takes a
    *kind* of ground, not a way of moving, so written as printed the
    avenger also walks over the rough for free. That is wider than the
    card and it is named here rather than left in prose.
    """
    me = c.me

    def on_hit(ev: Hit) -> None:
        if _longsword(c, ev):
            c.ignores_difficult(on=me, until=When.EOT)

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me, label=f"{c.ref} riders")
    c.bonus("skill:acrobatics", 2, on=me, until=When.ENCOUNTER, kind="feat")
