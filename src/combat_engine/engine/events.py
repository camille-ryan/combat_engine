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
from .types import (
    ActionType,
    Condition,
    DamageType,
    Defense,
    Forced,
    Keyword,
    Relation,
    Window,
)


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

    **`stretched_` rides the same way**, and is how many squares beyond the
    printed distance were actually *spent*. `c.extend_every("shift", 1)` adds
    to a move's **budget** and `World.decide` need not spend it, so "did the
    creature take the extra square" was not observable -- and `f2459` prints
    "you can shift 1 additional square. **If you do so**, you grant combat
    advantage", where the cost falls due only if the square was taken. Laying
    the benefit without the cost would have made that feat strictly better
    than the one on the page, which is why it stayed refused rather than
    taking `dropped=`. #572.

    Spent, not granted: the difference between the square the creature ended
    on and the distance its card printed. `0` on every ordinary move, which
    is every move nothing has lengthened.

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

    # **Neither is declarable here, and both forms were tried.** A plain
    # annotation in a dataclass *is* a field, which is the one thing the
    # docstring above rules out -- `Event.wire` is `asdict`, so it would
    # reach the page and all seven replay fixtures. A `TYPE_CHECKING` block
    # does not help: `ty` evaluates the class body statically and then
    # demands both as constructor arguments. A `ClassVar` is worse again --
    # it keeps them off `fields`, and then refuses the assignment that sets
    # them.
    #
    # So the reads and writes carry a `ty` suppression for an unresolved
    # attribute, the same one `drivers.py` uses in five places. Not a
    # loosening: `types.py --bless` *refuses* to raise a baseline entry on
    # purpose, so the growth was never blessable, and the alternative was a
    # field this docstring exists to argue against.


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
class Cushioned(Event):
    """A fall was softened, and by which row.

    `Cast.cushion` writes `Fell.soften` on the event it is answering and
    said nothing, so **four rows whose whole content is that write looked
    inert**: `f1979`, `i840p1`, `p1213` and `p13143` each call it and
    nothing else, and all four reported silent the moment #755 taught the
    harness to make a creature fall. The same shape `WeaponChanged` and
    `WeaponHeld` were added for, and `audit.py` states the rule in its own
    words -- *"the real fix is an event, not an excuse"*.

    `amount` is what came off and `all_of_it` is the printed "takes no
    damage from the fall, and consequently does not fall prone" -- one
    sentence whose two halves are `soften` and `prone`, so a listener can
    tell a partial reduction from a negated fall without re-reading the
    `Fell` it answered. #756.
    """

    actor: int
    by: str
    amount: int
    all_of_it: bool = False


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
    #: separate contract and content rows read `ctx.get("move_kind")`.
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
    #: The weapon the blow came through, by ref -- an attribute, not a
    #: field. See `Bloodied.weapon`.
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
    #: The row that did the healing, as a ref. Ten rows wanted it and none
    #: could ask: a rider on "the hit points regained by your cleric
    #: healing powers", "each character healed by one of your encounter or
    #: daily powers", or one named row, has to tell *which* heal it is
    #: looking at, and this event said only who healed whom.
    #:
    #: `""` when nothing named it -- a surge spent on its own, a rest. A
    #: gate on this must therefore test the ref it wants rather than
    #: treating empty as a wildcard, or a short rest reads as every power
    #: at once.
    power: str = ""


