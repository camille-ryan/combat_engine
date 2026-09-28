"""Warlock, level 1.

Implement powers throughout: no Weapon keyword, so no proficiency rides
along with the attack.

**The pacts are readable now and the pact lines are written.** Four rows
print "if you have the Fey/Infernal/Star Pact, this number is different",
and each used to stand at the base number under a comment saying pacts
were not modelled. `chargen.BUILDS["warlock"]` carries a leg for every
one of them, so `c.build("fey")` is the gate and the printed number goes
in. A pact *Prerequisite* on a whole row is still chargen's, not
`Power.requires`: that one is asked mid-fight and a build choice does not
change between rounds.

The curse itself is `cf:warlock-f4`, and `c.cursed(...)` reads it -- and
`cursed_by_me` is the same question asked of a trigger, which is what
arms the three pact boons.

Clauses this file cannot say now carry `dropped=` rather than a comment.
A prose note is invisible to `todo.py`, `audit.py` and `issues.py`, so a
row that has quietly lost a printed sentence reads as finished; four
rows here were in exactly that state, and one of them -- the
invisibility on `p1456` -- was waiting on a verb that already existed.
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
    dropped=("c.ability_for(ref)",),
)
def p1333(c: Cast) -> None:
    # Printed as "Charisma or Constitution", fixed once at 1st level. A
    # header holds one ability, so this is the Charisma build -- the
    # Constitution half is dropped, not absent, and nineteen rows want
    # the same reader for it.
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
        # The Star Pact line, which is `cf:warlock-f1s5`: `c.build("star")`
        # answers whether this character took that pact, so the pact
        # number is written rather than dropped.
        c.penalty(WILL, 1 + c.int_mod if c.build("star") else 1)


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
        # The Infernal Pact line, `cf:warlock-f1s3`, adds Intelligence.
        c.temp_hp(5 + (c.int_mod if c.build("infernal") else 0), on=c.me)


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
        # "You are invisible to the target until the start of your next
        # turn." `c.invisible(to=)` is the one-watcher form and its
        # default duration is the printed one. The note that used to
        # stand here said the engine had no invisibility; it has, and the
        # clause had been silently gone with no `dropped=` to show it.
        c.invisible(to=c.target, on=c.me, until=When.SONT)


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
    dropped=("c.ability_for(ref)",),
)
def p1457(c: Cast) -> None:
    # Printed as "Charisma or Constitution", fixed at 1st level; Charisma
    # here, and the other half marked rather than left in prose. See p1333.
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
        # The Fey Pact line, `cf:warlock-f1s2`.
        c.penalty("attack", 2 + c.int_mod if c.build("fey") else 2)


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
        # The Infernal Pact line, `cf:warlock-f1s3`. It replaces the
        # distance rather than adding to it, so it is the smaller number
        # for a warlock with no Intelligence to speak of -- written as
        # printed, not as the better of the two.
        c.slide(1 + c.int_mod if c.build("infernal") else 2)


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
    dropped=("c.grant_action(slide=)",),
)
def p1471(c: Cast) -> None:
    """The Effect line is half written and half marked.

    The hold itself is `c.effect`, a labelled save-ends effect and
    nothing more -- the old note here said there was no such thing, and
    there is. It matters on its own: the label is this row's ref, so
    `c.suffering("p1471")` names who is under it and the target owes a
    save every round until it is out.

    What the hold is *for* is dropped. "You can slide the target 1
    square as a minor action once per round" is a standing line in the
    caster's action menu, and `c.grant_action` reads four words --
    `shift`, `stand`, `escape`, `second_wind` -- none of which move
    somebody else. `c.give` is charges rather than a per-round licence
    and would have to invent a number of them.
    """
    if c.strike():
        c.damage("3d10", c.cha_mod, dtype=DamageType.PSYCHIC)
        c.slide(3)
    else:
        c.half_damage("3d10", c.cha_mod, dtype=DamageType.PSYCHIC)
    c.effect(c.ref, until=When.SAVE_ENDS)


@power(
    "p2094",
    level=1,
    cls="warlock",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    # Prerequisite: Fey Pact -- `cf:warlock-f1s2`, the build leg
    # `c.build("fey")` reads. It is expressible now, and it is still not
    # written as `requires=`: a Prerequisite is settled when the
    # character is built and `Power.requires` is asked of a creature on
    # a board mid-fight. Whether a warlock holds this row at all is
    # chargen's answer, the same as a feat's gate.
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
    dropped=("c.boost_roll()",),
)
def p2263(c: Cast) -> None:
    # Printed as +1 to any single d20 roll during your next turn: attack,
    # save, skill or ability check, the holder's choice. Only attack rolls
    # can carry a modifier here, so that is what it lands on -- `once` spends
    # it on the first roll, and the duration drops it if it goes unused.
    # The other three kinds of roll are a `dropped=` rather than a note:
    # one bonus offered across four different rolls, spent by whichever
    # comes first, is what `c.boost_roll()` names and twelve rows want.
    # "Cumulative" needs nothing -- three drops lay three of these and
    # each is spent by the same roll, which is the printed +3.
    c.bonus("attack", 1, on=c.me, until=When.EONT, once=True)
