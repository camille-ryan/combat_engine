"""Monk, level 7: encounter attacks, two stat blocks apiece."""

from __future__ import annotations

from combat_engine.engine import (
    DEX,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    REF,
    STANDARD,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    DamageType,
    Gear,
    Keyword,
    Melee,
    Ranged,
    UpTo,
    When,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.events import AttackDeclared, ConditionEnded

IMPLEMENT = [Keyword.IMPLEMENT]


def _hand_free(world: World, eid: int) -> bool:
    """"Requirement: you must have at least one hand free"."""
    gear = world.get(eid, Gear)
    if gear is None:
        return True
    if gear.shield or len(gear.melee) > 1:
        return False
    return gear.main is None or not gear.main.two_handed


def _fire(ctx: dict) -> bool:
    p = get(ctx.get("power", ""))
    return p is not None and Keyword.FIRE in p.keywords


@power(
    "p11224",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p11224(c: Cast) -> None:
    """The move half's "slide whoever you step away from into the square
    you vacated" needs the square mid-step, which nothing hands out; only
    the shift is written."""
    if c.strike():
        c.damage("2d6", c.dex_mod)
        c.dazed(until=When.EONT)
    if c.last:
        c.shift(2)


@power(
    "p11226",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p11226(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.dex_mod)
        c.push(c.str_mod)
    if c.last:
        c.move(c.speed_of())
        c.zone(spread({c.here}, 1), difficult=True, until=When.EONT)


@power(
    "p13163",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.LIGHTNING, Keyword.TELEPORTATION],
    attack=Attack(DEX, vs=REF),
)
def p13163(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.dex_mod, dtype=DamageType.LIGHTNING)
        c.push(2)
        if c.wielding("mace") or c.wielding("staff"):
            c.penalty(
                "attack", c.con_mod, until=When.EONT,
                when=lambda ctx: ctx.get("target") == c.me,
            )
        else:
            c.penalty("attack", 2, until=When.EONT)
    if c.last:
        c.teleport(c.speed_of())


@power(
    "p13165",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p13165(c: Cast) -> None:
    """The secondary burst is wider than the header's, so the whole power
    is resolved in the first body call: the second ring is found by range
    rather than by the declared target list."""
    if not c.first:
        return
    inner = [f for f in c.targets if c.can_see(f)]
    for foe in inner:
        if c.strike(on=foe):
            c.damage("1d8", c.dex_mod, on=foe)
    for foe in c.within(2, side="enemy"):
        if foe in c.targets or not c.can_see(foe):
            continue
        if c.strike(on=foe):
            c.damage(0, c.dex_mod, on=foe)
            c.push(2, on=foe)
    c.ignores_difficult(until=When.EOT)
    c.move(c.speed_of() + 2)


@power(
    "p13167",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p13167(c: Cast) -> None:
    """Standing up is the prone condition ending, which is the only moment
    the printed opening exists."""
    if c.strike():
        c.damage("2d6", c.dex_mod)
        c.prone()
        victim = c.target

        def rose(ev: ConditionEnded) -> None:
            if ev.target == victim and ev.condition is Condition.PRONE:
                c.provoke(c.me, on=victim, why="stood up")

        c.watch(ConditionEnded, rose, until=When.EONT, once=True)
    if c.last:
        c.shift(1)
        c.zone(spread({c.here}, 1), difficult=True, until=When.SONT)


@power(
    "p13169",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p13169(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.dex_mod)
        crowd = [a for a in c.allies() if a != c.me and c.adjacent_to(c.target, a)]
        if crowd:
            c.flat(2 * len(crowd))
    if not c.last:
        return
    mates = [a for a in c.within(1, side="ally") if a != c.me]
    if mates:
        partner = c.choose(mates, "swap places with")
        if partner is not None:
            c.swap(partner)


@power(
    "p13225",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p13225(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.dex_mod)
        c.slide(3, anchor=c.here)
    if c.last:
        c.shift(1)


@power(
    "p15987",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p15987(c: Cast) -> None:
    """Shedding a grab or a mark is written as ending the effect that
    carries the condition; nothing else can take one off."""
    if c.strike():
        c.damage("2d8", c.dex_mod)

        def retort(ev: AttackDeclared) -> None:
            if ev.target == c.me and ev.attacker != c.me and c.adjacent(ev.attacker):
                c.damage("1d8", 0, on=ev.attacker)

        c.watch(AttackDeclared, retort, until=When.SONT)
    if not c.last:
        return
    mine = list(c.world.effects.of(c.me))
    held = [e for e in mine if Condition.GRABBED in e.conditions]
    marks = [e for e in mine if Condition.MARKED in e.conditions]
    if held:
        c.world.effects.end(held[0], c.ref)
    elif marks:
        c.world.effects.end(marks[0], c.ref)
    c.shift(2)


@power(
    "p16163",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.THUNDER],
    attack=Attack(DEX, vs=REF),
)
def p16163(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.dex_mod, dtype=DamageType.THUNDER)
    if not c.last:
        return
    for near in c.within(1, side="other"):
        c.condition(Condition.DEAFENED, on=near, until=When.EONT)
    c.mode("fly", c.speed_of(), until=When.EOT)
    c.move(c.speed_of())


@power(
    "p16166",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.FIRE],
    attack=Attack(DEX, vs=REF),
)
def p16166(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.dex_mod, dtype=DamageType.FIRE)
    else:
        spare = [f for f in c.within(5, side="enemy") if f != c.target]
        if spare:
            unlucky = c.choose(spare, "who catches the stray flame")
            if unlucky is not None:
                c.damage("1d8", 0, dtype=DamageType.FIRE, on=unlucky)
    if c.last:
        c.shift(max(1, c.speed_of() // 2))
        c.bonus("damage", 2, on=c.me, until=When.EONT, when=_fire)


@power(
    "p16168",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
    requires=_hand_free,
    requires_text="needs at least one hand free",
)
def p16168(c: Cast) -> None:
    """The escape penalty has no modifier key to write to, and dragging a
    grabbed creature along has no method, so the move half is the move."""
    if c.strike():
        c.damage("2d6", c.dex_mod)
        c.grab()
    if c.last:
        for held in c.suffering("grab"):
            c.no_provoke(from_=held, until=When.EOT)
        c.move(c.speed_of())


@power(
    "p7465",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p7465(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.dex_mod)
        c.shift(1)
    if c.last:
        c.shift(2)


@power(
    "p7466",
    level=7,
    cls="monk",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p7466(c: Cast) -> None:
    """The secondary burst is centred on the primary target, so it is found
    by measuring from that creature after the slide."""
    if c.strike():
        c.damage("2d10", c.dex_mod)
        c.slide(c.wis_mod)
        victim = c.target
        for other in c.within(1, of=victim, side="any"):
            if other in (victim, c.me):
                continue
            if c.strike(on=other):
                c.prone(on=other)
    if c.last:
        for foe in c.within(1, side="enemy"):
            if c.is_(Condition.PRONE, on=foe):
                c.no_provoke(from_=foe, until=When.EOT)
        c.move(c.speed_of() + 2)
