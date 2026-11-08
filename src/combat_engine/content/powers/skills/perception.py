"""Perception skill powers: nine utilities about seeing and being first.

`cls` is the skill, which is what makes a skill power identifiable at all --
see the package docstring. All nine are Utility at level 2, 6 or 10.

What the group has in common is the two things this engine *does* read about
sight: the cover and concealment a shot has to look past, and the passive
check a hider is measured against. Everything here that prints a Trigger
declares it with `on=`, since `trigger=` alone is prose nothing reads.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MINOR,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    YOU_OR_ONE_ALLY,
    ActionType,
    Cast,
    CloseBurst,
    Condition,
    ConditionApplied,
    Event,
    Initiative,
    InitiativeRolled,
    Keyword,
    Miss,
    Ranged,
    RoundStart,
    Trigger,
    When,
    World,
    about_me,
    ally_within,
    both,
    get,
    power,
)
from combat_engine.engine.query import conscious, defence, is_

#: "Ranged sight" has no unbounded range kind, and 20 is the convention the
#: rest of the tree already uses for it: the board is smaller than that and
#: `area_of` clips to it anyway.
SIGHT = 20


@power(
    "p9332",
    level=2,
    cls="perception",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p9332(c: Cast) -> None:
    """Both halves, and only one of them needs a gate.

    The long-range penalty is charged by `resolve._long_range`, which
    already asks the row for the weapon keyword and for a `ranged` reach
    before it charges anything -- so an ungated waiver is exactly the
    printed narrowing rather than a wider one.

    The cover half does need the gate, because `ignore_cover` is read for
    every swing the caster makes. `partial=True` is the printed proviso:
    it waives the ordinary -2 and leaves superior cover and total
    concealment standing.
    """

    def ranged_weapon(ctx: dict[str, Any]) -> bool:
        row = get(str(ctx.get("power", "")))
        if row is None or not ctx.get("ranged"):
            return False
        return Keyword.WEAPON in c.keywords_of(row)

    c.ignores_long_range(on=c.me, until=When.EONT)
    c.ignore_cover(on=c.me, until=When.EONT, partial=True, when=ranged_weapon)


@power(
    "p11586",
    level=6,
    cls="perception",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you find a trap with a Perception check",
    out_of_combat=True,
)
def p11586(c: Cast) -> None:
    """Inert, and the circumstance is what says so rather than the skill.

    Both ends of this row are about a trap: the trigger is finding one and
    the benefit is a reroll on the checks made to disable it. No board
    presents a trap to find or to disable -- `c.disable_trap()` is the
    standing gap for the second half, waited on elsewhere -- so there is no
    moment in a fight at which either clause could pay.

    Not a marker: nothing is missing from the row, and a symbol here would
    sit in the queue behind a mechanism this power is not the reason to
    build. The trigger is left as the prose the card prints, because an
    inert row has nothing to fire.
    """


@power(
    "p11587",
    level=6,
    cls="perception",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.STANCE],
    todo=("c.lend_passive(skill)",),
)
def p11587(c: Cast) -> None:
    """Lending a check across creatures, which nothing does.

    The printed benefit is that an ally uses the caster's *passive*
    Perception in place of its own, and that number is read -- it is the DC
    a hider is measured against -- so this is a real gap and not a
    narrative one.

    What cannot be said is the substitution. `c.bonus("skill:perception")`
    moves one creature's own number; the difference wanted here is per
    ally, and a zone modifier carries one value for everybody standing in
    it, so the geometry half and the arithmetic half cannot both be right.
    `c.substitute_check()` is a different gap -- one creature rolling a
    different skill of its own -- so this wants its own symbol.

    Nothing survives without it, so the whole row waits rather than
    playing: a stance that grants nothing would be offered every fight.
    """


_CAUGHT_OUT = "you are surprised while conscious"


def _caught_out(world: World, me: int, ev: ConditionApplied) -> bool:
    """The moment the condition lands. `targets_me` reads the right field
    on this event and `about_me` would be false forever."""
    return (
        ev.target == me
        and ev.condition is Condition.SURPRISED
        and conscious(world, me)
    )


def _still_surprised(world: World, me: int, ev: Event) -> bool:
    """A round that opens with the caster already surprised, for a fight
    whose surprise was arranged before anything was watching."""
    return is_(world, me, Condition.SURPRISED) and conscious(world, me)


@power(
    "p16483",
    level=6,
    cls="perception",
    usage=DAILY,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=SELF,
    trigger=_CAUGHT_OUT,
    on=(
        Trigger(ConditionApplied, _caught_out, _CAUGHT_OUT),
        Trigger(RoundStart, _still_surprised, _CAUGHT_OUT),
    ),
)
def p16483(c: Cast) -> None:
    """Two triggers for one printed sentence, because nothing announces a
    surprise round: being surprised is readable as the condition arriving
    and as a round beginning with it already standing.

    "Aware of the location of any hidden enemy within 10 squares" is the
    sense this engine spells `truesight`: a radius inside which a creature
    gets no benefit from being unseen, read by `query.unseen_by`, which is
    what the awareness is worth in a fight. **The card gives the awareness
    no duration** and this holds it to the end of the caster's next turn,
    which is the judgement call in the row -- an encounter-long grant off a
    single trigger would be a larger sentence than the page prints.
    """
    c.cure(Condition.SURPRISED, on=c.me)
    c.truesight(10, on=c.me, until=When.EONT)
    c.shift(c.speed_of() // 2)


_MISSED_AC = "an ally within 10 squares misses with an attack against AC"


def _against_ac(world: World, me: int, ev: Event) -> bool:
    """Which defence the swing was aimed at. `resolve.attack` stamps `vs`
    on the outcome as a plain attribute, so it is read off the emission
    site and not off the dataclass.

    `ev: Event`, not `ev: Miss`, because that is the signature `both` and
    `Trigger.when` are typed for -- a predicate narrowed to one event class
    is the stricter function and cannot stand in for the general one. The
    `Trigger` beside it names `Miss`, so the narrowing is in the
    declaration where the dispatcher can see it rather than in a type a
    reader has to trust.
    """
    return getattr(ev, "vs", None) is AC


@power(
    "p9333",
    level=6,
    cls="perception",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    trigger=_MISSED_AC,
    on=Trigger(Miss, both(ally_within(10), _against_ac), _MISSED_AC),
)
def p9333(c: Cast) -> None:
    """The ally's swing is judged again against Reflex, not rolled again.

    The target line names the triggering ally, so the body reads the event
    rather than `c.target`: an immediate action is handed whatever the
    chooser picked out of the burst, and only the trigger says which ally
    actually missed.

    An `INTERRUPT` answers in `Window.BEFORE`, which on a `Miss` is inside
    `resolve.roll` and before its `confirm` callback -- so moving the
    number the outcome was measured against and re-settling turns a miss
    that fell short of Reflex into a real `Hit`, announced as one, with the
    riders on it paid. `c.settle_attack` is the door for exactly that; a
    `c.bonus` cannot do it, because the sum was taken when the die landed.

    `c.retarget_defence` is called as well and is not redundant: the
    settled outcome carries `vs`, which is what a row printing "an attack
    against your AC or Reflex" reads, and leaving it saying AC would make
    the record disagree with the arithmetic.
    """
    ev = c.trigger
    result = getattr(ev, "result", None)
    victim = getattr(ev, "target", None)
    if result is None or victim is None:
        return
    c.retarget_defence(REF)
    result.target_defence = defence(
        c.world, victim, REF, getattr(ev, "ctx", None) or {}
    )
    c.settle_attack(ev=ev)


@power(
    "p11588",
    level=10,
    cls="perception",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def p11588(c: Cast) -> None:
    """The full waiver rather than `partial=True`: the card names superior
    cover and total concealment as well, which is the 5 this lays and not
    the 2.

    Gated on the one creature, since the benefit sits on the caster's own
    sight and would otherwise cover every swing of the turn.
    """
    foe = c.target
    if foe is None:
        return
    c.ignore_cover(
        on=c.me, until=When.EONT, when=lambda ctx: ctx.get("target") == foe
    )


@power(
    "p11589",
    level=10,
    cls="perception",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p11589(c: Cast) -> None:
    """The printed radius is read: `query.sees_in` is handed the distance
    to whatever is being looked at, so the sense stops answering past 5."""
    c.blindsight(5, on=c.me, until=When.EONT)


@power(
    "p11590",
    level=10,
    cls="perception",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(SIGHT),
    target=ONE_CREATURE,
)
def p11590(c: Cast) -> None:
    """The errata is what `once=True` says: one damage roll, not every one
    until the end of the turn. A one-shot damage bonus is spent on the
    `DamageRolled` its own gate admits, so the roll against somebody else
    does not consume it.
    """
    foe = c.target
    if foe is None:
        return
    c.bonus(
        "damage",
        4,
        on=c.me,
        until=When.EONT,
        kind="power",
        once=True,
        when=lambda ctx: ctx.get("target") == foe,
    )


_ROLLED = "you roll initiative and dislike the result"


def _instead_of_the_roll(c: Cast, who: int, seen: int) -> None:
    """Move a creature to the count the caster's passive check names.

    `c.initiative` takes a difference and splices the creature back into
    the order, so the substitution is written as the gap between what was
    rolled and what the card says to use instead. `Initiative.rolled` is
    the count that is actually sorted on, and every creature has one by the
    time this fires -- `_roll_initiative` rolls everybody, then announces.
    """
    stood = c.world.get(who, Initiative)
    if stood is not None:
        c.initiative(seen - stood.rolled, on=who)


@power(
    "p9334",
    level=10,
    cls="perception",
    usage=DAILY,
    action=FREE,
    reach=CloseBurst(5),
    target=YOU_OR_ONE_ALLY,
    trigger=_ROLLED,
    on=Trigger(InitiativeRolled, about_me, _ROLLED),
)
def p9334(c: Cast) -> None:
    """"You and one ally" -- the `team` pool is one target, so the caster's
    own half is written explicitly on the first (and only) one.

    A substitution and not a bonus, which is why it is a difference: the
    printed line replaces the check rather than adding to it.
    """
    seen = c.passive("perception", of=c.me)
    who = c.target
    if who is not None:
        _instead_of_the_roll(c, who, seen)
    if c.first and who != c.me:
        _instead_of_the_roll(c, c.me, seen)
