"""Sorcerer, level 6: bigger blasts and bursts.

`dsl._stretched` now reads `"blast_size"` for a close blast, a close burst
**and** an area burst, and takes the row being measured as a gate -- so
"your arcane powers' blasts and bursts" is the printed sentence rather than
every area the sorcerer has.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Keyword,
    When,
    power,
)

from .level_2_t3 import arcane_power


@power(
    "p5275",
    level=6,
    cls="sorcerer",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE],
)
def p5275(c: Cast) -> None:
    """A burst's `within` is untouched, which is right: the printed line
    makes the blast bigger, not the distance it may be thrown."""
    c.bonus("blast_size", 1, on=c.me, until=When.EOT, when=arcane_power)
