"""Rogue: the second stat blocks printed beside `p10167` and `p10173`.

Both parents are grants and nothing else -- a stance in one case, a hold
until the end of your next turn in the other -- and both of these are the
swing that grant unlocks. Each carries two printed Requirements, the
parent being up and a light blade in hand, so `requires=` is the pair.

Printed frequency on both second blocks is not the frequency that can be
said. `p10167b` is printed Daily but its parent reads "each time an enemy
hits or misses you, you can use" -- it is not spent by being used, and the
once-a-round limit is the immediate action's. `p10173b` is printed At-Will
and means it.
"""

from __future__ import annotations

from combat_engine.content.powers.cards import active
from combat_engine.engine import *
from combat_engine.engine.query import adjacent


def _light_blade(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.is_light_blade)


def _up_with_a_blade(ref: str):  # noqa: ANN202
    standing = active(ref)

    def check(world: World, eid: int) -> bool:
        return standing(world, eid) and _light_blade(world, eid)

    return check


def _adjacent_attacker(world: World, me: int, ev: AttackDeclared) -> bool:
    return ev.attacker is not None and adjacent(world, me, ev.attacker)


def _enemy_opens_adjacent(world: World, me: int, ev: TurnStart) -> bool:
    return not ev.ghost and enemy_within(1)(world, me, ev)


@power(
    "p10167b",
    level=1,
    cls="rogue",
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(DEX, vs=REF),
    requires=_up_with_a_blade("p10167"),
    requires_text="the p10167 stance must be up, with a light blade in hand",
    trigger="an enemy adjacent to you attacks you",
    on=Trigger(
        AttackDeclared,
        both(targets_me, _adjacent_attacker),
        "an enemy adjacent to you attacks you",
    ),
)
def p10167b(c: Cast) -> None:
    if c.strike():
        c.damage(c.w(1), c.dex_mod)


@power(
    "p10173b",
    level=7,
    cls="rogue",
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(DEX, vs=REF),
    requires=_up_with_a_blade("p10173"),
    requires_text="the p10173 power must be active, with a light blade in hand",
    trigger="an enemy starts its turn in or enters a square adjacent to you",
    on=[
        Trigger(
            AdjacencyGained,
            both(closed_on_me, enemy_within(1)),
            "an enemy enters a square adjacent to you",
        ),
        Trigger(
            TurnStart,
            _enemy_opens_adjacent,
            "an enemy starts its turn adjacent to you",
        ),
    ],
)
def p10173b(c: Cast) -> None:
    """`AdjacencyGained` is emitted mirrored, so the enemy's own copy of the
    event has to be picked out: `closed_on_me` is true of both halves and
    `enemy_within` is what says which of the two named the enemy."""
    foe = c.target
    if foe is None:
        return
    sting = 2 + c.cha_mod if c.build("trickster") else c.cha_mod
    if c.strike():
        c.damage(c.w(1), c.dex_mod)
        c.penalty(
            "attack", sting, on=foe, until=When.EONT,
            when=lambda ctx: ctx.get("target") == c.me,
        )
