"""Monster abilities, level 1, split by role.

One file per role rather than one per level: a level has thirty monsters in
it and several people write them at once, and a role is the natural seam --
a brute and an artillery share nothing but their level.

What two roles genuinely do share goes here, which is why the pair of
helpers below are not in any of the files that call them.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import Cast, Condition, Movement, When


def aquatic_edge(c: Cast) -> None:
    """The half of an underwater creature's trait that has anything to model.

    Breathing underwater costs nothing in a fight -- nothing here drowns --
    so what is left is the bonus, and `c.terrain` is asked inside the gate
    rather than once when the trait is armed. It answers False in an
    ordinary fight, which is the whole reason the check is written out.

    **Untyped, not racial.** A monster's stat block prints a bare "+2
    bonus"; a *racial* bonus is a player-race idea and does not appear in
    one. The distinction is not cosmetic -- two racial bonuses do not
    stack and two untyped ones do. This was written both ways in two
    copies of the same sentence, so one of them was wrong either way.
    """

    def against_a_landlubber(ctx: dict[str, Any]) -> bool:
        # `.get`, not `[...]`. Not every context that asks about an attack
        # bonus carries a target, and indexing raised on the ones that did
        # not.
        victim = ctx.get("target")
        return (
            c.terrain("aquatic")
            and victim is not None
            and not c.is_kind("aquatic", on=victim)
        )

    c.bonus("attack", 2, until=When.ENCOUNTER, on=c.me, when=against_a_landlubber)
    c.note(f"{c.ref}: it can breathe underwater")


def settle(c: Cast) -> None:
    """Drop insubstantial and flight until the end of the caster's next turn.

    The price a pair of these creatures pay to finish something off. Neither
    half is a condition carried by default: insubstantial is ended if
    something granted it, and flight is a movement mode, so it is lifted out
    of `Movement.modes` and put back when the hold runs out.
    """
    for effect in list(c.world.effects.of(c.me)):
        if Condition.INSUBSTANTIAL in effect.conditions:
            c.world.effects.end(effect, c.ref)
    hold = c.effect(f"{c.ref} grounded", until=When.EONT, on=c.me)
    movement = c.world.get(c.me, Movement)
    if hold is None or movement is None or "fly" not in movement.modes:
        return
    speed = movement.modes.pop("fly")
    hold.on_end.append(lambda: movement.modes.setdefault("fly", speed))
