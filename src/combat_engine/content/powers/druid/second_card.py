"""Druid: the second stat block, where the card prints two.

Nine of these are the attack printed beside a shape. The first block is a
minor action that assumes the form and the second is the one thing that
shape can do, carrying "Requirement: the p#### power must be active" --
so the gate is not "am I in beast form" but "am I in *this* one", which
`forms.in_form` asks. Every shape wears the same label, so the row that
assumed it leaves its own ref behind for that to find.

`p9634b` is the odd one out: the opportunity attack a hit opens, gated on
the hold its parent now leaves on the caster and aimed by the hold it
leaves on the creature it hit.

**Usage is the child's own printed column**, which is the whole reason the
importer gave these refs of their own -- except where the parent states a
rate in words, and none of this batch does: "once before the end of the
encounter" is the daily the card prints.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.cards import active
from combat_engine.engine import *

from .forms import beast_row, in_form

PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]

#: "One Large or smaller creature", printed on two of the shapes.
LARGE_OR_SMALLER = Target(count=1, max_size=Size.LARGE)


# -- p9634b: the opening its parent's hit leaves -----------------------------


def _opening_on_the_burned(world: World, me: int, ev: Any) -> bool:
    """The window is mine, and the creature provoking is the one I set alight.

    `OpportunityWindow.actor` is whoever may answer rather than whoever
    moved, so the row has to check both ends: that the offer is to me, and
    that the provoker carries the hold `p9634` left on it.
    """
    if getattr(ev, "actor", None) != me:
        return False
    foe = getattr(ev, "provoker", None)
    return foe is not None and any(
        e.label == "p9634" and e.source == me for e in world.effects.of(foe)
    )


@power(
    "p9634b",
    level=1,
    cls="druid",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.RANGED, Keyword.FIRE],
    attack=Attack(WIS, vs=REF),
    requires=active("p9634"),
    requires_text="the p9634 power must be activated",
    trigger="the target takes any action that can provoke opportunity attacks",
    on=Trigger(
        OpportunityWindow,
        _opening_on_the_burned,
        "the target takes an action that provokes opportunity attacks",
    ),
)
def p9634b(c: Cast) -> None:
    """Aimed off the window rather than by the dispatcher: an enemy-side row
    is pointed at the event's actor, and on an `OpportunityWindow` that is
    the responder."""
    foe = getattr(c.trigger, "provoker", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.damage("1d8", c.wis_mod, dtype=DamageType.FIRE, on=foe)


# -- the shapes --------------------------------------------------------------


@power(
    "p10838b",
    level=1,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=LARGE_OR_SMALLER,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.BEAST_FORM],
    attack=Attack(WIS, vs=FORT),
    requires=in_form("p10838"),
    requires_text="the p10838 power must be active",
)
def p10838b(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.wis_mod)
        c.push(3)
        c.prone()


@power(
    "p10840b",
    level=1,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.BEAST_FORM],
    attack=Attack(WIS, vs=FORT),
    requires=in_form("p10840"),
    requires_text="the p10840 power must be active",
)
def p10840b(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.wis_mod)
        c.grab()


@power(
    "p10842b",
    level=1,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.BEAST_FORM],
    attack=Attack(WIS, vs=FORT),
    requires=in_form("p10842"),
    requires_text="the p10842 power must be active",
)
def p10842b(c: Cast) -> None:
    """The Special line -- this may be swung in place of a melee basic attack
    at the end of a charge -- has no header field to declare it, so what a
    row *is used as* is the one clause of this card left unsaid."""
    if c.strike():
        c.damage("2d10", c.wis_mod)
        c.slide(1)
        c.mark(until=When.EONT)


@power(
    "p10844b",
    level=5,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.BEAST_FORM],
    attack=Attack(WIS, vs=REF),
    requires=in_form("p10844"),
    requires_text="the p10844 power must be active",
)
def p10844b(c: Cast) -> None:
    """The rider is asked on `MoveEnd`: "into a square that is not adjacent to
    you" is only true once the step has landed, and `MoveStart` would read
    the square it came from. Forced movement emits neither, which is the
    printed distinction between moving and being moved."""
    if not c.strike():
        return
    c.damage("2d10", c.wis_mod)
    victim = c.target
    if victim is None:
        return
    c.slowed(until=When.EONT)

    def stepped(ev: MoveEnd) -> None:
        if ev.actor != victim or c.turn_of() != victim:
            return
        if ev.kind_ not in ("walk", "shift", "charge"):
            return
        if not c.is_(Condition.SLOWED, on=victim) or c.adjacent(victim):
            return
        c.flat(c.con_mod, on=victim)

    c.watch(MoveEnd, stepped, until=When.EONT, on=c.me, label=c.ref)


@power(
    "p10846b",
    level=5,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.BEAST_FORM],
    attack=Attack(WIS, vs=REF),
    requires=in_form("p10846"),
    requires_text="the p10846 power must be active",
)
def p10846b(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.wis_mod)
        c.immobilized(until=When.SAVE_ENDS)


def _beast_melee_hit(world: World, me: int, ev: Any) -> bool:
    """"You hit an enemy with a beast form melee attack."

    Beast Form is not a `Keyword`, so what makes a row one of them is its
    gate -- the same reading `forms.beast_row` takes for the damage bonuses.
    """
    if ev.attacker != me or ev.target == me:
        return False
    p = get(ev.power)
    return (
        p is not None
        and p.reach is not None
        and p.reach.kind == "melee"
        and beast_row({"power": ev.power})
    )


@power(
    "p10848b",
    level=5,
    cls="druid",
    usage=DAILY,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.BEAST_FORM],
    attack=Attack(WIS, vs=FORT),
    requires=in_form("p10848"),
    requires_text="the p10848 power must be active",
    trigger="you hit an enemy with a beast form melee attack",
    on=Trigger(Hit, _beast_melee_hit, "you hit an enemy with a beast form melee attack"),
)
def p10848b(c: Cast) -> None:
    """"The target of your triggering attack" is read off the event: the
    dispatcher aims an enemy-side row at whoever caused the event, and the
    cause of a `Hit` of mine is me."""
    victim = getattr(c.trigger, "target", None) or c.target
    if victim is None:
        return
    if c.strike(on=victim):
        c.damage("2d8", c.wis_mod, on=victim)
        c.prone(on=victim)


@power(
    "p10850b",
    level=9,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.BEAST_FORM],
    attack=Attack(WIS, vs=REF),
    requires=in_form("p10850"),
    requires_text="the p10850 power must be active",
)
def p10850b(c: Cast) -> None:
    """"At any point during this movement" cannot be placed -- the shift is
    one jump and the target was chosen before the body ran -- so the swing is
    taken at the start of the move, which is the point that keeps it in
    reach. The shift is an Effect and happens either way."""
    if c.strike():
        c.damage("2d10", c.wis_mod)
    c.shift(max(1, c.speed_of() // 2))


@power(
    "p10852b",
    level=9,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.BEAST_FORM],
    attack=Attack(WIS, vs=FORT),
    requires=in_form("p10852"),
    requires_text="the p10852 power must be active",
)
def p10852b(c: Cast) -> None:
    """The printed Requirement names this card's own ref rather than its
    parent's, which is a misprint: the shape is `p10852` and it is the shape
    that has to be up.

    The flight comes first, as printed, and the exemption from opportunity
    attacks is ended when the flight is rather than left to run to the end of
    the turn."""
    quiet = c.no_provoke(on=c.me, until=When.EOT)
    c.move(max(1, c.speed_of() // 2), at="fly")
    if quiet is not None:
        c.world.effects.end(quiet, "the flight ended")
    if c.strike():
        c.damage("2d10", c.wis_mod)
        c.shift(1)


@power(
    "p10854b",
    level=9,
    cls="druid",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=LARGE_OR_SMALLER,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.POISON, Keyword.BEAST_FORM],
    attack=Attack(WIS, vs=FORT),
    requires=in_form("p10854"),
    requires_text="the p10854 power must be active",
)
def p10854b(c: Cast) -> None:
    """"Save ends both" is two saves here: one hold per thing saved against
    is what the effect table keeps."""
    if c.strike():
        c.damage("1d10", c.wis_mod)
        c.ongoing(5, DamageType.POISON, until=When.SAVE_ENDS)
        c.slowed(until=When.SAVE_ENDS)
