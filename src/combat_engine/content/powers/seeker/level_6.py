"""Seeker level 6."""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.seeker import PRIMAL, bloodied_or_weakened
from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Condition,
    Keyword,
    Position,
    When,
    distance,
    power,
)
from combat_engine.engine.events import Hit, MoveEnd, MoveStart


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


@power(
    "p9517",
    level=6,
    cls="seeker",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[*PRIMAL, Keyword.ILLUSION],
)
def p9517(c: Cast) -> None:
    """The form itself carries nothing, so it is a named hold with the two
    watches clocked on the encounter and taken down when it ends -- a second
    effect on `When.SUSTAIN` would confuse the sustain bookkeeping.

    "At least 3 squares from where you started" is measured, not counted:
    where the move began is remembered on `MoveStart`, which fires before
    the first step.
    """
    me, world = c.me, c.world
    form = c.effect(c.ref, until=When.SUSTAIN, on=me, sustain=MINOR)
    run: dict[str, Any] = {"from": None}

    def on_start(ev: MoveStart) -> None:
        if ev.actor == me:
            pos = world.get(me, Position)
            run["from"] = pos.square if pos else None

    def on_end(ev: MoveEnd) -> None:
        began = run["from"]
        if ev.actor == me and began is not None and distance(began, ev.at) >= 3:
            c.conceal(on=me, until=When.EONT)

    for kind, fn in ((MoveStart, on_start), (MoveEnd, on_end)):
        held = c.watch(kind, fn, until=When.ENCOUNTER, on=me)
        if form is not None:
            form.on_end.append(
                lambda h=held: world.effects.end(h, "the form ended")
            )
