"""Cleric, level 9: the daily attacks printed after the first book.

`level_9.py` holds the four that came first; these are the rest. The shadow
keyword has no `Keyword` member and nothing reads one, so the rows printed
with it are declared with the keywords the engine has.

Two of them leave a zone standing, and both hang their listeners on the
zone's own effect -- `level_9.py`'s arrangement -- so the watching dies with
the zone rather than outliving it.

`p3667`'s prison is `Condition.REMOVED`: on the board, out of the fight,
standing where it was. That is what makes "reappears in its original space"
need no arranging at all, the reading `level_10.py`'s `p955` settled.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    DAILY,
    EACH_ENEMY,
    FORT,
    MINOR,
    ONE_CREATURE,
    STANDARD,
    STR,
    WILL,
    WIS,
    Attack,
    AttackDeclared,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageType,
    Effect,
    Health,
    Hit,
    Keyword,
    Melee,
    Ranged,
    TurnEnd,
    When,
    World,
    ZoneEntered,
    get,
    power,
)
from combat_engine.engine.events import ZoneExited
from combat_engine.engine.query import adjacent, hidden_from
from combat_engine.engine.zones import Zone

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]
DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]


def _bloodied(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return health is not None and health.bloodied


def _melee_row(ctx: dict[str, Any]) -> bool:
    """"A bonus to melee damage rolls", read off the attacking row's reach.

    Most melee rows carry no melee *keyword*, so asking for one would
    silently never pay; and the damage context carries `power` but no
    `attacker` and no `ranged`, so the row is the only thing there is to
    ask.
    """
    row = get(ctx.get("power") or "")
    return row is not None and row.reach is not None and row.reach.kind == "melee"


@power(
    "p11620",
    level=9,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p11620(c: Cast) -> None:
    """"Each enemy in the burst you can see" -- an enemy the cleric cannot
    see is not a target, so it is skipped rather than swung at and missed.
    """
    if c.target is None or c.me in hidden_from(c.world, c.target):
        return
    if c.strike():
        c.damage(c.w(3), c.str_mod)
        c.grants_advantage(to="allies", until=When.SAVE_ENDS)
    else:
        c.half_damage(c.w(3), c.str_mod)
        c.grants_advantage(to="allies", until=When.EONT)


@power(
    "p12615",
    level=9,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p12615(c: Cast) -> None:
    """Only the melee damage half of the printed bonus is written: the
    Strength and Athletics halves are checks this engine does not roll.

    The Effect block runs before the swing, because it is owed whether or
    not there is anything in the burst at all.
    """
    if c.first:
        c.bonus(
            "damage", c.con_mod, on=c.me, until=When.ENCOUNTER, when=_melee_row
        )
    if c.strike():
        c.damage(c.w(2), c.wis_mod)


@power(
    "p12616",
    level=9,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p12616(c: Cast) -> None:
    """The five-per-bloodied-ally rider is a second packet rather than part
    of the dice, so it is not doubled by a critical -- which is right: a
    critical maxes the dice, and this is not dice.
    """
    hurt = [f for f in c.within(5, side="ally") if f != c.me and c.bloodied(f)]
    if c.strike():
        c.damage(c.w(3), c.wis_mod)
        if hurt:
            c.flat(5 * len(hurt))
    else:
        c.half_damage(c.w(3), c.wis_mod)


@power(
    "p12617",
    level=9,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(WIS, vs=AC),
)
def p12617(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.wis_mod)
    victim = c.target
    if victim is None:
        return

    def bite(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == victim or ev.actor not in c.enemies():
            return
        if adjacent(c.world, victim, ev.actor):
            c.flat(10, on=ev.actor)

    c.watch(TurnEnd, bite, until=When.ENCOUNTER, on=victim, label=f"{c.ref} bites")


@power(
    "p13928",
    level=9,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=AC),
)
def p13928(c: Cast) -> None:
    """The hold ends itself: the printed line stops when the target ends a
    turn with nobody beside it, which no duration expresses, so the watcher
    that pays out is also the thing that tears the effect down.
    """
    if c.strike():
        c.damage(c.w(2), c.wis_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage(c.w(2), c.wis_mod, dtype=DamageType.PSYCHIC)
    victim = c.target
    if victim is None:
        return
    hold: list[Effect] = []

    def crowd(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != victim:
            return
        near = [f for f in c.allies() if adjacent(c.world, f, victim)]
        if near:
            c.flat(5 * len(near), dtype=DamageType.PSYCHIC, on=victim)
        elif hold:
            c.world.effects.end(hold[0], "nobody was beside it")

    hold.append(
        c.watch(TurnEnd, crowd, until=When.ENCOUNTER, on=victim, label=c.ref)
    )


@power(
    "p13929",
    level=9,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.NECROTIC, Keyword.ZONE],
    attack=Attack(WIS, vs=WILL),
)
def p13929(c: Cast) -> None:
    """"Enemies grant combat advantage **while** in the zone" is a hold per
    creature that comes and goes with the zone's own entered and exited
    events, plus whoever is already standing in it when it is laid.
    """
    if c.first:
        zone = c.zone(c.area(), label=c.ref, until=When.ENCOUNTER)
        held: dict[int, Effect] = {}

        def expose(who: int) -> None:
            if who in held or who not in c.enemies():
                return
            granted = c.grants_advantage(
                on=who, to="allies", until=When.ENCOUNTER
            )
            if granted is not None:
                held[who] = granted

        def arrived(ev: ZoneEntered) -> None:
            if ev.zone == zone:
                expose(ev.actor)

        def left(ev: ZoneExited) -> None:
            if ev.zone != zone:
                return
            granted = held.pop(ev.actor, None)
            if granted is not None:
                c.world.effects.end(granted, "left the zone")

        for standing in c.world.zones.occupants(zone):
            expose(standing)
        laid = c.world.get(zone, Zone)
        subs = [
            c.world.bus.on(ZoneEntered, arrived, owner=c.me),
            c.world.bus.on(ZoneExited, left, owner=c.me),
        ]
        if laid is not None and laid.effect is not None:
            laid.effect.subs.extend(subs)
    if c.strike():
        c.damage("2d8", c.wis_mod, dtype=DamageType.NECROTIC)
    else:
        c.half_damage("2d8", c.wis_mod, dtype=DamageType.NECROTIC)


#: The creature types the prison holds hardest, from the printed line.
_HARD_TO_ESCAPE = frozenset(
    {"aberrant", "elemental", "fey", "immortal", "shadow"}
)


@power(
    "p3667",
    level=9,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=WILL),
)
def p3667(c: Cast) -> None:
    """The Aftereffect hangs on the hold's `on_end`, so it begins whichever
    way the hold went -- which is the shape `rogue/level_5.py` settled.

    The penalty goes on the effect's own `save_mod` rather than on the
    creature: it is a penalty to saves *against this effect* and a
    creature-wide one would slow every other hold it is carrying.
    """
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.condition(Condition.REMOVED, until=When.EONT, on=victim)
        return

    def afterwards() -> None:
        c.dazed(on=victim, until=When.EOTNT)

    hard = bool(c.kinds_of(victim) & _HARD_TO_ESCAPE)
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=f"{c.ref} prison",
        conditions=(Condition.REMOVED,),
        save_mod=-5 if hard else -2,
        on_end=[afterwards],
    )


@power(
    "p7097",
    level=9,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.HEALING],
    attack=Attack(STR, vs=AC),
    requires=_bloodied,
    requires_text="you must be bloodied",
)
def p7097(c: Cast) -> None:
    """Each surge is its owner's, so each of them is asked separately.
    `c.within(5, side="ally")` already counts the caster, which is the
    printed "you and each ally".
    """
    if c.strike():
        c.damage(c.w(2), c.str_mod)
    for friend in sorted(c.within(5, side="ally")):
        if c.may("spend a healing surge", who=friend):
            c.surge(on=friend)


@power(
    "p7098",
    level=9,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*DIVINE_WEAPON, Keyword.HEALING, Keyword.RADIANT, Keyword.ZONE],
    attack=Attack(STR, vs=FORT),
)
def p7098(c: Cast) -> None:
    """Ten flat hit points, no surge: the printed line spends nothing.

    The listener rides on the zone's effect, so sustaining keeps it and
    letting the zone lapse takes it with it.
    """
    if c.first:
        zone = c.zone(c.area(), label=c.ref, until=When.SUSTAIN, sustain=MINOR)

        def blessed(ev: Hit) -> None:
            if ev.attacker not in c.allies() or ev.target not in c.enemies():
                return
            if ev.attacker in c.world.zones.occupants(zone):
                c.heal(10, on=ev.attacker)

        laid = c.world.get(zone, Zone)
        sub = c.world.bus.on(Hit, blessed, owner=c.me)
        if laid is not None and laid.effect is not None:
            laid.effect.subs.append(sub)
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage(c.w(2), c.str_mod, dtype=DamageType.RADIANT)


@power(
    "p7099",
    level=9,
    cls="cleric",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=WILL),
)
def p7099(c: Cast) -> None:
    """The -5 sits on the hold's own `save_mod` and is lifted by the first
    swing anybody on the cleric's side takes at the target, which is the
    printed "until you or any ally attacks the target". Read on
    `AttackDeclared`, so an attack that misses still lifts it.
    """
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.cannot_attack(on=victim, until=When.EONT)
        return
    hold = c.cannot_attack(on=victim, until=When.SAVE_ENDS)
    if hold is None:
        return
    hold.save_mod -= 5
    lifted: list[bool] = []

    def disturbed(ev: AttackDeclared) -> None:
        if lifted or ev.target != victim:
            return
        if ev.attacker != c.me and ev.attacker not in c.allies():
            return
        lifted.append(True)
        hold.save_mod += 5

    hold.subs.append(c.world.bus.on(AttackDeclared, disturbed, owner=c.me))
