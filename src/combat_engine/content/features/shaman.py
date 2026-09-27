"""Shaman class features: the spirit companion and the two features whose
whole benefit is a power the tree already carries.

The class page's `cf:shaman-f0cN` refs are not here. Every one of them is a
power card that is already declared under its own `p` ref in
`content/powers/shaman/` -- `cf:shaman-f0c0` and `p6515` are the same printed
block reached from the class page instead of the power list -- so declaring
them would deal a shaman the same card twice. They are an extraction fault
and are left out rather than stubbed.

What the class page genuinely adds is the choice between Companion Spirits,
which is the `cf:shaman-f0sN` run. `chargen.loadout` deals a shaman every
level 0 row its class has, so the choice is only real if the rows the other
spirits hand out are taken *away* -- the same trick `features/builds.py`
plays for the warlord's leader feature.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.shaman._spirit import beside_spirit, friends
from combat_engine.engine import (
    AC,
    ENCOUNTER,
    FORT,
    NO_TARGET,
    PERSONAL,
    REF,
    WILL,
    ActionType,
    Cast,
    Healed,
    Keyword,
    When,
    Window,
    power,
)

PRIMAL = [Keyword.PRIMAL]

#: A trait's header. Every row here is standing text rather than an action,
#: and they all take the same one.
TRAIT = {
    "level": 0,
    "cls": "shaman",
    "usage": ENCOUNTER,
    "action": ActionType.NONE,
    "reach": PERSONAL,
    "target": NO_TARGET,
    "keywords": PRIMAL,
}


def _spirit_choice(c: Cast, leg: str, refs: tuple[str, str]) -> None:
    """The half of a Companion Spirit option that is its two rows.

    Granting is nearly a no-op -- `loadout` already dealt them -- so the
    load-bearing branch is the other one: a shaman who chose a different
    spirit loses this one's special attack and its at-will, which is the
    only way "choose one of the following" is true on the board.
    """
    for ref in refs:
        if c.build(leg):
            c.grant_row(ref)
        else:
            # `c.forbid` follows `c.target` and a trait has none.
            c.forbid(ref, until=When.ENCOUNTER, on=c.me)


def _provoked_beside(c: Cast, who: int):  # noqa: ANN202
    """"Provokes an opportunity attack by entering or leaving a square
    adjacent to your spirit companion", as an attack-context gate.

    The attack context carries `opportunity`; which square the ally was
    moving out of it does not carry, so the gate is "still beside the
    spirit as the swing is rolled" -- true for the whole of the leaving
    case, since an opportunity attack interrupts the move.
    """

    def gate(ctx: dict[str, Any]) -> bool:
        return bool(ctx.get("opportunity")) and beside_spirit(c, who)

    return gate


@power(
    "cf:shaman-f0",
    **TRAIT,
    dropped=("Keyword.SPIRIT",),
)
def shaman_f0(c: Cast) -> None:
    """The feature's writable half is the power it hands over.

    "Your spirit companion must be present when you use a spirit power" is
    dropped: there is no `Keyword.SPIRIT`, so there is no set of rows to
    gate. The spirit-melee rows are gated anyway -- their reach is measured
    from the companion and cannot be measured without one -- but a ranged
    spirit power is not, and that is the gap.

    The Companion Spirit choice is the `cf:shaman-f0sN` rows.
    """
    c.grant_row("p6515")


@power("cf:shaman-f0s0", **TRAIT)
def shaman_f0s0(c: Cast) -> None:
    """The boon is a rider on somebody else's healing, so it is laid as a
    watcher on `Healed` in the before-window, where the amount is still
    negotiable, rather than as a second heal that would count as its own.

    A second wind is a heal whose source is its own target, which is how
    "when he or she uses second wind" is told from a leader's surge.
    """
    _spirit_choice(c, "protector", ("p5389", "p6521"))
    if not c.build("protector") or c.con_mod <= 0:
        return
    me, extra = c.me, c.con_mod

    def more(ev: Healed) -> None:
        if (
            ev.target in friends(c)
            and beside_spirit(c, ev.target)
            and ev.source in (me, ev.target)
        ):
            ev.amount += extra

    c.watch(
        Healed, more, until=When.ENCOUNTER, window=Window.BEFORE, on=me, label=c.ref
    )


@power("cf:shaman-f0s1", **TRAIT)
def shaman_f0s1(c: Cast) -> None:
    """Untyped: the card prints no word in front of "bonus". The gate is
    re-asked at each damage roll, so an ally who walks away from the spirit
    loses it, which "any ally adjacent to your spirit companion" means."""
    _spirit_choice(c, "stalker", ("p5388", "p5510"))
    if not c.build("stalker") or c.int_mod <= 0:
        return
    for mate in friends(c):
        c.bonus(
            "damage",
            c.int_mod,
            on=mate,
            until=When.ENCOUNTER,
            when=lambda ctx, m=mate: beside_spirit(c, m)
            and (victim := ctx.get("target")) is not None
            and c.bloodied(on=victim),
        )


@power("cf:shaman-f0s2", **TRAIT, dropped=("c.nearest_enemy()",))
def shaman_f0s2(c: Cast) -> None:
    """"Cover from other enemies" is narrower than anything the engine can
    say -- what grants the cover is not in the context the gate is handed --
    so this is `partial=True`, which cancels ordinary cover and leaves
    superior cover standing. Cover from a creature is the ordinary kind.

    The second sentence is dropped: nothing asks or answers which enemy is
    an ally's nearest, so "treat any enemy adjacent to your spirit companion
    as their nearest enemy" has nothing to change.
    """
    _spirit_choice(c, "world speaker", ("p9732", "p9734"))
    if not c.build("world speaker"):
        return
    for foe in c.enemies():
        c.no_cover(
            on=foe,
            until=When.ENCOUNTER,
            partial=True,
            when=lambda ctx, f=foe: beside_spirit(c, f),
        )


@power("cf:shaman-f0s3", **TRAIT)
def shaman_f0s3(c: Cast) -> None:
    """All four defences, which is what "all defenses" says, and untyped."""
    _spirit_choice(c, "watcher", ("p9733", "p9736"))
    if not c.build("watcher") or c.con_mod <= 0:
        return
    for mate in friends(c):
        gate = _provoked_beside(c, mate)
        for defence in (AC, FORT, REF, WILL):
            c.bonus(defence, c.con_mod, on=mate, until=When.ENCOUNTER, when=gate)


@power("cf:shaman-f1", **TRAIT)
def shaman_f1(c: Cast) -> None:
    """The whole benefit is the card, which the tree already carries."""
    c.grant_row("p3773")


@power("cf:shaman-f2", **TRAIT)
def shaman_f2(c: Cast) -> None:
    c.grant_row("p3775")
