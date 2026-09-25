"""Paladin, level 10: utility. Two rows, both about saving throws.

`p1446` rolls against every save-ends effect a target is carrying rather
than calling `c.save`, which takes one and stops -- the printed line is
"every effect that a save can end", and which one `c.save` would have found
first is an accident of insertion order.

The level's third row is left out; see the report.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    MINOR,
    STANDARD,
    Cast,
    CloseBurst,
    Keyword,
    Ranged,
    Target,
    When,
    power,
)

DIVINE = [Keyword.DIVINE]


@power(
    "p1446",
    level=10,
    cls="paladin",
    usage=DAILY,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ALLY,
    keywords=DIVINE,
)
def p1446(c: Cast) -> None:
    who = c.target
    if who is None:
        return
    for effect in list(c.world.effects.of(who)):
        if effect.when is When.SAVE_ENDS and not effect.ended:
            c.world.effects.save(effect)


@power(
    "p31",
    level=10,
    cls="paladin",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=Target("ally", 1, label="You or one ally"),
    keywords=DIVINE,
)
def p31(c: Cast) -> None:
    """The `"ally"` pool includes the caster, which is "you or one ally"
    exactly; `ONE_ALLY` is the same thing under a card that reads wrong."""
    c.save(on=c.target, bonus=2)
