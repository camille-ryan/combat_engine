"""The rogue tactic that is about not being seen.

Four tactics are printed and `features/strikers.py` writes the two that
`chargen.BUILDS["rogue"]` had legs for. This is the third leg and the row
that rides it.

**Half of the printed feature is not written and cannot be.** Two of its
three clauses remove a Stealth penalty -- the -5 for moving more than two
squares and the -10 for running -- and the engine imposes neither, so
taking one away would be taking away nothing. What is here is the clause
that stands on its own: move three squares from where the turn began and
roll to go unseen.

The DC is the best enemy's passive Perception, which is 10 plus its check
modifier and is the rule rather than an invented number.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    ActionType,
    Build,
    Cast,
    Keyword,
    MoveEnd,
    Square,
    TurnStart,
    When,
    World,
    distance,
    power,
)


def _sneak_leg(world: World, eid: int) -> bool:
    """Did this rogue take the leg this tactic is on?"""
    chosen = world.get(eid, Build)
    return chosen is not None and "sneak" in chosen.choices


@power(
    "cf:rogue-tactic-stealth",
    level=0,
    cls="rogue",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.MARTIAL],
    requires=_sneak_leg,
    requires_text="needs the tactic that goes unseen after moving",
)
def rogue_tactic_stealth(c: Cast) -> None:
    """Move three squares from where your turn began and you may vanish.

    The square the turn started in is remembered rather than derived: a
    `MoveEnd` carries where the creature is and nothing carries where it
    stood when the turn opened, and a rogue that walks, shifts and walks
    again has moved three squares in total while no single move was three.

    The printed proviso is "if you have any cover or concealment", which the
    check itself stands in for -- the board's cover is measured attacker by
    attacker and the roll is one number against the whole room.
    """
    me = c.me
    opened: dict[int, Square] = {}

    def remember(ev: TurnStart) -> None:
        if ev.actor == me:
            opened[0] = c.here

    def slipped(ev: MoveEnd) -> None:
        if ev.actor != me or opened.get(0) is None:
            return
        if distance(opened[0], ev.at) < 3:
            return
        watching = [c.passive("perception", of=foe) for foe in c.enemies()]
        if c.check("stealth", max(watching) if watching else 10):
            c.hide()

    c.watch(
        TurnStart, remember, until=When.ENCOUNTER, on=me,
        label="cf:rogue-tactic-stealth start",
    )
    c.watch(
        MoveEnd, slipped, until=When.ENCOUNTER, on=me,
        label="cf:rogue-tactic-stealth",
    )
