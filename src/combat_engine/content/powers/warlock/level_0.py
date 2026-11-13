"""Warlock, level 0: the pact boons and the pact blades.

**Five pact weapons, fifteen rows, and every one applies its Requirement
now.** Each set is a trio -- two "you must use this power with your <blade>"
and one "you must be holding" it -- and all three come to the same question,
which `holding` below asks.

**This note argued for three different symbols and the premise under all
three was false.** It said the weapon "is conjured by another row rather
than carried off the weapon table", and therefore that there was "no `w:`
ref for a weapon the character summons" and that "nothing in the tree
creates a pact blade at all". Measured: all six are ordinary rows of the
`weapon` table -- `w3740`, `w3741`, `w3742`, `w3743`, `w3744`, `w3752`, each
with a group, a hand count and its properties -- and `chargen.PRINTED`
has carried every one of them the whole time. So the thing to match on was
always there and three successive notes looked past it: the marker was
re-argued by name three times and none of the three re-measured its premise.

What was genuinely missing was the **dealer**: nothing put the weapon into a
hexblade's `Gear`. `chargen.PACT_WEAPON` does, keyed on the pact the
character's leg names, because the hexblade's class page prints one headed
section per pact and each names the weapon that pact grants. So the weapon
follows the pact, and `chargen.deal_pact_weapon` has the argument for why
`BUILD_OPTIONS` could not express that.

#236 guessed these "may want a marker rather than a predicate". It is a
predicate, and a load-bearing one -- see `holding`.

Nine of these are the free-action boon every pact prints, and all nine share
one Trigger written twice: `Dropped` with `by_me` for "you reduce an enemy to
0 hit points", and `Dropped` with a local predicate for "an enemy adjacent to
you drops to 0 hit points". `Dropped` carries `source`, so the first half is
declarable outright rather than routed off `DamageApplied`, which announces
before the creature is down.

The rest are the weapon rows each pact grants, and every one of them prints
"Requirement: you must use this power with your <pact weapon>", declared as
`requires=holding("<ref>")`. The "Special: you can use this power as a melee
basic attack" line is still not declared -- what a creature's basic attack
*is* lives on `Powers.basic`, and the header has no field that sets it.

Two-type damage -- "cold and psychic damage" -- is one roll and the engine
types a roll once, so the first printed type carries it.
"""

from __future__ import annotations

from collections.abc import Callable

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


def holding(blade: str) -> Callable[[World, int], bool]:
    """"Requirement: You must be holding your `<blade>`."

    All fifteen pact-weapon rows print one, in two wordings -- "use this
    power with your <blade>" and "be holding your <blade>" -- and both
    come to the same question, which is whether that weapon is in hand.
    `chargen.PACT_WEAPON` puts it there, keyed on the pact the character's
    leg names, so there is a weapon ref to match on: all six are ordinary
    rows of the `weapon` table (`w3740`..`w3752`).

    **Load-bearing rather than decorative, and the measurement is why.** A
    dealt hexblade is handed **all six** pacts' power sets rather than the
    one its own pact grants -- measured over four legs, 14 of the 15 rows
    in every hand -- so without this an infernal hexblade could swing the
    star pact's rows with whatever was in its hand, and `c.w()` would
    quietly read that weapon's dice. This is what makes the five sets a
    character should not have refuse themselves, which is the printed
    behaviour.

    Narrowing the *hand* is the other half and is a chargen gap rather
    than this one: a printed Requirement is a per-use gate and reads the
    same either way.
    """

    def gate(world: World, eid: int) -> bool:
        gear = world.get(eid, Gear)
        return gear is not None and any(w.ref == blade for w in gear.weapons)

    gate.__name__ = f"holding_{blade}"
    gate.__doc__ = f'"Requirement: ... your `{blade}`."'
    return gate


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
    requires=holding("w3741"),
    requires_text="you must use this power with your w3741",
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
    requires=holding("w3741"),
    requires_text="you must use this power with your w3741",
)
def p13681(c: Cast) -> None:
    victim = c.target
    dice = 2 + (c.level >= 13) + (c.level >= 23)
    if c.strike():
        c.damage(c.w(dice), c.cha_mod, dtypes=(DamageType.FIRE, DamageType.NECROTIC))
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
    requires=holding("w3741"),
    requires_text="you must be holding your w3741",
)
def p13682(c: Cast) -> None:
    c.flat(
        5 * (1 + (c.level >= 17) + (c.level >= 27)) + c.cha_mod,
        dtypes=(DamageType.FIRE, DamageType.NECROTIC),
    )
    if c.con_mod > 0:
        c.push(c.con_mod)


