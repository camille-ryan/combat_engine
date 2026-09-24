"""Paladin, level 7: encounter attacks.

Two of the four need a word about their header.

`p778` prints its crit range on the attack line and conditions it on the
mark, so the modifier is put on just before the swing and gated to this row
-- `crit_range` is read at the moment of the roll, which is what lets the
condition be asked then rather than fixed now.

`p1300` has no primary attack at all: the primary target is an ally, the
Effect swaps the two of them, and the only attack is the secondary one the
header carries. Its printed range line is "Melee weapon" while its primary
target is an ally a Wisdom modifier away, and one `reach` has to serve both.
It is `Melee(5)` rather than `Ranged(5)`: a `Ranged` reach on a row carrying
`Keyword.WEAPON` demands a ranged weapon of whoever holds it, so a paladin
with a sword could never use the row at all -- and the attack it makes
really is a melee one, which is what decides cover and provoking. The five
is a ceiling for the pool `candidates` offers; the printed Wisdom limit is
enforced in the body.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    CHA,
    EACH_ENEMY,
    ENCOUNTER,
    ONE_CREATURE,
    ONE_OTHER_ALLY,
    STANDARD,
    STR,
    WILL,
    Attack,
    Cast,
    CloseBurst,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    When,
    power,
)

DIVINE_IMPLEMENT = [Keyword.DIVINE, Keyword.IMPLEMENT]
DIVINE_WEAPON = [Keyword.DIVINE, Keyword.WEAPON]


@power(
    "p1244",
    level=7,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=DIVINE_IMPLEMENT,
    attack=Attack(CHA, vs=WILL),
)
def p1244(c: Cast) -> None:
    if c.strike():
        c.damage("2d10", c.cha_mod)
        c.pull(max(0, c.wis_mod))


@power(
    "p1300",
    level=7,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(5),
    target=ONE_OTHER_ALLY,
    keywords=[*DIVINE_WEAPON, Keyword.TELEPORTATION],
    attack=Attack(CHA, vs=AC),
)
def p1300(c: Cast) -> None:
    """The swap is the Effect line and happens whatever follows it.

    "If an enemy is now within your melee reach" is asked after the two of
    them have moved, which is the whole point of the row: the paladin lands
    where the ally was standing and swings at whatever was pressing it.
    """
    friend = c.target
    if friend is None or c.distance(friend) > max(1, c.wis_mod):
        return
    c.swap(friend)
    pool = sorted(c.within(1, side="enemy"))
    foe = c.choose(pool, "who the blade finds") if pool else None
    if foe is not None and c.strike(on=foe):
        c.damage(c.w(2), c.cha_mod, on=foe)


@power(
    "p1445",
    level=7,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[*DIVINE_IMPLEMENT, Keyword.RADIANT],
    attack=Attack(CHA, vs=WILL),
)
def p1445(c: Cast) -> None:
    if c.strike():
        c.damage("1d8", c.cha_mod, dtype=DamageType.RADIANT)
        c.dazed()


@power(
    "p778",
    level=7,
    cls="paladin",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[*DIVINE_WEAPON, Keyword.THUNDER],
    attack=Attack(STR, vs=AC),
)
def p778(c: Cast) -> None:
    """The wider crit range is gated to this row's own attack.

    Ungated it would have widened every swing the paladin made for the rest
    of the turn, which is a different card. `c.marked()` is asked before the
    modifier goes on because nothing can change the mark between here and
    the roll.
    """
    if c.marked():
        c.bonus(
            "crit_range", 1, until=When.EOT, on=c.me,
            when=lambda ctx: ctx.get("power") == c.ref,
        )
    if c.strike():
        c.damage(c.w(2), c.str_mod, dtype=DamageType.THUNDER)
        c.prone()
