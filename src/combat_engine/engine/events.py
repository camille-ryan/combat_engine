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

    def wire(self) -> dict[str, Any]:
        out = {"seq": self.seq, "kind": self.kind, "depth": self.depth}
        out.update(asdict(self))
        for f in fields(self):
            # `asdict` recurses, so a carried event -- `PowerUsed.trigger`
            # -- would inline a whole second event into the save format.
            # It is already in the log at its own seq; the pointer is the
            # useful half and it keeps the schema flat.
            value = getattr(self, f.name)
            if isinstance(value, Event):
                out[f.name] = f"{value.kind}#{value.seq}"
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
            if isinstance(value, Event):
                # An event carried by another event -- `PowerUsed.trigger`
                # -- is already in the log in full at its own seq, and
                # spelling it out again nests a whole repr inside a line.
                value = f"{value.kind}#{value.seq}"
                bits.append(f"{f.name}={value}")
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
class Decision(Event):
    """An event somebody may refuse. Most events are not one.

    Thirty-odd of the classes below are notifications: they say a thing
    happened and there is nothing to argue about. Five are proposals, and
    only those carry `cancel`.

    The distinction used to live on the base class, so every event
    advertised that it could be refused and a `cancel()` on any of the other
    thirty-three compiled, ran, logged nothing and did nothing. Putting the
    method here makes that an AttributeError where it is written instead of
    silence where it is read.

    **Refusing is only half of it.** A proposal is refused by a listener and
    honoured by the *emitter*, and four separate bugs came from an emitter
    that announced something and then went ahead from its own local
    variables. If you emit one of these and then do the work yourself, pass
    the work as `emit`'s second argument: the callback is handed the event,
    so reading the agreed answer is the natural thing to write and the stale
    local is not in scope.
    """

    def cancel(self, reason: str = "") -> None:
        self.cancelled = True
        self.reason = reason


