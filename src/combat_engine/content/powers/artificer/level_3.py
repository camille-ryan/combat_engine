"""Artificer, level 3."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    INT,
    INTERRUPT,
    NO_TARGET,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    Cast,
    DamageType,
    Hit,
    Keyword,
    MeleeOrRanged,
    Miss,
    Position,
    Ranged,
    Trigger,
    When,
    ally_within,
    by_melee,
    power,
    spread,
)

from . import ally_struck, one_ally


@power(
    "p10195",
    level=3,
    cls="artificer",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.LIGHTNING, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(INT, vs=AC),
    trigger="an enemy hits and deals damage to one of your allies",
    on=Trigger(Hit, ally_struck(10), "an enemy hits one of your allies"),
)
def p10195(c: Cast) -> None:
    """Declared on `Hit` rather than on the damage: `Hit` carries the
    attacker, which is what "the triggering enemy" means, and the damage
    events do not."""
    ally = getattr(c.trigger, "target", None)
    if c.strike():
        c.damage(c.w(2), c.int_mod, dtype=DamageType.LIGHTNING)
    if ally is not None:
        c.resist(5, on=ally, until=When.EONT)


@power(
    "p10196",
    level=3,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(INT, vs=WILL),
)
def p10196(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.int_mod, dtype=DamageType.PSYCHIC)
        if c.wis_mod > 0:
            c.penalty("attack", c.wis_mod, until=When.EONT)


@power(
    "p4138",
    level=3,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    attack=Attack(INT, vs=WILL),
)
def p4138(c: Cast) -> None:
    """The ally's +2 is printed as a floating bonus to any one roll, spent
    after seeing it. Only the attack roll half is modelled -- there is
    nothing to hang a skill or ability check on -- and `once=True` spends
    it on the first attack it could apply to."""
    if c.strike():
        c.damage("1d6", c.int_mod)
        c.penalty("save", 2, until=When.EONT)
    if not c.first:
        return
    ally = one_ally(c, c.in_squares(c.area(), side="ally"), "who is bolstered")
    if ally is not None:
        c.temp_hp(5 + c.wis_mod, on=ally)
        c.bonus("attack", 2, on=ally, until=When.EONT, once=True)


@power(
    "p7646",
    level=3,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.WEAPON],
    attack=Attack(INT, vs=FORT),
)
def p7646(c: Cast) -> None:
    """The Effect line stands whether or not the swing landed, so the watch
    is armed outside the hit."""
    victim = c.target

    def shove(ev: Hit) -> None:
        if (
            ev.target == victim
            and ev.attacker in c.allies()
            and by_melee(c.world, c.me, ev)
        ):
            c.push(1, on=victim, by=ev.attacker)

    if c.strike():
        c.damage(c.w(), c.int_mod + c.con_mod, dtype=DamageType.FORCE)
    c.watch(Hit, shove, until=When.EONT)


@power(
    "p7647",
    level=3,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(INT, vs=FORT),
)
def p7647(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.LIGHTNING)
        c.grants_advantage(to="allies", until=When.EONT)


@power(
    "p7648",
    level=3,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.WEAPON],
    attack=Attack(INT, vs=REF),
)
def p7648(c: Cast) -> None:
    """"Melee attack rolls" is a gate on the attack context, which carries
    `ranged`; the damage context would not have answered it."""
    if c.strike():
        c.damage(c.w(2), c.int_mod, dtype=DamageType.FORCE)
        if c.con_mod > 0:
            c.penalty(
                "attack",
                c.con_mod,
                until=When.EONT,
                when=lambda ctx: not ctx.get("ranged", False),
            )


@power(
    "p13442",
    level=3,
    cls="artificer",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[
        Keyword.ARCANE,
        Keyword.CONJURATION,
        Keyword.ILLUSION,
        Keyword.IMPLEMENT,
        Keyword.PSYCHIC,
    ],
    trigger="an ally within 10 squares of you misses an enemy with an attack",
    on=Trigger(Miss, ally_within(10), "an ally within 10 squares of you misses"),
)
def p13442(c: Cast) -> None:
    """A conjuration, so creatures move through it -- nothing printed says it
    blocks.

    Its own attack is printed as a second block carrying *this same id*, which
    the tree cannot hold twice, so that swing is dropped along with the move
    action that walks the thing and the flanking it grants. What is written is
    the conjuration arriving beside the enemy that was missed."""
    victim = getattr(c.trigger, "target", None)
    spot = c.world.get(victim, Position) if victim is not None else None
    where = None
    if spot is not None:
        for sq in sorted(spread({spot.square}, 1) - {spot.square}):
            if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
                where = sq
                break
    c.conjure(at=where, until=When.EONT, sustain=None, speed=6)
