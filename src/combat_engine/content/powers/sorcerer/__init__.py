"""sorcerer powers."""

from __future__ import annotations

from combat_engine.engine import World


def has_familiar(world: World, eid: int) -> bool:
    """"Requirement: your familiar must be in its active mode."

    A familiar is a `Companion`, and passive mode is a state one of those can
    be in -- off the board, holding no square -- so the printed line is asked
    in full: one of yours, and active.
    """
    from combat_engine.engine.components import Companion

    return any(
        world.get(e, Companion).owner == eid and not world.get(e, Companion).passive
        for e in world.having(Companion)
    )
