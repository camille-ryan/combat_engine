"""Warlock, level 0: the pact boons and the pact blades.

**Five pact blades, fifteen rows, and none applied its Requirement.** Each set is
a trio -- two "you must use this power with your <blade>" and one "you must be
holding" it -- and the blade is conjured by another row rather than carried off
the weapon table. So `query.holding` has nothing to match: there is no `w:` ref
for a weapon the character summons.

They play, and what they do not do is refuse a character who is not holding the
thing. That is one named clause, so `dropped=("c.as_weapon()",)` -- the symbol
eleven other rows already wait on, which is what makes it the right one rather
than a fifteenth name for one gap. #236 guessed these "may want a marker rather
than a predicate", and they do.

Nine of these are the free-action boon every pact prints, and all nine share
one Trigger written twice: `Dropped` with `by_me` for "you reduce an enemy to
0 hit points", and `Dropped` with a local predicate for "an enemy adjacent to
you drops to 0 hit points". `Dropped` carries `source`, so the first half is
declarable outright rather than routed off `DamageApplied`, which announces
before the creature is down.

The rest are the weapon rows each pact grants. Every one of them prints
"Requirement: you must use this power with your <pact blade>". The chassis
has no gear property for a named weapon, so the requirement is not declared:
a character who has the row has the blade. The "Special: you can use this
power as a melee basic attack" line is likewise not declared -- what a
creature's basic attack *is* lives on `Powers.basic`, and the header has no
field that sets it.

Two-type damage -- "cold and psychic damage" -- is one roll and the engine
types a roll once, so the first printed type carries it.
"""

from __future__ import annotations

from combat_engine.engine import *
from combat_engine.engine.query import distance_between, team

ARCANE = [Keyword.ARCANE]
SHADOW = [Keyword.ARCANE, Keyword.SHADOW]
ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


def _dropped_beside_me(world: World, me: int, ev: Dropped) -> bool:
    who = ev.actor
    return (
        who != me
        and team(world, who) is not team(world, me)
        and distance_between(world, me, who) <= 1
    )


BOON = (
    Trigger(Dropped, by_me, "you reduce an enemy to 0 hit points"),
    Trigger(Dropped, _dropped_beside_me, "an enemy adjacent to you drops to 0 hit points"),
)


def _adjacent_enemy_attacks_me(world: World, me: int, ev: AttackDeclared) -> bool:
    return targets_me(world, me, ev) and enemy_within(1)(world, me, ev)


ADJACENT_SWING = Trigger(
    AttackDeclared, _adjacent_enemy_attacks_me, "an adjacent enemy attacks you"
)


def _beside(c: Cast) -> Square | None:
    """A free square next to the caster, for a row that names the destination."""
    for sq in sorted(spread({c.here}, 1) - {c.here}):
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            return sq
    return None


