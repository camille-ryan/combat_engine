"""Warlock, level 1.

Implement powers throughout: no Weapon keyword, so no proficiency rides
along with the attack.

Several rows lean on a pact or on a creature's size, neither of which a
`requires` predicate can read. Where that is the case the rest of the row is
written and the missing clause is called out in a comment rather than
approximated. The curse itself is `cf:warlock-curse`, and `c.cursed(...)`
reads it -- and `cursed_by_me` is the same question asked of a trigger, which
is what arms the three pact boons.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    CHA,
    CON,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Ranged,
    Target,
    When,
    distance,
    power,
)
from combat_engine.engine.events import DamageApplied, Dropped, Moved, TurnStart
from combat_engine.engine.triggers import Trigger, cursed_by_me

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]

#: The three pact boons all pay out on the same line, so it is written once.
_CURSED_DROPS = "an enemy you have cursed drops to 0 hit points or fewer"
_ON_CURSED_DROPS = Trigger(Dropped, when=cursed_by_me, text=_CURSED_DROPS)


@power(
    "p1319",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT, Keyword.FEAR],
    attack=Attack(CHA, vs=WILL),
)
def p1319(c: Cast) -> None:
    if c.strike():
        c.damage("3d6", c.cha_mod, dtype=DamageType.RADIANT)
        c.immobilized()
    else:
        c.half_damage("3d6", c.cha_mod, dtype=DamageType.RADIANT)
        c.slowed()
    # The Effect line lands whatever the attack did.
    c.penalty(WILL, 2, until=When.SAVE_ENDS)


@power(
    "p1323",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CON, vs=REF),
)
def p1323(c: Cast) -> None:
    if c.strike():
        c.damage("3d10", c.con_mod, dtype=DamageType.FIRE)
    c.ongoing(5, DamageType.FIRE)


@power(
    "p1333",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=REF),
)
def p1333(c: Cast) -> None:
    # Printed as "Charisma or Constitution", fixed once at 1st level. A
    # header holds one ability, so this is the Charisma build.
    if c.strike():
        c.damage("1d10", c.cha_mod)


@power(
    "p1334",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.FEAR],
    attack=Attack(CHA, vs=WILL),
)
def p1334(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.cha_mod, dtype=DamageType.PSYCHIC)
        # The Star Pact line would make this 1 + Intelligence modifier.
        # Pacts are not modelled, so the base number stands.
        c.penalty(WILL, 1)


@power(
    "p1376",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(CON, vs=WILL),
)
def p1376(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.con_mod, dtype=DamageType.NECROTIC)
        # The Infernal Pact line would add Intelligence modifier here.
        c.temp_hp(5, on=c.me)


@power(
    "p1456",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p1456(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.cha_mod, dtype=DamageType.PSYCHIC)
        # "and you are invisible to the target until the start of your next
        # turn" -- there is no invisibility in the engine, and blinding the
        # target is a different and much stronger thing. Left out.


@power(
    "p1457",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.RADIANT, Keyword.FEAR],
    attack=Attack(CHA, vs=FORT),
)
def p1457(c: Cast) -> None:
    # Printed as "Charisma or Constitution", fixed at 1st level; Charisma here.
    if not c.strike():
        return
    c.damage("1d6", c.cha_mod, dtype=DamageType.RADIANT)

    victim = c.target
    mine = c.here
    fired = False

    def closing(ev: Moved) -> None:
        # "The first time the target moves closer to you on its next turn."
        nonlocal fired
        if fired or ev.actor != victim:
            return
        if distance(ev.to, mine) >= distance(ev.from_, mine):
            return
        fired = True
        # The extra damage is printed untyped, unlike the hit line.
        c.flat(c.world.rng.roll("1d6").total + c.cha_mod, on=victim)

    c.watch(Moved, closing, until=When.EOTNT)


@power(
    "p1458",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CON, vs=REF),
)
def p1458(c: Cast) -> None:
    if not c.strike():
        return
    c.damage("1d6", c.con_mod, dtype=DamageType.FIRE)

    victim = c.target
    fired = False

    def scorch(ev: DamageApplied) -> None:
        # "The first time you take damage before the end of your next turn."
        nonlocal fired
        if fired or ev.target != c.me or ev.amount <= 0:
            return
        fired = True
        c.flat(
            c.world.rng.roll("1d6").total + c.con_mod,
            dtype=DamageType.FIRE,
            on=victim,
        )

    c.watch(DamageApplied, scorch, until=When.EONT, on=c.me)


@power(
    "p1459",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.FIRE],
    attack=Attack(CHA, vs=REF),
)
def p1459(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.cha_mod, dtype=DamageType.FIRE)
        # The Fey Pact line would make this 2 + Intelligence modifier.
        c.penalty("attack", 2)


@power(
    "p1460",
    level=1,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    # Printed target is "one creature of size Large or smaller". Targets
    # cannot be filtered by size, so the restriction is only written down.
    target=Target("enemy", 1, label="One creature of size Large or smaller"),
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CON, vs=FORT),
)
def p1460(c: Cast) -> None:
    if c.strike():
        c.damage("2d8", c.con_mod)
        # The Infernal Pact line would make this 1 + Intelligence modifier.
        c.slide(2)


@power(
    "p1471",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.CHARM],
    attack=Attack(CHA, vs=WILL),
)
def p1471(c: Cast) -> None:
    if c.strike():
        c.damage("3d10", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.slide(3)
    else:
        c.half_damage("3d10", c.cha_mod, dtype=DamageType.PSYCHIC)
    # The Effect line -- a save-ends hold that grants the caster a minor
    # action to slide the target 1 square, once per round -- has no shape
    # here: there is no plain labelled save-ends effect, and nothing that
    # hands somebody an extra action for the duration. Left out.


@power(
    "p2094",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    # Prerequisite: Fey Pact. Not expressible, so not declared as a
    # requirement -- a `requires` predicate has nothing to read.
    trigger=_CURSED_DROPS,
    on=_ON_CURSED_DROPS,
)
def p2094(c: Cast) -> None:
    c.teleport(3)


@power(
    "p2095",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    # Prerequisite: Infernal Pact. See p2094.
    trigger=_CURSED_DROPS,
    on=_ON_CURSED_DROPS,
)
def p2095(c: Cast) -> None:
    c.temp_hp(c.level, on=c.me)


@power(
    "p222",
    level=1,
    cls="warlock",
    usage=DAILY,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.COLD],
)
def p222(c: Cast) -> None:
    c.temp_hp(10 + c.int_mod, on=c.me)
    # An aura 1 for the board to draw, and the bite hung off turn starts --
    # the printed line only fires for an enemy *starting* its turn adjacent,
    # so `hazard`, which also bites on entry, would be too generous.
    c.aura(1, until=When.ENCOUNTER)
    mine = c.me

    def chill(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == mine:
            return
        if ev.actor in c.enemies() and c.adjacent(ev.actor):
            c.flat(
                c.world.rng.roll("1d6").total + c.con_mod,
                dtype=DamageType.COLD,
                on=ev.actor,
            )

    c.watch(TurnStart, chill, until=When.ENCOUNTER, on=c.me)


@power(
    "p2263",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    # Prerequisite: Star Pact. See p2094.
    trigger=_CURSED_DROPS,
    on=_ON_CURSED_DROPS,
)
def p2263(c: Cast) -> None:
    # Printed as +1 to any single d20 roll during your next turn: attack,
    # save, skill or ability check, the holder's choice. Only attack rolls
    # can carry a modifier here, so that is what it lands on -- `once` spends
    # it on the first roll, and the duration drops it if it goes unused.
    c.bonus("attack", 1, on=c.me, until=When.EONT, once=True)
