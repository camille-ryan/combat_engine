"""Five heroic diseases, stages 1 to 3. #948.

One row per disease, branching on `c.stage`, armed by
`turns.arm_afflictions` at the start of every fight. The package docstring
has the shape and the one rule; three judgements are particular to these
five.

**Every stage paragraph is self-contained, so the branches are exclusive.**
Each card restates its whole penalty list per stage -- "while affected by
stage 2, ... and takes a -2 penalty to AC, Fortitude, and Reflex" -- rather
than adding to the stage before, so a chain of `elif` is what the page
says. The last branch is `>=` and not `==` because `affliction.tick` moves
a stage with `min(stage + 1, stages)` and `disease.stages` counts the
stage-0 paragraph, so the top printed stage is `stages - 1` and a stage
above it must not fall through to nothing.

**"The target loses N healing surges" lowers the ceiling and CLAMPS the
pool to it. It must not decrement the pool, and that distinction is the
whole of this paragraph.** `Health.max_surges` is rebuilt from the class on
every board, so lowering it is re-laid per fight exactly as a defence
penalty is -- but `Health.surges` is *carried*: `story.harvest` writes it
onto the `Sheet` and `story._wear` reads it back, clamped against the
board's own ceiling (`story/__init__.py:753`). `_wear` runs before
`turns.arm_afflictions`, so it clamps against the ceiling this row has not
lowered yet, and a `surges -= 1` therefore takes a *fresh* surge every
encounter. Measured over four boards at level 7, against a no-disease
control:

    no disease                  (max_surges, surges): 12,12  12,12  12,12  12,12
    stage 1, surges -= 1        (max_surges, surges): 11,11  11,10  11,9   11,8
    stage 1, surges clamped     (max_surges, surges): 11,11  11,11  11,11  11,11

The ceiling is stable either way, so measuring only `max_surges` says the
decrement is sound and it is not -- it is the repeating cost the package
docstring forbids, draining one surge a fight. `min(surges, max_surges)` is
the standing form, and `diseases.lost_surges` is the one place it is
written -- in the package root, because three modules write this clause
and 54 more rows are coming.

**"The target loses ALL healing surges" is `c.no_surges` instead**, which
is a different clause and not the same one with a bigger number: every
route a surge leaves by emits `SurgeSpent`, and refusing it is exactly what
a creature with an empty pool experiences in a fight.

**"Cannot regain hit points" is `c.no_healing`**, which refuses the heal
rather than the spend, and the cards print it beside the surge clause as a
second sentence -- so both are laid where both are printed.
"""

from __future__ import annotations

from combat_engine.content.diseases import lost_surges
from combat_engine.engine import (
    AC,
    AT_WILL,
    CON,
    FORT,
    NO_TARGET,
    REF,
    WILL,
    ActionType,
    Cast,
    Defense,
    Died,
    Melee,
    Team,
    When,
    power,
)


def _defences(c: Cast, *which: Defense) -> None:
    """The -2 to defences four of these cards print, as a standing penalty.

    `c.penalty` takes no `kind` and needs none: a penalty has no type, and
    two from one row collapse by label, which these do not share a key
    with.
    """
    for defence in which:
        c.penalty(defence, 2, on=c.me, until=When.ENCOUNTER)


@power("x5_92", cls="disease", level=1, usage=AT_WILL,
       action=ActionType.NONE, target=NO_TARGET, reach=Melee(0))
def x5_92(c: Cast) -> None:
    """Stage 1's whole paragraph is the lost surge, and stages 1 and 2 lose
    one each. Stage 3 prints the total loss instead, so the pool is refused
    rather than lowered -- see the module docstring for why those are two
    clauses and not one."""
    if c.stage == 1:
        lost_surges(c, 1)
    elif c.stage == 2:
        lost_surges(c, 1)
        _defences(c, AC, FORT, REF)
    elif c.stage >= 3:
        _defences(c, AC, FORT, REF)
        c.no_surges(on=c.me, until=When.ENCOUNTER)
        c.no_healing(on=c.me, until=When.ENCOUNTER)


@power("x5_45", cls="disease", level=2, usage=AT_WILL,
       action=ActionType.NONE, target=NO_TARGET, reach=Melee(0))
