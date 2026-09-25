"""Avenger, level 1: the rest of the encounter attacks, and the dailies.

`level_1.py` holds the at-wills and the first seven encounter rows, and
states the conventions this file inherits -- Wisdom everywhere, the oath
helpers, build riders gated on `c.build(...)`, and two printed damage types
dealt as the first of the two. The helpers it grew for the steps those rows
print are imported rather than written twice.

Two more show up only here. **"Your oath of enmity target" as a printed
Target line** has no header field: `Target` carries a side and a count, so
the header says one creature and the body asks `oath_target`. And **the
engine has no skill checks**, so a printed Effect that is partly a skill
bonus keeps only the half that is a combat effect.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Effect,
    Keyword,
    Melee,
    MoveEnd,
    Ranged,
    TurnEnd,
    TurnStart,
    When,
    Window,
    get,
    power,
    spread,
)
from combat_engine.engine.events import AdjacencyGained, DamageRolled, Hit
from combat_engine.engine.query import allies, distance_between, squares

from .level_1 import DIVINE_IMPLEMENT, DIVINE_WEAPON, _hostile, _near, _step_beside
from .oath import oath_target, swear


def _melee_damage(ctx: dict[str, Any]) -> bool:
    """Was the damage being rolled dealt by a melee row?

    The damage context carries `power` and nothing about how the attack was
    made, so a row answers by its printed reach. The detail a miss carries
    has the half-damage note on the end of it.
    """
    p = get((ctx.get("power") or "").removesuffix(" (half)"))
    return p is not None and p.reach.kind == "melee"


def _blink_near(c: Cast, victim: int, within: int) -> bool:
    """Teleport into a space within `within` squares of a named creature."""
    reach = c.distance(victim) + within
    for sq in sorted(
        spread(squares(c.world, victim), within), key=lambda s: _near(c, s, victim)
    ):
        if c.teleport(reach, to=sq):
            return True
    return False


# -- encounter --------------------------------------------------------------


@power(
    "p6981",
    level=1,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p6981(c: Cast) -> None:
    """"Melee touch" is a reach of 1 the implement carries rather than the
    weapon, so the dice are the power's own. "Willingly moves" is a walk or a
    shift, which is what `MoveEnd` carries in `kind_` -- being shoved is
    somebody else's doing and does not count."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("1d8", c.wis_mod, dtype=DamageType.RADIANT)
    amount, spent = 5 + c.wis_mod, []

    def punish(ev: MoveEnd) -> None:
        if spent or ev.actor != victim or ev.kind_ not in ("walk", "shift", "run"):
            return
        spent.append(1)
        c.flat(amount, dtype=DamageType.RADIANT, on=victim)

    c.watch(MoveEnd, punish, until=When.SONT, on=c.me, label=f"{c.ref} burn")


@power(
    "p6982",
    level=1,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p6982(c: Cast) -> None:
    """The build rider only pays out on the half where the avenger is the
    one that stepped, so the square it left is read before the shift."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.wis_mod)
    movers = [c.me, *sorted(
        a for a in c.allies() if a != c.me and c.adjacent_to(victim, a)
    )]
    who = c.choose(movers, "who takes the free step")
    vacated = c.here if who == c.me else None
    if c.shift(1, who=who) and vacated is not None and c.build("unity"):
        c.slide(1, to=vacated, on=victim)


@power(
    "p6983",
    level=1,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p6983(c: Cast) -> None:
    """"All defenses" is four modifiers with different `what`s, so nothing
    collides; the gate reads who is swinging, which is the key the defence
    context carries."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.wis_mod)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(
            defence,
            2,
            on=c.me,
            until=When.EONT,
            when=lambda ctx: ctx.get("attacker") != victim,
        )


@power(
    "p6984",
    level=1,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT],
    attack=Attack(WIS, vs=AC),
)
def p6984(c: Cast) -> None:
    """"On its turn" is the clause that keeps a push from feeding the
    avenger, so the watcher asks whose turn it is rather than what kind of
    move it was."""
    if c.first:
        c.shift(c.dex_mod if c.build("pursuit") else 1)
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(1), c.wis_mod, dtype=DamageType.RADIANT)
    me, spent = c.me, []

    def feed(ev: MoveEnd) -> None:
        if spent or ev.actor != victim or c.world.turn != victim:
            return
        spent.append(1)
        c.temp_hp(5, on=me)

    c.watch(MoveEnd, feed, until=When.EONT, on=c.me, label=f"{c.ref} vigour")


