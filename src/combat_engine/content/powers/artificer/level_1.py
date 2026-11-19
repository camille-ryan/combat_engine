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
    ONE_CREATURE,
    REF,
    STANDARD,
    YOU_OR_ONE_ALLY,
    ActionType,
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
                c.flat(c.wis_mod, dtype=DamageType.COLD, on=ev.attacker, from_attack=False)

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
                c.flat(c.wis_mod, dtype=DamageType.POISON, on=ev.attacker, from_attack=False)

        c.watch(Hit, sting, until=When.EONT)


@power(
    "p10191",
    level=1,
    cls="artificer",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=YOU_OR_ONE_ALLY,
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
    """**The Effect line is written, and the one proviso it waited on is a
    parameter now.** The note below is kept because it is the reasoning
    that got the symbol right, and it was right: the card gives two
    provisos -- *"if the ally is within 10 squares of you and you have line
    of effect to the ally"* -- and `dsl._lenders` checked only the second.

    Written with a bare `c.cast_from` the artificer would have borrowed an
    origin at any distance with line of effect, which reaches further than
    the card allows: silently stronger than print, which is the reading
    this tree refuses. So the clause waited for `within=` rather than
    being written anyway, and that is the trade worth keeping a note of.

    `within=10` now, and `_lenders` refuses the borrow the moment the ally
    is further off -- re-measured per attack, not frozen at the cast, so an
    ally that walks away stops lending and one that comes back lends again.

    The ally is the target, which is who the card names, and
    `When.ENCOUNTER` is the printed duration."""
    ally = c.target
    if c.strike():
        c.damage(c.w(3), c.int_mod)
    else:
        c.half_damage(c.w(3), c.int_mod)
    if ally is not None:
        c.cast_from(ally, within=10, until=When.ENCOUNTER)


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
                c.grants_advantage(on=ev.actor, to="team", until=When.EONT)

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
    target=YOU_OR_ONE_ALLY,
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
        wall, difficult=True, blocks_sight=True, until=When.SUSTAIN, sustain=MINOR,
        height=2,
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
    3 squares as a move action" comes to.

    **"Enemies within 3 squares of the eye do not benefit from concealment"
    is written now.** The old note said "nothing grants or denies
    concealment", and that was already false: `c.no_conceal` is the deny
    half of `c.conceal`, and both take the `when=` predicate this clause
    needs. #1341.

    Held by each enemy and gated on standing near the eye, which is
    `p11283`'s idiom for the same shape -- an enemy that walks into range
    later picks it up, and it lapses with the conjuration. Read against the
    eye's *current* square, so moving the eye moves the denial with it,
    which is the whole point of a conjuration with a speed.
    """
    spot = free_squares(c, spread({c.here}, 5) - {c.here}, 1)
    eye = c.conjure(
        at=spot[0] if spot else None,
        until=When.ENCOUNTER,
        sustain=None,
        speed=3,
    )
    if not eye:
        return

    for foe in c.enemies():
        c.no_conceal(
            on=foe,
            until=When.ENCOUNTER,
            when=lambda ctx, w=foe: near(c, eye, w, 3),
        )

    def stab(ev: Hit) -> None:
        if ev.attacker in c.allies() and near(c, eye, ev.target, 3):
            c.flat(c.int_mod, dtype=DamageType.PSYCHIC, on=ev.target, from_attack=False)

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
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.SUMMONING],
    summon=Summon(
        speed=6,
        attack=Attack(INT, vs=AC, plus=2),
        damage=Damage("1d10", "int"),
        commands=((STANDARD, "p7641c1"), (ActionType.OPPORTUNITY, "p7641c2")),
    ),
)
def p7641(c: Cast) -> None:
    """"Any marked enemy" is the condition rather than a mark of the caster's,
    so this asks `c.is_` and not `c.marked`, which would narrow it to mine.

    **Both commands are rows now and the rider is written.** The two differ
    in exactly two things: the standard is *"melee 1 **or** ranged 5"* and
    the opportunity is melee 1 and **marks**. One shared `attack` field
    could carry neither -- it has no reach of its own and no body -- so
    `dsl.Summon.commands` names the pair. `MeleeOrRanged(1, 5)` is the
    printed choice of shape. #1360.

    The shape this replaced, kept because the near miss is the thing worth
    knowing: `dsl.Summon` carried `hp, speed, defences, per_defence, size,
    attack, damage, modes, instinctive, label` -- **one** `attack`, so a
    second printed command line had nowhere to be declared. `commands` is
    that place, and `actions._commands` is what offers them. `p11842` and
    `p7657` wanted the same field for the same reason."""
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
            c.flat(c.wis_mod, on=who, from_attack=False)

    c.watch(TurnStart, sting, until=When.ENCOUNTER)


@power(
    "p7641c1",
    level=1,
    # **`cls=""`, and this is load-bearing rather than tidiness.** A
    # command row declared with its class joins that class's power pool:
    # the nine declared here are `AT_WILL` at a character level, so with a
    # class on them they shifted the invoker draw and `f1491` -- which
    # triggers on an invoker class feature -- went from firing to UNUSED on
    # the wide sweep at `d2899ec7`. They are never dealt (measured: no
    # command ref reaches a dealt hand), so the cost was the *draw moving*,
    # not a bad card being offered. A summon's command is not a power a
    # character can take, so it belongs to no class.
    cls="",
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    attack=Attack(INT, vs=AC, plus=2),
)
def p7641c1(c: Cast) -> None:
    """*"Standard Action: Melee 1 or Ranged 5; targets one creature;
    Intelligence + 2 vs. AC; 1d10 + Intelligence modifier damage."*

    `MeleeOrRanged(1, 5)` is the printed "or" -- two shapes in one command,
    which the shared `summon=` line could not hold because it carries no
    reach at all. Its opportunity command, `p7641c2`, is melee only and
    marks.
    """
    if c.strike():
        c.damage("1d10", c.int_mod)


@power(
    "p7641c2",
    level=1,
    cls="",
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    attack=Attack(INT, vs=AC, plus=2),
)
def p7641c2(c: Cast) -> None:
    """*"Opportunity Attack: Melee 1; targets one creature; Intelligence + 2
    vs. AC; 1d10 + Intelligence modifier damage, and the target is marked
    until the end of your next turn."*

    **The mark is the servant's, not the summoner's.** `c.mark` defaults to
    the caster as marker, and this row is used *by* the servant -- which is
    what the card says: the thing that hit you is what you are marked by.
    """
    if c.strike():
        c.damage("1d10", c.int_mod)
        c.mark(until=When.EONT)
