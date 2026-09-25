"""Barbarian, level 9: daily attacks.

Eleven of the fourteen are rages, and they are all the one shape: swing,
half on a miss, and then -- once, on the first target -- `enter(c)` and a
watcher handed to `held_by`. The watcher is clocked on the encounter and
never on `When.STANCE`, because a second stance-clocked effect confuses
`Effects.stance_of` and that is what decides what the next rage replaces.
`rage.py` is where both halves live.

`_each_turn` is the other recurring shape: "until the rage ends, once per
round as a <action> you can ...". It is offered at the start of the
barbarian's turn and the action is really spent, the arrangement
`paladin/level_10.py` settled. It returns its watcher, so the offer goes
down with the rage like everything else.

**Durations.** "Until the end of your turn" laid on at the start of that
same turn is `When.EOT`, not `When.EONT` -- and "until the end of its turn"
laid on an enemy at the start of *its* turn is `When.EOT` too, because
`When.EOTNT` latches when it is applied during the holder's own turn and
would run a whole turn long.

**`c.resist` takes `on=c.me`.** It reads `_who(on) or self.me`, so with a
target on the board it falls to the *target* -- "you gain resist 5" written
bare hands the resistance to the creature being hit. `docs/AUTHORING.md`
lists it among the methods that default to the caster; they do not. In the
report.

Two rows are not rages. `p14427` is an Effect, so its push and its fall come
whether the blow landed or not. `p14426`'s entire printed Effect is a
defender aura and a named class feature, neither of which the engine models;
the attack is written and the clause is a note -- see the report.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine import (
    AC,
    DAILY,
    FREE,
    MINOR,
    MOVE,
    ONE_CREATURE,
    REACTION,
    STANDARD,
    STR,
    ActionType,
    Attack,
    AttackDeclared,
    Cast,
    Condition,
    DamageApplied,
    DamageType,
    Effect,
    Hit,
    Keyword,
    Melee,
    Trigger,
    TurnStart,
    When,
    Window,
    both,
    by_charge,
    by_keyword,
    by_melee,
    power,
    targets_my_side,
)
from combat_engine.engine.grid import distance
from combat_engine.engine.query import distance_between, team
from combat_engine.engine.query import squares as squares_of

from .rage import enter, held_by

PRIMAL_WEAPON = [Keyword.PRIMAL, Keyword.WEAPON]
MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

_CHARGED_US = "an enemy charges you or an ally"


def _each_turn(
    c: Cast,
    cost: ActionType,
    what: str,
    fn: Callable[[], None],
    ready: Callable[[], bool] | None = None,
) -> Effect:
    """"Once per round as a <cost> action you can ..." -- offered at the top
    of the barbarian's turn, with the action really spent."""
    me = c.me

    def offer(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or c.world.encounter is None:
            return
        if ready is not None and not ready():
            return
        if not c.may(what, who=me):
            return
        if c.world.encounter.spend(me, cost):
            fn()

    return c.watch(TurnStart, offer, until=When.ENCOUNTER, on=me, label=f"{c.ref} {what}")


def _mine(c: Cast, who: int) -> bool:
    """On my side. `query.enemies` drops the dead, which is false exactly
    when a row wants to know who just went down."""
    return team(c.world, who) is team(c.world, c.me)


@power(
    "p10060",
    level=9,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10060(c: Cast) -> None:
    """"Whenever you reduce any enemy to 0 hit points" is read off
    `DamageApplied`, which names both who dealt it and what the hit points
    came to. `Dropped` says neither."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    if not c.first:
        return
    me = c.me
    stance = enter(c)

    def bank(ev: DamageApplied) -> None:
        if ev.source != me or ev.hp > 0 or _mine(c, ev.target):
            return
        c.bonus("damage", 5, on=me, until=When.ENCOUNTER, once=True)

    watcher = c.watch(
        DamageApplied, bank, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage"
    )
    held_by(c, stance, watcher)


@power(
    "p10061",
    level=9,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p10061(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(3), c.str_mod)
    if not c.first:
        return
    stance = enter(c)
    held_by(c, stance, c.resist(5, on=c.me, until=When.ENCOUNTER))


@power(
    "p14426",
    level=9,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p14426(c: Cast) -> None:
    """The whole Effect is a defender aura widening and a free shift before
    a melee basic attack granted by a named class feature. The engine has
    neither the aura nor the feature, so the attack is what is written and
    the rest is a note; see the report."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    if c.first:
        c.note(
            f"{c.ref}: until the end of the encounter your defender aura would widen to "
            "2 and you could shift 1 before each melee basic attack it grants"
        )


@power(
    "p14427",
    level=9,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p14427(c: Cast) -> None:
    """The shove and the fall are an Effect, so they come on a miss too."""
    if c.strike():
        c.damage(c.w(4), c.str_mod)
    else:
        c.half_damage(c.w(4), c.str_mod)
    c.push(4)
    c.prone()


@power(
    "p4837",
    level=9,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4837(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        c.prone()
    else:
        c.half_damage(c.w(3), c.str_mod)
    if not c.first:
        return
    me = c.me
    stance = enter(c)

    def floor_it(ev: Hit) -> None:
        if ev.attacker != me or _mine(c, ev.target) or not by_melee(c.world, me, ev):
            return
        if c.is_(Condition.PRONE, on=ev.target):
            c.flat(c.con_mod, on=ev.target)
        else:
            c.prone(on=ev.target)

    watcher = c.watch(Hit, floor_it, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage")
    held_by(c, stance, watcher)


@power(
    "p4838",
    level=9,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p4838(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    if not c.first:
        return
    stance = enter(c)
    held_by(c, stance, c.resist(c.con_mod, on=c.me, until=When.ENCOUNTER))


@power(
    "p4875",
    level=9,
    cls="barbarian",
    usage=DAILY,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
    trigger=_CHARGED_US,
    on=Trigger(AttackDeclared, both(by_charge, targets_my_side), _CHARGED_US),
)
def p4875(c: Cast) -> None:
    """The printed shift is six squares and does not say where; the charger
    is the only reason to spend it, so the destination is the nearest square
    in reach of it. "You can take further actions after a charge" is already
    true of the engine -- a charge spends a standard and ends nothing -- so
    that half is a note rather than a change.
    """
    victim = c.target
    if victim is None:
        return
    if c.first and not c.adjacent(victim):
        theirs = squares_of(c.world, victim)
        spots = [
            sq
            for sq in c.world.reachable_squares(c.me, 6)
            if min(distance(sq, t) for t in theirs) <= 1
        ]
        if spots:
            c.shift(6, to=min(spots))
        else:
            c.shift(6)
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    if not c.first:
        return
    stance = enter(c)
    held_by(c, stance, _each_turn(c, MOVE, "shift 2 squares", lambda: c.shift(2)))
    c.note(f"{c.ref}: a charge on your own turn no longer ends it")


@power(
    "p4924",
    level=9,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.POISON],
    attack=Attack(STR, vs=AC),
)
def p4924(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.POISON)
        c.ongoing(5, DamageType.POISON)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=DamageType.POISON)
    if not c.first:
        return
    me = c.me
    stance = enter(c)

    def expose(ev: Hit) -> None:
        if ev.attacker != me or _mine(c, ev.target):
            return
        c.grants_advantage(on=ev.target, until=When.EONT, to="allies")

    watcher = c.watch(Hit, expose, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage")
    held_by(c, stance, watcher)


@power(
    "p4949",
    level=9,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.ACID],
    attack=Attack(STR, vs=AC),
)
def p4949(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.ACID)
        c.ongoing(5, DamageType.ACID)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=DamageType.ACID)
    if not c.first:
        return
    me = c.me
    stance = enter(c)

    def sting(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        for foe in sorted(c.within(1, side="enemy")):
            c.blinded(on=foe, until=When.EOT)

    watcher = c.watch(
        TurnStart, sting, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage"
    )
    held_by(c, stance, watcher)


@power(
    "p4950",
    level=9,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.COLD],
    attack=Attack(STR, vs=AC),
)
def p4950(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.COLD)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=DamageType.COLD)
        c.slowed(until=When.SAVE_ENDS)
    if not c.first:
        return
    me = c.me
    stance = enter(c)

    def chill(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or _mine(c, ev.actor):
            return
        if c.adjacent(ev.actor):
            c.slowed(on=ev.actor, until=When.EOT)

    watcher = c.watch(
        TurnStart, chill, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage"
    )
    held_by(c, stance, watcher)


@power(
    "p7392",
    level=9,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p7392(c: Cast) -> None:
    """"The damage you take cannot be reduced or negated" has no expression
    -- resistance and insubstantiality are both read inside `deal_damage`
    and neither can be waived -- so the 5 is dealt untyped, which is the
    closest the engine gets; the clause is in the report."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    if not c.first:
        return
    me = c.me
    stance = enter(c)

    def maul() -> None:
        foes = sorted(c.within(1, side="enemy"))
        victim = c.choose(foes, f"{c.ref}: who to maul")
        if victim is None:
            return
        c.flat(5, on=me)
        c.flat(5 + c.con_mod, on=victim)

    offer = _each_turn(
        c, MINOR, "bleed to maul an adjacent enemy", maul,
        ready=lambda: bool(c.within(1, side="enemy")),
    )
    held_by(c, stance, offer)


@power(
    "p9576",
    level=9,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9576(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.vulnerable(5, until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.str_mod)
    if not c.first:
        return
    me = c.me
    stance = enter(c)
    is_primal = by_keyword(Keyword.PRIMAL)

    def spur(ev: Hit) -> None:
        if ev.attacker != me or _mine(c, ev.target) or not is_primal(c.world, me, ev):
            return
        friends = sorted(f for f in c.within(2, of=ev.target, side="ally") if f != me)
        friend = c.choose(friends, f"{c.ref}: who slips a square") if friends else None
        if friend is not None and c.may("slip a square", who=friend):
            c.shift(1, who=friend)

    watcher = c.watch(Hit, spur, until=When.ENCOUNTER, on=me, label=f"{c.ref} rage")
    held_by(c, stance, watcher)


@power(
    "p9577",
    level=9,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=PRIMAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p9577(c: Cast) -> None:
    """The bonus is gated on the mark rather than dated with it: "enemies
    marked by you" is asked when the attack is rolled, so a mark laid three
    turns later pays it too."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.weakened(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.str_mod)
        c.weakened(until=When.EONT)
    if not c.first:
        return
    me = c.me
    stance = enter(c)

    def call_them_out() -> None:
        for foe in sorted(c.within(2, side="enemy")):
            c.mark(on=foe, until=When.EONT)

    offer = _each_turn(
        c, FREE, "call out every enemy within 2 squares", call_them_out,
        ready=lambda: bool(c.within(2, side="enemy")),
    )
    edge = c.bonus(
        "attack",
        2,
        on=me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") is not None and c.marked(on=ctx["target"]),
    )
    held_by(c, stance, offer, edge)


@power(
    "p9578",
    level=9,
    cls="barbarian",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_WEAPON, Keyword.FEAR],
    attack=Attack(STR, vs=AC),
)
def p9578(c: Cast) -> None:
    """"Cannot charge" is the charge's own attack refused as it is declared
    -- `AttackDeclared` is a `Decision` and carries the charge flag, and
    there is no other seam between the run-up and the swing."""
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        c.push(3)
    else:
        c.half_damage(c.w(2), c.str_mod)
        c.push(1)
    if not c.first:
        return
    me = c.me
    stance = enter(c)
    guarded = max(0, c.cha_mod)

    def wave_off(ev: AttackDeclared) -> None:
        if not getattr(ev, "charge", False) or _mine(c, ev.attacker):
            return
        friend = ev.target
        if friend == me or not _mine(c, friend):
            return
        if distance_between(c.world, me, friend) <= guarded:
            ev.cancel(f"{c.ref}: they cannot be charged")

    watcher = c.watch(
        AttackDeclared, wave_off, until=When.ENCOUNTER, window=Window.BEFORE, on=me,
        label=f"{c.ref} rage",
    )
    held_by(c, stance, watcher)
