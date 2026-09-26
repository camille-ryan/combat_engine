"""What more than one warlock file needs.

`_backlash` was written out twice, byte for byte, in `level_1_b.py` and
`level_9_b.py`. Five refs in each file call it.
"""

from __future__ import annotations

from combat_engine.engine import Cast, DamageType, When


def backlash(c: Cast) -> None:
    """The Miss line several of these share: pay psychic damage for a bonus.

    "You do not expend this power" is the half that is still not said.
    Nothing gave a use back when this was written, so what is here is the
    price and the bonus it buys against the same target.
    """
    if not c.may("take the backlash", who=c.me):
        return
    c.flat(5 + c.level // 2, dtype=DamageType.PSYCHIC, on=c.me)
    c.bonus("attack", 4, on=c.me, kind="power", until=When.EONT, once=True)
