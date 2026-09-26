"""Invoker, level 3: the encounter attacks."""

from __future__ import annotations

from combat_engine.engine import (
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    ActionType,
    AreaBurst,
    Attack,
    AttackDeclared,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageApplied,
    DamageType,
    Keyword,
    MoveEnd,
    Powers,
    Ranged,
    TurnEnd,
    UpTo,
    When,
    get,
    power,
)
from combat_engine.engine.events import ZoneExited

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]


def only_basic_attacks(c: Cast, victim: int, until: When) -> None:
    """"Cannot use an attack power that requires a standard action, other
    than basic attacks."

    There is no method for "only basic attacks", so it is spelled as
    `c.forbid` over exactly the rows the sentence names: the creature's own
    standard-action attack rows, with whatever it uses as a basic left
    alone. A creature whose only standard attack *is* its basic therefore
    loses nothing, which is the printed reading.
    """
    known = c.world.get(victim, Powers)
    if known is None:
        return
    spared = {known.basic, known.ranged, known.opportunity, "mba", "rba", ""}
    for ref in known.all:
        if ref in spared:
            continue
        p = get(ref)
        if p is None or p.action is not ActionType.STANDARD or p.attack is None:
            continue
        c.forbid(ref, on=victim, until=until)


@power(
    "p11287",
    level=3,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT, Keyword.ZONE],
    attack=Attack(WIS, vs=FORT),
)
def p11287(c: Cast) -> None:
    """Blinding is tied to leaving the zone, so it is hung on `ZoneExited`
    for that zone alone and lasts as long as the zone does."""
    if c.first:
        glare = c.zone(c.area(), until=When.SONT)

        def dazzle(ev: ZoneExited, z: int = glare) -> None:
            if ev.zone == z and ev.actor in c.enemies():
                c.blinded(on=ev.actor, until=When.SONT)

        c.watch(ZoneExited, dazzle, until=When.SONT)
    if c.strike():
        c.damage("1d6", c.wis_mod, dtype=DamageType.RADIANT)
        c.penalty("attack", 2, until=When.EONT)


@power(
    "p12301",
    level=3,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p12301(c: Cast) -> None:
    """"Adjacent to an ally" is read from the target's side: the row
    punishes the enemy line for standing together."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage("2d8", c.wis_mod, dtype=DamageType.RADIANT)

    def huddled(ev: TurnEnd, who: int = victim) -> None:
        if ev.actor != who:
            return
        if any(x != who for x in c.within(1, of=who, side="enemy")):
            c.flat(5, dtype=DamageType.RADIANT, on=who)

    c.watch(TurnEnd, huddled, until=When.EOTNT, on=victim)


@power(
    "p2865",
    level=3,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
)
def p2865(c: Cast) -> None:
    """No attack roll at all: the whole row is an Effect that pays out one
    way or the other at the end of the target's next turn."""
    victim = c.target
    if victim is None:
        return
    mine = {c.me, *c.allies()}
    seen = {"attacked": False, "settled": False}

    def watch_attacks(ev: AttackDeclared, who: int = victim) -> None:
        if ev.attacker == who and ev.target in mine:
            seen["attacked"] = True

    def settle(ev: TurnEnd, who: int = victim) -> None:
        if ev.actor != who or seen["settled"]:
            return
        seen["settled"] = True
        if seen["attacked"]:
            c.damage("2d10", c.wis_mod, dtype=DamageType.RADIANT, on=who)
        else:
            c.temp_hp(5, on=who)

    c.watch(AttackDeclared, watch_attacks, until=When.EOTNT, on=victim)
    c.watch(TurnEnd, settle, until=When.EOTNT, on=victim)


@power(
    "p2866",
    level=3,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p2866(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage("1d8", c.wis_mod, dtype=DamageType.RADIANT)

    def stirred(ev: MoveEnd, who: int = victim) -> None:
        if ev.actor == who:
            c.flat(5, dtype=DamageType.RADIANT, on=who)

    c.watch(MoveEnd, stirred, until=When.EOTNT, on=victim, once=True)


@power(
    "p2867",
    level=3,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=FORT),
)
def p2867(c: Cast) -> None:
    if c.strike():
        hurt = [a for a in c.in_squares(c.area(), side="ally") if a != c.me]
        extra = 2 if any(c.bloodied(on=a) for a in hurt) else 0
        c.damage("1d10", c.wis_mod + extra, dtype=DamageType.RADIANT)


@power(
    "p5191",
    level=3,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p5191(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.wis_mod)
        c.slowed(until=When.EONT)


@power(
    "p7168",
    level=3,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[*DIVINE_IMPLEMENT, Keyword.FORCE],
    attack=Attack(WIS, vs=REF),
)
def p7168(c: Cast) -> None:
    if c.first:
        c.flat(5, on=c.me)
    if c.strike():
        dice = "2d12" if len(c.targets) == 1 else "2d10"
        c.damage(dice, c.wis_mod, dtype=DamageType.FORCE)
        c.push(c.con_mod if c.build("malediction") else 1)


@power(
    "p7169",
    level=3,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
)
def p7169(c: Cast) -> None:
    """"The next time the target deals damage" is the damage landing, not
    the attack roll, so it watches `DamageApplied` and spends itself on the
    first one."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.damage("2d6", c.wis_mod, dtype=DamageType.RADIANT)
    hurt = 5 + (c.con_mod if c.build("wrath") else 0)

    def rebound(ev: DamageApplied, who: int = victim, amount: int = hurt) -> None:
        if ev.source != who:
            return
        others = [f for f in c.within(10, side="enemy") if f != who]
        if not others:
            return
        picked = c.choose(others, "who the light strikes instead")
        if picked is not None:
            c.flat(amount, dtype=DamageType.RADIANT, on=picked)

    c.watch(DamageApplied, rebound, until=When.EONT, on=victim, once=True)


@power(
    "p7170",
    level=3,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.CHARM],
    attack=Attack(WIS, vs=WILL),
)
def p7170(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    only_basic_attacks(c, victim, When.EONT)
    if c.build("preservation") and c.int_mod > 0:
        c.penalty("attack", c.int_mod, until=When.EONT)


@power(
    "p7171",
    level=3,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[*DIVINE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
)
def p7171(c: Cast) -> None:
    """"Each creature in the burst" leaves the caster out -- a close burst
    has its origin in your own square rather than in the burst -- and the
    caster's own daze is the printed Effect line instead."""
    if c.first:
        c.dazed(on=c.me, until=When.EONT)
    if c.strike():
        c.damage("1d8", c.wis_mod, dtype=DamageType.PSYCHIC)
        c.dazed(until=When.EONT)
        c.slowed(until=When.EONT)


@power(
    "p931",
    level=3,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(WIS, vs=REF),
)
def p931(c: Cast) -> None:
    mates = [a for a in c.in_squares(c.area(), side="ally") if a != c.me]
    if c.first and c.build("preservation"):
        for mate in mates:
            c.bonus("save", 2, on=mate, until=When.SONT)
    if c.strike():
        dice = "2d12" if any(c.bloodied(on=a) for a in mates) else "2d10"
        c.damage(dice, c.wis_mod, dtype=DamageType.FIRE)
