"""Delaying and disabling a trap: the state, not the action that reaches it.

The printed rule, DMG p84, and the last sentence is the one that decides the
shape:

> *"Most traps can be disabled or delayed with the Thievery skill… When a
> character delays a trap, the trap stops functioning for a period of time
> (until the end of the character's next turn, with a 50% chance each round
> that it reactivates after that). Disabling a trap takes the trap out of
> commission until someone makes the effort to repair or reset it. **While
> it's delayed or disabled, the trap effectively isn't there.**"*

So this is **one suppression with two lifetimes**, not two behaviours. A
delayed trap and a disabled trap are equally absent while they last; the only
difference is whether the state ever lifts on its own. That is why there is a
single reader, `suppressed`, and why nothing here asks which of the two put
the trap to sleep.

`#955` scoped the engine half as needing to *"say which of the three
consequences it touches"* -- `Trap` having no `Health`, being outside
`query.creatures`, and taking no turn. This touches **none** of them: a
suppressed trap still has no hit points, still is not a creature, and still
holds no initiative slot. It simply does not fire. Being attackable is the
separate question that issue names, and it is not answered here.

**The Thievery action is deliberately absent.** `#955` holds it on `#1016`'s
policy weighting, and a menu entry nothing scores is a different piece of
work. What is here is the state 44 printed blocks describe, reachable by a
caller -- so the action, when it lands, has something to set.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .components import Trap
from .events import Note

if TYPE_CHECKING:
    from .ecs import World

#: What the reactivation roll has to beat on a d20. The page says "a 50%
#: chance each round", and a d20 at 11+ is that -- expressed on a die the
#: `Rng` already logs and that `Rng.loaded` can pin, rather than on a coin
#: flip no instrument can steer. A `die(2)` would have been the obvious
#: spelling and would have made both branches of this rule unassertable.
REACTIVATES_ON = 11


def delay(world: World, eid: int, by: int) -> bool:
    """Stop a trap functioning until the end of `by`'s next turn.

    After that anchor it gets a 50% chance a round to come back -- see
    `suppressed`, which rolls it lazily rather than on a hook.

    The anchor is **the round after this one**, which is where "the end of
    the character's next turn" lands for a creature that acts once a round.
    Holding the turn index instead would be more precise and less true: a
    delayer who is dazed, dead or skipped never reaches that turn, and the
    trap would stay off for the rest of the fight on a technicality.
    """
    trap = world.get(eid, Trap)
    if trap is None or trap.disabled:
        return False
    trap.delayed_until = world.round + 1
    trap.delay_check = -1
    world.bus.emit(Note(text=f"{trap.ref} is delayed by {by}"))
    return True


def disable(world: World, eid: int) -> bool:
    """Take a trap out of commission until somebody repairs or resets it.

    No expiry, because the page gives it none: *"until someone makes the
    effort to repair or reset it"*, and nothing in a fight does that.
    """
    trap = world.get(eid, Trap)
    if trap is None:
        return False
    trap.disabled = True
    trap.delayed_until = None
    world.bus.emit(Note(text=f"{trap.ref} is disabled"))
    return True


def suppressed(world: World, eid: int) -> bool:
    """Is this trap currently not there? The one reader.

    **Lazy, and decided once a round.** The reactivation could have been a
    `RoundEnd` listener; reading it here instead means there is no install
    step to forget and no ordering question about whether the roll happens
    before or after a creature's move. It is the same shape as
    `movement.swims`, and for the same reason: the answer has to be stable
    within the round it is asked in, or a trap would be absent when the menu
    was drawn and present when the square was entered.

    A creature that is not a trap is not suppressed, so a caller may ask
    about anything.
    """
    trap = world.get(eid, Trap)
    if trap is None:
        return False
    if trap.disabled:
        return True
    if trap.delayed_until is None:
        return False
    if world.round <= trap.delayed_until:
        return True
    # Past the anchor: 50% a round. Rolled at most once per round, and the
    # answer stands for the rest of it -- `delay_check` is what remembers
    # that this round has already been decided.
    if trap.delay_check != world.round:
        trap.delay_check = world.round
        if world.rng.d20().total >= REACTIVATES_ON:
            trap.delayed_until = None
            world.bus.emit(Note(text=f"{trap.ref} reactivates"))
            return False
    return True
