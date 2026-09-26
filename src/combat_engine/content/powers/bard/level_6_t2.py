"""Bard, level 6: a hold changing hands."""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MINOR,
    ONE_ALLY,
    Cast,
    CloseBurst,
    Keyword,
    When,
    power,
)


@power(
    "p2374",
    level=6,
    cls="bard",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.ARCANE],
)
def p2374(c: Cast) -> None:
    """Ending the hold and writing a fresh one by hand is a different thing:
    it loses the conditions, the ongoing damage and the saving throw already
    owed. `c.transfer` rebuilds the same effect on the new subject, and
    refuses a hold carrying a relation or a watcher rather than dropping half
    of it -- so those are filtered out of the choice too.

    The saving-throw bonus goes on the effect itself rather than as a modifier
    to every save the new subject rolls, which is what "against that effect"
    says."""
    victim = c.target
    if victim is None:
        return
    holds = [
        e
        for e in c.world.effects.of(victim)
        if e.when is When.SAVE_ENDS and not e.relations and not e.subs
    ]
    if not holds:
        return
    takers = [c.me] + [a for a in c.allies() if a != victim and c.distance(to=a) <= 5]
    hold = c.choose(holds, "which effect moves")
    taker = c.choose(takers, "who takes it")
    if hold is None or taker is None:
        return
    c.transfer(hold, to=taker, save_mod=c.con_mod)
