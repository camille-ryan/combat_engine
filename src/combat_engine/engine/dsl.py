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

import contextlib
import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import TYPE_CHECKING, Any

from ._weapon_reach import BY_WEAPON, GIVES
from .cast import Cast
from .grid import Square, area_burst, blast, blast_placements, spread
from .monster_math import NORMAL
from .query import (
    alive,
    allies,
    creatures,
    enemies,
    line_of_effect,
    scenery,
    squares,
    targetable,
)
from .skills import SKILLS
from .triggers import Trigger
from .types import (
    Ability,
    ActionType,
    Condition,
    DamageType,
    Defense,
    Keyword,
    Relation,
    Size,
    Usage,
)

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
    #: The other half of a range line that prints two -- "Melee or Ranged
    #: weapon". Seventy-two rows in PHB1 do, across cleric, ranger, rogue
    #: and warlord, and a row that can only hold one of them is declared
    #: half-right with nothing to say so.
    alt: Range | None = None
    #: "Ranged weapon" -- the range is **the wielded weapon's**, not a
    #: number on the card. 110 rows print it and every one of them was
    #: given an invented fixed size instead: 20 on seventy-four, 10 on
    #: thirty-one, 5 on five. A ranger with a longbow was shooting 10
    #: squares where the weapon reaches 20, and `Weapon.ranged`'s second
    #: number -- the long range -- had no reader anywhere in the tree, so
    #: `resolve._long_range` could charge its -2 only for shots the
    #: targeting had already refused.
    #:
    #: `size` stays as the fallback for a creature holding nothing that
    #: shoots, which is what a monster's improvised throw comes to.
    by_weapon: bool = False
    #: Whose square the range is measured from, when it is not the caster's.
    #: `"companion"` is the shaman's whole attack line -- "Melee spirit 1" --
    #: and 48 of its rows are that and nothing else. `c.strike(from_=)`
    #: already aimed the roll correctly; what refused the row was this
    #: measurement, taken before the body ever ran.
    from_: str = ""

    def __str__(self) -> str:
        mine = {
            "melee": f"Melee {self.size}",
            "ranged": f"Ranged {self.size}",
            "close_burst": f"Close burst {self.size}",
            "close_blast": f"Close blast {self.size}",
            "area_burst": f"Area burst {self.size} within {self.within}",
            "wall": f"Area wall {self.size} within {self.within}",
            "personal": "Personal",
        }[self.kind]
        return f"{mine} or {self.alt}" if self.alt else mine

    def branch(self, which: int) -> Range:
        """One branch on its own. 0 is this range, 1 is the other.

        Branch 0 drops `alt`, so the thing handed round afterwards is a
        plain single range and nothing downstream has to keep remembering
        that it might be half of a pair.
        """
        if which and self.alt:
            return self.alt
        return (
            Range(
                self.kind,
                self.size,
                self.within,
                by_weapon=self.by_weapon,
                from_=self.from_,
            )
            if self.alt
            else self
        )

    @property
    def branches(self) -> tuple[int, ...]:
        return (0, 1) if self.alt else (0,)


def Melee(n: int = 1, *, by_weapon: bool = False, from_: str = "") -> Range:
    """`by_weapon` for a row the compendium does not list, which is `mba`.

    The melee branch of `_reach_of` decides by `BY_WEAPON`, a set
    `scripts/reaches.py --emit` derives from the compendium -- so an
    **engine-declared** row can never be in it however plainly its reach is the
    weapon's. `Ranged` has taken this argument all along for the same reason.
    """
    return Range("melee", n, by_weapon=by_weapon, from_=from_)


def Ranged(n: int, *, by_weapon: bool = False, from_: str = "") -> Range:
    return Range("ranged", n, by_weapon=by_weapon, from_=from_)


def CloseBurst(n: int, *, from_: str = "") -> Range:
    return Range("close_burst", n, from_=from_)


def CloseBlast(n: int, *, from_: str = "") -> Range:
    return Range("close_blast", n, from_=from_)


def AreaBurst(n: int, within: int) -> Range:
    return Range("area_burst", n, within)


def Wall(n: int, within: int) -> Range:
    """"Area wall 5 within 10": `n` squares of barrier, laid within `within`.

    Its own kind rather than an area burst, because what it covers is not a
    template -- the caster picks a run of contiguous squares, which is the
    printed rule -- and because what it leaves behind stops movement and
    line of effect where a burst leaves nothing at all. `c.wall` raises it.
    """
    return Range("wall", n, within)


def MeleeOrRanged(melee: int = 1, ranged: int = 10, *, by_weapon: bool = False) -> Range:
    """"Melee or Ranged weapon" -- one printed line, two ways to use it.

    The two branches disagree about more than distance: whether using it
    provokes, which weapon it rolls, and often which ability attacks. Each
    is offered as its own option, so picking one is a thing the player does
    rather than something decided at declaration time.

    `by_weapon` lands on the **ranged half alone**. Only that half is the
    weapon's range; putting it on the melee half too would send
    `_reach_of` to `Gear.ranged` for a swing, and a ranger holding a
    longbow would reach forty squares with a sword.
    """
    return Range("melee", melee, alt=Range("ranged", ranged, by_weapon=by_weapon))


PERSONAL = Range("personal", 0)


@dataclass(frozen=True)
class Augment:
    """One printed "Augment N" clause, declared in the header.

    A psionic at-will prints its base effect and then one or two augments:
    spend that many power points **as you use it** and you get the
    augmented form instead. Most of those clauses are a different die or an
    extra rider and the body can say them on its own, asking
    `content.powers.augment.augment` how many points went. That is the
    older, body-side arrangement and it stays exactly as it was.

    This is for the clauses a body *cannot* say, which is every one that
    rewrites the header: a close burst where the base is a melee swing, a
    second target, a longer reach, a charge. **Targeting happens before the
    body runs**, so by the time a body could choose, the targets are
    already picked -- which is why twenty-nine of these were recorded in
    `docs/blocked.json` rather than written.

    So the spend is settled *before* targeting, the same way `branch`
    settles which half of a "Melee or Ranged" line is in play, and each
    affordable augment is offered as its own entry in the action menu.
    Picking one is then something the player does, and something a policy
    scores, rather than something the body decides after the fact.

    Every field left `None` falls through to the base row's, so an augment
    that only widens the burst names only `reach`.
    """

    #: Power points this form costs. 0 is legal: a handful of rows print
    #: "Augment 0", a free alternative form.
    cost: int
    reach: Range | None = None
    target: Target | None = None
    attack: Attack | None = None
    damage: Damage | None = None
    #: "You can shift and then charge, using this power in place of the
    #: charge's melee basic attack" -- the augmented form *is* a charge
    #: where the base is a standing swing. Read before the body, like the
    #: header field it shadows.
    charges: bool | None = None


@dataclass(frozen=True)
class Summon:
    """A creature a power puts on the board, defined by the power itself.

    Thirty-six rows across wizard, druid, invoker, psion and artificer
    print a stat block inline -- speed, defences, an attack line -- and give
    it no compendium id, so `c.summon(ref)` had nothing to name and every
    one of them was left out of the tree.

    It is spawned as a `Companion`, which is exactly the right shape and
    was built for the shaman: targetable, takes no turn, no vote on whether
    the fight is over. A 4e summon acts only when its summoner spends an
    action commanding it, so having no initiative slot is the rule rather
    than a simplification.

    The numbers default to the summoner's, because that is what most
    printed blocks say -- "its defences equal yours" -- and `defences` is an
    offset from them rather than an absolute, so a block printing "your
    defences +2" is `defences=2`.
    """

    #: Hit points. 0 means the summoner's healing surge value, which is the
    #: commonest printed line by a wide margin.
    hp: int = 0
    speed: int = 6
    #: Added to each of the summoner's defences. A block printing "+2 to
    #: AC and Fortitude" is not this -- pass `per_defence` instead, or
    #: Reflex and Will come out two too high, which happened to five rows.
    defences: int = 0
    #: One offset per defence, by name: `{"ac": 2, "fort": 2}`. Overrides
    #: `defences` for the ones it names.
    per_defence: dict[str, int] | None = None
    #: Large creatures arrive Large. Two druid blocks print one and both
    #: were spawned Medium, which is a square of footprint and a reach.
    size: str = "medium"
    #: Its own attack, for a block that prints one. Without it the summon
    #: rolls whatever row commands it, the way a conjuration does.
    attack: Attack | None = None
    damage: Damage | None = None
    #: Movement modes with their own speeds -- `{"fly": 6, "climb": 3}`.
    #: A bare tuple of names could not say "speed 0, fly 6", which three
    #: blocks print, and they had to correct it by hand in the body.
    modes: dict[str, int] | None = None
    #: What the creature does on a round nobody gave it an order -- the
    #: printed Instinctive Effect. Ten blocks print one and each prints a
    #: different priority list, so it is the block's own code rather than a
    #: flag: handed the cast driving it and the creature's id.
    #:
    #: `Cast.instinctive` is the only caller, and it rebinds the cast to
    #: the ref that did the summoning first, so `c.command` inside here
    #: reads this block's attack line and not the row spending the action.
    instinctive: Callable[[Cast, int], None] | None = None
    label: str = ""



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
    #: A printed target line naming what the creature must have in hand:
    #: "one creature wielding a magic weapon or implement". Filtered through
    #: `query.holding`, so `"magic"` means an enhancement bonus and anything
    #: else is a weapon group or property. Without it the row is aimed at
    #: creatures that have nothing for it to do anything to.
    holding: str = ""
    #: The two clauses an object target line prints on top of its side.
    #: `max_size` is "Medium or smaller"; `loose` is "not fastened in place
    #: or held by a creature". Fields rather than sides of their own,
    #: because they are two restrictions on one pool and not two pools.
    max_size: Size | None = None
    loose: bool = False
    #: A printed target line narrowed by how the creature stands **to the
    #: caster**: "one creature grabbed by it", "the creature marked by you".
    #: Measured outward from the caster -- `holds(relation, actor, target)` --
    #: because every one of these is asymmetric. "Grabbed by it" is not
    #: "grabbed", which is exactly the distinction a `Condition` cannot draw,
    #: and why these rows could not be written against `Conditions`.
    #:
    #: `HIDDEN_FROM` is the exception and is routed through `query.unseen_by`
    #: rather than read off the triple -- see `_stands_right`. Sight has two
    #: more inputs than the relation carries.
    relation: Relation | None = None
    #: Inverts `relation`. Three rows print the opposite -- "one creature
    #: **not** grabbed by it", "one creature that **can see** it" -- and
    #: without this they would silently become their own opposite, which is
    #: worse than being unwritten.
    without: bool = False
    #: "One creature granting combat advantage to it." Deliberately **not** a
    #: `relation` value, for two independent reasons. `Relation.GRANTS_CA_TO`
    #: is stored with its arguments the other way round (`query.py` reads
    #: `holds(GRANTS_CA_TO, target, attacker)`), so routed through the field
    #: above it is inverted and still returns a bool. And the stored relation
    #: is not the whole answer: flanking is computed and never stored, so only
    #: `query.has_combat_advantage` folds in the grant, the geometry and the
    #: clauses that suppress both.
    grants_ca: bool = False
    #: "One creature flanked by it", "one enemy it is flanking". **Narrower
    #: than `grants_ca` and not a spelling of it**: a prone or dazed creature
    #: grants combat advantage without being flanked, so a row that prints
    #: flanking and filters on combat advantage accepts targets its card
    #: refuses.
    flanked: bool = False
    #: A printed target line narrowed by what the creature is **suffering**:
    #: "one dazed creature", "any creature that is immobilized, stunned or
    #: unconscious".
    #:
    #: **Any of them, not all of them.** The printed line is a list of
    #: alternatives, and this is a set rather than a single `Condition` because
    #: 33 of the 62 rows that wanted it name two or more -- nine name four. A
    #: one-condition field would have been wrong for over half of them, and
    #: wrong in the direction that refuses legal targets.
    conditions: frozenset[Condition] = frozenset()
    #: "One bloodied creature", and the two rows printing the opposite.
    #:
    #: Tri-state on purpose: the field has to tell "must be bloodied" from
    #: "must not be" from "the card does not say". A bool can hold two of
    #: those, and the rows printing *nonbloodied* would have been unwritable --
    #: or worse, written as the thing they are not.
    bloodied: bool | None = None
    #: The negative of `conditions`: a creature carrying **any** of these is
    #: refused. "One creature that is not grabbed", "blinded creatures are
    #: immune".
    #:
    #: Its own field rather than `without` reused, because `without` inverts
    #: `relation` and the two are different sentences. "Not grabbed *by it*" is
    #: the relation inverted and a creature held by somebody else passes it;
    #: "not grabbed" is this, and that creature does not. Three rows print the
    #: negative of a condition and one of them was nearly written as the other.
    conditions_without: frozenset[Condition] = frozenset()
    #: "One creature able to take actions", and its negative.
    #:
    #: Not expressible as `conditions_without`, which is why it is its own
    #: field: being able to act is not the absence of a fixed list. `query.
    #: can_act` folds in consciousness, every condition whose rules say
    #: `cannot_act`, and the exemption that lets a trap or a conjuration act at
    #: all -- so naming a set here would be guessing at something the engine
    #: already answers.
    can_act: bool | None = None
    #: A printed target line narrowed by the creature's **type words**: "each
    #: undead creature in the burst", "one living humanoid", "a beast or magical
    #: beast ally". Any of them, like `conditions`.
    #:
    #: Read through `query.kinds_of`, which was lifted off `Cast` for this --
    #: while it lived there the only place to ask was the body, so the row was
    #: offered against creatures it would then decline.
    #:
    #: **Any-of, so it cannot say "living humanoid".** That is a conjunction and
    #: this set accepts either word, which would take an undead humanoid and a
    #: living beast -- both of which such a card refuses. Those rows stay marked.
    #:
    #: **And a positive word matches no player character.** `kinds_of` is empty
    #: for one: a character has no stat block, and its race is not on the board
    #: at all -- `chargen` reads `race.speed` and `race.size` and stores neither
    #: the race nor its words. So `kinds={"humanoid"}` aimed at a party yields an
    #: empty pool and the row is never offered. Measured on a live board: every
    #: character answers `[]` where every monster answers four or more words.
    #: Safe aimed at monsters, which is what the ally rows do; for a row a
    #: monster aims at the party, only `kinds_without` behaves.
    kinds: frozenset[str] = frozenset()
    #: The negative: "nonplant creatures in the burst", "not elemental". Five of
    #: the thirty rows print it, so it is not an afterthought.
    kinds_without: frozenset[str] = frozenset()
    #: "One creature taking ongoing damage", with no type named. One row.
    ongoing: bool = False
    #: "One creature taking ongoing **poison** damage". Seven of the eight rows
    #: name a type, so the untyped form above is the rare one -- and filtering
    #: without the type would accept a creature alight from the wrong source.
    ongoing_types: frozenset[DamageType] = frozenset()

    def __str__(self) -> str:
        if self.label:
            return self.label
        if self.side == "self":
            return "You"
        who = {
            "enemy": "creature", "ally": "ally", "any": "creature",
            "other": "creature", "other_ally": "ally", "object": "object",
        }[self.side]
        if self.everyone:
            return f"Each {who} in the area"
        return f"One {who}" if self.count == 1 else f"Up to {self.count} {who}s"


