"""Seeker level 6."""

from __future__ import annotations

from combat_engine.content.powers.seeker import PRIMAL, bloodied_or_weakened
from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Condition,
    When,
    power,
)
from combat_engine.engine.events import Hit


@power(
    "p11479",
    level=6,
    cls="seeker",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
)
def p11479(c: Cast) -> None:
    """`Hit` carries the opportunity flag as a plain attribute rather than a
    field, which is what `by_opportunity` reads."""

    def spite(ev: Hit) -> None:
        if (
            ev.target == c.me
            and getattr(ev, "opportunity", False)
            and c.adjacent(ev.attacker)
        ):
            c.flat(c.str_mod, on=ev.attacker)

    c.watch(Hit, spite, until=When.EONT)


@power(
    "p9518",
    level=6,
    cls="seeker",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=PRIMAL,
    requires=bloodied_or_weakened,
    requires_text="must be bloodied or weakened",
)
def p9518(c: Cast) -> None:
    c.temp_hp(2 * c.wis_mod, on=c.me)
    if c.is_(Condition.WEAKENED, on=c.me):
        c.save(on=c.me, against="weakened")
