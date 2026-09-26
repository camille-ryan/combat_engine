"""Shaman, level 6: the zone of bright light.

The spec entry said `c.strike(ignore_cover=True)` is per-call only. The
standing `c.ignore_cover` exists and takes the attack context as a gate, so
"against any enemy that is within the zone" is asked of the live zone rather
than frozen into the squares at the moment of casting.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    DAILY,
    MINOR,
    NO_TARGET,
    AreaBurst,
    Cast,
    Keyword,
    When,
    power,
)


@power(
    "p5398",
    level=6,
    cls="shaman",
    usage=DAILY,
    action=MINOR,
    reach=AreaBurst(5, 10),
    target=NO_TARGET,
    keywords=[Keyword.PRIMAL, Keyword.ZONE],
)
def p5398(c: Cast) -> None:
    """The gate asks `world.zones.occupants` rather than the square set, so
    an enemy that walks into the light is lit and one that walks out is not.

    "Any enemy takes a -5 penalty to Stealth checks" is a skill check and
    there are none, so it is dropped rather than approximated.
    """
    light = c.zone(c.area(), label=c.ref, until=When.EONT)

    def inside(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") in c.world.zones.occupants(light)

    for who in (c.me, *c.allies()):
        c.ignore_cover(on=who, until=When.EONT, when=inside)
