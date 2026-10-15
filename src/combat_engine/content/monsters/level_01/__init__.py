"""Monster abilities, level 1, split by role.

One file per role rather than one per level: a level has thirty monsters in
it and several people write them at once, and a role is the natural seam --
a brute and an artillery share nothing but their level.

What two roles genuinely do share goes here, which is why the pair of
helpers below are not in any of the files that call them.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import Cast, Condition, Health, Movement, When


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
    """The whole of one card, printed five times: ground yourself, finish
    something helpless, and feed if it dies.

    Neither cost is a condition carried by default: insubstantial is ended
    if something granted it, and flight is a movement mode, so it is lifted
    out of `Movement.modes` and put back when the hold runs out.

    **The finisher used to be missing and this helper paid only the price.**
    Four callers said so with `dropped=("c.coup_de_grace(ref=)",)` and
    **two did not** -- `m2939a2` and `m2940a3` carried no marker at all, so
    two rows reported finished while missing the same clause the other four
    admitted to. Every one of the five cards ends in the same sentence:
    "...makes a coup de grace against the target. If it kills the target, it
    regains all of its hit points."

    `c.coup_de_grace` is the wrong symbol for it and `m3435a3` -- the sixth
    row of this card, written and unmarked throughout -- says why in its own
    docstring: that verb refuses a row declaring no attack line, which was
    Camille's call on #250 rather than inventing damage, and none of these
    cards print one. So the swing is the creature's **own basic attack**, and
    the automatic critical comes from `c.maximise(critical=True)`, which sets
    `critical` on the live `Hit` rather than faking a number -- so crit
    riders on the swing are paid too.

    This follows `m3435a3` line for line rather than inventing a second
    answer to one question.
    """
    victim = c.target
    for effect in list(c.world.effects.of(c.me)):
        if Condition.INSUBSTANTIAL in effect.conditions:
            c.world.effects.end(effect, c.ref)
    hold = c.effect(f"{c.ref} grounded", until=When.EONT, on=c.me)
    movement = c.world.get(c.me, Movement)
    if hold is not None and movement is not None and "fly" in movement.modes:
        speed = movement.modes.pop("fly")
        hold.on_end.append(lambda: movement.modes.setdefault("fly", speed))

    # The price is paid above whether or not there is anything to finish,
    # which is what the cards print -- the grounding is not conditional on
    # the kill.
    if victim is None:
        return
    c.maximise(on=c.me, until=When.EOT, critical=True)
    c.basic(on=victim)
    hurt = c.world.get(victim, Health)
    if hurt is None or hurt.hp > 0:
        return
    mine = c.world.get(c.me, Health)
    if mine is not None:
        c.heal(mine.max_hp, on=c.me)