@power(
    "p7694",
    level=1,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p7694(c: Cast) -> None:
    """"Enters a square adjacent to you" is `AdjacencyGained` with the enemy
    as the one that moved -- `MoveEnd` also fires when the avenger is the one
    that closed the gap, which is not the printed sentence. The slide goes
    into the square just vacated, which is what keeps the avenger beside the
    target at the end of it.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(1), c.wis_mod)
    me = c.me
    steps = c.int_mod if c.build("retribution") else 1
    if steps <= 0:
        return
    spent: list[int] = []

    def give_ground(ev: AdjacencyGained) -> None:
        if spent or ev.actor != me or ev.mover != ev.other:
            return
        if not _hostile(c, ev.other) or c.world.turn != ev.other:
            return
        if not c.may("give ground", who=me):
            return
        spent.append(1)
        vacated = c.here
        if c.shift(steps) and vacated is not None:
            c.slide(steps, to=vacated, on=victim)

    c.watch(
        AdjacencyGained, give_ground, until=When.EONT, on=c.me,
        label=f"{c.ref} ground",
    )


@power(
    "p7695",
    level=1,
    cls="avenger",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p7695(c: Cast) -> None:
    """"Shift 3 squares to a square adjacent to it" names where the step
    ends, so the destination is chosen rather than left to the decider."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage(c.w(2), c.wis_mod)
    c.push(2)
    _step_beside(c, victim, 3)

# -- daily ------------------------------------------------------------------


@power(
    "p10402",
    level=1,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p10402(c: Cast) -> None:
    """The oath is sworn before the roll, which is what makes the class
    feature's second die live for this swing rather than the next one."""
    swear(c)
    if c.strike():
        c.damage(c.w(3), c.wis_mod)
    else:
        c.half_damage(c.w(3), c.wis_mod)


@power(
    "p2914",
    level=1,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.RADIANT, Keyword.ZONE],
    attack=Attack(WIS, vs=AC),
)
def p2914(c: Cast) -> None:
    """"The zone moves with the target" is an aura hung on the target rather
    than a set of squares: `c.aura(on=)` follows whatever it is given, and a
    fixed burst would sit where the creature used to be."""
    if c.strike():
        c.damage(c.w(2), c.wis_mod, dtype=DamageType.RADIANT)
    victim = c.target
    if not c.first or victim is None:
        return
    me = c.me
    ring = c.aura(2, label=c.ref, until=When.ENCOUNTER, on=victim)

    def sear(ev: Hit) -> None:
        if ev.attacker != me or ev.target not in c.world.zones.occupants(ring):
            return
        c.flat(c.roll("1d6"), dtype=DamageType.RADIANT, on=ev.target)

    c.watch(Hit, sear, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} glow")


@power(
    "p2915",
    level=1,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.LIGHTNING, Keyword.HEALING],
    attack=Attack(WIS, vs=REF),
)
def p2915(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.wis_mod, dtype=DamageType.LIGHTNING)
    else:
        c.half_damage("2d10", c.wis_mod, dtype=DamageType.LIGHTNING)
    if c.first and c.may("spend a healing surge", who=c.me):
        c.surge(on=c.me)


@power(
    "p3590",
    level=1,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.TELEPORTATION],
    attack=Attack(WIS, vs=AC),
)
def p3590(c: Cast) -> None:
    """The blink is offered at the start of each turn, which is the moment
    the printed condition is measured; the second clause takes the whole
    arrangement down at the end of a turn spent too far off, so the two
    watchers come down together.
    """
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    else:
        c.half_damage(c.w(2), c.wis_mod)
    me = c.me

    def blink(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        if distance_between(c.world, me, victim) <= 3:
            return
        if c.may("blink after it", who=me):
            _blink_near(c, victim, 3)

    hunt = c.watch(
        TurnStart, blink, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} hunt"
    )

    def slipped(ev: TurnEnd) -> None:
        if ev.actor == me and distance_between(c.world, me, victim) > 3:
            c.world.effects.end(hunt, "ended the turn too far off")

    away = c.watch(
        TurnEnd, slipped, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} slip"
    )
    hunt.on_end.append(lambda: c.world.effects.end(away, "the hunt is over"))


