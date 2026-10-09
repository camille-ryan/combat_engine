"""Asking and answering which shape a creature is wearing.

Four helpers, shared because three dozen rows across eight level directories
need them and the natural home -- the first file that wanted one -- would make
`level_01` import `level_03`, which is a cycle.

**This module imports nothing from `content`**, which is what keeps it
importable from any row file.

`level_04/brutes_sa.py` has its own `_in_shapes`, predating these and reading
the effect labels rather than a component. It does the same job for 26 rows
and should be folded in here; that is deliberately a separate change, because
its rows are gated and working and a rewrite of them proves nothing.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine.cast import Cast
from combat_engine.engine.durations import When
from combat_engine.engine.ecs import World
from combat_engine.engine.query import in_form, shifted


def _shapes(*words: str) -> Callable[[World, int], bool]:
    """A printed "must be in X form" Requirement, as a `requires=` gate.

    `requires=` is handed a world and an id rather than a `Cast`, so it reads
    `query.in_form` straight -- including that function's permissive answer
    for a creature nobody has transformed yet.

    **`_in_shapes` in `level_04/brutes_sa.py` is this same gate** read off
    effect labels instead of `Shapes`, and it came first. The two want
    unifying; until they are, both answer the same question the same way.
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


def _shapechange(c: Cast, *words: str) -> str:
    """"It alters its physical form to appear as one of these."

    **One at a time.** Taking a shape ends whichever it was already wearing,
    which is what "until it uses this power again" means on every one of
    these cards -- so the forms are a set on the creature but a shapechanger
    only ever has one of them in it.

    The natural form is in the list because changing *back* is a use of the
    same power, and after a change back the form is recorded rather than
    inferred -- which reads the same way round either way.
    """
    for eff in list(c.world.effects.of(c.me)):
        if eff.label.endswith(" form"):
            c.world.effects.end(eff, "it changed shape")
    taken = c.choose(list(words), "which shape to take")
    if not taken:
        return ""
    c.form(until=When.ENCOUNTER, name=taken, label=f"{c.ref} {taken} form")
    return taken
