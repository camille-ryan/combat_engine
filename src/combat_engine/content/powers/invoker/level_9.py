"""Invoker, level 9: the dailies."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    EACH_CREATURE,
    EACH_ENEMY,
    FORT,
    MINOR,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    AreaBurst,
    Attack,
    AttackDeclared,
    AttackRolled,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageType,
    Keyword,
    MeleeOrRanged,
    Ranged,
    TurnStart,
    UpTo,
    When,
    power,
)
from combat_engine.engine.events import ZoneExited

from .level_3 import only_basic_attacks

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]


@power(
    "p11294",
    level=9,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(WIS, vs=WILL),
)
def p11294(c: Cast) -> None:
    """"All creatures treat the target as an enemy" has nothing to say it
    with -- sides are a component, not a per-creature relation -- so the
    brand is written as its other two clauses, which share its duration."""
    if c.strike():
        c.damage("2d12", c.wis_mod, dtype=DamageType.FIRE)
    c.dazed(until=When.SAVE_ENDS)
    c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "p11295",
    level=9,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=FORT),
)
def p11295(c: Cast) -> None:
    """"Slides to a square not adjacent to the target" is a shove anchored
    on the target's own square, which is what `anchor=` is for."""
    victim = c.target
    if victim is None:
        return
    spot = c.there
    for foe in c.within(1, of=victim, side="enemy"):
        if foe == victim:
            continue
        c.flat(5, on=foe)
        c.push(1, on=foe, anchor=spot)
    if c.strike():
        c.damage("3d10", c.wis_mod)
        c.prone()


@power(
    "p12303",
    level=9,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
)
def p12303(c: Cast) -> None:
    """"Its nearest ally" is the closest creature on the target's own side,
    found by widening a ring around it rather than measured from the
    caster."""
    victim = c.target
    if victim is None:
        return
    landed = c.strike()
    c.damage("1d8", c.wis_mod, dtype=DamageType.PSYCHIC)
    if not landed:
        c.dazed(until=When.EONT)
        return

    def compel(ev: TurnStart, who: int = victim) -> None:
        if ev.ghost or ev.actor != who:
            return
        nearest = None
        for reach in range(1, 21):
            pool = [x for x in c.within(reach, of=who, side="enemy") if x != who]
            if pool:
                nearest = pool[0]
                break
        if nearest is not None and c.grant_attack(who, on=nearest):
            return
        c.flat(5, dtype=DamageType.PSYCHIC, on=who)
        c.dazed(on=who, until=When.EOT)

    c.watch(TurnStart, compel, until=When.SOTNT, on=victim, once=True)


