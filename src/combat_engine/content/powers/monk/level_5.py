"""Monk, level 5: the dailies.

These print one stat block rather than two, so there is no move half unless
the Effect line says so -- and where it does (p16159) the movement comes
first and the attack is made from where it ends.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    DEX,
    EACH_CREATURE,
    FORT,
    INTERRUPT,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    Attack,
    Cast,
    CloseBlast,
    Condition,
    DamageType,
    Defense,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    When,
    both,
    by_melee,
    get,
    hits_me,
    power,
)
from combat_engine.engine.events import AttackDeclared, Hit, Moved, TurnEnd

IMPLEMENT = [Keyword.IMPLEMENT]


def _swing(c: Cast, vs: Defense, on: int) -> bool:
    """This row's own attack line, rolled against a different defence."""
    line = get(c.ref).attack
    if line is None:
        return False
    bonus = line.bonus_for(c.world, c.me, c.ref, c.branch)
    return bool(c.attack(bonus, vs, on=on).hit)


def _melee(ctx: dict) -> bool:
    p = get(ctx.get("power", ""))
    return p is not None and p.reach.kind in ("melee", "close_burst", "close_blast")


@power(
    "p11220",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p11220(c: Cast) -> None:
    """The retaliation is tied to the mark rather than given a duration of
    its own: the printed line ends when this power's mark does."""
    if c.strike():
        c.damage("3d10", c.dex_mod)
        held = c.mark(until=When.SAVE_ENDS)
    else:
        c.half_damage("3d10", c.dex_mod)
        held = c.mark(until=When.EONT)
    victim = c.target
    if victim is None or held is None:
        return

    def sting(ev: Hit) -> None:
        if ev.attacker == victim and ev.target == c.me:
            c.flat(c.str_mod, on=victim)

    watcher = c.watch(Hit, sting, until=When.ENCOUNTER)
    held.on_end.append(lambda: c.world.effects.end(watcher, "mark ended"))


@power(
    "p11221",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p11221(c: Cast) -> None:
    """The "lengthen the forced movement instead" option is dropped: there
    is no way to reach into an attack's own shove after the fact."""
    if c.strike():
        c.damage("3d10", c.dex_mod)
    else:
        c.half_damage("3d10", c.dex_mod)
    victim = c.target
    if victim is None:
        return
    c.bonus(
        "damage", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx, v=victim: ctx.get("target") == v, kind="power")

    def herd(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target == victim:
            c.slide(1, on=victim)

    c.watch(Hit, herd, until=When.ENCOUNTER)


@power(
    "p13154",
    level=5,
    cls="monk",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*IMPLEMENT, Keyword.STANCE],
)
def p13154(c: Cast) -> None:
    """The stance's second stat block -- a standard-action attack that ends
    the stance -- has no id of its own in the spec, so only the stance is
    written."""
    posture = c.stance()
    held = c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, when=_melee, kind="power")
    if held is not None:
        posture.on_end.append(lambda: c.world.effects.end(held, "stance ended"))


@power(
    "p13156",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.COLD],
    attack=Attack(DEX, vs=REF),
)
def p13156(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.dex_mod, dtype=DamageType.COLD)
        held = c.immobilized(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d8", c.dex_mod, dtype=DamageType.COLD)
        held = c.slowed(until=When.SAVE_ENDS)
    victim = c.target
    if victim is None or held is None:
        return

    def chill(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == c.me or ev.actor not in c.enemies():
            return
        if c.adjacent_to(victim, ev.actor):
            c.flat(c.dex_mod, dtype=DamageType.COLD, on=ev.actor)

    watcher = c.watch(TurnEnd, chill, until=When.ENCOUNTER)
    held.on_end.append(lambda: c.world.effects.end(watcher, "the hold ended"))


@power(
    "p13157",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p13157(c: Cast) -> None:
    """Miss deals the same damage as a hit, so the roll is unconditional
    and only the vulnerability hangs off landing."""
    landed = bool(c.strike())
    c.damage("2d6", c.dex_mod)
    if not landed:
        return
    held = c.vulnerable(c.str_mod, until=When.SAVE_ENDS)
    victim = c.target
    if victim is None or held is None:
        return

    def nag(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target == victim:
            c.penalty("save", 2, on=victim, until=When.SAVE_ENDS, once=True)

    watcher = c.watch(Hit, nag, until=When.ENCOUNTER)
    held.on_end.append(lambda: c.world.effects.end(watcher, "vulnerability ended"))


@power(
    "p13158",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.THUNDER],
    attack=Attack(DEX, vs=REF),
)
def p13158(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.dex_mod, dtype=DamageType.THUNDER)
        for near in c.within(1, of=c.target, side="any"):
            if near != c.target:
                c.prone(on=near)
    else:
        c.half_damage("2d10", c.dex_mod, dtype=DamageType.THUNDER)


@power(
    "p15986",
    level=5,
    cls="monk",
    usage=DAILY,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
    trigger="an adjacent enemy hits you with a melee attack",
    on=Trigger(Hit, both(hits_me, by_melee), "an adjacent enemy hits you in melee"),
)
def p15986(c: Cast) -> None:
    """The charge rider is read off the triggering event, where the flag
    lives. The miss line -- regaining the power but not being able to use
    it again -- has no expression and is dropped."""
    charged = bool(getattr(c.trigger, "charge", False))
    if c.strike(plus=2 if charged else 0):
        c.damage("3d10", c.dex_mod)
        if charged:
            c.flat(c.roll("1d10"))
        c.slide(2)
        c.prone()


@power(
    "p16156",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.STANCE],
    attack=Attack(DEX, vs=FORT),
)
def p16156(c: Cast) -> None:
    """The stance's second stat block is an at-will interrupt on an adjacent
    enemy attacking, so it is written into the stance as a standing watch.
    A latch stops the counter-attack answering itself."""
    if c.strike():
        c.damage("2d6", c.dex_mod)
    else:
        c.half_damage("2d6", c.dex_mod)
    if not c.last:
        return
    posture = c.stance(conditions=[Condition.SLOWED])
    busy: list[int] = []

    def counter(ev: AttackDeclared) -> None:
        foe = ev.attacker
        if busy or foe == c.me or foe not in c.enemies() or not c.adjacent(foe):
            return
        busy.append(1)
        try:
            if _swing(c, REF, foe):
                c.damage("1d8", c.dex_mod, on=foe)
                c.prone(on=foe)
            else:
                c.grants_advantage(on=c.me, to=foe, until=When.SONT)
        finally:
            busy.clear()

    hold = c.on_attack(counter, until=When.ENCOUNTER)
    posture.on_end.append(lambda: c.world.effects.end(hold, "stance ended"))


@power(
    "p16158",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=FORT),
)
def p16158(c: Cast) -> None:
    """The aftereffect is hung on the daze's own ending, which is the only
    moment "after it saves" happens."""
    if c.strike():
        c.damage("2d8", c.dex_mod)
        held = c.dazed(until=When.SAVE_ENDS)
        victim = c.target
        if held is not None and victim is not None:
            held.on_end.append(lambda: c.slowed(on=victim, until=When.EOTNT))
    else:
        c.half_damage("2d8", c.dex_mod)
        c.slowed(until=When.EONT)


@power(
    "p16159",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.FIRE, Keyword.ZONE],
    attack=Attack(DEX, vs=REF),
)
def p16159(c: Cast) -> None:
    """The move is printed before the attack and the zone is the trail it
    leaves, so the squares are collected from the steps themselves."""
    if c.first:
        trail: list[object] = []

        def step(ev: Moved) -> None:
            if ev.actor == c.me:
                trail.append(ev.from_)

        sub = c.world.bus.on(Moved, step)
        try:
            c.move(c.speed_of())
        finally:
            c.world.bus.off(sub)
        if trail:
            burnt = c.zone(trail, until=When.EONT)
            c.burns(burnt, c.dex_mod, DamageType.FIRE)
    if c.strike():
        c.damage("4d6", 0, dtype=DamageType.FIRE)
    else:
        c.half_damage("4d6", 0, dtype=DamageType.FIRE)


@power(
    "p7461",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*IMPLEMENT, Keyword.POISON],
    attack=Attack(DEX, vs=FORT),
)
def p7461(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.dex_mod)
        c.ongoing(5, DamageType.POISON, until=When.SAVE_ENDS)
    else:
        c.half_damage("2d10", c.dex_mod)


@power(
    "p7462",
    level=5,
    cls="monk",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=IMPLEMENT,
    attack=Attack(DEX, vs=REF),
)
def p7462(c: Cast) -> None:
    """The Effect line widens the monk's Flurry of Blows, a class feature
    with no id in the spec, so it is not written."""
    if c.strike():
        c.damage("3d8", c.dex_mod)
        c.push(2)
    else:
        c.half_damage("3d8", c.dex_mod)
        c.push(1)
