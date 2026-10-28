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

from typing import Any

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
from combat_engine.engine.events import (
    AttackRolled,
    DamageApplied,
    Dropped,
    Moved,
    SavingThrow,
    SkillCheck,
    TurnStart,
)
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
    attack=Attack((CHA, CON), vs=REF),
    basic="ranged",
)
def p1333(c: Cast) -> None:
    # Printed as "Charisma or Constitution", fixed once at 1st level. The
    # header now holds both and `Attack.ability_for` takes whichever this
    # warlock is better at, which is the pick a player makes. The damage
    # line follows it through `c.attack_mod` rather than naming Charisma:
    # the printed line is "+ your attacking ability modifier", so a
    # Constitution warlock added the wrong modifier to every hit.
    if c.strike():
        c.damage("1d10", c.attack_mod)


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
    attack=Attack((CHA, CON), vs=FORT),
)
def p1457(c: Cast) -> None:
    # Printed as "Charisma or Constitution", fixed at 1st level. See p1333
    # for why the header holds both and the damage reads `c.attack_mod`.
    if not c.strike():
        return
    c.damage("1d6", c.attack_mod, dtype=DamageType.RADIANT)

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
    c.instead_of("temp_hp", lambda: c.temp_hp(c.level, on=c.me))


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


def one_d20_bonus(c: Cast) -> None:
    """"A +1 bonus to any single d20 roll you make during your next turn."

    Shared with `f292`, which prints the same sentence again on top of this
    one, so the shape lives here rather than twice.

    **Four holds and one shared ender**, which is the whole of the
    difficulty. Each key already spends itself at the moment it is *read*:
    `c.bonus(once=True)` watches `AttackRolled` for `attack`, `SavingThrow`
    for `save` and `SkillCheck` for `skill` and `ability_check`, and its own
    comment records that getting that pairing wrong six times is why an
    unrecognised key now refuses rather than guesses. But `once=` is per
    hold, so four of them are four bonuses where the card gives one. The
    ender is what makes them a single roll's worth, and `c.end_effect`'s
    docstring names this as the sanctioned shape.

    **Four keys because there are four readers**, and a single key would
    reach only one of them: `skills.modifier` totals `skill:<name>` plus
    `skill`, `skills.ability_check` totals the ability's own word plus
    `ability_check`, `Effects.roll_saves` totals `save`, and none of those
    sees `attack`.

    Every one of the four is read **before** the ender can fire, which is
    what makes the roll that spends the bonus the roll that got it: the
    attack and save totals are summed before their events are announced,
    and both check paths total inside the resolve callback `Bus.emit` runs
    between the two windows. `Effects.end` is idempotent, so a key firing
    its own spend before the shared ender reaches it costs nothing.

    Untyped and stacking, which is the printed "cumulative": three drops in
    one window lay three sets and the roll that spends them all adds +3.
    """
    me = c.me
    holds = [
        hold
        for key in ("attack", "save", "skill", "ability_check")
        if (hold := c.bonus(key, 1, on=me, until=When.EONT, once=True))
        is not None
    ]
    if not holds:
        return

    def spend(ev: Any) -> None:
        # `attacker` on an attack roll, `actor` on a save or a check. Both
        # asked, because somebody else's roll must not spend this.
        if (getattr(ev, "attacker", None) != me
                and getattr(ev, "actor", None) != me):
            return
        for hold in holds:
            c.end_effect(hold, why="spent on a d20 roll")

    for event in (AttackRolled, SavingThrow, SkillCheck):
        c.watch(event, spend, until=When.EONT, on=me, label=c.ref)


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
    """+1 to any single d20 roll during your next turn, the holder's choice.

    **Written: the one-shot spans kinds now.** The old note was right that
    `c.bonus(once=True)` does it for one kind of roll and that the gap was
    a one-shot spanning four. It was wrong that only attack rolls can carry
    a modifier here -- the save and both check paths each read one -- so the
    row no longer lands the whole card on the attack roll.

    **Re-pointed: this is not `c.boost_roll` either.** That verb (#495) adds
    to the roll on the table, and this bonus is banked *before* any of the
    four rolls happens.
    """
    one_d20_bonus(c)
