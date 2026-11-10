"""Vampire, level 3.

One row, and its Special line is this class's recurring trade: a healing
surge spent for something extra. The surge is read off `Health` before the
offer so that a character with none is not asked, and `c.spend_surge` is
still the thing that pays -- it refuses on its own if something has barred
the spend since.
"""

from __future__ import annotations

from combat_engine.engine import (
    DEX,
    ENCOUNTER,
    ONE_CREATURE,
    REF,
    STANDARD,
    Attack,
    Cast,
    Health,
    Keyword,
    Melee,
    When,
    power,
)

#: The two things the Special line buys, as the words the chooser shows.
_MORE_DAMAGE = "2d8 extra damage"
_SECOND = "a second creature"


@power(
    "p13857",
    level=3,
    cls="vampire",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.SHADOW],
    attack=Attack(DEX, vs=REF),
)
def p13857(c: Cast) -> None:
    """The choice is offered before the roll, because one of the two answers
    changes who is attacked.

    The second creature is a second roll of this same attack rather than an
    appended target. `c.add_target` reaches the use running *below* this one
    -- which is what an immediate interrupt wants and is `None` for a row
    adding to its own list -- so the shape is `battlemind/level_9.py`'s
    `p13056`: `c.strike(on=other)` and `c.damage(on=other)`.

    The extra dice are a rolled damage modifier rather than a second packet:
    `c.bonus("damage", 0, dice=)` joins the blow, where a second `c.damage`
    would meet a resistance twice and be maxed separately on a critical.
    """
    victim = c.target
    if victim is None:
        return
    health = c.world.get(c.me, Health)
    spare = [e for e in c.within(1, side="enemy") if e != victim]
    picked = None
    if health is not None and health.surges > 0:
        options = [_MORE_DAMAGE, *([_SECOND] if spare else [])]
        picked = c.choose(
            options, f"{c.ref}: lose a healing surge for", optional=True
        )
        if picked is not None and not c.spend_surge():
            picked = None
    if picked == _MORE_DAMAGE:
        c.bonus("damage", 0, dice="2d8", on=c.me, until=When.EOT, once=True)
    if c.strike():
        c.damage("2d12", c.dex_mod)
    if picked != _SECOND:
        return
    second = c.choose(spare, f"{c.ref}: the second creature")
    if second is not None and c.strike(on=second):
        c.damage("2d12", c.dex_mod, on=second)
