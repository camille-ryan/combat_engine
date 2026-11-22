"""The components a creature, a zone or a conjuration is made of.

No display names anywhere. `Ident.ref` is a compendium id like `m145` or
`p289`, and `Ident.tag` distinguishes the second goblin from the first. A
player sees a name because the API looks one up at the boundary; the engine
never holds one.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
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
    Usage,
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
class Senses:
    """Where a creature's senses are taken from, when not its own square.

    **`query.can_hear`'s docstring recorded that this did not exist** --
    *"There is no `Senses` component; what there is: `Condition.DEAFENED`
    ... and `query.sealed`"* -- and composed itself out of the pieces. It
    was right to, and two wild-talent cantrips print something that cannot
    be composed that way: *"Choose one square you can see that is within 5
    squares of you. Until the end of your next turn, you can determine your
    line of sight from that square."*

    `c.cast_from` is the near miss and it is two things away, which is what
    `p12407` carried its marker for. `Relation.CASTS_FROM` holds an
    **entity** and `dsl.measured_from` answers one, so there is nowhere to
    put a square -- and the card names a square it can see, not a creature
    standing in one. Second, `measured_from` has exactly one caller and only
    for `ranged`, `area_burst` and `wall` ranges, so it moves where an
    attack is *measured* from rather than what the creature can **see**.

    **Named fields and not a dict keyed by a sense.** A string key invites a
    misspelling that reads as "no lent square" rather than raising, which is
    the all-False gate that hides vocabulary drift. Two senses are two
    fields, and a third gets a third.

    `None` is the ordinary case and means "its own square", so every reader
    falls back without asking whether the component is there. #1283.
    """

    #: The square this creature's line of **sight** is traced from.
    #: `query.sight_squares` is the only reader and `c.can_see` the only
    #: caller, so the lent origin and the sight answer cannot disagree.
    sight_from: Square | None = None
    #: The **creature** whose space this one's sight is traced from, for a
    #: card that lends a body rather than a square: *"you can see and hear
    #: as if you were in the target's space"* -- `p12345`.
    #:
    #: A second field rather than storing that creature's square in
    #: `sight_from`, because the two sentences differ in what happens
    #: **next**: a lent square stays where it was put, and a lent body
    #: takes its eye with it when it walks. Freezing the square at the
    #: moment of the cast would have been right for one turn and wrong for
    #: the rest of a save-ends duration.
    #:
    #: Read by `query.sight_squares` ahead of `sight_from`, which is the
    #: order the two cards imply: nothing prints both, and a body is the
    #: more specific of the two.
    sight_from_who: int = 0
    #: Extra vantage points, **as well as** the creature's own squares.
    #:
    #: `sight_from` replaces: *"you can determine your line of sight from
    #: that square"* (`p12407`) moves the eye. `p14142` prints *"you can
    #: see from **both** your location and that spot"*, which is a second
    #: vantage rather than a different one -- so one field could not carry
    #: both readings without one of the two rows being wrong.
    #:
    #: A set because the printed line allows one spot and nothing says a
    #: creature may not be lent two; `query.sight_squares` unions it in.
    sight_also: frozenset[tuple[int, int]] = frozenset()


@dataclass
class Side:
    team: Team


# --------------------------------------------------------------------------
# Numbers
# --------------------------------------------------------------------------


@dataclass
class Skills:
    """Which skills this creature is **trained** in.

    `engine/skills.py` asked for exactly this, by name: *"a `Skills`
    component seeding it from the chassis is the one thing this file is
    short of"*. Until it existed there was no training model at all --
    nothing decided who was trained, so the +5 was never applied and the
    50 content files that lay a `skill:` modifier were adding to a check
    nobody had the base training for.

    **A set of lowercase skill names**, matching the keys of
    `skills.SKILLS` and the `skill:<name>` modifier key the tree already
    writes. Empty means "nobody recorded any", which is what every monster
    is: a stat block prints its skill totals outright rather than its
    training, so a monster's numbers come from `Mods` and this stays
    empty. Only `chargen` fills it.
    """

    trained: frozenset[str] = frozenset()


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
    #: **Whose pool this creature may draw on once its own is empty**, or 0.
    #:
    #: One card prints it -- *"you can spend the target's healing surges as
    #: if they were your own, if the target allows it"* -- and `p15888`'s own
    #: note measured why no verb could: `resolve.spend_surge` decrements the
    #: actor's own `surges` and names no alternative, and `c.surge`,
    #: `c.spend_surge`, `c.regain_surge` and `c.second_wind` are all about
    #: the creature in `on=`.
    #:
    #: **Here rather than on the borrower's row**, because this is the field
    #: the spend already reads. The emulation that field avoids is two
    #: bookkeeping moves standing in for one -- spend the ally's, refund the
    #: caster's -- which `p15888` rejected for three reasons that still hold:
    #: it announces two surges where one was spent, it reports both pools
    #: wrongly in between, and `c.regain_surge` has no ceiling so the refund
    #: could hand a caster more than an extended rest ever gave.
    #:
    #: **Own pool first, and only then the lender's.** *"As if they were your
    #: own"* is a pool extension rather than a substitution, so a caster with
    #: surges of his own spends those -- which also keeps every existing
    #: spend untouched, since the field is 0 on everybody who was not lent to.
    #:
    #: Written by `c.surge_from`, read in `resolve.spend_surge`, which
    #: announces whose pool paid on `SurgeSpent.pool`.
    surges_from: int = 0
    #: **A monster dies at 0.** Only a character keeps fighting into the
    #: negatives and only a character rolls death saves. Without this
    #: every monster inherited the player's floor and was still alive at
    #: minus half its printed hit points -- a 38-hit-point brute had to be
    #: taken to -19, which is half again the hit points on its card, on
    #: every monster in the game. Set by `loader.spawn`.
    dies_at_zero: bool = False
    #: **How many failed death saves kill this creature.** Three is the
    #: printed rule and the default.
    #:
    #: One card moves it -- *"until the end of the encounter, you die after
    #: failing your second, rather than third, death saving throw"* -- and
    #: `p4288` carried the marker for it. Its note had the shape right:
    #: `dies_at_zero` sits one line up, so a per-creature death rule is
    #: something this component already does.
    #:
    #: **That note said the literal `3` was read in one place and it is read
    #: in three**, which is the reason this is a field rather than three
    #: edits. `turns._death_save` is the one that kills; `Cast.death_save`
    #: caps the counter so a creature already dead takes no fourth failure;
    #: and `items/implement_d.py` reads it as **its own card's** limit,
    #: which is deliberately left at a literal -- that number is printed on
    #: the item, not derived from the death rule, and moving with this field
    #: would silently retune the card.
    #:
    #: A threshold honoured by the killer and not by the cap is the shape
    #: `engine/CLAUDE.md` calls this component's commonest bug, so both
    #: engine readers take it from here. Written by `c.dies_at_failures`.
    dies_at_failures: int = 3

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
class Leash:
    """How far this creature may get from something, and from what.

    "Cannot move more than 3 squares from the space it occupies", "cannot
    move more than 2 squares from a held creature", "cannot willingly end
    its turn farther away than where it started" -- fourteen rows print a
    **tether**, and the three verbs that look close are all wrong for it:
    `c.immobilized` and `c.no_walk` stop the creature dead, and nothing else
    measured distance from a remembered point.

    `to` names a creature and `square` a fixed point; exactly one is set.
    A creature anchor moves with it, which is what "from a held creature"
    needs -- a trap that drags its victim along keeps the leash taut rather
    than snapping it.

    Read in `movement.reachable`, so a square beyond the tether is never
    offered: the UI cannot draw it and `policy/` cannot score it. Punishing
    the move afterwards was the alternative and is worse -- the printed
    lines are restrictions, not penalties. #512.
    """

    radius: int = 0
    to: int | None = None
    square: tuple[int, int] | None = None
    #: **Several anchors, any one of which satisfies the tether.**
    #: `p13318`'s primary target *"may not leave the side of one or more"*
    #: of the secondary ones, so the anchor is a **set** and being near any
    #: of them is enough. `to` is the single-anchor spelling and stays --
    #: fourteen rows print one anchor and none of them should grow a set --
    #: so `query.leash_of` resolves whichever is given.
    #:
    #: Leashing to whichever secondary happened to be hit first would be a
    #: tighter cage than the card prints, which is what this row's marker
    #: said and why it was right to wait. #1297.
    anchors: frozenset[int] = frozenset()
    #: **The same restriction pointed the other way**: a creature this
    #: creature may not get *closer* to. "The target cannot move closer to
    #: the X (save ends)" is printed on seven rows and none of them could be
    #: written -- `c.immovable` is about being shoved and `c.cannot_shift`
    #: about shifting, and neither bars walking in one direction.
    #:
    #: Kept here rather than in a component of its own because it is the same
    #: question `radius` asks, with the comparison reversed, and
    #: `movement.reachable` is already the one place that asks it. A creature
    #: can carry both: tethered to a point and kept away from a creature.
    #:
    #: **No number beside it, on purpose.** The floor is the distance the
    #: creature is at when it moves, measured then -- the printed clause
    #: forbids *reducing* the distance. Freezing a number when the effect
    #: landed would leave the creature unable to move at all the moment the
    #: anchor walked towards it. #728.
    away_from: int | None = None


@dataclass
class Movement:
    speed: int = 6
    #: **True while this creature is in the middle of a charge.** A charge is
    #: a walk and then a swing, and three rows ask about the creature *doing*
    #: it rather than about the attack: "while charging, it gains +4 to all
    #: defences", "a bonus to Athletics checks made to jump as part of that
    #: charge", "+1 to speed when charging while in beast form".
    #:
    #: The attack context's `charge` is a different fact and is already
    #: there: it says *this attack is a charge's attack*, which an **attacker**
    #: reads. It cannot answer a defence bonus on the charger, because the
    #: attack that benefits is somebody else's opportunity swing on the way
    #: in -- and that is exactly the attack "while charging" is printed to
    #: survive.
    #:
    #: Set and cleared around the whole action in `actions.execute` and
    #: `Cast.charge_at`, which are the two doors a charge comes through, and
    #: cleared in a `finally` so a raise cannot leave a creature permanently
    #: charging. Read by `query.charging`. #732.
    charging: bool = False
    #: Extra modes and their speeds, e.g. {"fly": 8, "climb": 3}.
    modes: dict[str, int] = field(default_factory=dict)
    #: The round this creature last made an Athletics check to swim, and what
    #: it bought. Camille's ruling is that the check *"determines swim speed
    #: for the round"*, so the answer is remembered rather than re-rolled:
    #: `query.speed` is asked many times while a menu is drawn, and a fresh
    #: d20 per call would give a creature one speed in the menu and another
    #: when it moved. `movement.swims` owns both. Only a creature **without**
    #: a swim speed ever sets them -- the page exempts the rest. #949.
    swim_round: int = -1
    swim_squares: int = 0
    #: The same pair for climbing, and for the same reason -- PHB p183 gives
    #: the two skills the same shape on the same page, and Camille's "the
    #: check determines the speed for the round" applies word for word.
    #: `movement.climbs` owns both. Only a creature **without** a climb speed
    #: ever sets them: *"creatures that have a climb speed ... do not make
    #: Athletics checks to climb"*. #1300.
    climb_round: int = -1
    climb_squares: int = 0
    #: Kinds of difficult terrain this creature crosses for nothing, by the
    #: label `Grid.difficult` gives them. `"*"` is all of it.
    ignores: set[str] = field(default_factory=set)
    #: The ref of a trait letting this creature's **charge** pass straight
    #: through one body, trampling it. `""` for the overwhelming majority.
    #: #1057.
    #:
    #: **The ref rather than a bool**, for two reasons. The payout has to be
    #: attributable -- `Trampled.by` names it, so the event says which card
    #: allowed the move -- and the row is what makes the stamp attack, so
    #: something has to know which row to run.
    #:
    #: Why a field and not `ignores`: that set is strictly about difficult
    #: **terrain**, by the label `Grid.difficult` gives it. A body is not
    #: terrain, and overloading the set would make
    #: `c.ignores_difficult("*")` grant a trample.
    tramples: str = ''
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
    #: **How many squares of rough going are free per move**, where
    #: `ignores` above is all of it or none.
    #:
    #: *"You ignore 1 square of difficult terrain when you move"* --
    #: `f1873`, `f2622`. A **budget on a path** and not a property of a
    #: square, which is why it could not live in `World.crossing`'s
    #: closure: that prices one step at a time and is shared by `step`,
    #: `reachable` and `costs`, so a counter inside it would be spent by
    #: routes a search merely considered.
    #:
    #: `0` for every creature nothing has given one, and the three
    #: readers all take their fast path on that -- `movement.reachable`
    #: layers its search only when this is positive.
    free_difficult: int = 0
    #: How many of `free_difficult` are left in the move being walked
    #: right now. Reset by `movement.start_move`, spent by `step`.
    #:
    #: Separate from the allowance for the reason a `Powers.used` count
    #: is separate from `Power.uses`: one is what the card grants and the
    #: other is what is left, and a search must be able to ask the first
    #: without disturbing the second.
    free_difficult_left: int = 0
    #: The same exemption asked the other way: not what the going **is** but
    #: what **made** it. "Ignores difficult terrain that is `m2824`", "ignores
    #: difficult terrain related to spider swarms" -- five rows, and the only
    #: rough ground with a maker is a creature whose own square costs to
    #: enter (`c.shares_space(difficult=True)`).
    #:
    #: Holds a **stat-block ref** or a **printed type word**, because the
    #: cards print both: its own kind by name, or anybody's of a sort.
    #: `World._made_rough_by_something_waived` is the one reader.
    #:
    #: A set beside `ignores` rather than entries inside it, because the two
    #: are different questions and a square can be rough for both reasons at
    #: once -- a forest square with a swarm standing in it is still forest.
    #: #659.
    ignores_made_by: frozenset[str] = frozenset()
    #: Rough going is free in squares that are **unlit** -- dim light or
    #: darkness. `f3573` prints exactly that and nothing else.
    #:
    #: A square predicate, which is a fourth kind of waiver beside the
    #: three above: `ignores` is by label, `ignores_when` by move kind,
    #: `ignores_made_by` by provenance, and none of them can ask anything
    #: about *where* the square is. Written ungated the feat would be free
    #: movement over every sort of rough going anywhere, which is a much
    #: bigger card.
    ignores_unlit: bool = False
    #: Rough going is free, but only in squares **near a named creature** --
    #: `(anchor, squares)` pairs. `f1887` prints *"you and your allies
    #: ignore difficult terrain while adjacent to your spirit
    #: companion"*, so the waiver follows a creature about.
    #:
    #: The **fifth** kind of waiver and the second square predicate, after
    #: `ignores_unlit`. It belongs with that one rather than with the three
    #: by-label kinds, for the reason that field's note gives: it asks
    #: something about *where* the square is.
    #:
    #: A list because a creature can have two, and the anchor is an entity
    #: id rather than a position: the spirit moves, and the waiver has to
    #: move with it. A dead or absent anchor simply matches nothing, which
    #: is the printed answer -- no spirit, no sure footing.
    ignores_near: tuple[tuple[int, int], ...] = ()
    #: **The whole board costs this creature double**, which is what "treats
    #: all squares as difficult terrain" prints.
    #:
    #: **The first additive entry here, and that was the gap.** The three
    #: fields above are all waivers, and the filter in `World.difficult`
    #: only ever *removes* squares, so rough ground could be made easier for
    #: one creature and never harder. Three heroic rows print the other
    #: direction and none could be written.
    #:
    #: A flag and not a square set. The two other rows in that family name
    #: an **area** -- "squares in the aura", "all squares adjacent to you" --
    #: and an area that is described relative to a creature follows it, so
    #: those belong on `Zone.difficult_for`, where `Zones.refresh` already
    #: re-centres the squares every round. A snapshot taken here would have
    #: been the lesser reading of both cards; this field is for the one case
    #: with no geometry to follow.
    #:
    #: Materialised in `World.difficult` rather than written out as squares,
    #: so a board where nothing imposed it pays nothing -- that function is
    #: called once per square examined during a move search. Written by
    #: `c.difficult_for`. #831.
    harder_everywhere: bool = False
    #: **Extra squares this creature pays to move *closer* to somebody** --
    #: the anchor's entity id, against the number of extra squares.
    #:
    #: **The one shape `harder_everywhere` above cannot hold, and the
    #: difference is a direction.** Two rows print *"each square moved toward
    #: you costs 1 extra"* and *"each square closer costs an extra square"*,
    #: and both docstrings recorded the same correct diagnosis: the amount was
    #: exact (one extra square is what difficult terrain costs) and the verb
    #: was there, but `World.difficult` answered with a **set of squares**, so
    #: a step was never asked where it came from. Laying the flat version
    #: charged the creature for backing away, which is strictly stronger than
    #: print on a clause whose whole point is to slow an approach -- so both
    #: rows named the gap and left it.
    #:
    #: `World.crossing` answers with a function of `(from, to)` since the
    #: movement tax landed, so the direction is in hand and this is readable.
    #:
    #: **Keyed by anchor rather than a single pair**, because two rows may
    #: each slow an approach to a different creature and a creature walking
    #: between them pays both. Measured against the nearer square of a
    #: multi-square anchor, which is how every other distance here is taken.
    #:
    #: Written by `c.movement_tax`, read in `World.crossing`.
    harder_toward: dict[int, int] = field(default_factory=dict)
    #: What this creature crosses **without taking its damage**, by the same
    #: tokens `ignores` uses: a `DIFFICULT_LABELS` word, or `"*"` for the
    #: blanket form.
    #:
    #: **The twin of `ignores` and a different question.** That one waives
    #: the *cost* of rough ground; this waives the *damage* a hazard laid
    #: over it deals. Four monster rows print both halves in one sentence --
    #: "ignore difficult terrain, and take no damage if the surface it moves
    #: across would normally deal damage to it" -- and only the first half
    #: was sayable, so each of them laid the exemption it could and dropped
    #: the one it could not.
    #:
    #: A **set of tokens rather than a bool**, for `ignores`' reason: two
    #: rows granting it must not step on each other's expiry, and an effect
    #: discards exactly the token it added. Read by `Cast.burns`, which is
    #: where every hazard's teeth are.
    unharmed: set[str] = field(default_factory=set)
    #: How the creature is moving **right now**, or "" between moves.
    #:
    #: `modes` says what it *can* do and never what it *is* doing, so
    #: "Requirement: must be climbing" and "while it is not flying" could not
    #: be written at all -- a gate on `modes` is true whenever the creature
    #: has the speed, which is not the printed sentence. Four rows across two
    #: waves asked for this.
    using: str = ""
    #: How many squares this creature entered during its **current move
    #: action**, and which kind of going that action was.
    #:
    #: The printed Stealth rule is *"a Stealth check at the end of a move
    #: action; -5 if you moved more than 2 squares during it, -10 if you
    #: ran"*, and nothing counted the distance -- so the penalty had no
    #: number to be and four rows that only ever *waive* it had nothing to
    #: waive. #784.
    #:
    #: **Squares entered, not budget spent.** `movement.walk` already
    #: returns a cost, which is 2 for a difficult square -- so a creature
    #: crossing two squares of rough ground has spent 4 and moved 2, and the
    #: card says squares. Counted off the steps that actually landed.
    #:
    #: Reset at the top of each move action rather than per turn, because
    #: "during that action" is what the rule says: a creature that walks six
    #: squares, then takes a second move action for one, is 1 away from
    #: where it checks. `Budget.refresh` clears it too, so a turn with no
    #: movement reads 0 rather than last turn's number.
    #:
    #: Read by `query.moved_this_action` and `query.ran_this_action`. Two
    #: consumers: the hide **action**, which is the only hide that is a
    #: Stealth check -- a card reading "it becomes hidden" is not one, and
    #: there are 85 of those -- and `query.has_running_start`, for which 2
    #: squares is the printed run-up.
    went: int = 0
    went_kind: str = ""
    #: Where this creature's current move action **started**, for the one
    #: printed clause that asks about displacement rather than distance.
    #:
    #: *"If you end your movement at least 3 squares away from your
    #: starting position"* -- `cf:rogue-scoundrel-f1s2`. `went` beside this
    #: counts **squares entered**, which is the other question and the one
    #: the Stealth penalty asks: a creature that walks a circle enters four
    #: squares and ends where it began. Neither answers for the other, so
    #: both are kept.
    #:
    #: Same lifecycle as `went`, written at the same two places: set when
    #: `movement.walk` begins a move action, cleared with the action
    #: economy at the top of a turn so a creature that does not move is not
    #: carrying last turn's origin. `query.displaced_this_action` is the
    #: reader. #1250.
    went_from: Square | None = None
    #: Who is granting this creature a **running start** it has not run up
    #: for, by ref. Truthy means it has one however little it moved.
    #:
    #: *"If you move at least 2 squares before making the jump, divide your
    #: check result by 5, not 10"* (PHB 183, Athletics/Jump) is the rule,
    #: and `query.has_running_start` is where the two halves meet: this set
    #: or `went >= RUN_UP`. Read nowhere else -- a jump's **distance** is
    #: the calling row's arithmetic, because `c.jump` takes squares and the
    #: divisor is what the card prints.
    #:
    #: **A set of refs rather than a bool**, for `ignores_difficult`'s
    #: reason: two rows can grant it at once, and a bool cannot be given
    #: back by one effect ending without lying about the other.
    run_up: set[str] = field(default_factory=set)

    #: **Mid-air over a square this creature will not stop on.** True only
    #: while a flier is stepping *through* a square during one move, and
    #: False on the square it lands on.
    #:
    #: Camille's rule, 2026-11-19, on being shown that a flier in this
    #: engine was a walker with a different label:
    #:
    #: > *"fliers should ignore terrain and hazards except on the squares
    #: > they start and end from"*
    #:
    #: The start square needs no entry here: a cost and a hazard are both
    #: paid on *entering* a square, and a creature is already in the one it
    #: starts from. So this says "passing over", and it has two readers --
    #: `movement.walk`, which charges a flat 1 instead of the rough-ground
    #: price, and `Zones.create`'s hindering watch, which deals no damage.
    #:
    #: **Not three readers, and not the opportunity window.** The hop's
    #: provocation half cannot be carried by a flag of this shape: this
    #: engine provokes on *escaping a watcher's reach* rather than per
    #: square left, so the step a flag like this would allow is never the
    #: step the window opens on, and using it there waived every flier's
    #: window instead of all but one. `movement._hop_provokes` holds that
    #: reasoning and the measurement; it tests `went_from` and needs no
    #: state of its own.
    #:
    #: Set and cleared by `walk` around each step, so it is false whenever
    #: nobody is moving -- a flag that outlived its move would make a
    #: flier standing in a hazard immune to it, which is the half of the
    #: rule that keeps the other half honest.
    passing: bool = False


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
    #: Keywords the creature cannot be affected by at all -- "Immune fear",
    #: "Immune charm", "Immune sleep". **Not damage**, which is what
    #: `immune` above is: this is the printed immunity to a whole class of
    #: effect, and `query.immune_to` answers it beside the condition form.
    #:
    #: The data was there and was being thrown away. `monster.immune` holds
    #: these tokens for the creatures that print them, and
    #: `loader._stat_block` filtered the column to `DamageType` members
    #: only -- so **disease on 488 monsters, fear on 61, gaze on 36, sleep
    #: on 31 and charm on 27** were read out of the database and dropped on
    #: the floor. Two feats were marked `dropped=` for want of the reader
    #: while the facts were already in `game.db`. #560.
    immune_keywords: set[Keyword] = field(default_factory=set)
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
    #: Gates on the creature's insubstantial trait -- "while you have total
    #: concealment **from a creature**, you are insubstantial to that
    #: creature's attacks". Each is asked the damage context, which has
    #: carried `source` since #302, so "from that attacker" is sayable.
    #:
    #: A **list**, for the reason `half_except` above is a counted dict: two
    #: effects can lay the trait and the first to expire must not take the
    #: other's narrowing with it. Lifted on `on_suspend` the same way.
    #:
    #: `query.takes_half` answers True when **any** source applies: an
    #: ungated one always, a gated one when its gate accepts the blow. So
    #: `half_always` below is counted rather than the gate list being read
    #: as "unconditional when empty" -- the first draft did that and got the
    #: common case backwards, because a creature carrying a gated trait had
    #: a non-empty list and an ungated trait laid beside it left no mark at
    #: all, so the gate suppressed it. The driver's ungated control is what
    #: caught it. #747.
    half_when: list[Callable[[dict[str, Any]], bool]] = field(
        default_factory=list
    )
    #: How many **ungated** insubstantial sources this creature has, counted
    #: for the reason `half_except` is a counted dict: two effects can lay
    #: the trait and the first to expire must not take the other's with it.
    half_always: int = 0


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
    #: **Delayed or disabled, which the page treats as one state.** DMG p84:
    #: *"While it's delayed or disabled, the trap effectively isn't
    #: there."* So these three fields say *whether it is there*, and nothing
    #: reads which of the two reasons applies -- `engine/traps.py` owns them
    #: and `traps.suppressed` is the only reader.
    #:
    #: `disabled` has no expiry because the page gives it none. `delayed_until`
    #: is the round through which a delay certainly holds; after it, the
    #: printed 50% a round decides, and `delay_check` remembers which round
    #: that was last rolled in so the answer is stable inside a round.
    #: A trap absent for the menu and present for the step would be worse
    #: than either. #955.
    disabled: bool = False
    delayed_until: int | None = None
    delay_check: int = -1
    #: The printed `Perception DC` to notice it before it fires, or `None`
    #: for a trap whose block prints none -- 275 of the 631 do, and the
    #: honest reading of that is **cannot be noticed in advance** rather
    #: than a guessed number. Never derived: across the 356 that print one
    #: the DC is not a function of level, so a formula would be wrong by
    #: ten either way on the number that decides what a player is shown.
    perception_dc: int | None = None
    #: Somebody has found it by **looking**, as against noticing it in
    #: passing. One bit for the whole party, not one per character: a trap
    #: is found by the party, which is the position `render._noticed`
    #: already takes for the passive half ("one of them noticing is the
    #: party noticing").
    #:
    #: The stored bit the passive half deliberately does without. Passive
    #: Perception is recomputed on every render, so it needs no state and
    #: can never drift; a **roll** has to be remembered or the next render
    #: forgets it, and a party whose best passive is under the DC would
    #: have no way to find the trap at all. #959.
    #:
    #: It does not override `perception_dc is None`. A block printing no DC
    #: cannot be found in advance by either route -- otherwise the active
    #: check would quietly undo the more careful of the two readings above.
    found: bool = False

    #: **What it hits for, so somebody other than the trap can price it.**
    #: `arm` read this column into a local and captured it in the `strike`
    #: closure, which meant the expression was correct, live, and
    #: **unreachable** -- `policy/` could not ask how much a trap hurts, so
    #: `#981`'s hazard term had no number to derive a price from and a
    #: creature stepped into a trap for free.
    #:
    #: A **string**, as printed and as the column holds it: `"5"` as readily
    #: as `"1d10+3"`. The reader has to cope with both -- `Rng.roll` takes
    #: `str | int` and raises on a digit-only `str`, which is two thirds of
    #: the printed region population one table over, so the same care
    #: applies here.
    #:
    #: Empty for a trap `arm` had no row for, where the invented fallback
    #: stands in. Empty rather than that fallback's text, deliberately: a
    #: term pricing off this should be able to tell a printed number from a
    #: guessed one, and a non-empty string that was never printed is the
    #: kind of thing this repo keeps paying for. #981.
    damage: str = ""

    #: The skill the printed countermeasure names, and what it has to beat.
    #: `trap.disable_skill` / `disable_dc` in `game.db` (#989): **130** rows
    #: print one clause, **477** genuinely print none, and **24** are
    #: ambiguous and left NULL on purpose rather than guessed.
    #:
    #: Here for `perception_dc`'s reason and read the same way -- a trap
    #: that prints no way to disarm it cannot be disarmed, so an empty skill
    #: is a refusal rather than a default. Nothing invents a DC: a block
    #: naming a skill without a number is as unusable as one naming
    #: neither, which is why both have to be present for the action to be
    #: offered. #955.
    disable_skill: str = ""
    disable_dc: int | None = None
    #: The printed attack bonus and which defence it is rolled against --
    #: `"ref"`, `"fort"`, `"will"`, `"ac"` -- stored the way `damage` above
    #: already is.
    #:
    #: **They were locals in `content/terrain.py`'s `arm`**, closed over by
    #: a `strike` function nothing outside could reach. So a trap could only
    #: ever fire the two ways that closure was wired for -- a plate stepped
    #: on, and an ongoing trap's own turn -- and *"you trigger the trap"*
    #: (PHB p189, failing a Thievery check by 5 or more) had nowhere to go,
    #: which is what left `p11600` refused in play.
    #:
    #: Here so `traps.fire` can do it from the engine, which is where a rule
    #: belongs: the numbers are printed data and the firing is a rule, and
    #: `traps.py` already owns the suppression state beside it.
    #:
    #: `attack` is stored **as printed**, so `world.scaling` takes the level
    #: back out of it exactly as it does for a monster. `0` and `""` mean
    #: the row printed neither and the caller falls back -- `arm` keeps that
    #: fallback, because an invented number must not reach `policy/` as
    #: though the book had printed it (#981).
    attack: int = 0
    defence: str = ""


@dataclass
class Scenery:
    """Something standing on the map that no power put there.

    A crate, a statue, a campfire. It has a `Position`, so it has a square,
    a size and a footprint, and everything that measures to a thing --
    adjacency, a burst, line of effect -- measures to it for free.

    **It has no `Side`, ever**, and that is what keeps it out of
    `query.creatures` and out of `Encounter.winner`'s reckoning: no vote on
    whether the fight is over, so a crate left standing cannot stop a fight
    ending.

    **`Health` is optional and the two cases differ.** Without it, nothing
    can attack the thing -- a statue nobody can break, which is the common
    case. **With it**, the thing can be aimed at and destroyed, which is
    what the "destroy the object" objective wants, and then
    `query.combatants` has to subtract it: that is the **fourth
    subtraction**, after a companion, a barrier and a conjuration, and
    `#988` is what it was added for. This docstring said *"it has no
    `Health` ... and nothing can attack it"* as an invariant for as long as
    nothing constructed a `Scenery` at all, so the invariant was never
    tested. `content.terrain.put` is the writer, and `hp` is the opt-in.

    **`weight` is in pounds and `0` means not recorded.** Two rows need it:
    *"an object that weighs 400 pounds or less"* and *"one object you can
    lift"*. The thresholds are both printed -- the first on its own card,
    the second as PHB p223's Strength x 20 -- and `query.lift_limit` reads
    that. What is **not** printed is what a crate weighs: the same page
    says *"you don't need to calculate the weight ... unless it's likely to
    matter"*, so an object's weight is a DM call in print and a design
    decision here. So it lands empty, the same bargain `Grid.porous`,
    `Grid.light` and `Grid.climb_dc` strike: the reader lands with the
    model and costs nothing until a scene fills it. `0` is *unknown*
    rather than weightless, which is why no row may read it as liftable.

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
    #: **What the thing IS, beside the noun it is called.** A module names
    #: its thing with the printed word from its own scene -- "crate",
    #: "brazier", "idol" -- and every row's target line asks for the word
    #: `"object"`, so `query.scenery`'s exact match meant **no fielded
    #: objective thing could ever be the target of a row printing "or
    #: object"**. Measured: a `terrain.put(kind="object")` and a
    #: `field_thing(Objective(thing="crate"))` one square apart, identical
    #: in weight and distance, and `p11358` and `p11273` offered the first
    #: and neither offered the second. Six rows carry `objects=True` and
    #: none of them could reach a thing any module places -- while
    #: `carry`, `escort`, `destroy` and `protect` are exactly the scenes
    #: where moving or breaking the thing is the point. #1317.
    #:
    #: **A category rather than making `"object"` a magic value of `kind`.**
    #: That was the cheaper fix and `#1317` weighed both: `kind` is a real
    #: narrowing that `query.scenery(world, "fire")` depends on -- it is how
    #: a Requirement reading *"you must be adjacent to a fire"* works -- so
    #: collapsing the field into a free-text noun with one magic value puts
    #: those two uses in tension. The issue's own read was this option and
    #: it is what landed; it is a seam between `story/` and `content/`, so
    #: say so if the other reading is wanted -- the change is one field and
    #: one `or`.
    #:
    #: Empty by default, so a `terrain.put(kind="object")` keeps matching
    #: on its noun exactly as before and nothing had to be migrated.
    category: str = ""
    #: **What the thing is MADE OF**, which is a third question and not a
    #: value of either field above. `p15831`'s Requirement -- *"you must be
    #: adjacent to a Medium or larger tree or other wooden object, such as
    #: a door or a table"* -- names one material and three nouns, and a
    #: door, a table and a tree share nothing but the substance. #1321.
    #:
    #: **The noun half needed nothing**, which is what reading the corpus
    #: settled. 61 rows name a tree or wood and they fall into three
    #: groups:
    #:
    #: * **"adjacent to a tree, treant, or a plant of Large size or
    #:   bigger"** -- 14 rows, all unmarked, all asking the **noun** and
    #:   all already answered by `query.scenery(world, "tree")`. A wooden
    #:   door does not satisfy them, so a material would be the wrong
    #:   reader.
    #: * **"difficult terrain that is the result of trees, underbrush,
    #:   plants or natural growth"** -- forest walk, which is
    #:   `Grid.difficult`'s label and a different field again: the *going*
    #:   rather than the substance.
    #: * **`p15831` alone** wants the material.
    #:
    #: So the answer to "one field or two" is that the tree half was never
    #: missing. A tree is `kind="tree"`, `category="object"`,
    #: `material="wood"`, and each of the three answers a different printed
    #: sentence.
    #:
    #: Empty is **not recorded** rather than "no material", the same
    #: bargain `weight` strikes: no row may read an unrecorded material as
    #: anything.
    material: str = ""
    #: Pounds, `0` meaning **not recorded** -- see the note above. Read
    #: against `query.lift_limit` for *"one object you can lift"* and
    #: against a printed number for *"400 pounds or less"*. #1307.
    weight: int = 0
    fastened: bool = False
    by: int = 0


