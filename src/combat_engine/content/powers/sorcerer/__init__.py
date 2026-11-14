"""sorcerer powers."""

from __future__ import annotations

from combat_engine.engine import World


def wild_even(c, shot) -> bool:  # noqa: ANN001
    """Does this row's Wild Magic clause fire on this attack?

    Eight rows print one, each as *"If you rolled an even number on the
    attack roll, ..."* under the sorcerer's Wild Magic class feature, and
    the gate is the same two questions every time -- which is what makes
    this a shared helper rather than eight copies: `content/CLAUDE.md`
    allows one for a run of rows that genuinely share a marker, and these
    shared a *premise*.

    **The premise was wrong and that is why they were all dropped.** Seven
    of their docstrings said the clause "goes with the fork", meaning the
    build was not dealt. `cf:sorcerer-f0s3` is indeed absent from the tree
    -- but `chargen.BUILDS["sorcerer"]`'s first leg is named `wild`, so the
    build *is* dealt and `c.build` has always answered it. A missing
    class-feature row was read as a missing build.

    `AttackResult.parity` and not `natural % 2`, deliberately: `p5845` lets
    a sorcerer declare the roll odd or even whatever the die said, and that
    field is the only thing carrying the declared answer. Reading the die
    here would quietly ignore it.

    **Asks nothing about hitting**, which is the one thing not to fold in
    here. The printed clause attaches to a different line on different
    cards: `p3162`'s replaces the push inside the Hit, `p5279`'s widens an
    Effect that lands either way, and `p5264`'s sits between Hit and Miss.
    A hit test in the gate would silently impose one card's shape on all
    eight, so each row applies this where its own clause sits. #1303.
    """
    return shot is not None and c.build("wild") and shot.parity == "even"


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
