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

from typing import TYPE_CHECKING

from combat_engine.engine import Cast
from combat_engine.engine.durations import When
from combat_engine.engine.types import Keyword, Usage

if TYPE_CHECKING:
    from collections.abc import Callable

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


def lent(c: Cast) -> int:
    """Offer whatever a feat lent this row, spend it, and run the clause.

    The read half of `c.lend_augment`, and **the lent-to row has to call
    it**: four feats print "your <power> gains the augmentable keyword. When
    you would use it, you can spend 1 power point to <effect>", and the
    power prints no Augment line of its own, so nothing in its header or its
    body knows the option exists. #507.

    Returns what was spent, 0 when nothing was lent or nothing was chosen,
    so a row may read it for a rider of its own.

    **Call it before the attack**, not after. One of the four swaps the
    defence the row rolls against -- "target Will instead of Reflex" -- and
    `c.strike()` reads that when it rolls. The three that only add an effect
    do not care, and putting the call in one place for all four is worth
    more than letting each pick.

    Routed through `augment` above rather than choosing here, so a lent
    augment is paid for and recorded exactly like a printed one --
    `_LAST` included, which is what `spent_on` reads while the use is still
    resolving.
    """
    lenders = _lenders(c)
    if not lenders:
        return 0
    return augment(c, *sorted({cost for cost, _ in lenders}))


def one_hit_rider(c: Cast, amount: int, label: str) -> None:
    """"Choose a single creature hit by the at-will attack. That creature
    takes extra damage equal to your Wisdom modifier."

    Three battlemind aspects print this sentence verbatim as the second half
    of their lent augment, so it is written once -- the exception the global
    rule allows for a run of rows that genuinely share a clause.

    **It cannot be paid when the clause runs.** A lent clause is run at the
    moment the points leave the pool, which is before the at-will swings, so
    there is nobody hit yet to choose among. The pair of watchers below is
    `f1827`'s lesson generalised: `Hit` is emitted from *inside* the body,
    `PowerResolved` when the body is done, and "a creature hit by the
    attack" is only answerable at the second.

    `amount` is read by the caller, because it is the lending aspect's
    Wisdom modifier and not the at-will's.
    """
    from combat_engine.engine.events import Hit, PowerResolved

    struck: list[int] = []
    done: list[bool] = []

    def saw(ev: Hit) -> None:
        if (
            not done
            and ev.attacker == c.me
            and ev.power == c.ref
            and ev.target not in struck
        ):
            struck.append(ev.target)

    def pay(ev: PowerResolved) -> None:
        # **Guarded on the ref as well as the actor**, because an action
        # point can buy a second use of the same at-will inside one turn
        # and the collector's duration outlives a single use.
        if done or ev.actor != c.me or ev.power != c.ref or not struck:
            return
        done.append(True)
        who = (
            c.choose(struck, f"{label}: who takes the extra damage")
            if len(struck) > 1
            else struck[0]
        )
        c.flat(amount, on=who)

    c.watch(Hit, saw, until=When.EONT, on=c.me, label=f"{label} watches")
    c.watch(PowerResolved, pay, until=When.EONT, on=c.me, label=label)


def _lenders(c: Cast) -> tuple[tuple[int, Callable[[Cast], None]], ...]:
    """Every clause lent to the row being used -- by ref, and by class.

    The ref half is `c.lend_augment("p1450", ...)`: a feat printing an
    Augment line on a card that prints none. The class half is
    `c.lend_augment("battlemind", ..., every=True)`, which five aspects
    print and which names the character's whole augmentable at-will
    repertoire rather than a row somebody could list.

    **The class test is the printed sentence clause for clause** -- "your
    battlemind at-will attack powers that are augmentable" -- so a daily
    aspect carrying the augmentable keyword itself does not lend to itself,
    and a battlemind at-will that is not an attack is not reached.
    """
    from combat_engine.engine import get
    from combat_engine.engine.components import Powers

    known = c.world.get(c.me, Powers)
    if known is None:
        return ()
    lent = tuple(known.lent_augments.get(c.ref, ()))
    wide = known.lent_class_augments
    if wide:
        p = get(c.ref)
        if (
            p is not None
            and p.cls in wide
            and p.usage is Usage.AT_WILL
            and p.attack is not None
            and Keyword.AUGMENTABLE in (p.keywords or ())
        ):
            lent += wide[p.cls]
    return lent


def _run_lent(
    c: Cast, lent: tuple[tuple[int, Callable[[Cast], None]], ...], spent: int,
) -> None:
    """Run whatever was lent at the cost actually paid, once per use.

    **Once per use and not once per target**, which is the same reason
    `augment` memoises the spend on the cast: a close burst runs its body
    per creature in the burst and the points leave the pool once. Guarded
    on the cast rather than on `_LAST`, because a second use of the same
    row later in the encounter must run the clause again.
    """
    if not lent or not spent or getattr(c, "lent_ran", False):
        return
    c.lent_ran = True
    for cost, clause in lent:
        if cost == spent:
            clause(c)


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
        _run_lent(c, _lenders(c), c.augment)
        return c.augment
    held = getattr(c, "augment_spend", None)
    if held is not None:
        return held
    # **A lend adds its cost to the offer**, which is the other half of
    # what an aspect prints: its Augment 1 is usable with a row that prints
    # only an Augment 2, and a cost nothing offers can never be paid.
    lent = _lenders(c)
    costs = set(offers or (2, 1)) | {cost for cost, _ in lent}
    afford = sorted((n for n in costs if n <= c.points()), reverse=True)
    picked = c.choose([*afford, 0], "power points to augment")
    spent = c.spend_points(picked) if picked else 0
    c.augment_spend = spent
    _LAST[(c.me, c.ref)] = spent
    _run_lent(c, lent, spent)
    return spent
