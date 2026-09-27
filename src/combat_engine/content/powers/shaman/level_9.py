"""Shaman, level 9 dailies."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    EACH_CREATURE,
    FORT,
    MINOR,
    ONE_ALLY,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    WIS,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    DamageType,
    Hit,
    Keyword,
    Melee,
    Ranged,
    RoundStart,
    Square,
    TurnStart,
    When,
    power,
    spread,
)
from combat_engine.engine.query import distance_between

from ._spirit import by_hand, spirit_power

PRIMAL = [Keyword.PRIMAL]
PRIMAL_IMPLEMENT = [Keyword.PRIMAL, Keyword.IMPLEMENT]
SPIRIT_MELEE = Melee(1, from_="companion")


def free_square_beside(c: Cast, origin: Square | None) -> Square | None:
    """An unoccupied square next to `origin`, for a conjuration that prints
    "in an unoccupied square adjacent to the target"."""
    if origin is None:
        return None
    for sq in sorted(spread({origin}, 1) - {origin}):
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            return sq
    return None


@power(
    "p3875",
    level=9,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(5, 10),
    target=ONE_CREATURE,
    keywords=[
        *PRIMAL_IMPLEMENT, Keyword.LIGHTNING, Keyword.THUNDER, Keyword.ZONE
    ],
    attack=Attack(WIS, vs=REF),
)
def p3875(c: Cast) -> None:
    thunder = c.zone(c.area(), until=When.ENCOUNTER)

    def roll_on(ev: Any) -> None:
        if ev.attacker not in c.allies():
            return
        if ev.target in c.enemies() and ev.target in c.world.zones.occupants(
            thunder
        ):
            c.damage("1d6", dtype=DamageType.THUNDER, on=ev.target)

    c.watch(Hit, roll_on, until=When.ENCOUNTER, on=c.me)
    if c.strike():
        c.damage("3d6", c.wis_mod, dtype=DamageType.LIGHTNING)


@power(
    "p3884",
    level=9,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(WIS, vs=WILL),
)
def p3884(c: Cast) -> None:
    """An Aftereffect fires when the hold *ends*, which is the one thing
    `escalate` is not -- that runs on a failed save. So it is hung on the
    effect's own end."""
    victim = c.target
    if c.strike():
        c.damage("2d8", c.wis_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage("2d8", c.wis_mod, dtype=DamageType.PSYCHIC)
    if victim is None:
        return
    held = c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=victim)
    c.grants_advantage(on=victim, until=When.SAVE_ENDS, to="allies")
    if held is None:
        return

    def after() -> None:
        pool = [f for f in c.enemies() if f != victim]
        if not pool:
            return
        near = min(pool, key=lambda f: distance_between(c.world, victim, f))
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=near)
        c.grants_advantage(on=near, until=When.SAVE_ENDS, to="allies")

    held.on_end.append(after)


@power(
    "p3885",
    level=9,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.NECROTIC, Keyword.HEALING],
    attack=Attack(WIS, vs=FORT),
)
def p3885(c: Cast) -> None:
    if c.strike():
        c.damage("3d6", c.wis_mod, dtype=DamageType.NECROTIC)
        c.vulnerable(5, until=When.SAVE_ENDS)
    else:
        c.half_damage("3d6", c.wis_mod, dtype=DamageType.NECROTIC)
        c.vulnerable(2, until=When.SAVE_ENDS)
    for who in dict.fromkeys(c.within(10, side="team")):
        c.heal(5, on=who)


@power(
    "p5401",
    level=9,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.CONJURATION],
    attack=Attack(WIS, vs=REF),
)
def p5401(c: Cast) -> None:
    """The conjuration's own move action is `speed=`, which is what the
    engine reads for "as a move action you can move it 5 squares"."""
    where = free_square_beside(c, c.there)
    if c.strike():
        c.damage("1d10", c.wis_mod)
    warlord = c.conjure(at=where, until=When.ENCOUNTER, sustain=None, speed=5)
    if not warlord:
        return

    def rally(ev: Any) -> None:
        mate = getattr(ev, "actor", None)
        if mate not in c.allies() or not c.adjacent_to(warlord, mate):
            return
        foes = c.enemies()
        if not foes:
            return
        victim = min(foes, key=lambda f: distance_between(c.world, mate, f))
        c.basic(who=mate, on=victim)

    c.watch(TurnStart, rally, until=When.ENCOUNTER, on=c.me)


