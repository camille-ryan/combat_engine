"""Warlock, level 3: the encounter attacks.

The first four each print a pact line -- Infernal, Fey or Star -- adding the
caster's Intelligence modifier to something. The class carries two legs,
`infernal` and `fey`, so those two are asked for with `c.build`; a star,
dark, vestige, sorcerer-king or gloom rider has nothing to ask and the base
number stands, named in a comment rather than guessed at.

The rows from the later books follow, in their own order. Two recurring
readings, both settled in `level_1_b.py`: a line printing two damage types
at once is one amount and one `dtype`, and "reroll your own attack roll" is
written as one more swing, since `c.reroll_attack` reads the roll off
`c.trigger` and a row fired as an action is handed none.
"""

from __future__ import annotations

from combat_engine.engine import (
    CHA,
    CON,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    INTERRUPT,
    ONE_CREATURE,
    REF,
    STANDARD,
    WILL,
    Attack,
    AttackDeclared,
    Cast,
    CloseBlast,
    CloseBurst,
    DamageType,
    Defences,
    Hit,
    Keyword,
    MeleeOrRanged,
    Ranged,
    Relation,
    Target,
    Trigger,
    When,
    both,
    by_melee,
    get,
    power,
    targets_me,
)

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]

_HIT_BY_MELEE = "an enemy hits you with a melee attack"


@power(
    "p1341",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CON, vs=REF),
)
def p1341(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("3d6", c.con_mod, dtype=DamageType.FIRE)
    # The splash is printed as "creatures adjacent to the target", which is
    # everybody standing there, not only enemies -- and not the target, who
    # has already been hit. The Infernal Pact line would add Intelligence
    # modifier to it.
    for other in c.within(1, of=c.target):
        if other != c.target:
            c.damage("1d6", c.con_mod, dtype=DamageType.FIRE, on=other)


@power(
    "p1400",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    # "or two creatures no more than 5 squares apart from each other" -- the
    # spacing between two targets cannot be asked for, so it is only written.
    target=Target("enemy", 2, label="One creature, or two no more than 5 squares apart"),
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p1400(c: Cast) -> None:
    # One attack per target, which is what a body called per target already
    # does. The Fey Pact line would add Intelligence modifier to each damage
    # roll.
    if c.strike():
        c.damage("2d8", c.cha_mod)


@power(
    "p1401",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD, Keyword.FEAR],
    attack=Attack(CON, vs=FORT),
)
def p1401(c: Cast) -> None:
    """The advantage is printed for the whole side, not just the caster.

    `c.grants_advantage` hands it to the attacker alone, so the relation is
    applied once per ally on a single effect instead -- the same shape the
    monster rows that open an enemy up to everybody use.
    """
    if not c.strike():
        return
    c.damage("2d8", c.con_mod, dtype=DamageType.COLD)
    victim = c.target
    c.world.effects.apply(
        victim,
        c.me,
        When.EONT,
        label="p1401",
        relations=[
            (Relation.GRANTS_CA_TO, victim, friend) for friend in (c.me, *c.allies())
        ],
    )
    # The Star Pact line would add a penalty to AC equal to Intelligence
    # modifier for the same duration.


@power(
    "p661",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.TELEPORTATION],
    attack=Attack(CHA, vs=FORT),
)
def p661(c: Cast) -> None:
    if c.target is not None and c.strike():
        c.damage("1d8", c.cha_mod)
        c.immobilized()
    # The Effect line lands whether anything was hit or not, and after the
    # burst rather than before it -- so it goes on the last target, which is
    # also the one call the body gets when the burst catches nobody.
    if c.last:
        c.teleport(5)


