"""Avenger, level 6: utility, second half. Nothing here prints a Prerequisite.

The conventions of `level_6.py` carry over: a stance is `c.stance(on=c.me,
...)` and anything that must stop with it is clocked on the encounter and
taken down from `stance.on_end`; a printed Trigger is declared rather than
quoted.

"Whenever you reduce X to 0 hit points" is written on `DamageApplied` rather
than on `Dropped`: `Dropped` says who fell and not who felled them, and that
is the half of the sentence these rows turn on. `DamageApplied.hp` is what
the creature has left once the blow has come off.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    WILL,
    Cast,
    CloseBurst,
    DamageApplied,
    DamageType,
    Event,
    Hit,
    Keyword,
    Melee,
    Miss,
    Powers,
    PowerUsed,
    Ranged,
    Trigger,
    TurnStart,
    Usage,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.grid import distance as grid_distance
from combat_engine.engine.grid import spread
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.query import team

from .oath import oath_target, swear, sworn

DIVINE = [Keyword.DIVINE]


@power(
    "p12457",
    level=6,
    cls="avenger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*DIVINE, Keyword.STANCE],
)
def p12457(c: Cast) -> None:
    """"You miss all targets" is counted rather than assumed.

    A `Miss` is announced once per target and carries `among`, the whole
    target list of the one use, so the misses are collected until they
    account for all of it. A hit on any target means that target never
    enters the set and the count can no longer be reached, which is the
    same sentence said the other way round; `PowerUsed` clears the tally so
    a second use of the same row starts fresh.

    "Cannot be reduced or negated by any means" has no spelling -- the ten
    goes through `deal_damage` like anything else, so resistance still
    reads it -- and is left unwritten rather than faked.
    """
    me = c.me
    stance = c.stance(on=me, label=c.ref)
    missed: dict[str, set[int]] = {}

    def started(ev: PowerUsed) -> None:
        if ev.actor == me:
            missed.pop(ev.power, None)

    def tally(ev: Miss) -> None:
        if ev.attacker != me:
            return
        p = get(ev.power or "")
        if p is None or p.usage is not Usage.ENCOUNTER or p.attack is None:
            return
        among = tuple(getattr(ev, "among", (ev.target,)))
        seen = missed.setdefault(ev.power, set())
        seen.add(ev.target)
        if len(seen) < len(among):
            return
        missed.pop(ev.power, None)
        if not c.may("take ten to get it back", who=me):
            return
        c.flat(10, on=me)
        known = c.world.get(me, Powers)
        if known is not None:
            known.unuse(ev.power)
            c.note(f"{c.ref}: {ev.power} is available again")

    for event, fn in ((PowerUsed, started), (Miss, tally)):
        watcher = c.watch(
            event, fn, until=When.ENCOUNTER, on=me, label=f"{c.ref} sacrifice"
        )
        stance.on_end.append(
            lambda w=watcher: c.world.effects.end(w, "the stance ended")
        )


@power(
    "p2933",
    level=6,
    cls="avenger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
)
def p2933(c: Cast) -> None:
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="power")


@power(
    "p3656",
    level=6,
    cls="avenger",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=DIVINE,
)
def p3656(c: Cast) -> None:
    c.shift(5, who=c.me)
    for d in (AC, REF):
        c.bonus(d, 2, on=c.me, until=When.EONT, kind="untyped")


@power(
    "p3657",
    level=6,
    cls="avenger",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE,
    out_of_combat=True,
)
def p3657(c: Cast) -> None:
    """The whole printed Effect is knowing where something is. There is no
    combat consequence to invent for it, so it is declared inert.
    """
    c.note(f"{c.ref}: a standard action gives the range and bearing to {c.target}")


_CRIT_ON_ME = "an enemy scores a critical hit against you"


def _crit_on_me(world: World, me: int, ev: Event) -> bool:
    who = getattr(ev, "attacker", None)
    return (
        getattr(ev, "target", None) == me
        and bool(getattr(ev, "critical", False))
        and who is not None
        and team(world, who) is not team(world, me)
    )


@power(
    "p5341",
    level=6,
    cls="avenger",
    usage=DAILY,
    action=REACTION,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE, Keyword.RADIANT],
    trigger=_CRIT_ON_ME,
    on=Trigger(Hit, _crit_on_me, _CRIT_ON_ME),
)
def p5341(c: Cast) -> None:
    """"Damage equal to the critical hit's damage" is not knowable when the
    reaction resolves: `Hit` is announced before the attacking body rolls
    anything. So the reaction arms a one-shot on the blow landing and the
    echo is whatever actually came off hit points.
    """
    victim = oath_target(c)
    foe = getattr(c.trigger, "attacker", None)
    if victim is None or foe is None or c.distance(victim) > 10:
        return
    me = c.me

    def echo(ev: DamageApplied) -> None:
        if ev.source == foe and ev.target == me and ev.amount > 0:
            c.flat(ev.amount, dtype=DamageType.RADIANT, on=victim)

    c.watch(
        DamageApplied, echo, until=When.ENCOUNTER, on=me, once=True,
        label=f"{c.ref} echo",
    )


@power(
    "p6934",
    level=6,
    cls="avenger",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION, *DIVINE, Keyword.HEALING],
)
def p6934(c: Cast) -> None:
    """"Counts as an ally for flanking" has nowhere to go: `query.flanked_by`
    walks the caster's allies, and a conjuration carries no side. Noted.

    The second half of the line is the oath being sworn anew, which is what
    "use your oath of enmity power as a free action" comes to -- `swear`
    releases whoever was sworn before, as every re-swearing row prints.
    """
    me = c.me
    spirit = c.conjure(label=c.ref, until=When.SUSTAIN, sustain=MINOR, speed=5)
    if not spirit:
        return
    c.ignores_difficult(on=spirit)
    c.note(f"{c.ref}: {spirit} counts as an ally for flanking, which nothing holds")
    held = next((e for e in c.world.effects.of(spirit) if e.label == c.ref), None)

    def reap(ev: DamageApplied) -> None:
        if ev.source != me or ev.hp > 0 or not c.adjacent_to(spirit, ev.target):
            return
        c.heal(c.wis_mod, on=me)
        if not sworn(c.world, me, ev.target):
            return
        near = sorted(
            f for f in c.enemies() if f != ev.target and c.adjacent_to(spirit, f)
        )
        if near:
            swear(c, c.choose(near, "who the oath falls on next"))

    watcher = c.watch(
        DamageApplied, reap, until=When.ENCOUNTER, on=me, label=f"{c.ref} reaping"
    )
    if held is None:
        return
    held.on_end.append(lambda: c.world.effects.end(watcher, "the spirit went"))

    def drift() -> None:
        if not c.can_see(spirit):
            c.world.effects.end(held, "out of sight")
            return
        c.move(5, who=spirit)

    c.on_sustain(held, drift)


@power(
    "p7006",
    level=6,
    cls="avenger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*DIVINE, Keyword.STANCE],
)
def p7006(c: Cast) -> None:
    """`c.threatens` is the half of "melee reach" anything reads: the ring an
    opportunity attack opens from. What a row may be *aimed* at comes off
    its own header's range line, which no modifier reaches; that half is in
    the report.
    """
    me = c.me
    stance = c.stance(on=me, label=c.ref)
    for held in (
        c.bonus(WILL, 1, on=me, until=When.ENCOUNTER, kind="untyped"),
        c.threatens(2, on=me, until=When.ENCOUNTER),
    ):
        if held is not None:
            stance.on_end.append(
                lambda h=held: c.world.effects.end(h, "the stance ended")
            )


_MY_AVENGER_MISS = "you miss every target with an avenger attack power"


def _my_avenger_miss(world: World, me: int, ev: Event) -> bool:
    """Offered once per missed target, which is exact for the single-target
    rows and generous for an area one. `paladin/level_6.py`'s `p11050`
    settled the same sentence the same way.
    """
    if getattr(ev, "attacker", None) != me:
        return False
    p = get(getattr(ev, "power", "") or "")
    return p is not None and p.cls == "avenger" and p.attack is not None


@power(
    "p7007",
    level=6,
    cls="avenger",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=DIVINE,
    trigger=_MY_AVENGER_MISS,
    on=Trigger(Miss, _my_avenger_miss, _MY_AVENGER_MISS),
)
def p7007(c: Cast) -> None:
    c.flat(5, on=c.me)
    c.bonus("attack", 2, on=c.me, until=When.EONT, kind="power")


@power(
    "p7008",
    level=6,
    cls="avenger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*DIVINE, Keyword.STANCE],
)
def p7008(c: Cast) -> None:
    """The step is offered at the start of the turn, which is where "the
    first action on each of your turns" lands. Its destinations are filtered
    before the choice rather than after: `c.shift` hands a free hand to the
    decider, and with none installed that takes the lowest square on the
    board, which is usually a step away from the oath.
    """
    me = c.me
    stance = c.stance(on=me, label=c.ref)

    def step(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost or not c.may("step", who=me):
            return
        victim = oath_target(c)
        if victim is None:
            c.shift(1, who=me)
            return
        theirs = squares_of(c.world, victim)
        if not theirs:
            c.shift(1, who=me)
            return

        def gap(sq: Any) -> int:
            return min(grid_distance(sq, t) for t in theirs)

        here = c.here
        now = gap(here)
        options = sorted(
            sq
            for sq in spread({here}, 1) - {here}
            if c.world.grid.inside(sq)
            and c.world.grid.passable(sq)
            and c.world.grid.occupant(sq) is None
            and gap(sq) <= now
        )
        if options:
            c.shift(1, who=me, to=c.choose(options, "where the step goes"))

    watcher = c.watch(
        TurnStart, step, until=When.ENCOUNTER, on=me, label=f"{c.ref} first step"
    )
    stance.on_end.append(lambda: c.world.effects.end(watcher, "the stance ended"))


@power(
    "p7698",
    level=6,
    cls="avenger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*DIVINE, Keyword.STANCE],
)
def p7698(c: Cast) -> None:
    """"This bonus increases to +4" is a +1 and a gated **+4** of the same
    kind, not a +1 and another +3: two bonuses of one kind do not add, the
    larger wins, so written as a top-up it would come to +1 forever.
    """
    me = c.me
    stance = c.stance(on=me, label=c.ref)
    for d in (AC, FORT):
        held = c.bonus(d, 1, on=me, until=When.ENCOUNTER, kind="power")
        if held is not None:
            stance.on_end.append(
                lambda h=held: c.world.effects.end(h, "the stance ended")
            )

    def surge(ev: DamageApplied) -> None:
        if ev.source != me or ev.hp > 0 or not sworn(c.world, me, ev.target):
            return
        for d in (AC, FORT):
            c.bonus(d, 4, on=me, until=When.EONT, kind="power")

    watcher = c.watch(
        DamageApplied, surge, until=When.ENCOUNTER, on=me, label=f"{c.ref} exaltation"
    )
    stance.on_end.append(lambda: c.world.effects.end(watcher, "the stance ended"))