ONE_CREATURE = Target("enemy", 1)
#: A power aimed at anybody at all. `ONE_CREATURE` is the *enemy* pool, so a
#: beneficial row pointed at it is unusable on the only creatures it is ever
#: meant for.
ANY_CREATURE = Target("any", 1)
ONE_ALLY = Target("ally", 1)
#: "One ally" where the printed line excludes you. `ONE_ALLY`'s pool
#: includes the caster, which reads as "you or one ally" -- right for most
#: rows and wrong for the ones that say otherwise.
ONE_OTHER_ALLY = Target("other_ally", 1)
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


class Pick(Enum):
    """An attack line that names no ability, only how to choose one.

    A class row names its ability, because a class has one. **A theme does
    not know which class took it**, so its printed line says "Primary
    ability vs. AC" or "Highest ability modifier vs. Will" -- a rule for
    picking rather than a pick. That cannot be written as an `Ability` in a
    header, because the header is data evaluated at import and the answer
    depends on who is holding the row.

    So the header says the rule and `Attack.ability_for` answers it per
    caster. Kept out of `Ability` itself deliberately: that enum is the six
    scores, and a seventh member would appear in every loop over it and
    every score table in the game.

    `PRIMARY` reads the character's build. `HIGHEST` reads the sheet, and
    is also what `PRIMARY` falls back to for a creature with no build --
    which is the honest answer rather than a raise, since a monster or a
    companion holding such a row has no class to have a primary of.
    """

    PRIMARY = "primary"
    HIGHEST = "highest"
    #: What is in hand decides. The ranged basic attack is Dexterity with a
    #: bow or a light thrown weapon and **Strength with a heavy thrown
    #: one** -- one row, two abilities, chosen by the weapon rather than by
    #: the class or the sheet.
    BY_WEAPON = "by_weapon"


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

    #: A character's line names an ability. A monster's does not. A theme's
    #: names a `Pick` -- the rule for choosing one, resolved per caster.
    #:
    #: **A tuple is a printed choice between named abilities** -- "Charisma
    #: or Constitution vs. Reflex", "Strength, Constitution, or Dexterity".
    #: Resolved to whichever of them this creature is best at, which is the
    #: pick a player makes and the only one that can be made without asking
    #: mid-roll. Writing one of them and dropping the rest was worth up to
    #: four points of attack on the wrong character.
    ability: Ability | Pick | tuple[Ability, ...] | None = None
    vs: Defense = Defense.AC
    plus: int = 0
    #: A monster's finished attack bonus, level included, as printed.
    printed: int | None = None
    #: Who rolls it, when it is not the creature using the row. `"companion"`
    #: is a ranger's beast: the printed line is "Beast's attack bonus vs.
    #: AC", which is the beast's numbers and not its owner's. `from_=` on
    #: `c.strike` moves only the square the swing is measured from, so a row
    #: written with it looked finished and rolled the ranger.
    by: str = ""

    def bonus_for(self, world: World, actor: int, ref: str = "", branch: int = 0) -> int:
        """The bonus to roll with, under whatever scaling is in force.

        `branch` reaches `_attack_bonus`, which needs it to know whether the
        weapon it should take proficiency from is the one in hand or the one
        being fired.
        """
        from .cast import Cast
        from .components import Stats

        actor = roller(world, actor, self.by)
        if self.printed is not None:
            stats = world.get(actor, Stats)
            return world.scaling.trim(self.printed, stats.level if stats else 1)
        if self.ability is None:
            raise ValueError("an Attack needs either an ability or a printed bonus")
        # `ref` matters: proficiency applies to a weapon power and not to an
        # implement one, and `_attack_bonus` reads the keywords off it.
        probe = Cast(world=world, me=actor, ref=ref, branch=branch)
        return probe._attack_bonus(self.ability_for(world, actor, ref)) + self.plus

    def ability_for(self, world: World, actor: int, ref: str = "") -> Ability:
        """Which ability this line rolls, for this caster.

        A named one answers itself. A `Pick` is the theme case -- see its
        docstring -- and is resolved here rather than at declaration,
        because the header is data and the holder is not known then.

        `ref` is which row this line belongs to, and is only needed for the
        `c.rolls_with` override: without it a swap laid on a named row is
        silently not applied, so every caller that knows its ref passes it.
        """
        from .components import Build, Powers, Stats

        who = roller(world, actor, self.by)
        # **Before the header is read at all.** "You may use Dexterity
        # instead of Strength with this power" is a feat reaching into a row
        # it does not own, so it cannot be a header edit -- the header is
        # one object shared by everyone who ever holds the row.
        if ref:
            known = world.get(who, Powers)
            for ability, when in (known.rolls.get(ref, ()) if known else ()):
                if when is None or when(world, who):
                    return ability
        if isinstance(self.ability, Ability):
            return self.ability
        if self.ability is None:
            raise ValueError("an Attack needs either an ability or a printed bonus")
        if isinstance(self.ability, tuple):
            stats = world.get(who, Stats)
            if stats is None:
                return self.ability[0]
            return max(self.ability, key=stats.mod)
        if self.ability is Pick.BY_WEAPON:
            from .components import Gear

            gear = world.get(who, Gear)
            heavy = bool(gear) and any(
                "heavy thrown" in prop
                for w in gear.held
                for prop in w.properties
            )
            return Ability.STR if heavy else Ability.DEX
        if self.ability is Pick.PRIMARY:
            held = world.get(who, Build)
            for choice in held.choices if held else ():
                if choice.startswith("primary:"):
                    with contextlib.suppress(ValueError):
                        return Ability(choice.split(":", 1)[1])
            # No build, so no primary. Falls through to the sheet.
        stats = world.get(who, Stats)
        if stats is None:
            return Ability.STR
        return max(Ability, key=stats.mod)

    def __str__(self) -> str:
        if self.printed is not None:
            return f"{self.printed:+d} vs. {self.vs.value.upper()}"
        tail = f" {self.plus:+d}" if self.plus else ""
        if isinstance(self.ability, Pick):
            # As the card prints it, so the page and the audit both read the
            # rule rather than a resolved guess that is only true for one
            # character.
            name = {
                Pick.PRIMARY: "Primary ability",
                Pick.HIGHEST: "Highest ability modifier",
                Pick.BY_WEAPON: "Strength or Dexterity",
            }[self.ability]
        elif isinstance(self.ability, tuple):
            names = [a.value.title() for a in self.ability]
            if len(names) == 1:
                name = names[0]
            else:
                # "Strength, Constitution, or Dexterity" is how the card
                # prints three; two get no comma.
                join = ", " if len(names) > 2 else " "
                name = f"{', '.join(names[:-1])}{join}or {names[-1]}"
        else:
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
    #: The blow's type, or **a list of them** for the 88 rows printing one
    #: roll that is several -- "2d6 + 5 cold and necrotic damage". Written as
    #: one field rather than a scalar plus a second list, on Camille's call
    #: that two keywords is messy: an author says `dtype=[COLD, NECROTIC]`
    #: and `__post_init__` splits it.
    dtype: DamageType | Sequence[DamageType] = DamageType.UNTYPED
    #: The whole type, derived -- never written by an author. Empty is the
    #: ordinary case and means "just `dtype`".
    #:
    #: **The scalar cannot simply go away.** 172 sites read `.dtype` and
    #: expect one type, across 13 in the engine, 155 in content and 3 in the
    #: policy, and `resolve.deal_damage`'s own docstring states the
    #: invariant: `dtype` stays the blow's primary type, which is what the
    #: events carry and what every existing reader asks about. Making the
    #: field genuinely polymorphic would turn all 172 into "might be one,
    #: might be many"; normalising here gets the tidy call site for nothing.
    dtypes: tuple[DamageType, ...] = ()
    #: `normal`, `limited` (encounter or recharge) or `minion`. MM3 scales
    #: the three differently.
    kind: str = NORMAL
    #: Half on a miss, which most weapon dailies say.
    half_on_miss: bool = False

    def __post_init__(self) -> None:
        """Split a list of types into the primary plus the whole set.

        Duplicates are dropped and order is kept, so `[COLD, COLD]` is one
        type and `[FIRE, NECROTIC]` keeps fire as the primary -- the card
        prints the types in an order and the first of them is the one every
        scalar reader will see. An empty list means untyped rather than
        raising: a row that computes its own list should not explode on a
        board where the list comes out empty.
        """
        if isinstance(self.dtype, DamageType):
            return
        types = tuple(dict.fromkeys(self.dtype)) or (DamageType.UNTYPED,)
        object.__setattr__(self, "dtypes", types)
        object.__setattr__(self, "dtype", types[0])

    def __str__(self) -> str:
        tail = "" if not self.bonus else f" + {self.bonus}"
        # **A comma join with a final "and", because that is what the card
        # prints** -- "acid, cold, fire, lightning, and poison damage", not
        # four "and"s. `cards.py` compares this string against the printed
        # line, and two of the 88 rows name five types.
        kinds = [
            k.value for k in (self.dtypes or (self.dtype,))
            if k is not DamageType.UNTYPED
        ]
        if not kinds:
            kind = ""
        elif len(kinds) == 1:
            kind = f" {kinds[0]}"
        elif len(kinds) == 2:
            kind = f" {kinds[0]} and {kinds[1]}"
        else:
            kind = " " + ", ".join(kinds[:-1]) + f", and {kinds[-1]}"
        return f"{self.dice}{tail}{kind} damage"


