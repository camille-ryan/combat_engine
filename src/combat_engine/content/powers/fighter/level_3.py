"""Fighter, level 3: encounter attacks."""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DEX,
    EACH_ENEMY,
    ENCOUNTER,
    ONE_CREATURE,
    REF,
    STANDARD,
    STR,
    Attack,
    Cast,
    CloseBurst,
    Keyword,
    Melee,
    When,
    power,
)
from combat_engine.engine.query import hidden_from

from .grips import BRUTAL, FINESSE, wielding_any

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]


@power(
    "p200",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p200(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(2), c.str_mod)
        if c.wielding("polearm") or c.wielding("heavy blade"):
            c.immobilized()


@power(
    "p2176",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC, plus=4),
)
def p2176(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.str_mod)


#: The weapon clause on `p268`, which also wants Dexterity 15.
_THIRD_SWING = ("flail", "light blade", "spear")


@power(
    "p268",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p268(c: Cast) -> None:
    """Two swings, and a third for the right weapon and enough Dexterity.

    The third is offered against anything in reach, which is how "either the
    target or a different creature" reads once the first two have landed --
    a target that died to them is simply not in the pool any more.
    """
    for _ in range(2):
        if c.strike():
            c.damage(c.w(1))
    # `c.dex_` is the attack bonus; the printed line wants the raw score.
    if c.stats.score(DEX) < 15 or not any(c.wielding(group) for group in _THIRD_SWING):
        return
    pool = c.within(1, side="enemy")
    who = c.choose(pool, "who the third swing catches") if pool else None
    if who is not None and c.strike(on=who):
        c.damage(c.w(1), on=who)


@power(
    "p291",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p291(c: Cast) -> None:
    """The burst already checks line of effect. "You can see" rules out one
    more thing that does not: an enemy hidden from you.

    The `Weapon:` rider was missing and unmarked -- half a Strength modifier to
    the attack for four groups. #236. Half, rounded down, which is what "one-half
    your Strength modifier" means for a bonus."""
    if c.target is None or c.me in hidden_from(c.world, c.target):
        return
    if c.strike(plus=c.str_mod // 2 if wielding_any(c, BRUTAL) else 0):
        c.damage(c.w(1), c.str_mod)


@power(
    "p622",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=AC),
)
def p622(c: Cast) -> None:
    # **`f2370`'s second benefit, written here rather than laid from the
    # feat.** "When you attack with a power associated with this feat, the
    # power gains the invigorating keyword" -- and a row's keywords are one
    # tuple fixed at import and shared by everybody who holds it, so only
    # this creature's copy can gain one. #550's convention: the row holding
    # the thing is the row that asks.
    #
    # Granted before the attack, because that is when it has to be true:
    # `f758`'s +1 reads the attacking power's keywords during the roll, and
    # the weaponmaster's miss clause asks after. `dsl.keywords_of` folds the
    # grant in; `Power.keywords` would not see it.
    if c.feat("f2370"):
        c.counts_as_keyword(c.ref, Keyword.INVIGORATING, on=c.me,
                            until=When.ENCOUNTER)
    if c.strike():
        heavy = any(c.wielding(group) for group in ("axe", "hammer", "mace"))
        c.damage(c.w(2), c.str_mod + (c.con_mod if heavy else 0))


@power(
    "p634",
    level=3,
    cls="fighter",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(STR, vs=REF),
)
def p634(c: Cast) -> None:
    """**Two `Weapon:` lines, not one**, and both were missing: the same grip
    pays the attack roll *and* the damage roll a Dexterity modifier. #236.

    Asked once and spent twice, because one weapon is in hand and the card's two
    lines name the same groups -- re-asking would be the same question twice."""
    finesse = c.dex_mod if wielding_any(c, FINESSE) else 0
    if c.strike(plus=finesse):
        c.damage(c.w(1), c.str_mod + finesse)
