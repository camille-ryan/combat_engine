"""The paladin's second mark, shared by the two dozen rows that print it.

Later books give the paladin a mark it can hand out in passing -- a rider on
an attack rather than an action of its own. It holds like any mark and, on
top of that, bites for radiant damage the first time each round the marked
creature attacks without the paladin among the targets. That is the same
arrangement `p805` installs and with the same numbers; a bare `c.mark()` is
the half of it that costs nothing, and writing the watcher out per row would
be two dozen chances to get the once-a-round latch wrong.

`hold` hangs the whole thing on an effect that already exists, for the rows
printing "ongoing damage and <the mark> (save ends both)": two effects would
be two saving throws against a thing the book says is one.
"""

from __future__ import annotations

from combat_engine.engine import (
    Cast,
    DamageType,
    Effect,
    Relation,
    When,
    leaves_me_out,
)
from combat_engine.engine.events import AttackDeclared


def burning_mark(
    c: Cast,
    *,
    on: int | None = None,
    until: When = When.EONT,
    hold: Effect | None = None,
) -> Effect | None:
    """Mark a creature, and make attacking anybody else cost it."""
    who = c.target if on is None else on
    if who is None:
        return None
    me = c.me
    struck: dict[int, int] = {}

    def bite(ev: AttackDeclared) -> None:
        # "An attack that does not include you" is judged over the whole
        # attack rather than this one announcement: a burst that caught the
        # paladin would otherwise pay out off one of its other targets.
        if ev.attacker != who or not leaves_me_out(c.world, me, ev):
            return
        if struck.get(who) == c.world.round:
            return  # the first time each round, and no more
        struck[who] = c.world.round
        c.flat(3 + c.cha_mod, dtype=DamageType.RADIANT, on=who)

    if hold is None:
        held = c.mark(until=until, on=who)
        c.watch(AttackDeclared, bite, until=until, on=me, label=f"{c.ref} mark")
        return held
    c.world.relations.set(Relation.MARKED_BY, me, who)
    hold.relations.append((Relation.MARKED_BY, me, who))
    hold.subs.append(c.world.bus.on(AttackDeclared, bite, owner=me))
    return hold
