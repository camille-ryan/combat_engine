"""Battlemind level 6: a stance that pays for every point spent augmenting."""

from __future__ import annotations

from combat_engine.content.powers.augment import spent_on
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

    The spend and the hit are separate moments, and what joins them is the
    row's ref. `augment.spent_on` is what the use landing right now paid;
    `c.points_spent` is the encounter's running total against that ref, so
    once a row had been augmented every later hit with it -- augmented or
    not -- would have paid out, and the payment would have grown.
    """
    c.stance(label="p12424")
    me = c.me

    def landed(ev: Hit) -> None:
        spent = spent_on(me, ev.power)
        if ev.attacker == me and spent:
            c.temp_hp(spent, on=me)

    c.watch(Hit, landed, until=When.STANCE, on=me, label="p12424")
