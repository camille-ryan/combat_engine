"""Three diseases at levels 12 and 13, one row each. #948.

Written because something in the tree **inflicts** each of them and the
creature that does is fielded at its own level: `etl/build.py` imports
monsters to level 13 where powers stop at 10, so `m1140` (level 12),
`m6146` and `m3843` (level 13) are all offered by `loader.pick` and all
three called `c.contract` onto a stage no row could read --
`turns.arm_afflictions` skips a ref `dsl.get` answers `None` for, silently.

The package docstring has the shape and the one rule every body here obeys:
`arm_afflictions` runs the row at the start of **every** fight off the stage
the `Sheet` carried in, so a stage paragraph lays a **standing** effect and
never charges a one-time cost. `until=When.ENCOUNTER` is re-laid next fight
and stops being laid the moment the disease is cured, which is exactly the
printed "while affected by stage N".

**Two of the three are a lower-level card reprinted verbatim**, and that is
worth saying rather than rediscovering: `x5_43`'s three stage paragraphs are
`x5_23`'s word for word, and `x5_25`'s are `x5_34`'s. Only the level and the
two DCs differ, and all four of those numbers are columns rather than body
code. So the two bodies are written exactly as their siblings are, and a
change of reading on one of the four is a change of reading on all four.

**Every stage paragraph on those two is self-contained**, which is the
package's usual case: each one restates its whole penalty list rather than
adding to the stage before, so the branches are a chain of `elif` and the
last one is `>=` and not `==`. `affliction.tick` moves a stage with
`min(stage + 1, stages)` and `disease.stages` counts the stage-0 paragraph,
so the top printed stage is `stages - 1` and a stage above it must not fall
through to nothing.

**`x5_51` is the exception and is cumulative**: its stage 2 says "in
addition to the initial effect" and its stage 3 "in addition to prior
effects", so nothing there is exclusive and the one clause it can lay is
laid with `>=`. It is also the one card here that is mostly about a
*place* -- see its own docstring.
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
    Condition,
    Defense,
    Melee,
    When,
    power,
)


def _defences(c: Cast, *which: Defense) -> None:
    """The -2 to three defences `x5_43` prints twice, as a standing penalty.

    `c.penalty` takes no `kind` and needs none -- a penalty has no type --
    and the three laid here share no key with anything else this row lays,
    so they do not collapse into each other.
    """
    for defence in which:
        c.penalty(defence, 2, on=c.me, until=When.ENCOUNTER)


@power("x5_51", cls="disease", level=12, usage=AT_WILL,
       action=ActionType.NONE, target=NO_TARGET, reach=Melee(0),
       dropped=("c.treats_allies_as_enemies()", "c.must_take_opportunity()",
                "story.site_radius()", "story.npc_takeover()"))
def x5_51(c: Cast) -> None:
    """The one printed word this card has that the engine already holds is
    its final state's condition. Everything else on it is about a place.

    **Stage 3's condition is laid, and with `c.condition` rather than
    `c.dominate`.** The verb files `Relation.DOMINATED_BY` alongside the
    condition and takes a `by=` naming the dominator -- defaulting to the
    caster, which here is the diseased character itself. Nothing holds this
    character's strings: the affliction does, and an affliction is not an
    entity a relation can name. So `c.dominate(on=c.me)` would have filed
    the character as its own master, a fact every reader of that relation
    could read and none of which is true, where the condition alone says
    only what the page says. `conditions.Rules` makes that
    `grants_ca + one_action + no_reactions`, which is the whole mechanical
    content of the printed word.

    It is laid at `>= 3` rather than `== 3` because stage 3 is the top
    printed paragraph on a four-stage card, so a stage above it must not
    fall through.

    **Four clauses dropped, and three of them wait on the same absence: the
    board and the story graph hold no located site.** Stage 1's compulsion
    is gated on being within a mile of the one the affliction comes from,
    stage 2 is entirely a compulsion to go there and stay, and stage 3's
    hostility is bounded by the same radius. There is no position to measure
    any of that from and no faction to exempt the keepers of it, so none of
    the three is an approximation away -- they are gated on a thing that
    does not exist, and a gate that is always False is a clause that is
    never laid.

    The other two are verbs:

    * **Nothing turns a side around.** "Treats its allies as enemies for
      the purpose of making opportunity attacks" is printed at stage 1 and
      carried by both later stages, and `c.provoke` opens one window for one
      named creature rather than changing who a side is. `m6088a1` waits on
      the same symbol for the same sentence.
    * **Nothing compels a creature to take an opportunity window it is
      offered.** That is a different need from `c.must_attack(on=,
      against=)`, which three rows wait on: those constrain what a creature
      does with **its own turn**, and this one is about a reaction the
      window already hands out and the chooser may decline. One symbol
      serving both could not go green correctly for either.

    Stage 3's hostility half takes `story.npc_takeover()`, which `x5_93`
    already waits on: a character that considers the party its enemies and
    acts on it has stopped being the party's, and nothing hands a player
    character over.
    """
    if c.stage >= 3:
        c.condition(Condition.DOMINATED, on=c.me, until=When.ENCOUNTER)


@power("x5_25", cls="disease", level=13, usage=AT_WILL,
       action=ActionType.NONE, target=NO_TARGET, reach=Melee(0),
       dropped=("c.must_attack(on=, against=)",))
def x5_25(c: Cast) -> None:
    """`x5_34`'s card at a higher level, and written identically: stage 1
    plays, stages 2 and 3 are one gap said twice.

    Both later paragraphs take the character's turn away from it -- a melee
    attack on a random creature within 5 squares, or on the nearest one in
    line of sight, and a random walk when there is nobody to hit. That is an
    instruction to whoever is choosing the character's actions, and nothing
    constrains that; `m784a3` and `x5_34` carry the same symbol for the same
    reason.

    **Stage 2's saving throw is deliberately not written.** It exists only
    to decide whether the forced attack happens, so on its own it would roll
    a die at the end of every turn and act on nothing -- a row that looks
    like it is doing the work.

    The branch is `== 1` and not `>=`: the Will penalty is printed at stage
    1 and at neither later stage, so it is that stage's alone.
    """
    if c.stage == 1:
        c.penalty(WILL, 2, on=c.me, until=When.ENCOUNTER)


@power("x5_43", cls="disease", level=13, usage=AT_WILL,
       action=ActionType.NONE, target=NO_TARGET, reach=Melee(0))
def x5_43(c: Cast) -> None:
    """`x5_23`'s card at a higher level, and whole -- no marker.

    Stage 2 is defences only: the lost surge is stage 1's and is not
    restated, so it is not laid again. Stage 3 restates the defences beside
    the total loss.

    **"The target loses a healing surge" is `lost_surges`**, which lowers
    the ceiling and clamps the pool to it. A decrement would take a fresh
    surge every encounter, because `story._wear` runs before
    `turns.arm_afflictions` and hands the harvested pool back clamped
    against a ceiling this row has not lowered yet. The package docstring
    has the measurement.

    **"Loses all healing surges" is `c.no_surges` and is a different clause,
    not the same one with a bigger number**: it refuses every route a surge
    leaves by, which is what an empty pool feels like in a fight, where
    lowering a ceiling to zero would also be re-clamping a pool that the
    stage before had already lowered. "Cannot regain hit points" is
    `c.no_healing`, which refuses the heal rather than the spend, and the
    page prints the two side by side, so both are laid.
    """
    if c.stage == 1:
        lost_surges(c, 1)
    elif c.stage == 2:
        _defences(c, AC, FORT, REF)
    elif c.stage >= 3:
        _defences(c, AC, FORT, REF)
        c.no_surges(on=c.me, until=When.ENCOUNTER)
        c.no_healing(on=c.me, until=When.ENCOUNTER)
