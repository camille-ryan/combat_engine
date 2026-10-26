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
    my_hits_this_turn,
    my_misses_this_turn,
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

#: **"An area or a close attack power."** The question five content files were
#: each answering with their own tuple -- `_AREA_SHAPES`, `_SPREAD_OUT`,
#: `BURSTS`, `_SPREAD`, `_SPREADS` -- and four of the five left `"wall"` out.
#:
#: A wall **is** an area power, so the four were under-firing: a printed
#: "area and close attack powers" covers it, and `feats/sorcerer._SPREAD` was
#: the one that had it right. One row is affected in practice (`m5784a4` is
#: the only `wall` row in the tree that declares an attack line at all, 1 of
#: 9), which is what makes consolidating onto the wall-inclusive reading safe
#: as well as correct. #616.
#:
#: **Three neighbouring tuples are deliberately NOT this**, and folding them
#: in would be the "one symbol serving several needs" mistake:
#:
#: * `("ranged", "area_burst", "wall")` at `provokes_on`, `provokes` and
#:   `_legal_from` is *a line aimed away from you* -- it excludes close
#:   bursts and blasts precisely because those do not turn your back on
#:   anybody;
#: * `("close_burst", "close_blast", "area_burst")` in `_stretched` is the
#:   set whose size a `blast_size` modifier can grow, and a wall's size is
#:   its length rather than a radius;
#: * `MELEE_KINDS` and friends in content are the melee question.
AREA_OR_CLOSE = ("close_burst", "close_blast", "area_burst", "wall")


#: The states a printed range may switch size on. Closed, and
#: `Range.__post_init__` raises outside it.
#:
#: Three entries, from the four rows that print one. `aquatic` is **not** a
#: state of the creature at all -- it is a property of the encounter, which
#: `Cast.terrain` already reads and `World.terrain` already holds -- and it
#: is in the same set because it answers the same printed shape: a size the
#: range takes instead, decided by something other than the caster's choice.
OTHER_WHEN = frozenset({"bloodied", "grabbing", "aquatic"})


def switched(world: World, actor: int, r: Range) -> Range:
    """The printed range with its state-switched size applied, if one holds.

    **The one place the switch happens, called by every site that reads a
    size and has a world.** `dsl.reach_of` is the door for reshapes; this is
    narrower and is needed in places that door does not cover -- `area_of`,
    which must see the unswapped `kind` before it stretches, and
    `_within_reach`, which the explicit-target arm reaches without going
    through `candidates` at all.

    A grant honoured at one site and missed at the next is `keywords_of`'s
    trap and this component's commonest bug, so this is a function rather
    than five copies of two lines. #657.

    Clears the two fields on the way out: the answer is a plain range, and
    leaving them set would let a second application switch an
    already-switched size.
    """
    if r.other_when and _other_holds(world, actor, r.other_when):
        return replace(r, size=r.other_size, other_size=0, other_when="")
    return r


def _other_holds(world: World, actor: int, state: str) -> bool:
    """Is the state that switches a range's size in force for this creature?

    Both readings are about the **caster**, which is what all four cards
    say: "while *it* has a creature grabbed", "5 while *bloodied*". A
    version of this asking about the target would be a different mechanism
    and no card in the corpus prints one.
    """
    if state == "bloodied":
        from .components import Health

        hp = world.get(actor, Health)
        return hp is not None and hp.bloodied
    if state == "grabbing":
        from .types import Relation

        return bool(world.relations.targets(Relation.GRABBED_BY, actor))
    if state == "aquatic":
        # **The encounter, not the creature.** `Cast.terrain`'s own note
        # records that `World.terrain` is empty today (#539), so this reads
        # False in every fight the harness builds -- which makes the row no
        # worse than it was and the clause correct the day a board sets it.
        # Said out loud because an always-False gate is indistinguishable
        # from a misspelled one, which is the fault `TERRAIN_WORDS` exists
        # to prevent.
        return "aquatic" in getattr(world, "terrain", frozenset())
    return False


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
    #: A size the range takes **instead** while a named state holds: "Close
    #: burst 2 (**5 while bloodied**)", "Melee 2, or 1 **while it has a
    #: creature grabbed**". Four rows, three heroic.
    #:
    #: **Not `alt`, which is a printed choice.** `m5193a2` really does print
    #: "Close blast 3 **or** area burst 3 within 10" and the caster picks;
    #: these four are not choices -- the state decides, and offering a
    #: branch would put a menu entry in front of the player the card does
    #: not have.
    #:
    #: **A word, not a callable**, so the header stays data. `dsl.reach_of`
    #: resolves it and is handed the world and the actor, which is what #614
    #: built it for. `Power.reach_of` still answers the print.
    #:
    #: All four rows declared the **permissive** size and narrowed in the
    #: body, with two docstrings arguing for it -- "the permissive reach is
    #: the one the chooser must offer". Measured: with an enemy at three
    #: squares, `m1826a4` and `m6683a0` both offered it unbloodied, where
    #: the card allows two. A header wider than the card offers an illegal
    #: target and the body then *redirects* the swing. #657.
    other_size: int = 0
    #: The state that forces `other_size`. A closed vocabulary --
    #: `OTHER_WHEN` -- and `Range.__post_init__` raises on anything else,
    #: for the reason `DIFFICULT_LABELS` does: a word nothing reads is a
    #: clause that never fires on a row that looks finished.
    other_when: str = ""

    def __post_init__(self) -> None:
        if self.other_when and self.other_when not in OTHER_WHEN:
            raise ValueError(
                f"Range(other_when={self.other_when!r}) names no state"
                f" anything reads. Known: {', '.join(sorted(OTHER_WHEN))}."
                " A new one is a line in `OTHER_WHEN` plus a branch in"
                " `_other_holds`."
            )
        if bool(self.other_when) is not bool(self.other_size):
            raise ValueError(
                "Range: `other_size` and `other_when` go together -- one"
                " without the other is a size nothing switches to, or a"
                " state that switches to nothing."
            )

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


def Melee(
    n: int = 1, *, by_weapon: bool = False, from_: str = "",
    other_size: int = 0, other_when: str = "",
) -> Range:
    """`by_weapon` for a row the compendium does not list, which is `mba`.

    The melee branch of `_reach_of` decides by `BY_WEAPON`, a set
    `scripts/reaches.py --emit` derives from the compendium -- so an
    **engine-declared** row can never be in it however plainly its reach is the
    weapon's. `Ranged` has taken this argument all along for the same reason.
    """
    return Range("melee", n, by_weapon=by_weapon, from_=from_,
                 other_size=other_size, other_when=other_when)


def Ranged(
    n: int, *, by_weapon: bool = False, from_: str = "",
    other_size: int = 0, other_when: str = "",
) -> Range:
    return Range("ranged", n, by_weapon=by_weapon, from_=from_,
                 other_size=other_size, other_when=other_when)


