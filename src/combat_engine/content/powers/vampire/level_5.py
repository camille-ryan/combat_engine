"""Vampire, level 5.

One row. Its Effect line is four clauses, and the fourth is a drawback -- so
it is laid rather than quietly left out, which is the whole difference
between writing the card and writing the good half of it.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    DEX,
    EACH_OTHER,
    MOVE,
    REF,
    STANDARD,
    Attack,
    Cast,
    CloseBurst,
    Keyword,
    When,
    power,
)


@power(
    "p13859",
    level=5,
    cls="vampire",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.IMPLEMENT, Keyword.SHADOW],
    attack=Attack(DEX, vs=REF),
)
def p13859(c: Cast) -> None:
    """"Each creature in the burst" is `EACH_OTHER` and not `EACH_CREATURE`:
    the burst is centred on the caster and a close burst does not catch the
    square it comes out of, which is exactly the distinction `dsl.EACH_OTHER`
    exists for.

    The Effect line lands once and whether or not anything was hit, so it
    hangs on `c.last` -- which is True for an empty target list too.

    "You can shift up to your speed as a move action" is `c.shift_as`, a
    standing change to the action menu rather than a shift taken now. The
    speed is read at use, which is what the printed line says.
    """
    if c.strike():
        c.damage("2d10", c.dex_mod)
    else:
        c.half_damage("2d10", c.dex_mod)
    if not c.last:
        return
    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, kind="power")
    c.bonus("damage", 4, on=c.me, until=When.ENCOUNTER, kind="power")
    c.shift_as(MOVE, c.speed_of(), on=c.me, until=When.ENCOUNTER)
    c.no_surges(on=c.me, until=When.ENCOUNTER)