@dataclass
class MoveStart(Decision):
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

    **`kind_` rides as a plain attribute**, set on every emission: walk,
    shift, teleport, push, pull, slide. `MoveEnd` carries the word and no
    squares, `Moved` carried the squares and no word, so "one ally adjacent
    to you *before the teleport*" could be asked of neither -- the only
    event that knew where the creature came from did not know how it got
    there. A plain attribute rather than a field for the reason
    `AttackRolled.result` is one: it would otherwise reach the wire and
    every replay fixture, none of which is a change in how a fight
    resolves.
    """

    actor: int
    from_: Square
    to: Square


@dataclass
class MoveEnd(Event):
    actor: int
    at: Square
    #: walk, shift, teleport, forced. A row answering "an adjacent enemy
    #: shifts" has to wait for the move to finish -- `MoveStart` fires
    #: before the first step, so reacting to it puts the responder where
    #: nothing has moved yet -- and this said nothing about what kind of
    #: move had just happened.
    kind_: str = ""


@dataclass
class AdjacencyGained(Event):
    """`actor` became adjacent to `other`. Aura entry hangs off this.

    Emitted twice, mirrored, so either creature can answer it. `mover` is
    the one that actually moved -- without it, "when an enemy moves adjacent
    to it" also fired when the creature closed the gap itself, which is not
    the printed sentence and is true half the time.
    """

    actor: int
    other: int
    mover: int = 0


@dataclass
class AdjacencyLost(Event):
    """`actor` stopped being adjacent to `other`. So do opportunity attacks.

    **Emitted twice, mirrored, so either creature can answer it** --
    `movement.py:209-210`, exactly as `AdjacencyGained` above. Said here because
    it was not: a reader who took this docstring at its word and `AdjacencyGained`'s
    at its word would conclude the two differ, and filter one of them wrong.

    `mover` is the one that actually moved, the same field and the same
    reason as `AdjacencyGained`: without it "when an enemy moves away from
    it" also fires when the creature itself walks off, which is not the
    printed sentence and is true about half the time.

    **It arrived late, and the asymmetry was the point of #368.** For as long
    as one of the pair carried `mover` and the other did not, "enters or
    leaves my reach" could not be written once -- a row had to watch two
    events and filter only one of them, and `closed_on_me` had no partner to
    pair with. Defaulting to `0` keeps every existing watcher reading the
    same, since `0` is no creature.
    """

    actor: int
    other: int
    mover: int = 0


@dataclass
class ForcedMove(Decision):
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
class Fell(Decision):
    """A creature is falling, announced **before** it lands.

    Cancellable, because "you can attempt a saving throw to avoid falling
    farther" is a printed row and catching yourself has to be able to stop
    the drop. The two fields below are read back after the window closes,
    the way `Bus` insists: an interrupt that softens a fall does not stop
    it, it changes what landing costs.

    `squares` is how far, which is what the damage is worked out from.
    `soften` is how much of that damage a listener has taken off, and
    `prone` is whether the landing still knocks the creature down -- "takes
    no damage from the fall, and consequently does not fall prone" is one
    printed sentence and both halves live here.
    """

    actor: int
    squares: int
    from_: int = 0
    soften: int = 0
    prone: bool = True


@dataclass
class OpportunityWindow(Decision):
    """`actor` may take an opportunity action against `provoker`.

    The engine opens the window and never decides what goes in it -- a
    controller (a player, or whatever plays the monsters) subscribes and
    answers. Opened while the provoker is still in the square it is leaving,
    because an opportunity attack interrupts the move.
    """

    actor: int
    provoker: int
    why: str
    #: How the provoker moved, when movement is what opened this. `walk`,
    #: `shift`, `charge` -- `movement.step`'s own `kind`. Empty when the window
    #: was opened by something that is not a move.
    #:
    #: **`why` could not answer it.** It reads `"moved away"` for a walk, a charge
    #: and a flight alike, so "your movement **during the charge** does not
    #: provoke" had nothing to test -- while `step` had both facts in scope on the
    #: line that emits this. Four rows wanted them. #301.
    #:
    #: **Named `kind_` because a field called `kind` shadows `Event.kind`**, the
    #: property that returns the class name -- and this event was the only one in the
    #: file that got it wrong. `MoveStart`, `MoveEnd`, `RelationSet` and
    #: `RelationCleared` all carry `kind_` for exactly this reason.
    #:
    #: What the shadowing did, all of it silent: `str()` rendered the event as
    #: `run(actor=1, ...)` and `wire()["kind"]` returned `"run"`, so the class name was
    #: gone from every serialised form. The committed fixtures held 31 of these under
    #: the names `walk`, `""`, `charge` and `run` and **none** under
    #: `OpportunityWindow`; `replay.py coverage` reported the class as never exercised
    #: while it fired 31 times; `render.event_dto` shipped `kind: ""` where the page
    #: expects `"opportunity"`; and `narrate` branches on the class name, so the
    #: opportunity-attack sentence was never once emitted.
    #:
    #: The **ctx key stays `"kind"`** -- see `Cast.does_not_provoke`. That dict is a
    #: separate contract and content rows read `ctx.get("kind")`.
    kind_: str = ""
    #: And how it travelled: `walk`, `fly`, `swim`, `burrow`, resolved by
    #: `movement.mode_of`. "Your **flying** does not provoke" is one row.
    mode: str = ""


# -- using a power ----------------------------------------------------------


@dataclass
class PowerUsed(Event):
    """A power has started. `trigger` is what it was used *in answer to*.

    `dsl.use` has always been handed the event a reaction is answering --
    the body reads it as `c.trigger` -- and threw it away on the emit, so
    "when an ally's feature fires, do X to the thing that set it off" had
    nothing to read. `targets` is not that thing and is not a stand-in
    for it: an immediate action is routinely `NO_TARGET`, or aims itself
    at a creature off its own trigger, so the two name different
    creatures exactly when the distinction matters.

    None for an ordinary use -- a power nobody provoked.

    `granted_by` and `granted_via` are the other half of the same
    omission, and the bigger one. A great many cards let one creature
    hand another a swing -- a warlord's command, a defender's
    punishment, a charge somebody else is sent on -- and the swing was
    announced as `mba` like any other use, with nothing saying whose
    doing it was. So "when an ally makes a basic attack you granted" and
    "an attack granted by your Combat Challenge" both had nothing to
    read, and twenty-seven rows were waiting on it.

    `granted_by` is the creature that handed it over and `granted_via`
    the ref of the row that did. **Both are needed and neither implies
    the other**: a defender's punishment is a self-grant, so the granter
    alone cannot tell it from an ordinary swing, and a warlord grants
    through a dozen different rows, so the ref alone cannot say whose.
    -1 and "" mean nobody granted this -- an ordinary use.
    """

    actor: int
    power: str
    targets: list[int]
    trigger: Any = None
    granted_by: int = -1
    granted_via: str = ""


@dataclass
class ItemPowerUsed(Event):
    """A magic item's own power fired, and which item it belongs to.

    Its own class rather than a field on `PowerUsed`, which would have
    been free to add -- `Event.wire()` is `asdict`. But `triggers.arm`
    subscribes per event class, so a field would wake every listener of
    every power use to ask a question that is almost always no. Three of
    the artificer's four class-page features hang on this, and they are
    the only readers there will ever be many of.
    """

    actor: int
    power: str
    item: str


@dataclass
class PowerResolved(Event):
    """A power has **finished**. `PowerUsed` says one has started.

    `dsl.use` announces the start before running the body, which is the
    right moment for "when you use a power" and the wrong one for
    everything that reads a consequence. Nothing said a use was over, so
    a row repeating another resolved its repeat *before* the first one's
    effects, and a row wanting the whole set of attack rolls a use made
    had only the last.

    `rolls` is every `AttackResult` the use produced, in order -- which
    is the thing "reroll every attack roll you made with this power" has
    to be given.

    `trigger` is the same field `PowerUsed` carries and for the same
    reason; a row that has to see the consequence *and* name what
    provoked it would otherwise have to watch both events and pair them.
    `granted_by`/`granted_via` are carried here for the same reason
    again -- "if your ally hits with the attack this exploit provides"
    reads the outcome, not the declaration.
    """

    actor: int
    power: str
    targets: list[int]
    rolls: list[Any] = field(default_factory=list)
    trigger: Any = None
    granted_by: int = -1
    granted_via: str = ""


@dataclass
class AttackDeclared(Decision):
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
class Hit(Decision):
    attacker: int
    target: int
    power: str
    critical: bool


@dataclass
class Miss(Decision):
    attacker: int
    target: int
    power: str


# -- what happens to a creature ---------------------------------------------


@dataclass
class DamageRolled(Decision):
    source: int
    target: int
    amount: int
    dtype: DamageType
    detail: str
    #: The **whole** type of the blow, for a blow that is more than one --
    #: "1d8 lightning and thunder damage" is one roll of two types, which
    #: resistance reads as a unit. Empty is the ordinary case and means
    #: "just `dtype`", so every reader that asks `ev.dtype is
    #: DamageType.FIRE` goes on answering for the blows it always did.
    #:
    #: **Writable, and the way a listener retypes a blow to a pair.** A
    #: listener setting `dtype` alone still *overrides* the whole type,
    #: which is what "this weapon deals fire instead" means; set this to
    #: say "and", not "instead".
    dtypes: tuple[DamageType, ...] = ()

    def types(self) -> tuple[DamageType, ...]:
        """Every type this blow is, whether it is one or several."""
        return tuple(self.dtypes) if self.dtypes else (self.dtype,)


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
    #: **Temporary hit points spent on this blow, and nothing else.** Not
    #: resistance, which comes off further up and is `resisted` below. A
    #: row asking "did my resistance eat some of this" off `absorbed` is
    #: false in every fight that has no temporary hit points in it, which
    #: is nearly all of them, and true for the wrong reason in the rest.
    absorbed: int
    hp: int
    #: The docstring above has promised this since the class was written and
    #: the field was never there. `triggers._power_of` reads it, so
    #: `by_melee`, `by_ranged` and `by_keyword` were all silently false on
    #: this event -- and one content row had already been routed off `Hit`
    #: to work around it without anyone noticing why.
    detail: str = ""
    #: The whole type of the blow, as on `DamageRolled`. Empty means "just
    #: `dtype`", which is every blow that is of one type.
    dtypes: tuple[DamageType, ...] = ()
    #: **Points the target's resistance and immunity took off**, before
    #: any of it reached hit points. The gap between the blow that was
    #: rolled and the blow that landed, which is what "if your resistance
    #: reduces the damage" reads and what `absorbed` was being misread
    #: for. Zero is the ordinary blow, so it stays out of the log line.
    resisted: int = 0

    def types(self) -> tuple[DamageType, ...]:
        """Every type this blow was, whether it was one or several."""
        return tuple(self.dtypes) if self.dtypes else (self.dtype,)


@dataclass
class Healed(Decision):
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

    **Not a `Decision` yet, and #386 is why.** Making it refusable is two
    lines and unblocks nothing on its own: the verb that would read it,
    `c.no_surges`, has 14 rows waiting, and two of those are empty-bodied
    traits needing a watcher rather than a call. Landing the refusal without
    them turns `todo.py` red for a symbol that exists and is unused.
    """

    actor: int
    left: int


