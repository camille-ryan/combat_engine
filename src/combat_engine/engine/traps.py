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

from .components import Health, Trap
from .events import Note, TrapSprung
from .resolve import attack
from .types import DamageType, Defense

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


#: Which defence a trap's printed word names. `"ref"` is the common one and
#: the fallback: 4 in 5 printed blocks roll against Reflex, which is what
#: `content.terrain`'s own table said before this moved.
_DEFENCES = {
    "ac": Defense.AC,
    "fort": Defense.FORT,
    "fortitude": Defense.FORT,
    "ref": Defense.REF,
    "reflex": Defense.REF,
    "will": Defense.WILL,
}


def fire(
    world: World, eid: int, victim: int, *, by: int = 0, why: str = "stepped",
    attack_bonus: int | None = None, damage: str = "",
) -> bool:
    """Set a trap off at one creature. True if the attack hit.

    **The firing was a closure in `content/terrain.py` and nothing outside
    could reach it**, which is why a trap could only ever go off the two
    ways that closure was wired for: a plate stepped on, and an ongoing
    trap's own turn. *"You trigger the trap"* -- PHB p189, a Thievery check
    failed by 5 or more -- had nowhere to go, and `p11600` was refused in
    play for want of the moment.

    Here rather than there because the numbers are printed **data** and the
    firing is a **rule**: `Trap.attack`, `Trap.defence` and `Trap.damage`
    carry the page, and this module already owns the suppression state that
    decides whether a trap is there at all.

    **A suppressed trap fires nothing**, whatever asks -- DMG p84's *"while
    it's delayed or disabled, the trap effectively isn't there"* -- so a row
    cannot spring a disabled trap and neither can a fumbled disarm. That is
    one test here instead of one at each caller.

    `TrapSprung` is announced **before** the attack, so a row answering it
    as an immediate interrupt acts while the blow is still coming. `why`
    says how it came to fire and `by` who caused it, which are different
    questions from `victim`: the character who fumbles a disarm sets it off
    and the trap may then attack somebody else.

    `attack_bonus` and `damage` override the stored numbers, for the caller
    that has a printed fallback of its own. `arm` passes them for a block
    that prints neither, because an invented number must not be stored on
    the component as though the book had printed it (#981).
    """
    from .query import alive

    trap = world.get(eid, Trap)
    if trap is None or suppressed(world, eid):
        return False
    if world.get(victim, Health) is None or not alive(world, victim):
        return False
    bonus = trap.attack if attack_bonus is None else attack_bonus
    dice = damage or trap.damage
    world.bus.emit(TrapSprung(trap=eid, victim=victim, by=by, why=why))
    # Through `resolve.attack` with the trap itself as the attacker, so
    # `query.is_trap(ctx["attacker"])` is true for the rows that ask and a
    # bonus hung on the trap by a power is read like anybody else's.
    if not attack(world, eid, victim, bonus, _DEFENCES.get(trap.defence, Defense.REF),
                  power=trap.ref):
        return False
    if dice:
        world.damage(eid, victim, world.rng.roll(dice).total,
                     DamageType.UNTYPED, detail=trap.ref)
    return True
