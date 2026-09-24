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
    ActionType,
    Condition,
    DamageType,
    Defense,
    Forced,
    Keyword,
    Relation,
    Team,
    Window,
)

if TYPE_CHECKING:
    from .dsl import Damage
    from .ecs import World


class _Decline:
    """The answer a printed "may" adds to a list of choices.

    An object rather than `None` so it survives a list of options and
    renders with words a player can read, instead of the string "None".
    """

    __slots__ = ("text",)

    def __init__(self, text: str) -> None:
        self.text = text

    def __str__(self) -> str:
        return self.text

    def __bool__(self) -> bool:
        return False


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
    #: The event this row was offered in answer to, for a triggered power.
    #: None for everything used on its own turn.
    trigger: Any = None
    #: True when this use *is* an opportunity attack. Read by the attack
    #: context, so "+2 to AC against opportunity attacks" can be written.
    opportunity: bool = False
    #: Which half of a "Melee or Ranged weapon" line is being used. 0 is the
    #: printed first one. A body almost never reads this -- `c.w()` and
    #: `c.strike()` already honour it, which is the point.
    branch: int = 0

    @property
    def attack_mod(self) -> int:
        """The modifier of whatever ability *this branch* attacks with.

        A weapon power's damage line is "<the attack ability> modifier
        damage", and on a two-branch row that is Strength in melee and
        Dexterity at range. Writing `c.dex_mod` in the body hard-codes one
        half of a row that has two.
        """
        p = self._declared()
        line = p.attack_of(self.branch) if p else None
        if line is None or line.ability is None:
            return 0
        return self.stats.mod(line.ability)

    @property
    def ranged(self) -> bool:
        """Is this use a ranged one? Asks the branch, not the keywords."""
        p = self._declared()
        return bool(p and p.reach_of(self.branch).kind in ("ranged", "area_burst"))

    def redirect(self, *, to: int | None = None, by: int | None = None) -> bool:
        """Point the attack you are interrupting at somebody else.

        "The triggering attack targets a creature adjacent to you instead"
        is an interrupt that moves the blow rather than stopping it. Only
        works before the roll -- on `AttackDeclared` -- because after that
        there is a result and moving it would mean re-rolling.
        """
        ev = self.trigger
        if ev is None or not hasattr(ev, "target"):
            return False
        if to is not None:
            ev.target = to
        if by is not None:
            ev.attacker = by
        return True

    def cancel(self) -> None:
        """Stop the thing that triggered this.

        Only an immediate interrupt can: by the time a reaction runs, its
        window has already closed and the attack has happened. Calling it
        from a reaction does nothing, which is the printed rule rather than
        an oversight.
        """
        if self.trigger is not None:
            self.trigger.cancel()

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

    def adjacent_to(self, thing: int, who: int) -> bool:
        """Is `who` standing next to `thing`? Works for a conjuration too.

        `c.adjacent` measures from the caster; this measures between two
        named entities, which is what "adjacent to the sphere" needs.
        """
        from .query import adjacent

        return adjacent(self.world, thing, who)

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

    def build(self, choice: str, *, on: int | None = None) -> bool:
        """Did this character take that build? `c.build("infernal")`.

        Defaults to the *caster*, unlike almost everything else here: a
        build rider is always about whoever is using the power, never about
        who it lands on. Four agents across three classes asked for this
        independently, which is how it got written.
        """
        from .components import Build

        who = self.me if on is None else on
        held = self.world.get(who, Build)
        return held is not None and choice.lower() in held.choices

    def suffering(self, label: str = "", *, by: int | None = None) -> list[int]:
        """Everyone carrying an effect I applied. "Each creature affected by
        your X" is a common printed line and nothing could answer it.

        `label` picks out one power's effects; `by` defaults to the caster.
        """
        source = self.me if by is None else by
        out = []
        for eid in creatures(self.world):
            for eff in self.world.effects.of(eid):
                if eff.source != source:
                    continue
                if label and label not in eff.label:
                    continue
                out.append(eid)
                break
        return out

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
        from .resolve import spend_surge

        return spend_surge(self.world, self._who(on) or self.me)

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

    def hide(self, *, from_: int | None = None, until: When = When.ENCOUNTER) -> Effect | None:
        """Go unseen, and stay that way until something gives you away.

        The same held state as `c.invisible` and a different duration: being
        invisible runs out on a clock, being hidden lasts until you do
        something about it -- and attacking does. `resolve.attack` breaks it
        for whoever swung, so a row that keeps its concealment hides again
        afterwards, which is how the printed ones read.
        """
        return self.invisible(to=from_, until=until)

    def unhide(self) -> None:
        """Give yourself away deliberately."""
        self.world.relations.clear_source(Relation.HIDDEN_FROM, self.me, "revealed")

    def is_hidden(self, *, from_: int | None = None) -> bool:
        from .query import hidden_from

        unseeing = hidden_from(self.world, self.me)
        return bool(unseeing) if from_ is None else from_ in unseeing

    def is_trap(self, who: int | None = None) -> bool:
        """Is that a trap rather than a creature?

        What "+2 to all defences against traps" asks, off the attacker in a
        modifier's context: `c.bonus(AC, 2, when=lambda ctx:
        c.is_trap(ctx["attacker"]))`.
        """
        from .query import is_trap

        target = self._who(who)
        return target is not None and is_trap(self.world, target)

    def ignores_difficult(
        self, kind: str = "", *, on: int | None = None, until: When = When.ENCOUNTER
    ) -> Effect | None:
        """Cross rough ground for nothing. `kind` names which sort, or all.

        `c.ignores_difficult("mud")` is the printed line "ignores difficult
        terrain that is mud or shallow water" -- said twice, once per word.
        With no `kind` it is every sort. The labels are the ones the map and
        `c.zone(difficult=...)` give their squares.
        """
        from .components import Movement

        who = self._who(on) or self.me
        moves = self.world.get(who, Movement)
        if moves is None:
            return None
        word = kind.lower() or "*"
        if word in moves.ignores:
            return None
        moves.ignores.add(word)
        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} sure-footed",
            on_end=[lambda: moves.ignores.discard(word)],
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

    def score(self, a: Ability) -> int:
        """The raw ability score -- 15, 18 -- not its modifier or bonus.

        A printed Requirement reads "Dexterity 15 or higher" and means the
        score. `c.dex_` is the *attack bonus* (half level, modifier and
        proficiency) and `c.dex_mod` the modifier, so a row testing either
        against 15 fails quietly and for a reason nothing reports.
        """
        return self.stats.score(a)

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
            # Same question `c.w()` asks, and it has to be asked the same
            # way: the branch where there is one, the keyword otherwise.
            if p is not None and p.reach.alt is not None:
                ranged = self.ranged
            else:
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
        # The branch is the better answer where there is one: a row printing
        # "Melee or Ranged weapon" carries the RANGED keyword for both
        # halves, so the keyword alone put a bow in the hand of its melee
        # branch.
        if ranged is not None:
            fires = ranged
        elif p is not None and p.reach.alt is not None:
            fires = self.ranged
        else:
            fires = p is not None and Keyword.RANGED in p.keywords
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
        self,
        *,
        on: int | None = None,
        advantage: bool | None = None,
        plus: int = 0,
        from_: int | None = None,
        ignore_cover: bool = False,
    ) -> AttackResult:
        """Roll the attack the header declared.

        The overwhelmingly common case: the printed `Attack:` line is a plain
        ability against a defence, it went in the header where a policy can
        read it, and the body just says "roll it".
        """
        from .dsl import get

        p = get(self.ref)
        line = p.attack_of(self.branch) if p else None
        if line is None:
            raise ValueError(f"{self.ref} declared no attack line; call c.attack(...)")
        return self.attack(
            line.bonus_for(self.world, self.me, self.ref, self.branch) + plus,
            line.vs,
            on=on,
            advantage=advantage,
            from_=from_,
            ignore_cover=ignore_cover,
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
        """Two creatures change places. Either both move or neither does.

        Routed through `movement.step` rather than `place`, which is setup
        only and announces nothing. Done the quiet way, two creatures
        exchanged squares with no `Moved` and no adjacency change, so a
        fighter's mark watching for movement never saw it, an aura never
        noticed anyone arriving, and a row whose whole content was a swap
        could not be anything but silent to the audit.
        """
        from .components import Position
        from .movement import step

        a = who if who is not None else self.me
        first = self.world.get(a, Position)
        second = self.world.get(other, Position)
        if first is None or second is None:
            return False
        here, there = first.square, second.square
        # Both are lifted before either lands, or each sees the other's
        # square as occupied and neither moves.
        self.world.grid.lift(a)
        self.world.grid.lift(other)
        step(self.world, a, there, kind="swap", mode="walk")
        step(self.world, other, here, kind="swap", mode="walk")
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
        from_: int | None = None,
        ignore_cover: bool = False,
    ) -> AttackResult:
        who = self._who(on)
        if who is None:
            return AttackResult()
        # `from_` moves only where the swing comes from -- reach, cover and
        # flanking are measured from there. The numbers stay the caster's,
        # which is what a conjuration is: your attack, its position.
        self.result = attack(
            self.world, from_ or self.me, who, bonus, vs, self.ref,
            advantage=advantage, opportunity=self.opportunity,
            among=tuple(self.targets) or (who,), branch=self.branch,
            ignore_cover=ignore_cover, dying=self.dying,
        )
        # An interrupt may have moved the blow onto somebody else. The roll
        # and the `Hit` already name the new target; without this the body's
        # `c.hit()` still paid out against the old one, so one creature got
        # hit and a different one took the damage.
        if on is None and self.result.target and self.result.target != who:
            self.target = self.result.target
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
            self.world, self.me, who, amount, dtype, detail or self.ref,
            opportunity=self.opportunity,
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
        return deal_damage(
            self.world, self.me, who, amount, dtype, f"{self.ref} (half)",
            opportunity=self.opportunity,
        )

    def flat(self, amount: int, *, dtype: DamageType = DamageType.UNTYPED,
             on: int | None = None) -> int:
        who = self._who(on)
        if who is None:
            return 0
        return deal_damage(
            self.world, self.me, who, amount, dtype, self.ref,
            opportunity=self.opportunity,
        )

    def heal(self, amount: int, *, on: int | None = None) -> int:
        who = self._who(on)
        return 0 if who is None else heal(self.world, self.me, who, amount)

    def surge(self, *, on: int | None = None, bonus: int = 0) -> int:
        """Spend a healing surge: a quarter of maximum hit points."""
        from .resolve import spend_surge

        who = self._who(on)
        health = self.world.get(who, Health) if who else None
        if health is None or not spend_surge(self.world, who):
            return 0
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
            Forced.PUSH, squares_, anchor=anchor, to=to, power=self.ref,
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
            Forced.PULL, squares_, anchor=anchor, to=to, power=self.ref,
        )

    def slide(
        self,
        squares_: int,
        *,
        on: int | None = None,
        anchor: Square | None = None,
        to: Square | None = None,
        by: int | None = None,
    ) -> int:
        """`to` names the destination outright, for a row that does.
        `by` names who is doing the moving, when it is not the caster.

        A slide's destination is otherwise the decider's free choice, which
        is right for "slide it 3 squares" and wrong for "slide it into a
        square adjacent to you" -- that one was duly sliding enemies three
        squares *away*. `push` and `pull` have had `to` all along; this is
        the one that did not.
        """
        who = self._who(on)
        return 0 if who is None else forced(
            self.world, by if by is not None else self.me, who,
            Forced.SLIDE, squares_, anchor=anchor, to=to, power=self.ref,
        )

    def shift(
        self,
        squares_: int = 1,
        *,
        who: int | None = None,
        to: Square | None = None,
        share: bool = False,
    ) -> bool:
        """Shift, choosing the destination through the world's decider.

        `to` names the square outright, for the powers that do -- "shift into
        the space the target left" is not a choice, it is an instruction.

        `share` moves *into* an occupied square, for a creature that melds
        with the one it is on top of.
        """
        mover = self.me if who is None else who
        if to is not None:
            return shift(self.world, mover, to, share=share)
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

    def reroll_attack(self, *, keep: str = "new") -> bool:
        """Make the triggering attack roll again. `keep` is new, best or worst.

        Reads the attack off `c.trigger`, so it only means anything inside a
        row the dispatcher offered. Rerolling is not cancelling: the attack
        still happens, with a different number.
        """
        ev = self.trigger
        result = getattr(ev, "result", None) if ev is not None else None
        if result is None:
            return False
        fresh = self.world.rng.d20().total
        old = result.natural
        face = {"new": fresh, "best": max(old, fresh), "worst": min(old, fresh)}[keep]
        shift_ = face - old
        result.natural = face
        result.total += shift_
        result.critical = face == 20
        result.hit = face == 20 or (face != 1 and result.total >= result.target_defence)
        return True

    def terrain(self, word: str) -> bool:
        """Is the fight being had in that sort of place? `c.terrain("aquatic")`.

        A property of the encounter, not of anybody in it. Several creatures
        print a rider that only applies underwater, and writing only the
        bonus half would have buffed them in every dry fight there is.
        """
        return word.lower() in getattr(self.world, "terrain", frozenset())

    def teleport(
        self, squares_: int, *, who: int | None = None, to: Square | None = None
    ) -> bool:
        """Blink somewhere. `to` names the square, as `c.shift` already allowed.

        Without it the destination goes through the decider, which with no
        decider installed takes the lowest-sorted square -- fine for a player
        being asked, useless for a row whose printed line says exactly where
        it arrives.
        """
        mover = self.me if who is None else who
        origin = squares(self.world, mover)
        options = [
            sq
            for sq in spread(origin, squares_)
            if self.world.grid.passable(sq) and self.world.grid.occupant(sq) in (None, mover)
        ]
        if to is not None:
            return teleport(self.world, mover, to) if to in options else False
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

    def prone(
        self, *, on: int | None = None, held: When | None = None
    ) -> Effect | None:
        """Knocked prone. It lasts until the creature stands up, not until a
        turn boundary, so it hangs on the encounter clock.

        `held` is for "falls prone and cannot stand up until ...", which is a
        second, shorter clock on top of the first: the creature is prone for
        as long as prone normally lasts, and for `held` it may not do the one
        thing that ends it.
        """
        effect = self.condition(Condition.PRONE, until=When.ENCOUNTER, on=on)
        if held is not None:
            self.condition(Condition.PINNED, until=held, on=on)
        return effect

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

    def coup_de_grace(self, *, on: int | None = None) -> bool:
        """Finish a helpless creature. Automatic critical, plus a flat 5d6.

        Four rows across two monster batches asked for this, and every one of
        them would otherwise have spelled out the auto-crit rule in its own
        body. It is a rule of the game rather than a property of any power,
        so it lives here and they all get the same one.

        False if the target is not actually helpless, which is the printed
        requirement and worth checking rather than trusting the caller.
        """
        from .conditions import rules
        from .query import active

        who = self._who(on)
        if who is None or not any(rules(c).helpless for c in active(self.world, who)):
            return False
        result = self.strike(on=who, advantage=True)
        result.critical = True
        result.hit = True
        # `c.flat`, not `c.damage`: the extra 5d6 of a coup de grace is not
        # part of the attack's damage and a critical does not maximise it.
        # Rolled through `c.damage` with the critical flag already up, it
        # came out a flat 30 every time, on top of an automatic critical,
        # from a level 1 monster.
        self.flat(self.roll("5d6"), on=who)
        return True

    def vulnerable(
        self,
        amount: int,
        dtype: DamageType | None = None,
        *,
        until: When = When.SAVE_ENDS,
        on: int | None = None,
    ) -> Effect | None:
        """Takes `amount` extra from every hit, or from one damage type.

        Held by the *target*, not by whoever inflicted it: a save-ends
        duration is rolled by whoever carries the effect, and "vulnerable 5
        until it saves" is the target's save to make.
        """
        from .components import Defences

        who = self._who(on)
        if who is None:
            return None
        kinds = [dtype] if dtype is not None else list(DamageType)
        defences = self.world.get(who, Defences) or self.world.add(who, Defences())
        for kind in kinds:
            defences.vulnerable[kind] = defences.vulnerable.get(kind, 0) + amount

        def undo() -> None:
            for kind in kinds:
                left = defences.vulnerable.get(kind, 0) - amount
                if left > 0:
                    defences.vulnerable[kind] = left
                else:
                    defences.vulnerable.pop(kind, None)

        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} vulnerable", on_end=[undo]
        )

    def conjure(
        self,
        at: Square | None = None,
        *,
        label: str = "",
        until: When = When.SUSTAIN,
        sustain: ActionType | None = ActionType.MINOR,
        speed: int = 0,
        aura: int = 0,
        burn: tuple[int, DamageType] | None = None,
    ) -> int:
        """Put a conjuration on the board and return its entity id.

        It occupies its square -- which is the clause a zone could never say
        -- and nothing may walk through it. `speed` is how far its creator
        may move it with a move action; `aura` gives it a footprint that
        follows it, which is what "each creature adjacent to it" reads off
        and is also the only reason it is drawn at all.

        It rolls its creator's attacks. `c.from_(sphere)` is how a body
        makes it swing.

        `burn` gives the aura teeth -- "any creature that starts its turn
        adjacent to it takes N" -- and is set here rather than by the caller
        because the aura's id is made in this method and fishing it back out
        of the zone list afterwards picks up whatever else is on the board.
        """
        from .components import Conjuration, Ident, Movement, Position
        from .movement import place
        from .types import Size

        where = at or self._free_square_near(self.here)
        if where is None:
            return 0
        name = label or self.ref
        eid = self.world.spawn(
            Ident(ref=f"c:{name}"),
            Position(square=where, size=Size.MEDIUM),
            Movement(speed=speed),
            Conjuration(ref=name, by=self.me),
        )
        place(self.world, eid, where)
        effect = self.world.effects.apply(
            eid,
            self.me,
            until,
            label=name,
            sustain_cost=sustain if until is When.SUSTAIN else None,
            on_end=[lambda: self._banish(eid)],
        )
        conj = self.world.get(eid, Conjuration)
        if conj is not None:
            conj.effect = effect.id
        if aura:
            ring = self.aura(aura, label=name, until=until, on=eid)
            if burn is not None:
                self.burns(ring, burn[0], burn[1])
        return eid

    def _banish(self, eid: int) -> None:
        """Take a conjuration off the board when whatever held it ends."""
        if self.world.get(eid, Position) is not None:
            self.world.despawn(eid)

    def _free_square_near(self, origin: Square) -> Square | None:
        for sq in sorted(spread({origin}, 1) - {origin}):
            if self.world.grid.passable(sq) and self.world.grid.occupant(sq) is None:
                return sq
        return None


    def mode(
        self, name: str, speed: int, *, until: When = When.ENCOUNTER, on: int | None = None
    ) -> Effect | None:
        """Grant a way of moving -- fly, swim, climb -- for a while.

        `Movement.modes` was only ever set when a creature was loaded, so a
        power granting flight had nothing to write to.
        """
        from .components import Movement

        who = self._who(on) or self.me
        moves = self.world.get(who, Movement)
        if moves is None:
            return None
        had = moves.modes.get(name)
        moves.modes[name] = max(speed, had or 0)

        def undo() -> None:
            if had is None:
                moves.modes.pop(name, None)
            else:
                moves.modes[name] = had

        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} {name}", on_end=[undo]
        )

    def form(
        self,
        *,
        conditions: Iterable[Condition] = (),
        modes: dict[str, int] | None = None,
        until: When = When.ENCOUNTER,
        revert: ActionType | None = ActionType.MINOR,
        label: str = "",
    ) -> Effect:
        """Assume a shape: some conditions, some ways of moving, and a way out.

        A polymorph is not a stance -- you are not choosing between forms,
        you are in one and may step out of it -- so `revert` is what leaving
        costs rather than "taking another ends it".
        """
        effect = self.world.effects.apply(
            self.me,
            self.me,
            until,
            label=label or self.ref,
            conditions=conditions,
            drop_cost=revert,
        )
        for name, speed in (modes or {}).items():
            granted = self.mode(name, speed, until=until)
            if granted is not None:
                effect.on_end.append(lambda g=granted: self.world.effects.end(g, "form ended"))
        return effect

    def stance(
        self,
        *,
        on: int | None = None,
        conditions: Iterable[Condition] = (),
        label: str = "",
    ) -> Effect:
        """Assume a stance. Whatever you were in, you are not in it now.

        That last part is the whole of what makes a stance a stance -- one
        at a time, and it lasts until you take another or the fight ends.
        `When.STANCE` has been in the enum since durations were written and
        nothing ever set it.

        Returns the effect so a body can hang mods on it the usual way.
        """
        who = self._who(on) or self.me
        previous = self.world.effects.stance_of(who)
        if previous is not None:
            self.world.effects.end(previous, "took another stance")
        return self.world.effects.apply(
            who, self.me, When.STANCE, label=label or self.ref, conditions=conditions
        )

    def rooted(self, *, until: When = When.EONT, on: int | None = None) -> Effect | None:
        """Cannot shift. Still walks, which is why this is not `immobilized`.

        "Slowed and cannot shift" is one printed line in at least three
        classes, and until this existed the second half was quietly dropped.
        """
        return self.condition(Condition.ROOTED, until=until, on=on)

    def insubstantial(
        self, *, until: When = When.EONT, on: int | None = None
    ) -> Effect | None:
        """Halves all damage taken. A property of the creature, not the damage."""
        return self.condition(Condition.INSUBSTANTIAL, until=until, on=on)

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

    def immovable(self, *, until: When = When.EONT, on: int | None = None) -> Effect | None:
        """Cannot be pushed, pulled or slid. The counterpart of `c.no_provoke`.

        `ForcedMove` is cancellable, so this is a listener that refuses --
        but three rows had each written that listener out, and `c.rooted`
        is the wrong card: that bars a shift and leaves being shoved alone.
        """
        from .events import ForcedMove

        who = self._who(on) or self.me

        def refuse(ev: ForcedMove) -> None:
            if ev.target == who:
                ev.cancel("immovable")

        return self.watch(
            ForcedMove, refuse, until=until, window=Window.BEFORE, on=who,
            label=f"{self.ref} immovable",
        )

    def is_quarry(self, on: int | None = None) -> bool:
        """Is this creature the ranger's quarry?

        Relational, like `c.cursed`: a second ranger's quarry is not yours.
        Several rows read "one creature that is your quarry" and had no way
        to ask -- the quarry lived in a closure, so the only thing that knew
        was the rider paying out.
        """
        who = self._who(on)
        return who is not None and self.world.relations.holds(
            Relation.QUARRY_OF, self.me, who
        )

    def quarry(self, *, on: int | None = None, until: When = When.ENCOUNTER) -> Effect | None:
        """Name a creature your quarry."""
        who = self._who(on)
        if who is None:
            return None
        return self.world.effects.apply(
            self.me, self.me, until, label=f"{self.ref} quarry",
            relations=[(Relation.QUARRY_OF, self.me, who)],
        )

    # -- the three relations that simply name a second creature -------------
    #
    # A master, a rider and a guard are all the same shape: the stat block
    # says "its master" or "a creature guarded by it" and expects the engine
    # to know who that is. Source is the one in charge, target the one it is
    # responsible for, matching `Relation`.

    @property
    def dying(self) -> bool:
        """Is this row a death throe, answering its owner's own downfall?

        The killing blow usually overshoots `dying_at`, so by the time the
        row runs its owner is not alive -- and every gate that asks whether
        it can act would refuse it for the reason it exists.
        """
        ev = self.trigger
        return (
            ev is not None
            and getattr(ev, "actor", None) == self.me
            and not alive(self.world, self.me)
        )

    def resist_forced(
        self, squares_: int = 1, *, on: int | None = None, until: When = When.ENCOUNTER
    ) -> Effect | None:
        """Shorten every push, pull and slide against this creature.

        "Moves 1 square fewer than the effect specifies." A held modifier
        rather than a watcher, because it applies to shoves from anywhere.

        Defaults to the caster rather than to `c.target`: every row printing
        this is describing itself.
        """
        return self.bonus(
            "forced", squares_, on=on or self.me, until=until, kind="untyped"
        )

    def absorb(self, ev: Any = None, *, on: int | None = None) -> int:
        """Take damage somebody else was about to suffer.

        Reads the `DamageRolled` off `c.trigger` by default, zeroes it, and
        deals it to the absorber instead. Moving damage already dealt was not
        possible at all before this: the event carried the number and nothing
        could take it over.
        """
        ev = ev if ev is not None else self.trigger
        taken = max(0, getattr(ev, "amount", 0)) if ev is not None else 0
        if taken <= 0:
            return 0
        ev.amount = 0
        return deal_damage(
            self.world, getattr(ev, "source", self.me), on or self.me, taken,
            getattr(ev, "dtype", DamageType.UNTYPED), f"{self.ref} (absorbed)",
            from_attack=False,
        )

    def overrun(self, to: Square | None = None) -> list[int]:
        """Trample: walk through whoever is in the way, and say who that was.

        The body attacks each one. `c.move` refuses an occupied square and
        reports nothing about what it passed, so a trample could not be
        written at all.
        """
        from .movement import overrun as trample
        from .movement import reachable

        if to is None:
            # The line that tramples the most. Picking the destination is
            # the whole of the decision, so it is offered rather than taken.
            here = reachable(self.world, self.me, self.speed)
            if not here:
                return []
            to = self.world.decide(self.me, "overrun", sorted(here), "trample to")
        return trample(self.world, self.me, to)

    def summon(self, ref: str, at: Square | None = None, *, team: Team | None = None) -> int:
        """Put a creature on the board mid-fight and give it a turn.

        The two halves are equally necessary: `loader.spawn` alone makes an
        entity that is not in the initiative order, so it stands there and
        never acts. "Splits into two" and every summoner print this.
        """
        from combat_engine.content import loader

        where = at or self._free_square_near(self.here)
        if where is None:
            return 0
        from .query import team as side_of

        made = loader.spawn(
            self.world, ref, where, team=team or side_of(self.world, self.me) or Team.ENEMY
        )
        if self.world.encounter is not None:
            self.world.encounter.join(made)
        return made

    def extra_turn(self, at: int) -> bool:
        """Act again this round, at that initiative count. Solos do this."""
        if self.world.encounter is None:
            return False
        self.world.encounter.extra_turn(self.me, at)
        return True

    def forbid(
        self, ref: str, *, on: int | None = None, until: When = When.SAVE_ENDS
    ) -> Effect | None:
        """Take a row away for a while. "Loses the ability to use ..."

        Not the same as spending it: the creature still has the row and
        simply cannot reach it, so it comes back when the effect ends.
        """
        from .components import Powers

        who = self._who(on)
        if who is None:
            return None
        known = self.world.get(who, Powers)
        if known is None:
            return None
        # The effect first. Adding to `forbidden` before it exists meant a
        # caller that swallowed the raise left the row taken away with
        # nothing alive to ever give it back.
        effect = self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} forbids {ref}",
            on_end=[lambda: known.forbidden.discard(ref)],
        )
        if effect is None:
            return None
        known.forbidden.add(ref)
        return effect

    def master(self) -> int | None:
        """Whoever this creature serves, if anybody."""
        found = self.world.relations.sources(Relation.MASTER_OF, self.me)
        return found[0] if found else None

    def servants(self) -> list[int]:
        """Everything that serves this creature."""
        return self.world.relations.targets(Relation.MASTER_OF, self.me)

    def bind(self, *, on: int | None = None) -> bool:
        """Make that creature this one's servant."""
        who = self._who(on)
        if who is None:
            return False
        self.world.relations.set(Relation.MASTER_OF, self.me, who)
        return True

    def rider(self) -> int | None:
        """Whoever is riding this creature."""
        found = self.world.relations.targets(Relation.RIDDEN_BY, self.me)
        return found[0] if found else None

    def mount(self) -> int | None:
        """Whatever this creature is riding."""
        found = self.world.relations.sources(Relation.RIDDEN_BY, self.me)
        return found[0] if found else None

    def ride(self, *, on: int | None = None) -> bool:
        """Get on. The mount carries you when it moves."""
        who = self._who(on)
        if who is None:
            return False
        self.world.relations.set(Relation.RIDDEN_BY, who, self.me)
        return True

    def guard(self, *, on: int | None = None) -> bool:
        """Take that creature under this one's protection."""
        who = self._who(on)
        if who is None:
            return False
        self.world.relations.set(Relation.GUARDED_BY, self.me, who)
        return True

    def guarding(self) -> list[int]:
        """Everything this creature is guarding."""
        return self.world.relations.targets(Relation.GUARDED_BY, self.me)

    def is_guarded(self, on: int | None = None) -> bool:
        """Is that creature under *this* one's protection?"""
        who = self._who(on)
        return who is not None and self.world.relations.holds(
            Relation.GUARDED_BY, self.me, who
        )

    def grants_advantage(
        self,
        *,
        until: When = When.EONT,
        on: int | None = None,
        to: str | int = "me",
        once: bool = False,
    ) -> Effect | None:
        """The target grants combat advantage -- to you, an ally, or your side.

        The relation names **one** beneficiary, so anything wider is that
        relation once per creature, held on a single effect so they all end
        together. Four rows had hand-rolled that before this took an
        argument: `to="allies"` for "you and your allies", and `to=<id>`
        for "one ally gains combat advantage against the target", which is
        the printed line this method used to say wrong.
        """
        who = self._who(on)
        if who is None:
            return None
        if isinstance(to, int):
            beneficiaries = [to]
        elif to == "allies":
            beneficiaries = [self.me, *self.allies()]
        else:
            beneficiaries = [self.me]
        granted = self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} advantage",
            relations=[(Relation.GRANTS_CA_TO, who, b) for b in beneficiaries],
        )
        if once:
            # "Grants combat advantage to the *next* attack against it."
            # `c.bonus` has had `once` all along and this had no equivalent,
            # so rows wanting it hand-rolled the watch that spends it.
            from .events import AttackRolled

            def spend(ev: AttackRolled) -> None:
                if ev.target == who and not granted.ended:
                    self.world.effects.end(granted, "spent")

            granted.subs.append(
                self.world.bus.on(AttackRolled, spend, owner=self.me)
            )
        return granted

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
            before = len(self.world.bus.log)
            fn(ev)
            # `once` means "fire once", not "live for one event", and those
            # differ for every trigger with a guard -- which is most of them.
            # Ending unconditionally burned the effect on the first event of
            # the right *class*, so "the first time you hit a bloodied enemy"
            # was spent by the first attack that missed a healthy one.
            # Whether the body did anything is read off the log.
            if once and holder and len(self.world.bus.log) > before:
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
        difficult: bool | str = False,
        blocks_sight: bool = False,
        sustain: ActionType | None = None,
    ) -> int:
        return self.world.zones.create(
            self.me, label or self.ref, frozenset(area), until,
            difficult=difficult, blocks_sight=blocks_sight, sustain=sustain,
        )

    def aura(
        self,
        radius: int,
        *,
        label: str = "",
        until: When = When.ENCOUNTER,
        on: int | None = None,
        sustain: ActionType | None = None,
    ) -> int:
        """An aura around a creature -- or around anything with a position.

        `on` is what it follows. It used to be the caster and nothing else,
        which is what made "each creature adjacent to the sphere" unsayable:
        `Zones.refresh` has always been willing to follow any entity with a
        `Position`, and only this signature insisted it be `self.me`.
        """
        owner = self.me if on is None else on
        return self.world.zones.aura(owner, label or self.ref, radius, until, sustain)

    def hazard(
        self,
        area: Iterable[Square],
        amount: int,
        dtype: DamageType = DamageType.UNTYPED,
        *,
        label: str = "",
        until: When = When.SUSTAIN,
        difficult: bool = False,
        sustain: ActionType | None = ActionType.MINOR,
    ) -> int:
        """A zone that hurts whoever is standing in it.

        The commonest zone in the game: "any creature that enters the zone or
        starts its turn there takes N damage, and can take it only once per
        turn". All three clauses are here -- entering, starting, and the
        once-per-turn latch -- because writing them out per power would be
        three chances to get the latch wrong.
        """

        zone = self.zone(
            area, label=label, until=until, difficult=difficult,
            sustain=sustain if until is When.SUSTAIN else None,
        )
        self.burns(zone, amount, dtype)
        return zone

    def burns(self, zone: int, amount: int, dtype: DamageType = DamageType.UNTYPED) -> None:
        """Give an existing zone teeth: enter it or start a turn in it and it
        bites, once per turn.

        Split out of `hazard` so a zone somebody else made can have them --
        a conjuration's aura is created with the conjuration, and the thing
        that burns you for standing beside a sphere of flame is that aura
        rather than a second zone laid over it.
        """
        from .events import TurnStart, ZoneEntered

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

        held = dict(self.world.zones.all()).get(zone)
        subs = [
            self.world.bus.on(ZoneEntered, on_enter),
            self.world.bus.on(TurnStart, on_turn),
        ]
        if held is not None and held.effect is not None:
            held.effect.subs.extend(subs)

    def choose[T](
        self, options: list[T], prompt: str = "", *, optional: bool = False,
        decline: str = "none of them",
    ) -> T | None:
        """Pick one. With `optional`, "none of them" is one of the answers.

        A printed **may** is a real choice and has to be offered as one. It
        was not: a row that let a creature do something took the first
        option in the list and did it, so an optional rider was compulsory
        and the player never saw the word. The decline goes last, so the
        engine's own pick -- the first option -- stays a real one.
        """
        if not options:
            return None
        pool = [*options, _Decline(decline)] if optional else list(options)
        picked = self.world.decide(self.me, "choose", pool, prompt or self.ref)
        return None if isinstance(picked, _Decline) else picked

    def may(self, what: str, *, who: int | None = None, default: bool = True) -> bool:
        """Ask whether an optional clause happens. `c.may("spend a surge")`.

        Asked of the creature it is about rather than the caster: a heal
        says the *target* can spend the surge, and whose surge it is decides
        whether it is worth spending.

        `default` puts that answer first, which matters more than it looks:
        an engine with nobody playing takes the first option, so the order
        is the answer for every fight run headless.
        """
        asker = self._who(who) or self.me
        yes, no = f"yes, {what}", f"no, do not {what}"
        pool = [yes, no] if default else [no, yes]
        return self.world.decide(asker, "may", pool, what) == yes

    def missing(self, on: int | None = None) -> int:
        """How many hit points this creature is down. 0 when untouched."""
        who = self._who(on)
        health = self.world.get(who, Health) if who else None
        return max(0, health.max_hp - health.hp) if health else 0

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
    """Every die showing its highest face. What a critical hit deals.

    No dice at all is a real expression, not a malformed one: a minion's
    damage is a flat number and nothing else. This returned `int("")` for
    it, so every minion in the game raised on a natural 20 -- about one
    attack in twenty, which is exactly rare enough that eight seeds a row
    missed it.
    """
    if isinstance(dice, int):
        return dice
    if not dice:
        return 0
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
