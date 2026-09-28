"""Getting out of a grab.

A grabbed creature spends a move action and rolls one check: Acrobatics
against the grabber's Reflex, or Athletics against its Fortitude. On a
success the hold is gone and it may shift a square. That is the whole of
the printed action, and until now the engine had none of it -- `c.grab`
laid a relation that only the grabber could ever end.

Three modifier keys, and which creature carries each is the point:

* **`escape`** -- on the creature struggling. Every row that touches this
  writes to it. Deliberately not `skill:acrobatics`: a bonus to getting
  out of a grab is not a bonus to tumbling, and writing it as one would
  have raised every unrelated check the creature ever made.
* **`grab_defence`** -- on the grabber, added to the number the check must
  beat. "A bonus to your defences when preventing an escape from your
  grab" is about the hold, not about the holder in general.
* **`grab_vs_fort`** -- on the grabber. Any positive value measures every
  attempt against its Fortitude whichever skill is rolled, which is the
  one printed line that changes the pairing.

The check is rolled through `skills.check`, so the interrupt window it
opens is the same one a Trigger on `SkillCheck` answers, and the modifiers
are totalled after that window as they are everywhere else.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .events import Escaped
from .query import defence
from .resolve import _mods
from .skills import check, modifier
from .types import Defense, Relation

if TYPE_CHECKING:
    from .ecs import World

#: The two skills the action offers and the defence each is measured
#: against. Both are printed; the creature picks.
SKILLS: dict[str, Defense] = {
    "acrobatics": Defense.REF,
    "athletics": Defense.FORT,
}


def holders(world: World, eid: int) -> list[int]:
    """Everyone holding this creature in a grab."""
    return world.relations.sources(Relation.GRABBED_BY, eid)


def grabbed(world: World, eid: int) -> bool:
    return bool(holders(world, eid))


def _best(world: World, eid: int) -> str:
    """Which skill the creature would rather roll.

    By its own modifier and nothing else. Comparing the two *defences*
    would be closer to what a player does, but a creature does not know
    the numbers it is being measured against, and the cheap answer is the
    one a policy can reproduce.
    """
    return max(SKILLS, key=lambda s: modifier(world, eid, s))


def attempt(
    world: World,
    eid: int,
    *,
    holder: int | None = None,
    skill: str = "",
    bonus: int = 0,
    auto: bool = False,
) -> bool:
    """One escape attempt. True if the creature got free.

    `auto` is "you escape a grab automatically", which is printed without a
    roll -- so no check is made and none is announced, and a row watching
    for the check must not see one that never happened.
    """
    held = holders(world, eid)
    if not held:
        return False
    who = holder if holder in held else held[0]
    picked = skill if skill in SKILLS else _best(world, eid)
    ctx = {"actor": eid, "holder": who, "skill": picked}

    won = True
    if not auto:
        vs = Defense.FORT if _mods(world, who, "grab_vs_fort", ctx) > 0 else SKILLS[picked]
        dc = defence(world, who, vs, ctx) + _mods(world, who, "grab_defence", ctx)
        won = bool(check(
            world, eid, picked, dc=dc, bonus=bonus + _mods(world, eid, "escape", ctx)
        ))

    if won:
        from .cast import Cast

        world.relations.clear(Relation.GRABBED_BY, who, eid, "escaped")
        # "You can shift 1 square as part of the escape." Part of it, so it
        # costs nothing further and happens before anything answers the
        # attempt -- a row that slides the creature that got away must find
        # it where the escape left it.
        Cast(world=world, me=eid, ref="escape").shift(1)
    world.bus.emit(Escaped(actor=eid, holder=who, skill=picked, success=won))
    return won
