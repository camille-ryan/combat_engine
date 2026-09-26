"""The components a creature, a zone or a conjuration is made of.

No display names anywhere. `Ident.ref` is a compendium id like `m145` or
`p289`, and `Ident.tag` distinguishes the second goblin from the first. A
player sees a name because the API looks one up at the boundary; the engine
never holds one.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .grid import Square, footprint
from .types import Ability, Condition, DamageType, Defense, Size, Team, modifier

# --------------------------------------------------------------------------
# Identity and placement
# --------------------------------------------------------------------------


@dataclass
class Ident:
    ref: str
    tag: str = ""
    #: Which book this row's numbers were printed under: MM1, MM2, MM3, or
    #: empty for a character. `monster_math` needs it to know what it is
    #: converting *from*.
    book: str = ""

    def __str__(self) -> str:
        return f"{self.ref}{('#' + self.tag) if self.tag else ''}"


@dataclass
class Position:
    square: Square
    size: Size = Size.MEDIUM
    #: An explicit footprint, for a thing that is not a square block. A wall
    #: is five squares in a row and no `Size` describes that, so `footprint`
    #: cannot be asked -- and everything that measures to a thing, from
    #: adjacency to targeting, goes through `squares`.
    spans: frozenset[Square] = frozenset()
    #: How far off the ground, in squares. 0 is standing on the floor, which
    #: is everybody until something lifts them -- see `engine/falling.py`.
    height: int = 0

    @property
    def squares(self) -> frozenset[Square]:
        return self.spans or footprint(self.square, self.size)


@dataclass
class Side:
    team: Team


# --------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------


@dataclass
class Stats:
    level: int = 1
    scores: dict[Ability, int] = field(default_factory=dict)

    def score(self, a: Ability) -> int:
        return self.scores.get(a, 10)

    def mod(self, a: Ability) -> int:
        return modifier(self.score(a))

    @property
    def half_level(self) -> int:
        return self.level // 2


@dataclass
class Defenses:
    """Defences **without** their level term. See `engine/scaling.py`.

    `scale` says which way the level term goes: a character's sheet is built
    up from parts and has it added, a stat block is printed as a total and
    had it taken out when the monster was loaded.
    """

    values: dict[Defense, int] = field(default_factory=dict)
    scale: str = "pc"  # pc | monster | none

    def base(self, d: Defense) -> int:
        return self.values.get(d, 10)


@dataclass
class Health:
    max_hp: int
    hp: int = 0
    temp: int = 0
    surges: int = 0
    #: Failed death saves. Three and the creature is dead.
    failures: int = 0

    def __post_init__(self) -> None:
        if self.hp == 0:
            self.hp = self.max_hp

    @property
    def bloodied(self) -> bool:
        return self.hp <= self.max_hp // 2

    @property
    def surge_value(self) -> int:
        return self.max_hp // 4

    @property
    def dying_at(self) -> int:
        """Below this and the creature is dead outright."""
        return -(self.max_hp // 2)


@dataclass
class Movement:
    speed: int = 6
    #: Extra modes and their speeds, e.g. {"fly": 8, "climb": 3}.
    modes: dict[str, int] = field(default_factory=dict)
    #: Kinds of difficult terrain this creature crosses for nothing, by the
    #: label `Grid.difficult` gives them. `"*"` is all of it.
    ignores: set[str] = field(default_factory=set)
    #: How the creature is moving **right now**, or "" between moves.
    #:
    #: `modes` says what it *can* do and never what it *is* doing, so
    #: "Requirement: must be climbing" and "while it is not flying" could not
    #: be written at all -- a gate on `modes` is true whenever the creature
    #: has the speed, which is not the printed sentence. Four rows across two
    #: waves asked for this.
    using: str = ""


@dataclass
class Defences:
    """Damage the creature shrugs off or takes worse, by type."""

    resist: dict[DamageType, int] = field(default_factory=dict)
    vulnerable: dict[DamageType, int] = field(default_factory=dict)
    immune: set[DamageType] = field(default_factory=set)


@dataclass
class Trap:
    """Marks an entity as a hazard rather than a creature.

    A trap has a `Position` and attacks like anything else, but no `Health`
    and no `Side` -- which is what keeps it out of `query.creatures`, so it
    takes no turn, holds no initiative slot, and grants nobody cover. The
    component exists mainly so a power can *ask*: several rows give a bonus
    to defences "against traps", and until something on the board could be
    one, that sentence had no subject.
    """

    ref: str = ""
    #: A pressure plate that has gone off and not reset.
    sprung: bool = False


@dataclass
class Conjuration:
    """A thing a power put on the board that is not a creature.

    A sphere of flame, a spectral guardian, a blade of force. It has a
    `Position` -- so it occupies its square, which `Grid.occupant` and
    `movement._clear` enforce without knowing what it is -- and a
    `Movement`, so its creator can walk it. It has no `Health` and no
    `Side`, which is what keeps it out of `query.creatures`: no initiative
    slot, no turn of its own, no vote on whether the fight is over.

    `by` is who conjured it. Everything it does, it does on their orders and
    with their numbers -- a conjuration rolls the caster's attack, not one
    of its own.

    Un-attackable, deliberately: neither printed row that needs a
    conjuration gives the thing hit points. A `Companion` is the case that
    does, and the split this docstring used to defer now lives there.
    """

    ref: str = ""
    by: int = 0
    #: The effect it lives on. Ending that despawns it.
    effect: int = 0


@dataclass
class Companion:
    """A second body a character owns and fights through.

    A shaman's spirit, a ranger's beast, a familiar. Unlike a `Conjuration`
    it **is** attackable -- "your spirit companion is hit by a melee attack"
    is a printed trigger -- so it carries `Health`, `Defences` and a `Side`,
    and it is a legitimate target like anything else.

    What it is not is a combatant. It takes no turn, holds no initiative
    slot, and its death does not decide the fight. `query.creatures` used to
    answer all four of those questions at once -- roster, target pool, win
    condition, render list -- and this is the component that finally forced
    them apart. `query.combatants` is the narrower one; everything else
    still counts a companion in, which is what makes it targetable and
    adjacent and coverable for free.

    `owner` is whose it is. `origin` is why this exists at all: a shaman's
    ordinary attack range is "Melee spirit 1", measured from here rather
    than from the shaman, which `Range(from_="companion")` reads.
    """

    owner: int = 0
    ref: str = ""
    #: Dismissed companions leave the board; the owner can call them back.
    kind: str = "spirit"
    #: The dice its **own** attacks roll -- a ranger's beast prints `1[B]`
    #: the way a character's weapon prints `1[W]`, and `c.b(n)` reads this.
    #: Empty for a spirit, which has no attack of its own: every attack it
    #: makes is a row its owner used.
    damage: str = ""


@dataclass
class Barrier:
    """A wall a power raised: several squares, blocking, and attackable.

    The third thing on the same side of the split `Companion` opened. It has
    `Health` and a `Position`, so it is a legitimate target -- "the wall can
    be attacked" is printed on three of the four rows that raise one -- and
    it is subtracted out of `query.combatants`, so it takes no turn and has
    no vote on whether the fight is over.

    Not a `Conjuration`, which has no hit points; not a zone, which cannot
    stop a creature walking through it. The squares are in `Grid.blocking`
    for as long as it stands, and `Position.spans` is the same set, so the
    thing can be measured and aimed at.
    """

    by: int = 0
    squares: frozenset[Square] = frozenset()
    #: The zone laid over the same squares, which is what carries a printed
    #: "while within the wall" clause. 0 when the row printed none.
    zone: int = 0


@dataclass
class Item:
    """An object a creature holds, and the one-shot it is spent for.

    Six rows print a thing somebody carries away from the power that made
    it -- a seed, a scroll, four berries -- and the creature that spends it
    is not the creature that made it. `c.grant_row` could not say this: the
    payout is printed on the *maker's* row and uses the maker's numbers, and
    a granted row has no charges to run out.

    `owner` is whose hands it is in, or 0 for a thing lying on the floor,
    which is where a disarmed weapon goes.
    """

    ref: str
    owner: int = 0
    #: Who created it, so the payout can read their numbers.
    by: int = 0
    uses: int = 1
    #: What spending it does. Takes the eid of whoever spent it.
    spend: Callable[[int], None] | None = None
    #: The action spending it costs, by name -- "minor", "free".
    cost: str = "minor"
    #: Set when the item is a weapon rather than a consumable: a sword that
    #: has been knocked out of a hand is an item on the ground.
    weapon: Weapon | None = None


@dataclass
class Build:
    """The choices a character makes once, at creation, and lives with.

    A warlock's pact, a ranger's fighting style, a warlord's presence, a
    rogue's tactics, the ability a class lets you elect. None of them is a
    feat and none is a power; they are the fork in a class's own page, and
    a great many printed rows carry a rider that only applies on one side
    of it -- "if you have the X build, the target also ...".

    Held as a set of plain words rather than a field per class, because the
    engine never needs to know what any of them *mean*: a row asks
    `c.build("infernal")` and nothing else does anything with it.
    """

    choices: set[str] = field(default_factory=set)


@dataclass
class Initiative:
    """`bonus` excludes the level term, which `scaling` supplies."""

    bonus: int = 0
    rolled: int = 0
    scale: str = "pc"


# --------------------------------------------------------------------------
# What is currently true of a creature
# --------------------------------------------------------------------------


@dataclass
class Conditions:
    """Which conditions hold, and how many effects are imposing each.

    A count rather than a set: two powers can daze the same creature, and the
    first one to expire must not clear the daze the second is still imposing.
    """

    counts: dict[Condition, int] = field(default_factory=dict)
    #: Conditions held in abeyance -- "you act as though you were not
    #: stunned, and at the end of your turn the effect continues". Separate
    #: from the counts so that whatever imposed the condition is untouched:
    #: a save-ends daze still has its save to make when this lapses.
    suppressed: set[Condition] = field(default_factory=set)

    def has(self, c: Condition) -> bool:
        return self.counts.get(c, 0) > 0 and c not in self.suppressed

    def add(self, c: Condition) -> bool:
        """True when this is the condition's first source."""
        was = self.has(c)
        self.counts[c] = self.counts.get(c, 0) + 1
        return not was

    def remove(self, c: Condition) -> bool:
        """True when this was the condition's last source."""
        n = self.counts.get(c, 0) - 1
        if n <= 0:
            self.counts.pop(c, None)
            return True
        self.counts[c] = n
        return False

    @property
    def active(self) -> list[Condition]:
        return sorted(
            c for c, n in self.counts.items() if n > 0 and c not in self.suppressed
        )


