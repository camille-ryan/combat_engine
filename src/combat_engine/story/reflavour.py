"""Wearing a stat block as something else.

`README.md` has asked for this since the first commit: select monsters and
reflavour them, *"usually just generating their names and descriptions, but
sometimes this may also involve changing damage types"*, so the same stat block
can be a gang of bandits or a pack of ghouls. It had never been built and had
never even been filed. #790.

## It is the fallback, not the main road

Measured against the module now in `modules/`: 39 of its 39 high-confidence
creature names resolve straight to refs that are written and offerable. For a
4e module almost nothing needs reflavouring at all, and `cast_list.py` tries
the name first for that reason.

What this is for is the rest: the creature a module names that we do not have,
the two paragon ones the tier rule defers, and every module from every other
edition -- where no name will ever resolve and a right-shaped fight has to be
dressed as what the page describes.

## Three verbs, no engine change

A change under `engine/` widens `audit.py` to all 12,197 rows. None is needed:

* **Creature words** -- `Cast.set_origin(*words, instead_of=...)`, which
  `query.kinds_of` reads back. `instead_of` is the only way to take a printed
  word off a stat block, which is what "this is a ghoul now, not a bandit"
  requires.
* **Damage type** -- `Cast.deals`, **one call per declared ability**. The
  blanket form speaks only for `Keyword.WEAPON` or `Keyword.IMPLEMENT` rows and
  most monster abilities carry neither; there is deliberately no "any row"
  value. But `Cast._retyped` steps that gate aside when the effect names one
  row, so naming each of the creature's three-to-six abilities covers the
  whole stat block and is *more* precise than a blanket override would be --
  it can retype only the abilities that print the source type.
* **Resistances** -- written onto `Defences` directly. That is the same write
  `loader.spawn` does from the database a moment earlier; a spawn-time overlay
  is not an in-combat effect and should not pretend to be one by laying a
  duration nothing will ever end.

**Verified before anything was built on it**: a creature given three retypes, a
word and a resistance at spawn still has all of them in round 1, and
`query.kinds_of` reports the added word. The worry was real -- the overlay is
laid before `Encounter.start()`, and an encounter-duration effect cleared by
the clock starting would have left every reflavour silently gone by the first
attack.

## What a retype does not reach, measured

Fought for real -- five seeds at level 3, the same fights with and without an
undead reflavour, counting damage types off the bus:

    un-reflavoured   untyped 50, cold 11, acid 9, fire 5, poison 1
    reflavoured      necrotic 50, acid 6, fire 1, untyped 1

So the bulk converts and the control deals no necrotic at all. The **7 events
that did not convert** are not noise, and both causes are now named:

* **Ongoing damage** (5 of the 7) resolves off an `Effect` rather than from a
  `Cast` naming the ability, so `_retyped`'s `named != self.ref` test can never
  match.
* **`c.flat`** (2 of the 7) -- unrolled damage, *"the attacker takes 3 fire
  damage"* -- does not consult `_typed` at all. `_typed` has exactly two
  callers in `cast.py`, both on the rolled-damage path.

That is an engine gap rather than a story-engine one and it is filed: the same
hole makes an item printing *"all damage dealt by this weapon is fire"* fail to
recolour its own flat rider. Until it is fixed, **a reflavoured creature's
attacks change type and its ongoing damage and flat riders keep theirs**, which
is a visible wrong answer rather than a crash -- so it is written down here
rather than left for somebody to rediscover from a log.

## The name never reaches a column

The charter's constraint, and it is the one that would quietly break the legal
gate rather than the game: *"a generated name that lands in a column is
indistinguishable from a leaked one"*. So `Reflavour.name` lives on the
fielded result and nowhere else -- not `game.db`, not a spec, not
`localization/names.json`.

## Why the theme table is keyed the way it is

This file is **tracked code**, so the one rule applies to it in full. The keys
are therefore only words that are already safe to say here: the eleven
`DamageType` members, the six origins, and creature types the compendium
carries as glossary entries -- the ETL leaves `Glossary` out of its alias
tables precisely because those 518 terms are mechanical vocabulary rather than
anybody's prose.

Anything narrower than that -- the actual name of the thing a module wants --
comes out of the **git-ignored module file** at runtime and is matched against
the database. It never enters the tree, so `leaks.py` stays meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from combat_engine.content import loader
from combat_engine.engine.cast import Cast
from combat_engine.engine.components import Defences, Ident, Stats
from combat_engine.engine.durations import When
from combat_engine.engine.ecs import World
from combat_engine.engine.types import DamageType

#: The ref every effect this module lays is attributed to.
#:
#: Not a row ref and deliberately shaped so nobody mistakes it for one.
#: `audit._claimed` credits a row when an effect label starts with that row's
#: ref, so a reflavour borrowing a creature's own ref would make the creature's
#: abilities look as though they had fired.
REF = "story:reflavour"


def resist_amount(level: int) -> int:
    """What a themed resistance is worth at that level.

    5 / 10 / 15 by tier, which is the convention the printed stat blocks
    follow almost without exception. A flat 10 at heroic is most of a level-2
    brute's damage output and turns a reflavour into an immunity.
    """
    return 5 if level <= 10 else 10 if level <= 20 else 15


@dataclass(frozen=True)
class Theme:
    """What one word does to a creature, before a level is known."""

    #: Words to add to the creature's own, for `query.kinds_of`.
    words: tuple[str, ...] = ()
    #: A word this theme displaces. Origins are exclusive, so becoming shadow
    #: means no longer being natural.
    drop: str = ""
    #: Everything the creature deals becomes this.
    dtype: str = ""
    resist: tuple[str, ...] = ()
    vulnerable: tuple[str, ...] = ()
    immune: tuple[str, ...] = ()


#: What a theme word is worth, mechanically. Hand-written, one entry per word,
#: and short on purpose -- a table that tried to cover every creature type
#: would be inventing rules rather than applying them.
#:
#: The eleven damage types are the reliable half: *this thing is a fire
#: creature* has one obvious reading and the engine already has every piece of
#: it. The creature types below them are the few where the printed convention
#: is not in doubt.
THEMES: dict[str, Theme] = {
    # -- the damage types, which speak for themselves ----------------------
    **{
        d.value: Theme(words=(d.value,), dtype=d.value, resist=(d.value,))
        for d in DamageType
        if d is not DamageType.UNTYPED
    },
    # -- origins -----------------------------------------------------------
    "shadow": Theme(
        words=("shadow",), drop="natural", dtype="necrotic", resist=("necrotic",),
    ),
    "fey": Theme(words=("fey",), drop="natural", dtype="psychic"),
    "elemental": Theme(words=("elemental",), drop="natural"),
    "aberrant": Theme(words=("aberrant",), drop="natural", dtype="psychic"),
    "immortal": Theme(words=("immortal",), drop="natural", dtype="radiant"),
    "natural": Theme(words=("natural",)),
    # -- creature types whose printed treatment is not in doubt ------------
    "undead": Theme(
        words=("undead",), dtype="necrotic",
        resist=("necrotic",), vulnerable=("radiant",), immune=("poison",),
    ),
    "construct": Theme(words=("construct",), immune=("poison",)),
    "plant": Theme(words=("plant",), vulnerable=("fire",)),
    "demon": Theme(words=("demon", "elemental"), drop="natural", resist=("fire",)),
    "devil": Theme(words=("devil", "immortal"), drop="natural", resist=("fire",)),
    "angel": Theme(words=("angel", "immortal"), drop="natural", resist=("radiant",)),
}


@dataclass(frozen=True)
class Reflavour:
    """A stat block dressed as something else, with the numbers settled."""

    #: What the module calls it. Display only; never written anywhere.
    name: str = ""
    description: str = ""
    add_words: tuple[str, ...] = ()
    drop_word: str = ""
    #: `(from, to)` damage types. `from == ""` retypes everything.
    retype: tuple[tuple[str, str], ...] = ()
    resist: tuple[tuple[str, int], ...] = ()
    vulnerable: tuple[tuple[str, int], ...] = ()
    immune: tuple[str, ...] = ()

    @property
    def mechanical(self) -> bool:
        """Does this change anything a die roll can see?"""
        return bool(
            self.add_words or self.drop_word or self.retype
            or self.resist or self.vulnerable or self.immune
        )

    def __str__(self) -> str:
        bits: list[str] = []
        if self.add_words:
            bits.append("+" + "/".join(self.add_words))
        if self.drop_word:
            bits.append(f"-{self.drop_word}")
        bits += [f"{a or '*'}->{b}" for a, b in self.retype]
        bits += [f"resist {n} {d}" for d, n in self.resist]
        bits += [f"vuln {n} {d}" for d, n in self.vulnerable]
        bits += [f"immune {d}" for d in self.immune]
        return ", ".join(bits) or "cosmetic"


def themed(words: tuple[str, ...], level: int, *, name: str = "") -> Reflavour:
    """Build a reflavour from whatever theme words a module gave.

    Words the table does not know are **ignored rather than guessed at** --
    a module saying "bandit" means something to a reader and nothing to a
    resistance table, and inventing a mechanical consequence for it would be
    worse than leaving the creature as it is. The word still reaches
    `cast_list`, which uses it to pick a better-fitting creature in the first
    place; this is only about what to change afterwards.
    """
    amount = resist_amount(level)
    add: list[str] = []
    drop = ""
    dtype = ""
    resist: dict[str, int] = {}
    vulnerable: dict[str, int] = {}
    immune: list[str] = []
    for word in words:
        theme = THEMES.get(word.strip().lower())
        if theme is None:
            continue
        add += [w for w in theme.words if w not in add]
        drop = drop or theme.drop
        dtype = dtype or theme.dtype
        for d in theme.resist:
            resist[d] = max(resist.get(d, 0), amount)
        for d in theme.vulnerable:
            vulnerable[d] = max(vulnerable.get(d, 0), amount)
        immune += [d for d in theme.immune if d not in immune]
    # A creature cannot be both resistant and vulnerable to one type. The
    # resistance wins, because it is the one the theme that named the creature
    # asked for -- "undead, and also on fire" is a fire-resistant undead, not a
    # contradiction to be resolved by whichever word came last.
    for d in list(vulnerable):
        if d in resist:
            del vulnerable[d]
    return Reflavour(
        name=name,
        add_words=tuple(add),
        drop_word=drop if drop not in add else "",
        retype=((("", dtype),) if dtype else ()),
        resist=tuple(sorted(resist.items())),
        vulnerable=tuple(sorted(vulnerable.items())),
        immune=tuple(immune),
    )


def _dtype(word: str) -> DamageType | None:
    try:
        return DamageType(word)
    except ValueError:
        return None


def apply(world: World, eid: int, flavour: Reflavour) -> int:
    """Lay a reflavour on a creature already on the board. Returns effects laid.

    Called straight after `loader.spawn`, before the encounter starts. Proven
    to survive `Encounter.start()`.
    """
    if not flavour.mechanical:
        return 0
    laid = 0
    cast = Cast(world, eid, REF)

    if flavour.add_words or flavour.drop_word:
        cast.set_origin(
            *flavour.add_words, on=eid, until=When.ENCOUNTER,
            instead_of=flavour.drop_word,
        )
        laid += len(flavour.add_words) + bool(flavour.drop_word)

    if flavour.retype:
        ident = world.get(eid, Ident)
        abilities = loader.load(ident.ref).declared if ident else ()
        for source, target in flavour.retype:
            to = _dtype(target)
            if to is None:
                continue
            frm = _dtype(source) if source else None
            # **One call per ability, naming the ability.** See the module
            # docstring: an unnamed retype speaks only for weapon or implement
            # rows, and a monster's claw is neither.
            for ability in abilities:
                cast.deals(
                    dtype=to, from_=frm, ref=ability, on=eid, until=When.ENCOUNTER,
                )
                laid += 1

    defences = world.get(eid, Defences)
    if defences is not None:
        for word, amount in flavour.resist:
            d = _dtype(word)
            if d is not None:
                defences.resist[d] = max(defences.resist.get(d, 0), amount)
        for word, amount in flavour.vulnerable:
            d = _dtype(word)
            # A creature the database already says resists this keeps the
            # resistance. Writing a vulnerability on top would leave both
            # standing and `resolve.deal_damage` would net them out silently.
            if d is not None and d not in defences.resist:
                defences.vulnerable[d] = max(defences.vulnerable.get(d, 0), amount)
        for word in flavour.immune:
            d = _dtype(word)
            if d is not None:
                defences.immune.add(d)
    return laid


def level_of(world: World, eid: int) -> int:
    """The creature's level, for `resist_amount`. 1 when it has no stats."""
    stats = world.get(eid, Stats)
    return stats.level if stats else 1


