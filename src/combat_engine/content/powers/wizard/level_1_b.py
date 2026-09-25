"""Wizard, level 1: the attacks printed in the books after the first.

Three shapes recur often enough to be written once.

`_teeth` is a zone that bites whoever *ends* a turn in it. `c.burns` is the
other pair of clauses -- entering and *starting* -- so a row printing "ends
its turn there" cannot use it, and the rows that print both get the entering
half as well. Subscribed after the zone is laid, so the creatures the burst
caught are not counted as having walked in.

"Cannot make opportunity attacks" is a veto on `OpportunityWindow` hung on
whatever hold the printed line gives it. `c.no_provoke` is the other
direction: it stops a creature *provoking* rather than answering.

`_reachable_from` is who a granted melee swing could actually land on, which
is the half of "a creature of your choice" the choice cannot express.

Concealment has no expression anywhere here -- it is a -2 an attacker takes
and there is nowhere to hang one on a square -- so p13977 lays its zone,
applies its daze, and says the rest out loud.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    INT,
    MINOR,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    AttackDeclared,
    Cast,
    CloseBlast,
    Condition,
    DamageApplied,
    DamageType,
    Effect,
    Healed,
    Keyword,
    MoveEnd,
    OpportunityWindow,
    Ranged,
    TurnEnd,
    UpTo,
    When,
    Window,
    ZoneEntered,
    power,
    spread,
)
from combat_engine.engine.components import Defences
from combat_engine.engine.zones import Zone

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


def _teeth(
    c: Cast, zone: int, amount: int, dtype: DamageType, *, entering: bool = False
) -> None:
    """A zone that bites an enemy for finishing a turn in it, once per turn."""
    struck: dict[int, int] = {}

    def bite(who: int) -> None:
        if struck.get(who) == c.world.round or who not in c.enemies():
            return
        struck[who] = c.world.round
        c.flat(amount, dtype=dtype, on=who)

    def dusk(ev: TurnEnd) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(zone):
            bite(ev.actor)

    def walked_in(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            bite(ev.actor)

    subs = [c.world.bus.on(TurnEnd, dusk)]
    if entering:
        subs.append(c.world.bus.on(ZoneEntered, walked_in))
    held = c.world.get(zone, Zone)
    if held is not None and held.effect is not None:
        held.effect.subs.extend(subs)


def _no_opportunity(c: Cast, held: Effect | None, who: int, *, only_me: bool = False) -> None:
    """Refuse this creature the opening, for as long as the hold lasts."""
    if held is None:
        return

    def refuse(ev: OpportunityWindow) -> None:
        if ev.actor == who and (not only_me or ev.provoker == c.me):
            ev.cancel("cannot make opportunity attacks")

    held.subs.append(
        c.world.bus.on(OpportunityWindow, refuse, window=Window.BEFORE, owner=c.me)
    )


def _reachable_from(c: Cast, swinger: int) -> list[int]:
    """Who a granted melee swing could actually land on."""
    return sorted(f for f in c.enemies() if f != swinger and c.adjacent_to(swinger, f))


@power(
    "p10069",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.ILLUSION],
    attack=Attack(INT, vs=WILL),
)
def p10069(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("1d8", c.int_mod, dtype=DamageType.PSYCHIC)
    for who in c.within(1, of=victim, side="enemy"):
        if who != victim:
            c.flat(c.int_mod, dtype=DamageType.PSYCHIC, on=who)


@power(
    "p10137",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.PSYCHIC, Keyword.ILLUSION],
    attack=Attack(INT, vs=WILL),
)
def p10137(c: Cast) -> None:
    """No ability modifier on the damage line, which is what the printed 1d6
    says and is unusual enough to be worth not "correcting"."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("1d6", dtype=DamageType.PSYCHIC)
    _no_opportunity(c, c.effect(f"{c.ref} no openings", until=When.EONT), victim)


@power(
    "p10138",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CHARM],
    attack=Attack(INT, vs=WILL),
)
def p10138(c: Cast) -> None:
    """The slide comes first, so the swing the Effect line grants is offered
    from wherever the target has been put -- which is the point of sliding it.

    "A creature of your choice" is narrowed to one the charmed enemy can
    actually reach: a melee basic swung at somebody across the room is
    refused by `use` and the line pays out nothing.
    """
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.slide(3)
        c.dazed()
    near = _reachable_from(c, victim)
    quarry = c.choose(near, f"{c.ref}: who it swings at") if near else None
    if quarry is not None:
        c.grant_attack(victim, on=quarry, damage_bonus=2)


