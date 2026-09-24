"""Rogue, level 2.

The whole level is skill utilities, and the model has no skills: no
training, no checks, no rerolling one. Two of the five rows still land on
the battlefield -- a move and a hide, and a shift -- and are written out.
The other three *are* their check and nothing else, so they carry
`out_of_combat=True` and a note rather than an invented mechanic.

The Prerequisite lines gate *taking* these at character creation rather
than using them, so none of them is declared as a `requires`.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    PERSONAL,
    SELF,
    Cast,
    Keyword,
    power,
)

MARTIAL = [Keyword.MARTIAL]


@power(
    "p1038",
    level=2,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p1038(c: Cast) -> None:
    """Move your speed, then go unseen.

    The printed row waives the movement penalty on the check and keeps the
    normal requirements to hide; neither is rolled here, so what is left is
    the walk and the concealment `c.hide()` holds until something breaks it.
    """
    c.move(c.speed_of())
    c.hide()


@power(
    "p1395",
    level=2,
    cls="rogue",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=MARTIAL,
)
def p1395(c: Cast) -> None:
    c.shift(c.speed_of())


@power(
    "p1039",
    level=2,
    cls="rogue",
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p1039(c: Cast) -> None:
    c.note("p1039: a jump with a running start, its distance uncapped by speed")


@power(
    "p1040",
    level=2,
    cls="rogue",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    trigger="you dislike the result of a check you just made",
    out_of_combat=True,
)
def p1040(c: Cast) -> None:
    c.note("p1040: reroll that check, and the second result is the one that counts")


@power(
    "p1394",
    level=2,
    cls="rogue",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=MARTIAL,
    out_of_combat=True,
)
def p1394(c: Cast) -> None:
    c.note("p1394: a check that normally costs a standard action, made as a minor")
