"""Battlemind, level 6: the one that knows where everybody is.

The spec entry wanted `c.ignore_cover` as a standing effect rather than an
argument to one `c.strike`, and named `c.no_advantage` as the half that had
already been built. Both exist; what was still missing was the gate --
`query.has_combat_advantage` read the `no_advantage` modifier with an empty
context, so "you don't grant combat advantage to **those** creatures" could
only have been written as the unconditional sentence.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Keyword,
    When,
    power,
)

#: What "living" rules out. Everything else on a 4e board breathes.
UNLIVING = ("undead", "construct")


def _sensed(c: Cast, who: int | None) -> bool:
    if who is None or c.distance(who) > 10:
        return False
    return not any(c.is_kind(word, on=who) for word in UNLIVING)


@power(
    "p11168",
    level=6,
    cls="battlemind",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC],
)
def p11168(c: Cast) -> None:
    """Both clauses are gated on the same question, asked of whichever end
    of the attack the modifier sits on: `no_advantage` lives on the
    battlemind and is read with the **attacker** named, `ignore_cover` lives
    on the battlemind and is read with the **target** named.

    `partial=True` on the second, because the printed line waives the -2 and
    says nothing about superior cover.

    "You know the location of all living creatures within 10 squares" is not
    written. `c.truesight` is the nearest thing and it reveals the unliving
    too, which is more than printed; the two clauses above are what the row
    is bought for and neither depends on the sense being modelled.
    """
    def attacker_is_known(ctx: dict[str, Any]) -> bool:
        return _sensed(c, ctx.get("attacker"))

    def target_is_known(ctx: dict[str, Any]) -> bool:
        return _sensed(c, ctx.get("target"))

    c.no_advantage(until=When.EONT, when=attacker_is_known)
    c.ignore_cover(until=When.EONT, partial=True, when=target_is_known)