@dataclass
class SurgeSpent(Decision):
    """A healing surge leaving somebody's pool, and refusable.

    Emitted from every place that decrements one, which is the only way a
    row reading "when a creature spends a healing surge in this aura" can
    ever see it happen -- three separate sites were decrementing silently.

    **A `Decision`, so "the target cannot spend healing surges" is
    writable.** `c.no_surges` is the verb and 14 rows waited on it.
    `c.no_healing` was the wrong tool for every one of them: it cancels
    *all* healing, which is a strictly stronger line than any of these
    cards print -- a creature that cannot surge can still be healed by a
    cleric.

    `resolve.spend_surge` is the **only** place `Health.surges` is
    decremented, confirmed by walking the tree, so one refusal reaches all
    three routes a surge is spent by: the second wind, a leader's power
    granting one, and a monster paying its own.

    ## The four extra fields, and why they land together

    Promoting this for `cancel` alone would have left five marker groups
    naming fields it still did not carry:

        SurgeSpent.source       i1807x1, p16053
        SurgeSpent.granted_by   m3764a2
        SurgeSpent.power        f3770
        SurgeSpent.healed       f3688

    So the event is done once rather than widened four more times. Each is
    `0`/`""` when nothing supplied it, which is the honest answer for a
    surge nobody granted and no row caused -- `spend_surge` is reachable
    from a bare `c.spend_surge()` with no context to pass.

    `healed` is what the surge paid out, which is **not** always a quarter
    of maximum: `c.spend_surge` is "spend one and gain nothing", and 80-odd
    rows use it that way. Zero there is the printed answer, not a missing
    one. #386.
    """

    actor: int
    left: int
    #: Who caused the spend, when a row did. The creature itself for a
    #: second wind; the row's caster for "the target loses a healing surge".
    source: int = 0
    #: Who *gave* the surge, for "when an ally grants you a healing surge".
    #: Different from `source`: a leader grants, the spender spends.
    granted_by: int = 0
    #: The row that caused it, for a rider narrowing by power.
    power: str = ""
    #: Hit points the surge actually restored. 0 for a surge spent for
    #: nothing, which is most of them.
    healed: int = 0


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
    #: The row that granted them, as a ref. Seven rows narrow on it --
    #: "the temporary hit points you gained from your rt:r36-t1 racial
    #: trait" -- and this event said only who gave how many to whom.
    #: `""` when nothing named it. Same contract as `Healed.power`.
    power: str = ""


@dataclass
class Bloodied(Event):
    """Crossed the half-hit-point line this blow.

    `source` is whoever struck it, and may be None when nothing did --
    ongoing damage that ticks a creature past the line. Same shape and
    same reason as `Dropped.source`: "whenever you bloody an enemy" is a
    common printed trigger and, without it, `by_me` was false on this
    event and nineteen rows had nowhere to ask.

    **`power` is the ref of the row that struck**, and it is the second half
    of the same argument. Five rows print the *shape* of the blow -- "you
    become bloodied from a **melee** attack", "an enemy adjacent to you
    bloodies you with a melee attack" -- or the weapon it came through, and
    `source` alone cannot say either. With the ref, `dsl.reach_of` answers
    the kind and `Cast.weapon_of` the weapon, which are the two questions
    the cards actually ask.
    #
    Empty for ongoing damage and for anything that crosses the line without
    a row behind it, which is the same case `source=None` covers. A reader
    must treat `""` as "nothing to ask about" rather than as a miss --
    `DamageApplied.detail` has carried it this way all along and is where
    this value comes from.
    """

    actor: int
    source: int | None = None
    power: str = ""
    #: The weapon the blow came through, by ref, or "" when it came through
    #: none -- an implement power, ongoing damage, a monster's claws.
    #:
    #: `power` answers the clause's keyword and the attack's shape and says
    #: nothing about *which* weapon swung it, because a weapon power and a
    #: basic attack can both be made with either hand. `i1688p1` prints "you
    #: bloody an enemy with an attack **that uses the augmented weapon**",
    #: and nothing between `Cast.w()` picking a weapon and this event
    #: carried it forward. Stamped by the `Cast` that struck, which is the
    #: only thing that knows.
    #:
    #: **An attribute, not a field**, for the reason `Moved.kind_` and
    #: `Effect.by` are: a field reaches the wire and every replay fixture,
    #: and which arm swung is not a change in how a fight resolves. Declared
    #: as a field first and **all 7 fixtures diverged**, which is the cost
    #: that comment was written about. Read it with
    #: `getattr(ev, "weapon", "")`. #653.