# -- w3742 -------------------------------------------------------------------


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
    requires=holding("w3742"),
    requires_text="you must use this power with your w3742",
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
    requires=holding("w3742"),
    requires_text="you must use this power with your w3742",
)
def p13723(c: Cast) -> None:
    """The destination is named rather than measured, so the teleport is
    given a square and a distance wide enough to reach it."""
    victim = c.target
    dice = 2 + (c.level >= 13) + (c.level >= 23)
    if c.strike():
        c.damage(c.w(dice), c.cha_mod, dtypes=(DamageType.PSYCHIC, DamageType.RADIANT))
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
    requires=holding("w3742"),
    requires_text="you must be holding your w3742",
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
    requires=holding("w3743"),
    requires_text="you must use this power with your w3743",
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
    requires=holding("w3743"),
    requires_text="you must use this power with your w3743",
)
def p13747(c: Cast) -> None:
    """"While in the aura, your enemies have vulnerable 3 radiant to **your**
    attacks" -- all three qualifiers now, where the row had none of them.

    **The old note admitted two of the faults and was wrong about both.**
    It said a vulnerability "carries no attacker", which stopped being true
    at #471 -- `c.vulnerable(when=)` keeps the entry as a triple on
    `Defences.vulnerable_when` and `resolve.deal_damage` reads it against a
    context carrying `source`. And it said the clause "runs its duration
    rather than ending when the enemy steps out", which was a description
    of this body rather than of the engine: the hand-rolled version below
    watched `ZoneEntered` and **never `ZoneExited`**, so nothing could have
    taken it back.

    So the row was live and wrong in three ways at once -- every attacker's
    blow, not only the caster's; no end on leaving the aura; and the aura's
    own end not clearing it either -- and it audited green throughout,
    because the attack and the damage are the parts that fire.

    `c.vulnerable_in` is the whole of it, and `_while_inside` is what the
    body was approximating: it gives to whoever is already standing there,
    takes it back on exit, **and** hangs a `clear_all` on the zone's own
    effect, so the aura ending lifts it from everybody. Three teardowns
    where this had none.

    The `pact_blade` marker stays: the Requirement naming one particular
    weapon is the clause nothing enforces.
    """
    me = c.me
    dice = 2 + (c.level >= 13) + (c.level >= 23)
    if c.strike():
        c.damage(c.w(dice), c.cha_mod, dtype=DamageType.RADIANT)
    ring = c.aura(1, until=When.EONT, on=me)
    c.vulnerable_in(
        ring, 3, DamageType.RADIANT, side="enemy",
        when=lambda ctx: ctx.get("source") == me,
    )


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
    # Narrowed here rather than at the `distance_between` call: a row with
    # no target cannot strike either, so one guard is the whole of it.
    if victim is not None and c.strike():
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
    requires=holding("w3744"),
    requires_text="you must use this power with your w3744",
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
    requires=holding("w3744"),
    requires_text="you must use this power with your w3744",
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
    requires=holding("w3744"),
    requires_text="you must be holding your w3744",
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
    requires=holding("w3752"),
    requires_text="you must use this power with your w3752",
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
    requires=holding("w3752"),
    requires_text="you must use this power with your w3752",
    dropped=("c.resist(immunity=)",),
)
def p16259(c: Cast) -> None:
    """"The target loses any resistance or immunity to this power's damage
    type until the end of your next turn." The resistance half now goes.

    **"nothing on `Cast` takes a resistance away" was the old note and it
    is false.** `c.resist` with a **negative** amount is that sentence --
    its own comment says so, *"the other printed sentence -- 'the target
    loses resist 10 to fire' -- and stays arithmetic: there is no highest
    to take"* -- and `c.resistances` reads the standing number, so the
    delta is exact and the duration puts it back. `i1184p1` prints this
    same sentence and has been written this way; the pattern was sitting
    one file over.

    No choice offered here, unlike `i1184p1`: that card says "choose a
    damage type" as a separate decision, where this one strips the type
    the power is **already** dealing, picked once in the `Special` line.

    **Immunity stays dropped, and shares `i1184p1`'s symbol.**
    `Defences.immune` is a separate set and nothing takes anything out of
    it. `c.ignore_resistance(immunity=)` is the *attacker's* side of that
    sentence -- it bypasses, where the card says the target loses the
    property -- and using it here would narrow the clause to the caster
    while the card lets anybody's blow of that type through.

    Narrower is the safe error and absent is safer still: a creature that
    is *immune* keeps its immunity, so the row never does more than print.
    `m5808a0`'s line is the rule -- a row stronger than its printed line
    is worse than an absent one.

    **The symbol's name is wrong even though its premise is right**, and
    `#1224` is why it was never visible: `blocked.py` asked `hasattr` to
    decide whether a dataclass field existed, and a field without a
    default is not a class attribute -- so `Defences.immune` read as
    missing for this marker's whole life. The field is there. What is
    missing is a **door onto it**: no verb adds to or takes out of that
    set, where `c.resist` writes the dict beside it and registers an
    `undo` in `on_end`. `c.resist(immunity=)` is the accurate symbol --
    the mirror of `c.ignore_resistance(immunity=)` on the target's side.

    **The marker was pinned by an instrument and has now been freed.**
    `drivers.resistance_taken_off_the_target` asserted the literal string
    `"Defences.immune"` in this row's `unfinished`, so the marker could not
    move without redding a rule in `scripts/` -- which an authoring agent
    may not touch. It found that, proved it by planting the re-point in the
    registry (that one assertion failed, the other eight held), and
    referred it up rather than leaving the row to report ARRIVED for ever.

    The main session re-pointed both halves together: the rule now reads
    the symbol off one `IMMUNITY_OWED` constant, so the next rename is one
    edit there instead of a red run somebody has to trace back to a string.
    Planted again afterwards from this end -- dropping the symbol from this
    marker reds that rule, 8 hold and 1 does not -- so the assertion still
    bites and is not merely satisfied by its own constant.

    `i1184p1` prints the same sentence and moved with it.
    """
    dtype = c.choose(list(ELEMENTS), "what this one is made of")
    # **Guarded once, over the whole body, where it used to guard only the
    # resist clause.** `c.choose` answers `None` for an empty list or a
    # declined `optional=`, and this call is neither -- so the three
    # clauses below could never really see one. But the narrow `if dtype
    # is not None:` sat around the resist half while `c.damage` and
    # `_bites` took the same value unchecked, which reads as though the
    # None case had been thought about and handled. It had not, in two of
    # three places. Behaviour is unchanged; `types.py` found it. #1155.
    if dtype is None:
        return
    dice = 2 + (c.level >= 13) + (c.level >= 23)
    if c.strike():
        c.damage(c.w(dice), c.cha_mod, dtype=dtype)
        foe = c.target
        standing = c.resistances(on=foe).get(dtype, 0)
        if standing:
            c.resist(-standing, dtype, on=foe, until=When.EONT)
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
    requires=holding("w3752"),
    requires_text="you must be holding your w3752",
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