@power(
    "p10417",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.ZONE],
    attack=Attack(INT, vs=REF),
)
def p10417(c: Cast) -> None:
    """"The zone moves with the target" is an aura on the target rather than
    a zone, which is the one difference between the two.

    The Active Familiar rider is dropped: nothing in the engine is a familiar.
    """
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("2d8", c.int_mod, dtype=DamageType.COLD)
    ring = c.aura(2, label=c.ref, until=When.EONT, on=victim)
    cold = c.world.get(ring, Zone)
    if cold is None:
        return
    cold.difficult = True
    if cold.effect is not None:
        # `c.aura(on=...)` makes the creature the aura follows its source as
        # well, so "until the end of *your* next turn" would be measured off
        # the target's turn. The zone is the wizard's; it merely rides.
        cold.effect.source = c.me
        cold.effect.clock = c.me
        cold.effect.latch = c.world.turn == c.me
    _teeth(c, ring, 5, DamageType.COLD)


@power(
    "p11030",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(3),
    keywords=[*ARCANE_IMPLEMENT],
    attack=Attack(INT, vs=REF),
)
def p11030(c: Cast) -> None:
    if c.strike():
        c.damage("2d8" if len(c.targets) == 1 else "1d8", c.int_mod)


@power(
    "p11031",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.THUNDER, Keyword.ZONE],
    attack=Attack(INT, vs=REF),
)
def p11031(c: Cast) -> None:
    """Walking the zone six squares with a move action, and the free-standing
    minor that slides without sustaining, both have no expression: a zone's
    squares are fixed where they were laid, and only the sustain has a hook.
    """
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.THUNDER)
        c.slide(1)
    else:
        c.half_damage("2d6", c.int_mod, dtype=DamageType.THUNDER)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    zone = c.zone(area, label=c.ref, until=When.SUSTAIN, sustain=MINOR)

    def gust() -> None:
        inside = c.world.zones.occupants(zone)
        who = c.choose(inside, f"{c.ref}: who the wind moves") if inside else None
        if who is not None:
            c.slide(2, on=who)

    held = c.world.get(zone, Zone)
    c.on_sustain(held.effect if held is not None else None, gust)


@power(
    "p12547",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(INT, vs=FORT),
)
def p12547(c: Cast) -> None:
    """The watch is held by the target, so "before the end of the target's
    next turn" is clocked on the right creature."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("1d10", c.int_mod, dtype=DamageType.FIRE)

    def dusk(ev: TurnEnd) -> None:
        if not ev.ghost and ev.actor != victim and c.adjacent_to(victim, ev.actor):
            c.flat(c.int_mod, dtype=DamageType.FIRE, on=ev.actor)

    c.watch(TurnEnd, dusk, until=When.EOTNT, on=victim, label=c.ref)


@power(
    "p12732",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=[*ARCANE_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(INT, vs=REF),
)
def p12732(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.LIGHTNING)


@power(
    "p12733",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CLOSE, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(INT, vs=WILL),
)
def p12733(c: Cast) -> None:
    if c.strike():
        c.damage(0, c.int_mod, dtype=DamageType.PSYCHIC)
        c.push(3)


@power(
    "p12734",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.COLD],
    attack=Attack(INT, vs=REF),
)
def p12734(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.COLD)
        if c.may("slide it 1 square", who=c.me):
            c.slide(1)


@power(
    "p12735",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CHARM],
    attack=Attack(INT, vs=WILL),
)
def p12735(c: Cast) -> None:
    """The swing is only worth choosing when there is something in reach, so
    the slide is offered alone when there is not -- which is the choice the
    printed line would leave a player with anyway."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    near = _reachable_from(c, victim)
    if near and c.choose(["it swings", "it is moved"], f"{c.ref}: which") == "it swings":
        quarry = c.choose(near, f"{c.ref}: who it swings at")
        if quarry is not None:
            c.grant_attack(victim, on=quarry, attack_bonus=4)
            return
    c.slide(3)