@dataclass
class PowerRecharged(Event):
    """A spent row came back, on its die or on its printed condition.

    **Nothing announced it, and `triggers.py` said so in its own comment**:
    "there is no `PowerRecharged` event yet -- `m6180a3` wants one and
    carries the marker for it -- and minting one here would put a new event
    in every fixture's stream for a reason unrelated to this change. It
    wants adding on both paths at once, which is its own commit." This is
    that commit. #605.

    **Both paths, and they had to move together.** A recharge happens two
    ways -- `actions.recharge` rolls the printed die at the start of a turn,
    and `triggers.Triggers` restores a row whose printed condition is an
    event rather than a die. Minting this on one and not the other is how a
    row written against it would be right in one half of the game and
    silently wrong in the other.

    `rolled` is the die that brought it back, or 0 when the printed
    condition did -- which is also how a reader tells the two apart without
    a second field for it.
    """

    actor: int
    ref: str
    rolled: int = 0


@dataclass
class FamiliarMode(Event):
    """A familiar went into passive mode, or came back out of it.

    `c.familiar_mode` does the work and announced nothing, so *"when you
    switch your familiar into active mode"* had no moment to ride --
    `f2256` carried the marker for it. The state was never missing:
    `Companion.passive` holds it and `feats/general_c._familiar_in` already
    reads it back. Only the announcement was. #620.

    **`mode` rather than a boolean**, because the card names both
    directions and a row reading `passive=False` has to know which of
    "active" and "no familiar at all" it is looking at -- the distinction
    `f2257` turns on.

    Emitted only when the mode actually **changes**: `c.familiar_mode`
    already returns False for a switch into the mode it is in, and an event
    on a no-op would make "when you switch it" fire on a row that switched
    nothing.
    """

    actor: int
    familiar: int
    mode: str


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

    `power` is the row that did it, and seven rows need it: the printed
    line is almost never bare -- "with a melee basic attack", "with a
    ranged attack", "with a melee attack". `""` when nothing named the
    blow, which is ongoing damage and a failed death save, so a gate on a
    particular power must test for it rather than treat empty as any.

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
    #: The row that struck the killing blow. See the note above.
    power: str = ""


@dataclass
class Died(Event):
    actor: int


@dataclass
class ConditionApplied(Event):
    """A condition went on. `source` is who imposed it.

    **`power` is the row that laid it**, and four rows need it: "whenever
    you daze or stun an enemy with a **primal** power", "using a **psionic**
    power", "when you immobilize a target with a **melee attack**". The
    keyword and the shape both come off the ref, and `source` alone says
    neither -- same argument as `Bloodied.power` and `Dropped.power`, which
    is now three events making it.

    `Effect.by` is where it comes from at both `durations.py` sites: that
    field already holds "the ref of the row that laid this" and is
    defaulted from the label, so 333 call sites keep today's behaviour.

    **Empty when a *relation* imposed it** -- a grab, a domination. Those go
    through `relations.py`, which holds no effect and so knows no row, and
    the condition is a consequence of the hold rather than of a card's
    clause. A reader must treat `""` as "nothing to ask about": gating on a
    keyword would otherwise silently pay out on every grab.
    """

    source: int
    target: int
    condition: Condition
    duration: str
    power: str = ""
    #: The weapon the blow came through, by ref, or "" for none. `power`
    #: answers the keyword and the shape; three rows print *which weapon*
    #: -- "when you immobilize a target with a melee attack using this
    #: weapon" -- and nothing carried it. Hung on the effect by
    #: `Effects.apply` and read off it here, the way `power` reads `by`.
    #:
    #: **An attribute, not a field**, exactly as `Bloodied.weapon` is and
    #: for the same measured reason. #653.


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
class ShortRested(Event):
    """Five minutes passed, for this creature.

    **`turns.short_rest` existed and announced nothing**, so every card
    clocked on a rest -- "after a short rest you regain the use of this
    power", "at the end of a short rest choose a phase" -- had no moment to
    hang from. 17 rows named this; for 13 of them it was the only thing they
    were waiting for.

    **One per creature, not one for the party.** A rest is a party-wide
    thing, and every printed clause is about what *you* get back, so a row
    filtering on `actor` is the common case and a single party event would
    make every listener re-derive who it is about. `short_rest` already
    walks the creatures that have `Powers`.

    Emitted **after** the restore, so a row that asks what it has available
    sees the refreshed list rather than the spent one. #506-adjacent; the
    rest family is its own thing.
    """

    actor: int = 0


