"""The strikers' extra damage.

Three classes, one shape: once a round, when you hit the right sort of
target, you do more. The rogue's condition is combat advantage, the ranger
and the warlock each nominate a victim first. None of the three has a
compendium row of its own -- they are described in the class's own pages --
so they carry `cf:` refs.

A striker without this is not a striker. The rogue's dagger does 1d4, and
the whole class is built around what happens the round it connects.
"""

from __future__ import annotations

from collections.abc import Callable

from combat_engine.engine import (
    AT_WILL,
    FREE,
    MINOR,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    Cast,
    Gear,
    Keyword,
    Ranged,
    When,
    World,
    power,
)
from combat_engine.engine.events import Hit
from combat_engine.engine.query import has_combat_advantage


def extra_damage(
    c: Cast, dice: str, *, applies: Callable[[int], bool], label: str
) -> None:
    """Arm "once per round, when you hit X, add dice".

    Written once because all three strikers are this and differ only in what
    counts as X. The latch is per round and per *striker*, not per target --
    hitting two different creatures in one round pays once, which is what
    every one of the three printed texts says.
    """
    me = c.me
    paid: dict[int, int] = {}

    def on_hit(ev: Hit) -> None:
        if ev.attacker != me or not applies(ev.target):
            return
        if paid.get(me) == c.world.round:
            return
        paid[me] = c.world.round
        c.damage(dice, on=ev.target, detail=label)

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me, label=label)


def _light_blade_or_bow(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    if gear is None or gear.main is None:
        return False
    return gear.main.is_light_blade or bool(gear.main.ranged)


@power(
    "cf:rogue-strike",
    level=0,
    cls="rogue",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.MARTIAL],
    requires=_light_blade_or_bow,
    requires_text="needs a light blade, a crossbow or a sling",
)
def rogue_strike(c: Cast) -> None:
    """Once a round, a hit against a creature you have the drop on hurts more.

    Combat advantage is asked of the board at the moment of the hit rather
    than stored, which is the same reason `query` computes it: flanking ends
    the instant an ally steps away, and a stored flag would not notice.
    """
    extra_damage(
        c,
        "2d6",
        applies=lambda target: has_combat_advantage(c.world, c.me, target),
        label="cf:rogue-strike",
    )


@power(
    "cf:ranger-quarry",
    level=0,
    cls="ranger",
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL],
)
def ranger_quarry(c: Cast) -> None:
    """Name the nearest enemy as your quarry; hitting it pays once a round.

    The printed text says the nearest enemy you can see, which is a choice
    the ranger makes and the interface offers, so the target comes in as
    `c.target` like any other.
    """
    quarry = c.target
    if quarry is None:
        return
    extra_damage(
        c, "1d6", applies=lambda target: target == quarry, label="cf:ranger-quarry"
    )


@power(
    "cf:warlock-curse",
    level=0,
    cls="warlock",
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE],
)
def warlock_curse(c: Cast) -> None:
    """Curse an enemy; hitting it pays once a round, for the rest of the fight.

    Several warlock powers read "if the target is cursed", and this is what
    makes that true. `c.cursed(target)` is how they ask.
    """
    victim = c.target
    if victim is None:
        return
    c.curse(on=victim)
    extra_damage(
        c, "1d6", applies=lambda target: target == victim, label="cf:warlock-curse"
    )
