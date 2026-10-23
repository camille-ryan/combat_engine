"""Everything a creature could legally do right now, as concrete choices.

Two callers need exactly this list and must never disagree about it: the
interface, which draws it, and a policy, which picks from it. So it is
computed once, here, and both read the same answer. A policy that could
choose something the interface would not offer is a policy that cheats.

An `Action` is fully determined -- power, targets, destination square, all of
it. Nothing is left to be resolved later, which is what lets a policy be
scored on the choice it actually made.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .components import Budget, Build, Health, Mod, Movement, Position, Powers
from .dsl import affordable, aim_points, candidates, get, usable
from .durations import When
from .grid import Square, distance, spread
from .query import alive, can_act, distance_between, enemies, is_
from .resolve import _mods
from .types import ActionType, Condition, Relation, Usage

if TYPE_CHECKING:
    from .ecs import World
    from .turns import Encounter


#: What running costs the runner on every attack roll until the start of
#: its next turn. The printed action is three things -- speed + 2, this,
#: and granting combat advantage -- and for a long time only the third was
#: here, so running was cheaper in this engine than on the page and the AI
#: policy was scoring it that way.
#:
#: A constant because two rows change it and neither should have to know
#: the number: `c.run_penalty(2)` says the replacement and the arithmetic
#: from 5 happens here. The rule gives no higher figure at any tier, so
#: unlike the high-crit dice this needs no level band. #669.
RUN_PENALTY = 5


@dataclass(frozen=True)
class Action:
    #: power | move | run | shift | charge | stand | escape | second_wind |
    #: total_defence | coup_de_grace |
    #: bull_rush | grab | aid_attack | aid_defence |
    #: sustain | move_zone | drop | wield | item | instinctive | command | end
    kind: str
    cost: ActionType
    ref: str = ""
    targets: tuple[int, ...] = ()
    dest: Square | None = None
    origin: Square | None = None
    #: Which half of a two-branch range line this option uses. 0 for
    #: everything that prints one range, which is almost everything.
    branch: int = 0
    #: How many power points this option spends to augment the row. 0 for
    #: everything that prints no Augment line, which is almost everything.
    #:
    #: An augment that rewrites the header -- a close burst where the base
    #: is a melee swing -- is a different set of targets, so it cannot be
    #: a decision the body takes afterwards. It is its own entry here, the
    #: same way each half of a "Melee or Ranged" line is, which is what
    #: makes both reachable by clicking and both weighable by a policy.
    augment: int = 0
    #: Which registered clause substitution this option uses. 0 is the card
    #: as printed, and is always offered -- a feat saying "you can X instead
    #: of Y" does not take Y away.
    #:
    #: The third discriminator beside `branch` and `augment`, and here for
    #: the reason given above them: a substitution has to be reachable by
    #: clicking and weighable by a policy, and a question asked halfway
    #: through the body is neither. `Powers.pre_empts` holds the clauses and
    #: `c.instead_of` is what reads this.
    variant: int = 0
    #: What this acts on, when that is not the actor and not a square: a live
    #: effect for `sustain`, and later a conjuration to walk or command.
    #:
    #: Everything here used to be a thing the actor did to a target or a
    #: square, so "spend a minor to sustain e17" had no shape. Kept as a bare
    #: int rather than a union because the `kind` already says which of the
    #: two it is, and an Action is read far more often than it is built.
    subject: int | None = None
    #: Only for a rejected option: why the interface should grey it out.
    blocked: str = ""
    path: tuple[Square, ...] = field(default=(), repr=False)

    @property
    def available(self) -> bool:
        return not self.blocked

    def __str__(self) -> str:
        bits = [self.kind]
        if self.ref:
            bits.append(self.ref)
        if self.targets:
            bits.append("-> " + ",".join(str(t) for t in self.targets))
        if self.subject is not None:
            bits.append(f"on e{self.subject}")
        if self.dest:
            bits.append(f"@{self.dest}")
        if self.augment:
            bits.append(f"+{self.augment}pp")
        if self.variant:
            bits.append(f"instead#{self.variant}")
        if self.blocked:
            bits.append(f"({self.blocked})")
        return " ".join(bits)


def legal(
    world: World, encounter: Encounter, actor: int, *, include_blocked: bool = False
) -> list[Action]:
    """Every action `actor` may take. Deterministic order.

    With `include_blocked`, unusable powers come back carrying the reason, so
    the interface can grey a card and say why rather than hiding it.
    """
    out: list[Action] = []
    if not can_act(world, actor):
        return [Action(kind="end", cost=ActionType.NONE)]

    out.extend(_powers(world, encounter, actor, include_blocked))
    out.extend(_recasts(world, encounter, actor))
    out.extend(_instinctives(world, encounter, actor))
    out.extend(_commands(world, encounter, actor))
    out.extend(_movement(world, encounter, actor))
    out.extend(_charges(world, encounter, actor))
    out.extend(_recovery(world, encounter, actor))
    out.extend(_sustaining(world, encounter, actor))
    out.extend(_dropping(world, encounter, actor))
    out.extend(_wielding(world, encounter, actor))
    out.extend(_loading(world, encounter, actor))
    out.extend(_picking_up(world, encounter, actor))
    out.extend(_spending(world, encounter, actor))
    out.extend(_action_points(world, encounter, actor))
    out.extend(_manoeuvres(world, encounter, actor))
    out.extend(_hiding(world, encounter, actor))
    out.extend(_delaying(world, encounter, actor))
    out.append(Action(kind="end", cost=ActionType.NONE))
    return out


def _powers(world: World, encounter: Encounter, actor: int, include_blocked: bool) -> list[Action]:
    known = world.get(actor, Powers)
    if known is None:
        return []
    out: list[Action] = []
    for ref in known.all:
        p = get(ref)
        if p is None:
            continue
        if p.action is ActionType.NONE:
            continue  # a trait; armed at the start of the fight, never chosen
        if p.trigger or p.triggers:
            # **A printed Trigger means the row is not yours to choose.**
            # It is offered by `engine/triggers.py`, when the thing it names
            # happens, and never from the list of what a creature may do on
            # its turn. This used to refuse only the rows whose Trigger was
            # prose with no `on=` -- a condition nothing can check is not a
            # condition -- and a free at-will of that shape was taken every
            # iteration of `take_turn`: one brute cast the same row 22 times
            # in a fight, walking itself across the map a square at a time,
            # and only the turn cap stopped it.
            #
            # Which left the fix exactly half done. Writing the `on=` that
            # makes such a row work took it straight back out of this branch
            # and into the offered list, so the same brute did the same 22
            # shifts the moment its trigger was declared -- now with a
            # working trigger as well. The Trigger line is what disqualifies
            # it, not the absence of a machine-readable one.
            continue
        if p.out_of_combat:
            # Declared on rows that light a torch or mend a cloak. The field
            # existed and only `audit.py` read it, so the four wizard
            # cantrips were offered as combat actions like anything else --
            # and got taken, because a policy picks from what it is given.
            continue
        ok, why = usable(world, actor, p)
        if not ok and p.augments:
            # An augment can reach where the base card cannot -- a close
            # burst over a melee swing, one more square of reach -- so a
            # row refused at its printed form may still have a form that
            # lands. Asking only the base hid every one of those.
            ok = any(
                usable(world, actor, p, augment=n)[0]
                for n in affordable(world, actor, p)
                if n
            )
        if not encounter.can_spend(actor, p.action):
            ok, why = False, "no action left"
        if not ok:
            if include_blocked:
                out.append(Action(kind="power", cost=p.action, ref=ref, blocked=why))
            continue
        out.extend(_aimings(world, actor, ref))
    return out





def _delaying(world: World, encounter: Encounter, actor: int) -> list[Action]:
    """Waiting for a better moment. Offered only before anything else.

    "This option must be taken before any other actions in a turn", so
    the budget has to be untouched -- and a creature that has already
    swung cannot un-swing to go later. Delaying past somebody is a whole
    turn rather than a position, which is why the slot travels.
    """
    from .components import Budget

    budget = world.get(actor, Budget)
    if budget is None or world.turn != actor:
        return []
    if (budget.standard, budget.move, budget.minor) != (1, 1, 1):
        return []
    later = [
        e
        for e in encounter.order[encounter.index + 1:]
        if e != actor and alive(world, e)
    ]
    return [
        Action(kind="delay", cost=ActionType.NONE, subject=e, targets=(e,))
        for e in later
    ]

def _hiding(world: World, encounter: Encounter, actor: int) -> list[Action]:
    """Going unseen. A minor action, and only where you could be missed.

    Everything under this already existed -- `Relation.HIDDEN_FROM`,
    `Cast.hide`, `query.hidden_from`, `resolve.attack` breaking it for
    whoever swung, and a `skill:stealth` modifier read like any other.
    What did not exist was any way to *choose* it, so the only creatures
    that ever hid were the ones whose own rows hid them.

    You can only hide from somebody who cannot plainly see you, which in
    4e means cover or concealment against them. Both are already
    computed: `query.cover_between` traces one and `concealment_of`
    reads the other off the creature.
    """
    from .query import concealment_of, cover_between, enemies, hidden_from

    if not encounter.can_spend(actor, ActionType.MINOR):
        return []
    unseeing = hidden_from(world, actor)
    hideable = [
        e
        for e in sorted(enemies(world, actor))
        if alive(world, e)
        and e not in unseeing
        and (cover_between(world, e, actor) or concealment_of(world, actor))
    ]
    if not hideable:
        return []
    return [Action(kind="hide", cost=ActionType.MINOR, targets=tuple(hideable))]

def _action_points(world: World, encounter: Encounter, actor: int) -> list[Action]:
    """Spending an action point for an extra action.

    **The rule, checked rather than remembered:** a free action, once per
    encounter, buying one additional action, and the spender chooses
    whether that is a standard, a move or a minor.

    Everything below this was already built -- the pool, the two separate
    limits, the round stamp `resolve.attack` reads so that "an attack made
    with an action point" is a gate, and `Cast.action_point` itself. What
    did not exist was any way to reach it, so in a whole fight not one
    point had ever been spent. The third mechanic found this session
    modelled end to end with no menu entry.
    """
    from .components import ActionPoints

    pool = world.get(actor, ActionPoints)
    if pool is None or pool.available <= 0:
        return []
    # **One a round, whoever you are.** Only a solo can reach this -- it
    # is the one thing with two points -- and the rule is that it may
    # still spend just one per round.
    if pool.spent_round == world.round:
        return []
    # Offered whenever there is one to spend. Holding it back until the
    # turn is otherwise empty is a judgement about *when* it is worth
    # using, and that belongs to the policy -- `legal` says what the
    # rules allow, and the rules allow it at any point in your turn.
    return [
        Action(kind="action_point", cost=ActionType.FREE, subject=i, ref=which.value)
        for i, which in enumerate((ActionType.STANDARD, ActionType.MOVE, ActionType.MINOR))
    ]

def _recast_key(ref: str, cost: ActionType) -> str:
    return f"{ref} as {cost.value}"


def _recast_used(world: World, known: Powers, key: str) -> int:
    """How many of this turn's granted casts have already gone."""
    return known.times(key) if known.last_round.get(key) == world.round else 0