@power(
    "p12309",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(CHA, vs=WILL),
)
def p12309(c: Cast) -> None:
    """The secondary's granted swing is printed at half damage, which cannot
    be said: `c.grant_attack` rolls that creature's own row and nothing
    halves what it deals. The swing is handed over whole."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.damage("1d10", c.cha_mod, dtype=DamageType.PSYCHIC)
        _turns_on_itself(c, victim)
        if c.build("infernal"):
            _spite(c)
        return
    c.flat(c.level, on=c.me)
    pool = sorted(e for e in c.enemies() if e != victim and c.distance(e) <= 10)
    second = c.choose(pool, f"{c.ref}: who the backlash finds") if pool else None
    if second is None or not c.attack(c.cha_, WILL, on=second):
        return
    c.half_damage("1d10", c.cha_mod, dtype=DamageType.PSYCHIC, on=second)
    _turns_on_itself(c, second)


def _turns_on_itself(c: Cast, victim: int) -> None:
    """"A melee basic attack against itself or an adjacent creature"."""
    pool = sorted({victim, *c.within(1, of=victim)})
    mark = c.choose(pool, f"{c.ref}: who it swings at")
    if mark is not None:
        c.grant_attack(victim, on=mark)


def _spite(c: Cast) -> None:
    """The infernal rider: an attack on you scalds everything else beside you."""

    def lash(ev: AttackDeclared) -> None:
        if ev.target != c.me:
            return
        for foe in c.within(1, side="enemy"):
            if foe != ev.attacker:
                c.flat(c.cha_mod, dtype=DamageType.PSYCHIC, on=foe)

    c.watch(AttackDeclared, lash, until=When.EONT)


@power(
    "p12891",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p12891(c: Cast) -> None:
    """The sorcerer-king rider would drop the word "melee"; no leg to ask."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("1d10", c.cha_mod, dtype=DamageType.PSYCHIC)
    paid = [False]
    friends = {c.me, *c.allies()}

    def reward(ev: Hit) -> None:
        if paid[0] or ev.target != victim or ev.attacker not in friends:
            return
        p = get(ev.power)
        if p is None or p.reach.kind != "melee":
            return
        paid[0] = True
        c.temp_hp(c.int_mod, on=ev.attacker)

    c.watch(Hit, reward, until=When.EONT)


@power(
    "p13905",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CHA, vs=REF),
)
def p13905(c: Cast) -> None:
    # The gloom pact rider has no leg to ask for.
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.NECROTIC)
        c.slowed()


@power(
    "p13915",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.ZONE],
    attack=Attack(CHA, vs=WILL),
)
def p13915(c: Cast) -> None:
    if c.target is not None and c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.PSYCHIC)
    if not c.last:
        return
    area = c.area()
    if area:
        # "Heavily obscured" and "blocks line of sight" are the same clause
        # here: a zone that blocks sight is the whole of what can be said.
        c.zone(area, label=c.ref, until=When.EONT, blocks_sight=True)


@power(
    "p15903",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID, Keyword.HEALING],
    attack=Attack(CON, vs=FORT),
)
def p15903(c: Cast) -> None:
    # The star pact rider would add Intelligence to the hit points regained.
    if c.strike():
        c.damage("2d8", c.con_mod, dtype=DamageType.ACID)
        c.heal(3, on=c.me)