@dataclass(frozen=True)
class Wave:
    """Creatures that walk on after the fight has started. #962.

    One per module line rather than one per arrival, because the schedule
    is what the module states -- a fixed number joining at the start of
    every round -- and expanding it into a list of rounds up front would
    have to guess how long the fight runs.

    `worth` is the module's own XP rule and the reason this is not just a
    count: the module counts only its earliest waves toward the reward.
    """

    at: int
    every: int
    until: int
    refs: tuple[str, ...]
    flavour: Reflavour
    worth: bool = True
    name: str = ""

    def due(self, round_now: int) -> bool:
        """Does this wave walk on at the start of `round_now`.

        The same arithmetic `module.FoeSpec.due` states, kept here because
        a `Dressed` outlives the scene it came from and the schedule has
        to survive with it.
        """
        if round_now < self.at:
            return False
        if round_now == self.at:
            return True
        if not self.every:
            return False
        if self.until and round_now > self.until:
            return False
        return (round_now - self.at) % self.every == 0


@dataclass
class Dressed:
    """What a scene's opposition came out as, creature by creature."""

    refs: list[str] = field(default_factory=list)
    flavours: list[Reflavour] = field(default_factory=list)
    #: Lines the caller should print -- a clamp applied, a creature deferred.
    notes: list[str] = field(default_factory=list)
    #: Reinforcements, which are **not** in `refs`: those are the creatures
    #: standing on the board before the first turn. #962.
    waves: list[Wave] = field(default_factory=list)
    #: Creatures on the **party's** side, and their dressing, running
    #: parallel the way `refs` and `flavours` do. Not in `refs` for the
    #: obvious reason and for a second one: `refs` is what the XP award and
    #: the `cleared` tally are written against, and an ally is neither
    #: something the party overcame nor something it killed. #961.
    allies: list[str] = field(default_factory=list)
    ally_flavours: list[Reflavour] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.refs)
