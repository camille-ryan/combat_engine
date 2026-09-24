"""Wizard, level 0: the cantrips.

None of these has a battlefield effect. They light a room, make a noise,
fetch a thing off a shelf, or produce a small harmless illusion -- the last
of which says outright that it cannot deal damage, serve as a weapon, or
hinder a creature. So they carry `out_of_combat=True` rather than an
invented mechanic, and the body is a note: the effect is the fiction.
"""

from __future__ import annotations

from combat_engine.engine import (
    AT_WILL,
    MINOR,
    NO_TARGET,
    STANDARD,
    Cast,
    Keyword,
    Ranged,
    power,
)


@power(
    "p1217",
    level=0,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def p1217(c: Cast) -> None:
    c.note("p1217: a sound, from a whisper to a shout, from a chosen square")


@power(
    "p1225",
    level=0,
    cls="wizard",
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def p1225(c: Cast) -> None:
    c.note("p1225: bright light out to 4 squares, until the encounter ends")


@power(
    "p1227",
    level=0,
    cls="wizard",
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE, Keyword.CONJURATION],
    out_of_combat=True,
)
def p1227(c: Cast) -> None:
    c.note("p1227: a floating hand that carries one object of 20 pounds or less")


@power(
    "p1930",
    level=0,
    cls="wizard",
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(2),
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    out_of_combat=True,
)
def p1930(c: Cast) -> None:
    c.note("p1930: one small harmless effect, three at a time")
