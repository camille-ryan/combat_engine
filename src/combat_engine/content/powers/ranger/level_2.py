"""Ranger, level 2.

Three immediate reactions. Two of them answer something the bus emits and
declare their printed Trigger line with `on=` rather than only quoting it.
The third answers an ally's skill check and hands out a bonus to it --
nothing the model rolls, and nothing that touches the battlefield -- so it
is `out_of_combat=True` and inert on purpose.

The later rows are the utilities from the books after the first. Ten of that
level's rows are gated on owning a particular beast companion, which this
engine has no notion of at all, and are absent rather than approximated --
see `level_1_b.py`'s docstring.

Two of them print "No Action" and a Trigger. There is an `ActionType.NONE`,
but `triggers.WINDOW_OF` does not map it to a bus window, so a row declared
with it is never offered; `FREE` is the nearest thing that dispatches and it
costs nothing, which is what "no action" means.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    WILL,
    AreaBurst,
    Cast,
    CloseBurst,
    Gear,
    Keyword,
    Melee,
    Powers,
    Ranged,
    Relation,
    When,
    World,
    distance,
    power,
)
from combat_engine.engine.events import ForcedMove, Hit, InitiativeRolled, Miss
from combat_engine.engine.query import allies, enemies, flanked_by
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_melee,
    targets_me,
)

MARTIAL = [Keyword.MARTIAL]
MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
PRIMAL = [Keyword.PRIMAL]
PRIMAL_ZONE = [Keyword.PRIMAL, Keyword.ZONE]

_DAMAGED_BY_MELEE = "an enemy damages you with a melee attack"
_MISSED_BY_MELEE = "an enemy misses you with a melee attack"
_ROLLED_INITIATIVE = "you roll initiative"
_SHOVED = "you are pushed, pulled or slid"
_HIT_A_MARK = "you hit an enemy an ally has marked, with a melee attack"


def _has_ranged(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return gear is not None and gear.ranged is not None


def _is_flanking(world: World, eid: int) -> bool:
    """"You must be flanking an enemy." """
    return any(flanked_by(world, foe, eid) for foe in enemies(world, eid))


def _hit_an_allys_mark(world: World, me: int, ev: Hit) -> bool:
    """"You hit a target with a melee attack and the target is marked by an
    ally." The mark is a relation and names who laid it, so "by an ally" is
    asked of each of them rather than of the condition."""
    if getattr(ev, "attacker", None) != me or not by_melee(world, me, ev):
        return False
    victim = getattr(ev, "target", None)
    if victim is None:
        return False
    return any(
        world.relations.holds(Relation.MARKED_BY, mate, victim)
        for mate in allies(world, me)
    )


def _step_clear(c: Cast, squares_: int) -> None:
    """Shift, ending somewhere adjacent to no enemy at all.

    "Must not end the shift adjacent to any enemy" is a condition on the
    square, and `c.shift` hands the choice to the mover's decider, which
    knows nothing about it.
    """
    if squares_ <= 0:
        return
    held = {sq for foe in c.enemies() for sq in squares_of(c.world, foe)}
    away = sorted(
        s
        for s in c.world.reachable_squares(c.me, squares_)
        if not any(distance(s, at) <= 1 for at in held)
    )
    if away:
        c.shift(squares_, to=away[0])


def _second_wind(c: Cast) -> None:
    """"You can use your second wind."

    Spelled out to match `actions.perform`, which is where a second wind
    otherwise happens: the use is counted in `Powers` so it cannot be taken
    twice, a surge is spent, and the bonus is +2 to AC alone and untyped.
    """
    known = c.world.get(c.me, Powers)
    if known is None or known.times("second-wind"):
        return
    known.note_use("second-wind", c.world.round)
    c.surge(on=c.me)
    c.bonus(AC, 2, on=c.me, until=When.SONT, kind="untyped")


@power(
    "p749",
    level=2,
    cls="ranger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_DAMAGED_BY_MELEE,
    on=Trigger(Hit, when=both(targets_me, by_melee), text=_DAMAGED_BY_MELEE),
)
def p749(c: Cast) -> None:
    """Hung off the melee hit rather than off the damage it deals.

    `DamageApplied` carries no power, so `by_melee` -- which looks the reach
    up off the power -- cannot read it. `Hit` is the nearest event that
    knows the attack was a melee one, and the two differ only for a hit that
    happens to deal nothing.
    """
    c.shift(c.wis_mod)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=c.me, until=When.EONT)


@power(
    "p923",
    level=2,
    cls="ranger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    trigger=_MISSED_BY_MELEE,
    on=Trigger(Miss, when=both(targets_me, by_melee), text=_MISSED_BY_MELEE),
)
def p923(c: Cast) -> None:
    """Where the slide ends -- "a square adjacent to you" -- cannot be said.

    `c.slide` takes no `to`, and an anchor does nothing to a slide, so the
    destination is whatever the mover's decider picks. The three squares and
    the advantage afterwards are as printed.
    """
    c.slide(3)
    c.grants_advantage()


@power(
    "p922",
    level=2,
    cls="ranger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="an ally you can see or hear makes a check you are trained for",
    out_of_combat=True,
)
def p922(c: Cast) -> None:
    """Inert by declaration: no event announces a check, and no roll takes it.

    The Trigger line is kept as prose for the card only -- there is nothing
    for `on=` to watch, and `out_of_combat` is what stops that reading as a
    row somebody forgot to finish.
    """
    c.note(f"p922: the ally rerolls, with a +{c.wis_mod} power bonus")


@power(
    "p10605",
    level=2,
    cls="ranger",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_ROLLED_INITIATIVE,
    on=Trigger(InitiativeRolled, when=about_me, text=_ROLLED_INITIATIVE),
)
def p10605(c: Cast) -> None:
    """The +2 to the initiative check itself is not written: the roll has
    already been made and placed in the order by the time the event carrying
    it is announced, and nothing re-reads a modifier afterwards.

    "Until it is no longer your quarry" is the rest of the fight, which is
    what `c.quarry` holds for.
    """
    foe = c.choose(c.enemies(), "p10605: which enemy is named quarry")
    if foe is None:
        return
    c.quarry(on=foe)
    c.bonus(
        "attack",
        2,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") == foe,
    )


@power(
    "p10606",
    level=2,
    cls="ranger",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.HEALING],
)
def p10606(c: Cast) -> None:
    _step_clear(c, max(0, c.wis_mod))
    if c.may("take a second wind", who=c.me):
        _second_wind(c)


@power(
    "p10607",
    level=2,
    cls="ranger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p10607(c: Cast) -> None:
    """The gate is re-asked every time a defence is read, so stepping out of
    the rough ground drops the bonus and stepping back in restores it --
    which is what "while you occupy" says."""
    for defence in (AC, FORT, REF, WILL):
        c.bonus(
            defence,
            4,
            on=c.me,
            until=When.EONT,
            when=lambda ctx: c.here in c.world.difficult(c.me),
        )


@power(
    "p10699",
    level=2,
    cls="ranger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL_WEAPON,
    requires=_has_ranged,
    out_of_combat=True,
)
def p10699(c: Cast) -> None:
    """Inert by declaration: the whole printed Effect is a climb DC, and the
    engine holds no DCs and rolls no checks."""
    c.note(f"p10699: five squares of wall are {2 * c.dex_mod} easier to climb")


@power(
    "p13598",
    level=2,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=AreaBurst(2, 10),
    target=NO_TARGET,
    keywords=PRIMAL_ZONE,
)
def p13598(c: Cast) -> None:
    """Difficult *for your enemies*: the zone's rough going is labelled with
    this row's ref, and everybody on the ranger's side is excused that one
    label. `world.difficult(for_=)` reads exactly that exemption.

    The second sentence -- an enemy charge cannot path through the zone --
    is not written. Nothing distinguishes a charge's movement from a walk
    once the squares are being costed.
    """
    c.zone(c.area(), until=When.ENCOUNTER, difficult=c.ref, label=c.ref)
    for friend in (c.me, *c.allies()):
        c.ignores_difficult(c.ref, on=friend, until=When.ENCOUNTER)


@power(
    "p13599",
    level=2,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=AreaBurst(1, 10),
    target=NO_TARGET,
    keywords=PRIMAL_ZONE,
)
def p13599(c: Cast) -> None:
    """"Heavily obscured **to your enemies**" is one-sided and
    `blocks_sight` is not: the ranger cannot see through it either. The Move
    Action that relocates the zone is not written -- nothing moves a zone
    once it is placed."""
    c.zone(c.area(), until=When.ENCOUNTER, blocks_sight=True, label=c.ref)


@power(
    "p13623",
    level=2,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p13623(c: Cast) -> None:
    c.resist(max(1, c.wis_mod), on=c.me, until=When.ENCOUNTER)


@power(
    "p13624",
    level=2,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p13624(c: Cast) -> None:
    """The speed only. `actions.legal` offers a shift from a ring fixed at
    one square and nothing reads a modifier there, so the extra square has
    no number to raise -- the same gap `level_10.py`'s `p926` reports."""
    c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER)


