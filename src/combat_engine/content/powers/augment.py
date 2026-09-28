"""Buying an augment with power points.

Ardent, psion and battlemind rows print "Augment 1" and "Augment 2"
clauses: the caster may spend that many points out of `PowerPoints` to use
a different form of the same power. Which form is a decision, so it goes
through `c.choose`.

**There are two places that decision can be taken, and the row picks.**

A clause that only changes the dice or adds a rider is settled here, in
the body, by `c.choose` -- the arrangement below, and the one about sixty
rows use.

A clause that rewrites the **header** cannot be: a close burst where the
base is a melee swing, a second target, a longer reach, a charge. Targets
are chosen before the body runs, so by the time this function could ask,
the answer is already too late to matter. Those rows declare every one of
their augments in the header as `dsl.Augment`, `dsl.use(augment=)` settles
the spend above targeting, and `actions.legal` offers each affordable form
as its own entry. `augment()` still answers for them -- it reads
`Cast.augment`, which is already paid for -- so a body reads the spend the
same way whichever arrangement its row uses.

**The order of the options is the answer for every headless fight.**
`World.decide` takes the first option when no decider is installed, and
`HandPolicy.decide` does the same for a `choose` it has no rule for --
there is no feature in `policy.features` for a body-side augment to weigh.
(A header-side one is a whole `Action` and *is* weighed, by
`augment_cost`, which is why that half does not need this rule.) So the
options run richest first: a point not spent by the end of the encounter
is lost, which makes spending it the better default of the two, and it is
also the only ordering under which an augment clause is ever reached.

The answer is settled once per use and remembered on the cast, because the
body runs once per target and the points are spent once for the whole use.
"""

from __future__ import annotations

from combat_engine.engine import Cast

#: What the most recent use of a row was bought with, by (caster, ref).
#: Read **while that use is still resolving**: "your unaugmented attacks
#: deal 1d6 extra" is a rider on a `Hit`, and a `Hit` carries the ref and
#: nothing about how the row was paid for. `PowerPoints.augmented` answers
#: a different question -- it is the encounter's running total, so once a
#: row has been augmented it reads as augmented for the rest of the fight.
_LAST: dict[tuple[int, str], int] = {}


def spent_on(who: int, ref: str) -> int:
    """How many points bought that creature's current use of that row.

    0 for a row nobody augments, which is what "unaugmented" means for the
    three rows that ask.
    """
    return _LAST.get((who, ref), 0)


def augment(c: Cast, *offers: int) -> int:
    """Power points spent on this use. 0 is the form printed above Augment 1.

    `offers` are the augments **the row can honour**, which are not always
    the ones it prints: a clause needing a different range or a wider
    target line cannot be written in a body at all, because targeting
    happens before the body runs. Those are recorded in
    `docs/blocked.json` and left out of the offer rather than
    approximated, which is why a row may offer 2 and not 1.
    """
    from combat_engine.engine import get

    declared = get(c.ref)
    if declared is not None and declared.augments:
        # **The header settled it, above targeting.** A row whose augment
        # rewrites its own target line declares every one of its augments
        # in `augments=`, the action menu offers each as a separate entry,
        # and `dsl.use` has already spent the points by the time a body
        # runs. Asking again here would offer the same choice twice and
        # charge for it twice.
        _LAST[(c.me, c.ref)] = c.augment
        return c.augment
    held = getattr(c, "augment_spend", None)
    if held is not None:
        return held
    afford = sorted((n for n in (offers or (2, 1)) if n <= c.points()), reverse=True)
    picked = c.choose([*afford, 0], "power points to augment")
    spent = c.spend_points(picked) if picked else 0
    c.augment_spend = spent
    _LAST[(c.me, c.ref)] = spent
    return spent
