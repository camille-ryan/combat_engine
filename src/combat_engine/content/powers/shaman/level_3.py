"""Shaman, level 3.

Every row here is measured from the spirit companion, which is what
`reach=Melee(1, from_="companion")` says: the header is checked against
the spirit's square and the roll is taken from there, with the shaman's
numbers.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    ONE_ALLY,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    Attack,
    Cast,
    Condition,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Ranged,
    Trigger,
    TurnStart,
    When,
    both,
    by_melee,
    hits_my_companion,
    power,
    spread,
)

from ._spirit import (
    beside,
    beside_spirit,
    by_hand,
    friends,
    granted_hit,
    pick_foe,
    spirit_square,
)

PRIMAL = [Keyword.PRIMAL]
PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]
SPIRIT_MELEE = Melee(1, from_="companion")


@power(
    "p11364",
    level=3,
    cls="shaman",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
    trigger="your spirit companion is hit by a melee attack",
    on=Trigger(
        Hit,
        both(hits_my_companion, by_melee),
        "your spirit companion is hit by a melee attack",
    ),
)
def p11364(c: Cast) -> None:
    """The target is the creature that swung, read off the trigger rather
    than chosen. Nothing in the engine hurts the shaman when the spirit
    goes, so "you take no damage" costs nothing."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    if c.strike(on=foe, from_=c.companion()):
        c.damage("1d8", c.wis_mod, dtype=DamageType.PSYCHIC, on=foe)
        other = c.choose(
            [f for f in c.enemies() if f != foe], "who it is made to swing at"
        )
        if other is not None:
            c.grant_attack(foe, on=other)
        c.dismiss_companion()


@power(
    "p12528",
    level=3,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.FIRE, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
)
def p12528(c: Cast) -> None:
    """The zone is a burst 2 laid out from the spirit's square. "Taking
    ongoing cold damage" is not a question the engine can be asked, so the
    saving throw is offered for the two conditions that can."""
    at = spirit_square(c)
    if c.strike(from_=c.companion()):
        c.damage("2d6", c.wis_mod, dtype=DamageType.FIRE)
    if at is None:
        return
    warmth = c.zone(spread({at}, 2), until=When.EONT)

    def thaw(ev: Any) -> None:
        mate = getattr(ev, "actor", None)
        if mate not in friends(c, with_me=True):
            return
        if mate not in c.world.zones.occupants(warmth):
            return
        if c.is_(Condition.SLOWED, on=mate) or c.is_(Condition.IMMOBILIZED, on=mate):
            c.save(on=mate)

    c.watch(TurnStart, thaw, until=When.EONT, on=c.me)


@power(
    "p12870",
    level=3,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_ALLY,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=AC, plus=2),
)
def p12870(c: Cast) -> None:
    """The header's attack line is the secondary one: the primary target is
    an ally and takes no attack at all, and the burst round it is rolled by
    hand against whoever is standing there."""
    mate = c.target
    c.dismiss_companion()
    if mate is None:
        return
    c.resist(
        2 + c.int_mod if c.build("elemental") else 3, on=mate, until=When.EONT
    )
    for foe in [f for f in c.enemies() if c.adjacent_to(f, mate)]:
        if c.strike(on=foe):
            c.damage("2d6", c.wis_mod, on=foe)


@power(
    "p3789",
    level=3,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p3789(c: Cast) -> None:
    """The damage context carries no reach, so "melee attacks" is read off
    the attacking row itself."""
    if not c.strike(from_=c.companion()) or c.wis_mod <= 0:
        return
    c.damage("2d8", c.wis_mod)
    for mate in friends(c):
        c.bonus(
            "damage", c.wis_mod, on=mate, until=When.EONT,
            when=lambda ctx, w=mate: by_hand(ctx) and beside_spirit(c, w), kind="power")


@power(
    "p3792",
    level=3,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.COLD, Keyword.FIRE],
    attack=Attack(WIS, vs=WILL),
)
def p3792(c: Cast) -> None:
    """One lump of damage carries one type here, so the cold half is what
    is dealt. `c.vulnerable` takes no gate, so the two vulnerabilities go
    to the enemies standing by the spirit as the row goes off."""
    if not c.strike():
        return
    c.damage("2d6", c.wis_mod, dtype=DamageType.COLD)
    for foe in beside(c, "enemy"):
        c.vulnerable(5, DamageType.COLD, on=foe, until=When.EONT)
        c.vulnerable(5, DamageType.FIRE, on=foe, until=When.EONT)