@dataclass(frozen=True)
class Swap:
    """The power a feat takes back in exchange for the card it hands over.

    Printed as "you can swap one of your 3rd-level **or higher** encounter
    attack powers for this one", so `level` is a floor and not a match.
    `utility` is the other half of the sentence and `Usage` alone cannot
    say it: a 3rd-level encounter *attack* power and a 2nd-level *utility*
    are both `ENCOUNTER`, and the printed line always distinguishes them.
    """

    level: int
    #: `None` for a utility, which is the one the printed line does not
    #: narrow: "one 6th-level or higher utility power" takes an at-will,
    #: an encounter or a daily, and only the attack lines name a usage.
    usage: Usage | None = None
    utility: bool = False


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
    #: The other branch's attack and damage, for a `MeleeOrRanged` row whose
    #: two halves differ -- "Strength vs. AC (melee) or Dexterity vs. AC
    #: (ranged)". Left unset when both branches roll the same line, which is
    #: every rogue row and no ranger one.
    attack_alt: Attack | None = None
    damage_alt: Damage | None = None
    #: A printed Requirement line, as a predicate on the caster.
    requires: Callable[[World, int], bool] | None = None
    requires_text: str = ""
    #: This row *is* a charge: it runs at somebody and then swings. Its
    #: reach is therefore reach plus speed when asking whether anybody can
    #: be caught -- measuring the melee reach before the run refused every
    #: such row in exactly the situation it exists for.
    charges: bool = False
    #: This row reaches at range but is not *fired*: it hurls something off
    #: the weapon in hand. The ranged gate below asks for a bow, which is
    #: right for an arrow and wrong for a paladin throwing radiance five
    #: squares with a longsword -- that row could never be used at all.
    thrown_by_hand: bool = False
    #: The second branch's Requirement. A dual row's printed one is usually
    #: the two joined by "or" -- "two melee weapons **or** a ranged weapon"
    #: is the melee branch's requirement and the ranged branch's, and
    #: checking it whole says yes to both when only one is true.
    requires_alt: Callable[[World, int], bool] | None = None
    #: A printed Trigger line. Set for immediate and opportunity actions.
    trigger: str = ""
    #: The same line in a form the dispatcher can act on. With it the row is
    #: offered when its trigger happens; without it `trigger` is prose and
    #: nothing reads it. See `engine/triggers.py`.
    on: Trigger | Sequence[Trigger] | None = None
    recharge: int = 0
    #: The printed "Recharge when ..." condition, in a form the dispatcher
    #: can act on -- `recharge` is the die half and this is the sentence.
    #:
    #: **440 cards print a condition and no die**, and for those `recharge=0`
    #: is the honest declaration, so this is the only thing that can give the
    #: row back. 204 of them carried `dropped=("Usage.RECHARGE(when=)",)`
    #: because there was nowhere to say it, and 169 more armed a watcher by
    #: hand from the body -- which works, and cannot be read by the wire or
    #: the policy without running the row. Header is data. #449, #488.
    recharge_when: Trigger | Sequence[Trigger] | None = None
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
    #: A creature this row puts on the board, defined here because the
    #: printed block gives it no compendium id. Header data, so the card
    #: can show what you are about to summon without running the body.
    summon: Summon | None = None
    #: What this row could not say, as the symbols it wanted.
    #:
    #: The old rule was that an unwritable row is left out entirely, and the
    #: reason was sound: an absence is counted and a half-row looks
    #: finished. But items and feats are four thousand rows against an
    #: engine that has never met either, so the absences would be the
    #: majority and the reason for each would live nowhere.
    #:
    #: So a row may now be written with the gap declared -- `todo=("c.deals
    #: ()",)`. Symbols, never prose: the same grammar `docs/blocked.json`
    #: uses, so `scripts/blocked.py` reads it with the parser it already
    #: has, and `power()` refuses anything that parser could not read.
    #:
    #: `usable` refuses such a row outright, which is the whole safety of
    #: the arrangement: it is exactly as inert in play as the absence it
    #: replaced, and says what it is waiting for.
    todo: tuple[str, ...] = ()
    #: A clause of this row that could not be written, where the rest of
    #: it could.
    #:
    #: The common case, and `todo=` was the wrong tool for it. A feat
    #: reading "+2 damage on a charge and +2 to bull rush attempts" has a
    #: first half the engine can say and a second half it cannot; marking
    #: the row `todo` refuses the whole thing in play and throws the
    #: working half away, so an author is pushed towards dropping the
    #: clause quietly in a docstring instead -- which is the silently-false
    #: failure this project exists to hunt, wearing a comment.
    #:
    #: So: `todo` means *nothing* here works and the row is refused.
    #: `dropped` means the row works and one named thing is missing. Both
    #: are symbols, both count as partial, both hold an issue open, both
    #: go red when the symbol arrives. Only `todo` makes the row inert.
    dropped: tuple[str, ...] = ()
    #: A clause of this row that is not absent -- it has no combat meaning
    #: at all. The per-clause form of `out_of_combat`.
    #:
    #: `dropped` was being used for this and is wrong about *why*. "+5 to
    #: pick a lock" is not waiting on `c.skill_circumstance()`; nothing
    #: ever rolls Thievery in a fight, so that verb would be a mechanism
    #: nobody passes a purpose to, and a marker naming a symbol that must
    #: never be built sits in the queue forever. The marker grammar exists
    #: to stop exactly that.
    #:
    #: **Not a symbol, because there is no symbol.** An element is
    #: `skill:<name>` for one of the seventeen skills -- the same key
    #: `c.bonus` takes -- naming the skill whose *circumstance* is the
    #: narrative part. That is a closed vocabulary the guard checks against
    #: the engine's own table, so prose, an invented skill and a wishful
    #: verb are all refused at import, and a new kind of narrative clause
    #: costs an edit here rather than a sentence inline.
    #:
    #: The token says which skill; the body's docstring says why that
    #: narrowing has nothing to do with a fight, and `power()` refuses the
    #: row without one. Naming a skill the engine does consult is fine and
    #: common -- `skill:perception` -- because the claim is about the
    #: circumstance, never about the skill.
    #:
    #: Counted done, never red, and **audited like any other finished
    #: row**: a `dropped` row is exempt from the audit's run, so a row that
    #: claimed this and then did nothing in a fight would be caught silent.
    #: `scripts/todo.py` names these rows so the set stays readable.
    narrative: tuple[str, ...] = ()
    #: **A row the rules have superseded. Never offered, and not waiting.**
    #:
    #: The fourth marker, and the three before it could not say this. `todo=`
    #: means "nothing works yet", so `scripts/todo.py` reports the row ready the
    #: moment the symbol it names arrives -- which is exactly wrong for a row that
    #: will never be wanted, however much of the engine gets written. `dropped=`
    #: and `narrative=` both claim the row plays.
    #:
    #: The value is the reason, in plain words, because that is the only thing a
    #: later reader needs and there is no symbol to wait for.
    #:
    #: Refused by `usable`, like `todo=`, and excluded from every chargen draw --
    #: Camille's instruction being that an obsolete option is offered neither to a
    #: player nor to the dealer.
    obsolete: str = ""
    #: **We are not building this.** Not unfinished, not superseded, not a
    #: gap in the source -- a decision that the mechanism is out of scope.
    #:
    #: The sixth marker, and the five before it all say something false.
    #: `todo=` and `dropped=` name a symbol, so `todo.py` reports the row
    #: ready the moment that symbol lands -- exactly wrong for a row nobody
    #: intends to finish. `narrative=` claims it plays. `defect=` blames the
    #: compendium, which has the page. `obsolete=` is the closest and is the
    #: one worth keeping clean: that row was **retired by a rules change**,
    #: and writing a scope decision into it would blur the single word
    #: carrying that argument.
    #:
    #: The value is the reason in plain words, as `obsolete=` is and for the
    #: same reason -- there is no symbol to wait for, ever. Say whose call it
    #: was and when, because the next reader's question is "can this be
    #: revisited" and nothing else in the row answers it.
    #:
    #: Refused by `usable` and excluded from every chargen draw, exactly as
    #: `obsolete=` is: a declined option is offered neither to a player nor
    #: to the dealer.
    declined: str = ""
    #: The row cannot be written because **the compendium is missing what it
    #: would be written from**. Not a gap in this engine: a gap in the source.
    #:
    #: The fifth marker, and the four before it all say the wrong thing here.
    #: `todo=` and `dropped=` name a symbol and so promise that somebody coming
    #: back with that symbol finishes the row -- and nobody can, because the
    #: sentence the row needs is not in the data. 30 rows carried
    #: `todo=("etl.monster.attack_defence()",)`, which told every reader to go
    #: and write a parser for text that is blank in both HTML dialects as
    #: shipped. `obsolete=` is the closest and still wrong: that row was retired
    #: by a rules change and this one was never imported properly.
    #:
    #: The value is the reason in plain words, as `obsolete=` is and for the same
    #: reason -- there is no symbol to wait for. **Plain words about the defect,
    #: never the card's own prose**: the one rule is unchanged here, and the
    #: whole point is that the prose is what is missing.
    #:
    #: Refused by `usable`, like `todo=` and `obsolete=`, so the row is as inert
    #: in play as an absence and says why.
    #:
    #: **The procedure, which is Camille's and is the reason this exists.** An
    #: authoring agent that cannot parse a printed line does not guess and does
    #: not invent: it refers the line back to the main session, which may read
    #: the compendium. If the compendium has it, the main session says what it
    #: says and the row gets written. If the compendium does not, the row is
    #: flagged here. Measured when this landed: blank attack defences run 5-11x
    #: the corpus rate of 0.86% in Dragon and Dungeon magazine imports, so the
    #: defect is concentrated in the periodicals rather than scattered. #360.
    defect: str = ""
    #: Base items this row lets a character carry, by weapon ref --
    #: `("w3607",)`. **Build-time data, never run.** "You gain
    #: proficiency with all hammers" cannot be a body: a `Cast` opens on a
    #: board with the gear already in hand, so the sentence has no moment
    #: to happen in. `chargen.proficiency` reads this when the character is
    #: made, and one ref stands for a whole printed group the way
    #: `chargen._arms` deals one weapon per proficiency line.
    proficiency: tuple[str, ...] = ()
    #: What taking this row costs, for a feat printed "you can swap one of
    #: your 3rd-level or higher encounter attack powers for this one". The
    #: card is handed over by the body; this is the half that goes back,
    #: and `chargen.power_swap` is what applies it.
    swap: Swap | None = None
    #: The printed "Augment N" clauses this row honours by rewriting its
    #: own header -- a wider burst, a second target, a longer reach. The
    #: spend is settled before targeting and each affordable one is a
    #: separate entry in the action menu. See `Augment`.
    #:
    #: **Not every augment belongs here.** One that only changes the dice
    #: or adds a rider is said in the body, through
    #: `content.powers.augment.augment`, and declaring it in both places
    #: would offer it twice. A row that declares any augment here declares
    #: *all* of them here, because the choice is then made once, before the
    #: body, and `Cast.augment` is what the body reads.
    augments: tuple[Augment, ...] = ()

    @property
    def unfinished(self) -> tuple[str, ...]:
        """Everything this row is waiting for, whichever way it is waiting."""
        return self.todo + self.dropped

    @property
    def is_attack(self) -> bool:
        return self.is_attack_at(0)

    def is_attack_at(self, augment: int = 0) -> bool:
        """Does *this form* aim at somebody? An augment can add a target
        line where the base card has none, and one does."""
        aim = self.target_of(augment)
        return aim.side != "self" or aim.count > 0

    # -- one branch of a two-branch row -------------------------------------
    #
    # A row printing "Melee or Ranged weapon" is two ways of using one power,
    # and they disagree about four independent things: how far it reaches,
    # whether it provokes, which weapon it rolls, and often which ability
    # attacks. Each of those is asked at a different place, so each asks by
    # branch rather than reading the header directly.

    @property
    def branches(self) -> tuple[int, ...]:
        return self.reach.branches

    @property
    def triggers(self) -> tuple[Trigger, ...]:
        """Every printed Trigger this row answers, as a tuple.

        A `Trigger` names one event class, and several printed lines name
        more than one thing -- "pushed, pulled, slid, **or knocked prone**"
        is a `ForcedMove` and a `ConditionApplied`. Declaring one of them
        left the row looking finished and quietly missing the rest, which is
        worse than leaving it out.

        `on=` therefore takes one or a sequence, and everything that reads it
        goes through here so neither form is special.
        """
        if self.on is None:
            return ()
        return (self.on,) if isinstance(self.on, Trigger) else tuple(self.on)

    @property
    def recharges(self) -> tuple[Trigger, ...]:
        """Every printed condition that gives this row back, as a tuple.

        Same shape as `triggers` and for the same reason: a card prints
        *"Recharge when the m4356 takes cold **or** fire damage"*, which is
        two event classes, and declaring one of them leaves the row looking
        finished while quietly missing half the sentence.

        **A condition, not a die.** 440 cards print "Recharge when ..." with
        no threshold at all, and `recharge=0` is the honest declaration for
        them -- so this is the only thing that can give those rows back. One
        card prints both (`m4356a2`: "recharge 6, **or** recharges when ...")
        and keeps its number as well as this. #449, #488.
        """
        if self.recharge_when is None:
            return ()
        return (
            (self.recharge_when,)
            if isinstance(self.recharge_when, Trigger)
            else tuple(self.recharge_when)
        )

    # -- one augment of an augmentable row ----------------------------------
    #
    # Same shape as a branch, one layer out: a printed "Augment 2" that
    # swaps the melee swing for a close burst disagrees with the base row
    # about reach, about who is caught and sometimes about what is rolled.
    # Everything that asks the header a targeting question therefore asks
    # it *of the form being used*, and `augment=0` -- the base card -- is
    # what every non-psionic row in the tree gets without asking.

    @property
    def augment_costs(self) -> tuple[int, ...]:
        """Every form of this row, cheapest first. `(0,)` for almost all."""
        return (0, *sorted({a.cost for a in self.augments if a.cost}))

    def augment_at(self, cost: int) -> Augment | None:
        """The declared clause bought with that many points, if there is one."""
        if not cost:
            return None
        for a in self.augments:
            if a.cost == cost:
                return a
        return None

    def reach_of(self, branch: int = 0, augment: int = 0) -> Range:
        bought = self.augment_at(augment)
        if bought is not None and bought.reach is not None:
            return bought.reach.branch(branch)
        return self.reach.branch(branch)

    def target_of(self, augment: int = 0) -> Target:
        bought = self.augment_at(augment)
        if bought is not None and bought.target is not None:
            return bought.target
        return self.target

    def charges_of(self, augment: int = 0) -> bool:
        bought = self.augment_at(augment)
        if bought is not None and bought.charges is not None:
            return bought.charges
        return self.charges

    def attack_of(self, branch: int = 0, augment: int = 0) -> Attack | None:
        bought = self.augment_at(augment)
        if bought is not None and bought.attack is not None:
            return bought.attack
        return self.attack_alt or self.attack if branch else self.attack

    def damage_of(self, branch: int = 0, augment: int = 0) -> Damage | None:
        bought = self.augment_at(augment)
        if bought is not None and bought.damage is not None:
            return bought.damage
        return self.damage_alt or self.damage if branch else self.damage

    def requires_of(self, branch: int = 0) -> Callable[[World, int], bool] | None:
        """The Requirement gating one branch, and **no fallback between them**.

        This used to read `self.requires_alt or self.requires` for the
        ranged branch, so a dual-range row whose printed Requirement gates
        only the melee half -- "you must be wielding a light blade" -- also
        gated the half you throw, which the card does not say. Silently: the
        branch was simply never offered, indistinguishable from a row that
        does not have one.

        No row in the tree depended on the fallback. The seeker's six all
        carried a hand-written always-true predicate to defeat it, which is
        the tell that it was working against its authors rather than for
        them. A Requirement that really does gate both branches is written
        on both.
        """
        return self.requires_alt if branch else self.requires

    def can_branch(self, world: World, actor: int, branch: int = 0) -> bool:
        """Is this branch open to this creature, given what it is holding?

        Two gates. The row's own Requirement for that branch, and the plain
        fact that you cannot fire without something to fire and cannot swing
        without something to swing -- which no printed line bothers to say
        and every one of them assumes.
        """
        from .components import Gear

        gate = self.requires_of(branch)
        if gate is not None and not gate(world, actor):
            return False
        if Keyword.WEAPON not in self.keywords:
            return True
        gear = world.get(actor, Gear)
        # Nothing carried means nothing to gate on. A monster's weapon
        # attack is its claws: the row carries `Keyword.WEAPON` and the
        # creature has no `Gear` to hold anything, and demanding one made
        # thirty-two perfectly good monster rows unusable.
        #
        # **An implement counts as nothing here**, and has to. A wizard
        # carrying no gear at all could always punch; give it the orb its
        # class page prints and the list stops being empty, the gate starts
        # being applied, and the punch it always had is refused -- an
        # implement being the one thing you cannot hit anybody with.
        if gear is None or not any(w.group != "implement" for w in gear.weapons):
            return True
        kind = self.reach_of(branch).kind
        if kind == "ranged":
            # Unless it is thrown by hand, in which case a melee weapon is
            # exactly what it wants.
            return bool(gear.melee) if self.thrown_by_hand else gear.ranged is not None
        if kind == "melee":
            return bool(gear.melee)
        return True

    def provokes_on(self, branch: int = 0, augment: int = 0) -> bool:
        """Does *this branch* leave an opening? The melee half does not."""
        if self.no_provoke:
            return False
        return self.reach_of(branch, augment).kind in ("ranged", "area_burst", "wall")

    def label_of(self, branch: int = 0) -> str:
        """What to call this branch on the card. Empty for a single-branch row."""
        return "" if not self.reach.alt else self.reach_of(branch).kind

    @property
    def provokes(self) -> bool:
        """Does using this leave an opening for anyone standing next to you?

        The melee branch of a two-branch row does not, so a caller that
        knows which branch is in play should ask `provokes_on` instead.

        Ranged and area powers do; melee and close powers do not. Taking aim
        at something across the room is what turns your back on the creature
        already in your face, and a wizard who can stand next to a brute and
        fire into the far rank with impunity is a different game.

        Derived from the range line rather than declared per row, so nothing
        has to remember it. A power that says otherwise sets `no_provoke`.
        """
        if self.no_provoke:
            return False
        return self.reach.kind in ("ranged", "area_burst", "wall")

    def hit_chance(
        self, world: World, actor: int, target: int, branch: int = 0, augment: int = 0
    ) -> float | None:
        """Probability this power hits, or **None** when there is no attack line.

        It used to return 0.5 for a row that declared none, described as an
        honest "no idea". It is not honest, because 0.5 is a *score*: the caller
        weighs it, and a row with nothing to hit was collecting `hit_chance` at
        3.0 and `expected_hits` at 4.0 for a total of +3.50 it had not earned.
        1,361 class rows have no attack line and do not attack -- mostly heals,
        buffs and zones -- and `expected_hits` sums over targets, so a buff on
        three allies took +1.5 rather than +0.5 and grew with the number of
        allies it helped.

        None instead, so a caller has to decide what no attack line means rather
        than being handed a middling number that competes. Same reasoning as
        `ratings.rating` returning None for an unrated option.

        Both `api/render.py` callers already guard on `attack is None` and are
        unaffected.
        """
        line = self.attack_of(branch, augment)
        if line is None:
            return None
        from .query import cover_between, defence, has_combat_advantage

        bonus = line.bonus_for(world, actor, self.ref, branch)
        if has_combat_advantage(world, actor, target):
            bonus += 2
        ranged = self.reach_of(branch, augment).kind == "ranged"
        bonus -= int(cover_between(world, actor, target, ranged=ranged))
        need = defence(world, target, line.vs) - bonus
        return min(0.95, max(0.05, (21 - need) / 20))

    def __str__(self) -> str:
        return f"{self.ref} ({self.usage.value}, {self.action.value}, {self.reach})"


