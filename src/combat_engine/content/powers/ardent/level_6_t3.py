"""Ardent, level 6: two allies who cover each other's flanks.

The spec entry asked for `when=` on `c.cannot_be_flanked`, the same gate
`c.bonus` takes. The argument is half of it; the other half was that
`query.has_combat_advantage` read the `unflankable` modifier with an empty
context, so any gate written against it would have been false forever and
the row would have suppressed nothing while looking finished. It is now
handed the attacker and the target.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    MINOR,
    Cast,
    Keyword,
    Ranged,
    Target,
    World,
    power,
)
from combat_engine.engine.query import distance_between, enemies, flanked_by


def _flanked(world: World, who: int) -> bool:
    """Is anybody flanking this creature at all?

    The printed exception is "unless both are flanked", which names no
    attacker -- so it is asked of the board rather than of the swing being
    resolved.
    """
    return any(flanked_by(world, who, foe) for foe in enemies(world, who))


@power(
    "p11101",
    level=6,
    cls="ardent",
    usage=DAILY,
    action=MINOR,
    reach=Ranged(5),
    target=Target(side="ally", count=2),
    keywords=[Keyword.PSIONIC],
)
def p11101(c: Cast) -> None:
    """Written once for the pair rather than once per target, because the
    gate each of them carries names the other one.

    "Or you and one ally": a single target is paired with the ardent, which
    is the second printed reading of the target line.
    """
    if not c.first:
        return
    pair = [w for w in c.targets if w is not None]
    if len(pair) == 1 and pair[0] != c.me:
        pair.append(c.me)
    if len(pair) != 2:
        return
    world = c.world
    for who, partner in ((pair[0], pair[1]), (pair[1], pair[0])):

        def covered(_ctx: dict[str, Any], who: int = who, partner: int = partner) -> bool:
            return (
                distance_between(world, who, partner) <= 5
                and not _flanked(world, partner)
            )

        c.cannot_be_flanked(on=who, when=covered)
