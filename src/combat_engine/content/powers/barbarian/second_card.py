"""Barbarian: the second stat block printed beside `p4832`.

A free-action swing the parent's rage grants, with no printed Trigger --
it is chosen, not answered, so it belongs on the turn menu and takes no
`on=`. Printed Daily; the parent grants it "once per turn only on your own
turn" for as long as the rage runs, which is at-will with a round latch.
"""

from __future__ import annotations

from combat_engine.engine import *

from .rage import RAGE


def _in_this_rage(ref: str):  # noqa: ANN202
    """"Requirement: the <ref> power must be active."

    `cards.active` matches the label exactly and a rage is labelled with
    the word as well as the ref, so the stance is read directly.
    """

    def check(world: World, eid: int) -> bool:
        stance = world.effects.stance_of(eid)
        return stance is not None and stance.label == f"{ref} {RAGE}"

    return check


@power(
    "p4832b",
    level=5,
    cls="barbarian",
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PRIMAL, Keyword.WEAPON, Keyword.THUNDER],
    attack=Attack(STR, vs=FORT),
    once_per_round=True,
    requires=_in_this_rage("p4832"),
    requires_text="the p4832 rage must be running",
)
def p4832b(c: Cast) -> None:
    if c.strike():
        c.prone()
