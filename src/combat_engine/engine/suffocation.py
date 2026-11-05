"""Holding your breath in a fight. `#1115`.

DMG p159, read in `resources/` rather than taken from the issue:

> *"In strenuous situations, such as combat, going without air is much
> harder. A character holding his breath during underwater combat, for
> example, must make a DC 20 Endurance check at the end of his turn in a
> round where he takes damage."*

> *"As with environmental dangers, a character cannot regain healing surges
> lost to starvation, thirst, or suffocation until he eats a meal, drinks,
> or gains access to air again, respectively."*

> *"A character with 0 or fewer hit points who continues to suffer from one
> of these effects keeps taking damage as described above until he dies or
> is rescued."*

So four things, and the clause most likely to be dropped is the one that
makes the rule bearable:

| | |
|---|---|
| the check | DC **20** Endurance, at the end of a turn |
| **when** | **only in a round where the creature took damage** -- not every turn |
| on a failure | a surge; with none left, damage equal to level |
| at 0 or fewer | it keeps going, which falls out of not exempting them |

Dropping *"in a round where he takes damage"* makes this fire every turn,
which is strictly harsher than print, so it is the assertion
`drivers.suffocation` leads with.

## Who is holding their breath is derived, not flagged

The printed sentence assumes it and nothing on a creature records it. The
set is **in aquatic terrain, and not exempt from swimming** -- which is
`movement.swims`' own exemption, read through the same door rather than
re-derived:

* `"aquatic" in world.terrain`, which only a module sets (`#1083`), so this
  rule reaches module play and leaves every arcade board and `replay`
  fixture alone;
* `Movement.modes["swim"]`, which is what exempts a creature from the
  Athletics check to swim.

A creature that does not have to roll to swim does not have to hold its
breath, and tying the two to one reader is what keeps them agreeing. A new
`holding_breath` flag would have been a second thing to keep in step.

## Taking damage is read off the bus, not stored

`Health` records hit points, not when they went, and `#1115` suggested a
`DamageApplied` watcher setting a per-round mark -- the shape
`Movement.swim_round` already uses. Checked first, as that issue asked:
**nothing records it today**, so it would have been new state.

The log answers it instead. `world.bus.log` holds every `DamageApplied`
and `RoundStart`, so "this round" is a bounded backward scan to the round
boundary -- no component field, nothing to keep in step, and it is the same
thing a driver would read to assert it. `#946`'s "who hurt me last" reader
would want the same scan, so if that lands the two share this.

## Not the deprivation half

`#971` keeps that: three weeks without food, three days without water, an
**escalating** DC of 20/25/30 and a check per day. Three minutes of air is
rounds rather than days, which is why the page states it separately.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .components import Health, Movement
from .events import RoundStart
from .types import DamageType

if TYPE_CHECKING:  # pragma: no cover - typing only
    # Under `TYPE_CHECKING` because `ecs` imports nothing from here and this
    # module is reached from `turns`, which `ecs` is below -- a real import
    # would be a cycle. `world: object` was the first draft and it is the
    # annotation fault this repo has a standing note about: it erases the
    # type, `ruff` passes, and `types.py` goes red.
    from .ecs import World

#: The printed DC. One number, flat, and **not** off `dc.py`: that table
#: scales with level because a challenge is pitched at the party, and the
#: page prints 20 for everybody. Reading it off a band would make drowning
#: easier for a stronger character, which is the same mistake
#: `story/run.py`'s weather note records about its own fixed DCs.
DC = 20

#: The skill the page names.
SKILL = "endurance"


def holding_breath(world: World, eid: int) -> bool:
    """Is this creature without air on this board?

    In aquatic terrain and not exempt from swimming. See the module
    docstring for why the exemption is `movement.swims`' and not a flag of
    its own.
    """
    if "aquatic" not in getattr(world, "terrain", frozenset()):
        return False
    move = world.get(eid, Movement)
    if move is None:
        return False
    return not move.modes.get("swim")


def hurt_this_round(world: World, eid: int) -> bool:
    """Did this creature take damage since the round began?

    A backward scan to the last `RoundStart`, which is cheap and stores
    nothing. See the module docstring: `Health` does not record *when* hit
    points went, and adding a mark would be new state for one reader.
    """
    log = getattr(world, "bus", None)
    if log is None:
        return False
    for event in reversed(list(log.log)):
        if isinstance(event, RoundStart):
            return False
        if type(event).__name__ != "DamageApplied":
            continue
        if getattr(event, "target", None) == eid and getattr(
                event, "amount", 0) > 0:
            return True
    return False


def owed(world: World, eid: int) -> bool:
    """Does this creature owe the check at the end of this turn?

    Both halves, because either alone is the wrong rule: without the
    terrain test it fires on dry land, and without the damage test it fires
    every turn, which is harsher than print.
    """
    return holding_breath(world, eid) and hurt_this_round(world, eid)


def check(world: World, eid: int) -> bool:
    """The printed end-of-turn check. Returns whether it was passed.

    `True` when nothing was owed, because the caller's question is "is this
    creature in trouble" and a creature with air is not. A caller wanting
    to know whether a roll happened asks `owed` first -- which is what the
    driver does, so a check that stops being owed cannot read as a pass.

    **A failure costs a surge, and damage equal to level with none left.**
    That is the same consequence the environmental rule has, which is the
    page's own *"as described above"*. At 0 or fewer hit points it keeps
    going: nothing here exempts a dying creature, which is the printed
    *"keeps taking damage ... until he dies or is rescued"* falling out
    rather than being written.
    """
    from .resolve import deal_damage, spend_surge
    from .skills import check as roll

    if not owed(world, eid):
        return True
    got = roll(world, eid, SKILL, DC, purpose="suffocation")
    if got:
        return True
    health = world.get(eid, Health)
    if health is not None and health.surges > 0:
        spend_surge(world, eid)
        return False
    level = getattr(health, "level", 0) if health is not None else 0
    if not level:
        from .components import Stats

        stats = world.get(eid, Stats)
        level = stats.level if stats is not None else 1
    deal_damage(
        world,
        0,
        eid,
        max(1, level),
        DamageType.UNTYPED,
        detail="suffocation",
        from_attack=False,
    )
    return False
