"""Three paragon-tier diseases, levels 13 and 16. #948.

One row per disease, branching on `c.stage`, armed by
`turns.arm_afflictions` at the start of every fight. The package docstring
has the shape and the one rule a stage body must obey -- **lay a standing
effect, never charge a one-time cost** -- and these three add nothing to
it. Four judgements are particular to them.

**Two of the three print FIVE stages, not four**, so they have four
printed stage paragraphs above the recovery one. `x5_65` and `x5_66` both
store `stages = 5`, which means their top printed stage is 4 and not the 3
every row written before this wave stops at.

**Each stage paragraph is self-contained, so the branches are exclusive.**
All three cards restate their whole penalty list per stage rather than
adding to the stage above -- `x5_66` prints its surge loss again at stages
2 and 3, and its defence penalties again at stage 3 -- so a chain of
`elif` is what the page says. Reading them as cumulative would double
`x5_66`'s vulnerability onto a stage that replaces it with a bigger
number.

**The top branch is `>=` and carries the worst load the row can lay, even
where the top printed stage is a marker.** Two of these three print a
death at their worst stage -- which `affliction.tick` cannot deal, so it
is dropped -- and `affliction.tick` caps a worsening at `worst()`, so that
stage is *reachable* and a sheet sits on it indefinitely. An `==` chain
would leave the disease's worst stage laying **nothing**, so a character
at it would be strictly better off than one a stage below, with nothing
reporting it. The `>=` is therefore a floor rather than the page: it says
"at least as bad as the stage below", which is the weakest true thing to
say about a stage whose own paragraph this row cannot write.

**A pool reduction is clamped, never decremented**, for `PowerPoints`
exactly as `diseases.lost_surges` argues it for `Health`. See
`_lost_points`.
"""

from __future__ import annotations

from combat_engine.content.diseases import lost_surges
from combat_engine.engine import (
    AC,
    AT_WILL,
    FORT,
    NO_TARGET,
    REF,
    WILL,
    ActionType,
    Cast,
    Defense,
    Melee,
    PowerPoints,
    When,
    power,
)


def _defences(c: Cast, *which: Defense) -> None:
    """The -2 to defences `x5_66` prints at two of its stages.

    `c.penalty` takes no `kind` and needs none: a penalty has no type, and
    two from one row collapse by label, which these do not share a key
    with. Same helper and same reasoning as `low_heroic._defences`, kept
    local rather than imported from a sibling module -- the package root is
    where a shared technique lives, and three lines are not worth putting
    there.
    """
    for defence in which:
        c.penalty(defence, 2, on=c.me, until=When.ENCOUNTER)


def _vulnerable(c: Cast, amount: int) -> None:
    """"It gains vulnerable N to all damage", laid exactly once per board.

    **A disease row is armed more than once on one board, and this is the
    clause that could not survive it.** `turns.arm_traits` loops until no
    fresh ref appears -- a trait that grants a row lengthens the list and
    buys another pass -- and it calls `arm_afflictions` at the end of
    *each* pass, so the stage body runs once per pass. `turns.join` is a
    second route to the same thing for a character arriving mid-fight.

    Most of what a stage lays survives that. `c.penalty` collapses two
    modifiers from one row by `Mod.label`, which `c.penalty`'s own
    docstring is about, and `diseases.lost_surges` carries a
    `once_per_board` guard for exactly this reason. `c.vulnerable` does
    neither: it is a running total in `Defences.vulnerable`, keyed by
    damage type with nothing recording who added what, so a second arming
    simply adds again.

    Measured on `audit.board`, which deals the character that buys the
    extra passes, before this guard existed:

        x5_66 stage 2    5 printed, 10 laid     (2 armings)
        x5_66 stage 3   10 printed, 30 laid     (3 armings)

    `c.me` plus a word of its own in the key, because `lost_surges` has
    already taken `(ref, c.me)` on the same board and the two clauses must
    not latch each other out.
    """
    if c.once_per_board(c.me, "vulnerable"):
        c.vulnerable(amount, on=c.me, until=When.ENCOUNTER)


