"""The `@power` decorator, the registry, and the runner.

A row is a header plus a body. The header is data -- it is what the interface
needs in order to list a power, grey it out with a reason, and draw its range
without running anything. The body is code, and the engine never inspects it,
only calls it.

Monster abilities use the same decorator. There is no second mechanism for
them, which is the README's rule that abilities share ops, kept by there
being only one kind of thing to share.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .cast import Cast
from .grid import Square, area_burst, blast, blast_placements, spread
from .monster_math import NORMAL
from .query import alive, allies, creatures, enemies, line_of_effect, squares
from .triggers import Trigger
from .types import Ability, ActionType, DamageType, Defense, Keyword, Usage

if TYPE_CHECKING:
    from .ecs import World

Body = Callable[[Cast], None]


# --------------------------------------------------------------------------
# Range
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Range:
    """How far a power reaches, and what shape it arrives in."""

    kind: str  # melee | ranged | close_burst | close_blast | area_burst | personal
    size: int = 1
    #: For an area burst: how far away the origin square may be.
    within: int = 10

    def __str__(self) -> str:
        return {
            "melee": f"Melee {self.size}",
            "ranged": f"Ranged {self.size}",
            "close_burst": f"Close burst {self.size}",
            "close_blast": f"Close blast {self.size}",
            "area_burst": f"Area burst {self.size} within {self.within}",
            "personal": "Personal",
        }[self.kind]


def Melee(n: int = 1) -> Range:
    return Range("melee", n)


def Ranged(n: int) -> Range:
    return Range("ranged", n)


def CloseBurst(n: int) -> Range:
    return Range("close_burst", n)


def CloseBlast(n: int) -> Range:
    return Range("close_blast", n)


def AreaBurst(n: int, within: int) -> Range:
    return Range("area_burst", n, within)


PERSONAL = Range("personal", 0)


# --------------------------------------------------------------------------
# Targets
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Target:
    """Who a power may be aimed at.

    `side` filters the pool, `count` caps it, and `pick` says whether the user
    chooses (a single-target power) or the power simply takes everyone in the
    area (a burst).
    """

    side: str = "enemy"  # enemy | ally | any | other | self
    count: int = 1
    #: True when the area decides, so every legal creature is a target.
    everyone: bool = False
    label: str = ""

    def __str__(self) -> str:
        if self.label:
            return self.label
        if self.side == "self":
            return "You"
        who = {"enemy": "creature", "ally": "ally", "any": "creature", "other": "creature"}[
            self.side
        ]
        if self.everyone:
            return f"Each {who} in the area"
        return f"One {who}" if self.count == 1 else f"Up to {self.count} {who}s"


ONE_CREATURE = Target("enemy", 1)
#: A power aimed at anybody at all. `ONE_CREATURE` is the *enemy* pool, so a
#: beneficial row pointed at it is unusable on the only creatures it is ever
#: meant for.
ANY_CREATURE = Target("any", 1)
ONE_ALLY = Target("ally", 1)
SELF = Target("self", 1)
EACH_ENEMY = Target("enemy", 99, everyone=True)
EACH_CREATURE = Target("any", 99, everyone=True)
#: Everyone in the area **except** the caster. A close burst declared with
#: `EACH_CREATURE` catches the creature standing at its centre, which is the
#: printed reading for some rows and plainly not for others.
EACH_OTHER = Target("other", 99, everyone=True)
EACH_ALLY = Target("ally", 99, everyone=True)
NO_TARGET = Target("self", 0, label="None")


def UpTo(n: int, side: str = "enemy") -> Target:
    return Target(side, n)


# --------------------------------------------------------------------------
# The row
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Attack:
    """A printed `Attack:` line.

    This sits in the header rather than in the body, and that is a deliberate
    choice with two payoffs. The body gets shorter -- `c.strike()` instead of
    repeating the numbers -- and a policy can work out the chance of hitting
    **without running the power**, which it otherwise could not, because a
    body is code and code cannot be read.

    A power whose attack bonus depends on the situation ignores this and
    calls `c.attack(...)` with whatever it worked out.

    A monster writes its line the other way round. A stat block prints a
    finished total -- `+6 vs. AC` -- with the creature's level already inside
    it, so `Attack(vs=AC, printed=6)` says exactly what the page says and the
    engine takes the level back out according to `world.scaling`. That keeps
    the two sides of a fight moving together when the treadmill is turned
    down, and it is less for an author to work out, not more.
    """

    #: A character's line names an ability. A monster's does not.
    ability: Ability | None = None
    vs: Defense = Defense.AC
    plus: int = 0
    #: A monster's finished attack bonus, level included, as printed.
    printed: int | None = None

    def bonus_for(self, world: World, actor: int, ref: str = "") -> int:
        """The bonus to roll with, under whatever scaling is in force."""
        from .cast import Cast
        from .components import Stats

        if self.printed is not None:
            stats = world.get(actor, Stats)
            return world.scaling.trim(self.printed, stats.level if stats else 1)
        if self.ability is None:
            raise ValueError("an Attack needs either an ability or a printed bonus")
        # `ref` matters: proficiency applies to a weapon power and not to an
        # implement one, and `_attack_bonus` reads the keywords off it.
        return Cast(world=world, me=actor, ref=ref)._attack_bonus(self.ability) + self.plus

    def __str__(self) -> str:
        if self.printed is not None:
            return f"{self.printed:+d} vs. {self.vs.value.upper()}"
        tail = f" {self.plus:+d}" if self.plus else ""
        name = self.ability.value.title() if self.ability else "?"
        return f"{name}{tail} vs. {self.vs.value.upper()}"


@dataclass(frozen=True)
class Damage:
    """A printed damage expression, in the header so it can be rescaled.

    The same move as `Attack`, for a sharper reason. Monster Manual 1 and 3
    are two different sets of maths, and converting between them is almost
    entirely a damage conversion -- see `engine/monster_math.py`. Damage
    written as a literal inside a body cannot be converted at all, so a row
    that wants to be convertible says its damage here and lets `c.hit()`
    apply it.

    A power doing something more involved still calls `c.damage(...)` in its
    body and simply is not rescalable. That is an honest limit and it will be
    the minority.

    Two payoffs beyond the conversion, both free: a policy can forecast
    damage instead of learning it from logs, and the card can print it.
    """

    dice: str = ""
    #: Added on top: a monster's flat bonus, or a character's ability
    #: modifier named as a string -- "str", "dex" -- resolved at use.
    bonus: str | int = 0
    dtype: DamageType = DamageType.UNTYPED
    #: `normal`, `limited` (encounter or recharge) or `minion`. MM3 scales
    #: the three differently.
    kind: str = NORMAL
    #: Half on a miss, which most weapon dailies say.
    half_on_miss: bool = False

    def __str__(self) -> str:
        tail = "" if not self.bonus else f" + {self.bonus}"
        kind = "" if self.dtype is DamageType.UNTYPED else f" {self.dtype.value}"
        return f"{self.dice}{tail}{kind} damage"


@dataclass
class Power:
    ref: str
    body: Body
    level: int = 1
    cls: str = ""
    usage: Usage = Usage.AT_WILL
    action: ActionType = ActionType.STANDARD
    reach: Range = field(default_factory=lambda: Melee(1))
    target: Target = ONE_CREATURE
    keywords: tuple[Keyword, ...] = ()
    #: The printed Attack line, when there is one. Read by policies.
    attack: Attack | None = None
    #: The printed damage, when the row is simple enough to declare it.
    damage: Damage | None = None
    #: A printed Requirement line, as a predicate on the caster.
    requires: Callable[[World, int], bool] | None = None
    requires_text: str = ""
    #: A printed Trigger line. Set for immediate and opportunity actions.
    trigger: str = ""
    #: The same line in a form the dispatcher can act on. With it the row is
    #: offered when its trigger happens; without it `trigger` is prose and
    #: nothing reads it. See `engine/triggers.py`.
    on: Trigger | None = None
    recharge: int = 0
    #: How many times per encounter. Two for the cleric's heal; one for
    #: everything else that is not at-will.
    uses: int = 1
    #: True when those uses may not be spent on the same round.
    once_per_round: bool = False
    #: Rows sharing a group share one budget. Several classes have a set of
    #: powers of which only one may be used per fight, and `uses` alone is
    #: per row and cannot say so.
    group: str = ""
    #: Set on the few rows whose printed text says they do not provoke,
    #: despite being ranged or area.
    no_provoke: bool = False
    #: True for a row that does nothing in a fight and is not supposed to --
    #: a cantrip that lights a torch, a ritual. Declared rather than
    #: inferred, so `scripts/audit.py` can tell "deliberately inert" from
    #: "written wrong", which is a distinction nothing else can draw.
    out_of_combat: bool = False

    @property
    def is_attack(self) -> bool:
        return self.target.side != "self" or self.target.count > 0

    @property
    def provokes(self) -> bool:
        """Does using this leave an opening for anyone standing next to you?

        Ranged and area powers do; melee and close powers do not. Taking aim
        at something across the room is what turns your back on the creature
        already in your face, and a wizard who can stand next to a brute and
        fire into the far rank with impunity is a different game.

        Derived from the range line rather than declared per row, so nothing
        has to remember it. A power that says otherwise sets `no_provoke`.
        """
        if self.no_provoke:
            return False
        return self.reach.kind in ("ranged", "area_burst")

    def hit_chance(self, world: World, actor: int, target: int) -> float:
        """Probability this power hits, from the declared attack line.

        Returns 0.5 when the power did not declare one -- an honest "no idea"
        that keeps a scorer from preferring undeclared powers or avoiding
        them.
        """
        if self.attack is None:
            return 0.5
        from .query import cover_between, defence, has_combat_advantage

        bonus = self.attack.bonus_for(world, actor, self.ref)
        if has_combat_advantage(world, actor, target):
            bonus += 2
        bonus -= int(cover_between(world, actor, target))
        need = defence(world, target, self.attack.vs) - bonus
        return min(0.95, max(0.05, (21 - need) / 20))

    def __str__(self) -> str:
        return f"{self.ref} ({self.usage.value}, {self.action.value}, {self.reach})"


REGISTRY: dict[str, Power] = {}


def power(
    ref: str,
    *,
    level: int = 1,
    cls: str = "",
    usage: Usage = Usage.AT_WILL,
    action: ActionType = ActionType.STANDARD,
    reach: Range | None = None,
    target: Target = ONE_CREATURE,
    keywords: Iterable[Keyword] = (),
    attack: Attack | None = None,
    damage: Damage | None = None,
    requires: Callable[[World, int], bool] | None = None,
    requires_text: str = "",
    trigger: str = "",
    on: Trigger | None = None,
    recharge: int = 0,
    uses: int = 1,
    once_per_round: bool = False,
    group: str = "",
    no_provoke: bool = False,
    out_of_combat: bool = False,
) -> Callable[[Body], Body]:
    """Declare one power or one monster ability.

    `ref` is the compendium id -- `p289`, or `m145a2` for a stat block's
    second ability. Never a name: the engine has no use for one, and the
    agent that wrote this function was never shown it.
    """

    def wrap(body: Body) -> Body:
        if ref in REGISTRY:
            raise ValueError(f"{ref} declared twice")
        REGISTRY[ref] = Power(
            ref=ref,
            body=body,
            level=level,
            cls=cls,
            usage=usage,
            action=action,
            reach=reach or Melee(1),
            target=target,
            keywords=tuple(keywords),
            attack=attack,
            damage=damage,
            requires=requires,
            requires_text=requires_text,
            trigger=trigger,
            on=on,
            recharge=recharge,
            uses=uses,
            once_per_round=once_per_round,
            group=group,
            no_provoke=no_provoke,
            out_of_combat=out_of_combat,
        )
        return body

    return wrap


def get(ref: str) -> Power | None:
    return REGISTRY.get(ref)


def declared() -> list[str]:
    return sorted(REGISTRY)


# --------------------------------------------------------------------------
# Working out what a power can be aimed at
# --------------------------------------------------------------------------


def area_of(world: World, actor: int, p: Power, origin: Square | None = None) -> frozenset[Square]:
    """The squares a power covers, given where its origin was placed.

    Clipped to the board. A ranged 20 power on a board sixteen squares wide
    otherwise reports a reach that runs off the edge, and an interface that
    highlights what it is given lights up squares that are not there.
    """
    mine = squares(world, actor)
    r = p.reach
    if r.kind == "close_burst":
        out = spread(mine, r.size)
    elif r.kind == "close_blast":
        aim = origin or next(iter(sorted(spread(mine, 1) - mine)))
        out = blast(mine, r.size, aim)
    elif r.kind == "area_burst":
        out = area_burst(origin or next(iter(sorted(mine))), r.size)
    elif r.kind in ("melee", "ranged"):
        out = spread(mine, r.size)
    else:
        out = frozenset(mine)
    return frozenset(sq for sq in out if world.grid.inside(sq))


def aim_points(world: World, actor: int, p: Power) -> list[Square]:
    """Every square this power can be pointed at.

    For a close blast these are the placement centres -- a blast 3 from a
    Medium creature gives the ring two squares out. For an area burst it is
    every square in range. Everything else aims at a creature rather than a
    square and gets an empty list.
    """
    mine = squares(world, actor)
    if p.reach.kind == "close_blast":
        return sorted(blast_placements(mine, p.reach.size))
    if p.reach.kind == "area_burst":
        return sorted(
            sq
            for sq in spread(mine, p.reach.within)
            if world.grid.inside(sq)
            and any(world.grid.line_of_effect(src, sq) for src in mine)
        )
    return []


def candidates(world: World, actor: int, p: Power, origin: Square | None = None) -> list[int]:
    """Everyone this power could legally be aimed at right now.

    An area power is checked at both ends. The **origin** has to be somewhere
    the power could be put: within its range, on the board, and with line of
    effect from the caster. Then each target needs line of effect **from the
    origin square**, not from the caster -- a burst thrown round a corner
    catches what is round the corner with it, not what the caster can see.

    Leaving the origin unchecked meant an "area burst 1 within 10" could be
    centred twenty squares away and still hit, which is a rule the printed
    range line states outright.
    """
    if p.target.side == "self" and p.target.count == 0:
        return []
    if p.target.side == "self":
        return [actor]
    pool = {
        "enemy": enemies(world, actor),
        "ally": [*allies(world, actor), actor],
        "any": creatures(world),
        "other": [c for c in creatures(world) if c != actor],
    }[p.target.side]

    aimed = origin is not None and p.reach.kind in ("area_burst", "close_blast")
    if aimed and origin not in aim_points(world, actor, p):
        return []

    area = area_of(world, actor, p, origin)
    if p.reach.kind == "area_burst" and origin is not None:
        return [
            c
            for c in pool
            if alive(world, c)
            and squares(world, c) & area
            and any(world.grid.line_of_effect(origin, sq) for sq in squares(world, c))
        ]
    return [
        c
        for c in pool
        if alive(world, c)
        and squares(world, c) & area
        and line_of_effect(world, actor, c)
    ]


def usable(world: World, actor: int, p: Power) -> tuple[bool, str]:
    """Can this power be used, and if not, why not?

    The reason is returned rather than logged, because the interface shows it
    on the greyed-out card and a player who cannot see why is playing blind.
    """
    from .components import Powers
    from .query import can_act

    if not can_act(world, actor):
        return False, "cannot act"
    powers = world.get(actor, Powers)
    if powers is not None:
        if p.ref not in powers.all:
            return False, "not known"
        if p.usage is not Usage.AT_WILL:
            used = powers.times(p.ref)
            if used >= p.uses:
                return False, "expended" if p.uses == 1 else f"used {used} of {p.uses}"
            if p.once_per_round and powers.last_round.get(p.ref) == world.round:
                return False, "already used this round"
            if p.group and _group_spent(world, actor, p):
                return False, f"one {p.group} power per encounter"
    if p.requires is not None and not p.requires(world, actor):
        return False, p.requires_text or "requirement not met"
    if p.is_attack and not _can_land(world, actor, p):
        return False, _no_targets(world, actor, p)
    return True, ""


def _can_land(world: World, actor: int, p: Power) -> bool:
    """Is there any way to aim this that catches somebody?

    For an area power that means trying the placements, not the default one.
    Asking `candidates` with no origin centres a blast on an arbitrary
    adjacent square, and a blast that happens to point away from everybody
    reported itself unusable while three creatures stood in range.
    """
    if p.reach.kind in ("area_burst", "close_blast"):
        return any(candidates(world, actor, p, aim) for aim in aim_points(world, actor, p))
    return bool(candidates(world, actor, p))


def _group_spent(world: World, actor: int, p: Power) -> bool:
    """Has a sibling of this row already been used this fight?"""
    from .components import Powers

    powers = world.get(actor, Powers)
    if powers is None:
        return False
    return any(
        other != p.ref
        and (sib := REGISTRY.get(other)) is not None
        and sib.group == p.group
        and powers.times(other) > 0
        for other in powers.all
    )


def _no_targets(world: World, actor: int, p: Power) -> str:
    """Say how far short the power fell, not merely that it did.

    "3 squares away" is actionable; "no targets" is not.
    """
    from .query import distance_between

    pool = enemies(world, actor) if p.target.side == "enemy" else creatures(world)
    live = [c for c in pool if alive(world, c)]
    if not live:
        return "no targets"
    nearest = min(distance_between(world, actor, c) for c in live)
    if p.reach.kind in ("melee", "close_burst", "close_blast"):
        return f"nearest is {nearest} squares away"
    return f"nearest is {nearest} squares away, range {p.reach.size}"


# --------------------------------------------------------------------------
# Running one
# --------------------------------------------------------------------------


def use(
    world: World,
    actor: int,
    ref: str,
    *,
    targets: list[int] | None = None,
    origin: Square | None = None,
    spend: bool = True,
    trigger: Any = None,
    opportunity: bool = False,
) -> bool:
    """Use a power. Returns False if it could not be used.

    The body runs once per target. A power with no targets runs once with
    `c.target` set to None, which is what a personal or zone-only power wants.

    `trigger` is the event being answered, for a row the dispatcher is
    offering. The body reads it as `c.trigger` and an interrupt stops it with
    `c.cancel()`.
    """
    from .components import Powers

    p = get(ref)
    if p is None:
        return False
    ok, _why = usable(world, actor, p)
    if not ok:
        return False

    if targets is not None:
        chosen = targets
    else:
        chosen, origin = _auto_targets(world, actor, p, origin)
    cast = Cast(
        world=world,
        me=actor,
        ref=ref,
        targets=list(chosen),
        origin=origin,
        trigger=trigger,
        opportunity=opportunity,
    )
    cast.used()

    if p.provokes and not _survive_provoking(world, actor, ref):
        # Stopped before it went off -- stunned by an interrupt, or killed.
        # The power is *not* spent: the action was lost, not used.
        return False

    if spend and p.usage is not Usage.AT_WILL:
        powers = world.get(actor, Powers)
        if powers is not None:
            powers.note_use(ref, world.round)

    if not chosen:
        p.body(cast)
        return True
    landed = False
    for i, t in enumerate(chosen):
        if not alive(world, t):
            continue
        cast.index = i
        cast.target = t
        cast.result = None
        p.body(cast)
        landed = landed or bool(cast.result and cast.result.hit)

    # Reliable: a daily that misses everything is not spent. The keyword was
    # declared and nothing read it, so the two fighter dailies that carry it
    # were costing a use per miss -- which is the entire point of the word.
    if spend and Keyword.RELIABLE in p.keywords and not landed:
        powers = world.get(actor, Powers)
        if powers is not None:
            powers.unuse(ref)
    return True


def _survive_provoking(world: World, actor: int, ref: str) -> bool:
    """Open an opportunity window for everyone standing next to the caster.

    Returns False if the caster cannot finish what it started -- an
    opportunity attack interrupts, so one that stuns or drops the caster
    stops the power rather than merely hurting them on the way.
    """
    from .components import Position
    from .events import OpportunityWindow
    from .grid import spread
    from .query import can_act
    from .query import squares as occupies

    reach = spread(occupies(world, actor), 1)
    for foe in sorted(enemies(world, actor)):
        pos = world.get(foe, Position)
        if pos is not None and pos.squares & reach:
            world.bus.emit(
                OpportunityWindow(actor=foe, provoker=actor, why=f"{ref} is a ranged power")
            )
    return can_act(world, actor)


def _auto_targets(
    world: World, actor: int, p: Power, origin: Square | None
) -> tuple[list[int], Square | None]:
    """Who this power lands on when the caller did not say, and where it aimed.

    An area power with no origin would otherwise centre on the caster's own
    square, which catches almost nothing and is never what was meant. The
    interface and any policy always pass an origin; this is the default for
    everything else, and it aims where the power does most.

    The aim comes back with the targets, and for a while it did not. The
    caster's `origin` stayed None while the targets were the ones standing
    round the square this picked, so a burst that leaves a zone behind
    dropped the zone on the caster's own feet and the damage somewhere else
    entirely. Two answers to "where is this power" is one too many.
    """
    if origin is None and p.reach.kind in ("area_burst", "close_blast"):
        best: list[int] = []
        chosen: Square | None = None
        for aim in aim_points(world, actor, p):
            hit = candidates(world, actor, p, aim)
            if len(hit) > len(best):
                best, chosen = hit, aim
        if best:
            return (best if p.target.everyone else best[: p.target.count]), chosen
    pool = candidates(world, actor, p, origin)
    if p.target.everyone:
        return pool, origin
    return pool[: p.target.count], origin
