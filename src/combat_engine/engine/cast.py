"""`Cast` -- what a power body is written against.

This is the whole authoring surface. If translating a printed power costs
more than a few lines, the missing thing belongs here as a method, not in a
registry of ops somewhere else. Adding one is cheap and affects nothing that
already works, which is the point.

The body is **called once per target**. `c.target` is whichever target this
call is for, and `c.first` is True on the first of them, which is where the
once-per-power part of a printed power goes. A power with no targets is
called exactly once with `c.target` set to None.

Everything that reads "the target" defaults to `c.target`, and everything
takes `on=` to say otherwise. That default is what makes the common case one
line and the unusual case still one line.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .components import Gear, Health, Mod, Mods, Position, Stats
from .durations import Effect, When
from .events import Event, Note, PowerUsed
from .grid import Square, spread
from .movement import forced, shift, teleport, walk
from .query import (
    adjacent,
    alive,
    allies,
    creatures,
    distance_between,
    enemies,
    is_,
    line_of_effect,
    squares,
)
from .resolve import AttackResult, attack, deal_damage, heal, temp_hp
from .rng import average
from .types import Ability, Condition, DamageType, Defense, Forced, Relation, Window

if TYPE_CHECKING:
    from .ecs import World


@dataclass
class Cast:
    """One use of one power, aimed at one target."""

    world: World
    me: int
    ref: str
    targets: list[int] = field(default_factory=list)
    target: int | None = None
    index: int = 0
    #: The most recent attack this cast rolled. `c.hit` reads off it.
    result: AttackResult | None = None

    # -- who and where -------------------------------------------------------

    @property
    def first(self) -> bool:
        """True on the first target. Where a once-per-power line goes."""
        return self.index == 0

    @property
    def last(self) -> bool:
        return self.index == max(0, len(self.targets) - 1)

    @property
    def here(self) -> Square:
        pos = self.world.get(self.me, Position)
        return pos.square if pos else (0, 0)

    @property
    def there(self) -> Square:
        pos = self.world.get(self.target, Position) if self.target else None
        return pos.square if pos else self.here

    def _who(self, on: int | None) -> int | None:
        return self.target if on is None else on

    def allies(self) -> list[int]:
        return allies(self.world, self.me)

    def enemies(self) -> list[int]:
        return enemies(self.world, self.me)

    def within(self, radius: int, *, of: int | None = None, side: str = "any") -> list[int]:
        """Creatures within `radius` squares. `side` is any, enemy, ally or other."""
        origin = self.me if of is None else of
        area = spread(squares(self.world, origin), radius)
        pool = {
            "any": creatures(self.world),
            "enemy": enemies(self.world, self.me),
            "ally": [*allies(self.world, self.me), self.me],
            "other": [c for c in creatures(self.world) if c != origin],
        }[side]
        return [c for c in pool if squares(self.world, c) & area and alive(self.world, c)]

    def in_squares(self, area: Iterable[Square], *, side: str = "any") -> list[int]:
        space = frozenset(area)
        pool = {
            "any": creatures(self.world),
            "enemy": enemies(self.world, self.me),
            "ally": [*allies(self.world, self.me), self.me],
            "other": [c for c in creatures(self.world) if c != self.me],
        }[side]
        return [c for c in pool if squares(self.world, c) & space and alive(self.world, c)]

    def distance(self, to: int | None = None) -> int:
        other = self._who(to)
        return 99 if other is None else distance_between(self.world, self.me, other)

    def adjacent(self, to: int | None = None) -> bool:
        other = self._who(to)
        return other is not None and adjacent(self.world, self.me, other)

    def can_see(self, to: int | None = None) -> bool:
        other = self._who(to)
        return other is not None and line_of_effect(self.world, self.me, other)

    def is_(self, condition: Condition, on: int | None = None) -> bool:
        who = self._who(on)
        return who is not None and is_(self.world, who, condition)

    def bloodied(self, on: int | None = None) -> bool:
        who = self._who(on)
        health = self.world.get(who, Health) if who else None
        return health is not None and health.bloodied

    # -- the attacker's numbers ---------------------------------------------

    @property
    def stats(self) -> Stats:
        return self.world.need(self.me, Stats)

    def mod(self, a: Ability) -> int:
        return self.stats.mod(a)

    def _attack_bonus(self, a: Ability) -> int:
        """Half level, the ability modifier, and the weapon if there is one.

        A printed power says "Strength vs. AC" and means all three, so `c.str_`
        means all three too. `c.str_mod` is the bare modifier, which is what
        the damage line wants.
        """
        bonus = self.stats.half_level + self.stats.mod(a)
        gear = self.world.get(self.me, Gear)
        if gear is not None and gear.main is not None:
            bonus += gear.main.proficiency
        return bonus

    @property
    def str_(self) -> int:
        return self._attack_bonus(Ability.STR)

    @property
    def con_(self) -> int:
        return self._attack_bonus(Ability.CON)

    @property
    def dex_(self) -> int:
        return self._attack_bonus(Ability.DEX)

    @property
    def int_(self) -> int:
        return self._attack_bonus(Ability.INT)

    @property
    def wis_(self) -> int:
        return self._attack_bonus(Ability.WIS)

    @property
    def cha_(self) -> int:
        return self._attack_bonus(Ability.CHA)

    @property
    def str_mod(self) -> int:
        return self.stats.mod(Ability.STR)

    @property
    def con_mod(self) -> int:
        return self.stats.mod(Ability.CON)

    @property
    def dex_mod(self) -> int:
        return self.stats.mod(Ability.DEX)

    @property
    def int_mod(self) -> int:
        return self.stats.mod(Ability.INT)

    @property
    def wis_mod(self) -> int:
        return self.stats.mod(Ability.WIS)

    @property
    def cha_mod(self) -> int:
        return self.stats.mod(Ability.CHA)

    @property
    def level(self) -> int:
        return self.stats.level

    def w(self, count: int = 1) -> str:
        """`count`[W]: the wielded weapon's damage dice, that many times."""
        gear = self.world.get(self.me, Gear)
        weapon = gear.main if gear else None
        if weapon is None:
            return f"{count}d4"
        n, _, faces = weapon.damage.partition("d")
        return f"{int(n or 1) * count}d{faces}"

    def wielding(self, prop: str) -> bool:
        gear = self.world.get(self.me, Gear)
        if gear is None:
            return False
        if prop == "shield":
            return gear.shield
        weapon = gear.main
        return weapon is not None and (prop in weapon.properties or weapon.group == prop)

    # -- attacking -----------------------------------------------------------

    def strike(self, *, on: int | None = None, advantage: bool | None = None) -> AttackResult:
        """Roll the attack the header declared.

        The overwhelmingly common case: the printed `Attack:` line is a plain
        ability against a defence, it went in the header where a policy can
        read it, and the body just says "roll it".
        """
        from .dsl import get

        p = get(self.ref)
        if p is None or p.attack is None:
            raise ValueError(f"{self.ref} declared no attack line; call c.attack(...)")
        bonus = self._attack_bonus(p.attack.ability) + p.attack.plus
        return self.attack(bonus, p.attack.vs, on=on, advantage=advantage)

    def attack(
        self,
        bonus: int,
        vs: Defense,
        *,
        on: int | None = None,
        advantage: bool | None = None,
    ) -> AttackResult:
        who = self._who(on)
        if who is None:
            return AttackResult()
        self.result = attack(
            self.world, self.me, who, bonus, vs, self.ref, advantage=advantage
        )
        return self.result

    @property
    def hit(self) -> bool:
        return self.result is not None and self.result.hit

    @property
    def crit(self) -> bool:
        return self.result is not None and self.result.critical

    # -- damage and healing --------------------------------------------------

    def damage(
        self,
        dice: str | int = 0,
        bonus: int = 0,
        *,
        dtype: DamageType = DamageType.UNTYPED,
        on: int | None = None,
        detail: str = "",
    ) -> int:
        """Roll and apply damage. A critical hit maxes the dice, as printed."""
        who = self._who(on)
        if who is None:
            return 0
        if self.crit:
            amount = _max_of(dice) + bonus
        else:
            amount = self.world.rng.roll(dice).total + bonus if dice else bonus
        return deal_damage(
            self.world, self.me, who, amount, dtype, detail or self.ref
        )

    def half_damage(
        self,
        dice: str | int = 0,
        bonus: int = 0,
        *,
        dtype: DamageType = DamageType.UNTYPED,
        on: int | None = None,
    ) -> int:
        """"Miss: half damage" -- rolled, then halved, as the rule reads."""
        who = self._who(on)
        if who is None:
            return 0
        amount = (self.world.rng.roll(dice).total + bonus) // 2 if dice else bonus // 2
        return deal_damage(self.world, self.me, who, amount, dtype, f"{self.ref} (half)")

    def flat(self, amount: int, *, dtype: DamageType = DamageType.UNTYPED,
             on: int | None = None) -> int:
        who = self._who(on)
        return 0 if who is None else deal_damage(self.world, self.me, who, amount, dtype, self.ref)

    def heal(self, amount: int, *, on: int | None = None) -> int:
        who = self._who(on)
        return 0 if who is None else heal(self.world, self.me, who, amount)

    def surge(self, *, on: int | None = None, bonus: int = 0) -> int:
        """Spend a healing surge: a quarter of maximum hit points."""
        who = self._who(on)
        health = self.world.get(who, Health) if who else None
        if health is None or health.surges <= 0:
            return 0
        health.surges -= 1
        return heal(self.world, self.me, who, health.surge_value + bonus)

    def temp_hp(self, amount: int, *, on: int | None = None) -> None:
        who = self._who(on)
        if who is not None:
            temp_hp(self.world, self.me, who, amount)

    def ongoing(
        self,
        amount: int,
        dtype: DamageType = DamageType.UNTYPED,
        *,
        on: int | None = None,
        until: When = When.SAVE_ENDS,
    ) -> Effect | None:
        who = self._who(on)
        if who is None:
            return None
        return self.world.effects.apply(
            who, self.me, until, label=f"ongoing {amount}", ongoing=(amount, dtype)
        )

    # -- moving things around ------------------------------------------------

    def push(self, squares_: int, *, on: int | None = None,
             anchor: Square | None = None) -> int:
        who = self._who(on)
        return 0 if who is None else forced(
            self.world, self.me, who, Forced.PUSH, squares_, anchor=anchor
        )

    def pull(self, squares_: int, *, on: int | None = None,
             anchor: Square | None = None) -> int:
        who = self._who(on)
        return 0 if who is None else forced(
            self.world, self.me, who, Forced.PULL, squares_, anchor=anchor
        )

    def slide(self, squares_: int, *, on: int | None = None,
              anchor: Square | None = None) -> int:
        who = self._who(on)
        return 0 if who is None else forced(
            self.world, self.me, who, Forced.SLIDE, squares_, anchor=anchor
        )

    def shift(self, squares_: int = 1, *, who: int | None = None) -> bool:
        """Shift, choosing the destination through the world's decider."""
        mover = self.me if who is None else who
        options = self.world.reachable_squares(mover, squares_)
        if not options:
            return False
        dest = self.world.decide(mover, "shift", options, f"{self.ref}: shift {squares_}")
        return shift(self.world, mover, dest)

    def move(self, squares_: int, *, who: int | None = None) -> int:
        mover = self.me if who is None else who
        paths = self.world.reachable_paths(mover, squares_)
        if not paths:
            return 0
        dest = self.world.decide(mover, "move", sorted(paths), f"{self.ref}: move {squares_}")
        return walk(self.world, mover, paths[dest])

    def teleport(self, squares_: int, *, who: int | None = None) -> bool:
        mover = self.me if who is None else who
        origin = squares(self.world, mover)
        options = [
            sq
            for sq in spread(origin, squares_)
            if self.world.grid.passable(sq) and self.world.grid.occupant(sq) in (None, mover)
        ]
        if not options:
            return False
        dest = self.world.decide(mover, "teleport", sorted(options), f"{self.ref}: teleport")
        return teleport(self.world, mover, dest)

    # -- conditions and modifiers -------------------------------------------

    def condition(
        self,
        *conditions: Condition,
        until: When = When.EONT,
        on: int | None = None,
        save_mod: int = 0,
        escalate: Callable[[Effect], None] | None = None,
    ) -> Effect | None:
        who = self._who(on)
        if who is None:
            return None
        return self.world.effects.apply(
            who,
            self.me,
            until,
            label=self.ref,
            conditions=conditions,
            save_mod=save_mod,
            escalate=escalate,
        )

    def prone(self, *, on: int | None = None) -> Effect | None:
        """Knocked prone. It lasts until the creature stands up, not until a
        turn boundary, so it hangs on the encounter clock."""
        return self.condition(Condition.PRONE, until=When.ENCOUNTER, on=on)

    def dazed(self, *, until: When = When.EONT, on: int | None = None) -> Effect | None:
        return self.condition(Condition.DAZED, until=until, on=on)

    def stunned(self, *, until: When = When.SAVE_ENDS, on: int | None = None) -> Effect | None:
        return self.condition(Condition.STUNNED, until=until, on=on)

    def slowed(self, *, until: When = When.EONT, on: int | None = None) -> Effect | None:
        return self.condition(Condition.SLOWED, until=until, on=on)

    def immobilized(self, *, until: When = When.EONT, on: int | None = None) -> Effect | None:
        return self.condition(Condition.IMMOBILIZED, until=until, on=on)

    def weakened(self, *, until: When = When.EONT, on: int | None = None) -> Effect | None:
        return self.condition(Condition.WEAKENED, until=until, on=on)

    def blinded(self, *, until: When = When.EONT, on: int | None = None) -> Effect | None:
        return self.condition(Condition.BLINDED, until=until, on=on)

    def unconscious(self, *, until: When = When.SAVE_ENDS, on: int | None = None) -> Effect | None:
        return self.condition(Condition.UNCONSCIOUS, until=until, on=on)

    def mark(self, *, until: When = When.EONT, on: int | None = None) -> Effect | None:
        who = self._who(on)
        if who is None:
            return None
        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} mark",
            relations=[(Relation.MARKED_BY, self.me, who)],
        )

    def grab(self, *, on: int | None = None) -> Effect | None:
        who = self._who(on)
        if who is None:
            return None
        return self.world.effects.apply(
            who, self.me, When.ENCOUNTER, label=f"{self.ref} grab",
            relations=[(Relation.GRABBED_BY, self.me, who)],
        )

    def grants_advantage(self, *, until: When = When.EONT, on: int | None = None) -> Effect | None:
        """The target grants combat advantage to the attacker specifically."""
        who = self._who(on)
        if who is None:
            return None
        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} advantage",
            relations=[(Relation.GRANTS_CA_TO, who, self.me)],
        )

    def bonus(
        self,
        what: str | Defense,
        value: int,
        *,
        until: When = When.EONT,
        on: int | None = None,
        kind: str = "power",
        when: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Effect | None:
        """A numeric modifier with a duration.

        `what` is `attack`, `damage`, `save`, `speed` or a defence. `when` is
        an optional gate -- "only against the creature you marked", "only
        while you have a shield" -- written as a lambda right here rather than
        as a new kind of op.
        """
        who = self._who(on)
        if who is None:
            return None
        key = what.value if isinstance(what, Defense) else what
        mod = Mod(what=key, value=value, kind=kind, when=when, label=self.ref)
        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} {key}{value:+d}", mods=[(who, mod)]
        )

    def penalty(self, what: str | Defense, value: int, **kw: Any) -> Effect | None:
        return self.bonus(what, -abs(value), kind="untyped", **kw)

    # -- standing arrangements -----------------------------------------------

    def watch(
        self,
        event: type[Event],
        fn: Callable[[Any], None],
        *,
        until: When = When.EONT,
        window: Window = Window.AFTER,
        on: int | None = None,
        label: str = "",
    ) -> Effect:
        """Arm a trigger that expires with a duration.

        "Whenever an ally within 5 squares is hit, ..." is this plus an `if`
        in `fn`. The subscription is owned by the effect, so when the duration
        runs out the trigger goes with it and nothing has to remember.
        """
        who = self._who(on) or self.me
        sub = self.world.bus.on(event, fn, window=window, owner=self.me)
        return self.world.effects.apply(
            who, self.me, until, label=label or f"{self.ref} trigger", subs=[sub]
        )

    # -- areas ---------------------------------------------------------------

    def zone(
        self,
        area: Iterable[Square],
        *,
        label: str = "",
        until: When = When.EONT,
        difficult: bool = False,
    ) -> int:
        return self.world.zones.create(
            self.me, label or self.ref, frozenset(area), until, difficult=difficult
        )

    def aura(self, radius: int, *, label: str = "", until: When = When.ENCOUNTER) -> int:
        return self.world.zones.aura(self.me, label or self.ref, radius, until)

    # -- choices and commentary ---------------------------------------------

    def choose[T](self, options: list[T], prompt: str = "") -> T | None:
        if not options:
            return None
        return self.world.decide(self.me, "choose", options, prompt or self.ref)

    def note(self, text: str) -> None:
        self.world.bus.emit(Note(text=text))

    def used(self) -> None:
        self.world.bus.emit(
            PowerUsed(actor=self.me, power=self.ref, targets=list(self.targets))
        )

    # -- reading modifiers back ---------------------------------------------

    def total(self, what: str, on: int | None = None) -> int:
        who = self._who(on) or self.me
        mods = self.world.get(who, Mods)
        return mods.total(what) if mods else 0


def _max_of(dice: str | int) -> int:
    """Every die showing its highest face. What a critical hit deals."""
    if isinstance(dice, int):
        return dice
    n, _, rest = dice.partition("d")
    faces, sign, tail = rest.partition("+")
    if not sign:
        faces, sign, tail = rest.partition("-")
    count = int(n or 1)
    top = count * int(faces)
    if sign == "+":
        top += int(tail)
    elif sign == "-":
        top -= int(tail)
    return top


def expected(dice: str | int, bonus: int = 0) -> float:
    return average(dice) + bonus