@dataclass
class Summon:
    """A creature a power put on the board, and whose power it was.

    *"An enemy hits a creature you summoned"*, *"creatures summoned by your
    artificer powers can shift 2 squares"* -- four item rows print this and
    none could ask it, because **nothing recorded it**.

    **Why `Companion.kind == "summon"` is not the answer.** It looks like
    one: `Cast.summon_inline` spawns with exactly that. But the *other*
    summon path -- `Cast.summon`, whose own comment calls it "the path every
    row uses" -- goes through `loader.spawn` and builds no `Companion` at
    all, deliberately: a `Companion` takes no turn, and a summoned creature
    on that path is given one. So reading `kind` answers correctly for the
    rarer path and silently False for the common one.

    **And not a relation either.** `Relation.MASTER_OF` is what
    `i2716p1`'s predicate reached for, and the rows' own notes say
    *"`c.summon` records nothing"* -- what it does not record is a
    relation, which is a narrower claim than it reads as. A relation also
    says something else: who commands whom. Being summoned is a fact about
    where the creature came from.

    So this is the fact, on both paths, and `query.is_summoned` is the
    reader. `by` is the summoner; `ref` is the power that did it, which
    `i2640p1` needs -- *"summoned by your artificer powers"* is a question
    about which row, not which creature.
    """

    by: int = 0
    ref: str = ""


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
    #: An Instinctive Effect **lent** to a creature whose own block prints
    #: none, run by `turns._uncommanded` exactly where the block's own one
    #: would be.
    #:
    #: *"If the creature normally does nothing if you end your turn
    #: without giving it a command, it instead uses a free action to make
    #: a basic attack against the nearest enemy"* -- `i3538p1`. The clause
    #: is about the creatures that print **no** effect, so it cannot be
    #: said by firing the block's own: `Cast.instinctive` answers False
    #: for exactly those.
    #:
    #: A callable rather than a ref, because the lent behaviour is the
    #: lending row's and has no block of its own. Runtime state like
    #: `Effect.on_end`, which holds closures for the same reason and is
    #: never serialised. `Cast.instinctive(fn=)` is what sets it.
    lent_instinctive: Any = None
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
    #: **Whose it was before it hit the floor**, which is not `by`. For a
    #: disarmed weapon `by` is the creature that *did* the disarming, and
    #: three rows print "call **your** weapon back to your hand" -- so the
    #: one fact they need was the one nothing recorded. `i1252x1`'s note is
    #: the statement of it: a dropped weapon has "no record of whose it
    #: was, so 'call your blade back' cannot pick it out".
    #:
    #: 0 for anything that never belonged to anybody -- a seed, a scroll,
    #: the four berries. Only `Cast.disarm` sets it today. #736.
    was: int = 0
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
class Counted:
    """A set of keywords that remembers **how many effects** want each one.

    The shape `Conditions` has and for the same reason: two powers can
    forbid the same keyword, and the first one to expire must not lift a bar
    the second is still imposing. `forbidden_keywords` and
    `required_keywords` were bare sets, so the second `add` was a no-op and
    whichever hold ended first `discard`ed the entry out from under the
    other. #526.

    **Reads like the set it replaced**, deliberately: `in`, `or`, `&`, `-`
    and iteration all answer off `live`, so the five reader sites in
    `dsl.py` and `drivers.py` did not change. `set & Counted` works through
    `__rand__`, since the left operand's `__and__` returns `NotImplemented`
    for a type it does not know.

    `forbidden`, `forbidden_usages` and `forbidden_attack_usages` beside it
    have the same shape and the same latent fault. They are not converted
    here -- no row makes an overlap reachable on any of them yet, and one
    issue names one gap -- but the class is the answer when one does.
    """

    counts: dict[Keyword, int] = field(default_factory=dict)

    @property
    def live(self) -> set[Keyword]:
        return {k for k, n in self.counts.items() if n > 0}

    def add(self, k: Keyword) -> bool:
        """True when this is the keyword's first holder."""
        was = k in self
        self.counts[k] = self.counts.get(k, 0) + 1
        return not was

    def discard(self, k: Keyword) -> None:
        """Give up one holder's claim on the keyword.

        Named `discard` rather than `remove` because that is what the set it
        replaced was called with, and an unheld keyword is not an error:
        `c.forbid`'s undo runs whether or not anything else touched it.

        **Returns nothing, where `Conditions.remove` returns "was that the
        last one".** That answer has no reader here, and `c.forbid` hands
        this straight to an `on_end` list typed `() -> None` -- so returning
        a bool made every undo lambda the wrong type, which `ty` said and
        was right about. A verb needs a reader; this one has none.
        """
        n = self.counts.get(k, 0) - 1
        if n <= 0:
            self.counts.pop(k, None)
            return
        self.counts[k] = n

    def __bool__(self) -> bool:
        return any(n > 0 for n in self.counts.values())

    def __contains__(self, k: object) -> bool:
        return self.counts.get(k, 0) > 0

    def __iter__(self) -> Iterator[Keyword]:
        return iter(self.live)

    def __len__(self) -> int:
        return len(self.live)

    def __and__(self, other: set[Keyword]) -> set[Keyword]:
        return self.live & other

    __rand__ = __and__

    def __sub__(self, other: set[Keyword]) -> set[Keyword]:
        return self.live - other

    def __rsub__(self, other: set[Keyword]) -> set[Keyword]:
        return other - self.live


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
    #: Parts of a condition's printed rules this creature does not suffer,
    #: by condition, naming `Rules` fields -- `{"attack", "halve_speed"}`.
    #:
    #: **Not `suppressed`, and the difference is the whole point.** Suppressing
    #: squeezing would mean you are not squeezing, so you no longer fit in the
    #: small space you squeezed into. Twelve rows print the other thing: you
    #: are still squeezing and some of what it costs does not apply to you --
    #: "you take no penalty to attack rolls", "you move at full speed", "you
    #: do not grant combat advantage". A condition's cost is three knobs and
    #: the cards turn them independently. #508.
    waived: dict[Condition, set[str]] = field(default_factory=dict)

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
        """Does this modifier's own gate pass for this roll?

        **Plus one substitution, which is a printed rule and not a
        kindness.** `cf:fighter-weaponmaster-f3s0` prints *"any of your
        feats that grant feat bonuses to attack rolls or damage rolls with
        one of your arena weapons apply to your other arena weapon as
        well"*, and a feat's weapon gate is a `when=` predicate inside
        **that feat's** body -- so nothing could reach in and widen it.
        That is what `c.shares_feat_bonus(weapon=)` named.

        So the widening happens on the **reading** side instead: when a
        gate fails, it is asked again with the context rewritten as
        though the swing had been with the other arena weapon.
        `resolve` puts the substitutions on the context and only when the
        creature actually swung one of the pair, so this costs a second
        predicate call on exactly the rolls the card is about.

        **Three narrowings, each straight off the printed sentence**, and
        together they are why this is not a general back door:

        * `kind == "feat"` -- the card says *feat* bonuses. A power's
          untyped rider is not shared.
        * `what in ("attack", "damage")` -- the card names those two
          rolls. A feat bonus to AC or to a skill is not shared.
        * only when the gate **failed**, so a predicate that already
          passes is never asked twice and nothing is double-counted:
          `Mods.total` buckets by kind, so two readings of one modifier
          could not add anyway, but the saving is real on the hot path.

        One door for both `Mods.total` and `Mods.split`, which is why it
        is here rather than in either -- the damage half of the printed
        sentence goes through `split`.
        """
        if self.when is None:
            return True
        if self.when(ctx):
            return True
        if self.kind != "feat" or self.what not in ("attack", "damage"):
            return False
        return any(self.when({**ctx, **alt})
                   for alt in ctx.get("arena_alt") or ())

    def amount(self) -> int:
        return self.value + (self.roll() if self.roll is not None else 0)


