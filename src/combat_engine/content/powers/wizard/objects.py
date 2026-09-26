"""Wizard: the row whose target is a thing rather than a creature.

An object is `Scenery`: a square, a size and a footprint, no hit points and
no side, so it is in nobody's target pool until a row asks for one.
`Target(side="object")` is that ask, and the two clauses printed alongside
it -- "Medium or smaller", "not fastened in place or held by a creature" --
are `max_size` and `loose` on the same target line rather than checks in the
body. A body that filters its own target is a row that silently does
nothing; a target line that filters is a row the interface never offers.
"""

from __future__ import annotations

from combat_engine.engine import (
    ENCOUNTER,
    MOVE,
    Cast,
    Keyword,
    Ranged,
    Size,
    Target,
    When,
    power,
)


@power(
    "p14548",
    level=2,
    cls="wizard",
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(10),
    target=Target("object", 1, loose=True, max_size=Size.MEDIUM),
    keywords=[Keyword.ARCANE],
)
def p14548(c: Cast) -> None:
    """"You can move it farther by sliding it up to 5 squares as a move
    action" and "Sustain Move" are the same move action written twice: one
    says what it costs to keep the animation, the other what the cost buys.
    So there is one hold, sustained by a move, and the slide is what it pays
    out each time."""
    thing = c.target
    if thing is None:
        return
    animated = c.effect(f"{c.ref} animated", until=When.SUSTAIN, on=thing, sustain=MOVE)
    c.slide(5, on=thing)
    c.on_sustain(animated, lambda: c.slide(5, on=thing))
