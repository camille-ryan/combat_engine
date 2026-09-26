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
    #: Was this swing a charge? Rides the same road `opportunity` does --
    #: several rows print a rider that only applies on one.
    charge: bool = False
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

    def cancel(self) -> bool:
        """Stop the thing that triggered this.

        Only an immediate interrupt can: by the time a reaction runs, its
        window has already closed and the attack has happened. Calling it
        from a reaction does nothing, which is the printed rule rather than
        an oversight.

        Most events cannot be refused at all -- `cancel` lives on `Decision`,
        and `ConditionApplied`, `Moved` and `DamageApplied` are plain
        announcements of something that has already happened. Asking anyway
        used to raise `AttributeError` from inside the row, which reads as a
        bug in the content; it is a fact about the event. Returns whether
        anything was actually stopped.
        """
        stop = getattr(self.trigger, "cancel", None)
        if stop is None:
            return False
        stop()
        return True

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
        """Line of effect **and** actually visible.

        This was line of effect and nothing else, so it answered True for a
        creature invisible to the asker -- and `if c.can_see(foe)` is what
        a row naturally writes. `query.unseen_by` is the question that
        consults `HIDDEN_FROM` and `sees_invisible` together, and its own
        docstring says it exists "so the sight and the combat advantage can
        never disagree"; the verb a body reaches for was walking straight
        past it.
        """
        from .query import unseen_by

        other = self._who(to)
        return (
            other is not None
            and line_of_effect(self.world, self.me, other)
            and not unseen_by(self.world, self.me, other)
        )

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

    def suffering(
        self, label: str = "", *, by: int | None = None, include_self: bool = False
    ) -> list[int]:
        """Everyone carrying an effect I applied. "Each creature affected by
        your X" is a common printed line and nothing could answer it.

        `label` picks out one power's effects; `by` defaults to the caster.

        The caster is left out unless asked for. "Each creature affected by
        your X" means the creatures you did it *to*, and a row that anchors
        its own sustain on itself found itself in this list and politely
        dragged itself across the board once a round.
        """
        source = self.me if by is None else by
        out = []
        for eid in creatures(self.world):
            if eid == self.me and not include_self:
                continue
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

    def save(
        self, *, on: int | None = None, bonus: int = 0, against: str = ""
    ) -> bool:
        """Roll a saving throw now against one save-ends effect.

        A few powers hand somebody an extra save out of turn. Returns True
        if something was shaken off.

        `against` picks which one: `"ongoing"` for the commonest printed
        form -- "a saving throw against an ongoing damage effect" -- or a
        label fragment. Without it this takes whichever save-ends effect it
        finds first, which may well be a daze when the row means the burn.

        **Follows `c.target`, and falls back to the caster.** "The target
        makes a saving throw" is how this is printed almost every time, so
        unlike `c.resist` and `c.stance` -- which are yours -- this one
        belongs to whoever the row is aimed at. A row that means the caster
        on a board where somebody else is targeted says `on=c.me`. A row declared
        `target=NO_TARGET` that answers its own trigger has `c.target` as
        None, and this used to return False without rolling or logging
        anything -- so the row looked finished and did nothing.
        """
        who = self._who(on) or self.me
        if who is None:
            return False
        for effect in self.world.effects.of(who):
            if against == "ongoing" and effect.ongoing is None:
                continue
            if against and against not in ("ongoing", "") and against not in effect.label:
                continue
            if effect.when is When.SAVE_ENDS:
                effect.save_mod += bonus
                self.world.effects.save(effect)
                return effect.ended
        return False

    def surge_value(self, of: int | None = None) -> int:
        """A quarter of that creature's maximum, which is what a surge heals.

        **Defaults to the caster.** It used to fall to `c.target`, and the
        docstring read as though it did not -- so "you regain hit points
        equal to your healing surge value" written as `c.surge_value()`
        quietly healed off the victim's maximum instead of yours.
        """
        who = self.me if of is None else of
        health = self.world.get(who, Health)
        return health.surge_value if health else 0

    def spend_surge(self, *, on: int | None = None) -> bool:
        """Spend a surge and gain nothing for it.

        The paladin's touch reads exactly that: the paladin pays and somebody
        else is healed.
        """
        from .resolve import spend_surge

        return spend_surge(self.world, on if on is not None else self.me)

    def size_of(self, on: int | None = None):  # noqa: ANN201
        from .components import Position
        from .types import Size

        pos = self.world.get(self._who(on), Position) if self._who(on) else None
        return pos.size if pos else Size.MEDIUM

    def turn_of(self) -> int | None:
        """Whose turn it is, for a trigger that cares."""
        return self.world.turn

    def effect(
        self,
        label: str,
        *,
        until: When = When.SAVE_ENDS,
        on: int | None = None,
        sustain: ActionType | None = None,
    ) -> Effect | None:
        """A named hold with no mechanical content of its own.

        For the rows that say "the target is subjected to <something> (save
        ends)" and then describe what that lets *you* do. The effect exists
        so it can be seen, saved against, and hung things on.

        `sustain=` is what a printed "Sustain Minor" costs. Without it a
        `When.SUSTAIN` hold has no cost for anyone to pay, and `durations`
        lapses it after a round -- so the obvious way to write a sustained
        effect quietly lasted one round and looked like it worked.
        `c.aura` and `c.zone` both took `sustain=` already; this was the
        odd one out.
        """
        who = self._who(on)
        if who is None:
            return None
        return self.world.effects.apply(
            who, self.me, until, label=label, sustain_cost=sustain
        )

    def invisible(
        self,
        *,
        to: int | None = None,
        on: int | None = None,
        until: When = When.SONT,
    ) -> Effect | None:
        """Cannot be seen -- by one creature, or by everybody.

        Held as `HIDDEN_FROM`, which `query.has_combat_advantage` already
        reads, so being unseen grants the advantage it should.

        `on` is *who* is unseen, and defaults to the caster. It hid the
        caster and nobody else, so "the creature **or one of its allies** is
        invisible to the target" had to set the relation by hand.
        """
        who = on or self.me
        watchers = [to] if to is not None else self.enemies()
        pairs = [(Relation.HIDDEN_FROM, who, w) for w in watchers if w is not None]
        if not pairs:
            return None
        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} unseen", relations=pairs
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

        who = on if on is not None else self.me
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
        """How fast somebody is. **Defaults to the caster**, not the target.

        "You can move your speed" is what every row saying this means, and
        it is written beside `c.move`/`c.shift`/`c.teleport`, which all
        default to the caster too. Routing this through `_who` made the bare
        call mean *the target's* speed -- so eight rows silently moved the
        caster the wrong distance, and a log cannot show it.
        """
        from .query import speed

        return speed(self.world, self.me if who is None else who)

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
        trigger: Any = None,
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
            # The trigger goes through. A row reading "when an ally drops,
            # the ally makes a basic attack" hands the swing to a creature
            # that is no longer alive, and `usable`'s act gate refuses it
            # without the event that explains why it should not.
            return use(
                self.world, who, chosen, targets=[target], spend=False,
                trigger=trigger if trigger is not None else self.trigger,
            )
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
            # The engine's ranged basic, unless the creature has one of its
            # own. `known.known` is non-empty for every character, so the
            # old test handed a PC its *melee* basic and every "an ally
            # makes a ranged basic attack" row was inert -- an archer with a
            # bow three squares off simply did nothing.
            own = next(
                (r for r in (known.known if known else ()) if r == RANGED), ""
            )
            ref = own or RANGED
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
            ignore_cover=ignore_cover, dying=self.dying, charge=self.charge,
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
        # The branch's own damage line. `damage_of` existed and had no
        # callers anywhere, so a row printing "2d8 melee or 1d10 ranged"
        # rolled the melee line whichever branch was used -- and looked
        # finished, because `attack_of` and `requires_of` are both wired.
        d = p.damage_of(self.branch) if p is not None else None
        if p is None or d is None:
            raise ValueError(f"{self.ref} declared no damage; call c.damage(...)")
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
            amount = self._roll_damage(dice) + bonus if dice else bonus
        return deal_damage(
            self.world, self.me, who, amount, dtype, detail or self.ref,
            opportunity=self.opportunity, charge=self.charge,
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
        amount = (self._roll_damage(dice) + bonus) // 2 if dice else bonus // 2
        return deal_damage(
            self.world, self.me, who, amount, dtype, f"{self.ref} (half)",
            opportunity=self.opportunity, charge=self.charge,
        )

    def flat(self, amount: int, *, dtype: DamageType = DamageType.UNTYPED,
             on: int | None = None) -> int:
        who = self._who(on)
        if who is None:
            return 0
        return deal_damage(
            self.world, self.me, who, amount, dtype, self.ref,
            opportunity=self.opportunity, charge=self.charge,
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
        """Ongoing damage. **Of one type, only the highest applies.**

        That is the printed rule and the engine stacked them: four burns of
        the same type left four separate holds and four saving throws to
        shake them off. Every burn in the tree was wrong by however many
        landed.

        A weaker one is refused outright; a stronger one replaces what is
        there, so the save still comes.
        """
        who = self._who(on)
        if who is None:
            return None
        # The rule itself lives in `Effects.apply`, because this is not the
        # only door: a "save ends both" hold carrying a burn and a condition
        # goes straight there.
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

    def shift_as(
        self,
        cost: ActionType,
        squares_: int = 1,
        *,
        on: int | None = None,
        until: When = When.STANCE,
    ) -> Effect | None:
        """"You can shift 2 squares as a move action."

        Not `c.shift`: nothing happens now. It is a standing change to what
        the creature may spend an action on, which `actions.legal` reads
        back -- a shift was one square for a move action and nothing else,
        so a stance whose entire content is a better one had no way to say
        it and read as an empty stance.

        Defaults to the **caster**, like the movement methods beside it.
        `until=When.STANCE` because that is what nearly all of them are;
        the effect ends when the next stance begins.
        """
        who = on if on is not None else self.me
        return self.grant_action("shift", cost, squares_=squares_, on=who, until=until)

    def grant_action(
        self,
        what: str,
        cost: ActionType,
        *,
        squares_: int = 1,
        on: int | None = None,
        until: When = When.STANCE,
    ) -> Effect | None:
        """Let a creature do an ordinary thing for a different action.

        "Allies within 3 squares of you can stand up as a minor action" is
        not a bonus, a condition or a power -- it is a line in the action
        menu that is normally a constant. `what` is `shift` or `stand`;
        anything else is carried, costs nothing and does nothing, so add
        the reader in `actions` at the same time as the word.

        Follows `c.target`, because the printed lines grant it to somebody
        else -- `on=c.me` for a stance about yourself, which is what
        `c.shift_as` passes.
        """
        who = self._who(on)
        if who is None:
            return None
        return self.bonus(
            f"{what} as {cost.value}", max(1, squares_), on=who,
            until=until, kind=self.ref,
        )

    def restore_use(self, ref: str, *, on: int | None = None) -> bool:
        """"You regain the use of your second wind."

        The inverse of spending one, and the opposite of `c.forbid`: that
        takes a row the creature still has, this hands back one it has
        already used. `Powers.restore` did the work and nothing on `Cast`
        reached it, so the half-dozen rows whose entire Effect is this line
        had no way to say it.

        Defaults to the **caster** -- every printed one is about its own
        owner -- and returns False if the row had not been used, which is
        the Requirement those rows print.
        """
        from .components import Powers as _Powers

        who = on if on is not None else self.me
        powers = self.world.get(who, _Powers)
        if powers is None or powers.times(ref) == 0:
            return False
        powers.restore(ref)
        self.world.bus.emit(Note(text=f"{who} regains the use of {ref}"))
        return True

    def initiative(self, amount: int, *, on: int | None = None) -> int:
        """"Each target gains a +10 bonus to his or her initiative check."

        Returns the creature's new initiative count. Follows `c.target`,
        because every row printing this hands the bonus out to a list that
        includes the caster rather than being about the caster.

        `c.bonus` cannot say it: `Initiative.bonus` is added before the d20
        is rolled, and a row triggered on `InitiativeRolled` is by
        definition answering a roll that has happened. Setting
        `ev.rolled` cannot say it either -- the sort reads the component,
        not the event. So this moves the creature in the order, and during
        the opening rolls `Encounter._roll_initiative` reads the component
        back after every announcement.
        """
        who = self._who(on)
        encounter = getattr(self.world, "encounter", None)
        if who is None or encounter is None:
            return 0
        return encounter.adjust_initiative(who, amount)

    def move(
        self, squares_: int, *, who: int | None = None, at: str = ""
    ) -> int:
        """Walk. `at` names a movement mode to travel at instead.

        "It flies up to its fly speed" came up short by the difference
        between the two, because the pathfinder measures `query.speed` and
        that is the ground speed. Three monster helpers had each worked
        around it by lending a speed modifier for the length of the move
        and taking it back in a `finally` -- the same fifteen lines three
        times, one of them a byte-for-byte copy of another.
        """
        mover = self.me if who is None else who
        lent = None
        if at:
            from .components import Movement

            mv = self.world.get(mover, Movement)
            extra = max(0, (mv.modes.get(at, 0) if mv else 0) - self.speed_of(mover))
            if extra:
                lent = self.bonus(
                    "speed", extra, until=When.EOT, on=mover, kind="untyped"
                )
        try:
            paths = self.world.reachable_paths(mover, squares_)
            if not paths:
                return 0
            dest = self.world.decide(
                mover, "move", sorted(paths), f"{self.ref}: move {squares_}"
            )
            return walk(self.world, mover, paths[dest])
        finally:
            if lent is not None:
                self.world.effects.end(lent, "the move ended")

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
        self,
        squares_: int,
        *,
        who: int | None = None,
        to: Square | None = None,
        share: bool = False,
    ) -> bool:
        """Blink somewhere. `to` names the square, as `c.shift` already allowed.

        Without it the destination goes through the decider, which with no
        decider installed takes the lowest-sorted square -- fine for a player
        being asked, useless for a row whose printed line says exactly where
        it arrives.
        """
        mover = self.me if who is None else who
        origin = squares(self.world, mover)
        # Filtered by the mover's whole footprint, not by the one square.
        # `movement.step` requires every square a Large creature covers to
        # be clear, so offering it a destination that only checks the
        # corner handed it squares it cannot stand in -- and a Large
        # creature's blink then failed silently, every seed.
        from .components import Position
        from .grid import footprint

        here = self.world.get(mover, Position)
        size = here.size if here is not None else None

        def fits(sq: Square) -> bool:
            covered = footprint(sq, size) if size is not None else {sq}
            return all(
                self.world.grid.passable(s)
                and (share or self.world.grid.occupant(s) in (None, mover))
                for s in covered
            )

        options = [sq for sq in spread(origin, squares_) if fits(sq)]
        if to is not None:
            # `share` arrives into an occupied square, which a row landing
            # somebody in a dying creature's space needs: `resolve._die`
            # lifts the body *after* `Dropped` is announced, so the square
            # is still taken during the interrupt window.
            return (
                teleport(self.world, mover, to, share=share) if to in options else False
            )
        if not options:
            return False
        dest = self.world.decide(mover, "teleport", sorted(options), f"{self.ref}: teleport")
        return teleport(self.world, mover, dest, share=share)

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

    def cure(self, *conditions: Condition, on: int | None = None) -> list[Condition]:
        """Take standing conditions off a creature. Returns what actually went.

        "You remove one condition from the target" and "you are no longer
        marked or slowed" are the same operation and nothing did it: every
        route out of a condition was a clock or a saving throw, so a row
        whose whole Effect is the removal had nothing to say.

        Follows `c.target`, like everything else done *to* somebody --
        `on=c.me` for the battlemind shape, which is about itself.

        Only the named condition goes. The effect that carried it keeps its
        modifiers, its ongoing damage and the saving throw it is still owed,
        because "remove one condition" is not "end the effect".
        """
        who = self._who(on)
        if who is None:
            return []
        return self.world.effects.cure(who, conditions)

    def immune(
        self, *conditions: Condition, until: When = When.EONT, on: int | None = None
    ) -> Effect | None:
        """"You cannot be marked or slowed until the end of your next turn."

        The other half of `c.cure`, and a different sentence: curing strips
        what is there, this refuses what arrives. Both are needed by the one
        printed line, and writing only the first leaves a row that shakes a
        mark off and is marked again by the same creature a beat later.

        `durations.Effects.apply` drops the condition on the way in and
        `relations.set` refuses the mark outright, so the rest of an effect
        -- its damage, its other conditions -- still lands.
        """
        who = self._who(on)
        if who is None:
            return None
        mods = [
            (who, Mod(what=f"immune to {c.value}", value=1, kind=self.ref, label=self.ref))
            for c in conditions
        ]
        if not mods:
            return None
        return self.world.effects.apply(
            who, self.me, until,
            label=f"{self.ref} immune to {', '.join(c.value for c in conditions)}",
            mods=mods,
        )

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

    def resist(
        self,
        amount: int,
        dtype: DamageType | None = None,
        *,
        until: When = When.ENCOUNTER,
        on: int | None = None,
    ) -> Effect | None:
        """Shrugs off `amount` of every hit, or of one damage type.

        The mirror of `c.vulnerable`, which existed on its own -- so a row
        printing "gains resist 10 to the triggering damage type" had to
        write `c.vulnerable(-10, ...)`, which comes to the same arithmetic
        and puts "vulnerable -10" on the card.
        """
        from .components import Defences

        who = on if on is not None else self.me
        kinds = [dtype] if dtype is not None else list(DamageType)
        defences = self.world.get(who, Defences) or self.world.add(who, Defences())
        for kind in kinds:
            defences.resist[kind] = defences.resist.get(kind, 0) + amount

        def undo() -> None:
            for kind in kinds:
                left = defences.resist.get(kind, 0) - amount
                if left > 0:
                    defences.resist[kind] = left
                else:
                    defences.resist.pop(kind, None)

        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} resist", on_end=[undo]
        )

    def grant_row(
        self, ref: str, *, on: int | None = None, until: When = When.ENCOUNTER
    ) -> Effect | None:
        """Let a creature use a row it does not know, for a while.

        The opposite number of `c.forbid`, and asked for twice before it
        existed -- "gains one use of an attack it has seen", "can make two
        attacks as a standard action". A row could be taken away and never
        given, so anything printing this had to be left out whole rather
        than half-written.
        """
        from .components import Powers

        who = on if on is not None else self.me
        known = self.world.get(who, Powers)
        if known is None or ref in known.known:
            return None
        effect = self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} grants {ref}",
            on_end=[lambda: known.known.remove(ref) if ref in known.known else None],
        )
        if effect is not None:
            known.known.append(ref)
        return effect

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
        solid: bool = False,
    ) -> int:
        """Put a conjuration on the board and return its entity id.

        **Creatures move through it unless the printed line says otherwise**,
        which is the rule and was not what this did. It used to claim its
        square in `grid.occupants` always, so nothing could ever enter --
        and "when an enemy enters its space", printed on several rows, was
        permanently false. `solid=True` is for the ones that really do
        block, a wall of fire rather than a spectral hound.

        It keeps its `Position` either way, so it is drawn, it can be
        targeted, and its aura follows it. `speed` is how far its creator
        may move it with a move action; `aura` gives it a footprint, which
        is what "each creature adjacent to it" reads off.

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
        if solid:
            place(self.world, eid, where)
        else:
            # The square is where it *is*, not something it owns. Setting
            # the position without indexing it in `grid.occupants` is the
            # whole difference between standing in a square and blocking it.
            self.world.need(eid, Position).square = where
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


    def moving_as(self, mode: str, *, on: int | None = None) -> bool:
        """Is this creature moving that way **right now**?

        "Requirement: the creature must be climbing" and "while it is not
        flying" are about what it is doing, not what it could do. `c.mode`
        and `Movement.modes` answer the second question and were the only
        thing available for the first, which made the gate true whenever the
        creature had the speed at all.
        """
        from .query import moving_as

        return moving_as(self.world, on or self.me, mode)

    def phasing(
        self, *, until: When = When.ENCOUNTER, on: int | None = None
    ) -> Effect | None:
        """Move through earth, rock and anything else in the way.

        A mode like any other, so it expires the same way. It still has to
        *stop* somewhere legal -- this only says the wall is not a wall on
        the way past.
        """
        return self.mode("phasing", self.speed_of(on or self.me), until=until, on=on)

    def mode(
        self, name: str, speed: int, *, until: When = When.ENCOUNTER, on: int | None = None
    ) -> Effect | None:
        """Grant a way of moving -- fly, swim, climb -- for a while.

        `Movement.modes` was only ever set when a creature was loaded, so a
        power granting flight had nothing to write to.
        """
        from .components import Movement

        who = on if on is not None else self.me
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
        who = on if on is not None else self.me
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

    def mark(
        self, *, until: When = When.EONT, on: int | None = None, by: int | None = None
    ) -> Effect | None:
        """Mark the target -- for you, or for somebody else.

        `by=` is the bard's whole conceit: "the target is marked by an ally
        within 5 squares of you". `c.marked` has always been able to *ask*
        about a mark somebody else laid; until now nothing could lay one.
        """
        who = self._who(on)
        if who is None:
            return None
        marker = self.me if by is None else by
        if marker == who:
            return None          # nothing is marked by itself
        return self.world.effects.apply(
            who, marker, until, label=f"{self.ref} mark",
            relations=[(Relation.MARKED_BY, marker, who)],
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
        self, *, from_: int | None = None, on: int | None = None,
        until: When = When.EOTNT
    ) -> Effect | None:
        """Walking away from that creature does not give it an opening.

        A handful of rows say so outright. Implemented as an interrupt on the
        opportunity window rather than as a flag movement would have to
        consult, so it applies wherever the window opens and needs nothing
        added to the movement rules.

        `on=` is who gets the immunity, and it defaults to the **caster**
        because nearly every printed line is about yourself. Without it the
        other printed shape -- "the target cannot make opportunity attacks
        against any creature other than you" -- could not be said at all,
        since that one hands the immunity to everybody else on the board.
        """
        from .events import OpportunityWindow

        # `from_` untouched by `_who`: None means **anybody**, which the
        # veto below already handles and which "you can move your speed
        # without provoking opportunity attacks" needs. Routing it through
        # `_who` narrowed the bare call to the power's target -- the
        # opposite of what leaving the argument out reads as.
        who = from_
        me = on if on is not None else self.me

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

        who = on if on is not None else self.me

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

    def half_healing(
        self, *, on: int | None = None, until: When = When.SAVE_ENDS
    ) -> Effect | None:
        """"The target regains half the normal hit points from healing."

        A listener on `Healed`, which is negotiable now, rather than clawing
        the surplus back off `Health` afterwards -- that came to the right
        total and put the wrong number in the log.
        """
        from .events import Healed

        who = on or self._who(None) or self.me

        def halve(ev: Healed) -> None:
            if ev.target == who:
                ev.amount //= 2

        return self.watch(
            Healed, halve, until=until, window=Window.BEFORE, on=who,
            label=f"{self.ref} half healing",
        )

    def cannot_be_flanked(
        self, *, on: int | None = None, until: When = When.ENCOUNTER
    ) -> Effect | None:
        """"Enemies can't gain combat advantage by flanking it."

        Only the flanking branch: being dazed, hidden from, or granted the
        opening outright still works, which is what the printed line says.
        """
        return self.bonus(
            "unflankable", 1, on=on or self.me, until=until, kind="untyped"
        )

    def conceal(
        self,
        *,
        when: Callable[[dict[str, Any]], bool] | None = None,
        on: int | None = None,
        until: When = When.EONT,
        total: bool = False,
    ) -> Effect | None:
        """"You gain concealment." -2 to attacks against you, -5 if total.

        Defaults to the **caster**: every printed line that grants this says
        "you" or "you and your allies", and the handful aimed elsewhere say
        so. Cover and concealment do not add -- `resolve.attack` takes the
        larger.

        Seven classes print this and every such row was left out of the tree
        for want of it, because `query.cover_between` computes cover from
        two positions and reads no modifier at all. Do not reach for
        `c.zone(blocks_sight=True)` instead: that is terrain, and it blinds
        both sides.

        `when` is handed the attack context, so "concealment from creatures
        more than 3 squares away" is sayable -- a creature printing that had
        to hand-roll four bonuses to defences instead, which stacked with
        cover where concealment must take the larger of the two.
        """
        # `kind="concealment"` so two sources do not add. Untyped modifiers
        # stack, so a creature concealed three times over came to 6 and read
        # as *total* concealment -- a -5 nobody printed. Same kind means the
        # larger wins, which is the stacking rule.
        return self.bonus(
            "concealment", 5 if total else 2,
            on=on if on is not None else self.me, until=until,
            kind="concealment", when=when,
        )

    def see_invisible(
        self, *, on: int | None = None, until: When = When.EONT
    ) -> Effect | None:
        """"You can see invisible creatures and objects."

        Defaults to the **caster**: it is a sense of yours, like `c.mode`
        and `c.resist`, and every printed line granting it says "you".

        Invisibility is held as `HIDDEN_FROM` and the only rule that reads
        it is combat advantage, so this is what turns that one branch off
        for one watcher. It does not make a hidden creature a legal target
        for anything that needs line of sight -- nothing in the engine asks
        that question yet -- so a row wanting *only* the targeting half is
        still not sayable.
        """
        return self.bonus(
            "see_invisible", 1, on=on if on is not None else self.me,
            until=until, kind=self.ref,
        )

    def ignore_cover(
        self,
        *,
        on: int | None = None,
        until: When = When.EONT,
        partial: bool = False,
        when: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Effect | None:
        """"You ignore cover and concealment when attacking."

        Defaults to the **caster**, because this is your eyesight rather
        than something done to the target -- `c.no_cover` is the same
        sentence written from the other end, and that one follows
        `c.target`.

        `ignore_cover=` already existed as an argument to one `c.strike`,
        which cannot say "until the end of your next turn" and cannot be
        read by an opportunity attack or by an ally. `when` is handed the
        attack context, so "against any enemy within the zone" is a gate.

        `partial=True` waives the ordinary -2 and leaves superior cover
        standing, which is the narrower line two rows print.
        """
        return self.bonus(
            "ignore_cover", 2 if partial else 5,
            on=on if on is not None else self.me,
            until=until, kind="ignore cover", when=when,
        )

    def no_cover(
        self,
        *,
        on: int | None = None,
        until: When = When.EONT,
        partial: bool = False,
        when: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Effect | None:
        """"The target does not benefit from cover or concealment."

        `c.ignore_cover` sits on whoever is looking; this sits on whoever is
        being looked at, and so follows `c.target`. That is the difference
        between "you ignore cover" and "it gains no cover against anybody",
        and a row that prints the second cannot be written as the first
        without also blinding the caster to every other creature's cover.

        `when` is the attack context, which carries `attacker` -- so "on
        attacks made by you or allies adjacent to you" is a gate rather
        than an approximation.
        """
        return self.bonus(
            "no_cover", 2 if partial else 5, on=on, until=until,
            kind="ignore cover", when=when,
        )

    def no_advantage(
        self, *, on: int | None = None, until: When = When.EONT
    ) -> Effect | None:
        """"You do not grant combat advantage to any of your enemies."

        The wider sentence, and the inverse of `c.grants_advantage`. Where
        `c.cannot_be_flanked` shuts one branch, this shuts all of them --
        flanked, dazed, hidden from, or granted outright. Defaults to the
        **caster**, because the printed line is nearly always about yourself;
        pass `on=` for the row that says otherwise.

        Four rows were left out for want of it, across three classes, each
        agent naming it slightly differently -- the +2 is worked out inside
        `query.has_combat_advantage` from the board, so no modifier could
        reach it until that read a key.
        """
        return self.bonus(
            "no_advantage", 1, on=on if on is not None else self.me,
            until=until, kind="untyped",
        )

    def maximise(
        self,
        *,
        on: int | None = None,
        ref: str = "",
        until: When = When.EONT,
        critical: bool = False,
    ) -> Effect | None:
        """The next damage this creature rolls comes out maximum.

        "The attack deals maximum damage" is a printed line that could only
        be faked before: `_max_of` computes the number and is private, and
        `DamageRolled` carries the rolled total rather than the dice.
        Setting `critical` instead would pay out every crit rider, which is
        not what the line says.
        """
        from .dsl import get
        from .events import DamageRolled

        who = on or self.me
        spent: list[bool] = []

        def top_up(ev: DamageRolled) -> None:
            # **The next roll, not every roll in the window.** It used to
            # top up anything the creature rolled until the duration ran
            # out, so a row whose printed splash is a flat 3 to each
            # creature beside the victim came out [23, 23, 23, 23] instead
            # of [23, 3, 3, 3] -- and the riders were rewritten to the
            # header's dice, which is not a number the card mentions
            # anywhere.
            if ev.source != who or spent:
                return
            # The row that *rolled*, off the event -- not the row that armed
            # this. Both rows wanting it are free actions with no damage
            # line of their own ("Trigger: it hits with an implement
            # attack. Effect: the attack deals maximum damage"), so reading
            # `self.ref` found nothing and the listener did nothing at all.
            # `Cast.damage` already sets `detail` to whoever is rolling.
            # The row that rolled, unless one is named. "The attack deals
            # maximum damage" is about whatever swung; `ref` is for the rare
            # line that names a row instead.
            p = get(ref or ev.detail)
            d = p.damage_of(0) if p is not None else None
            if d is None:
                return
            topped = _max_of(d.dice) + self._bonus_of(d.bonus)
            # A rider rolled by the same row carries the same `detail`, so
            # the header's line is the wrong yardstick for it. Only raise
            # what is plausibly *this* line: a flat 3 is not a 2d10+3 that
            # rolled badly.
            if ev.amount < _min_of(d.dice) + self._bonus_of(d.bonus):
                return
            ev.amount = max(ev.amount, topped)
            spent.append(True)

        held = self.watch(
            DamageRolled, top_up, until=until, window=Window.BEFORE, on=who,
            label=f"{self.ref} maximum damage",
        )
        if critical and held is not None:
            # "Treated as a critical hit" is more than maximum damage -- it
            # pays every crit rider too -- so it is set on the live result
            # rather than faked by topping the number up.
            from .events import Hit

            def crit(ev: Hit) -> None:
                if ev.attacker == who and ev.result is not None:
                    ev.result.critical = True

            held.subs.append(
                self.world.bus.on(Hit, crit, window=Window.BEFORE, owner=who)
            )
        return held

    def threatens(
        self, squares_: int = 2, *, on: int | None = None, until: When = When.ENCOUNTER
    ) -> Effect | None:
        """How far this creature threatens for opportunity attacks.

        "It can make opportunity attacks against enemies within 2 squares"
        had no expression: the window was opened from a ring fixed at one.
        A held modifier, so "gains reach 2" can raise it too.
        """
        return self.bonus(
            "reach", max(0, squares_ - 1), on=on or self.me, until=until,
            kind="untyped",
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

    def second_wind(self, *, on: int | None = None) -> bool:
        """Take a second wind: a surge, and +2 to AC until your next turn.

        The only implementation. `actions.perform` used to own it and there
        was no door from a power body, so three content helpers had written
        it out again -- and each of their docstrings says so, which is the
        tell. A bare `c.surge` is not the same thing: the use has to be
        counted in `Powers` or the creature can take a second one.

        Returns False if it has already been taken this fight.
        """
        from .components import Health, Powers
        from .resolve import spend_surge

        who = on if on is not None else self.me
        health = self.world.get(who, Health)
        if health is None:
            return False
        known = self.world.get(who, Powers)
        if known is not None:
            if known.times("second-wind"):
                return False
            known.note_use("second-wind", self.world.round)
        spend_surge(self.world, who)
        self.world.heal(who, who, health.surge_value)
        self.bonus("ac", 2, until=When.SONT, on=who, kind="untyped")
        return True

    def forces(
        self,
        squares_: int = 1,
        *,
        on: int | None = None,
        until: When = When.ENCOUNTER,
        when: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Effect | None:
        """Lengthen every push, pull and slide this creature makes.

        The other side of `c.resist_forced`, and the one that was missing:
        the shove read a `"forced"` modifier off the creature *being*
        shoved and nothing at all off the one doing it, so "your pushes
        move the target 1 extra square" could not be said. It is a feat
        and a magic-item line rather than a one-off, so it gets a key --
        `"forcing"` -- rather than being faked as a negative `"forced"` on
        every possible victim.

        The gate is handed `how` (push, pull or slide) and `power`, so
        "your *pushes*" and "when you push with <this row>" are both
        sayable.

        Defaults to the caster: a row printing this is describing itself.
        """
        return self.bonus(
            "forcing", squares_, on=on if on is not None else self.me,
            until=until, kind="untyped", when=when,
        )

    def on_sustain(self, effect: Effect | None, fn: Callable[[], None]) -> bool:
        """What happens each time this effect is sustained.

        "Sustain Minor: the target takes 1d6 + 3 damage and is pulled 3."
        The clock refreshing was the whole of what sustaining did, so the
        payout half of every such line had nowhere to go.
        """
        if effect is None:
            return False
        effect.on_sustain.append(fn)
        return True

    def no_basic(self, *, on: int | None = None, until: When = When.ENCOUNTER) -> Effect | None:
        """Take away what this creature's basic attack *is*, not the ability.

        "Cannot make basic attacks" bars the designation -- what a granted
        swing reaches for, and what an opportunity attack rolls. A monster's
        basic attack is one of its own abilities, so forbidding the ref would
        stop it using that ability at all, which the printed line does not
        say.
        """
        from .components import Powers

        who = on or self.me
        known = self.world.get(who, Powers)
        if known is None:
            return None
        was, was_opp = known.basic, known.opportunity

        def restore() -> None:
            known.basic, known.opportunity = was, was_opp

        known.basic, known.opportunity = "", ""
        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} no basic attack",
            on_end=[restore],
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

    def reduce(self, amount: int, ev: Any = None) -> int:
        """Take a number off damage that has been rolled but not yet dealt.

        "Reduce the damage by 5", "the target takes half damage" -- printed
        on interrupts all over the leader and defender classes. `c.absorb`
        moves the *whole* blow somewhere else and was the only thing near
        it, so rows were reaching into `c.trigger.amount` by hand: three
        ardent rows and two psion ones did, which is the tell that this was
        missing rather than that content wanted the freedom.

        Returns how much was actually taken off, which is less than asked
        when the blow was smaller than the reduction.
        """
        ev = ev if ev is not None else self.trigger
        was = max(0, getattr(ev, "amount", 0)) if ev is not None else 0
        if was <= 0 or amount <= 0:
            return 0
        ev.amount = max(0, was - amount)
        return was - ev.amount

    def halve(self, ev: Any = None) -> int:
        """"The target takes half damage" from an interrupt answering the blow."""
        ev = ev if ev is not None else self.trigger
        was = max(0, getattr(ev, "amount", 0)) if ev is not None else 0
        return self.reduce(was - was // 2, ev)

    def run_at(self, victim: int, *, who: int | None = None) -> bool:
        """Walk into reach of a named creature, the way a charge's move does.

        `c.move` picks its own destination through the decider, which is
        right for "it moves" and useless for "it charges *that one*". The
        path is chosen here, shortest first, the same way `actions._charges`
        chooses one. Returns whether the target is in reach afterwards.
        """
        from .movement import walk
        from .query import squares

        runner = who if who is not None else self.me
        beside = spread(squares(self.world, victim), 1)
        paths = self.world.reachable_paths(runner, self.speed_of(runner))
        best = min(
            (
                (len(path), dest, path)
                for dest, path in paths.items()
                if dest in beside and path
            ),
            default=None,
        )
        if best is not None:
            walk(self.world, runner, list(best[2]))
        return adjacent(self.world, runner, victim)

    def charge_at(self, victim: int, ref: str = "", *, who: int | None = None) -> bool:
        """Run at somebody and swing, with the swing marked as a charge.

        `actions.perform` builds a charge out of a walk plus
        `use(..., charge=True)`, and a row whose printed Effect *is* the
        charge is doing the same thing from inside a body. The flag is not
        decoration: it is what puts `charge` on the attack events and in
        both modifier contexts, which is what every charge rider reads.

        Three content files had grown their own copy of this.
        """
        from .components import Powers
        from .dsl import use

        # `who` charges instead of the caster -- "three of its allies can
        # charge one creature of its choice". `c.grant_attack` hands over
        # the swing without the move or the flag, which is the half of that
        # line that matters.
        runner = who if who is not None else self.me
        if not self.run_at(victim, who=runner):
            return False
        if not ref:
            known = self.world.get(runner, Powers)
            ref = (known.basic if known else "") or "mba"
        return use(
            self.world, runner, ref, targets=[victim], spend=False, charge=True
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
            # The line that tramples the most, *ranked*. This said so and
            # did not: it offered the reachable squares in sorted order, and
            # with no decider installed `World.decide` takes the first --
            # the lowest-sorted square on the board. So a bare `c.overrun()`
            # reliably walked away from everybody and trampled nobody, which
            # is exactly what a wrong row looks like.
            from .movement import _line
            from .query import enemies as _foes
            from .query import squares as _sq

            here = reachable(self.world, self.me, self.speed_of())
            if not here:
                return []
            theirs = {s: f for f in _foes(self.world, self.me) for s in _sq(self.world, f)}

            def crossed(dest: Square) -> int:
                path = _line(self.here, dest)
                return len({theirs[s] for s in path if s in theirs})

            ranked = sorted(here, key=lambda d: (-crossed(d), d))
            to = self.world.decide(self.me, "overrun", ranked, "trample to")
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

    # -- a second body you own ----------------------------------------------

    def companion(self, *, of: int | None = None) -> int | None:
        """The companion this creature owns, if it has one on the board.

        The question 107 blocked rows were asking. A companion is not a
        conjuration -- it belongs to the character rather than to the power
        that made it, it persists, and it can be hit -- and it is not a
        servant either, because it never takes a turn of its own.
        """
        from .components import Companion

        owner = of if of is not None else self.me
        for eid in self.world.having(Companion):
            if self.world.get(eid, Companion).owner == owner:
                return eid
        return None

    def call_companion(
        self,
        ref: str = "",
        at: Square | None = None,
        *,
        kind: str = "spirit",
        speed: int = 6,
    ) -> int:
        """Put your companion on the board, moving the one you have if any.

        "You can call it again" is printed on nearly every row that can
        dismiss one, and the printed reading is that you only ever have the
        one -- so calling again relocates rather than accumulating.

        With no `ref` the companion's numbers come off its owner, which is
        what the printed spirit does: its hit points are the shaman's surge
        value, its defences are the shaman's, and it has no attack of its
        own because every attack it makes is a row the shaman used. A
        database ref is for the ones that really are their own creature --
        a ranger's beast.
        """
        from dataclasses import replace

        from .components import (
            Companion,
            Defenses,
            Health,
            Movement,
            Position,
            Side,
            Stats,
        )
        from .grid import Size
        from .query import team as side_of

        where = at or self._free_square_near(self.here)
        if where is None:
            return 0
        standing = self.companion()
        if standing is not None:
            from .movement import place

            place(self.world, standing, where)
            return standing

        side = side_of(self.world, self.me) or Team.ALLY
        if ref:
            from combat_engine.content import loader

            made = loader.spawn(self.world, ref, where, team=side)
        else:
            mine = self.world.need(self.me, Defenses)
            hp = max(1, self.surge_value())
            made = self.world.spawn(
                Position(square=where, size=Size.MEDIUM),
                Side(team=side),
                Health(hp=hp, max_hp=hp),
                # Its own copy, so buffing the spirit does not buff the
                # shaman and a mark laid on one is not laid on both.
                Defenses(values=dict(mine.values), scale=mine.scale),
                Movement(speed=speed),
                # Its owner's level and scores. Not decoration: anything
                # that asks a creature for an attack bonus goes through
                # `Cast.stats`, which does `world.need(me, Stats)` and
                # raises on a creature without one -- so a companion
                # lacking it made four unrelated rows blow up inside
                # `bonus_for` rather than anywhere near the companion.
                replace(self.world.need(self.me, Stats)),
            )
        self.world.add(made, Companion(owner=self.me, ref=ref, kind=kind))
        return made

    def summon_inline(self, spec: Any, at: Square | None = None) -> int:
        """Put a creature the *power itself* defines on the board.

        `c.summon(ref)` needs a row in the database, and thirty-six printed
        blocks give their creature no id at all -- they print its speed,
        its defences and its attack line in the power's own text. This
        takes that block.

        Spawned as a `Companion`, which is the right shape and already
        exists: targetable, no initiative slot, no vote on the fight. A
        summon in play acts only when its summoner spends an action
        commanding it, so having no turn is the printed rule.

        Several may stand at once -- "you summon two" is printed -- so this
        does not relocate the way `c.call_companion` does.
        """
        from dataclasses import replace

        from .components import (
            Companion,
            Defenses,
            Health,
            Movement,
            Position,
            Side,
            Stats,
        )
        from .events import Summoned
        from .grid import Size
        from .query import team as side_of

        where = at or self._free_square_near(self.here)
        if where is None:
            return 0
        mine = self.world.need(self.me, Defenses)
        hp = spec.hp or max(1, self.surge_value())
        # Per-defence first, falling back to the flat offset. Five rows
        # print "+2 to AC and Fortitude" and one number gave Reflex and
        # Will the bonus too.
        each = spec.per_defence or {}
        made = self.world.spawn(
            Position(square=where, size=Size(spec.size)),
            Side(team=side_of(self.world, self.me) or Team.ALLY),
            Health(hp=hp, max_hp=hp),
            Defenses(
                values={
                    k: v + each.get(str(k), spec.defences)
                    for k, v in mine.values.items()
                },
                scale=mine.scale,
            ),
            # `Movement.modes` maps a name to its own speed, so "speed 0,
            # fly 6" is sayable. Built as a set of names, every later
            # `c.mode`, `c.phasing` or `c.moving_as` on the summon raised
            # on `.get`.
            Movement(speed=spec.speed, modes=_modes_of(spec)),
            replace(self.world.need(self.me, Stats)),
        )
        self.world.add(
            made, Companion(owner=self.me, ref=spec.label or self.ref, kind="summon")
        )
        # Announced, because `World.spawn` says nothing and a row whose
        # whole Effect is "you summon X" left no trace at all -- four
        # correct rows reported SILENT for it.
        self.world.bus.emit(
            Summoned(actor=self.me, summon=made, ref=spec.label or self.ref)
        )
        return made

    def command(self, who: int, *, on: int | None = None) -> AttackResult | None:
        """Spend your action making a summon attack with **its own** line.

        The half `from_=` could not do: it moves where the attack is
        measured and rolled from, and leaves the numbers the summoner's. A
        printed block that gives its creature an attack bonus means that
        bonus, so this reads the header's `summon=` line and rolls it from
        the creature.
        """
        from .dsl import get

        p = get(self.ref)
        spec = getattr(p, "summon", None) if p else None
        if spec is None or spec.attack is None:
            return None
        bonus = spec.attack.bonus_for(self.world, who, self.ref, self.branch)
        hit = self.attack(bonus, spec.attack.vs, on=on, from_=who)
        if hit and spec.damage is not None:
            line = spec.damage
            # Through `_bonus_of`, the way `c.hit` reads a header's damage.
            # Every printed summon block says "+ Intelligence modifier", which
            # is `Damage(..., "int")` -- handed to `c.damage` raw it reached
            # `roll(dice).total + "int"` and every one of them raised.
            self.damage(
                line.dice, self._bonus_of(line.bonus), dtype=line.dtype, on=on
            )
        return hit

    def dismiss_companion(self) -> bool:
        """"Your spirit companion disappears." An Effect line on ~20 rows."""
        standing = self.companion()
        if standing is None:
            return False
        self.world.despawn(standing)
        return True

    def move_companion(self, squares_: int) -> int:
        """Walk the companion. It has a speed of its own and no turn to use it."""
        standing = self.companion()
        return self.move(squares_, who=standing) if standing is not None else 0

    def extra_turn(self, at: int) -> bool:
        """Act again this round, at that initiative count. Solos do this."""
        if self.world.encounter is None:
            return False
        self.world.encounter.extra_turn(self.me, at)
        return True

    def reroll_initiative(self, *, on: int | None = None) -> int:
        """Take a new initiative check and move in the order. Returns the roll."""
        who = on or self.me
        enc = self.world.encounter
        return enc.reroll_initiative(who) if enc is not None else 0

    def autohit(self, ev: Any = None) -> bool:
        """Make the attack being answered simply hit. It cannot be rolled away.

        The outcome is recomputed from the die once the interrupt window
        closes, so setting `hit` on the result is thrown away and rigging
        the total would be faking a number the log then shows.
        """
        ev = ev if ev is not None else self.trigger
        result = getattr(ev, "result", None) if ev is not None else None
        if result is None:
            return False
        result.forced = True
        return True

    def unsave(self, ev: Any = None) -> bool:
        """Make the saving throw being rolled fail. "It automatically fails."

        Only means anything inside a listener on `SavingThrow`, which is
        announced before it is acted on.
        """
        ev = ev if ev is not None else self.trigger
        if ev is None or not hasattr(ev, "saved"):
            return False
        ev.saved = False
        return True

    def had_advantage(self, ev: Any = None) -> bool:
        """Did *that* attack have combat advantage? Reads the event.

        Asking `has_combat_advantage` again after the fact is too late: a
        one-shot grant has already been spent by the time `Hit` is
        announced, so the question comes back false and two traits on the
        same stat block quietly fail to combine. The live `AttackResult`
        rides on the attack events, and this is where to read it.
        """
        ev = ev if ev is not None else self.trigger
        result = getattr(ev, "result", None) if ev is not None else None
        return bool(result and result.advantage)

    def cannot_attack(
        self,
        *,
        on: int | None = None,
        against: int | None = None,
        until: When = When.SAVE_ENDS,
    ) -> Effect | None:
        """Bar a creature from attacking -- everything, or one creature.

        "The target cannot attack (save ends)" and "cannot attack **you**"
        are the charm and fear shapes, and neither could be said: `c.forbid`
        takes one named row away and `c.no_basic` takes away what a row is
        used *as*. Refuses at the declaration, so nothing is rolled and no
        rider fires.
        """
        from .events import AttackDeclared

        who = self._who(on)
        if who is None:
            return None

        def refuse(ev: AttackDeclared) -> None:
            if ev.attacker == who and (against is None or ev.target == against):
                ev.cancel("cannot attack")

        return self.watch(
            AttackDeclared, refuse, until=until, window=Window.BEFORE, on=who,
            label=f"{self.ref} cannot attack",
        )

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
        kind: str = "untyped",
        when: Callable[[dict[str, Any]], bool] | None = None,
        once: bool = False,
        stacks: bool = True,
    ) -> Effect | None:
        """A numeric modifier with a duration.

        **`kind` is the 4e bonus type and it decides whether this stacks.**
        Two bonuses of the same type do not add -- the larger applies --
        and untyped ones do add, so writing the wrong type is a number
        that is silently too big or too small in every fight.

        Unspecified means **untyped**, which is what the absence of a type
        word on a card means. It used to mean `"power"`, so `Mod` and this
        gave different answers to the same question and a row printing a
        plain "+2 to attack" was quietly non-stacking. `scripts/bonuses.py`
        compares every call against the word in front of "bonus" on its
        card and wrote the 283 explicit `kind=`s that this change would
        otherwise have altered.

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
        # `stacks=False` buckets this row's bonus under its own ref, so a
        # second one from the same row does not add -- the larger wins, the
        # way two bonuses of a type do. "This bonus increases to +4" and "a
        # second hit renews rather than doubles" are both that sentence,
        # and both used to lean on being `kind="power"` by accident. One
        # row had already discovered the trick and written `kind=c.ref`.
        if not stacks:
            kind = self.ref
        key = what.value if isinstance(what, Defense) else what
        mod = Mod(what=key, value=value, kind=kind, when=when, label=self.ref)
        effect = self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} {key}{value:+d}", mods=[(who, mod)]
        )
        if once and effect is not None:
            from .events import AttackRolled, DamageRolled, Hit

            # A one-shot *damage* bonus has to be spent on the damage, not
            # on the roll. `resolve.attack` emits `AttackRolled` before the
            # body ever rolls damage, so watching that ended the effect
            # before `deal_damage` read the "damage" mods and the bonus
            # never once applied. Correct for an attack bonus, where the
            # roll has already been made.
            # Three kinds of one-shot, and they are spent at three
            # different moments. An attack bonus is spent on the roll,
            # because by then it has been used. A damage bonus cannot be --
            # `AttackRolled` fires before the body rolls damage. And a
            # *defence* bonus is spent when the blow lands or misses:
            # `resolve.attack` re-reads the defence after announcing the
            # roll, so spending it on `AttackRolled` removes it before the
            # comparison it exists for, and the owner is the defender
            # rather than the attacker, so the old filter never matched.
            # `crit_range` is read when the outcome is recomputed, which is
            # *after* `AttackRolled` -- so spending it there ended it before
            # the one comparison it exists for, exactly as the damage and
            # defence cases did. Three branches of this method have now been
            # wrong in the same way; the moment a modifier is spent has to
            # be the moment it is read, and nothing in the signature says
            # when that is.
            if key == "crit_range" or isinstance(what, Defense):
                from .events import Miss

                def spend_defence(ev: Hit | Miss) -> None:
                    if ev.target == who:
                        self.world.effects.end(effect, "used")

                for kind in (Hit, Miss):
                    effect.subs.append(
                        self.world.bus.on(kind, spend_defence, owner=who)
                    )
            elif key == "damage":

                def spend_damage(ev: DamageRolled) -> None:
                    if ev.source == who and mod.applies(
                        {"target": ev.target, "power": ev.detail}
                    ):
                        self.world.effects.end(effect, "used")

                effect.subs.append(
                    self.world.bus.on(DamageRolled, spend_damage, owner=who)
                )
            else:

                def spend(ev: AttackRolled) -> None:
                    if ev.attacker != who:
                        return
                    if mod.applies({"attacker": ev.attacker, "target": ev.target,
                                    "power": ev.power, "advantage": ev.advantage}):
                        self.world.effects.end(effect, "used")

                effect.subs.append(self.world.bus.on(AttackRolled, spend, owner=who))
        return effect

    def penalty(self, what: str | Defense, value: int, **kw: Any) -> Effect | None:
        """A negative modifier. **It takes no `kind`, and that is the rule.**

        Penalties have no type in 4e. They add, except that two from the
        same source do not -- so what decides their stacking is the row
        that laid them, which `Mods.total` reads off `Mod.label` and this
        sets for free. A `kind=` here was silently discarded by
        `value < 0`, and six rows were passing one; taking the argument
        away is the difference between a parameter that does nothing and
        a `TypeError` where it is written.
        """
        if "kind" in kw:
            raise TypeError(
                "c.penalty takes no kind: penalties have no type in 4e, and "
                "what stops two of them stacking is coming from the same row"
            )
        return self.bonus(what, -abs(value), **kw)

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

        `by` is whose attacks to watch. **It has no default target**: left
        out, it watches everybody, which is what "whenever a creature
        attacks" means. It used to fall through to `c.target`, so on a
        `target=SELF` row a bare call silently watched the caster alone.

        Written out by hand it is a `watch` plus a filter plus a latch, three
        times per class. Here once.
        """
        from .events import AttackDeclared

        who = by
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
        who = on if on is not None else self.me
        holder: list[Effect] = []

        def fire(ev: Any) -> None:
            before = len(self.world.bus.log)
            held = len(self.world.effects.live)
            fn(ev)
            # `once` means "fire once", not "live for one event", and those
            # differ for every trigger with a guard -- which is most of them.
            # Ending unconditionally burned the effect on the first event of
            # the right *class*, so "the first time you hit a bloodied enemy"
            # was spent by the first attack that missed a healthy one.
            # Whether the body did anything is read off the log.
            # Anything the handler *did*, not only what it announced.
            # `c.summon` puts a creature on the board and in the order and
            # emits nothing at all, so a once-only row whose whole effect is
            # a summon never spent its hold and fired every round.
            did = len(self.world.bus.log) > before or len(self.world.effects.live) != held
            if once and holder and did:
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

    def my_aura(self, label: str = "") -> int:
        """The caster's own live aura, or 0 if it has none.

        "Your aura gains the following effect" is printed on twelve bard
        rows and every one of them was left out, because `c.aura` can only
        make a *new* one -- at a radius the spec never states -- and there
        was no way to ask for the one you already have. With this, such a
        row hangs its payout on the standing aura and the radius stays the
        class feature's business, which is where the card puts it.

        `label` narrows it when a creature has more than one.
        """
        mine = [
            zid
            for zid, z in self.world.zones.all()
            # `z.aura` is the radius, and a plain zone's is 0 -- so this is
            # what tells "an aura around me" from "a patch of ground I
            # made", which both answer `owner == me`.
            if z.aura and z.owner == self.me and (not label or label in (z.label or ""))
        ]
        return mine[-1] if mine else 0

    def hazard(
        self,
        area: Iterable[Square],
        amount: str | int,
        dtype: DamageType = DamageType.UNTYPED,
        *,
        label: str = "",
        until: When = When.SUSTAIN,
        difficult: bool = False,
        blocks_sight: bool = False,
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
            blocks_sight=blocks_sight,
            sustain=sustain if until is When.SUSTAIN else None,
        )
        self.burns(zone, amount, dtype)
        return zone

    def burns(
        self, zone: int, amount: str | int, dtype: DamageType = DamageType.UNTYPED
    ) -> None:
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
            # Rolled per bite when it is dice, not once when the zone is
            # made. A flat number stays flat. Several auras print "takes
            # 1d8 fire damage" and had to hand-roll the whole watcher pair
            # because this only took an int.
            bit = self.roll(amount) if isinstance(amount, str) else amount
            self.world.damage(source, who, bit, dtype, detail=f"{self.ref} zone")

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

    def grants_in(
        self,
        zone: int,
        what: str | Defense,
        value: int,
        *,
        side: str = "ally",
        kind: str = "power",
    ) -> None:
        """A zone that carries a modifier for as long as you stand in it.

        The counterpart of `c.burns`, and the same shape: hung on the
        zone's own effect so it dies with the zone. "While within the zone
        you and your allies gain a +1 power bonus to AC" is printed all
        over warden, shaman and artificer, and every such row was written
        without its bonus or left out -- a zone could bite you but never
        help you.

        **It ends when you leave**, which is the half a plain
        `c.bonus(until=...)` cannot say: a duration runs on the clock and
        this runs on the geometry. Whoever is already standing inside when
        the zone is made gets it too, since the printed line is about being
        there rather than about arriving.

        `side` is whose: `"ally"` counts the caster, `"enemy"` the other
        side, `"any"` everybody.
        """
        # Resistance is not a modifier -- `deal_damage` reads it off
        # `Defences.resist` and never consults `Mods` -- so asking for it
        # here used to install a key nothing reads and look like a working
        # zone. Said out loud rather than swallowed; `c.resist_in` is the
        # one that works.
        if str(what) == "resist":
            raise ValueError(
                "resistance is not a modifier: use c.resist_in(zone, amount)"
            )
        self._while_inside(
            zone,
            lambda who: self.bonus(
                what, value, on=who, until=When.ENCOUNTER, kind=kind
            ),
            side,
        )

    def resist_in(
        self,
        zone: int,
        amount: int,
        dtype: DamageType | None = None,
        *,
        side: str = "ally",
    ) -> None:
        """"While within the zone you and your allies gain resist N."

        `c.grants_in` cannot carry this: resistance lives on `Defences`
        rather than in `Mods`, so a modifier named "resist" is read by
        nothing. Six rows across warden and shaman print the sentence.
        """
        self._while_inside(
            zone,
            lambda who: self.resist(amount, dtype, on=who, until=When.ENCOUNTER),
            side,
        )

    def _while_inside(
        self, zone: int, give_one: Any, side: str
    ) -> None:
        """Hold something on whoever stands in a zone, and take it back."""
        from .events import ZoneEntered, ZoneExited
        from .query import team as side_of

        held: dict[int, Effect] = {}

        def wanted(who: int) -> bool:
            theirs = side_of(self.world, who)
            mine = side_of(self.world, self.me)
            if side == "any":
                return True
            return theirs is mine if side == "ally" else theirs is not mine

        def give(who: int) -> None:
            if who in held or not wanted(who):
                return
            got = give_one(who)
            if got is not None:
                held[who] = got

        def take(who: int) -> None:
            got = held.pop(who, None)
            if got is not None:
                self.world.effects.end(got, "left the zone")

        def on_enter(ev: ZoneEntered) -> None:
            if ev.zone == zone:
                give(ev.actor)

        def on_exit(ev: ZoneExited) -> None:
            if ev.zone == zone:
                take(ev.actor)

        for who in self.world.zones.occupants(zone):
            give(who)

        standing = dict(self.world.zones.all()).get(zone)
        subs = [
            self.world.bus.on(ZoneEntered, on_enter),
            self.world.bus.on(ZoneExited, on_exit),
        ]
        if standing is not None and standing.effect is not None:
            standing.effect.subs.extend(subs)
            # And take the bonus back off everybody when the zone itself
            # goes: leaving is not the only way it can end.
            def clear_all() -> None:
                for w in list(held):
                    take(w)

            standing.effect.on_end.append(clear_all)

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
        who = on if on is not None else self.me
        mods = self.world.get(who, Mods)
        return mods.total(what) if mods else 0

    # -- senses, one printed line each ---------------------------------------

    def truesight(
        self,
        radius: int = 0,
        *,
        of: int | None = None,
        on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """"Truesight 5", and "the target cannot become invisible to you".

        `c.see_invisible` is the same sense with no range on it, so every
        printed line that names one had to be granted as the unlimited
        version or left out. `of=` is the other printed shape -- one named
        creature, at any distance -- and both are read in `query.unseen_by`,
        so a creature seen this way stops getting combat advantage for being
        unseen, which is what the sentence is bought for.

        A sense of yours, so it defaults to the **caster** like
        `c.see_invisible`. `radius` is ignored when `of` is given.
        """
        who = on if on is not None else self.me
        what = f"truesight:{of}" if of is not None else "truesight"
        return self.bonus(
            what, max(1, radius), on=who, until=until, kind=self.ref,
        )

    def sight_range(
        self, squares_: int, *, on: int | None = None, until: When = When.EONT
    ) -> Effect | None:
        """"The target has no line of sight to any creature more than 3
        squares away from it."

        `c.blinded` is the whole sense at once and this is a cap on it, so
        the half-dozen rows printing a distance had nothing to say. Read by
        `query.unseen_by`: everything past the cap is unseen, and therefore
        has combat advantage against the target.

        Done *to* a creature, so it follows `c.target`. Two caps bucket
        under one kind, so the more generous of them applies rather than the
        pair of them adding into no cap at all.
        """
        who = self._who(on)
        if who is None:
            return None
        return self.bonus(
            "sight_range", max(1, squares_), on=who, until=until, kind="sight_range",
        )

    # -- the damage roll somebody else makes ---------------------------------

    def damage_disadvantage(
        self, *, on: int | None = None, until: When = When.EONT
    ) -> Effect | None:
        """"The target rolls twice when it makes a damage roll and must use
        the lower roll."

        The damage-side twin of `c.reroll_attack(keep="worst")`, which
        reaches an attack roll and nothing else. Held on the creature that
        *rolls*, and read in `c.damage` as the dice come up, so it catches
        the header's line and any rider rolled beside it.
        """
        who = self._who(on)
        if who is None:
            return None
        return self.bonus(
            "damage_twice_lower", 1, on=who, until=until, kind=self.ref,
        )

    def _roll_damage(self, dice: str | int) -> int:
        """The dice of a damage roll, honouring "rolls twice and uses the
        lower roll" -- which is a property of the roller, not of the blow."""
        first = self.world.rng.roll(dice).total
        if self.total("damage_twice_lower") <= 0:
            return first
        return min(first, self.world.rng.roll(dice).total)

    # -- the action economy --------------------------------------------------

    def extra_action(
        self, cost: ActionType = ActionType.MOVE, *, on: int | None = None
    ) -> bool:
        """"You can take an extra move action."

        `c.extra_turn` was the nearest thing and hands out a whole second
        slot in the initiative order, which is a solo's line rather than
        this one. This drops one action into the budget the turn is already
        spending, which `Encounter.can` reads back.

        Yours, so it defaults to the **caster**.
        """
        from .components import Budget

        who = on if on is not None else self.me
        budget = self.world.get(who, Budget) or self.world.add(who, Budget())
        if not hasattr(budget, cost.value):
            return False
        setattr(budget, cost.value, getattr(budget, cost.value) + 1)
        return True

    # -- borrowing somebody else's square ------------------------------------

    def cast_from(
        self, who: int, *, on: int | None = None, until: When = When.ENCOUNTER
    ) -> Effect | None:
        """"Determine line of sight and effect for your ranged and area
        attacks from the target rather than from yourself."

        `c.strike(from_=)` is one swing and nothing held it, so the standing
        version of the line -- and the stat block trait that says the same
        thing about a servant -- had no way to be written. Read in
        `dsl.measured_from`, so the borrowed square decides what may be
        aimed at as well as where the line is traced from.

        Falls back to the borrower's own square whenever the lender has left
        the board or is out of sight, which is the proviso both printed
        lines carry rather than an approximation of them.

        Yours, so it defaults to the **caster** borrowing.
        """
        borrower = on if on is not None else self.me
        self.world.relations.set(Relation.CASTS_FROM, borrower, who)

        def undo() -> None:
            self.world.relations.clear(Relation.CASTS_FROM, borrower, who)

        return self.world.effects.apply(
            borrower, self.me, until, label=f"{self.ref} origin", on_end=[undo]
        )

    # -- a condition held in abeyance ----------------------------------------

    def ignore_condition(
        self,
        *conditions: Condition,
        on: int | None = None,
        until: When = When.EOT,
    ) -> Effect | None:
        """"You take your turn as though you were not stunned, dazed or
        unconscious. At the end of your turn, the effect continues."

        Not `c.cure`: curing ends the effect, and the printed line is that
        the condition is still standing afterwards -- a cured save-ends daze
        would never be saved against, and one that came from an aura would
        come straight back. So the condition is *suppressed*: `Conditions`
        stops reporting it until this expires and the counts are untouched,
        which is also what one fighter row had already written out by hand
        against `conds.counts`.

        Done to a creature's conditions, so it follows `c.target` the way
        `c.cure` does.
        """
        from .components import Conditions as _Conditions

        who = self._who(on)
        if who is None or not conditions:
            return None
        conds = self.world.get(who, _Conditions)
        if conds is None:
            return None
        hushed = [x for x in conditions if x not in conds.suppressed]
        conds.suppressed.update(hushed)

        def undo() -> None:
            conds.suppressed.difference_update(hushed)

        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} ignored", on_end=[undo]
        )

    # -- a number that lived in a closure ------------------------------------

    def quarry_damage(self) -> str:
        """The dice the ranger's quarry rider pays out, as an expression.

        It lives in a closure inside `cf:ranger-quarry` and nothing could
        read it back, so "extra damage equal to your Hunter's Quarry damage"
        -- a line two rows hand to somebody else -- had no number to name.
        Kept as one expression beside that feature's rather than derived
        from the printed per-tier table, so the two cannot disagree.
        """
        return "1d6"


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


