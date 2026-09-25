"""The barbarian's rage: one at a time, lasting the fight, read by other rows.

A rage is a stance in everything but the printed keyword -- you are in one
rage or another or none, entering one ends the last, and it runs to the end
of the encounter. `c.stance` is exactly that, so `enter` is a thin wrapper
whose only job is to put the word in the label, because two dozen rows print
"Requirement: You must be raging" or "If you are raging" and something has to
be able to answer them.

`held_by` is the other half. Nearly every rage hangs a watcher off itself --
"until the rage ends, whenever you hit ..." -- and a watcher clocked on
`When.STANCE` of its own confuses `Effects.stance_of`, which is what decides
what a later rage replaces. So the watcher is clocked on the encounter and
ended by hand when the stance goes, the arrangement `p1436` settled for the
fighter.
"""

from __future__ import annotations

from combat_engine.engine import Cast, Effect, World

#: The word in a rage stance's label. `raging` matches on it.
RAGE = "rage"


def enter(c: Cast) -> Effect:
    """Enter this row's rage, ending whichever one was running.

    `on=c.me` is not decoration: `c.stance` falls to `c.target` like
    `c.bonus` does, and every rage in the class is printed on a row that
    swings at an enemy first -- so the unqualified call put the rage on the
    creature being hit, `raging()` was false for the barbarian, and every
    "while raging" rider in the class was silently dead.
    """
    return c.stance(on=c.me, label=f"{c.ref} {RAGE}")


def raging(world: World, eid: int) -> bool:
    """"Requirement: You must be raging" -- as a `requires=` gate."""
    stance = world.effects.stance_of(eid)
    return stance is not None and RAGE in stance.label


def in_rage(c: Cast) -> bool:
    """"If you are raging" -- the same question from inside a body."""
    return raging(c.world, c.me)


def held_by(c: Cast, stance: Effect, *watchers: Effect | None) -> None:
    """Take these down when the rage does."""
    for watcher in watchers:
        if watcher is not None:
            stance.on_end.append(
                lambda w=watcher: c.world.effects.end(w, "the rage ended")
            )
