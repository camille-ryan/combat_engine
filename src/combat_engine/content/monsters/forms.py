"""Asking and answering which shape a creature is wearing.

Four helpers, shared because a hundred rows across twelve level directories
need them and the natural home -- the first file that wanted one -- would make
`level_01` import `level_03`, which is a cycle.

**This module imports nothing from `content`**, which is what keeps it
importable from any row file.

## One question, and it used to have eight answers (#477)

The reader was written eight times: `_in_shape` in five files (twice taking
its prefix from an argument and three times from a module constant),
`_in_shapes` for the two-form case, `_in_sludge` for one exact label, and the
three here. All seven of the others walked the creature's effects looking for
a label, because they predate `c.form(name=)` -- which is the thing that
records *which* shape rather than merely that there is one.

**The writer was the blocker, not the readers.** `_change_shape` in
`level_04/brutes.py` and `level_08/brutes.py` laid `c.form(label=...)` with no
`name=`, so `Shapes` stayed empty and `query.in_form` could not see the form
at all. Folding the readers first would have made 44 rows answer "yes" to
every shape gate, because `in_form` is permissive when nothing is recorded --
silently false, which is what this tree's notes warn about first. So the
writers moved first and the readers followed.

The label is `"<ref> <word> form"` everywhere now. It was `"<ref> <word>"` in
the `_change_shape` half, and the two formats could not share a clear-loop:
this one ends a previous shape by `endswith(" form")` and that one by
`startswith(prefix)`, so a creature written one way and read the other would
keep two live shapes at once.

The `prefix` argument is gone because it was `f"{c.ref} "` at all 14 writer
call sites, checked rather than assumed. On the reading side it was never
load bearing: `Shapes` is per creature, so the prefix only ever told one of a
creature's own labels from another of its own, and a shapechanger has one
shape power.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine.cast import Cast
from combat_engine.engine.durations import When
from combat_engine.engine.ecs import World
from combat_engine.engine.query import in_form, shifted
from combat_engine.engine.types import ActionType


def _shapes(*words: str) -> Callable[[World, int], bool]:
    """A printed "must be in X form" Requirement, as a `requires=` gate.

    `requires=` is handed a world and an id rather than a `Cast`, so it reads
    `query.in_form` straight -- including that function's permissive answer
    for a creature nobody has transformed yet.

    **The one gate, where there were eight.** The seven label-sniffing
    versions this replaces each reproduced that permissive answer by hand --
    "a creature that has not changed shape is in whatever shape it was found
    in, the block does not say which, so no attack is ruled out" -- and the
    argument now lives once, in `query.in_form`. #477.
    """

    def ask(world: World, eid: int) -> bool:
        return in_form(world, eid, *words)

    return ask


def _strictly(*words: str) -> Callable[[World, int], bool]:
    """Like `_shapes`, but **not** permissive about an unrecorded shape.

    `_shapes` passes when nothing has been recorded, because a Requirement
    should not refuse an attack the stat block never ruled out. A clause that
    *pays out* in a form wants the opposite: it must not pay before the form
    is taken. `shifted` and `in_form` compose to say so, which is why neither
    needs a `strict` keyword.

    **This is the distinction the fold had to keep.** Collapsing it into
    `_shapes` would start paying every one of these bonuses to creatures
    nobody has transformed, which is the failure a tidier-looking merge
    produces and nothing would report.
    """

    def ask(world: World, eid: int) -> bool:
        return shifted(world, eid) and in_form(world, eid, *words)

    return ask


def _not_in(*words: str) -> Callable[[World, int], bool]:
    """"It loses its bite attack in humanoid form" -- the other direction.

    Permissive the same way `_shapes` is, and for the same reason: a creature
    that has not changed shape has not lost anything.
    """

    def ask(world: World, eid: int) -> bool:
        return not (shifted(world, eid) and in_form(world, eid, *words))

    return ask


def _shapechange(
    c: Cast, *words: str, revert: ActionType | None = ActionType.MINOR
) -> str:
    """"It alters its physical form to appear as one of these."

    **One at a time.** Taking a shape ends whichever it was already wearing,
    which is what "until it uses this power again" means on every one of
    these cards -- so the forms are a set on the creature but a shapechanger
    only ever has one of them in it.

    The natural form is in the list because changing *back* is a use of the
    same power, and after a change back the form is recorded rather than
    inferred -- which reads the same way round either way.

    **`revert` is the one thing the three old writers genuinely disagreed
    about**, so it is a parameter rather than a default. `_change_shape`
    passed `MINOR` -- the printed minor-action way out -- and the three
    inline grantors in the two `controllers.py` files and
    `level_05/controllers_sa.py` passed `None`, because their cards print no
    way out and the form lasts the encounter. Collapsing that would have
    handed three creatures an escape their cards do not give them.

    The first shape if nothing is chosen, which only matters defensively:
    `c.choose` returns None solely for an empty list and every caller passes
    a non-empty tuple. Two of the three old writers wrote that fallback and
    `_change_shape` did not -- so on an empty choice it would have laid a
    form labelled `None` at 14 call sites.
    """
    for eff in list(c.world.effects.of(c.me)):
        if eff.label.endswith(" form"):
            c.world.effects.end(eff, "it changed shape")
    taken = c.choose(list(words), "which shape to take") or (words[0] if words else "")
    if not taken:
        return ""
    c.form(until=When.ENCOUNTER, revert=revert, name=taken,
           label=f"{c.ref} {taken} form")
    return taken
