"""Psion, level 10: resistance that only answers the far attacks.

The spec entry asked for the same `Callable[[dict], bool]` gate `c.bonus`
takes. `c.resist(when=...)` is it: `Defences.resist` is a flat number per
type with nowhere to hang a condition, so the gated form lays a modifier and
`resolve.damage` reads it after the flat one.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    EACH_ALLY,
    ENCOUNTER,
    MINOR,
    Cast,
    CloseBurst,
    DamageType,
    Keyword,
    When,
    get,
    power,
)

CHOICES = [
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.FORCE,
    DamageType.LIGHTNING,
    DamageType.NECROTIC,
    DamageType.RADIANT,
    DamageType.THUNDER,
]

#: "Ranged or area attacks". A close blast is neither: it comes off the
#: attacker's own square, and the printed line leaves it out.
FROM_AFAR = ("ranged", "area_burst")


def _far(ctx: dict[str, Any]) -> bool:
    p = get(ctx.get("power", ""))
    return p is not None and p.reach.kind in FROM_AFAR


@power(
    "p11323",
    level=10,
    cls="psion",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ALLY,
    keywords=[Keyword.PSIONIC],
)
def p11323(c: Cast) -> None:
    """One type for the whole burst, so the choice is made on the first
    target and applied to all of them at once rather than asked again per
    ally -- "choose cold, fire, ..." is one decision, not one each.
    """
    if not c.first:
        return
    dtype = c.choose(CHOICES, "which damage type")
    if dtype is None:
        return
    for who in dict.fromkeys([c.me, *c.targets]):
        if who is not None:
            c.resist(5 + c.int_mod, dtype, on=who, until=When.EONT, when=_far)
