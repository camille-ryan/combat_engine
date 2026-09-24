"""Cleric, level 1."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    WIS,
    Attack,
    Cast,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    When,
    get,
    power,
)

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]
DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]


def _melee_at(foe: int | None) -> Callable[[dict[str, Any]], bool]:
    """Gate a bonus on "melee attack rolls against the target".

    The gate is handed the attacking power's id, so melee-ness is read off
    that row's declared reach: most melee rows carry no melee *keyword*, so
    asking for one would silently never pay the bonus.
    """

    def gate(ctx: dict[str, Any]) -> bool:
        if ctx.get("target") != foe:
            return False
        p = get(ctx.get("power") or "")
        return p is not None and p.reach is not None and p.reach.kind == "melee"

    return gate


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


@power(
    "p1580",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p1580(c: Cast) -> None:
    """The guard covers you and one neighbour, so it is two separate bonuses."""
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        c.bonus(AC, 1, on=c.me)
        beside = [a for a in c.within(1, side="ally") if a != c.me]
        if beside:
            c.bonus(AC, 1, on=c.choose(beside, "who shelters with you"))


@power(
    "p839",
    level=1,
    cls="cleric",
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=DIVINE_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p839(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)
        friends = [a for a in c.within(5, side="ally") if a != c.me]
        if friends:
            c.bonus(
                "attack",
                3,
                on=c.choose(friends, "who gets the opening"),
                when=_melee_at(c.target),
            )
