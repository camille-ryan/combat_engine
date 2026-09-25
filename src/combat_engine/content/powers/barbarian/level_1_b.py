"""Barbarian, level 1: the daily attacks.

`level_1.py` holds the at-wills and the encounter rows and states the
conventions the whole batch follows; these sit beside it because twelve of
the fourteen are the same shape and that shape is worth saying once.

**Every daily here but two is a rage.** The printed Effect line is "you
enter the rage of X. Until the rage ends, ...", which is a stance plus a
watcher: `enter(c)` assumes the stance and ends whichever rage was running,
and `held_by(c, stance, watcher)` takes the watcher down with it. The
watcher is clocked on the encounter rather than on `When.STANCE`, because a
second stance-clocked effect confuses `Effects.stance_of` and that is what
decides what the *next* rage replaces.

The attack half comes first and the rage half is guarded by `c.first`: a
burst rolls the body once per target and the barbarian enters one rage, not
four.

**Anything about the barbarian takes `on=c.me`.** `c.watch`, `c.bonus` and
`c.stance` all fall to `c.target`, and every rage is printed on a row that
swings at an enemy first -- so an unqualified call hangs the rage's own
rider on the creature being hit.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    CloseBurst,
    Health,
    Hit,
    Keyword,
    Melee,
    MoveEnd,
    Relation,
    TurnStart,
    When,
    get,
    power,
)
from combat_engine.engine.events import DamageApplied
from combat_engine.engine.query import adjacent, distance_between

from .rage import enter, held_by

PRIMAL_RAGE = [Keyword.PRIMAL, Keyword.WEAPON]
MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


def _melee_row(ctx: dict[str, Any]) -> bool:
    """Was the damage being rolled dealt by a melee row?

    The damage context carries the power's ref and nothing about its shape,
    so melee-ness is read off the declared reach. Gating on a melee
    *keyword* would pay nothing: almost no melee row carries one.
    """
    p = get(ctx.get("power") or "")
    return p is not None and p.reach is not None and p.reach.kind == "melee"


def _felled(c: Cast, ev: Any) -> bool:
    """Did this damage put a nonminion creature on the floor, by our hand?

    `Dropped` says who fell and never who felled them; `DamageApplied`
    carries both the source and the hit points left. A minion's single hit
    point is in the database, so `max_hp` is what "nonminion" asks.
    """
    if not isinstance(ev, DamageApplied) or ev.source != c.me or ev.hp > 0:
        return False
    health = c.world.get(ev.target, Health)
    return health is not None and health.max_hp > 1


# -- the two that are not rages ---------------------------------------------


@power(
    "p14414",
    level=1,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_RAGE,
    attack=Attack(STR, vs=AC),
)
def p14414(c: Cast) -> None:
    """The Special line -- using this in place of a melee basic attack while
    charging -- has no header field; see the report. It is not `charges=True`,
    which is for a row whose own Effect is the run."""
    if c.strike():
        c.damage(c.w(4), c.str_mod)
    else:
        c.half_damage(c.w(4), c.str_mod)


@power(
    "p14415",
    level=1,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p14415(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.prone()
    else:
        c.half_damage(c.w(2), c.str_mod)


# -- the rages --------------------------------------------------------------


@power(
    "p10056",
    level=1,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_RAGE,
    attack=Attack(STR, vs=AC),
)
def p10056(c: Cast) -> None:
    """The step is printed as an immediate reaction the barbarian *may*
    take, so it is offered rather than taken: `c.may(who=c.me)`, because a
    bare `c.may` asks the target."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.prone()
    else:
        c.half_damage(c.w(2), c.str_mod)
    if not c.first:
        return
    me = c.me
    stance = enter(c)

    def step(ev: Hit) -> None:
        if ev.attacker == me or ev.attacker not in c.allies():
            return
        if ev.target not in c.enemies() or not adjacent(c.world, me, ev.target):
            return
        if c.may("shift with the blow", who=me):
            c.shift(2)

    held_by(
        c, stance,
        c.watch(Hit, step, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage"),
    )


@power(
    "p10057",
    level=1,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_RAGE,
    attack=Attack(STR, vs=AC),
)
def p10057(c: Cast) -> None:
    """An extra opportunity is an extra *window*: `c.provoke` opens one and
    whoever is playing the barbarian decides what goes in it, which is how
    every other opportunity in the engine works. `MoveEnd` rather than
    `MoveStart`, because a shift has to have happened to be one."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    if not c.first:
        return
    me = c.me
    stance = enter(c)

    def slipped(ev: MoveEnd) -> None:
        if ev.kind_ != "shift" or ev.actor not in c.enemies():
            return
        if c.bloodied(on=ev.actor) and adjacent(c.world, me, ev.actor):
            c.provoke(me, on=ev.actor, why=c.ref)

    held_by(
        c, stance,
        c.watch(MoveEnd, slipped, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage"),
    )


@power(
    "p10058",
    level=1,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_RAGE,
    attack=Attack(STR, vs=AC),
)
def p10058(c: Cast) -> None:
    """"This damage cannot be resisted or negated" has no expression -- every
    door into hit points runs through resistance -- so the 3 is dealt the
    ordinary way and the exemption is in the report."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    if not c.first:
        return
    me = c.me
    stance = enter(c)

    def bleed(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost:
            c.flat(3, on=me)

    held_by(
        c, stance,
        c.watch(TurnStart, bleed, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage"),
        c.bonus("attack", 1, on=me, until=When.ENCOUNTER, kind="untyped"),
    )


@power(
    "p4824",
    level=1,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_RAGE,
    attack=Attack(STR, vs=AC),
)
def p4824(c: Cast) -> None:
    """"If either you or your target is bloodied" is asked when the damage is
    rolled, not when the rage is entered, so it is a gate on the modifier
    rather than a branch around it."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    if not c.first:
        return
    me = c.me
    stance = enter(c)

    def either_bloodied(ctx: dict[str, Any]) -> bool:
        if not _melee_row(ctx):
            return False
        who = ctx.get("target")
        return c.bloodied(on=me) or (who is not None and c.bloodied(on=who))

    held_by(
        c, stance,
        c.bonus(
            "damage", c.con_mod, on=me, until=When.ENCOUNTER,
            kind="untyped", when=either_bloodied,
        ),
    )


@power(
    "p4825",
    level=1,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_RAGE,
    attack=Attack(STR, vs=AC),
)
def p4825(c: Cast) -> None:
    """"You can shift 2 squares as a move action" adds an option to the turn
    for as long as the rage runs, and nothing in `Cast` grants an action;
    see the report. The speed half is the whole of what is written."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    if not c.first:
        return
    stance = enter(c)
    held_by(
        c, stance,
        c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER, kind="untyped"),
    )


@power(
    "p4874",
    level=1,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_RAGE,
    attack=Attack(STR, vs=AC),
)
def p4874(c: Cast) -> None:
    """"A +4 bonus to grab attacks" has nothing to modify: a grab in this
    engine is a relation applied outright and never a roll, so there is no
    attack for the bonus to find. The crush is the half that is written."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.grab()
    else:
        c.half_damage(c.w(2), c.str_mod)
    if not c.first:
        return
    me = c.me
    stance = enter(c)

    def crush(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if me in c.world.relations.sources(Relation.GRABBED_BY, ev.actor):
            c.flat(5 + c.str_mod, on=ev.actor)

    held_by(
        c, stance,
        c.watch(TurnStart, crush, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage"),
    )


@power(
    "p4926",
    level=1,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_RAGE,
    attack=Attack(STR, vs=AC),
)
def p4926(c: Cast) -> None:
    """A bonus whose value climbs. A modifier's number is fixed when it is
    applied, so each kill applies a fresh one a point larger -- and because
    two power bonuses of the same kind do not add but the larger wins, the
    standing total is always the newest one. Each is hung off the rage as it
    is made, so none of them outlives it.
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)
    if not c.first:
        return
    me = c.me
    stance = enter(c)
    tally = [0]

    def count(ev: DamageApplied) -> None:
        if not _felled(c, ev):
            return
        tally[0] += 1
        held_by(
            c, stance,
            c.bonus("attack", tally[0], on=me, until=When.ENCOUNTER, kind="power"),
        )

    held_by(
        c, stance,
        c.watch(
            DamageApplied, count, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage"
        ),
    )


@power(
    "p4935",
    level=1,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=PRIMAL_RAGE,
    attack=Attack(STR, vs=REF),
)
def p4935(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.prone()
    else:
        c.half_damage(c.w(1), c.str_mod)
    if not c.first:
        return
    me = c.me
    stance = enter(c)

    def feed(ev: Hit) -> None:
        if ev.attacker == me:
            c.temp_hp(c.str_mod, on=me)

    held_by(
        c, stance,
        c.watch(Hit, feed, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage"),
    )


@power(
    "p4936",
    level=1,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_RAGE,
    attack=Attack(STR, vs=AC),
)
def p4936(c: Cast) -> None:
    """The +2 is on the attack roll and is read off the target before it is
    rolled, which is what `c.strike(plus=...)` is for. "Once per round" is
    kept by hand: `c.watch` has no such flag and the round number is on the
    encounter.
    """
    if c.strike(plus=2 if c.bloodied() else 0):
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    if not c.first:
        return
    me = c.me
    stance = enter(c)
    last: list[int] = []

    def again(ev: DamageApplied) -> None:
        if (last and last[-1] == c.world.round) or not _felled(c, ev):
            return
        near = sorted(f for f in c.within(1, side="enemy") if f != ev.target)
        if not near or not c.may("swing again", who=me):
            return
        last.append(c.world.round)
        c.basic(on=near[0], who=me)

    held_by(
        c, stance,
        c.watch(
            DamageApplied, again, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage"
        ),
    )


@power(
    "p5234",
    level=1,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_RAGE,
    attack=Attack(STR, vs=AC),
)
def p5234(c: Cast) -> None:
    """The rage's whole rider is a licence to walk through one or two enemies
    each turn, and the extra damage it pays out only exists once that licence
    has been used. `c.phasing` is the nearest thing and it is wider -- it
    walks through walls and through any number of creatures -- so neither
    half is written; see the report.
    """
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    if c.first:
        enter(c)


@power(
    "p9563",
    level=1,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_RAGE, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p9563(c: Cast) -> None:
    """The surge is an Effect line, so it is spent whether the swing landed
    or not, and it is the caster's -- `c.may` asks the target unless told
    otherwise, which on a healing line is usually right and here is not."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)
    if not c.first:
        return
    me = c.me
    if c.may("spend a healing surge", who=me):
        c.surge(on=me)
    stance = enter(c)

    def warmth(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.allies():
            return
        if distance_between(c.world, me, ev.actor) <= 3:
            c.temp_hp(c.cha_mod, on=ev.actor)

    held_by(
        c, stance,
        c.watch(TurnStart, warmth, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage"),
    )


@power(
    "p9564",
    level=1,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_RAGE, Keyword.FEAR],
    attack=Attack(STR, vs=WILL),
)
def p9564(c: Cast) -> None:
    """The rage's rider is a minor action the barbarian may take once a round
    for as long as the rage runs, and nothing in `Cast` adds an action to a
    turn; see the report. The rage is still entered, which is the half a
    dozen "if you are raging" at-wills read."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.str_mod)
        c.dazed(until=When.EONT)
    if c.first:
        enter(c)