REGISTRY: dict[str, Power] = {}

#: What a `todo=` element may look like. Either a dotted name --
#: `Keyword.RAGE`, `AttackResult.parity`, `c.deals` -- or any name with an
#: argument list, `enemy_within(n)`. Both forms are things a tool can go and
#: look for; a sentence is not, and 45 of `blocked.json`'s 46 entries were
#: sentences, which is why a quarter of that list went unchecked for weeks
#: while the summary read "0 ready".
_SYMBOL = re.compile(
    r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+\s*(?:\([^()]*\))?"
    r"|[A-Za-z_]\w*\s*\([^()]*\)"
    # **A compendium ref is a symbol too.** "This row is waiting on
    # another row" is a real and common state -- an item that grants a
    # named class power nobody has written yet -- and it is exactly as
    # checkable as a missing method: the tool looks in the registry
    # instead of on `Cast`. Without it such a row had no way to say what
    # it wanted, and two were left looking merely broken.
    # `rt:` is the same case as `cf:` and was left out of it: a racial
    # trait is a declared row like any other, and a feat riding on one
    # that is not written yet had no way to name what it waited for.
    r"|[pmifr]\d+[a-z]?\d*|(?:cf|rt):[\w-]+"
)

#: What a `narrative=` element may look like -- `skill:thievery`. See
#: `Power.narrative` for why this is a closed vocabulary and not a symbol.
_NARRATIVE = re.compile(r"skill:([a-z]+)")

