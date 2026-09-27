"""The second stat block a card prints beside its own.

Three hundred and seventy-five compendium entries print two blocks under
one id -- a standard-action attack and the free action it grants, a stance
and the attack that only works inside it -- and the importer gives the
second a ref of its own with a letter on the end, because the parent's
columns are wrong for it.

Nearly all of those second blocks carry the same Requirement line: the row
they are printed beside has to be up. `active` is that line. It reads the
effect table rather than the power list, since what the parent leaves
behind is a stance, a form or a hold labelled with its own ref -- which is
what `c.stance`, `c.form` and `c.effect` all default to.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine import World


def active(ref: str) -> Callable[[World, int], bool]:
    """"Requirement: the <ref> power must be active to use this power."""

    def check(world: World, eid: int) -> bool:
        return any(eff.label == ref for eff in world.effects.of(eid))

    return check
