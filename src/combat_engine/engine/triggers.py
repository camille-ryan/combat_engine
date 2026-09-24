"""Offering a power when its printed trigger happens.

4e hangs a great deal on immediate actions -- "when an enemy moves adjacent
to you", "when you are hit by a melee attack", "when an ally within 5 squares
drops". Until this existed, `Power.trigger` was a line of prose that nothing
read, so every one of those rows could be written and none could ever fire:
the interface never offered them, because the interface only offers what a
creature can do *on its own turn*, and by definition none of these happen
then.

The whole mechanism is two observations.

**The bus already has the ordering.** An immediate *interrupt* resolves
before the thing that triggered it and may stop it; an immediate *reaction*
resolves after. `Bus.emit` runs `Window.BEFORE`, then the action itself, then
`Window.AFTER`, and a `BEFORE` listener that cancels stops the action. So the
two action types are the two windows, and nothing new had to be invented to
sequence them.

**The budget already exists.** `Encounter.can_spend` has known since it was
written that an immediate action is once per round and an opportunity action
is once per *other creature's* turn. It simply had no callers for either.

What is left is this file: watch the events that some declared row names,
work out who may respond, and ask them.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .components import Powers
from .events import Event
from .query import alive, can_act
from .types import ActionType, Window

if TYPE_CHECKING:
    from .ecs import World
    from .turns import Encounter


def _always(world: World, me: int, ev: Event) -> bool:
    return True


@dataclass(frozen=True)
class Trigger:
    """A printed Trigger line, in a form something can act on.

    `event` is what to watch and `when` is the rest of the sentence. The two
    are separate because the event class is what gets subscribed -- cheap, and
    known at import time -- while the predicate is per-responder and only runs
    for a creature that could actually answer.

    `when` is handed `(world, me, event)`, where `me` is the creature being
    offered the power, not the one that caused the event. "When you are hit"
    and "when an ally is hit" are the same event class and differ only here.

    `text` is the printed line, kept for the power card. It is prose and no
    code reads it; `when` is the authority.
    """

    event: type[Event]
    when: Callable[[World, int, Any], bool] = _always
    text: str = ""


#: Refs currently resolving, keyed by responder. A reaction that emits the
#: event it watches -- a riposte is an attack, and attacks are what it
#: watches -- would otherwise answer itself forever.
_IN_FLIGHT: set[tuple[int, str]] = set()


WINDOW_OF = {
    ActionType.IMMEDIATE_INTERRUPT: Window.BEFORE,
    ActionType.IMMEDIATE_REACTION: Window.AFTER,
    ActionType.OPPORTUNITY: Window.BEFORE,
    ActionType.FREE: Window.AFTER,
}


@dataclass
class Triggers:
    """The dispatcher. One per encounter; owned by it."""

    world: World
    encounter: Encounter
    _subs: list[Any] = field(default_factory=list)

    def arm(self) -> None:
        """Subscribe to every event class any declared row triggers off.

        Done once, from the registry, rather than per creature: the set of
        watched classes is fixed at import time and is small, and a listener
        that walks the creatures is cheaper than a subscription per creature
        per row -- of which a fight would hold several hundred.
        """
        from .dsl import REGISTRY

        watched: dict[type[Event], set[Window]] = {}
        for p in REGISTRY.values():
            if p.on is None:
                continue
            window = WINDOW_OF.get(p.action)
            if window is not None:
                watched.setdefault(p.on.event, set()).add(window)

        for etype, windows in watched.items():
            for window in sorted(windows, key=lambda w: w.name):
                self._subs.append(
                    self.world.bus.on(
                        etype,
                        lambda ev, w=window: self._offer(ev, w),
                        window=window,
                    )
                )

    def disarm(self) -> None:
        for sub in self._subs:
            self.world.bus.off(sub)
        self._subs.clear()

    # -- the offer -----------------------------------------------------------

    def _offer(self, ev: Event, window: Window) -> None:
        """Ask everyone who could answer this event whether they want to.

        Initiative order, so a replay of the same seed offers in the same
        sequence. An interrupt that cancels the event ends the round of
        offers: the thing being responded to is no longer happening.
        """
        for eid in list(self.encounter.order):
            if ev.cancelled:
                return
            if not (alive(self.world, eid) and can_act(self.world, eid)):
                continue
            for ref in self._answers(eid, ev, window):
                self._ask(eid, ref, ev)
                if ev.cancelled:
                    return

    def _answers(self, eid: int, ev: Event, window: Window) -> list[str]:
        """Which of this creature's rows this event triggers, in order."""
        from .dsl import get, usable

        known = self.world.get(eid, Powers)
        if known is None:
            return []
        out = []
        for ref in known.all:
            p = get(ref)
            if p is None or p.on is None:
                continue
            if WINDOW_OF.get(p.action) is not window:
                continue
            if not isinstance(ev, p.on.event):
                continue
            if (eid, ref) in _IN_FLIGHT:
                continue
            if not self.encounter.can_spend(eid, p.action):
                continue
            if not p.on.when(self.world, eid, ev):
                continue
            ok, _why = usable(self.world, eid, p)
            if ok:
                out.append(ref)
        return out

    def _ask(self, eid: int, ref: str, ev: Event) -> None:
        """Offer one power, and use it if it is taken.

        The offer is a real choice -- a printed trigger is permission, not an
        obligation, and several are worth declining to keep the immediate
        action for something better later in the round. With no decider
        installed the first option wins, so taking it comes first: a declared
        reaction that never fired would be the harder bug to see.
        """
        from .dsl import get, use

        p = get(ref)
        if p is None:
            return
        options = [ref, ""]
        if self.world.decide(eid, "trigger", options, p.on.text if p.on else "") != ref:
            return
        if not self.encounter.spend(eid, p.action):
            return

        _IN_FLIGHT.add((eid, ref))
        try:
            use(self.world, eid, ref, trigger=ev)
        finally:
            _IN_FLIGHT.discard((eid, ref))