def _bites(c: Cast, ring: int, amount: int, dtype: DamageType, *, until: When) -> None:
    """"Any creature that enters the aura or starts its turn there takes N",
    once per turn. `c.hazard` says that of a fixed area, not of an aura."""
    struck: dict[int, int] = {}

    def bite(who: int) -> None:
        if struck.get(who) == c.world.round or amount <= 0:
            return
        struck[who] = c.world.round
        c.flat(amount, dtype=dtype, on=who)

    def on_enter(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            bite(ev.actor)

    def on_start(ev: TurnStart) -> None:
        if ev.actor in c.world.zones.occupants(ring):
            bite(ev.actor)

    c.watch(ZoneEntered, on_enter, until=until)
    c.watch(TurnStart, on_start, until=until)


# -- the winter blade --------------------------------------------------------


@power(
    "p13669",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
    once_per_round=True,
    trigger="you reduce an enemy to 0 hit points, or one adjacent to you drops",
    on=BOON,
)
def p13669(c: Cast) -> None:
    if c.dex_mod > 0:
        c.teleport(c.dex_mod)


@power(
    "p13670",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.COLD, Keyword.IMPLEMENT, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
)
def p13670(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage(c.w(2 if c.level >= 21 else 1), c.cha_mod, dtype=DamageType.COLD)
        for d in (AC, FORT, REF, WILL):
            c.bonus(
                d, 2, on=c.me, until=When.EONT,
                when=lambda ctx, who=victim: ctx.get("attacker") == who, kind="power")


@power(
    "p13671",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[
        Keyword.ARCANE,
        Keyword.COLD,
        Keyword.ILLUSION,
        Keyword.IMPLEMENT,
        Keyword.PSYCHIC,
        Keyword.WEAPON,
    ],
    attack=Attack(CHA, vs=WILL),
)
def p13671(c: Cast) -> None:
    victim = c.target
    dice = 2 + (c.level >= 13) + (c.level >= 23)
    if c.strike():
        c.damage(c.w(dice), c.cha_mod, dtype=DamageType.COLD)
    if victim is not None:
        c.invisible(to=victim, on=c.me, until=When.SONT)


# -- the annihilating blade --------------------------------------------------


@power(
    "p13679",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    once_per_round=True,
    trigger="you reduce an enemy to 0 hit points, or one adjacent to you drops",
    on=BOON,
)
def p13679(c: Cast) -> None:
    flat = 0 if c.level < 11 else (2 if c.level < 21 else 5)
    c.temp_hp(max(1, flat + c.con_mod), on=c.me)


@power(
    "p13680",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
    dropped=("c.as_weapon()",),
)
def p13680(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage(c.w(2 if c.level >= 21 else 1), c.cha_mod, dtype=DamageType.NECROTIC)
        c.bonus(
            "attack", 2, on=c.me, until=When.EONT, once=True,
            when=lambda ctx, who=victim: ctx.get("target") == who, kind="power")


@power(
    "p13681",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[
        Keyword.ARCANE,
        Keyword.FIRE,
        Keyword.IMPLEMENT,
        Keyword.NECROTIC,
        Keyword.WEAPON,
    ],
    attack=Attack(CHA, vs=FORT),
    dropped=("c.as_weapon()",),
)
def p13681(c: Cast) -> None:
    victim = c.target
    dice = 2 + (c.level >= 13) + (c.level >= 23)
    if c.strike():
        c.damage(c.w(dice), c.cha_mod, dtype=DamageType.FIRE)
    if victim is not None:
        c.bonus(
            "damage", 5, on=c.me, until=When.EONT, once=True,
            when=lambda ctx, who=victim: ctx.get("target") == who, kind="power")


@power(
    "p13682",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.FIRE, Keyword.NECROTIC],
    trigger="an adjacent enemy attacks you",
    on=ADJACENT_SWING,
    dropped=("c.as_weapon()",),
)
def p13682(c: Cast) -> None:
    c.flat(5 * (1 + (c.level >= 17) + (c.level >= 27)) + c.cha_mod, dtype=DamageType.FIRE)
    if c.con_mod > 0:
        c.push(c.con_mod)


# -- the starshadow blade ----------------------------------------------------


@power(
    "p13721",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    once_per_round=True,
    trigger="you reduce an enemy to 0 hit points, or one adjacent to you drops",
    on=BOON,
)
def p13721(c: Cast) -> None:
    c.bonus("attack", 1, on=c.me, until=When.EONT)


@power(
    "p13722",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
    dropped=("c.as_weapon()",),
)
def p13722(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage(c.w(2 if c.level >= 21 else 1), c.cha_mod, dtype=DamageType.RADIANT)
        near = [e for e in c.within(1, of=victim, side="enemy") if e != victim]
        if near and c.int_mod > 0:
            c.flat(
                c.int_mod,
                dtype=DamageType.RADIANT,
                on=c.choose(near, "who the light spills onto"),
            )


@power(
    "p13723",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[
        Keyword.ARCANE,
        Keyword.IMPLEMENT,
        Keyword.PSYCHIC,
        Keyword.RADIANT,
        Keyword.TELEPORTATION,
        Keyword.WEAPON,
    ],
    attack=Attack(CHA, vs=FORT),
    dropped=("c.as_weapon()",),
)
def p13723(c: Cast) -> None:
    """The destination is named rather than measured, so the teleport is
    given a square and a distance wide enough to reach it."""
    victim = c.target
    dice = 2 + (c.level >= 13) + (c.level >= 23)
    if c.strike():
        c.damage(c.w(dice), c.cha_mod, dtype=DamageType.PSYCHIC)
        spot = _beside(c)
        if spot is not None and victim is not None:
            c.teleport(20, who=victim, to=spot)


@power(
    "p13724",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=ARCANE,
    trigger="an adjacent enemy attacks you",
    on=ADJACENT_SWING,
    dropped=("c.as_weapon()",),
)
def p13724(c: Cast) -> None:
    c.blinded(until=When.EONT)


# -- the white well ----------------------------------------------------------


@power(
    "p13746",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(CHA, vs=REF),
    dropped=("c.as_weapon()",),
)
def p13746(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage(c.w(2 if c.level >= 21 else 1), c.cha_mod, dtype=DamageType.RADIANT)

        def lingers(ev: TurnEnd) -> None:
            if ev.actor == victim and c.adjacent(victim) and c.dex_mod > 0:
                c.flat(c.dex_mod, dtype=DamageType.RADIANT, on=victim)

        c.watch(TurnEnd, lingers, until=When.EOTNT, once=True)


@power(
    "p13747",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
    dropped=("c.as_weapon()",),
)
def p13747(c: Cast) -> None:
    """"Vulnerable to *your* attacks" is widened to vulnerable outright: a
    vulnerability is a property of the creature and carries no attacker. It
    also runs its duration rather than ending when the enemy steps out."""
    dice = 2 + (c.level >= 13) + (c.level >= 23)
    if c.strike():
        c.damage(c.w(dice), c.cha_mod, dtype=DamageType.RADIANT)
    ring = c.aura(1, until=When.EONT, on=c.me)
    for who in c.world.zones.occupants(ring):
        if who in c.enemies():
            c.vulnerable(3, DamageType.RADIANT, on=who, until=When.EONT)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring and ev.actor in c.enemies():
            c.vulnerable(3, DamageType.RADIANT, on=ev.actor, until=When.EONT)

    c.watch(ZoneEntered, entered, until=When.EONT)


# -- the scourge -------------------------------------------------------------


@power(
    "p13903",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(5),
    target=ANY_CREATURE,
    keywords=SHADOW,
    once_per_round=True,
    trigger="you reduce a creature to 0 hit points, or one adjacent to you drops",
    on=BOON,
)
def p13903(c: Cast) -> None:
    """`ANY_CREATURE` rather than `ONE_CREATURE`: the dispatcher aims a
    single-enemy row at whoever the event was about, and here that is the
    creature that just fell."""
    c.slide(3)


@power(
    "p13912",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=SHADOW,
    once_per_round=True,
    trigger="you reduce a creature to 0 hit points, or one adjacent to you drops",
    on=BOON,
)
def p13912(c: Cast) -> None:
    c.invisible(on=c.me, until=When.EONT)


@power(
    "p13913",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.SHADOW],
    attack=Attack(CHA, vs=WILL),
)
def p13913(c: Cast) -> None:
    """Who is 3 or more squares off is measured once, when the dark settles;
    an unseen-relation cannot re-ask the distance as the fight moves."""
    victim = c.target
    if c.strike():
        c.damage("2d10" if c.level >= 21 else "1d10", c.cha_mod, dtype=DamageType.PSYCHIC)
        for friend in c.allies():
            if distance_between(c.world, friend, victim) >= 3:
                c.invisible(to=victim, on=friend, until=When.EONT)


@power(
    "p13962",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=SHADOW,
    trigger="you reduce an enemy to 0 hit points, or one adjacent to you drops",
    on=BOON,
)
def p13962(c: Cast) -> None:
    c.insubstantial(on=c.me, until=When.EONT)
    c.phasing(on=c.me, until=When.EONT)


@power(
    "p13963",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[
        Keyword.ARCANE,
        Keyword.IMPLEMENT,
        Keyword.NECROTIC,
        Keyword.SHADOW,
        Keyword.WEAPON,
    ],
    attack=Attack(CHA, vs=AC),
    dropped=("c.as_weapon()",),
)
def p13963(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2 if c.level >= 21 else 1), c.cha_mod, dtype=DamageType.NECROTIC)
        if c.may("slide it a square"):
            c.slide(1)
        c.penalty("attack", 2, until=When.SONT)


@power(
    "p13964",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[
        Keyword.ARCANE,
        Keyword.IMPLEMENT,
        Keyword.NECROTIC,
        Keyword.PSYCHIC,
        Keyword.SHADOW,
        Keyword.WEAPON,
    ],
    attack=Attack(CHA, vs=REF),
    dropped=("c.as_weapon()",),
)
def p13964(c: Cast) -> None:
    dice = 1 + (c.level >= 13) + (c.level >= 23)
    if c.first:
        c.conceal(on=c.me, until=When.EONT)
    if c.strike():
        c.damage(c.w(dice), c.cha_mod, dtype=DamageType.NECROTIC)
        c.dazed(until=When.EONT)


@power(
    "p13965",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.NECROTIC, Keyword.PSYCHIC, Keyword.SHADOW],
    trigger="an adjacent enemy attacks you",
    on=ADJACENT_SWING,
    dropped=("c.as_weapon()",),
)
def p13965(c: Cast) -> None:
    flat = 5 * (1 + (c.level >= 13) + (c.level >= 23))
    c.flat(flat + c.cha_mod, dtype=DamageType.NECROTIC)
    c.grants_advantage(until=When.EONT, to="team")


# -- the blade of chaos ------------------------------------------------------


@power(
    "p16257",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.ELEMENTAL],
    once_per_round=True,
    trigger="you reduce an enemy to 0 hit points, or one adjacent to you drops",
    on=BOON,
)
def p16257(c: Cast) -> None:
    for dtype in ELEMENTS:
        c.resist(5, dtype, on=c.me, until=When.EONT)
    if c.con_mod > 0:
        c.shift(c.con_mod)