@power(
    "p5395",
    level=3,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(WIS, vs=REF),
)
def p5395(c: Cast) -> None:
    """Both riders hand out something there is no verb for -- shifting as a
    minor action, and rough ground ignored in one patch of the board rather
    than by label -- so the attack is the whole row."""
    if c.strike():
        c.damage("1d10", c.wis_mod, dtype=DamageType.LIGHTNING)


@power(
    "p5396",
    level=3,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.HEALING],
    attack=Attack(WIS, vs=FORT),
)
def p5396(c: Cast) -> None:
    if not c.strike(from_=c.companion()):
        return
    c.damage("2d8", c.wis_mod)
    mate = c.choose(
        [a for a in beside(c) if a != c.me], "who spends a healing surge"
    )
    if mate is not None and c.may("spend a healing surge", who=mate):
        c.surge(on=mate, bonus=c.con_mod if c.build("protector") else 0)


@power(
    "p5436",
    level=3,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p5436(c: Cast) -> None:
    """The spirit is standing next to the target -- the range line says so
    -- so it cannot be one of the creatures that crowd it."""
    victim = c.target
    if not c.strike(from_=c.companion()) or victim is None:
        return
    spirit = c.companion()
    crowd = [x for x in c.within(1, of=victim) if x not in (victim, spirit)]
    c.damage("2d10" if crowd else "3d10", c.wis_mod)


@power(
    "p5537",
    level=3,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p5537(c: Cast) -> None:
    """Flanking with the spirit has no verb -- `c.cannot_be_flanked` is all
    the engine says about flanking -- so the build clause, which is a bonus
    for doing it, goes with it."""
    if c.strike(from_=c.companion()):
        c.damage("1d8", c.wis_mod)
        c.immobilized(until=When.EONT)


@power(
    "p9749",
    level=3,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p9749(c: Cast) -> None:
    mate = c.target
    foe = pick_foe(c, mate)
    if mate is None or foe is None:
        return
    if not granted_hit(c, mate, foe):
        return
    second = c.choose(
        [a for a in beside(c) if a not in (c.me, mate)], "who swings next"
    )
    if second is not None:
        c.grant_attack(second, on=pick_foe(c, second) or foe)


@power(
    "p9750",
    level=3,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=FORT),
)
def p9750(c: Cast) -> None:
    if not c.strike(from_=c.companion(), plus=2 if c.bloodied() else 0):
        return
    c.damage("2d8", c.wis_mod)
    amount = c.dex_mod if c.build("watcher") else 2
    if amount <= 0:
        return
    for mate in friends(c):
        for what in ("attack", "damage"):

            def keen(ctx: dict[str, Any], w: int = mate) -> bool:
                foe = ctx.get("target")
                return (
                    foe is not None and c.bloodied(on=foe) and beside_spirit(c, w)
                )

            c.bonus(what, amount, on=mate, until=When.EONT, when=keen, kind="power")


@power(
    "p9751",
    level=3,
    cls="shaman",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=FORT),
)
def p9751(c: Cast) -> None:
    if c.strike(from_=c.companion()):
        c.damage("1d10", c.wis_mod)
        c.push(2)
    for mate in friends(c, with_me=True):
        for what in (AC, FORT, REF, WILL):
            c.bonus(
                what, 1, on=mate, until=When.EONT,
                when=lambda ctx, w=mate: beside_spirit(c, w), kind="power")