@dataclass
class Mod:
    """One numeric modifier.

    `what` names what it changes: `attack`, `damage`, `save`, `speed`, or a
    `Defense` value. `kind` is the bonus type -- same-named types do not
    stack and untyped ones do. Penalties ignore `kind` and bucket by
    `label` instead, because the rule for them is by *source*.

    `when` is an optional gate the power body closes over. It makes the
    modifier un-introspectable, which is the accepted price of powers being
    code: a bonus that applies "only against the creature you marked" is one
    lambda here instead of a new op, a builder and a schema.
    """

    what: str
    value: int
    kind: str = "untyped"
    when: Callable[[dict[str, Any]], bool] | None = None
    label: str = ""

    def applies(self, ctx: dict[str, Any]) -> bool:
        return self.when is None or self.when(ctx)


@dataclass
class Mods:
    items: list[Mod] = field(default_factory=list)

    def total(self, what: str, ctx: dict[str, Any] | None = None) -> int:
        """Sum the modifiers to `what`, applying 4e's stacking rules.

        Bonuses bucket by **type**: two of a kind do not add, the larger
        applies, and untyped ones add freely.

        Penalties have no type and generally do add -- **except that two
        from the same source do not**, and the worse applies. So they
        bucket by `label`, which is the ref of the row that laid them.
        Every penalty used to stack unconditionally, so one power landing
        on a creature twice came to -4 where the rule says -2; the six
        rows passing `kind=` to `c.penalty` were writing something that
        `value < 0` short-circuited past before it could mean anything.
        """
        ctx = ctx or {}
        best: dict[str, int] = {}
        worst: dict[str, int] = {}
        out = 0
        for m in self.items:
            if m.what != what or not m.applies(ctx):
                continue
            if m.value < 0:
                worst[m.label] = min(worst.get(m.label, 0), m.value)
            elif m.kind == "untyped":
                out += m.value
            else:
                best[m.kind] = max(best.get(m.kind, 0), m.value)
        return out + sum(best.values()) + sum(worst.values())