@power(
    "p16258",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.ELEMENTAL, Keyword.IMPLEMENT, Keyword.WEAPON],
    attack=Attack(CHA, vs=AC),
    dropped=("c.as_weapon()",),
)
def p16258(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2 if c.level >= 21 else 1), c.cha_mod)
        c.vulnerable(3, c.choose(list(ELEMENTS), "what it becomes weak to"), until=When.EONT)


@power(
    "p16259",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.ELEMENTAL, Keyword.IMPLEMENT, Keyword.WEAPON],
    attack=Attack(CHA, vs=REF),
    dropped=("c.as_weapon()",),
)
def p16259(c: Cast) -> None:
    """The Hit clause stripping the target's resistance and immunity to the
    chosen type is dropped: nothing on `Cast` takes a resistance away. The
    aura bites everybody, caster included, which is what it says."""
    dtype = c.choose(list(ELEMENTS), "what this one is made of")
    dice = 2 + (c.level >= 13) + (c.level >= 23)
    if c.strike():
        c.damage(c.w(dice), c.cha_mod, dtype=dtype)
    ring = c.aura(1, until=When.EONT, on=c.me)
    _bites(c, ring, c.con_mod, dtype, until=When.EONT)


@power(
    "p16260",
    level=0,
    cls="warlock",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.ELEMENTAL, Keyword.PSYCHIC],
    trigger="an adjacent enemy attacks you",
    on=ADJACENT_SWING,
    dropped=("c.as_weapon()",),
)
def p16260(c: Cast) -> None:
    flat = 5 * (1 + (c.level >= 17) + (c.level >= 27))
    c.flat(flat + c.cha_mod, dtype=DamageType.PSYCHIC)
    c.grants_advantage(until=When.EONT, to="team")


# -- the last two ------------------------------------------------------------


@power(
    "p16348",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(5),
    target=ANY_CREATURE,
    keywords=SHADOW,
    once_per_round=True,
    trigger="you reduce a creature to 0 hit points, or one adjacent to you drops",
    on=BOON,
)
def p16348(c: Cast) -> None:
    """The penalty is gated on the attack context's `target`, which is the
    one key that says "against you"."""
    c.penalty(
        "attack", 5, until=When.EONT,
        when=lambda ctx, me=c.me: ctx.get("target") == me,
    )


@power(
    "p16349",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=UpTo(2),
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.PSYCHIC, Keyword.SHADOW],
    attack=Attack(CHA, vs=WILL),
)
def p16349(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.pull(2)

        def recoil(ev: AttackDeclared) -> None:
            if ev.target == c.me and c.int_mod > 0:
                c.flat(c.int_mod, dtype=DamageType.PSYCHIC, on=victim)

        c.on_attack(recoil, by=victim, until=When.EONT, once=True)