@dataclass
class SecondWind(Event):
    """A creature took its second wind.

    `Cast.second_wind` is the one implementation and it announced nothing,
    so "when you use your second wind" and "when an ally within 5 squares
    uses his or her second wind" had no moment to hang from at all. Fifty-
    nine rows were waiting on it. `SurgeSpent` is not a substitute: a surge
    is spent by a dozen leader rows that are not a second wind, and the
    healing one is not the whole of what a second wind is.

    `healed` is the hit points it is about to restore -- the surge value,
    clamped by what is actually missing, because a creature two hit points
    off full regains two. "That ally regains the hit points instead of
    you" is the sentence that has to be handed the number.

    `cost` is the action it was taken as. Normally a standard; a printed
    feat turns on its being a **minor**, which is why this is a field and
    not an assumption.

    **Announced before the surge is spent**, not after the healing, and
    that is deliberate: three printed rows read "when you use your second
    wind *while you are bloodied*", and by the time the hit points are
    back that is no longer true. It also puts the log in causal order --
    SecondWind, SurgeSpent, Healed, EffectApplied.
    """

    actor: int
    healed: int
    cost: ActionType = ActionType.STANDARD


@dataclass
class TotalDefence(Event):
    """A creature took the total defence action.

    The sibling of `SecondWind` above and filed for the same reason: eight
    rows print "when you take the total defense action" and `Cast
    .total_defence` announced nothing, so the sentence had no moment to hang
    from. Four of the eight name **both** actions in one line -- "when you
    take the total defense or second wind action" -- which is what makes the
    pair worth keeping symmetrical.

    `amount` is the bonus actually laid, because the verb takes an
    `amount=` and a row reading "you add the enhancement bonus of this
    weapon *instead*" needs to know what it is replacing.
    """

    actor: int
    amount: int


