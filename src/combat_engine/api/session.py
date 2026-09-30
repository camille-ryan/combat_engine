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

from combat_engine import chargen
from combat_engine.content import loader, terrain
from combat_engine.engine import (
    Action,
    Bus,
    DoctrinePolicy,
    Encounter,
    Grid,
    Ident,
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
from combat_engine.transcript import Transcript

from .wire import Wire

#: Which four classes take the field. What each of them *knows* is dealt by
#: `chargen.spawn` from the registry -- this file used to keep its own list
#: of ids, `scripts/fight.py` kept another, and both had gone stale: the
#: party the server dealt out carried no class features at all, so its rogue
#: had no extra damage and its fighter could not mark.
PARTY = ["fighter", "cleric", "rogue", "wizard"]


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


#: Which kind of option a clicked square resolves to, by the mode the page
#: asked for. `run` was unreachable by pointing until it was listed here: the
#: engine has offered `run` options for a while and the old reader tested only
#: for "shift", so the one surface most people play could not run.
#:
#: "walk" is the word the page has always sent for a plain move.
MODES = {"move": "move", "walk": "move", "shift": "shift", "run": "run"}


@dataclass
class Session:
    id: str
    world: World
    encounter: Encounter
    wire: Wire
    policy: DoctrinePolicy
    seed: int
    level: int
    scaling: str
    gate: Turnstile = field(default_factory=Turnstile)
    #: Every event of this fight, written to `logs/<id>.jsonl` as it happens.
    transcript: Transcript | None = None
    #: True while  is running somebody else's turn, so a
    #: character's triggered row asks the policy rather than parking a
    #: question the player has no way to answer.
    _theirs: bool = False
    #: True while the encounter is being set up, for the same reason and
    #: with a worse deadlock: `encounter.start()` arms every trait, and a
    #: trait that asks its owner something is asking before the session
    #: exists to be asked. The worker blocks on an answer that cannot be
    #: sent until `create` returns, and `create` cannot return until the
    #: worker unblocks, so the whole request hangs rather than erroring.
    #: A build choice made at arming time is a setup fact, and the policy
    #: is the right answerer for it.
    _setting_up: bool = False

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
        terrain.dress(world, seed, level=level)
        world.scaling = PRESETS.get(scaling, PRESETS["full"])

        for i, name in enumerate(pcs or PARTY):
            key = name.strip().lower()
            chargen.spawn(world, chargen.Character(key, level), (2, 3 + i * 2))

        pool = enemies or _opposition(level)
        if not pool:
            raise ValueError("no monster is fully written yet")
        fielded = [pool[i % len(pool)] for i in range(4)]
        for i, ref in enumerate(fielded):
            loader.spawn(world, ref, (12, 3 + i * 2), team=Team.ENEMY)

        _tag(world)
        encounter = Encounter(world)
        policy = DoctrinePolicy()
        ident = uuid.uuid4().hex[:12]
        session = cls(
            id=ident,
            world=world,
            encounter=encounter,
            wire=Wire.of(world),
            policy=policy,
            seed=seed,
            level=level,
            scaling=scaling,
        )
        session._install()
        # Attached before the fight starts, so initiative and the traits
        # armed at the top of round one are in the file like everything
        # else. A transcript that begins on round two is a transcript of
        # the wrong fight.
        session.transcript = Transcript.open(
            ident,
            {
                "seed": seed,
                "level": level,
                "scaling": scaling,
                "pcs": list(pcs or PARTY),
                "enemies": fielded,
            },
        )
        session.transcript.attach(world)
        session._setting_up = True
        try:
            encounter.start()
        finally:
            session._setting_up = False
        session._run_monsters()
        return session

    def _install(self) -> None:
        """Characters ask the player; monsters ask the policy."""
        from combat_engine.engine import Side

        def decide(actor: int, kind: str, options: list[Any], prompt: str) -> Any:
            side = self.world.get(actor, Side)
            # `theirs` is the same rule `on_window` below already states:
            # a question parked inside somebody else's action cannot be
            # answered, because the answer arrives on a request that cannot
            # be made until this one returns. `_run_monsters` runs the
            # monsters' turns inside the player's `act`, so a character's
            # triggered row offered during a monster's move deadlocked the
            # whole session -- the worker blocked on `_answers.get()` and
            # the HTTP call never came back. The first row in the tree to
            # be offered that way hung the app at round 3.
            if side and side.team is Team.PC and not (self._theirs or self._setting_up):
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

    def walk_to(self, square: tuple[int, int], *, mode: str = "move") -> None:
        """Move to a square the player clicked.

        Resolved to one of the same options `legal` produced, so clicking the
        board and picking from the list are the same act and cannot disagree
        about what is allowed.
        """
        wanted = MODES.get(mode)
        if wanted is None:
            raise LookupError(f"no way of moving called {mode!r}")
        for i, option in enumerate(self.options()):
            if option.kind == wanted and option.dest == square:
                self.act(i)
                return
        raise LookupError(
            f"cannot {wanted} to {square}"
            + (" -- a shift is one square" if wanted == "shift" else " -- out of reach")
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
        mine = [
            (i, o)
            for i, o in enumerate(self.options())
            if o.kind == "power" and o.ref == ref
        ]
        # **An aimed power is aimed at the square, and only at the square.**
        # The two tests used to be an `or`, so a click anywhere on a large
        # creature also matched the first option that merely *caught* it --
        # and the option list is in origin order, so a zone dropped on the
        # creature's anchor square instead of where the player clicked. The
        # bigger the creature, the further the spell landed from the point
        # of it. The target test is for a power with no origin at all,
        # where clicking a creature is how you name it.
        aimed = [(i, o) for i, o in mine if o.origin is not None]
        if aimed:
            for i, option in aimed:
                if option.origin == square:
                    self.act(i)
                    return
        else:
            for i, option in mine:
                if any(t in standing for t in option.targets):
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
        # Traits are left out. A trait is not something a player picks --
        # it is armed when the fight starts and is simply true -- so putting
        # it in the list of things you can use offered five rogue class
        # features as choices, each showing a raw ref because a feature has
        # no printed name to look up. They belong in `ActorDTO.traits`.
        from combat_engine.engine.types import ActionType

        return [
            ref
            for ref in known.all
            if (p := get(ref)) is not None and p.action is not ActionType.NONE
        ]

    def _after_action(self, choice: Action | None) -> None:
        """Advance past anything the player does not control."""
        try:
            if choice is not None and choice.kind == "end":
                self._advance()
            self._run_monsters()
        finally:
            self._write_log()

    def _advance(self) -> None:
        """Step the turn with the same guard `_run_monsters` uses.

        **The advance is not the player's move either.** Ending a turn
        emits `TurnEnd` and then `TurnStart`, and a character's triggered
        row offered from there reaches `gate.decide` on *this* thread --
        which blocks on an answer that can only arrive on a request this
        one is holding open. `_run_monsters` states that rule and wraps
        its loop; these two call sites ran the advance just outside it.

        Nothing offered it until races were dealt, because no raceless
        character in the fixtures carried a row that answers a turn
        boundary. The hole was there the whole time.
        """
        self._theirs = True
        try:
            self.encounter.advance()
        finally:
            self._theirs = False

    def _run_monsters(self) -> None:
        """Play every non-character turn until it is a character's move again."""
        from combat_engine.engine import Side

        # The flag covers the whole loop, not just `take_turn`. Advancing
        # the turn emits `TurnEnd`, a character's watch answers it, and the
        # first row in the tree to ask a question from there deadlocked the
        # session exactly as a mid-turn interrupt did -- the guard had to
        # be around everything that runs while it is not the player's move,
        # which is the entire body of this method.
        self._theirs = True
        try:
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
        finally:
            self._theirs = False

    def end_turn(self) -> None:
        try:
            self._advance()
            self._run_monsters()
        finally:
            self._write_log()

    def _write_log(self) -> None:
        """Put the transcript on disk, whatever just happened.

        Flushed when the board comes back to the player, which is the moment
        it is worth having: whatever looked wrong is in the file before they
        can ask about it.

        In a `finally`, and on this path too. `end_turn` did not flush at
        all, so a monster turn that raised left every event of that turn --
        the ones that would say what went wrong -- unwritten in memory. A
        fight wedged mid-monster-turn and the log stopped at the player's
        last action, which is exactly the shape that is hardest to diagnose.
        """
        if self.transcript is not None:
            self.transcript.flush()

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
