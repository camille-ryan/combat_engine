"""Warlock, level 9: the dailies from the books after the first.

The class's settled readings hold: `c.build` answers the `infernal` and
`fey` legs and every other pact rider is named in a comment, a line printing
two damage types is one amount under the first of them, and nothing refunds
a use.

Three shapes recur here.

**"First Failed Saving Throw"** is `escalate`, which runs on exactly that.
**An Aftereffect** is `on_end`, which follows the hold going whichever way
it went -- the reading `rogue/level_5.py` settled. The two are different
clocks and a row printing both needs both.

**`c.prone(held=...)` written out longhand** appears once: it is a `PRONE`
hold on the encounter clock plus a `PINNED` hold on a shorter one, and a row
whose first failed save worsens the second of those needs to name it in
order to hang `escalate` on it.
"""

from __future__ import annotations

from combat_engine.engine import (
    CHA,
    CON,
    DAILY,
    EACH_CREATURE,
    FORT,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    STANDARD,
    WILL,
    AreaBurst,
    Attack,
    AttackDeclared,
    Cast,
    CloseBlast,
    Condition,
    DamageApplied,
    DamageType,
    Effect,
    Health,
    Keyword,
    MeleeOrRanged,
    Ranged,
    TurnStart,
    When,
    power,
)

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


def _backlash(c: Cast) -> None:
    """The Miss line this book gives its biggest dailies.

    "You do not expend this power" has no method, so what is written is the
    price paid and the bonus it buys against the same target.
    """
    if not c.may("take the backlash", who=c.me):
        return
    c.flat(5 + c.level // 2, dtype=DamageType.PSYCHIC, on=c.me)
    c.bonus("attack", 4, on=c.me, kind="power", until=When.EONT, once=True)


@power(
    "p10384",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CON, vs=FORT),
)
def p10384(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        _backlash(c)
        return
    c.damage("2d12", c.con_mod)
    if c.build("infernal"):
        c.slide(max(0, c.int_mod))
    if victim is None:
        return

    def spreads(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == c.me:
            return
        if ev.actor in c.enemies() and c.adjacent_to(victim, ev.actor):
            c.curse(on=ev.actor)

    c.watch(TurnStart, spreads, until=When.ENCOUNTER)


@power(
    "p11305",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON],
    attack=Attack(CON, vs=FORT),
)
def p11305(c: Cast) -> None:
    """The Aftereffect hangs on the hold's `on_end`, so it begins whichever
    way the petrification ended. The vestige pact and the augment it grants
    have no leg to ask for."""
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.half_damage("2d8", c.con_mod, dtype=DamageType.POISON)
        c.slowed(until=When.SAVE_ENDS)
        return
    c.damage("2d8", c.con_mod, dtype=DamageType.POISON)

    def afterwards() -> None:
        c.immobilized(until=When.SAVE_ENDS, on=victim)

    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=f"{c.ref} petrified",
        conditions=(Condition.PETRIFIED,),
        on_end=[afterwards],
    )


@power(
    "p12895",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=WILL),
)
def p12895(c: Cast) -> None:
    """"Has cover against all creatures except you" is not written: cover is
    computed from the board and nothing grants it to a creature outright.

    The prone and the hold that stops it standing are laid separately --
    which is all `c.prone(held=)` does -- so that the first failed save has
    a named effect to worsen.
    """
    victim = c.target
    if not c.strike():
        c.half_damage("2d8", c.cha_mod, dtype=DamageType.FIRE)
        c.immobilized()
        return
    c.damage("2d8", c.cha_mod, dtype=DamageType.FIRE)
    if victim is None:
        return
    c.prone()

    def worse(_eff: Effect) -> None:
        c.condition(
            Condition.REMOVED,
            until=When.SAVE_ENDS,
            on=victim,
            ongoing=(5, DamageType.FIRE),
        )

    c.condition(Condition.PINNED, until=When.SAVE_ENDS, escalate=worse)


@power(
    "p16494",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p16494(c: Cast) -> None:
    """Printed as "Constitution or Charisma", fixed once at first level; the
    Charisma line is the one written, as the class's other dual rows are."""
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.dazed(until=When.SAVE_ENDS)
        return

    def afterwards() -> None:
        c.dazed(until=When.SAVE_ENDS, on=victim)

    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=f"{c.ref} dominated",
        conditions=(Condition.DOMINATED,),
        save_mod=-2 if c.is_kind("aberrant", victim) else 0,
        on_end=[afterwards],
    )


@power(
    "p1873",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC, Keyword.RELIABLE],
    attack=Attack(CHA, vs=REF),
)
def p1873(c: Cast) -> None:
    # The dark pact rider -- ignoring necrotic resistance -- has no leg to
    # ask for, and nothing lets one damage roll walk past a resistance.
    if c.strike():
        c.damage("3d10", c.cha_mod, dtype=DamageType.NECROTIC)


@power(
    "p1921",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(CHA, vs=WILL),
)
def p1921(c: Cast) -> None:
    """The burn is an Effect line and lands on a miss as well; the spreading
    is `escalate`, which runs on the first failed save and no other."""
    if c.strike():
        c.damage("2d10", c.cha_mod, dtype=DamageType.PSYCHIC)

    def spreads(_eff: Effect) -> None:
        pool = sorted(f for f in c.enemies() if c.distance(f) <= 10)
        second = c.choose(pool, f"{c.ref}: who else it takes") if pool else None
        if second is not None:
            c.ongoing(5, DamageType.PSYCHIC, on=second)

    c.condition(
        until=When.SAVE_ENDS, ongoing=(10, DamageType.PSYCHIC), escalate=spreads
    )