def _lost_points(c: Cast, count: int) -> None:
    """"The target loses `count` power points", as a standing reduction.

    The power-point twin of `diseases.lost_surges`, and clamped for the
    same reason that one is: `PowerPoints.maximum` is the only thing
    `refresh()` and `c.regain_points` read, so lowering the ceiling and
    clamping the pool to it is the whole of "there is one fewer point
    available", while a bare `pool.points -= count` would be a fresh point
    taken every fight.

    **The ordering is what makes it safe, and it is not the ordering
    `lost_surges` has to fight.** `Encounter.start` calls `_refresh_pools`
    *before* `_arm_traits`, so `points == maximum` by the time this runs
    and the clamp lands on a full pool. `maximum` itself is rebuilt from
    the class chassis on every board (`chargen.spawn` makes the component
    fresh) and no `Sheet` field carries a pool across boards, so the
    reduction cannot compound between fights the way a decrement of
    `Health.surges` does.

    `once_per_board` on the caster, because the sentence is about the
    character rather than about a fight: `turns.join` arms a creature that
    arrives mid-fight, and two armings on one board would otherwise lower
    the ceiling twice.
    """
    pool = c.world.get(c.me, PowerPoints)
    if pool is None or not c.once_per_board(c.me):
        return
    pool.maximum = max(0, pool.maximum - count)
    pool.points = min(pool.points, pool.maximum)


def _no_points(c: Cast) -> None:
    """"The target loses all of its power points and cannot regain them."

    Both halves in two assignments, because `maximum` is what the two
    routes back into a pool read: `refresh()` sets `points = maximum` at
    the start of every fight and `c.regain_points` caps its gift at
    `maximum - points`, so a ceiling of zero refuses both rather than
    emptying the pool and letting it fill again.

    No `once_per_board` guard, unlike `_lost_points`: this is an
    assignment to zero and not a subtraction, so a second arming on one
    board is the same answer.
    """
    pool = c.world.get(c.me, PowerPoints)
    if pool is None:
        return
    pool.maximum = 0
    pool.points = 0


@power("x5_65", cls="disease", level=13, usage=AT_WILL,
       action=ActionType.NONE, target=NO_TARGET, reach=Melee(0),
       dropped=("c.on_points_spent()", "affliction.tick(rest_choice=)",
                "affliction.tick(no_improve=)"))
