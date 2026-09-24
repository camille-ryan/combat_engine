"""Warlock, level 6: utility. Four personal rows, no attack.

`p1368` walks the path itself rather than calling `c.move`, because the
whole of its printed line is *how* the warlock is moving: `mode_of` never
picks "climb" on its own, so a granted climb speed alone would have left it
walking, and `c.moving_as("climb")` -- which is what a climbing rider reads
-- would have stayed false.

`p1402` puts its three modifiers on one effect so that the printed "you can
end this effect as a minor action" ends all three together, which is what
`drop_cost` is for.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    ONE_OTHER_ALLY,
    PERSONAL,
    SELF,
    AttackRolled,
    Cast,
    Keyword,
    Mod,
    Ranged,
    Trigger,
    When,
    by_me,
    power,
)
from combat_engine.engine.movement import walk

ARCANE = [Keyword.ARCANE]

_A_ROLL_I_DISLIKE = "you make a roll you dislike"


@power(
    "p1326",
    level=6,
    cls="warlock",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
    trigger=_A_ROLL_I_DISLIKE,
    on=Trigger(AttackRolled, when=by_me, text=_A_ROLL_I_DISLIKE),
)
def p1326(c: Cast) -> None:
    """"Using the higher of the two results" is `keep="best"`.

    Declared on the attack roll only. The printed line also offers a skill
    check, an ability check and a saving throw: the first two are not rolled
    by this engine at all, and `SavingThrow` is announced after the effect
    has already been judged, so there is nothing left to reroll.
    """
    if c.reroll_attack(keep="best"):
        c.note("p1326: the die is thrown again and the better face stands")


@power(
    "p1368",
    level=6,
    cls="warlock",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p1368(c: Cast) -> None:
    pace = c.speed_of()
    c.mode("climb", pace, until=When.EOT)
    paths = c.world.reachable_paths(c.me, pace)
    if not paths:
        return
    dest = c.world.decide(c.me, "move", sorted(paths), f"{c.ref}: climb {pace}")
    walk(c.world, c.me, paths[dest], mode="climb")


@power(
    "p1402",
    level=6,
    cls="warlock",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=ARCANE,
)
def p1402(c: Cast) -> None:
    c.world.effects.apply(
        c.me,
        c.me,
        When.ENCOUNTER,
        label=c.ref,
        mods=[
            (c.me, Mod(what=AC.value, value=2, kind="power", label=c.ref)),
            (c.me, Mod(what=FORT.value, value=2, kind="power", label=c.ref)),
            (c.me, Mod(what="speed", value=-2, kind="untyped", label=c.ref)),
        ],
        drop_cost=MINOR,
    )


@power(
    "p2264",
    level=6,
    cls="warlock",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(10),
    target=ONE_OTHER_ALLY,
    keywords=[Keyword.ARCANE, Keyword.TELEPORTATION],
)
def p2264(c: Cast) -> None:
    """"Willing" is why the ally is asked before the two of them move."""
    friend = c.target
    if friend is not None and c.may("trade places", who=friend):
        c.swap(friend)