@power(
    "p3592",
    level=1,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p3592(c: Cast) -> None:
    """The Athletics third of the Effect has nowhere to go -- there are no
    skill checks in the engine -- so the speed and the melee damage are the
    whole of it here."""
    if c.strike():
        c.damage(c.w(3), c.wis_mod)
    else:
        c.half_damage(c.w(3), c.wis_mod)
    if not c.first:
        return
    c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER)
    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, when=_melee_damage)


@power(
    "p6985",
    level=1,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT, Keyword.THUNDER],
    attack=Attack(WIS, vs=FORT),
)
def p6985(c: Cast) -> None:
    """The standing reroll has nothing to reroll with: `DamageRolled` carries
    the number and not the dice that made it, so a second result cannot be
    rolled. The attack is written and the rider is in the report."""
    if c.strike():
        c.damage("2d10", c.wis_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage("2d10", c.wis_mod, dtype=DamageType.RADIANT)


@power(
    "p6986",
    level=1,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p6986(c: Cast) -> None:
    """"Each Failed Saving Throw" is `escalate`, which runs on every failed
    save rather than the first. The Aftereffect follows the hold going
    whichever way it went, which is `on_end` and not a second escalation."""
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.half_damage("2d10", c.wis_mod, dtype=DamageType.RADIANT)
        c.immobilized(until=When.EONT)
        return
    c.damage("2d10", c.wis_mod, dtype=DamageType.RADIANT)

    def burn(eff: Effect) -> None:
        c.flat(5, dtype=DamageType.RADIANT, on=eff.owner)

    held = c.condition(
        Condition.IMMOBILIZED, until=When.SAVE_ENDS, escalate=burn
    )
    if held is not None:
        held.on_end.append(lambda: c.slowed(until=When.SAVE_ENDS, on=victim))


@power(
    "p6988",
    level=1,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p6988(c: Cast) -> None:
    """The Effect is printed before the attack and covers this row's own
    damage, so the watcher goes up first. It adds to `DamageRolled.amount`,
    which is the one moment the number exists and can still be changed --
    a "damage" modifier would collide with every other power bonus."""
    me = c.me
    if c.first:

        def swell(ev: DamageRolled) -> None:
            if ev.source != me or ev.amount <= 0:
                return
            near = [
                a
                for a in allies(c.world, me)
                if a != me and distance_between(c.world, me, a) <= 2
            ]
            ev.amount += 2 * len(near)

        c.watch(
            DamageRolled, swell, until=When.EONT, window=Window.BEFORE, on=c.me,
            label=f"{c.ref} company",
        )
    if c.strike():
        c.damage(c.w(3), c.wis_mod)
    else:
        c.half_damage(c.w(3), c.wis_mod)


@power(
    "p6989",
    level=1,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.THUNDER],
    attack=Attack(WIS, vs=AC),
)
def p6989(c: Cast) -> None:
    """The secondary is an Effect line, so the burst goes off whether the
    primary landed or not, and it rolls longhand: the header holds the
    primary, which is what the card shows."""
    primary = c.target
    if primary is None:
        return
    if c.strike():
        c.damage(c.w(1), c.wis_mod)
        c.damage("1d10", dtype=DamageType.THUNDER)
    else:
        c.half_damage(c.w(1), c.wis_mod)
        c.half_damage("1d10", dtype=DamageType.THUNDER)
    if not c.first:
        return
    for foe in sorted(f for f in c.within(2, side="enemy") if f != primary):
        if c.attack(c.wis_, FORT, on=foe):
            c.damage("1d6", c.wis_mod, dtype=DamageType.THUNDER, on=foe)
            c.push(2, on=foe)


@power(
    "p6990",
    level=1,
    cls="avenger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p6990(c: Cast) -> None:
    """The printed Target is the oath target outright, so the body asks for
    it rather than taking whoever was pointed at. The flight is the caster's
    own move landing beside that creature, which is what `c.run_at` does;
    the mode and the reprieve from opportunity attacks are granted first so
    the walk is made under them. Sworn against nobody, the row does nothing.
    """
    if not c.first:
        return
    victim = oath_target(c)
    if victim is None:
        return
    c.mode("fly", 6, until=When.EOT, on=c.me)
    c.no_provoke(until=When.EOT)
    c.run_at(victim)
    if c.strike(on=victim):
        c.damage(c.w(3), c.wis_mod, on=victim)
    else:
        c.half_damage(c.w(3), c.wis_mod, on=victim)