def CloseBurst(
    n: int, *, from_: str = "", other_size: int = 0, other_when: str = "",
) -> Range:
    return Range("close_burst", n, from_=from_,
                 other_size=other_size, other_when=other_when)


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
    #: The target must have **something to take away** -- a printed "one
    #: creature carrying equipment", where the effect animates or ruins what
    #: it finds.
    #:
    #: **Not `holding=""`**, which is the no-filter default: `query.holding`
    #: answers about what is *in hand*, so a creature in armour with a
    #: shield and no weapon drawn passes it by being unfiltered rather than
    #: by qualifying. This asks the wider question.
    #:
    #: Armour is deliberately **not** counted on its own: `Gear.armour`
    #: defaults to `"cloth"` for every creature in the game, so a filter
    #: that honoured it would pass everybody and read exactly like a filter
    #: that worked. Weapons in hand, weapons on the belt, and a shield are
    #: the things a card of this shape does something to.
    carrying: bool = False
    #: The target must be a creature of **this block**, by ref -- "up to
    #: four of its own kind", "each ally of its own kind".
    #:
    #: **Nine rows filtered this in their bodies and that is not the same
    #: thing.** A body check runs after the targeter has already chosen, so
    #: a row printing "up to four of its own kind" was offered any four
    #: allies, rejected the wrong ones one at a time and paid nothing for
    #: them -- the count is spent on candidates the card never allowed.
    #: Declared here instead, so `candidates()` and `use` agree, which is
    #: the whole reason `_stands_right` is one predicate (#381).
    #:
    #: A ref, never a name: `Ident.ref` is what a monster carries. The one
    #: special value is **`"own"`** -- "of its own kind", which is the
    #: commonest printing of this line and cannot be a literal, because
    #: the block being asked for is whichever creature is casting. Four of
    #: the eight rows print it that way, and two of those name a *different*
    #: block (`m858a2` wants `m499`), so the two spellings are not
    #: interchangeable and guessing from the row's own ref would be wrong.
    ident: str = ""
    #: Read `kinds` and `ident` as **either** rather than both.
    #:
    #: **Named narrowly on purpose, and the first version was not.** I
    #: called this `any_of`, and four rows already carry
    #: `dropped=("Target.any_of",)` meaning the *general* disjunction over
    #: any two fields -- `m6172a2` says it outright, "until `Target.any_of`
    #: can hold two alternatives", wanting flanked **or** prone, and
    #: `m5302a4` wants immobilised **or** grabbed. Taking that name for
    #: this narrower thing would have made the symbol exist without
    #: satisfying a single row that asked for it, which is exactly the
    #: fault `content/CLAUDE.md` states: a symbol doing duty for two needs
    #: cannot go red or green correctly for either.
    #:
    #: The general `Target.any_of` **landed in #656** and those four rows
    #: were written in the same wave; this comment said it was "still
    #: unbuilt and still wanted" for as long as that took, which is the
    #: hazard of arguing a gap in the place the gap is not. The naming
    #: argument above still holds and is why the two fields are two
    #: fields: this one says only what it does.
    #:
    #: Eight rows print one sentence that needs it: "allies of its own
    #: sort" counts an ally that carries the printed type word *or* one of
    #: the caster's own block. Nine with `m1138a4`, which says it the other
    #: way round -- an orc *or* its own block -- and was the last row still
    #: marked `Target.ident`. #570.
    #:
    #: **Neither test alone is right, and the data is why.** The type words
    #: are real -- 101 of them across `monster.keywords` -- but uneven: only
    #: 11 stat blocks carry `kobold`, and `m906`, whose card rallies
    #: kobolds, is not one of them. Its line reads `(reptile)`. So `kinds`
    #: alone narrows the offer to the 11 and **excludes the caster's own
    #: kin**, which is the one thing the card is certainly about; `ident`
    #: alone drops every other stat block of the same family. The cards
    #: print the union and so does this.
    #:
    #: **Scoped to those two tests on purpose.** A general "any of these
    #: filters" would be a different and much vaguer field: every other
    #: clause on a target line is a restriction that genuinely compounds --
    #: a Medium *and* unheld object, a bloodied *and* adjacent enemy -- and
    #: OR-ing those would widen pools no card widens.
    kind_or_ident: bool = False
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
    #: "One creature it hit this turn." Four rows print it as a **target
    #: line**, which is why this is a field and not a `requires=`: a
    #: Requirement allows the row and then lets it be aimed at anybody,
    #: and these cards narrow the pool itself.
    #:
    #: Plain bool rather than `bloodied`'s tri-state, because no card in
    #: the corpus prints the negation -- nothing says "a creature you have
    #: *not* hit this turn". Widen it if one turns up; do not widen it in
    #: advance, which is the mistake `conditions` records from the other
    #: direction.
    #:
    #: Reads `query.my_hits_this_turn`, the shared log walk. Six rows'
    #: docstrings claimed the turn's hits were unrecorded and all six were
    #: wrong -- `lurkers_sa._landed_with` had been reading them as a
    #: `requires=` gate the whole time. #576.
    hit_by_me_this_turn: bool = False
    #: "You must have **missed** an enemy with a melee attack during this
    #: turn", and then "the same enemy". `i1132p1`, and so far only it.
    #:
    #: A separate field rather than a tri-state on the one above, because
    #: the two are not opposites: a creature can be both hit and missed in
    #: one turn, so "not hit" and "missed" are different pools and a row
    #: asking for the second would silently get the first.
    missed_by_me_this_turn: bool = False
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
    #: **A positive word reaches a player character now**, which it did not
    #: until #542. `kinds_of` was empty for one -- a character has no stat
    #: block and its race was not on the board at all -- so `kinds={
    #: "humanoid"}` aimed at a party yielded an empty pool and the row was
    #: never offered. Every character carries `natural` and `humanoid` by
    #: default, so the asymmetry this note used to warn about is gone and a
    #: positive word is as safe aimed at the party as at a monster.
    kinds: frozenset[str] = frozenset()
    #: The negative: "nonplant creatures in the burst", "not elemental". Five of
    #: the thirty rows print it, so it is not an afterthought.
    kinds_without: frozenset[str] = frozenset()
    #: **"One living creature", which is not a set operation at all.** Seven
    #: rows print it and every one of them spelled it `kinds_without={
    #: "undead"}` with the remainder carried as a marker, because #411 found
    #: the exact test and no any-of negative can say it: *not undead, and
    #: not construct unless it carries living*. Twenty-five stat blocks
    #: carry both `living` and `construct` and their cards call them living,
    #: while a construct with neither word is not -- so the loose negative
    #: admits a non-living construct and the tight one refuses the
    #: twenty-five. `query.living` is the one `if` that says it.
    living: bool = False
    #: "One creature taking ongoing damage", with no type named. One row.
    ongoing: bool = False
    #: "One creature taking ongoing **poison** damage". Seven of the eight rows
    #: name a type, so the untyped form above is the rare one -- and filtering
    #: without the type would accept a creature alight from the wrong source.
    ongoing_types: frozenset[DamageType] = frozenset()
    #: "Targets a creature **affected by** `mNNNNaN`" -- the ref of another
    #: row of this creature's whose effect the target must be carrying.
    #:
    #: Five monster rows print it and every one of them names a *sibling
    #: ability of the same stat block*: a swarm that strikes what its own
    #: cloud has caught, a sickle that finishes what its own snare holds.
    #: So this is not "any effect" -- it is a named row, which is what makes
    #: it a header field rather than a body check.
    #:
    #: Read off `Effect.by`, the ref of the row that laid an effect, which
    #: has been there since #580 and is the same field
    #: `ConditionApplied.power` and `durations.keywords_of` read. No new
    #: state: the question was always answerable and nothing asked it.
    #:
    #: **`Cast.suffering` is the body-side half and is not a duplicate of
    #: this.** That returns the *list* of creatures carrying an effect the
    #: caster laid, for a body that iterates; this is a *filter*, so the
    #: offered menu only contains legal targets. Five rows had the
    #: restriction in their bodies and played correctly while the interface
    #: and `policy/` offered them against anybody -- which is what "header
    #: is data, body is code" exists to prevent.
    #:
    #: The two read different fields and that is deliberate: `suffering`
    #: matches a substring of `Effect.label`, this matches `Effect.by`
    #: exactly. `by` is the robust one -- #580 added it precisely because
    #: six `cast.py` sites label by content (`"ongoing 5"`,
    #: `"deals:fire:weapon"`) rather than by ref, so a label match answers
    #: nothing for those. Narrowing `suffering` to `by` would change a verb
    #: with live callers and is not done here.
    affected_by: str = ""
    #: "While it has a creature grabbed, it can use this only against the
    #: grabbed creature."
    #:
    #: **Conditional, and that is the entire content of the field.** Holding
    #: nobody, the line is whatever the rest of the target says and nothing
    #: is narrowed; holding somebody, the pool is exactly those creatures.
    #:
    #: `relation=Relation.GRABBED_BY` is the plausible spelling and is
    #: wrong, which all four of the rows that wanted this said in their
    #: docstrings before it existed. That filter is unconditional, so it
    #: empties the pool whenever nothing is held -- and three of the four
    #: are the attack that *takes* the grab, so the row would be refused in
    #: exactly the situation it is printed for.
    #:
    #: The two readings are told apart on a board with nothing grabbed:
    #: `relation=` offers zero candidates there and this offers the whole
    #: pool. A rule asserting only the grabbing state cannot see the
    #: difference, which is the trap recorded against `cover_granters`.
    #:
    #: **Four rows narrowed in their bodies and that is not the same
    #: thing.** Each discarded `c.target` and swung at whoever was held
    #: instead, so the row was offered against anybody on the board and
    #: then hit somebody else: `policy/` chose a target it did not get and
    #: the page listed a menu the card forbids. #654.
    only_grabbed: bool = False
    #: **The general disjunction: a target line printing two alternatives
    #: that are not the same field.** "One bloodied **or** prone creature",
    #: "one creature it is flanking **or** one prone creature", "one
    #: immobilized creature **or** one grabbed by it".
    #:
    #: Each entry is a whole `Target`, and a creature stands right if it
    #: satisfies **any one of them** -- plus whatever this `Target`'s own
    #: clauses say, which still compound. So the printed sentence "one
    #: Medium or smaller creature that is bloodied or prone" is
    #: `max_size=MEDIUM, any_of=(Target(bloodied=True),
    #: Target(conditions={PRONE}))` and reads in that order.
    #:
    #: **Whole `Target`s rather than a list of field names**, because three
    #: of the five rows that want this pair fields from different places --
    #: `bloodied` with `conditions`, `flanked` with `conditions`,
    #: `conditions` with `relation` -- and because an alternative is
    #: sometimes itself a conjunction. Nothing new has to be taught about
    #: how a clause is tested: `_stands_right` recurses.
    #:
    #: **`kind_or_ident` stays, and is not this.** It is the narrow
    #: "`kinds` or `ident`" reading that nine rows print as one sentence,
    #: and its own note records that it deliberately refused *this* name so
    #: that `any_of` would not go green for the rows wanting the general
    #: thing. Both exist; neither is a spelling of the other.
    #:
    #: **`side` is not part of an alternative.** `candidates` builds the
    #: pool from the outer `side` before any of this runs, so two
    #: alternatives cannot be on different sides -- which is exactly what
    #: `m4766a3` prints ("an adjacent allied beast … or any creature with a
    #: type word"), and why that row is **still** marked and now names a
    #: narrower gap. Widening the outer side to `"any"` and testing the
    #: side per alternative would work and has not been built, because one
    #: row is not the evidence for putting a pool test inside a predicate
    #: that has never had one.
    #:
    #: **Not a general "any of these filters".** Every *other* clause on a
    #: printed target line compounds -- a Medium and unheld object, a
    #: bloodied and adjacent enemy -- and OR-ing those would widen pools no
    #: card widens. This field is only for the cards that print the word.
    any_of: tuple[Target, ...] = ()
    #: "Targets enemies in the burst **touching the ground**", "affects only
    #: creatures **in contact with the ground**", and the row printing the
    #: negative -- "a **nonflying** creature's space".
    #:
    #: **Tri-state, for `bloodied`'s reason**: the field has to tell "must be
    #: on the floor" from "must not be" from "the card does not say", and a
    #: bool holds two of those. `m5741a5` prints the negation, so with a bool
    #: it would be unwritable or written as its own opposite.
    #:
    #: Reads `query.on_the_ground`, which is **two** inputs -- height and how
    #: the creature is moving. A hovering creature at height 0 is not
    #: touching the ground and a climbing one is holding a wall, so neither
    #: `falling.height` nor `falling.airborne` alone is the printed test.
    #: Five rows asked it in their bodies and spelled it four different ways
    #: between them, one of them with the wrong notion of airborne. #660.
    on_the_ground: bool | None = None
    #: "One creature in the burst the m3675 has **concealment or cover
    #: against**." One row, and it is a field rather than a body check for
    #: the usual reason: the page and `policy/` read the header.
    #:
    #: **Reads `query.sheltered_from`, one reader over both halves of the
    #: printed "or".** Not `any_of` over two fields, because concealment is
    #: a property of the caster alone and does not vary by candidate -- a
    #: field that answers the same for every creature in the pool is a
    #: Requirement in a target line's clothing, and OR-ing it with a real
    #: per-target test inside `any_of` would read as though both narrowed.
    sheltered_from: bool = False

    def __str__(self) -> str:
        if self.label:
            return self.label
        if self.side == "self":
            return "You"
        # **`"team"` prints the caster, because that is the whole of what
        # makes it a different pool from `"ally"`.** It was missing from this
        # dict entirely, so printing a `team` target raised
        # `KeyError: 'team'` -- the same latent crash `candidates`' pool dict
        # had, in the second of the three places `"team"` has to be known.
        # `_SIDES` below listed it the whole time, which is exactly the drift
        # `_SIDES`' own comment says it exists to prevent and did not.
        if self.side == "team":
            if self.everyone:
                return "You and each ally in the area"
            return ("You or one ally" if self.count == 1
                    else f"You or up to {self.count} allies")
        who = {
            "enemy": "creature", "ally": "ally", "any": "creature",
            "other": "creature", "object": "object",
        }[self.side]
        if self.everyone:
            return f"Each {who} in the area"
        return f"One {who}" if self.count == 1 else f"Up to {self.count} {who}s"