#: How much docstring counts as a reason. `out_of_combat` asks for one by
#: convention and gets one; `narrative=` is the easier field to reach for,
#: so it is asked for by the guard. A sentence clears this and a word does
#: not, which is the whole distinction being drawn.
_REASON = 40


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
    attack_alt: Attack | None = None,
    damage_alt: Damage | None = None,
    requires: Callable[[World, int], bool] | None = None,
    requires_text: str = "",
    charges: bool = False,
    thrown_by_hand: bool = False,
    requires_alt: Callable[[World, int], bool] | None = None,
    trigger: str = "",
    on: Trigger | Sequence[Trigger] | None = None,
    recharge: int = 0,
    recharge_when: Trigger | Sequence[Trigger] | None = None,
    uses: int = 1,
    once_per_round: bool = False,
    group: str = "",
    no_provoke: bool = False,
    out_of_combat: bool = False,
    summon: Summon | None = None,
    todo: Iterable[str] = (),
    dropped: Iterable[str] = (),
    narrative: Iterable[str] = (),
    obsolete: str = "",
    declined: str = "",
    defect: str = "",
    proficiency: Iterable[str] = (),
    swap: Swap | None = None,
    augments: Iterable[Augment] = (),
) -> Callable[[Body], Body]:
    """Declare one power or one monster ability.

    `ref` is the compendium id -- `p289`, or `m145a2` for a stat block's
    second ability. Never a name: the engine has no use for one, and the
    agent that wrote this function was never shown it.
    """
    todo, dropped = tuple(todo), tuple(dropped)
    for want in (*todo, *dropped):
        if not _SYMBOL.fullmatch(want.strip()):
            raise ValueError(
                f"{ref}: todo={want!r} is prose. Name the symbol you wanted "
                f"-- c.deals(), query.speed(world, eid, ctx), Keyword.RAGE "
                f"-- so the tools can tell when it arrives."
            )
    if todo and out_of_combat:
        # One says "this row is finished and deliberately does nothing";
        # the other says "this row is unfinished". A row claiming both is
        # counted as fine by `audit.py`'s inert branch and never looked at
        # again, which is the exact hole the marker exists to close.
        raise ValueError(f"{ref}: out_of_combat and todo cannot both be set")
    if todo and dropped:
        # One says nothing here works, the other says the rest of it does.
        raise ValueError(f"{ref}: todo and dropped cannot both be set")
    if defect and (todo or dropped or obsolete or declined or out_of_combat):
        # `defect=` says no symbol will ever finish this row, because the
        # sentence it needs is not in the source. Every other marker promises
        # the opposite -- a symbol to wait for, a clause that plays, or a
        # deliberate retirement -- so a row claiming both tells the tools two
        # incompatible things and gets counted by whichever asks first.
        raise ValueError(
            f"{ref}: defect cannot be combined with todo, dropped, obsolete, declined "
            f"or out_of_combat -- it means no symbol can finish this row"
        )

    narrative = tuple(narrative)
    skills = []
    for clause in narrative:
        got = _NARRATIVE.fullmatch(clause.strip())
        if got is None or got[1] not in SKILLS:
            raise ValueError(
                f"{ref}: narrative={clause!r} is not a skill. An element is "
                f"skill:<name> for one of the {len(SKILLS)} skills -- "
                f"skill:thievery -- naming the skill whose circumstance has "
                f"no combat meaning. Not a symbol: there is no symbol."
            )
        skills.append(got[1])
    if narrative and todo:
        # A `todo` row is refused in play, so it has no combat half for a
        # narrative clause to sit beside. Claiming both says the row both
        # does nothing and does the part that matters.
        raise ValueError(f"{ref}: todo and narrative cannot both be set")
    if narrative and out_of_combat:
        # The row is already declared narrative whole. Saying it again of
        # one clause draws a distinction against nothing, and a marker
        # that cannot be wrong is a marker nobody reads.
        raise ValueError(f"{ref}: out_of_combat and narrative cannot both be set")

    def wrap(body: Body) -> Body:
        if narrative:
            # The token says which skill, never why, and "why" is the only
            # part that can be checked by a person. `out_of_combat` asks
            # for this by convention; this field is the easier one to reach
            # for to make an awkward clause go away, so it is asked here.
            why = (body.__doc__ or "").strip()
            if len(why) < _REASON or not any(s in why.lower() for s in skills):
                raise ValueError(
                    f"{ref}: narrative= needs a docstring saying why the "
                    f"clause has no combat meaning, naming the skill "
                    f"({', '.join(skills)}). A clause the engine is merely "
                    f"missing is dropped=, not narrative=."
                )
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
            attack_alt=attack_alt,
            damage_alt=damage_alt,
            requires=requires,
            requires_text=requires_text,
        charges=charges,
        thrown_by_hand=thrown_by_hand,
            requires_alt=requires_alt,
            trigger=trigger,
            on=on,
            recharge=recharge,
            recharge_when=recharge_when,
            uses=uses,
            once_per_round=once_per_round,
            group=group,
            no_provoke=no_provoke,
            out_of_combat=out_of_combat,
            summon=summon,
            todo=todo,
            dropped=dropped,
            narrative=narrative,
            obsolete=obsolete,
            declined=declined,
            defect=defect,
            proficiency=tuple(proficiency),
            swap=swap,
            augments=tuple(augments),
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


def area_of(
    world: World, actor: int, p: Power, origin: Square | None = None, branch: int = 0,
    augment: int = 0,
) -> frozenset[Square]:
    """The squares a power covers, given where its origin was placed.

    Clipped to the board. A ranged 20 power on a board sixteen squares wide
    otherwise reports a reach that runs off the edge, and an interface that
    highlights what it is given lights up squares that are not there.
    """
    r = p.reach_of(branch, augment)
    # Every origin, unioned. One companion gives one origin and the same answer
    # as before; two give the area either of them could reach, which is what the
    # printed rule asks for on both of its sentences. See `origins`.
    mine = set()
    for eye in origins(world, actor, r):
        mine |= squares(world, eye)
    stretch = _stretched(world, actor, r.kind, {"power": p.ref, "kind": r.kind})
    if stretch:
        r = replace(r, size=r.size + stretch)
    if r.kind == "close_burst":
        out = spread(mine, r.size)
    elif r.kind == "close_blast":
        aim = origin or next(iter(sorted(spread(mine, 1) - mine)))
        out = blast(mine, r.size, aim)
    elif r.kind == "area_burst":
        out = area_burst(origin or next(iter(sorted(mine))), r.size)
    elif r.kind == "wall":
        # Everywhere the wall may be put, which is what an interface lights
        # up and what `c.wall` picks its run of squares out of.
        out = spread(mine, r.within)
    elif r.kind in ("melee", "ranged"):
        out = spread(mine, _reach_of(world, actor, r, p.ref))
    else:
        out = frozenset(mine)
    return frozenset(sq for sq in out if world.grid.inside(sq))


def _reach_of(world: World, actor: int, r: Range, ref: str = "") -> int:
    """How far this range actually carries.

    For a weapon range that is the **long** range, because a shot past
    the normal one is legal and merely takes the -2 that
    `resolve._long_range` charges. Capping the offer at the normal range
    made that penalty unreachable: the target was refused before it could
    be charged, so the whole of `_long_range` was dead code.
    """
    from .components import Gear

    gear = world.get(actor, Gear)
    if r.kind == "melee":
        # **A reach weapon reaches, which nothing here used to say.**
        # `Weapon.reach` was filled by the ETL, carried on the component and
        # read by no code in the engine, so a glaive was a reach-1 weapon in
        # play: 12 of 117 printed weapons have reach above 1 and every
        # character holding one was swinging short.
        #
        # **Only on a row that prints "Melee weapon."** A melee range is two
        # different things -- the weapon's reach, or a fixed number -- and both
        # arrive here as `Melee(1)`. `max(weapon, printed)` was the first attempt
        # and it over-extends the fixed ones: a "Melee touch" row would stretch
        # to two squares in a glaive's hand, which no printed line says. The
        # compendium knows which is which, 1,023 against 325, and
        # `scripts/reaches.py --emit` writes the set out.
        #
        # **Or the row says so itself**, which is what `r.by_weapon` is for and
        # what `mba` needs: the melee basic attack is declared in `engine/basic
        # .py` and has no compendium id, so it can never be in a set derived from
        # the compendium. Without this a glaive-wielder **threatened** two squares
        # and could not **choose** a basic attack at two -- `_threat` reads the
        # weapon and `candidates` read the printed 1. #294.
        if ref not in BY_WEAPON and not r.by_weapon:
            return r.size
        # **The weapon's reach plus what the card grants**, and neither `max` with
        # the printed size nor the weapon alone. Both of those were tried and both
        # were wrong, because the figure they needed had been thrown away upstream:
        # four of these rows print "Melee weapon +1 reach", the ETL kept only the
        # "melee weapon" half, and so the bonus could not be read from the row at
        # all. Fixed in the parser; `GIVES` is what it now records. One square
        # unarmed, which is what a fist reaches.
        held = getattr(gear, "main", None) if gear else None
        worn = getattr(held, "reach", None) if held else None
        return (worn or 1) + GIVES.get(ref, 0)
    if not r.by_weapon:
        return r.size
    # **The weapon's range, not the card's.** A row printing `Ranged weapon`
    # does not print a number, so the number the ETL wrote down is a stand-in
    # and must lose to the thing in hand. It used to be `max(weapon, printed)`,
    # which cannot be right in both directions and was wrong in both:
    #
    #   * a thrown weapon's range was not consulted at all, because `Gear.ranged`
    #     answers "can be fired" and a dagger cannot be -- so a javelin (10/20)
    #     reached only the 10 its card happened to carry, and 145 rows carrying
    #     20 would have let a dagger throw twice as far as a dagger goes;
    #   * and `max` floors every row at its stand-in, so a 3/6 trident in the
    #     hand of a row printing 20 still reached 20.
    #
    # Fired first, then thrown, because a character holding a bow *and* a dagger
    # is firing the bow -- the same precedence `Cast.w` uses to pick which dice
    # to roll. The printed size is what is left when the hand holds neither, and
    # there it is the only number there is.
    shot = getattr(gear, "ranged", None) if gear else None
    flies = getattr(shot, "ranged", None) if shot else None
    if flies is None:
        hurled = getattr(gear, "thrown", None) if gear else None
        flies = getattr(hurled, "thrown", None) if hurled else None
    return flies[1] if flies else r.size


def _stretched(
    world: World, actor: int, kind: str, ctx: dict[str, Any] | None = None
) -> int:
    """How much longer than printed this creature's reach or range is.

    `Mods.total` was read for attack, damage, save, speed, forced, crit
    range and the defences, and for nothing about distance -- so "the
    target's reach increases by 1" and "add your Wisdom modifier to the
    range of your ranged powers" were stored and never consulted. Applied
    where the area is worked out, so the extra square decides what may be
    aimed at and not merely what a body may reach.

    Melee reads `"reach"` and a ranged line reads `"range"`. A blast or a
    burst reads `"blast_size"`: its size is the blast itself, so "increase
    the size of your blasts and bursts by 1" is that number and not the
    `within` an area burst may be placed at, which no printed line of this
    shape lengthens.

    `ctx` carries the row being measured, so "the range of your **arcane**
    powers" is a gate on the modifier rather than a blanket stretch of
    everything the creature can throw.
    """
    from .components import Mods

    mods = world.get(actor, Mods)
    if mods is None or not mods.items:
        return 0
    ctx = ctx or {}
    if kind == "melee":
        return max(0, mods.total("reach", ctx))
    if kind == "ranged":
        return max(0, mods.total("range", ctx))
    if kind in ("close_burst", "close_blast", "area_burst"):
        return max(0, mods.total("blast_size", ctx))
    return 0


