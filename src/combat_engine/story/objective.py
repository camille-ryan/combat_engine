"""What a fight is *for*, other than killing everything on the other side.

A combat scene could say what ground it was fought on (`Scene.terrain`), how
hard it was meant to be (`Scene.difficulty`) and who was in it
(`Scene.foes`). It could not say what the party was trying to achieve, so
`run._fight` had exactly one win condition -- `Encounter.winner is Team.PC`,
which is *"the one side with a living combatant left"* -- and one loss
condition, which was its complement.

Camille's call, 2026-10-29, after reading another system's encounter-objective
rules:

> I'd like these encounter objectives to be represented in encounter design in
> this project. [...] you don't need to do a 1:1 conversion. This is more of a
> generic DM advice thing.

So this is the concept rather than the numbers: **an objective is a stated
goal, a stated way to fail it, and a step along the difficulty ladder**. No
imported currency and no imported formulas. `plans/20261029-encounter-
objectives.md` records the translations that were made and the four objectives
that are deferred because they want a thing on the board that is not a
creature.

## The dividing line for what is here

Whether the board can already answer the question. These six read counts,
rounds and squares -- all of which exist -- so none of them needs a new
component or a new action. The ones left out need a destructible object, a
carryable object, a ward, or an action a character can take mid-fight that is
not an attack; see the plan.

## Why the position is a word and not coordinates

`hold` needs an area. A module author converting a published
adventure cannot know this engine's board is 16x12 (#974), and a scene that
named squares would be wrong the moment the board changed size. So a position
is one of `POSITIONS`, resolved against the real grid at fielding time -- the
same shape `Scene.terrain` already uses, a closed vocabulary the loader
refuses outside of.

The party spawns in the west (`chargen.spawn` places it at `(2, 3 + i*2)`), so
`hold` defaults to the party's own end of the floor. That is the only reason
the default is what it is, and a scene may say otherwise.

## What was dropped on the way, and why it is not here

**An `assault` objective -- take and hold a position -- was built and then
removed.** It could not be met on these boards and the measurement is the
argument: every arm reported `0 of N consecutive rounds`, including one where
the party was standing in the area having killed everything. Two reasons,
and they compound. `Encounter.finished` ends the fight the moment a side is
gone, so there is at most **one** round boundary at which the party holds a
cleared area and never the three a duration asks for. And a round cap as a
resolve condition cuts the fight short before the area can be taken at all,
so the same field was doing duty as a deadline *and* as a hold counter.

What it wants is a fight that continues around the party -- reinforcements
arriving while the position is held, which is #962. Filed rather than
shipped: an objective that cannot be met is worse than one that does not
exist.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from combat_engine.engine.components import Position, Side, Team
from combat_engine.engine.ecs import World
from combat_engine.engine.events import RoundEnd
from combat_engine.engine.query import alive, combatants

#: The objectives a scene may state.
#:
#: `defeat_all` is what every fight has always done and is named rather than
#: left implicit, so that "this scene has no objective" and "this scene's
#: objective is to win the fight" are different statements. The first means
#: the old code path runs untouched; the second means the watcher runs and
#: agrees with it. Keeping both is what makes the no-objective control in
#: `drivers.py` worth anything.
KINDS = (
    "defeat_all",
    "diminish",
    "defeat_foe",
    "survive",
    "hold",
)

#: Where on the floor an objective's area is. Resolved against the grid by
#: `area`, never written as squares by a module.
POSITIONS = ("west", "east", "north", "south", "centre")

#: How wide a band a position word covers, in squares. Four, which is what
#: `content.terrain.dress` already treats as a starting band -- it leaves
#: `_band(0, 4, height)` and the mirror of it clear of scatter for the same
#: reason this uses it: that is where a side stands.
BAND = 4

#: What share of its starting numbers the opposition has to be cut to for
#: `diminish`, when a scene does not say. Half, which is the plainest reading
#: of "their numbers are broken" and is a figure a module can override.
SHARE = 0.5

#: How many rounds `survive` and `hold` run for when a scene does not say.
ROUNDS = 3


@dataclass(frozen=True)
class Objective:
    """What the party is trying to do, and what counts as failing.

    `kind` is from `KINDS`. The rest are parameters that only some kinds read,
    and each kind's docstring in `Watch` says which.

    **`harder` and `easier` are the difficulty step**, and they are declared by
    the module rather than derived from the kind. The source this came from
    attaches a modifier to each objective and then qualifies every one of them
    -- a thing guarded by a powerful monster is harder, one with an escape
    route is easier -- so the modifier is a property of *this* encounter and
    not of the kind. `cast_list` applies it before it spends the budget.
    """

    kind: str = "defeat_all"
    #: For `defeat_foe`: which creatures have to go down.
    #:
    #: **The module's own word for the creature, not a database ref.** An
    #: author converting a published adventure writes what the page calls the
    #: thing -- that is what every other field here takes, and `cast_list`
    #: resolves it -- and cannot possibly know that the draw will answer with
    #: `m258`. The first version of this matched refs only, which made the
    #: objective unusable from a module file while looking finished.
    #:
    #: A ref is accepted too, for a hand-built `Objective` in a driver or a
    #: probe, and `Watch._matches` takes either.
    foes: tuple[str, ...] = ()
    #: For `diminish`: the share of its starting count the opposition must be
    #: cut to.
    share: float = SHARE
    #: For `survive` and `hold`: how many rounds.
    rounds: int = ROUNDS
    #: For `hold`: which part of the floor.
    position: str = ""
    #: For `hold`: how many enemies may reach the position before the party
    #: has failed. Defaults to the party's own size at fielding time, which is
    #: the figure the source uses and the only one that scales with the table.
    leaks: int = 0
    #: One step along `module.DIFFICULTY`. Both false is no change; both true
    #: is refused at load.
    harder: bool = False
    easier: bool = False
    #: What the module calls this objective, for the line the player reads.
    #: Flavour only -- never matched on.
    says: str = ""


def area(world: World, position: str) -> frozenset[tuple[int, int]]:
    """The squares a position word covers on *this* board.

    Empty for a word that is not in `POSITIONS`, which cannot happen through
    the loader and can through a hand-built `Objective`. Empty rather than
    raising, because an objective that watches nowhere is reported by the
    verdict as unmet rather than taking a fight down with it.
    """
    width, height = world.grid.width, world.grid.height
    if position == "west":
        xs, ys = range(0, min(BAND, width)), range(height)
    elif position == "east":
        xs, ys = range(max(0, width - BAND), width), range(height)
    elif position == "north":
        xs, ys = range(width), range(0, min(BAND, height))
    elif position == "south":
        xs, ys = range(width), range(max(0, height - BAND), height)
    elif position == "centre":
        xs = range(max(0, width // 2 - BAND // 2), min(width, width // 2 + BAND // 2))
        ys = range(max(0, height // 2 - BAND // 2), min(height, height // 2 + BAND // 2))
    else:
        return frozenset()
    return frozenset((x, y) for x in xs for y in ys)


def _side(world: World, eid: int) -> Team | None:
    side = world.get(eid, Side)
    return side.team if side else None


def _standing(world: World, team: Team) -> list[int]:
    """Living combatants on a side.

    `combatants` rather than `creatures` deliberately: it is the narrower
    question -- *"who takes turns and decides the fight"* -- and it already
    subtracts companions, barriers and attackable conjurations. An objective
    counting heads wants the same set the win condition counts.
    """
    return [
        eid for eid in combatants(world)
        if alive(world, eid) and _side(world, eid) is team
    ]


def _inside(world: World, eid: int, squares: frozenset[tuple[int, int]]) -> bool:
    pos = world.get(eid, Position)
    return bool(pos) and bool(pos.squares & squares)


@dataclass
class Verdict:
    """What the objective says happened."""

    met: bool = False
    #: Met without a single character going down. The grade the source keeps
    #: a second reward tier for; here it is recorded and **not yet paid for**,
    #: because the thing that would pay is the XP award and that does not
    #: exist (#967). Recording it now means the award has something to read
    #: when it lands rather than needing this measured again.
    clean: bool = False
    #: One sentence, for the line the player reads.
    why: str = ""


@dataclass
class Watch:
    """Follows a fight and decides whether its objective was met.

    Subscribes to `RoundEnd` rather than polling from the turn loop, so that
    what it counts is the board at a round boundary and not the board halfway
    through somebody's turn. That matters for `hold`, where a creature shoved
    into the area and shoved back out again within one round has not broken
    the line.

    **`resolved` is what lets a fight stop early.** A fight today runs until a
    side is wiped or `MAX_ROUNDS`; an objective with a duration has to end the
    moment it is decided, which is the loop's third condition in `_fight`.
    """

    world: World
    objective: Objective
    #: Living enemies when the watcher was attached, which is after the cast
    #: is spawned and before `Encounter.start()`.
    #:
    #: **Counted at `attach`, and the first draft counted it at the first
    #: `RoundEnd` instead.** The docstring for that version argued it was
    #: better -- a trap or a surprise round that kills somebody first would be
    #: "counted the way the fight actually went" -- and it is simply wrong for
    #: a denominator: anything that died during round one left the starting
    #: number, so `diminish` asked the party to halve an already-reduced cast.
    #: Measured on a probe, it reported *"2 of 4 are down"* for a fight that
    #: began with six. An objective quietly easier than it was written is the
    #: exact failure mode this component's own notes warn about.
    began_with: int = 0
    #: Enemies that have been inside the area at any round boundary. A set, so
    #: that one creature walking in and out does not count twice -- "fewer
    #: enemies who get through, the better" is about bodies, not crossings.
    reached: set[int] = field(default_factory=set)
    #: Rounds that have ended.
    rounds: int = 0
    #: A character has been down at some point. Read once at the end rather
    #: than per round, so a character who dropped and was healed still costs
    #: the clean grade -- which is the honest reading of "nobody went down".
    anyone_down: bool = False
    resolved: bool = False
    _verdict: Verdict | None = None

    def attach(self) -> None:
        """Start watching. Call before `Encounter.start()`.

        Takes the starting count here rather than on the first round
        boundary -- see `began_with`.
        """
        self.began_with = len(_standing(self.world, Team.ENEMY))
        self.world.bus.on(RoundEnd, self._round)

    # -- per round ----------------------------------------------------------

    def _round(self, ev: RoundEnd) -> None:
        world, aim = self.world, self.objective
        self.rounds = ev.round
        foes = _standing(world, Team.ENEMY)
        # **Anybody, not everybody.** The first draft of this asked whether
        # the PC side had a living combatant left, which is a wipe rather than
        # a casualty -- so the clean grade survived a character dropping and
        # only failed on a total party kill, where `_judge`'s first branch has
        # already said the objective was missed. One character down is what
        # costs the grade, and `_standing` filters on `alive` so it is the
        # wrong set to ask: the dead are not in it.
        if not all(alive(world, eid) for eid in combatants(world)
                   if _side(world, eid) is Team.PC):
            self.anyone_down = True

        if aim.kind == "hold":
            squares = area(world, aim.position)
            self.reached |= {eid for eid in foes if _inside(world, eid, squares)}

        self._decide(foes)

    def _decide(self, foes: list[int]) -> None:
        """Set `resolved` when the fight no longer has anything to settle."""
        aim = self.objective
        ours = _standing(self.world, Team.PC)
        if not ours:
            self.resolved = True
            return
        if aim.kind in ("survive", "hold") and self.rounds >= aim.rounds:
            self.resolved = True
        elif aim.kind == "diminish" and self.began_with:
            if len(foes) <= self.began_with * aim.share:
                self.resolved = True
        elif aim.kind == "defeat_foe" and not self._left_standing():
            self.resolved = True

    #: `ref -> the module's own word for it`, from the cast list.
    #:
    #: **Set when the watcher is built, not when it judges**, and the first
    #: version got that wrong with a visible cost: `_decide` calls
    #: `_left_standing` at every round boundary, so an empty map matched
    #: nobody, `defeat_foe` resolved as satisfied at the **end of round one**,
    #: and the fight stopped four rounds early. The verdict was still right --
    #: by then the map was filled -- so the objective reported *"still
    #: standing"* on a fight it had itself cut short. A watcher that decides
    #: during the fight has to know everything it needs before the fight
    #: starts.
    named: dict[str, str] = field(default_factory=dict)

    def _matches(self, ref: str) -> bool:
        """Does this fielded creature answer to one of the designated words?

        Either the module's own word for it or its database ref, folded for
        case and surrounding space. A module says "the dragonborn mercenary";
        a driver building an `Objective` by hand has the ref and nothing else.
        """
        wanted = {w.strip().lower() for w in self.objective.foes}
        return ref.lower() in wanted or self.named.get(ref, "").lower() in wanted

    def _left_standing(self) -> list[str]:
        """Designated creatures still up. Empty means `defeat_foe` is done."""
        from combat_engine.engine.components import Ident

        out = []
        for eid in _standing(self.world, Team.ENEMY):
            ident = self.world.get(eid, Ident)
            if ident and self._matches(ident.ref):
                out.append(self.named.get(ident.ref) or ident.ref)
        return out

    # -- the answer ---------------------------------------------------------

    def verdict(self, *, winner: Team | None, fielded: tuple[str, ...] = (),
                named: dict[str, str] | None = None) -> Verdict:
        """Judge the fight. `winner` is `Encounter.winner`, for `defeat_all`.

        `named` maps each fielded ref to the module's own word for it, which
        is what `defeat_foe` is written against -- see `Objective.foes`.

        Idempotent: `_fight` reads this once, but a driver reading it twice
        should get the same answer rather than a second count of a board that
        has stopped moving.
        """
        if self._verdict is None:
            if named:
                self.named = dict(named)
            self._verdict = self._judge(winner, fielded)
        return self._verdict

    def _judge(self, winner: Team | None, fielded: tuple[str, ...]) -> Verdict:
        aim, world = self.objective, self.world
        ours = _standing(world, Team.PC)
        foes = _standing(world, Team.ENEMY)

        if not ours:
            return Verdict(False, False, "the party was defeated")

        if aim.kind == "defeat_all":
            met = winner is Team.PC
            return Verdict(met, met and not self.anyone_down,
                           "the opposition is down" if met
                           else "the opposition is still standing")

        if aim.kind == "diminish":
            if not self.began_with:
                return Verdict(False, False, "nothing was fielded to diminish")
            want = self.began_with * aim.share
            met = len(foes) <= want
            return Verdict(
                met, met and not self.anyone_down,
                f"{self.began_with - len(foes)} of {self.began_with} are down, "
                f"and the objective wanted {self.began_with - want:.0f}",
            )

        if aim.kind == "defeat_foe":
            known = {w.lower() for w in fielded}
            known |= {w.lower() for w in self.named.values() if w}
            missing = [w for w in aim.foes if w.strip().lower() not in known]
            if missing or not aim.foes:
                # **Not a success.** A designation nobody fielded would
                # otherwise satisfy itself, which is the quiet failure this
                # whole mechanism is supposed to avoid: an objective that
                # reports met because it was never possible to fail.
                named = ", ".join(missing) or "nobody"
                return Verdict(False, False,
                               f"the objective names {named}, which this "
                               "scene did not field")
            left = self._left_standing()
            met = not left
            return Verdict(met, met and not self.anyone_down,
                           "the named foe is down" if met
                           else f"still standing: {', '.join(sorted(left))}")

        if aim.kind == "survive":
            # **Or the opposition ran out, which is not a failure to
            # survive.** The first draft was `rounds >= aim.rounds` alone and
            # a party that wiped the cast in round 4 of a five-round hold was
            # told it had failed. You cannot fail to outlast a fight you have
            # already won, and on these boards winning early is the *common*
            # case because `Encounter.finished` ends the loop the moment a
            # side is gone.
            met = self.rounds >= aim.rounds or not foes
            return Verdict(met, met and not self.anyone_down,
                           "the opposition was gone before the "
                           "time was up" if met and not foes
                           else f"the party held out {self.rounds} of "
                                f"{aim.rounds} rounds")

        if aim.kind == "hold":
            allowed = aim.leaks
            through = len(self.reached)
            # The duration **or** an empty field, for the reason `survive`
            # gives. The leak count still binds either way: breaking through
            # and then dying is not holding the line.
            lasted = self.rounds >= aim.rounds or not foes
            met = lasted and through < allowed
            how = ("the line was clear before the time was up"
                   if lasted and not foes
                   else f"the line held {self.rounds} of {aim.rounds} rounds")
            return Verdict(
                met, met and not self.anyone_down,
                f"{how}, and {through} of an allowed {allowed} reached "
                f"the {aim.position}",
            )

        # An unknown kind cannot reach here through the loader, which refuses
        # one. Unmet rather than raising, for the reason `area` gives.
        return Verdict(False, False, f"unknown objective {aim.kind!r}")


def watcher(world: World, objective: Objective | None,
            party_size: int, named: dict[str, str] | None = None) -> Watch | None:
    """Build and attach a watcher, or `None` for a scene with no objective.

    `None` is the whole of the backward compatibility: `_fight` keeps its old
    `winner is Team.PC` line when there is no watcher, so a module written
    before this existed fields, plays and is judged bit for bit as it was.
    `drivers.no_objective` is the control for that.

    `leaks` is filled in here rather than at load, because the figure the
    source uses is the size of the table and a module does not know it.

    `named` maps each fielded ref to the module's own word for it and must be
    supplied **now** rather than at judgement -- see `Watch.named`.
    """
    if objective is None:
        return None
    if objective.kind == "hold" and not objective.leaks:
        from dataclasses import replace

        objective = replace(objective, leaks=max(1, party_size))
    watch = Watch(world=world, objective=objective, named=dict(named or {}))
    watch.attach()
    return watch