@dataclass
class TempHP(Event):
    source: int
    target: int
    amount: int


@dataclass
class Bloodied(Event):
    """Crossed the half-hit-point line this blow.

    `source` is whoever struck it, and may be None when nothing did --
    ongoing damage that ticks a creature past the line. Same shape and
    same reason as `Dropped.source`: "whenever you bloody an enemy" is a
    common printed trigger and, without it, `by_me` was false on this
    event and nineteen rows had nowhere to ask.
    """

    actor: int
    source: int | None = None


@dataclass
class Summoned(Event):
    """A creature arrived on the board because a power put it there.

    `World.spawn` emits nothing, so a row whose whole printed Effect is
    "you summon X" left no trace in the log at all -- `audit.py` could not
    see it and reported four correct rows SILENT. It also makes "when a
    creature is summoned" writable, which nothing could say before.
    """

    actor: int
    summon: int
    ref: str = ""


@dataclass
class Dropped(Event):
    """Went to 0 hit points or below -- dying, or dead outright.

    `dead` says which. Emitted for both because every printed row that
    reads it says "drops to 0 hit points or fewer", and a minion is always
    the second kind.

    `source` is who struck the killing blow, and may be None when nothing
    did -- ongoing damage, a failed death save. Without it "whenever you
    reduce an enemy to 0 hit points" could not be declared at all: two
    waves in a row routed that line off `DamageApplied` instead, which
    carries a source but announces before the creature is down, and a third
    left its row out. `by_me` works on this now.

    `critical` is whether the blow that did it was a critical hit, for the
    two rows printing "reduced to 0 hit points, **but not by a critical
    hit**" -- a clause that could not be asked at all. #428.

    Smaller than it looked: `crit` is already in scope at the one site that
    emits this, so it is a parameter rather than a new fact to thread.
    Defaults to `False`, which is also the honest answer for the deaths that
    no blow caused -- ongoing damage, a failed death save -- where there is
    no attack to have been critical.

    ## This is not a `Decision`, and a card that wants one declares elsewhere

    **"When you are reduced to 0 hit points (immediate interrupt): the
    triggering attack misses" names this event and must not be declared on
    it.** `Dropped` is an announcement of something already true: hit points
    are at zero by the time it is emitted and the resolve path has moved on,
    so `c.cancel()` answers False and the row does nothing -- quietly, because
    `cancel` deliberately does not raise for an event that cannot be refused.

    Making it refusable is not a widening like `source` and `critical` were.
    It would have to mean one of two things and both are worse than the gap:

    * **move the announcement earlier**, which reorders every death throe and
      every "when an enemy drops" rider in the tree, for one sentence; or
    * **let cancel mean "restore it"**, which is not what cancel means
      anywhere else in this engine -- everywhere else it prevents a thing that
      has not happened yet.

    **Declare on `DamageRolled` instead.** It is a `Decision`, it carries the
    amount, and it fires while the hit points are still there -- so "would be
    reduced to 0" is a predicate on the number rather than a fact about the
    creature. The worked example is `i652p1` in `content/items/waist.py`:
    `on=Trigger(DamageRolled, _would_drop_me, "an attack would drop you")`,
    whose docstring states the reasoning. #445.
    """

    actor: int
    dead: bool = False
    source: int | None = None
    critical: bool = False


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
class Escaped(Event):
    """One attempt to get out of a grab, win or lose.

    Emitted for a failure as well, because "whenever a creature fails an
    escape attempt against you" is printed as often as the other half.
    `holder` is the grabber, so a row about *your* grabs gates on that and
    not on `actor` -- which is the creature struggling.
    """

    actor: int
    holder: int
    skill: str
    success: bool


