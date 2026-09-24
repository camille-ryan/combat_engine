"""Events, and the bus that runs them.

Everything the engine does is an event, because 4e triggers off everything.
An event passes through three beats:

1. the **interrupt window** -- listeners run before it happens, against a
   mutable event they may change or cancel;
2. **resolution** -- it happens;
3. the **reaction window** -- listeners run after, responding to what did.

That ordering is the whole reason immediate interrupts and immediate
reactions are different things, so it lives in the bus rather than in each
caller.

The log is the save format. Events are appended when they are *emitted*, not
when they finish, so a trigger that fires mid-event reads in causal order.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import MISSING, asdict, dataclass, field, fields
from typing import Any

from .grid import Square
from .types import ActionType, Condition, DamageType, Defense, Forced, Relation, Window


@dataclass
class Event:
    seq: int = field(default=-1, init=False, kw_only=True)
    depth: int = field(default=0, init=False, kw_only=True)
    cancelled: bool = field(default=False, init=False, kw_only=True)
    reason: str = field(default="", init=False, kw_only=True)

    @property
    def kind(self) -> str:
        return type(self).__name__

    def cancel(self, reason: str = "") -> None:
        self.cancelled = True
        self.reason = reason

    def wire(self) -> dict[str, Any]:
        out = {"seq": self.seq, "kind": self.kind, "depth": self.depth}
        out.update(asdict(self))
        if not self.cancelled:
            out.pop("cancelled", None)
            out.pop("reason", None)
        return out

    def __str__(self) -> str:
        # Fields sitting at their default are noise. `ghost=False` on every
        # turn boundary in a fight is a lot of nothing to read past.
        skip = {"seq", "depth", "cancelled", "reason"}
        bits = []
        for f in fields(self):
            if f.name in skip:
                continue
            value = getattr(self, f.name)
            if f.default is not MISSING and value == f.default:
                continue
            bits.append(f"{f.name}={value!r}")
        tail = f"  CANCELLED({self.reason})" if self.cancelled else ""
        return f"{self.kind}({', '.join(bits)}){tail}"


# -- the clock --------------------------------------------------------------


@dataclass
class RoundStart(Event):
    round: int


@dataclass
class RoundEnd(Event):
    round: int


@dataclass
class TurnStart(Event):
    actor: int
    round: int
    #: The creature is dead and takes no actions. The turn is ticked anyway
    #: so that durations measured against it can reach their end.
    ghost: bool = False


@dataclass
class TurnEnd(Event):
    actor: int
    round: int
    ghost: bool = False


# -- movement ---------------------------------------------------------------


@dataclass
class MoveStart(Event):
    actor: int
    kind_: str  # "walk", "shift", "teleport", "push", "pull", "slide"


@dataclass
class LeaveSquare(Event):
    actor: int
    square: Square


@dataclass
class EnterSquare(Event):
    actor: int
    square: Square


@dataclass
class Moved(Event):
    """One step, with both ends of it.

    `EnterSquare` and `LeaveSquare` are per square of a *footprint* -- a Large
    creature emits four of each for one step -- so neither answers "what did
    this creature just do". This does, and it is what an animation plays.
    """

    actor: int
    from_: Square
    to: Square


@dataclass
class MoveEnd(Event):
    actor: int
    at: Square


@dataclass
class AdjacencyGained(Event):
    """`actor` became adjacent to `other`. Aura entry hangs off this."""

    actor: int
    other: int


@dataclass
class AdjacencyLost(Event):
    """`actor` stopped being adjacent to `other`. So do opportunity attacks."""

    actor: int
    other: int


@dataclass
class ForcedMove(Event):
    """Somebody is being pushed, pulled or slid.

    Cancellable: a creature that cannot be moved refuses it here. `power` is
    the row doing the shoving, so "cannot be pushed by a melee or ranged
    attack" can tell one from a burst.
    """

    source: int
    target: int
    how: Forced
    squares: int
    power: str = ""


@dataclass
class OpportunityWindow(Event):
    """`actor` may take an opportunity action against `provoker`.

    The engine opens the window and never decides what goes in it -- a
    controller (a player, or whatever plays the monsters) subscribes and
    answers. Opened while the provoker is still in the square it is leaving,
    because an opportunity attack interrupts the move.
    """

    actor: int
    provoker: int
    why: str


# -- using a power ----------------------------------------------------------


@dataclass
class PowerUsed(Event):
    actor: int
    power: str
    targets: list[int]


@dataclass
class AttackDeclared(Event):
    attacker: int
    target: int
    power: str
    vs: Defense


@dataclass
class AttackRolled(Event):
    attacker: int
    target: int
    power: str
    vs: Defense
    natural: int
    bonus: int
    total: int
    defence: int
    advantage: bool


@dataclass
class Hit(Event):
    attacker: int
    target: int
    power: str
    critical: bool


@dataclass
class Miss(Event):
    attacker: int
    target: int
    power: str


# -- what happens to a creature ---------------------------------------------


@dataclass
class DamageRolled(Event):
    source: int
    target: int
    amount: int
    dtype: DamageType
    detail: str


@dataclass
class DamageApplied(Event):
    """Damage that actually came off hit points.

    `detail` is what dealt it -- a power ref where one did, or a short note
    like "coup de grace". A trigger reading "when an enemy damages you with
    a melee attack" needs it to find the reach, and had nothing to read.
    """

    source: int
    target: int
    amount: int
    dtype: DamageType
    absorbed: int
    hp: int


@dataclass
class Healed(Event):
    source: int
    target: int
    amount: int
    hp: int


@dataclass
class SurgeSpent(Event):
    """A healing surge left somebody's pool.

    Emitted from every place that decrements one, which is the only way a
    row reading "when a creature spends a healing surge in this aura" can
    ever see it happen -- three separate sites were decrementing silently.
    """

    actor: int
    left: int


@dataclass
class TempHP(Event):
    source: int
    target: int
    amount: int


@dataclass
class Bloodied(Event):
    actor: int


@dataclass
class Dropped(Event):
    """Went to 0 hit points or below -- dying, or dead outright.

    `dead` says which. Emitted for both because every printed row that
    reads it says "drops to 0 hit points or fewer", and a minion is always
    the second kind.
    """

    actor: int
    dead: bool = False


@dataclass
class Died(Event):
    actor: int


@dataclass
class ConditionApplied(Event):
    source: int
    target: int
    condition: Condition
    duration: str


@dataclass
class ConditionEnded(Event):
    target: int
    condition: Condition
    why: str


@dataclass
class RelationSet(Event):
    kind_: Relation
    source: int
    target: int


@dataclass
class RelationCleared(Event):
    kind_: Relation
    source: int
    target: int
    why: str


@dataclass
class ActionSpent(Event):
    """A creature used up an action. `Encounter.spend` is the one door.

    Several rows read "whenever an enemy takes a standard or a move action",
    and nothing announced one: `PowerUsed` misses a plain walk and counts a
    move-action power twice.
    """

    actor: int
    cost: ActionType


@dataclass
class SavingThrow(Event):
    actor: int
    against: str
    natural: int
    bonus: int
    saved: bool


@dataclass
class EffectExpired(Event):
    actor: int
    what: str
    why: str


# -- areas ------------------------------------------------------------------


@dataclass
class ZoneCreated(Event):
    zone: int
    owner: int
    squares: list[Square]
    label: str


@dataclass
class ZoneEnded(Event):
    zone: int
    why: str


@dataclass
class ZoneEntered(Event):
    zone: int
    actor: int


@dataclass
class ZoneExited(Event):
    zone: int
    actor: int


@dataclass
class Note(Event):
    """Engine commentary. Carries no rules meaning; it makes logs readable."""

    text: str


# -- the bus ----------------------------------------------------------------

Listener = Callable[[Any], None]


@dataclass
class Sub:
    id: int
    etype: type[Event]
    fn: Listener
    window: Window
    once: bool
    owner: int | None
    #: Runs after every ordinary listener in the same window. Expiry uses
    #: it: `Effects` subscribes when the world is built, so it was always
    #: first, and a watch hung on "the end of its next turn" was torn down
    #: before its own listener was ever reached.
    late: bool = False


class Bus:
    """The event bus.

    **Two kinds of cancellation, and the difference has cost four bugs.**

    For some events, cancelling works by itself: `_run` stops the rest of
    the window, so an earlier listener refusing the thing prevents the later
    listeners that would have done it. `OpportunityWindow` is the example --
    nothing happens unless a responder acts, so silencing the responders is
    the whole of it, and the emitter is right to ignore the return.

    For the rest, the *emitter* does the work after announcing it, and
    cancelling means nothing unless the emitter reads the answer back.
    `ForcedMove`, `AttackDeclared`, `AttackRolled` and `MoveStart` were all
    of this second kind and all four ignored it, so each looked like a hook
    and was decoration. If you emit an event and then act on it yourself,
    read the return.

    The same applies to fields a listener is invited to change: read them
    back off the event rather than from the local you passed in.
    """

    def __init__(self) -> None:
        self.log: list[Event] = []
        self._subs: list[Sub] = []
        self._next_sub = 0
        self._depth = 0

    # -- subscription --------------------------------------------------------

    def on(
        self,
        etype: type[Event],
        fn: Listener,
        *,
        window: Window = Window.AFTER,
        once: bool = False,
        owner: int | None = None,
        late: bool = False,
    ) -> Sub:
        """Watch `etype`. The returned handle is what a duration cancels with.

        Subscriptions keep insertion order, which is what makes two runs of
        the same seed produce the same log.
        """
        self._next_sub += 1
        sub = Sub(self._next_sub, etype, fn, window, once, owner, late)
        self._subs.append(sub)
        return sub

    def off(self, sub: Sub) -> None:
        if sub in self._subs:
            self._subs.remove(sub)

    def off_owner(self, owner: int) -> None:
        self._subs = [s for s in self._subs if s.owner != owner]

    # -- dispatch ------------------------------------------------------------

    def emit[E: Event](self, ev: E, resolve: Callable[[E], None] | None = None) -> E:
        ev.seq = len(self.log)
        ev.depth = self._depth
        self.log.append(ev)

        self._depth += 1
        try:
            self._run(ev, Window.BEFORE)
            if not ev.cancelled and resolve is not None:
                resolve(ev)
            if not ev.cancelled:
                self._run(ev, Window.AFTER)
        finally:
            self._depth -= 1
        return ev

    def _run(self, ev: Event, window: Window) -> None:
        # Copy: a listener may subscribe or unsubscribe while this runs, and
        # an interrupt that cancels stops the rest of its own window.
        ordered = [s for s in self._subs if not s.late] + [s for s in self._subs if s.late]
        for sub in ordered:
            if sub.window is not window or not isinstance(ev, sub.etype):
                continue
            if sub not in self._subs:
                continue  # removed by an earlier listener in this same window
            if sub.once:
                self.off(sub)
            sub.fn(ev)
            if ev.cancelled:
                return

    # -- reading it back -----------------------------------------------------

    def since(self, cursor: int) -> list[Event]:
        return self.log[cursor:]

    def render(self, cursor: int = 0) -> str:
        return "\n".join(f"{'  ' * e.depth}{e}" for e in self.log[cursor:])