def _recasts(world: World, encounter: Encounter, actor: int) -> list[Action]:
    """Rows a standing effect lets this creature use for a cheaper action.

    `c.recast` is the writer, on the same "<what> as <cost>" carrier
    `c.shift_as` uses, with a ref as the what and how many times a turn as
    the value. Offered *on top of* the row's own entry rather than instead
    of it: the printed line adds a way to use the power and takes none away.

    Anything whose what is not a ref belongs to somebody else's reader --
    `shift` to `_movement` -- and falls out on the `get`.
    """
    known = world.get(actor, Powers)
    if known is None:
        return []
    out: list[Action] = []
    for (ref, cost), per_turn in sorted(
        _granted(world, actor).items(), key=lambda kv: (kv[0][0], kv[0][1].value)
    ):
        p = get(ref)
        if p is None or cost is p.action or ref not in known.all:
            continue
        if _recast_used(world, known, _recast_key(ref, cost)) >= per_turn:
            continue
        ok, _why = usable(world, actor, p)
        if not ok or not encounter.can_spend(actor, cost):
            continue
        out.extend(_aimings(world, actor, ref, cost=cost))
    return out


def _instinctives(world: World, encounter: Encounter, actor: int) -> list[Action]:
    """Summons this creature may set going without commanding them.

    "Once per round you can use a minor action to command one of your
    summoned creatures to use its instinctive effect" is a line in the
    menu and nothing else, so it rides the same "<what> as <cost>" carrier
    `c.shift_as` and `c.recast` use, with `instinctive` as the what and
    how many times a round as the value. This is its reader, and without
    one the word would be carried and never looked at.

    Counted per round rather than per turn, which is what the carrier's
    `last_round` already measures -- the value is a cap on the whole
    round, not one per creature.
    """
    from .components import Companion

    known = world.get(actor, Powers)
    if known is None:
        return []
    offers = {
        cost: n
        for (what, cost), n in _granted(world, actor).items()
        if what == "instinctive"
    }
    out: list[Action] = []
    for cost in sorted(offers, key=lambda a: a.value):
        if _recast_used(world, known, _recast_key("instinctive", cost)) >= offers[cost]:
            continue
        if not encounter.can_spend(actor, cost):
            continue
        for eid in sorted(world.having(Companion)):
            mine = world.get(eid, Companion)
            if mine.owner != actor or not alive(world, eid):
                continue
            p = get(mine.ref)
            spec = getattr(p, "summon", None) if p else None
            if spec is None or spec.instinctive is None:
                continue
            out.append(
                Action(kind="instinctive", cost=cost, ref=mine.ref, subject=eid)
            )
    return out


def _commands(world: World, encounter: Encounter, actor: int) -> list[Action]:
    """The swing a companion takes only because its owner paid for one.

    "Using your actions in combat, you control your beast companion by
    issuing it commands", and commanding one to attack costs a **standard**
    action. So the companion holding no initiative slot was never the missing
    half -- `query.combatants` subtracts `Companion` and
    `components.Companion` states it as doctrine, and both are right. The
    missing half was this reader. Without it a beast swung only when
    something else handed it a swing: an opportunity window,
    `c.grant_attack`, or a row calling `c.basic(who=)`. A ranger on the
    companion leg fielded a creature that soaked, flanked and took every buff
    written for it, and never once attacked on its own.

    A cheaper cost is offered too when something grants one, on the same
    "<what> as <cost>" carrier `_instinctives` and `c.recast` read, with
    `command` as the what. A 21st-level feat reprices this swing to a minor
    and will not be the last thing that does.

    Two creatures are deliberately not offered anything here:

    * A **summon**, whose ref carries a `summon=` block. `Cast.command` and
      `_instinctives` are its doors, and it is the reason a beast was offered
      nothing -- `_instinctives` gates on that block and a companion's ref is
      a `comp:` row without one.
    * A companion with **no attack line of its own**, which `Companion.damage`
      says outright: "empty for a spirit, which has no attack of its own:
      every attack it makes is a row its owner used." Commanding one would
      roll a basic attack for a creature whose page prints none.
    """
    from .components import Companion

    own = world.get(actor, Powers)
    granted = {
        cost: n
        for (what, cost), n in _granted(world, actor).items()
        if what == "command"
    }
    costs = [ActionType.STANDARD, *sorted(granted, key=lambda a: a.value)]
    out: list[Action] = []
    for eid in sorted(world.having(Companion)):
        mine = world.get(eid, Companion)
        if mine is None or mine.owner != actor or not mine.damage:
            continue
        if not alive(world, eid) or not can_act(world, eid):
            continue
        held = get(mine.ref)
        if held is not None and getattr(held, "summon", None) is not None:
            continue
        known = world.get(eid, Powers)
        ref = (known.basic if known is not None else "") or ""
        p = get(ref) if ref else None
        if p is None or not usable(world, eid, p)[0]:
            continue
        for cost in costs:
            if cost in granted:
                if own is None:
                    continue
                key = _recast_key("command", cost)
                if _recast_used(world, own, key) >= granted[cost]:
                    continue
            if not encounter.can_spend(actor, cost):
                continue
            # Aimed from the **beast**: reach, cover and flanking are all
            # measured from its square, and `_aimings` already does that for
            # whichever actor it is handed. Only the payer changes.
            for aim in _aimings(world, eid, ref, cost=cost):
                out.append(
                    Action(
                        kind="command",
                        cost=cost,
                        ref=ref,
                        targets=aim.targets,
                        subject=eid,
                    )
                )
    return out