@dataclass
class ExtendedRested(Event):
    """A long rest ended, for this creature. The sibling of `ShortRested`.

    **"Per day" means this**, which is Camille's answer and the reason this
    exists: the engine has no calendar, so a daily allowance needs a moment
    to reset at, and `turns.extended_rest` is it. It matters for the
    "encounter day" -- four or five fights on one set of resources -- and for
    story mode, where a day is the unit the story engine deals in.
    `story/__init__.py` already reasons about `extended_rest` clearing
    `Powers.used`; this is the announcement it had no way to hear.

    One per creature and emitted after the restore, for the two reasons
    `ShortRested` records: every printed clause is about what *you* get back,
    and a row answering the rest asks what it has available.
    """

    actor: int = 0


@dataclass
class Boosted(Event):
    """A roll already made was added to, and by which row.

    The sibling of `Rerolled` below, filed for the same reason and found the
    same way: `c.boost_roll` mutates the result in place and said nothing, so
    the four feats printing a rider on **"an attack benefiting from"** a
    banked charge had no subject. `artificer_b._banked`'s own docstring
    records the pair of blockers -- the charge needing a rest to be laid at,
    and a landed roll needing something that can add to it -- and this is
    what was left once both of those landed.

    `by` is the ref of the row that paid for the boost, which is what lets a
    rider keyed to one feature ignore a boost somebody else's row bought.
    `amount` is what went on, after the row decided it.

    **`actor` is who *paid*; `rolled_by` is whose roll it was**, and they
    are different creatures whenever a row helps somebody else -- which is
    the common case for this event, since every row that emits it is a
    rider on an ally. The two were one field and `actor` carried the payer,
    so "the effect ends when the **ally** uses the bonus" could not be
    asked: `f3044` watched for the ally and saw the artificer. #679.

    `kind` is `attack`, `save` or `check`, and it says what was boosted
    rather than what the caller was willing to boost -- see
    `Cast.boost_roll`, where the same word is a filter on the way in.
    """

    actor: int = 0
    amount: int = 0
    by: str = ""
    kind: str = ""
    #: Whose roll was added to. Last because it has a default and because it
    #: arrived after the other four.
    rolled_by: int = -1