#: Every `side` `candidates()` can build a pool for, plus `"self"`, which
#: it answers before reaching the pool. Declared here so the import-time
#: guard and the pool cannot drift apart -- the guard exists because they
#: could, and `KeyError: 'creature'` is what that looked like.
_SIDES = frozenset({
    "self", "enemy", "ally", "any", "other", "team", "object",
})

ONE_CREATURE = Target("enemy", 1)
#: A power aimed at anybody at all. `ONE_CREATURE` is the *enemy* pool, so a
#: beneficial row pointed at it is unusable on the only creatures it is ever
#: meant for.
ANY_CREATURE = Target("any", 1)
#: "One ally", and the caster is **not** one of its own allies -- the printed
#: word, and what `Cast._side` has always answered on the body path.
#:
#: This comment used to say the opposite ("`ONE_ALLY`'s pool includes the
#: caster, which reads as 'you or one ally'"), and it was accurately
#: describing `candidates`, which disagreed with `_side` about the same
#: word. #364 flipped the pool; a row that means you as well now says
#: `YOU_OR_ONE_ALLY`.
ONE_ALLY = Target("ally", 1)
SELF = Target("self", 1)
EACH_ENEMY = Target("enemy", 99, everyone=True)
EACH_CREATURE = Target("any", 99, everyone=True)
#: Everyone in the area **except** the caster. A close burst declared with
#: `EACH_CREATURE` catches the creature standing at its centre, which is the
#: printed reading for some rows and plainly not for others.
EACH_OTHER = Target("other", 99, everyone=True)
EACH_ALLY = Target("ally", 99, everyone=True)
#: **"You or one ally", and "you and each ally".** The `team` pool is allies
#: *plus* the caster, and these two are the only honest way to declare a card
#: that prints the word "you" beside the word "ally".
#:
#: Named after the printed phrases rather than as `ONE_TEAM`/`EACH_TEAM`,
#: because the pool name answers "which creatures" and the printed line is
#: what an author is matching against. `YOU_AND_ALLIES` already existed as a
#: local constant in one content file, spelled with the `ally` pool, which is
#: the mistake these exist to stop.
#:
#: **Until #364 these could not be written.** `candidates`' pool dict had no
#: `"team"` key at all, so declaring it raised `KeyError` -- which is why 0
#: rows used it and why 170 rows printing "you and each ally" were declared
#: `ally` instead. They were correct only because `candidates` added the
#: caster to the `ally` pool, which is the disagreement #364 is about.
YOU_OR_ONE_ALLY = Target("team", 1)
YOU_AND_EACH_ALLY = Target("team", 99, everyone=True)
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
    #: This row **counts as** a basic attack: `"melee"` or `"ranged"`.
    #:
    #: **A header field and not per-character state**, which is the whole
    #: argument. Two authors reached for one independently -- *"the Special
    #: line ... has no header field"* and *"the header has no field that sets
    #: it"* -- and they were right: "counts as a melee basic attack" is a
    #: fact about the card, true for everybody who holds it, so the UI and
    #: `policy/` can read it without running a body. #522.
    #:
    #: **Different from `c.as_basic`, and 4e means them differently.**
    #: Camille's wording: *"'In place of a melee basic attack' means it could
    #: be used when a melee basic attack could be used, but it is NOT a melee
    #: basic attack. 'Counts as' or 'can be used as' a basic attack means
    #: that it would benefit from modifiers to basic attacks."* So this
    #: declares both halves -- the offer **and** the designation -- where
    #: `c.as_basic` declares only the offer and deliberately leaves
    #: `Powers.basic` alone.
    #:
    #: `dsl.basics_of` is the read, and both of its callers matter:
    #: `basic_options`, so a granted swing offers the row, and
    #: `resolve._is_basic`, so `ctx["basic"]` lets a modifier ask.
    basic: str = ""
    #: **A standing "in place of a basic attack", declared rather than laid.**
    #: The window the row stands in for -- `"charge"`, `"opportunity"`,
    #: `"challenge"`, `"ranged"`, or `"*"` for every melee one -- and `""`
    #: for the great majority that stand in for nothing.
    #:
    #: `c.as_basic` is the verb and does the same filing, and it is the right
    #: door for a row that *grants* the substitution to somebody -- a feat
    #: armed at the start of a fight, which is all 14 of its callers. It is
    #: the wrong door for a row whose **own card** says it: "When charging,
    #: it can use this power in place of a melee basic attack" is a property
    #: of the row, and a body that files it runs only when the row is used,
    #: which is after the charge menu has already been built. Three rows
    #: carried `c.as_basic(charge=)` for that, and the parameter was never
    #: the gap -- `window="charge"` has always existed. The gap was a *body*
    #: where a header was wanted, the same shape `basic=` above is in. #677.
    #:
    #: `basics_of` deliberately does **not** read this, and that is #522's
    #: distinction: a row swung *in place of* a basic attack is not one, so
    #: it must not pick up a basic-attack modifier. Only `basic_options`
    #: reads it, which is the offer and nothing else.
    instead_of_basic: str = ""
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
    #: A recharge condition that is a **state, not a moment**, re-asked at
    #: the start of the creature's turn beside the d6. `recharge_when` takes
    #: a `Trigger` and so needs an event to watch; ten rows print a standing
    #: condition instead -- "recharges when no creature is affected by this
    #: power" -- which becomes true by any of five routes and has no single
    #: moment to subscribe to. See `query.lingers` and #489.
    #:
    #: All three forms coexist, because a card may print more than one:
    #: the die, a trigger, and a state.
    recharge_while: Callable[[World, int], bool] | None = None
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
    #: pick a lock" is not waiting on `c.skill_circumstance()`; no board
    #: presents a lock, so that verb would be a mechanism nobody passes a
    #: purpose to, and a marker naming a symbol that must never be built
    #: sits in the queue forever. The marker grammar exists to stop exactly
    #: that.
    #:
    #: **This read "nothing ever rolls Thievery in a fight", and that is
    #: false** -- thievery is rolled three times in the tree and `i455p1`
    #: is an encounter free action triggered by one. The wide version of the
    #: claim is what 24 rows were inert on, each of them arguing about the
    #: *engine* where the honest argument is about the *card*. #691. The
    #: paragraph below already says the right thing and says it twice: the
    #: claim is about the circumstance, never about the skill.
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
    #: **This row's clause is written into another row's body**, naming that
    #: row. The convention is #550: a feat that names one power has its
    #: clause written into that power, gated on `c.feat("<this ref>")`.
    #:
    #: **Only when this row's body is empty**, which is narrower than this
    #: field first claimed and was found on the first migration. `f3188`
    #: and `f3234` each write a clause into a power *and* print a standing
    #: skill bonus of their own; marking either would stop `audit.py`
    #: firing a row with live clauses in it, which is the one thing the
    #: field must not do. A row that is half-migrated carries no marker at
    #: all -- it still has a body and still fires.
    #:
    #: It also used to say the clause should be laid with
    #: `label="<this ref>"` to keep the credit here. Both halves were
    #: wrong: `c.bonus` and `c.penalty` took no `label=`, and there is no
    #: credit to keep, because a row carrying this field is **not fired**
    #: by the sweep at all. `c.bonus(label=)` exists now and is for two
    #: penalties in one body, which is a stacking question and not this
    #: one.
    #:
    #: So the body is empty **and the clause is written**, which no other
    #: marker could say. `todo=` claims nothing works; `obsolete=`,
    #: `declined=` and `defect=` all refuse the row; `narrative=` and
    #: `out_of_combat=` claim it has no combat meaning, when it has one laid
    #: elsewhere.
    #:
    #: **`dropped=` is the one it combines with**, and it has to. A row has
    #: several clauses: this field says where the written ones live, and
    #: `dropped=` says a *different* clause is still owed. 13 of the 30
    #: rider-bearing feats are in exactly that state. Refusing the
    #: combination -- which the first version did -- made #550 one 58-row
    #: change that could not be staged, because a power's exclusivity
    #: `elif` needs every feat naming it to be inline, while a feat's
    #: marker needs every power *it* names to be finished. Neither side can
    #: go first. The mistake was reasoning from the markers' *names*
    #: instead of from the fact that a row has more than one clause --
    #: `c.race_option()` made the same one across six gaps.
    #:
    #: **It must not refuse the row**, which is the whole subtlety. The
    #: other five markers exclude a row from every chargen draw -- and a
    #: feat that is never dealt is a feat `c.feat()` answers False for, so
    #: the clause in the power would never fire and the migration would
    #: silently undo itself. `usable` therefore says nothing about this
    #: field.
    #:
    #: Reconciled by `lint.py`: **every** named row's source must actually
    #: mention `c.feat("<this ref>")`. A pointer at a power that no longer
    #: carries the clause is the obvious failure and would be silent, which
    #: is the fault #492 and #551 are both open about. #553.
    #:
    #: **A tuple, because one feat normally names several powers.** The
    #: first draft of this field took a single ref and was wrong for 28 of
    #: the 32 rider-bearing feats -- they ride two, three or four powers
    #: each, and the card is "you gain a benefit with any of the following
    #: exploits you possess". Caught on first use rather than by review.
    implemented_in: tuple[str, ...] = ()
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
            if self.thrown_by_hand:
                return bool(gear.melee)
            if gear.ranged is None:
                return False
            # **And it has to be loaded**, which is the half that makes the
            # load worth modelling at all. Three weapons print `load
            # minor`; firing one empties it and `actions` offers the
            # reload. A `load free` weapon and everything without a load
            # property answer True here always -- `ready_to_fire` carries
            # that, so this site does not have to remember it. #675, #725.
            from .query import ready_to_fire

            return ready_to_fire(world, actor, gear.ranged)
        if kind == "melee":
            return bool(gear.melee)
        return True

    def provokes_on(self, branch: int = 0, augment: int = 0) -> bool:
        """Does *this branch* leave an opening? The melee half does not."""
        if self.no_provoke:
            return False
        return self.reach_of(branch, augment).kind in PROVOKING_KINDS

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
        return self.reach.kind in PROVOKING_KINDS

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
        reach = self.reach_of(branch, augment).kind
        ranged = reach == "ranged"
        # The estimator is a *forecast*, so it hands the cover read the
        # shape it knows -- otherwise a target carrying "cover against
        # ranged attacks" is priced as having none, and the policy picks
        # the shot the rules will penalise. Two keys, not the full attack
        # context: this runs before any attack exists. #644.
        bonus -= int(cover_between(world, actor, target, ranged=ranged,
                                   ctx={"ranged": ranged, "reach": reach}))
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
    #
    # **`x5_` is a disease**, and it is the third time this list has grown for
    # the same reason: a row waiting on something the database now holds had
    # no way to name it. Until `#389`'s table landed there was nothing behind
    # the ref, so the 47 rows that want one say `c.contract(ref)` -- naming
    # the *verb* and leaving the ref abstract, which is the only thing they
    # could do. With the table built the ref is nameable, and
    # `x5_\d+` is the shape the ETL mints.
    #
    # Deliberately narrow: `x\d+_\d+` in general would admit the 3,071 ritual
    # and deity tokens, which are **not** rows and would make a marker
    # unverifiable again -- the exact fault this pattern exists to prevent.
    r"|[pmifr]\d+[a-z]?\d*|(?:cf|rt):[\w-]+|x5_\d+"
)