def measured_from(world: World, actor: int, r: Range) -> int:
    """Whose square this range is taken from -- the caster, unless it says.

    "Melee spirit 1" is measured from the shaman's companion, and the row is
    refused or allowed on that distance long before the body runs. Falls
    back to the caster when the named thing is not on the board, so a shaman
    whose spirit has been dismissed is simply out of reach rather than
    throwing from inside `legal()`.
    """
    if r.from_ != "companion":
        # A square lent by another creature -- `c.cast_from`. Only a ranged
        # or area line borrows one, and only while the lender is on the
        # board and in sight, which is the proviso both printed lines carry.
        if r.kind in ("ranged", "area_burst", "wall"):
            from .components import Position as _Position
            from .types import Relation

            for lender in world.relations.targets(Relation.CASTS_FROM, actor):
                if world.get(lender, _Position) and line_of_effect(world, actor, lender):
                    return lender
        return actor
    from .components import Companion, Position

    for eid in world.having(Companion):
        # A companion that has been dismissed or killed keeps its component
        # for a moment but has no square, and measuring from it gave the
        # row an **empty area** -- so the page lit nothing up and the power
        # could not be aimed anywhere at all. Falling back to the caster
        # makes it merely out of reach, which is the honest answer.
        if world.get(eid, Companion).owner == actor and world.get(eid, Position):
            return eid
    return actor


def origins(world: World, actor: int, r: Range) -> list[int]:
    """Every square this range could be measured from, not just the first.

    The plural of `measured_from`, and the shaman's second spirit is why it
    exists. The printed rule is two sentences and they want different things:

    * "When you attack with a spirit power, you **choose** which spirit
      companion to use for the attack" -- so the menu has to offer whatever
      *either* spirit could reach, and the choice is made at use time;
    * "When an effect applies to creatures adjacent to your spirit companion,
      that effect applies to creatures adjacent to **both**" -- a union.

    Both come out of offering from every origin, which is what `area_of` and
    `candidates` do with this. **With one companion the list is one long and
    nothing changes**, which is every character that exists today: only `p3839`
    conjures a second.
    """
    if r.from_ != "companion":
        return [measured_from(world, actor, r)]
    from .components import Companion, Position

    mine = [
        eid
        for eid in world.having(Companion)
        if world.get(eid, Companion).owner == actor and world.get(eid, Position)
    ]
    return mine or [actor]


def roller(world: World, actor: int, by: str) -> int:
    """Whose numbers an attack line rolls -- the user's, unless it names one.

    The companion is found the way `measured_from` finds it, and falls back
    to the caster for the same reason: a ranger whose beast is dead rolls
    something rather than raising from inside a header.
    """
    if by != "companion":
        return actor
    from .components import Companion, Position

    for eid in world.having(Companion):
        if world.get(eid, Companion).owner == actor and world.get(eid, Position):
            return eid
    return actor


def aim_points(world: World, actor: int, p: Power, augment: int = 0) -> list[Square]:
    """Every square this power can be pointed at.

    For a close blast these are the placement centres -- a blast 3 from a
    Medium creature gives the ring two squares out. For an area burst it is
    every square in range. Everything else aims at a creature rather than a
    square and gets an empty list.
    """
    mine = squares(world, actor)
    # The form being used, not the printed base: an augment that turns a
    # melee swing into an area burst has a `within` the base row has not
    # got, and asking the base here offered the burst nowhere to land.
    reach = p.reach_of(0, augment)
    if reach.kind == "close_blast":
        return sorted(blast_placements(mine, reach.size))
    if reach.kind in ("area_burst", "wall"):
        return sorted(
            sq
            for sq in spread(mine, reach.within)
            if world.grid.inside(sq)
            and any(world.grid.line_of_effect(src, sq) for src in mine)
        )
    return []


def basic_options(world: World, actor: int, window: str, own: str = "") -> list[str]:
    """What may be swung where the game *grants* a basic attack.

    "You can use <this row> in place of a melee basic attack" is an
    option beside the ordinary swing and not a replacement for it, so
    the creature's own basic is always in the list. `c.as_basic` files
    the stand-ins; the three places that hand out a swing -- the charge
    menu, the opportunity window and a defender's punishment -- all ask
    here, so the two guards below are written once.

    **Ordered rather than sorted, because a headless run takes the
    first.** An at-will stand-in costs nothing and is the whole reason
    the card was taken, so it leads; the plain basic comes next; one
    that spends an encounter or a daily goes last, where nobody burns a
    daily on a riposte by default.
    """
    from .components import Powers

    known = world.get(actor, Powers)
    if known is None:
        return []
    # `own` is the caller's answer to "what is this creature's basic
    # attack": `c.basic` has already worked out the engine's fallbacks
    # and a PC's `Powers.ranged` is empty, so asking again here would
    # drop the bow out of its own list.
    own = own or (known.ranged if window == "ranged" else known.basic)
    free: list[str] = []
    costly: list[str] = []
    for ref in known.instead_of_basic(window):
        p = get(ref)
        # An associated-powers list names rows the character may not
        # possess, and `usable` is what says so -- along with refusing a
        # spent encounter power and an unfinished one.
        if p is None or not usable(world, actor, p)[0]:
            continue
        (free if p.usage is Usage.AT_WILL else costly).append(ref)
    return list(dict.fromkeys([*free, *([own] if own else []), *costly]))


def candidates(
    world: World, actor: int, p: Power, origin: Square | None = None, branch: int = 0,
    augment: int = 0,
) -> list[int]:
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
    aim = p.target_of(augment)
    if aim.side == "self" and aim.count == 0:
        return []
    if aim.side == "self":
        return [actor]
    pool = {
        "enemy": enemies(world, actor),
        "ally": [*allies(world, actor), actor],
        "any": creatures(world),
        "other": [c for c in creatures(world) if c != actor],
        "other_ally": allies(world, actor),
        # **`"team"` was missing here entirely**, so a row declaring it
        # raised `KeyError` at targeting and no row in the tree used it --
        # which is why `_side`'s note that "a card meaning you as well says
        # you and each ally, and `team` is that pool" described something
        # unreachable. `Cast._side` has had it all along; this is the
        # targeting half catching up. #364.
        "team": [*allies(world, actor), actor],
        # Not a creature at all, and not in any of the pools above: scenery
        # has no `Side`, so every one of them is empty for it.
        "object": scenery(world, "object", loose=aim.loose),
    }[aim.side]
    if aim.holding:
        from .query import holding

        pool = [c for c in pool if holding(world, c, aim.holding)]
    if aim.max_size is not None:
        cap = aim.max_size.order
        pool = [c for c in pool if _size_of(world, c).order <= cap]
    if (
        aim.relation is not None
        or aim.grants_ca
        or aim.flanked
        or aim.conditions
        or aim.conditions_without
        or aim.can_act is not None
        or aim.kinds
        or aim.kinds_without
        or aim.ongoing
        or aim.ongoing_types
        or aim.bloodied is not None
    ):
        pool = [c for c in pool if _stands_right(world, actor, aim, c, p.ref)]

    reach = p.reach_of(branch, augment)
    aimed = origin is not None and reach.kind in ("area_burst", "close_blast")
    if aimed and origin not in aim_points(world, actor, p, augment):
        return []

    area = area_of(world, actor, p, origin, branch, augment)
    # **A row asking for a corpse must have the corpse in its pool.**
    # `targetable` is "alive, or scenery" -- it already carves out scenery so
    # that "one Medium or smaller object" can be aimed at, and a target line
    # naming `Condition.DEAD` needs the same exception for the same reason.
    # Without it `Condition.DEAD` is a condition nothing can ever be filtered
    # on: `_die` applies it correctly and the pool drops the body first. #399.
    if Condition.DEAD in aim.conditions:
        from .query import is_

        def can_aim(c: int) -> bool:
            return targetable(world, c) or is_(world, c, Condition.DEAD)
    else:

        def can_aim(c: int) -> bool:
            return targetable(world, c)
    if reach.kind == "area_burst" and origin is not None:
        return [
            c
            for c in pool
            if can_aim(c)
            and squares(world, c) & area
            and any(world.grid.line_of_effect(origin, sq) for sq in squares(world, c))
        ]
    # Line of effect is traced from whatever the range was measured from, so
    # a spirit round the corner reaches what *it* can see rather than what
    # its shaman can.
    eyes = origins(world, actor, reach)
    return [
        c
        for c in pool
        if can_aim(c)
        and squares(world, c) & area
        and any(line_of_effect(world, eye, c) for eye in eyes)
    ]


def _size_of(world: World, eid: int) -> Size:
    from .components import Position

    pos = world.get(eid, Position)
    return pos.size if pos is not None else Size.MEDIUM


def unmet_requirement(world: World, actor: int, p: Power) -> bool:
    """Is this row refused *because of its Requirement line* specifically?

    Asked instead of matching on the words of `usable`'s reason, which is
    the printed sentence whenever the row has one.
    """
    return not any(p.can_branch(world, actor, b) for b in p.branches)


def affordable(world: World, actor: int, p: Power) -> tuple[int, ...]:
    """Which forms of this row the creature can pay for, cheapest first.

    `(0,)` for every row that prints no Augment line, which is all but a
    handful -- so nothing non-psionic gains an entry in the action menu.
    """
    if not p.augments:
        return (0,)
    from .components import PowerPoints

    pool = world.get(actor, PowerPoints)
    have = pool.points if pool is not None else 0
    return tuple(n for n in p.augment_costs if n <= have)


def keywords_of(world: Any, actor: int, p: Any) -> frozenset[Keyword]:
    """Every keyword a row carries **for this creature**.

    The declared tuple plus whatever a feat granted. Read this, never
    `Power.keywords` directly: a row's keywords are header data -- one
    tuple, fixed at import, shared by everybody who ever holds the row --
    and 12 feats print "your <row> is considered an arcane attack power" or
    "gains the reliable keyword", which a header cannot say for one
    character only.

    **There were 22 sites reading the header** across `cast`, `dsl`,
    `resolve`, `triggers`, `durations`, `api/render` and `policy`. A grant
    honoured at 21 of them is a modifier nothing consults at the 22nd,
    which is this component's commonest bug, so they all come through here.

    `p` may be None -- a basic attack has no declared row -- and an actor
    with no `Powers` answers the header, which is every monster.
    """
    from .components import Powers

    if p is None:
        return frozenset()
    declared = frozenset(p.keywords)
    known = world.get(actor, Powers) if actor is not None else None
    if known is None:
        return declared
    return declared | known.granted_keywords.get(p.ref, frozenset())


