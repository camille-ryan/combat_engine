"""Artificer, level 7."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    INT,
    ONE_CREATURE,
    REACTION,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    AttackDeclared,
    Cast,
    DamageApplied,
    DamageType,
    Hit,
    Keyword,
    Melee,
    MeleeOrRanged,
    Ranged,
    Trigger,
    When,
    both,
    by_keyword,
    enemy_within,
    power,
    spread,
    targets_me,
)

from . import ally_at, ally_struck, one_ally, with_keyword


@power(
    "p10202",
    level=7,
    cls="artificer",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Ranged(10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.NECROTIC, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(INT, vs=AC),
    trigger="an enemy hits and deals damage to one of your allies",
    on=Trigger(Hit, ally_struck(), "an enemy hits one of your allies"),
)
def p10202(c: Cast) -> None:
    """The penalty is gated on adjacency rather than handed to whoever
    happens to be standing there, so an enemy that closes later is caught
    too. It is still only handed to the enemies on the board now."""
    ally = getattr(c.trigger, "target", None)
    if c.strike():
        c.damage(c.w(2), c.int_mod, dtype=DamageType.NECROTIC)
    if ally is None:
        return
    for enemy in c.enemies():
        c.penalty(
            "attack",
            2,
            on=enemy,
            until=When.EONT,
            when=lambda ctx, a=ally: c.adjacent_to(a, ctx.get("attacker", -1)),
        )


@power(
    "p10203",
    level=7,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.THUNDER],
    attack=Attack(INT, vs=WILL),
)
def p10203(c: Cast) -> None:
    """**Written, and the old note had the gap located exactly: it is in the
    kind of origin.** `c.cast_from(who: int)` borrows from a **creature** --
    `Relation.CASTS_FROM` between two entities, with `dsl.measured_from`
    handing back the lender's id for `Position` to be read off it -- and
    this card picks "a square adjacent to the target". A bare square is
    nobody.

    `c.cast_from_square` answers it by putting a **marker** in the square
    and filing the ordinary relation against that, which is this engine's
    existing answer to "a thing that is somewhere and is not a creature":
    `terrain.arm`'s trap has a `Position` and no `Health` or `Side`, and is
    deliberately not in the occupancy index. The marker blocks nothing,
    occupies nobody's square and takes no turn, and it is despawned when
    the hold ends.

    The alternative was teaching `dsl.origins` to answer squares as well as
    entities -- three call sites on the targeting hot path, for one printed
    row. This touches none of them: all three already turn an origin into
    `squares(world, eye)`, and a marker answers that.

    `p10193` is still the sibling wanting the other piece, a distance
    proviso, which is why those were two symbols and not one."""
    if not c.strike():
        return
    c.damage("2d10", c.int_mod, dtype=DamageType.THUNDER)
    # "Choose a square adjacent to the target."
    there = c.there
    if there is None:
        return
    spots = sorted(
        sq for sq in spread({there}, 1)
        if c.world.grid.inside(sq) and sq != there
    )
    spot = c.choose(spots, f"{c.ref}: the new point of origin")
    if spot is not None:
        c.cast_from_square(spot, until=When.EONT)


@power(
    "p14403",
    level=7,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.LIGHTNING, Keyword.WEAPON],
    attack=Attack(INT, vs=AC),
)
def p14403(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.damage(c.w(), c.int_mod, dtype=DamageType.LIGHTNING)
    ally = one_ally(c, c.within(5, of=victim, side="ally"), "who shakes it off")
    if ally is not None and c.save(on=ally, bonus=c.wis_mod):
        c.flat(5, dtype=DamageType.LIGHTNING, on=victim)
        c.dazed(on=victim, until=When.EONT)


@power(
    "p16504",
    level=7,
    cls="artificer",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[
        Keyword.ARCANE,
        Keyword.COLD,
        Keyword.IMPLEMENT,
        Keyword.NECROTIC,
    ],
    attack=Attack(INT, vs=FORT),
    trigger="an adjacent enemy attacks you",
    on=Trigger(
        AttackDeclared,
        both(targets_me, enemy_within(1)),
        "an adjacent enemy attacks you",
    ),
)
def p16504(c: Cast) -> None:
    """"Cold and necrotic damage" is one instance of two types and damage
    carries one, so it is dealt as cold; both keywords stay in the header,
    where anything reading for resistance will find them."""
    if c.strike():
        c.damage("1d6", c.int_mod, dtype=DamageType.COLD)
    for who in c.within(1, side="team"):
        c.temp_hp(5, on=who)


@power(
    "p4144",
    level=7,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    attack=Attack(INT, vs=REF),
)
def p4144(c: Cast) -> None:
    if c.first:
        ally = ally_at(c, within=10)
        if ally is not None:
            c.bonus(AC, 2 + c.con_mod, on=ally, until=When.EONT, kind="power")
    if c.strike():
        c.damage("1d10", c.int_mod)
        c.slide(2)


@power(
    "p4145",
    level=7,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    attack=Attack(INT, vs=REF),
)
def p4145(c: Cast) -> None:
    """Both printed choices are made once for the whole burst, which the
    per-target body cannot do -- a local does not survive to the next
    target -- so this one runs whole on the first and swings at the rest
    itself."""
    if not c.first:
        return
    types = [
        DamageType.ACID,
        DamageType.COLD,
        DamageType.FIRE,
        DamageType.LIGHTNING,
    ]
    dealt = c.choose(types, "the damage type dealt") or DamageType.ACID
    warded = c.choose(types, "the damage type resisted") or dealt
    for who in c.targets:
        if c.strike(on=who):
            c.damage("2d6", c.int_mod, dtype=dealt, on=who)
    for ally in c.in_squares(c.area(), side="ally"):
        c.resist(5 + c.wis_mod, warded, on=ally, until=When.EONT)


@power(
    "p7653",
    level=7,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.COLD, Keyword.WEAPON],
    attack=Attack(INT, vs=AC),
)
def p7653(c: Cast) -> None:
    if not c.strike():
        return
    c.damage(c.w(), c.int_mod, dtype=DamageType.COLD)
    c.slowed(until=When.EONT)
    if c.con_mod <= 0:
        return
    gate = with_keyword(Keyword.WEAPON, Keyword.COLD)
    for who in c.within(2, side="team"):
        c.bonus("damage", c.con_mod, on=who, until=When.EONT, when=gate)


@power(
    "p7654",
    level=7,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[
        Keyword.ARCANE,
        Keyword.HEALING,
        Keyword.NECROTIC,
        Keyword.WEAPON,
    ],
    attack=Attack(INT, vs=AC),
)
def p7654(c: Cast) -> None:
    """Who counts as "within 5 squares of you" is fixed when the power is
    used; the once-each latch is the printed "only once for each use"."""
    if not c.strike():
        return
    c.damage(c.w(), c.int_mod, dtype=DamageType.NECROTIC)
    blessed = set(c.within(5, side="ally")) - {c.me}
    healed: set[int] = set()
    is_weapon = by_keyword(Keyword.WEAPON)

    def mend(ev: DamageApplied) -> None:
        if ev.source not in blessed or ev.source in healed:
            return
        if not is_weapon(c.world, c.me, ev):
            return
        healed.add(ev.source)
        c.heal(c.roll("1d6") + c.con_mod, on=ev.source)

    c.watch(DamageApplied, mend, until=When.EONT)
