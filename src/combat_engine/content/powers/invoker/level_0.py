"""Invoker, level 0: the two Channel Divinity features.

Both carry `group=CHANNEL_DIVINITY`, which is the printed "only one channel
divinity power per encounter" -- an allowance shared with every other row
that prints the same line, so it cannot be a per-row usage count.
"""

from __future__ import annotations

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    EACH_ENEMY,
    ENCOUNTER,
    MINOR,
    STANDARD,
    WILL,
    WIS,
    Attack,
    Cast,
    CloseBlast,
    DamageType,
    Hit,
    Keyword,
    Target,
    When,
    by_keyword,
    power,
)

EACH_UNDEAD = Target(side="any", everyone=True, label="Each undead creature in the blast")


@power(
    "p5186",
    level=0,
    cls="invoker",
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_UNDEAD,
    keywords=[Keyword.DIVINE, Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(WIS, vs=WILL),
    group=CHANNEL_DIVINITY,
)
def p5186(c: Cast) -> None:
    """The header's target can say "everyone in the blast" but not "every
    undead in the blast", so the creature type is a gate in the body. On a
    board with no undead the row is legal and does nothing, which is what
    the printed power does too."""
    if not c.is_kind("undead"):
        return
    dice = 1 + sum(c.level >= n for n in (5, 11, 15, 21, 25))
    if c.strike():
        c.damage(f"{dice}d10", c.wis_mod, dtype=DamageType.RADIANT)
        c.push(2)
        c.dazed(until=When.EONT)
    else:
        c.half_damage(f"{dice}d10", c.wis_mod, dtype=DamageType.RADIANT)


@power(
    "p7150",
    level=0,
    cls="invoker",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.DIVINE, Keyword.FEAR],
    group=CHANNEL_DIVINITY,
)
def p7150(c: Cast) -> None:
    """The push rides on a watch rather than on the penalty effect: it fires
    off somebody else's fear attack, so it has to read the `Hit` for the
    keyword rather than gate on anything this row did."""
    victim = c.target
    if victim is None:
        return
    c.penalty("attack", -1, until=When.EONT, on=victim)
    c.penalty("save", -1, until=When.EONT, on=victim)
    scared = by_keyword(Keyword.FEAR)

    def shove(ev: Hit) -> None:
        if ev.target == victim and scared(c.world, c.me, ev):
            c.push(1, on=victim)

    c.watch(Hit, shove, until=When.EONT, on=c.me, label=f"{c.ref} rout")
