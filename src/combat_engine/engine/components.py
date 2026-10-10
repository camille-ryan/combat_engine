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
from .types import (
    Ability,
    ActionType,
    Condition,
    DamageType,
    Defense,
    Keyword,
    Size,
    Team,
    modifier,
)

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
    #: What this creature is *for*. A monster's printed role -- artillery,
    #: brute, controller, lurker, skirmisher, soldier -- or a character's
    #: class role: defender, striker, leader, controller.
    #:
    #: Both sides carry it in the compendium already and neither reached the
    #: board: the monster's was read only by `loader.pick` when *choosing* a
    #: creature, and the class's was fetched by `SELECT *` and dropped. So
    #: nothing in a fight could tell a wizard from a fighter, and the only
    #: target discrimination `policy.features` has is `targets_bloodied` --
    #: hit whoever is already hurt. Naming the role is what a threat estimate
    #: has to be built on.
    #:
    #: Lower case on both sides. The compendium capitalises the class column
    #: and not the monster one.
    role: str = ""

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
    #: The surge pool an extended rest refills to. Recorded when the
    #: creature is built, because `surges` is spent down during the day
    #: and nothing else remembers what it started with.
    max_surges: int = 0
    #: **A monster dies at 0.** Only a character keeps fighting into the
    #: negatives and only a character rolls death saves. Without this
    #: every monster inherited the player's floor and was still alive at
    #: minus half its printed hit points -- a 38-hit-point brute had to be
    #: taken to -19, which is half again the hit points on its card, on
    #: every monster in the game. Set by `loader.spawn`.
    dies_at_zero: bool = False

    def __post_init__(self) -> None:
        if self.hp == 0:
            self.hp = self.max_hp
        if self.max_surges == 0:
            self.max_surges = self.surges

    @property
    def bloodied(self) -> bool:
        return self.hp <= self.max_hp // 2

    @property
    def surge_value(self) -> int:
        return self.max_hp // 4

    @property
    def dying_at(self) -> int:
        """Below this and the creature is dead outright.

        Zero for a monster, which simply dies; minus half its maximum for
        a character, who drops and rolls death saves.

        **Derived, so raising `max_hp` lowers the death floor
        retroactively** -- and `query.alive` is `hp > dying_at`, with no
        memory of having died. An `on_end` callback that restores an
        original ceiling therefore makes `alive` answer True for a
        creature whose `Died` has already been emitted, because
        `Effects.bereave` runs *inside* `resolve._die`, after the
        announcement. `Cast.reanimate` is the only thing doing that today
        and guards itself with `if alive(...)`; anything else that edits
        `max_hp` under a duration has to do the same.

        Not solved with a sticky `dead` flag on purpose: `alive` is read
        in dozens of places and every revival path would have to clear
        it, so a heal that missed one would leave a healed creature dead
        forever -- a commoner failure than the rare one it prevents.
        """
        return 0 if self.dies_at_zero else -(self.max_hp // 2)


@dataclass
class Movement:
    speed: int = 6
    #: Extra modes and their speeds, e.g. {"fly": 8, "climb": 3}.
    modes: dict[str, int] = field(default_factory=dict)
    #: Kinds of difficult terrain this creature crosses for nothing, by the
    #: label `Grid.difficult` gives them. `"*"` is all of it.
    ignores: set[str] = field(default_factory=set)
    #: The same exemption, but only for one **kind of going**, keyed by the
    #: `kind` a move is made with -- "ignores difficult terrain when it
    #: shifts", which 23 rows print and `ignores` could only say by granting
    #: it for walking too. A row stronger than its card.
    #:
    #: Keyed on the move kind rather than carrying a predicate because the
    #: kind is already threaded through `step` and `MoveStart.kind_`, so the
    #: scope costs a dict lookup where a callable would cost a call per
    #: square searched. `charge` and `run` are the other two the cards name
    #: and this engine prices both -- `movement.PRICED_KINDS`.
    ignores_when: dict[str, set[str]] = field(default_factory=dict)
    #: How the creature is moving **right now**, or "" between moves.
    #:
    #: `modes` says what it *can* do and never what it *is* doing, so
    #: "Requirement: must be climbing" and "while it is not flying" could not
    #: be written at all -- a gate on `modes` is true whenever the creature
    #: has the speed, which is not the printed sentence. Four rows across two
    #: waves asked for this.
    using: str = ""


@dataclass
class Shapes:
    """Which forms a creature is currently in, by the word its card prints.

    `c.form` identifies a shape only by the effect label it lays, which is
    the ref of the row that laid it -- so nothing could ask "is it in rat
    form", and 43 rows print a Requirement that asks exactly that.

    A **set**, because the cards stack: `m115824` prints "human or hybrid
    form" on one row and "rat or hybrid form" on another, so hybrid is both
    at once and a single current-form string could not say so.

    Maintained by `c.form`, which adds the word and takes it off again when
    the form ends. Side state, like `Movement.ignores`, so it lifts and
    restores with a suspension too.
    """

    live: set[str] = field(default_factory=set)


@dataclass
class Undying:
    """This creature gets back up unless it is finished with one of `by`.

    A troll clause: "reduced to 0 hit points by an attack that does not deal acid
    or fire damage, it falls prone and remains at 0 until the start of its next
    turn, when it regains 10 hit points."

    **Declared so a policy can read it**, which is the whole reason this exists as
    a component rather than staying inside the row's body. The body already
    implements the mechanic correctly by watching its own `Dropped`; what nothing
    could see was that the creature *will* get up, so `threat_removed` scored it at
    nothing once it hit 0 and the party had no reason to spend the one row that
    ends it. Three of 24 level-10 fights ran to the round cap on that. #318.

    Empty `by` means nothing finishes it, which no printed row says; a row that
    declares this names its types.
    """

    by: frozenset[DamageType] = field(default_factory=frozenset)


@dataclass
class Defences:
    """Damage the creature shrugs off or takes worse, by type."""

    resist: dict[DamageType, int] = field(default_factory=dict)
    vulnerable: dict[DamageType, int] = field(default_factory=dict)
    #: Vulnerability that applies to **some** of what reaches the creature:
    #: `(dtype or None, amount, when)` triples, `when` a predicate on the
    #: damage context.
    #:
    #: `vulnerable` above is a flat `dict[DamageType, int]` with nowhere to
    #: record a scope, and eleven rows print one -- "vulnerable 10 to the
    #: <monster>'s attacks", "vulnerable 3 to **weapon** attacks",
    #: "vulnerable 5 to your attacks that deal the chosen type". A `None`
    #: dtype means every type, which is what the attacker-scoped ones say.
    #:
    #: A list rather than a dict because two scoped vulnerabilities to the
    #: same type are two different clauses and both count; the unscoped
    #: dict is a running total and cannot say which clause put it there.
    #: Read in `resolve.deal_damage` beside immunity and resistance, which
    #: are already read against the same context. #471.
    vulnerable_when: list[
        tuple[DamageType | None, int, Callable[[dict[str, Any]], bool]]
    ] = field(default_factory=list)
    immune: set[DamageType] = field(default_factory=set)
    #: Types the creature's insubstantial trait does **not** halve -- "takes
    #: half damage from any damage source, except those that deal force
    #: damage". Counted rather than a set, for the same reason `Conditions`
    #: is: two effects can name the same exception and the first to expire
    #: must not clear the other's.
    #:
    #: Read as a property of the *creature*, not of the effect that laid it,
    #: which is a simplification and a deliberate one: no printed stat block
    #: carries two insubstantial traits at once, so there is no card on which
    #: one trait's exception would wrongly narrow another's. `query.takes_half`
    #: says so where it reads this.
    half_except: dict[DamageType, int] = field(default_factory=dict)


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
    #: The printed `Perception DC` to notice it before it fires, or `None`
    #: for a trap whose block prints none -- 275 of the 631 do, and the
    #: honest reading of that is **cannot be noticed in advance** rather
    #: than a guessed number. Never derived: across the 356 that print one
    #: the DC is not a function of level, so a formula would be wrong by
    #: ten either way on the number that decides what a player is shown.
    perception_dc: int | None = None


@dataclass
class Scenery:
    """Something standing on the map that no power put there.

    A crate, a statue, a campfire. It has a `Position`, so it has a square,
    a size and a footprint, and everything that measures to a thing --
    adjacency, a burst, line of effect -- measures to it for free. It has no
    `Health` and no `Side`, which is what keeps it out of `query.creatures`:
    no turn, no initiative slot, no vote on whether the fight is over, and
    nothing can attack it.

    Not a `Conjuration`, which is a power's own doing and dies with the
    effect holding it up; not a `Trap`, which attacks. Scenery is what was
    already in the room, and the rows that want it are the ones whose target
    line says "object" or whose Requirement says "a fire".

    `kind` is the printed word a row asks for -- "object", "fire". `size`
    lives on the `Position` with everybody else's. `fastened` is a thing
    bolted down, which one printed target line excludes. `by` is whoever is
    holding or controlling it, 0 for a thing nobody has: one field, because
    "held by a creature" and "controlled by a creature" are the same
    question asked by two cards.
    """

    kind: str = "object"
    fastened: bool = False
    by: int = 0


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
    #: The round its owner last spent an action on it. Every summon block
    #: prints "if you haven't given it any commands by the end of your
    #: turn", so the instinctive effect needs to know whether one was.
    commanded: int = -1
    #: The dice its **own** attacks roll -- a ranger's beast prints `1[B]`
    #: the way a character's weapon prints `1[W]`, and `c.b(n)` reads this.
    #: Empty for a spirit, which has no attack of its own: every attack it
    #: makes is a row its owner used.
    damage: str = ""
    #: Which ability its own damage line adds -- `"str"` or `"dex"`. Three
    #: of the eight beast categories are Dexterity and taking Strength for
    #: all of them is a point of damage quietly gone on the fast ones.
    ability: str = "str"
    #: Active or passive, which only a familiar prints. A passive one
    #: occupies no square at all -- it cannot be targeted, nothing is
    #: adjacent to it and no range is measured from it -- so `Position` is
    #: taken off it and kept in `stowed` until it turns active again. Held
    #: rather than rebuilt because the square *and the size* have to come
    #: back unchanged.
    passive: bool = False
    stowed: Position | None = None


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
    #: A modifier that is **rolled** rather than fixed -- "roll a d6 and add
    #: it as a power bonus to the roll". The body closes over its own rng,
    #: the way `when` closes over its own question, and it is called once per
    #: time the modifier is read, which is once per roll.
    roll: Callable[[], int] | None = None
    #: The damage type this modifier's points come out as, for a *damage*
    #: modifier and nothing else. Empty is the ordinary case: the rider
    #: joins the blow and is whatever the blow already was.
    #:
    #: "Your attacks deal 2 extra fire damage" is not that. The two points
    #: are fire even when the sword is not, so they meet the target's fire
    #: resistance and its fire vulnerability and the sword's points do not.
    #: A tuple because "1d6 extra cold **and** lightning damage" is one
    #: rider of two types, which resistance reads as a unit.
    dtype: tuple[DamageType, ...] = ()

    def applies(self, ctx: dict[str, Any]) -> bool:
        return self.when is None or self.when(ctx)

    def amount(self) -> int:
        return self.value + (self.roll() if self.roll is not None else 0)


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
            value = m.amount()
            if value < 0:
                worst[m.label] = min(worst.get(m.label, 0), value)
            elif m.kind == "untyped":
                out += value
            else:
                best[m.kind] = max(best.get(m.kind, 0), value)
        return out + sum(best.values()) + sum(worst.values())

    def split(
        self, what: str, ctx: dict[str, Any] | None = None
    ) -> dict[tuple[DamageType, ...], int]:
        """`total`, but kept apart by the damage type each modifier carries.

        `()` is the untyped share and is what every existing modifier
        contributes, so a blow with no typed rider comes back as a single
        entry holding exactly what `total` would have returned. Only
        `resolve.deal_damage` calls this; everything else -- the policy's
        estimate of a hit, the UI -- still wants one number and still
        asks `total`.

        Stacking is settled **within** a type, not across: two feat bonuses
        of extra fire damage are the same bonus and the larger applies, but
        a feat bonus of fire and a feat bonus of cold are two different
        riders and both land. Bucketing them together would have made a
        character who had earned both deal one of them.
        """
        ctx = ctx or {}
        out: dict[tuple[DamageType, ...], int] = {}
        best: dict[tuple[tuple[DamageType, ...], str], int] = {}
        worst: dict[tuple[tuple[DamageType, ...], str], int] = {}
        for m in self.items:
            if m.what != what or not m.applies(ctx):
                continue
            value = m.amount()
            if value < 0:
                key = (m.dtype, m.label)
                worst[key] = min(worst.get(key, 0), value)
            elif m.kind == "untyped":
                out[m.dtype] = out.get(m.dtype, 0) + value
            else:
                key = (m.dtype, m.kind)
                best[key] = max(best.get(key, 0), value)
        for (types, _), value in list(best.items()) + list(worst.items()):
            out[types] = out.get(types, 0) + value
        return out


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
    #: Rows that may be swung *instead of* the basic attack, keyed by the
    #: window that hands one out: `"opportunity"`, `"charge"`,
    #: `"challenge"` -- the swing a defender's mark punishes with -- and
    #: `"ranged"`. A tuple per window, because the printed line is nearly
    #: always a choice among an associated-powers list, and `""` is the
    #: key for a card that names no window and answers every melee one.
    #:
    #: Not folded into `all`: a feat lists rows the character may not
    #: possess, and one of those in `all` would be offered on an ordinary
    #: turn as well. `dsl.basic_options` is the read.
    instead: dict[str, tuple[str, ...]] = field(default_factory=dict)
    #: The ranged basic attack, for a creature that has one. Separate from
    #: `basic`, which is the melee one: pointing `basic` at a ranged row
    #: would hand it to the opportunity window too. Empty for a monster,
    #: whose ranged attacks are its own printed rows.
    ranged: str = ""
    #: Rows taken away for a while. Not the same as spent: a forbidden row
    #: is one the creature still has and cannot currently reach.
    forbidden: set[str] = field(default_factory=set)
    #: Keywords whose rows cannot be used. *"The target is dazed and cannot
    #: use powers that have the polymorph keyword"* -- two items print that,
    #: and `p12344`'s "cannot teleport" is the same thing said about a
    #: different keyword.
    forbidden_keywords: set[Keyword] = field(default_factory=set)
    #: Keywords a row **must** carry to be usable -- the opposite reading,
    #: and four rows print it: *"you can't use weapon or implement attack
    #: powers that lack the beast form keyword."* Kept apart from
    #: `forbidden_keywords` rather than inverted into it, because the two
    #: sentences coexist on one creature and a single set cannot say which
    #: direction each entry means. #487.
    required_keywords: set[Keyword] = field(default_factory=set)
    #: Rows exempt from `required_keywords` because they are only being
    #: *sustained*. Every one of those four cards prints "although you can
    #: sustain such powers", and a refusal written without it cancels every
    #: zone and stance the character had running when it shifted.
    sustainable: set[str] = field(default_factory=set)
    #: Which ability a named row rolls, when something has changed it.
    #: Keyed by ref, each entry an `(ability, when)` pair -- sixteen feats
    #: print "you may use Dexterity instead of Strength with <row>", and
    #: the ability a row attacks with is otherwise **header data**, fixed
    #: at import for everyone who ever holds it.
    #:
    #: A list, because two feats may both speak about one row, and `when`
    #: is a `(world, eid)` predicate so "when the weapon is thrown" and
    #: "with a bow" are sayable -- those read what is in hand, which is a
    #: fact about the creature and not about the attack in flight. First
    #: entry whose `when` passes wins; `dsl.Attack.ability_for` is the
    #: only read.
    rolls: dict[str, list[tuple[Ability, Callable[[Any, int], bool] | None]]] = field(
        default_factory=dict
    )
    #: Which dice a named row rolls, when something has changed them.
    #:
    #: The sibling of `rolls` above and for the same reason: the die a row
    #: rolls is written into its body, so "you add 1d10 to the roll, rather
    #: than 1d6" had nothing to change. 21 rows print a sentence of that
    #: shape -- a bigger die on a racial power, a brutal weapon's reroll
    #: threshold, a sneak attack upgraded a step.
    #:
    #: A list, because two feats may both speak about one row, and `when` is
    #: a context predicate so "on a Nature check" and "with a bow" are
    #: sayable. First entry whose `when` passes wins; `Cast.dice_for` is the
    #: read and the row that rolls must use it.
    dice: dict[str, list[tuple[str, Callable[[dict[str, Any]], bool] | None]]] = field(
        default_factory=dict
    )
    #: Keywords a named row carries **for this creature only**, by ref.
    #:
    #: "Your `p1448` power is considered an arcane attack power", "your
    #: `p11739` gains the reliable keyword" -- 12 feats print a sentence of
    #: that shape, and a row's keywords are otherwise **header data**: one
    #: tuple, fixed at import, shared by everybody who ever holds the row.
    #: A feat cannot edit it without editing it for everybody.
    #:
    #: Read through `dsl.keywords_of`, never off `Power.keywords` directly.
    #: That is the whole discipline here: there were 22 sites reading the
    #: header, and a grant honoured at 21 of them is a modifier nothing
    #: consults at the 22nd -- this component's commonest bug.
    granted_keywords: dict[str, frozenset[Keyword]] = field(default_factory=dict)
    #: Clauses that may run *instead of* one named clause of a named row.
    #: Keyed `(ref, what)`, where `what` is the clause's own word --
    #: `"pull"`, `"shift"`, `"temp_hp"` -- chosen by the row that offers it.
    #:
    #: A feat printing "when you use <row>, you can X instead of Y" cannot
    #: replace the row's *body*: `p5330` pulls **and** damages, so swapping
    #: the body throws the damage away. The substitution belongs at the
    #: clause, and the row reads it with `c.instead_of` -- the same bargain
    #: `dice` above makes, whose note says it outright: a row must read it
    #: to be changed.
    #:
    #: **Not asked at the clause, decided before the body runs.** Each
    #: registration becomes its own entry in the action menu, the way each
    #: half of a "Melee or Ranged" line and each augment already do, and
    #: for the reason `Action.augment` gives: that is what makes both
    #: reachable by clicking *and* weighable by a policy. A `c.choose`
    #: buried in a body is invisible to `policy/`, which cannot compare
    #: "pull" against "slide" if the option was scored before the question
    #: was put. `Cast.variant` carries which one this use picked.
    #:
    #: A list per key, latest first, because two feats may speak about one
    #: clause -- `p10439`'s shift is replaced by two of them. They do not
    #: combine: substituting one clause twice is a choice among them, which
    #: is why the menu is a flat list and not a product.
    pre_empts: dict[tuple[str, str], list[tuple[Callable[[], Any], str]]] = field(
        default_factory=dict
    )
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
        for extra in (self.basic, self.ranged):
            if extra and extra not in out:
                out.append(extra)
        return out

    def instead_of_basic(self, window: str) -> tuple[str, ...]:
        """What may stand in for the basic attack in that window.

        The windowless key is folded in for every melee window and not
        for the bow: "in place of a melee basic attack" with no window
        named answers the charge, the opportunity attack and the
        defender's punishment alike, and none of them is ranged.
        """
        wide = () if window == "ranged" else self.instead.get("", ())
        return tuple(dict.fromkeys((*self.instead.get(window, ()), *wide)))

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
    #: What the **most recent** use of each augmentable row was bought
    #: with, which is a different question from `augmented` and the one
    #: "when you augment <row>" has to ask. `augmented` is the encounter's
    #: running total, so once a row has been augmented it reads as
    #: augmented for the rest of the fight; this is set on every use of a
    #: row that declares `augments=`, including the ones bought with
    #: nothing, so a watcher can tell this use from the last.
    last: dict[str, int] = field(default_factory=dict)

    def refresh(self) -> None:
        self.points = self.maximum
        self.augmented.clear()
        self.last.clear()

    def spend(self, n: int) -> int:
        """Take `n` points if they are there. Returns how many actually went."""
        n = max(0, min(n, self.points))
        self.points -= n
        return n


@dataclass
class Shrouds:
    """The assassin's shrouds: who is carrying them and how many.

    A count rather than a stack of effects. The count is the only thing
    anything reads, only one creature carries them at a time, and clearing
    them when they are invoked is then one assignment rather than a search.
    """

    on: int = 0
    count: int = 0


@dataclass
class Magic:
    """One magic item, reduced to what a fight needs to know.

    **Not a weapon, and that distinction is the whole design.** A magic
    longsword is the printed longsword with an enhancement bonus and some
    rows attached -- so this says which base item it was laid on and what
    it adds, and the `Weapon` keeps the numbers it always had.

    Its fields are read off `game.db` by whoever equips it; the engine
    never opens that database, the way it never opens it for a monster's
    hit points either.
    """

    ref: str
    slot: str = ""
    #: The enhancement bonus of the rung being held, not the whole ladder.
    plus: int = 0
    #: What the bonus applies to: `attack_damage`, `ac`, `defences`, or
    #: nothing at all.
    enh_to: str = ""
    #: A critical rider, as dice -- "1d6" for the "+1d6 per plus" that 734
    #: heroic items print. Multiplied by `plus`, which is what "per plus"
    #: means.
    crit: str = ""
    #: The item's own rows -- its Properties and its Powers -- which go
    #: into `Powers.known` while it is worn.
    powers: tuple[str, ...] = ()
    #: What base items this magic may be laid on, as the printed column
    #: reads them -- `("heavy blade", "light blade")`, `("arrow",)`.
    #: Empty is "any", which is most of the catalogue. Read by
    #: `equipment` to decide which launcher a piece of ammunition fits.
    base: tuple[str, ...] = ()


@dataclass
class Ammo:
    """Magic ammunition in the quiver: what it is, and how much is left.

    Not a `Weapon` and not a `Magic` in `Gear.worn`, because it is neither
    held nor worn -- it is *spent*. One piece goes when a shot is fired
    and the item's property rides that shot and no other, which is the
    whole of what the ammunition rows have been waiting for.

    `count` is how many pieces the wielder bought. That is not a printed
    rule -- the card says what one piece does -- so it is a field rather
    than a constant, and whoever hands the ammunition out chooses.
    """

    ref: str
    #: `arrow`, `bolt` or `stone`, off the item's base-item column.
    kind: str = ""
    plus: int = 0
    count: int = 1


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
    #: What taking a weapon up costs this creature, when something has made
    #: it cheaper than the printed minor action.
    #:
    #: `actions._wielding` offers the draw and hard-coded `MINOR`, which is
    #: the rule. Three rows buy their way out of it -- "once per turn you can
    #: draw or sheathe a weapon as a free action **instead of** a minor
    #: action" -- and that is a cost on the creature, not on any row, so it
    #: cannot live in a header.
    #:
    #: `None` is the printed minor. A row that is free only once per turn
    #: sets `draws_left` as well.
    draw_cost: ActionType | None = None
    #: How many cheap draws remain this turn, for the "once per turn" half.
    #: `-1` is unlimited, which is what a card printing no limit means.
    draws_left: int = -1
    #: What `draws_left` refills to at the start of this creature's turn.
    #: Kept separately because `draws_left` is spent down and would
    #: otherwise have nothing to be restored from.
    draw_allowance: int = -1
    #: Which weapon the cheaper cost applies to, by ref. Empty is every
    #: weapon, which is what two of the three rows mean; the third is "draw
    #: and attack with a dagger", one weapon and not the rest.
    draw_only: str = ""
    #: Weapon-requirement waivers: `(holding, satisfies)` pairs.
    #:
    #: "You can use a warhammer with any power that normally requires a
    #: light blade" -- 16 feats print a sentence of that shape, and the
    #: requirement they waive is checked in exactly one place,
    #: `Cast.wielding`. So the waiver is a fact about the character rather
    #: than about any of the powers it unlocks, which is why it cannot sit
    #: in a header: the same rogue power is reachable with a light blade by
    #: everybody and with a hammer only by whoever took the feat.
    #:
    #: `holding` is matched the way `wielding` matches a Requirement -- a
    #: property, a group, a category -- **plus the printed slug**, because
    #: several of these cards name one weapon rather than a group.
    counts_as: list[tuple[str, str]] = field(default_factory=list)
    #: The weapons this creature is **trained** with, by ref -- its chassis's
    #: printed lines plus whatever its feats and its race opened up.
    #:
    #: **Empty means "nobody recorded any", not "proficient with nothing."** A
    #: monster has no `Build` and carries no weapons; a board assembled by hand
    #: in a probe or an instrument records none either. Penalising those would
    #: turn a missing record into a to-hit penalty, which is the wrong failure
    #: -- so the bonus is withheld only when there **is** a record and the
    #: weapon in hand is not in it. `chargen.spawn` is what fills it. #242.
    trained: frozenset[str] = frozenset()
    #: The **bands** this creature is proficient in, as the class page prints
    #: them -- `{"simple:melee", "military:melee"}`, or `"weapon:<slug>"` for
    #: the classes whose line names weapons one at a time.
    #:
    #: `trained` above is a set of refs and answers "was this exact weapon
    #: dealt to me"; this answers "does my page allow it", which is the
    #: question a *human* choosing gear asks and the one #285 was about. A
    #: fighter dealt a longsword was refused the bonus on a warhammer its page
    #: plainly grants.
    #:
    #: **A band is never expanded into the weapons it covers.** Camille's call
    #: (#436): "if a character has proficiency in all simple and military
    #: weapons, that should hold true and not be parsed into individual
    #: proficiencies." So coverage is decided by asking the `Weapon`, not by
    #: membership in a precomputed list -- which also means a weapon added
    #: later is covered without anything being regenerated.
    #:
    #: Empty means "nobody recorded any", exactly as `trained` does.
    bands: frozenset[str] = frozenset()
    #: Magic items being worn, by slot. A weapon's own magic is on the
    #: `Weapon` -- it is a longsword with properties -- so this holds the
    #: armour, the neck, and the eight small slots that had nowhere to go.
    worn: dict[str, Magic] = field(default_factory=dict)
    #: Magic ammunition, in the order it is drawn. Not in `worn`, because
    #: a worn item is on the creature for the whole fight and a piece of
    #: ammunition is gone the moment it is loosed.
    quiver: list[Ammo] = field(default_factory=list)

    def proficient_with(self, arm: Weapon) -> bool:
        """Does a recorded band or grant cover this weapon?

        Three shapes, which is every one of the 19 terms the 25 class pages
        print between them:

            simple:melee / military:ranged    a category and a reach
            military:light blade              a category and a weapon group
            weapon:<slug>                     one weapon, named

        Asked of the `Weapon` rather than against an expanded list, so a band
        covers a weapon nobody thought about when the band was recorded --
        which is what "proficiency in all simple and military weapons should
        hold true" means (#436).

        **An unrecognised qualifier does not match**, and that is deliberate.
        The assassin prints "simple **one-handed** melee" and `Weapon` carries
        no `hands`, so that band covers nothing here: the class keeps the
        weapons it was dealt through `Gear.trained`, and the band adds
        nothing until the column exists. Withholding is the safe direction --
        the same reasoning `Cast._trained_with` uses for an empty record.
        """
        if f"weapon:{arm.slug}" in self.bands:
            return True
        cat = (arm.category or "").lower()
        if not cat:
            return False
        reach = "ranged" if arm.ranged is not None else "melee"
        want = {
            f"{cat}:",                    # the whole category
            f"{cat}:{reach}",             # ...or one half of it
        }
        if arm.group:
            want.add(f"{cat}:{arm.group.lower()}")
        # "simple one-handed melee" is narrower than "simple melee" and the
        # assassin is the only class that prints it. Reading it as the wider
        # band would hand the class two-handed weapons its page withholds.
        if arm.hands:
            want.add(f"{cat}:{arm.hands.lower()} {reach}")
        return bool(want & self.bands)

    def __post_init__(self) -> None:
        """Start with a grip that a pair of hands could actually make.

        Everything carried counted as held, so an archer was holding a
        two-handed bow *and* a short sword at once -- and since a power's
        melee or ranged branch is offered on the strength of what is in
        hand, that handed out both branches of every row to everybody.

        **The first thing that can be swung or fired, not simply
        `weapons[0]`**, which is the same rule `main` and `melee` already
        follow and for the same reason. A fighter carrying a rod, a greataxe
        and a wand wielded the rod -- an implement, one-handed, so the wand
        came up in the other hand and the two-handed axe went on the belt.
        It then stood next to an enemy holding two implements it cannot hit
        anything with, and **every melee row it owned was refused, `mba`
        included**: `can_branch` asks for a melee weapon in hand and `melee`
        correctly answered none. Three starts in 144 across three levels,
        every one of them the fighter. #268.

        An all-implement creature still wields its first implement -- a
        wizard holding nothing but an orb is holding the orb -- because the
        fallback is `weapons[0]` when nothing else can be swung.
        """
        if self.weapons and not self.stowed:
            self.wield(next((w for w in self.weapons
                             if w.group != "implement"), self.weapons[0]))

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

        The fallbacks skip implements for the same reason `melee` does: a
        wizard holding nothing but an orb is holding nothing it can swing,
        and answering "the orb" makes every row that asks what is in hand
        quietly true.

        **Both remaining branches filter `held`, so this cannot contradict
        `melee`.** There was a third that filtered `weapons` instead, and so
        answered "the greataxe" for an axe sitting on the belt while `melee`
        answered "nothing" -- one disagreeing pair read by 86 callers, every
        one of which is asking what the creature is *using*. It became visible
        when a grip bug put a fighter's axe in its stow (#268); the two readings
        had been inconsistent all along.

        Removed rather than corrected, because correcting it makes it identical
        to the branch above. Measured first: across 16 fights and 1.8 million
        calls, **the branch answered zero times** -- `melee[0]` 810,779 and
        `None` 995,039, nothing else. And `None` being the commonest answer is
        why dropping it is safe: every caller already handles it. #295.
        """
        melee = self.melee
        if melee:
            return melee[0]
        # A creature holding only a bow has nothing to swing and something to
        # fire, and that is what it is using.
        firing = [w for w in self.held if w.group != "implement"]
        return firing[0] if firing else None

    @property
    def ranged(self) -> Weapon | None:
        """The first weapon that can be fired, if the creature carries one.

        A ranger with a short sword and a longbow has both, and a ranged
        power should be rolling the bow's dice rather than the sword's.
        """
        return next((w for w in self.held if w.ranged), None)

    @property
    def thrown(self) -> Weapon | None:
        """The first thing in hand that can be thrown, if anything can.

        The sibling of `ranged` above and deliberately not the same property:
        that one answers "can this be fired", which decides whether there is a
        ranged basic attack, and this answers "how far does it go when thrown",
        which a row printing `Ranged weapon` needs and nothing could ask.
        """
        return next((w for w in self.held if w.thrown), None)

    @property
    def melee(self) -> list[Weapon]:
        """What is in hand that can actually be swung at somebody.

        **An implement is not one, and it used to count as one**, because
        the test was "held and not ranged" and an orb is neither. That was
        invisible only for as long as nobody held an implement without a
        weapon: give a wizard an orb and a row printing "Requirement: you
        must be wielding a melee weapon in one hand" starts firing off the
        orb, which is not a thing a wizard can hit anyone with.
        `chargen._shield_for` had already worked this out and was excluding
        implements by hand.
        """
        return [w for w in self.held if not w.ranged and w.group != "implement"]

    @property
    def implement(self) -> Weapon | None:
        """The rod, staff, wand or holy symbol in hand, if there is one.

        Its own property because `main` would answer the wrong thing: an
        implement is not ranged, so it counts as melee, and a cleric
        holding a mace and a symbol has the mace returned. Harmless while
        every implement was a plain one -- and the moment a magic implement
        has an enhancement bonus, that bonus is read off the mace instead.
        """
        return next((w for w in self.held if w.group == "implement"), None)

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
    #: The printed name, lowered and hyphenated -- **a matching key, never an
    #: identity.** A card reading "you must be wielding a whip" names one
    #: weapon and a whip has no group of its own, so `query.holding` and
    #: `chargen.meets` have to be able to ask by the printed word.
    #:
    #: `ref` used to be this string, so one field answered both "which weapon
    #: is this" and "which weapon does that word mean". Splitting them is #339;
    #: a weapon's name is mechanics here -- thirty of them are in
    #: `sanitise.RULES_TERMS` -- so it is fine in a field and was never fine in
    #: an identifier.
    slug: str = ""
    damage: str = "1d8"
    proficiency: int = 2
    reach: int = 1
    ranged: tuple[int, int] | None = None
    #: Short and long range **when thrown**, kept apart from `ranged` on
    #: purpose. `Gear.ranged` means "can be fired", and a dagger cannot be --
    #: letting it answer that question hands a rogue a ranged basic attack it
    #: does not have, which is why a thrown weapon's range used to be dropped
    #: on the floor instead. It is a different question from how far the thing
    #: flies, and 17 printed weapons answer it differently: 2/5, 3/6, 4/8,
    #: 5/10, 6/12 and 10/20.
    thrown: tuple[int, int] | None = None
    group: str = ""
    #: Simple, military or superior -- the proficiency band the table prints
    #: beside the group. A handful of rows carry "you must use this power
    #: with a simple weapon" as their Requirement and had nothing to ask.
    category: str = ""
    #: `one-handed`, `two-handed` or `double`, as the page prints it. Here
    #: because the assassin's proficiency line is "simple **one-handed**
    #: melee" and without it that band could match nothing, which refused the
    #: class its own dagger. #285.
    hands: str = ""
    properties: frozenset[str] = frozenset()
    #: A magic weapon's enhancement bonus, which adds to its attack and its
    #: damage. Zero is a plain weapon, and everything `chargen` hands out is
    #: plain -- the number is here so that the rows that *reduce* it have
    #: something to reduce, and so that a weapon with one runs hotter.
    enhancement: int = 0
    #: What this weapon's damage *is*. `None` is the ordinary case -- a
    #: sword deals whatever the power says, which is usually untyped -- and
    #: a type here is a weapon that has been made of something: a flaming
    #: blade, a frost axe. Twenty-five heroic feats and a long tail of items
    #: turn on it, and there was nowhere to write it down.
    #:
    #: Read by `Cast._weapon_dtype`, which resolves it **before** the damage
    #: context is built, so a bonus gated on the damage type sees the type
    #: the weapon actually deals.
    dtype: DamageType | None = None
    #: The magic item this weapon is, if it is one. A magic weapon is a
    #: base weapon with properties laid on top -- not a weapon of its own --
    #: so the numbers above stay the printed longsword's and this says which
    #: item's rows come with it.
    item: str = ""

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