@dataclass
class Rerolled(Event):
    """A d20 was rolled again, and by which row.

    **Nothing announced this and 18 rows print a rider on it** -- "a damage
    bonus when the reroll lands", "combat advantage when the forced second
    roll misses", "a slide or a shift depending on the parity of the
    reroll". `c.reroll_attack` took the reroll and said neither that one
    happened nor what it came up, so every one of those riders had no moment
    to hang from. #496.

    `by` is the ref of the row that bought the reroll, which is what the
    riders actually narrow on: all of them say "the reroll *your racial
    power* grants", not "any reroll". Without it a feat keyed to one racial
    power would pay out on a magic weapon's reroll as well.

    `roll` is `attack`, `save`, `check` or `initiative`. A penalty on a
    rerolled attack must not land on a rerolled save, so the riders need to
    tell them apart.

    **Named `roll` and not `kind` because `Event.kind` is a property** that
    returns the class name and `wire()` puts it in the envelope every replay
    fixture reads. A field of that name shadows it, which breaks the wire
    format rather than only this event.

    `old` and `new` are the faces, not the totals -- the parity clauses read
    the die, and a total carries modifiers the card does not mention.

    **Damage rerolls are deliberately not this.** `c.reroll_damage` and
    `c.reroll_ones` are standing modifiers read inside `_roll_damage`, where
    there is no d20 and no single face; none of the 18 rows is about one.
    Announcing them is a separate event and a separate issue, and calling
    them `Rerolled` here would make a rider on an attack reroll fire on a
    damage die.
    """

    actor: int
    roll: str
    by: str
    old: int
    new: int


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
class Aided(Event):
    """One creature helped another: aid another, aid attack or aid defence.

    `kind_` is which of the three, as the word `actions.legal` uses --
    `aid_another`, `aid_attack`, `aid_defence`.

    **Why an event and not a readable effect.** Two feats answer "when you
    use the aid attack action", and what the three verbs leave behind is an
    ordinary `c.bonus` whose label names the row that called them. A feat
    gating on that label would be reading the caller's ref, not the action
    -- and one of the two feats sets the granted amount to *zero*, so there
    may be no effect to find at all.

    `enemy` is who the aid was aimed against, and is `None` for the skill
    form, which names no enemy.
    """

    actor: int
    ally: int
    kind_: str
    enemy: int | None = None


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
    #: **When in the turn this throw was taken.** `"end"` is the ordinary
    #: one; `"early"` is a throw moved to the start of the turn, or an extra
    #: one taken there. Nothing said which, and three rows narrow on it:
    #: `f2553` gives "+2 to saving throws made **at the start of your
    #: turn**" and was paying on both, `f1941` triggers on one, and `i499x1`
    #: moves one. A gate could not be written and a trigger could not tell
    #: the two apart. #671.
    when_: str = "end"
    #: The ref of the row that handed this throw over, empty for the
    #: ordinary end-of-turn one nobody granted. `f2554` and `f1024` print
    #: "a saving throw granted by your `cf:warden-f0` class feature" and
    #: there was nothing to read: `against` is the effect being saved
    #: **against**, and a display string at that. #672.
    #:
    #: **Named `when_` and `granted_via` for `Event.kind`'s reason**: a
    #: field called `when` or `kind` shadows the property `wire()` puts in
    #: the envelope every replay fixture reads, which breaks the wire format
    #: rather than only this event. `Rerolled.roll` records the same
    #: collision from the other side.
    granted_via: str = ""
    #: The keywords of the effect being saved against, read off the row that
    #: laid it. On the event as well as in the modifier context because
    #: `f1941` *triggers* on the throw rather than modifying it -- "when you
    #: save against a poison effect" -- and `against=str(eff)` is a display
    #: string with nothing to match on.
    keywords: frozenset[Keyword] = frozenset()