#: What a `narrative=` element may look like -- `skill:thievery`. See
#: `Power.narrative` for why this is a closed vocabulary and not a symbol.
_NARRATIVE = re.compile(r"skill:([a-z]+)")
#: A row's own ref, for `implemented_in=`. The shapes the tree actually
#: uses: a power, monster ability, item block, feat, class-feature leg or
#: racial trait. Checked rather than taken on trust so that a pointer at a
#: symbol or a sentence is refused where it is written, not discovered by
#: `lint.py` later. #553.
_REF = re.compile(r"(?:[pmif]\d+[a-z]?\d*[a-z]?\d*|cf:[\w-]+|rt:[\w:-]+)")

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
    basic: str = "",
    instead_of_basic: str = "",
    requires_alt: Callable[[World, int], bool] | None = None,
    trigger: str = "",
    on: Trigger | Sequence[Trigger] | None = None,
    recharge: int = 0,
    recharge_when: Trigger | Sequence[Trigger] | None = None,
    recharge_while: Callable[[World, int], bool] | None = None,
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
    implemented_in: Iterable[str] = (),
    proficiency: Iterable[str] = (),
    swap: Swap | None = None,
    augments: Iterable[Augment] = (),
) -> Callable[[Body], Body]:
    """Declare one power or one monster ability.

    `ref` is the compendium id -- `p289`, or `m145a2` for a stat block's
    second ability. Never a name: the engine has no use for one, and the
    agent that wrote this function was never shown it.
    """
    # **A `Target.side` the pool has no entry for is refused here**, the
    # same bargain `c.bonus(once=)` struck in #544: an unrecognised key is
    # a typo, and the only question is whether it is reported at import or
    # raises in play. `candidates()` builds its pool as a dict literal and
    # subscripts it, so `Target("creature", 1)` -- a plausible spelling,
    # since a card's "one creature" is `ONE_CREATURE` and that is
    # `side="enemy"` -- got all the way to `KeyError: 'creature'` inside a
    # row the auditor was firing. Written by me, caught by `audit.py`
    # rather than by `lint.py`, which is one wide sweep too late.
    if target is not None and getattr(target, "side", "") not in _SIDES:
        raise ValueError(
            f"{ref}: target side {getattr(target, 'side', None)!r} is not one "
            f"of {sorted(_SIDES)}. A card's 'one creature' is `ONE_CREATURE`, "
            f"which is side='enemy'."
        )
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
    implemented_in = tuple(implemented_in)
    if implemented_in:
        # **Finished, with the clause in another row.** Every other marker
        # says something incompatible: the two symbol lists promise a symbol
        # that will never arrive, the three refusals take the row out of play
        # *and out of every chargen draw* -- which would stop the feat being
        # dealt and so stop `c.feat()` in the implementing row ever answering
        # True -- and `narrative=`/`out_of_combat=` claim no combat meaning.
        # **`dropped=` is allowed beside it, and nothing else is.** The two
        # describe *different clauses* of the same row: "these clauses live
        # in those powers, and this symbol is still owed". 13 of the 30
        # rider-bearing feats are in exactly that state, and refusing the
        # combination -- which this did for an afternoon -- made #550's
        # migration one 58-row change that could not be staged, because a
        # power's exclusivity needs every feat naming it to be inline and a
        # feat's marker needs every power it names to be done.
        #
        # The first version reasoned from the markers' *names* rather than
        # from the fact that a row has several clauses, which is the same
        # mistake `c.race_option()` made at six times the scale.
        #
        # The other five stay refused and for unchanged reasons: `todo=`
        # says nothing here works, which contradicts a clause living
        # elsewhere; `narrative=` and `out_of_combat=` claim no combat
        # meaning; and `obsolete=`, `declined=` and `defect=` all refuse the
        # row, which would stop the feat being dealt and so stop the
        # `c.feat()` gate in the implementing power ever answering True.
        if todo or narrative or obsolete or declined or defect \
                or out_of_combat:
            raise ValueError(
                f"{ref}: implemented_in may be combined with dropped= and "
                f"nothing else -- it says this row's written clauses live in "
                f"{tuple(implemented_in)!r}, and the other markers each say "
                f"something incompatible with that"
            )
        for host in implemented_in:
            if not _REF.fullmatch(host.strip()):
                raise ValueError(
                    f"{ref}: implemented_in={host!r} is not a ref. Name the rows "
                    f"whose bodies carry this one's clauses, so the pair reads "
                    f"both ways and `lint.py` can check each clause is really "
                    f"there."
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
        basic=basic,
            instead_of_basic=instead_of_basic,
            requires_alt=requires_alt,
            trigger=trigger,
            on=on,
            recharge=recharge,
            recharge_when=recharge_when,
            recharge_while=recharge_while,
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
            implemented_in=implemented_in,
            proficiency=tuple(proficiency),
            swap=swap,
            augments=tuple(augments),
        )
        return body

    return wrap


def get(ref: str) -> Power | None:
    return REGISTRY.get(ref)