@power(
    "p16351",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p16351(c: Cast) -> None:
    """"Charge that enemy or make a basic attack against it" is one swing
    either way here, so the charge is not offered separately."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.pull(4)
        fetched = [False]

        def sics(ev: AttackDeclared) -> None:
            if fetched[0] or ev.target != c.me or ev.attacker == victim:
                return
            fetched[0] = True
            if c.build("fey"):
                c.slide(3, on=victim)
            c.grant_attack(victim, on=ev.attacker)

        c.watch(AttackDeclared, sics, until=When.EONT)
    # The Effect line lands either way.
    c.cannot_attack(on=victim, against=c.me, until=When.EONT)


@power(
    "p1886",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=REF),
)
def p1886(c: Cast) -> None:
    """The damage changes type to whatever the target is weakest to, read off
    its own `Defences`. With more than one the choice is offered; with none
    it stays psychic, as printed. The dark pact rider has no leg."""
    victim = c.target
    if not c.strike() or victim is None:
        return
    weak = c.world.get(victim, Defences)
    soft = sorted((weak.vulnerable if weak else {}), key=lambda d: d.value)
    dtype = DamageType.PSYCHIC
    if soft:
        dtype = c.choose(soft, f"{c.ref}: which weakness to strike") or soft[0]
    c.damage("2d6", c.cha_mod, dtype=dtype)


@power(
    "p3405",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p3405(c: Cast) -> None:
    """The way out is the target's own choice, which is what `c.may` asks --
    it puts the question to `c.target` and not to the caster. The dark pact
    rider would let the attack go against Fortitude instead."""
    if not c.strike():
        return
    c.damage("1d8", c.cha_mod, dtype=DamageType.PSYCHIC)
    fog = c.dazed(until=When.EOTNT)
    if fog is not None and c.may("tear free of it"):
        c.damage("2d8")
        c.world.effects.end(fog, "it hurt itself clear")


@power(
    "p4068",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID],
    attack=Attack(CON, vs=FORT),
)
def p4068(c: Cast) -> None:
    # The rider is printed for the infernal *or* the vestige pact; only the
    # first is a leg the class carries, so only that half is asked for.
    if c.strike():
        c.damage("2d6", c.con_mod, dtype=DamageType.ACID)
        c.grants_advantage(to="allies")
    elif c.build("infernal"):
        c.grants_advantage()


@power(
    "p4069",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CON, vs=FORT),
)
def p4069(c: Cast) -> None:
    """Handing an effect on is written as ending yours and laying its
    conditions and its burn on the target for a turn. The hold itself is a
    different object with a different clock, which is what the printed line
    means by "until the end of your next turn" replacing "save ends"."""
    if not c.strike():
        return
    c.damage("2d8", c.con_mod, dtype=DamageType.PSYCHIC)
    mine = [e for e in c.world.effects.of(c.me) if e.when is When.SAVE_ENDS]
    if not mine:
        return
    passed = mine[0]
    c.world.effects.end(passed, "handed on")
    if passed.conditions or passed.ongoing:
        c.condition(*passed.conditions, until=When.EONT, ongoing=passed.ongoing)
    else:
        c.effect(passed.label, until=When.EONT)


@power(
    "p4070",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p4070(c: Cast) -> None:
    if c.strike():
        c.damage("2d12", c.cha_mod, dtype=DamageType.PSYCHIC)
        return
    if not c.may("pay for a second shot", who=c.me):
        return
    c.flat(10, dtype=DamageType.PSYCHIC, on=c.me)
    if c.strike():
        c.damage("2d12", c.cha_mod, dtype=DamageType.PSYCHIC)


@power(
    "p4281",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=WILL),
)
def p4281(c: Cast) -> None:
    # The star pact rider -- eating into the target's cold resistance -- has
    # no leg to ask for, and nothing lowers a resistance in any case.
    if c.strike():
        c.damage("2d12", c.cha_mod, dtype=DamageType.COLD)
        c.slowed()


@power(
    "p5910",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=CloseBurst(4),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CHA, vs=WILL),
    trigger=_HIT_BY_MELEE,
    on=Trigger(Hit, when=both(targets_me, by_melee), text=_HIT_BY_MELEE),
)
def p5910(c: Cast) -> None:
    """The choice is the target's, which is what `c.may` asks by default.

    Dealing half damage is `c.weakened` for the rest of the turn -- there is
    no way to halve one named blow -- and an interrupt resolves before the
    damage, so the weakness is in force when it lands.
    """
    if not c.strike():
        return
    c.damage("1d8", c.cha_mod, dtype=DamageType.NECROTIC)
    if c.may("pull the blow"):
        c.weakened(until=When.EOT)
    else:
        c.damage("1d8", dtype=DamageType.NECROTIC)


@power(
    "p5911",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=FORT),
)
def p5911(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.damage("2d6", c.cha_mod, dtype=DamageType.COLD)
    c.immobilized()
    if c.build("fey"):
        for foe in c.within(1, of=victim, side="enemy"):
            if foe != victim:
                c.slowed(on=foe)


@power(
    "p5912",
    level=3,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[
        *ARCANE_IMPLEMENT,
        Keyword.COLD,
        Keyword.FIRE,
        Keyword.LIGHTNING,
        Keyword.THUNDER,
    ],
    attack=Attack(CON, vs=REF),
)
def p5912(c: Cast) -> None:
    """The rider is printed as all four types at once and `c.damage` carries
    one, so it is dealt as cold. The vestige pact rider that splashes it onto
    the target's neighbours has no leg to ask for."""
    if c.strike():
        c.damage("2d8", c.con_mod)
        if c.cursed():
            c.flat(c.int_mod, dtype=DamageType.COLD)
