"""Bard, level 9: the dailies that hang an effect on the caster's own aura."""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.bard._shared import aura_allies, in_aura
from combat_engine.engine import *


@power(
    "p14469",
    level=9,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
)
def p14469(c: Cast) -> None:
    """"The first time each turn" has no header field to say it -- header
    `once_per_round` is a round and belongs to `c.on_attack` -- so it is a
    flag cleared by a `TurnStart` listener.

    **Noted:** the damage is credited to the caster. `c.flat` sources from
    the caster and nothing lets a row deal damage *as* somebody else, so
    "that ally deals damage" is the right amount from the wrong hand.
    """
    spent: list[int] = []

    def missed(ev: Any) -> None:
        if spent or ev.attacker not in aura_allies(c):
            return
        row = get(ev.power)
        if row is None or row.usage is not Usage.AT_WILL:
            return
        spent.append(1)
        c.flat(c.cha_mod, on=ev.target)

    c.watch(Miss, missed, until=When.ENCOUNTER)
    c.watch(TurnStart, lambda ev: spent.clear(), until=When.ENCOUNTER)


@power(
    "p14470",
    level=9,
    cls="bard",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p14470(c: Cast) -> None:
    """`c.vulnerable` says neither half of this: it is scoped neither to who
    dealt the damage nor to a zone. Adding to the rolled damage is, so the
    listener does both gates at once.

    **Noted:** a roll is bumped before resistance where real vulnerability
    applies after it, so a resistant enemy comes out 2 apart from the card.
    """

    def extra(ev: Any) -> None:
        if ev.source not in c.allies() or ev.target not in c.enemies():
            return
        if in_aura(c, ev.target):
            ev.amount += 2

    c.watch(DamageRolled, extra, until=When.ENCOUNTER)
