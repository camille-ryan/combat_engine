"""One encounter, held open across HTTP requests.

The interesting problem here is that a power can ask a question halfway
through resolving. "One ally within 5 squares gains a bonus" -- which ally?
The engine asks through `world.decide`, which is an ordinary synchronous
call, and the answer has to come from a browser several seconds later.

`Turnstile` is the answer. The action runs on a worker thread; when it needs
a choice it parks on a queue and the request thread returns with `pending`
set. The player's answer goes back down the queue and the action carries on
from exactly where it stopped -- no replaying, no rollback, no partial state
to undo.

Only one action is ever in flight per session, so nothing races, and the
worker is the only thread that touches the world or the dice. Replay stays
exact.
"""

from __future__ import annotations

import queue
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from combat_engine.content import chargen, loader
from combat_engine.engine import (
    Action,
    Bus,
    Encounter,
    Grid,
    Ident,
    LinearPolicy,
    Rng,
    Team,
    World,
    legal,
    perform,
    take_turn,
)
from combat_engine.engine.events import OpportunityWindow
from combat_engine.engine.query import alive
from combat_engine.engine.scaling import PRESETS

from .wire import Wire

PARTY = [
    ("fighter", ["p997", "p992", "p1000", "p289", "p1429"]),
    ("cleric", ["p841", "p889", "p1455", "p891", "p913"]),
    ("rogue", ["p704", "p970", "p1382", "p163"]),
    ("wizard", ["p1167", "p1166", "p463", "p159", "p185"]),
]


@dataclass
class Question:
    kind: str
    chooser: int
    prompt: str
    options: list[Any]


class Turnstile:
    """Runs one action on a worker thread, stopping when it needs an answer."""

    def __init__(self) -> None:
        self._answers: queue.Queue[int] = queue.Queue(maxsize=1)
        self._events: queue.Queue[tuple[str, Any]] = queue.Queue(maxsize=1)
        self._thread: threading.Thread | None = None
        self.question: Question | None = None
        self.error: BaseException | None = None

    @property
    def busy(self) -> bool:
        return self.question is not None

    def run(self, fn: Callable[[], None]) -> None:
        """Start `fn`. Returns once it finishes or parks on a question."""
        if self._thread is not None and self._thread.is_alive():
            raise RuntimeError("an action is already in flight")

        def body() -> None:
            try:
                fn()
            except BaseException as exc:
                self.error = exc
            self._events.put(("done", None))

        self.error = None
        self._thread = threading.Thread(target=body, daemon=True)
        self._thread.start()
        self._pump()

    def answer(self, index: int) -> None:
        """Hand back a choice and let the action carry on."""
        if self.question is None:
            return
        self.question = None
        self._answers.put(index)
        self._pump()

    def _pump(self) -> None:
        kind, payload = self._events.get()
        self.question = payload if kind == "ask" else None
        if self.error is not None:
            err, self.error = self.error, None
            raise err

    # -- what the engine calls ----------------------------------------------

    def decide(self, actor: int, kind: str, options: list[Any], prompt: str) -> Any:
        """Called on the worker thread, from inside a power body."""
        if len(options) == 1:
            return options[0]
        self._events.put(("ask", Question(kind, actor, prompt, list(options))))
        index = self._answers.get()
        return options[max(0, min(index, len(options) - 1))]


