"""Warlock, level 7: the encounter attacks.

`p1351` is the only awkward one. "Roll twice and use the lower" is exactly
`c.reroll_attack(keep="worst")`, which reads the attack off `c.trigger` --
so the watch that answers the target's next roll hands itself the event
before calling it. The latch is kept by hand rather than with `once=True`,
because `once` spends itself by watching the log grow and a reroll writes no
event at all.

`p1461` cannot use `c.invisible`: that method only ever hides the caster,
and the printed line hides the whole party from one creature, so the
relations go on one effect directly and end together.
"""

from __future__ import annotations

from combat_engine.engine import (
    CHA,
    CON,
    EACH_CREATURE,
    ENCOUNTER,
    FORT,
    ONE_CREATURE,
    STANDARD,
    WILL,
    Attack,
    AttackRolled,
    Cast,
    CloseBlast,
    DamageType,
    Keyword,
    Ranged,
    Relation,
    When,
    power,
)

ARCANE_IMPLEMENT = [Keyword.ARCANE, Keyword.IMPLEMENT]


@power(
    "p1351",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=ARCANE_IMPLEMENT,
    attack=Attack(CHA, vs=WILL),
)
def p1351(c: Cast) -> None:
    """The second die is thrown in the `AttackRolled` window, which is where
    `resolve.attack` is still willing to read the result back."""
    victim = c.target
    if c.strike():
        c.damage("2d6", c.cha_mod)
    if victim is None:
        return
    spent = [False]

    def twice(ev: AttackRolled) -> None:
        if spent[0] or ev.attacker != victim:
            return
        spent[0] = True
        c.trigger = ev
        if c.reroll_attack(keep="worst"):
            c.note(f"{c.ref}: {victim} rolled twice and kept the worse face")

    c.watch(AttackRolled, twice, until=When.ENCOUNTER, label=c.ref)


@power(
    "p1461",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.PSYCHIC, Keyword.ILLUSION],
    attack=Attack(CHA, vs=WILL),
)
def p1461(c: Cast) -> None:
    """"In range" is the row's own ten squares, measured from the warlock."""
    victim = c.target
    if not c.strike():
        return
    c.damage("1d10", c.cha_mod, dtype=DamageType.PSYCHIC)
    if victim is None:
        return
    crowd = {c.me, *c.within(10, side="ally")}
    c.world.effects.apply(
        c.me,
        c.me,
        When.EONT,
        label=f"{c.ref} unseen",
        relations=[(Relation.HIDDEN_FROM, who, victim) for who in sorted(crowd)],
    )
    if c.build("fey"):
        c.note(f"{c.ref}: a Stealth bonus of {c.int_mod}, and there are no skills here")


@power(
    "p1462",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.POISON],
    attack=Attack(CON, vs=FORT),
)
def p1462(c: Cast) -> None:
    """"Held immobilized five feet off the ground" is immobilised: the engine
    has no third dimension for the height to mean anything in."""
    if c.strike():
        bonus = c.int_mod if c.build("infernal") else 0
        c.damage("2d8", c.con_mod + bonus, dtype=DamageType.POISON)
        c.immobilized()


@power(
    "p501",
    level=7,
    cls="warlock",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[*ARCANE_IMPLEMENT, Keyword.THUNDER, Keyword.FEAR],
    attack=Attack(CON, vs=FORT),
)
def p501(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", c.con_mod, dtype=DamageType.THUNDER)
        c.push(1 + c.int_mod if c.build("infernal") else 2)