def _variants(world: World, actor: int, ref: str) -> list[int]:
    """0, then one index per clause substitution registered against this row.

    0 leads, because the note in `basic_options` applies here too: a
    headless run takes the first, and the first should be the printed card
    rather than whichever feat happened to register.
    """
    from .components import Powers

    known = world.get(actor, Powers)
    if known is None:
        return [0]
    found = sum(
        len(entries)
        for (on_ref, _what), entries in known.pre_empts.items()
        if on_ref == ref
    )
    return list(range(found + 1))


def _aimings(world: World, actor: int, ref: str, *, cost: ActionType | None = None) -> list[Action]:
    """One action per distinct way of aiming this power.

    A row printing "Melee or Ranged weapon" is two ways of using it that
    disagree about reach, provoking, weapon and often ability, so each
    branch is enumerated separately. That is what makes both of them
    reachable by clicking, and what lets a policy weigh one against the
    other instead of being handed whichever was declared first.
    """
    p = get(ref)
    if p is None:
        return []
    open_branches = [b for b in p.branches if p.can_branch(world, actor, b)]
    if not open_branches:
        open_branches = [0]
    # Each affordable augment is its own way of using the row, exactly as
    # each open branch is. `affordable` answers `(0,)` for every row that
    # prints no Augment line, so nothing outside the three psionic classes
    # gains an entry here.
    forms = affordable(world, actor, p)
    out: list[Action] = []
    for spend in forms:
        if spend and not usable(world, actor, p, augment=spend)[0]:
            continue
        for b in open_branches:
            # And each registered substitution, for the third time and the
            # same argument.
            for v in _variants(world, actor, ref):
                out.extend(
                    _aiming_branch(world, actor, ref, p, b, cost, spend, v)
                )
    return out


def _aiming_branch(world: World, actor: int, ref: str, p, branch: int, cost: ActionType | None = None, augment: int = 0, variant: int = 0) -> list[Action]:  # noqa: ANN001, E501
    cost = cost or p.action
    reach = p.reach_of(branch, augment)
    aim_at = p.target_of(augment)

    def act(**kw) -> Action:  # noqa: ANN003
        return Action(
            kind="power", cost=cost, ref=ref, branch=branch, augment=augment,
            variant=variant, **kw
        )

    if not p.is_attack_at(augment):
        return [act()]

    def aimed(origins: list[Square]) -> list[Action]:
        """One option per place the area can be laid down, honouring its target line.

        **The target line used to be ignored here**, so a blast or burst whose printed
        target is "one creature" hit *everyone* in its footprint. 19 attack rows declare an
        area with a capped target line -- 14 at one creature, three at two, two at three --
        and the path below for non-area rows has always honoured both `everyone` and
        `count`. #322.

        The worked case: `m493a7` is `Close blast 10, Target: one creature`, an at-will
        minor whose whole hit line is a slide -- its own docstring says "No damage at all".
        Offered against a four-character party it became a four-target power, and one solo
        used it **28 times across 9 turns, 72 of its 77 attack rolls, for 0 damage**. The
        inflated target count is also what made it win the comparison, so this and the
        policy's per-body terms were feeding each other.

        `count == 1` **enumerates** rather than capping, which is what the non-area path
        does and for the same reason: capping to `hit[:1]` would silently pick the first
        creature in sort order on the caster's behalf, and which one is hit is the
        interesting half of the choice.
        """
        out = []
        for origin in origins:
            hit = candidates(world, actor, p, origin, branch, augment)
            if not hit:
                continue
            if aim_at.everyone:
                out.append(act(targets=tuple(hit), origin=origin))
            elif aim_at.count == 1:
                out.extend(act(targets=(t,), origin=origin) for t in hit)
            else:
                out.append(act(targets=tuple(hit[: aim_at.count]), origin=origin))
        return out

    if reach.kind == "close_blast":
        # Keyed by the square it is aimed at -- for a blast 3 that is the ring two out.
        return aimed(aim_points(world, actor, p, augment))

    if reach.kind == "area_burst":
        return aimed(_burst_origins(world, actor, p, augment))

    pool = candidates(world, actor, p, None, branch, augment)
    if aim_at.everyone:
        return [act(targets=tuple(pool))] if pool else []
    if aim_at.count == 1:
        return [act(targets=(t,)) for t in pool]
    # "Up to N creatures": offer the whole pool, capped. A policy that wants a
    # subset asks for one; the interface lets the player click them.
    return [act(targets=tuple(pool[: aim_at.count]))]


def _burst_origins(world: World, actor: int, p, augment: int = 0) -> list[Square]:  # noqa: ANN001
    """Candidate origin squares for an area burst, capped to ones that land.

    `aim_points` is the authority on where the power may be centred -- it
    knows the range off the printed line -- and this keeps only the squares
    a creature is standing in. An area burst aimed at empty ground is legal
    and occasionally right, but offering every square within ten would swamp
    the interface and any policy alike.

    Narrowing without asking `aim_points` first is how an "area burst 1
    within 10" came to be offered twenty-one squares away.
    """
    from .query import creatures, squares

    legal_aims = set(aim_points(world, actor, p, augment))
    out: set[Square] = set()
    for other in creatures(world):
        if not alive(world, other):
            continue
        out |= squares(world, other) & legal_aims
    return sorted(out)


def _movement(world: World, encounter: Encounter, actor: int) -> list[Action]:
    from .query import can_move, can_run, can_walk, speed

    out: list[Action] = []
    if is_(world, actor, Condition.PRONE):
        return out  # stand up first; see `_recovery`
    if encounter.can_spend(actor, ActionType.MOVE) and can_walk(world, actor):
        for dest, path in sorted(world.reachable_paths(actor, speed(world, actor)).items()):
            out.append(
                Action(
                    kind="move",
                    cost=ActionType.MOVE,
                    dest=dest,
                    path=tuple(path),
                )
            )
    # **Running.** Speed + 2, and you grant combat advantage until the
    # start of your next turn. The engine built no run action at all, so
    # seven content gates reading `kind_ == "run"` -- in fighter, avenger,
    # ardent, warlord and two monster files -- could never once fire, and
    # two engine docstrings promised it in the same breath ("cannot use
    # move actions to walk or run"). A printed rule modelled nowhere.
    #
    # `c.bonus("run")` is read here so a stance can print a longer one:
    # the ranger's is speed + 4 and grants nothing, which is a change to
    # this menu rather than a power with a body.
    # **`can_run`, not `can_walk`.** This gated on the walk, so the only way
    # to stop a creature running was `c.no_walk`, which stops it walking
    # too -- and `m5452a2`'s card is a walk that cannot be run. #670.
    if encounter.can_spend(actor, ActionType.MOVE) and can_run(world, actor):
        extra = 2 + _mods(world, actor, "run", {})
        far = speed(world, actor) + extra
        # Priced as a run, because `execute` walks it as one. Offering
        # options at walk prices and then charging run prices is the exact
        # split `World.difficult` exists to prevent.
        for dest, path in sorted(
            world.reachable_paths(actor, far, kind="run").items()
        ):
            out.append(Action(kind="run", cost=ActionType.MOVE, dest=dest, path=tuple(path)))

    # A shift is its own action: one square, and it provokes nothing.
    # Offered separately because walking to the same square and shifting
    # to it are different decisions with different consequences.
    #
    # One square for a move action is only the default. `c.shift_as` grants
    # a longer one, or one at a different cost -- a stance printing "you can
    # shift 2 squares as a move action" is a change to this menu and nothing
    # else, so it could not be written while the menu was a constant.
    from .movement import OVERHEAD, mode_of, reachable

    # **`can_move`, not `can_walk`, and the difference is the whole point.**
    # `_movement` above gates its walk on `can_walk` and this gated on nothing,
    # so an immobilized or grabbed creature was offered seven shifts it could not
    # take -- seven squares a player would be shown as legal destinations for
    # something that cannot move. `movement.shift` refused them correctly, so the
    # rule was never broken; the menu was lying about it. #246.
    #
    # The weaker test is deliberate: `can_walk` also refuses a **rooted**
    # creature, and rooted is "cannot use move actions to walk or run" -- its own
    # docstring says such a creature "may still shift". Gating this on `can_walk`
    # would take the shift away from every row printing that line.
    if can_move(world, actor):
        offers = {ActionType.MOVE: 1}
        for (what, cost), squares_ in _granted(world, actor).items():
            if what != "shift":
                continue
            offers[cost] = max(offers.get(cost, 0), squares_)
        mode = mode_of(world, actor, None)
        for cost in sorted(offers, key=lambda a: a.value):
            if not encounter.can_spend(actor, cost):
                continue
            # Priced as a shift, to match `Cast.shift` and `execute`. A
            # creature exempt from difficult terrain only while shifting was
            # offered the same squares as one that is not.
            step = reachable(
                world, actor, offers[cost],
                mode="walk" if mode in OVERHEAD else None, kind="shift",
            )
            for dest in sorted(step):
                out.append(Action(kind="shift", cost=cost, dest=dest, path=(dest,)))
    return out


