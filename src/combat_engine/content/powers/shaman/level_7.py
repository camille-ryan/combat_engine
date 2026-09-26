"""Shaman, level 7 encounter attacks."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
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
    Hit,
    Keyword,
    Melee,
    Ranged,
    TurnEnd,
    When,
    power,
)

from ._spirit import beside, beside_spirit, friends, spirit_square

PRIMAL = [Keyword.PRIMAL]
PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]
SPIRIT_MELEE = Melee(1, from_="companion")


@power(
    "p11360",
    level=7,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=FORT),
)
def p11360(c: Cast) -> None:
    """"Or until your target is not adjacent to your spirit companion at
    the end of any turn" is not a duration, so the hold is ended by hand
    off the end of each turn."""
    victim = c.target
    if not c.strike(from_=c.companion()) or victim is None:
        return
    c.damage("1d6", c.wis_mod)
    held = c.condition(Condition.RESTRAINED, until=When.EONT, on=victim)
    if held is None:
        return

    def slip(ev: Any) -> None:
        if not held.ended and not beside_spirit(c, victim):
            c.world.effects.end(held, "no longer beside the spirit")

    c.watch(TurnEnd, slip, until=When.EONT, on=c.me)


@power(
    "p12531",
    level=7,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2, from_="companion"),
    target=EACH_ENEMY,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=WILL),
)
def p12531(c: Cast) -> None:
    at = spirit_square(c)
    if c.strike(from_=c.companion()):
        c.damage("1d8", c.wis_mod)
        c.pull(1, anchor=at)
    if c.last:
        c.dismiss_companion()


@power(
    "p12874",
    level=7,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1, from_="companion"),
    target=EACH_ENEMY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
)
def p12874(c: Cast) -> None:
    """The zone and the allies' slide are laid out first: both are measured
    from the spirit, which does not survive the row."""
    if c.first:
        dust = c.zone(c.area(), until=When.EONT)
        for mate in c.in_squares(c.area(), side="ally"):
            if mate != c.companion():
                c.slide(1, on=mate)

        def choke(ev: Any) -> None:
            foe = getattr(ev, "actor", None)
            if foe in c.enemies() and foe in c.world.zones.occupants(dust):
                c.dazed(on=foe, until=When.EOTNT)

        c.watch(TurnEnd, choke, until=When.EONT, on=c.me)
    if c.strike(from_=c.companion()):
        c.damage("2d6", c.wis_mod)
    if c.last:
        c.dismiss_companion()


@power(
    "p3795",
    level=7,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.LIGHTNING, Keyword.THUNDER],
    attack=Attack(WIS, vs=REF),
)
def p3795(c: Cast) -> None:
    """One lump of damage carries one type, so the lightning half is what
    is dealt."""
    if not c.strike(from_=c.companion()):
        return
    c.damage("2d8", c.wis_mod, dtype=DamageType.LIGHTNING)
    mate = c.choose([a for a in beside(c) if a != c.me], "who shifts")
    if mate is not None:
        c.shift(5, who=mate)


@power(
    "p3796",
    level=7,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=WILL),
)
def p3796(c: Cast) -> None:
    if not c.strike(from_=c.companion()):
        return
    c.damage("2d10", c.wis_mod)
    for mate in friends(c):
        c.bonus(
            "crit_range", 2, on=mate, until=When.EONT,
            when=lambda ctx, w=mate: beside_spirit(c, w),
        )
        if c.build("stalker") and c.int_mod > 0:
            c.bonus(
                "damage", c.int_mod, on=mate, until=When.EONT,
                when=lambda ctx, w=mate: beside_spirit(c, w),
            )


@power(
    "p5399",
    level=7,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.LIGHTNING, Keyword.THUNDER],
    attack=Attack(WIS, vs=REF),
)
def p5399(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("1d12", c.wis_mod, dtype=DamageType.LIGHTNING)

    def crack(ev: Any) -> None:
        if ev.attacker not in friends(c, with_me=True):
            return
        if ev.target in c.enemies() and beside_spirit(c, ev.target):
            c.flat(c.roll("1d6"), dtype=DamageType.LIGHTNING, on=ev.target)

    c.watch(Hit, crack, until=When.EONT, on=c.me)


@power(
    "p5400",
    level=7,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.COLD],
    attack=Attack(WIS, vs=REF),
)
def p5400(c: Cast) -> None:
    """The printed rider is an immediate interrupt taken later, once. There
    is no verb for holding an action, so it is armed here and spent on the
    first blow it can answer: the outcome is recomputed from the die after
    the interrupt window, so the bonus can still turn the hit away."""
    if not c.strike():
        return
    c.damage("1d10", c.wis_mod, dtype=DamageType.COLD)
    amount = 3 + c.con_mod if c.build("protector") else 4
    spent = [False]

    def shield(ev: Any) -> None:
        mate = getattr(ev, "target", None)
        if spent[0] or mate not in friends(c) or not beside_spirit(c, mate):
            return
        if not c.may("raise the ally's defence", who=mate):
            return
        spent[0] = True
        c.bonus(AC, amount, on=mate, until=When.EOT, once=True)

    c.watch(Hit, shield, until=When.EONT, on=c.me)


@power(
    "p5438",
    level=7,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p5438(c: Cast) -> None:
    if not c.strike(from_=c.companion()):
        return
    c.damage("2d8", c.wis_mod)
    for foe in c.enemies():
        for what in (AC, FORT, REF, WILL):
            c.penalty(
                what, 2, on=foe, until=When.EONT,
                when=lambda ctx, f=foe: beside_spirit(c, f),
            )


@power(
    "p5445",
    level=7,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1, from_="companion"),
    target=EACH_ENEMY,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p5445(c: Cast) -> None:
    """The bonus counts how many targets were hit, and a count cannot be
    carried from one call of the body to the next, so the whole burst is
    rolled in the first call."""
    if not c.first:
        return
    spirit = c.companion()
    hits = 0
    for foe in c.targets:
        if c.strike(on=foe, from_=spirit):
            c.damage("1d10", c.wis_mod, on=foe)
            hits += 1
    if hits <= 0:
        return
    for mate in friends(c):
        c.bonus(
            "damage", 2 * hits, on=mate, until=When.EONT,
            when=lambda ctx, w=mate: beside_spirit(c, w),
        )


@power(
    "p9760",
    level=7,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2, from_="companion"),
    target=EACH_ENEMY,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=FORT),
)
def p9760(c: Cast) -> None:
    """"If you hit at least one target" is the same shape as p5445: the
    whole burst is rolled in the first call so the answer is known before
    the allies are moved."""
    if not c.first:
        return
    spirit = c.companion()
    area = c.area()
    hits = 0
    for foe in c.targets:
        if c.strike(on=foe, from_=spirit):
            c.damage("1d10", c.wis_mod, on=foe)
            hits += 1
            if c.build("watcher"):
                c.slide(3, on=foe)
    if hits <= 0:
        return
    for mate in c.in_squares(area, side="ally"):
        if mate != spirit:
            c.slide(3, on=mate)


@power(
    "p9761",
    level=7,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2, from_="companion"),
    target=EACH_ENEMY,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p9761(c: Cast) -> None:
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            if mate != c.companion():
                c.bonus("speed", 3, on=mate, until=When.EONT)
    if c.strike(from_=c.companion()):
        c.damage("1d8", c.wis_mod)
        c.slowed(until=When.EONT)


@power(
    "p9762",
    level=7,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=WILL),
)
def p9762(c: Cast) -> None:
    """The granted swing has combat advantage, which is the target granting
    it to that one ally for the one attack."""
    victim = c.target
    if not c.strike(from_=c.companion()) or victim is None:
        return
    c.weakened(until=When.EONT)
    mate = c.choose(
        [a for a in friends(c) if c.adjacent_to(victim, a)], "who swings"
    )
    if mate is None:
        return
    c.grants_advantage(on=victim, until=When.EOT, to=mate, once=True)
    c.grant_attack(
        mate, on=victim, damage_bonus=c.int_mod if c.build("stalker") else 0
    )
