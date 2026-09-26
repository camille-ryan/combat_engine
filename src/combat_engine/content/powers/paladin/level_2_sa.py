"""Paladin level 2: answering a skill check you are about to make."""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    ENCOUNTER,
    FREE,
    NO_TARGET,
    PERSONAL,
    Cast,
    Event,
    Hit,
    Keyword,
    SkillCheck,
    Trigger,
    When,
    Window,
    World,
    get,
    power,
)

#: The two the card names.
_ASKED = ("athletics", "endurance")


def _the_two(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "actor", None) == me and getattr(ev, "skill", "") in _ASKED


def _melee_damage(ctx: dict[str, Any]) -> bool:
    """The damage context carries the row and nothing about how it was swung,
    so the reach is read off the row. A miss's detail has a suffix."""
    p = get((ctx.get("power") or "").removesuffix(" (half)"))
    return p is not None and p.reach is not None and p.reach.kind == "melee"


@power(
    "p11049",
    level=2,
    cls="paladin",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    trigger="you would make an Athletics check or an Endurance check",
    on=Trigger(
        SkillCheck,
        _the_two,
        "you would make an Athletics check or an Endurance check",
        window=Window.BEFORE,
    ),
)
def p11049(c: Cast) -> None:
    """+5 to the check, +2 to melee damage, and your sanction on what you hit.

    "**Would** make" is the interrupt window, so the trigger declares
    `Window.BEFORE` rather than the reaction window a free action usually
    answers in -- `engine/skills.py` totals the modifiers inside the resolve
    callback, which is after this and is what makes the +5 reach the roll
    it is printed for.

    Divine sanction is written as the paladin's mark: it is the same hold
    with a different word on the card, and nothing else in the engine
    distinguishes them.
    """
    ev = c.trigger
    skill = getattr(ev, "skill", "")
    if skill:
        c.bonus(f"skill:{skill}", 5, kind="power", on=c.me, until=When.EOT)
    c.bonus("damage", 2, kind="power", on=c.me, until=When.EONT, when=_melee_damage)

    me = c.me

    def sanctioned(hit: Hit) -> None:
        p = get(hit.power)
        melee = p is not None and p.reach is not None and p.reach.kind == "melee"
        if hit.attacker == me and melee:
            c.mark(on=hit.target, until=When.EONT)

    c.watch(Hit, sanctioned, until=When.EONT, on=me, label="p11049 sanction")
