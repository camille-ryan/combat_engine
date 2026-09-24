"""Cleric, level 1."""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    ONE_CREATURE,
    REF,
    STANDARD,
    WIS,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Ranged,
    When,
    power,
)

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]


@power(
    "p841",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p841(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.wis_mod, dtype=DamageType.RADIANT)
        # An ally gets a bonus to its *next* attack roll, and only against
        # this target. Both halves of that are the `when` gate and `once`.
        friends = [a for a in c.allies() if c.can_see(a)]
        if friends:
            mark = c.target
            c.bonus(
                "attack",
                2,
                on=c.choose(friends, "who gets the opening"),
                until=When.ENCOUNTER,
                once=True,
                when=lambda ctx: ctx.get("target") == mark,
            )


@power(
    "p889",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=REF),
)
def p889(c: Cast) -> None:
    if c.strike():
        c.damage("1d6", c.wis_mod, dtype=DamageType.RADIANT)
        friends = [a for a in c.allies() if c.can_see(a)]
        if not friends:
            return
        ally = c.choose(friends, "who is helped")
        # The printed line lets the *ally* pick, so the question goes to
        # whoever is playing the ally rather than to the cleric.
        saves = [e for e in c.world.effects.of(ally) if e.when is When.SAVE_ENDS]
        wants = c.world.decide(
            ally, "choose", ["save", "temporary hit points"], "which do you take"
        )
        if saves and wants == "save":
            c.world.effects.save(saves[0])
        else:
            c.temp_hp(c.cha_mod + c.level // 2, on=ally)