@dataclass
class InitiativeRolled(Event):
    """A creature's place in the order was decided.

    Announced so a row can answer it -- "make a new initiative check" is a
    printed line and `_roll_initiative` said nothing at all, so there was
    no event to hang it from.
    """

    actor: int
    rolled: int


@dataclass
class EffectApplied(Event):
    """An effect landed on somebody, whatever it carries.

    `ConditionApplied` only fires for effects that impose a *condition*, so
    a save-ends effect carrying nothing but ongoing damage announced
    nothing at all -- and "subject to an effect that a save can end" could
    only be declared on the half of the cases that happen to daze you.
    Named by two waves three levels apart.
    """

    source: int
    target: int
    duration: str
    label: str = ""
    save_ends: bool = False


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
class ActionGranted(Event):
    """A creature was handed an action it had not got. The other half of
    `ActionSpent`, and `Cast.extra_action` is the one door.

    The budget was raised in silence, so a row whose whole printed effect
    is "you can take a move action" left no trace at all -- nothing to
    answer and nothing to show it had worked. An action point announces
    itself with `ActionPointSpent` and emits this too, because the extra
    action is the same thing however it was bought.
    """

    actor: int
    cost: ActionType


@dataclass
class SavingThrow(Decision):
    """A saving throw, announced **before** it is acted on.

    `saved` is read back, so a row printing "the target automatically fails
    the saving throw" or "reroll it" has somewhere to go. It used to be
    emitted and then ignored -- the caller branched on its own local -- and
    the event was decoration.
    """

    actor: int
    against: str
    natural: int
    bonus: int
    saved: bool


@dataclass
class SkillCheck(Decision):
    """A skill check, announced **before** its modifiers are totalled.

    `bonus` is the fixed part -- the ability modifier and half level -- and
    is finished inside the resolve callback, which runs after the interrupt
    window. That ordering is the whole point: "Trigger: you would make an
    Athletics check" is a *free action taken before the roll counts*, and it
    answers by laying a modifier the callback then reads. A listener may
    also add to `bonus` directly.

    `dc` of 0 is a check with no number to beat -- "you make a Heal check
    and the target regains half the result" -- and always succeeds.
    """

    actor: int
    skill: str
    dc: int
    natural: int
    bonus: int
    total: int
    success: bool


@dataclass
class ActionPointSpent(Event):
    """A creature spent an action point and gained an extra action.

    `free` is the point that a row handed out and that does not count
    against the one-per-encounter limit, because two printed rows turn on
    exactly that distinction.
    """

    actor: int
    cost: ActionType
    free: bool = False


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
class ZoneResized(Event):
    """An aura's radius changed in place, on a zone that already exists.

    `Zones.refresh` re-cuts `zone.squares` from `zone.aura` every tick, so
    widening an aura is a one-field mutation and nothing announced it. Two
    rows do exactly that and both sat in `audit.KNOWN_SILENT` with the reason
    written out: "widens its own aura, which emits no event for the audit to
    see". The rows were correct and invisible, not inert. #375.

    Both radii, because "while its aura is smaller than 5" is a printed
    recharge condition and a row reading this wants to know which way it went.
    """

    zone: int
    actor: int
    from_: int
    to: int


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
