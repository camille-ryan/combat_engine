"""sorcerer powers."""

from __future__ import annotations

from combat_engine.engine import World


def has_familiar(world: World, eid: int) -> bool:
    """"Requirement: your familiar must be in its active mode."

    A familiar is a `Companion`, and passive mode is a state one of those can
    be in -- off the board, holding no square.

    **"In full" used to mean two of the three conditions.** This walked the
    companions itself and asked owner-and-not-passive, which a *destroyed*
    familiar satisfies: `resolve._die` leaves the body an entity and death
    does not touch `passive`. `query.familiar_active` is the one reader and
    asks the third condition too. #620.
    """
    from combat_engine.engine.query import familiar_active

    return familiar_active(world, eid) is not None
