"""The adventuring day, arcade mode.

**Parallel to the story engine, not part of it.** Camille's framing: this is
a number of single combats the user asks for, each built to its own share of
the printed XP budget, with a rest between. The story engine is the other
thing that wants a day and wants it for different reasons -- a campaign that
remembers -- so the two are kept apart deliberately and only meet at
`story.budget`, which is the printed rule either way.

Nothing here is a new notion of difficulty. A leg's `scale` is a multiple of
`story.budget(level)`, which reads what the monsters are actually worth out
of the database, so a 1.25 leg is 25% more of the same currency rather than
a separate dial.
"""

from __future__ import annotations

#: The softest and hardest legs of the default curve.
OPENER = 0.75
FINALE = 1.25


def scales(count: int) -> list[float]:
    """The default difficulty curve for a day of `count` fights.

    A soft opener, a hard finale, and standard fights between -- so four legs
    come out `0.75, 1, 1, 1.25`, which is Camille's default and totals four
    times a standard encounter, the printed shape of an adventuring day.

    **Padded in the middle rather than stretched.** Camille's call: a longer
    day keeps one soft fight and one hard one and adds standard ones, rather
    than spreading the curve thinner. It matters less than it looks because
    the user sets the difficulties -- this is the starting point the page
    offers, not a rule.

    One fight is standard, because an opener with no finale after it is not
    an opener; two are the opener and the finale with nothing between.
    """
    if count <= 0:
        return []
    if count == 1:
        return [1.0]
    if count == 2:
        return [OPENER, FINALE]
    return [OPENER, *([1.0] * (count - 2)), FINALE]
