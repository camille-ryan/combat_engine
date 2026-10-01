"""Who decides. Monsters need one of these; characters may use one too.

A policy answers three different questions and it is worth keeping them
apart, because a learned policy will be good at the first long before it is
trusted with the third:

* `act` -- which of the legal actions to take on its turn;
* `decide` -- a choice *inside* a power, like where a shift lands;
* `react` -- whether to spend an opportunity or immediate action.

Nothing here knows any rules. `actions.legal` produces the options and this
only ranks them, which means a policy cannot do something the interface would
not have offered.

**Making policies rather than writing them.** The engine is deterministic and
the event log is complete, so a fight is a labelled example: `features()`
turns a `(state, action)` pair into a flat dict of numbers, the policy
consumes weights over exactly those names, and `Memory` learns what a power
is worth by watching what it did rather than by being told. That is the whole
loop -- play fights, record features and outcomes, fit weights, play again --
and it needs nothing written per power, which is the point.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from .actions import Action, legal, perform
from .components import Gear, Health, Side
from .dsl import get
from .events import DamageApplied, Event, OpportunityWindow, PowerUsed
from .grid import distance
from .query import alive, distance_between, enemies, speed
from .types import ActionType, Keyword, Team, Usage

if TYPE_CHECKING:
    from .ecs import World
    from .turns import Encounter


class Policy(Protocol):
    def act(
        self, world: World, encounter: Encounter, actor: int, options: list[Action]
    ) -> Action: ...

    def decide(
        self, world: World, actor: int, kind: str, options: list[Any], prompt: str
    ) -> Any: ...

    def react(
        self, world: World, encounter: Encounter, actor: int, window: Event
    ) -> Action | None: ...


# --------------------------------------------------------------------------
# What a policy sees
# --------------------------------------------------------------------------


def features(
    world: World, encounter: Encounter, actor: int, action: Action
) -> dict[str, float]:
    """A flat, named view of one candidate action.

    Every name here is stable and every value is a number, so the same dict
    feeds a hand-tuned weighting and a fitted one. Add a feature and both get
    it; nothing has to be re-declared per power.
    """
    f: dict[str, float] = defaultdict(float)
    f["is_power"] = float(action.kind == "power")
    f["is_move"] = float(action.kind == "move")
    f["is_stand"] = float(action.kind == "stand")
    f["is_second_wind"] = float(action.kind == "second_wind")
    f["is_end"] = float(action.kind == "end")
    f["is_wield"] = float(action.kind == "wield")
    # Named, because an action kind the scorer does not name scores
    # **zero** -- which beats ending a turn and beats a move, and is how
    # a weapon swap became the AI's idle default twelve times a fight.
    # A run is a move that gives the enemy combat advantage, so it is
    # worth strictly less than walking the same way.
    f["is_run"] = float(action.kind == "run")
    # Named, like every other kind, because an unnamed one scores zero.
    f["is_action_point"] = float(action.kind == "action_point")
    f["is_hide"] = float(action.kind == "hide")
    f["is_delay"] = float(action.kind == "delay")
    # Named on the day the escape action arrived, for the reason every
    # comment here gives: an unnamed kind scores zero, which beats ending
    # a turn -- so the first grabbed creature would have spent every move
    # action of the fight struggling whether or not it was worth it.
    f["is_escape"] = float(action.kind == "escape")
    # **The last six.** Every kind `actions.legal` can produce is named
    # here now, because an unnamed one scores zero -- which beats ending
    # a turn at -2 and beats a move that closes nothing -- and so becomes
    # the idle default rather than being ignored. `shift` was the
    # dangerous one: `closes_distance` is computed only for `move` and
    # `run`, so a shift was never aimed, and ties break on `str(action)`,
    # which picks the lexicographically largest square -- as likely away
    # from the enemy as toward it.
    f["is_shift"] = float(action.kind == "shift")
    f["is_charge"] = float(action.kind == "charge")
    f["is_sustain"] = float(action.kind == "sustain")
    f["is_drop"] = float(action.kind == "drop")
    f["is_item"] = float(action.kind == "item")
    f["is_instinctive"] = float(action.kind == "instinctive")
    f["is_command"] = float(action.kind == "command")
    # Named on the day it was added, rather than six weeks later when
    # somebody notices the AI kneeling to collect litter instead of
    # fighting. That is what an unnamed kind does.
    f["is_pick_up"] = float(action.kind == "pick_up")
    if action.kind == "pick_up":
        # Worth doing only when it is *your* weapon on the floor, which
        # is the situation it exists for -- a creature that has just been
        # disarmed. Otherwise it is a minor spent on clutter.
        gear = world.get(actor, Gear)
        f["pick_up_disarmed"] = float(gear is not None and not gear.held)
    if action.kind == "wield":
        # **Drawing the right weapon was unreachable.** `actions._wielding`
        # offers the minor and `actions` can execute it, but nothing here
        # named the kind, so a wield scored as an unrecognised action and
        # was never once taken in any fight. `Gear.__post_init__` grips
        # `weapons[0]`, so a ranger held a sword and a rogue a dagger
        # because those are typed first -- and `Power.can_branch` then
        # refused every ranged weapon row they knew, for the whole fight.
        #
        # Worth a minor only when it buys reach the creature does not
        # have: swapping while the enemy is already adjacent is a wasted
        # action, and swapping to a bow with nobody in bowshot is worse.
        f["wield_reaches"] = float(_reaches_further(world, actor, action))
    f["targets"] = float(len(action.targets))
    # **What the augment cost.** Every other feature here measures what an
    # action buys; this is the only one that measures what it spends, and
    # without it a psionic character augments everything it can afford on
    # the first at-will of the fight -- an augmented burst scores strictly
    # higher than the base swing it replaces, because catching more
    # enemies is all the scorer can see. Weighted against
    # `enemies_caught`, so a point has to buy about a target and a half
    # before it is worth spending, and a bigger die on one creature is
    # not.
    f["augment_cost"] = float(action.augment)

    me = world.get(actor, Health)
    if me is not None:
        f["my_hp_fraction"] = me.hp / max(1, me.max_hp)
        f["i_am_bloodied"] = float(me.bloodied)
        f["my_surges"] = float(me.surges)

    p = get(action.ref) if action.ref else None
    if p is not None:
        f["usage_at_will"] = float(p.usage is Usage.AT_WILL)
        f["usage_encounter"] = float(p.usage is Usage.ENCOUNTER)
        f["usage_daily"] = float(p.usage is Usage.DAILY)
        f["costs_standard"] = float(p.action is ActionType.STANDARD)
        f["range"] = float(p.reach.size)
        f["declares_attack"] = float(p.attack is not None)
        # Using a ranged or area power with somebody in your face hands them
        # a free attack. Without this a wizard happily stands in melee and
        # fires across the room all fight.
        f["provokes_now"] = float(
            p.provokes and any(_adjacent(world, actor, e) for e in enemies(world, actor))
        )
        # **Avoidably**, which is the distinction a flat penalty cannot draw.
        # A ranged attack from inside melee is sometimes the only play -- pinned,
        # or out of move -- and sometimes a wasted hit because a one-square shift
        # was free and would have removed the provocation entirely. Camille's
        # rule: for a ranged character, stepping out first should usually win.
        #
        # This is the interaction a linear model cannot hold on its own: the shift
        # is cheap and the attack is valuable, so the attack outbids the shift and
        # the saving never happens. Priced on the attack instead, where the choice
        # actually is.
        if f["provokes_now"]:
            f["provokes_avoidably"] = float(_could_step_out(world, encounter, actor))

        # **None means there is nothing to hit**, and such a row gets no
        # hit-chance feature at all rather than a phantom one. See
        # `Power.hit_chance`.
        chances = [c for t in action.targets
                   if (c := p.hit_chance(world, actor, t)) is not None]
        if chances:
            f["hit_chance"] = sum(chances) / len(chances)
            f["expected_hits"] = sum(chances)
        if action.kind == "command" and action.subject is not None:
            # **Whose roll it is.** Every feature above measures the action
            # from `actor`, and a command is the one kind whose attack is
            # rolled by somebody else -- the beast's bonus off its own block,
            # not its ranger's. Scored as the owner's it reported the wrong
            # creature's chance to hit, and the owner's is usually the better
            # one, so the policy would have over-valued every command.
            theirs = [c for t in action.targets
                      if (c := p.hit_chance(world, action.subject, t)) is not None]
            if theirs:
                f["hit_chance"] = sum(theirs) / len(theirs)
                f["expected_hits"] = sum(theirs)

    hurt = 0.0
    nearly = 0.0
    friendly = 0.0
    mine = world.get(actor, Side)
    for t in action.targets:
        health = world.get(t, Health)
        if health is None:
            continue
        hurt += 1.0 - health.hp / max(1, health.max_hp)
        nearly += float(health.bloodied)
        theirs = world.get(t, Side)
        # A burst says "each creature", and that includes your own side.
        # Counting them as targets is how the wizard came to be aiming a
        # close blast at the fighter and scoring it well.
        # Aiming at *yourself* does not catch an ally. Counting it as such
        # gave every `target=SELF` row a score of 6 - 7 = -1, so the policy
        # preferred almost anything to a class feature and the marks, the
        # channels and the strikers' riders were never used at all.
        if t != actor and mine and theirs and mine.team is theirs.team:
            friendly += 1.0
    f["target_damage_taken"] = hurt
    f["targets_bloodied"] = nearly
    f["allies_caught"] = friendly
    # **The caster is not an enemy it caught.** `friendly` skips `t == actor` above,
    # for the stated reason -- aiming at yourself does not clip an ally -- but only
    # that half was fixed, so the actor fell straight through into `enemies_caught`
    # and a `target=SELF` row was paid 2.0 for catching an enemy that was itself.
    #
    # Measured: a fighter's self-aura row scored `is_power 6.0 + enemies_caught 2.0`
    # and was re-cast twice a turn for seven consecutive rounds while its wizard died
    # four squares away. Nothing else on that turn could reach +8. See #231.
    on_self = 1.0 if actor in action.targets else 0.0
    f["enemies_caught"] = max(0.0, float(len(action.targets)) - friendly - on_self)

    # Swapping the stance you are already in for a different one. Legal,
    # and almost always pointless: a stance ends whatever you were in, so
    # two at-will minor stances scored the same and the fighter alternated
    # between them for the whole fight -- eighty-three swaps, and a
    # twelve-round win became a thirty-round stalemate. Nothing in the
    # policy knew what a stance was. Scored rather than forbidden, because
    # replacing a stance *is* sometimes right and a fitted policy should
    # be able to learn when.
    if action.kind == "power" and action.ref:
        declared = get(action.ref)
        if declared is not None and Keyword.STANCE in declared.keywords:
            f["swaps_stance"] = float(world.effects.stance_of(actor) is not None)

    foes = [e for e in enemies(world, actor) if alive(world, e)]
    if foes:
        f["nearest_enemy"] = float(min(distance_between(world, actor, e) for e in foes))
        f["enemies_left"] = float(len(foes))
    if action.kind in ("move", "run") and action.dest is not None and foes:
        after = min(distance(action.dest, _square(world, e)) for e in foes)
        f["closes_distance"] = f.get("nearest_enemy", 0.0) - after

    # **Movement provokes, and this could not see it.** `provokes_now` was
    # computed only inside the `power` branch, off `Power.provokes` -- so the
    # -5.0 weight existed, was documented, and never fired for the commonest way
    # a creature provokes: walking out of an enemy's reach. Measured over 24
    # fights, every one of the party's move-provocations had a shift available
    # and a shift does not provoke. See #258.
    if action.kind in _WALKS and action.dest is not None:
        f["provokes_now"] = float(_would_provoke(world, actor, action.dest))
    # Stepping out of reach so the *next* action does not provoke. A shift is
    # free of provocation itself, so for a creature whose attacks would provoke
    # from where it stands, this is the move that pays for itself -- and nothing
    # here could express it, because the benefit lands on a later action.
    if action.kind in _SAFE_STEPS and action.dest is not None:
        f["leaves_melee"] = float(
            _in_reach(world, actor, _square(world, actor))
            and not _in_reach(world, actor, action.dest)
            and _attacks_would_provoke(world, actor)
        )
    return dict(f)


#: Movement that provokes. `movement._SAFE` is the complement and a shift is in
#: it, which is the whole reason stepping out first works.
_WALKS = ("move", "run", "charge")
_SAFE_STEPS = ("shift",)


def _could_step_out(world: World, encounter: Encounter, actor: int) -> bool:
    """Is there a shift this creature could still take that leaves melee?

    Asks the movement budget as well as the board: a creature that has spent its
    move action cannot fix its position, and penalising it for standing where it
    is would only make it decline to attack at all.
    """
    from .types import ActionType

    if not encounter.can_spend(actor, ActionType.MOVE):
        return False
    here = _square(world, actor)
    for dest in world.reachable_squares(actor, 1):
        if dest != here and not _in_reach(world, actor, dest):
            return True
    return False


def _reach_of(world: World, other: int) -> int:
    from .movement import _threat

    return _threat(world, other)


def _in_reach(world: World, actor: int, where) -> bool:  # noqa: ANN001
    """Is any living enemy able to reach `where`?"""
    from .grid import distance

    for foe in enemies(world, actor):
        if not alive(world, foe):
            continue
        if distance(where, _square(world, foe)) <= _reach_of(world, foe):
            return True
    return False


def _would_provoke(world: World, actor: int, dest) -> bool:  # noqa: ANN001
    """Would walking to `dest` leave an enemy's reach?

    The same question `movement.step` asks before opening the window: a creature
    provokes when it *was* in reach and is not once it arrives. Asked per enemy,
    because leaving one reach while staying in another still provokes from the
    one left.
    """
    from .grid import distance

    here = _square(world, actor)
    for foe in enemies(world, actor):
        if not alive(world, foe):
            continue
        reach = _reach_of(world, foe)
        there = _square(world, foe)
        if distance(here, there) <= reach and distance(dest, there) > reach:
            return True
    return False


def _attacks_would_provoke(world: World, actor: int) -> bool:
    """Does this creature have an attack that provokes from where it stands?

    A ranged or area power used with somebody adjacent hands them a free swing,
    which is what makes stepping out first worth a move action. Read off the
    rows the creature actually knows rather than from a list of caster classes.

    **Not gated on a declared attack line.** That was the first version and it
    found nothing: `Power.provokes` is derived from the range line, and a row may
    provoke while declaring its attack in the body instead of the header -- which
    `Attack`'s own docstring sanctions for a bonus that depends on the situation.
    All 118 of one class's ranged rows report `attack is None` and `provokes`
    True, so requiring both matched none of them and the feature never fired. A
    ranged *utility* counts for the same reason: using it in melee provokes too.
    """
    from .components import Powers

    known = world.get(actor, Powers)
    for ref in (known.known if known else ()):
        declared = get(ref)
        if declared is not None and declared.provokes:
            return True
    return False



def _reaches_further(world: World, actor: int, action: Action) -> bool:
    """Would drawing this weapon let the creature hit something it cannot?

    Cheap on purpose: the exact answer is "re-run `can_branch` for every
    known row against hypothetical gear", which is a menu rebuild per
    candidate. The nearest enemy and the weapon's reach settle it in
    practice -- a bow is worth drawing when the fight is at range, and a
    blade when it is not.
    """
    from .components import Gear

    gear = world.get(actor, Gear)
    if gear is None:
        return False
    drawing = next((w for w in gear.weapons if w.ref == action.ref), None)
    if drawing is None:
        return False
    foes = [e for e in enemies(world, actor) if alive(world, e)]
    if not foes:
        return False
    near = min(distance_between(world, actor, e) for e in foes)
    reach = drawing.ranged[1] if drawing.ranged else 1
    holding = max(
        (w.ranged[1] if w.ranged else 1) for w in gear.held
    ) if gear.held else 0
    # **Beyond walking, not merely beyond arm's length.** The first rule
    # here only asked whether the drawn weapon reached further, so a
    # rogue spent its round-one minor taking up a crossbow it could have
    # closed on -- and then held a crossbow all fight, with every melee
    # row refused, which for a rogue throws away the sneak attack that is
    # most of its damage. A weapon swap has to beat walking over there.
    return reach >= near > holding + speed(world, actor)

def _adjacent(world: World, a: int, b: int) -> bool:
    from .query import adjacent

    return adjacent(world, a, b)


def _allies_of(world: World, eid: int) -> list[int]:
    """Whose side the *target of a push* is on -- that is, the pusher's foes.

    A push is aimed at an enemy, so the creatures it should be driven away
    from are that enemy's own allies.
    """
    from .query import allies, enemies

    foes = enemies(world, eid)
    return allies(world, foes[0]) if foes else []


def _square(world: World, eid: int) -> tuple[int, int]:
    from .components import Position

    pos = world.get(eid, Position)
    return pos.square if pos else (0, 0)


# --------------------------------------------------------------------------
# Learning what a power is worth
# --------------------------------------------------------------------------


@dataclass
class Memory:
    """What powers have actually done, learned from logs.

    A body is code, so nothing can read how much damage a power deals without
    running it. This watches fights instead: every `DamageApplied` is credited
    to whichever power was in flight, and the running mean is what a scorer
    uses. Costs nothing per power and improves with every fight played.
    """

    damage: dict[str, float] = field(default_factory=dict)
    uses: dict[str, int] = field(default_factory=dict)

    def observe(self, log: list[Event]) -> None:
        current = ""
        pending: dict[str, int] = defaultdict(int)
        for ev in log:
            if isinstance(ev, PowerUsed):
                current = ev.power
                self.uses[current] = self.uses.get(current, 0) + 1
            elif isinstance(ev, DamageApplied) and current:
                pending[current] += ev.amount
        for ref, total in pending.items():
            n = max(1, self.uses.get(ref, 1))
            seen = self.damage.get(ref, 0.0)
            self.damage[ref] = seen + (total / n - seen) / n

    def worth(self, ref: str, default: float = 5.0) -> float:
        return self.damage.get(ref, default)


# --------------------------------------------------------------------------
# The default
# --------------------------------------------------------------------------

#: Hand-set weights over `features`. A fitted policy replaces this dict and
#: nothing else, which is the point of scoring through named features.
WEIGHTS: dict[str, float] = {
    "is_power": 6.0,
    # A power point, priced a little above what one more enemy caught is
    # worth. Points refresh every encounter, so hoarding them to the end
    # of a fight wastes them and the number must not be so large that
    # nothing is ever augmented -- but an augment that buys one extra
    # target is a wash, and one that buys three is clearly right.
    "augment_cost": -3.0,
    # Ending the turn is mildly bad; moving is mildly bad too, so a move has
    # to earn itself through `closes_distance`. Make ending much worse than
    # moving and the creature shuffles every turn it cannot attack, which is
    # what the first version of these numbers did.
    "is_end": -2.0,
    "is_move": -1.0,
    "is_stand": 3.0,
    # The same shape as standing up -- a move action spent to shed a
    # condition -- and priced a little under it because the check can
    # fail and standing cannot.
    "is_escape": 2.5,
    "is_second_wind": 0.0,
    "expected_hits": 4.0,
    "hit_chance": 3.0,
    "targets": 0.0,      # counted by side instead; see below
    "enemies_caught": 2.0,
    # Worth more than an enemy is worth catching, so a burst that would clip
    # one ally to catch one enemy is not worth taking.
    "allies_caught": -7.0,
    "targets_bloodied": 3.0,
    "target_damage_taken": 1.0,
    "usage_daily": -3.0,
    "usage_encounter": -0.5,
    "closes_distance": 2.0,
    "nearest_enemy": -0.1,
    # Worth about one attack, which is what it hands over.
    "provokes_now": -5.0,
    # Provoking when a free shift would have avoided it. Stacks on top of
    # `provokes_now`, so an avoidable provocation costs 9.0 against an
    # unavoidable one's 5.0 -- enough to put a ranged attack from inside melee
    # below the shift that fixes it, and not enough to stop a creature that has
    # already moved from attacking anyway.
    "provokes_avoidably": -4.0,
    # Stepping out of reach so the next action does not provoke. Worth more than
    # the -0.5 a shift costs and less than a good attack, because the point is to
    # make "step out, then shoot" beat "shoot from inside melee" without making a
    # ranged character spend its whole turn backing away.
    #
    # The arithmetic it has to win: a ranged attack from inside melee scores
    # `provokes_now` at -5.0, so stepping out first is worth up to that much on
    # the following action. 3.0 against the shift's own -0.5 nets +2.5, which
    # beats a walk that closes one square (+2.0) and loses to one that closes
    # two -- so a character still advances when advancing is the point.
    "leaves_melee": 3.0,
    # A minor spent on nothing visible, so it has to earn itself through
    # `wield_reaches` exactly the way a move earns itself through
    # `closes_distance`.
    "is_wield": -4.0,
    "wield_reaches": 9.0,
    # Strictly worse than walking: it covers the same ground and hands
    # every enemy combat advantage until your next turn. Worth it only
    # when `closes_distance` is large enough to pay for that.
    "is_run": -3.0,
    # A whole extra action for a free one, and it is only offered when the
    # turn has nothing left -- so the alternative really is ending. Worth
    # more than ending a turn and less than a good attack, because the
    # point is gone for the rest of the fight either way.
    "is_action_point": 4.0,
    # A minor spent on a check that may fail, buying combat advantage on
    # the next attack and only against those it hides from. Worth about
    # what the advantage is, and less than spending the minor on a power.
    "is_hide": 2.0,
    # Giving up the whole turn for a later one. Sometimes right and the
    # scorer cannot tell when, so it is worse than ending a turn -- an
    # unnamed kind would score zero and become the idle action, which is
    # the failure this weight exists to avoid.
    "is_delay": -6.0,
    # A shift is a move that provokes nothing, so it is worth slightly
    # more than walking the same square -- but it is one square and is
    # not aimed, so it must not beat a real move that closes ground.
    "is_shift": -0.5,
    # A charge is an attack and earns most of its score through the
    # attack features, but it loses the flat `is_power` bonus because it
    # is not a power -- so it is handed back here, or a charge is
    # systematically six points worse than the same swing standing still
    # and nothing ever charges.
    "is_charge": 6.0,
    # Keeping something alive that is already paid for.
    "is_sustain": 3.0,
    # Letting go of a grab, and spending a one-shot: both are situational
    # and neither should be an idle default.
    "is_drop": -2.0,
    "is_item": 1.0,
    # Bending down in a fight, which is worth it only when you are
    # standing there empty-handed -- so the flat cost is real and
    # `pick_up_disarmed` is what pays for it, the same shape as
    # `is_wield` and `wield_reaches`.
    "is_pick_up": -5.0,
    "pick_up_disarmed": 12.0,
    # A summon acting on its own is free value; the action is the
    # owner's minor, which `_instinctives` has already charged for.
    "is_instinctive": 5.0,
    # The same shape as `is_charge`: an attack that is not a power, so the
    # flat `is_power` bonus has to be handed back or a command is six points
    # worse than the identical swing and nothing ever commands anything.
    #
    # **Level with `is_power`, not under it.** Priced at 4.0 first, to say
    # that the beast's line is smaller than its ranger's. Measuring it showed
    # that double-counts: `hit_chance` and `expected_hits` are computed from
    # the *beast* for this kind, so the weaker swing is already in the score
    # -- 0.40 against the ranger's 0.50 on the same enemy. Charging for it
    # twice left the command strictly dominated by every at-will the ranger
    # owns, in every board, which is how `is_wield` came to be offered all
    # fight and taken never. So the flat part says only "this spends a
    # standard to make one attack", which is true of both, and the features
    # decide which attack is the better one.
    "is_command": 6.0,
    # Enough to outweigh `is_power`, so a second stance has to be worth
    # more than an attack before the creature gives up the one it has.
    "swaps_stance": -8.0,
}


def _is_square(value: Any) -> bool:
    return isinstance(value, tuple) and len(value) == 2 and all(isinstance(v, int) for v in value)


def _opportunity_options(
    world: World, encounter: Encounter, actor: int, provoker: int
) -> list[Action]:
    """Opportunity attacks available against one provoker.

    A creature's opportunity attack is its melee basic attack unless it has a
    power that says otherwise, so this is every declared opportunity-action
    power that can reach, plus the basic.
    """
    from .components import Powers
    from .dsl import basic_options, candidates
    from .dsl import usable as is_usable

    out: list[Action] = []
    known = world.get(actor, Powers)
    if known is None:
        return out

    refs = [r for r in known.all if (p := get(r)) and p.action is ActionType.OPPORTUNITY]
    # The basic, plus whatever a feat has put in its place here. An option
    # beside it rather than a replacement for it, so both are scored.
    refs.extend(basic_options(world, actor, "opportunity"))

    for ref in dict.fromkeys(refs):
        p = get(ref)
        if p is None:
            continue
        ok, _ = is_usable(world, actor, p)
        if ok and provoker in candidates(world, actor, p):
            out.append(
                Action(kind="power", cost=ActionType.OPPORTUNITY, ref=ref, targets=(provoker,))
            )
    return out


# --------------------------------------------------------------------------
# Plumbing
# --------------------------------------------------------------------------


def install(
    world: World,
    encounter: Encounter,
    policies: dict[Team, Policy],
    *,
    default: Policy | None = None,
) -> None:
    """Route the engine's questions to whichever policy owns the creature.

    A team with no policy falls back to `default`, so a session can hand the
    characters to a human interface and leave the monsters on a policy
    without either side knowing about the other.
    """
    # Imported here rather than at the top because `doctrine` imports this module
    # for `features`, `WEIGHTS` and the helpers. There is one policy now, so this is
    # the only concrete one there is.
    from .doctrine import DoctrinePolicy

    fallback = default or DoctrinePolicy()

    def owner(eid: int) -> Policy:
        side = world.get(eid, Side)
        return policies.get(side.team, fallback) if side else fallback

    def decide(actor: int, kind: str, options: list[Any], prompt: str) -> Any:
        return owner(actor).decide(world, actor, kind, options, prompt)

    world.decider = decide

    def on_window(ev: OpportunityWindow) -> None:
        choice = owner(ev.actor).react(world, encounter, ev.actor, ev)
        if choice is not None:
            perform(world, encounter, ev.actor, choice)

    world.bus.on(OpportunityWindow, on_window)


def take_turn(
    world: World, encounter: Encounter, actor: int, policy: Policy, *, cap: int = 12
) -> None:
    """Play one creature's whole turn.

    `cap` stops a policy that keeps choosing a free action from spinning. It
    is a guard against a bug, not a rule, so hitting it is worth noticing.
    """
    from .actions import recharge

    recharge(world, actor)
    for _ in range(cap):
        options = legal(world, encounter, actor)
        choice = policy.act(world, encounter, actor, options)
        if choice.kind == "end":
            return
        if not perform(world, encounter, actor, choice):
            return
        if not alive(world, actor):
            return