@dataclass
class Powers:
    """What a creature can do, by id. Never by name."""

    known: list[str] = field(default_factory=list)
    #: How many times each row has been used this encounter. A count rather
    #: than a set, because a few powers are usable twice -- and one of them
    #: is the cleric's heal, which a party without is not a party.
    used: dict[str, int] = field(default_factory=dict)
    #: The round each was last used, for "once per round" on top of that.
    last_round: dict[str, int] = field(default_factory=dict)
    #: Recharge powers that came back up this turn, and those still down.
    recharging: dict[str, int] = field(default_factory=dict)
    #: What this creature's basic attack is. A monster points at one of its
    #: own abilities; everyone else uses the engine's melee basic.
    basic: str = "mba"
    #: A power that replaces the basic attack when opportunity knocks.
    opportunity: str = ""
    #: The ranged basic attack, for a creature that has one. Separate from
    #: `basic`, which is the melee one: pointing `basic` at a ranged row
    #: would hand it to the opportunity window too. Empty for a monster,
    #: whose ranged attacks are its own printed rows.
    ranged: str = ""
    #: Rows taken away for a while. Not the same as spent: a forbidden row
    #: is one the creature still has and cannot currently reach.
    forbidden: set[str] = field(default_factory=set)
    #: A spellbook: rows the creature **owns and has not prepared**.
    #:
    #: `known` is what can be used, and it was the only list there was -- so
    #: "a power of the same level that is in your spellbook" had nothing to
    #: name and "you prepare one of each after a rest" could not be said at
    #: all. Owning and preparing are different states, and a wizard is
    #: mostly the difference between them.
    owned: list[str] = field(default_factory=list)

    def prepare(self, ref: str, *, instead_of: str = "") -> bool:
        """Move a row out of the book and into the prepared list.

        The row it replaces goes back into the book, because a swap is what
        every printed line of this shape is: the slot count never changes.
        """
        if ref not in self.owned:
            return False
        self.owned.remove(ref)
        if instead_of and instead_of in self.known:
            self.known.remove(instead_of)
            self.owned.append(instead_of)
        if ref not in self.known:
            self.known.append(ref)
        return True

    @property
    def all(self) -> list[str]:
        """Everything usable, with the basic attack included exactly once."""
        out = list(self.known)
        for extra in (self.basic, self.opportunity, self.ranged):
            if extra and extra not in out:
                out.append(extra)
        return out

    @property
    def spent(self) -> set[str]:
        """Rows used at least once. Kept for readers that only ask that."""
        return {ref for ref, n in self.used.items() if n > 0}

    def times(self, ref: str) -> int:
        return self.used.get(ref, 0)

    def note_use(self, ref: str, round_: int) -> None:
        self.used[ref] = self.used.get(ref, 0) + 1
        self.last_round[ref] = round_

    def restore(self, ref: str) -> None:
        self.used.pop(ref, None)
        self.last_round.pop(ref, None)

    def note_round(self, ref: str, round_: int) -> None:
        """Remember this was used this round, without spending a use.

        What a "1/round" at-will needs: it has no uses to count down, only a
        round to remember, and `note_use` would have started expending one.
        """
        self.last_round[ref] = round_

    def unuse(self, ref: str) -> None:
        """Give back one use. What a reliable power does when it misses.

        Not `restore`: a row with two uses that has spent both and then
        misses gets one back, not both.
        """
        left = self.used.get(ref, 0) - 1
        if left > 0:
            self.used[ref] = left
        else:
            self.used.pop(ref, None)
        self.last_round.pop(ref, None)

    def available(self, ref: str) -> bool:
        return ref in self.all and self.times(ref) == 0