@power(
    "p12736",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.ILLUSION],
    attack=Attack(INT, vs=WILL),
)
def p12736(c: Cast) -> None:
    """One hold carries both halves, so they end together."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("1d8", c.int_mod, dtype=DamageType.PSYCHIC)
    _no_opportunity(c, c.grants_advantage(until=When.EONT, to="allies"), victim)


@power(
    "p12737",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.ILLUSION],
    attack=Attack(INT, vs=WILL),
)
def p12737(c: Cast) -> None:
    """"If the target moves" is one payment, not one per step, so the watch is
    spent by the first move that finishes. `MoveEnd` rather than `MoveStart`:
    the latter fires before anything has happened."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("1d8", c.int_mod, dtype=DamageType.PSYCHIC)

    def stirred(ev: MoveEnd) -> None:
        if ev.actor == victim:
            c.flat(5, dtype=DamageType.PSYCHIC, on=victim)

    c.watch(MoveEnd, stirred, until=When.EONT, once=True, label=c.ref)


@power(
    "p12739",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.ILLUSION],
    attack=Attack(INT, vs=WILL),
)
def p12739(c: Cast) -> None:
    """"Unable to charge" is a refusal at the declaration keyed on the charge
    flag the attack carries. `c.no_basic` is the wrong instrument: it takes
    away opportunity attacks and granted swings with it.

    The run itself is not prevented -- `actions.legal` offers a charge without
    consulting anything -- so the creature spends the move and the swing is
    refused. That is as close as the surface gets to the printed line.
    """
    victim = c.target
    if victim is None:
        return
    held = c.dazed() if c.strike() else c.effect(f"{c.ref} no charge", until=When.EONT)
    if held is None:
        return

    def refuse(ev: AttackDeclared) -> None:
        if ev.attacker == victim and getattr(ev, "charge", False):
            ev.cancel("unable to charge")

    held.subs.append(
        c.world.bus.on(AttackDeclared, refuse, window=Window.BEFORE, owner=c.me)
    )


@power(
    "p12740",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.FIRE, Keyword.ZONE],
    attack=Attack(INT, vs=REF),
)
def p12740(c: Cast) -> None:
    if c.strike():
        c.damage("3d8", c.int_mod, dtype=DamageType.FIRE)
    else:
        c.half_damage("3d8", c.int_mod, dtype=DamageType.FIRE)
    if not c.first:
        return
    area = c.area()
    if not area:
        return
    _teeth(c, c.zone(area, label=c.ref, until=When.ENCOUNTER), 5, DamageType.FIRE, entering=True)


@power(
    "p13741",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA],
    attack=Attack(INT, vs=FORT),
)
def p13741(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.int_mod)
        c.slowed()


@power(
    "p13742",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POLYMORPH],
    attack=Attack(INT, vs=FORT),
)
def p13742(c: Cast) -> None:
    """The shape is the whole row: no damage on either line, and the hit and
    the miss differ only in how long it lasts.

    `Condition.SHAPED` is "no standard actions" and the daze is the rest of
    "the only actions it can take are to move its speed or shift".
    `c.form` is the wrong instrument -- it shapes the caster, not a victim.
    """
    victim = c.target
    if victim is None:
        return
    held = c.condition(
        Condition.DAZED,
        Condition.SHAPED,
        until=When.SAVE_ENDS if c.strike() else When.EOTNT,
    )
    if held is None:
        return

    def broken(ev: DamageApplied) -> None:
        if ev.target == victim and ev.amount > 0:
            c.world.effects.end(held, "it took damage")

    held.subs.append(c.world.bus.on(DamageApplied, broken))


@power(
    "p13743",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT],
    attack=Attack(INT, vs=FORT),
)
def p13743(c: Cast) -> None:
    """The Effect line lands whether the attack did or not, and one hold
    carries both halves of "slowed and can't shift"."""
    if c.strike():
        c.damage("2d8", c.int_mod)
    c.condition(Condition.SLOWED, Condition.ROOTED, until=When.EOTNT)


@power(
    "p13972",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ZONE],
    attack=Attack(INT, vs=REF),
)
def p13972(c: Cast) -> None:
    """"Difficult terrain for your enemies" is the zone labelled with this
    row's ref and everybody on the caster's side excused from that label,
    which is exactly what `c.ignores_difficult` takes.

    "One nonflying creature" has nowhere to go: a target line filters by side
    and count and cannot ask what a creature is doing.
    """
    if not c.strike():
        return
    c.damage("1d8", c.int_mod)
    ground = spread({c.there}, 1) - {c.there}
    if not ground:
        return
    c.zone(ground, label=c.ref, until=When.EONT, difficult=c.ref)
    for friend in (c.me, *c.allies()):
        c.ignores_difficult(c.ref, on=friend, until=When.EONT)


