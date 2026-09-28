"""Avenger feats.

Every one of these turns on "your oath of enmity target", and the class
already answers that question: `content/powers/avenger/oath.py` labels
the hold it lays and exports `sworn(world, me, who)` to read it back.
Importing it here rather than re-deriving the test is the point -- two
versions of "is this creature sworn" would be two chances to disagree,
and the one in `oath.py` is the one the oath itself uses.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.avenger.oath import sworn
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Cast,
    Dropped,
    Gear,
    Hit,
    Trigger,
    When,
    power,
)
from combat_engine.engine.query import enemies
from combat_engine.engine.types import Forced


def _enemy_hit_me(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.target == me and not sworn(world, me, ev.attacker)


def _charged_my_oath(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return (
        ev.attacker == me
        and getattr(ev, "charge", False)
        and sworn(world, me, ev.target)
    )


@power("f1007", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an enemy other than your oath target hits you",
       on=Trigger(Hit, _enemy_hit_me, "somebody other than your oath hits you"))
def f1007(c: Cast) -> None:
    """The bonus applies only against the sworn enemy, which is asked per
    attack -- the oath moves from creature to creature over a fight."""
    me = c.me
    c.bonus(
        "attack", 1, on=me, until=When.EONT,
        when=lambda ctx: sworn(c.world, me, ctx.get("target")),
    )


@power("f1013", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit your oath target with a charge",
       on=Trigger(Hit, _charged_my_oath, "you charge your oath"))
def f1013(c: Cast) -> None:
    c.bonus(AC, 2, on=c.me, until=When.EONT)
    c.bonus("damage", 2, on=c.me, until=When.EONT)


@power("f1489", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1489(c: Cast) -> None:
    """Defences against **everyone except** the sworn enemy, and only
    while standing next to it. Both halves are asked per attack: the
    avenger moves and the oath moves."""
    me = c.me

    def elsewhere(ctx: dict) -> bool:
        attacker = ctx.get("attacker")
        if attacker is None or sworn(c.world, me, attacker):
            return False
        # Standing next to the sworn one. Found by asking each enemy
        # rather than the relation table: the oath is held as a labelled
        # *effect* -- see `oath.swear` -- and not as a relation, so
        # `Relations` has nothing to look up.
        return any(
            sworn(c.world, me, foe) and c.adjacent(to=foe)
            for foe in enemies(c.world, me)
        )

    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 1, on=me, until=When.ENCOUNTER, when=elsewhere)


@power("f1078", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1078(c: Cast) -> None:
    """+1 AC in cloth or nothing, with no shield. `Gear.armour` is the
    printed word and `Gear.shield` the other half, both read when the
    trait arms -- neither changes mid-fight."""
    gear = c.world.get(c.me, Gear)
    if gear is None or gear.shield or gear.armour not in ("cloth", ""):
        return
    c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER)


@power("f1493", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you drop your oath target",
       on=Trigger(Dropped, lambda w, me, ev: (
           getattr(ev, "source", None) == me and sworn(w, me, ev.actor)
       ), "you drop your oath"))
def f1493(c: Cast) -> None:
    """An extra move action. `usage=ENCOUNTER` is the "first time in an
    encounter" -- the budget does the limiting, so the body counts
    nothing. `c.extra_action`, not `c.grant_action`: the latter opens a
    menu line for an action you already have and understands only
    `shift`, `stand` and `second_wind`."""
    c.extra_action(ActionType.MOVE)


@power("f1490", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_racial_bonus()",))
def f1490(c: Cast) -> None:
    """Extra damage equal to a bonus a racial power gave the attack roll.
    The power is named by ref; what is missing is any record of how much
    a particular modifier contributed to a particular roll."""


@power("f1492", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1492(c: Cast) -> None:
    """Adds two squares to the pull `p6980` makes.

    `c.extend_forced()` was the wrong symbol: `c.forces` is the verb and
    it is the shover's side of `c.resist_forced`, read off whoever is
    doing the shoving. Its gate is handed `how` and `power`, which is
    both halves of "the pull your p6980 makes" -- and `how` arrives as
    the enum's value rather than the member, so the comparison is
    against `Forced.PULL.value`.

    A standing modifier rather than a rider on the use: the shove reads
    the key while it is being applied, which is inside that row's body.
    """
    c.forces(
        2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("power") == "p6980" and ctx.get("how") == Forced.PULL.value
        ),
    )