@power(
    "p2876",
    level=9,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.CHARM],
    attack=Attack(WIS, vs=WILL),
)
def p2876(c: Cast) -> None:
    """Both halves hang off being attacked: on a hit that is an extra
    saving throw against this effect alone, on a miss it simply ends."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.cannot_attack(until=When.SAVE_ENDS)

        def shake(ev: AttackDeclared, who: int = victim) -> None:
            if ev.target == who:
                c.save(on=who, against=c.ref)

        c.watch(AttackDeclared, shake, until=When.SAVE_ENDS, on=victim)
        return
    hold = c.cannot_attack(until=When.EOTNT)
    if hold is None:
        return

    def release(ev: AttackDeclared, who: int = victim) -> None:
        if ev.target == who:
            c.world.effects.end(hold, "the spell was broken")

    c.watch(AttackDeclared, release, until=When.EOTNT, on=victim, once=True)


@power(
    "p2879",
    level=9,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(10),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(WIS, vs=WILL),
)
def p2879(c: Cast) -> None:
    """"Hits or misses you" is the roll rather than its outcome, so the
    watch sits on `AttackRolled` and pays out either way."""
    if c.first:

        def recoil(ev: AttackRolled) -> None:
            if ev.target == c.me and ev.attacker != c.me:
                c.flat(5, dtype=DamageType.PSYCHIC, on=ev.attacker)

        c.watch(AttackRolled, recoil, until=When.ENCOUNTER)
    if c.strike():
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.dazed(until=When.EONT)


@power(
    "p3315",
    level=9,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
)
def p3315(c: Cast) -> None:
    """Blinding needs both halves of the printed sentence -- started its
    turn inside, then left -- so one watch records and the other pays."""
    if c.first:
        light = c.zone(c.area(), until=When.SUSTAIN, sustain=MINOR)
        inside: set[int] = set()

        def note(ev: TurnStart, z: int = light) -> None:
            if not ev.ghost and ev.actor in c.world.zones.occupants(z):
                inside.add(ev.actor)

        def dazzle(ev: ZoneExited, z: int = light) -> None:
            if ev.zone == z and ev.actor in inside:
                inside.discard(ev.actor)
                c.blinded(on=ev.actor, until=When.SAVE_ENDS)

        c.watch(TurnStart, note, until=When.ENCOUNTER)
        c.watch(ZoneExited, dazzle, until=When.ENCOUNTER)
    if c.strike():
        c.damage("3d6", c.wis_mod, dtype=DamageType.RADIANT)
    else:
        c.half_damage("3d6", c.wis_mod, dtype=DamageType.RADIANT)


@power(
    "p7186",
    level=9,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=WILL),
)
def p7186(c: Cast) -> None:
    """The reroll has to happen while the die is still live -- once `Hit`
    is announced the comparison has been made -- so it watches
    `AttackRolled` and reads the hit off the total. `c.reroll_attack` only
    reads `c.trigger`, so the event is put there for the length of the
    call and taken back out again."""
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.half_damage("1d10", c.wis_mod)
        c.dazed(until=When.EONT)
        return
    c.damage("1d10", c.wis_mod)

    def meddle(ev: AttackRolled, who: int = victim) -> None:
        if ev.attacker != who or ev.total < ev.defence:
            return
        if not c.may("take 5 damage to force a reroll", who=c.me, default=False):
            return
        c.flat(5, on=c.me)
        held, c.trigger = c.trigger, ev
        c.reroll_attack(keep="new")
        c.trigger = held
        result = getattr(ev, "result", None)
        if result is not None and not result.hit:
            c.flat(5 + c.con_mod, on=who)

    c.watch(AttackRolled, meddle, until=When.SAVE_ENDS, on=victim)


@power(
    "p7187",
    level=9,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.THUNDER, Keyword.ZONE],
    attack=Attack(WIS, vs=FORT),
)
def p7187(c: Cast) -> None:
    """A zone that stays centred on the caster is an aura. Sustaining it
    pays out as well as holding it, so the push goes in `c.on_sustain`."""
    if c.first:
        ring = c.aura(2, until=When.SUSTAIN, sustain=MINOR)
        for mate in (c.me, *c.allies()):
            for what in ("ac", "fort"):
                c.bonus(
                    what,
                    2,
                    on=mate,
                    kind="power",
                    until=When.ENCOUNTER,
                    when=lambda ctx, w=mate, z=ring: w in c.world.zones.occupants(z),
                )

        def shove(z: int = ring) -> None:
            for foe in c.world.zones.occupants(z):
                if foe in c.enemies():
                    c.push(1, on=foe)

        held = dict(c.world.zones.all()).get(ring)
        c.on_sustain(held.effect if held is not None else None, shove)
    if c.strike():
        c.damage("2d6", c.wis_mod, dtype=DamageType.THUNDER)
        c.push(c.int_mod)
    else:
        c.half_damage("2d6", c.wis_mod, dtype=DamageType.THUNDER)
        c.push(1)


@power(
    "p7188",
    level=9,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.LIGHTNING, Keyword.THUNDER, Keyword.ZONE],
    attack=Attack(WIS, vs=FORT),
)
def p7188(c: Cast) -> None:
    """Two different tolls of two different types, so neither is
    `c.hazard`: that one charges on entering and on starting a turn, and
    this row charges on starting a turn and on leaving. Moving the zone
    with a move action is not written -- a zone's squares are fixed."""
    if c.first:
        storm = c.zone(c.area(), until=When.SUSTAIN, sustain=MINOR)

        def shock(ev: TurnStart, z: int = storm) -> None:
            if not ev.ghost and ev.actor in c.world.zones.occupants(z):
                c.flat(5, dtype=DamageType.LIGHTNING, on=ev.actor)

        def crack(ev: ZoneExited, z: int = storm) -> None:
            if ev.zone == z:
                c.flat(5, dtype=DamageType.THUNDER, on=ev.actor)

        c.watch(TurnStart, shock, until=When.ENCOUNTER)
        c.watch(ZoneExited, crack, until=When.ENCOUNTER)
    if c.strike():
        c.damage("3d6", c.wis_mod, dtype=DamageType.LIGHTNING)
        c.slide(2)
    else:
        c.half_damage("3d6", c.wis_mod, dtype=DamageType.LIGHTNING)


@power(
    "p7189",
    level=9,
    cls="invoker",
    usage=DAILY,
    action=MINOR,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.FEAR],
    attack=Attack(WIS, vs=WILL),
)
def p7189(c: Cast) -> None:
    if c.first:
        c.immobilized(on=c.me, until=When.EONT)
    if c.strike():
        c.damage("1d8", c.wis_mod)
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(10, DamageType.UNTYPED))
    else:
        c.half_damage("1d8", c.wis_mod)
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED))


@power(
    "p7190",
    level=9,
    cls="invoker",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(WIS, vs=WILL),
)
def p7190(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.half_damage("2d6", c.wis_mod, dtype=DamageType.PSYCHIC)
        return
    c.damage("2d6", c.wis_mod, dtype=DamageType.PSYCHIC)
    lasts = When.SAVE_ENDS if len(c.targets) == 1 else When.EOTNT
    only_basic_attacks(c, victim, lasts)
    if c.build("preservation") and c.int_mod > 0:
        c.penalty("attack", c.int_mod, until=When.EONT)