# -- the predicates rows actually want --------------------------------------
#
# Written once here rather than as a lambda in every row: "when you are hit"
# is the same sentence in forty places, and forty hand-written versions is
# forty chances to read the wrong field off the event.


def targets_me(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "target", None) == me


def by_me(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "attacker", getattr(ev, "source", None)) == me


def about_me(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "actor", None) == me


def not_me(world: World, me: int, ev: Event) -> bool:
    return getattr(ev, "actor", getattr(ev, "attacker", None)) != me


def ally_within(squares: int) -> Callable[[World, int, Event], bool]:
    """An ally -- not you -- within range of whoever the event is about."""
    from .query import distance_between, team

    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "actor", getattr(ev, "target", None))
        if who is None or who == me:
            return False
        if team(world, who) is not team(world, me):
            return False
        return distance_between(world, me, who) <= squares

    return check


def enemy_within(squares: int) -> Callable[[World, int, Event], bool]:
    from .query import distance_between, team

    def check(world: World, me: int, ev: Event) -> bool:
        who = getattr(ev, "actor", getattr(ev, "attacker", None))
        if who is None or who == me:
            return False
        if team(world, who) is team(world, me):
            return False
        return distance_between(world, me, who) <= squares

    return check


def by_melee(world: World, me: int, ev: Event) -> bool:
    """Was the attack that caused this a melee one?

    "Missed by a *melee* attack" is four rows, and the reach is on the power
    rather than the event. `resolve._is_ranged` already does this lookup for
    cover; this is the other half of the same question.
    """
    from .dsl import get

    p = get(getattr(ev, "power", "") or "")
    return p is not None and p.reach.kind in ("melee", "close_burst", "close_blast")


def by_ranged(world: World, me: int, ev: Event) -> bool:
    from .dsl import get

    p = get(getattr(ev, "power", "") or "")
    return p is not None and p.reach.kind in ("ranged", "area_burst")


def leaves_me_out(world: World, me: int, ev: Event) -> bool:
    """Did this attack miss me out entirely?

    What a defender's mark actually asks. An attack is announced once per
    target, so `ev.target != me` only says *this announcement* was not aimed
    at me -- a burst that caught me still passed that test on every other
    target's row, and both marks punished an enemy for an attack that did
    include them. `among` carries the whole target list of the one power
    use, which is the only thing that can answer it.
    """
    return me not in getattr(ev, "among", (getattr(ev, "target", None),))


def cursed_by_me(world: World, me: int, ev: Event) -> bool:
    """Is whoever this event is about under my curse?

    Three warlock pact boons pay out when a cursed enemy drops, and the
    curse is a relation rather than anything on the event.
    """
    from .types import Relation

    who = getattr(ev, "actor", getattr(ev, "target", None))
    return who is not None and world.relations.holds(Relation.CURSED_BY, me, who)


def both(*checks: Callable[[World, int, Event], bool]) -> Callable[[World, int, Event], bool]:
    def check(world: World, me: int, ev: Event) -> bool:
        return all(c(world, me, ev) for c in checks)

    return check