def _modes_of(spec: Any) -> dict[str, int]:
    """`Summon.modes` as a mapping, however it was written.

    It began as a tuple of names and became a mapping so "speed 0, fly 6"
    could be said. Rows written against the older shape are still correct
    English -- `modes=("fly",)` means it flies at its own speed -- so both
    are read rather than one being a `ValueError` from inside `dict()`.
    """
    modes = getattr(spec, "modes", None)
    if not modes:
        return {}
    if isinstance(modes, dict):
        return dict(modes)
    return dict.fromkeys(modes, spec.speed)


def _min_of(dice: str | int) -> int:
    """Every die showing 1 -- the floor of the same expression.

    The yardstick `maximise` needs to tell the header's damage line from a
    flat rider the same row rolled. Both carry the row's ref as `detail`,
    so a printed splash of 3 beside a 2d10+3 was being raised to 23.
    """
    if isinstance(dice, int):
        return dice
    if not dice:
        return 0
    n, _, rest = dice.partition("d")
    _faces, sign, tail = rest.partition("+")
    if not sign:
        _faces, sign, tail = rest.partition("-")
    low = int(n or 1)
    if sign == "+":
        low += int(tail)
    elif sign == "-":
        low -= int(tail)
    return low


def expected(dice: str | int, bonus: int = 0) -> float:
    return average(dice) + bonus