def x5_45(c: Cast) -> None:
    """The one card here with no pool loss, so the whole of it is written.

    Stage 2 is gated on being bloodied and nothing else, so an unbloodied
    character at stage 2 carries no penalty at all while one at stage 1
    carries -2. That reads like an error and is what the page prints; a
    printed row wins.

    The gate is a closure reading `c.bloodied` live rather than a `when=`
    key, because the context carries none -- and live is what the clause
    wants, since a character bloodied mid-fight is bloodied for the rest of
    it. `c.no_surges` takes the same gate, which is what its `when=` is
    for: the clause has no duration of its own.
    """
    me = c.me
    if c.stage == 1:
        c.penalty("attack", 2, on=me, until=When.ENCOUNTER)
    elif c.stage >= 2:
        bloodied = lambda ctx: c.bloodied(on=me)  # noqa: E731
        c.penalty("attack", 4, on=me, until=When.ENCOUNTER, when=bloodied)
        c.no_surges(on=me, until=When.ENCOUNTER, when=bloodied)


@power("x5_94", cls="disease", level=3, usage=AT_WILL,
       action=ActionType.NONE, target=NO_TARGET, reach=Melee(0))
def x5_94(c: Cast) -> None:
    """Stage 3 prints no surge clause at all -- the pool loss stops at
    stage 2, which is the only one of these five cards that does that --
    and its closing sentence about the victim's state of mind carries no
    number, no duration and no roll, so there is nothing of it to lay."""
    if c.stage == 1:
        lost_surges(c, 1)
    elif c.stage == 2:
        lost_surges(c, 1)
        _defences(c, AC, FORT, REF)
    elif c.stage >= 3:
        _defences(c, AC, FORT, REF)
        c.slowed(on=c.me, until=When.ENCOUNTER)


@power("x5_23", cls="disease", level=5, usage=AT_WILL,
       action=ActionType.NONE, target=NO_TARGET, reach=Melee(0))
def x5_23(c: Cast) -> None:
    """Stage 2 is defences only -- the lost surge is stage 1's and is not
    restated -- and stage 3 restates the defences beside the total loss."""
    if c.stage == 1:
        lost_surges(c, 1)
    elif c.stage == 2:
        _defences(c, AC, FORT, REF)
    elif c.stage >= 3:
        _defences(c, AC, FORT, REF)
        c.no_surges(on=c.me, until=When.ENCOUNTER)
        c.no_healing(on=c.me, until=When.ENCOUNTER)


@power("x5_91", cls="disease", level=5, usage=AT_WILL,
       action=ActionType.NONE, target=NO_TARGET, reach=Melee(0),
       dropped=("affliction.tick(no_improve=)", "affliction.tick(fatal=)"))
def x5_91(c: Cast) -> None:
    """Will rather than Reflex in the trio, and two clauses stage 3 adds.

    **Stage 2 loses TWO surges**, which is the only stage on these five
    cards that loses more than one, and the count is the whole of what
    tells it from its siblings.

    **The check penalty is two keys, because the engine rolls two kinds of
    check.** `skills.modifier` reads `skill:<name>` and
    `skills.ability_check` reads `ability_check` with the ability in its
    context, so "Constitution-based ability and skill checks" is a gate on
    the second and a flat penalty on the first -- and the first needs no
    gate, since `skills.SKILLS` makes endurance the only Constitution
    skill. Writing one key would have dropped half the printed clause
    silently.

    **The creature that emerges is a `Died` watch and not a `Dropped`
    one.** A character dropped to 0 is dying rather than dead, and the page
    says dies; `resolve._die` emits `Died` and lifts the body off the grid
    afterwards, so `c.here` inside the handler is still the former space the
    card names. It arrives hostile: the page gives it no side and a thing
    bursting out of a corpse is not on the party's.

    Two clauses of stage 3 belong to the rest and not to a fight. The stage
    holding on a successful check and the character dying when it rises are
    both decisions `affliction.tick` makes, and it makes one three-way
    comparison for every stage of every disease with no way to be told a
    stage's own exception -- so neither is a clause this row could carry.
    """
    if c.stage == 1:
        lost_surges(c, 1)
    elif c.stage == 2:
        lost_surges(c, 2)
        _defences(c, AC, FORT, WILL)
    elif c.stage >= 3:
        _defences(c, AC, FORT, WILL)
        c.no_surges(on=c.me, until=When.ENCOUNTER)
        c.no_healing(on=c.me, until=When.ENCOUNTER)
        c.penalty("skill:endurance", 2, on=c.me, until=When.ENCOUNTER)
        c.penalty("ability_check", 2, on=c.me, until=When.ENCOUNTER,
                  when=lambda ctx: ctx.get("ability") == CON)

        def sprouts(ev: Died) -> None:
            if ev.actor == c.me:
                c.summon("m6342", at=c.here, team=Team.ENEMY)

        c.watch(Died, sprouts, until=When.ENCOUNTER, on=c.me)
