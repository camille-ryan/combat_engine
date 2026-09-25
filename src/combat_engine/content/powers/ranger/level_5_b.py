"""Ranger, level 5: the rows from the later books.

Three shapes recur here and are worth stating once.

**"Ranged weapon" needs no Requirement of its own.** A row carrying
`Keyword.WEAPON` with a ranged reach is already gated on a bow being in
hand -- `Power.can_branch` asks `gear.ranged` -- so declaring one as well
only risks hiding the row from `chargen.build_for`, which reads the refusal
text. The rows that print "a thrown weapon" are the exception: no weapon
carries a thrown flag, so those declare `thrown_by_hand=True`, which asks
for a melee weapon in hand instead, which is what a thrown weapon is.

**A row whose printed Requirement is the charge** carries `charges=True`, so
reach is measured after the run, and the body walks and raises `c.charge`
itself -- `c.charge_at` reaches its swing through `use`, and `use` will not
re-enter a row already in flight.

**The beast companion is not modelled.** Where it is only a rider on a row
the ranger swings, the rider is dropped and said so; where the attack itself
is the beast's, the row is absent and in the report.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    DEX,
    ENCOUNTER,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    SELF,
    STANDARD,
    STR,
    Attack,
    Cast,
    Condition,
    Event,
    Gear,
    Keyword,
    Melee,
    MeleeOrRanged,
    Ranged,
    Target,
    Trigger,
    TurnEnd,
    When,
    World,
    distance,
    get,
    power,
)
from combat_engine.engine.events import Hit, Miss
from combat_engine.engine.query import cover_between, line_of_effect, team
from combat_engine.engine.query import squares as squares_of

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]
MARTIAL_RANGED = [Keyword.MARTIAL, Keyword.WEAPON, Keyword.RANGED]
MARTIAL = [Keyword.MARTIAL]

_QUARRY_TARGET = Target("enemy", 1, label="One creature designated as your quarry")

_ENEMY_CLOSES = "an enemy moves adjacent to you"
_ENEMY_ENDS_BESIDE = "an enemy you can see ends its turn adjacent to you"


def _two_melee(world: World, eid: int) -> bool:
    """"You must be wielding two melee weapons" -- two that are not fired."""
    gear = world.get(eid, Gear)
    if gear is None:
        return False
    return len([w for w in gear.weapons if w.ranged is None]) >= 2


def _has_ranged(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return gear is not None and gear.ranged is not None


def _enemy_moved_next_to_me(world: World, me: int, ev: Event) -> bool:
    """The *mover* is the enemy and the one it reached is me.

    The reading `level_6.py` and `level_10.py` already settled: every step
    emits the pair both ways round, so reading `actor` alone would also
    answer the ranger walking up to somebody.
    """
    mover = getattr(ev, "actor", None)
    if mover is None or getattr(ev, "other", None) != me:
        return False
    return team(world, mover) is not team(world, me)


def _enemy_ended_beside_me(world: World, me: int, ev: Event) -> bool:
    foe = getattr(ev, "actor", None)
    if foe is None or foe == me or getattr(ev, "ghost", False):
        return False
    if team(world, foe) is team(world, me):
        return False
    if not line_of_effect(world, me, foe):
        return False
    return any(
        distance(mine, theirs) <= 1
        for mine in squares_of(world, me)
        for theirs in squares_of(world, foe)
    )


def _clear_of_enemies(c: Cast, squares_: int) -> None:
    """Shift, refusing any square that ends up next to an enemy.

    "You must not end the shift adjacent to any enemy" is a condition on the
    destination, and `c.shift` hands the choice to the decider, which is
    happy to step straight back into reach.
    """
    held = [sq for foe in c.enemies() for sq in squares_of(c.world, foe)]
    away = sorted(
        s
        for s in c.world.reachable_squares(c.me, squares_)
        if not any(distance(s, at) <= 1 for at in held)
    )
    if away:
        c.shift(squares_, to=away[0])


def _melee_row(ref: str) -> bool:
    p = get(ref or "")
    return p is not None and p.reach.kind == "melee"


@power(
    "p10156",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    charges=True,
)
def p10156(c: Cast) -> None:
    """The square the target is pushed out of is read before the push.

    `c.there` is the target's square now, so it has to be taken while the
    creature is still standing in it -- afterwards it is the square it was
    pushed to, and the shift would follow it rather than take its place.

    The Effect line is the beast companion's charge, and the companion is
    not modelled; it is dropped rather than approximated.
    """
    victim = c.target
    if victim is None:
        return
    c.run_at(victim)
    c.charge = True
    if not c.strike():
        return
    c.damage(c.w(2), c.str_mod)
    vacated = c.there
    c.push(1)
    c.shift(1, to=vacated)


@power(
    "p10615",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    requires=_two_melee,
    requires_text="needs two melee weapons",
)
def p10615(c: Cast) -> None:
    """Main weapon, off-hand, then the off-hand thrown at somebody else.

    The printed Requirement is a thrown weapon in the off hand and a melee
    weapon in the main one. No weapon carries a thrown flag, so what is
    checked is the pair in the hands, which is the half of the sentence the
    model can hold.

    The tertiary throw is rolled longhand -- it is aimed at a creature the
    header never named -- and does not provoke, which is what the printed
    line says of it rather than of the row as a whole.
    """
    if c.strike():
        c.damage(c.w(1, hand="main"), c.str_mod)
    if c.attack(c.str_, AC):
        c.damage(c.w(1, hand="off"), c.str_mod)

    primary = c.target
    pool = [e for e in c.enemies() if e != primary and c.can_see(e)]
    second = c.choose(pool, f"{c.ref}: who the throw is aimed at") if pool else None
    if second is None:
        return
    if c.attack(c.str_, AC, on=second):
        c.damage(c.w(2, hand="off"), c.str_mod, on=second)
        c.penalty("attack", 2, on=second, until=When.SAVE_ENDS)


@power(
    "p10616",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
    charges=True,
)
def p10616(c: Cast) -> None:
    """Naming the quarry is an Effect line, so it happens before the run and
    whether or not the swing lands. The companion's half of the charge is
    dropped -- the beast is not modelled."""
    victim = c.target
    if victim is None:
        return
    c.quarry(on=victim)
    c.run_at(victim)
    c.charge = True
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    else:
        c.half_damage(c.w(2), c.str_mod)


@power(
    "p10617",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=_QUARRY_TARGET,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p10617(c: Cast) -> None:
    """The printed Target is the quarry, and the board never names one, so
    the restriction is declared on the card and not gated in the body.

    "Until the target is no longer your quarry" is the encounter: `c.quarry`
    holds for that long unless something ends it, and nothing here does.
    """
    if c.strike():
        c.damage(c.w(3), c.dex_mod)
    else:
        c.half_damage(c.w(3), c.dex_mod)

    victim = c.target
    me = c.me

    def trip(ev: Hit) -> None:
        if ev.attacker != me or ev.target != victim or not _melee_row(ev.power):
            return
        c.prone(on=victim)

    c.watch(Hit, trip, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p10618",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.STANCE],
)
def p10618(c: Cast) -> None:
    """Hit *or* miss, so the riposte hangs off both events.

    Each watch is encounter-clocked and ended from the stance, the
    arrangement `level_10.py`'s `p718` settled: a second stance-clocked
    effect confuses `Effects.stance_of`.
    """
    stance = c.stance(label=c.ref)
    me = c.me

    def riposte(ev: Any) -> None:
        foe = getattr(ev, "attacker", None)
        if foe is None or getattr(ev, "target", None) != me:
            return
        p = get(getattr(ev, "power", "") or "")
        if p is None or p.reach.kind not in ("melee", "close_burst", "close_blast"):
            return
        if not c.may("strike back", who=me):
            return
        c.basic(on=foe)
        _clear_of_enemies(c, 3)

    for kind in (Hit, Miss):
        watching = c.watch(kind, riposte, until=When.ENCOUNTER, label=c.ref)
        stance.on_end.append(
            lambda w=watching: c.world.effects.end(w, "stance ended")
        )


@power(
    "p10619",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p10619(c: Cast) -> None:
    """The damage context carries no `attacker` and no reach of its own, so
    "melee damage rolls against the target" is gated on the power ref in the
    context, which is what `reach.kind` can be looked up from."""
    if not c.strike():
        return
    c.damage(c.w(2), c.dex_mod + c.wis_mod)
    victim = c.target

    def closing(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == victim and _melee_row(ctx.get("power") or "")

    c.bonus("damage", c.wis_mod, on=c.me, until=When.ENCOUNTER, when=closing)


@power(
    "p10620",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
)
def p10620(c: Cast) -> None:
    """The Special line offers the same row as an immediate reaction when an
    adjacent enemy bloodies you or crits you. A header holds one action, and
    there is no field for a second, so the printed standard action is what is
    declared; the alternative is in the report."""
    if c.strike():
        c.damage(c.w(3), c.str_mod)
    else:
        c.half_damage(c.w(3), c.str_mod)
    if c.may("spend a healing surge", who=c.me):
        c.surge(on=c.me)


@power(
    "p10701",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(DEX, vs=AC),
)
def p10701(c: Cast) -> None:
    """The standing shot is armed on the target's own turn ending.

    The printed effect also ends if the target has cover at the end of any
    of *your* turns; that is a second clock on the same hold, and it is left
    off -- the cover test at the moment of the shot is what decides whether
    anything happens, and it is the half that has teeth.
    """
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    else:
        c.half_damage(c.w(2), c.dex_mod)

    victim = c.target
    me = c.me

    def snipe(ev: TurnEnd) -> None:
        if ev.actor != victim or ev.ghost:
            return
        if cover_between(c.world, me, victim, ranged=True):
            return
        if c.may("take the shot", who=me):
            c.basic(on=victim, ranged=True)

    c.watch(TurnEnd, snipe, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "p13600",
    level=5,
    cls="ranger",
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
    trigger=_ENEMY_ENDS_BESIDE,
    on=Trigger(TurnEnd, when=_enemy_ended_beside_me, text=_ENEMY_ENDS_BESIDE),
)
def p13600(c: Cast) -> None:
    c.shift(c.wis_mod)


@power(
    "p16480",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
)
def p16480(c: Cast) -> None:
    """"Blinded and cannot shift" is one hold carrying two conditions, so one
    save ends both, as printed. The free-action step is clocked off that same
    hold rather than given a duration of its own -- "until this effect ends"
    is what the printed line measures it by."""
    if not c.strike():
        c.half_damage(c.w(1), c.attack_mod)
        c.penalty("attack", 2, until=When.SAVE_ENDS)
        return
    c.damage(c.w(1), c.attack_mod)
    held = c.condition(Condition.BLINDED, Condition.ROOTED, until=When.SAVE_ENDS)
    if held is None:
        return

    victim = c.target
    me = c.me

    def sidestep(ev: Miss) -> None:
        if ev.attacker == victim and c.may("step aside", who=me):
            c.shift(1)

    watching = c.watch(Miss, sidestep, until=When.ENCOUNTER, on=me, label=c.ref)
    held.on_end.append(lambda: c.world.effects.end(watching, "the blinding ended"))


@power(
    "p16486",
    level=5,
    cls="ranger",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_RANGED,
    attack=Attack(STR, vs=AC),
    attack_alt=Attack(DEX, vs=AC),
)
def p16486(c: Cast) -> None:
    """The Effect line takes away blindsight and tremorsense. Neither is a
    thing a creature has here -- sight is line of effect and nothing else --
    so there is nothing to take, and the clause is dropped."""
    if c.strike():
        c.damage(c.w(2), c.attack_mod)
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(2), c.attack_mod)

