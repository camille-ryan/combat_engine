"""Fighter, level 2: all utility, no attack rolls."""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    ENCOUNTER,
    MINOR,
    MOVE,
    ONE_ALLY,
    PERSONAL,
    SELF,
    Cast,
    Forced,
    Keyword,
    Melee,
    When,
    power,
)
from combat_engine.engine.events import TurnStart
from combat_engine.engine.grid import distance
from combat_engine.engine.movement import forced

MARTIAL = [Keyword.MARTIAL]


@power(
    "p1119",
    level=2,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p1119(c: Cast) -> None:
    c.temp_hp(c.roll("2d6") + c.con_mod, on=c.me)


@power(
    "p1120",
    level=2,
    cls="fighter",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=MARTIAL,
)
def p1120(c: Cast) -> None:
    """"To a square adjacent to you" is the whole of this row, and `c.slide`
    takes no `to` -- an anchor does nothing to a slide, so the mover's decider
    would be free to walk the ally anywhere within two squares. The square is
    picked here instead, from the ones that both satisfy the printed line and
    can actually be reached, and the slide goes through `forced`, which takes
    a destination the way `c.push` and `c.pull` already do.

    Nothing happens when no such square is free: ending adjacent is not
    optional, so there is no lesser version of this to fall back to.
    """
    friend = c.target
    if friend is None:
        return
    spots = [sq for sq in c.world.reachable_squares(friend, 2) if distance(sq, c.here) <= 1]
    where = c.choose(spots, "where the ally ends up")
    if where is not None:
        forced(c.world, c.me, friend, Forced.SLIDE, 2, to=where)


@power(
    "p1522",
    level=2,
    cls="fighter",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL, Keyword.HEALING, Keyword.STANCE],
)
def p1522(c: Cast) -> None:
    """Regeneration is not something the engine holds, so it is written out:
    healing at the start of each of your turns, and only while bloodied.

    The listener is hung off the stance rather than given a `When.STANCE`
    duration of its own -- a second stance-clocked effect would confuse
    `Effects.stance_of`, and taking another stance has to end the healing
    with it.
    """
    me = c.me
    amount = 2 + c.con_mod
    stance = c.stance(label="p1522")

    def regenerate(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost and c.bloodied(on=me):
            c.heal(amount, on=me)

    watching = c.watch(
        TurnStart, regenerate, until=When.ENCOUNTER, on=me, label="p1522 regeneration"
    )
    stance.on_end.append(lambda: c.world.effects.end(watching, "stance ended"))
