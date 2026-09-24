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
from .grid import distance as _distance
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
from .types import (
    Ability,
    Condition,
    DamageType,
    Defense,
    Forced,
    Keyword,
    Relation,
    Window,
)
from .zones import Zone

if TYPE_CHECKING:
    from .dsl import Damage
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
    #: Where an area power was aimed. None for everything else.
    origin: Square | None = None
    #: The most recent attack this cast rolled. `c.landed` reads off it.
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

    def wounded(self, on: int | None = None) -> bool:
        """Has lost any hit points at all. What a healing power looks for."""
        who = self._who(on)
        health = self.world.get(who, Health) if who else None
        return health is not None and health.hp < health.max_hp

    def kinds_of(self, on: int | None = None) -> frozenset[str]:
        """A creature's type words: undead, goblin, beast, natural, and so on.

        Off the stat block's own type line. A power that reads "each undead
        creature in the burst" asks this; a character has none, which is the
        right answer for one.
        """
        from .components import Ident

        who = self._who(on)
        ident = self.world.get(who, Ident) if who else None
        if ident is None or not ident.ref.startswith("m"):
            return frozenset()
        from combat_engine.content.loader import load

        try:
            import json

            row = load(ident.ref).row
        except Exception:  # a ref with no row is simply typeless
            return frozenset()
        words = set(json.loads(row.get("keywords") or "[]"))
        for column in ("kind", "origin"):
            if row.get(column):
                words.add(row[column])
        # The type line parenthesises its subtypes -- "(undead)" -- and a
        # power asking whether something is undead should not have to know.
        return frozenset(w.strip("() ,.").lower() for w in words if w.strip("() ,."))

    def is_kind(self, word: str, on: int | None = None) -> bool:
        """Is this creature of that type? `c.is_kind("undead")`."""
        return word.lower() in self.kinds_of(on)

    def roll(self, dice: str | int) -> int:
        """Roll dice and get the number, without applying it to anybody.

        `c.damage` was the only documented way to turn dice into a total and
        it also deals them, so a power wanting a number for something else
        had to reach past the API.
        """
        return self.world.rng.roll(dice).total

    def marked(self, on: int | None = None, *, by: int | None = None) -> bool:
        """Is that creature marked -- **by you**, unless told otherwise?

        `c.is_(Condition.MARKED)` is true of a mark laid by anybody, which
        quietly pays a paladin's bonus off the fighter's mark.
        """
        who = self._who(on)
        if who is None:
            return False
        return self.world.relations.holds(Relation.MARKED_BY, self.me if by is None else by, who)

    def save(self, *, on: int | None = None, bonus: int = 0) -> bool:
        """Roll a saving throw now against one save-ends effect.

        A few powers hand somebody an extra save out of turn. Returns True
        if something was shaken off.
        """
        who = self._who(on)
        if who is None:
            return False
        for effect in self.world.effects.of(who):
            if effect.when is When.SAVE_ENDS:
                effect.save_mod += bonus
                self.world.effects.save(effect)
                return effect.ended
        return False

    def surge_value(self, of: int | None = None) -> int:
        """A quarter of that creature's maximum, which is what a surge heals."""
        who = self._who(of) or self.me
        health = self.world.get(who, Health)
        return health.surge_value if health else 0

    def spend_surge(self, *, on: int | None = None) -> bool:
        """Spend a surge and gain nothing for it.

        The paladin's touch reads exactly that: the paladin pays and somebody
        else is healed.
        """
        who = self._who(on) or self.me
        health = self.world.get(who, Health)
        if health is None or health.surges <= 0:
            return False
        health.surges -= 1
        return True

    def size_of(self, on: int | None = None):  # noqa: ANN201
        from .components import Position
        from .types import Size

        pos = self.world.get(self._who(on), Position) if self._who(on) else None
        return pos.size if pos else Size.MEDIUM

    def turn_of(self) -> int | None:
        """Whose turn it is, for a trigger that cares."""
        return self.world.turn

    def effect(
        self, label: str, *, until: When = When.SAVE_ENDS, on: int | None = None
    ) -> Effect | None:
        """A named hold with no mechanical content of its own.

        For the rows that say "the target is subjected to <something> (save
        ends)" and then describe what that lets *you* do. The effect exists
        so it can be seen, saved against, and hung things on.
        """
        who = self._who(on)
        if who is None:
            return None
        return self.world.effects.apply(who, self.me, until, label=label)

    def invisible(self, *, to: int | None = None, until: When = When.SONT) -> Effect | None:
        """You cannot be seen -- by one creature, or by everybody.

        Held as `HIDDEN_FROM`, which `query.has_combat_advantage` already
        reads, so being unseen grants the advantage it should.
        """
        watchers = [to] if to is not None else self.enemies()
        pairs = [(Relation.HIDDEN_FROM, self.me, w) for w in watchers if w is not None]
        if not pairs:
            return None
        return self.world.effects.apply(
            self.me, self.me, until, label=f"{self.ref} unseen", relations=pairs
        )

    def speed_of(self, who: int | None = None) -> int:
        from .query import speed

        return speed(self.world, self._who(who) or self.me)

    # -- the attacker's numbers ---------------------------------------------

    @property
    def stats(self) -> Stats:
        return self.world.need(self.me, Stats)

    def mod(self, a: Ability) -> int:
        return self.stats.mod(a)

    def _attack_bonus(self, a: Ability) -> int:
        """Half level, the ability modifier, and the weapon where it counts.

        A printed power says "Strength vs. AC" and means all three, so `c.str_`
        means all three too. `c.str_mod` is the bare modifier, which is what
        the damage line wants.

        Proficiency only applies to a **weapon** power. A cleric holding a
        mace and casting an implement attack does not add the mace to it, and
        adding it anyway is invisible -- every ranged cleric attack simply
        runs two points hot for the life of the project.
        """
        bonus = self.world.scaling.pc(self.stats.level) + self.stats.mod(a)
        p = self._declared()
        weapon_power = p is None or Keyword.WEAPON in p.keywords
        gear = self.world.get(self.me, Gear)
        if weapon_power and gear is not None:
            ranged = p is not None and Keyword.RANGED in p.keywords
            weapon = (gear.ranged if ranged and gear.ranged else gear.main)
            if weapon is not None:
                bonus += weapon.proficiency
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

    def w(self, count: int = 1, *, hand: str = "main", ranged: bool | None = None) -> str:
        """`count`[W]: the wielded weapon's damage dice, that many times.

        A ranged power rolls the ranged weapon, where the creature has one.
        A ranger carries a blade and a bow, and firing the bow while rolling
        the blade's dice is wrong in a way nothing would ever report.
        """
        gear = self.world.get(self.me, Gear)
        if gear is None:
            return f"{count}d4"
        weapon = gear.off if hand == "off" else gear.main
        p = self._declared()
        fires = ranged if ranged is not None else (
            p is not None and Keyword.RANGED in p.keywords
        )
        if fires and gear.ranged is not None:
            weapon = gear.ranged
        if weapon is None:
            return f"{count}d4"
        n, _, faces = weapon.damage.partition("d")
        return f"{int(n or 1) * count}d{faces}"

    def _declared(self):  # noqa: ANN202
        from .dsl import get

        return get(self.ref)

    def wielding(self, prop: str) -> bool:
        """Does the caster meet a printed Requirement line?

        `"shield"`, `"two-weapon"`, a weapon group like `"light blade"`, or
        a weapon property like `"two-handed"`.
        """
        gear = self.world.get(self.me, Gear)
        if gear is None:
            return False
        if prop == "shield":
            return gear.shield
        if prop in ("two-weapon", "two melee weapons"):
            return gear.two_weapon
        weapon = gear.main
        return weapon is not None and (prop in weapon.properties or weapon.group == prop)

    # -- attacking -----------------------------------------------------------

    def strike(
        self, *, on: int | None = None, advantage: bool | None = None, plus: int = 0
    ) -> AttackResult:
        """Roll the attack the header declared.

        The overwhelmingly common case: the printed `Attack:` line is a plain
        ability against a defence, it went in the header where a policy can
        read it, and the body just says "roll it".
        """
        from .dsl import get

        p = get(self.ref)
        if p is None or p.attack is None:
            raise ValueError(f"{self.ref} declared no attack line; call c.attack(...)")
        return self.attack(
            p.attack.bonus_for(self.world, self.me, self.ref) + plus,
            p.attack.vs,
            on=on,
            advantage=advantage,
        )

    def grant_attack(
        self,
        who: int,
        *,
        on: int | None = None,
        ref: str = "",
        damage_bonus: int = 0,
        attack_bonus: int = 0,
    ) -> bool:
        """Let somebody else make an attack, now, out of turn.

        The warlord's entire reason to exist, and a thing `Cast` could not
        say at all: `c.strike()` always rolls for the caster. Without this
        the class's signature row has no content whatsoever.

        `ref` defaults to that creature's own basic attack, so a monster
        whose basic has been replaced attacks with the right thing.
        """
        from .components import Powers
        from .dsl import use

        target = self._who(on)
        if target is None or not alive(self.world, who):
            return False
        known = self.world.get(who, Powers)
        from .basic import MELEE

        chosen = ref or (known.basic if known else MELEE) or MELEE

        granted = []
        if damage_bonus:
            granted.append(
                self.world.effects.apply(
                    who, self.me, When.EOT,
                    label=f"{self.ref} granted damage",
                    mods=[(who, Mod(what="damage", value=damage_bonus, kind="power"))],
                )
            )
        if attack_bonus:
            granted.append(
                self.world.effects.apply(
                    who, self.me, When.EOT,
                    label=f"{self.ref} granted attack",
                    mods=[(who, Mod(what="attack", value=attack_bonus, kind="power"))],
                )
            )
        try:
            return use(self.world, who, chosen, targets=[target], spend=False)
        finally:
            for effect in granted:
                if effect is not None:
                    self.world.effects.end(effect, "the granted attack is over")

    def provoke(self, attacker: int, *, on: int | None = None, why: str = "") -> None:
        """Open an opportunity window for a named creature against a target.

        A handful of rows say "it provokes an opportunity attack from an ally
        of your choice". The engine already has the window and a controller
        to answer it; this is the door in.
        """
        from .events import OpportunityWindow

        victim = self._who(on)
        if victim is None:
            return
        self.world.bus.emit(
            OpportunityWindow(actor=attacker, provoker=victim, why=why or self.ref)
        )

    def swap(self, other: int, *, who: int | None = None) -> bool:
        """Two creatures change places. Either both move or neither does."""
        from .components import Position
        from .movement import place

        a = who if who is not None else self.me
        first = self.world.get(a, Position)
        second = self.world.get(other, Position)
        if first is None or second is None:
            return False
        here, there = first.square, second.square
        self.world.grid.lift(a)
        self.world.grid.lift(other)
        place(self.world, a, there)
        place(self.world, other, here)
        return True

    def basic(
        self, *, on: int | None = None, who: int | None = None, ranged: bool = False
    ) -> bool:
        """Make a basic attack -- whichever row that creature's actually is.

        A great many powers grant one, and spelling it out longhand gets it
        wrong for any creature whose basic attack has been replaced: a
        monster points `Powers.basic` at one of its own abilities, and a
        hand-written copy of "roll and deal weapon damage" would quietly
        ignore that.
        """
        from .basic import MELEE, RANGED
        from .components import Powers
        from .dsl import use

        attacker = self.me if who is None else who
        target = self._who(on)
        if target is None:
            return False
        known = self.world.get(attacker, Powers)
        ref = (known.basic if known else MELEE) or MELEE
        if ranged:
            ref = RANGED if known is None or not known.known else ref
        return use(self.world, attacker, ref, targets=[target], spend=False)

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
    def landed(self) -> bool:
        """Did the last attack hit? `c.hit()` is the damage; this is the question.

        Rarely needed -- `if c.strike():` already answers it -- but a body
        that rolls once and then branches twice wants to ask again.
        """
        return self.result is not None and self.result.hit

    @property
    def crit(self) -> bool:
        return self.result is not None and self.result.critical

    # -- damage and healing --------------------------------------------------

    def hit(self, *, on: int | None = None, half: bool = False) -> int:
        """Deal the damage the header declared.

        The common case, and the one that can be converted between editions:
        the expression lives in the header as data, so `world.monster_math`
        can rescale an older monster to the newer curve without anybody
        rewriting a body. See `engine/monster_math.py`.

        `half` is the "Miss: half damage" line -- rolled, then halved.
        """
        from .dsl import get

        p = get(self.ref)
        if p is None or p.damage is None:
            raise ValueError(f"{self.ref} declared no damage; call c.damage(...)")
        d = p.damage
        dice = self._converted(d)
        bonus = self._bonus_of(d.bonus)
        if half:
            return self.half_damage(dice, bonus, dtype=d.dtype, on=on)
        return self.damage(dice, bonus, dtype=d.dtype, on=on)

    def _converted(self, d: Damage) -> str:
        """The declared dice, under whichever edition's maths is in force."""
        from .components import Ident

        if not d.dice:
            return ""
        ident = self.world.get(self.me, Ident)
        book = getattr(ident, "book", "") if ident else ""
        return self.world.monster_math.convert(
            d.dice, book=book, level=self.stats.level, kind=d.kind
        )

    def _bonus_of(self, bonus: str | int) -> int:
        """A flat number, or an ability modifier named as a string."""
        if isinstance(bonus, int):
            return bonus
        if not bonus:
            return 0
        try:
            return self.stats.mod(Ability(bonus.lower()))
        except ValueError:
            return 0

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

    def push(
        self,
        squares_: int,
        *,
        on: int | None = None,
        anchor: Square | None = None,
        to: Square | None = None,
        by: int | None = None,
    ) -> int:
        """`to` names the destination outright, for a row that does.
        `by` names who is doing the moving, when it is not the caster."""
        who = self._who(on)
        return 0 if who is None else forced(
            self.world, by if by is not None else self.me, who,
            Forced.PUSH, squares_, anchor=anchor, to=to,
        )

    def pull(
        self,
        squares_: int,
        *,
        on: int | None = None,
        anchor: Square | None = None,
        to: Square | None = None,
        by: int | None = None,
    ) -> int:
        """`to` names the destination outright, for a row that does.
        `by` names who is doing the moving, when it is not the caster."""
        who = self._who(on)
        return 0 if who is None else forced(
            self.world, by if by is not None else self.me, who,
            Forced.PULL, squares_, anchor=anchor, to=to,
        )

    def slide(self, squares_: int, *, on: int | None = None,
              anchor: Square | None = None) -> int:
        who = self._who(on)
        return 0 if who is None else forced(
            self.world, self.me, who, Forced.SLIDE, squares_, anchor=anchor
        )

    def shift(
        self, squares_: int = 1, *, who: int | None = None, to: Square | None = None
    ) -> bool:
        """Shift, choosing the destination through the world's decider.

        `to` names the square outright, for the powers that do -- "shift into
        the space the target left" is not a choice, it is an instruction.
        """
        mover = self.me if who is None else who
        if to is not None:
            return shift(self.world, mover, to)
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

    def flee(self, squares_: int, *, on: int | None = None) -> int:
        """The target runs, under its own power, as far from you as it can.

        Not forced movement, which matters: it is the creature moving, so it
        provokes on the way out, and that is usually the entire point of the
        power. A push of the same distance would be safe for the target and a
        different card altogether.
        """
        from .movement import walk

        who = self._who(on)
        if who is None or squares_ <= 0:
            return 0
        paths = self.world.reachable_paths(who, squares_)
        if not paths:
            return 0
        away = max(sorted(paths), key=lambda sq: _distance(sq, self.here))
        return walk(self.world, who, paths[away])

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
        ongoing: tuple[int, DamageType] | None = None,
        escalate: Callable[[Effect], None] | None = None,
    ) -> Effect | None:
        """Apply one or more conditions for a duration.

        `ongoing` hangs damage on the *same* effect, which matters when the
        printed line reads "slowed and takes ongoing 5 damage (save ends
        both)". Applying the two separately gives the victim two saving
        throws and lets it shake off half of a thing the book says is one.
        """
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
            ongoing=ongoing,
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

    def curse(self, *, on: int | None = None, until: When = When.ENCOUNTER) -> Effect | None:
        """Curse a creature. Lasts the fight unless something says otherwise.

        Relational, because a warlock power that reads "if the target is
        cursed" means cursed *by you*. Two warlocks in a party curse
        separately and neither reads the other's.
        """
        who = self._who(on)
        if who is None:
            return None
        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} curse",
            relations=[(Relation.CURSED_BY, self.me, who)],
        )

    def cursed(self, on: int | None = None) -> bool:
        """Has *this* caster cursed that creature?"""
        who = self._who(on)
        return who is not None and self.world.relations.holds(
            Relation.CURSED_BY, self.me, who
        )

    def grab(self, *, on: int | None = None) -> Effect | None:
        who = self._who(on)
        if who is None:
            return None
        return self.world.effects.apply(
            who, self.me, When.ENCOUNTER, label=f"{self.ref} grab",
            relations=[(Relation.GRABBED_BY, self.me, who)],
        )

    def no_provoke(
        self, *, from_: int | None = None, until: When = When.EOTNT
    ) -> Effect | None:
        """Walking away from that creature does not give it an opening.

        A handful of rows say so outright. Implemented as an interrupt on the
        opportunity window rather than as a flag movement would have to
        consult, so it applies wherever the window opens and needs nothing
        added to the movement rules.
        """
        from .events import OpportunityWindow

        who = self._who(from_)
        me = self.me

        def veto(ev: OpportunityWindow) -> None:
            if ev.provoker == me and (who is None or ev.actor == who):
                ev.cancel("the power says it does not provoke")

        return self.watch(
            OpportunityWindow,
            veto,
            until=until,
            window=Window.BEFORE,
            on=me,
            label=f"{self.ref} no provoke",
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
        once: bool = False,
    ) -> Effect | None:
        """A numeric modifier with a duration.

        `what` is `attack`, `damage`, `save`, `speed` or a defence. `when` is
        an optional gate -- "only against the creature you marked", "only
        while you have a shield" -- written as a lambda right here rather than
        as a new kind of op.

        `once` is for "to his or her **next** attack roll": the bonus ends
        after the first attack that could use it. It is spent by watching the
        roll rather than by consuming it inside the gate, because the gate is
        also called when a policy is only *considering* an attack, and a
        bonus that evaporated on being thought about would be a hard thing to
        ever notice.
        """
        who = self._who(on)
        if who is None:
            return None
        key = what.value if isinstance(what, Defense) else what
        mod = Mod(what=key, value=value, kind=kind, when=when, label=self.ref)
        effect = self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} {key}{value:+d}", mods=[(who, mod)]
        )
        if once and effect is not None:
            from .events import AttackRolled

            def spend(ev: AttackRolled) -> None:
                if ev.attacker != who:
                    return
                if mod.applies({"attacker": ev.attacker, "target": ev.target,
                                "power": ev.power, "advantage": ev.advantage}):
                    self.world.effects.end(effect, "used")

            effect.subs.append(self.world.bus.on(AttackRolled, spend, owner=who))
        return effect

    def penalty(self, what: str | Defense, value: int, **kw: Any) -> Effect | None:
        return self.bonus(what, -abs(value), kind="untyped", **kw)

    # -- standing arrangements -----------------------------------------------

    def on_attack(
        self,
        fn: Callable[[Any], None],
        *,
        by: int | None = None,
        until: When = When.EONT,
        once: bool = False,
        once_per_round: bool = False,
        label: str = "",
    ) -> Effect:
        """"Whenever that creature attacks..." -- the commonest trigger in 4e.

        Written out by hand it is a `watch` plus a filter plus a latch, three
        times per class. Here once.
        """
        from .events import AttackDeclared

        who = self._who(by)
        seen: dict[int, int] = {}

        def guard(ev: AttackDeclared) -> None:
            if who is not None and ev.attacker != who:
                return
            if once_per_round and seen.get(0) == self.world.round:
                return
            seen[0] = self.world.round
            fn(ev)

        return self.watch(
            AttackDeclared, guard, until=until, once=once,
            label=label or f"{self.ref} on attack",
        )

    def watch(
        self,
        event: type[Event],
        fn: Callable[[Any], None],
        *,
        until: When = When.EONT,
        window: Window = Window.AFTER,
        on: int | None = None,
        once: bool = False,
        label: str = "",
    ) -> Effect:
        """Arm a trigger that expires with a duration.

        "Whenever an ally within 5 squares is hit, ..." is this plus an `if`
        in `fn`. The subscription is owned by the effect, so when the duration
        runs out the trigger goes with it and nothing has to remember.
        """
        who = self._who(on) or self.me
        holder: list[Effect] = []

        def fire(ev: Any) -> None:
            fn(ev)
            if once and holder:
                self.world.effects.end(holder[0], "used")

        sub = self.world.bus.on(event, fire, window=window, owner=self.me)
        effect = self.world.effects.apply(
            who, self.me, until, label=label or f"{self.ref} trigger", subs=[sub]
        )
        holder.append(effect)
        return effect

    # -- areas ---------------------------------------------------------------

    def area(self) -> frozenset[Square]:
        """The squares this power is covering, for the ones that leave
        something behind. Empty for a power that has no area."""
        from .dsl import area_of, get

        p = get(self.ref)
        return area_of(self.world, self.me, p, self.origin) if p else frozenset()

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

    def hazard(
        self,
        area: Iterable[Square],
        amount: int,
        dtype: DamageType = DamageType.UNTYPED,
        *,
        label: str = "",
        until: When = When.SUSTAIN,
        difficult: bool = False,
    ) -> int:
        """A zone that hurts whoever is standing in it.

        The commonest zone in the game: "any creature that enters the zone or
        starts its turn there takes N damage, and can take it only once per
        turn". All three clauses are here -- entering, starting, and the
        once-per-turn latch -- because writing them out per power would be
        three chances to get the latch wrong.
        """
        from .events import TurnStart, ZoneEntered

        zone = self.zone(area, label=label, until=until, difficult=difficult)
        struck: dict[int, int] = {}
        source = self.me

        def bite(who: int) -> None:
            if struck.get(who) == self.world.round:
                return
            struck[who] = self.world.round
            self.world.damage(source, who, amount, dtype, detail=f"{self.ref} zone")

        def on_enter(ev: ZoneEntered) -> None:
            if ev.zone == zone:
                bite(ev.actor)

        def on_turn(ev: TurnStart) -> None:
            if not ev.ghost and ev.actor in self.world.zones.occupants(zone):
                bite(ev.actor)

        for event, fn in ((ZoneEntered, on_enter), (TurnStart, on_turn)):
            sub = self.world.bus.on(event, fn, owner=source)
            zone_effect = self.world.get(zone, Zone).effect
            if zone_effect is not None:
                zone_effect.subs.append(sub)
        return zone

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