@dataclass
class Budget:
    """The action economy for one turn.

    `immediate_round` and `opportunity_turn` are stamped with the round and
    the turn they were spent on, because their limits are per round and per
    *other creature's* turn rather than per own turn.
    """

    standard: int = 1
    move: int = 1
    minor: int = 1
    immediate_round: int = -1
    opportunity_turn: int = -1

    def refresh(self) -> None:
        self.standard = 1
        self.move = 1
        self.minor = 1


@dataclass
class ActionPoints:
    """Action points, and the two limits that are not the same limit.

    `points` is the pool, which survives a fight. `spent_round` is when one
    was last spent -- read by `resolve.attack` so that "an attack made with
    an action point" is a gate rather than prose -- and `spent` counts the
    ordinary expenditures this encounter against `limit`, which is the
    printed one-per-encounter rule.

    `free` is separate because one printed row hands out a point that
    "does not count against the limits on action point expenditures for
    this encounter", and a single counter cannot say that. A free point is
    spent first and is lost at the end of the fight.
    """

    points: int = 1
    free: int = 0
    spent: int = 0
    limit: int = 1
    #: The round an action point was last spent on, or -1. Together with
    #: whose turn it is this is "the extra action this point bought".
    spent_round: int = -1

    @property
    def available(self) -> int:
        return self.free + (self.points if self.spent < self.limit else 0)

    def refresh(self) -> None:
        """A new fight: the per-encounter limit resets, granted points do not
        carry over."""
        self.spent = 0
        self.free = 0
        self.spent_round = -1