@dataclass
class CheckDeclared(Event):
    """A skill check about to be made, announced **before its d20 is rolled**.

    `SkillCheck` below is announced before the *modifiers* are totalled,
    which is early enough for "when you would make an Athletics check, gain
    a bonus" and not early enough for a row that has to **call the die**.
    `f2804` prints *"before making an untrained skill check, choose even
    numbers or odd numbers"*, and `SkillCheck.natural` is already in the
    event: a row answering that one would be guessing with the face in
    hand, which turns a 50/50 into an always-on bonus. Green in the audit
    and wrong in play. #693.

    So this is the one moment before the roll, the way `AttackDeclared`
    precedes the attack roll.

    **An `Event` and not a `Decision`, deliberately.** `Decision`'s own
    docstring is the reason: a proposal is refused by a listener and
    *honoured by the emitter*, and nothing printed in this tier refuses a
    skill check. Declaring it refusable would advertise a `cancel()` that
    `skills.check` does not implement -- which is the silence that comment
    was written about. When a row that forbids a check turns up, this
    becomes a `Decision` and `check()` honours it in the same commit.

    A row that answers this pays at resolution rather than here: the parity
    is not known yet. `skills.modifier` puts the die face in its context
    under `natural`, so the bonus is laid now and gated on the face.
    """

    actor: int
    skill: str
    dc: int
    target: int | None = None


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

    `target` is **who the check was made against**, for the seven rows
    whose printed line is about a creature rather than a number: "if you
    successfully intimidate an enemy", "a Bluff check in combat to gain
    combat advantage". A check against nobody leaves it `None`, which is
    most of them -- a History check is about a fact.
    """

    actor: int
    skill: str
    dc: int
    natural: int
    bonus: int
    total: int
    success: bool
    #: **Last, because it has a default.** A dataclass cannot put a
    #: defaulted field before the required ones, and placing it at the top
    #: beside the docstring that describes it made `types.py` report all
    #: seven of the others as "cannot be defined after fields with default
    #: values" -- one mistake reported as seven faults.
    target: int | None = None


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


@dataclass
class EffectSuspended(Event):
    """An effect was lifted without being ended, or put back.

    **Suspension announced nothing at all.** `Effects.suspend` sets a flag
    and calls `_lift`, and `_lift` emits only what a *condition* leaving
    needs -- so a suspended modifier was an unobservable state change.
    `Effects.end` has announced itself since it existed; this is the same
    courtesy for the thing #470 added beside it.

    Found by a row whose whole content is suspension: `i1014p1` puts out
    every light within 10 squares, fired 48 times with a lit carrier right
    beside it, and read **silent** -- correctly, because nothing it did was
    visible to anything. Teaching the harness to diff state is the wrong
    fix; the event is the right one.

    `back` is False for a suspension and True for a resume, so one event
    covers both halves and a listener can tell them apart -- the same shape
    `Rerolled` uses for `old`/`new` rather than two events.
    """

    actor: int
    what: str
    why: str
    back: bool = False


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
class WeaponHeld(Event):
    """Which weapon is in a creature's hand changed -- drawn or put away.

    **Not `WeaponChanged`**, which is a weapon's own *fields* changing in
    place. This is the other thing: the same weapon, a different hand.

    Announced for the reason `WeaponChanged` and `ZoneResized` were.
    `c.draw` and `c.stow` mutate `Gear` and emitted a `Note` -- and `Note`
    is deliberately outside `audit.DID_SOMETHING`, because it "carries no
    rules meaning" and has no actor to attribute it with. So a row whose
    whole content is drawing or sheathing was correct and invisible:
    `i1052p1` and `i1556p1` both fired 48 times, did exactly what their
    cards say, and reported silent.

    `drawn` is True for taking up and False for putting away, so one event
    covers both -- the same shape `EffectSuspended` uses for `back`.
    """

    actor: int
    ref: str
    drawn: bool = True
    #: **Caught out of the air rather than drawn off the belt.** One card
    #: triggers on a catch and must not fire on an ordinary draw, and a
    #: `Note` could not tell them apart -- it has no actor and sits outside
    #: `audit.DID_SOMETHING` on purpose. Same arrangement as `drawn` one
    #: field up: one event, two cases, a flag that says which. Only
    #: `Cast.disarm(catch=True)` ever sets it. #745.
    caught: bool = False
    #: **Whose it was**, on a catch. The same fact `Item.was` records for a
    #: weapon that reaches the floor (#736) -- and a caught one never does,
    #: so there is no `Item` to carry it. 0 for an ordinary draw.
    from_: int = 0


@dataclass
class WeaponChanged(Event):
    """A carried weapon's own fields changed in place.

    `Gear.weapons` holds per-character `replace(w)` copies, so raising a
    weapon's die or laying a property on it is a plain field write that
    needed no reader -- `_high_crit`, `_weapon_is` and `query.holding` all
    see it with no change to any of them. That is the whole argument for
    `weapon_dice` and `gains_property` working the way they do, and it has
    one cost: **nothing announced it**, so a row whose entire content is
    such a write looked inert.

    Exactly `ZoneResized`'s shape and fixed the same way. Three rows sat in
    `audit.KNOWN_SILENT` for it -- a high-crit property on an unarmed copy,
    a lengthened weapon range, and a silvered blanket -- each correct and
    invisible rather than idle. The alternative was teaching the harness to
    diff component state, which `audit.py` argues against in its own words:
    *"the real fix is an event, not an excuse"*.

    `field` is which one moved -- `"properties"`, `"damage"`, `"range"` --
    and `what` is the value laid, so a listener can tell a silvered blade
    from a high-crit one without re-reading the weapon.
    """

    actor: int
    weapon: str
    field: str
    what: str = ""


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
