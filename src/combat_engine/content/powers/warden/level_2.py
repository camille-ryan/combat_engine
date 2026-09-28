"""Warden, level 2: the utilities.

Two of them turn on class features the chassis carries no ref for. The
saving-throw one can still be declared -- a successful save is an event
with a field saying so -- and the conjuration's is written as "whenever
this warden marks anybody", which is the same sentence for every mark a
warden actually lays.

Both mark watches hang on `RelationSet`: a mark is a relation and is only
mirrored into `Conditions`, so `ConditionApplied` never names one.
"""

from __future__ import annotations

from combat_engine.engine import *
from combat_engine.engine.events import SavingThrow

from . import dropped_one_this_turn, marks_laid_by

PRIMAL = [Keyword.PRIMAL]


def _saved(world: World, me: int, ev: SavingThrow) -> bool:
    return ev.actor == me and ev.saved


@power(
    "p13603",
    level=2,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.CONJURATION],
)
def p13603(c: Cast) -> None:
    """The mark it spreads is itself a mark, so the watch has to refuse to
    answer its own work or it would mark the whole board."""
    faerie = c.conjure(c.origin, until=When.ENCOUNTER, sustain=None, speed=5)
    busy = {"now": False}

    def on_mark(ev: RelationSet) -> None:
        if busy["now"] or ev.source != c.me or ev.kind_ is not Relation.MARKED_BY:
            return
        near = [
            e for e in c.enemies() if c.adjacent_to(faerie, e) and not c.marked(e)
        ]
        if not near:
            return
        busy["now"] = True
        try:
            c.mark(on=c.choose(near, "who the faerie marks too"), until=When.EONT)
        finally:
            busy["now"] = False

    c.watch(RelationSet, on_mark, until=When.ENCOUNTER)


@power(
    "p5107",
    level=2,
    cls="warden",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    out_of_combat=True,
)
def p5107(c: Cast) -> None:
    c.note("p5107: a Perception check with a +10 power bonus")


@power(
    "p5108",
    level=2,
    cls="warden",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p5108(c: Cast) -> None:
    c.ignores_difficult(on=c.me, until=When.EONT)


@power(
    "p5110",
    level=2,
    cls="warden",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PRIMAL, Keyword.HEALING],
    requires=dropped_one_this_turn,
    requires_text="must have dropped an enemy this turn",
)
def p5110(c: Cast) -> None:
    c.heal(c.roll("1d6") + c.wis_mod + c.con_mod, on=c.me)


@power(
    "p5588",
    level=2,
    cls="warden",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p5588(c: Cast) -> None:
    """The trade is two modifiers and two conditions on them: the ally's
    existing marks go, and the ally marking anybody hands the ward back."""
    ally = c.target
    if ally is None:
        return
    for mark in marks_laid_by(c.world, ally):
        c.world.effects.end(mark, "gave up the watch")
    mine = c.penalty(AC, c.con_mod, on=c.me, until=When.EONT)
    theirs = c.bonus(AC, c.con_mod, on=ally, until=When.EONT, kind="power")

    def on_mark(ev: RelationSet) -> None:
        if ev.source != ally or ev.kind_ is not Relation.MARKED_BY:
            return
        for eff in (mine, theirs):
            if eff is not None:
                c.world.effects.end(eff, "the ally took the watch back")

    c.watch(RelationSet, on_mark, until=When.EONT)


@power(
    "p5589",
    level=2,
    cls="warden",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=PRIMAL,
    trigger="you succeed on the saving throw your class feature grants you",
    on=Trigger(SavingThrow, _saved, "you make a successful saving throw"),
)
def p5589(c: Cast) -> None:
    """The printed trigger names one class feature's saving throw; the
    chassis gives that feature no ref, so any save this warden makes and
    passes answers it."""
    c.mark(until=When.EONT)


@power(
    "p9832",
    level=2,
    cls="warden",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p9832(c: Cast) -> None:
    ally = c.target
    if ally is None:
        return

    def punish(ev: Hit | Miss) -> None:
        if ev.target == ally and c.marked(ev.attacker):
            c.flat(5, on=ev.attacker)

    c.watch(Hit, punish, until=When.EONT)
    c.watch(Miss, punish, until=When.EONT)


@power(
    "p9833",
    level=2,
    cls="warden",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL,
)
def p9833(c: Cast) -> None:
    """"One enemy marked by you" is a target restriction and `Target` has no
    field for one, so it is asked here instead."""
    if c.marked():
        c.slide(1)
