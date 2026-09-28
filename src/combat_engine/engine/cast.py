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

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from .components import Gear, Health, Mod, Mods, Position, Stats
from .durations import Effect, When
from .events import Event, ItemPowerUsed, Note, PowerUsed
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
    Size,
    Team,
    Window,
)

if TYPE_CHECKING:
    from .components import Weapon
    from .dsl import Damage, Power
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
    #: Who handed this use over, and through which row. Set by the three
    #: methods that make somebody swing out of turn -- `c.grant_attack`,
    #: `c.basic` and `c.charge_at` -- and carried onto `PowerUsed`,
    #: `PowerResolved`, all four attack events and both modifier
    #: contexts. -1 and "" mean nobody granted it.
    granted_by: int = -1
    granted_via: str = ""
    #: Which half of a "Melee or Ranged weapon" line is being used. 0 is the
    #: printed first one. A body almost never reads this -- `c.w()` and
    #: `c.strike()` already honour it, which is the point.
    branch: int = 0
    #: How many power points bought this use, for a row whose header
    #: declares `augments=`. Settled by `dsl.use` **before** the targets
    #: were chosen, which is the only moment at which an augment that
    #: widens the target line can be honoured, and already paid for by the
    #: time the body sees it. 0 is the printed base card.
    #:
    #: The body branches on it -- `if c.augment >= 2:` -- rather than
    #: asking `content.powers.augment.augment`, which is the older
    #: body-side arrangement for augments that only change the dice.
    augment: int = 0

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
        is an interrupt that moves the blow rather than stopping it. On an
        `AttackDeclared` that is all there is to do. On a `Hit` -- "the
        triggering attack hits you instead of the ally" -- the roll has
        already happened and is *not* made again: the live result is moved
        with the event, and `c.attack` reads its target back before the body
        that rolled deals its damage. Moving the event alone moved the
        announcement and left the damage on the creature that was spared.
        """
        ev = self.trigger
        if ev is None or not hasattr(ev, "target"):
            return False
        if to is not None:
            ev.target = to
            result = getattr(ev, "result", None)
            if result is not None:
                result.target = to
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

    def _side(self, side: str, excluded: int) -> list[int]:
        """The pool a `side=` names.

        **Always the caster's sides**, never the pool of whatever square
        or creature the caller is measuring from. That is the printed
        word: "each enemy within 2 squares of the target" means an enemy
        of *yours*, and a card meaning the target's own side says "the
        target and its allies". `excluded` is read by `"other"` and by
        nothing else, which is the whole of its job -- it names the one
        creature a "each *other* creature" line leaves out, not a
        creature whose allegiances the other four words follow.

        **`"ally"` leaves the caster out**, which is the printed word: a
        card that means you as well says "you and each ally", and `"team"`
        is that pool -- your side with you in it. It was the other way
        round, and ninety rows printing "an ally" quietly counted the
        caster: a heal that mended the healer, a slide that moved the
        slider, and nothing to see in either.
        """
        return {
            "any": creatures(self.world),
            "enemy": enemies(self.world, self.me),
            "ally": allies(self.world, self.me),
            "team": [*allies(self.world, self.me), self.me],
            "other": [c for c in creatures(self.world) if c != excluded],
        }[side]

    def within(self, radius: int, *, of: int | None = None, side: str = "any") -> list[int]:
        """Creatures within `radius` squares.

        `of` moves the **centre** of the circle and nothing else. `side`
        is still read from the caster, so `c.within(1, of=foe,
        side="ally")` is "you or an ally of yours standing next to that
        enemy" and not "that enemy's own side" -- which is what the cards
        print, and what the rows using it are written against.

        `side` is any, enemy, ally, team or other. `"ally"` is allies and
        **not** the caster; `"team"` is the caster as well; `"other"` is
        everyone but whoever the circle is centred on.
        """
        origin = self.me if of is None else of
        area = spread(squares(self.world, origin), radius)
        pool = self._side(side, origin)
        return [c for c in pool if squares(self.world, c) & area and alive(self.world, c)]

    def in_squares(self, area: Iterable[Square], *, side: str = "any") -> list[int]:
        """Whoever stands in these squares. `side` reads as it does on
        `c.within`: the caster's sides, `"ally"` without the caster,
        `"team"` with."""
        space = frozenset(area)
        pool = self._side(side, self.me)
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

        Off the stat block's own type line, plus anything `c.set_origin`
        has written on. A power that reads "each undead creature in the
        burst" asks this; a character has no type line, and nineteen races
        print a sentence that gives one a word anyway.
        """
        who = self._who(on)
        if who is None:
            return frozenset()
        words = set()
        gone = set()
        for eff in self.world.effects.of(who):
            if eff.label.startswith("origin:"):
                words.add(eff.label.split(":", 1)[1])
            elif eff.label.startswith("unorigin:"):
                gone.add(eff.label.split(":", 1)[1])
        row = self._stat_block(who)
        if row:
            import json

            words |= set(json.loads(row.get("keywords") or "[]"))
            for column in ("kind", "origin"):
                if row.get(column):
                    words.add(row[column])
        # The type line parenthesises its subtypes -- "(undead)" -- and a
        # power asking whether something is undead should not have to know.
        return frozenset(
            w.strip("() ,.").lower()
            for w in words
            if w.strip("() ,.") and w.strip("() ,.").lower() not in gone
        )

    def _stat_block(self, who: int | None) -> dict[str, Any]:
        """The compendium row behind a creature, or `{}` if it has none.

        A character, a companion and a summon are all typeless here -- only
        an `Ident` naming an `m` ref has a block to read.
        """
        from .components import Ident

        if who is None:
            return {}
        ident = self.world.get(who, Ident)
        if ident is None or not ident.ref.startswith("m"):
            return {}
        from combat_engine.content.loader import load

        try:
            return load(ident.ref).row
        except Exception:  # a ref with no row is simply typeless
            return {}

    def is_kind(self, word: str, on: int | None = None) -> bool:
        """Is this creature of that type? `c.is_kind("undead")`."""
        return word.lower() in self.kinds_of(on)

    def is_minion(self, on: int | None = None) -> bool:
        """Is this creature a minion? What "a nonminion enemy" asks.

        Its own column on the stat block, and not a hit point count. The
        two read the same on almost every row -- a minion is printed with
        1 hit point -- and the tree twice wrote `max_hp <= 1` locally
        because nothing else could answer. That test is false for the
        three blocks that print a nonminion with one hit point, and true
        for anything else that happens to have one: a summon spawned off
        `Summon(hp=1)`, a conjuration standing in for a creature, a
        character whose maximum was ground down.

        A creature with no stat block -- a character, a companion, a
        summon -- is never a minion, which is the printed rule.
        """
        return bool(self._stat_block(self._who(on)).get("minion"))

    def set_origin(
        self,
        *words: str,
        on: int | None = None,
        until: When = When.ENCOUNTER,
        instead_of: str = "",
    ) -> Effect | None:
        """"You are considered a fey creature for the purpose of effects
        that relate to creature origin."

        A character's compendium row is its class, so `kinds_of` -- which
        reads the `kind` and `origin` columns of a stat block -- had
        nothing to read and nowhere to be written. Held as a labelled
        effect, the way `c.deals` holds an overridden damage type, so the
        word lasts exactly as long as whatever gave it and one reader
        answers for character and monster alike.

        Several words at once, because two races print more than one and
        the sentence is a single trait.

        `instead_of` is the other printed shape -- "gains the shadow
        origin **instead of** the natural origin", which a beast
        companion's stat block really does carry. An origin is exclusive,
        so the displaced word has to stop answering or the companion is
        both; nothing else can take a word off a stat block.

        Yours, so it defaults to the **caster**.
        """
        who = on if on is not None else self.me
        held: Effect | None = None
        if instead_of:
            held = self.world.effects.apply(
                who, self.me, until, label=f"unorigin:{instead_of.strip().lower()}"
            )
        for word in words:
            held = self.world.effects.apply(
                who, self.me, until, label=f"origin:{word.strip().lower()}"
            )
        return held

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

    def feat(self, ref: str, *, on: int | None = None) -> bool:
        """Has this character taken that feat? `c.feat("f611")`.

        Defaults to the caster, for the same reason `c.build` does: a feat
        is a fact about whoever is acting, never about who it lands on.

        A feat is an ordinary row in `Powers.known` -- that is what makes
        one arm itself at the start of a fight and answer a trigger, with
        no machinery of its own. So having a feat is knowing its row, and
        this is the question 74 heroic feats ask about another feat.
        """
        from .components import Powers

        who = self.me if on is None else on
        known = self.world.get(who, Powers)
        return known is not None and ref in known.all

    def element(self, *, on: int | None = None) -> DamageType | None:
        """The damage type this character's build is bound to, if any.

        "The damage type matching your current elemental affinity" is a
        whole row's payload and nothing held one. `chargen` records it
        beside the build's name as `element:<type>`, so the leg and the
        element stay one choice. Defaults to the caster, as `c.build` does.
        """
        from .components import Build

        who = self.me if on is None else on
        held = self.world.get(who, Build)
        if held is None:
            return None
        by_value = {d.value: d for d in DamageType}
        for choice in held.choices:
            if choice.startswith("element:"):
                return by_value.get(choice.split(":", 1)[1])
        return None

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
        self, *, on: int | None = None, bonus: int = 0, against: str = "",
        bare: bool = False,
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
        if bare:
            # A saving throw against nothing in particular. 4e has a few --
            # "the creature can attempt a saving throw to avoid falling
            # farther" is one -- and this used to find no save-ends effect
            # and return False without rolling, so the row could never
            # succeed and looked like a rule that never applies.
            from .events import SavingThrow

            natural = self.world.rng.roll("1d20").total
            from .durations import keywords_of

            label = against or self.ref
            plus = bonus + self.total(
                "save", who, {"actor": who, "label": label,
                              "conditions": frozenset(), "ongoing": False,
                              "dtype": None,
                              "keywords": keywords_of(label)}
            )
            ev = self.world.bus.emit(
                SavingThrow(
                    actor=who, against=against or self.ref, natural=natural,
                    bonus=plus, saved=natural + plus >= 10,
                )
            )
            return ev.saved
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

    def reroll_save(self, *, bonus: int = 0, keep: str = "new") -> bool:
        """Roll the **triggering** saving throw again. Returns the new result.

        `SavingThrow` is announced before it is acted on and its `saved` is
        read back -- its own docstring says that exists so "reroll it" has
        somewhere to go -- but nothing ever went there, and five feats in
        one batch print exactly that line. Written as a verb rather than
        as five rows reaching into the event, because five hand-written
        versions is five chances to forget that `bonus` is already
        totalled and add the modifier twice.

        `keep` is `new`, `best` or `worst`, matching `c.reroll_attack`.
        The printed lines differ on this and the difference matters: one
        says "use the new result even if it is worse" and another says
        "use whichever you prefer".
        """
        ev = self.trigger
        if ev is None or not hasattr(ev, "saved"):
            return False
        again = self.world.rng.roll("1d20").total
        if keep == "best":
            again = max(again, ev.natural)
        elif keep == "worst":
            again = min(again, ev.natural)
        ev.natural = again
        ev.bonus += bonus
        ev.saved = again + ev.bonus >= 10
        return ev.saved

    def surge_value(self, of: int | None = None) -> int:
        """A quarter of that creature's maximum, which is what a surge heals.

        **Defaults to the caster.** It used to fall to `c.target`, and the
        docstring read as though it did not -- so "you regain hit points
        equal to your healing surge value" written as `c.surge_value()`
        quietly healed off the victim's maximum instead of yours.
        """
        from .query import surge_value

        return surge_value(self.world, self.me if of is None else of)

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

    def resize(
        self,
        size: Size,
        *,
        on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """Take up more room, or less, and shove whoever is standing in it.

        "It becomes Large, occupying 4 squares instead of 1. Any creature in
        the squares it comes to occupy is pushed 1 square" -- the push is
        the printed consequence of growing rather than a separate line, so
        it happens here. The footprint is re-indexed in the grid, because
        everything that asks where a creature is asks that and not the
        `Size`, and the old one comes back when the hold ends.

        Yours, so it defaults to the caster: every printed line of this
        shape is a creature changing its own shape.
        """
        from .movement import place

        who = on if on is not None else self.me
        pos = self.world.get(who, Position)
        if pos is None or pos.size is size:
            return None
        was = pos.size
        from .grid import footprint

        taking = footprint(pos.square, size)
        for other in creatures(self.world):
            if other != who and squares(self.world, other) & taking:
                self.push(1, on=other, anchor=pos.square)
        pos.size = size
        place(self.world, who, pos.square)

        def revert() -> None:
            live = self.world.get(who, Position)
            if live is not None:
                live.size = was
                place(self.world, who, live.square)

        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} size", on_end=[revert]
        )

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

    def end_effect(
        self,
        effect: Effect | None = None,
        *,
        on: int | None = None,
        against: str = "",
        save_ends: bool = False,
        carrying: Condition | None = None,
        why: str = "",
    ) -> Effect | None:
        """Take a live effect off early, before its duration runs out.

        An effect was only ever ended by its clock or by a saving throw, so
        every printed "until you attack", "the effect ends if the target
        takes damage" and "you can end one effect that a save can end" had
        nowhere to go. Two shapes, because the cards print two.

        **Hand it the effect.** Everything that lays one hands one back, so
        a row keeps its own hold in a local and ends it from a `c.watch`.
        That is the commonest half by a long way.

        **Or name a category and let somebody pick.** "One effect that a
        save can end" is not an effect, it is a choice among the ones
        standing, so `save_ends=True` collects them and `c.choose` asks --
        a headless run takes the oldest, which is the one that has had the
        most chances to lapse on its own. `against` narrows by label
        fragment the way `c.save` does, and `carrying` by a condition the
        effect imposes -- "you can make a saving throw to end that daze"
        names the daze and not the row that laid it.

        Returns what went, or None if there was nothing to end. **Ending is
        not saving**: none of the printed lines here roll, and a row that
        reaches for `c.save` instead has written a rule that can fail.

        Follows `c.target` and falls back to the caster, as `c.save` does:
        "the target can end the effect" is the usual printing. A row that
        means the caster on a board where somebody else is targeted says
        `on=c.me`.
        """
        if effect is not None:
            if effect.ended:
                return None
            self.world.effects.end(effect, why or f"{self.ref} ended it")
            return effect
        who = self._who(on) or self.me
        if who is None:
            return None
        pool = [
            eff
            for eff in sorted(self.world.effects.of(who), key=lambda e: e.id)
            if not eff.ended
            and (not save_ends or eff.when is When.SAVE_ENDS)
            and (not against or against in eff.label)
            and (carrying is None or carrying in eff.conditions)
        ]
        picked = self.choose(pool, f"{self.ref}: which effect to end")
        if picked is None:
            return None
        self.world.effects.end(picked, why or f"{self.ref} ended it")
        return picked

    def endable(
        self,
        effect: Effect | None,
        cost: ActionType = ActionType.MINOR,
        *,
        then: Callable[[], None] | None = None,
    ) -> Effect | None:
        """Let whoever holds this effect end it deliberately, for an action.

        "You can end this effect as a minor action" and "it can use a
        standard action to end this effect" are one printed line seen from
        the two sides, and both are `Effect.drop_cost`: `actions.legal`
        offers a `drop` to the effect's **owner** when it carries one.

        So this is aimed by whose effect it is and takes no `on=` -- an
        immobilisation the target shakes off is endable by the target
        because the hold sits on the target, and a self-buff you can
        dismiss is yours for the same reason.

        `then` is what ending it deliberately *buys*, for the printed
        lines that are a trade rather than a dismissal: "end the effect as
        a free action to teleport", "end the effect by taking 5 damage".
        It runs for the deliberate drop and for nothing else -- not for
        the clock and not for a saving throw -- because a payout owed for
        choosing is not owed for waiting.
        """
        if effect is not None:
            effect.drop_cost = cost
            effect.drop_then = then
        return effect

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

        **Enhancement is a different question and used to share the answer.**
        One test gated both, so a magic implement added nothing at all --
        and implements are the largest bucket of magic items there is. A
        wizard with an enchanted staff attacked exactly as hard as a wizard
        with a stick. Proficiency asks "is this a weapon power"; enhancement
        asks "what is in hand for this power", which is the implement for an
        implement row and the weapon for a weapon row.
        """
        bonus = self.world.scaling.pc(self.stats.level) + self.stats.mod(a)
        p = self._declared()
        weapon_power = p is None or Keyword.WEAPON in p.keywords
        gear = self.world.get(self.me, Gear)
        if gear is not None:
            if weapon_power:
                bonus += getattr(self._wielded(), "proficiency", 0)
            bonus += self._enhancement_of(p)
        return bonus

    def _wielded(self) -> Weapon | None:
        """The weapon this power swings or fires.

        The same question `c.w()` asks, asked the same way: the branch
        where the row has one, the keyword otherwise.
        """
        gear = self.world.get(self.me, Gear)
        if gear is None:
            return None
        p = self._declared()
        if p is not None and p.reach.alt is not None:
            ranged = self.ranged
        else:
            ranged = p is not None and Keyword.RANGED in p.keywords
        return gear.ranged if ranged and gear.ranged else gear.main

    def _enhancement_of(self, p: Power | None) -> int:
        """The enhancement bonus of whatever this power is cast through.

        An implement row reads the implement, a weapon row reads the
        weapon, and a row that is neither -- a class feature's attack, the
        probe `Attack.bonus_for` builds -- reads the weapon too, because
        that is what an unqualified attack swings.
        """
        gear = self.world.get(self.me, Gear)
        if gear is None:
            return 0
        if p is not None and Keyword.IMPLEMENT in p.keywords:
            arm = gear.implement
        else:
            arm = self._wielded()
        return arm.enhancement if arm is not None else 0

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

        `"shield"`, `"two-weapon"`, a weapon group like `"light blade"`, a
        category like `"simple"`, or a property like `"two-handed"`.
        """
        gear = self.world.get(self.me, Gear)
        if gear is None:
            return False
        if prop == "shield":
            return gear.shield
        if prop in ("two-weapon", "two melee weapons"):
            return gear.two_weapon
        weapon = gear.main
        return weapon is not None and (
            prop in weapon.properties
            or weapon.group == prop
            or weapon.category == prop
        )

    # -- attacking -----------------------------------------------------------

    def strike(
        self,
        *,
        on: int | None = None,
        advantage: bool | None = None,
        plus: int = 0,
        from_: int | None = None,
        ignore_cover: bool = False,
        keep: str = "",
        hand: str = "main",
    ) -> AttackResult:
        """Roll the attack the header declared.

        The overwhelmingly common case: the printed `Attack:` line is a plain
        ability against a defence, it went in the header where a policy can
        read it, and the body just says "roll it".

        `keep` is the printed "make the attack roll twice and use either
        result" -- "best", or "worst" for the rows that say so. It has to be
        here rather than arranged by the body, because by the time `c.strike`
        returns the first roll has already been announced and answered. Both
        faces stay on `c.result.rolls`, which is what "if both of your attack
        rolls would hit" reads.
        """
        from .dsl import get

        p = get(self.ref)
        line = p.attack_of(self.branch) if p else None
        if line is None:
            raise ValueError(f"{self.ref} declared no attack line; call c.attack(...)")
        if line.by and from_ is None:
            # "Beast's attack bonus" is the beast's swing: `bonus_for` already
            # rolls its numbers, and the blow has to come from where it is
            # standing too, or reach, cover and flanking are all the owner's.
            from .dsl import roller

            elsewhere = roller(self.world, self.me, line.by)
            from_ = elsewhere if elsewhere != self.me else None
        return self.attack(
            line.bonus_for(self.world, self.me, self.ref, self.branch) + plus,
            line.vs,
            on=on,
            advantage=advantage,
            from_=from_,
            ignore_cover=ignore_cover,
            keep=keep,
            hand=hand,
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
        reentrant: bool = False,
    ) -> bool:
        """Let somebody else make an attack, now, out of turn.

        The warlord's entire reason to exist, and a thing `Cast` could not
        say at all: `c.strike()` always rolls for the caster. Without this
        the class's signature row has no content whatsoever.

        `ref` defaults to that creature's own basic attack, so a monster
        whose basic has been replaced attacks with the right thing.

        `reentrant` is "the target repeats the attack": the swing being
        granted is the very row and the very use this one is answering, so
        the in-flight guard and the usage limit both have to stand aside for
        it. Nothing else should pass it -- it is what stops two rows handing
        a swing back and forth forever.
        """
        from .components import Powers
        from .dsl import get, use

        target = self._who(on)
        if target is None or not alive(self.world, who):
            return False
        known = self.world.get(who, Powers)
        from .basic import MELEE

        # **A named row that does not exist is loud.** The fallback is for
        # `ref=""` -- "grant a basic attack" -- and an unknown *named* ref
        # used to fall through it silently and resolve nothing, so a row
        # written correctly against a power nobody has imported yet looked
        # like a row that does nothing. Two item blocks were reported
        # SILENT for exactly that, and the expression in both was right.
        if ref and get(ref) is None:
            raise ValueError(
                f"{self.ref}: c.grant_attack(ref={ref!r}) names a row that is "
                f"not declared. Leave `ref` out for a basic attack, or mark "
                f"the row `todo=(\"{ref}\",)` until that row lands."
            )
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
        # **Lend the row if the creature does not know it.** `usable`
        # refuses anything outside `Powers.known` -- rightly, for a row a
        # character is choosing -- but the commonest magic item shape
        # there is reads "use this as if it were the wizard's X", and the
        # carrier is a fighter. Without this the swing resolved nothing
        # and said nothing: two item blocks audited SILENT with the right
        # expression in them.
        #
        # Lent rather than given: taken back in the `finally` below, so a
        # character does not quietly keep a bard's at-will after using a
        # rod once.
        lent = False
        if known is not None and chosen not in known.all:
            known.known.append(chosen)
            lent = True
        try:
            # The trigger goes through. A row reading "when an ally drops,
            # the ally makes a basic attack" hands the swing to a creature
            # that is no longer alive, and `usable`'s act gate refuses it
            # without the event that explains why it should not.
            return use(
                self.world, who, chosen, targets=[target], spend=False,
                trigger=trigger if trigger is not None else self.trigger,
                granted_by=self.me, granted_via=self.ref,
                reentrant=reentrant,
            )
        finally:
            if lent and known is not None and chosen in known.known:
                known.known.remove(chosen)
            for effect in granted:
                if effect is not None:
                    self.world.effects.end(effect, "the granted attack is over")

    def add_target(self, who: int) -> bool:
        """"The ally also becomes a target of the power."

        Adds a creature to the use this one is nested **inside**. An
        immediate interrupt runs while the power it answers is still walking
        its target list, so an appended creature is one that power's body is
        then called for -- attack roll, damage and all. Refused where nothing
        is running underneath, because there is then no power to be a target
        of, and refused for a creature already in the list.
        """
        from .dsl import running_below

        outer = running_below(self)
        if outer is None or outer is self or who in outer.targets:
            return False
        outer.targets.append(who)
        return True

    def ignores_long_range(
        self, *, on: int | None = None, until: When = When.EONT
    ) -> Effect | None:
        """"You take no penalty to attack rolls for attacking at long range."

        The penalty is 2 and `resolve.attack` charges 2 less whatever
        `"long_range"` comes to, so waiving it is an ordinary modifier -- and
        a card that waives it only sometimes gates it the ordinary way.
        """
        return self.bonus(
            "long_range", 2, until=until, on=on if on is not None else self.me,
            stacks=False,
        )

    def as_ranged(
        self, squares_: int = 10, *, on: int | None = None, until: When = When.EONT
    ) -> Effect | None:
        """"The next melee attack you make becomes a ranged attack with a
        range of N."

        Rendered as the distance and nothing else. `_is_ranged` reads the
        row's printed range line, so the swing still takes no cover from
        bodies and still leaves no opening -- the reach is what the sentence
        is for and the rest of it is not sayable per creature. Spent on the
        next attack roll rather than on the next melee one, because the gate
        is also asked where no range line is in the question.
        """
        return self.bonus(
            "reach", max(0, squares_ - 1), until=until,
            on=on if on is not None else self.me,
            when=lambda ctx: ctx.get("kind", "melee") == "melee",
            once=True, stacks=False,
        )

    def shroud(self, *, on: int | None = None, cap: int = 4) -> int:
        """Lay an assassin's shroud, and say how many that creature now has.

        Shrouds follow one victim at a time: naming a new one drops whatever
        the last was carrying, which is the printed rule and also the reason
        this is a count rather than a stack of effects.
        """
        from .components import Shrouds

        who = self._who(on)
        if who is None:
            return 0
        held = self.world.get(self.me, Shrouds)
        if held is None:
            held = self.world.add(self.me, Shrouds())
        if held.on != who:
            held.on, held.count = who, 0
        held.count = min(cap, held.count + 1)
        return held.count

    def shrouds(self, on: int | None = None, *, of: int | None = None) -> int:
        """How many of my shrouds that creature is carrying. 0 for anybody
        else, since only one creature carries them at a time."""
        from .components import Shrouds

        who = self._who(on)
        held = self.world.get(self.me if of is None else of, Shrouds)
        if held is None or who is None or held.on != who:
            return 0
        return held.count

    def spend_shrouds(self) -> int:
        """Invoke them: the count goes, and what it was is returned."""
        from .components import Shrouds

        held = self.world.get(self.me, Shrouds)
        if held is None:
            return 0
        was, held.count = held.count, 0
        return was

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
        self,
        *,
        on: int | None = None,
        who: int | None = None,
        ranged: bool = False,
        window: str = "",
    ) -> bool:
        """Make a basic attack -- whichever row that creature's actually is.

        A great many powers grant one, and spelling it out longhand gets it
        wrong for any creature whose basic attack has been replaced: a
        monster points `Powers.basic` at one of its own abilities, and a
        hand-written copy of "roll and deal weapon damage" would quietly
        ignore that.

        `window` names which grant this is, so that a stand-in filed by
        `c.as_basic` for that window is offered beside the ordinary
        swing. A grant that names no window -- most of them -- still
        picks up the stand-ins written with no window of their own.
        """
        from .basic import MELEE, RANGED
        from .components import Powers
        from .dsl import basic_options, use

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
        offered = basic_options(
            self.world, attacker, "ranged" if ranged else window, ref
        )
        if len(offered) > 1:
            ref = self.choose(offered, "which attack to make") or ref
        # Marked as granted even when the swinger is the caster: the
        # defender's punishment is a self-grant, and eight feats are
        # about exactly that swing and no other.
        return use(
            self.world, attacker, ref, targets=[target], spend=False,
            granted_by=self.me, granted_via=self.ref,
        )

    def attack(
        self,
        bonus: int,
        vs: Defense,
        *,
        on: int | None = None,
        advantage: bool | None = None,
        from_: int | None = None,
        ignore_cover: bool = False,
        keep: str = "",
        hand: str = "main",
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
            granted_by=self.granted_by, granted_via=self.granted_via,
            keep=keep, hand=hand,
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
        dtypes: Sequence[DamageType] = (),
        on: int | None = None,
        detail: str = "",
    ) -> int:
        """Roll and apply damage. A critical hit maxes the dice, as printed.

        `dtypes` is a blow that is **several types at once** -- "1[W] cold
        and necrotic damage" is one roll of two types, not two rolls of
        one, and the printed rule is that the target shrugs off only as
        much of it as it resists *every* type in it. Pass it instead of
        `dtype`, never beside it: two `c.damage` calls deal the damage
        twice, and a single type meets a resistance the card says does not
        apply.

        A **rider** of a type the power itself is not -- "your attacks
        deal 2 extra fire damage" -- is `c.bonus("damage", ..., dtype=)`
        and not this.
        """
        who = self._who(on)
        if who is None:
            return 0
        if self.crit:
            amount = _max_of(dice) + bonus
        else:
            amount = self._roll_damage(dice) + bonus if dice else bonus
        amount += self._enhancement()
        # A card naming two types has said what it deals, so the weapon's
        # own type gets no vote -- the rule `_typed` already applies to one
        # named type.
        dtype = dtype if dtypes else self._typed(dtype)
        dealt = deal_damage(
            self.world, self.me, who, amount, dtype, detail or self.ref,
            dtypes=dtypes,
            opportunity=self.opportunity, charge=self.charge,
            granted_by=self.granted_by, granted_via=self.granted_via, crit=self.crit,
        )
        if dealt:
            self._rattle(who)
        return dealt

    def half_damage(
        self,
        dice: str | int = 0,
        bonus: int = 0,
        *,
        dtype: DamageType = DamageType.UNTYPED,
        dtypes: Sequence[DamageType] = (),
        on: int | None = None,
    ) -> int:
        """"Miss: half damage" -- rolled, then halved, as the rule reads.

        `dtypes` is one blow of several types, as on `c.damage`.
        """
        who = self._who(on)
        if who is None:
            return 0
        amount = (self._roll_damage(dice) + bonus) // 2 if dice else bonus // 2
        dtype = dtype if dtypes else self._typed(dtype)
        dealt = deal_damage(
            self.world, self.me, who, amount, dtype, f"{self.ref} (half)",
            dtypes=dtypes,
            opportunity=self.opportunity, charge=self.charge,
            granted_by=self.granted_by, granted_via=self.granted_via, miss=True,
        )
        # "Miss: half damage" still deals damage, and the rattling keyword
        # asks nothing about hitting.
        if dealt:
            self._rattle(who)
        return dealt

    def flat(self, amount: int, *, dtype: DamageType = DamageType.UNTYPED,
             dtypes: Sequence[DamageType] = (),
             on: int | None = None) -> int:
        """Damage that is not rolled. `dtypes` is one blow of several types.

        "The attacker takes 10 lightning and thunder damage" is ten points
        that are both, not ten of each -- see `c.damage`.
        """
        who = self._who(on)
        if who is None:
            return 0
        return deal_damage(
            self.world, self.me, who, amount, dtype, self.ref,
            dtypes=dtypes,
            opportunity=self.opportunity, charge=self.charge,
            granted_by=self.granted_by, granted_via=self.granted_via,
        )

    def heal(self, amount: int, *, on: int | None = None) -> int:
        who = self._who(on)
        return 0 if who is None else heal(self.world, self.me, who, amount)

    def surge(self, *, on: int | None = None, bonus: int = 0) -> int:
        """Spend a healing surge: a quarter of maximum hit points."""
        from .query import surge_value
        from .resolve import spend_surge

        who = self._who(on)
        health = self.world.get(who, Health) if who else None
        if health is None or not spend_surge(self.world, who):
            return 0
        return heal(self.world, self.me, who, surge_value(self.world, who) + bonus)

    def temp_hp(self, amount: int, *, on: int | None = None) -> None:
        who = self._who(on)
        if who is not None:
            temp_hp(self.world, self.me, who, amount)

    def ongoing(
        self,
        amount: int,
        dtype: DamageType = DamageType.UNTYPED,
        *,
        dtypes: Sequence[DamageType] = (),
        on: int | None = None,
        until: When = When.SAVE_ENDS,
    ) -> Effect | None:
        """Ongoing damage. **Of one type, only the highest applies.**

        `dtypes` is a burn of several types at once -- "ongoing 5 fire and
        radiant damage" is five points a turn that are both, not five of
        each. Two `c.ongoing` calls would tick for ten and take two saves
        to shake off, which is the shape this replaces.

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
            who, self.me, until, label=f"ongoing {amount}",
            ongoing=(amount, dtypes[0] if dtypes else dtype),
            ongoing_types=tuple(dtypes),
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
        menu that is normally a constant. `what` is `shift`, `stand`,
        `escape` or `second_wind`; anything else is carried, costs nothing
        and does nothing, so add the reader in `actions` at the same time
        as the word.

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

    def recast(
        self,
        ref: str,
        *,
        action: ActionType = ActionType.MINOR,
        per_turn: int = 1,
        until: When = When.ENCOUNTER,
        on: int | None = None,
    ) -> Effect | None:
        """"You can use a power you already know for a cheaper action."

        Not `c.grant_row`: that lends a row to a creature that does not have
        it and says nothing about what using it costs, and here the cost is
        the entire printed Effect. It rides the same "<what> as <cost>"
        carrier `c.shift_as` uses, with the ref as the what, and
        `actions._recasts` is the reader -- the row keeps its own entry in
        the menu and gains a second one at this price.

        The value is how many times a turn, because that is the unit every
        printed line of this shape uses. Defaults to the caster.
        """
        who = on if on is not None else self.me
        return self.bonus(
            f"{ref} as {action.value}", max(1, per_turn), on=who,
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

    def expend_row(self, ref: str, *, on: int | None = None) -> bool:
        """"You can expend your p1449 racial power to mark each enemy."

        The exact inverse of `c.restore_use`, and the price half of three
        dozen printed lines: a use is spent and **the row never runs**.
        Nothing that goes through `dsl.use` can say that -- using a power
        is what those do -- and `c.forbid` says a different thing, since a
        forbidden row is one the creature still owns and cannot reach,
        which comes back when the effect ends.

        Defaults to the **caster**, like `c.restore_use` and `c.expended`
        beside it. Returns False when there is no use to spend -- the row
        is not known, is already spent, or is an at-will with nothing to
        count down -- and that False **is** the Requirement these cards
        print, so a row buying something with it must check it:

            if not c.expend_row("p1449"):
                return

        A row this creature does not own is refused rather than lent: the
        printed line always names the character's own power, and lending
        one in order to spend it would charge nothing.
        """
        from .components import Powers as _Powers
        from .dsl import get as _get
        from .types import Usage as _Usage

        who = on if on is not None else self.me
        powers = self.world.get(who, _Powers)
        if powers is None or ref not in powers.all:
            return False
        p = _get(ref)
        if p is not None and p.usage is _Usage.AT_WILL:
            return False
        if powers.times(ref) >= (p.uses if p is not None else 1):
            return False
        powers.note_use(ref, self.world.round)
        self.world.bus.emit(Note(text=f"{who} expends {ref}"))
        return True

    def use_power(
        self,
        ref: str,
        *,
        on: int | None = None,
        who: int | None = None,
        spend: bool = True,
        again: bool = False,
    ) -> bool:
        """"You can use your p1449 racial power as a free action."

        One row using another. `dsl.use` is the engine's only entry point
        for it and `Cast` could reach it three ways, all narrower than the
        printed line: `c.grant_attack` hands *somebody else* a swing at
        one creature, `c.charge_at` runs and swings, `c.give` puts a
        one-shot in a pocket for later. Thirty rows want none of those --
        "as the wizard's p1227 power", "use p377 as an immediate
        reaction", "use a melee at-will attack power on the target".

        **It never charges an action.** The card that says this has
        already declared what it costs, in its own header.

        `on` aims it at one creature; left out, the borrowed row picks its
        own targets exactly as it would on an ordinary turn, which is what
        a personal, close or area power wants. `who` uses it on somebody
        else's behalf.

        The row is **lent** if the creature does not have it and taken
        back afterwards, so "as the wizard's X" works in a fighter's
        hands -- and a lent row is never spent, because the item's own
        use is the cost and a borrowed power is not the character's to
        expend. `spend` therefore only decides what happens to a row the
        creature really owns, and it defaults to spending, because "use
        *your* p1449 racial power" spends p1449.

        `again` waives the usage limit, for the one printed shape that
        says so outright -- "even if you have already used it during this
        encounter".

        `c.trigger` goes through, so the borrowed row reads the event this
        one is answering as its own `PowerUsed.trigger` -- which is how
        "use it against the creature that triggered this" is written.

        **The return is "was it used", not "did it hit".** `dsl.use` says
        no more than that, and "if you hit, you also..." is half of most
        of these cards -- so the borrowed row's last attack is read off
        its `PowerResolved` and left in `c.result`, which makes `c.landed`
        the answer to the printed "if you hit" in the line below the call.
        A rider that can be laid *before* the attack should still be laid
        before it: `c.bonus(..., once=True)` is spent by the damage roll
        only if there is one, so it needs no hit to test.
        """
        from .components import Powers as _Powers
        from .dsl import get as _get
        from .dsl import use as _use
        from .events import PowerResolved as _PowerResolved

        # **A named row that does not exist is loud**, for the reason
        # `c.grant_attack` says it: a row written correctly against a
        # power nobody has imported yet is otherwise a silent no-op.
        if _get(ref) is None:
            raise ValueError(
                f"{self.ref}: c.use_power({ref!r}) names a row that is not "
                f"declared. Mark the row `todo=(\"{ref}\",)` until it lands."
            )
        actor = self.me if who is None else who
        known = self.world.get(actor, _Powers)
        lent = False
        if known is not None and ref not in known.all:
            known.known.append(ref)
            lent = True

        def _keep(ev: Any) -> None:
            if ev.actor == actor and ev.power == ref and ev.rolls:
                self.result = ev.rolls[-1]

        sub = self.world.bus.on(_PowerResolved, _keep)
        try:
            return _use(
                self.world, actor, ref,
                targets=None if on is None else [on],
                spend=spend and not lent,
                trigger=self.trigger,
                reentrant=again,
            )
        finally:
            self.world.bus.off(sub)
            if lent and known is not None and ref in known.known:
                known.known.remove(ref)

    def expended(self, *, group: str = "", on: int | None = None) -> list[str]:
        """The rows this creature has used up, for one that hands a use back.

        `c.restore_use` needs a ref and "an expended channel divinity power"
        prints none, so the choice has to be made on the board. `group`
        narrows it to the printed allowance the row belongs to, which is the
        same `group=` the header declares.

        Defaults to the **caster**, like `c.restore_use` beside it.
        """
        from .components import Powers as _Powers
        from .dsl import get as _get

        who = on if on is not None else self.me
        powers = self.world.get(who, _Powers)
        if powers is None:
            return []
        return [
            ref
            for ref in powers.all
            if powers.times(ref) > 0
            and (not group or ((p := _get(ref)) is not None and p.group == group))
        ]

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

    def swap_initiative(self, other: int) -> bool:
        """"You and one ally switch places in the initiative order."

        The slot being played changes hands with the count, so a swap made
        on your own turn hands the rest of that slot to the other creature
        -- see `Encounter.swap_initiative`, which is where that lives.
        """
        encounter = getattr(self.world, "encounter", None)
        if encounter is None or other == self.me:
            return False
        return encounter.swap_initiative(self.me, other)

    def end_turn(self) -> bool:
        """"Your turn ends when you use this power."

        Only the creature acting can end its own turn, and only once: the
        driver's `advance` finds `world.turn` already cleared and does not
        announce a second `TurnEnd`. What is left after this is free actions
        and nothing else, because `Encounter.can_spend` refuses every other
        cost once the turn is nobody's.
        """
        encounter = getattr(self.world, "encounter", None)
        if encounter is None or self.world.turn != self.me:
            return False
        encounter.end_turn()
        return True

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

    def reroll_attack(self, *, keep: str = "new", bonus: int = 0) -> bool:
        """Make the triggering attack roll again. `keep` is new, best or worst.

        Reads the attack off `c.trigger`, so it only means anything inside a
        row the dispatcher offered. Rerolling is not cancelling: the attack
        still happens, with a different number.

        `bonus` is for "reroll it with a bonus equal to your Strength
        modifier" -- the reroll and the bonus are one printed clause, and a
        `c.bonus` laid afterwards is read by the next attack rather than by
        this one.
        """
        ev = self.trigger
        result = getattr(ev, "result", None) if ev is not None else None
        if result is None:
            return False
        fresh = self.world.rng.d20().total
        old = result.natural
        result.rolls.append(fresh)
        face = {"new": fresh, "best": max(old, fresh), "worst": min(old, fresh)}[keep]
        shift_ = face - old
        result.natural = face
        result.total += shift_ + bonus
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
        when: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Effect | None:
        """Shrugs off `amount` of every hit, or of one damage type.

        The mirror of `c.vulnerable`, which existed on its own -- so a row
        printing "gains resist 10 to the triggering damage type" had to
        write `c.vulnerable(-10, ...)`, which comes to the same arithmetic
        and puts "vulnerable -10" on the card.

        `when` is handed the damage context -- `source`, `power`, `dtype`,
        `opportunity`, `charge` -- for the narrow printed shape, "but only
        when the damage is from ranged or area attacks". `Defences.resist`
        is a flat number per type with nowhere to hang a condition, so a
        gated line written there would shrug off everything and be strictly
        stronger than print; the gated form is a modifier instead, and
        `resolve.damage` reads it after the flat one.
        """
        from .components import Defences

        who = on if on is not None else self.me
        if when is not None:
            what = "resist" if dtype is None else f"resist {dtype.value}"
            return self.bonus(
                what, amount, on=who, until=until,
                kind=f"{self.ref} resist", when=when,
            )
        kinds = [dtype] if dtype is not None else list(DamageType)
        defences = self.world.get(who, Defences) or self.world.add(who, Defences())
        # **Resistances of one type do not stack -- the highest applies**, the
        # same printed rule `Effects.apply` enforces for ongoing damage. This
        # added, so resist 5 laid on a creature already resisting 10 came to
        # 15. A weaker one is refused outright and changes nothing, which is
        # also what makes `undo` right: it puts back what this call moved and
        # nothing else, however the holds overlap.
        #
        # A **negative** amount is the other printed sentence -- "the target
        # loses resist 10 to fire" -- and stays arithmetic: there is no
        # highest to take, and four rows hand over a computed delta.
        before: dict[DamageType, int] = {}
        for kind in kinds:
            standing = defences.resist.get(kind, 0)
            if amount < 0 or amount > standing:
                before[kind] = standing
                defences.resist[kind] = standing + amount if amount < 0 else amount

        def undo() -> None:
            for kind, standing in before.items():
                if standing > 0:
                    defences.resist[kind] = standing
                else:
                    defences.resist.pop(kind, None)

        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} resist", on_end=[undo]
        )

    def ignore_resistance(
        self,
        amount: int | None = None,
        dtype: DamageType | None = None,
        *,
        until: When = When.ENCOUNTER,
        on: int | None = None,
        when: Callable[[dict[str, Any]], bool] | None = None,
        immunity: bool | int = False,
        insubstantial: bool = False,
    ) -> Effect | None:
        """"Your fire powers ignore the target's fire resistance."

        **Yours, so it defaults to the caster** -- it is a property of the
        attacker, not of the creature being hit, and that is the one thing
        about it that is easy to get backwards. `c.resist(-n, ..., on=foe)`
        is the *other* sentence, "the target loses resist 10 to fire", and
        it strips the resistance for everybody rather than for you.

        `amount` is the cap the card prints -- "ignore the first 5 points"
        -- and `None` is the blanket form, "ignore all resistances".
        `dtype` narrows it to one type; `None` is any.

        `when` is handed the damage context -- `target`, `power`, `dtype`,
        `opportunity`, `charge`, `advantage`, `ranged` -- for the printed
        narrowings: only against a bloodied enemy, only with a particular
        power, only when you have combat advantage. Read the keys before
        gating on one; a gate on a key the context does not carry is
        silently false and looks exactly like a rule that never applies.

        `immunity` is the second half of the sentence on the cards that
        have it. `True` is "ignore poison immunity"; a number is the
        commoner "treat a creature immune to poison as if it had resist
        poison 20", which the ignored points then come off in turn.

        `insubstantial=True` is "ignores all resistances, **including
        insubstantial**", printed on a handful and nowhere expressible --
        it is a halving rather than a resistance and lives in a different
        line of `deal_damage`.
        """
        from .resolve import IGNORE_ALL

        who = on if on is not None else self.me
        suffix = "" if dtype is None else f" {dtype.value}"
        points = IGNORE_ALL if amount is None else amount
        mods = [Mod(
            what=f"ignore resist{suffix}", value=points,
            kind="untyped", when=when, label=self.ref,
        )]
        if immunity is not False:
            mods.append(Mod(
                what=f"ignore immunity{suffix}", value=1,
                kind="untyped", when=when, label=self.ref,
            ))
            if immunity is not True and immunity:
                mods.append(Mod(
                    what=f"immune as resist{suffix}", value=int(immunity),
                    kind=f"{self.ref} immune as", when=when, label=self.ref,
                ))
        if insubstantial:
            mods.append(Mod(
                what="ignore insubstantial", value=1,
                kind="untyped", when=when, label=self.ref,
            ))
        shown = "all" if amount is None else str(points)
        return self.world.effects.apply(
            who, self.me, until,
            label=f"{self.ref} ignores {shown} resist{suffix}",
            mods=[(who, m) for m in mods],
        )

    def resistances(self, *, on: int | None = None) -> dict[DamageType, int]:
        """What the creature shrugs off, by type, right now.

        Theirs, so it follows `c.target`. The reader `c.resist` needed and
        did not have: "the target **loses** that resistance" and "if it
        already has fire resistance, increase it" are both a number this
        row has to know before it can hand `c.resist` a delta, and four
        rows were computing one they could not see.

        A copy, and types the creature does not resist are left out.
        """
        from .components import Defences

        who = self._who(on)
        held = self.world.get(who, Defences) if who is not None else None
        return {t: n for t, n in (held.resist if held else {}).items() if n}

    def grant_row(
        self,
        ref: str,
        *,
        on: int | None = None,
        until: When = When.ENCOUNTER,
        uses: int = 0,
    ) -> Effect | None:
        """Let a creature use a row it does not know, for a while.

        The opposite number of `c.forbid`, and asked for twice before it
        existed -- "gains one use of an attack it has seen", "can make two
        attacks as a standard action". A row could be taken away and never
        given, so anything printing this had to be left out whole rather
        than half-written.

        **A trait handed over during arming is armed.** It was not:
        `turns.arm_traits_of` walked one list built before the first row
        ran, so a feat whose whole benefit is "you gain class feature X"
        appended a ref nothing ever turned on and sat inert while
        looking finished. That loop re-reads between passes now.

        **Not the tool for a build's own rows.** `chargen.loadout` deals a
        character every level-0 row of its class, so this returns `None`
        for one of those -- the creature already knows it. Three features
        have been written around that with a `c.forbid` on the other legs,
        and it reads like a bug in `loadout`.

        It is not. The arrangement is deal-everything and gate at the
        point of use: `requires=on_leg("...")` in the header refuses the
        row on a build that did not take it, which is what "choose one of
        the following" means and what eight rows already do. Withholding
        the rows instead would need a feature to hand each one back, and
        exactly one ref in the whole tree is granted by name -- the rest
        of the exclusivity is written with variables, so the rows would
        simply vanish.

        **`uses` is the cadence the granting card prints, not the granted
        row's own.** Nineteen multiclass feats read "choose a 1st-level
        at-will attack power from <another class>; you can use that power
        once per encounter", and handing the row over bare gives an
        at-will -- an unlimited extra attack, every turn, for one feat.
        `dsl.usable` reads the *row's* `usage` and there is nowhere on a
        creature to say "this one, but only twice", so the limit had no
        home. It has one here: the grant counts the holder's own uses off
        `PowerUsed` and forbids the row when they run out. Left at 0 the
        granted row keeps its printed usage, which is right whenever the
        two agree -- an encounter power granted "once per encounter" needs
        nothing, and inside one fight so does a daily.
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
        if effect is None:
            return None
        known.known.append(ref)
        if uses > 0:
            spent = [0]

            def count(ev: Any) -> None:
                if getattr(ev, "actor", None) != who or getattr(ev, "power", "") != ref:
                    return
                spent[0] += 1
                if spent[0] >= uses:
                    self.forbid(ref, on=who, until=until)

            self.watch(PowerUsed, count, until=until, on=who)
        return effect

    def borrow_row(
        self,
        cls: str = "",
        *,
        level: int = 1,
        usage: Any = None,
        keyword: Keyword | None = None,
        among: Sequence[str] = (),
        attacks: bool = True,
        uses: int = 1,
        until: When = When.ENCOUNTER,
    ) -> str:
        """"Choose a 1st-level at-will attack power from <another class>."

        The multiclass sentence, and it was one symbol covering two
        different holes. The first is gone: `c.grant_row` hands a row
        over and 124 class features were declared, so "you gain the
        bard's <feature>" is now an ordinary one-liner. What is left is
        this -- the card names a *set* and asks the character to take one
        of it, and nothing could either enumerate the set or record the
        pick.

        The set is read off the registry the way `chargen.loadout` reads
        it, by class, level and usage, because that is the only place the
        membership is written down. Where the card names the candidates
        outright, pass them as `among` instead.

        **Which one is a build choice with nowhere to live**, so it goes
        to `world.decide` like any other -- the same arrangement `f1224`
        makes for "choose a damage type", and inside one encounter a
        choice made at arming and a choice made at character creation are
        the same choice. A campaign that carried between fights would
        want `chargen` to record it.

        `uses` is passed straight to `c.grant_row`, so the printed "once
        per encounter" survives the row being an at-will. Returns the ref
        taken, or `""` when the set is empty -- an empty set is a gap and
        the caller should still be carrying a marker for it.
        """
        from .components import Powers
        from .dsl import REGISTRY
        from .types import Usage

        want = usage if usage is not None else Usage.AT_WILL
        known = self.world.get(self.me, Powers)
        held = set(known.all) if known is not None else set()
        pool = [
            ref
            for ref in (among or REGISTRY)
            if (p := REGISTRY.get(ref)) is not None
            and not p.todo
            and ref not in held
            # A class feature and the cards it deals are not powers the
            # class *has* at a level; they arrive with the feature. Left
            # in, "choose a 1st-level at-will of that class" offered a
            # curse card off a feature the character cannot own.
            and (bool(among) or not ref.startswith("cf:"))
            and (bool(among) or p.cls == cls)
            and (bool(among) or p.level == level)
            and (bool(among) or p.usage is want)
            and (bool(among) or not attacks or p.attack is not None)
            and (keyword is None or keyword in p.keywords)
        ]
        if not pool:
            return ""
        taken = self.choose(sorted(pool), self.ref)
        if not taken:
            return ""
        self.grant_row(taken, on=self.me, until=until, uses=uses)
        return taken

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

    def scenery(
        self,
        kind: str = "",
        *,
        within: int = 0,
        of: int | None = None,
        loose: bool = False,
    ) -> list[int]:
        """What is standing on the map that is not a creature: a crate, a fire.

        `kind` is the printed word and `""` is all of it. `within` measures
        from `of`, which is the caster unless named. `loose` drops the ones
        bolted down or in somebody's hands, which is the clause an object
        target line prints.
        """
        from .query import scenery

        return scenery(
            self.world,
            kind,
            within=within,
            of=self.me if of is None else of,
            loose=loose,
        )

    def control(
        self,
        *,
        on: int | None = None,
        until: When = When.EONT,
        sustain: ActionType | None = None,
    ) -> Effect | None:
        """Take charge of a map feature, and put it back when you let go.

        "You take control of each fire in the burst that is not controlled
        by a creature ... expanded or relocated flames return to their
        normal size and location at the end of your next turn." Where it
        stood and how big it was are part of what taking control holds, so
        letting go is what restores them -- one hold rather than a separate
        clock per thing that might be done to it.
        """
        from .components import Scenery

        who = self._who(on)
        thing = self.world.get(who, Scenery) if who is not None else None
        pos = self.world.get(who, Position) if who is not None else None
        if thing is None or pos is None or thing.by == self.me:
            return None
        was, stood, spread_to, size = thing.by, pos.square, pos.spans, pos.size
        thing.by = self.me

        def release() -> None:
            live = self.world.get(who, Position)
            if live is None:
                return  # put out rather than let go: it is not coming back
            thing.by = was
            live.spans = spread_to
            live.size = size
            # Lifted rather than re-placed: scenery stands in its square
            # without owning it, the way a conjuration does, and moving it
            # is the only thing that ever put it in the occupancy index.
            self.world.grid.lift(who)
            live.square = stood

        return self.world.effects.apply(
            who,
            self.me,
            until,
            label=f"{self.ref} control",
            sustain_cost=sustain,
            on_end=[release],
        )

    def grow(self, squares_: int = 1, *, on: int | None = None) -> bool:
        """Spread a map feature into the clear ground beside it.

        A footprint rather than a `Size`: which neighbouring squares a fire
        takes depends on which of them are free, and no size category
        describes that shape. `Position.spans` is where a footprint that is
        not a block already lives.

        No duration of its own. What puts a thing back is whatever is
        holding it -- `c.control` restores the placement it took charge of
        -- because "expanded or relocated flames return to normal" is one
        clock covering both, not a clock per way of disturbing them.
        """
        who = self._who(on)
        pos = self.world.get(who, Position) if who is not None else None
        if pos is None or squares_ <= 0:
            return False
        taking = [
            sq
            for sq in sorted(spread(pos.squares, 1) - pos.squares)
            if self.world.grid.passable(sq) and self.world.grid.occupant(sq) is None
        ][:squares_]
        if not taking:
            return False
        pos.spans = pos.squares | frozenset(taking)
        self.world.bus.emit(Note(text=f"{self.ref}: {who} spreads to {sorted(taking)}"))
        return True

    def douse(self, *, on: int | None = None) -> bool:
        """Take a map feature off the board. It does not come back.

        The other half of `c.grow`: a fire that is put out is gone, where
        one that was made bigger is only bigger for a while.
        """
        from .components import Scenery

        who = self._who(on)
        if who is None or self.world.get(who, Scenery) is None:
            return False
        self.world.bus.emit(Note(text=f"{self.ref}: {who} is put out"))
        self.world.despawn(who)
        return True


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

    def shares_space(
        self,
        *,
        on: int | None = None,
        until: When = When.ENCOUNTER,
        difficult: bool = True,
    ) -> Effect | None:
        """Anyone may stand in this creature's square, and it costs them.

        Not `c.shift(share=True)`: that is an argument to **one move**, made
        by the creature doing the moving. This is the standing property the
        printed line describes -- a swarm's square is enterable by whoever
        likes, and the swarm is still in it -- so it has to live on the
        creature being entered rather than on the mover.

        Two mod keys rather than one, because the two halves come apart: a
        printed line that shares a square without charging for it is
        `difficult=False`, and `movement._clear` reads only the first.

        Yours, so it defaults to the **caster** -- every printed line of
        this shape is a trait about the creature carrying it.
        """
        who = on if on is not None else self.me
        held = self.bonus("shares_space", 1, on=who, until=until, kind=self.ref)
        if difficult:
            self.bonus("shares_space_rough", 1, on=who, until=until, kind=self.ref)
        return held

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

    def grab(self, *, on: int | None = None, by: int | None = None) -> Effect | None:
        """`by=` names the grabber when it is not the caster, as `c.mark`
        does: a summoned creature grabs on its own account, and hanging the
        relation on its summoner means nothing can read back what it holds.
        """
        who = self._who(on)
        if who is None:
            return None
        holder = self.me if by is None else by
        return self.world.effects.apply(
            who, self.me, When.ENCOUNTER, label=f"{self.ref} grab",
            relations=[(Relation.GRABBED_BY, holder, who)],
        )

    def grabbing(self, *, of: int | None = None) -> list[int]:
        """Everything this creature is holding in a grab."""
        return self.world.relations.targets(
            Relation.GRABBED_BY, self.me if of is None else of
        )

    def grabbed_by(self, *, on: int | None = None) -> list[int]:
        """Everyone holding that creature in a grab."""
        from .escape import holders

        who = self._who(on)
        return [] if who is None else holders(self.world, who)

    def escape(
        self,
        *,
        on: int | None = None,
        bonus: int = 0,
        skill: str = "",
        auto: bool = False,
    ) -> bool:
        """Make one escape attempt now. True if the grab is broken.

        The printed action is a move action and `actions.legal` offers it;
        this is the *other* half -- "you immediately use the escape
        action", "each ally can make an escape attempt as a free action"
        -- which happens on somebody else's clock and costs whatever the
        row that called it cost.

        **Follows `c.target` and falls back to the caster**, the way
        `c.save` does and for the same reason: almost every printed line
        of this shape hands the attempt to somebody else.

        `auto` is "you escape automatically" -- no check is rolled, so a
        row watching for one does not see a roll that never happened.
        """
        who = self._who(on) or self.me
        if who is None:
            return False
        from .escape import attempt

        return attempt(self.world, who, bonus=bonus, skill=skill, auto=auto)

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
        self,
        *,
        on: int | None = None,
        until: When = When.ENCOUNTER,
        when: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Effect | None:
        """"Enemies can't gain combat advantage by flanking it."

        Only the flanking branch: being dazed, hidden from, or granted the
        opening outright still works, which is what the printed line says.

        `when` is handed `attacker` and `target`, for the conditional
        printing -- "unless both of you are flanked", "while within 5
        squares of each other". `query.has_combat_advantage` used to read
        this modifier with an empty context, so such a gate was false
        forever and the row would have suppressed nothing.
        """
        return self.bonus(
            "unflankable", 1, on=on or self.me, until=until, kind="untyped",
            when=when,
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

    def see_unseen(
        self,
        *,
        on: int | None = None,
        until: When = When.ENCOUNTER,
        revert: ActionType | None = ActionType.MINOR,
    ) -> Effect | None:
        """Trade one sight for the other: the unseen are seen and the rest
        are not.

        Both halves already existed and neither said the swap.
        `c.see_invisible` turns the seer's own blindness off; the second
        sentence is aimed *at* the seer, so it is one `HIDDEN_FROM` per
        creature that was visible when this was cast -- which is where the
        honest limit is: nothing announces a creature arriving, so one that
        walks in afterwards stays seen.

        A sense of yours, so it defaults to the caster. `revert` is the
        printed way out, held the way `c.form`'s is.
        """
        from .query import hidden_from

        who = on or self.me
        worn = self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} swapped sight", drop_cost=revert
        )
        holds = [self.see_invisible(on=who, until=until)]
        for other in creatures(self.world):
            if other == who or who in hidden_from(self.world, other):
                continue
            holds.append(self.invisible(on=other, to=who, until=until))
        for hold in holds:
            if hold is not None:
                worn.on_end.append(
                    lambda h=hold: self.world.effects.end(h, "sight came back")
                )
        return worn

    def ignore_cover(
        self,
        *,
        on: int | None = None,
        until: When = When.EONT,
        partial: bool = False,
        once: bool = False,
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

        `once=True` is "your **next** attack ignores cover", spent on the
        roll that uses it. It passes straight through to `c.bonus`, which
        has always understood it -- a row wanting it wrote the underlying
        `c.bonus` call out by hand instead, duplicating this key, this
        size and this kind, which would have drifted the first time any
        of the three changed here.
        """
        return self.bonus(
            "ignore_cover", 2 if partial else 5,
            on=on if on is not None else self.me,
            until=until, kind="ignore cover", once=once, when=when,
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
        self,
        *,
        on: int | None = None,
        until: When = When.EONT,
        when: Callable[[dict[str, Any]], bool] | None = None,
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

        `when` is handed `attacker` and `target`, for the narrower printing:
        "you don't grant combat advantage to *those* creatures".
        """
        return self.bonus(
            "no_advantage", 1, on=on if on is not None else self.me,
            until=until, kind="untyped", when=when,
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
        # And the same thing again as a modifier, because the listener above
        # can only work for a **monster**: it reads the rolling row's header
        # damage line, and a character's damage is rolled in the body where
        # the header has no line to read. So every character row printing
        # "the attack deals maximum damage" was silently inert. The modifier
        # is read inside `_roll_damage`, which is the one place the dice are
        # actually in hand, and is spent there.
        if held is not None:
            mods = self.world.get(who, Mods) or self.world.add(who, Mods())
            mod = Mod("maximise", 1, kind="untyped", label=f"{self.ref} maximum damage")
            mods.items.append(mod)
            held.mods.append((who, mod))
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

    def second_wind(
        self, *, on: int | None = None, cost: ActionType = ActionType.STANDARD
    ) -> bool:
        """Take a second wind: a surge, and +2 to AC until your next turn.

        The only implementation. `actions.perform` used to own it and there
        was no door from a power body, so three content helpers had written
        it out again -- and each of their docstrings says so, which is the
        tell. A bare `c.surge` is not the same thing: the use has to be
        counted in `Powers` or the creature can take a second one.

        Being the one implementation is what makes `SecondWind` reliable:
        every door -- the action menu, a leader row spending an ally's,
        an item -- comes through here, so the event is emitted once, here,
        the way `SurgeSpent` is emitted from the one place a surge is
        decremented. `cost` is carried because a fighter's second wind is
        a minor action and a printed feat reads that.

        Returns False if it has already been taken this fight.
        """
        from .components import Health, Powers
        from .events import SecondWind
        from .query import surge_value
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
        worth = surge_value(self.world, who)
        coming = min(worth, max(0, health.max_hp - max(0, health.hp)))
        self.world.bus.emit(SecondWind(actor=who, healed=coming, cost=cost))
        spend_surge(self.world, who)
        self.world.heal(who, who, worth)
        # **All four defences, not just AC.** The printed rule is "+2 to
        # all defences until the start of your next turn" and this gave
        # AC alone, so every creature that took a second wind has been
        # two points easier to hit on Fortitude, Reflex and Will since
        # the method was written. It also made one feat unwritable in a
        # second way: a card reading "+1 AC and +3 to the others" would
        # have to be written against the bug and would go to +5 AC the
        # day it was fixed.
        for defence in Defense:
            self.bonus(defence, 2, until=When.SONT, on=who, kind="untyped")
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

    def as_basic(
        self,
        *refs: str,
        window: str = "",
        on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """"You can use <this row> in place of a melee basic attack."

        The other side of `c.no_basic`, which takes away what the basic
        attack *is*. This sentence only ever matters where the game
        **grants** a swing rather than asking for one, so the offer is
        filed under the window that hands it out -- `"opportunity"`,
        `"charge"`, `"challenge"` for the melee basic a defender's mark
        punishes with, `"ranged"` for a granted ranged basic -- and the
        default `""` is the card that names no window and answers every
        melee one.

        Several refs, because the printed line is nearly always a choice
        among an associated-powers list. Nothing is checked here: a list
        names rows the character may not possess and rows this build has
        not imported, and `dsl.basic_options` drops both at the moment
        the swing is offered rather than at the moment the feat is armed,
        which is when a borrowed row could still arrive.

        Yours, so it defaults to the caster.
        """
        from .components import Powers

        who = on if on is not None else self.me
        known = self.world.get(who, Powers)
        if known is None or not refs:
            return None
        was = known.instead.get(window)
        known.instead[window] = tuple(
            dict.fromkeys((*known.instead.get(window, ()), *refs))
        )

        def restore() -> None:
            if was is None:
                known.instead.pop(window, None)
            else:
                known.instead[window] = was

        return self.world.effects.apply(
            who, self.me, until,
            label=f"{self.ref} instead of a basic attack",
            on_end=[restore],
        )

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
        was, was_instead = known.basic, dict(known.instead)

        def restore() -> None:
            known.basic, known.instead = was, was_instead

        # The stand-ins go with it: they are what the basic attack *is*
        # in one window each, so leaving them would let a creature that
        # cannot make a basic attack still swing one on a charge.
        known.basic, known.instead = "", {}
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
        from .query import speed as _speed
        from .query import squares

        runner = who if who is not None else self.me
        beside = spread(squares(self.world, victim), 1)
        # Measured as a charge: `c.speed_of` is the ordinary question and a
        # bonus gated on charging is correctly false for it.
        paths = self.world.reachable_paths(runner, _speed(self.world, runner, {"charge": True}))
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
        from .dsl import basic_options, use

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
            # "You can use this in place of a melee basic attack when
            # charging." Asked of the runner, not the caster: a row that
            # sends somebody else charging is their choice to make.
            offered = basic_options(self.world, runner, "charge", ref)
            if len(offered) > 1:
                ref = self.world.decide(
                    runner, "choose", offered, "which attack to make"
                )
        return use(
            self.world, runner, ref, targets=[victim], spend=False, charge=True,
            granted_by=self.me, granted_via=self.ref,
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

        from .events import Summoned

        where = at or self._free_square_near(self.here)
        if where is None:
            return 0
        from .query import team as side_of

        made = loader.spawn(
            self.world, ref, where, team=team or side_of(self.world, self.me) or Team.ENEMY
        )
        if self.world.encounter is not None:
            self.world.encounter.join(made)
        # `Summoned` was added because a row whose whole Effect is "you
        # summon X" left no trace in the log -- and then only the two
        # inline paths emitted it, never this one, which is the path every
        # row naming a creature by id takes. So the commonest summon in the
        # game still announced nothing.
        self.world.bus.emit(Summoned(actor=self.me, summon=made, ref=self.ref))
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
        damage: str = "",
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
            Ident,
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
        if ref.startswith("comp:"):
            # A beast's page is a formula rather than a finished stat block
            # and lives in its own table, so it has a loader of its own. Its
            # level is its ranger's, which is what "based on its category
            # and level" means.
            from combat_engine.content import loader

            made = loader.spawn_companion(
                self.world, ref, where, team=side, level=self.stats.level
            )
            block = loader.companion(ref)
            damage = damage or block.damage
            kind = kind if kind != "spirit" else "beast"
            self.world.add(
                made,
                Companion(
                    owner=self.me,
                    ref=ref,
                    kind=kind,
                    damage=damage,
                    ability=block.ability.value,
                ),
            )
            return made
        if ref:
            from combat_engine.content import loader

            made = loader.spawn(self.world, ref, where, team=side)
        else:
            mine = self.world.need(self.me, Defenses)
            hp = max(1, self.surge_value())
            made = self.world.spawn(
                # A companion conjured from no stat block still has to be
                # somebody. The other two branches get an `Ident` from the
                # loader; this one had none, and a creature without one is
                # a creature `query.creatures` hands to every reader that
                # then asks it who it is -- the renderer raised on exactly
                # that, on a familiar armed at the start of the fight.
                # Named like the wall and the zone: the row that made it,
                # then what it is.
                Ident(ref=f"{self.ref}:{kind}"),
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
        self.world.add(
            made, Companion(owner=self.me, ref=ref, kind=kind, damage=damage)
        )
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

    def command(
        self, who: int, *, on: int | None = None, charge: bool = False
    ) -> AttackResult | None:
        """Spend your action making a summon attack with **its own** line.

        The half `from_=` could not do: it moves where the attack is
        measured and rolled from, and leaves the numbers the summoner's. A
        printed block that gives its creature an attack bonus means that
        bonus, so this reads the header's `summon=` line and rolls it from
        the creature.

        `charge=True` is "using its attack as a melee basic attack" at the
        end of a run-in: the swing is a charge, which is the +1 and every
        rider that reads one. `c.charge_at` cannot say it here, because it
        goes through `dsl.use` and a summon's attack line is not a row.
        """
        from .components import Companion
        from .dsl import get

        # Spending an action on it is what "you gave it a command" means,
        # and `turns._uncommanded` reads this at the end of the turn.
        held = self.world.get(who, Companion)
        if held is not None:
            held.commanded = self.world.round

        p = get(self.ref)
        spec = getattr(p, "summon", None) if p else None
        if spec is None or spec.attack is None:
            return None
        bonus = spec.attack.bonus_for(self.world, who, self.ref, self.branch)
        was, self.charge = self.charge, self.charge or charge
        try:
            hit = self.attack(bonus, spec.attack.vs, on=on, from_=who)
            if hit and spec.damage is not None:
                line = spec.damage
                # Through `_bonus_of`, the way `c.hit` reads a header's damage.
                # Every printed summon block says "+ Intelligence modifier",
                # which is `Damage(..., "int")` -- handed to `c.damage` raw it
                # reached `roll(dice).total + "int"` and every one raised.
                self.damage(
                    line.dice, self._bonus_of(line.bonus), dtype=line.dtype, on=on
                )
        finally:
            self.charge = was
        return hit

    def instinctive(self, who: int) -> bool:
        """Set a standing summon going on its own Instinctive Effect.

        The behaviour is written on the block that made the creature, and
        the row spending the action is generally a different one, so the
        block is found through the `Companion.ref` the summon was spawned
        with rather than through `self.ref` -- and the cast handed to it is
        rebound to that ref, or `c.command` inside would look for an attack
        line on the row that is only paying for this.

        False when the creature is not a summon of this caster's, or when
        its block prints no instinctive effect: most do not.
        """
        from dataclasses import replace

        from .components import Companion
        from .dsl import get

        mine = self.world.get(who, Companion)
        if mine is None or mine.owner != self.me:
            return False
        p = get(mine.ref)
        spec = getattr(p, "summon", None) if p else None
        act = getattr(spec, "instinctive", None) if spec is not None else None
        if act is None:
            return False
        act(replace(self, ref=mine.ref, targets=[], target=None, result=None), who)
        return True

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

    def companions(self, *, of: int | None = None) -> list[int]:
        """**Every** companion this creature owns, in the order they arrived.

        `c.companion` answers with one because one is the printed rule for
        a spirit and a beast alike. A summon is not so limited -- several
        stand at once -- and neither is a shaman who has been told he may
        call a second spirit.
        """
        from .components import Companion

        owner = of if of is not None else self.me
        return [
            eid
            for eid in self.world.having(Companion)
            if self.world.get(eid, Companion).owner == owner
        ]

    def familiar(self, *, of: int | None = None) -> int | None:
        """The familiar this creature keeps, whichever mode it is in.

        A familiar is a `Companion` -- the sorcerer rows have read it that
        way since the first one needed it -- so this is `c.companion` with
        the kind asked for, falling back to whatever single companion the
        creature has when nothing named one. The fallback cannot pick the
        wrong body: a class that keeps a familiar keeps no spirit and no
        beast.
        """
        from .components import Companion

        mine = self.companions(of=of)
        named = [e for e in mine if self.world.get(e, Companion).kind == "familiar"]
        if named:
            return named[0]
        return mine[0] if mine else None

    def beast(self, *, of: int | None = None, category: str = "") -> int | None:
        """The beast companion a ranger keeps, if it is on the board.

        `c.familiar` with the other word, and the same fallback for the same
        reason: a ranger who keeps a beast keeps no spirit and no familiar,
        so a single unnamed companion is it.

        `category` is the printed "chosen from one of these categories" --
        two feats pay out only for one particular category, and the ref the
        beast was called with *is* the category. It never guesses: a beast
        with no ref answers no category.
        """
        from .components import Companion

        mine = self.companions(of=of)
        named = [e for e in mine if self.world.get(e, Companion).kind == "beast"]
        found = named[0] if named else (mine[0] if mine else None)
        if found is None or not category:
            return found
        held = self.world.get(found, Companion)
        return found if held is not None and held.ref == category else None

    def call_beast(self, at: Square | None = None) -> int:
        """Put the ranger's beast on the board, the category off its build.

        The category is one choice with the fighting style rather than a
        second one, so `chargen` records it beside the leg's name as
        `beast:<ref>` and this reads it back -- exactly how `c.element`
        reads the warlock's. A character whose build names none gets
        nothing: a beast conjured out of no choice is a creature the sheet
        never paid for.
        """
        from .components import Build

        held = self.world.get(self.me, Build)
        ref = next(
            (
                choice.split(":", 1)[1]
                for choice in (held.choices if held is not None else ())
                if choice.startswith("beast:")
            ),
            "",
        )
        return self.call_companion(ref, at, kind="beast") if ref else 0

    def familiar_mode(self, mode: str, *, of: int | None = None) -> bool:
        """"Your familiar enters passive mode", and the way back out of it.

        Passive is off the board rather than a flag on something standing
        there: no square, so it cannot be targeted, nothing is adjacent to
        it and `Range(from_="companion")` measures from its owner instead.
        `Position` is kept rather than rebuilt because the size has to come
        back too.
        """
        from .components import Companion
        from .movement import place

        who = self.familiar(of=of)
        if who is None:
            return False
        mine = self.world.get(who, Companion)
        want = mode == "passive"
        if mine.passive == want:
            return False
        if want:
            mine.stowed = self.world.get(who, Position)
            self.world.grid.lift(who)
            self.world.drop(who, Position)
            mine.passive = True
            return True
        back = mine.stowed or Position(square=self.here)
        anchor = self.world.get(mine.owner or self.me, Position)
        if anchor is not None:
            back.square = self._free_square_near(anchor.square) or back.square
        self.world.add(who, back)
        mine.stowed = None
        mine.passive = False
        place(self.world, who, back.square)
        return True

    def can_flank(
        self, *, on: int | None = None, until: When = When.EONT
    ) -> Effect | None:
        """"Your familiar can flank with you or your allies."

        A companion is left out of `query.allies` on purpose, so one
        standing in the far square is furniture and every row that reads
        "each ally adjacent to your spirit" stays right. This is the
        modifier `query.flankers` reads to make an exception of one.

        Yours, so it defaults to the caster; a row granting it to a
        familiar names it.
        """
        return self.bonus("can_flank", 1, on=on or self.me, until=until, kind="untyped")

    # -- bodies raised and bodies put away -----------------------------------

    def reanimate(
        self,
        *,
        on: int | None = None,
        team: Team | None = None,
        hp: int = 1,
        until: When = When.ENCOUNTER,
    ) -> bool:
        """Put a dead creature back on the board, on somebody's side.

        `_die` leaves the body an entity and only lifts it off the grid, so
        raising one is a matter of giving it a square again. `c.summon`
        could not: it needs a ref, it spawns a *second* creature, and the
        corpse stays where it fell.

        The hold this leaves ends with the encounter -- or the instant the
        creature dies again, `Effects.bereave` sweeping what sits on a
        corpse -- and puts the side and the hit point ceiling back as they
        were. Without that a creature raised for one fight is quietly left
        on the wrong team for the next.

        One hit point is the printed number and it is not decoration:
        `dying_at` is half the maximum, so a body at a maximum of 1 dies
        outright to anything that touches it, which is the rule the card is
        describing.
        """
        from .components import Side
        from .events import Summoned
        from .movement import place
        from .query import team as side_of

        who = on if on is not None else self.target
        body = self.world.get(who, Health) if who is not None else None
        spot = self.world.get(who, Position) if who is not None else None
        if who is None or body is None or spot is None:
            return False
        grave = spot.square
        if self.world.grid.occupant(grave) not in (None, who):
            free = self._free_square_near(grave)
            if free is None:
                return False
            grave = free
        was_max, was_side = body.max_hp, self.world.get(who, Side)
        old_team = was_side.team if was_side is not None else None
        body.max_hp = max(1, hp)
        body.hp = max(1, hp)
        body.temp = 0
        body.failures = 0
        if was_side is not None:
            was_side.team = team or side_of(self.world, self.me) or was_side.team
        place(self.world, who, grave)

        def lay_down() -> None:
            # Only for a creature still standing. When the hold ends
            # because the body died *again*, `bereave` runs inside the
            # death and putting the old ceiling back moved `dying_at` down
            # with it -- so `alive` answered True for a corpse that had
            # just been announced dead.
            if alive(self.world, who):
                body.max_hp = was_max
            if was_side is not None and old_team is not None:
                was_side.team = old_team

        hold = self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} risen", on_end=[lay_down]
        )
        if hold is None:
            lay_down()
            return False
        self.world.bus.emit(Summoned(actor=self.me, summon=who, ref=self.ref))
        return True

    def no_healing(
        self, *, on: int | None = None, until: When = When.ENCOUNTER
    ) -> Effect | None:
        """"The creature cannot heal."

        `Healed` is a `Decision`, so this refuses it outright where
        `c.half_healing` only shrinks it.
        """
        from .events import Healed

        who = self._who(on)
        if who is None:
            return None

        def refuse(ev: Healed) -> None:
            if ev.target == who:
                ev.cancel("cannot heal")

        return self.watch(
            Healed, refuse, until=until, window=Window.BEFORE, on=who,
            label=f"{self.ref} cannot heal",
        )

    def no_miss_damage(
        self, *, on: int | None = None, until: When = When.ENCOUNTER
    ) -> Effect | None:
        """"The creature takes no damage from an attack that misses."

        The minion clause. The damage context had no way to ask whether the
        blow landed, so `deal_damage` is handed a `miss` flag and this is
        the only thing that reads it.
        """
        return self.bonus(
            "no_miss_damage", 1, on=on, until=until, kind="untyped"
        )

    def merge(
        self, into: Square | None = None, *, until: When = When.ENCOUNTER
    ) -> Effect | None:
        """Step inside something solid and stop being reachable.

        The square is the object's, and it is blocking already, so nothing
        walks into it and nothing walks through it. What the printed line
        adds is that line of effect stops in **both** directions --
        `c.hide` and `c.invisible` are about being seen, and an attacker
        that knows where you are still reaches through those.

        "You can see normally" is left as it reads: a perception line, with
        nothing on the board it could change while there is no line of
        effect to anything.

        Ending it puts the caster in the nearest unoccupied square, however
        it ended.
        """
        here = self.here
        stone = into or next(
            (
                sq
                for sq in sorted(spread({here}, 1) - {here})
                if self.world.grid.inside(sq)
                and not self.world.grid.passable(sq)
                and self.world.grid.occupant(sq) is None
            ),
            None,
        )
        if stone is None:
            return None
        from .movement import place

        hold = self.bonus("sealed", 1, on=self.me, until=until, kind="untyped")
        if hold is None:
            return None
        place(self.world, self.me, stone)

        def step_out() -> None:
            free = self._free_square_near(stone)
            if free is not None:
                place(self.world, self.me, free)

        hold.on_end.append(step_out)
        # "Until you end this effect as a minor action" is a printed way
        # out, which is what `drop_cost` is for -- distinct from a sustain,
        # which keeps a thing alive rather than killing it.
        hold.drop_cost = ActionType.MINOR
        return hold

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

    def guard(self, *, on: int | None = None, by: int | None = None) -> bool:
        """Take that creature under this one's protection.

        `by=` names the protector when it is not the caster, the way
        `c.mark` does. A summoned creature guards the character its
        summoner chose, and hanging the relation on the summoner instead
        means nothing can read back which character that was.
        """
        who = self._who(on)
        if who is None:
            return False
        self.world.relations.set(
            Relation.GUARDED_BY, self.me if by is None else by, who
        )
        return True

    def guarding(self, *, of: int | None = None) -> list[int]:
        """Everything this creature is guarding."""
        return self.world.relations.targets(
            Relation.GUARDED_BY, self.me if of is None else of
        )

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
        argument: `to="team"` for "you and your allies", and `to=<id>`
        for "one ally gains combat advantage against the target", which is
        the printed line this method used to say wrong.

        The words are `c.within`'s: **`"ally"` leaves you out** and
        `"team"` puts you in, so a card reading "each ally" and a card
        reading "you and each ally" are different arguments here as they
        are everywhere else. `"allies"` was the old spelling of `"team"`
        and there was no way at all to say `"ally"`.

        **An unknown word is an error.** Anything this did not recognise
        fell through to the caster, so `to="ally"` -- the obvious thing to
        write -- was a row that quietly benefited one creature instead of
        a side, and four rows written `to="side"` had been doing exactly
        that. A `KeyError` is the same answer `c.within` gives.
        """
        who = self._who(on)
        if who is None:
            return None
        if isinstance(to, int):
            beneficiaries = [to]
        else:
            beneficiaries = {
                "me": [self.me],
                "ally": self.allies(),
                "team": [self.me, *self.allies()],
            }[to]
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

    def treat_roll_as(
        self, parity: str, *, until: When = When.EONT, on: int | None = None
    ) -> Effect | None:
        """"Treat your attack roll as odd", whatever the die shows.

        Set on the result rather than by rewriting the die: the card says
        the *roll* counts as odd, not that a different number came up, and
        faking `natural` would change whether the attack hit and whether
        it was a critical -- both recomputed from it after the interrupt
        window. `AttackResult.parity` is the only thing that should read
        either, and the two rows that were asking `natural % 2` by hand
        now go through it.

        One roll, so it is spent on the first attack the creature makes.
        """
        from .events import AttackRolled

        # The **caster**, not `c.target`. `_who` follows the target, and
        # every printed one of these is about its own owner -- the same
        # trap that made `c.forbid` take a row away from nobody.
        who = on if on is not None else self.me
        held = self.effect(f"{self.ref} roll counts as {parity}", until=until, on=who)
        if held is None:
            return None

        def dictate(ev: AttackRolled) -> None:
            if ev.attacker != who or held.ended:
                return
            result = getattr(ev, "result", None)
            if result is not None:
                result.treated = parity
                self.world.effects.end(held, "spent")

        held.subs.append(self.world.bus.on(AttackRolled, dictate, owner=who))
        return held

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
        dice: str = "",
        dtype: DamageType | Sequence[DamageType] | None = None,
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

        `dice` is a **rolled** modifier -- "roll a d6 and add it as a power
        bonus to the roll" -- and it is rolled afresh every time the modifier
        is read, which is once per roll, because that is what the sentence
        says. `value` still adds on top, for a card printing both.

        `dtype` is for `"damage"` and `"crit_damage"` only, and it is the
        difference between "+2 damage" and "**2 extra fire damage**". The
        second is a whole family of feats and a long tail of item riders,
        and every one of them used to roll untyped: the points went past a
        fire resistance that should have stopped them and missed a fire
        vulnerability that should have caught them. Given one, the rider
        is carried as its own typed part of the blow and meets the
        target's defences on its own terms; the power's own damage is
        untouched and stays whatever type the power was.

        A sequence is one rider of several types -- "1d6 extra cold and
        lightning damage" is a single 1d6, not two -- and resistance reads
        it as a unit: it is shrugged off only as far as the target resists
        every type in it.

        **Only reach for it when the rider's type differs from the
        power's.** "Your fire powers deal +2 damage" is a plain untyped
        `c.bonus`, because those points are already fire: the power said
        so. Passing `dtype=` there splits one blow into two parts that
        meet the same resistance and changes nothing but the arithmetic's
        shape.
        """
        who = self._who(on)
        if who is None:
            return None
        key = what.value if isinstance(what, Defense) else what
        if dtype is not None and key not in ("damage", "crit_damage"):
            raise ValueError(
                f"{self.ref}: c.bonus(dtype=) is the type of the extra "
                f"*damage*, so it means nothing on {key!r}. "
                f"To gate a bonus on the damage type of the blow, use "
                f"when=lambda ctx: ctx['dtype'] is DamageType.FIRE."
            )
        types: tuple[DamageType, ...] = ()
        if dtype is not None:
            types = (dtype,) if isinstance(dtype, DamageType) else tuple(dtype)
        # `stacks=False` buckets this row's bonus under its own ref, so a
        # second one from the same row does not add -- the larger wins, the
        # way two bonuses of a type do. "This bonus increases to +4" and "a
        # second hit renews rather than doubles" are both that sentence,
        # and both used to lean on being `kind="power"` by accident. One
        # row had already discovered the trick and written `kind=c.ref`.
        if not stacks:
            # **And a caller's `kind=` is refused, not overwritten.** This
            # used to silently discard it, which let a row pass
            # `scripts/bonuses.py` -- that reads the source literal --
            # while bucketing under the row's ref at runtime. A row could
            # satisfy the bonus-type audit and not be of that type, which
            # is the one thing that audit exists to make impossible.
            if kind != "untyped":
                raise ValueError(
                    f"{self.ref}: c.bonus(stacks=False) buckets under the "
                    f"row's own ref, so it cannot also be kind={kind!r}. "
                    f"Drop one: `stacks=False` for a bonus that renews "
                    f"rather than adds, `kind=` for a printed type."
                )
            kind = self.ref
        rng = self.world.rng
        mod = Mod(
            what=key, value=value, kind=kind, when=when, label=self.ref,
            roll=(lambda: rng.roll(dice).total) if dice else None,
            dtype=types,
        )
        shown = f"+{dice}" if dice else f"{value:+d}"
        effect = self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} {key}{shown}", mods=[(who, mod)]
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
                    # The real context, as above: the two-key rebuild made
                    # a one-shot damage rider gated on `opportunity` or
                    # `charge` impossible to spend.
                    ctx = getattr(ev, "ctx", None) or {
                        "target": ev.target, "power": ev.detail,
                    }
                    if ev.source == who and mod.applies(ctx):
                        self.world.effects.end(effect, "used")

                effect.subs.append(
                    self.world.bus.on(DamageRolled, spend_damage, owner=who)
                )
            elif key == "save":
                # **A one-shot save bonus was spent by the next attack
                # roll.** The branch below watches `AttackRolled` for
                # every key that is not damage, a defence or the crit
                # range -- so "a +2 bonus to your next saving throw", a
                # common printed line that ten rows in the tree carry,
                # was consumed by the owner's next *swing* and was still
                # standing for the second save of the window. Fourth
                # time a branch of this method has spent a modifier
                # somewhere other than where it is read.
                from .events import SavingThrow

                def spend_save(ev: SavingThrow) -> None:
                    if ev.actor == who:
                        self.world.effects.end(effect, "used")

                effect.subs.append(
                    self.world.bus.on(SavingThrow, spend_save, owner=who)
                )
            else:

                def spend(ev: AttackRolled) -> None:
                    if ev.attacker != who:
                        return
                    # **The context the roll actually used**, which
                    # `resolve.attack` stamps on the event. This used to
                    # rebuild a four-key one, so a `when=` gate reading
                    # anything else -- `ranged`, `opportunity`, `charge`,
                    # `branch`, `action_point` -- was False here and the
                    # effect was never ended. Forty-six gated one-shots in
                    # the tree were therefore permanent bonuses, each
                    # looking exactly like a correctly written row.
                    ctx = getattr(ev, "ctx", None) or {
                        "attacker": ev.attacker, "target": ev.target,
                        "power": ev.power, "advantage": ev.advantage,
                    }
                    if mod.applies(ctx):
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

    @property
    def enhancement(self) -> int:
        """The plus of the magic item **this row belongs to**.

        "Equal to the enhancement bonus" is printed on fourteen of the
        first sixty weapon blocks, and the number is a column that a body
        must never write down -- so it has to be read. The first item
        wave invented the same helper to do it and every later wave would
        have invented it again, which is how a project ends up with three
        subtly different answers to one question.

        Found by matching this row's item against `Weapon.item`, not by
        taking whatever magic is in hand: a character carrying a magic
        sword and a magic bow has two, and the row belongs to one of
        them.

        Falls back to the enhancement of whatever magic *is* held, and
        then to 1. A row that read 0 would do nothing at all, which on an
        audit board looks exactly like a row that is broken.
        """
        mine = self.ref.split("x")[0].split("p")[0]
        # `on=self.me`, not the default. `c.held` follows `c.target` like
        # everything else that is about somebody else's body -- and this
        # is about the caster's hand. Written without it first, and it
        # returned 1 for a +2 axe in silence, which is the fourth time
        # this default has caught somebody on this project.
        magic = self.held(on=self.me, what="magic")
        for w in magic:
            if w.item == mine:
                return w.enhancement
        # Neither is a suit of armour or anything in the small slots, and
        # "a bonus equal to the armour's enhancement bonus" is printed on
        # a dozen of them -- they were all reading the plus of whatever
        # sword happened to be in the same hand. Ammunition is in neither
        # place: it is spent, so it lives in the quiver.
        gear = self.world.get(self.me, Gear)
        if gear is not None:
            worn = next((m for m in gear.worn.values() if m.ref == mine), None)
            if worn is not None and worn.plus:
                return worn.plus
            for piece in gear.quiver:
                if piece.ref == mine:
                    return piece.plus
        return magic[0].enhancement if magic else 1

    def as_implement(self, *, on: int | None = None) -> None:
        """This weapon counts as an implement for its wielder's powers.

        The commonest single property in the magic weapon slot -- 35 item
        blocks print it, eleven of them in the first sixty -- and there
        was no door at all: `Gear.implement` picks the first held weapon
        whose `group` is `"implement"`, and a sword's group is `"heavy
        blade"` whatever a card says about it.

        Written onto the weapon rather than held as an effect, because
        the sentence is a fact about the object and not about the fight:
        it is true while the thing is in your hand and meaningless when
        it is not. `chargen.spawn` copies every weapon per character, so
        this cannot leak into anybody else's sword -- which it would
        have done before that copy existed.

        The **class** half of the printed line -- "*bards* can use this
        weapon as an implement" -- is not enforced here. The character
        holding it is the one the item was dealt to, and nothing deals a
        bard's weapon to a fighter; enforcing it would mean a `requires=`
        that is true for every creature that will ever hold the thing.
        """
        gear = self.world.get(self._who(on) or self.me, Gear)
        if gear is None:
            return
        arm = gear.main
        if arm is None or arm.group == "implement":
            return
        gear.weapons = [
            replace(w, group="implement", properties=w.properties | {arm.group})
            if w is arm
            else w
            for w in gear.weapons
        ]

    def regeneration(
        self,
        amount: int,
        *,
        until: When = When.ENCOUNTER,
        on: int | None = None,
        while_bloodied: bool = False,
    ) -> Effect:
        """Heal this much at the start of each of that creature's turns.

        Written out by hand in eight files before this existed -- the same
        `TurnStart` watcher, the same `ev.ghost` guard, the same
        `ev.actor == me` test, eight times -- and `docs/AUTHORING.md` said
        regeneration was in the vocabulary while `grep` found one comment.

        `while_bloodied` is the commoner printed form of the two: a
        regenerating monster usually only does it while hurt.

        **`ev.ghost` matters.** A ghost turn is the engine looking ahead,
        not a turn happening, and healing on one pays out for free every
        time a policy thinks about the board.
        """
        who = self._who(on) if on is not None else self.me
        if who is None:
            return None  # type: ignore[return-value]

        def tick(ev: Any) -> None:
            if ev.actor != who or ev.ghost:
                return
            if while_bloodied and not self.bloodied(on=who):
                return
            self.heal(amount, on=who)

        from .events import TurnStart

        return self.watch(
            TurnStart, tick, until=until, on=who,
            label=f"{self.ref} regeneration",
        )

    def arm_trigger(
        self,
        event: type[Event],
        fn: Callable[[Any], None],
        *,
        when: Callable[[Any], bool] | None = None,
        cost: ActionType = ActionType.IMMEDIATE_REACTION,
        until: When = When.EONT,
        on: int | None = None,
        window: Window | None = None,
        label: str = "",
    ) -> Effect:
        """A `c.watch` that costs the watcher the action a trigger costs.

        A declared trigger is **header data on the row that owns it**, so a
        body that arms a reaction for a duration -- "until the end of its
        next turn, when an adjacent enemy moves it may shift 1" -- has no
        header to write to and falls back to `c.watch`, which is free.
        That is the one way such a row differs from its printed line, and
        the difference is the whole point of an immediate action: once a
        round, and not while dazed.

        `Encounter.spend` is the same budget `triggers._ask` charges, so an
        armed reaction and a declared one cannot both fire in one round.
        Nothing happens if it cannot be paid, which is the printed rule.

        `window` defaults to the one the action type implies, the same
        table the dispatcher uses -- an interrupt resolves before the thing
        it answers and may `ev.cancel()` it, a reaction after.

        **Handing a whole row over is `c.grant_row`, not this.** A row with
        a declared trigger goes into `Powers.known` and the dispatcher
        budgets it already; this is for the reaction that has no row.
        """
        from .triggers import WINDOW_OF

        who = on if on is not None else self.me
        where = window if window is not None else WINDOW_OF.get(cost, Window.AFTER)

        def budgeted(ev: Any) -> None:
            if when is not None and not when(ev):
                return
            encounter = getattr(self.world, "encounter", None)
            if encounter is None or not encounter.spend(who, cost):
                return
            fn(ev)

        return self.watch(
            event, budgeted, until=until, window=where, on=who,
            label=label or self.ref,
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

    def in_my_aura(self, who: int | None = None, *, label: str = "") -> bool:
        """Is that creature standing inside an aura of mine?

        The other half of `c.my_aura`, which could hand back the aura's id
        and never say who was in it -- so "an enemy subject to your defender
        aura", printed on a row per defender class, had nothing to ask.
        Theirs, so it follows `c.target`; `label` narrows it to one aura
        when a creature is carrying more than one.
        """
        target = self._who(who)
        if target is None:
            return False
        return any(
            z.aura
            and z.owner == self.me
            and (not label or label in (z.label or ""))
            and target in self.world.zones.occupants(zid)
            for zid, z in self.world.zones.all()
        )

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
        side: str = "team",
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

        `side` reads as it does on `c.within`: `"team"` is your side with
        you in it, which is the "you and your allies" these zones print;
        `"ally"` leaves you out, which is the rarer "allies in the zone".
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
        side: str = "team",
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

        held: dict[int, Effect] = {}

        def give(who: int) -> None:
            # `_side`, so the five words mean here what they mean on
            # `c.within` and `c.in_squares`. They did not: this answered
            # team identity, which made `"ally"` include the caster while
            # one file along it excluded him -- right in both places and
            # opposite between them, which is worse than a uniform bug.
            # Asked per arrival rather than once, because a creature
            # summoned after the zone was laid still has to be in the pool
            # the moment it walks in.
            if who in held or who not in self._side(side, self.me):
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
            PowerUsed(
                actor=self.me, power=self.ref, targets=list(self.targets),
                trigger=self.trigger,
                granted_by=self.granted_by, granted_via=self.granted_via,
            )
        )
        owner = self._item_owner()
        if owner:
            self.world.bus.emit(
                ItemPowerUsed(actor=self.me, power=self.ref, item=owner)
            )

    def _item_owner(self) -> str:
        """The magic item this row came off, if it came off one.

        An item's rows are ordinary rows in `Powers.known`; what makes
        this one an *item* power is that something the creature is
        carrying lists it. Asked of the gear rather than of the ref's
        spelling, because a ref is an id and reading meaning out of its
        letters is how the next rename becomes a silent bug.
        """
        gear = self.world.get(self.me, Gear)
        if gear is None:
            return ""
        for magic in gear.worn.values():
            if self.ref in magic.powers:
                return magic.ref
        return ""

    # -- reading modifiers back ---------------------------------------------

    def total(self, what: str, on: int | None = None,
              ctx: dict[str, Any] | None = None) -> int:
        """Sum the modifiers to `what` on that creature.

        `ctx` is what a gated modifier is asked. Without it a
        `c.bonus(..., when=...)` cannot narrow, and every such bonus
        counts -- which is how a "+2 to saving throws **against poison**"
        came to be a bonus to every saving throw.
        """
        who = on if on is not None else self.me
        mods = self.world.get(who, Mods)
        return mods.total(what, ctx or {}) if mods else 0

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
        lower roll" and its opposite -- both properties of the roller rather
        than of the blow, which is why they are read here and not passed in.
        The worse of the two wins when a creature somehow carries both."""
        # Maximum comes first, and is read **here** rather than topped up on
        # `DamageRolled`. The listener version looked the dice up from the
        # rolling row's *header* damage line -- which only a monster has,
        # because a character's damage is rolled in the body -- so
        # "the attack deals maximum damage" was silently inert for every
        # character row that prints it. Two agents flagged it and neither
        # fixed it; the dice are in hand at this point and nowhere else.
        if self._take_maximum():
            return _max_of(dice)
        first = self.world.rng.roll(dice).total
        if self.total("damage_twice_lower") > 0:
            return min(first, self.world.rng.roll(dice).total)
        if self._rolls_twice_higher():
            return max(first, self.world.rng.roll(dice).total)
        return first

    def _take_maximum(self) -> bool:
        """Is a "deals maximum damage" hold waiting, and spend it if so.

        One-shot, and removed here rather than left to expire: the printed
        line is "the *attack* deals maximum damage", so a row whose splash
        is a flat 3 to everyone beside the victim must come out [23, 3, 3,
        3] and not [23, 23, 23, 23].
        """
        mods = self.world.get(self.me, Mods)
        if mods is None:
            return False
        for m in mods.items:
            if m.what == "maximise":
                mods.items.remove(m)
                return True
        return False

    # -- the action economy --------------------------------------------------

    def extra_action(
        self, cost: ActionType = ActionType.MOVE, *, on: int | None = None
    ) -> bool:
        """"You can take an extra move action."

        `c.extra_turn` was the nearest thing and hands out a whole second
        slot in the initiative order, which is a solo's line rather than
        this one. This drops one action into the budget the turn is already
        spending, which `Encounter.can` reads back.

        Announced with `ActionGranted`, because the budget alone is
        invisible: a row whose whole printed effect is this one line left
        nothing in the log and nothing for another row to answer.

        Yours, so it defaults to the **caster**.
        """
        from .components import Budget
        from .events import ActionGranted

        who = on if on is not None else self.me
        budget = self.world.get(who, Budget) or self.world.add(who, Budget())
        if not hasattr(budget, cost.value):
            return False
        setattr(budget, cost.value, getattr(budget, cost.value) + 1)
        self.world.bus.emit(ActionGranted(actor=who, cost=cost))
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

        It lives in a closure inside `cf:ranger-f1` and nothing could
        read it back, so "extra damage equal to your Hunter's Quarry damage"
        -- a line two rows hand to somebody else -- had no number to name.
        Kept as one expression beside that feature's rather than derived
        from the printed per-tier table, so the two cannot disagree.
        """
        return "1d6"

    # -- what a zone gives the people standing in it -------------------------

    def cover_in(self, zone: int, *, side: str = "team") -> None:
        """"You and your allies have cover while within the zone."

        `c.zone(blocks_sight=True)` is the nearest thing and is not this: it
        is terrain, it blinds both sides, and the creature standing in it
        gets nothing for being there. Cover was traced between two positions
        and read no modifier, so a zone could never be the thing sheltering
        you; `query.cover_between` now takes the larger of the trace and a
        carried `"cover"`, which is also why this does not stack with a
        pillar.

        Hung on the geometry like `c.grants_in`: taken on entering, given
        back on leaving.
        """
        self._while_inside(
            zone,
            lambda who: self.bonus(
                "cover", 2, on=who, until=When.ENCOUNTER, kind="cover"
            ),
            side,
        )

    def ignores_difficult_in(self, zone: int, *, side: str = "team") -> None:
        """"You and your allies can ignore difficult terrain in the zone."

        `c.ignores_difficult` is per-creature and board-wide, so writing the
        printed line as that exempts the party everywhere -- which is a
        different rule, and why the row printing it was left out rather than
        approximated. Same grant, bounded by the zone's squares.
        """
        self._while_inside(
            zone,
            lambda who: self.ignores_difficult(on=who, until=When.ENCOUNTER),
            side,
        )

    # -- reach that is not a reach -------------------------------------------

    def widen_areas(
        self, squares_: int = 1, *, on: int | None = None, until: When = When.EONT
    ) -> Effect | None:
        """"Increase the size of your close blast or close burst attacks by 1."

        `dsl._stretched` lengthened a melee reach and a ranged range from a
        modifier and returned 0 for everything else, so a burst was the one
        shape no printed line could stretch. Defaults to the **caster**: it
        is a reach of yours, beside `c.threatens` and `c.mode`.
        """
        return self.bonus(
            "blast_size", squares_, on=on if on is not None else self.me, until=until
        )

    # -- a second roll, which is not a maximum -------------------------------

    def reroll_damage(
        self,
        *,
        keyword: Keyword | None = None,
        on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """"Roll the damage twice and use the higher result."

        The mirror of `c.damage_disadvantage`, and read in the same place
        for the same reason: a character's damage line lives in the body,
        not the header, so there is nothing to look up afterwards and
        `DamageRolled` carries a total with no dice behind it. A watcher on
        that event can only ever raise a monster's printed line, which is
        not who prints this sentence.

        `c.maximise` is the neighbour and a different operation -- a maximum
        is not a second roll, and a row printing both would pay out twice.

        `keyword` narrows it to the powers the printed line names; the row
        being rolled is what answers, so the key carries the word.
        """
        who = on if on is not None else self.me
        what = "damage_twice_higher"
        if keyword is not None:
            what = f"{what}:{keyword.value}"
        return self.bonus(what, 1, on=who, until=until, kind=self.ref)

    def _rolls_twice_higher(self) -> bool:
        """Does this roller take the better of two, for *this* row?

        The unqualified key is every damage roll it makes; a qualified one
        names a keyword, and the row doing the rolling is asked whether it
        carries the word.
        """
        if self.total("damage_twice_higher") > 0:
            return True
        from .dsl import get

        p = get(self.ref)
        if p is None:
            return False
        return any(
            self.total(f"damage_twice_higher:{k.value}") > 0 for k in p.keywords
        )

    # -- a hold changing hands -----------------------------------------------

    def pass_on(self, ev: Any = None, *, to: int | None = None) -> Effect | None:
        """Whatever conditions the attack being answered would apply, land
        on somebody else instead.

        An interrupt resolves **before** the blow, so at the moment this
        runs there is nothing to `c.transfer` -- the conditions do not exist
        yet. So it arms rather than moves: every condition the triggering
        power puts on this creature while it is still resolving is picked
        up and passed along intact, saving throw and all.

        Bounded by the log and by `ev` rather than by a clock. "Applied by
        the triggering attack" is one power's resolution by one creature,
        and `When.EOT` would have caught the whole of the attacker's turn;
        the watch takes only what the creature that swung applies, and
        stands down as soon as another power is used.

        It inherits `c.transfer`'s one refusal: a hold carrying a relation
        -- a mark, a grab -- is left where it landed rather than half moved.
        """
        from .events import ConditionApplied

        victim = self._who(to)
        mine = self.me
        if victim is None or victim == mine:
            return None
        blow = ev if ev is not None else self.trigger
        swinger = getattr(blow, "attacker", None)
        start = len(self.world.bus.log)
        armed: list[Effect] = []

        def caught(applied: ConditionApplied) -> None:
            if any(isinstance(e, PowerUsed) for e in self.world.bus.log[start:]):
                if armed:
                    self.world.effects.end(armed[0], "the blow is over")
                return
            if applied.target != mine:
                return
            if swinger is not None and applied.source != swinger:
                return
            for eff in sorted(self.world.effects.of(mine), key=lambda e: -e.id):
                if applied.condition in eff.conditions:
                    self.transfer(eff, to=victim)
                    return

        armed.append(
            self.watch(
                ConditionApplied,
                caught,
                until=When.EOT,
                on=mine,
                label=f"{self.ref} passed on",
            )
        )
        return armed[0]

    def transfer(
        self, effect: Effect | None, *, to: int, save_mod: int = 0
    ) -> Effect | None:
        """Move a live hold from one creature to another, intact.

        `Effects` can apply and end, and "you transfer one effect on the
        target to yourself" is neither: ending it and writing a fresh one by
        hand loses the hold's conditions, its ongoing damage and the saving
        throw it is still owed. Rebuilt from the effect itself, with every
        modifier that pointed at the old subject re-aimed at the new one.

        **It refuses a hold carrying a relation or a subscription** and
        returns None rather than dropping half of it: whose mark it is has
        no answer here, and a watcher armed on the old subject is not the
        same watcher on the new one.
        """
        if effect is None or effect.ended or effect.relations or effect.subs:
            return None
        old = effect.owner
        self.world.effects.end(effect, "transferred")
        return self.world.effects.apply(
            to,
            effect.source,
            effect.when,
            label=effect.label,
            conditions=effect.conditions,
            mods=[(to if eid == old else eid, m) for eid, m in effect.mods],
            ongoing=effect.ongoing,
            save_mod=effect.save_mod + save_mod,
            escalate=effect.escalate,
        )

    # -- added for the tail-3 batch ------------------------------------------

    def no_walk(self, *, until: When = When.EONT, on: int | None = None) -> Effect | None:
        """"It cannot use move actions to walk or run." It may still shift.

        The mirror of `c.rooted`, which bars the shift and leaves the walk.
        Neither is `c.immobilized`: that stops both, and a row printing only
        one half was being written as the stronger card or dropped.

        A modifier rather than a condition, because nothing else about the
        creature changes -- it grants nothing, it is not slowed, it is only
        not walking. `query.can_walk` is what reads it, and `actions.legal`
        stops offering the move so a policy cannot pick one either.
        """
        return self.bonus("no_walk", 1, on=on, until=until, kind="untyped")

    def regain_surge(self, count: int = 1, *, on: int | None = None) -> int:
        """"Each target regains a healing surge." Returns how many it now has.

        The counterpart of `c.spend_surge`, which existed alone -- so a row
        handing one back had only `Health.surges += 1` to reach for, which
        announces nothing and audits as a row that did nothing at all.

        Follows `c.target`: it is done *to* somebody, and every printed line
        of this shape hands them out to a list of allies.
        """
        who = self._who(on)
        health = self.world.get(who, Health) if who is not None else None
        if who is None or health is None or count <= 0:
            return 0
        health.surges += count
        self.world.bus.emit(
            Note(text=f"{who} regains {count} healing surge(s): {health.surges} left")
        )
        return health.surges

    # -- borrowing somebody else's attack ------------------------------------

    def knows(self, ref: str) -> int | None:
        """Who on the board has that row, if anybody.

        For the rows that choose a power belonging to a creature they can
        see and then do something with it. `c.grant_row` goes the other way
        and there was no way to ask the question at all.
        """
        from .components import Powers

        for eid in creatures(self.world):
            known = self.world.get(eid, Powers)
            if known is not None and ref in known.all:
                return eid
        return None

    def borrowed_rows(self, of: int, *, at_will: bool = True, melee: bool = True) -> list[str]:
        """That creature's attack rows, for a power that copies one.

        Filtered the way the printed lines filter: "one at-will melee attack
        power belonging to an enemy that it can see". A standard action, so
        a class feature that happens to carry an attack line -- a trait, an
        opportunity rider -- is not offered as a power to copy; one of those
        chosen is a row whose body does nothing outside its own trigger.
        """
        from .components import Powers
        from .dsl import get
        from .types import Usage

        known = self.world.get(of, Powers)
        out: list[str] = []
        for ref in known.all if known else ():
            p = get(ref)
            if p is None or p.attack_of(0) is None:
                continue
            if p.action is not ActionType.STANDARD:
                continue
            if at_will and p.usage is not Usage.AT_WILL:
                continue
            kind = p.reach_of(0).kind
            if melee and kind != "melee":
                continue
            if not melee and kind not in ("ranged", "area_burst"):
                continue
            out.append(ref)
        return out

    def as_though_hit_by(
        self, ref: str, *, on: int | None = None, by: int | None = None
    ) -> bool:
        """"The target is subject to effects as though hit by the chosen attack."

        Five rows roll an attack of their own and then pay out a power they
        have copied off somebody else. `c.grant_row` lends the whole row --
        its own attack line and its own numbers -- and `use` rolls it again,
        so neither of them says this sentence.

        The borrowed body runs with its **owner** as the caster, which is
        how the printed line gets "the ability score modifier of the
        creature from whom the power was taken", and its attack is forced to
        land rather than rolled a second time. The cost of that judgement is
        that the blow is credited to the owner rather than to whoever
        borrowed it; the alternative loses the owner's weapon and modifier,
        which is the only number the line names. `by` says who owns it when
        nobody on the board does.
        """
        from .dsl import get
        from .events import AttackRolled

        who = self._who(on)
        p = get(ref)
        owner = by if by is not None else self.knows(ref)
        if who is None or p is None or owner is None:
            return False
        borrowed = Cast(
            world=self.world, me=owner, ref=ref, targets=[who], target=who
        )

        def lands(ev: AttackRolled) -> None:
            result = getattr(ev, "result", None)
            if result is not None and ev.attacker == owner and ev.power == ref:
                result.forced = True

        sub = self.world.bus.on(AttackRolled, lands)
        try:
            p.body(borrowed)
        finally:
            self.world.bus.off(sub)
        return True

    # -- the rattling keyword ------------------------------------------------

    def _rattle(self, who: int) -> None:
        """Pay out `Keyword.RATTLING` on a blow that has just dealt damage.

        Here rather than in `resolve` because `c.damage` is where every
        power's damage goes through and the keyword is a property of the
        power, which is only known on this side. The whole of the word is
        -2 to the target's attack rolls until the end of your next turn.
        """
        p = self._declared()
        rattles = bool(p and Keyword.RATTLING in p.keywords)
        if not rattles:
            rattles = bool(self.total("rattling")) or (
                bool(self.total("rattling melee")) and not self.ranged
            )
        if not rattles:
            return
        self.penalty("attack", 2, on=who, until=When.EONT)
        self.effect("rattled", on=who, until=When.EONT)

    def rattling(
        self, *, until: When = When.ENCOUNTER, on: int | None = None, melee: bool = False
    ) -> Effect | None:
        """"Your attacks gain the rattling keyword."

        The keyword is a property of a *power*, and these rows hand it to a
        creature instead, so it is held as a modifier that `c.damage` reads
        beside the header. `melee` is the narrower printing -- "your melee
        attacks" -- which is the only difference between the two rows that
        say it. Defaults to the caster; every printed one is about its owner.
        """
        return self.bonus(
            "rattling melee" if melee else "rattling", 1,
            on=on if on is not None else self.me, until=until, kind="untyped",
        )

    def rattled(self, on: int | None = None) -> bool:
        """Is that creature taking the penalty from one of my rattling attacks?"""
        who = self._who(on)
        return who is not None and who in self.suffering("rattled")

    def sneak_damage(self) -> str:
        """The dice the rogue's once-a-round rider pays out, as an expression.

        The twin of `c.quarry_damage`, and for the same reason: the number
        lives in a closure inside `cf:rogue-scoundrel-f4` and nothing could read it
        back, so "extra damage equal to your Sneak Attack damage" -- a line
        one row hands to somebody else -- had no number to name. Kept as one
        expression beside that feature's so the two cannot disagree; the
        modifier half is `c.total("cf:rogue-scoundrel-f4 damage")`, which is what
        `extra_damage` adds on top.
        """
        return "2d6"

    # -- moving a zone, and jumping ------------------------------------------

    def my_zones(self) -> list[int]:
        """Every live zone and conjuration this caster owns. Auras included."""
        from .zones import Zone as _Zone

        return sorted(
            eid for eid, zone in self.world.each(_Zone) if zone.owner == self.me
        )

    def line(self, a: Square, b: Square) -> list[Square]:
        """The squares a straight run from one square to another covers.

        The board's own answer, so a row that spans two points does not do
        arithmetic on coordinates -- diagonals count as one step here as
        they do everywhere else.
        """
        from .movement import _line

        return _line(a, b)

    def floor(
        self,
        area: Iterable[Square],
        *,
        until: When = When.SUSTAIN,
        sustain: ActionType | None = ActionType.MINOR,
    ) -> Effect | None:
        """Lay ground where the ground is against you: a bridge, a plank.

        Not a zone. A zone can only *add* difficult going, and the printed
        sentence is a removal -- "as though it were normal terrain, even if
        it normally contains no terrain, difficult terrain or hindering
        terrain" takes away the hole, the rough going and the drop at once.
        `Grid.bridged` is the single overlay all three are answered
        through, so the map underneath is untouched and comes back when
        this lapses.

        The squares are the caster's to place, so this does not take `on=`.
        """
        laid = {sq for sq in area if sq not in self.world.grid.bridged}
        if not laid:
            return None
        self.world.grid.bridged |= laid
        return self.world.effects.apply(
            self.me,
            self.me,
            until,
            label=f"{self.ref} floor",
            sustain_cost=sustain if until is When.SUSTAIN else None,
            on_end=[lambda: self.world.grid.bridged.difference_update(laid)],
        )

    def move_zone(self, zone: int, squares_: int, *, to: Square | None = None) -> bool:
        """Move a zone or a conjuration, keeping its shape.

        "As a move action you can move the zone 5 squares" is printed on
        every second zone in the game, and `Zones` had no mover at all -- so
        the rider was dropped from five written rows and the one row whose
        whole Effect is that sentence could not be written. An aura moves
        with its owner and is refused here, which is the printed rule.
        """
        from .zones import Zone as _Zone

        z = self.world.get(zone, _Zone)
        if z is None or z.aura is not None or not z.squares or squares_ <= 0:
            return False
        here = min(z.squares)
        if to is None:
            to = self.world.decide(
                self.me, "move", sorted(spread({here}, squares_)),
                f"{self.ref}: move a zone {squares_}",
            )
        dx, dy = to[0] - here[0], to[1] - here[1]
        if not dx and not dy:
            return False
        z.squares = frozenset((x + dx, y + dy) for x, y in z.squares)
        spot = self.world.get(zone, Position)
        if spot is not None:
            spot.square = (spot.square[0] + dx, spot.square[1] + dy)
        self.world.zones.refresh()
        self.note(f"{self.ref}: zone {zone} moves to {min(z.squares)}")
        return True

    def jump(self, squares_: int, *, on: int | None = None) -> int:
        """A jump: ground crossed rather than walked over.

        "You can jump a number of squares equal to your Wisdom modifier, and
        the distance does not count toward your movement." Neither `c.move`
        nor `c.shift` says it -- a jump clears what is in the way -- so it is
        a move with the rough going and the bodies ignored for its length,
        paid for by the power rather than out of the turn.

        Defaults to the caster, like the movement methods beside it.
        """
        who = self.me if on is None else on
        if squares_ <= 0 or self.world.get(who, Position) is None:
            return 0
        over = self.phasing(until=When.EOT, on=who)
        rough = self.ignores_difficult(on=who, until=When.EOT)
        try:
            return self.move(squares_, who=who)
        finally:
            for held in (over, rough):
                if held is not None:
                    self.world.effects.end(held, "the jump ended")

    # -- a blow that lands twice ---------------------------------------------

    def also_hits(self, *, on: int | None = None, ev: Any = None) -> bool:
        """"The triggering attack also hits the target."

        Not `c.redirect`, which moves the one blow, and not `c.autohit`,
        which forces the one being answered: this copies a blow that has
        already landed onto a second creature. The damage has not been
        rolled when the `Hit` is announced, so the copy is taken off the
        next roll that attack makes and dealt again, of the same type --
        re-running the row would be a different attack with a different die.
        """
        from .events import DamageRolled

        who = self._who(on)
        ev = ev if ev is not None else self.trigger
        attacker = getattr(ev, "attacker", None)
        power = getattr(ev, "power", "")
        if who is None or attacker is None:
            return False
        done: list[bool] = []

        def echo(rolled: DamageRolled) -> None:
            if done or rolled.source != attacker or rolled.detail != power:
                return
            done.append(True)
            self.flat(rolled.amount, dtype=rolled.dtype, on=who)

        self.watch(
            DamageRolled, echo, until=When.EOT, on=self.me,
            label=f"{self.ref} also hits",
        )
        return True

    # -- skill checks, and the three resources a character spends ------------

    def check(self, skill: str, dc: int = 0, *, who: int | None = None, bonus: int = 0):  # noqa: ANN201
        """Roll a skill check. Truthy when it beat the DC.

        `who` is who rolls, and it defaults to the **caster**: it is your
        check. One printed line hands the roll to somebody else -- "any
        character can make a DC 25 History check" -- and that is what `who`
        is for; it is not `on=`, because nothing is being done *to* anybody.

        The result carries `.total` as well, for the one shape that halves
        the number instead of comparing it. A `dc` of 0 is a check with
        nothing to beat and always succeeds.

        Training is not modelled -- see `engine/skills.py` -- so this is the
        ability modifier plus half level plus whatever modifiers stand.
        """
        from .skills import check as _check

        roller = self.me if who is None else who
        return _check(self.world, roller, skill, dc, bonus=bonus)

    def passive(self, skill: str, *, of: int | None = None) -> int:
        """10 plus a creature's check modifier -- what it notices unbidden.

        Defaults to the **caster**. A row going unseen needs a number to
        beat and the alternative was inventing a DC.
        """
        from .skills import passive as _passive

        return _passive(self.world, self.me if of is None else of, skill)

    def boost_check(self, bonus: int) -> bool:
        """Add to the triggering skill check, after the die is already down.

        For "Trigger: you fail a skill check" -- the failure is what is
        being answered, so the bonus cannot be laid as a modifier before the
        roll the way `p11049` lays one. `skills.check` builds its result from
        the event **after** the bus has finished with it, so a row answering
        in the after-window still decides what the check came to.

        Returns False when there is no check to change, which is every use
        outside a `SkillCheck` trigger.
        """
        from .events import SkillCheck

        ev = self.trigger
        if not isinstance(ev, SkillCheck):
            return False
        ev.bonus += bonus
        ev.total = ev.natural + ev.bonus
        ev.success = ev.dc <= 0 or ev.total >= ev.dc
        return True

    def reroll_check(self, *, keep: str = "new", bonus: int = 0) -> int:
        """Roll the triggering skill check again. `keep` is new, best or worst.

        The skill-check twin of `c.reroll_attack`, and six rows print it.
        Returns the **face of the second die**, or 0 if there was no check to
        reroll: one card pays the use back when the second roll is the worse
        of the two, and that cannot be read off the settled event.

        `bonus` is for "reroll it with a power bonus equal to your Wisdom
        modifier", which is one printed clause with the reroll.
        """
        from .events import SkillCheck

        ev = self.trigger
        if not isinstance(ev, SkillCheck):
            return 0
        fresh = self.world.rng.d20().total
        old = ev.natural
        ev.natural = {"new": fresh, "best": max(old, fresh), "worst": min(old, fresh)}[
            keep
        ]
        self.boost_check(bonus)
        return fresh

    # -- action points -------------------------------------------------------

    def _points(self, who: int) -> Any:
        from .components import ActionPoints

        return self.world.get(who, ActionPoints) or self.world.add(who, ActionPoints())

    def action_points(self, *, of: int | None = None) -> int:
        """How many action points this creature could spend right now."""
        return self._points(self.me if of is None else of).available

    def action_point(
        self, cost: ActionType = ActionType.STANDARD, *, who: int | None = None
    ) -> bool:
        """Spend an action point for an extra action. Yours, so it defaults
        to the caster.

        A granted point -- one that does not count against the encounter
        limit -- is spent first, because that is the only order in which
        both limits can be honoured. The round is stamped so that
        `resolve.attack` can say an attack was bought with it.
        """
        from .events import ActionPointSpent

        spender = self.me if who is None else who
        pool = self._points(spender)
        free = pool.free > 0
        if not free and (pool.points <= 0 or pool.spent >= pool.limit):
            return False
        if free:
            pool.free -= 1
        else:
            pool.points -= 1
            pool.spent += 1
        pool.spent_round = self.world.round
        self.extra_action(cost, on=spender)
        self.world.bus.emit(ActionPointSpent(actor=spender, cost=cost, free=free))
        return True

    def grant_action_point(self, count: int = 1, *, on: int | None = None) -> int:
        """"The target gains 1 action point", outside the encounter's limit.

        Theirs, so it follows `c.target`. Granted points are cleared by
        `ActionPoints.refresh`, which is the printed "if the target does not
        spend it before the end of the encounter, it is lost".
        """
        who = self._who(on)
        if who is None or count <= 0:
            return 0
        pool = self._points(who)
        pool.free += count
        self.world.bus.emit(
            Note(text=f"{who} gains {count} action point(s) outside the limit")
        )
        return pool.free

    # -- power points --------------------------------------------------------

    def _pool(self, who: int) -> Any:
        from .components import PowerPoints

        return self.world.get(who, PowerPoints) or self.world.add(who, PowerPoints())

    def points(self, *, of: int | None = None) -> int:
        """How many power points this creature has left."""
        return self._pool(self.me if of is None else of).points

    def spend_points(self, n: int, *, who: int | None = None) -> int:
        """Spend power points to augment this row. Returns how many went.

        Yours, so it defaults to the caster. The number is recorded against
        the row's own ref, which is what "temporary hit points equal to the
        power points you spent to augment that power" reads back: the spend
        and the hit are separate moments and nothing else joins them.
        """
        spender = self.me if who is None else who
        pool = self._pool(spender)
        gone = pool.spend(n)
        if gone:
            pool.augmented[self.ref] = pool.augmented.get(self.ref, 0) + gone
            self.world.bus.emit(
                Note(text=f"{spender} spends {gone} power point(s) on {self.ref}")
            )
        return gone

    def points_spent(self, ref: str, *, of: int | None = None) -> int:
        """How many points augmented that row this encounter."""
        return self._pool(self.me if of is None else of).augmented.get(ref, 0)

    def augmented(self, ref: str, *, of: int | None = None) -> int:
        """What bought the **latest** use of that row. 0 for an unaugmented one.

        "When you augment <row>, ..." is a rider on somebody else's card and
        has to be able to tell this use from the last, which
        `c.points_spent` cannot: that is the encounter's running total, so
        once a row has been augmented it reads as augmented for the rest of
        the fight. Recorded by `dsl.use` above the body, so a watcher on
        `PowerUsed` -- which is announced there too -- already has the
        answer.

        Only rows that declare `augments=` in the header are recorded. One
        whose augments live in the body settles them after `PowerUsed` has
        gone out and there is nothing to read at that moment.
        """
        return self._pool(self.me if of is None else of).last.get(ref, 0)

    def transfer_points(self, n: int, *, on: int | None = None) -> int:
        """"You transfer 1 or 2 power points to the target."

        Theirs, so it follows `c.target`. The receiver gets a pool if it
        had none: the printed line does not ask whether the ally is psionic,
        and a transferred point is over the receiver's own maximum, which
        `refresh` takes back at the end of the fight.
        """
        who = self._who(on)
        if who is None or who == self.me or n <= 0:
            return 0
        mine = self._pool(self.me)
        gone = mine.spend(n)
        if not gone:
            return 0
        theirs = self._pool(who)
        theirs.points += gone
        self.world.bus.emit(
            Note(text=f"{self.me} transfers {gone} power point(s) to {who}")
        )
        return gone

    # -- the spellbook -------------------------------------------------------

    def spellbook(self, *, of: int | None = None) -> list[str]:
        """The rows this creature owns and has not prepared."""
        from .components import Powers

        known = self.world.get(self.me if of is None else of, Powers)
        return list(known.owned) if known is not None else []

    def prepare(self, ref: str, *, instead_of: str = "", on: int | None = None) -> bool:
        """Prepare a row out of the spellbook, putting one back if it swaps.

        Yours, so it defaults to the **caster**: it is your book. Returns
        False when the row is not in the book, which is what a printed
        "another power of the same level that is in your spellbook" means
        when there is not one.
        """
        from .components import Powers

        who = self.me if on is None else on
        known = self.world.get(who, Powers)
        if known is None or not known.prepare(ref, instead_of=instead_of):
            return False
        self.world.bus.emit(
            Note(text=f"{who} prepares {ref}" + (f" instead of {instead_of}" if instead_of else ""))
        )
        return True

    # -- a companion that rolls its own line ---------------------------------

    def b(self, count: int = 1) -> str:
        """`count`[B]: the **companion's** damage dice, that many times.

        `c.w` for a beast. Read in the order the numbers can actually come
        from: the die the companion was called with, then a `summon=` block
        on this row's header, then the same `d4` `c.w` gives a creature with
        nothing in its hands. The last is the honest answer today -- the
        printed die belongs to a species the engine does not model, and no
        card in this batch states one -- and it is a fallback rather than an
        invention: give the beast a die and every row here rolls it.
        """
        from .components import Companion

        # Asked *of the beast itself* -- its own basic attack is a row it
        # uses, so `self.me` is the companion and it owns none. Without this
        # the beast rolled the d4 fallback while its block printed 1d8.
        pet = self.companion() or (
            self.me if self.world.get(self.me, Companion) is not None else None
        )
        die = ""
        if pet is not None:
            mine = self.world.get(pet, Companion)
            die = mine.damage if mine is not None else ""
        if not die:
            spec = getattr(self._declared(), "summon", None)
            if spec is not None and spec.damage is not None:
                die = spec.damage.dice
        if not die:
            return f"{count}d4"
        n, _, faces = die.partition("d")
        return f"{int(n or 1) * count}d{faces}"

    def b_mod(self, a: Ability | None = None) -> int:
        """"Beast's Strength modifier" -- the companion's own, not its owner's.

        With no ability named it is the one the companion's *own* damage
        line adds, which its block prints and three of the eight categories
        print as Dexterity.

        Falls back to the caster's, because a ref-less companion is built
        with a copy of its owner's scores and the two are then the same
        number; the point is that the row asks the right creature.
        """
        from .components import Companion, Stats

        pet = self.companion() or (
            self.me if self.world.get(self.me, Companion) is not None else None
        )
        if a is None:
            mine = self.world.get(pet, Companion) if pet is not None else None
            a = Ability(mine.ability) if mine is not None else Ability.STR
        stats = self.world.get(pet, Stats) if pet is not None else None
        return stats.mod(a) if stats is not None else self.stats.mod(a)

    # -- what a creature is holding -------------------------------------------

    def held(self, *, on: int | None = None, what: str = "") -> list[Weapon]:
        """What that creature has in hand. `what` is `"magic"` or a group."""
        from .query import holding

        who = self._who(on)
        return holding(self.world, who, what) if who is not None else []

    def weapon_of(self, ev: Any = None) -> Weapon | None:
        """Which weapon the attack behind this event was swung with.

        `c.struck_with` answers a looser question -- it prefers whatever
        magic thing the attacker is holding, which is right for "an attack
        using this ki focus" and wrong for a coated blade: a poison is on
        one weapon and the other must not carry it. This one picks the way
        the attack itself did, off the reach of the row that made it.
        """
        from .dsl import get

        ev = ev if ev is not None else self.trigger
        attacker = getattr(ev, "attacker", None) if ev is not None else None
        gear = self.world.get(attacker, Gear) if attacker is not None else None
        if gear is None:
            return None
        p = get(getattr(ev, "power", "") or "")
        fired = p is not None and p.reach.kind == "ranged"
        return gear.ranged if fired and gear.ranged else gear.main

    def ammunition(self, ev: Any = None) -> bool:
        """Was that shot fired from the ammunition **this row belongs to**?

        The question every ammunition property asks and none could. The
        item is found the way `c.enhancement` finds it -- off this row's
        own ref -- so a wielder carrying two kinds of magic arrow has each
        property answering its own shots and neither answering the other's.

        `resolve.attack` draws and spends one piece as the shot is
        declared and writes the item's ref onto all four attack events, so
        this is exact for an `AttackDeclared` answered in the before
        window as well as for the `Hit`.

        False when the quiver is empty, which is the point: the property
        stops paying out, rather than riding every shot for the rest of
        the fight.
        """
        from .ammunition import fired_with

        return fired_with(
            ev if ev is not None else self.trigger,
            self.ref.split("x")[0].split("p")[0],
        )

    def apply_poison(
        self,
        bite: Callable[[Any], None],
        *,
        weapon: Weapon | None = None,
        groups: Sequence[str] = (),
        until: When = When.ENCOUNTER,
        once: bool = True,
    ) -> Effect | None:
        """Coat a weapon in hand. `bite(ev)` runs on the next hit with it.

        The printed line is "apply the poison to your weapon or one piece
        of ammunition, and the next creature you hit with the coated item
        takes...". The card offers the wielder a choice of two and this
        takes the weapon, which is one of the printed answers rather than
        an approximation of both. Coating a *piece* of ammunition is now
        sayable -- `Gear.quiver` holds them and `c.ammunition` reads which
        shot came from which -- and is not done here, because the hold
        below is keyed on a `Weapon` and the choice would be between two
        different kinds of thing.

        What was missing was the tie. Every one of these rows was written
        as a bare `c.watch(Hit, ...)`, so the poison rode whichever weapon
        the wielder happened to swing next -- a ranger who coated a blade
        and then shot somebody got the poison for free off the bow. The
        hold now names the weapon and `c.weapon_of` checks the blow.

        `groups` narrows what may be coated to the printed list of weapon
        groups; `once=False` is the "five pieces of ammunition" printing,
        which is every hit for the rest of the fight rather than one.

        Returns the hold, so a row can end it early with `c.end_effect`, or
        None when there is nothing in hand to coat.
        """
        from .events import Hit

        coated = weapon
        if coated is None:
            # `c.held` follows `c.target`, and the wielder is the caster.
            pool = [
                w for w in self.held(on=self.me) if not groups or w.group in groups
            ]
            coated = self.choose(pool, f"{self.ref}: what to coat")
        if coated is None:
            return None

        def struck(ev: Any) -> None:
            if ev.attacker != self.me or self.weapon_of(ev) is not coated:
                return
            bite(ev)

        return self.watch(
            Hit, struck, until=until, once=once,
            label=f"{self.ref} coated {coated.ref}",
        )

    def deals(
        self,
        dtype: DamageType,
        *,
        until: When = When.ENCOUNTER,
        on: int | None = None,
        implement: bool = False,
    ) -> Effect | None:
        """This creature's weapon attacks deal that type from now on.

        The printed line is "all damage dealt by this weapon is fire
        damage", and it is an *override*, not an addition -- which is why
        it beats the type the power named rather than stacking beside it.
        For a long while the code was narrower than this paragraph:
        `_typed` recoloured a blow only when the card had named no type,
        so "**all** damage" quietly meant "the untyped part", and every
        item block printing the line got the smaller thing. The docstring
        was the correct half and the code now matches it.

        `implement=True` for the symbol and staff version of the same
        sentence, "all damage dealt by powers using this implement".
        Without it the override speaks only for `Keyword.WEAPON` rows,
        which is what the weapon cards say and is silently false for
        every implement one.

        Held as a labelled effect rather than written onto the `Weapon`,
        because the weapon object is the character's and the change is
        usually for a fight. Yours, so it defaults to the caster.
        """
        who = on if on is not None else self.me
        for eff in list(self.world.effects.of(who)):
            if eff.label.startswith("deals:"):
                self.world.effects.end(eff, "deals another type now")
        through = Keyword.IMPLEMENT if implement else Keyword.WEAPON
        return self.world.effects.apply(
            who, self.me, until, label=f"deals:{dtype.value}:{through.value}"
        )

    def _typed(self, dtype: DamageType) -> DamageType:
        """The type this blow really is.

        Two different sentences meet here and they are not equally loud.
        A weapon *made* of something -- a silvered blade -- only says what
        an attack that named no type comes out as, so it fills `UNTYPED`
        and stops. A card saying "all damage dealt by this weapon is fire"
        is an override and beats the type the power printed.

        Both speak only for a row that used the thing: a wizard's fire
        spell is not the sword's business. `c.deals(implement=True)` is
        the other half of that gate, for the cards that retype what a
        symbol casts.
        """
        p = self._declared()
        # `None` is a blow with no row behind it -- a hazard, a fall. It
        # has no keywords to fail the gate with, so it is not gated.
        keywords = p.keywords if p is not None else None
        retype = self._retyped(keywords)
        if retype is not None:
            return retype
        if dtype is not DamageType.UNTYPED:
            return dtype
        if keywords is not None and Keyword.WEAPON not in keywords:
            return dtype
        return self._weapon_dtype() or dtype

    def _retyped(self, keywords: Sequence[Keyword] | None) -> DamageType | None:
        """The override a `c.deals` laid down, if it covers this row.

        Separate from `_weapon_dtype` because the two halves of that
        method were one lookup doing opposite jobs: this one wins over a
        printed type and the gear below it does not.

        One that does not cover this row is **skipped, not the end of the
        search**. `deals` ends any standing retype before it lays a new
        one, so only one can be held today and the difference cannot show
        -- but the day a weapon retype and an implement retype stand at
        once, returning on the first miss would silence whichever the
        effect list happened not to yield first.
        """
        for eff in self.world.effects.of(self.me):
            if not eff.label.startswith("deals:"):
                continue
            _, _, rest = eff.label.partition(":")
            said, _, through = rest.partition(":")
            if through and keywords is not None and Keyword(through) not in keywords:
                continue
            return DamageType(said)
        return None

    def _weapon_dtype(self) -> DamageType | None:
        """What a blow from the thing in hand comes out as.

        Resolved here and **not** on a `DamageRolled` listener, and the
        ordering is the whole point: `resolve.deal_damage` sums the damage
        modifiers against `dmg_ctx["dtype"]` before it emits. A type set
        after that emit changes resistance and the log and nothing else, so
        "my weapon deals fire" and "+1 damage with fire powers" would
        disagree about the same blow.
        """
        gear = self.world.get(self.me, Gear)
        if gear is None:
            return None
        weapon = gear.ranged if self.ranged and gear.ranged else gear.main
        return weapon.dtype if weapon is not None else None

    def _enhancement(self) -> int:
        """What a magic weapon or implement adds to the damage it deals.

        **Not gated on `Keyword.WEAPON`**, which is what it used to be and
        which silently threw away every implement's bonus -- see
        `_attack_bonus`, where the same one test was answering two
        questions. The two sides of a magic item's "attack rolls and damage
        rolls" have to agree, and for the whole of this project they did
        agree, on zero.
        """
        return self._enhancement_of(self._declared())

    def struck_with(self, ev: Any = None) -> Weapon | None:
        """The weapon or implement the triggering attack was made with."""
        ev = ev if ev is not None else self.trigger
        attacker = getattr(ev, "attacker", None) if ev is not None else None
        if attacker is None:
            return None
        magic = self.held(on=attacker, what="magic")
        if magic:
            return magic[0]
        gear = self.world.get(attacker, Gear)
        return gear.main if gear is not None else None

    def decay(
        self,
        *,
        on: int | None = None,
        amount: int = 1,
        until: When = When.ENCOUNTER,
        weapon: Weapon | None = None,
    ) -> Effect | None:
        """Take an item's enhancement bonus down, to a minimum of 0.

        An effect an item carries: the number goes back up when the hold
        ends, which is the printed "the enhancement bonus returns to normal
        at the end of the encounter". Hung on the creature holding it, so
        the item and the hold die together if the creature drops it.
        """
        who = self._who(on)
        if who is None:
            return None
        arm = weapon or next(iter(self.held(on=who, what="magic")), None)
        if arm is None:
            return None
        gone = min(amount, arm.enhancement)
        if gone <= 0:
            return None
        arm.enhancement -= gone

        def restore() -> None:
            arm.enhancement += gone

        self.world.bus.emit(
            Note(text=f"{arm.ref} is decaying: enhancement {arm.enhancement}")
        )
        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} decays {arm.ref}", on_end=[restore]
        )

    def destroy(self, *, on: int | None = None, weapon: Weapon | None = None) -> bool:
        """Destroy an item a creature is carrying. It does not come back."""
        who = self._who(on)
        gear = self.world.get(who, Gear) if who is not None else None
        if gear is None:
            return False
        arm = weapon or next(iter(self.held(on=who, what="magic")), None)
        if arm is None or arm not in gear.weapons:
            return False
        gear.weapons.remove(arm)
        gear.stowed.discard(arm.ref)
        self.world.bus.emit(Note(text=f"{arm.ref} is destroyed"))
        return True

    def disarm(self, *, on: int | None = None, weapon: Weapon | None = None) -> bool:
        """Knock a weapon out of a hand. It lands in that creature's square.

        Not stowed: a stowed weapon is on the belt and can be drawn again for
        a minor action, and the printed line puts this one on the floor.
        """
        from .components import Item, Position

        who = self._who(on)
        gear = self.world.get(who, Gear) if who is not None else None
        if gear is None:
            return False
        arm = weapon or gear.main
        if arm is None or arm not in gear.weapons:
            return False
        gear.weapons.remove(arm)
        gear.stowed.discard(arm.ref)
        here = self.world.get(who, Position)
        parts: list[Any] = [Item(ref=arm.ref, owner=0, by=self.me, uses=0, weapon=arm)]
        if here is not None:
            parts.append(Position(square=here.square))
        self.world.spawn(*parts)
        self.world.bus.emit(Note(text=f"{who} drops {arm.ref}"))
        return True

    def give(
        self,
        ref: str = "",
        fn: Callable[[int], None] | None = None,
        *,
        on: int | None = None,
        uses: int = 1,
        cost: ActionType = ActionType.MINOR,
    ) -> int:
        """Put a one-shot in somebody's hands for them to spend later.

        The seed, the scroll, the four berries: the creature that spends it
        is not the creature that made it, and the payout is printed on the
        maker's row with the maker's numbers. `c.grant_row` cannot say that
        -- it needs a row that already exists and it has no charges -- so
        `fn` is the payout, handed whoever spent it, and it closes over this
        caster. `actions.legal` offers spending it to whoever is carrying it.
        """
        from .components import Item

        who = self._who(on)
        if who is None:
            return 0
        label = ref or self.ref
        if fn is None and ref:
            def fn(spender: int, _ref: str = ref) -> None:
                from .dsl import use

                use(self.world, spender, _ref, targets=[spender], spend=False)

        item = self.world.spawn(
            Item(
                ref=label, owner=who, by=self.me, uses=uses, spend=fn, cost=cost.value
            )
        )
        self.world.bus.emit(Note(text=f"{who} carries {label} ({uses} left)"))
        return item

    def carrying(self, ref: str = "", *, on: int | None = None) -> list[int]:
        """The items that creature is holding, by entity id."""
        from .components import Item

        who = self._who(on)
        return [
            eid
            for eid, item in sorted(self.world.each(Item))
            if item.owner == who and item.uses > 0 and (not ref or item.ref == ref)
        ]

    # -- a wall -----------------------------------------------------------

    def link(
        self,
        a: Square,
        b: Square,
        *,
        until: When = When.EONT,
        sustain: ActionType | None = None,
    ) -> Effect | None:
        """Two squares a mover crosses between in one step.

        **Movement only.** `Grid.links` is read by `movement.reachable` and
        by nothing else, so a creature can walk from one end to the other
        and nothing measures a melee reach, a burst or a line of effect
        through it -- which is exactly what the one printed rift that says
        "for movement only" asks for, and only half of what a row saying
        "and for making melee attacks" would need.
        """
        links = self.world.grid.links
        if a == b:
            return None
        links[a] = links.get(a, frozenset()) | {b}
        links[b] = links.get(b, frozenset()) | {a}

        def close() -> None:
            for here, there in ((a, b), (b, a)):
                rest = links.get(here, frozenset()) - {there}
                if rest:
                    links[here] = rest
                else:
                    links.pop(here, None)

        return self.world.effects.apply(
            self.me,
            self.me,
            until,
            label=f"{self.ref} link",
            sustain_cost=sustain if until is When.SUSTAIN else None,
            on_end=[close],
        )

    def wall(
        self,
        size: int = 0,
        *,
        at: Square | None = None,
        hp: int = 0,
        blocks_sight: bool = False,
        solid: bool = True,
        difficult: bool | str = False,
        until: When = When.EONT,
        sustain: ActionType | None = None,
        label: str = "",
    ) -> int:
        """Raise a barrier: `size` contiguous squares that stop a creature.

        Three things at once, and a zone is only one of them. The squares go
        into `Grid.blocking`, which is what stops movement and line of
        effect; a `Zone` is laid over the same squares, which is what a
        printed "while within the wall" clause reads; and with `hp` a
        `Barrier` entity stands there too, so the wall can be attacked. All
        three come down together, and only the squares this row added are
        taken back out, so a wall raised across existing rock leaves it.

        Returns the zone, because that is what the rest of `Cast` takes --
        `c.grants_in`, `c.burns`, `c.cover_in`, `c.resist_in`.
        """
        from .components import Barrier, Defenses, Ident, Position, Side
        from .events import Dropped, ZoneEnded
        from .query import team as side_of

        p = self._declared()
        reach = p.reach_of(self.branch) if p is not None else None
        size = size or (reach.size if reach is not None else 5)
        within = reach.within if reach is not None else 10
        grid = self.world.grid
        # Offered nearest-the-trouble first rather than in raster order: a
        # decider that takes the head of the list put every wall in the
        # bottom-left corner of the board, where it blocked nothing.
        foes = [sq for foe in self.enemies() for sq in squares(self.world, foe)]
        spots = sorted(
            (
                sq
                for sq in spread({self.here}, within)
                if grid.passable(sq) and grid.occupant(sq) is None and sq != self.here
            ),
            key=lambda sq: (
                min((_distance(sq, f) for f in foes), default=0),
                _distance(sq, self.here),
                sq,
            ),
        )
        anchor = at or (
            self.choose(spots, f"{self.ref}: where the wall stands") if spots else None
        )
        if anchor is None:
            return 0
        # Laid across the line of sight to the anchor, which is the way a
        # wall is meant to be used and the way `p16283` already lays one.
        across, along = anchor[0] - self.here[0], anchor[1] - self.here[1]
        step = (1, 0) if abs(along) >= abs(across) else (0, 1)
        low = -(size // 2)
        run = [(anchor[0] + step[0] * i, anchor[1] + step[1] * i)
               for i in range(low, low + size)]
        laid = [sq for sq in run if grid.passable(sq) and grid.occupant(sq) is None]
        if not laid:
            return 0
        # `solid=False` is the wall you can get through -- one printed wall
        # is water and says "a creature must swim to move through it". It
        # still stands between an attacker and a target, which is what
        # `blocks_sight` gives it.
        if solid:
            grid.blocking.update(laid)
        zone = self.zone(
            laid, label=label or self.ref, until=until,
            blocks_sight=blocks_sight, difficult=difficult, sustain=sustain,
        )
        standing: list[int] = []
        if hp:
            barrier = self.world.spawn(
                Position(square=min(laid), spans=frozenset(laid)),
                Side(team=side_of(self.world, self.me) or Team.ALLY),
                Health(hp=hp, max_hp=hp),
                # "Attacks against it hit automatically", which is a defence
                # of nothing rather than a special case in the attack.
                Defenses(values=dict.fromkeys(Defense, 0), scale="none"),
                Barrier(by=self.me, squares=frozenset(laid), zone=zone),
                Ident(ref=f"{self.ref}:wall"),
            )
            standing.append(barrier)
            self.world.bus.on(
                Dropped,
                lambda ev: self.world.zones.end(zone, "the wall is broken")
                if ev.actor == barrier else None,
                owner=barrier,
            )

        def demolish(ev: ZoneEnded) -> None:
            if ev.zone != zone:
                return
            if solid:
                grid.blocking.difference_update(laid)
            for eid in standing:
                self.world.despawn(eid)

        # Hung on `ZoneEnded` rather than on the zone's effect: `Zones.end`
        # clears `effect.on_end` before ending it, so a callback appended
        # there is dropped whenever a zone is ended early -- and a wall
        # knocked down by an attack is exactly that. The squares stayed
        # blocking with nothing standing in them.
        self.world.bus.on(ZoneEnded, demolish, owner=zone)
        return zone

    def barrier(self, zone: int) -> int | None:
        """The attackable body of a wall, given the zone `c.wall` returned."""
        from .components import Barrier

        for eid, wall in sorted(self.world.each(Barrier)):
            if wall.zone == zone:
                return eid
        return None

    # -- up and down --------------------------------------------------------

    def height(self, *, on: int | None = None) -> int:
        """How far off the ground that creature is. Defaults to the caster."""
        from .falling import height

        return height(self.world, on if on is not None else self.me)

    def rise(self, squares_: int, *, on: int | None = None) -> int:
        """Go up, and stay there. Yours, so it defaults to the caster."""
        from .falling import lift

        return lift(self.world, on if on is not None else self.me, squares_)

    def hover(
        self,
        squares_: int = 0,
        *,
        on: int | None = None,
        until: When = When.EONT,
        sustain: ActionType | None = None,
    ) -> Effect | None:
        """Go up and stay up. Yours, so it defaults to the caster.

        Two things at once, and the second is what makes it work: the
        creature is lifted, and it is *moving as* something airborne, which
        is what keeps `falling.ground` from putting it straight back down on
        its next step. When the hold ends it descends without taking falling
        damage, which is the printed line on the one row that levitates.
        """
        from .components import Movement

        who = on if on is not None else self.me
        mv = self.world.get(who, Movement)
        if mv is None:
            return None
        was = mv.using
        if squares_:
            self.rise(squares_, on=who)
        mv.using = "hover"

        def land() -> None:
            mv.using = was
            self.fall(on=who, safe=True)

        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} aloft",
            on_end=[land], sustain_cost=sustain,
        )

    def fall(self, squares_: int = 0, *, on: int | None = None, safe: bool = False) -> int:
        """Come down, with everything that costs. Follows `c.target`.

        `squares_` defaults to however high the creature is. `safe` is the
        printed "you descend without taking falling damage", which announces
        no `Fell` because nothing is going wrong.
        """
        from .falling import drop

        who = self._who(on)
        if who is None:
            return 0
        return drop(self.world, who, squares_, by=self.me, safe=safe)

    def cushion(self, amount: int = 0) -> bool:
        """Soften the fall being answered. With no number, all of it.

        "The target takes no damage from the fall, and consequently does not
        fall prone" is one sentence and both halves are this. A number is
        the other printing -- "reduce the damage by 5 + half your level".
        """
        from .events import Fell

        ev = self.trigger
        if not isinstance(ev, Fell):
            return False
        if amount > 0:
            ev.soften += amount
        else:
            ev.soften += 10 * max(1, ev.squares)
            ev.prone = False
        return True

    def made_by(self, thing: int) -> int | None:
        """Whoever put that zone or conjuration on the board."""
        from .components import Conjuration
        from .zones import Zone

        zone = self.world.get(thing, Zone)
        if zone is not None:
            return zone.owner
        conj = self.world.get(thing, Conjuration)
        return conj.by if conj is not None else None

    def conjurations(self, *, within: int = 0, side: str = "any") -> list[int]:
        """The zones, auras and conjurations standing on the board.

        What `c.scenery` is for the things the room came with. `c.my_zones`
        asks the same question about your own; this is the pool a target
        line reading "one conjuration or zone" picks from, and it can see
        everybody's. `within` measures from the caster's space to the
        nearest square of the thing, 0 being anywhere.
        """
        from .components import Conjuration
        from .grid import between
        from .query import team
        from .zones import Zone

        mine = team(self.world, self.me)
        here = squares(self.world, self.me) or frozenset({self.here})
        out: list[int] = []
        for eid in list(self.world.having(Zone)) + list(self.world.having(Conjuration)):
            if eid in out:
                continue
            zone = self.world.get(eid, Zone)
            area = zone.squares if zone is not None else squares(self.world, eid)
            if within and between(here, area) > within:
                continue
            owner = self.made_by(eid)
            theirs = team(self.world, owner) if owner is not None else None
            if side == "enemy" and (theirs is None or theirs is mine):
                continue
            if side == "ally" and theirs is not mine:
                continue
            if side == "other" and owner == self.me:
                continue
            out.append(eid)
        return out

    def dispel(self, thing: int) -> bool:
        """Destroy a zone or a conjuration, and unwind what it was holding.

        "All its effects end, including those a save can end" is the half
        `Zones.end` does not do: a hold a zone laid on a creature lives on
        that creature and outlives the zone. Nothing records which effect
        came from which zone, so they are found by the label their maker
        stamped them with -- a zone's label is the ref of the row that made
        it, and every hold that row applied wears the same ref.
        """
        from .components import Conjuration
        from .zones import Zone

        zone = self.world.get(thing, Zone)
        conj = self.world.get(thing, Conjuration)
        if zone is None and conj is None:
            return False
        name = zone.label if zone is not None else conj.ref
        maker = self.made_by(thing)
        why = f"{self.ref} dispelled it"
        for eff in list(self.world.effects.live.values()):
            if eff.ended or eff.source != maker:
                continue
            if eff.label in (name, f"zone {name}") or eff.label.startswith(f"{name} "):
                self.world.effects.end(eff, why)
        if self.world.get(thing, Zone) is not None:
            self.world.zones.end(thing, why)
        elif self.world.get(thing, Position) is not None:
            self.world.despawn(thing)
        return True

    def terraform(
        self, square: Square | None = None, *, raise_: int = 0, sink: int = 0
    ) -> bool:
        """Push one square of ground up, or pull it down.

        Raised with nobody on it, it is a pillar: blocking terrain, which is
        the printed "the area below it is filled with solid rock". Raised
        with somebody standing there, they ride up and are then that far off
        the ground -- stepping off is a fall. Sunk, its floor is below the
        rest of the board and walking in is a fall of the same depth.
        """
        from .falling import lift

        sq = square or self.there or self.here
        grid = self.world.grid
        rider = grid.occupant(sq)
        if rider is not None and self.may("shift clear of it", who=rider):
            self.shift(1, who=rider)
            rider = grid.occupant(sq)
        if raise_:
            grid.elevation[sq] = raise_
            if rider is None:
                grid.blocking.add(sq)
            else:
                lift(self.world, rider, raise_)
        elif sink:
            grid.elevation[sq] = -sink
            if rider is not None:
                self.fall(sink, on=rider)
        else:
            return False
        self.world.bus.emit(
            Note(text=f"{sq} is now at {grid.floor(sq)} squares")
        )
        return True


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