#: The words `Cast.grant_action` may hand out -- **every one of them read in
#: this file**, which is the whole point of the set living here.
#:
#: `c.grant_action` lays a bonus under `"<what> as <cost>"` and nothing
#: validated the word, so a row could carry one nothing reads: it costs
#: nothing, does nothing, and the row still fires and still audits green.
#: That is #583, which cost nine rows, and it was **still live on one row**
#: when this set was written -- `m3617a3` handed an ally
#: `grant_action("attack", FREE)` and the ally never got an attack, because
#: no reader has ever looked for that word.
#:
#: So the rule is the one #583's own write-up asked for: *"add the reader in
#: `actions` at the same time as the word"*. Adding a word here without a
#: reader below is the same bug with a longer fuse, and
#: `drivers.granted_words` greps this file for the comparison that proves
#: each word is consulted -- planted both ways.
#:
#: `Cast.recast` deliberately does **not** come through `grant_action`: its
#: `what` is a power's ref, not a word, so it builds the same carrier by
#: hand and this set does not constrain it.
GRANTABLE = frozenset({
    "aid_attack", "aid_defence", "command", "escape", "instinctive",
    "move_zone", "second_wind", "shift", "stand",
})


def _granted(world: World, actor: int) -> dict[tuple[str, ActionType], int]:
    """`query.granted_actions`, with the cost as an `ActionType`."""
    from .query import granted_actions

    out: dict[tuple[str, ActionType], int] = {}
    for (what, word), n in granted_actions(world, actor).items():
        try:
            out[(what, ActionType(word))] = n
        except ValueError:  # a key that is not an action name is not one
            continue
    return out


def _charges(world: World, encounter: Encounter, actor: int) -> list[Action]:
    """Run at somebody and swing. One option per enemy, not per square.

    A charge is a standard action that spends the move as well, and the printed
    rule puts **two** constraints on the movement that this did not enforce:

    * the move must end **at least 2 squares from where you started** -- "at
      least one square" was what this docstring claimed and the code allowed;
    * **every square of the movement must bring you closer to the target.**

    Then a melee basic attack, or a row that may replace one, at +1.

    **Both were missing and it was a free bonus rather than a real choice.**
    Measured over sixteen fights before the fix: of 2,112 charges offered,
    **1,072 ended fewer than two squares from the start** -- every one of them a
    single sidestep -- and **986 contained a square that did not close**. A
    creature already adjacent could step one square sideways, stay adjacent, and
    swing at +1, which is strictly better than standing still and attacking. The
    AI took it constantly, which is what a free bonus looks like.

    A charge is simply **unavailable** when no closing path exists -- going round
    a pillar is a move, not a charge -- so the filter is the rule rather than a
    preference.

    Offered per enemy rather than per destination: a dozen squares around one
    target are the same decision, and the shortest legal one is what anybody
    would take.
    """
    from .query import enemies, speed, squares

    if is_(world, actor, Condition.PRONE):
        return []
    if not encounter.can_spend(actor, ActionType.STANDARD):
        return []
    if not encounter.can_spend(actor, ActionType.MOVE):
        return []

    known = world.get(actor, Powers)
    if known is None or not known.basic:
        return []

    # "You can use a power associated with this feat in place of a melee
    # basic attack when charging" -- one option per row rather than one
    # per enemy, so the policy scores the swap against the plain swing
    # instead of the charge menu deciding for it.
    from .dsl import basic_options

    swings = basic_options(world, actor, "charge")

    # The charge context, so "+4 power bonus to speed when charging" is read
    # by the one measurement it is about.
    # Priced as a charge, to match the `kind="charge"` that `execute` walks
    # it with -- "ignore all difficult terrain when you move as part of a
    # charge" is a printed line and this is where it is spent.
    reachable = world.reachable_paths(
        actor, speed(world, actor, {"charge": True}), kind="charge"
    )
    mine = world.get(actor, Position)
    here = mine.square if mine is not None else None
    if here is None:
        return []
    out: list[Action] = []
    for foe in sorted(enemies(world, actor)):
        if not alive(world, foe):
            continue
        space = squares(world, foe)

        def closes(path: list[Square], at: tuple[int, int] = here,
                   toward: frozenset = space) -> bool:
            """Does every square of this path bring the walker closer?"""
            was = min(distance(at, s) for s in toward)
            for step in path:
                now = min(distance(step, s) for s in toward)
                if now >= was:
                    return False
                was = now
            return True

        for ref in swings:
            # **A charge with reach may end at reach, not only adjacent.** Camille's
            # clarification, and it is per *swing* rather than per enemy, because
            # two rows a creature could charge with need not reach equally far. This
            # asked for an adjacent square whatever was being swung, so a reach
            # weapon's one advantage -- hitting from a square that cannot hit back --
            # was unavailable on a charge.
            swing = get(ref)
            far = swing.reach_of(0).size if swing is not None and swing.reach else 1
            lands = spread(space, max(1, far))
            best = min(
                (
                    (len(path), dest, path)
                    for dest, path in reachable.items()
                    # The two printed constraints, in order of what they rule out:
                    # ending too close to where you began, and a square that does
                    # not close. See the docstring for what each was costing.
                    if dest in lands and path
                    and distance(here, dest) >= 2
                    and closes(path)
                ),
                default=None,
            )
            if best is None:
                continue
            _n, dest, path = best
            out.append(
                Action(
                    kind="charge",
                    cost=ActionType.STANDARD,
                    ref=ref,
                    targets=(foe,),
                    dest=dest,
                    path=tuple(path),
                )
            )
    return out


def _sustaining(world: World, encounter: Encounter, actor: int) -> list[Action]:
    """Keeping a sustained effect going, deliberately.

    Mostly you do not need this: an effect whose action is still unspent
    sustains itself at the end of your turn (`Effects._sustain_by_default`).
    It is here for the two cases where the default is not what you want --
    sustaining early, and choosing which of two effects gets the one minor
    you have.
    """
    out: list[Action] = []
    for eff in sorted(world.effects.live.values(), key=lambda e: e.id):
        if eff.source != actor or eff.sustain_cost is None:
            continue
        if eff.sustained >= world.round:
            continue  # already going this round
        if not encounter.can_spend(actor, eff.sustain_cost):
            continue
        out.append(
            Action(kind="sustain", cost=eff.sustain_cost, subject=eff.id, ref=eff.label)
        )
    return out


def _dropping(world: World, encounter: Encounter, actor: int) -> list[Action]:
    """Ending something deliberately, where the printed line allows it.

    "Reverting to your normal form is a minor action" is the shape: the
    effect is yours, it is not going to expire on its own, and stepping out
    of it costs something. Nothing could say that before -- an effect was
    only ever ended by its duration running out.
    """
    from .components import Conjuration

    mine = list(world.effects.of(actor))
    # **A conjuration's effect is held by the conjuration**, which has no turn --
    # no `Health`, no `Side`, no initiative slot, deliberately. So an effect that
    # `c.endable` made droppable on a spectral hound was offered to nobody, and
    # "as a standard action you can dismiss it and make a close burst 1 attack
    # centred on its square" had no action to be. Offered to whoever conjured it,
    # which is the only creature the printed line can mean. #296.
    for _eid, conj in world.each(Conjuration):
        if conj.by != actor:
            continue
        held = world.effects.live.get(conj.effect or -1)
        if held is not None and held not in mine:
            mine.append(held)
    out: list[Action] = []
    for eff in sorted(mine, key=lambda e: e.id):
        if eff.drop_cost is None or not encounter.can_spend(actor, eff.drop_cost):
            continue
        out.append(
            Action(kind="drop", cost=eff.drop_cost, subject=eff.id, ref=eff.label)
        )
    return out


