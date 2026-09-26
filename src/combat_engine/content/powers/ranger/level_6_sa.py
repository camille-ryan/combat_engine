"""Ranger level 6: patching a friend up by the strength of a Heal check."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    ONE_ALLY,
    Cast,
    Keyword,
    Melee,
    power,
)


@power(
    "p10622",
    level=6,
    cls="ranger",
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.MARTIAL, Keyword.HEALING],
)
def p10622(c: Cast) -> None:
    """Half the check, rounded down, and a saving throw against a poison.

    The check has no DC -- nothing is being beaten, the number itself is
    the payout -- so `c.check` is read for `.total` rather than for whether
    it succeeded. `c.save` follows the target, which is whose poison it is.
    """
    c.heal(c.check("heal").total // 2)
    c.save(against="poison")