@power(
    "p13973",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(INT, vs=FORT),
)
def p13973(c: Cast) -> None:
    """The Effect line lands whether the attack did or not. Healing is
    refused on the way in rather than clawed back afterwards, which is what
    makes the log read the way the table saw it."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.NECROTIC)
        if c.is_kind("undead"):
            c.vulnerable(5, until=When.SONT)

    def refuse(ev: Healed) -> None:
        if ev.target == victim:
            ev.amount = 0

    c.watch(
        Healed, refuse, until=When.SONT, window=Window.BEFORE, on=victim,
        label=f"{c.ref} no healing",
    )


@power(
    "p13974",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CLOSE, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(INT, vs=WILL),
)
def p13974(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("1d8", c.int_mod, dtype=DamageType.PSYCHIC)
    _no_opportunity(
        c, c.effect(f"{c.ref} no openings", until=When.EONT), victim, only_me=True
    )


@power(
    "p13975",
    level=1,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[*ARCANE_IMPLEMENT],
    attack=Attack(INT, vs=FORT),
)
def p13975(c: Cast) -> None:
    """"The damage is of those types" is dealt once, typed as the first of
    them: one lot of damage per type would multiply the line by however many
    weaknesses the target happens to carry."""
    if not c.strike():
        return
    defences = c.world.get(c.target, Defences)
    weak = sorted(
        (k for k, v in (defences.vulnerable if defences else {}).items() if v > 0),
        key=lambda k: k.value,
    )
    if weak:
        c.damage("1d4", c.int_mod, dtype=weak[0])
    else:
        c.damage("1d4", c.int_mod + c.wis_mod)


@power(
    "p13976",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(INT, vs=REF),
)
def p13976(c: Cast) -> None:
    """The splash is an Effect line, so it happens on a miss too, and it says
    "each creature" rather than each enemy -- allies standing beside the
    target burn with it."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("2d8", c.int_mod, dtype=DamageType.NECROTIC)
    for who in c.within(1, of=victim):
        if who != victim:
            c.flat(c.int_mod, dtype=DamageType.FIRE, on=who)


@power(
    "p13977",
    level=1,
    cls="wizard",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.PSYCHIC, Keyword.ZONE],
    attack=Attack(INT, vs=WILL),
)
def p13977(c: Cast) -> None:
    """"In the origin square" is read off `c.origin`, the square the burst was
    aimed at, rather than off the target's own position -- a Large creature
    standing across it is in it."""
    victim = c.target
    if c.strike() and victim is not None:
        c.damage("1d6", c.int_mod, dtype=DamageType.PSYCHIC)
        if c.origin is not None and victim in c.in_squares({c.origin}):
            c.dazed()
    if not c.first:
        return
    area = c.area()
    if area:
        c.zone(area, label=c.ref, until=When.EONT)
        c.note(
            f"{c.ref}: an enemy attacking from the zone should give its target "
            "partial concealment, and there is no concealment here"
        )


@power(
    "p13978",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(INT, vs=FORT),
)
def p13978(c: Cast) -> None:
    """The advantage is printed on the attack line rather than granted, so it
    is passed to the roll rather than held on the target. `None` leaves the
    board to answer, which is what an unqualified roll means."""
    if c.strike(advantage=True if c.bloodied() else None):
        c.damage("2d8", c.int_mod, dtype=DamageType.NECROTIC)
        c.weakened(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d8", c.int_mod, dtype=DamageType.NECROTIC)
        c.weakened()


@power(
    "p13979",
    level=1,
    cls="wizard",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    keywords=[*ARCANE_IMPLEMENT, Keyword.AREA, Keyword.NECROTIC],
    attack=Attack(INT, vs=WILL),
)
def p13979(c: Cast) -> None:
    """The undead clause replaces the hit outright -- no damage, no hold --
    and `c.flee` is the run itself: the creature moves under its own power,
    away from the caster, and provokes on the way, which a push would not.
    """
    victim = c.target
    if not c.strike():
        c.half_damage("3d6", c.int_mod, dtype=DamageType.NECROTIC)
        return
    if victim is not None and c.is_kind("undead"):
        c.flee(c.speed_of(victim), on=victim)
        c.dazed(until=When.SAVE_ENDS)
        return
    c.damage("3d6", c.int_mod, dtype=DamageType.NECROTIC)
    c.immobilized(until=When.SAVE_ENDS)
