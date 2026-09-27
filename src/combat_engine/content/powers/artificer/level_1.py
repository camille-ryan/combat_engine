"""Artificer, level 1.

Two things run through the whole level. The first is that almost every row
pays an ally as well as hitting an enemy, so the defaults matter: `c.resist`
and `c.surge_value` are the caster's and have to be aimed with `on=`, while
`c.bonus`, `c.penalty` and `c.condition` already follow the target.

The second is that "burst centered on an ally" has no header spelling. Those
rows are declared as area bursts aimed at a square and find the ally with
`ally_at`.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    INT,
    MINOR,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    REF,
    STANDARD,
    AreaBurst,
    Attack,
    AttackDeclared,
    Cast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Hit,
    Keyword,
    Melee,
    MeleeOrRanged,
    Ranged,
    Summon,
    TurnStart,
    When,
    ZoneEntered,
    by_melee,
    get,
    power,
    spread,
)

from . import ally_at, free_squares, near, one_ally, with_keyword, zone_alive


@power(
    "p10188",
    level=1,
    cls="artificer",
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.COLD],
    attack=Attack(INT, vs=REF),
)
def p10188(c: Cast) -> None:
    """The ward on the ally is laid once for the whole use, not once per
    enemy caught, so it hangs off `c.first`."""
    ally = ally_at(c, within=5)
    if c.first and ally is not None:

        def sting(ev: Hit) -> None:
            if ev.target == ally and ev.attacker in c.enemies():
                c.flat(c.wis_mod, dtype=DamageType.COLD, on=ev.attacker)

        c.watch(Hit, sting, until=When.EONT)
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.COLD)


@power(
    "p10189",
    level=1,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(INT, vs=AC),
)
def p10189(c: Cast) -> None:
    if c.strike():
        c.damage("1d10", c.int_mod, dtype=DamageType.NECROTIC)
        c.slowed(until=When.EONT)
        ally = one_ally(c, c.within(5, of=c.target, side="ally"), "who is sped")
        if ally is not None:
            c.bonus("speed", 2, on=ally, until=When.EONT)
            c.temp_hp(5, on=ally)


@power(
    "p10190",
    level=1,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON, Keyword.RANGED, Keyword.POISON],
    attack=Attack(INT, vs=AC),
)
def p10190(c: Cast) -> None:
    """The revision's standard action and weapon keyword, not the printing
    they replace."""
    if c.strike():
        c.damage(c.w(2), c.int_mod, dtype=DamageType.POISON)
        ally = one_ally(c, c.within(5, of=c.target, side="ally"), "who is warded")
        if ally is None:
            return

        def sting(ev: Hit) -> None:
            if ev.target == ally and by_melee(c.world, c.me, ev):
                c.flat(c.wis_mod, dtype=DamageType.POISON, on=ev.attacker)

        c.watch(Hit, sting, until=When.EONT)


@power(
    "p10191",
    level=1,
    cls="artificer",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.FIRE],
)
def p10191(c: Cast) -> None:
    """The infusion, and the two holds that carry its grant: one on the
    caster, which is `p10191b`'s Requirement, and one on the infused ally,
    which is the square that burst is centred on."""
    ward = c.target
    if ward is None:
        return
    c.resist(5, DamageType.FIRE, on=ward, until=When.ENCOUNTER)
    c.effect(c.ref, on=c.me, until=When.ENCOUNTER)
    c.effect(f"{c.ref} anchor", on=ward, until=When.ENCOUNTER)


@power(
    "p10193",
    level=1,
    cls="artificer",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(3, 5),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON],
    attack=Attack(INT, vs=AC),
)
def p10193(c: Cast) -> None:
    """The Effect line -- firing from the ally's square for the rest of the
    encounter -- has no hold to live in and is dropped; `c.strike(from_=)`
    only reaches as far as one use."""
    if c.strike():
        c.damage(c.w(3), c.int_mod)
    else:
        c.half_damage(c.w(3), c.int_mod)


@power(
    "p14400",
    level=1,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[
        Keyword.ARCANE,
        Keyword.COLD,
        Keyword.CONJURATION,
        Keyword.IMPLEMENT,
    ],
    attack=Attack(INT, vs=FORT),
)
def p14400(c: Cast) -> None:
    """The traps are zones rather than conjurations: a conjuration occupies
    its square, so nothing could ever step into one. Each fires once and is
    then spent, which is what "the trap disappears" comes to."""
    def arm(trap: int) -> None:
        spent: list[int] = []

        def spring(ev: ZoneEntered) -> None:
            if ev.zone != trap or spent or ev.actor not in c.enemies():
                return
            spent.append(ev.actor)
            if c.strike(on=ev.actor):
                c.damage("1d8", c.int_mod, dtype=DamageType.COLD, on=ev.actor)
                c.vulnerable(5, DamageType.COLD, on=ev.actor, until=When.EONT)
                c.grants_advantage(on=ev.actor, to="allies", until=When.EONT)

        c.watch(ZoneEntered, spring, until=When.EONT)

    for sq in free_squares(c, c.area() - {c.here}, 2):
        arm(c.zone({sq}, label=f"{c.ref} trap", until=When.EONT))


@power(
    "p4131",
    level=1,
    cls="artificer",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.WEAPON],
    attack=Attack(INT, vs=AC),
)
def p4131(c: Cast) -> None:
    """"The next ally to attack" is watched on `AttackDeclared`, which is
    emitted before the roll reads its modifiers, so the bonus lands on the
    very attack that spent the hold."""
    victim = c.target
    if not c.strike():
        return
    c.damage(c.w(), c.int_mod, dtype=DamageType.FORCE)

    def helps(ev: AttackDeclared) -> None:
        if ev.target == victim and ev.attacker in c.allies():
            c.bonus(
                "attack",
                2,
                on=ev.attacker,
                until=When.EONT,
                once=True,
                when=lambda ctx: ctx["target"] == victim, kind="power")

    c.watch(AttackDeclared, helps, until=When.EONT, once=True)


@power(
    "p4133",
    level=1,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.IMPLEMENT],
    attack=Attack(INT, vs=REF),
)
def p4133(c: Cast) -> None:
    """The +1 is gated on adjacency rather than handed out on the spot: the
    defence context is read at the moment of the blow, so an ally who closes
    later still gets it."""
    victim = c.target
    if c.strike():
        c.damage("2d6", c.int_mod, dtype=DamageType.FORCE)
    for ally in c.allies():
        c.bonus(
            AC,
            1,
            on=ally,
            until=When.EONT,
            when=lambda ctx, a=ally: c.adjacent_to(victim, a), kind="power")


@power(
    "p4134",
    level=1,
    cls="artificer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    attack=Attack(INT, vs=REF),
)
def p4134(c: Cast) -> None:
    landed = c.strike()
    if landed:
        c.damage("2d10", c.int_mod)
    else:
        c.half_damage("2d10", c.int_mod)
    ally = one_ally(c, c.within(10, side="ally"), "who is shielded")
    if ally is not None:
        c.temp_hp(10 if landed else 5, on=ally)


@power(
    "p4199",
    level=1,
    cls="artificer",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(10),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.THUNDER],
    attack=Attack(INT, vs=FORT),
)
def p4199(c: Cast) -> None:
    """The header aims at the primary target -- the ally warded -- because
    that is the one the row always has; the enemy is picked out of the
    squares beside them."""
    primary = c.target
    if primary is None:
        return
    c.bonus(AC, 1, on=primary, until=When.EONT, kind="power")
    beside = [e for e in c.within(10, side="enemy") if c.adjacent_to(primary, e)]
    victim = c.choose(beside, "the enemy beside them") if beside else None
    if victim is None:
        return
    if c.strike(on=victim):
        c.damage("1d8", c.int_mod, dtype=DamageType.THUNDER, on=victim)
        c.push(1, on=victim, by=primary)


@power(
    "p4200",
    level=1,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.IMPLEMENT],
    attack=Attack(INT, vs=FORT),
)
def p4200(c: Cast) -> None:
    """"Any attack deals extra damage to the target" is vulnerability: a
    damage bonus would have to be handed to every attacker one at a time,
    and would miss whoever arrives after."""
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.FORCE)
        c.vulnerable(c.wis_mod, on=c.target, until=When.EONT)


@power(
    "p4201",
    level=1,
    cls="artificer",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=NO_TARGET,
    keywords=[
        Keyword.ACID,
        Keyword.ARCANE,
        Keyword.CONJURATION,
        Keyword.IMPLEMENT,
        Keyword.ZONE,
    ],
)
def p4201(c: Cast) -> None:
    """A wall is not a range the header can spell, so it is aimed as an area
    and laid out from the origin. The fumes reach one square past the wall,
    which the zone itself cannot say, so the bite is a watch of its own --
    checked against the zone still standing, since the watch outlives it."""
    origin = c.origin or c.here
    wall = frozenset((origin[0] + i, origin[1]) for i in range(5))
    zone = c.zone(
        wall, difficult=True, blocks_sight=True, until=When.SUSTAIN, sustain=MINOR
    )
    reach = spread(wall, 1)

    def fumes(ev: TurnStart) -> None:
        if ev.ghost or not zone_alive(c, zone):
            return
        if ev.actor in c.in_squares(reach):
            c.damage("1d6", c.int_mod, dtype=DamageType.ACID, on=ev.actor)

    c.watch(TurnStart, fumes, until=When.ENCOUNTER)


@power(
    "p5207",
    level=1,
    cls="artificer",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON],
    attack=Attack(INT, vs=AC, plus=1),
)
def p5207(c: Cast) -> None:
    """The printed choice between Constitution and Wisdom is taken as
    whichever is larger; nothing in the row turns on which one it was."""
    if not c.strike():
        return
    c.damage(c.w(), c.int_mod)
    extra = max(c.con_mod, c.wis_mod)
    for ally in c.within(1, side="ally"):
        if ally == c.me:
            continue
        c.bonus("attack", 1, on=ally, until=When.EONT, kind="power")
        if extra > 0:
            c.bonus("damage", extra, on=ally, until=When.EONT, kind="power")


@power(
    "p7378",
    level=1,
    cls="artificer",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.IMPLEMENT],
    attack=Attack(INT, vs=FORT),
)
def p7378(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.damage("1d8", c.int_mod, dtype=DamageType.FORCE)

    def shove(ev: Hit) -> None:
        if ev.target == victim and ev.attacker in c.allies():
            c.push(1, on=victim, by=ev.attacker)

    c.watch(Hit, shove, until=When.EONT, once=True)


@power(
    "p7424",
    level=1,
    cls="artificer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[
        Keyword.ARCANE,
        Keyword.CONJURATION,
        Keyword.IMPLEMENT,
        Keyword.PSYCHIC,
    ],
)
def p7424(c: Cast) -> None:
    """The eye is a conjuration with a speed, which is what "you can move it
    3 squares as a move action" comes to. Nothing grants or denies
    concealment, so that half of the line is dropped."""
    spot = free_squares(c, spread({c.here}, 5) - {c.here}, 1)
    eye = c.conjure(
        at=spot[0] if spot else None,
        until=When.ENCOUNTER,
        sustain=None,
        speed=3,
    )
    if not eye:
        return

    def stab(ev: Hit) -> None:
        if ev.attacker in c.allies() and near(c, eye, ev.target, 3):
            c.flat(c.int_mod, dtype=DamageType.PSYCHIC, on=ev.target)

    c.watch(Hit, stab, until=When.ENCOUNTER)


@power(
    "p7636",
    level=1,
    cls="artificer",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(INT, vs=REF),
)
def p7636(c: Cast) -> None:
    """Melee only: the update deletes "or Ranged" from the range line."""
    if c.strike():
        c.damage("1d8", c.int_mod, dtype=DamageType.LIGHTNING)
        if c.con_mod > 0:
            c.penalty("damage", c.con_mod, until=When.EONT, once=True)


@power(
    "p7637",
    level=1,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(INT, vs=AC),
)
def p7637(c: Cast) -> None:
    """A damage bonus has no type of its own, so "extra fire damage" is
    extra damage of whatever the attack already dealt."""
    if not c.strike():
        return
    c.damage(c.w(), c.int_mod, dtype=DamageType.FIRE)
    if c.con_mod <= 0:
        return
    gate = with_keyword(Keyword.WEAPON, Keyword.FIRE)
    for who in c.within(2, side="team"):
        c.bonus("damage", c.con_mod, on=who, until=When.EONT, when=gate)


@power(
    "p7638",
    level=1,
    cls="artificer",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10, by_weapon=True),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID, Keyword.ARCANE, Keyword.WEAPON],
    attack=Attack(INT, vs=AC),
)
def p7638(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.int_mod, dtype=DamageType.ACID)
        c.penalty(AC, 2, until=When.EONT)


@power(
    "p7641",
    level=1,
    cls="artificer",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    summon=Summon(
        speed=6,
        attack=Attack(INT, vs=AC, plus=2),
        damage=Damage("1d10", "int"),
    ),
)
def p7641(c: Cast) -> None:
    """"Any marked enemy" is the condition rather than a mark of the caster's,
    so this asks `c.is_` and not `c.marked`, which would narrow it to mine.

    The opportunity command's mark rider is dropped: the header carries one
    attack line and `c.command` rolls it, and the two printed commands differ
    only in that rider."""
    servant = c.summon_inline(get(c.ref).summon, at=c.origin)
    if not servant:
        return

    def sting(ev: TurnStart) -> None:
        who = ev.actor
        if (
            who in c.enemies()
            and c.is_(Condition.MARKED, on=who)
            and c.adjacent_to(servant, who)
        ):
            c.flat(c.wis_mod, on=who)

    c.watch(TurnStart, sting, until=When.ENCOUNTER)