@power(
    "p13625",
    level=2,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=PRIMAL,
)
def p13625(c: Cast) -> None:
    """`EACH_ALLY`'s pool includes the caster, which is "you and each ally"
    exactly."""
    c.ignores_difficult(on=c.target, until=When.ENCOUNTER)
    c.bonus("speed", 2, on=c.target, until=When.ENCOUNTER)


@power(
    "p4379",
    level=2,
    cls="ranger",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    requires=_is_flanking,
    requires_text="needs to be flanking an enemy",
)
def p4379(c: Cast) -> None:
    """Combat advantage held for a duration, rather than the board's own
    answer: flanking ends the moment the ally steps away and this does not,
    which is the whole point of the row."""
    flanked = [foe for foe in c.enemies() if flanked_by(c.world, foe, c.me)]
    who = c.choose(flanked, "p4379: which flanked enemy") if flanked else None
    if who is not None:
        c.grants_advantage(on=who, to=c.me, until=When.EONT)


@power(
    "p4380",
    level=2,
    cls="ranger",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_HIT_A_MARK,
    on=Trigger(Hit, when=_hit_an_allys_mark, text=_HIT_A_MARK),
)
def p4380(c: Cast) -> None:
    c.shift(1)
    foe = getattr(c.trigger, "target", None)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(
            defence,
            2,
            on=c.me,
            until=When.EONT,
            when=lambda ctx, f=foe: f is None or ctx.get("attacker") == f,
        )


@power(
    "p9348",
    level=2,
    cls="ranger",
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_SHOVED,
    on=Trigger(ForcedMove, when=targets_me, text=_SHOVED),
)
def p9348(c: Cast) -> None:
    """`ForcedMove` is one of the five cancellable events, so "you negate
    the forced movement" is `c.cancel()` and not a shove back.

    The spec prints no usage word for this row. Nothing limits it, so it is
    at-will; the once-per-round budget on an immediate action is what stops
    it answering every shove in a turn.
    """
    c.cancel()
    c.bonus(
        "attack",
        2,
        on=c.me,
        until=When.EONT,
        once=True,
        when=lambda ctx: not ctx.get("ranged", False),
    )