@power(
    "p4098",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.ZONE],
    attack=Attack(CON, vs=WILL),
)
def p4098(c: Cast) -> None:
    """`c.burns` is the once-a-turn bite the printed line asks for, and it
    rolls its dice per bite. Moving the zone with a move action is not
    written: `c.zone` has no speed and nothing offers the action."""
    if c.target is not None and c.strike():
        c.damage("1d8", c.con_mod, dtype=DamageType.PSYCHIC)
        c.dazed(until=When.SAVE_ENDS)
    if not c.last:
        return
    area = c.area()
    if area:
        spirits = c.zone(area, label=c.ref, until=When.EONT, difficult=True)
        bite = f"1d8+{c.con_mod}" if c.con_mod > 0 else "1d8"
        c.burns(spirits, bite, DamageType.COLD)


@power(
    "p4109",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.COLD],
    attack=Attack(CHA, vs=FORT),
)
def p4109(c: Cast) -> None:
    """Held off the ground is restrained: there is no third dimension for the
    height to mean anything in, so the fey pact's taller version of the same
    sentence would change nothing even if there were a leg to ask for.

    The Aftereffect hangs on the hold's `on_end` -- the fall follows the
    hold going, whichever way it went.
    """
    victim = c.target
    if not c.strike() or victim is None:
        c.push(2)
        c.prone()
        return
    c.flat(c.cha_mod, dtype=DamageType.COLD)

    def falls() -> None:
        c.prone(on=victim)
        c.slide(2, on=victim)

    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=f"{c.ref} hoisted",
        conditions=(Condition.RESTRAINED,),
        on_end=[falls],
    )


@power(
    "p4115",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON],
    attack=Attack(CHA, vs=FORT),
)
def p4115(c: Cast) -> None:
    """The burn is an Effect line and lands on a miss too. The fey pact rider
    -- a minor action that ends the burn *and* slides three -- is not
    written: `drop_cost` would end the hold, and `on_end` cannot tell a
    deliberate end from a saving throw, so the slide would follow both.
    """
    victim = c.target
    if c.strike():
        c.damage("1d8", c.cha_mod)
    burn = c.ongoing(10, DamageType.POISON)
    if victim is None or burn is None:
        return

    def drags(ev: DamageApplied) -> None:
        if ev.target != victim or ev.dtype is not DamageType.POISON:
            return
        if ev.source == c.me and ev.amount > 0 and c.may("drag it a step", who=c.me):
            c.slide(1, on=victim)

    burn.subs.append(c.world.bus.on(DamageApplied, drags))


@power(
    "p4287",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CON, vs=FORT, plus=2),
)
def p4287(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        c.half_damage("3d10", c.con_mod, dtype=DamageType.NECROTIC)
        return
    c.damage("3d10", c.con_mod, dtype=DamageType.NECROTIC)
    hp = c.world.get(victim, Health) if victim is not None else None
    if hp is None or hp.hp > 0:
        return
    pool = sorted(f for f in c.within(3, of=victim, side="enemy") if f != victim)
    second = c.choose(pool, f"{c.ref}: what the death touches") if pool else None
    if second is not None and c.attack(c.cha_, FORT, on=second):
        c.damage("2d10", c.cha_mod, dtype=DamageType.NECROTIC, on=second)


@power(
    "p6860",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.TELEPORTATION],
    attack=Attack(CON, vs=REF),
)
def p6860(c: Cast) -> None:
    # The Ilmeth pact boon has no leg to ask for.
    victim = c.target
    if c.strike():
        c.damage("2d10", c.con_mod, dtype=DamageType.PSYCHIC)
    else:
        c.half_damage("2d10", c.con_mod, dtype=DamageType.PSYCHIC)
        return
    if victim is None:
        return

    def recoil(ev: AttackDeclared) -> None:
        if ev.attacker == victim and ev.target == c.me:
            c.flat(c.int_mod, dtype=DamageType.PSYCHIC, on=victim)

    c.watch(AttackDeclared, recoil, until=When.ENCOUNTER)


@power(
    "p6861",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CON, vs=FORT),
)
def p6861(c: Cast) -> None:
    # The Shax pact boon has no leg to ask for.
    if c.target is None:
        return
    c.prone()  # an Effect line: everything the blast covers falls
    if c.strike():
        c.damage("2d10", c.con_mod)
        c.push(max(0, c.int_mod))
    else:
        c.half_damage("2d10", c.con_mod)


@power(
    "p6955",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CHA, vs=WILL),
)
def p6955(c: Cast) -> None:
    """"Lose a healing surge" is `c.spend_surge`, which takes one and heals
    nobody -- which is what losing one means."""
    if c.strike():
        c.damage("3d8", c.cha_mod, dtype=DamageType.NECROTIC)
    else:
        c.half_damage("3d8", c.cha_mod, dtype=DamageType.NECROTIC)
    if c.may("pay a surge for the rot", who=c.me) and c.spend_surge(on=c.me):
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "p7506",
    level=9,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[*ARCANE_IMPLEMENT, Keyword.ACID, Keyword.POLYMORPH],
    attack=Attack(CON, vs=REF),
)
def p7506(c: Cast) -> None:
    """`c.overrun` is the only thing that walks through occupied squares and
    then says whose they were, so the printed shift is written as a trample.
    It walks rather than shifts, which is the one clause that does not
    survive -- leaving a square this way provokes where a shift would not.

    "Squeeze without penalties" has no method: `Condition.SQUEEZING` is the
    state and nothing exempts a creature from what it costs.
    """
    for caught in c.overrun():
        if c.attack(c.con_, REF, on=caught):
            c.damage("3d8", c.con_mod, dtype=DamageType.ACID, on=caught)
        c.push(1, on=caught)
