"""Battlemind level 6: a stance that pays for every point spent augmenting."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Hit,
    Keyword,
    When,
    power,
)


@power(
    "p12424",
    level=6,
    cls="battlemind",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSIONIC, Keyword.STANCE],
)
def p12424(c: Cast) -> None:
    """Temporary hit points equal to the points that augmented the hit.

    `c.spend_points` records the spend against the row's own ref, which is
    what joins it to a hit that happens later -- the augment is declared
    when the power is used and the stance pays out when it lands.

    Every psionic row in the tree is written at Augment 0 today, so this
    pays nothing until the augment clauses are written; it is not the
    stance that is missing anything. Driven by hand with two points spent
    on a row, the hit hands over two temporary hit points.
    """
    c.stance(label="p12424")
    me = c.me

    def landed(ev: Hit) -> None:
        spent = c.points_spent(ev.power)
        if ev.attacker == me and spent:
            c.temp_hp(spent, on=me)

    c.watch(Hit, landed, until=When.STANCE, on=me, label="p12424")
