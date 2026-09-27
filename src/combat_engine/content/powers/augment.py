"""Buying an augment with power points.

Ardent, psion and battlemind rows print "Augment 1" and "Augment 2"
clauses: the caster may spend that many points out of `PowerPoints` to use
a different form of the same power. Which form is a decision, so it goes
through `c.choose`.

**The order of the options is the answer for every headless fight.**
`World.decide` takes the first option when no decider is installed, and
`HandPolicy.decide` does the same for a `choose` it has no rule for --
there is no augment feature in `policy.features` for it to weigh. So the
options run richest first: a point not spent by the end of the encounter
is lost, which makes spending it the better default of the two, and it is
also the only ordering under which an augment clause is ever reached.

The answer is settled once per use and remembered on the cast, because the
body runs once per target and the points are spent once for the whole use.
"""

from __future__ import annotations

from combat_engine.engine import Cast


def augment(c: Cast, most: int = 2) -> int:
    """Power points spent on this use. 0 is the form printed above Augment 1.

    `most` is the highest augment **the row can honour**, which is not
    always the highest it prints: a clause that needs a different range or
    a wider target line cannot be written in a body at all, because
    targeting happens before the body runs. Those are recorded in
    `docs/blocked.json` and left out of the offer rather than approximated.
    """
    held = getattr(c, "augment_spend", None)
    if held is not None:
        return held
    afford = min(most, c.points())
    picked = c.choose([*range(afford, 0, -1), 0], "power points to augment")
    spent = c.spend_points(picked) if picked else 0
    c.augment_spend = spent
    return spent
