"""Vampire, level 10.

One row, the class's second polymorph, and every clause of it is sayable.
"""

from __future__ import annotations

from combat_engine.engine import (
    DAILY,
    MINOR,
    PERSONAL,
    SELF,
    Cast,
    Condition,
    Keyword,
    When,
    power,
)

from . import ends_with


@power(
    "p13862",
    level=10,
    cls="vampire",
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH, Keyword.SHADOW],
)
def p13862(c: Cast) -> None:
    """The shape has no name to give, and that is a fact about the extract
    rather than a gap.

    The spec reads "you assume a p13862" -- the printed word for the shape
    was replaced by this row's own ref on the way in, so there is no second
    ref to assume and nothing to look up. `c.form(name=)` would have been the
    place for that word, and it exists to make a shape *askable* by
    `query.in_form`, for the rows printing "Requirement: must be in
    <shape>". Nothing prints one naming this shape, so nothing is lost.

    **Not `c.form` at all, and that is the sustain rather than the name.**
    Two clocks ride on one hold and both are printed: it lapses at the end
    of the caster's turn unless a minor keeps it going (`When.SUSTAIN` plus a
    `sustain_cost`) and a minor also ends it deliberately (a `drop_cost`).
    `c.form` says the second and has no parameter for the first, so the hold
    goes through `world.effects.apply` -- which is how `druid/level_10.py`
    and three warlock files reach the same printed line.

    `c.form` followed by `shape.sustain_cost = MINOR` was tried and is wrong
    rather than untidy: `apply` calls `Effects._warn_sustainless` before it
    returns, so the row emitted "p13862 is sustained but costs nothing to
    sustain, so nothing can keep it going" on every use -- a `Note` saying
    the opposite of what the row does, one line before it became false.

    **`Condition.SHAPED` is deliberately left out.** That card is
    `Rules(no_standard=True)` and this one takes away *attacking*, not the
    standard action -- the character can still move, sustain and use a
    utility. `warlock/level_10.py`'s `p95` passes it because its own card
    says so; copying it here would have been a silent narrowing.

    Everything else is laid beside the hold at the longer printed clock and
    tied back to it by `ends_with`, so a deliberate end lifts all of it.
    """
    me = c.me
    shape = c.world.effects.apply(
        me,
        me,
        When.SUSTAIN,
        label=c.ref,
        conditions=(Condition.INSUBSTANTIAL,),
        sustain_cost=MINOR,
        drop_cost=MINOR,
        by=c.ref,
    )
    ends_with(
        c,
        shape,
        c.mode("fly", 8, on=me, until=When.ENCOUNTER),
        c.phasing(on=me, until=When.ENCOUNTER),
        c.bonus("skill:stealth", 10, on=me, until=When.ENCOUNTER, kind="power"),
        c.cannot_attack(on=me, until=When.ENCOUNTER),
    )