def x5_65(c: Cast) -> None:
    """Five stages, every printed paragraph about the power-point pool, and
    the two ends of the track run while the middle is one gap said twice.
    The one clause that leaves the pool is stage 3's second half, and it
    only reaches a healing surge as the price of not paying in points.

    **Stage 1 is a ceiling, stage 2 is a toll, and the page does not
    restate the first at the second.** "Loses 1 newly regained power point
    after each short or extended rest" is the pool coming back one short
    for as long as the stage holds, which `_lost_points` is; the stages
    above it print a cost per *use* instead and say nothing about the
    ceiling, so the branches are exclusive and the reduction is stage 1's
    alone. That leaves a character at stage 2 better off than at stage 1,
    which reads like an error and is the gap below rather than a reading:
    the toll is the clause that cannot be written.

    **Stages 2 and 3 are `c.on_points_spent()`.** "Loses 1 power point each
    time it uses its own power points to augment a psionic power" needs a
    moment that announces a spend, and `c.spend_points` emits a bare `Note`
    -- which carries no `by` and nothing a watch can match on. `f3322` and
    `f3323` wait on the same symbol for the same reason, so it is reused
    rather than renamed.

    Three near-misses were checked before marking it, and each is wrong in
    a way that would have shipped a row green on the wrong clause.
    `c.points_spent(ref)` is the **encounter's** running total against one
    ref, so once a row has been augmented every later use of it reads as
    augmented and the toll would be charged for uses that paid nothing.
    `c.augmented(ref)` is per-use and correct, but its own docstring limits
    it to rows declaring `augments=` in the header -- one whose augments
    live in the body settles them after `PowerUsed` has gone out -- so it
    would miss a share of the corpus silently. And watching `PowerUsed` to
    diff the pool across the use cannot tell an augment from any other
    spend a feat makes on the same turn.

    **Stage 3's second half is a decision at a rest**, not an effect in a
    fight: "after each short or extended rest, the target loses a healing
    surge unless it spends 4 power points" offers a choice between two
    resources at a moment `affliction.tick` owns and nothing else reaches.
    Re-laid per encounter it would charge once a fight, which is the
    failure the package docstring is about, and picking a side for the
    character would be inventing the choice rather than writing it.

    **Stage 4 plays, and it is the one stage where the component does the
    whole clause.** `_no_points` drops the ceiling to zero, which is both
    "loses all of its power points" and "cannot regain them by any means":
    `refresh()` and `c.regain_points` are the only readers of `maximum`
    and a zero refuses both. The one route it does not close is
    `c.transfer_points`, which adds over the receiver's ceiling
    deliberately -- the giver pays out of their own pool -- and there is no
    event to refuse it with, which is the same `c.on_points_spent()` gap
    already named rather than a second one.

    Stage 4's closing sentence is `affliction.tick(no_improve=)`: "only a
    x0_28 ritual can remove the disease at this stage" is the three-way
    comparison in `tick` being told that one stage cannot improve on a
    successful check, which it has no way to be told. `x5_91` carries the
    same symbol for the same sentence.

    ## This row audits SILENT, and there are two separate reasons

    Said here rather than left for the next reader to re-derive, and
    neither of them is the row declining to do its job: both branches run,
    on all 48 attempts, 60 calls across the two.

    **The board deals no psionic character.** `audit.board` was asked on
    seeds 0 to 7 and `world.get(caster, PowerPoints)` is `None` on every
    one, so both helpers return on their first line and there is nothing to
    lower. That is the shape of the excuses `audit.KNOWN_SILENT` already
    carries for a row whose caster is the wrong class.

    **And a pool is not one of the observables, so it would be silent
    anyway.** Planting `PowerPoints(points=6, maximum=6)` on the board's
    caster makes the arithmetic happen and verifiably so -- 6 to 5 at stage
    1, 6 to 0 at stage 4, with the repeat armings reading back as
    no-ops -- and the verdict is still `events=set()`. Nothing in
    `audit.DID_SOMETHING` covers a pool moving, because nothing announces
    one: `c.spend_points` and `c.regain_points` each end in a `Note`, which
    carries no `by`. So this is the `UseRestored`/`UseSpent` case one
    component over, and the honest fix is an event in the engine rather
    than anything a row can write -- which is also what would retire
    `c.on_points_spent()` above. `diseases.lost_surges` is invisible for
    the same reason and only looks credited because every row carrying it
    also lays a defence penalty at some stage.
    """
    if c.stage == 1:
        _lost_points(c, 1)
    elif c.stage >= 4:
        _no_points(c)


@power("x5_66", cls="disease", level=13, usage=AT_WILL,
       action=ActionType.NONE, target=NO_TARGET, reach=Melee(0),
       dropped=("affliction.tick(contagious=)", "affliction.tick(dies=)"))
