"""Vampire powers, levels 1 to 10, and the two sentences the class repeats.

**`next_check` is "a +N bonus to the next <skill> check you make".** Three
rows here print it and `c.bonus(once=True)` is nearly the thing and wrong in
two ways on a card that names more than one skill. Its spend watcher ends the
hold on *any* check the owner makes, so an unrelated roll eats a bonus the
card reserves for a named one; and two holds laid separately are two separate
spends, where the card gives one bonus between the skills it lists. So the
hold is spent by hand, by the check the printed sentence names, and every key
laid for one sentence goes at once.

**`ends_with` ties a while-in-this-shape benefit to the shape**, the way
`druid/forms.py` does with a helper of the same name. The benefits are
written at the longer of the two printed clocks and the shape's own ending is
the shorter one; without it a character stepping out early keeps what the
shape gave it. Duplicated rather than imported across a class boundary, which
is what every other power package does with its own helpers.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import Cast, Effect, SkillCheck, When


def next_check(
    c: Cast,
    amount: int,
    *keys: str,
    until: When,
    against: int | None = None,
) -> list[Effect]:
    """One bonus shared between the skills a card lists, spent by the first.

    `keys` are **modifier** keys -- `skill:bluff`, `ability:str` -- because
    that is what `c.bonus` reads and what `engine/skills.py` totals.
    `SkillCheck.skill` carries the bare name for a skill check and the
    prefixed one for an ability check, so the second spelling is derived here
    rather than asked of the caller.

    `against` is a printed "against the target", and only a skill check
    carries one: `skills.ability_check` takes no target at all, so an
    `ability:` key in `keys` is gated on nothing. That is the honest reading
    of a card listing both kinds -- the narrowing is applied where it can be
    asked and not invented where it cannot.
    """
    rolled = {k.split(":", 1)[1] if k.startswith("skill:") else k for k in keys}

    def wanted(ctx: dict[str, Any]) -> bool:
        return against is None or ctx.get("target") == against

    holds = [
        hold
        for hold in (
            c.bonus(key, amount, on=c.me, until=until, kind="power", when=wanted)
            for key in keys
        )
        if hold is not None
    ]
    if not holds:
        return []

    def spent(ev: SkillCheck) -> None:
        if ev.actor != c.me or ev.skill not in rolled:
            return
        if against is not None and ev.target != against:
            return
        for hold in holds:
            c.world.effects.end(hold, "used")

    c.watch(SkillCheck, spent, until=until, on=c.me, label=f"{c.ref} spends")
    return holds


def ends_with(c: Cast, shape: Effect | None, *holds: Effect | None) -> None:
    """Tie a while-in-this-shape benefit to the shape itself."""
    if shape is None:
        return
    for hold in holds:
        if hold is not None:
            shape.on_end.append(
                lambda h=hold: c.world.effects.end(h, "the shape ended")
            )