#: How a row's ref names the **compendium entry** it was printed in. One
#: entry is one page, and a page may print several rows:
#:
#: * `m1234a5` and `m1234c0a5` -- a stat block's abilities, so the entry is
#:   the creature. `m1234c0` is a conjuration printed inside an item's own
#:   page (#601) and is its own entry, which is why the `c<n>` is kept.
#: * `i601p1`, `i601x1` -- an item's Power and its Property. The unit of
#:   *work* is the block (`content/CLAUDE.md`), and the unit of **printing**
#:   is the item.
#: * `p123b` -- a second card printed inside another power's entry, 154 of
#:   them. The `b` is dropped, so the pair is one entry.
#:
#: Anything else -- `f959`, `cf:fighter-...`, `rt:r33-...`, `comp:...` -- is
#: its own entry and comes back unchanged. A feat pair is `f959`/`f960b`,
#: two *different* ids, so it is genuinely two entries and the convention
#: cannot be read off the ref.
_ENTRY = (
    re.compile(r"^(m\d+(?:c\d+)?)a\d+.*$"),
    re.compile(r"^(i\d+)[a-z]\d+[a-z]?$"),
    re.compile(r"^(p\d+)b$"),
)


def entry_of(ref: str) -> str:
    """The compendium entry a row was printed in. See `_ENTRY`."""
    for pattern in _ENTRY:
        hit = pattern.match(ref)
        if hit:
            return hit.group(1)
    return ref


def entry_defect(ref: str) -> str:
    """Why this row's whole **entry** is unfit to appear in the game.

    **Camille's rule, 2026-10-15, widened from the monster case:** *"the
    ENTIRE compendium entry should be dropped if any part of it is
    defective."*

    `defect=` already meant that for a stat block -- `loader.defective`
    derives it from the rows and `pick` stops offering the creature, because
    a monster fielded without the thing its card is about is wrong in every
    fight. The same argument holds for an item and for a power and nothing
    was doing it: a tome whose Power is defective was still dealt, still
    worn, and still paid out its Property, so a player held a working
    fraction of an object the compendium cannot describe.

    Derived from the rows and never listed again, for `loader.defective`'s
    reason: `defect=` on the row is the one place the fact lives, so a
    second list cannot go stale against it.

    Returns the offending row's reason prefixed with its ref, or `""`.

    **Indexed rather than walked.** `usable` is on the path of every
    power-use check, and a scan of 23,000 rows per call is not something to
    put there. `REGISTRY` is filled once at import and never afterwards, so
    the index is built on first ask; `_forget_defects` exists for the one
    caller that legitimately adds a row later, which is a plant test.
    """
    if _DEFECTS is None:
        _index_defects()
    assert _DEFECTS is not None
    return _DEFECTS.get(entry_of(ref), "")


#: Entry -> the first defective row in it and its reason. `None` until asked.
_DEFECTS: dict[str, str] | None = None


def _index_defects() -> None:
    """One pass over `REGISTRY`, keyed by entry. See `entry_defect`."""
    global _DEFECTS
    found: dict[str, str] = {}
    for row, p in sorted(REGISTRY.items()):
        if p.defect:
            found.setdefault(entry_of(row), f"{row}: {p.defect}")
    _DEFECTS = found