def _wielding(world: World, encounter: Encounter, actor: int) -> list[Action]:
    """Drawing or swapping a weapon. A minor action, as printed.

    Without it a character was stuck for the whole fight with whatever it
    started holding -- which matters now that a power's melee or ranged
    branch is offered on the strength of what is in hand. A ranger who put
    the bow away could never pick it up again.
    """
    from .components import Gear, Weapon

    gear = world.get(actor, Gear)
    # **`< 2` was here and it is the swapping case, not the drawing one.**
    # A character carrying exactly one weapon and holding nothing could
    # never take it back up -- which is word for word the fault this
    # function's own docstring says it exists to fix, "a ranger who put the
    # bow away could never pick it up again", one weapon short of being
    # caught. The `w.ref not in held` filter below already refuses to offer
    # what is in hand, so the guard was both redundant for the common case
    # and wrong for the single-weapon one. #689.
    if gear is None or not gear.weapons:
        return []
    # A minor is the rule; three rows buy their way out of it and
    # `c.draws_free` is what records that. `draws_left` is the "once per
    # turn" half -- spent, the cost goes back to the printed minor rather
    # than the draw going away.
    cheap = gear.draw_cost is not None and gear.draws_left != 0

    def price(w: Weapon) -> ActionType:
        # Priced per weapon, because "draw and attack with a dagger" makes
        # one weapon cheap and leaves the rest at the printed minor.
        if cheap and (not gear.draw_only or gear.draw_only == w.ref):
            return gear.draw_cost or ActionType.MINOR
        return ActionType.MINOR

    held = {w.ref for w in gear.held}
    return [
        Action(kind="wield", cost=price(w), subject=i, ref=w.ref)
        for i, w in enumerate(gear.weapons)
        if w.ref not in held and encounter.can_spend(actor, price(w))
    ]


def _loading(world: World, encounter: Encounter, actor: int) -> list[Action]:
    """Reloading an emptied weapon, at the printed minor.

    Offered the way `_wielding` offers a draw, and priced the same way: a
    minor is the rule, `c.loads_free` is what four rows use to buy out of
    it, and `loads_left` is the "once per turn" half -- spent, the cost
    goes back to the printed minor rather than the reload going away.

    Only a weapon in hand and actually empty is offered. Three weapons can
    ever be empty (`query.needs_loading`), so for every other creature in
    the game this returns `[]` after one set lookup. #675, #725.
    """
    from .components import Gear, Weapon
    from .query import needs_loading

    gear = world.get(actor, Gear)
    if gear is None or not gear.unloaded:
        return []
    cheap = gear.load_cost is not None and gear.loads_left != 0

    def price(w: Weapon) -> ActionType:
        # **By group as well as by ref**, which `draw_only` does not need
        # and this does: every card here names "a crossbow", and crossbow
        # is a group of three. Matched the way `Cast.wielding` matches a
        # printed word -- ref, then group -- rather than inventing a third
        # spelling of the same question.
        named = gear.load_only
        if cheap and (not named or named in (w.ref, w.group)):
            return gear.load_cost or ActionType.MINOR
        return ActionType.MINOR

    return [
        Action(kind="load", cost=price(w), ref=w.ref)
        for w in gear.held
        if w.ref in gear.unloaded and needs_loading(w)
        and encounter.can_spend(actor, price(w))
    ]


def _spending(world: World, encounter: Encounter, actor: int) -> list[Action]:
    """Eating the seed, expending the scroll -- a one-shot in somebody's hand.

    The creature spending it is generally not the creature that made it, and
    the payout is printed on the maker's row with the maker's numbers, so
    this cannot be a granted row: it is an `Item`, and the action to spend
    it is offered here or nowhere.
    """
    from .components import Item

    out: list[Action] = []
    for eid, item in sorted(world.each(Item)):
        if item.owner != actor or item.uses <= 0 or item.spend is None:
            continue
        cost = ActionType(item.cost)
        if not encounter.can_spend(actor, cost):
            continue
        out.append(Action(kind="item", cost=cost, subject=eid, ref=item.ref))
    return out


def _picking_up(world: World, encounter: Encounter, actor: int) -> list[Action]:
    """Taking something up off the floor. A minor action, as printed.

    `Cast.disarm` has always dropped a weapon into a square as an `Item`
    with `owner=0`, `uses=0` and no `spend` -- which makes it invisible to
    `_spending`, the only thing that ever looked at an `Item`. So a
    disarmed weapon lay there permanently and nothing in the game could
    reach it, including the creature it had just been taken from.
    `docs/blocked.json`'s `cf:swordmage-f0` is the printed line that
    noticed: calling a bonded blade back to hand had no state to change.
    """
    from .components import Item, Position
    from .query import squares

    out: list[Action] = []
    cost = ActionType.MINOR
    if not encounter.can_spend(actor, cost):
        return out
    here = squares(world, actor)
    for eid, item in sorted(world.each(Item)):
        if item.owner or item.weapon is None:
            continue
        where = world.get(eid, Position)
        if where is None or where.square not in here:
            continue
        out.append(Action(kind="pick_up", cost=cost, subject=eid, ref=item.ref))
    return out


def _recovery(world: World, encounter: Encounter, actor: int) -> list[Action]:
    out: list[Action] = []
    if is_(world, actor, Condition.PRONE) and not is_(world, actor, Condition.PINNED):
        # A move action to stand is the rule; `c.grant_action` is the
        # printed line that changes it ("allies within 3 squares of you can
        # stand up as a minor action"), which had nowhere to go while the
        # cost was written in here as a constant.
        costs = {ActionType.MOVE} | {
            cost for (what, cost) in _granted(world, actor) if what == "stand"
        }
        for cost in sorted(costs, key=lambda a: a.value):
            if encounter.can_spend(actor, cost):
                out.append(Action(kind="stand", cost=cost))
    # Getting out of a grab. A move action by default, and the same
    # `_granted` road `stand` above takes, because "you can use the escape
    # action as a minor action" is a printed line and a constant here left
    # it nowhere to go.
    from .escape import grabbed

    if grabbed(world, actor):
        costs = {ActionType.MOVE} | {
            cost for (what, cost) in _granted(world, actor) if what == "escape"
        }
        for cost in sorted(costs, key=lambda a: a.value):
            if encounter.can_spend(actor, cost):
                out.append(Action(kind="escape", cost=cost))
    # **"As a minor action it can move the zone up to 3 squares."** Nine
    # monster rows print a line of this shape and none of them offered it:
    # `c.move_zone` has existed and worked, and `c.grant_action` knew four
    # words -- `shift`, `stand`, `escape`, `second_wind` -- so the fifth was
    # *carried*, which its own docstring warns "costs nothing and does
    # nothing". The word needed a reader, which is this. #583.
    #
    # **One entry per zone, and the destination is not enumerated here.**
    # `c.move_zone` already asks `World.decide` for a square when `to` is
    # None, bounded by the granted distance -- so offering every reachable
    # square per zone would both duplicate that and multiply the menu by
    # `spread()`. A creature may hold several zones (`m1003a2` prints "up
    # to three such portals at a time"), so *which* zone is the choice the
    # card actually asks about and it is the one this enumerates.
    #
    # **Its own zones, by `Zone.owner`.** The negative control the family
    # invites is moving somebody else's zone, which none of the four
    # existing granted words can get wrong because none of them takes an
    # object.
    #
    # An aura is refused, which is the printed rule and `c.move_zone`'s
    # own guard -- filtered here as well so the menu does not offer an
    # entry that would return False.
    #
    # The granted distance is **not** carried on the `Action`. Adding a
    # field would widen a structure the UI and the AI policy both read
    # without running anything, for a number `perform` can read back out
    # of `_granted` itself -- which is where every other granted word
    # gets its parameters too.
    for what, cost in _granted(world, actor):
        if what != "move_zone" or not encounter.can_spend(actor, cost):
            continue
        from .zones import Zone as _Zone

        for zone, held in world.each(_Zone):
            if held.owner == actor and held.aura is None and held.squares:
                out.append(Action(kind="move_zone", cost=cost,
                                  targets=(zone,)))

    health = world.get(actor, Health)
    known = world.get(actor, Powers)
    # Second wind is a character's action. Monsters carry surges -- one per
    # tier -- because leader rows spend them ("an adjacent ally can spend a
    # healing surge"), not so that every monster can heal itself for a
    # quarter of its hit points once a fight. Granting the surges without
    # this had them taking second wind the moment they were bloodied.
    if (
        world.get(actor, Build) is not None
        and health is not None
        and health.surges > 0
        and known is not None
        and known.times("second-wind") == 0
    ):
        # A standard by default, and cheaper where a row says so -- the
        # fighter's is a minor. Written the way `stand` above is, because
        # `SecondWind.cost` is read by a feat and a constant here would
        # have made that field permanently a standard.
        costs = {ActionType.STANDARD} | {
            cost for (what, cost) in _granted(world, actor) if what == "second_wind"
        }
        for cost in sorted(costs, key=lambda a: a.value):
            if encounter.can_spend(actor, cost):
                out.append(Action(kind="second_wind", cost=cost))
    # **Total defence.** A basic action anybody may take with a standard, and it was
    # missing from the menu entirely -- so a creature that had closed as far as it
    # could and still could not reach anything had nothing to do but end its turn.
    # Offered to monsters as well as characters: unlike a second wind it spends no
    # resource and no printed line is needed to permit it.
    if encounter.can_spend(actor, ActionType.STANDARD):
        out.append(Action(kind="total_defence", cost=ActionType.STANDARD))
    # **A coup de grace is a standard action anybody may take**, not a property
    # of any power -- and it was offered to nobody. `Cast.coup_de_grace` existed
    # and was reachable only from inside a power body, so the only coups de grace
    # in the game were the two a monster's own card spells out: the AI could never
    # take one and neither could a player. #251.
    #
    # One per adjacent helpless enemy, because the target is the whole decision.
    # Reach 1 rather than the creature's own: the printed action is made in melee,
    # and a row that finishes somebody at range is that row's own business.
    if encounter.can_spend(actor, ActionType.STANDARD):
        from .components import Powers as _Powers
        from .conditions import rules as condition_rules
        from .dsl import get as _get
        from .query import active as conditions_on

        # **The row it will swing is on the action**, which is what lets the
        # policy price it. Scored without a `ref` the option carries only its own
        # premium and none of the damage terms an attack gets, so an ordinary
        # swing at the same creature outscored it -- 9.47 against 7.90 -- and the
        # finisher was offered and never chosen, which is the same outcome as not
        # offering it. With the ref the policy reads the same expected damage it
        # reads for any attack and adds the premium on top.
        known = world.get(actor, _Powers)
        basic = known.basic if known is not None else "mba"
        row = _get(basic)
        if row is None or row.attack is None:
            basic = "mba"
        for foe in enemies(world, actor):
            if not alive(world, foe) or distance_between(world, actor, foe) > 1:
                continue
            if any(condition_rules(c).helpless for c in conditions_on(world, foe)):
                out.append(Action(kind="coup_de_grace", cost=ActionType.STANDARD,
                                  ref=basic, targets=(foe,)))
    return out