@dataclass
class Session:
    id: str
    world: World
    encounter: Encounter
    wire: Wire
    policy: LinearPolicy
    seed: int
    level: int
    scaling: str
    gate: Turnstile = field(default_factory=Turnstile)

    # -- building -----------------------------------------------------------

    @classmethod
    def create(
        cls,
        *,
        seed: int,
        level: int = 1,
        scaling: str = "full",
        pcs: list[str] | None = None,
        enemies: list[str] | None = None,
    ) -> Session:
        world = World(Grid(16, 12), Rng(seed), Bus())
        world.scaling = PRESETS.get(scaling, PRESETS["full"])

        wanted = pcs or [cls_ for cls_, _ in PARTY]
        loadouts = dict(PARTY)
        for i, name in enumerate(wanted):
            key = name.strip().lower()
            chargen.spawn(
                world,
                chargen.Character(key, level, list(loadouts.get(key, []))),
                (2, 3 + i * 2),
            )

        pool = enemies or _opposition(level)
        if not pool:
            raise ValueError("no monster is fully written yet")
        for i in range(4):
            loader.spawn(world, pool[i % len(pool)], (12, 3 + i * 2), team=Team.ENEMY)

        _tag(world)
        encounter = Encounter(world)
        policy = LinearPolicy()
        session = cls(
            id=uuid.uuid4().hex[:12],
            world=world,
            encounter=encounter,
            wire=Wire.of(world),
            policy=policy,
            seed=seed,
            level=level,
            scaling=scaling,
        )
        session._install()
        encounter.start()
        session._run_monsters()
        return session

    def _install(self) -> None:
        """Characters ask the player; monsters ask the policy."""
        from combat_engine.engine import Side

        def decide(actor: int, kind: str, options: list[Any], prompt: str) -> Any:
            side = self.world.get(actor, Side)
            if side and side.team is Team.PC:
                return self.gate.decide(actor, kind, options, prompt)
            return self.policy.decide(self.world, actor, kind, options, prompt)

        self.world.decider = decide

        def on_window(ev: OpportunityWindow) -> None:
            # An opportunity attack is taken by whoever is provoked, on either
            # side, and it interrupts a move already in progress. Asking a
            # human here would mean parking a question inside somebody else's
            # action, so for now the policy answers for both sides.
            choice = self.policy.react(self.world, self.encounter, ev.actor, ev)
            if choice is not None:
                perform(self.world, self.encounter, ev.actor, choice)

        self.world.bus.on(OpportunityWindow, on_window)

    # -- playing ------------------------------------------------------------

    @property
    def current(self) -> int | None:
        return self.world.turn

    @property
    def awaiting(self) -> bool:
        """Is it a character's turn, with the player owed a decision?"""
        from combat_engine.engine import Side

        if self.gate.busy:
            return True
        actor = self.current
        if actor is None or self.encounter.finished:
            return False
        side = self.world.get(actor, Side)
        return bool(side and side.team is Team.PC)

    def options(self) -> list[Action]:
        actor = self.current
        if actor is None or self.encounter.finished or self.gate.busy:
            return []
        return legal(self.world, self.encounter, actor)

    def act(self, index: int) -> None:
        """Take the option at `index`, pausing if the power asks something."""
        actor = self.current
        if actor is None or self.gate.busy:
            return
        options = self.options()
        if not 0 <= index < len(options):
            raise IndexError(f"no option {index}")
        choice = options[index]

        def body() -> None:
            perform(self.world, self.encounter, actor, choice)

        self.gate.run(body)
        if not self.gate.busy:
            self._after_action(choice)

    def answer(self, index: int) -> None:
        self.gate.answer(index)
        if not self.gate.busy:
            self._after_action(None)

    # -- playing by pointing at squares --------------------------------------

    def walk_to(self, square: tuple[int, int], *, shift: bool = False) -> None:
        """Move to a square the player clicked.

        Resolved to one of the same options `legal` produced, so clicking the
        board and picking from the list are the same act and cannot disagree
        about what is allowed.
        """
        wanted = "shift" if shift else "move"
        for i, option in enumerate(self.options()):
            if option.kind == wanted and option.dest == square:
                self.act(i)
                return
        raise LookupError(
            f"cannot {wanted} to {square}"
            + (" -- out of reach" if not shift else " -- a shift is one square")
        )

    def aim(self, power_index: int, square: tuple[int, int]) -> None:
        """Use the `power_index`th entry of the roster, aimed at a square.

        The square means whichever of two things the power needs: the origin
        of a burst or a blast, or whoever is standing there.
        """
        from combat_engine.engine.query import squares as occupies

        refs = self.roster_refs()
        if not 0 <= power_index < len(refs):
            raise LookupError(f"no power {power_index}")
        ref = refs[power_index]

        standing = [
            c
            for c in self.world.entities
            if self.world.has(c, Ident) and square in occupies(self.world, c)
        ]
        for i, option in enumerate(self.options()):
            if option.kind != "power" or option.ref != ref:
                continue
            if option.origin == square or any(t in standing for t in option.targets):
                self.act(i)
                return
        raise LookupError(f"{ref} cannot be aimed at {square}")

    def roster_refs(self) -> list[str]:
        """The refs behind the roster, in the order the page is shown them.

        The page sends back a position in that list, so both ends have to
        derive it the same way -- hence one function, called by both.
        """
        from combat_engine.engine import Powers, get

        actor = self.current
        if actor is None:
            return []
        known = self.world.get(actor, Powers)
        if known is None:
            return []
        return [ref for ref in known.all if get(ref) is not None]

    def _after_action(self, choice: Action | None) -> None:
        """Advance past anything the player does not control."""
        if choice is not None and choice.kind == "end":
            self.encounter.advance()
        self._run_monsters()

    def _run_monsters(self) -> None:
        """Play every non-character turn until it is a character's move again."""
        from combat_engine.engine import Side

        for _ in range(200):
            if self.encounter.finished:
                return
            actor = self.current
            if actor is None:
                self.encounter.advance()
                continue
            side = self.world.get(actor, Side)
            if side and side.team is Team.PC and alive(self.world, actor):
                return
            take_turn(self.world, self.encounter, actor, self.policy)
            self.encounter.advance()

    def end_turn(self) -> None:
        self.encounter.advance()
        self._run_monsters()

    # -- reading ------------------------------------------------------------

    @property
    def status(self) -> str:
        if self.encounter.finished:
            return "finished"
        return "active" if self.encounter.started else "setup"

    def since(self, cursor: int) -> list:
        return self.world.bus.log[cursor:]


def _opposition(level: int) -> list[str]:
    for candidate in range(min(max(level, 1), 13), 0, -1):
        pool = loader.pick(candidate)
        if pool:
            return pool
    return []


def _tag(world: World) -> None:
    seen: dict[str, int] = {}
    for _eid, ident in world.each(Ident):
        seen[ident.ref] = seen.get(ident.ref, 0) + 1
        if seen[ident.ref] > 1 or ident.ref.startswith("m"):
            ident.tag = str(seen[ident.ref])


SESSIONS: dict[str, Session] = {}
