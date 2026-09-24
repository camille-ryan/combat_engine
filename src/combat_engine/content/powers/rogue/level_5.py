"""Rogue, level 5: the daily attacks.

Two want a light blade at reach 1. The third prints "Melee or Ranged weapon"
over the rogue's own three weapon groups and is `MeleeOrRanged`; Dexterity
attacks on either branch, so there is no second attack line and what differs
is the range, the weapon rolled and whether firing provokes.

Both standing arrangements are Effect lines, so they are armed whether or
not the opening swing landed, and both run to the end of the encounter.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    DAILY,
    DEX,
    FORT,
    ONE_CREATURE,
    STANDARD,
    Attack,
    Cast,
    Gear,
    Keyword,
    Melee,
    MeleeOrRanged,
    Moved,
    MoveEnd,
    When,
    World,
    power,
)
from combat_engine.engine.events import AttackDeclared, MoveStart

MARTIAL_WEAPON = [Keyword.MARTIAL, Keyword.WEAPON]

ROGUE_GROUPS = frozenset({"light blade", "crossbow", "sling"})


def _light_blade(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.is_light_blade)


def _rogue_weapon(world: World, eid: int) -> bool:
    gear = world.get(eid, Gear)
    return bool(gear and gear.main and gear.main.group in ROGUE_GROUPS)


@power(
    "p543",
    level=5,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=AC),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p543(c: Cast) -> None:
    """"Immediately after attacking you" is the reaction window of
    `AttackDeclared`, which the whole attack resolves inside -- so a listener
    there runs after the blow has landed, not before it is rolled.

    The shift is a printed *can*, so it is asked rather than taken.
    """
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
    victim = c.target
    if victim is None:
        return

    def retort(ev: AttackDeclared) -> None:
        if ev.target != c.me:
            return
        c.flat(c.dex_mod, on=victim)
        if c.may("shift a square", who=c.me):
            c.shift(1)

    c.on_attack(retort, by=victim, until=When.ENCOUNTER, label="p543")


@power(
    "p981",
    level=5,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=FORT),
    requires=_light_blade,
    requires_text="needs a light blade",
)
def p981(c: Cast) -> None:
    # The ongoing damage is the one place this row reads Strength.
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.ongoing(5 + c.str_mod)
    else:
        c.half_damage(c.w(2), c.dex_mod)


@power(
    "p999",
    level=5,
    cls="rogue",
    usage=DAILY,
    action=STANDARD,
    reach=MeleeOrRanged(1, 20),
    target=ONE_CREATURE,
    keywords=MARTIAL_WEAPON,
    attack=Attack(DEX, vs=FORT),
    requires=_rogue_weapon,
    requires_text="needs a crossbow, a light blade or a sling",
)
def p999(c: Cast) -> None:
    """The arrangement counts squares rather than measuring the two ends of
    the move: a walk that doubles back covers ground the finishing square
    does not show, and "moves more than half its speed" is about the going.

    One action's worth of it, so the tally opens at `MoveStart` and closes at
    `MoveEnd`; being shoved is not the target moving with an action of its
    own, so only a walk counts, and only on its own turn.
    """
    victim = c.target
    if c.strike():
        c.damage(c.w(2), c.dex_mod)
        c.prone()
    else:
        c.half_damage(c.w(2), c.dex_mod)
    if victim is None:
        return

    walking = False
    steps = 0

    def began(ev: MoveStart) -> None:
        nonlocal walking, steps
        if ev.actor == victim:
            walking, steps = ev.kind_ == "walk", 0

    def stepped(ev: Moved) -> None:
        nonlocal steps
        if ev.actor == victim:
            steps += 1

    def ended(ev: MoveEnd) -> None:
        nonlocal walking, steps
        if ev.actor != victim:
            return
        far, was_walking = steps, walking
        walking, steps = False, 0
        if was_walking and c.turn_of() == victim and far * 2 > c.speed_of(victim):
            c.prone(on=victim)

    c.watch(MoveStart, began, until=When.ENCOUNTER, label="p999 sets off")
    c.watch(Moved, stepped, until=When.ENCOUNTER, label="p999 counts")
    c.watch(MoveEnd, ended, until=When.ENCOUNTER, label="p999 stops")