def _manoeuvres(world: World, encounter: Encounter, actor: int) -> list[Action]:
    """The three basic manoeuvres anybody may elect: bull rush, grab, aid.

    **The menu offered some of 4e's basic manoeuvres and not others, and
    which made it in looked accidental**: coup de grace and total defence
    were first-class, grab existed as a verb nobody could choose, and bull
    rush and aid another were absent entirely. 26 rows *modify* one of the
    three and none of them makes one, so what was missing was the action and
    not a verb. #501, #510.

    Each is a standard action against an adjacent creature, so the offer is
    one walk over who is next to this one. A bull rush and a grab are
    attacks and respect the printed size rule; the two aid actions are not
    attacks at all and grant outright.

    **Aid is offered per enemy, and the ally is chosen when it resolves.**
    The printed line picks an adjacent *enemy* first -- "it chooses an enemy
    adjacent to it" -- and the ally second, which is the opposite way round
    from how it reads. Offering the cross product of enemies and allies
    would put a dozen near-identical entries on one menu and give `policy/`
    a dozen things to score that differ only in a pick it can make later.
    """
    out: list[Action] = []
    # **A cheaper aid is a granted action, so the standard is not the gate.**
    # f3535 prints "you can use the aid defense action as a minor action",
    # which `c.grant_action` records and `_granted` reads back. Returning
    # early on the standard alone dropped that entry on every turn the
    # standard was already spent -- which is most of the turns a minor
    # action is worth having.
    granted = _granted(world, actor)
    cheap = {
        what: cost
        for (what, cost), _ in granted.items()
        if what in ("aid_attack", "aid_defence")
        and cost is not ActionType.STANDARD
        and encounter.can_spend(actor, cost)
    }
    standard = encounter.can_spend(actor, ActionType.STANDARD)
    if not standard and not cheap:
        return out
    for foe in enemies(world, actor):
        if not alive(world, foe) or distance_between(world, actor, foe) > 1:
            continue
        if standard:
            out.append(Action(kind="bull_rush", cost=ActionType.STANDARD,
                              targets=(foe,)))
            out.append(Action(kind="grab", cost=ActionType.STANDARD,
                              targets=(foe,)))
        for what in ("aid_attack", "aid_defence"):
            # The cheaper cost replaces the standard rather than joining it:
            # two entries differing only in what they spend is a choice no
            # player would make the expensive way round, and `policy/` would
            # have to score both.
            cost = cheap.get(what)
            if cost is None and standard:
                cost = ActionType.STANDARD
            if cost is not None:
                out.append(Action(kind=what, cost=cost, targets=(foe,)))
    return out


# --------------------------------------------------------------------------
# Doing it
# --------------------------------------------------------------------------