@power(
    "p9763",
    level=9,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.PSYCHIC, Keyword.RELIABLE],
    attack=Attack(WIS, vs=WILL),
)
def p9763(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("2d10", c.wis_mod, dtype=DamageType.PSYCHIC)
    for foe in c.enemies():
        if foe == victim:
            continue

        def near(ctx: dict[str, Any], f: int = foe, v: int = victim) -> bool:
            return distance_between(c.world, f, v) <= 5

        c.penalty("attack", 2, on=foe, until=When.ENCOUNTER, when=near)
        c.penalty("save", 2, on=foe, until=When.ENCOUNTER, when=near)


@power(
    "p9766",
    level=9,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.HEALING, Keyword.CONJURATION],
    attack=Attack(WIS, vs=FORT),
)
def p9766(c: Cast) -> None:
    """The spirit swings, so the attack is rolled `from_` it -- my numbers,
    its square. The rough ground around it is a zone my own side ignores,
    which is how "difficult terrain for your enemies" is said."""
    victim = c.target
    where = free_square_beside(c, c.there)
    spirit = c.conjure(at=where, until=When.EONT, sustain=None, speed=5)
    if where is not None:
        c.zone(spread({where}, 2), until=When.EONT, difficult=c.ref)
        for mate in dict.fromkeys([c.me, *c.allies()]):
            c.ignores_difficult(c.ref, on=mate, until=When.EONT)
    mended: set[int] = set()

    def mend(ev: Any) -> None:
        mate = ev.attacker
        if mate not in c.allies() or mate in mended:
            return
        if ev.target not in c.enemies():
            return
        if distance_between(c.world, spirit, mate) > 2:
            return
        mended.add(mate)
        c.heal(5, on=mate)

    c.watch(Hit, mend, until=When.EONT, on=c.me)
    c.watch(RoundStart, lambda ev: mended.clear(), until=When.EONT, on=c.me)
    if victim is None:
        return
    if c.strike(on=victim, from_=spirit or None):
        c.damage("3d6", c.wis_mod, on=victim)
    else:
        c.half_damage("3d6", c.wis_mod, on=victim)


# -- the rows built round the spirit ----------------------------------------


@power(
    "p12532",
    level=9,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(20),
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p12532(c: Cast) -> None:
    """The printed second block is `p12532b`, the standard-action attack the
    change of shape grants at will. What is written here is the
    transformation and the hold under this ref that gates it."""
    spirit = c.companion()
    if spirit is None:
        return
    c.resist(5, on=spirit, until=When.ENCOUNTER)
    c.effect(c.ref, on=c.me, until=When.ENCOUNTER)


@power(
    "p12875",
    level=9,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_ALLY,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.POLYMORPH],
    attack=Attack(WIS, vs=FORT),
)
def p12875(c: Cast) -> None:
    """`c.form` is the caster's own shape and takes no `on=`, so the ally's
    form is written out piece by piece. Ending it early as a minor action
    has no verb. The burst round the ally is rolled by hand, since the
    header's range is the spirit's."""
    mate = c.target
    c.dismiss_companion()
    if mate is None:
        return
    c.slowed(on=mate, until=When.EONT)
    c.resist(5, on=mate, until=When.EONT)
    if c.int_mod > 0:
        c.bonus("damage", c.int_mod, on=mate, until=When.EONT, when=by_hand, kind="power")
    for foe in [f for f in c.enemies() if c.adjacent_to(f, mate)]:
        if c.strike(on=foe):
            c.damage("2d6", c.wis_mod, on=foe)
            c.prone(on=foe)
        else:
            c.half_damage("2d6", c.wis_mod, on=foe)


@power(
    "p13771",
    level=9,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=SPIRIT_MELEE,
    target=ONE_ALLY,
    keywords=PRIMAL,
)
def p13771(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    for foe in [f for f in c.enemies() if c.adjacent_to(f, mate)][:4]:
        c.grant_attack(mate, on=foe)


@power(
    "p9764",
    level=9,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(2, from_="companion"),
    target=EACH_CREATURE,
    keywords=PRIMAL_IMPLEMENT,
    attack=Attack(WIS, vs=REF),
)
def p9764(c: Cast) -> None:
    """"You can't call it back until after the end of your next turn" wants
    the call's own id to take away, and the call is not a row here."""
    if c.strike(from_=c.companion()):
        c.damage("2d6", c.wis_mod)
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.half_damage("2d6", c.wis_mod)
    if c.last:
        c.dismiss_companion()


@power(
    "p9765",
    level=9,
    cls="shaman",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_CREATURE,
    keywords=[*PRIMAL_IMPLEMENT, Keyword.PSYCHIC, Keyword.ZONE],
    attack=Attack(WIS, vs=REF),
)
def p9765(c: Cast) -> None:
    """Every attack the spirit makes is a row the shaman used, so both
    bonuses are the shaman's, gated on the row being one measured from the
    spirit."""
    if c.first:
        glare = c.zone(c.area(), until=When.ENCOUNTER)
        if c.wis_mod > 0:
            c.bonus(
                "damage", c.wis_mod, on=c.me, until=When.ENCOUNTER,
                when=lambda ctx: (
                    spirit_power(ctx)
                    and c.companion() in c.world.zones.occupants(glare)
                ),
            )
    victim = c.target
    if c.strike():
        c.damage("1d10", c.wis_mod, dtype=DamageType.PSYCHIC)
        if victim is not None:
            c.bonus(
                "attack", 2, on=c.me, until=When.ENCOUNTER, kind="power",
                when=lambda ctx, v=victim: (
                    spirit_power(ctx) and ctx.get("target") == v
                ),
            )
    else:
        c.half_damage("1d10", c.wis_mod, dtype=DamageType.PSYCHIC)
