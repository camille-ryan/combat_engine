"""Fighter, level 0: the defender aura, the stances, and the two at-will
opportunity rows the later books hang off them.

Three sentences carry this whole file.

**"A basic attack using a weapon"** is `Powers.basic`, and for a character
that is the engine's own `mba`/`rba` -- both of which carry the Weapon
keyword, so "using a weapon" needs no second question. `BASICS` is the pair
and `MELEE` alone is the melee half. A monster points `Powers.basic` at one
of its own abilities; no fighter row is ever used by one.

**A stance's benefit must die with the stance.** `c.stance` displaces the
previous stance but does not touch anything hung off it, so every benefit
below is taken `until=When.ENCOUNTER` and tied back through `_ends_with`.
`When.STANCE` is not used for the benefit: `Effects.stance_of` returns the
first `When.STANCE` effect it finds, and a second one would be mistaken for
the stance itself.

**The defender aura is a named hold plus an aura 1.** `subject_to_aura`
is the question the two opportunity rows ask, and it carries the printed
exemption -- a marked enemy is outside it. "An ally of yours who has this
aura active" is read as "you": the aura is per fighter and the engine has
no way to ask another character whether its own class feature is up.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    MELEE,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    OPPORTUNITY,
    PERSONAL,
    RANGED,
    SELF,
    STR,
    ActionType,
    Attack,
    AttackDeclared,
    Cast,
    Effect,
    Hit,
    Keyword,
    Melee,
    MoveStart,
    OpportunityWindow,
    Relation,
    Trigger,
    When,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.query import distance_between, team
from combat_engine.engine.query import squares as squares_of

from .footwork import aura_ring, close_by_shift

MARTIAL = [Keyword.MARTIAL]
MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_STANCE = [Keyword.MARTIAL, Keyword.STANCE]

#: The two rows a character's basic attack can be.
BASICS = (MELEE, RANGED)

#: The label the aura's hold wears. See `m6474a0` for the printed feature.
AURA = "defender aura"


# -- the vocabulary this file needs -----------------------------------------


def _basic_ctx(ctx: dict[str, Any]) -> bool:
    """"Basic attacks using a weapon", as a modifier gate."""
    return ctx.get("power") in BASICS


def _weapon_power(ctx: dict[str, Any]) -> bool:
    """"Attack rolls with weapon powers"."""
    p = get(ctx.get("power") or "")
    return p is not None and Keyword.WEAPON in p.keywords


def _ends_with(c: Cast, stance: Effect, *holds: Effect | None) -> None:
    for hold in holds:
        if hold is not None:
            c_hold = hold
            stance.on_end.append(
                lambda h=c_hold: c.world.effects.end(h, "stance ended")
            )


def _on_basic_hit(
    c: Cast, stance: Effect, fn: Callable[[Hit], None], *, melee: bool = True
) -> None:
    """"Whenever you hit an enemy with a (melee) basic attack using a weapon"."""
    me = c.me
    wanted = (MELEE,) if melee else BASICS

    def landed(ev: Hit) -> None:
        if ev.attacker == me and ev.power in wanted:
            fn(ev)

    held = c.watch(Hit, landed, until=When.ENCOUNTER, on=me, label=c.ref)
    _ends_with(c, stance, held)


def has_defender_aura(world: World, me: int) -> bool:
    return any(e.label == AURA for e in world.effects.of(me))


def subject_to_aura(world: World, me: int, who: int | None) -> bool:
    """"An enemy subject to your defender aura." Marked enemies are not."""
    if who is None or not has_defender_aura(world, me):
        return False
    if team(world, who) is team(world, me):
        return False
    if distance_between(world, me, who) > 1:
        return False
    return not world.relations.sources(Relation.MARKED_BY, who)


_BREACH = "an enemy in your defender aura shifts, or attacks without you in it"


def _aura_foe_shifts(world: World, me: int, ev: MoveStart) -> bool:
    """`MoveStart`, not `MoveEnd`: by the end of the shift the enemy has left
    the aura, which is exactly when the row should fire."""
    return ev.kind_ == "shift" and subject_to_aura(world, me, ev.actor)


def _aura_foe_swings(world: World, me: int, ev: AttackDeclared) -> bool:
    if ev.target == me or not subject_to_aura(world, me, ev.attacker):
        return False
    return team(world, ev.target) is team(world, me)


def _aura_foe_swings_at_anyone(world: World, me: int, ev: AttackDeclared) -> bool:
    """p13773's half of the sentence leaves the ally out: any attack that
    does not include the fighter is enough."""
    return ev.target != me and subject_to_aura(world, me, ev.attacker)


def _triggering_foe(c: Cast) -> int | None:
    ev = c.trigger
    who = getattr(ev, "actor", None)
    return who if who is not None else getattr(ev, "attacker", None)


def _beside(c: Cast, thing: int) -> Any:
    """An unoccupied square touching `thing`, for a named teleport."""
    theirs = squares_of(c.world, thing)
    if not theirs:
        return None
    for sq in sorted(spread(theirs, 1) - theirs):
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            return sq
    return None


# -- the rows ---------------------------------------------------------------


_PROVOKED = "an adjacent enemy takes an action that provokes an opportunity attack"


def _provoked_me(world: World, me: int, ev: OpportunityWindow) -> bool:
    return ev.actor == me and distance_between(world, me, ev.provoker) <= 1


@power(
    "p10469",
    level=0,
    cls="fighter",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    trigger=_PROVOKED,
    on=Trigger(OpportunityWindow, _provoked_me, _PROVOKED),
)
def p10469(c: Cast) -> None:
    """"After the triggering enemy completes the action" cannot be honoured:
    the window is opened while the provoker is still in the square it is
    leaving, because an opportunity attack interrupts the move, and there is
    no later window to answer in. The shift and the swing happen in the
    order printed; only the "after" is lost.
    """
    foe = getattr(c.trigger, "provoker", None)
    if foe is None:
        foe = c.target
    if foe is None:
        return
    close_by_shift(c, c.dex_mod)
    if c.strike(on=foe):
        c.damage(c.w(2 if c.level >= 21 else 1), c.str_mod, on=foe)
        c.prone(on=foe)


@power(
    "p12660",
    level=0,
    cls="fighter",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p12660(c: Cast) -> None:
    """The aura is an aura 1 plus a named hold, so that the two opportunity
    rows have something to ask about; `aura_ring` puts the penalty on
    whoever walks in and takes it off again on the way out.

    "Until you end it as a minor action" is dropped -- nothing takes an aura
    down early, and the printed second clause, falling unconscious, is not
    something a fighter chooses. See the report.
    """
    me = c.me
    hold = c.effect(AURA, until=When.ENCOUNTER, on=me)
    if hold is None:
        return

    def give(who: int) -> list[Effect | None]:
        def gate(ctx: dict[str, Any]) -> bool:
            if ctx.get("target") == me:
                return False
            return not c.world.relations.sources(Relation.MARKED_BY, who)

        return [
            c.penalty("attack", 2, on=who, until=When.ENCOUNTER, when=gate)
        ]

    aura_ring(c, hold, side="enemy", give=give)


@power(
    "p12661",
    level=0,
    cls="fighter",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_BREACH,
    on=[
        Trigger(MoveStart, _aura_foe_shifts, _BREACH),
        Trigger(AttackDeclared, _aura_foe_swings, _BREACH),
    ],
)
def p12661(c: Cast) -> None:
    foe = _triggering_foe(c)
    if foe is None:
        return
    if not c.basic(on=foe):
        c.flat(c.str_mod, on=foe)


@power(
    "p12662",
    level=0,
    cls="fighter",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL_STANCE,
)
def p12662(c: Cast) -> None:
    stance = c.stance(label=c.ref)
    step = 4 if c.level >= 21 else 3 if c.level >= 11 else 2
    _ends_with(
        c,
        stance,
        c.bonus("damage", step, on=c.me, until=When.ENCOUNTER, when=_basic_ctx, kind="power"),
    )


@power(
    "p12663",
    level=0,
    cls="fighter",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL_STANCE,
)
def p12663(c: Cast) -> None:
    """"One enemy adjacent to you other than the target" is a choice the row
    leaves open; the nearest is taken."""
    stance = c.stance(label=c.ref)

    def splash(ev: Hit) -> None:
        others = [f for f in c.enemies() if f != ev.target and c.adjacent(f)]
        if others:
            c.flat(c.con_mod, on=others[0])

    _on_basic_hit(c, stance, splash)


@power(
    "p12664",
    level=0,
    cls="fighter",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL_STANCE,
)
def p12664(c: Cast) -> None:
    stance = c.stance(label=c.ref)
    _on_basic_hit(c, stance, lambda ev: c.slowed(on=ev.target, until=When.EONT))


@power(
    "p12665",
    level=0,
    cls="fighter",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL_STANCE,
)
def p12665(c: Cast) -> None:
    """"Shift the same distance to a square adjacent to the enemy" is a
    filter on the destination, so it goes through `close_by_shift` rather
    than the decider, which would happily step into the open."""
    stance = c.stance(label=c.ref)

    def shove(ev: Hit) -> None:
        if not c.may("push and follow", who=c.me):
            return
        if c.push(1, on=ev.target):
            close_by_shift(c, 1)

    _on_basic_hit(c, stance, shove)


@power(
    "p12666",
    level=0,
    cls="fighter",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL_STANCE,
)
def p12666(c: Cast) -> None:
    stance = c.stance(label=c.ref)

    def step(_: Hit) -> None:
        if c.may("shift a square", who=c.me):
            c.shift(1)

    _on_basic_hit(c, stance, step)


@power(
    "p12667",
    level=0,
    cls="fighter",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL_STANCE,
)
def p12667(c: Cast) -> None:
    stance = c.stance(label=c.ref)
    _ends_with(
        c,
        stance,
        c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, when=_basic_ctx, kind="power"),
    )


_BASIC_LANDED = "you hit an enemy with a melee basic attack using a weapon"


def _my_melee_basic_hit(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and ev.power == MELEE


@power(
    "p12668",
    level=0,
    cls="fighter",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL_WEAPON,
    trigger=_BASIC_LANDED,
    on=Trigger(Hit, _my_melee_basic_hit, _BASIC_LANDED),
)
def p12668(c: Cast) -> None:
    """Extra damage "from the triggering attack", dealt as a second packet:
    the blow has already been rolled by the time a No Action answers it."""
    ev = c.trigger
    if ev is None:
        return
    c.damage(c.w(3 if c.level >= 27 else 2 if c.level >= 17 else 1), on=ev.target)


@power(
    "p12688",
    level=0,
    cls="fighter",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL_STANCE,
)
def p12688(c: Cast) -> None:
    """The attack half is gated on `charge`, which the attack context
    carries. The speed half is dropped: speed is asked for with no context
    at all, so "+2 to your speed **when charging**" cannot be gated and an
    ungated +2 would be a permanent one. See the report.
    """
    stance = c.stance(label=c.ref)
    _ends_with(
        c,
        stance,
        c.bonus(
            "attack", 2, on=c.me, until=When.ENCOUNTER, kind="power",
            when=lambda ctx: bool(ctx.get("charge")),
        ),
    )


@power(
    "p12689",
    level=0,
    cls="fighter",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL_STANCE,
)
def p12689(c: Cast) -> None:
    """"A target that has no creatures adjacent to it other than you" is
    asked at damage time, which is the one context that carries `target`."""
    stance = c.stance(label=c.ref)
    step = 8 if c.level >= 21 else 6 if c.level >= 11 else 4
    me = c.me

    def alone(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        if foe is None or ctx.get("power") != MELEE:
            return False
        crowd = [w for w in c.within(1, of=foe) if w not in (me, foe)]
        return not crowd

    _ends_with(
        c, stance,
        c.bonus("damage", step, on=me, until=When.ENCOUNTER, when=alone, kind="power"),
    )


@power(
    "p12690",
    level=0,
    cls="fighter",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL_STANCE,
)
def p12690(c: Cast) -> None:
    stance = c.stance(label=c.ref)

    def stride(_: Hit) -> None:
        if c.dex_mod > 0 and c.may("move away", who=c.me):
            c.move(c.dex_mod)

    _on_basic_hit(c, stance, stride, melee=False)


@power(
    "p12692",
    level=0,
    cls="fighter",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL_STANCE,
)
def p12692(c: Cast) -> None:
    stance = c.stance(label=c.ref)
    step = 8 if c.level >= 21 else 6 if c.level >= 11 else 4
    _ends_with(
        c,
        stance,
        c.penalty("attack", 2, on=c.me, until=When.ENCOUNTER, when=_weapon_power),
        c.bonus("damage", step, on=c.me, until=When.ENCOUNTER, when=_basic_ctx, kind="power"),
    )


@power(
    "p13773",
    level=0,
    cls="fighter",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.TELEPORTATION],
    requires_text="you must be r3",
    trigger=_BREACH,
    on=[
        Trigger(MoveStart, _aura_foe_shifts, _BREACH),
        Trigger(AttackDeclared, _aura_foe_swings_at_anyone, _BREACH),
    ],
)
def p13773(c: Cast) -> None:
    """The Prerequisite is a race, and a character's race is not a question
    the engine answers -- `c.kinds_of` reads a monster's type line and is
    empty for a character. It is kept as printed text rather than written as
    a gate that would refuse the row to every eladrin as well.
    """
    foe = _triggering_foe(c)
    if foe is None:
        return
    landing = _beside(c, foe)
    if landing is None:
        return
    c.teleport(2, to=landing)
    c.basic(on=foe)


@power(
    "p13774",
    level=0,
    cls="fighter",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE, Keyword.TELEPORTATION],
    requires_text="you must be r3 and must have its racial teleport power",
)
def p13774(c: Cast) -> None:
    """The Prerequisite is prose for the reason given on p13773; the second
    half of it names a row by name, which is not something a header says."""
    stance = c.stance(label=c.ref)

    def blink(ev: Hit) -> None:
        landing = _beside(c, ev.target)
        if landing is not None and c.may("blink to its side", who=c.me):
            c.teleport(2, to=landing)

    _on_basic_hit(c, stance, blink)