def usable(
    world: World, actor: int, p: Power, *, dying: bool = False, spent_ok: bool = False,
    augment: int = 0, aimed: bool = False,
) -> tuple[bool, str]:
    """Can this power be used, and if not, why not?

    The reason is returned rather than logged, because the interface shows it
    on the greyed-out card and a player who cannot see why is playing blind.

    `spent_ok` waives the usage limits alone. "The target repeats the attack"
    is not the target using the power again -- it is one use happening twice
    -- so an encounter attack that has just been spent would otherwise refuse
    the very repeat the card is printed to cause.
    """
    from .components import Powers
    from .query import can_act

    # **An unfinished row is refused outright**, and this is the whole
    # safety of letting one be written at all. A `todo` row is still in
    # `REGISTRY`, so without this it is offered, chosen, and plays whatever
    # fraction of its card got written -- which is worse than the absence
    # it replaced, because a wrong result is harder to see than a missing
    # one. Refused here, it is exactly as inert as being absent was, and it
    # says what it is waiting for.
    if p.obsolete:
        return False, "superseded by a rules change"
    if p.declined:
        # **Deliberately not built.** Refused for `obsolete=`'s reason and
        # not `todo=`'s: nothing is coming, so there is nothing to wait for,
        # and offering a fraction of it would be worse than the absence.
        return False, "not being built"
    if p.defect:
        # **The compendium is missing what this row would be written from.**
        # Refused rather than offered half-written, for the reason above: a
        # wrong result is harder to see than a missing one. #360.
        return False, "the compendium is missing what this row needs"
    if p.todo:
        return False, "not finished yet"

    # `dying` is for the one row shape that answers its own downfall: a
    # death throe fires *because* the creature has dropped, so refusing it
    # for not being able to act refuses it for the very reason it exists.
    # A declared no-action row is the same exemption one step further out. It
    # is not an action, and at least one of them is printed *specifically* to
    # be used while stunned -- "Trigger: you start your turn stunned, dazed,
    # or unconscious" -- so the can-act gate refused it for the only
    # situation it exists for. A trait with no trigger keeps the gate: that
    # one is armed at the start of the fight, and nothing should re-arm it on
    # a creature that cannot move.
    no_action = p.action is ActionType.NONE and bool(p.triggers)
    if not dying and not no_action and not can_act(world, actor):
        return False, "cannot act"
    # **The stance you are already in.** A stance ends whatever you were
    # in and starts itself, so re-taking the same one is a no-op that
    # costs a minor -- and nothing refused it, because the policy has no
    # notion of a stance at all. Given a fighter who could reach one, it
    # thrashed: eighty-three swaps in a single fight and one row used
    # eighty-four times, which turned a twelve-round win into a
    # thirty-round stalemate. The bug predates the two-handed weapon that
    # exposed it; no fighter the tree dealt could take those rows before.
    if Keyword.STANCE in keywords_of(world, actor, p):
        standing = world.effects.stance_of(actor)
        if standing is not None and standing.label == p.ref:
            return False, "already in this stance"

    powers = world.get(actor, Powers)
    if powers is not None:
        if p.ref not in powers.all:
            return False, "not known"
        if p.ref in powers.forbidden:
            return False, "cannot be used right now"
        # Checked for every usage, because **every printed "1/round" rider
        # is on an at-will** -- and this lived inside the not-at-will branch,
        # so the guard was unreachable and the header field was decoration.
        if not spent_ok:
            if p.once_per_round and powers.last_round.get(p.ref) == world.round:
                return False, "already used this round"
            if p.usage is not Usage.AT_WILL:
                used = powers.times(p.ref)
                if used >= p.uses:
                    return False, (
                        "expended" if p.uses == 1 else f"used {used} of {p.uses}"
                    )
                if p.group and _group_spent(world, actor, p):
                    return False, f"one {p.group} power per encounter"
    if augment:
        # A form that was never declared is not a refusal to explain to a
        # player -- it is a caller asking for something that does not
        # exist, and saying yes would run the base card while charging
        # for the augment.
        if p.augment_at(augment) is None:
            return False, "no such augment"
        if augment not in affordable(world, actor, p):
            return False, "not enough power points"
    open_branches = [b for b in p.branches if p.can_branch(world, actor, b)]
    if not open_branches:
        # The printed sentence when there is one, because it is what the
        # card shows. Callers that need to know *which* refusal this is
        # should ask `unmet_requirement`, not read these words -- a custom
        # `requires_text` hid the failure from `chargen.build_for`, which
        # then handed a bow-only row to a ranger holding two blades.
        return False, p.requires_text or "requirement not met"
    # **Skipped when the caller has already named who it is swinging at.** This
    # scan asks "is anybody hostile *to the swinger* within reach", which is the
    # wrong question for a forced attack: `c.basic(who=victim, on=<the victim's
    # own ally>)` makes the victim the swinger, so the row was refused unless
    # something hostile to the *victim* happened to stand nearby. Measured:
    # `usable(world, victim, "m145a0") -> (False, 'nearest is 8 squares away')`
    # on a swing the card describes exactly. **Every "turn them on each other"
    # row in the tree worked by accident.**
    #
    # Two questions, asked separately now: *can this creature make this attack*
    # stays here, and *is that particular target legal* is `_within_reach`,
    # which `use`'s explicit-target arm has enforced per target since #381. The
    # callers that do the offering -- `actions.legal`, the trigger dispatcher --
    # name no targets and so keep the scan and its greyed-card reason. #429.
    if p.is_attack_at(augment) and not aimed and not any(
        _can_land(world, actor, p, b, augment) for b in open_branches
    ):
        return False, _no_targets(world, actor, p)
    return True, ""


def _can_land(world: World, actor: int, p: Power, branch: int = 0, augment: int = 0) -> bool:
    """Is there any way to aim this that catches somebody?

    For an area power that means trying the placements, not the default one.
    Asking `candidates` with no origin centres a blast on an arbitrary
    adjacent square, and a blast that happens to point away from everybody
    reported itself unusable while three creatures stood in range.
    """
    if p.reach_of(branch, augment).kind in ("area_burst", "close_blast"):
        return any(
            candidates(world, actor, p, aim, branch, augment)
            for aim in aim_points(world, actor, p, augment)
        )
    if p.charges_of(augment):
        # A charge covers ground first, so the question is whether anybody
        # is within reach *after* the run. Asking about the printed melee
        # reach refused the row whenever the target was further off than a
        # sword -- which is every time a charge is the right thing to do.
        from .query import distance_between, enemies, speed

        far = p.reach_of(branch, augment).size + speed(world, actor, {"charge": True})
        return any(
            distance_between(world, actor, foe) <= far for foe in enemies(world, actor)
        )
    return bool(candidates(world, actor, p, None, branch, augment))


def _stands_right(world: World, actor: int, aim: Target, target: int, ref: str = "") -> bool:
    """Does that creature stand to the caster the way the target line demands?

    The three relational halves of a printed target line, in one predicate
    because **two callers must not disagree about it**: `candidates()`, which
    decides what is offered, and `use`'s explicit-target arm, which decides what
    connects. #381 was exactly that disagreement about reach -- at ten squares
    `candidates()` offered a target zero times and `use` rolled the attack --
    and a second copy of this logic would reproduce it one field over.
    """
    if aim.relation is Relation.HIDDEN_FROM:
        # **Sight is never the bare relation.** `query.unseen_by` subtracts
        # `sees_through` and folds in a capped sight range, and its own
        # docstring says it exists so that "the sight and the combat advantage
        # can never disagree" -- asked in one place rather than at each reader.
        # Reading the triple directly here would have made this a third reader
        # and wrong in both directions at once: too wide, accepting an enemy
        # that plainly sees the caster past its hiding, and too narrow,
        # refusing a *blinded* enemy -- including one blinded by the same stat
        # block for the sake of this very row. 37 content sites set
        # `see_invisible` or `sight_range`, so neither case is hypothetical.
        from .query import unseen_by

        if unseen_by(world, target, actor) is aim.without:
            return False
    # Outward from the caster, which is the direction every one of these is
    # stored in: `Cast.grab` files `(GRABBED_BY, holder, victim)`, and the mark,
    # the curse, the quarry and domination all put the imposer first. So
    # "grabbed by it" is `holds(kind, actor, target)` and never the reverse,
    # which would read as "grabbing it".
    elif (
        aim.relation is not None
        and world.relations.holds(aim.relation, actor, target) is aim.without
    ):
        return False
    if aim.grants_ca:
        from .query import has_combat_advantage

        if not has_combat_advantage(world, actor, target, ref):
            return False
    if aim.flanked:
        from .query import flanked_by

        if not flanked_by(world, target, actor):
            return False
    if aim.conditions or aim.conditions_without:
        from .query import is_

        # Any, not all. See the field.
        if aim.conditions and not any(is_(world, target, c) for c in aim.conditions):
            return False
        if any(is_(world, target, c) for c in aim.conditions_without):
            return False
    if aim.can_act is not None:
        from .query import can_act

        if can_act(world, target) is not aim.can_act:
            return False
    if aim.kinds or aim.kinds_without:
        from .query import kinds_of

        words = kinds_of(world, target)
        if aim.kinds and not (words & aim.kinds):
            return False
        if words & aim.kinds_without:
            return False
    if aim.ongoing or aim.ongoing_types:
        from .query import taking_ongoing

        if not taking_ongoing(world, target, aim.ongoing_types):
            return False
    if aim.bloodied is not None:
        from .components import Health

        hp = world.get(target, Health)
        # A creature with no `Health` is scenery, and scenery is neither
        # bloodied nor unbloodied -- so it fails either way round rather than
        # defaulting into one of them.
        if hp is None or hp.bloodied is not aim.bloodied:
            return False
    return True


#: Events whose whole point is that the creature is leaving, or has left.
#: A row answering one of these is *meant* to swing at something no longer in
#: reach -- "when an enemy leaves an adjacent square, make a melee basic attack
#: against it, **even if the enemy is shifting**" -- so the reach test is waived
#: when the target is the creature that event is about. 18 of the occurrences
#: measured for #381 are this, and this is why they are not faults.
_DEPARTING = ("AdjacencyLost", "MoveStart", "MoveEnd", "Moved")


