"""Terrain powers: rows the board owns, that any creature by them may use.

The compendium's `terrain` table holds **24** rows of `kind = 'terrain
power'`, and before `#980` none of them could be written at all. They are
not anybody's powers: nothing casts them, no creature has one in its
`Powers.all`, and `dsl.usable` refused every one on the *"not known"* gate.
What they are is a thing on the floor with an action attached.

The printed shape, which is the same on all 24:

    <Single-Use | At-Will> Terrain
    <Standard | Move | Minor | Free> Action
    Requirement: You must be adjacent to / in / within N squares of <it>
    Check: <skill> check (<band> DC) to <do the thing>
    Success: <it happens, and usually makes an attack>
    Target:  ...
    Attack:  ...

So the mechanism is three parts and `#980` built the first: a region
carries a ref (`Zone.power`), the action menu offers it to whoever is
standing near enough (`actions._terrain`), and `perform` runs it through
`dsl.use(board=True)`. `content/terrain.py`'s `lay` is the writer.

**This module holds one row, deliberately, and the other 23 are a content
wave with two gaps in front of them.** Writing a facility with no caller is
how `c.zone(hindering=)` sat unused from `#952` until `#1039` -- the field
was recorded and burned nobody -- so the mechanism gets a live caller in
the same commit that builds it. What the remaining 23 want is measured on
`#980`:

* **`Attack(level + N)` has no header form.** 12 of the 24 print
  *"Attack: Level + 3 vs. Reflex"*. `Attack(printed=)` is a finished total
  with the creature's level already inside it and `Attack(ability=)` rolls
  a character's line; neither says "the user's level, plus three". Filed as
  `#1105`.
* **A `Check:` that gates the attack cannot be rolled in the body.** 21 of
  24 print one, and the body runs **once per target** -- so a check rolled
  there is rolled once per creature in the blast, and a failure on the
  first target cannot stop the second. `c.first` guards a once-per-use line
  but gives no way to abandon the rest. That wants a header field; filed as
  `#1106`.

`x2_124` needs neither, which is why it is the one here: `target=SELF`, so
the body runs exactly once and the check is correct in it, and it has no
attack line at all.
"""

from __future__ import annotations

from typing import Any

from combat_engine.dc import dc
from combat_engine.engine.cast import Cast
from combat_engine.engine.dsl import PERSONAL, SELF, power
from combat_engine.engine.durations import When
from combat_engine.engine.events import Hit, Miss, Moved
from combat_engine.engine.types import ActionType, Usage


@power("x2_124", level=1, usage=Usage.AT_WILL, action=ActionType.STANDARD,
       reach=PERSONAL, target=SELF)
def x2_124(c: Cast) -> None:
    """Burrow into the loose sand: fall prone, and be unseen until you stir.

    The first terrain power in the tree and the mechanism's live caller.
    `Zone.power = "x2_124"` with `power_uses=0` -- the card's heading reads
    `At-Will Terrain`, so the feature is not spent by being used -- and
    `power_reach=1`, which is the printed *"you must be in a square of the
    dune"*: a creature standing in the region is within 1 of its own
    square, so the same reach serves both that wording and the 16 rows that
    say *adjacent*.

    **The check is rolled here and that is only sound because `target` is
    `SELF`.** `dsl.use` runs a body once per target, so a row with a blast
    would roll this once per creature caught -- see the module docstring and
    `#1106`. One target, one roll, and the printed failure is simply that
    nothing happens.

    `dc(c.level, "easy")` rather than a number: the card prints a *band*,
    not a DC, and 15 of the 24 rows do the same. `combat_engine/dc.py` is
    the 90-number table those bands index, and its own docstring already
    named `terrain` as a waiting consumer -- this is the first row to take
    it up.

    **"Total concealment until you move or attack" is two ends and neither
    is a `When`.** So the encounter clock is the outer bound and both ends
    are taken off by hand, which is the idiom `i3296p1` and
    `_unseen_until_it_stirs` already use.

    **`Moved` and not `MoveStart`, and this row is the sharpest case for
    that choice in the tree.** It was written as `MoveStart` on the
    reasoning that a creature climbing out of the sand has broken cover by
    *starting* to move. A control caught it: the same body makes the
    creature **prone**, a prone creature cannot walk at all, so the very
    first attempted walk was **refused** -- 0 squares covered, still on its
    own square -- and `MoveStart` had already ended the concealment. The
    buried creature lost its cover for a move that never happened, and
    nothing would have reported it: the effect ending is exactly what the
    card says should happen, just for the wrong reason.

    `Moved` is what the printed *"until you move"* means and it is also
    `i3296p1`'s reading, whose note says its dust "should survive a move
    that is refused". Two rows, two cards, same answer -- the original
    argument for splitting them was mine and it was wrong.

    `Hit` and `Miss` both, because an attack that misses is still an
    attack. `once=True` on each watch and a shared `spent` guard anyway:
    three watches against one effect, and ending an effect twice is a
    second `EffectEnded` nothing printed.

    `c.conceal(total=True)` and **not** `c.invisible` or `c.hide`. The
    printed words are *"total concealment"*, which is a -5 to attacks
    against you; being hidden or invisible is a different rule -- it
    changes whether you can be targeted at all, and grants combat
    advantage, neither of which this card says. The two rows above reach
    for `c.invisible` because their cards print *"unseen"*.
    """
    if not c.check("athletics", dc(c.level, "easy")):
        return
    c.prone()
    buried = c.conceal(total=True, until=When.ENCOUNTER)
    if buried is None:
        return
    me = c.me
    spent: list[bool] = []

    def stirs(ev: Any) -> None:
        if spent:
            return
        who = getattr(ev, "attacker", None)
        if who is None:
            who = getattr(ev, "actor", None)
        if who != me:
            return
        spent.append(True)
        c.world.effects.end(buried, "it moved or attacked")

    for event in (Hit, Miss, Moved):
        c.watch(event, stirs, until=When.ENCOUNTER, on=me, once=True,
                label=f"{c.ref} buried")