#: The suffix a clipping modifier is keyed under -- `"attack penalty clip"`.
#:
#: Shared by `Mods.total`, which reads it, and `Cast.bonus(clip=True)`,
#: which writes it, so the two cannot drift apart. A modifier key nothing
#: reads is this component's commonest bug and `lint.UNREAD_MODIFIER_KEYS`
#: exists because of it.
_CLIP = "penalty clip"


@dataclass
class Mods:
    items: list[Mod] = field(default_factory=list)

    def total(self, what: str, ctx: dict[str, Any] | None = None) -> int:
        """Sum the modifiers to `what`, applying 4e's stacking rules.

        **A clip lessens whatever penalty is standing and cannot turn it
        into a bonus**, which is the third stacking rule here and the one
        `p2384` prints: *"any penalty to attack rolls that such an ally
        takes is lessened by 2"*. `c.bonus(clip=True)` lays it under
        `"<what> penalty clip"`, and this is the only reader.

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
        clip = 0
        # **One pass, not two.** This is asked for every attack roll, save
        # and check in the game, so the clip key is matched inside the loop
        # that was already walking the list rather than by a second scan.
        clipped = f"{what} {_CLIP}"
        for m in self.items:
            if m.what == clipped:
                if m.applies(ctx):
                    # The **largest** clip and not their sum: two cards
                    # each lessening a penalty by 2 is two of a kind, and
                    # the better applies -- the same rule a typed bonus
                    # gets two lines down.
                    clip = max(clip, m.amount())
                continue
            if m.what != what or not m.applies(ctx):
                continue
            value = m.amount()
            if value < 0:
                worst[m.label] = min(worst.get(m.label, 0), value)
            elif m.kind == "untyped":
                out += value
            else:
                best[m.kind] = max(best.get(m.kind, 0), value)
        penalties = sum(worst.values())
        if clip and penalties:
            # **Never past zero**, which is what "lessens any penalty by 2"
            # says and what makes this different from a flat +2: with no
            # penalty standing it is worth nothing, and `p2384`'s own note
            # records that a flat bonus "would be a different card".
            penalties = min(0, penalties + clip)
        return out + sum(best.values()) + penalties

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
    #: How many times each row has been used **today**, by ref. The board
    #: half of `story.Sheet.per_day`, mirrored in by `story._wear` and back
    #: out by `story.harvest`, exactly as `used`/`spent` already are.
    #:
    #: `used` is per encounter and both rests clear it, so "a number of times
    #: per day" had nothing to count against and those rows were written as
    #: once per fight. The counter existed on the sheet and could not be
    #: reached from inside a fight, which is where a row runs. #507-adjacent;
    #: the allowance family is its own thing.
    per_day: dict[str, int] = field(default_factory=dict)
    #: Per-encounter resources that are **not** a row's use, keyed by a
    #: `<ref>:<what>` string the owning row coins. Cleared with `used` by
    #: both rests.
    #:
    #: `used` could not hold these, and #529 is the measurement: a trait is
    #: `action=NONE` with no trigger, so `turns.arm_traits` calls
    #: `dsl.use(..., spend=True)` on it, and a trait declared
    #: `usage=ENCOUNTER` therefore has its single use **spent at arming** --
    #: before round 1. All seven warlock pact boons were written against
    #: that use on the reasoning that "the boon is a row with
    #: `usage=ENCOUNTER`, so its charge *is* a use of that feature", and the
    #: charge was gone before any row could reach it. Driven: `used` goes
    #: 0 -> 1 across `arm_traits` for all seven, and `c.expend_row` then
    #: returns False.
    #:
    #: So arming a trait and holding a resource on it are two different
    #: things that wanted two different counters. `c.spend_charge` is the
    #: write and `c.charge_left` the read; `c.restore_charge` hands one
    #: back, which is what a boon that regains on a kill needs.
    charges: dict[str, int] = field(default_factory=dict)
    #: Every remnant this warlock has bargained with **since its last rest**.
    #:
    #: `#1046`, and it is Camille's design rather than mine:
    #:
    #:   > *"I still don't understand the question. Yes, keep rules parity.
    #:   > If i were writing this myself, I'd just save a set of used
    #:   > vestiges and wipe it on every rest."*
    #:
    #: The printed clause offers *"any other vestige you have been
    #: bargaining with since your last short or extended rest"*, so the
    #: options are a record over a rest-length window. `Cast.vestiges`
    #: reads `When.ENCOUNTER` effects, which is the right lifetime for
    #: "what may you bargain with" and the wrong one for this.
    #:
    #: **A list, not a set**, because `story.Sheet` carries it between
    #: encounters and a sheet is written as JSON. Order is insertion order
    #: and readers sort, the same arrangement `Cast.vestiges` already uses
    #: so a menu cannot depend on it.
    #:
    #: Wiped by **both** rests -- `turns.short_rest` and
    #: `turns.extended_rest` -- because the card names both.
    vestiges_used: list[str] = field(default_factory=list)
    #: **Rolls recorded now and spent later, by the row that recorded
    #: them.** `p14141` records three d20 results for an ally to use in
    #: place of its next three, and *"when you next take an extended rest,
    #: the effect ends"* -- so they outlive the encounter, which
    #: `When.ENCOUNTER` cannot say.
    #:
    #: Kept here rather than in the row's own closure because a closure
    #: dies with the fight. `story.Sheet.kept_rolls` is the persisted half
    #: and `story._wear`/`harvest` mirror the two, exactly as `per_day`
    #: above is mirrored; the extended rest clears it, which is the printed
    #: clock and the only thing that does.
    #:
    #: Keyed on the **recording row's** ref and held on the creature whose
    #: rolls they replace -- which is not the caster. `p14141` records them
    #: on an ally, so a count on the caster would follow the wrong sheet.
    #:
    #: A list because they are spent in order, front first: *"in the order
    #: they come"*. Empty or absent both mean none left, and the row's
    #: watches are a no-op then.
    kept_rolls: dict[str, list[int]] = field(default_factory=dict)
    #: **How large a grant's allowance is, and how much of it has gone**,
    #: both keyed on the **granted** row's ref.
    #:
    #: `Cast.grant_row(uses=)` is the printed cadence of the card doing the
    #: granting laid over a row with a cadence of its own -- *"you can use
    #: that power once per encounter"* over an at-will. It held both of
    #: these numbers in a closure: `uses` was the parameter and `spent` a
    #: one-element list, so the allowance was correct and **unreachable**.
    #:
    #: `f2442` is the card that wanted to reach it. It adds a *second* use
    #: to the row `rt:r6-t3` hands over, when that row is martial, and the
    #: only ways in were to re-grant (refused -- `grant_row` returns None
    #: for a ref already known) or to find the other row's `forbid` by
    #: parsing its label, which is the read `Cast.stored_row` exists to
    #: replace. `Cast.raise_grant` is the write and it needs the cap to be
    #: a fact about the creature, which is what it is.
    #:
    #: Here rather than in a rest's bookkeeping because the lifetime is the
    #: **grant's**: `grant_row`'s own `on_end` drops both entries beside the
    #: ref it drops from `known`, so a grant that lapses mid-fight takes its
    #: allowance with it and no rest has to learn a new field.
    #:
    #: Absent means *no* allowance rather than none left -- `uses=0` leaves
    #: the granted row its own printed cadence, which is the common case and
    #: writes nothing here.
    granted_uses: dict[str, int] = field(default_factory=dict)
    granted_spent: dict[str, int] = field(default_factory=dict)
    #: Rows whose own `Cast.grant_row` calls do **nothing** for this
    #: creature, by ref.
    #:
    #: One printed sentence needs it: *"if the feature grants powers, this
    #: feat does not grant them"*. `f3589` trades a cleric's templar
    #: feature for one of the nine domain features printed under
    #: `cf:cleric-warpriest-f1`, and **all nine** hand their domain's cards
    #: over with `c.grant_row` inside their own bodies. A borrowed trait is
    #: armed, so borrowing one gave the powers too -- strictly better than
    #: print, and silently, because both halves are individually correct.
    #:
    #: Keyed on the **granting** row rather than on the granted card,
    #: because the card is what the body picks and the sentence is about
    #: the feature. `Cast.borrow_row(powers=False)` is the only writer and
    #: the borrow's own effect takes the entry away with it.
    #:
    #: Not a `Cast.forbid`: that refuses a row the creature *has*, and this
    #: stops it arriving at all. A creature that already knew the card
    #: keeps it.
    grants_blocked: set[str] = field(default_factory=set)
    #: Rows this creature uses as **daily** powers whatever their card
    #: declares, by ref.
    #:
    #: `Power.usage` is a fact about the card and the same card is an
    #: encounter power for everybody else, so the override cannot live
    #: there. It is a fact about the creature, which is why it lives
    #: here beside `used`.
    #:
    #: `cf:wizard-bladesinger-f2` and its two later rungs are the printed case: *"you add two
    #: wizard encounter attack powers to your spellbook... the two
    #: function as daily attack powers for you"*, three times over. The
    #: direction matters -- an encounter power used as a daily is
    #: **weaker**, so dealing those powers without this would hand the
    #: character something stronger than its own card prints.
    #:
    #: Read by `turns.short_rest`, which is where the two usages differ:
    #: a short rest gives back everything that is not daily, and a ref in
    #: here is daily for this creature.
    as_daily: set[str] = field(default_factory=set)
    #: Augment clauses a **feat** lent to a named row, as `(cost, clause)`.
    #:
    #: Four feats print "your <power> gains the augmentable keyword. When you
    #: would use it, you can spend 1 power point to <effect>" -- an Augment
    #: line on a card that prints none. The clause is the feat's, not the
    #: power's, so it cannot live in the power's header and the power's body
    #: has no way to know it.
    #:
    #: **A callable, like `pre_empts` above**, and for the same reason: the
    #: lending row is the only thing that knows what its clause does.
    #:
    #: `content.powers.augment.lent` is the read, and the lent-to row must
    #: call it -- a lent augment on a row that never asks is a modifier
    #: nothing consults, which is this component's commonest bug. #507.
    lent_augments: dict[
        str, tuple[tuple[int, Callable[[Any], None]], ...]
    ] = field(default_factory=dict)
    #: The same lend aimed at a **class of rows** instead of one ref,
    #: keyed by class name. Five battlemind aspects print "while in this
    #: aspect you can use the following augmentation with your <class>
    #: at-will attack powers that are augmentable", which names a set the
    #: ref-keyed dict above cannot say -- the character's whole augmentable
    #: at-will repertoire, whatever it happens to hold.
    #:
    #: `content.powers.augment.augment` is the read, and it is read there
    #: rather than in each row because **none of the 28 rows this reaches
    #: asks**: the ref-keyed half works only because all five of its
    #: lent-to rows call `augment.lent` by hand, and a class lend has no
    #: such list to edit.
    lent_class_augments: dict[
        str, tuple[tuple[int, Callable[[Any], None]], ...]
    ] = field(default_factory=dict)
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
    #: Of those, the ones still offered when their own use is gone --
    #: *"even if you have already used it this encounter"*. Not keyed by
    #: window, because the waiver is about the row's usage and not about
    #: where the swing came from, and a card printing it names one row.
    #:
    #: `dsl.basic_options` turns this into `usable(..., spent_ok=True)`,
    #: which waives the usage limits **alone** -- so a row the character
    #: does not hold, cannot act with, or has not finished is still
    #: refused. `c.as_basic(spent=True)` is what fills it.
    instead_when_spent: set[str] = field(default_factory=set)
    #: The ranged basic attack, for a creature that has one. Separate from
    #: `basic`, which is the melee one: pointing `basic` at a ranged row
    #: would hand it to the opportunity window too. Empty for a monster,
    #: whose ranged attacks are its own printed rows.
    ranged: str = ""
    #: Rows taken away for a while. Not the same as spent: a forbidden row
    #: is one the creature still has and cannot currently reach.
    forbidden: set[str] = field(default_factory=set)
    #: **A named row's own Requirement, waived while a predicate holds.**
    #: Keyed by the ref the waiver is *for*, so it can never become a
    #: blanket one -- which is the property `dsl.usable`'s existing waiver
    #: note demands: *"waiving the whole requirement would make every
    #: `requires=` a suggestion for anybody willing to route through
    #: `use_power`."*
    #:
    #: Three printed lines want it and all three are the same sentence --
    #: a Requirement met by something its own predicate will not accept.
    #: `f2931` is bloodied, `f2933` offers the creature that triggered
    #: `p8278`, `f2338` offers a crossbow where the card demands a light
    #: blade. None of them is a new gate.
    #:
    #: The predicate takes `(world, eid)`, which is deliberately the **same
    #: shape as `requires=` itself** -- `Power.can_branch` has exactly those
    #: two to hand, and a waiver written like the gate it answers cannot
    #: drift from it. `None` is an unconditional waiver, which is what a
    #: card printing no condition gets.
    waived_requires: dict[str, list[Any]] = field(default_factory=dict)
    #: The subset of `forbidden` that is there because a **grant's uses ran
    #: out**, rather than because anything prohibited the row.
    #:
    #: `c.grant_row(uses=N)` counts the holder's own `PowerUsed` and forbids
    #: the row when they run out -- which is the only mechanism available,
    #: since an at-will has no printed allowance to exhaust. But the two are
    #: different facts, and one reader has to tell them apart:
    #: `grant_attack(reentrant=True)` is "the target repeats *this* use", so
    #: its docstring promises the usage limit stands aside. It did not,
    #: because `usable` refuses anything in `forbidden` unconditionally and
    #: two gates before it looks at `spent_ok`. #820.
    #:
    #: Narrow on purpose: a genuine prohibition -- "loses the ability to use
    #: that power" -- is **not** in here and still refuses a reentrant
    #: repeat, which is the whole reason this is a second set rather than a
    #: flag on the first.
    #:
    #: Cleared by the same `undo` the forbid itself carries, so it cannot
    #: outlive the limit that put it here.
    spent_out: set[str] = field(default_factory=set)
    #: Keywords whose rows cannot be used. *"The target is dazed and cannot
    #: use powers that have the polymorph keyword"* -- two items print that,
    #: and `p12344`'s "cannot teleport" is the same thing said about a
    #: different keyword.
    #:
    #: **Counted, not a set** -- see `Counted` for why, and for which
    #: neighbours still are not. #526.
    forbidden_keywords: Counted = field(default_factory=Counted)
    #: Keywords a row **must** carry to be usable -- the opposite reading,
    #: and four rows print it: *"you can't use weapon or implement attack
    #: powers that lack the beast form keyword."* Kept apart from
    #: `forbidden_keywords` rather than inverted into it, because the two
    #: sentences coexist on one creature and a single set cannot say which
    #: direction each entry means. #487.
    required_keywords: Counted = field(default_factory=Counted)
    #: Usage categories whose rows cannot be used. *"The target can't use
    #: encounter powers until the end of its next turn"* -- a whole category
    #: rather than one ref, which `forbidden` could not say.
    forbidden_usages: set[Usage] = field(default_factory=set)
    #: **Action types whose rows this creature cannot use.** The same shape
    #: as `forbidden_usages` one line up and for the same reason: a whole
    #: category rather than a number of refs, which `forbidden` cannot say.
    #:
    #: *"The only actions that the horse can take while riderless are move
    #: actions and free actions"* -- `i1662p1`, and the printed sentence is
    #: an **allow**-list, so the row inverts it: everything but move and
    #: free goes in here. `conditions.Rules` has `no_standard`,
    #: `one_action` and `cannot_act` for the condition-derived cases and no
    #: entry for a minor, so there was nothing to lay and nothing to read.
    #:
    #: Read in `dsl.usable` beside the usage sets, so `actions.legal`
    #: follows without learning anything -- it offers what `usable`
    #: allows.
    forbidden_actions: set[ActionType] = field(default_factory=set)
    #: **The only attack rows this creature may reach**, by ref, when it is
    #: not empty. *"When it attacks, the target can only make a melee basic
    #: attack"* and *"dominated … but can use only basic attacks"* are the
    #: two printed shapes, and neither could be said: `forbidden` names what
    #: is taken away and there is no number of refs that spells "everything
    #: else".
    #:
    #: **Attack rows only.** Both cards narrow what the creature may *attack*
    #: with; a heal or a buff is not an attack and is left alone, which is
    #: what "can only make a melee basic attack" says and not a word more.
    #:
    #: A plain `set[str]`, which is what `forbidden` above is and for the
    #: same reason: `Counted` is typed for `Keyword` and these are refs.
    #: The cancel hazard `Counted` exists for is handled the way
    #: `forbidden_usages` handles it -- the undo discards only what its own
    #: call added.
    #:
    #: Two holds naming **different** refs would leave both reachable, which
    #: is weaker than either alone. Accepted rather than engineered around:
    #: it needs one creature under two such cards, and the tree holds two
    #: rows, on two different monsters.
    only_attacks: set[str] = field(default_factory=set)
    #: The same, narrowed to **attack** powers: *"the target cannot use
    #: encounter or daily ATTACK powers"*. Kept as a second set rather than
    #: a flag beside the first, for the reason `required_keywords` gives
    #: about its own neighbour -- both sentences can be true of one creature
    #: at once and a flag could not say which entry each belonged to.
    forbidden_attack_usages: set[Usage] = field(default_factory=set)
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
    #: **What a named row's next die comes up**, by ref. The sibling of
    #: `dice` one field up and a different question: that one says *which*
    #: die a row rolls, and this says what it **shows**.
    #:
    #: One card prints it -- *"you lose a healing surge, and you can select
    #: the result of your d6 roll"*, answering the moment its sibling is
    #: used. `c.boost_roll` adds to a roll and `c.replace_roll` substitutes
    #: a face on a d20 that `resolve.settle` recomputes; neither reaches a
    #: plain `c.roll` in the middle of a body, which is where that d6 is
    #: thrown.
    #:
    #: **One-shot, consumed by the read.** The printed clause is about *the*
    #: d6 roll, singular, so a face left lying about would pin the next one
    #: too. `Cast.picked` pops it; the effect that laid it clears whatever
    #: is left on expiry, so a choice made and never rolled does not
    #: outlive its duration.
    #:
    #: **The row that rolls must read it**, with `Cast.picked` -- the same
    #: arrangement `dice` has with `Cast.dice_for`, and for the same reason:
    #: a pick on a row whose body ignores it is a modifier nothing consults.
    picked_roll: dict[str, int] = field(default_factory=dict)
    #: How big a number a named mechanic hands out, when something has
    #: changed it. The third sibling of `dice` and `extra_squares`, and the
    #: same argument once more: "you grant a +3 bonus, rather than the
    #: normal +2" is about an amount written inside somebody else's body.
    #:
    #: Aiding another is where it was first needed -- three monster traits,
    #: two feats, an item and a racial power all raise the granted bonus,
    #: and none of them can reach the 2 inside `Cast.aid_attack`.
    #:
    #: **The largest matching entry wins, where `dice` takes the first.**
    #: The printed rule is that an ally benefits once per attack, so two
    #: rows both speaking about one grant are not additive and the better
    #: one applies. First-wins would have made the answer depend on which
    #: effect was laid last, which is not a rule anybody printed.
    #:
    #: `Cast.amount_for` is the read and the row handing the number out
    #: must use it.
    #: An entry's first half is the number, or a **callable** counted at
    #: each read -- `query.granted_amount` resolves it, the way
    #: `Mods.total` resolves `Mod.roll`. `c.change_amount(compute=)`
    #: is the writer, for a card whose number changes as the fight
    #: moves.
    amounts: dict[
        str,
        list[tuple[int | Callable[[], int],
                   Callable[[dict[str, Any]], bool] | None]],
    ] = (
        field(default_factory=dict)
    )

    #: Which "once per round" or "once per turn" payouts this creature has
    #: already spent, by the paying feature's label, holding the window it
    #: was spent in.
    #:
    #: **It lived in a closure and that is why two rows could not be
    #: written.** `features/strikers.extra_damage` kept `paid: dict[int,
    #: object]` inside itself, so nothing outside could ask whether the
    #: striker had paid this round or hand the payment back -- and two
    #: feats are exactly those sentences: "a second helping after an action
    #: point" and "pays the extra damage on a miss". Both blamed a missing
    #: *announcement*, which was never the gap: `extra_damage` already
    #: passes `detail=label` and the damage events carry it. #569.
    #:
    #: The value is the window, not a boolean, because the window is the
    #: thing with the rule in it: per *round* for two strikers and per
    #: *turn* for the rogue, which a solo with two initiative slots can
    #: reach twice. A boolean would need clearing by somebody, and the
    #: round number clears itself.
    latched: dict[str, Any] = field(default_factory=dict)
    #: Extra squares a named row moves you, when something has lengthened it.
    #:
    #: The exact sibling of `dice` above, and the same argument wins it: the
    #: distance a row moves you is an **argument inside its own body** --
    #: `c.teleport(8)`, `c.shift(1)`, `c.slide(3)` -- so "one more square on
    #: every swordmage teleport" and "five squares further on that power" had
    #: nothing to change. Eleven rows print a sentence of that shape and each
    #: says so in its own docstring.
    #:
    #: A second move laid beside the first is **not** the same thing: two hops
    #: of 1 and 8 are not one hop of 9 when something blocks the way, and
    #: `f1236`'s note already said that.
    #:
    #: A list, latest first, and `when` is a context predicate so "if it ends
    #: beside a shrouded enemy" is sayable. The values **add**, unlike `dice`
    #: where the first match wins: two feats each granting a square give two
    #: squares, which is what the cards say. `Cast.squares_for` is the read
    #: and the row that moves must use it. #502.
    extra_squares: dict[
        str, list[tuple[int, Callable[[dict[str, Any]], bool] | None]]
    ] = field(default_factory=dict)
    #: Extra uses of a named row, per encounter, **for this creature only**,
    #: by ref.
    #:
    #: "You gain one more use of `p12668` per encounter, but you can still
    #: use it only once per turn" -- seventeen class-feature rows across six
    #: Essentials chassis print that sentence, and a row's allowance is
    #: otherwise **header data**: `Power.uses`, fixed at import, shared by
    #: everybody who holds the row. A feature cannot raise it without
    #: raising it for everybody.
    #:
    #: Read in `dsl.usable`, which is the one place `Power.uses` is
    #: compared against `Powers.times` -- so there is no second site to
    #: keep in step, unlike `granted_keywords` with its 22 readers. The
    #: values **add**: two features each granting a use give two, which is
    #: what the cards say.
    #:
    #: The printed "only once per turn" needs nothing from this: it is
    #: `Power.once_per_round`, a separate header field tested a few lines
    #: above the allowance, so raising the per-encounter count cannot
    #: accidentally allow two in a turn. #642.
    extra_uses: dict[str, int] = field(default_factory=dict)
    #: **A budget across a whole class's daily attack powers**, as
    #: `(class, how many a day)`. `None` is no cap, which is every class
    #: but one.
    #:
    #: `cf:bard-skald-f1` prints it: *"each day you can use only one `c104`
    #: attack power ... two per day [at 5th] ... three [at 9th], but no
    #: more than one of a particular level."* Every other allowance in this
    #: file is **per ref** -- `used`, `per_day`, `extra_uses` -- and this
    #: is a cap over a family, which is why it could not be spelled with
    #: any of them. `c.spend_per_day` on a shared label is the nearest and
    #: is a pool for *named* rows (`cf:artificer-f2`'s three infusions),
    #: not a cap over everything a class knows.
    #:
    #: Read at the one site in `dsl.usable` that compares a spend against
    #: an allowance, which is the safety argument `extra_uses` above makes:
    #: one reader cannot be honoured in one place and ignored in another.
    #:
    #: **The tally is `used`, and that it works is a fact about the rest
    #: model rather than a new field.** `turns.extended_rest` is the only
    #: thing that clears `used`, so for a daily power `used` already *is*
    #: "spent today" -- a short rest leaves it alone. `#1276`.
    daily_cap: tuple[str, int] | None = None
    #: Skills this creature rolls **twice** on, keeping either result, by
    #: lower-case skill name.
    #:
    #: "Whenever you make a Stealth check or a Thievery check, you can roll
    #: twice and use either result" -- four class-feature rows across three
    #: Essentials chassis print it, and the tree had no reader: `c.reroll_ones`
    #: and `c.reroll_faces` are both about **damage** dice, and
    #: `vocab.py --find reroll` finds nothing else.
    #:
    #: Read in `skills.check`, which is the one place a check's d20 is
    #: rolled -- one reader, which is the same safety argument
    #: `extra_uses` above makes and the opposite of `granted_keywords`
    #: with its 22 sites.
    #:
    #: **A set and not a count.** "Roll twice" does not compose: two
    #: features each granting it to Stealth still roll twice, where two
    #: features each granting an extra use give two uses. That is why this
    #: is shaped differently from the field above it.
    #:
    #: The printed "use either result" is taken as the better one. A
    #: headless run has to pick and the offer is pure benefit, so there is
    #: nothing to weigh -- the same reading `c.may` gets for an offer with
    #: no cost. #642.
    #: **Scoped entries, since `#1276`.** A plain `"stealth"` is every
    #: Stealth check; `"acrobatics@escape"` is an Acrobatics check made
    #: as part of the escape action and nothing else.
    #:
    #: `cf:rogue-thief-f18` is why, and it is the printed distinction
    #: rather than a convenience: it pays *"as part of the escape
    #: action"* only, so granting the skills outright would roll twice on
    #: every climb -- which its own docstring refused to do, correctly,
    #: and kept the marker for. `cf:rogue-thief-f20` beside it prints no
    #: action test and stays unscoped.
    #:
    #: One set rather than two, keyed `skill@purpose`, because
    #: `skills.check` already takes a `purpose` and the read is then one
    #: membership test against each spelling.
    rolls_twice: set[str] = field(default_factory=set)
    #: Saving throws this creature rolls twice, by **condition** -- or
    #: `"*"` for every throw.
    #:
    #: A different field from `rolls_twice` above because it is a
    #: different roll read in a different module: a check's d20 comes out
    #: of `skills.check` and a throw's out of `durations.Clock.save`.
    #: `cf:rogue-thief-f18` names both halves and carried **two** symbols
    #: for exactly that reason -- a row waiting on one would have
    #: reported ready with half a facility.
    #:
    #: Matched against `Effect.conditions`, which the save context
    #: already carries for the eighteen rows that narrow a save bonus the
    #: same way. So *"against an effect that immobilizes, restrains, or
    #: slows you"* is three entries and needs no new vocabulary.
    #:
    #: A set and not a count, for the reason above it: rolling twice does
    #: not compose.
    saves_twice: set[str] = field(default_factory=set)
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
    #: **Two keys are reserved and are not refs.** `"*"` is every row
    #: this creature uses and `"*attack"` is every row of its that
    #: declares an `Attack` -- *"every attack you make gains the fear
    #: keyword"* is about the creature, so it had nowhere to live in a
    #: store keyed by ref. `dsl.keywords_of` is where both are read, and
    #: no ref can collide with them because every ref starts with a
    #: letter.
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
    #: **The clause takes the using `Cast`, and this said it took nothing.**
    #: `Cast._instead_of` calls `clause(self)` and `picked(self)` -- a
    #: substitution has to know who is being hit -- so `Callable[[], Any]`
    #: was wrong from the start and nothing noticed, because every caller
    #: passed a bare `lambda using: ...` that `ty` never had to reconcile
    #: against a typed append. `#954`'s driver rule appends a properly
    #: annotated function and the declaration went red at once. #954.
    pre_empts: dict[tuple[str, str], list[tuple[Callable[[Any], Any], str]]] = field(
        default_factory=dict
    )
    #: The same substitutions, **imposed rather than offered**.
    #:
    #: `pre_empts` above is "you **can** X instead of Y": each registration
    #: is its own action-menu entry and `Cast.instead_of` reads the chosen
    #: one off `Cast.variant`. Two heroic weapon blocks print the other
    #: mood -- *"**Instead of** normal damage, each target hit takes ongoing
    #: 5 fire damage"* -- where there is no choice to click and no variant to
    #: settle, and the clause must apply to a swing nobody picked from a
    #: menu at all: `Cast.basic` calls `dsl.use` with no `variant`, so an
    #: optional registration is read as variant 0 and the printed clause
    #: stands. The substitution was registered, offered nowhere, and silent.
    #:
    #: Keyed and shaped exactly like `pre_empts` so `instead_of` can read
    #: both, and consulted **first**: an imposed clause is not a choice, so
    #: it cannot be one of the options a variant indexes.
    #:
    #: Written by `c.pre_empt(forced=True)`. #712.
    #: Same correction as `pre_empts` above and for the same reason: the
    #: clause is handed the using `Cast`. #954.
    forced_clauses: dict[tuple[str, str], list[tuple[Callable[[Any], Any], str]]] = field(
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
    #: **A row held by an object rather than by a creature**, keyed by the
    #: ref of the row doing the holding -- an item's Property -- and valued
    #: with the ref it is holding.
    #:
    #: Three cards print this and none of them could be written: an armour
    #: that stores a power until it is used, and two alchemical items that
    #: link to a second item and set it off. `c.grant_row` is the near miss
    #: and is the wrong shape, as `i540p1`'s note says: it hands a row to a
    #: *creature*, so the power becomes the wielder's for the encounter,
    #: where the printed thing is a property of the armour that the wielder
    #: then spends an action on.
    #:
    #: **Keyed by the holder so two items cannot collide**, which is the
    #: whole reason this is a dict and not a field: a character can wear an
    #: armour that stores a power and carry a linked flask at the same time,
    #: and each has to read back its own.
    #:
    #: On the wielder's `Powers` rather than on the item, because an item is
    #: not an entity and there is no component to hang it on. That is sound
    #: here precisely because nothing persists between encounters -- the
    #: store is settled when the Property arms and dies with the fight,
    #: which is the model `c.borrow_row` already argues for. #720.
    stored: dict[str, str] = field(default_factory=dict)

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

    def clear_round(self, ref: str) -> bool:
        """Forget the round mark, leaving any spent uses alone.

        The inverse of `note_round`, and **not** `restore`: that pops
        `used` as well, which would refund a use to a row that is both
        once-per-round and limited -- right for the at-wills that have no
        uses to refund and wrong for anything else. Two cards grant a
        second use of a once-per-round row in one turn and neither says
        anything about its daily or encounter budget.

        Returns whether there was a mark to clear, which is the printed
        Requirement on both: *"you have already used ... during this
        turn"*.
        """
        return self.last_round.pop(ref, None) is not None

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
    #: Points **above** the pool that expire on a clock rather than at the
    #: end of the fight -- "you gain 2 power points that expire at the end
    #: of your turn".
    #:
    #: A second number rather than a bigger `points`, for two reasons the
    #: cards force. `gain` clamps at `maximum`, which is right for "you
    #: regain 2 power points" and wrong here: a full pool must still take
    #: these, because the card grants them from outside. And they have to
    #: be told apart to be taken away again when the clock runs out, which
    #: a single total cannot do.
    temporary: int = 0
    #: Points banked **inside an item**, keyed by its ref. "Expend 1 or 2
    #: power points and place them in the orb. They remain there until you
    #: use them or until you take an extended rest."
    #:
    #: Deliberately **not** cleared by `refresh`, which is the whole
    #: printed difference from `points` and `temporary`: those come back
    #: every encounter and these survive until the day ends.
    #: `turns.extended_rest` is what empties them.
    stored: dict[str, int] = field(default_factory=dict)
    #: Caps on augments somebody else is paying for. Each entry covers
    #: **one** augment of at most that many points, and is taken by
    #: `take_payer` where `dsl.use` settles the cost.
    #:
    #: A cap rather than a source, because the row has already paid by the
    #: time it lays one -- a healing surge for `i1966p1`, a point out of
    #: `stored` for `i1980p2` -- so what is left to record is only how
    #: much is covered. That is what lets one hold serve both cards.
    payers: list[int] = field(default_factory=list)

    def take_payer(self, cost: int) -> bool:
        """Spend a payer that covers `cost`, if one does. One augment each.

        The **smallest** sufficient cap goes first, so a card covering 2
        is not burnt on an augment a card covering 1 could have paid for.
        """
        fits = sorted(n for n in self.payers if n >= cost)
        if not fits:
            return False
        self.payers.remove(fits[0])
        return True

    def refresh(self) -> None:
        self.points = self.maximum
        self.temporary = 0
        self.payers.clear()
        self.augmented.clear()
        self.last.clear()

    def spend(self, n: int) -> int:
        """Take `n` points if they are there. Returns how many actually went.

        **Expiring points go first**, which is not a courtesy to the
        player: they are about to vanish, so spending the pool ahead of
        them would throw them away and make the granting card worth
        nothing on any turn the character also augments from the pool.
        """
        n = max(0, min(n, self.points + self.temporary))
        from_temp = min(n, self.temporary)
        self.temporary -= from_temp
        self.points -= n - from_temp
        return n

    def gain(self, n: int) -> int:
        """Put `n` points back, never above `maximum`. Returns how many went.

        The mirror of `spend`, and clamped at the top for the same reason
        that clamps at the bottom: *"you regain 2 power points"* on a full
        pool regains nothing, and a row reaching into `points` by hand
        would be the one place in the tree doing its own bookkeeping on a
        store five readers share.
        """
        n = max(0, min(n, self.maximum - self.points))
        self.points += n
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
class Afflictions:
    """What a creature has caught. #389.

    `contracted` maps a disease's ref to the stage it is at, which is **1**
    for every row in the tree -- "the target contracts `x5_23`" is the whole
    of what 47 monster cards say, and every disease page prints stage 1 as
    where you start.

    **The stage never advances in play, and that is the cards' doing rather
    than a gap.** Every one of the 69 pages checks at the *end of an extended
    rest*, and an extended rest does not exist in this engine -- `chargen`
    says persistence does not exist and the adventuring day is a deliberate
    `501`. So a disease caught in a fight stays at the stage it was caught
    at for the rest of that fight, which is exactly what the printed rules
    say happens.

    What the state is *for* inside an encounter is the rows that ask about
    it: `m5100a0`'s aura acts on "an enemy that has been exposed to a
    disease", and before this there was nothing to ask.
    """

    contracted: dict[str, int] = field(default_factory=dict)

    #: Caught but not settled: the disease's ref mapped to the stage it
    #: would be contracted at, while the end-of-encounter saving throw is
    #: still owed. **Nineteen cards distinguish this from `contracted` and
    #: the model did not** -- "the target is exposed to `x5_59`" at the
    #: moment of the hit, and the throw at the end of the fight decides
    #: whether it moves across. `m5100a0`'s trait asks after this one by
    #: name and had nothing to read, which is what its `c.exposed(pending=)`
    #: marker has been naming. #515.
    pending: dict[str, int] = field(default_factory=dict)


@dataclass
class Gear:
    """What the creature is holding and wearing, as mechanical facts only.

    A weapon is its numbers -- there is no place here for a printed name.
    """

    weapons: list[Weapon] = field(default_factory=list)
    #: Which shield is held: 0 none, 1 light, 2 heavy -- and the number is
    #: the printed AC and Reflex bonus, which `query.shield_bonus` reads off
    #: the `armour` table rather than from this literal.
    #:
    #: **Annotated `bool` until now, and chargen flattened it on the way in**
    #: (`shield=bool(carried_shield)`), so the kind was known on the class
    #: line -- documented there as "0 none, 1 light shield, 2 heavy shield" --
    #: and thrown away at this boundary. Nine rows wanted the number: "your
    #: shield bonus also applies to Fortitude", "raises the light shield's
    #: bonus by one", "trade the shield's bonus to AC and Reflex for damage".
    #: None of them could ask.
    #:
    #: Every existing reader tests truthiness (`bool(gear.shield)`, `if
    #: gear.shield or ...`), which is why widening it moves nothing: checked
    #: across all 55 sites, none compares against True or False.
    shield: int = 0
    armour: str = "cloth"
    #: What is on the belt rather than in the hands, by weapon ref.
    stowed: set[str] = field(default_factory=set)
    #: The weapon most recently put away, by ref.
    #:
    #: *"The weapon most recently sheathed in the scabbard"* --
    #: `i2361p1` and `i2400p1`, which both had to recolour whatever was
    #: in hand because `stowed` is an unordered `set[str]` and says only
    #: *that* a weapon is away, never *when*.
    #:
    #: Written by `wield`, which is the one place a weapon goes from
    #: held to stowed, and read by `Cast.sheathed`. Empty for a creature
    #: that has never put one away, which is most of them.
    last_sheathed: str = ""
    #: What may not be **swung**, by weapon ref, while still being held.
    #:
    #: *"While grabbing the target, you cannot make attacks with the
    #: whip"* -- `f970b`. Deliberately not `stowed`: the whip is still in
    #: hand, so `c.wielding` must keep saying so and the grab it is
    #: holding does not end. What changes is which weapon a swing may
    #: come through.
    #:
    #: Read by `swingable` below, which `melee` and `ranged` filter -- so
    #: `main`, `off` and every reader of those get it from one place
    #: rather than each asking. `c.forbid(weapon=)` is what fills it.
    barred: set[str] = field(default_factory=set)
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
    #: Ranged weapons that have been **fired and not yet reloaded**, by ref.
    #:
    #: Only a weapon whose printed properties include a *costed* load can
    #: ever appear here. The table carries two forms and only one is a cost:
    #: `load free` on seven weapons, `load minor` on three -- `w3629`
    #: crossbow, `w3659` superior-crossbow, `w3662` blowgun. #725.
    #:
    #: **Spent rather than loaded, and the inversion is deliberate.** Held
    #: as "which are loaded" it would have to be filled in everywhere a
    #: creature is built -- `chargen.spawn`, `loader.spawn`, the audit
    #: board, `story`, every drivers pose -- and one missed site is a
    #: crossbow that can never fire, which looks exactly like a row that
    #: does not work. Held as "which are empty" an untouched creature is
    #: ready, which is both the common case and the safe default.
    unloaded: set[str] = field(default_factory=set)
    #: What a reload costs this creature, where `None` is the printed minor.
    #: The mirror of `draw_cost` above and for the identical reason: four
    #: rows print "you can load a crossbow as a free action", and what they
    #: change is what it *costs*, which is a fact about the creature rather
    #: than about any row. `c.loads_free` is what records it. #675, #725.
    load_cost: ActionType | None = None
    #: How many cheap reloads remain this turn. `-1` is unlimited, which is
    #: what a card printing no limit means.
    loads_left: int = -1
    #: What `loads_left` refills to at the start of this creature's turn.
    load_allowance: int = -1
    #: Which weapon the cheaper reload applies to, by ref. Empty is every
    #: weapon.
    load_only: str = ""
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
    #: Weapon properties that only count against *some* creatures:
    #: `(property, ref, predicate)` triples, where the predicate is handed a
    #: victim's entity id and answers whether this character's blows count
    #: as carrying the property against that creature right now.
    #:
    #: **The `ref` is in the key so that arming the trait twice says the
    #: same thing once**, which is the behaviour the blanket gets for free:
    #: `every=True` unions into a `set`, where a list of closures cannot
    #: dedupe itself -- two closures are never equal, even built from the
    #: same line of the same row. So the writer replaces an entry with the
    #: same `(property, ref)` rather than appending beside it.
    #:
    #: Separate from the properties on `Weapon` because a property lives on
    #: the weapon and **the weapon does not know who it is pointed at**.
    #: `f2893` prints "while an enemy grants combat advantage to you, your
    #: attacks against that enemy count as silvered" -- both halves dynamic,
    #: scoped to one creature at a time -- where `f1075` prints the blanket
    #: and lays it on the weapons with `every=True`.
    #:
    #: A predicate rather than a set of ids because the gate comes and goes
    #: mid-fight and nothing emits when it does: combat advantage is derived
    #: from position, conditions and modifiers, so a set written when the
    #: trait armed would be answering about the board as it was. Resolved at
    #: the moment of the read instead, which is `Cast.struck_by_property`.
    scoped: list[tuple[str, str, Callable[[int], bool]]] = field(
        default_factory=list)
    #: The weapon the swing **in flight** is made with, by ref, overriding
    #: what is in hand -- and `""` for every swing that is not one of
    #: these.
    #:
    #: Two cards print it: *"make a basic attack with the claw"* (`f977`,
    #: `i1261p1`), where the claw is filed **stowed** on purpose. `Gear`
    #: answered "what is in hand" and nothing else, so each blow was
    #: struck with whatever the wearer happened to be holding.
    #:
    #: **Not `hand=`, and not putting it in hand.** `hand=` picks main or
    #: off out of what is already held, which a stowed weapon is not, and
    #: wielding it would silently disarm the wearer -- `Gear.wield` puts
    #: away whatever cannot share the grip. Rolling the swing longhand
    #: through `c.attack` would stop it being a *basic* attack, which is
    #: the word the card prints and what every rider keyed on one reads.
    #:
    #: Read by **both** pickers, which is the care this needs: `_swinging`
    #: answers the dice, the high-crit die and the weapon of record, and
    #: `_wielded` answers proficiency and enhancement. One field, two
    #: readers, because the two already existed.
    #:
    #: Set and cleared around one `use` by `Cast.basic(with_=)`, in a
    #: `finally`, so a swing that raises cannot leave the override
    #: standing for the next one.
    swinging: str = ""
    #: Weapon **groups** whose enhancement bonus counts for an implement
    #: power, when this creature is holding one and no implement.
    #:
    #: *"You can use a longsword as an implement ... it adds its
    #: enhancement bonus to implement attack and damage rolls"* --
    #: `f1128`. Counting as an implement and lending an enhancement are
    #: two printed facts and the card states both, so `counts_as` grants
    #: the first and `counts_as(enhancement=True)` the second: an
    #: implement's enhancement is read off the implement, not off
    #: whatever is standing in for it.
    #:
    #: Opt-in rather than following from `counts_as`, because a row that
    #: only grants the standing-in half would otherwise get the bonus it
    #: does not print.
    #:
    #: The proficiency half of that card needs nothing: `Cast.attack_with`
    #: adds proficiency only for a row carrying `Keyword.WEAPON`, and an
    #: implement power does not, so *"you do not gain its proficiency
    #: bonus"* holds by construction.
    lends_enhancement: set[str] = field(default_factory=set)
    #: This creature's **arena weapons**, by ref.
    #:
    #: `cf:fighter-weaponmaster-f3s0` prints *"you select two weapons as
    #: your arena weapons ... any of your feats that grant feat bonuses to
    #: attack rolls or damage rolls with one of your arena weapons apply to
    #: your other arena weapon as well"*, and the sharing is read by
    #: `Mod.applies` off a substitution `resolve` puts on the context.
    #:
    #: A fact about the character rather than about any feat, for the
    #: reason `counts_as` above is: the feats this widens are written by
    #: other rows and cannot know they are being widened. A tuple rather
    #: than a pair because `Cast.chosen_weapons` answers the whole dealt
    #: hand, which for a fighter is two or three -- the row says so.
    arena: tuple[str, ...] = ()
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
    #: The heaviest armour rung this creature's **class page** allows, as
    #: `armour.LADDER` spells it -- `"plate"`, `"scale"`, `"cloth"`.
    #:
    #: `bands` above is the weapon half of the same question and this is the
    #: armour half, written from `ClassLine.armour` by `chargen.spawn`. It
    #: exists because reading proficiency off `armour` -- what the creature
    #: is *wearing* -- is a documented under-grant in `Cast.grant_armor`,
    #: and for one row it is total: `p16411` prints *"Requirement: You must
    #: not be wearing armor"*, so the worn read always answered `cloth` and
    #: *"choose a type of armor with which you have proficiency"* could
    #: never conjure anything else. It is a theme power, so every class can
    #: take it.
    #:
    #: **Empty means "nobody recorded any", not "proficient with nothing"**
    #: -- `trained`'s convention above, and for the same reason. A monster
    #: has no `Build`, and a board assembled by hand in a probe records
    #: none, so readers fall back to the worn read rather than refusing.
    armour_trained: str = ""
    #: Magic items being worn, by slot. A weapon's own magic is on the
    #: `Weapon` -- it is a longsword with properties -- so this holds the
    #: armour, the neck, and the eight small slots that had nowhere to go.
    worn: dict[str, Magic] = field(default_factory=dict)
    #: Magic ammunition, in the order it is drawn. Not in `worn`, because
    #: a worn item is on the creature for the whole fight and a piece of
    #: ammunition is gone the moment it is loosed.
    quiver: list[Ammo] = field(default_factory=list)
    #: Item refs the creature has **on its person** -- carried, not worn and
    #: not wielded. Potions and the like.
    #:
    #: **A list of refs rather than `Magic` objects, and not in `worn`.**
    #: `worn` is keyed by slot and a slot holds one thing for the whole
    #: fight; a carried item occupies no slot, there can be several of the
    #: same kind, and it is spent rather than taken off. That is `quiver`'s
    #: argument one step more general, and `#877` asked which of the two
    #: shapes this should be -- a refs list or its own component -- and a
    #: refs list is the smaller of them while `Gear` is already where
    #: `quiver` and `thrown_left` live.
    #:
    #: Refs rather than objects because nothing needs the columns yet: the
    #: rows waiting on this ask *whether* a ref is carried -- "you must have
    #: `i390` on your person" is the printed line on three of them -- and a
    #: row that later needs the item's numbers can read them from the
    #: database the way every other item row does.
    #:
    #: **Empty is the honest default and means "carrying nothing"**, not
    #: "untracked" -- unlike `thrown_left` above, where absent has to mean
    #: untracked so a monster is not refused. A monster carries no `Gear` at
    #: all, so it never reaches this either way, and a dealt character
    #: always has the field. Camille's ruling on `#1233`, 2026-11-10:
    #:
    #:   > *"For characters generated automatically, for now let's just give
    #:   > them two random potions of their level or lower. For player
    #:   > generated characters don't do that. We'll actually have item
    #:   > shopping."*
    carried: list[str] = field(default_factory=list)
    #: **How many size categories above its own this creature may wield**,
    #: 0 for everybody by default.
    #:
    #: The glossary says *"Creatures can't use weapons designed for
    #: creatures larger than themselves"*, and `rt:r10-t0` is the printed
    #: exemption: *"You can use weapons of your size or one size larger
    #: than you as if they were your size."* So the waiver is a number of
    #: categories rather than a flag -- the sentence says "one size larger",
    #: and a second row saying "two" would otherwise need a second field.
    #:
    #: Read only by `query.can_wield`. **Correct and inert today**, which is
    #: worth saying rather than finding out later: nothing in this engine
    #: hands anybody a weapon that is not their own size. chargen deals
    #: size-appropriate ones, `loader.spawn` gives a monster no `Weapon` at
    #: all, and `c.pick_up()` does not exist. PHB 220, `#1241`.
    oversized: int = 0
    #: How many copies of a throwable weapon are left, by weapon ref.
    #:
    #: **A dict rather than a field on `Weapon`, deliberately.** `Weapon` is
    #: the dataclass `main`'s docstring records 86 callers for, and the count
    #: is not a property of the kind of weapon -- a dagger is a dagger -- but
    #: of what this creature happens to be carrying. The same argument that
    #: put `stowed` here as a set of refs rather than a flag on each weapon.
    #:
    #: **Absent means untracked, not zero**, which is what keeps a monster
    #: out of this: it carries no `Gear` at all, and `#516` is where its
    #: equipment is owed. `query.ready_to_throw` answers True for a ref that
    #: is not in here, so nothing that was never stocked is refused.
    #:
    #: A count reaching zero does **not** take the weapon out of
    #: `weapons` -- the gate refuses the next throw instead. Removing it
    #: would be the truer picture of a thrown dagger lying across the room,
    #: and `ammunition.hurl` runs when the attack is *declared*, so the
    #: weapon whose dice the fifth throw is about would be gone before it
    #: rolled them. The rules let you pick the thing back up anyway, so a
    #: spent weapon still in hand is the cheaper wrong answer. #520.
    thrown_left: dict[str, int] = field(default_factory=dict)
    #: **Does a thrown weapon come back?** `cf:seeker-f1s1` prints *"when
    #: you make an attack by throwing a weapon with which you have
    #: proficiency, the weapon returns to your hand after the attack"*.
    #:
    #: A flag rather than a move, because this engine never puts a thrown
    #: weapon on the ground: `ammunition.hurl` decrements a **count** and
    #: its own note says *"the weapon stays in hand"*. So "returns to your
    #: hand" is not a journey, it is the throw not being spent -- which is
    #: why the row's old marker reasoned about a facility that moves a
    #: weapon between the ground and a hand and could not find one.
    #:
    #: Read by `ammunition.hurl`, laid by `Cast.returns_to_hand`.
    thrown_returns: bool = False

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
        The assassin prints "simple **one-handed** melee"; `Weapon.hands`
        exists now and the band key below reads it, so a weapon that records
        its grip is covered and one that leaves it `""` is not: the class keeps the
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
            # **A natural weapon is not what gets wielded**, for the same
            # reason an implement is not: it occupies no hand, so choosing
            # it would stow the thing the creature actually carries. A monk
            # listing its own strike first had its greataxe put on the belt
            # -- measured while `Weapon.natural` was added, `#1276`.
            self.wield(next(
                (w for w in self.weapons
                 if w.group != "implement" and not w.natural),
                self.weapons[0],
            ))

    @property
    def held(self) -> list[Weapon]:
        """What is actually in hand right now."""
        return [w for w in self.weapons if w.ref not in self.stowed]

    @property
    def swingable(self) -> list[Weapon]:
        """What is in hand that a swing may actually come through.

        `held` minus `barred`, and the two are different questions on
        purpose: *"you cannot make attacks with the whip"* does not put
        the whip away, so `c.wielding` must keep saying it is in hand and
        the grab it is holding does not end.

        Between `held` and `melee`/`ranged` so that `main`, `off` and
        everything reading those get the answer from one place. Equal to
        `held` for every creature nothing has barred, which is all but one
        feat.
        """
        if not self.barred:
            return self.held
        return [w for w in self.held if w.ref not in self.barred]

    def wield(self, weapon: Weapon) -> None:
        """Take that weapon in hand, putting away whatever cannot share it.

        A two-handed weapon needs both hands, so everything else goes away.
        Otherwise a second one-hander may stay -- which is what a ranger
        fighting with two blades is doing.
        """
        self.stowed.discard(weapon.ref)
        if weapon.two_handed:
            # **A natural weapon is left held even here**, and this is the
            # branch where it matters: stowing it would be permanent -- the
            # set persists, so a monk that took up a greataxe would lose
            # its own strike for good and never get it back on dropping
            # the axe. It costs no hand (`hands_free`) and `melee`
            # withholds it while both hands are full, so holding it is
            # free and correct. `#1276`.
            going = {
                w.ref for w in self.weapons
                if w.ref != weapon.ref and not w.natural
            }
            self._note_sheathed(going)
            self.stowed |= going
            return
        keep = [weapon]
        for other in self.held:
            if other.ref == weapon.ref or other.two_handed or len(keep) >= 2:
                continue
            keep.append(other)
        # **A natural weapon is never stowed**, because it is not a thing
        # that can be put down. It takes no hand either -- see
        # `hands_free` -- so keeping it cannot crowd out a real weapon, and
        # `melee` is what withholds it when both hands are full.
        going = {
            w.ref for w in self.weapons
            if w not in keep and not w.natural
        }
        self._note_sheathed(going)
        self.stowed = going

    def _note_sheathed(self, going: set[str]) -> None:
        """Remember which weapon was put away, if any newly was.

        **Only what is NEWLY stowed**, which is the whole care: `wield`
        rewrites the set every time it is called, so a weapon that was
        already on the belt is in `going` on every later call and would
        keep re-claiming "most recently sheathed" for a creature that
        put nothing away.

        Ties break by ref, so the same hand sheathing two weapons at
        once is reproducible rather than set-ordered -- and no card
        distinguishes them, since both went away in the same motion.
        """
        fresh = sorted(going - self.stowed)
        if fresh:
            self.last_sheathed = fresh[0]

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
        # fire, and that is what it is using. `swingable` rather than
        # `held` for the reason the docstring above gives about `melee`:
        # the two branches must not disagree, and a barred weapon is one
        # `melee` has already dropped.
        firing = [w for w in self.swingable if w.group != "implement"]
        return firing[0] if firing else None

    @property
    def ranged(self) -> Weapon | None:
        """The first weapon that can be fired, if the creature carries one.

        A ranger with a short sword and a longbow has both, and a ranged
        power should be rolling the bow's dice rather than the sword's.
        """
        return next((w for w in self.swingable if w.ranged), None)

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
        swingable = [
            w for w in self.swingable
            if not w.ranged and w.group != "implement"
        ]
        # **A natural weapon needs a hand free**, which is `cf:monk-f1`'s
        # printed refusal: *"you must have a hand free to use your `w3678`,
        # even if you're kicking, kneeing, elbowing, or head-butting."*
        #
        # Here rather than in `query.can_wield`, where the row's own
        # docstring put it, for a measured reason: `can_wield` has **no
        # production caller at all** -- only `drivers` -- so the refusal
        # would have been written and read by nobody, which is this
        # component's signature failure. `melee` is the one door
        # `Gear.main` filters through and 86 callers reach, so a refusal
        # here bites wherever the question is actually asked. `can_wield`
        # carries it too, for whoever wires that up later. `#1276`.
        if self.hands_free < 1:
            return [w for w in swingable if not w.natural]
        return swingable

    @property
    def hands_free(self) -> int:
        """How many hands this creature has nothing in. Two, one, or none.

        **A natural weapon occupies nothing**, because it *is* the hand --
        counting the monk's own strike as a held object would make its
        hands full by carrying itself, and then `melee` above would
        withhold the very weapon the count exists to gate.

        A two-handed weapon takes both; a shield takes one; everything else
        in hand takes one each. Floored at zero rather than going negative,
        because a creature carrying three one-handed weapons is a thing the
        board can produce and "minus one hands free" answers no question.

        Implements are counted: a wizard holding an orb has one hand full,
        which is what `powers/wizard/level_0._sword_hand` has always
        asked by hand and what `cf:wizard-bladesinger-f0` requires.
        """
        taken = 1 if self.shield else 0
        for arm in self.held:
            if arm.natural:
                continue
            taken += 2 if arm.two_handed else 1
        return max(0, 2 - taken)

    @property
    def implement(self) -> Weapon | None:
        """The rod, staff, wand or holy symbol in hand, if there is one.

        Its own property because `main` would answer the wrong thing: an
        implement is not ranged, so it counts as melee, and a cleric
        holding a mace and a symbol has the mace returned. Harmless while
        every implement was a plain one -- and the moment a magic implement
        has an enhancement bonus, that bonus is read off the mace instead.
        """
        born = next((w for w in self.held if w.group == "implement"), None)
        if born is not None:
            return born
        # **A born implement wins, then a weapon serving as one.** The order
        # matters for a creature holding both: a cleric with a mace and a
        # holy symbol should still channel through the symbol. `as_implement`
        # only answers when there is no proper implement in hand, which is
        # the case the printed grant is for. #1009.
        return next((w for w in self.held if w.as_implement), None)

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


#: The hand counts the printed weapon table uses, which are the only words
#: `Weapon.hands` may hold. **Not `off-hand`**: that is a property saying the
#: thing may be held in the off hand, not a count of hands it occupies, and
#: reading it as one would make a dagger answer a Requirement about grip.
_HAND_COUNTS = ("two-handed", "one-handed", "double")


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
    #: **Which size of wielder this weapon was made for.** The printed
    #: default, said by the glossary's first sentence: *"The weapon tables
    #: assume a Medium wielder, which includes almost all player
    #: characters."* So every row the `weapon` table supplies is Medium, and
    #: a larger or smaller one is a thing somebody made or took.
    #:
    #: Here rather than derived, because it is not derivable: a Large
    #: longsword and a Medium one are the same printed row with a different
    #: damage die, and nothing in `game.db` distinguishes them.
    #:
    #: Read by `query.can_wield`, which is where the glossary's refusals
    #: live. PHB 220, *Weapons and Size*. `#1241`.
    size: Size = Size.MEDIUM
    #: **Is this the creature's own body rather than a thing it carries?**
    #: `cf:monk-f1` prints *"when you make a weapon attack such as a melee
    #: basic attack, you can use `w3678`, which is a weapon in the unarmed
    #: weapon group ... You must have a hand free to use your `w3678`, even
    #: if you're kicking, kneeing, elbowing, or head-butting."*
    #:
    #: **The group cannot carry this**, which is what the row's marker got
    #: wrong when it asked the ETL for a citation: `w3635` and `w3724` are
    #: unarmed-group weapons a character **buys and holds**, so refusing
    #: the group for a full hand would refuse those wrongly. The question
    #: is about one weapon, and this is the field that answers it.
    #:
    #: Two readers, and both fall out of the same fact. `Gear.hands_free`
    #: does not count a natural weapon as occupying a hand -- it *is* the
    #: hand -- and `Gear.melee` withholds one when no hand is free, which
    #: is the printed refusal. `query.can_wield` carries it too, for the
    #: callers that ask before a thing is picked up.
    #:
    #: Set by `chargen` on the monk's strike, not by the ETL: `game.db` has
    #: no column for it and the compendium's own `x_m6475a0` is a glossary
    #: ref with no table behind it. `#1276`.
    natural: bool = False
    #: **May this implement lend its enhancement to a natural weapon?**
    #: One printed family of implements does -- `i1775` and its scaling
    #: rows -- and `cf:monk-f1` prints the sentence from the other side.
    #:
    #: A flag rather than a test on the implement's slug or name, for two
    #: reasons. `engine` must not name a printed item, which is the one
    #: rule; and `engine` must not import `chargen`, which is a contract
    #: `.importlinter` holds at zero. So the fact is declared where it is
    #: known -- `chargen.KI_FOCUS` -- and read here, which is the same
    #: arrangement `natural` above has. `#1276`.
    lends_natural: bool = False
    properties: frozenset[str] = frozenset()
    #: Who granted each property that a row laid, by word -> the refs that
    #: granted it. Empty for a weapon's **printed** properties, which
    #: nobody granted and nobody may take away.
    #:
    #: **Two grants of one word cannot otherwise be told apart**, and that
    #: is a row silently breaking another row. `i2478p1` silvers the
    #: weapons of everybody in its light and strips the word when they
    #: leave; `i1764x1` silvers a weapon standing. Without a count per
    #: source, the light going out clears the standing grant -- a correct
    #: reading of one card breaking another.
    #:
    #: `i2478p1` had worked around it by recording which weapons did not
    #: already carry the word, and its own note says why that is not
    #: enough: two lights over one ally means the second records nothing,
    #: so the first to end strips a word the second is still paying for.
    #: That bookkeeping cannot live in a row, because the other source is
    #: another row's closure.
    #:
    #: Written by `Cast.gains_property` and read by
    #: `Cast.loses_property(mine_only=True)`. A `frozenset` of refs rather
    #: than a count, so laying the same word twice from one row is
    #: idempotent -- the same reason `gains_property`'s blanket unions
    #: into a set.
    granted_by: dict[str, frozenset[str]] = field(default_factory=dict)
    #: A magic weapon's enhancement bonus, which adds to its attack and its
    #: damage. Zero is a plain weapon, and everything `chargen` hands out is
    #: plain -- the number is here so that the rows that *reduce* it have
    #: something to reduce, and so that a weapon with one runs hotter.
    enhancement: int = 0
    #: An **explicit** critical-hit die, for a weapon whose card prints one
    #: rather than carrying the printed "high crit" property.
    #:
    #: `cast._high_crit_dice` pays `damage` for a high-crit weapon -- one
    #: extra `[W]`, which is what the 18 printed ones get. A conjured
    #: weapon is the other shape: `p15895` prints *"+1 enhancement bonus
    #: ... and it deals 1d8 extra damage on a critical hit"*, a die of its
    #: own and not its damage die, so there was nowhere to put it.
    #:
    #: `Mods` was the obvious home and cannot be: its values are `int` and
    #: this is a dice expression.
    #:
    #: **`repr=False`, following `Swung`'s own argument.** `replay`'s
    #: fixtures record `str(event)` and `Event.wire` drops un-repr'd
    #: fields, so a declared-but-unrepr'd field stays out of the
    #: regression net and off the wire. No fixture carries a `Weapon`
    #: repr today -- measured, 0 of 8 -- and this keeps that true whatever
    #: starts carrying one.
    crit: str = field(default="", repr=False)
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
    #: **Also serving as an implement, while staying the weapon it is.**
    #:
    #: A role, not a kind, which is why it is separate from `group`.
    #: `c.as_implement` answered the printed grant *"you can use this weapon
    #: as an implement"* by **overwriting** `group` with `"implement"` and
    #: pushing the real group into `properties` -- so the sword stopped
    #: being a sword. `Gear.main` skips implements, correctly and for a
    #: documented reason, so the holder could no longer make a melee basic
    #: attack at all: `usable` refused `mba` and `Cast.basic` returned False
    #: before it rolled, silently.
    #:
    #: Measured across 225 dealt characters -- every class, levels 1, 5 and
    #: 10, three seeds -- **32 (14.2%) had lost their weapon that way**,
    #: among them a fighter and a barbarian. A separate 18 hold nothing but
    #: a born implement, which is the case `Gear.main`'s note is about and
    #: is right.
    #:
    #: So `group` stays the printed group for ever, and the sites asking
    #: "can this be swung" (`group != "implement"`) go on being correct
    #: untouched. The ones asking "does this serve as an implement" read
    #: `group == "implement" or as_implement`. #1009.
    as_implement: bool = False

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

    def __post_init__(self) -> None:
        """Keep `hands` and `properties` saying the same thing.

        **One fact lived in two fields and neither was on every object.**
        `etl`'s `_printed_weapons` fills both -- `hands=row["hands"]` and
        `properties` carrying the same word -- while the 38 hand-written
        constants in `chargen` took the default, and 8 of them put the fact
        in `properties` only. So a row asking how many hands a weapon takes
        got a different answer depending on where the weapon came from, and
        both live readers were reading the field their own docstring names:

        * `Gear.suits`, which only adds `f"{cat}:{hands} melee"` to the
          match set `if arm.hands`. With `hands == ''` a printed Requirement
          naming a hand count -- the assassin's "simple one-handed melee" --
          **could not be satisfied by any of the 19**, and those are the
          weapons a low-level board deals;
        * `content/feats/exploits.f978`, which asks `w.hands == "double"`.

        Derived here rather than taught to each reader, which is the fix
        #562 argues for: two more sites to keep in step is how this got hard
        to see in the first place. Both directions, so neither spelling can
        drift from the other again -- and `off-hand` is deliberately not in
        the vocabulary. It is a *property* ("may be held in the off hand"),
        not a hand count, and 3 constants carry it beside nothing else.
        """
        if not self.hands:
            for word in _HAND_COUNTS:
                if word in self.properties:
                    self.hands = word
                    break
        elif self.hands.lower() not in self.properties:
            self.properties = self.properties | {self.hands.lower()}



#: The total a hidden creature rolled on the Stealth check that hid it, kept
#: on `Powers.charges`. `#1088`.
#:
#: **Remembered rather than re-rolled, because the page says so**:
#:
#:   > "If an enemy makes an active Perception check and beats your Stealth
#:   > check result (**don't make a new check**), you don't remain hidden
#:   > from that enemy."
#:
#: So a spot is opposed by the number the hider actually rolled, and there
#: is nowhere else that number survives -- `Cast.check` answers whether a DC
#: was beaten, not by how much.
#:
#: On `charges` for the reason `actions.FEINT_USE` gives: per-encounter
#: bookkeeping that belongs to a printed action rather than to a row. It is
#: cleared by both rests with the rest of `charges`, and by `Cast.unhide`,
#: so a stale number cannot oppose a later hide.
#:
#: **Here and not in `actions.py`.** `FEINT_USE` is written and read in
#: `actions`; this is written in `cast` and read in `actions`, and `actions`
#: already imports `cast` function-locally to dodge a cycle. `components` is
#: below both.
STEALTH_RESULT = "stealth:result"


def weapon_from_printed(ref: str, **over: Any) -> Weapon | None:
    """A `Weapon` off the printed table, or `None` if the table has no row.

    **The one mapper, because the mapping is not the table.**
    `combat_engine.weapons` holds the columns and sits below every
    component -- it must not import the engine, or it would stop being a
    table -- so turning a row into a `Weapon` happens here, at the lowest
    layer that knows what a `Weapon` is. Two callers:
    `chargen._printed_weapons` for everything a character can be dealt,
    and `Cast.as_weapon(base=)` for a card that changes an item's shape.

    Before this, the mapping lived in `chargen` and so did the read. That
    was right while `chargen` was the only reader and became the `#852`
    situation the moment the kernel wanted it: `engine -> chargen` is
    contractually **zero** with no `ignore_imports`, so a verb in
    `cast.py` could reach these columns neither by importing chargen nor
    by reading the table a second time.

    `over` sets fields the table is not the authority on -- `enhancement`
    and `item` are per-character, which is why `chargen._FROM_TABLE`
    names them as deliberate exclusions.
    """
    from combat_engine import weapons

    row = weapons.printed().get(ref)
    if row is None:
        return None
    return Weapon(
        ref=row.ref,
        slug=row.slug,
        category=row.category,
        hands=row.hands,
        damage=row.damage,
        proficiency=row.proficiency,
        reach=row.reach,
        ranged=row.ranged,
        thrown=row.thrown,
        group=row.group,
        properties=row.properties,
        **over,
    )