def _within_reach(
    world: World,
    actor: int,
    p: Power,
    target: int,
    branch: int = 0,
    augment: int = 0,
    *,
    trigger: Any = None,
    charge: bool = False,
    reached: bool = False,
) -> bool:
    """May this creature attack that one from where it stands?

    **The explicit-target arm of `use` had no reach test at all**, so
    `c.basic(on=x)` and `c.use_power(ref, on=x)` connected at any distance while
    `candidates()` -- which every offered action goes through -- refused the same
    target. The two disagreed outright: at ten squares `candidates()` offered a
    target zero times and `use` rolled the attack, hit, and dealt damage. 100
    out-of-reach melee swings were measured across the tree, 65 of them faults.
    #381.

    **Reach only, never `candidates()` membership.** Membership also filters by
    side, and two of the first three violations found were at distance 1 --
    legal, and excluded for a side reason. A guard built on membership refuses
    legal attacks.

    Measured from `origins()` rather than from `actor`, because a shaman's
    "Melee spirit 1" is measured from the spirit; and with `_reach_of` rather
    than `Range.size`, because that resolves `by_weapon` to the wielded weapon's
    long range. Getting either wrong breaks 39 rows.

    Three exemptions, and the shape of each matters:

    * **`charge`** is exempt because its legality is reach **plus speed** --
      `_can_land` says so, and the explicit-target arm never reaches
      `_can_land`, so it has to be restated here or every `c.charge_at` breaks.
    * **A departing trigger** is exempt when the target is the creature the
      event is about. Trigger-aware rather than a flag, so a row cannot claim
      the exemption by declaring itself special.
    * **`reached`** is for a mover that has already crossed the target's square
      -- trample, overrun. It carries *proof*: `c.overrun` returns the creatures
      whose squares were entered, and a caller passes this only for one of them.
      A bare opt-out is what the next author copies by habit.
    """
    r = p.reach_of(branch, augment)
    if r.kind not in ("melee", "ranged") or charge or reached:
        return True
    if trigger is not None and type(trigger).__name__ in _DEPARTING:
        for field in ("mover", "actor", "who", "target"):
            if getattr(trigger, field, None) == target:
                return True
    from .query import distance_between

    far = _reach_of(world, actor, r, p.ref)
    return any(
        distance_between(world, eye, target) <= far
        for eye in origins(world, actor, r)
    )


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

    "3 squares away" is actionable; "no targets" is not. **And this string is
    shown to the player** -- `actions.legal(include_blocked=True)` puts it on
    the greyed card -- so a wrong reason is a wrong sentence on screen.

    It used to measure the **unfiltered** side pool, so a row refused because
    nothing *qualifies* blamed geometry: a reach-1 row with two enemies standing
    adjacent reported "nearest is 0 squares away", which is both untrue as an
    explanation and absurd on its face. That was always wrong for `holding` and
    `max_size`; it became wrong on roughly 190 rows at once when the relational
    and condition filters landed, because those rows previously carried a
    `requires_text` and the card said something true. #403.

    So the pool is narrowed by every clause `candidates` narrows it by, and the
    clause that emptied it is named rather than guessed at.
    """
    from .query import distance_between, holding

    aim = p.target
    pool = enemies(world, actor) if aim.side == "enemy" else creatures(world)
    live = [c for c in pool if alive(world, c)]
    if not live:
        return "no targets"
    fits = [c for c in live if _stands_right(world, actor, aim, c, p.ref)]
    if aim.holding:
        fits = [c for c in fits if holding(world, c, aim.holding)]
    if aim.max_size is not None:
        cap = aim.max_size.order
        fits = [c for c in fits if _size_of(world, c).order <= cap]
    if not fits:
        # The printed wording, which is what `Target.__str__` returns when the
        # row carries a label -- so the card says the restriction the card
        # states, rather than a distance that has nothing to do with it.
        return f'nothing here is "{aim}"'
    nearest = min(distance_between(world, actor, c) for c in fits)
    furthest = max(p.reach_of(b).size for b in p.branches)
    if p.reach.kind in ("melee", "close_burst", "close_blast") and not p.reach.alt:
        return f"nearest is {nearest} squares away"
    return f"nearest is {nearest} squares away, range {furthest}"


# --------------------------------------------------------------------------
# Running one
# --------------------------------------------------------------------------


#: Refs currently running, keyed by actor. A row that grants an attack can
#: reach itself -- two creatures whose basic attack is "on a miss, an ally
#: attacks" handed it back and forth 131 times before the stack died. The
#: dispatcher kept a set like this for triggered rows; every other route in
#: had none, so the guard lives here now and `triggers` shares it.
_IN_FLIGHT: set[tuple[int, str]] = set()

#: The uses that are running right now, innermost last. An immediate
#: interrupt is a use nested inside the one it answers, and "the ally also
#: becomes a target of the power" has to reach that outer one while its
#: target list is still being walked. `Cast.add_target` is the only reader.
_RUNNING: list[Any] = []


def running_below(cast: Any) -> Any:
    """The use this one is nested inside, if any."""
    for i in range(len(_RUNNING) - 1, -1, -1):
        if _RUNNING[i] is cast:
            return _RUNNING[i - 1] if i else None
    return _RUNNING[-1] if _RUNNING else None


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
    charge: bool = False,
    granted_by: int = -1,
    granted_via: str = "",
    branch: int = 0,
    augment: int = 0,
    variant: int = 0,
    reentrant: bool = False,
    reached: bool = False,
) -> bool:
    """Use a power. Returns False if it could not be used.

    The body runs once per target. A power with no targets runs once with
    `c.target` set to None, which is what a personal or zone-only power wants.

    `trigger` is the event being answered, for a row the dispatcher is
    offering. The body reads it as `c.trigger` and an interrupt stops it with
    `c.cancel()`.

    `granted_by`/`granted_via` are who handed this use over and through
    which row -- set by `c.grant_attack`, `c.basic` and `c.charge_at`,
    and by nothing else. A swing somebody was *given* was announced as
    an ordinary `mba`, so every card reading "the basic attack granted
    by X" had nothing to tell it apart from a swing taken freely.

    `branch` picks which half of a "Melee or Ranged weapon" line is being
    used. 0 is the printed first one and is what every single-branch row
    gets without asking.

    `augment` is how many power points this use is bought with, for a row
    that declares `augments=` in its header. **Settled here, above
    targeting**, because that is the whole reason the field exists: a
    clause that swaps a melee swing for a close burst cannot be chosen by
    a body that is only called once the targets are already picked. 0 is
    the printed base card and is what every other row in the tree gets.
    """
    from .components import Powers

    p = get(ref)
    if p is None:
        return False
    # A death throe answers the actor's own `Dropped`. It fires *because*
    # the creature has gone down, so the ordinary "can it act?" gate would
    # always refuse it -- which is why no row of that shape had ever fired.
    dying = (
        trigger is not None
        and getattr(trigger, "actor", None) == actor
        and not alive(world, actor)
    )
    # `aimed=` because the caller below has already said who: see the scan in
    # `usable` that this turns off, and `_within_reach` further down, which is
    # the question that replaces it. #429.
    ok, _why = usable(world, actor, p, dying=dying, spent_ok=reentrant,
                      augment=augment, aimed=targets is not None)
    if not ok:
        return False
    # **The points go before the targets are chosen.** An augmented form
    # is a different card -- different reach, different target line -- so
    # everything below has to be told which one is being used, and the
    # spend is what says so. Paid here rather than in the body: a body
    # runs once per target and would pay once per target with it.
    if p.augments:
        from .components import PowerPoints

        pool = world.get(actor, PowerPoints) or world.add(actor, PowerPoints())
        if augment and pool.spend(augment) < augment:
            return False
        if augment:
            pool.augmented[ref] = pool.augmented.get(ref, 0) + augment
        # Recorded for **every** use of an augmentable row, nought
        # included, because "when you augment this" has to be able to tell
        # this use from the last one -- and `augmented`, being the
        # encounter's running total, cannot.
        pool.last[ref] = augment
    # `reentrant` is "the attacker repeats the attack": the row has to run a
    # second time inside itself, which is the one case the guard below is
    # wrong about. It is never the default -- the guard exists because two
    # rows can otherwise hand a swing back and forth until the stack dies.
    if not reentrant and (actor, ref) in _IN_FLIGHT:
        return False

    if targets is not None:
        chosen = [
            t
            for t in targets
            if _within_reach(world, actor, p, t, branch, augment,
                             trigger=trigger, charge=charge, reached=reached)
            # **The same predicate `candidates()` uses, for the same reason the
            # reach test is here.** A header saying "one creature grabbed by it"
            # is a restriction on what may be struck, not advice to whoever
            # aims: without this a body passing an explicit target connected
            # with anybody, while the offered list refused all but the victim.
            and _stands_right(world, actor, p.target, t, p.ref)
        ]
        if targets and not chosen:
            return False
    else:
        chosen, origin = _auto_targets(world, actor, p, origin, branch, augment)
        chosen = list(chosen)
    cast = Cast(
        world=world,
        me=actor,
        ref=ref,
        # The **same** list the loop below walks, not a copy, so a target
        # added mid-run is one the body is then called for.
        targets=chosen,
        origin=origin,
        trigger=trigger,
        opportunity=opportunity,
        charge=charge,
        granted_by=granted_by,
        granted_via=granted_via,
        branch=branch,
        augment=augment,
        variant=variant,
    )
    # **The same hole as the `PowerResolved` emit at the bottom of this
    # function, on the other side of the body.** `cast.used()` announces
    # `PowerUsed`, the dispatcher offers rows to it, and one of those may
    # be a row that this one triggers in turn: two free item blocks each
    # reading "when you use a healing power other than me" handed the use
    # back and forth until the stack ran out. The guard eighteen lines
    # below is the thing meant to stop that and it is set too late to be
    # true for this emit -- so is `powers.note_use`, which means the
    # encounter limit does not stop it either. Taken and released the way
    # the emit below does, and for the same reason: the release has to be
    # in a `finally` or a body that raises leaves the row refused.
    guarded = (actor, ref) not in _IN_FLIGHT
    if guarded:
        _IN_FLIGHT.add((actor, ref))
    try:
        cast.used()
    finally:
        if guarded:
            _IN_FLIGHT.discard((actor, ref))

    if p.provokes_on(branch, augment) and not _survive_provoking(world, actor, ref):
        # Stopped before it went off -- stunned by an interrupt, or killed.
        # The power is *not* spent: the action was lost, not used.
        return False

    if spend:
        powers = world.get(actor, Powers)
        if powers is not None:
            if p.usage is not Usage.AT_WILL:
                powers.note_use(ref, world.round)
            elif p.once_per_round:
                # An at-will has no uses to count down, only a round to
                # remember -- and nothing remembered it, so a "1/round"
                # at-will could be used all turn.
                powers.note_round(ref, world.round)

    # A reentrant run finds its own row already marked; leaving the mark
    # standing on the way out is what keeps the guard true for the outer one.
    fresh = (actor, ref) not in _IN_FLIGHT
    _IN_FLIGHT.add((actor, ref))
    _RUNNING.append(cast)
    rolls: list[Any] = []
    try:
        if not chosen:
            p.body(cast)
        landed = False
        # By index rather than by iterator: `chosen` is `cast.targets`, and a
        # row answering this one may lengthen it while it is being walked.
        i = 0
        while i < len(chosen):
            t = chosen[i]
            cast.index = i
            i += 1
            if not targetable(world, t):
                continue
            cast.target = t
            cast.result = None
            p.body(cast)
            if cast.result is not None:
                rolls.append(cast.result)
            landed = landed or bool(cast.result and cast.result.hit)
    finally:
        _RUNNING.pop()
        if fresh:
            _IN_FLIGHT.discard((actor, ref))

    # **The use is over.** `PowerUsed` was announced before the body ran,
    # which is right for "when you use a power" and wrong for anything
    # reading a consequence -- a row repeating another resolved its
    # repeat before the first one's effects, and a row wanting every
    # attack roll a use made had only the last one to look at.
    from .events import PowerResolved

    # **Still holding the in-flight mark.** The guard above refuses to run
    # a row that is already running, and the `finally` releases it one
    # line before this emit -- so a row declared on `PowerResolved` and
    # triggered by its own caster answered its *own* resolution: firing
    # is a use, which resolves, which offers it again. The traceback
    # surfaced inside `query.can_act`, so it read as an engine fault
    # rather than a content one, and it accounted for thirty rows.
    #
    # Re-taken around the emit rather than moved inside the `try`,
    # because the release has to stay in a `finally`: a body that raises
    # must not leave the mark standing, or the row is refused for the
    # rest of the fight and looks merely unused.
    if fresh:
        _IN_FLIGHT.add((actor, ref))
    try:
        world.bus.emit(
            PowerResolved(
                actor=actor, power=ref, targets=list(chosen), rolls=rolls,
                trigger=trigger,
                granted_by=granted_by, granted_via=granted_via,
            )
        )
    finally:
        if fresh:
            _IN_FLIGHT.discard((actor, ref))

    # Reliable: a daily that misses everything is not spent. The keyword was
    # declared and nothing read it, so the two fighter dailies that carry it
    # were costing a use per miss -- which is the entire point of the word.
    if spend and Keyword.RELIABLE in keywords_of(world, actor, p) and not landed:
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
    world: World, actor: int, p: Power, origin: Square | None, branch: int = 0,
    augment: int = 0,
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
    want = p.target_of(augment)
    if origin is None and p.reach_of(branch, augment).kind in ("area_burst", "close_blast"):
        best: list[int] = []
        chosen: Square | None = None
        for aim in aim_points(world, actor, p, augment):
            hit = candidates(world, actor, p, aim, branch, augment)
            if len(hit) > len(best):
                best, chosen = hit, aim
        if best:
            return (best if want.everyone else best[: want.count]), chosen
    pool = candidates(world, actor, p, origin, branch, augment)
    if want.everyone:
        return pool, origin
    return pool[: want.count], origin