def x5_66(c: Cast) -> None:
    """Five stages, and the three that are a stage effect are written in
    full.

    Each paragraph restates its whole list, so the branches are exclusive:
    stage 2 prints the surge loss again beside the defence penalties, and
    stage 3 prints the defences again beside **two** lost surges and a
    bigger vulnerability. Reading them cumulatively would stack 5 and 10
    into 15 on a stage that prints 10 instead.

    **The count is the thing that tells stage 3 from stage 2.** One surge
    at stages 1 and 2 and two at stage 3, through `lost_surges` rather than
    a spend -- `c.spend_surge` would take a fresh surge every encounter,
    which is the repeating cost this package forbids and which the package
    helper has the measurement for.

    "Vulnerable 5 to all damage" is `c.vulnerable` with no `dtype`, which
    is what "all damage" means -- the verb loops every type when none is
    named. `until=When.ENCOUNTER` rather than the verb's `SAVE_ENDS`
    default: the page says "while affected by stage N", which is a hold the
    disease owns and not one the character rolls against.

    **It goes through `_vulnerable` and not through the verb**, because a
    stage body is armed more than once on one board and this is the one
    clause here that stacks when it is -- measured at 30 where the page
    prints 10. The helper has the arithmetic and the cause.

    Stage 3's sentence about the victim becoming disoriented and chaotic
    carries no number, no duration and no roll, so there is nothing of it
    to lay -- the same shape as `x5_94`'s closing line.

    **The contagion clause is dropped at all three stages.** "Any
    uninfected creature that spends at least 8 hours with the target must
    succeed on a DC 14 Endurance check at the end of that creature's next
    extended rest or also become infected" is a roll made by *somebody
    else*, at a rest, against a DC the stage sets -- 14 at stages 1 and 2
    and 20 at stage 3. `affliction.tick` is the one place with that moment
    and it reads each sheet's own afflictions only, so it cannot spread one
    sideways through the party. Nothing on `Cast` is the gap: a board has
    no eight hours on it.

    **Stage 4 is `affliction.tick(dies=)`.** "The target dies, exploding
    into three m6000" is a death the track inflicts and not a death on a
    board, so it is neither a `Died` watch nor anything a stage body lays
    -- `x5_91` writes a `Died` watch because its page prints *"if the
    target dies while at this stage"*, a conditional this card does not
    have. The tick would have to end a character and stand three creatures
    up in its place, which is the half of `x5_81`'s symbol that is about
    standing something up.

    So the branch for stage 3 is `>=`, and the module docstring has the
    argument: with stage 4's own paragraph undeliverable, an `==` would
    make the worst stage of the disease the most harmless.
    """
    if c.stage == 1:
        lost_surges(c, 1)
    elif c.stage == 2:
        lost_surges(c, 1)
        _defences(c, AC, FORT, REF)
        _vulnerable(c, 5)
    elif c.stage >= 3:
        lost_surges(c, 2)
        _defences(c, AC, FORT, REF)
        _vulnerable(c, 10)


@power("x5_18", cls="disease", level=16, usage=AT_WILL,
       action=ActionType.NONE, target=NO_TARGET, reach=Melee(0),
       dropped=("c.must_attack(on=, against=)", "affliction.tick(dies=)"))
def x5_18(c: Cast) -> None:
    """Four stages and the shortest card of the three: one defence penalty
    is the whole of what a board can carry.

    **Stage 1 is an Initial Effect with no mechanic in it.** Something is
    implanted in the target and the page gives it no number, no roll and no
    duration -- it is what the later stages are *about* rather than an
    effect of its own -- so there is nothing to lay and no symbol that
    would ever close it. Not a marker for that reason: a marker names a gap
    something could fill.

    **Stage 2's second sentence is `c.must_attack(on=, against=)`.** "While
    bloodied, the target succumbs to madness and attacks the nearest
    creature" takes the character's turn away from it, which is an
    instruction to whoever is choosing its actions, and nothing constrains
    that. `m784a3` and `x5_34` carry the same symbol for the same clause,
    so it is reused. Note which half of the printed sentence this is: the
    row is not being asked to *make* the swing -- `x5_54` does that, where
    the page hands the attack out itself -- but to force the character's
    own choice of target, which is a different mechanism and the one that
    does not exist.

    The bloodied gate is deliberately not written on its own. On its own it
    would be a predicate nothing reads, and a half-written clause that
    looks finished is the failure mode this component produces.

    **Stage 3 is `affliction.tick(dies=)`.** "Final State: the target dies,
    and a m708 burrows out of its skull" is the track killing the character
    at a rest and standing something up in its place, which `tick` cannot
    do -- the same symbol and the same half of it as `x5_81`'s. Not a
    `Died` watch: the page prints no condition on the death, so a watch
    would be answering a moment the card does not name.

    So the Will penalty is laid at `>= 2` rather than `== 2`: `tick` caps a
    worsening at stage 3 and a sheet sits there, and with stage 3's own
    paragraph undeliverable an exact branch would leave the worst stage of
    the disease laying nothing at all.
    """
    if c.stage >= 2:
        c.penalty(WILL, 2, on=c.me, until=When.ENCOUNTER)