@dataclass
class PowerPoints:
    """A psionic character's pool, refreshed every encounter.

    `maximum` comes off the class chassis; `points` is what is left.
    `augmented` records how many points each row was augmented with, which
    is the number "temporary hit points equal to the power points you spent
    to augment that power" has to read -- the spend and the hit are two
    separate moments and nothing connected them.
    """

    points: int = 0
    maximum: int = 0
    augmented: dict[str, int] = field(default_factory=dict)

    def refresh(self) -> None:
        self.points = self.maximum
        self.augmented.clear()

    def spend(self, n: int) -> int:
        """Take `n` points if they are there. Returns how many actually went."""
        n = max(0, min(n, self.points))
        self.points -= n
        return n


@dataclass
class Gear:
    """What the creature is holding and wearing, as mechanical facts only.

    A weapon is its numbers -- there is no place here for a printed name.
    """

    weapons: list[Weapon] = field(default_factory=list)
    shield: bool = False
    armour: str = "cloth"
    #: What is on the belt rather than in the hands, by weapon ref.
    stowed: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        """Start with a grip that a pair of hands could actually make.

        Everything carried counted as held, so an archer was holding a
        two-handed bow *and* a short sword at once -- and since a power's
        melee or ranged branch is offered on the strength of what is in
        hand, that handed out both branches of every row to everybody.
        """
        if self.weapons and not self.stowed:
            self.wield(self.weapons[0])

    @property
    def held(self) -> list[Weapon]:
        """What is actually in hand right now."""
        return [w for w in self.weapons if w.ref not in self.stowed]

    def wield(self, weapon: Weapon) -> None:
        """Take that weapon in hand, putting away whatever cannot share it.

        A two-handed weapon needs both hands, so everything else goes away.
        Otherwise a second one-hander may stay -- which is what a ranger
        fighting with two blades is doing.
        """
        self.stowed.discard(weapon.ref)
        if weapon.two_handed:
            self.stowed |= {w.ref for w in self.weapons if w.ref != weapon.ref}
            return
        keep = [weapon]
        for other in self.held:
            if other.ref == weapon.ref or other.two_handed or len(keep) >= 2:
                continue
            keep.append(other)
        self.stowed = {w.ref for w in self.weapons if w not in keep}

    @property
    def main(self) -> Weapon | None:
        """What is being swung -- the first weapon that can be swung.

        Not simply `weapons[0]`: an archer's list starts with a bow, and
        taking the first thing listed had it clubbing people with the bow
        whenever a melee attack asked what was in hand.
        """
        melee = self.melee
        if melee:
            return melee[0]
        held = self.held
        return held[0] if held else (self.weapons[0] if self.weapons else None)

    @property
    def ranged(self) -> Weapon | None:
        """The first weapon that can be fired, if the creature carries one.

        A ranger with a short sword and a longbow has both, and a ranged
        power should be rolling the bow's dice rather than the sword's.
        """
        return next((w for w in self.held if w.ranged), None)

    @property
    def melee(self) -> list[Weapon]:
        return [w for w in self.held if not w.ranged]

    @property
    def off(self) -> Weapon | None:
        """The second melee weapon, for a creature fighting with two.

        Its own property rather than `weapons[1]`, because a ranger carrying
        a blade and a bow has a second weapon and is not fighting with two.
        """
        melee = self.melee
        return melee[1] if len(melee) > 1 else None

    @property
    def two_weapon(self) -> bool:
        """Is this creature wielding two melee weapons?

        A printed Requirement several rows carry. Counting melee weapons
        rather than weapons, for the same reason as `off`.
        """
        return len(self.melee) > 1 and not self.shield


@dataclass
class Weapon:
    ref: str
    damage: str = "1d8"
    proficiency: int = 2
    reach: int = 1
    ranged: tuple[int, int] | None = None
    group: str = ""
    properties: frozenset[str] = frozenset()
    #: A magic weapon's enhancement bonus, which adds to its attack and its
    #: damage. Zero is a plain weapon, and everything `chargen` hands out is
    #: plain -- the number is here so that the rows that *reduce* it have
    #: something to reduce, and so that a weapon with one runs hotter.
    enhancement: int = 0

    @property
    def magic(self) -> bool:
        return self.enhancement > 0

    @property
    def is_light_blade(self) -> bool:
        return self.group == "light blade"

    @property
    def two_handed(self) -> bool:
        """Needs both hands, so nothing else can be held with it."""
        return "two-handed" in self.properties