def perform(world: World, encounter: Encounter, actor: int, action: Action) -> bool:
    """Spend the action and carry it out. False if it was not available."""
    from .events import Note
    from .movement import walk

    if action.kind == "end":
        return True
    # **Asked before the action is spent, not after.** `candidates()` filtered
    # these targets when the action was offered, but the board can move in
    # between -- an interrupt repositions somebody, and the aim goes stale. If
    # the swing is then refused for reach (#381), spending first would charge
    # the creature a standard action for an attack that never happened, and
    # `Encounter.spend` has no inverse to refund it with. So the legality is
    # re-asked here and a stale aim costs nothing.
    if action.kind == "power" and action.targets:
        from .dsl import _within_reach

        p = get(action.ref)
        if p is not None and not any(
            # No charge exemption needed: a charge is `kind == "charge"`, so it
            # never reaches this branch.
            _within_reach(world, actor, p, t, action.branch, action.augment)
            for t in action.targets
        ):
            return False
    if not encounter.spend(actor, action.cost):
        return False

    if action.kind == "power":
        from .dsl import use

        p = get(action.ref)
        known = world.get(actor, Powers)
        if (
            p is not None
            and known is not None
            and action.cost is not p.action
            and (action.ref, action.cost) in _granted(world, actor)
        ):
            # A cheaper cast granted by `c.recast`, counted on a key of its
            # own: the row it re-prices is usually an at-will with no uses to
            # spend, and the limit printed is per turn rather than per day.
            key = _recast_key(action.ref, action.cost)
            known.used[key] = _recast_used(world, known, key) + 1
            known.last_round[key] = world.round
        return use(
            world,
            actor,
            action.ref,
            targets=list(action.targets) or None,
            origin=action.origin,
            spend=True,
            opportunity=action.cost is ActionType.OPPORTUNITY,
            branch=action.branch,
            augment=action.augment,
            variant=action.variant,
        )

    if action.kind == "instinctive":
        from .cast import Cast

        if action.subject is None:
            return False
        # Counted before it runs, on the carrier's key, so a body that
        # despawns the creature still spends the round's one use.
        known = world.get(actor, Powers)
        if known is not None:
            key = _recast_key("instinctive", action.cost)
            known.used[key] = _recast_used(world, known, key) + 1
            known.last_round[key] = world.round
        return Cast(world=world, me=actor, ref=action.ref).instinctive(action.subject)

    if action.kind == "command":
        from .components import Companion
        from .dsl import use

        if action.subject is None:
            return False
        beast = action.subject
        if not alive(world, beast) or not can_act(world, beast):
            return False
        if action.cost is not ActionType.STANDARD:
            # A granted cheaper command, counted on the carrier's key the way
            # `instinctive` is. The printed standard needs no counter: the
            # action itself is the limit.
            known = world.get(actor, Powers)
            if known is not None:
                key = _recast_key("command", action.cost)
                known.used[key] = _recast_used(world, known, key) + 1
                known.last_round[key] = world.round
        # "You gave it a command", which `turns._uncommanded` reads so that a
        # creature its owner *did* direct is not also run on instinct at the
        # end of the turn.
        mine = world.get(beast, Companion)
        if mine is not None:
            mine.commanded = world.round
        # `spend=False` because `perform` has already charged the owner, and
        # no `granted_by`: a warlord handing an ally a swing is a different
        # thing with riders of its own, and this swing is the beast's own.
        return use(
            world, beast, action.ref, targets=list(action.targets) or None, spend=False
        )

    if action.kind == "move":
        walk(world, actor, list(action.path))
        return True

    if action.kind == "delay":
        return encounter.delay_until(actor, action.subject or actor)

    if action.kind == "hide":
        from .cast import Cast

        # **The check lives in `c.hide(check=True)` now, and the DC was
        # invented here.** `dc=10 + world.round` is a number no card prints
        # and it drifted upward as the fight went on, so hiding got harder
        # the longer you waited for no printed reason. The printed
        # arrangement is Stealth against the watchers' **passive
        # Perception** -- `c.passive` exists for exactly this and says so --
        # plus the movement penalty, which was charged nowhere. #784.
        #
        # A failed check is still a spent minor and nothing else, which is
        # the risk this action has always carried.
        Cast(world=world, me=actor, ref="hide").hide(check=True)
        return True

    if action.kind == "action_point":
        from .cast import Cast

        return Cast(world=world, me=actor, ref="action point").action_point(
            ActionType(action.ref or "standard")
        )

    if action.kind == "run":
        # **The penalty is paid only if the running happened.** `walk` returns
        # how many squares were covered and **0** when the creature cannot move,
        # and this threw that away -- so a creature that did not run granted
        # combat advantage until the start of its next turn for nothing, which
        # is worse than the shift case in #246: that one wasted an action, this
        # one hands the enemy a bonus. Found sweeping the other `perform`
        # branches after fixing the shift. #246.
        covered = walk(world, actor, list(action.path), kind="run")
        if not covered:
            return False
        # "You grant combat advantage until the start of your next turn."
        # Unless something says otherwise -- the ranger's stance is the
        # printed exception and turns this off with `run_exposed`.
        # **Two printed consequences, and only one was here.** The action is
        # speed + 2, *a -5 penalty to all your attack rolls* until the start
        # of your next turn, and granting combat advantage until the same
        # moment. The penalty was modelled nowhere, so running was cheaper in
        # this engine than on the page and the policy was scoring it that
        # way. Two rows wait on it and both *change* it, which is why it is a
        # gated `Mod` rather than a number in `resolve`. #669.
        relations = [
            (Relation.GRANTS_CA_TO, actor, e)
            for e in enemies(world, actor)
            if alive(world, e)
        ] if _mods(world, actor, "run_exposed", {}) >= 0 else []
        # "You take only a -2 penalty" -- `i1695x1`. Softening, not a
        # replacement, so two sources cannot fight over which number wins;
        # clamped at 0 because nothing turns the penalty into a bonus.
        paid = max(0, RUN_PENALTY - _mods(world, actor, "run_softened", {}))
        mods = []
        if paid:
            # "No penalty on attack rolls **against your p3069 target**" --
            # `f2165`. Per-target, so the waiver has to be asked at the swing
            # with the attack context rather than when the running happened:
            # `resolve`'s ctx carries `target`, and `run_waived` is an
            # ordinary gated modifier like every other narrow permission here.
            def unwaived(ctx: dict[str, Any]) -> bool:
                return _mods(world, actor, "run_waived", ctx) <= 0

            mods = [(actor, Mod(what="attack", value=-paid, kind="untyped",
                                label="running", when=unwaived))]
        if relations or mods:
            world.effects.apply(
                actor, actor, When.SONT, label="running",
                relations=relations, mods=mods,
            )
        return True

    if action.kind == "charge":
        from .dsl import use

        # **`kind="charge"`, so the move says what it is.** It walked as an ordinary
        # one, so `OpportunityWindow.kind` read `"walk"` and "your movement during
        # the charge does not provoke" had nothing to test -- two rows named that as
        # their gap and one named it twice. `walk` already threads `kind` through to
        # `step`, which is where the window is opened. #301.
        # **The creature is charging for the whole of this**, which is what
        # "while charging" spans: the run in, the opportunity attacks it
        # provokes on the way, and the swing at the end. Cleared in a
        # `finally` so a raise cannot leave a creature charging for the rest
        # of the fight. `query.charging` is the reader. #732.
        mover = world.get(actor, Movement)
        was_charging = mover.charging if mover is not None else False
        if mover is not None:
            mover.charging = True
        try:
            walk(world, actor, list(action.path), kind="charge")
        # The move goes with it, and so does everything else: a charge ends your
        # turn whatever you have left. Spent after the walk so that an opportunity
        # attack on the way in still resolves normally.
        #
        # **An action point is the printed exception and it works.** "After you
        # charge, you can't take any further actions this turn, unless you spend an
        # action point" -- and because `_action_points` is offered off the pool
        # rather than off the budget, and `Cast.action_point` restores a slot, the
        # sequence falls out without a special case. Checked rather than assumed,
        # and exercised in play: over 24 fights, 76 turns contained a charge, 14 of
        # those spent a point afterwards, and all 14 then attacked again.
            encounter.spend(actor, ActionType.MOVE)
            hit = use(
                world, actor, action.ref,
                targets=list(action.targets) or None, spend=True, charge=True,
            )
        finally:
            if mover is not None:
                mover.charging = was_charging
        budget = world.get(actor, Budget)
        if budget is not None:
            budget.standard = budget.move = budget.minor = 0
        return hit

    if action.kind == "shift":
        from .movement import shift

        # **Return what the move returned.** This said `True` unconditionally, so
        # a caller was told the shift succeeded while the creature stood exactly
        # where it was -- the silently-false shape, and `LinearPolicy.act` was
        # being told a wasted action had worked. #246.
        return shift(world, actor, action.dest)

    if action.kind == "coup_de_grace":
        # The basic attack, with the auto-critical rule on top. A coup de grace
        # is "a standard action to use an attack power against a helpless foe",
        # and an action taken on its own has no row declaring anything -- so the
        # creature's own basic attack is what it uses. #251.
        #
        # `Cast.coup_de_grace` does the rest: it refuses a target that is not
        # actually helpless, it may miss, and a hit is a critical.
        from .cast import Cast
        from .components import Powers as _Powers
        from .dsl import get as _get

        # **Aliased** because a later branch in this function uses `Powers` from
        # its own local import, and binding the bare name here would make it a
        # local for the whole function -- so that branch raised
        # "referenced before assignment" whenever this one did not run.
        # `legal` already worked out which row this swings and put it on the
        # action, including the fallback for a basic that declares no attack
        # line. Trusting it keeps the two in step.
        known = world.get(actor, _Powers)
        ref = action.ref or (known.basic if known is not None else "mba")
        row = _get(ref)
        if row is None or row.attack is None:
            ref = "mba"
        cast = Cast(world=world, me=actor, ref=ref,
                    targets=list(action.targets),
                    target=action.targets[0] if action.targets else None)
        return cast.coup_de_grace()

    if action.kind in ("bull_rush", "grab", "aid_attack", "aid_defence"):
        # **No row, so no ref**, the same as a coup de grace: a manoeuvre is
        # an action taken on its own and nothing declares it. The `Cast` is
        # built on the manoeuvre's own name so `c.ref` says which one this is
        # -- which is what a `Note` and the log read.
        from .cast import Cast
        from .query import allies as _allies

        if not action.targets:
            return False
        foe = action.targets[0]
        cast = Cast(world=world, me=actor, ref=f"manoeuvre:{action.kind}",
                    targets=[foe], target=foe)
        if action.kind == "bull_rush":
            return cast.bull_rush(on=foe)
        if action.kind == "grab":
            return cast.grab_attempt(on=foe)
        # The two aid actions choose the ally here rather than at offer time
        # -- see `_manoeuvres`. With nobody to help, aiding is not an action
        # this creature can usefully take, so it is refused rather than
        # spending a standard action on nothing.
        friends = [a for a in _allies(world, actor) if alive(world, a)]
        if not friends:
            return False
        ally = cast.choose(friends, "which ally to aid") or friends[0]
        if action.kind == "aid_attack":
            return cast.aid_attack(foe, ally) is not None
        return cast.aid_defence(foe, ally) is not None

    if action.kind == "stand":
        for eff in world.effects.of(actor):
            if Condition.PRONE in eff.conditions:
                world.effects.end(eff, "stood up")
        world.bus.emit(Note(text=f"{actor} stands"))
        return True

    if action.kind == "escape":
        from .escape import attempt

        # A failed attempt is a spent move action and nothing else, the
        # way a failed `hide` is a spent minor.
        attempt(world, actor)
        return True

    if action.kind == "move_zone":
        # The granted distance, read back out of `_granted` rather than
        # carried on the `Action` -- see the offer side in `_recovery`. The
        # largest grant wins where a creature holds two, which is the same
        # answer `c.amount_for` gives for a raised number and for the same
        # reason: two rows granting the move are not additive.
        reach = max(
            (n for (what, _c), n in _granted(world, actor).items()
             if what == "move_zone"),
            default=0,
        )
        zone = action.targets[0] if action.targets else None
        if zone is None or reach <= 0:
            return False
        # Imported here because `perform` binds `Cast` in a branch further
        # down, which makes the name local to the whole function.
        from .cast import Cast
        # `c.move_zone` asks `World.decide` for the square when `to` is
        # None, and re-checks the aura rule and the zone's existence -- so
        # this neither duplicates the destination search nor trusts the
        # menu's view of a board that may have moved since it was drawn.
        return Cast(world=world, me=actor, ref="move_zone").move_zone(zone, reach)

    if action.kind == "sustain":
        eff = world.effects.live.get(action.subject or -1)
        if eff is None:
            return False
        world.effects.sustain(eff)
        world.bus.emit(Note(text=f"{eff.label or eff} sustained"))
        return True

    if action.kind == "load":
        from .components import Gear

        gear = world.get(actor, Gear)
        if gear is None or not action.ref or action.ref not in gear.unloaded:
            return False
        gear.unloaded.discard(action.ref)
        # Only a reload that actually used the cheap rate spends the
        # allowance, exactly as a draw does.
        if gear.load_cost is not None and action.cost == gear.load_cost \
                and gear.loads_left > 0:
            gear.loads_left -= 1
        from .events import WeaponLoaded

        world.bus.emit(WeaponLoaded(actor=actor, ref=action.ref,
                                    cost=action.cost))
        return True
    if action.kind == "wield":
        from .components import Gear

        gear = world.get(actor, Gear)
        if gear is None or action.subject is None:
            return False
        if not 0 <= action.subject < len(gear.weapons):
            return False
        gear.wield(gear.weapons[action.subject])
        # Only a draw that actually used the cheap rate spends the
        # allowance; one taken at the printed minor leaves it alone.
        if gear.draw_cost is not None and action.cost == gear.draw_cost \
                and gear.draws_left > 0:
            gear.draws_left -= 1
        # **The other door, so the event means "which weapon is in hand"
        # rather than "a content row said so".** `c.draw` is the free
        # taking-up a row has already paid for; this is the printed minor
        # the action menu offers, and both change the same fact.
        from .events import WeaponHeld

        world.bus.emit(WeaponHeld(
            actor=actor, ref=gear.weapons[action.subject].ref, drawn=True,
        ))
        world.bus.emit(Note(text=f"{actor} takes up {gear.weapons[action.subject].ref}"))
        return True

    if action.kind == "pick_up":
        from .components import Gear, Item

        item = world.get(action.subject or -1, Item)
        gear = world.get(actor, Gear)
        if item is None or item.owner or item.weapon is None or gear is None:
            return False
        gear.weapons.append(item.weapon)
        gear.wield(item.weapon)
        world.despawn(action.subject)
        world.bus.emit(Note(text=f"{actor} picks up {item.weapon.ref}"))
        return True

    if action.kind == "item":
        from .components import Item

        item = world.get(action.subject or -1, Item)
        if item is None or item.owner != actor or item.uses <= 0:
            return False
        item.uses -= 1
        if item.spend is not None:
            item.spend(actor)
        world.bus.emit(Note(text=f"{actor} spends {item.ref}"))
        if item.uses <= 0:
            world.despawn(action.subject)
        return True

    if action.kind == "drop":
        eff = world.effects.live.get(action.subject or -1)
        if eff is None:
            return False
        payout = eff.drop_then
        world.effects.end(eff, "ended deliberately")
        # After the end, not before: the printed trades read "end the
        # effect to gain X", and a payout that lays an effect of its own
        # must not be swept up by the ending it was paid for.
        if payout is not None:
            payout()
        return True

    if action.kind == "second_wind":
        # Characters only, the same rule `legal` applies. A monster carries
        # surges so that a leader row can spend one; it does not spend them
        # itself unless a printed line says so. Checked here as well because
        # `perform` is reachable from the API and the policy without going
        # through `legal`.
        if world.get(actor, Build) is None:
            return False
        from .cast import Cast

        return Cast(world=world, me=actor, ref="second-wind").second_wind(
            cost=action.cost
        )

    if action.kind == "total_defence":
        from .cast import Cast

        return Cast(world=world, me=actor, ref="total-defence").total_defence()

    return False


