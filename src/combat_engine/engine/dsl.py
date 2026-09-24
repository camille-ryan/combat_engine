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
from typing import TYPE_CHECKING

from .cast import Cast
from .grid import Square, area_burst, blast, blast_placements, spread
from .query import alive, allies, creatures, enemies, line_of_effect, squares
from .types import Ability, ActionType, Defense, Keyword, Usage

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
ONE_ALLY = Target("ally", 1)
SELF = Target("self", 1)
EACH_ENEMY = Target("enemy", 99, everyone=True)
EACH_CREATURE = Target("any", 99, everyone=True)
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
    #: A printed Requirement line, as a predicate on the caster.
    requires: Callable[[World, int], bool] | None = None
    requires_text: str = ""
    #: A printed Trigger line. Set for immediate and opportunity actions.
    trigger: str = ""
    recharge: int = 0

    @property
    def is_attack(self) -> bool:
        return self.target.side != "self" or self.target.count > 0

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
    requires: Callable[[World, int], bool] | None = None,
    requires_text: str = "",
    trigger: str = "",
    recharge: int = 0,
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
            requires=requires,
            requires_text=requires_text,
            trigger=trigger,
            recharge=recharge,
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
    """The squares a power covers, given where its origin was placed."""
    mine = squares(world, actor)
    r = p.reach
    if r.kind == "close_burst":
        return spread(mine, r.size)
    if r.kind == "close_blast":
        aim = origin or next(iter(sorted(spread(mine, 1) - mine)))
        return blast(mine, r.size, aim)
    if r.kind == "area_burst":
        return area_burst(origin or next(iter(sorted(mine))), r.size)
    if r.kind in ("melee", "ranged"):
        return spread(mine, r.size)
    return frozenset(mine)


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
    """Everyone this power could legally be aimed at right now."""
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
    area = area_of(world, actor, p, origin)
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
    if powers is not None and not powers.available(p.ref):
        return False, "expended" if p.ref in powers.spent else "not known"
    if p.requires is not None and not p.requires(world, actor):
        return False, p.requires_text or "requirement not met"
    if p.is_attack and not candidates(world, actor, p):
        return False, _no_targets(world, actor, p)
    return True, ""


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
) -> bool:
    """Use a power. Returns False if it could not be used.

    The body runs once per target. A power with no targets runs once with
    `c.target` set to None, which is what a personal or zone-only power wants.
    """
    from .components import Powers

    p = get(ref)
    if p is None:
        return False
    ok, _why = usable(world, actor, p)
    if not ok:
        return False

    chosen = targets if targets is not None else _auto_targets(world, actor, p, origin)
    cast = Cast(world=world, me=actor, ref=ref, targets=list(chosen))
    cast.used()

    if spend and p.usage is not Usage.AT_WILL:
        powers = world.get(actor, Powers)
        if powers is not None:
            powers.spent.add(ref)

    if not chosen:
        p.body(cast)
        return True
    for i, t in enumerate(chosen):
        if not alive(world, t):
            continue
        cast.index = i
        cast.target = t
        cast.result = None
        p.body(cast)
    return True


def _auto_targets(world: World, actor: int, p: Power, origin: Square | None) -> list[int]:
    """Who this power lands on when the caller did not say.

    An area power with no origin would otherwise centre on the caster's own
    square, which catches almost nothing and is never what was meant. The
    interface and any policy always pass an origin; this is the default for
    everything else, and it aims where the power does most.
    """
    if origin is None and p.reach.kind in ("area_burst", "close_blast"):
        best: list[int] = []
        for aim in aim_points(world, actor, p):
            hit = candidates(world, actor, p, aim)
            if len(hit) > len(best):
                best = hit
        if best:
            return best if p.target.everyone else best[: p.target.count]
    pool = candidates(world, actor, p, origin)
    if p.target.everyone:
        return pool
    return pool[: p.target.count]