def _forget_defects() -> None:
    """Drop the index, for a test that declares a row after the first ask."""
    global _DEFECTS
    _DEFECTS = None


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

    **`branch` is resolved by `_aimed_shape`, not by `Power.reach_of`.** This
    read the header directly until #884, which made it answer for the printed
    aiming whatever aiming actually ran: an index past the printed ones
    *clamped* to the print, and an **optional** reshape was applied to the
    printed aiming -- the one thing `optional=` exists to prevent. The swap
    still lands below rather than inside the helper, because the
    `blast_size` stretch needs the unswapped `kind` first; that ordering is
    the reason this function does not come through `reach_of`'s door and it
    is unchanged.
    """
    r, swap = _aimed_shape(world, actor, p, branch, augment)
    # Every origin, unioned. One companion gives one origin and the same answer
    # as before; two give the area either of them could reach, which is what the
    # printed rule asks for on both of its sentences. See `origins`.
    mine = set()
    for eye in origins(world, actor, r):
        mine |= squares(world, eye)
    stretch = _stretched(world, actor, r.kind,
                         {"power": p.ref, "range_kind": r.kind})
    # **Not applied to a melee or ranged range here**, because those go
    # through `_reach_of` below and it derives its own answer from the
    # weapon -- so a size raised here was read, overwritten and lost. See
    # `_reach_of`. The spread kinds have no such second opinion and take it
    # directly.
    if stretch and r.kind not in ("melee", "ranged"):
        r = replace(r, size=r.size + stretch)
    # **After the stretch, and it has the last word.** "Its area changed to
    # 1 square" is absolute, so a `blast_size` bonus standing at the same
    # moment is overridden rather than added to -- which is what the card
    # says and the opposite of what applying this first would do. No printed
    # pair of these is known; the order is stated so the answer is not an
    # accident of line order. #614.
    #
    # **Whichever reshape this branch names**, settled above: the replacing
    # one for a printed aiming, and for an index past the printed ones the
    # *particular* offered reshape that contributed that index. This line
    # used to ask `_reshaped` for the first match of either kind, so a
    # character holding an optional reshape had it imposed on the printed
    # aiming as well as offered beside it. #884.
    if swap is not None:
        r = swap(r)
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
        out = spread(mine, within_of(world, actor, r,
                                     {"power": p.ref, "range_kind": r.kind}))
    elif r.kind in ("melee", "ranged"):
        out = spread(mine, _reach_of(world, actor, r, p.ref, stretch=stretch))
    else:
        out = frozenset(mine)
    return frozenset(sq for sq in out if world.grid.inside(sq))


def _reach_of(
    world: World, actor: int, r: Range, ref: str = "", *,
    stretch: int | None = None,
) -> int:
    """How far this range actually carries.

    For a weapon range that is the **long** range, because a shot past
    the normal one is legal and merely takes the -2 that
    `resolve._long_range` charges. Capping the offer at the normal range
    made that penalty unreachable: the target was refused before it could
    be charged, so the whole of `_long_range` was dead code.

    **`stretch` is "the target's reach increases by 1", and it used to be
    thrown away here.** `area_of` computed it, added it to `r.size`, and
    then called this -- which answers a by-weapon range off the weapon and
    never looks at `r.size`. So the modifier was read, applied and
    discarded on the **common** path: 1,023 melee rows print "melee
    weapon" against 325 with a fixed number, and `mba` is on it too, so the
    melee basic attack ignored a reach bonus. #533.

    `None` means ask `_stretched` here. That is the default on purpose:
    `_within_reach`, `Cast.reach_of` and the three policy readers all call
    this without a stretch, and none of them applied one anywhere else --
    so the modifier reached the *area* a power offered and not the question
    "may I reach that creature". Computing it here is what makes those
    four agree with each other.
    """
    from .components import Gear

    if stretch is None:
        stretch = _stretched(
            world, actor, r.kind, {"power": ref, "range_kind": r.kind}
        )
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
            return r.size + stretch
        # **The weapon's reach plus what the card grants**, and neither `max` with
        # the printed size nor the weapon alone. Both of those were tried and both
        # were wrong, because the figure they needed had been thrown away upstream:
        # four of these rows print "Melee weapon +1 reach", the ETL kept only the
        # "melee weapon" half, and so the bonus could not be read from the row at
        # all. Fixed in the parser; `GIVES` is what it now records. One square
        # unarmed, which is what a fist reaches.
        held = getattr(gear, "main", None) if gear else None
        worn = getattr(held, "reach", None) if held else None
        return (worn or 1) + GIVES.get(ref, 0) + stretch
    if not r.by_weapon:
        return r.size + stretch
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
    return (flies[1] if flies else r.size) + stretch


#: The kinds of range that turn your back on somebody. One tuple, three
#: readers -- `Power.provokes`, `Power.provokes_on` and `provokes_for` below
#: -- where it used to be written out at each. A set spelled three times is
#: three chances to update two of them.
PROVOKING_KINDS = ("ranged", "area_burst", "wall")


def provokes_for(
    world: World, actor: int, p: Power, branch: int = 0, augment: int = 0
) -> bool:
    """Does **this creature's** use of this row leave an opening?

    `Power.provokes_on` is the printed line and takes no creature, so it
    cannot see a reshape. This is the same question asked where there is
    somebody to ask about, and it is a function rather than inline in `use`
    because the first version *was* inline -- which made it a second copy of
    `provokes_on`'s set, the drift fault this engine keeps paying for, and
    left `drivers.recast_range` asserting its own copy of the logic rather
    than the code that runs.

    A ranged power a feat lets you use as a melee attack must not turn your
    back on the brute in front of you. That is the whole of why the card is
    worth taking. #614.
    """
    return not p.no_provoke and reach_of(
        world, actor, p, branch, augment
    ).kind in PROVOKING_KINDS


def reach_of(
    world: World, actor: int, p: Power, branch: int = 0, augment: int = 0
) -> Range:
    """This row's range **for this creature**, reshape applied.

    `Power.reach_of` is the printed line: header data, one value fixed at
    import and shared by everybody who ever holds the row. Fifteen heroic
    rows print a per-character replacement of it -- a ranged power usable as
    a melee attack, a close blast offered as an area burst, a bow feat making
    a melee power ranged -- and a header cannot say that for one character
    only. #614.

    **This is `durations.keywords_of`'s shape, and that is not a coincidence
    -- it is the same problem.** That docstring records the trap and it is the
    whole reason this function exists rather than each site asking
    `_reshaped` for itself: *there were 22 sites reading the header, and a
    grant honoured at 21 is a modifier nothing consults at the 22nd.* So
    every reader that **has a world and an actor** must come through here.

    The ones that cannot are named, because a blind spot nobody has written
    down is indistinguishable from a bug:

    * `Power.provokes`, `Power.label_of` and `Range.branches` are header-only
      -- no world, no actor -- so they answer the printed line. `provokes_on`
      is the one a caller holding a world should prefer, and
      `Cast._would_provoke` already does.
    * `Power.usable_with` reads the kind to pick a weapon from `Gear`. It has
      a world, so it could come through here; it is left on the print
      deliberately, because a reshape changing which *weapon* a row demands
      is not a thing any of the fifteen cards says, and widening it would
      make a dagger feat refuse the dagger.

    `area_of` resolves its branch through `_aimed_shape` below, which is this
    function's first half factored out, and still applies the swap itself: it
    needs the unswapped `kind` first to decide whether a `blast_size` stretch
    applies at all, so the order there is stretch-then-swap and is documented
    on the spot. Before #884 it had a second copy of the resolution that read
    the header, and the two answered differently.
    """
    r, swap = _aimed_shape(world, actor, p, branch, augment)
    return swap(r) if swap is not None else r


def _aimed_shape(
    world: World, actor: int, p: Power, branch: int = 0, augment: int = 0
) -> tuple[Range, Callable[[Range], Range] | None]:
    """The shape a branch names for this creature, and the reshape owed it.

    **One door for branch resolution**, which is the whole of #884.
    `area_of` had its own copy reading `Power.reach_of` -- header data, which
    cannot know what this creature was offered -- so an index past the
    printed ones *clamped* to the print, and `Range.reach_of`'s clamp made
    that silent rather than loud. Two readings of one index, and the blind
    one was answering for all 456 `c.area()` call sites.

    Returned as a **pair** rather than a finished `Range` because the two
    callers need the swap at different moments: `reach_of` applies it at
    once, `area_of` must measure its stretch against the unswapped `kind`
    first. Handing back the callable is what lets them share the choice of
    *which* reshape without sharing the moment it lands.

    `switched` is applied on **every** path, including the extra index and
    the fallback. It was applied only to the printed branch, which this
    function's own argument says is wrong: a reshape replaces the line the
    creature is holding right now, so "close burst 2 (5 while bloodied)"
    has to be switched *before* the reshape sees it, whichever index asked.
    No row in the tree is both state-switched and reshaped, so this is
    inert today and correct rather than measured-as-different.
    """
    printed = p.branches
    if branch in printed:
        # **The state-switched size, before any reshape.** "Close burst 2 (5
        # while bloodied)" is the printed line for this creature right now,
        # and a reshape replaces *that* -- the card the feat is rewriting is
        # the one the creature is actually holding.
        r = switched(world, actor, p.reach_of(branch, augment))
        # A **replacing** reshape only. An optional one is reached through
        # its own index below, and applying it here as well would impose the
        # alternative on the printed aiming -- which is the whole thing
        # `optional=` exists to avoid.
        return r, _reshaped(world, actor,
                            {"power": p.ref, "range_kind": r.kind},
                            optional=False)

    # **An extra index**, contributed by an optional reshape in force for
    # this creature. Derived from the printed count rather than hard-coded:
    # a row with `reach.alt` already owns 0 and 1, so its first extra is 2.
    #
    # Applied to the row's **first** printed branch. Every one of the eleven
    # cards names one alternative to one printed shape; a card offering an
    # alternative to the *second* branch of a two-range row is not among
    # them, and inventing a rule for it here would be a second opinion about
    # what the pages say.
    base = switched(world, actor, p.reach_of(printed[0], augment))
    extras = _offered(world, actor, p)
    spot = branch - len(printed)
    if 0 <= spot < len(extras):
        return base, extras[spot]

    # A branch nothing offers. The print for branch 0, which is what every
    # caller that guessed an index got before any of this existed.
    #
    # **Still a clamp, and deliberately not a raise.** #884 asked for the
    # decision: `api.render` hands this an index chosen by the client, so
    # raising turns a crafted request into a 500, and `turns`/`policy` walk
    # `branches_for` in a loop where one bad index would stop a whole turn.
    # The honest guard is the one that already exists a layer up --
    # `can_branch_for` answers whether an aiming is open to this creature --
    # and the clamp is what a caller that did not ask gets.
    return base, None


def can_branch_for(world: World, actor: int, p: Power, branch: int = 0) -> bool:
    """Is this aiming open to this creature -- printed or contributed?

    `Power.can_branch` indexes the printed branches: `requires_of` is
    `requires_alt if branch else requires`, so handing it an extra index
    would read the *alternate* branch's Requirement on a row that has none
    and refuse an aiming the card allows.

    **An extra aiming carries the printed branch's Requirement**, because
    that is what the cards say. Every one of the eleven gates the *feat* --
    "when you are attacking with a greatbow and you have proficiency" --
    which is checked where the reshape is laid, not where it is aimed. The
    target row's own Requirement does not change because you chose the other
    shape. #614.
    """
    printed = p.branches
    return p.can_branch(world, actor, branch if branch in printed else printed[0])


def branches_for(world: World, actor: int, p: Power) -> tuple[int, ...]:
    """Which aimings **this creature** may choose between for this row.

    `Power.branches` is the printed line -- `(0, 1)` for a row printing two
    ranges, `(0,)` otherwise -- and header data cannot say that one character
    has a third option. Eleven heroic rows print exactly that: "you can
    **choose** to make it X **instead of** Y". #614.

    So each *optional* reshape in force adds an index past the printed ones,
    and `reach_of` resolves it. The printed aimings keep their indices and
    their shapes, which is the half that matters: a feat offering an
    alternative must not take the card's own shape away.

    **Every reader of `Power.branches` that has a creature must come through
    here**, for the reason `durations.keywords_of` records and `reach_of`
    repeats: a grant honoured at three sites and missed at the fourth is a
    modifier nothing consults. The four are `dsl.unusable`, `dsl.usable`,
    `dsl._within_reach` and `query.range_profile`.

    `Range.branches` itself stays header-only and is named as a blind spot on
    `reach_of`: it answers for the card, which is what the card asks.
    """
    return (*p.branches, *range(len(p.branches),
                                len(p.branches) + len(_offered(world, actor, p))))


def _offered(
    world: World, actor: int, p: Power
) -> tuple[Callable[[Range], Range], ...]:
    """Every *optional* reshape standing on `actor` for this row, in order.

    All of them, where `_reshaped` returns only the first. That difference is
    deliberate and is the one place the two semantics genuinely part: two
    cards both **replacing** one use is not a printed case and composing them
    would invent a rule, but two cards each **offering** an alternative is
    just a longer menu, and refusing the second would silently drop a feat
    the character has.

    Composing is still refused -- each extra applies to the printed shape,
    never to another extra's output.
    """
    out = []
    for eff in world.effects.of(actor):
        if eff.reshape is None or eff.suspended or not eff.reshape_optional:
            continue
        gate = eff.reshape_when
        r = p.reach_of(p.branches[0])
        if gate is not None and not gate(
            {"power": p.ref, "range_kind": r.kind}
        ):
            continue
        out.append(eff.reshape)
    return tuple(out)


def _reshaped(
    world: World, actor: int, ctx: dict[str, Any], *, optional: bool | None = None
) -> Callable[[Range], Range] | None:
    """A standing replacement for this row's **shape**, if one is in force.

    `_stretched` beside this is the same arrangement one word smaller: it
    returns an `int` added to `r.size`, so it can grow a burst and can never
    make it a blast. Four of the six cards under #614 do exactly that, and
    the gap was never the reading -- it was that `Mod.value` is an integer.

    First match wins and the rest are ignored, deliberately. Two cards both
    reshaping one use is not a printed case, and *composing* them -- a blast
    to a burst and then that burst to a square -- would invent a rule no page
    states. The effects are walked in the order they were laid, so "first"
    means the earliest still standing.

    **A read, with no side effect.** `area_of` is a query: the renderer calls
    it to highlight squares and `_aimings` calls it once per candidate
    origin, so spending a one-shot here would burn it on a preview. A card
    reading "the next power you use" ends its own effect on the `PowerUsed`
    it was waiting for -- see `i2467p1`, which watches for its own
    qualifying use.
    """
    for eff in world.effects.of(actor):
        if eff.reshape is None or eff.suspended:
            continue
        # `optional=None` is "either", which is what `area_of` wants: it
        # draws the squares for the aiming actually in play, and by then the
        # branch has already selected which. `reach_of` passes `False`, so a
        # merely *offered* alternative never overwrites the printed shape.
        if optional is not None and eff.reshape_optional is not optional:
            continue
        gate = eff.reshape_when
        if gate is not None and not gate(ctx):
            continue
        return eff.reshape
    return None


def target_of(
    world: World, actor: int, p: Power, augment: int = 0
) -> Target:
    """This row's target line **for this creature**, replacement applied.

    `Power.target_of` is the printed line; this is the per-creature door, the
    way `reach_of` is for the range. One mechanism writes it --
    `Cast.becomes_burst`, through `Effect.retarget` -- because a card that
    turns a single-target attack into an area says in the same sentence that
    each creature in the area is a target.

    **Read in `_auto_targets` and nowhere else, deliberately.** The other
    three readers of the printed line are `candidates` and `actions`, which
    offer and draw, and `Power.target_of`'s own caller inside `Power`. The
    widened line is strictly more permissive -- a bigger `count` and
    `everyone` -- so a site that keeps reading the print offers *fewer*
    targets than the card, never more, and `_stands_right` (the filter on an
    explicitly handed target) reads neither field. Pointing the offer path
    at this as well is a fair next step and is not needed by either row.
    #712.
    """
    printed = p.target_of(augment)
    for eff in world.effects.of(actor):
        if eff.retarget is None or eff.suspended:
            continue
        gate = eff.reshape_when
        if gate is not None and not gate(
            {"power": p.ref, "range_kind": p.reach_of(0, augment).kind}
        ):
            continue
        return eff.retarget
    return printed


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
    `within` an area burst may be placed at.

    **Two printed lines lengthen that `within`, and this docstring used to
    say none did.** `f1995` and `i2771x1` each state a range increase and
    then extend it to area powers in as many words, one with a worked
    example -- "an area burst 1 within 10 becomes an area burst 1 within
    12". They are a **third** kind, `"within"`, and not `"blast_size"`:
    laying their plus on the radius turns 9 squares into 49, which is a
    different and much stronger clause than print. Read through
    `within_of`, which is the one door all three placement readers use.
    #738.

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
    if kind == "within":
        return max(0, mods.total("within", ctx))
    return 0


def within_of(
    world: World, actor: int, r: Range, ctx: dict[str, Any] | None = None
) -> int:
    """How far from this creature an area line may be **placed**.

    `Range.within` plus whatever lengthens it. Three readers ask this
    question and before #738 all three read the field raw -- and one of
    them, `Cast.wall`, hand-rolled the `spread` as well. They have to agree
    or the longer range is offered and then refused one question later,
    which is the failure both waiting rows' notes describe from #533: a
    stretch that reached `area_of` and not the gate `actions.perform`
    re-asks was worth nothing.

    `aim_points` is the authority on whether a placement is legal -- it is
    what `actions.legal` offers from and what `use` refuses against -- so a
    stretch missing from it would light up a square the action then
    declined.
    """
    return max(0, r.within + _stretched(world, actor, "within", ctx))


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
    #
    # **Through `reach_of` and not `switched` alone**, which is the same
    # sentence one step further: `switched` applies a state-switched size and
    # `reach_of` is "the door for reshapes" in its own words, so asking
    # `switched` here saw a `c.reshape_area` that every other reader honoured.
    # Measured: a reshape turning a ranged line into an area burst gave
    # `reach_of` "Area burst 1 within 10" and `area_of` nine squares while
    # this returned **nothing at all** -- so `use` refused the placement one
    # question after the interface offered it, which is #533's failure and
    # #738's. #712.
    reach = reach_of(world, actor, p, 0, augment)
    if reach.kind == "close_blast":
        return sorted(blast_placements(mine, reach.size))
    if reach.kind in ("area_burst", "wall"):
        far = within_of(world, actor, reach,
                        {"power": p.ref, "range_kind": reach.kind})
        # **`reach_of` and `within_of` still run every time.** They are where
        # every state-dependent answer is -- a reshape, a switched size, a
        # modifier that lengthens the `within` -- and the comment above is
        # the history of getting that wrong. Only the square enumeration
        # below is remembered, and its key holds everything it reads:
        # `mine`, `far`, the board's bounds (`inside`) and the blocking set
        # (`line_of_effect`). Nothing else enters the comprehension.
        grid = world.grid
        mine_key = frozenset(mine)
        key = (mine_key, far, grid.width, grid.height, frozenset(grid.blocking))
        hit = grid.aims.get(key)
        if hit is None:
            hit = tuple(sorted(
                sq
                for sq in spread(mine, far)
                if grid.inside(sq)
                and any(grid.line_of_effect(src, sq) for src in mine)
            ))
            grid.aims[key] = hit
        # A fresh list, because callers get a mutable one today and
        # `actions.aimed` sorts and slices it. Handing out the cached tuple
        # would make one caller's edit the next caller's answer.
        return list(hit)
    return []


def basics_of(world: World, actor: int, window: str = "") -> tuple[str, ...]:
    """Every ref that **is** a basic attack for this creature.

    The designated melee row (`Powers.basic`, which a monster points at one
    of its own abilities) and the ranged one, plus every row this creature
    knows whose header declares `basic=`. `window="ranged"` asks the ranged
    half alone and `"melee"` the melee half; the default asks both, which is
    what a "with basic attacks" modifier wants.

    **`Powers.instead` is deliberately absent.** A row swung *in place of* a
    basic attack is not one, so it must not pick up a basic-attack modifier
    -- that is the distinction #522 is about, and conflating them is the bug
    an implementation falls into. `drivers.counts_as_basic` asserts the
    negative half, which is the one that matters: a check asserting only
    that the designation works passes on an implementation that conflated
    the two.

    Scanned off `Powers.all` rather than read out of a second store, because
    the declaration is header data -- and a row the creature does not hold
    is not its basic attack however the card reads.
    """
    from .components import Powers

    known = world.get(actor, Powers)
    if known is None:
        return ()
    out: list[str] = []
    if window != "ranged":
        out.append(known.basic)
    if window != "melee":
        out.append(known.ranged)
    want = {"ranged"} if window == "ranged" else (
        {"melee"} if window == "melee" else {"melee", "ranged"}
    )
    for ref in known.all:
        p = get(ref)
        if p is not None and p.basic in want:
            out.append(ref)
    return tuple(dict.fromkeys(r for r in out if r))


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
    # **A row that counts as a basic attack is offered here too.** "Counts
    # as" implies the offer -- if a row *is* a ranged basic attack then it is
    # usable wherever one is handed out -- and the eleven rows printing that
    # line were in no store at all, so none of the 259 printed sites granting
    # a swing could reach them. A warlock whose ally granted a ranged basic
    # attack could not use its own at-will. #522.
    #
    # `basics_of` returns the designated row as well, which `own` above
    # already covers; the dedupe at the end is what keeps it from appearing
    # twice.
    designated = basics_of(world, actor, "ranged" if window == "ranged" else "melee")
    # **And the rows that declare the substitution in their own header.**
    # `Powers.instead` holds what somebody else *granted*; this is the row
    # whose card says it about itself, which a body cannot file in time --
    # it runs when the row is used, and the menu is built first. Scanned off
    # `Powers.all` for the reason `basics_of` gives: a row the creature does
    # not hold is not its stand-in however the card reads. #677.
    # **The empty declaration must not match the empty window**, and the
    # first version of this let it: `c.basic` asks with `window=""`, so
    # `"" in (window, "*")` was true of every row the creature knows and the
    # first at-will among them was swung in place of the basic attack.
    # `drivers.lent_basic` caught it -- "returned True; declared []" -- which
    # is a rule written for a different fault in the same function.
    declared = [
        ref
        for ref in known.all
        if (row := get(ref)) is not None
        and row.instead_of_basic
        and row.instead_of_basic in (window, "*")
        and not (window == "ranged" and row.instead_of_basic == "*")
    ]
    for ref in dict.fromkeys(
        (*known.instead_of_basic(window), *declared, *designated)
    ):
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
        # **The caster is not its own ally**, which is the printed word and
        # is what `Cast._side` has always answered on the body path. This
        # line said `[*allies(world, actor), actor]`, so the two halves of
        # the engine disagreed about one word and the targeting half -- the
        # one a player sees -- was the wrong one. A row printing "each ally
        # in the burst shifts 1" moved the creature that is not a target,
        # and because the row fired and emitted events the audit called it
        # working. #364.
        #
        # A card that means you as well says "you and each ally", and that
        # is `"team"` below. 185 rows declare it now; before this flip they
        # could not, because `"team"` was absent from this dict and from
        # `Target.__str__`, so they were declared `ally` and were correct
        # only by the accident this line fixes.
        "ally": allies(world, actor),
        "any": creatures(world),
        "other": [c for c in creatures(world) if c != actor],
        # **`"other_ally"` is gone**, and its absence is the point. It
        # existed to say "the printed line excludes you" at a time when
        # `"ally"` did not; #364 made `"ally"` mean exactly that, so the two
        # were the same list and one of them was a trap -- a second spelling
        # of a settled question, which is what `vocab.py` warns near-synonyms
        # cost. 73 declarations retired into `ONE_ALLY`/`EACH_ALLY`, and
        # `_SIDES` no longer lists it so a row naming it raises at import
        # rather than quietly working.
        # **`"team"` was missing here entirely**, so a row declaring it
        # raised `KeyError` at targeting and no row in the tree used it --
        # which is why `_side`'s note that "a card meaning you as well says
        # you and each ally, and `team` is that pool" described something
        # unreachable. `Cast._side` has had it all along; this is the
        # targeting half catching up. #364.
        "team": [*allies(world, actor), actor],
        # Not a creature at all, and not in any of the pools above: scenery
        # has no `Side`, so every one of them is empty for it.
        # `loose=` is passed here as well as tested in `_stands_right`, and
        # that is not a duplicate: it decides *which scenery exists* for
        # this pool, where the predicate decides whether one handed in is
        # allowed. The second is the half that was missing.
        "object": scenery(world, "object", loose=aim.loose),
    }[aim.side]
    # **`holding` and `max_size` used to be filtered here and nowhere else**,
    # which made them the exact disagreement `_stands_right` exists to
    # prevent: 24 rows refused an oversized creature on the menu and struck
    # one handed in explicitly by another row's `c.command`. Moved into the
    # predicate and named in the guard list below. #658.
    if (
        aim.relation is not None
        or aim.grants_ca
        or aim.flanked
        or aim.conditions
        or aim.conditions_without
        or aim.can_act is not None
        or aim.kinds
        or aim.kinds_without
        or aim.living
        or aim.ongoing
        or aim.ongoing_types
        or aim.bloodied is not None
        # **A new `Target` field must be named here as well as tested in
        # `_stands_right`**, or the offer path skips it in silence. This
        # guard is a hand-kept list of "is any relational field set", so
        # adding one to the predicate alone leaves the explicit-target arm
        # honouring it and `candidates()` not -- which is #381's
        # disagreement arriving one field at a time. `ident` was written
        # that way and the driver caught it on its first run.
        or aim.ident
        or aim.kind_or_ident
        or aim.hit_by_me_this_turn
        or aim.missed_by_me_this_turn
        or aim.affected_by
        or aim.only_grabbed
        or aim.holding
        or aim.carrying
        or aim.max_size is not None
        or aim.loose
        or aim.any_of
        or aim.on_the_ground is not None
        or aim.sheltered_from
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
    return not any(
        can_branch_for(world, actor, p, b) for b in branches_for(world, actor, p)
    )


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
    if p.defect or entry_defect(p.ref):
        # **The compendium is missing what this row would be written from.**
        # Refused rather than offered half-written, for the reason above: a
        # wrong result is harder to see than a missing one. #360.
        #
        # **`entry_defect` as well as `p.defect`, which is Camille's rule of
        # 2026-10-15**: the entire entry is dropped if any part of it is
        # defective. It already worked that way for a stat block, through
        # `loader.defective`; an item whose Power was defective was still
        # dealt and still paid out its Property, so a player held a working
        # fraction of an object the compendium cannot describe. #600.
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
        # **"Can only make a melee basic attack."** Checked before the
        # `forbidden` list below because it is the same kind of answer and
        # the narrower one: a creature under this may reach exactly the rows
        # named, and only where the row is an attack at all.
        if (powers.only_attacks and p.attack is not None
                and p.ref not in powers.only_attacks):
            return False, "it can only attack with another power"
        if p.ref in powers.forbidden:
            return False, "cannot be used right now"
        # **Two keyword prohibitions, and they point opposite ways.** Read
        # through `keywords_of` rather than `p.keywords`, for #483's reason:
        # a feat can grant a keyword to one character's copy of a row, and a
        # refusal reading the header would ignore the grant.
        if powers.forbidden_keywords or powers.required_keywords:
            mine = keywords_of(world, actor, p)
            barred = mine & powers.forbidden_keywords
            if barred:
                return False, f"cannot use {sorted(barred)[0].value} powers"
            # "You can't use weapon or implement attack powers that lack the
            # beast form keyword, **although you can sustain such powers.**"
            # The exception is the half most easily dropped, and dropping it
            # cancels every zone and stance the character had running when it
            # changed shape -- so a row already standing is exempt.
            if powers.required_keywords and p.ref not in powers.sustainable:
                missing = powers.required_keywords - mine
                if missing:
                    return False, (
                        f"needs the {sorted(missing)[0].value} keyword"
                    )
        # **A whole usage category, which `forbidden` could not say.** Two
        # monster cards print "cannot use encounter powers" and one narrows
        # it to attack powers, so the narrowing is its own set: an attack
        # power is one whose header declares an `Attack`, which is the same
        # question `blocked.py` and the audit ask of a row.
        if powers.forbidden_usages or powers.forbidden_attack_usages:
            if p.usage in powers.forbidden_usages:
                return False, f"cannot use {p.usage.value} powers"
            if (p.usage in powers.forbidden_attack_usages
                    and p.attack is not None):
                return False, f"cannot use {p.usage.value} attack powers"
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
    open_branches = [
        b for b in branches_for(world, actor, p)
        if can_branch_for(world, actor, p, b)
    ]
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

        far = (switched(world, actor, p.reach_of(branch, augment)).size
               + speed(world, actor, {"charge": True}))
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
    if aim.affected_by and not any(
        getattr(eff, "by", "") == aim.affected_by and not eff.suspended
        for eff in world.effects.of(target)
    ):
        # **A suspended effect does not count.** `#470` made suspension a
        # real state, and a creature whose snare is suspended is not held by
        # it -- the sickle row would otherwise finish something that is free.
        return False
    if aim.any_of and not any(
        _stands_right(world, actor, alt, target, ref) for alt in aim.any_of
    ):
        # **The disjunction is asked first and the rest of this predicate is
        # still asked after it**, because that is what the cards print: "one
        # Medium or smaller creature that is bloodied or prone" is one
        # restriction compounding with a choice of two. An alternative that
        # also fails its own clauses is simply not one of the ways in.
        return False
    if aim.max_size is not None and _size_of(world, target).order > aim.max_size.order:
        return False
    if aim.holding:
        from .query import holding

        if not holding(world, target, aim.holding):
            return False
    if aim.carrying:
        from .components import Gear

        kit = world.get(target, Gear)
        if kit is None or not (kit.weapons or kit.stowed or kit.shield):
            return False
    if aim.loose:
        from .components import Scenery

        thing = world.get(target, Scenery)
        # A creature is never fastened down and never in somebody's hands,
        # so the clause is about scenery and passes for anything else --
        # which is the pool's reading too: `loose=` only ever reaches
        # `scenery()`.
        if thing is not None and (thing.fastened or thing.by):
            return False
    if aim.sheltered_from:
        from .query import sheltered_from

        if not sheltered_from(world, actor, target):
            return False
    if aim.on_the_ground is not None:
        from .query import on_the_ground

        if on_the_ground(world, target) is not aim.on_the_ground:
            return False
    if aim.only_grabbed:
        # **Asked only when something is held.** An empty grip narrows
        # nothing, which is the field and not a shortcut: the three bites
        # that carry this are what establish the grab, so refusing them
        # here would refuse the row in its ordinary use.
        #
        # Outward from the caster, like the relational block below -- what
        # *it* is holding, never what is holding the target. A creature in
        # somebody else's grip is not this one's business.
        held = world.relations.targets(Relation.GRABBED_BY, actor)
        if held and target not in held:
            return False
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
        # `kinds_without` is an exclusion and compounds even under
        # `kind_or_ident`: "any ally of that sort, but never an undead
        # one" means
        # both, and no card prints an exclusion it also waives.
        if words & aim.kinds_without:
            return False
        # Under `kind_or_ident` the kind is one of two ways in, so failing it is
        # not a refusal -- `ident` below is asked instead.
        if (
            aim.kinds
            and not (words & aim.kinds)
            and not (aim.kind_or_ident and aim.ident)
        ):
            return False
    if aim.living:
        from .query import living

        if not living(world, target):
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
    if aim.hit_by_me_this_turn and target not in {
        # **`actor`, not the target.** "One creature **it** hit this turn"
        # is about who swung, and this predicate is handed both -- the one
        # place the distinction is free. Reading the target's own hits
        # would answer "a creature that hit something", which no card asks.
        hit.target for hit in my_hits_this_turn(world, actor)
    }:
        return False
    if aim.missed_by_me_this_turn and target not in {
        swing.target for swing in my_misses_this_turn(world, actor)
    }:
        return False
    if aim.ident:
        # Scenery and anything else with no `Ident` is not of any block, so
        # it fails rather than defaulting into the kind being asked for.
        from .components import Ident

        who = world.get(target, Ident)
        wanted = aim.ident
        if wanted == "own":
            # Resolved here because this is where the caster is known; a
            # header field cannot hold "whatever block I am".
            mine = world.get(actor, Ident)
            wanted = mine.ref if mine is not None else ""
        matched = who is not None and bool(wanted) and who.ref == wanted
        if not matched:
            if not aim.kind_or_ident or not aim.kinds:
                return False
            # **The union, and it is asked here rather than above because
            # this is the second of the two ways in.** The kind test let
            # the creature through to this point without deciding, so a
            # miss on both is the only refusal.
            from .query import kinds_of

            if not (kinds_of(world, target) & aim.kinds):
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
    r = switched(world, actor, p.reach_of(branch, augment))
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
    # Through the per-creature readers: a feat offering a longer aiming makes
    # the row reach further for *that* creature, and a distance guard reading
    # the print alone refuses a shot the card allows.
    furthest = max(
        reach_of(world, actor, p, b).size for b in branches_for(world, actor, p)
    )
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

    if provokes_for(world, actor, p, branch, augment) and not _survive_provoking(
        world, actor, ref
    ):
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
            del cast.swings[:]
            p.body(cast)
            # **Every swing the body made, not the last one it happened to
            # leave behind.** `cast.result` is written by `Cast.attack`, the
            # single funnel every attack roll goes through, so a body with
            # two roll sites overwrote the first and this sampled one entry
            # for two swings.
            #
            # `rolls` then said one result per *target*, where
            # `PowerResolved.rolls` is documented as every `AttackResult`
            # the use produced -- which is what "reroll every attack roll
            # you made with this power" has to be handed. Measured on a
            # two-swing power: two `AttackRolled` on the bus, one entry
            # here.
            #
            # And `landed` came off the same field, which is the part that
            # reached a player: a RELIABLE power is refunded below when
            # nothing landed, so a daily whose primary **hit** and whose
            # off-hand missed was handed back, because the miss was what
            # `result` ended as. Reproduced in all four cells; the one that
            # passed was "primary misses, off-hand hits", because there the
            # hit is last and survives. #810.
            made = list(cast.swings)
            if not made and cast.result is not None:
                # `c.use_power` sets `result` off the inner use's
                # `PowerResolved` without going through `Cast.attack`, so
                # it leaves no swing here. Kept as the fallback rather than
                # also appending there: those rolls belong to the inner
                # use's own announcement, and folding them into this one
                # would be a second change wearing this one's clothes.
                made = [cast.result]
            rolls.extend(made)
            landed = landed or any(r.hit for r in made)
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
    want = target_of(world, actor, p, augment)
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