def recharge(world: World, actor: int) -> None:
    """Roll for any recharge power the creature has spent.

    Monsters only -- nothing a character carries recharges on a die.
    """
    known = world.get(actor, Powers)
    if known is None:
        return
    for ref in sorted(known.spent):
        p = get(ref)
        if p is None or p.usage is not Usage.RECHARGE:
            continue
        # A row may print a die, a state, or both -- and one that prints only
        # a state has `recharge=0`, which the old gate dropped before it could
        # be asked. #489.
        if p.recharge <= 0 and p.recharge_while is None:
            continue
        # **A d6, not a d20.** A printed "Recharge 6" is *roll a d6, recharge on a 6* --
        # one chance in six. Rolling a d20 against the same threshold made it
        # `P(d20 >= 6) = 15/20`, so:
        #
        #     declared        was        is
        #     recharge=6      75%        17%
        #     recharge=5      80%        33%
        #     recharge=4      85%        50%
        #
        # **307 of the 314 declared recharge values in `content/` are `recharge=6`**, so
        # effectively every recharge row in the tree fired about 4.5 times too often.
        # Measured in play before the fix: one elite's 2d10+6-and-stun fired on 10 of 13
        # acting rounds in one fight and 4 of 8 in another -- 14/21, against a printed 17%.
        #
        # It lands hardest where it is least visible. A recharge row is where an elite or a
        # solo keeps most of its damage and a standard monster mostly has none, so the
        # error was concentrated in exactly the encounter shapes that read as too long and
        # too lethal. #320.
        #
        # `roll` rather than `die`, because `die` does not append to `Rng.rolls` and this
        # module's contract is that every draw is recorded in order.
        #
        # **The die is rolled first, and that ordering is deliberate.** This
        # module's contract is that every draw is recorded in `Rng.rolls` in
        # order, so short-circuiting on a state that happens to be true would
        # drop a draw a fixture has already recorded. Asking the state first
        # would have re-recorded every replay fixture holding a recharge row.
        rolled = world.rng.roll("1d6").total if p.recharge > 0 else 0
        by_die = p.recharge > 0 and rolled >= p.recharge
        back = by_die
        if not back and p.recharge_while is not None:
            back = p.recharge_while(world, actor)
        if back:
            known.restore(ref)
            # **Announced, on both paths.** A row whose printed clause ends
            # "until it recharges this ability" had no moment to end on --
            # `m1032a1` is the case and there is no `When` for it. #605.
            #
            # **`by_die` and not `back`**, which the first draft had: a row
            # printing both a die and a condition rolls the die either way
            # (the ordering above is deliberate, so a fixture's recorded
            # draws stay in order), so reporting `rolled` whenever anything
            # restored the row announced a die that had **missed** as the
            # reason it came back. Driven over 59 boards: the field showed
            # 3, 4, 5 and 6 for a row that needs a 6.
            from .events import PowerRecharged

            world.bus.emit(
                PowerRecharged(actor=actor, ref=ref, rolled=rolled if by_die else 0)
            )
