"""Artificer, level 2: the springboard.

`c.jump` is the missing verb -- a jump clears what is in the way and the
distance does not come off the turn's movement, which is neither `c.move`
nor `c.shift`. It is written as a move with the rough going and the standing
bodies ignored for its length.

**The springboard is a zone of one square rather than a conjuration.** The
question this row asks is "who entered the square", and that is diffed for
zones and not for a conjuration's position: `c.conjure` gives an entity with
a `Position` and nothing announces stepping onto it. The keyword stays as
printed.

"Only once per turn" is latched per round, which is the clock the body can
read; the difference shows only if a creature crosses the square twice in a
round on two different turns, which it cannot.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    NO_TARGET,
    STANDARD,
    Cast,
    Keyword,
    Ranged,
    When,
    ZoneEntered,
    power,
)


@power(
    "p4137",
    level=2,
    cls="artificer",
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CONJURATION],
)
def p4137(c: Cast) -> None:
    spots = sorted(c.world.reachable_squares(c.me, 1))
    where = c.origin or (c.choose(spots, "where the springboard goes") if spots else c.here)
    board = c.zone({where}, label="p4137", until=When.SUSTAIN, sustain=MINOR)
    reach = max(1, c.wis_mod)
    side = {c.me, *c.allies()}
    sprung: dict[int, int] = {}

    def spring(ev: ZoneEntered) -> None:
        if ev.zone != board or ev.actor not in side:
            return
        if sprung.get(ev.actor) == c.world.round:
            return
        sprung[ev.actor] = c.world.round
        c.jump(reach, on=ev.actor)

    c.watch(ZoneEntered, spring, until=When.ENCOUNTER, on=c.me, label="p4137")
