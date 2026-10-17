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

import re
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Any

from .components import Gear, Health, Mod, Mods, Position, Stats
from .durations import Effect, When
from .events import Aided, Boosted, Event, ItemPowerUsed, Note, PowerUsed
from .grid import Square, spread
from .grid import distance as _distance
from .movement import forced, shift, teleport, walk
from .query import (
    UNLIMITED_SENSE,
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
    DEFENCES,
    Ability,
    ActionType,
    Condition,
    DamageType,
    Defense,
    Forced,
    Keyword,
    Light,
    Relation,
    Size,
    Team,
    Usage,
    Window,
)

if TYPE_CHECKING:
    from .components import Weapon
    from .dsl import Damage, Power, Range
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


#: The hold that waives the printed size rule on a basic manoeuvre. Two
#: feats grant it and `Cast._manoeuvrable` is the one reader.
_ANY_SIZE = "manoeuvre:any-size"

#: The ref a bull rush is keyed on -- what `perform` builds its `Cast` with,
#: what `c.extend_move` lengthens and what `c.pre_empt` replaces a clause of.
#: A manoeuvre is an action kind and not a row, so it has no declared ref and
#: this is the one it borrows.
#: The size of the bonus an aid action hands the ally. Read through
#: `Cast.amount_for`, because seven rows raise it off the printed 2 and the
#: number was written inside `aid_attack` where none of them could reach.
MANOEUVRE_AID = "manoeuvre:aid"
#: A distance stretched for **every move of a kind**, rather than for one
#: named row -- "one extra square on every shift", "one more square on
#: every swordmage teleport you make". Eight rows print that sentence.
#:
#: `c.extend_move` has always keyed on a row's ref, which is right for "a
#: named row moves you further" and cannot say "any of them": twelve rows
#: between two symbols wanted the kind instead, and `f1393`'s note said so
#: -- "both are distances a row names when it moves you; nothing lengthens
#: one from the outside".
#:
#: Stored in the same `Powers.extra_squares` under a reserved key, so the
#: gates, the durations and `squares_for` all work unchanged -- the same
#: arrangement `manoeuvre:` above uses for a number nobody could reach.
MOVE_KIND = "move:"
#: The bonus to the *check* an aid another action rolls, as against the bonus
#: it hands out. Two different numbers on two cards that print both of them
#: in one sentence -- "a +5 bonus to checks you make to aid another. When you
#: succeed ... you grant a +3 bonus instead of a +2" -- so one symbol serving
#: the pair could not go green for either.
AID_CHECK = "manoeuvre:aid-check"
#: A bonus to checks made to aid **this** creature, which is the mirror of
#: `AID_CHECK` and belongs to the one being helped. Read with
#: `Cast.amount_for(..., who=ally)`, because the aider is the caster and this
#: number is not its own.
AID_RECEIVED = "manoeuvre:aid-check-received"
MANOEUVRE_BULL_RUSH = "manoeuvre:bull_rush"
#: How far the attacker follows a bull rush, as against how far the target
#: goes. A separate symbol from `MANOEUVRE_BULL_RUSH` because the printed
#: clauses come apart: a belt lengthens the push and says nothing about the
#: shift, while p14383 lengthens both. One symbol serving the two made the
#: belt walk the attacker three squares for free.
MANOEUVRE_BULL_RUSH_FOLLOW = "manoeuvre:bull_rush-follow"
#: The attack-roll bonus on a swing **this creature made somebody else
#: take**. Read off the granter in `c.grant_attack`, never off the swinger:
#: the card is "when one of *your* powers forces a creature to make an
#: attack", so the bonus is the granter's to hand out, exactly as the extra
#: squares of a push belong to the pusher.
#:
#: A rider rather than a parameter on every granting row, because the cards
#: printing it name a **class** of powers -- "one of your arcane enchantment
#: powers" -- and there is no finite list of bodies to edit. The same
#: argument `c.extend_every` settled for forced movement, and it is the
#: documented exception in `content/CLAUDE.md` to writing a clause into the
#: power it names.
MANOEUVRE_GRANTED_ATTACK = "manoeuvre:granted-attack"


#: **Keys whose one-shot is correctly spent by the attack roll**, because
#: each is *consulted before* it: `attack` at the roll itself, and `range`
#: and `reach` when `dsl._reach_of` decides what may be reached, which is
#: aiming and happens first. So the roll is the moment after which the hold
#: has been used, which is exactly what `once=` means.
#:
#: Written down rather than left as an `else`, because the `else` is what
#: silently mis-spent every key nobody had thought of -- five times. A key
#: added here needs one sentence saying where it is read; a key that has no
#: such moment belongs in the refusal below, not here.
#:
#: `ignore_cover` and `no_cover` are read by `query.cover_waived`, which
#: `resolve.attack` calls at line 167 while gathering the situational
#: modifiers -- so before the roll, like the two above.
#:
#: **Those two were missed on the first pass and four rows raised for it.**
#: They are never written as `c.bonus("ignore_cover", once=True)`; they
#: arrive through `c.ignore_cover(once=...)`, which forwards to `bonus`.
#: `audit.py --calls 'c.bonus('` cannot see that -- it finds rows naming
#: the verb, not rows reaching it through a helper -- and the commit that
#: introduced this refusal said so in as many words before shipping the
#: thing it warned about. The pre-push wide sweep is what caught it, which
#: is the whole argument for paying for one.
_SPENT_ON_ATTACK = frozenset({
    "attack", "range", "reach", "ignore_cover", "no_cover",
})


#: Every word a fight's place may be described by. **Closed**, and
#: `c.terrain` refuses anything else -- `c.bonus(once=)`'s discipline,
#: for the reason #544 records: five keys were silently mis-spent
#: because nothing checked them.
#:
#: It is closed because the vocabulary had already drifted. Re-derived
#: across 61 calls in 50 rows:
#:
#:     24 aquatic   17 sunlight   6 water     3 darkness
#:      2 dim light  2 ice        2 snow      1 moonlight
#:      1 starlight  1 icy        1 bright    1 forest
#:
#: `water` and `aquatic` are the same question asked two ways, and so
#: are `ice` and `icy`. Nothing noticed, because `World.terrain` is
#: empty and **every** one of these gates is False in every fight
#: (#539) -- so a row asking for a word no board would ever carry read
#: exactly like a row asking for the right one. Two bugs stacked, and
#: the outer one hid the inner.
#:
#: The light words are **not** merged. `bright`, `dim light` and
#: `darkness` are the three printed light levels and `sunlight`,
#: `moonlight` and `starlight` are sources; a creature burned by
#: daylight is not one hindered by gloom. This set exists to catch a
#: synonym and a typo, not to re-design the vocabulary.
TERRAIN_WORDS = frozenset({
    "aquatic", "ice", "snow", "forest",
    "bright", "dim light", "darkness",
    "sunlight", "moonlight", "starlight",
})

#: What sort of going a square is, which `Grid.difficult` holds one of per
#: square. A **closed set for the same reason `TERRAIN_WORDS` is**: `kind=`
#: took any string, and 29 calls across the tree named a word no square ever
#: carries -- `mud` eight times, `blood` three, `snow` two -- so each waived
#: nothing while reading exactly like a working row. #598.
#:
#: **Five of these are the only words anything writes today**: `forest`,
#: `ice`, `rubble`, `water` and `web`, all through `c.zone(difficult=)`. The
#: rest are words the *cards* print, and a waiver naming one is a correct
#: clause waiting for a map that makes that ground -- which is a different
#: thing from a typo, and the whole point of listing both. `scripts/lint.py`
#: reports which are unwritten so the distinction stays visible instead of
#: becoming a silent allowance.
#:
#: `shallow water` is kept apart from `water` deliberately. There is no deep
#: water label, so aliasing them would make six rows waive the only water the
#: grid has -- possibly right, and `m5808a0`'s rule says err the other way: a
#: row stronger than its card is worse than one weaker.
#:
#: **A ref is also a label, and that is not a loophole.** Twelve rows do
#: `c.zone(difficult=c.ref)` and then `c.ignores_difficult(c.ref)`, which is
#: how "difficult terrain for all creatures except you" is said: labelling
#: the squares with the row's own ref scopes the exemption to *this* zone,
#: where a word would waive every patch of the same going on the board and
#: `difficult=True` would slow the caster too. `p15852`'s docstring states
#: the idiom. A closed set of words would have refused all twelve, and the
#: first draft of this one did -- so `_is_terrain_label` accepts a
#: ref-shaped string as well.
DIFFICULT_LABELS = frozenset({
    # written by `c.zone(difficult=)` today
    "forest", "ice", "rubble", "water", "web",
    # **Printed by cards, written by nothing yet.** Six content files feed
    # these through a tuple in a `for` loop rather than one call per word --
    # `("rubble", "uneven stone", "earthen construction")` is one printed
    # line said three ways -- which is why no static census found them and
    # why the raise did. #598's own table listed ten of these; there are
    # seventeen.
    "blood", "debris", "dirt", "earth", "earthen construction", "mud",
    "natural growth", "plants", "sand", "shallow water", "silt", "snow",
    "stone", "trees", "underbrush", "uneven stone", "vehicle",
})

#: The shapes a ref takes, for `_is_terrain_label`. The same alternation
#: `lint._REF_SHAPE` uses, kept here rather than imported because `engine/`
#: must not reach into `scripts/`.
_REF_LABEL = re.compile(
    r"\A(?:p\d+|m\d+(?:c\d+)?a\d+|i\d+[px]\d+|f\d+[a-z]?"
    r"|cf:[\w-]+|rt:[\w-]+)\Z"
)


def _is_terrain_label(word: str) -> bool:
    """Could any square carry this label?

    A printed sort of going from `DIFFICULT_LABELS`, or a **ref** -- which
    is the per-zone idiom described above and is minted per row, so no set
    could list them.
    """
    return word in DIFFICULT_LABELS or bool(_REF_LABEL.match(word))


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
    #: Which registered substitution this use picked. 0 is the card as
    #: printed, which is what every use has unless a feat has registered a
    #: `c.pre_empt` against this row *and* the menu entry for it was the one
    #: taken. 1-based into `Powers.pre_empts` flattened for this ref, in the
    #: order `c.substitutions` lists them.
    #:
    #: Settled by `dsl.use` from the chosen `Action`, like `branch` and
    #: `augment` and for the same reason: a substitution has to be
    #: clickable and scoreable, which a question asked halfway through a
    #: body is not. A body never compares this directly -- `c.instead_of`
    #: is the read.
    variant: int = 0
    #: Which feat of each bracketed category this use is applying, by
    #: category. Written by `c.declare` and read by nothing else -- see
    #: there for why the answer is settled once per use rather than once
    #: per target or once per clause.
    declared_feats: dict[str, str] = field(default_factory=dict)

    @property
    def attack_mod(self) -> int:
        """The modifier of whatever ability *this branch* attacks with.

        A weapon power's damage line is "<the attack ability> modifier
        damage", and on a two-branch row that is Strength in melee and
        Dexterity at range. Writing `c.dex_mod` in the body hard-codes one
        half of a row that has two.

        **Resolved through `ability_for`, never read off the header.** A
        theme's line names a `Pick` rather than an ability, and handing one
        to `Stats.mod` is not an error -- `scores.get` misses, returns the
        default 10, and the modifier comes back 0. Every such row would
        have quietly dealt its weapon dice and nothing else.
        """
        p = self._declared()
        line = p.attack_of(self.branch) if p else None
        if line is None or line.ability is None:
            return 0
        return self.stats.mod(line.ability_for(self.world, self.me, self.ref))

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

        **Only an immediate interrupt may stop an *attack*, and that is now
        enforced.** The printed rule is about attacks specifically, which is
        narrower than the way this docstring used to state it and is why the
        wholesale version could not be enforced: 6 rows cancel from a
        non-interrupt window and every one of them refuses forced movement,
        a move, or damage -- things a reaction or a free action legitimately
        undoes ("you ignore the triggering forced movement", "you take half
        damage from the triggering attack").

        Measured over every row in the tree that calls this, by what it
        refuses:

            ForcedMove     15 interrupt  + 2 free + 1 reaction
            MoveStart       4 interrupt  + 1 opportunity + 1 reaction
            DamageRolled    2 interrupt  + 1 free
            AttackDeclared  4 interrupt
            AttackRolled    2 interrupt
            Hit             7 interrupt

        **Every row refusing an attack event is already an interrupt, 13 of
        13.** So #444's worry that "a shipped row depends on the gap" is true
        of the wholesale rule and false of the printed one -- nothing in the
        tree changes behaviour, and the next row that gets it wrong is caught
        instead of working by accident.

        Most events cannot be refused at all -- `cancel` lives on `Decision`,
        and `ConditionApplied`, `Moved` and `DamageApplied` are plain
        announcements of something that has already happened. `Dropped` is one
        of those and should not be: "when reduced to 0 hit points (immediate
        interrupt): the triggering attack misses" names it and cannot be
        declared on it -- #445. Asking anyway used to raise `AttributeError`
        from inside the row, which reads as a bug in the content; it is a fact
        about the event.

        Returns whether anything was actually stopped: False both for an event
        that cannot be refused and for a window that is not allowed to refuse
        this one.
        """
        stop = getattr(self.trigger, "cancel", None)
        if stop is None:
            return False
        if self._refusing_an_attack() and not self._declared_as_interrupt():
            return False
        stop()
        return True

    #: Refusing one of these *is* refusing the attack, which the printed rule
    #: reserves to an immediate interrupt. `DamageRolled` is deliberately not
    #: here: a card reading "you take half damage from the triggering attack"
    #: is a free action in the book and refuses the damage, not the swing.
    _ATTACK_DECISIONS = ("AttackDeclared", "AttackRolled", "Hit", "Miss")

    def _refusing_an_attack(self) -> bool:
        return type(self.trigger).__name__ in self._ATTACK_DECISIONS

    def _declared_as_interrupt(self) -> bool:
        """Whether this row's card prints an immediate interrupt.

        The **declared** action rather than the bus window, because the
        printed rule is about what kind of action the card is, and that is
        what an author writes and a reader checks. A row whose action cannot
        be read -- no registry entry -- is allowed through: refusing on
        missing information would turn an unrelated gap into a silently
        dead clause, which is the failure this component produces most.
        """
        from .dsl import get

        p = get(self.ref)
        action = getattr(p, "action", None) if p is not None else None
        return action is None or action is ActionType.IMMEDIATE_INTERRUPT

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

    def flurry_of_blows(self, *, on: int | None = None) -> str:
        """Which flurry of blows **this** monk has, as a ref. Empty for anyone else.

        Six rows print "your flurry of blows power" and mean whichever one the
        monk's tradition granted -- there are five, one per tradition, and a row
        naming any single ref would be right for a fifth of the monks who hold it.
        Camille's call on #277 was a verb per family rather than a general
        "the row this feature granted me", and this is the monk's.

        **Derived, not tabulated.** The five share a signature no other row has:
        a monk row at level 0, at-will, `action=NONE`, with the psionic keyword --
        checked, and it matches exactly those five out of the whole registry. A
        hardcoded tuple of refs would have been an `engine` -> `content` leak and
        a list to maintain; this is a query over the registry, which `dsl` owns.

        Returns the one the creature actually holds, so a row can watch it, spend
        it, or hand back a use. Empty string rather than None, because every
        caller feeds it to something that takes a ref.
        """
        from .components import Powers
        from .dsl import REGISTRY
        from .types import Keyword as _Kw
        from .types import Usage as _Usage

        known = self.world.get(self._who(on) if on is not None else self.me, Powers)
        if known is None:
            return ""
        for ref in known.all:
            declared = REGISTRY.get(ref)
            if (declared is not None
                    and declared.cls == "monk"
                    and declared.level == 0
                    and declared.usage is _Usage.AT_WILL
                    and declared.action is ActionType.NONE
                    # **The header on purpose, not `keywords_of`.** This is
                    # identifying *which* row in the loadout is the monk's
                    # at-will, by the shape it was declared with. A keyword
                    # a feat granted to some other row must not make that
                    # row answer to this search.
                    and _Kw.PSIONIC in declared.keywords):
                return ref
        return ""

    def reach(self, ref: str = "", *, on: int | None = None) -> int:
        """How far this creature's melee attacks carry, in squares.

        **"Within your melee reach" is a printed phrase and no row could ask for
        it.** A card reading "if an enemy is now within your melee reach" had to
        hard-code 1, so the row played short for anybody holding a glaive --
        `c.strike` validates against the true reach, but the row gathering
        candidates could not find the enemy two squares away to offer it. #294.

        The same arithmetic `dsl._reach_of` does, and deliberately *that*
        function rather than a copy: a weapon row's reach is the wielded
        weapon's plus whatever the card grants, a fixed "Melee 5" row's is the
        number it prints, and which of the two applies is `BY_WEAPON`'s answer.
        Two copies of that rule would be one too many.

        Defaults to the row being cast, which is the common case; naming another
        ref answers for that row instead -- the same shape `c.ability_for` and
        `c.weapon_dice` take, and what "the reach of the power you are about to
        grant" needs.

        A ranged row answers its range, because `_reach_of` does; a row that
        reaches nowhere answers 1, which is what a fist reaches.
        """
        from .dsl import REGISTRY, _reach_of

        who = self.me if on is None else on
        want = ref or self.ref
        declared = REGISTRY.get(want)
        if declared is None:
            return 1
        return _reach_of(self.world, who, declared.reach_of(self.branch), want)

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

    def fallen(
        self, radius: int = 99, *, side: str = "any", kind: str = ""
    ) -> list[int]:
        """The corpses within `radius`. `c.within` can never return one.

        Every creature-finding verb here ends in `alive(...)`, which is
        right for the hundreds of rows that mean a living target and wrong
        for the four that print "one destroyed undead creature". So those
        four read "the board has no way to name a corpse" and three of them
        were marked `query.dead_allies()` and dropped -- while the fourth,
        `m135a3`, hand-rolled the same comprehension and worked. The gap was
        never in the board; `_die` keeps the body an entity and its
        `Position`, and only lifts it off the grid. It was in the vocabulary.

        **`side="enemy"` cannot see a corpse**, and that is `query.enemies`
        filtering the dead where `query.allies` does not. No printed card
        asks for one -- a raiser raises its own side, or says nothing about
        sides at all, which is `"any"` -- so this is documented rather than
        papered over. Changing `enemies` to match would move hundreds of
        live rows for the sake of none.

        The printed restrictions a card puts *on top* of this -- "of level 6
        or lower", "minion" -- stay in the row, which is where every other
        level and minion test in the tree already lives.
        """
        pool = self._side(side, self.me)
        return [
            e
            for e in pool
            if not alive(self.world, e)
            and distance_between(self.world, self.me, e) <= radius
            and (not kind or self.is_kind(kind, on=e))
        ]

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

    def race_of(self, on: int | None = None) -> str:
        """A character's race, by ref -- `c.race_of(on=ally) == "r4"`.

        The question `c.is_kind("<a race word>")` was being asked instead, and
        a character has no type line, so those gates were False for every PC
        in the game (#411). A monster of that race *does* carry the word, so a
        row that means either asks both.

        A ref, never a word: `kinds_of` answers *origin* -- fey, shadow,
        immortal -- which 21 races share with each other and with every fey
        creature on the board, so it cannot tell r3 from r4. Delegates to
        `query.race_of`, which reads the `race:<ref>` that `Build.choices` has
        carried all along.
        """
        from .query import race_of

        who = self._who(on)
        return "" if who is None else race_of(self.world, who)

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
        # **Lifted into `query` so `dsl.candidates` can ask it too**, and
        # delegated rather than duplicated: a target line narrowing to "each
        # undead creature" is a filter on the pool, and two copies of this would
        # be the `candidates`/`use` disagreement of #381 in a third place. #401.
        from .query import kinds_of

        return kinds_of(self.world, who)

    def _stat_block(self, who: int | None) -> dict[str, Any]:
        """The compendium row behind a creature, or `{}` if it has none.

        **One of the engine's reaches into `content`, and now it is not.** This
        read the loader directly and `query.standoff` had a byte-identical copy,
        so the seam `engine/CLAUDE.md` counts had two sites doing one thing.
        Both go through `query.stat_block`, which takes the count from five to
        four.
        """
        if who is None:
            return {}
        from .query import stat_block

        return stat_block(self.world, who)

    def is_kind(self, word: str, on: int | None = None) -> bool:
        """Is this creature of that type? `c.is_kind("undead")`."""
        return word.lower() in self.kinds_of(on)

    def living(self, on: int | None = None) -> bool:
        """Is this a living creature? `query.living`, defaulting to the target.

        Ten rows print it as a restriction and every one of them means "not
        undead" -- so this is not a new type word, it is the read the tree
        was already spelling by hand.

        **Defaults to the target**, like almost everything here, because
        every printed use is about who the power lands on: "one living
        creature", "a bloodied, living enemy". Pass `on=c.me` for the rare
        row asking about its own caster.

        The two races printing "both living and undead" are why this is a
        function rather than `not c.is_kind("undead")` -- see
        `query.living`.
        """
        from .query import living

        return living(self.world, self._who(on))

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
        # **The ref leads the label**, because that is the convention
        # `audit._claimed` credits by: an `EffectApplied` counts for a row only
        # if its label *starts with* that row's ref. `origin:fey` does not, so
        # a row whose whole content is this verb laid a real effect and still
        # reported SILENT -- 17 of them in the recorded baseline. #374.
        #
        # `query.kinds_of` reads the word back by searching for the marker
        # rather than anchoring at the start, and checks `unorigin:` first
        # because `origin:` is a substring of it.
        if instead_of:
            held = self.world.effects.apply(
                who, self.me, until,
                label=f"{self.ref} unorigin:{instead_of.strip().lower()}",
                by=self.ref,
            )
        for word in words:
            held = self.world.effects.apply(
                who, self.me, until,
                label=f"{self.ref} origin:{word.strip().lower()}",
                by=self.ref,
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

    def declare(self, category: str, *feats: str) -> str:
        """Which feat of one printed category applies to **this use**.

        The compendium prints a feat's category in brackets after its name
        and the rule is one feat per category per use of a power:
        `[Arena Fighting]` says "you can take any number but you can use
        only one at a time", the style families say "any single attack can
        benefit from only one lesser style feat and one greater style
        feat". #550 writes those clauses into the power's body, so this is
        where the one is picked.

        Returns the chosen ref, or `""` when the character holds none of
        them. A body reads it as `if picked == "f972":` rather than asking
        `c.feat` again -- that is the whole point, because `c.feat` is true
        for every feat held and cannot say which one is being applied.

        **Called before the attack, and the rule is in the printed text:**
        *"if multiple lesser style feats or greater style feats can affect
        an attack, you must declare which of each type you are using
        before making the attack."* So the declaration must not consult the
        outcome -- a character who declares a critical-hit feat and then
        does not crit gets nothing, rather than falling through to the next
        branch. The `if`/`elif` chains written before this verb existed did
        fall through, which was more generous than the card.

        **Settled once per use, not per target or per clause.** The memo
        lives on this `Cast` and `dsl.use` builds exactly one per use, so a
        row that calls this from a body running once per target asks the
        player once and every target honours the same answer. That is the
        unit the rule names -- "a single application of a power".

        A real choice when more than one is held, through `c.choose`, so
        the printed "you must declare" is a decision and not a preference
        baked into the order the clauses happen to be written in. With one
        held there is nothing to ask.

        **The category is a rules word, not a printed name.** `leaks.py`
        has no objection to `"Arena Fighting"`: it is the bracket the page
        prints over a whole family, the same kind of vocabulary as a
        keyword, and it is a column in `game.db` since #557.
        """
        if category in self.declared_feats:
            return self.declared_feats[category]
        held = [f for f in feats if self.feat(f)]
        picked = held[0] if len(held) == 1 else (
            self.choose(held, f"{self.ref}: which {category} feat applies")
            or "" if held else ""
        )
        self.declared_feats[category] = picked or ""
        return self.declared_feats[category]

    @property
    def primary(self) -> Ability:
        """The ability this character's class attacks with.

        "A bonus equal to your **primary ability** modifier" is a printed
        phrase in its own right, on rows with no attack line for
        `ability_for` to read -- a saving throw, a number of squares. Those
        were standing in with the largest modifier on the sheet, which is a
        different sentence and is only accidentally the same number.
        """
        from .dsl import Attack, Pick

        return Attack(Pick.PRIMARY).ability_for(self.world, self.me)

    @property
    def primary_mod(self) -> int:
        """The modifier of `c.primary`. What the printed phrase means."""
        return self.stats.mod(self.primary)

    def ability_for(self, ref: str = "", *, on: int | None = None) -> Ability:
        """Which ability a row's attack line rolls, for this creature.

        The header answers this on its own when the line names an ability.
        This is for a **body** that needs the same answer -- a damage line
        reading "+ your primary ability modifier", or a row whose rider
        applies only when it rolled one particular ability.

        Defaults to this row, which is the common case; naming another ref
        answers for that row instead, which is what "the ability your
        *other* power rolls" wants. A row with no attack line at all falls
        back to the best modifier on the sheet, the same way `Pick.PRIMARY`
        does for a creature with no build -- an answer rather than a raise,
        because a body asking this is about to do arithmetic with it.
        """
        from .dsl import REGISTRY, Attack, Pick

        who = self.me if on is None else on
        declared = REGISTRY.get(ref or self.ref)
        line = getattr(declared, "attack", None)
        if line is None:
            line = Attack(Pick.HIGHEST)
        if line.printed is not None:
            # A stat block's finished total names no ability to return.
            line = Attack(Pick.HIGHEST)
        return line.ability_for(self.world, who, ref or self.ref)

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
            # **Find the effect this save is against, so its keywords are
            # the laying row's.** `against` is a label, and for a burn that
            # label is the printed amount -- so asking `keywords_of(label)`
            # answered nothing. The effect carries `by`; matching it back by
            # label is what gets hold of it. #580
            held = next(
                (e for e in self.world.effects.of(who) if e.label == label),
                None,
            )
            plus = bonus + self.total(
                "save", who, {"actor": who, "label": label,
                              "conditions": frozenset(), "ongoing": False,
                              "dtype": None,
                              "keywords": keywords_of(held or label)}
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

    def worsen(self, eff: Effect, cond: Condition) -> bool:
        """"First Failed Saving Throw: the target is **also** dazed (save ends
        both)" -- add a condition to a hold that is already standing.

        One effect carrying two conditions, which is what makes one save end
        both: a second save-ends effect laid beside it would hand the victim a
        second saving throw against one printed sentence.

        **Not `eff.conditions = (*eff.conditions, cond)`.** That is the obvious
        way and it is silently false: `Effects.end` reads the mutated tuple so
        teardown works, but nothing fills the `Conditions` cache that every
        `query.is_` reads -- so the hold says "dazed" and the creature says it
        is not. See `Effects.worsen` for the three steps. #367.

        `escalate=` on the effect is how "each failed saving throw" gets here.
        Returns False when the condition was already on, so a second failed save
        does not double it.
        """
        return self.world.effects.worsen(eff, cond, source=self.me)

    def reroll_save(
        self, *, bonus: int = 0, keep: str = "new", ev: Any = None
    ) -> bool:
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

        `ev=` names the throw when it is not the trigger, for
        `c.reroll_attack`'s reason -- a banked reroll is a `c.watch`, and
        its handler closes over the row's `Cast` rather than the roll.
        """
        ev = ev if ev is not None else self.trigger
        if ev is None or not hasattr(ev, "saved"):
            return False
        again = self.world.rng.roll("1d20").total
        if keep == "best":
            again = max(again, ev.natural)
        elif keep == "worst":
            again = min(again, ev.natural)
        was = ev.natural
        ev.natural = again
        ev.bonus += bonus
        ev.saved = again + ev.bonus >= 10
        self._announce_reroll("save", was, again, actor=getattr(ev, "actor", self.me))
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

        return spend_surge(
            self.world, on if on is not None else self.me,
            source=self.me, power=self.ref,
        )

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
            who, self.me, until, label=f"{self.ref} size", on_end=[revert],
            by=self.ref,
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
            who, self.me, until, label=label, sustain_cost=sustain,
            # `label` here is whatever the row passed, which is prose on
            # plenty of cards. `by` is the row itself, so a keyword gate
            # still finds it. #580
            by=self.ref,
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
            who, self.me, until, label=f"{self.ref} unseen", relations=pairs,
            by=self.ref,
        )

    def hide(self, *, from_: int | None = None, until: When = When.ENCOUNTER) -> Effect | None:
        """Go unseen, and stay that way until something gives you away.

        The same held state as `c.invisible` and a different duration: being
        invisible runs out on a clock, being hidden lasts until you do
        something about it -- and attacking does. `resolve.attack` breaks it
        for whoever swung.

        **"It remains hidden if the attack misses" goes in the
        `AttackDeclared` AFTER window, not in a `Miss` watch.** This docstring
        used to say a row "hides again afterwards, which is how the printed
        ones read", and that is true from a power's *body* and false from a
        `Miss` watch -- which is exactly where a printed "remains hidden on a
        miss" wants to live, so the obvious reading fails silently. One
        shipped row was inert that way.

        The clear sits **below** the loop that emits `Hit`/`Miss`, and it has
        to:

        * being hidden is one of the things that grants combat advantage
          (`query.hidden_from` -> `has_combat_advantage`);
        * a striker's extra damage asks for combat advantage **live, at the
          moment of the hit** -- `extra_damage(applies=...)` in
          `features/strikers.py`, whose docstring gives the reason: flanking
          ends the instant an ally steps away and a stored flag would not
          notice;
        * so clearing before the emit makes every such rider read the
          *post-attack* board. Measured: moving it cost a rogue its 2d6 on
          `level-5-full`, 2043 events down to 1925, with
          `DamageRolled(detail='cf:rogue-scoundrel-f4')` becoming a plain
          `'mba'`.

        The `AttackDeclared` AFTER window runs once the whole attack is done,
        past the clear, so a re-hide laid there sticks. `m2304a5` documents
        the three-watch idiom: take who you were hidden from in BEFORE,
        remember the outcome from the announcement, restore in AFTER.
        #390, #446.
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
        self,
        kind: str = "",
        *,
        on: int | None = None,
        until: When = When.ENCOUNTER,
        when: str = "",
    ) -> Effect | None:
        """Cross rough ground for nothing. `kind` names which sort, or all.

        `c.ignores_difficult("mud")` is the printed line "ignores difficult
        terrain that is mud or shallow water" -- said twice, once per word.
        With no `kind` it is every sort. The labels are the ones the map and
        `c.zone(difficult=...)` give their squares.

        `when` narrows it to **one kind of going**: `when="shift"` is "ignores
        difficult terrain when it shifts", which 23 rows print and which this
        verb could previously only say by granting the exemption for walking
        too -- a row stronger than its card, on every one of them.

        The cards name two more kinds and this engine has both:
        `when="charge"` is "ignore all difficult terrain when you move as
        part of a charge" and `when="run"` is "you ignore difficult terrain
        when you run". `movement.PRICED_KINDS` is the authority on which
        kinds exist, and anything outside it **raises**: a teleport or a
        forced slide pays nothing for terrain in the first place, so an
        exemption scoped to one would be a modifier nothing consults, which
        is this component's commonest bug and reads exactly like a working
        row.

        **`kind` raises on a word outside `DIFFICULT_LABELS`**, which is the
        same discipline `when` above already has and the one change that
        stops #598 recurring: that argument took any string, and 29 calls
        named ground no square carries. A new sort of going is one line in
        that set, and a typo is now a failure instead of a silent waiver --
        `"webs"` for `"web"` was exactly that, on a row that read as
        finished.
        """
        from .components import Movement

        who = on if on is not None else self.me
        moves = self.world.get(who, Movement)
        if moves is None:
            return None
        word = kind.lower() or "*"
        # **Refused, not accepted silently.** `"*"` is the bare call --
        # every sort of going -- and anything else must be a label something
        # can write. #598: 29 calls named ground no square carries, and each
        # read as a finished row.
        if word != "*" and not _is_terrain_label(word):
            raise ValueError(
                f"{self.ref}: c.ignores_difficult({kind!r}) names no sort of"
                f" going. Known: {', '.join(sorted(DIFFICULT_LABELS))}, or a"
                f" ref for the per-zone idiom. A new word is a line in"
                f" `DIFFICULT_LABELS`; a move kind like 'shift' belongs in"
                f" `when=`."
            )
        if when:
            scope = when.lower()
            from .movement import PRICED_KINDS

            if scope not in PRICED_KINDS:
                raise ValueError(
                    f"{self.ref}: nothing prices a move of kind {scope!r} "
                    f"against difficult terrain; the kinds that do are "
                    f"{sorted(PRICED_KINDS)}"
                )
            held = moves.ignores_when.setdefault(scope, set())
            if word in held or word in moves.ignores:
                return None
            held.add(word)
            return self.world.effects.apply(
                who, self.me, until, label=f"{self.ref} sure-footed {scope}",
                on_suspend=[lambda: held.discard(word)],
                on_resume=[lambda: held.add(word)],
                by=self.ref,
            )
        if word in moves.ignores:
            return None
        moves.ignores.add(word)
        # **`on_suspend`, not `on_end`.** `Effects._lift` runs this for an
        # expiry *and* for a suspension, so the label comes off exactly once
        # either way -- and "it ignores difficult terrain while raging" can
        # switch off without spending the stance.
        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} sure-footed",
            on_suspend=[lambda: moves.ignores.discard(word)],
            on_resume=[lambda: moves.ignores.add(word)],
            by=self.ref,
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
        """`self.me`'s abilities. **Assumes `me` is a creature**, and that
        assumption is measured rather than hoped for. #617.

        `world.need` raises for an entity with no `Stats`, and creatures,
        characters, companions and conjurations all carry them -- including
        the ones `summon_inline` builds. What lacks them is everything on
        the board that is **not a creature**. Counted on one audited board
        with a wall added, six such entities:

            z:…                 Ident only                 (2 zones, 1 wall)
            audit:setup object  Ident, Position, Scenery
            audit:setup fire    Ident, Position, Scenery    (2 hazards)

        **Not "a `Barrier`", which this said for a while and is wrong**:
        none of the six carries that component, `c.wall(solid=True)`
        included -- it makes a zone-shaped entity. The right statement is
        the shape, not the component.

        Nothing anywhere constructs a `Cast` around one. **36 `Cast(...)`
        sites in `src/`, 23 in `content/` and 13 in `engine/`**, and every
        `me=` is a creature id: `me` (10), `actor` (10), `eid` (8), `who`
        (4), `owner` (2), `ev.actor` (1). AST-walked rather than grepped,
        because this count has already gone stale once -- it was recorded
        as "ten engine and six content" and both numbers had moved by the
        time anyone re-read it. Re-measure before relying on the figures;
        the *conclusion* is what is stable.

        So the throw is reachable only by hand -- `Cast(me=<a wall>)` in a
        probe, which is how it was found -- and the 4,862 content reads
        through here are all a caster's own modifier. Left raising rather
        than made to answer 0: a silent zero on a modifier is the shape
        this repo spends most of its instruments catching, and `need`
        names the entity.
        """
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

    def attack_with(self, a: Ability) -> int:
        """The full attack bonus for an ability, named at runtime.

        `c.str_` and its six siblings are this with the ability baked in, which
        is what a row printing "Strength vs. AC" wants. A row printing **"Primary
        ability vs. Reflex"** does not know which ability until it asks, so it
        needs the generic form -- `p11808` rolls its dismissal burst through here
        off `c.ability_for()`.

        Public because content asked: reaching for `_attack_bonus` from a row is
        the same thing with a private name on it.
        """
        return self._attack_bonus(a)

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
        weapon_power = p is None or Keyword.WEAPON in self.keywords_of(p)
        gear = self.world.get(self.me, Gear)
        if gear is not None:
            if weapon_power and self._trained_with(gear, self._wielded()):
                bonus += getattr(self._wielded(), "proficiency", 0)
            bonus += self._enhancement_of(p)
        return bonus

    def _trained_with(self, gear: Gear, arm: Weapon | None) -> bool:
        """Is this creature trained with the weapon it is holding?

        **The test used to be "is this a weapon power", never "is this character
        proficient".** So any creature holding anything got that weapon's full
        proficiency bonus, and the superior weapons -- whose entire cost is a
        feat -- were free: a level-1 fighter with no feat rolled +8 with a
        fullblade against +7 with the greataxe it is actually trained with.
        #242.

        `Gear.trained` empty means **no record**, not "trained with nothing". A
        monster has no `Build` and a probe's hand-built board records nothing,
        and turning a missing record into a to-hit penalty would be a worse bug
        than the one being fixed. So the bonus is withheld only when there is a
        record and the weapon is not in it.
        """
        if arm is None or not (gear.trained or gear.bands):
            return True
        # **The band first, because it is the broader claim.** `trained` is the
        # handful of weapons this character was dealt; `bands` is what its page
        # allows. A fighter dealt a longsword was refused the bonus on a
        # warhammer its page plainly grants, which is #285 -- the fix for #242
        # was right about the superior weapon and wrong about the warhammer.
        return gear.proficient_with(arm) or arm.ref in gear.trained

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
            ranged = p is not None and Keyword.RANGED in self.keywords_of(p)
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
        if p is not None and Keyword.IMPLEMENT in self.keywords_of(p):
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

    def level_of(self, who: int | None = None) -> int:
        """Somebody else's level, for a printed "of level 6 or lower".

        `c.level` is the caster's and there was nothing for anyone else, so
        four content modules each wrote a private `_level_of` and one of
        them is imported across two directories. Same body in all four,
        including the 99 -- a creature with no stat block is out of reach of
        a sentence about levels, never under it, so the ceiling must fail
        closed rather than treat an absent level as zero.
        """
        other = self._who(who)
        stats = self.world.get(other, Stats) if other is not None else None
        return 99 if stats is None else stats.level

    def w(self, count: int = 1, *, hand: str = "main", ranged: bool | None = None) -> str:
        """`count`[W]: the wielded weapon's damage dice, that many times.

        A ranged power rolls the ranged weapon, where the creature has one.
        A ranger carries a blade and a bow, and firing the bow while rolling
        the blade's dice is wrong in a way nothing would ever report.
        """
        weapon = self._swinging(hand=hand, ranged=ranged)
        if weapon is None:
            return f"{count}d4"
        n, _, faces = weapon.damage.partition("d")
        return f"{int(n or 1) * count}d{faces}"

    def _swinging(self, *, hand: str = "main", ranged: bool | None = None):  # noqa: ANN202
        """Which weapon this row is being used with, or None.

        Lifted out of `w` so `_high_crit` asks the same question rather than a
        similar one: a high-crit die has to come off the weapon whose dice the
        row is already rolling, or a ranger firing a bow would get the extra die
        from the blade on its belt.
        """
        gear = self.world.get(self.me, Gear)
        if gear is None:
            return None
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
            fires = p is not None and Keyword.RANGED in self.keywords_of(p)
        if fires and gear.ranged is not None:
            weapon = gear.ranged
        return weapon

    def _high_crit(self) -> int:
        """The extra damage a high crit weapon deals on a critical hit.

        **18 of 117 printed weapons carry the property and nothing read it**, so
        a greataxe and a maul differed only in their dice and `choices.py` was
        scoring a benefit the engine did not grant -- a silently-false term in
        the scorer rather than in a row. #240.

        One extra `[W]`, which is the heroic number and the only one this build
        needs: the rule gives two at paragon and three at epic, and the level
        ceiling stops at 10 (#281).

        **Rolled, not maxed**, which is the part worth being careful about. A
        critical maximises the power's own dice; the high-crit dice are extra
        damage *on top of* that and are rolled normally. Maxing them too would
        pay a greataxe 12 where the rule pays it an average of 6.5.

        Only for a row carrying the weapon keyword. A wizard's implement power
        is not a weapon attack, and a held weapon must not lend it anything.
        """
        p = self._declared()
        if p is None or Keyword.WEAPON not in self.keywords_of(p):
            return 0
        weapon = self._swinging()
        if weapon is None or "high crit" not in weapon.properties:
            return 0
        return self._roll_damage(weapon.damage)

    def _declared(self):  # noqa: ANN202
        from .dsl import get

        return get(self.ref)

    def counts_as(
        self,
        satisfies: str,
        *,
        holding: str,
        on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """"You can use a warhammer with any power that requires a light blade."

        `holding` is what is actually in hand and `satisfies` is what the
        card the character wants to use asks for. Read by `wielding`, which
        is the one place a printed weapon Requirement is checked, so one
        waiver covers every row that asks.

        Call it once per weapon the card names: two of these feats name a
        pair ("a warhammer **or** a throwing hammer"), which is two waivers
        and not a group.
        """
        who = on if on is not None else self.me
        gear = self.world.get(who, Gear)
        if gear is None:
            return None
        pair = (holding, satisfies)
        # The effect first, as `forbid` and `rolls_with` do.
        effect = self.world.effects.apply(
            who, self.me, until,
            label=f"{self.ref}: {holding} counts as {satisfies}",
            by=self.ref,
        )
        if effect is None:
            return None
        gear.counts_as.append(pair)
        # `on_suspend` only -- `Effects._lift` runs it on expiry too, which
        # is the whole point of its being the single list.
        effect.on_suspend.append(
            lambda: gear.counts_as.remove(pair) if pair in gear.counts_as else None
        )
        effect.on_resume.append(lambda: gear.counts_as.append(pair))
        return effect

    def keywords_of(self, p: Any) -> frozenset[Keyword]:
        """This row's keywords **for this caster**, header plus granted.

        A one-line hop to `dsl.keywords_of` so the eleven reads in this file
        do not each have to import it and name `self.me`.
        """
        from .dsl import keywords_of

        return keywords_of(self.world, self.me, p)

    def as_weapon(
        self,
        *,
        damage: str,
        group: str,
        proficiency: int = 0,
        properties: frozenset[str] = frozenset(),
        hands: str = "one-handed",
        on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """"This shield can be used as a one-handed melee weapon."

        Four item rows print a full weapon profile on something that is not
        a weapon -- two shields and two rods -- and the `weapon` table has
        no row for them, because they are items. The numbers are on the card
        and are hand-written here, which is how every other row in this tree
        gets its numbers.

        The profile is added to `Gear.weapons` so everything that asks what
        is in hand finds it: `c.w()`, `c.wielding`, `Gear.main`. It carries
        the item's own enhancement, which is what "applies its enhancement
        bonus to attack and damage rolls" means.

        **`hands` is the printed phrase, not a count.** `Weapon.hands` is a
        `str` and `Gear.proficient_with` builds a band key off it --
        `f"{cat}:{arm.hands.lower()} {reach}"` -- so an `int` here is an
        `AttributeError` on the first proficiency test for any character with
        a band. The annotation said `int` and one caller obliged.

        **Not held on arrival.** A shield-as-pick is a second weapon the
        character may take up, so it goes to the belt and
        `actions._wielding` offers the draw -- otherwise laying the profile
        would silently disarm whatever was in the main hand.
        """
        from .components import Gear, Weapon

        who = on if on is not None else self.me
        gear = self.world.get(who, Gear)
        if gear is None:
            return None
        arm = Weapon(
            ref=self.ref,
            slug="",
            damage=damage,
            proficiency=proficiency,
            group=group,
            category="simple",
            hands=hands,
            properties=properties,
            enhancement=self.enhancement,
        )

        def lift() -> None:
            if arm in gear.weapons:
                gear.weapons.remove(arm)
            gear.stowed.discard(arm.ref)

        effect = self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} is a weapon",
            by=self.ref,
        )
        if effect is None:
            return None
        gear.weapons.append(arm)
        gear.stowed.add(arm.ref)
        # `on_suspend` only -- `Effects._lift` runs it on expiry too.
        effect.on_suspend.append(lift)

        def rearm() -> None:
            if arm not in gear.weapons:
                gear.weapons.append(arm)
            gear.stowed.add(arm.ref)

        effect.on_resume.append(rearm)
        return effect

    def counts_as_keyword(
        self,
        ref: str,
        keyword: Keyword,
        *,
        on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """"Your <row> is considered an arcane attack power."

        A keyword this creature's copy of a named row carries, on top of
        whatever the header declares. Read through `dsl.keywords_of` and
        nowhere else -- a row's keywords are header data, one tuple shared
        by everybody who holds the row, so a feat cannot edit it without
        editing it for all of them.

        The sibling of `counts_as`, which waives a *weapon* requirement.
        Both are "X counts as Y", and they are separate verbs because they
        touch different state and are read in different places: that one is
        `Cast.wielding`, this one is 22 sites.
        """
        from .components import Powers

        who = on if on is not None else self.me
        known = self.world.get(who, Powers)
        if known is None:
            return None
        was = known.granted_keywords.get(ref, frozenset())
        if keyword in was:
            return None

        def lift() -> None:
            known.granted_keywords[ref] = was
            if not was:
                known.granted_keywords.pop(ref, None)

        # The effect first, as `forbid` and `rolls_with` do.
        effect = self.world.effects.apply(
            who, self.me, until,
            label=f"{self.ref}: {ref} counts as {keyword.value}",
            by=self.ref,
        )
        if effect is None:
            return None
        known.granted_keywords[ref] = was | {keyword}
        # `on_suspend` only -- `Effects._lift` runs it on expiry too.
        effect.on_suspend.append(lift)
        effect.on_resume.append(
            lambda: known.granted_keywords.__setitem__(ref, was | {keyword})
        )
        return effect

    def wielding(self, prop: str) -> bool:
        """Does the caster meet a printed Requirement line?

        `"shield"`, `"two-weapon"`, a weapon group like `"light blade"`, a
        category like `"simple"`, or a property like `"two-handed"`.
        """
        gear = self.world.get(self.me, Gear)
        if gear is None:
            return False
        if prop == "shield":
            # **A count, not a flag.** `Gear.shield` is 0/1/2 -- none, light,
            # heavy -- because the number *is* the printed AC and Reflex
            # bonus. Returned bare it made this `-> bool` hand back an int,
            # and seven content copies of the same helper repeat the mistake
            # one for one. #618.
            return bool(gear.shield)
        if prop in ("two-weapon", "two melee weapons"):
            return gear.two_weapon
        weapon = gear.main
        if weapon is None:
            return False
        if (
            prop in weapon.properties
            or weapon.group == prop
            or weapon.category == prop
        ):
            return True
        # A feat may let what is in hand stand in for what the card asks
        # for. Checked after the printed test rather than folded into it,
        # so a character with no waiver takes exactly the path it always
        # did.
        return any(
            satisfies == prop and _weapon_is(weapon, holding)
            for holding, satisfies in gear.counts_as
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
        damage_type: DamageType | None = None,
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

        `damage_type` types the `damage_bonus`, which is `Mod.dtype`'s own
        reason for existing: *"and deals extra thunder damage equal to your
        Intelligence modifier"* is thunder even when the sword is not, so it
        meets the target's thunder resistance where the sword's points do
        not. Left out, the rider joins the blow and is whatever the blow
        already was, which is right for a plain "+2 damage".
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
                    mods=[(who, Mod(
                        what="damage", value=damage_bonus, kind="power",
                        dtype=(damage_type,) if damage_type is not None else (),
                    ))],
                    by=self.ref,
                )
            )
        # **Plus whatever the granter carries for granted attacks.** Read off
        # `self.me` and not `who`: the card is "when one of *your* powers
        # forces a creature to make an attack", so the bonus belongs to the
        # creature doing the forcing. Reading `who` would let a creature
        # improve the swings it is forced into, which is the same mistake
        # `_extra_every` records for pushes from the other side.
        #
        # `self.ref` is the granting row by construction, so a card naming a
        # class of powers gates on `ctx["power"]` and needs no new key.
        attack_bonus += self.amount_for(
            MANOEUVRE_GRANTED_ATTACK, 0, {"power": self.ref, "who": who}
        )
        if attack_bonus:
            granted.append(
                self.world.effects.apply(
                    who, self.me, When.EOT,
                    label=f"{self.ref} granted attack",
                    mods=[(who, Mod(what="attack", value=attack_bonus, kind="power"))],
                    by=self.ref,
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

        **"Melee" is enforced by the key, and the `when=` is a second lock
        on the same door.** #547 read this note and concluded the gate was
        dead -- "no modifier context carries `kind`" -- and that is wrong in
        both halves, measured:

        * `dsl._stretched` **does** carry it, as `{"power": ..., "kind":
          r.kind}`, where `r.kind` is the *range* kind. So the gate is a
          real test: it answers True on a melee line and **False on a
          ranged one**, which is measured -- reading this modifier with a
          ranged ctx returns 0 even if the key is right;
        * and it could not matter anyway, because each range kind reads a
          **different key**. A melee line asks `"reach"`, a ranged line asks
          `"range"`, a blast or burst asks `"blast_size"`. Laying 4 squares
          of `"reach"` and then asking each: melee 4, ranged 0, close burst
          0, area burst 0. There is no attack of another shape for this hold
          to leak onto.

        **Two locks, either one sufficient, and the key is the one holding
        today.** Three plants settle which is which: making a ranged line
        read `"reach"` leaves the rule green, because the gate refuses it;
        cutting the gate leaves it green, because the key never offers it;
        doing both turns it red. So neither is dead and neither is
        load-bearing alone, which is worth knowing before anybody removes
        one as redundant. `drivers.a_reach_hold_cannot_reach_a_ranged_line`
        asks about them separately for exactly that reason.

        The other reader is `movement._threat`, for threatening reach, whose
        ctx carries no `kind` -- and the `"melee"` default is right there
        too, since a threatened square is melee by definition.

        **The real hazard the issue found is the word `kind` itself**, which
        is one context key over four vocabularies: a range kind here, a
        *move* kind in `c.no_provoke` and `_extra_every`, and a *roll* kind
        (`check`/`attack`/`save`) in what `p6186` hands its narrowers. A
        reader cannot tell from the gate which one is meant, which is how
        this came to be filed as a bug. #639.
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
            # **`Powers.ranged` is the field that answers this**, and it was not
            # being asked. The old test searched `known.known` for the engine's
            # generic `rba`, which is right for a character -- `chargen` sets
            # both -- and wrong for a monster, whose ranged attack is one of its
            # own printed rows. So "it makes a ranged basic attack" swung a
            # notional bow off Dexterity instead of the attack bonus and damage
            # its page prints: the swing happened, a `Hit` was emitted, and the
            # numbers were somebody else's.
            #
            # `dsl.basic_options` already read the field correctly and could
            # never be reached, because this passes a non-empty `own` that
            # shadows it. #398.
            ref = (known.ranged if known else "") or RANGED
        offered = basic_options(
            self.world, attacker, "ranged" if ranged else window, ref
        )
        if len(offered) > 1:
            ref = self.choose(offered, "which attack to make") or ref
        # Marked as granted even when the swinger is the caster: the
        # defender's punishment is a self-grant, and eight feats are
        # about exactly that swing and no other.
        #
        # **The trigger is forwarded, and a death throe depends on it.**
        # `dsl.use` derives its `dying` exemption from the trigger it is
        # handed -- "this row answers the actor's own `Dropped`" -- and this
        # call passed none, so `dying` was always False and `usable`'s
        # "can it act?" gate refused the swing for a creature that had
        # already gone down. That is precisely the gate a death throe exists
        # to be exempt from, so a row whose whole content is "when it drops,
        # it makes a basic attack" emitted `PowerUsed` and no
        # `AttackDeclared`: finished-looking and inert.
        return use(
            self.world, attacker, ref, targets=[target], spend=False,
            trigger=self.trigger,
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
        as_: str = "",
    ) -> AttackResult:
        """`as_` names *which* swing this is, when one row makes more than one.

        A row granting a counter-attack rolls it longhand through here, so the
        opening blow and the counter arrived with the same `power` and a feat
        printing a clause about the counter alone had nothing to ask. It rides
        on the `Hit` and the `Miss` the way `charge` and `opportunity` do.
        """
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
            keep=keep, hand=hand, as_=as_,
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
        # `dtypes` as well as `dtype`: a header naming two types is one blow
        # that is both, and resistance reads it as a unit. Passing only the
        # primary would have let a creature resisting the second half shrug
        # off nothing.
        if half:
            return self.half_damage(
                dice, bonus, dtype=d.dtype, dtypes=d.dtypes, on=on
            )
        return self.damage(dice, bonus, dtype=d.dtype, dtypes=d.dtypes, on=on)

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
            amount = _max_of(dice) + bonus + self._high_crit()
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

        **The enhancement bonus is halved with the rest, and was missing.** This
        method and `c.damage` sit twenty lines apart and only the other one added
        it, so every miss line in the tree understated itself by half the
        enhancement -- 1.5 points at +3, on a clause that fires on roughly a
        third of attacks. Half damage is half of *the damage the hit would have
        dealt*, and the enhancement is part of that, so it goes in before the
        halving and not after. #241.

        Added here rather than removed there, because `c.damage` is the one that
        matches the printed rule; the inconsistency was the symptom and the
        omission was the fault.
        """
        who = self._who(on)
        if who is None:
            return 0
        full = self._roll_damage(dice) + bonus if dice else bonus
        amount = (full + self._enhancement()) // 2
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
             unpreventable: bool = False,
             on: int | None = None) -> int:
        """Damage that is not rolled. `dtypes` is one blow of several types.

        "The attacker takes 10 lightning and thunder damage" is ten points
        that are both, not ten of each -- see `c.damage`.

        **`unpreventable=True` is "this damage cannot be reduced or
        prevented in any way"**, which ten cards print.

        **Most** are a price the character elects to pay -- hit points for
        an ally's healing, for pulling an attack onto itself, for raising a
        weapon's damage -- and resistance would let the payer dodge the
        bill while keeping what it bought. `i696p1` is the clearest: the
        target takes double what the wielder paid, so resisting your own
        cost would double the profit.

        **Two are not, and the first reading of this family missed them.**
        `i2056p1` deals five necrotic to an *enemy* that ends its turn
        adjacent, and the clause is there to go through that enemy's
        necrotic resistance; `i3376p1` charges an *ally* who volunteers.
        So the flag means what it says about the damage and carries no
        assumption about who takes it.

        Skips insubstantial halving, immunity and resistance. Does **not**
        touch temporary hit points, which are spent after all of that and
        are how hit points work rather than a reduction of the blow. See
        `resolve.deal_damage` for why vulnerability goes with the rest.
        """
        who = self._who(on)
        if who is None:
            return 0
        return deal_damage(
            self.world, self.me, who, amount, dtype, self.ref,
            dtypes=dtypes, unpreventable=unpreventable,
            opportunity=self.opportunity, charge=self.charge,
            granted_by=self.granted_by, granted_via=self.granted_via,
        )

    def heal(self, amount: int, *, on: int | None = None) -> int:
        """Put hit points back. The row's own ref rides along on `Healed`.

        `power=self.ref` is what lets a rider tell *which* heal it is
        looking at -- "the hit points regained by your cleric healing
        powers", "each character healed by one of your encounter powers".
        Ten rows wanted that and the event said only who healed whom.
        """
        who = self._who(on)
        if who is None:
            return 0
        return heal(self.world, self.me, who, amount, self.ref)

    def surge(self, *, on: int | None = None, bonus: int = 0) -> int:
        """Spend a healing surge: a quarter of maximum hit points."""
        from .query import surge_value
        from .resolve import spend_surge

        who = self._who(on)
        health = self.world.get(who, Health) if who else None
        if health is None:
            return 0
        worth = surge_value(self.world, who) + bonus
        # `healed` is announced as what the surge is *about* to pay out,
        # which is the number the printed riders on it ask about -- and the
        # heal is capped by the pool, so this is a forecast rather than the
        # applied total. The one row reading it ("when you spend a surge and
        # regain hit points") wants the surge's worth, not the shortfall.
        if not spend_surge(
            self.world, who, source=self.me, power=self.ref, healed=worth
        ):
            return 0
        return heal(self.world, self.me, who, worth, self.ref)

    def temp_hp(self, amount: int, *, on: int | None = None) -> None:
        """Grant temporary hit points. The row's ref rides on `TempHP`.

        Seven rows narrow on which row granted them -- see `TempHP.power`
        and `Healed.power`, which carries the same contract.
        """
        who = self._who(on)
        if who is not None:
            temp_hp(self.world, self.me, who, amount, self.ref)

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
            # The label is the printed amount, so it resolves to no row --
            # which is how a psychic burn answered "not psychic". #580
            by=self.ref,
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
        if who is None:
            return 0
        # **The squares belong to whoever is doing the forcing**, which is
        # the opposite of `c.shift` and `c.teleport`: those read the mover,
        # because "whenever you shift" is about the creature stepping. Here
        # the card is "when one of *your* powers allows you to push, the
        # maximum distance increases by 2" -- the pusher's rider, applied to
        # somebody else's trip. Reading the victim would have let a creature
        # lengthen the pushes it suffers.
        #
        # Skipped when `to` names the destination outright, for the reason
        # `c.shift` skips it there: a row that says where the creature ends
        # up is not asking how far it may go. #581.
        mover = by if by is not None else self.me
        if to is None:
            squares_ += self._extra_every(mover, "push")
        return forced(
            self.world, mover, who,
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
        if who is None:
            return 0
        # **The squares belong to whoever is doing the forcing**, which is
        # the opposite of `c.shift` and `c.teleport`: those read the mover,
        # because "whenever you shift" is about the creature stepping. Here
        # the card is "when one of *your* powers allows you to push, the
        # maximum distance increases by 2" -- the pusher's rider, applied to
        # somebody else's trip. Reading the victim would have let a creature
        # lengthen the pushes it suffers.
        #
        # Skipped when `to` names the destination outright, for the reason
        # `c.shift` skips it there: a row that says where the creature ends
        # up is not asking how far it may go. #581.
        mover = by if by is not None else self.me
        if to is None:
            squares_ += self._extra_every(mover, "pull")
        return forced(
            self.world, mover, who,
            Forced.PULL, squares_, anchor=anchor, to=to, power=self.ref,
        )

    def slide(
        self,
        squares_: int,
        *,
        on: int | None = None,
        anchor: Square | None = None,
        to: Square | None = None,
        toward: int | None = None,
        by: int | None = None,
    ) -> int:
        """`to` names the destination outright, for a row that does.
        `by` names who is doing the moving, when it is not the caster.

        A slide's destination is otherwise the decider's free choice, which
        is right for "slide it 3 squares" and wrong for "slide it into a
        square adjacent to you" -- that one was duly sliding enemies three
        squares *away*. `push` and `pull` have had `to` all along; this is
        the one that did not.

        `toward` names a **creature** to slide somebody at, which is what
        "slide the target 3 squares and then it attacks its nearest ally"
        needs: the line is walked at that creature and `forced` stops where it
        legally can. It is `to` with the square worked out, so it goes through
        the same path rather than adding a second one.

        It arrived late. `c.move`, `c.shift`, `c.jump` and `c.teleport` were
        given a destination bias for #381 and this verb was missed, so three
        rows that slide a charmed creature at an ally were still sliding it
        away -- invisible for as long as the swing afterwards went unchecked,
        and the whole row once it did not.
        """
        who = self._who(on)
        if to is None and toward is not None and who is not None:
            from .query import squares as _squares

            mine = _squares(self.world, toward)
            if mine:
                here = self.world.get(who, Position)
                from .grid import distance

                at = here.square if here is not None else None
                to = min(mine, key=lambda sq: distance(sq, at)) if at else min(mine)
        if who is None:
            return 0
        # The pusher's rider, as in `c.push` above -- and asked after the
        # `toward=` branch, because that branch *computes* a `to` and a
        # destination is not lengthened.
        mover = by if by is not None else self.me
        if to is None:
            squares_ += self._extra_every(mover, "slide")
        return forced(
            self.world, mover, who,
            Forced.SLIDE, squares_, anchor=anchor, to=to, power=self.ref,
        )

    def _nearest_first(
        self,
        options: list[Square],
        toward: int | None,
        away_from: int | None = None,
        mover: int | None = None,
    ) -> list[Square]:
        """The same squares, ordered by how near a creature they leave you.

        **Ranking, not overriding.** `World.decide` with no decider attached
        takes the first option in the list, so an unordered list means the
        lowest coordinate on the board -- a creature told to step aside walks
        to a corner (#383), and a row that moves and then swings finds its
        target out of reach (#381). A real decider still sees every option, in
        a better order. `movement.overrun` settled this shape for itself; this
        is the same answer for the verbs that move without naming a square.

        **Both directions, because the printed lines go both ways.** Six of the
        seven rows that were waiting on `c.shift(toward=)` say "end adjacent to
        the enemy" or "end closer to you"; the seventh says "you must end the
        move *farther* from your ally". A parameter that could only close would
        have let that one report finished while still picking a corner.

        **With neither named, the mover anchors on itself.** That is #383: the
        ranking only engaged for `toward=`/`away_from=`, so every row that
        moves without a stated preference still took `options[0]` -- the lowest
        coordinate on the board. A level-12 row surfaced from a burrow and its
        close burst 2 caught nobody, because the caster had teleported to the
        far corner. Least displacement is the neutral answer and it is the only
        one available here: which square is *tactically* best is the policy
        layer's judgement, not the kernel's, and a kernel that guessed would be
        deciding something `World.decide` exists to delegate. What it must not
        do is prefer a corner, which is what sorted order means.
        """
        if not options:
            return options
        from .grid import distance
        from .query import squares as _squares

        anchor = toward if toward is not None else away_from
        anchored_on_self = anchor is None
        if anchored_on_self:
            anchor, toward = mover, mover
        if anchor is None:
            return options
        mine = _squares(self.world, anchor)
        if not mine:
            return options
        near = sorted(options, key=lambda sq: min(distance(sq, t) for t in mine))
        if anchored_on_self:
            # **Least displacement, but still a move.** `c.teleport`'s options
            # include the square the creature is already on, so ranking by pure
            # distance made an unnamed teleport a no-op -- which is a different
            # wrong answer from the corner, and one the audit would read as a
            # silent row. A row that genuinely wants to stay put does not call
            # a move verb.
            moved = [sq for sq in near if sq not in mine]
            return moved or near
        return near if toward is not None else list(reversed(near))

    def shift(
        self,
        squares_: int = 1,
        *,
        who: int | None = None,
        to: Square | None = None,
        toward: int | None = None,
        away_from: int | None = None,
        share: bool = False,
    ) -> bool:
        """Shift, choosing the destination through the world's decider.

        `to` names the square outright, for the powers that do -- "shift into
        the space the target left" is not a choice, it is an instruction.

        `toward` names a creature to end up near instead of a square to stand
        on, for "shift and then attack it": the options are offered closest
        first, so a row that keeps a swing pending does not step out of reach.
        `away_from` is the mirror, for "you must end the move farther from your
        ally". See `_nearest_first`.

        `share` moves *into* an occupied square, for a creature that melds
        with the one it is on top of.

        **It was inert twice over on this branch, and ten rows were plain
        shifts.** `reachable_squares` never offered an occupied square, so
        the destination a shared shift is *about* was not in the option list
        -- and even had it been, `share=` was not forwarded to
        `movement.shift`. Only the `to=` branch above ever worked. Both
        halves are fixed here, which is what `c.teleport` 600 lines below had
        been doing correctly all along. #527.
        """
        mover = self.me if who is None else who
        if to is not None:
            return shift(self.world, mover, to, share=share)
        # **The printed distance, before anything lengthens it.** What
        # `Moved.stretched_` reports is the difference between this and the
        # square the decider actually picked -- "spent", not "granted",
        # because `c.extend_every` raises a budget the mover need not use.
        printed = squares_
        squares_ += self._extra_every(mover, "shift")
        # **Priced as a shift**, which is where "it ignores difficult terrain
        # when it shifts" is actually spent: a one-square shift cannot enter
        # difficult terrain because the square costs two, so the exemption is
        # the difference between an option being offered and not. Nothing in
        # `shift` or `step` charges for terrain -- the budget goes here.
        options = self.world.reachable_squares(mover, squares_, kind="shift",
                                               share=share)
        if not options:
            return False
        options = self._nearest_first(list(options), toward, away_from, mover)
        dest = self.world.decide(mover, "shift", options, f"{self.ref}: shift {squares_}")
        return shift(self.world, mover, dest, share=share,
                     stretched=self._stretch(mover, printed, dest))

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
        self, squares_: int, *, who: int | None = None, at: str = "",
        toward: int | None = None, away_from: int | None = None,
    ) -> int:
        """Walk. `at` names a movement mode to travel at instead.

        `toward` names a creature to end up near, which is what "moves up to 6
        squares and makes a melee basic attack" needs: without it the
        destinations go to `World.decide` unordered and the first in sorted
        order wins, so the creature walks away from the thing it is about to
        swing at. 13 rows were measured attacking from out of reach for exactly
        this reason (#381). `away_from` is the mirror, for "you must end the
        move farther from your ally". See `_nearest_first`.

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
                mover,
                "move",
                self._nearest_first(sorted(paths), toward, away_from, mover),
                f"{self.ref}: move {squares_}",
            )
            return walk(self.world, mover, paths[dest])
        finally:
            if lent is not None:
                self.world.effects.end(lent, "the move ended")

    def walk_toward(
        self,
        target: int | Square,
        squares_: int = 0,
        *,
        on: int | None = None,
    ) -> int:
        """Compelled: the creature walks the most direct route, no choice.

        **The difference from `c.move(toward=)` is the whole verb.** That one
        *ranks* the destinations and hands them to `World.decide` -- a real
        decider still sees every option, which `_nearest_first` says in as
        many words. A compulsion is the printed line where the mover has no
        vote: "must use a move action to move as close to the attacker as
        possible", "walks by the most direct route". So this picks the
        nearest square itself and never asks. #513.

        It is still the creature's **own** move, not forced movement, which
        matters twice: it provokes on the way, and it spends the target's
        move action rather than the caster's. `c.push` and `c.slide` are the
        other thing and neither spends the mover's economy.

        `target` is a creature to close on or a square to reach. `squares_`
        defaults to the mover's own speed, which is what "use a move action"
        means.

        **Follows `c.target`**, like every verb that is about somebody
        else's body: both printed lines compel a creature other than the
        one whose card it is. A row compelling *itself* passes `on=c.me`,
        and `m5452a3` is that row -- written without it, the walk returned
        0 in silence.

        Returns how far it actually got -- 0 when it is already as close as
        it can be, which is a true answer and not a failure.
        """
        from .movement import walk

        who = self._who(on)
        if who is None:
            return 0
        far = squares_ or self.speed_of(who)
        if far <= 0:
            return 0
        paths = self.world.reachable_paths(who, far)
        if not paths:
            return 0
        if isinstance(target, int):
            goal = self.world.get(target, Position)
            if goal is None:
                return 0
            spot = goal.square
        else:
            spot = target
        # **Sorted first, then the nearest.** `min` over a set is not
        # deterministic across runs and a replay fixture compares event for
        # event, so the tie-break has to be the board's own order.
        best = min(sorted(paths), key=lambda sq: _distance(sq, spot))
        return walk(self.world, who, paths[best])

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

    def reroll_attack(
        self, *, keep: str = "new", bonus: int = 0, ev: Any = None
    ) -> bool:
        """Make an attack roll again. `keep` is new, best or worst.

        Defaults to the **triggering** attack, which is `c.trigger` and only
        means anything inside a row the dispatcher offered. Rerolling is not
        cancelling: the attack still happens, with a different number.

        **`ev=` names the roll when it is not the trigger**, which is every
        *banked* reroll: *"once before the end of the encounter, when you
        make an attack roll for an encounter or a daily power and dislike
        the result, you can reroll"*. A row like that fires now and the
        reroll happens later, so it is written as a `c.watch` -- and a watch
        handler is a closure over the `Cast` the **row** was built with, so
        `c.trigger` there is whatever the row was answering when it armed,
        not the roll being watched. Without this the reroll silently
        rerolled the wrong thing or nothing at all.

        `AttackRolled` carries `result` at runtime -- attached in
        `resolve.py` rather than declared, deliberately, so it does not
        reach the wire -- which is what makes the handed event usable here.

        `bonus` is for "reroll it with a bonus equal to your Strength
        modifier" -- the reroll and the bonus are one printed clause, and a
        `c.bonus` laid afterwards is read by the next attack rather than by
        this one.
        """
        from .resolve import _mods

        ev = ev if ev is not None else self.trigger
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
        # **Modifiers that apply only to a second roll.** Three rows print
        # "a penalty on the roll your racial power forces to be made again",
        # and there was nowhere to lay one: this function recomputes the
        # result inline and re-sums nothing, so a `c.bonus(..., when=...)`
        # gated on a reroll was never consulted. Taken as the *difference*
        # between the context with `reroll` set and without, so only the
        # reroll-gated modifiers move and the ordinary ones are not counted
        # twice -- they are already in `total`.
        ctx = getattr(ev, "ctx", None) or {}
        if ctx:
            who = ctx.get("attacker", self.me)
            # `reroll_by` as well as `reroll`, because the three rows wanting
            # this each narrow to the reroll **their own** racial power
            # forces -- "a penalty on the attack roll `p1452` makes you roll
            # again". A bare `reroll` flag would have them modify every
            # reroll on the board, including a magic weapon's.
            again = {**ctx, "reroll": True, "reroll_by": self.ref}
            result.total += _mods(self.world, who, "attack", again) - _mods(
                self.world, who, "attack", ctx
            )
        result.critical = face == 20
        result.hit = face == 20 or (face != 1 and result.total >= result.target_defence)
        # Recorded on the result and announced as a moment, which are two
        # different needs: 14 of the 18 rows hang on the settled outcome
        # ("a damage bonus when the reroll lands") and read the list; the
        # rest want the moment. #496.
        result.rerolled_by.append(self.ref)
        self._announce_reroll(
            "attack", old, face, actor=ctx.get("attacker", self.me)
        )
        return True

    def _announce_reroll(self, roll: str, old: int, new: int, *, actor: int) -> None:
        """One place that says a d20 was rolled again.

        Four paths roll a d20 again -- `reroll_attack`, `reroll_save`,
        `reroll_check` and `reroll_initiative` -- and a path that forgets to
        announce is silent, which is indistinguishable from a rider that
        never fires. So they all come through here and `drivers.py` asserts
        the count. #496.

        The **damage** rerolls are not among them on purpose: `reroll_damage`
        and `reroll_ones` are standing modifiers read inside `_roll_damage`,
        where there is no d20 and no single face, and none of the rows
        wanting this is about one.
        """
        from .events import Rerolled

        said = Rerolled(actor=actor, roll=roll, by=self.ref, old=old, new=new)
        # The live result rides along as a plain attribute rather than a
        # field, so it never reaches the wire or a replay fixture -- the same
        # arrangement `resolve` uses for `rolled.result`, and for the same
        # reason. Three rows answer this event by changing the roll again
        # ("+1d4 to the reroll", "reroll it once more with a +2 bonus"), and
        # without it they have the moment and nothing to act on.
        said.result = getattr(self.trigger, "result", None)
        self.world.bus.emit(said)

    def boost_roll(self, amount: int, *, kind: str = "") -> bool:
        """Add to the triggering roll **without rolling it again**.

        "Add 4 to the roll", where the roll has already been made and the
        outcome already decided from it. Three near neighbours exist and each
        is a different sentence:

        * `c.reroll_attack` and `c.reroll_save` **replace** the die, which is
          a different number whenever the original was already good enough
          with the bonus on it -- a 14 against AC 17 is a hit at +4, and a
          fresh d20 misses 15 times in 20.
        * `c.boost_check` does exactly this, and only for a `SkillCheck`.
        * `c.bonus("attack", ...)` is read by the *next* attack. The roll in
          hand was summed before the row was offered.

        `kind` is `attack`, `save`, `check`, or empty for whatever triggered.
        It is there so a row can refuse to fire on the wrong sort of roll
        rather than silently boosting one its card never mentions.

        **`natural` does not move, and that is the whole point.** The card
        says add to the *roll*, not that the die landed differently, so a
        boost can turn a miss into a hit and can never manufacture a
        critical or rescue a natural 1 -- the same distinction
        `AttackResult.treated` records for "treat the roll as odd". #495.
        """
        from .events import SkillCheck

        ev = self.trigger
        if ev is None or not amount:
            return False

        result = getattr(ev, "result", None)
        if result is not None and kind in ("", "attack"):
            result.total += amount
            # Recomputed from the untouched `natural`, so a 1 stays a miss
            # and a boost cannot manufacture a critical. `forced` outranks
            # the arithmetic: a row that said the attack simply hits is not
            # un-hit by a number.
            #
            # **The crit floor is read, not assumed to be 20.** `resolve`
            # judges a hit as `natural >= 20 - crit_range`, so hard-coding 20
            # here would judge a boosted roll by a different rule than the
            # one that settled it -- wrong for every build that widens the
            # range, and wrong invisibly. The context rides on the event for
            # exactly this.
            from .resolve import _mods

            ctx = getattr(ev, "ctx", None) or {}
            floor = 20 - (
                _mods(self.world, ctx.get("attacker", self.me), "crit_range", ctx)
                if ctx
                else 0
            )
            result.hit = (
                result.forced
                or result.natural >= floor
                or (result.natural != 1 and result.total >= result.target_defence)
            )
            return self._boosted(amount, kind)

        if hasattr(ev, "saved") and kind in ("", "save"):
            ev.bonus += amount
            # 10 is the printed threshold and `c.reroll_save` uses the same
            # literal; there is one saving throw DC in the game.
            ev.saved = ev.natural + ev.bonus >= 10
            return self._boosted(amount, kind)

        if isinstance(ev, SkillCheck) and kind in ("", "check"):
            self.boost_check(amount)
            return self._boosted(amount, kind)

        return False

    def _boosted(self, amount: int, kind: str) -> bool:
        """Say that a roll already made was added to, and return True.

        All three of `boost_roll`'s paths come through here -- an attack, a
        saving throw, a skill check -- because a rider on "an attack
        benefiting from" a charge must not fire on a boosted save, and the
        only way to tell them apart afterwards is to say which it was.
        """
        self.world.bus.emit(
            Boosted(actor=self.me, amount=amount, by=self.ref, kind=kind)
        )
        return True

    def terrain(self, word: str) -> bool:
        """Is the fight being had in that sort of place? `c.terrain("aquatic")`.

        A property of the encounter, not of anybody in it. Several creatures
        print a rider that only applies underwater, and writing only the
        bonus half would have buffed them in every dry fight there is.

        **An unknown word raises**, because the alternative is what this
        already cost: a gate reading `"water"` where the vocabulary says
        `"aquatic"` is indistinguishable from a correct gate for as long as
        `World.terrain` stays empty, and it stays empty today (#539). So the
        two bugs would land together and the second would survive the first
        being fixed.
        """
        if word.lower() not in TERRAIN_WORDS:
            raise ValueError(
                f"{self.ref}: c.terrain({word!r}) is not a terrain word. "
                f"Known: {', '.join(sorted(TERRAIN_WORDS))}."
            )
        return word.lower() in getattr(self.world, "terrain", frozenset())

    def teleport(
        self,
        squares_: int,
        *,
        who: int | None = None,
        to: Square | None = None,
        toward: int | None = None,
        away_from: int | None = None,
        share: bool = False,
    ) -> bool:
        """Blink somewhere. `to` names the square, as `c.shift` already allowed.

        Without it the destination goes through the decider, which with no
        decider installed takes the lowest-sorted square -- fine for a player
        being asked, useless for a row whose printed line says exactly where
        it arrives.

        `toward` names a creature to arrive near instead of the square to
        arrive in, for "it teleports 5 squares before each attack": a row that
        blinks and then swings has a square to pick and no way to say which,
        so it blinked out of its own reach. `away_from` is the mirror. See
        `_nearest_first`.
        """
        mover = self.me if who is None else who
        # See `c.shift`: the print before anything lengthens it, so the
        # arrival can say how much of the extra was actually used.
        printed = squares_
        squares_ += self._extra_every(mover, "teleport")
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
            # **Measured even when the row named the square.** A printed
            # destination is not a choice, but it is still a distance, and a
            # row that blinks somebody exactly where the extra square put
            # them has spent it as surely as a decider would have.
            return (
                teleport(self.world, mover, to, share=share,
                         stretched=self._stretch(mover, printed, to))
                if to in options else False
            )
        if not options:
            return False
        dest = self.world.decide(
            mover,
            "teleport",
            self._nearest_first(sorted(options), toward, away_from, mover),
            f"{self.ref}: teleport",
        )
        return teleport(self.world, mover, dest, share=share,
                        stretched=self._stretch(mover, printed, dest))

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
            by=self.ref,
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
        self, *conditions: Condition, until: When = When.EONT, on: int | None = None,
        when: Callable[[dict[str, Any]], bool] | None = None,
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
        # `when` rides on the `Mod`, where `Mods.total` already evaluates it through
        # `applies(ctx)`. `query.immune_to` used to hand that call an empty dict, so a
        # gate could only ever answer from what it closed over -- the context it needs
        # is added there, in this same commit, because a keyword whose reader cannot
        # read it is this component's commonest bug wearing a friendlier face.
        mods = [
            (who, Mod(what=f"immune to {c.value}", value=1, kind=self.ref,
                      label=self.ref, when=when))
            for c in conditions
        ]
        if not mods:
            return None
        return self.world.effects.apply(
            who, self.me, until,
            label=f"{self.ref} immune to {', '.join(c.value for c in conditions)}",
            mods=mods,
            by=self.ref,
        )

    #: The size rule all three basic manoeuvres print: "smaller than you, the
    #: same size category as you, or one category larger than you". One
    #: constant because three verbs quote it and a fourth will.
    _MANOEUVRE_REACH = 1

    def _manoeuvrable(self, who: int) -> bool:
        """Is this a creature a basic manoeuvre may be tried on?

        The printed size rule, which is the same sentence on bull rush and on
        grab: one category larger is the ceiling, and there is no floor.
        """
        if self.lingers_label(_ANY_SIZE):
            return True
        order = list(Size)
        mine = self.size_of(self.me)
        theirs = self.size_of(who)
        if mine is None or theirs is None:
            return True
        return order.index(theirs) - order.index(mine) <= self._MANOEUVRE_REACH

    def any_size_manoeuvre(
        self, *, on: int | None = None, until: When = When.ENCOUNTER
    ) -> Effect | None:
        """"You can bull rush targets of any size."

        Waives the printed size rule for this creature, which two feats
        grant and which `_manoeuvrable` is the one reader of. A labelled hold
        rather than a flag, so it suspends and lapses with everything else.
        """
        who = self._who(on)
        if who is None:
            return None
        return self.effect(_ANY_SIZE, on=who, until=until)

    def payment_window(self, *, per_turn: bool = False) -> object:
        """The window a "once per round" or "once per turn" payout sits in.

        Per *round* for two strikers and per *turn* for the rogue, and the
        difference is not cosmetic: a rogue may pay again on somebody
        else's turn, off an immediate action or an opportunity attack, and
        a per-round latch silently refused that. The initiative slot being
        played is what names a turn -- the round alone cannot, and the
        actor cannot either, because a solo with a second turn owns two
        slots. Lifted verbatim out of `features/strikers.extra_damage`,
        which is where that reasoning was written down.
        """
        fight = self.world.encounter
        if not per_turn or fight is None:
            return self.world.round
        return (self.world.round, fight.index)

    def latched(
        self, label: str, *, on: int | None = None, per_turn: bool = False
    ) -> bool:
        """Has that creature already spent this payout in the current window?

        **Moved out of a closure so two feats could be written.**
        `features/strikers.extra_damage` kept its latch in a local dict, so
        nothing outside could ask whether the striker had already paid --
        and "a second helping after an action point" and "pays the extra
        damage on a miss" are exactly that question from two sides. Both
        rows blamed a missing *announcement*, which was never the gap:
        `extra_damage` passes `detail=label` and the damage events carry
        it. #569.
        """
        from .components import Powers as _Powers

        who = on if on is not None else self.me
        known = self.world.get(who, _Powers)
        if known is None:
            return False
        return known.latched.get(label) == self.payment_window(per_turn=per_turn)

    def latch(
        self, label: str, *, on: int | None = None, per_turn: bool = False
    ) -> None:
        """Spend the payout for this window."""
        from .components import Powers as _Powers

        who = on if on is not None else self.me
        known = self.world.get(who, _Powers)
        if known is not None:
            known.latched[label] = self.payment_window(per_turn=per_turn)

    def unlatch(self, label: str, *, on: int | None = None) -> bool:
        """Hand the payout back, so it may be spent again this window.

        Answers whether there was one to give back, so a row paying for the
        privilege -- an action point, a daily use -- can tell a refund from
        a no-op rather than spending itself on nothing.
        """
        from .components import Powers as _Powers

        who = on if on is not None else self.me
        known = self.world.get(who, _Powers)
        if known is None or label not in known.latched:
            return False
        del known.latched[label]
        return True

    def lingers_label(self, label: str, *, on: int | None = None) -> bool:
        """Is a hold with this label standing on the creature?

        The reading half of a labelled `c.effect`, which rows have been doing
        by hand -- `any(e.label == X for e in world.effects.of(eid))` appears
        in several content files. One door, so a rename cannot leave half of
        them behind.
        """
        who = self._who(on)
        if who is None:
            return False
        return any(e.label == label for e in self.world.effects.of(who))

    def bull_rush(self, *, on: int | None = None) -> bool:
        """"Push the target 1 square, and shift into the vacated space."

        A standard action **every creature has**, which is why it is here and
        not on a row: 14 rows add to a bull rush -- its attack roll, its push
        distance, a trigger on it -- and none of them makes one, so what was
        missing was the manoeuvre rather than a verb. #501.

        Strength against Fortitude, and **no weapon modifiers**, which the
        card states and which is why this rolls `c.attack(self.str_, FORT)`
        longhand rather than going near a weapon.

        `as_="bull_rush"` is what the 14 modifiers gate on. It rides the
        attack context, declared in `resolve` beside the other shape keys.

        **"Impossible Push: if there's no square you can push the target
        into, your bull rush has no effect."** So the push is tried first and
        the shift follows only if the target actually moved -- a hit that
        could not move anybody is not a hit that moves the attacker.
        """
        who = self._who(on)
        if who is None or not self._manoeuvrable(who):
            return False
        if not self.attack(self.str_, Defense.FORT, on=who, as_="bull_rush"):
            return False
        # **The push is the clause a feat replaces**, so it is offered through
        # `instead_of`: two feats print "you can slide the target rather than
        # push it", and swapping the whole manoeuvre would cost it the shift.
        # `manoeuvre:bull_rush` is the ref those registrations name.
        # **How far, read rather than fixed at 1.** Five rows lengthen the
        # push -- a belt, a pair of boots, two monster traits and a racial
        # power -- and `Powers.extra_squares` is the store they write to,
        # keyed on this manoeuvre's own ref. `c.squares_for` is the read.
        #
        # **Both allowances are read before the push, and that is why they
        # can be read at all.** A row lengthening a bull rush fires on the
        # `Hit` this attack just emitted, which is over by the line above --
        # so a listener that wrote `extra_squares` during it is in the store
        # by now. A rider that tried to lengthen the push *after* the fact
        # would have nothing to lengthen, which is the shape p14383 was first
        # written in and the reason it pushed the wrong way.
        far = 1 + self.squares_for(MANOEUVRE_BULL_RUSH, 0)
        follows = 1 + self.squares_for(MANOEUVRE_BULL_RUSH_FOLLOW, 0)
        return bool(
            self.instead_of("push", lambda: self._shove(who, far, follows))
        )

    def _shove(self, who: int, far: int, follows: int) -> bool:
        """The push half of a bull rush: `far` squares, following `follows`.

        **One square at a time, not one push of `far`.** The printed rider on
        p14383 is "shifting into each square the target leaves", which a
        single long push cannot honour -- the attacker would have to cross
        squares the target was never in. Stepping also stops exactly where
        the target stops, which is the Impossible Push clause applied to
        every square rather than only the first.

        For the ordinary bull rush `far` and `follows` are both 1 and this is
        the printed sentence. They come apart on purpose: a belt lengthening
        the push does **not** let the attacker follow further -- the printed
        shift is one square and nothing on those items says otherwise -- so
        `far` can be 3 with `follows` still 1.
        """
        from .components import Position

        moved = False
        for step in range(far):
            was = self.world.get(who, Position)
            vacated = was.square if was is not None else None
            if not self.push(1, on=who):
                break
            after = self.world.get(who, Position)
            # **Impossible Push, per square.** "If there's no square you can
            # push the target into, your bull rush has no effect" -- a push
            # that returned true without moving anybody must not walk the
            # attacker forward either.
            if vacated is None or after is None or after.square == vacated:
                break
            moved = True
            if step < follows:
                self.shift(1, to=vacated)
        return moved

    def grab_attempt(self, *, on: int | None = None) -> bool:
        """The grab **anybody** may try, as opposed to one a row applies.

        `c.grab` is the applying half -- "the target is grabbed" on a card --
        and `i2393x1` records that it is "applied, not rolled and not
        measured". This is the elective manoeuvre: a standard action, a
        Strength attack against Reflex with no weapon modifiers, and a hit
        grabs. #501, #510.

        "You must have at least one hand free to make a grab attempt", which
        is read off `Gear` -- a creature with both hands full cannot try.
        """
        who = self._who(on)
        if who is None or not self._manoeuvrable(who):
            return False
        gear = self.world.get(self.me, Gear)
        if gear is not None and len(gear.held) >= 2:
            return False
        if not self.attack(self.str_, Defense.REF, on=who, as_="grab"):
            return False
        self.grab(on=who)
        return True

    def aid_attack(self, enemy: int, ally: int, *, until: When = When.EONT) -> Effect | None:
        """"That ally gains a +2 bonus to its next attack roll against the
        chosen enemy."

        **No roll.** The combat aid actions grant outright -- the DC-10-plus-
        half-level check is the *skill* version of aid another and is a
        different printed block, which is worth saying because the two get
        conflated and one of them would make this miss.

        Scoped to the one enemy, which is #471's machinery: a bare +2 to the
        ally's next attack would pay out against anything it swung at.
        `once=True` is "its next attack roll", and the duration is the
        **aider's** next turn, not the ally's -- the card says so and they
        are different clocks.

        **How much is read, not fixed at 2.** Seven rows raise it and none of
        them could reach a literal in here; `MANOEUVRE_AID` is the symbol and
        `c.change_amount` is the write. The read is on the *aider*, which is
        the creature whose rows say "you grant a +3 bonus" -- so it happens
        here rather than on the ally receiving it.
        """
        laid = self.bonus(
            "attack", self.amount_for(MANOEUVRE_AID, 2),
            on=ally, until=until, kind="power", once=True,
            when=lambda ctx: ctx.get("target") == enemy,
        )
        self.world.bus.emit(Aided(actor=self.me, ally=ally,
                                  kind_="aid_attack", enemy=enemy))
        return laid

    def aid_defence(self, enemy: int, ally: int, *, until: When = When.EONT) -> Effect | None:
        """"That ally gains a +2 bonus to all defences against the chosen
        enemy's next attack against it."

        The sibling of `aid_attack` and the same shape, scoped the other way
        round: the gate is on who is *attacking*, not who is being hit.
        `Defense.ANY` is "all defences", which #360 added for exactly this
        kind of line. The granted amount is read the same way, off
        `MANOEUVRE_AID`: f2056 raises every aid action at once and would
        otherwise have had to name two.
        """
        laid = self.bonus(
            Defense.ANY, self.amount_for(MANOEUVRE_AID, 2),
            on=ally, until=until, kind="power", once=True,
            when=lambda ctx: ctx.get("attacker") == enemy,
        )
        self.world.bus.emit(Aided(actor=self.me, ally=ally,
                                  kind_="aid_defence", enemy=enemy))
        return laid

    def aid_another(
        self,
        ally: int,
        skill: str = "athletics",
        *,
        auto: bool = False,
        until: When = When.EONT,
    ) -> bool:
        """"Make a check against DC 10 + half the ally's level. On a success
        it gains a +2 bonus to its next check with that skill."

        **The third aid action, and the one that rolls.** `aid_attack` and
        `aid_defence` grant outright -- those are the combat pair and they
        attack AC 10 -- while this one is the skill version and is a
        different printed block. The two get conflated, and conflating them
        is what would make this one free.

        `auto` is for the rows that print "you **successfully** use the aid
        another action": the success is the whole of what the power buys, so
        it is a parameter rather than a lucky roll.

        The DC is off the **ally's** level, not the caster's, which is the
        printed rule and the one a reader gets backwards: helping somebody
        far above you is harder, not easier.

        The granted amount comes off `MANOEUVRE_AID` like the other two, so
        a row raising "the bonus you grant" raises all three without naming
        them. `AID_CHECK` is the **other** number, added to the roll -- f3131
        prints both in one sentence and a single symbol could not have gone
        green for either half.
        """
        if not auto:
            dc = 10 + (self.world.get(ally, Stats) or Stats()).half_level
            # **Two symbols, summed.** `AID_CHECK` is what the aider brings
            # and `AID_RECEIVED` is what the creature being helped brings,
            # and they are different printed bonus types -- a feat's +5 and
            # an item's +2 do stack. Each takes the largest within itself;
            # a single max across both would have thrown one away.
            seen = {"skill": skill, "ally": ally}
            if not self.check(
                skill, dc,
                bonus=self.amount_for(AID_CHECK, 0, seen)
                + self.amount_for(AID_RECEIVED, 0, seen, who=ally),
            ):
                return False
        # **`skill:<name>`, not the bare name**, which is the key
        # `skills.modifier` reads: it totals `f"skill:{skill.lower()}"` and
        # `"skill"` and nothing else. Laid bare, this +2 was a modifier no
        # reader consulted -- `engine/CLAUDE.md` calls that the commonest
        # bug in this component, and it meant **the aid another action has
        # never granted anything** in any fight.
        #
        # Found by `c.bonus(once=)`'s new refusal (#544) raising on the key
        # during a pre-push wide sweep, which is a second argument for that
        # refusal: the dead key had been silent for as long as it existed.
        self.bonus(
            f"skill:{skill.lower()}", self.amount_for(MANOEUVRE_AID, 2),
            on=ally, until=until, kind="power", once=True,
        )
        # **After the grant, not before.** The event says the aid landed,
        # and a listener answering it may want to read what was laid.
        self.world.bus.emit(Aided(actor=self.me, ally=ally,
                                  kind_="aid_another"))
        return True

    def coup_de_grace(self, *, on: int | None = None) -> bool:
        """Finish a helpless creature. An automatic critical, and nothing added.

        Four rows across two monster batches asked for this, and every one of
        them would otherwise have spelled out the auto-crit rule in its own
        body. It is a rule of the game rather than a property of any power,
        so it lives here and they all get the same one.

        Three ways to come back False: the target is not actually helpless,
        which is the printed requirement and worth checking rather than trusting
        the caller; **the row declared no attack of its own**; or the attack
        missed, which it may.

        **"Regardless of the roll" licenses the critical, not the hit.** This
        forced `hit = True`, so a helpless creature could not be missed -- and
        it was the silently-false shape besides: `strike` was called and its
        answer overwritten, so the die it rolled decided nothing. You can miss a
        helpless creature; if you connect, it is a critical whatever the natural
        was. #250.

        **The flat 5d6 is gone, and the no-attack guard replaces it.** The 5d6
        had no basis in the rule; it stood in for the real finisher -- damage
        meeting the target's bloodied value -- on behalf of two callers that
        print no attack line and no damage line and would otherwise deal
        nothing. Camille's call on #250 was to disallow a no-attack power rather
        than invent damage for one.

        That also closes a **live crash**, which is the part worth knowing:
        `strike` raises for a row with no attack line, so those two rows raised
        `ValueError` the first time their target was genuinely helpless. The
        audit never saw it because the audit's target never is -- the helper
        refused on the helpless check and returned before reaching `strike`. So
        the guard has to come before `strike` and not inside it.
        """
        from .conditions import rules
        from .dsl import get
        from .query import active

        who = self._who(on)
        if who is None or not any(rules(c).helpless for c in active(self.world, who)):
            return False
        row = get(self.ref)
        if row is None or row.attack_of(self.branch) is None:
            return False
        result = self.strike(on=who, advantage=True)
        if not result.hit:
            return False
        result.critical = True
        return True

    def vulnerable(
        self,
        amount: int,
        dtype: DamageType | None = None,
        *,
        until: When = When.SAVE_ENDS,
        on: int | None = None,
        when: Callable[[dict[str, Any]], bool] | None = None,
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

        # **A scoped vulnerability goes somewhere else entirely.** The flat
        # dict is a running total with nowhere to record what the clause
        # applies to, and eleven rows print a scope -- "vulnerable 10 to the
        # <monster>'s attacks", "vulnerable 3 to weapon attacks". Those are
        # kept as triples and read in `resolve.deal_damage` beside immunity
        # and resistance, which already consult the same context. #471.
        if when is not None:
            entry = (dtype, amount, when)
            defences.vulnerable_when.append(entry)

            def lift_scoped() -> None:
                if entry in defences.vulnerable_when:
                    defences.vulnerable_when.remove(entry)

            # `on_suspend` only -- `Effects._lift` runs it on expiry too.
            return self.world.effects.apply(
                who, self.me, until, label=f"{self.ref} vulnerable when",
                on_suspend=[lift_scoped],
                on_resume=[lambda: defences.vulnerable_when.append(entry)],
                by=self.ref,
            )

        for kind in kinds:
            defences.vulnerable[kind] = defences.vulnerable.get(kind, 0) + amount

        def undo() -> None:
            for kind in kinds:
                left = defences.vulnerable.get(kind, 0) - amount
                if left > 0:
                    defences.vulnerable[kind] = left
                else:
                    defences.vulnerable.pop(kind, None)

        def redo() -> None:
            for kind in kinds:
                defences.vulnerable[kind] = defences.vulnerable.get(kind, 0) + amount

        # `on_suspend` rather than `on_end` -- see `Effects._lift`. Naming
        # `undo` in both lists would subtract the amount twice on an expiry
        # that followed a suspension, and leave the creature *resistant* to
        # the type it was vulnerable to.
        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} vulnerable",
            on_suspend=[undo], on_resume=[redo],
            by=self.ref,
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
            who, self.me, until, label=f"{self.ref} resist", on_end=[undo],
            by=self.ref,
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
            by=self.ref,
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

    def vulnerabilities(self, *, on: int | None = None) -> dict[DamageType, int]:
        """What the creature takes extra from, by type, right now.

        `c.resistances`' mirror, and missing for the same reason it was: "if
        it is already vulnerable, increase it" and "the target loses that
        vulnerability" both need the current number before a delta can be
        handed over, and **9 content sites reach past `Cast` into the
        `Defences` component** because this was not here. #391.

        Purely additive -- no existing row changes behaviour -- which is why
        it rides in a batch rather than warranting its own sweep.

        Does **not** unblock the write side. Eleven rows carry a marker for a
        gated or conditional `c.vulnerable(...)`; this is the reader, and
        `i1444p1`'s `c.is_vulnerable()` is the one marker it answers.

        A copy, and types the creature is not vulnerable to are left out.
        """
        from .components import Defences

        who = self._who(on)
        held = self.world.get(who, Defences) if who is not None else None
        return {t: n for t, n in (held.vulnerable if held else {}).items() if n}

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
            by=self.ref,
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
            and (keyword is None or keyword in self.keywords_of(p))
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
            # A conjuration's label is what it is called, not a ref. #580
            by=self.ref,
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
            by=self.ref,
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

    def blocks_entry(
        self, *, on: int | None = None, until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """"An enemy cannot enter this creature's space by any means."

        Eight stat blocks print that sentence word for word and it is the
        exact opposite of `c.shares_space` below, so it is laid the same
        way -- a `Mods` key with a duration rather than a movement mode,
        because being un-enterable is not a way of travelling.

        What it adds over the ordinary occupancy rule is the waivers:
        phasing through the creature, and the creature having been made
        shareable by something else. See `movement.blocks_entry` for what
        it deliberately does **not** beat, and why.

        Yours, so it defaults to the caster: every printed line of this
        shape is a trait about the creature carrying it.
        """
        who = on if on is not None else self.me
        return self.bonus("blocks_entry", 1, on=who, until=until, kind=self.ref)

    def may_enter(
        self,
        *,
        sizes: Sequence[Size] = (),
        side: str = "",
        on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """"Can enter enemies' spaces during its movement" -- the mover's
        permission, which is **not** `c.shares_space`.

        That verb is the mirror: *"anyone may stand in this creature's
        square"*, laid on the creature being entered. Laying it here opens
        the holder's own square to the whole board and still refuses it a
        step through anybody -- weaker and stronger than the card at once,
        which `m6654a1` drove and recorded. `movement.may_enter` has the
        measurement. #626.

        `sizes` and `side` are the narrowing `m5808a0` prints, *"the spaces
        of Medium or Small enemies"*, and they are **arguments rather than a
        `when=`** on purpose: the predicate needs the occupant's size and
        allegiance, which only the world can answer, and a `when=` gate sees
        the context alone. Built here, the world is in scope and the context
        carries just the two participants.

        Empty means every creature, which is what the other two cards print.
        """
        from .query import enemies

        who = on if on is not None else self.me
        wanted = tuple(sizes)
        want_side = side.lower()

        def allowed(ctx: dict[str, Any]) -> bool:
            them = ctx.get("occupant")
            if them is None:
                return False
            if wanted and self.size_of(them) not in wanted:
                return False
            if want_side:
                # Asked of the holder rather than of the caster: a trait
                # armed on somebody else is still that creature's
                # permission, and "enemies" means its enemies.
                foe = them in enemies(self.world, who)
                if want_side == "enemy" and not foe:
                    return False
                if want_side == "ally" and foe:
                    return False
            return True

        return self.bonus("may_enter", 1, on=who, until=until, when=allowed)

    def reshape_area(
        self,
        into: Callable[[Range], Range],
        *,
        ref: str = "",
        kinds: Sequence[str] = (),
        keyword: Keyword | None = None,
        on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """Replace the **shape** of another row's area, for as long as this lasts.

        `c.bonus("blast_size", n)` is the same arrangement one word smaller:
        it adds an `int` to the size, so it can grow a burst and can never
        make it a blast. That one word is the whole of #614's gap -- six
        cards turn a burst into a blast, a blast into a burst, or an area
        into a single square, and no integer says any of them.

        **`into` is a callable on the printed range, not a replacement
        `Range`.** `i2467p1` prints "its area changed to 1 square (*within
        the same range*)", so what it becomes is derived from what it was:
        the `within` belongs to the power, not to the wand. A literal could
        not say that, and the two cards that shrink a blast by two squares
        could not either.

        **Not `Range.alt` and not a header axis**, both of which were built
        and backed out on #614 before the cards were read properly.
        `Range.alt` + `branch` is "one row, two printed shapes" and 137 rows
        use it correctly; every card here alters a *different* row's area
        than its own, which `alt` cannot reach. A fourth header integer
        collided with `Cast.form` (polymorph) and `variant` (#479's clause
        substitution) -- one symbol, two meanings, which is the fault rather
        than the fix.

        Narrowed the way `_stretched`'s modifiers are, because "the next
        **area burst** power" is a gate and not a blanket:

        * `ref` -- one named row, which is `i1836x1`'s whole scope;
        * `kinds` -- the printed shapes it applies to, `("area_burst",)`;
        * `keyword` -- "an arcane close blast power".

        With none of the three it reshapes everything the creature throws,
        which no card prints; passing nothing is almost certainly a mistake
        and is left legal only because refusing it here would be a second
        opinion about what the cards say.

        **Read, never consumed, by `area_of`.** That function is a query --
        the renderer calls it to highlight squares and `_aimings` calls it
        per candidate origin -- so a one-shot must end itself on the
        `PowerUsed` it was waiting for rather than on being measured. See
        `i2467p1`.
        """
        from .dsl import REGISTRY

        who = on if on is not None else self.me

        def gate(ctx: dict[str, Any]) -> bool:
            if ref and ctx.get("power") != ref:
                return False
            if kinds and ctx.get("kind") not in kinds:
                return False
            if keyword is not None:
                row = REGISTRY.get(str(ctx.get("power") or ""))
                if row is None or keyword not in row.keywords:
                    return False
            return True

        return self.world.effects.apply(
            who, self.me, until, label=self.ref, by=self.ref,
            reshape=into, reshape_when=gate,
        )

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
            who, self.me, until, label=f"{self.ref} {name}", on_end=[undo],
            by=self.ref,
        )

    def lose_mode(
        self, name: str, *, until: When = When.EOTNT, on: int | None = None
    ) -> Effect | None:
        """Take a way of moving away for a while, and give it back.

        The exact mirror of `c.mode` above, including its `undo`: the
        printed sentence is "**loses** its fly speed until the end of its
        next turn", said by a creature paying for a finishing move with the
        thing that was keeping it out of reach.

        **Popped rather than set to 0, and the first draft had it the other
        way round.** 0 looks like the right spelling -- `dsl.Summon.modes`
        records "speed 0, fly 6" as a shape three blocks print, so the
        engine does use 0 to mean present-and-useless, and every other
        reader asks `modes.get(name)` for a truthy value.

        **`query.phasing` is the exception and it decides this.** It tests
        `"phasing" in mv.modes` -- membership, not the value -- so a
        phasing creature set to 0 would still be phasing and `m1032a1`'s
        clause would do nothing while reading as written. Making that
        reader consistent is the tidier change and it is **not** safe:
        `c.phasing` lays `mode("phasing", speed_of(...))`, which is 0 for
        an immobilised creature, so a creature that is phasing *and*
        immobilised would stop phasing. Popping needs no reader to change.

        The cost is that `c.mode(name, 2)` during the loss grants the mode
        outright rather than being capped by it, and `undo` then puts the
        original back over that grant. Two live effects on one mode is
        already ambiguous in `c.mode` and this does not make it worse; no
        card in the tree does it.

        `When.EOTNT` by default, because that is what the cards print.
        Returns `None` when the creature never had the mode, which is not a
        fault: "loses its fly speed" said by a grounded creature is a
        sentence about nothing.
        """
        from .components import Movement

        who = on if on is not None else self.me
        moves = self.world.get(who, Movement)
        if moves is None:
            return None
        had = moves.modes.get(name)
        if had is None:
            return None
        moves.modes.pop(name, None)

        def undo() -> None:
            moves.modes[name] = had

        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} lost {name}", on_end=[undo],
            by=self.ref,
        )

    def form(
        self,
        *,
        conditions: Iterable[Condition] = (),
        modes: dict[str, int] | None = None,
        until: When = When.ENCOUNTER,
        revert: ActionType | None = ActionType.MINOR,
        label: str = "",
        name: str = "",
    ) -> Effect:
        """Assume a shape: some conditions, some ways of moving, and a way out.

        A polymorph is not a stance -- you are not choosing between forms,
        you are in one and may step out of it -- so `revert` is what leaving
        costs rather than "taking another ends it".

        `name` is the word the card prints for the shape -- "rat", "hybrid",
        "guardian" -- and it is what makes the form *askable*. Without it a
        form is identified only by the effect label, which is the ref of the
        row that laid it, so "Requirement: must be in rat form" had nothing
        to read. 43 rows print that sentence. `query.in_form` is the reader
        and `c.in_form` the shorthand.

        Several at once is the ordinary case, not an edge: a card printing
        "human or hybrid form" on one row and "rat or hybrid form" on another
        means hybrid is both, so the names go in a set.
        """
        effect = self.world.effects.apply(
            self.me,
            self.me,
            until,
            label=label or self.ref,
            conditions=conditions,
            drop_cost=revert,
            by=self.ref,
        )
        if name:
            from .components import Shapes

            word = name.strip().lower()
            shapes = self.world.get(self.me, Shapes) or self.world.add(
                self.me, Shapes()
            )
            # Side state, so it lifts on a suspension and comes back -- the
            # same contract `c.ignores_difficult` and `c.vulnerable` keep.
            if word not in shapes.live:
                shapes.live.add(word)
                effect.on_suspend.append(lambda: shapes.live.discard(word))
                effect.on_resume.append(lambda: shapes.live.add(word))
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
            who, self.me, When.STANCE, label=label or self.ref, conditions=conditions,
            by=self.ref,
        )

    def cannot_shift(self, *, until: When = When.EONT, on: int | None = None) -> Effect | None:
        """Cannot shift. Still walks, which is why this is not `immobilized`.

        "Slowed and cannot shift" is one printed line in at least three classes,
        and until this existed the second half was quietly dropped.

        **Was `c.rooted`, which named a condition the rules do not have.** 4e has
        no rooted condition -- *Rooted* is a monster feature whose meaning varies
        from block to block -- so the chip read "rooted" to a player, and an author
        reading the verb would reasonably have assumed it implemented that feature.
        Camille's correction.

        The mirror is `c.no_walk`, which bars the walk and leaves the shift;
        `c.immobilized` is both.
        """
        return self.condition(Condition.CANNOT_SHIFT, until=until, on=on)

    def insubstantial(
        self,
        *,
        until: When = When.EONT,
        on: int | None = None,
        except_: tuple[DamageType, ...] = (),
    ) -> Effect | None:
        """Halves all damage taken. A property of the creature, not the damage.

        `except_` names the types it does not halve -- "takes half damage from
        any damage source, except those that deal force damage", which six
        stat blocks print. It goes in `Defences.half_except` rather than on
        the effect, and `query.takes_half` says why.

        The exception lifts on `on_suspend` and not `on_end`, so that the
        three cards printing *both* clauses -- an exception and "it loses this
        trait until the start of its next turn" -- do not leave an exception
        standing for a trait that is switched off.
        """
        held = self.condition(Condition.INSUBSTANTIAL, until=until, on=on)
        kinds = tuple(except_)
        if held is None or not kinds:
            return held
        who = held.owner
        from .components import Defences

        defences = self.world.get(who, Defences) or self.world.add(who, Defences())

        def lift() -> None:
            for kind in kinds:
                left = defences.half_except.get(kind, 0) - 1
                if left > 0:
                    defences.half_except[kind] = left
                else:
                    defences.half_except.pop(kind, None)

        def lay() -> None:
            for kind in kinds:
                defences.half_except[kind] = defences.half_except.get(kind, 0) + 1

        lay()
        held.on_suspend.append(lift)
        held.on_resume.append(lay)
        return held

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
            by=self.ref,
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
            by=self.ref,
        )

    def cursed(self, on: int | None = None) -> bool:
        """Has *this* caster cursed that creature?"""
        who = self._who(on)
        return who is not None and self.world.relations.holds(
            Relation.CURSED_BY, self.me, who
        )

    def grab(
        self, *, on: int | None = None, by: int | None = None, dc: int = 0
    ) -> Effect | None:
        """`by=` names the grabber when it is not the caster, as `c.mark`
        does: a summoned creature grabs on its own account, and hanging the
        relation on its summoner means nothing can read back what it holds.

        **`dc=` is the printed escape DC, and it replaces the grabber's
        defence rather than adding to it.** 58 rows print a flat number and
        53 of those print one matching neither the grabber's Fortitude nor
        its Reflex -- almost always lower -- so every one of those holds was
        3 to 7 points harder to escape than its card says. `grab_defence` is
        the additive key and a different sentence: "a bonus to your defences
        when preventing an escape from your grab".

        `0` means no printed DC, which is the common case and leaves
        `escape.attempt` computing the defence as before. A DC that is
        *another creature's defence* is not this -- that is
        `c.grab(dc_from=)`, its own one-row symbol, because `dc=int` could
        never satisfy it. #421.
        """
        who = self._who(on)
        if who is None:
            return None
        holder = self.me if by is None else by
        return self.world.effects.apply(
            who, self.me, When.ENCOUNTER, label=f"{self.ref} grab",
            relations=[(Relation.GRABBED_BY, holder, who)],
            escape_dc=dc,
            by=self.ref,
        )

    def dominate(
        self,
        *,
        on: int | None = None,
        by: int | None = None,
        until: When = When.SAVE_ENDS,
    ) -> Effect | None:
        """Dominate a creature, relation and condition together.

        **`Relation.DOMINATED_BY` had 15 readers and one writer.** Everything
        else that dominated went through `c.condition(Condition.DOMINATED, ...)`,
        and `relations.IMPLIES` maps relation to condition one way only -- so the
        condition was imposed and the triple was never filed, leaving every
        reader of the relation silently false. That included any target line
        narrowing to "a creature dominated by it", which could not be written at
        all: the pool was empty for a creature dominated by any ordinary means.

        Shaped exactly like `c.grab`, which has the same two halves, and `by=`
        names the dominator when it is not the caster for the same reason.
        `IMPLIES` supplies `Condition.DOMINATED`, so this lays one thing and
        gets both. #405.
        """
        who = self._who(on)
        if who is None:
            return None
        master = self.me if by is None else by
        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} dominate",
            relations=[(Relation.DOMINATED_BY, master, who)],
            by=self.ref,
        )

    def grabbing(self, *, of: int | None = None) -> list[int]:
        """Everything this creature is holding in a grab.

        The boolean form a `requires=` gate needs is `query.holds_somebody`,
        which takes `(world, eid)` -- a gate runs before there is a `Cast`.
        """
        return self.world.relations.targets(
            Relation.GRABBED_BY, self.me if of is None else of
        )

    def grabbed_by(self, *, on: int | None = None) -> list[int]:
        """Everyone holding that creature in a grab.

        Delegates to `query.held_by` so a `requires=` gate and a body read the
        same implementation. #362.
        """
        from .query import held_by

        who = self._who(on)
        return [] if who is None else held_by(self.world, who)

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
        until: When = When.EOTNT,
        when: Callable[[dict[str, Any]], bool] | None = None,
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

        `when` narrows it to particular openings -- `ctx["why"]` is the window's own
        reason ("moved away", "is a ranged power"), and `ctx["actor"]` is whoever
        would swing. Without it the only sayable sentence was "never provokes at
        all", which is why 13 rows carried a marker.
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
            if ev.provoker != me or (who is not None and ev.actor != who):
                return
            # **The gate is read here, inside the veto**, which is the only place
            # that knows what opened the window. 13 rows asked for it and they are
            # all of the shape "does not provoke *when you shift*" or "...from the
            # creature you marked" -- conditions on the opening, not on the
            # creature. Keys follow the convention `escape` and `skills` use: the
            # participants by name, plus the reason the window opened.
            if when is not None and not when(
                {"actor": ev.actor, "provoker": ev.provoker, "why": ev.why,
                 # How and by what means the provoker moved, for the rows that
                 # narrow by it. Empty for a window a move did not open. #301.
                 # The ctx key stays `kind`; the event field is `kind_` because a
                 # field named `kind` shadows `Event.kind`. Content rows read
                 # `ctx.get("kind")` and must not have to care.
                 "kind": ev.kind_, "mode": ev.mode}
            ):
                return
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
        but three rows had each written that listener out, and `c.cannot_shift`
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
            by=self.ref,
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
            who, self.me, until, label=f"{self.ref} swapped sight", drop_cost=revert,
            by=self.ref,
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
        self, squares_: int = 2, *, on: int | None = None, until: When = When.ENCOUNTER,
        when: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Effect | None:
        """How far this creature threatens for opportunity attacks.

        "It can make opportunity attacks against enemies within 2 squares"
        had no expression: the window was opened from a ring fixed at one.
        A held modifier, so "gains reach 2" can raise it too.

        **Two modifiers, and the flag is the one that makes it work.** This set
        `reach` alone and was therefore **inert**: `movement._threat` gates on
        `threatening_reach` first -- because a reach weapon must *not* extend the
        window, which is the printed rule and the whole of #306 -- and only then
        reads `reach`. So the gate was never satisfied, and `m4928a1` called this
        verb and threatened **one** square where its card says three. Measured:

            after c.threatens(3)   _threat = 1   reach=2  threatening_reach=0

        Both keys, because they answer different halves: the flag says this
        creature's window is not fixed at one, and `reach` says how far.
        """
        who = on or self.me
        # **`when=` is a passthrough, not a mechanism.** Both halves are
        # `bonus` calls and `bonus` has always taken a gate, so "against
        # bloodied creatures" and "while armed with its halberd" were sayable
        # one layer down and unsayable here. Three rows wanted it: one carried
        # `dropped=("c.threatens(when=)",)` and two more went in bare and
        # threatened unconditionally where their cards gate it. #425.
        #
        # It must reach **both** modifiers. Gating only `reach` would leave the
        # flag standing, and `movement._threat` reads the flag first -- so the
        # window would open at one square whenever the gate was false, which is
        # a different wrong answer rather than no answer.
        self.bonus("threatening_reach", 1, on=who, until=until, kind="untyped",
                   when=when)
        return self.bonus(
            "reach", max(0, squares_ - 1), on=who, until=until,
            kind="untyped", when=when,
        )

    def resist_forced(
        self, squares_: int = 1, *, on: int | None = None, until: When = When.ENCOUNTER,
        when: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Effect | None:
        """Shorten every push, pull and slide against this creature.

        "Moves 1 square fewer than the effect specifies." A held modifier
        rather than a watcher, because it applies to shoves from anywhere.

        Defaults to the caster rather than to `c.target`: every row printing
        this is describing itself.
        """
        # `when` reaches the shove's own gate: `movement._settle` reads `"forced"`
        # with `{"how": push|pull|slide, "power": ref}`, so "1 square fewer against
        # a *pull*" is sayable without a second key.
        return self.bonus(
            "forced", squares_, on=on or self.me, until=until, kind="untyped",
            when=when,
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
        # The creature pays its own, so `source` is itself and there is no
        # granter. A refusal here stops the surge and the heal below still
        # runs -- which is wrong, and is why the return is read.
        if not spend_surge(
            self.world, who, source=who, power="second-wind", healed=worth
        ):
            return False
        self.world.heal(who, who, worth)
        # **All four defences, not just AC.** The printed rule is "+2 to
        # all defences until the start of your next turn" and this gave
        # AC alone, so every creature that took a second wind has been
        # two points easier to hit on Fortitude, Reflex and Will since
        # the method was written. It also made one feat unwritable in a
        # second way: a card reading "+1 AC and +3 to the others" would
        # have to be written against the bug and would go to +5 AC the
        # day it was fixed.
        for defence in DEFENCES:
            self.bonus(defence, 2, until=When.SONT, on=who, kind="untyped")
        return True

    def total_defence(
        self,
        *,
        on: int | None = None,
        amount: int = 2,
    ) -> bool:
        """Hunker down: +2 to every defence until the start of your next turn.

        One of the basic actions anybody can take with a standard, and it did not
        exist -- which is why **nine content rows carry `c.total_defence()` as a
        marker** rather than a body ("you may instead take a total defence action",
        "...and gain the benefit of total defence"). They can be finished now.

        **Until the *start* of the next turn, not the end.** Checked rather than
        recalled, because I had it the other way round and a duration is exactly the
        silently-wrong kind of bug this component produces. Two independent sources
        agree it is the start, which also matches `second_wind` directly above --
        the same +2 to the same four defences for the same span. If the book says
        otherwise, this is the one line to change.

        All four defences, for the reason `second_wind` records: granting AC alone
        left every creature two points easier to hit on the other three, and made a
        card reading "+1 AC and +3 to the others" unwritable.

        **Announced, as `second_wind` is.** Eight rows print "when you take the
        total defense action" and this was the one implementation saying nothing,
        so the sentence had nowhere to hang. The bonus goes on first and the
        event second, so a row reacting to it sees the defences already raised.
        """
        from .events import TotalDefence

        who = on if on is not None else self.me
        for defence in DEFENCES:
            self.bonus(defence, amount, until=When.SONT, on=who, kind="untyped")
        self.world.bus.emit(TotalDefence(actor=who, amount=amount))
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
            by=self.ref,
        )

    def lend_augment(
        self,
        ref: str,
        cost: int,
        clause: Callable[[Cast], None],
        *,
        on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """"Your <power> gains the augmentable keyword": lend it a clause.

        Four feats print an Augment line on a card that prints none -- "when
        you would use it, you can spend 1 power point to <effect>" -- and the
        effect is the *feat's*, so it belongs neither in the power's header
        nor in its body.

        **Not `Power.augments`, and #507 is the record of why that mattered.**
        A declared augment is read by the action menu *before any body runs*,
        which is what lets one rewrite a target line or a reach. Threading
        the holder through that surface would make header data
        holder-dependent -- the thing `engine/CLAUDE.md`'s first rule
        protects -- and all four of these clauses are body-sayable anyway: a
        bonus, some damage, a teleport, a defence swap before the strike. So
        the lend is per-character state and the spend happens at body time,
        through the door `content.powers.augment` already owns.

        **The lent-to row must ask**, with `augment.lent(c)`. A lend on a row
        that never calls it is a modifier nothing consults.

        `clause` takes the `Cast` of the row being used, not of the feat --
        it is that row's use the effect joins.

        Yours, so it defaults to the caster.
        """
        from .components import Powers

        who = on if on is not None else self.me
        known = self.world.get(who, Powers)
        if known is None:
            return None
        entry = (cost, clause)
        was = known.lent_augments.get(ref)
        known.lent_augments[ref] = (*known.lent_augments.get(ref, ()), entry)

        def restore() -> None:
            if was is None:
                known.lent_augments.pop(ref, None)
            else:
                known.lent_augments[ref] = was

        return self.world.effects.apply(
            who, self.me, until,
            label=f"{self.ref} lends {ref} an augment at {cost}",
            on_end=[restore],
            by=self.ref,
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
            by=self.ref,
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

    def summon(
        self, ref: str, at: Square | None = None, *, team: Team | None = None,
        after: int | None = None,
    ) -> int:
        """Put a creature on the board mid-fight and give it a turn.

        The two halves are equally necessary: `loader.spawn` alone makes an
        entity that is not in the initiative order, so it stands there and
        never acts. "Splits into two" and every summoner print this.

        `after` is the printed line **"Initiative as conjurer"** -- the
        creature takes its turn on that creature's count rather than
        rolling one of its own. Pass `after=c.me` for the common case,
        which is an item conjuring a servant; 10 of the 12 blocks printed
        inside an item's own entry say it (#601), and `m3788a6` wanted the
        same thing from the other end. Without it the servant rolls, and
        a servant that acts in a different part of the round each fight is
        a different creature from the one the card describes.
        """
        from combat_engine.content import loader

        from .events import Summoned

        where = at or self._free_square_near(self.here)
        if where is None:
            return 0
        from .query import team as side_of

        # **An `x10_` ref is a character's summon, not a monster.** #459 built
        # that table, and its blocks derive their numbers from the summoner --
        # "HP your bloodied value", "Defenses your defenses + 2" -- so they
        # spawn through a path that is handed one. `loader.spawn` reads the
        # `monster` table and would raise on these.
        if ref.startswith("x10_"):
            made = loader.spawn_associate(self.world, ref, where, of=self.me,
                                          team=team)
        else:
            made = loader.spawn(
                self.world, ref, where,
                team=team or side_of(self.world, self.me) or Team.ENEMY,
            )
        if self.world.encounter is not None:
            self.world.encounter.join(made, beside=after)
        # `Summoned` was added because a row whose whole Effect is "you
        # summon X" left no trace in the log -- and then only the two
        # inline paths emitted it, never this one, which is the path every
        # row naming a creature by id takes. So the commonest summon in the
        # game still announced nothing.
        self.world.bus.emit(Summoned(actor=self.me, summon=made, ref=self.ref))
        return made

    # -- a second body you own ----------------------------------------------

    def companion(
        self, *, of: int | None = None, which: int | None = None
    ) -> int | None:
        """The companion this creature owns, if it has one on the board.

        The question 107 blocked rows were asking. A companion is not a
        conjuration -- it belongs to the character rather than to the power
        that made it, it persists, and it can be hit -- and it is not a
        servant either, because it never takes a turn of its own.

        `which` picks among several, for the one creature that can have two: a
        shaman who has used `p3839` chooses which spirit an attack is made from,
        and this is where that choice lands. Out of range or absent falls back to
        the first, which is the same answer this gave before there was a choice.
        """
        from .components import Companion

        owner = of if of is not None else self.me
        mine = [
            eid
            for eid in self.world.having(Companion)
            if self.world.get(eid, Companion).owner == owner
        ]
        if not mine:
            return None
        if which is not None and 0 <= which < len(mine):
            return mine[which]
        return mine[0]

    def call_companion(
        self,
        ref: str = "",
        at: Square | None = None,
        *,
        kind: str = "spirit",
        speed: int = 6,
        damage: str = "",
        second: bool = False,
    ) -> int:
        """Put your companion on the board, moving the one you have if any.

        "You can call it again" is printed on nearly every row that can
        dismiss one, and the printed reading is that you only ever have the
        one -- so calling again relocates rather than accumulating.

        `second=True` is the exception and there is exactly one: a shaman who
        has used `p3839` "can use your <call> power to conjure a **second**
        spirit companion". It adds rather than relocating, and leaves the
        standing one where it is. Everything downstream is already plural --
        `Cast.companions`, and `dsl.origins` since this change -- so the only
        thing that had to be said was "do not move the one I have".

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
        # The kind this call will actually produce, which is not always the
        # kind it was handed: the `comp:` branch below reads a bare
        # "spirit" as "beast", since that is the default and a beast's page
        # is what `comp:` refs are. Normalised **here** because the
        # relocate test needs the same answer the spawn will give, and
        # comparing against the raw argument would turn "call your beast
        # again" into a dismiss-and-respawn.
        want = "beast" if ref.startswith("comp:") and kind == "spirit" else kind
        standing = None if second else self.companion()
        if standing is not None:
            mine = self.world.get(standing, Companion)
            # **Both halves, and `ref` alone was not enough.** The comment
            # below describes this exact fault as fixed, and it was -- for
            # the case where the two refs *differ*. Two calls that both pass
            # no ref compare equal on `ref` and slipped straight through to
            # the relocate, keeping whatever `kind` was already standing.
            #
            # `cf:wizard-sha-ir-f1` is the live case. It calls
            # `c.call_companion(kind="familiar")` and the wizard ended up
            # owning a **spirit**, because something had already put a
            # refless companion there and this moved it. So a dozen wizard
            # rows opening `pet = c.familiar()` only ever found it through
            # that method's single-companion fallback, and the one row that
            # asks the question properly -- `f1334b`'s "your familiar must
            # be in its active state", which reads `kind == "familiar"` --
            # could never open its gate. #636.
            if mine is not None and mine.ref == ref and mine.kind == want:
                from .movement import place

                place(self.world, standing, where)
                return standing
            # **A different creature is a different companion.** This
            # relocated whatever was already standing and returned before
            # `ref`, `kind`, `speed` or `damage` were looked at -- those are
            # read only in the branches below. So "you gain a familiar" on a
            # shaman who already had a spirit moved the spirit and left it a
            # spirit, and `call_companion(ref="comp:...", kind="beast")` over
            # one left a spirit answering to `c.beast`. Harmless while
            # nothing read `kind`; a command action does, and would have
            # spent a standard rolling a beast's attack for a creature whose
            # page prints none.
            #
            # Dismissed rather than reconciled in place, because the numbers
            # are wrong too: a spirit's hit points are its shaman's surge
            # value and a beast's come off a formula in its own table, so
            # writing a new `kind` onto the standing body would leave a
            # beast-labelled creature with a spirit's block. "You can call it
            # again" is about calling *that* companion again.
            self.dismiss_companion()

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
            # `want` above, computed once so the relocate test and this
            # spawn cannot disagree about what kind is being made.
            kind = want
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
                    line.dice, self._bonus_of(line.bonus),
                    dtype=line.dtype, dtypes=line.dtypes, on=on,
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
        from .query import familiar_of

        return familiar_of(self.world, of if of is not None else self.me)

    def familiar_active(self, *, of: int | None = None) -> int | None:
        """The familiar, if the printed cards would call it active.

        *"Requirement: your familiar must be in its active state"*, which
        six rows across three files each asked by hand off
        `Companion.passive` -- one condition short, because a destroyed
        familiar keeps its `Companion` row and `passive` is not a field
        death touches. `query.familiar_active` is the one reader now; this
        is the `Cast` door onto it, for the rows that have a `Cast`. The
        other two are `requires=` gates that get `(world, eid)` and call
        the query directly.
        """
        from .query import familiar_active

        return familiar_active(self.world, of if of is not None else self.me)

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

    def familiar_mode(
        self,
        mode: str,
        *,
        of: int | None = None,
        past_death: bool = False,
        until: When = When.EONT,
    ) -> bool:
        """"Your familiar enters passive mode", and the way back out of it.

        Passive is off the board rather than a flag on something standing
        there: no square, so it cannot be targeted, nothing is adjacent to
        it and `Range(from_="companion")` measures from its owner instead.
        `Position` is kept rather than rebuilt because the size has to come
        back too.

        **`past_death=True` holds the mode rather than changing it**, which
        is `f2257`: *"when your familiar is destroyed, treat your familiar
        as in its active state until the end of your next turn, at which
        time the spirit fades away."* Nothing is switched -- the creature is
        a corpse and switching a corpse is the thing this verb cannot do,
        which is why the row was marked for a parameter here rather than for
        a verb of its own. What it lays is a span in which
        `query.familiar_active` skips its deadness test.

        On the **owner**, not the familiar: `resolve._die` tears down the
        effects a dead creature carries, so a waiver about being dead is the
        one thing that could not live there. And the span is an ordinary
        effect, so "the spirit fades away" is an ordinary turn boundary
        rather than a second mechanism. #620.
        """
        from .components import Companion
        from .movement import place

        if past_death:
            # Deliberately **not** gated on there being a familiar. The
            # printed trigger is the familiar being destroyed, and on a
            # board where the corpse has already been cleared away there is
            # nobody to find -- the row still granted its turn of grace, and
            # a gate here would have made it silently do nothing in exactly
            # the case it is written for.
            return self.bonus(
                "familiar_past_death", 1,
                on=of if of is not None else self.me, until=until,
            ) is not None

        who = self.familiar(of=of)
        if who is None:
            return False
        mine = self.world.get(who, Companion)
        want = mode == "passive"
        if mine.passive == want:
            return False
        # **Announced at both ends**, for `PowerRecharged`'s reason: a row
        # written against one direction would be right in half the game and
        # silently wrong in the other. #620.
        from .events import FamiliarMode

        if want:
            mine.stowed = self.world.get(who, Position)
            self.world.grid.lift(who)
            self.world.drop(who, Position)
            mine.passive = True
            self.world.bus.emit(
                FamiliarMode(actor=self.me, familiar=who, mode="passive"))
            return True
        back = mine.stowed or Position(square=self.here)
        anchor = self.world.get(mine.owner or self.me, Position)
        if anchor is not None:
            back.square = self._free_square_near(anchor.square) or back.square
        self.world.add(who, back)
        mine.stowed = None
        mine.passive = False
        place(self.world, who, back.square)
        self.world.bus.emit(
            FamiliarMode(actor=self.me, familiar=who, mode="active"))
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
            who, self.me, until, label=f"{self.ref} risen", on_end=[lay_down],
            by=self.ref,
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

    def no_surges(
        self, *, on: int | None = None, until: When = When.ENCOUNTER,
        when: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Effect | None:
        """"The target cannot spend healing surges."

        **Not `c.no_healing`**, which is what 14 rows had to reach for and is
        a strictly stronger line than any of their cards print: a creature
        that cannot surge can still be healed by a cleric. `SurgeSpent` is a
        `Decision` now, so this refuses the spend itself.

        `resolve.spend_surge` is the only place `Health.surges` is
        decremented, so one refusal covers all three routes a surge leaves by
        -- the second wind, a leader's power granting one, and a monster
        paying its own. Shaped exactly like `c.no_healing`, which refuses
        `Healed` the same way.

        **`when=` is for a card whose clause has no duration of its own**:
        "while taking this ongoing damage, the target cannot spend healing
        surges" (`m1882a4`). A `When` cannot say that -- the burn is a
        save-ends effect and a second save-ends refusal would be a *second*
        save, where the card means one condition. The gate reads the burn's
        own lifetime instead, which is the same idiom `c.conceal(when=)` and
        `c.threatens(when=)` use. #386.
        """
        from .events import SurgeSpent

        who = self._who(on)
        if who is None:
            return None

        def refuse(ev: SurgeSpent) -> None:
            if ev.actor != who:
                return
            if when is not None and not when({"actor": who}):
                return
            ev.cancel("cannot spend healing surges")

        return self.watch(
            SurgeSpent, refuse, until=until, window=Window.BEFORE, on=who,
            label=f"{self.ref} cannot surge",
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
        """Take a new initiative check and move in the order. Returns the roll.

        Announces itself like the other three d20 rerolls (#496). No row
        currently riders on a rerolled initiative, and it is announced
        anyway: a path that stays silent is the one a future rider fails on
        for no visible reason, and `drivers.py` asserts all four speak.
        """
        from .components import Initiative

        who = on or self.me
        enc = self.world.encounter
        if enc is None:
            return 0
        # `rolled`, not `roll`. `Initiative` carries `bonus`, `rolled` and
        # `scale`, so the old spelling fell through the `getattr` default and
        # every announced initiative reroll reported a "before" of 0 -- the
        # log half of this verb has never once said what the creature had.
        before = getattr(self.world.get(who, Initiative), "rolled", 0) or 0
        rolled = enc.reroll_initiative(who)
        self._announce_reroll("initiative", before, rolled, actor=who)
        return rolled

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

    def contract(
        self,
        ref: str,
        *,
        on: int | None = None,
        stage: int = 1,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """"...and the target contracts `x5_23`." 47 rows print this. #389.

        The ref is a disease's row in `game.db` -- `#389` built that table,
        and the ETL already resolves the printed name to the ref, so the
        clause an author writes is the clause the card prints.

        **The stage does not advance, and that is the card rather than a
        gap.** All 69 disease pages check at the *end of an extended rest*,
        and this engine has no extended rest -- `chargen` says persistence
        does not exist and `GET /api/day` is a deliberate `501`. So a disease
        caught in a fight stays at the stage it was caught at for the rest of
        that fight, which is what the printed rules say happens. `stage` is a
        parameter because two cards print "contracts stage 2" outright.

        What the state is *for* in an encounter is the rows that ask about it.
        `m5100a0`'s aura acts on "an enemy that has been exposed to a
        disease" and had nothing to read; `c.exposed` is that reader.

        Laid as an effect rather than written straight onto the component, so
        it suspends and resumes with everything else (#470) -- and so the
        `until` is visible, which matters because `When.ENCOUNTER` is a
        statement about this engine's horizon and not about the disease.
        """
        from .components import Afflictions

        who = self._who(on)
        if who is None:
            return None
        caught = self.world.get(who, Afflictions) or self.world.add(
            who, Afflictions()
        )
        if ref in caught.contracted:
            return None
        effect = self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} {ref}",
            # **Both lists, which is what side state needs.** `on_suspend`
            # alone lifted the infection and never gave it back -- the rule
            # that the undo goes in `on_suspend` and not also in `on_end` is
            # about `_lift` running it from both the suspend and the expiry
            # paths, and says nothing about coming back. `c.form` registers
            # the pair for the same reason. Caught by the driver asserting
            # resume, which is the half it is easy not to assert.
            on_suspend=[lambda: caught.contracted.pop(ref, None)],
            on_resume=[lambda: caught.contracted.__setitem__(ref, stage)],
            by=self.ref,
        )
        if effect is None:
            return None
        caught.contracted[ref] = stage
        return effect

    def expose(
        self,
        ref: str,
        *,
        on: int | None = None,
        stage: int = 1,
        bonus: int = 0,
    ) -> Effect | None:
        """"At the end of the encounter, the target makes a saving throw. On
        a failure, the target contracts `x5_59` (stage 1)." 19 rows. #515.

        The exposure is recorded **now** and settled **later**, which is the
        two-step the cards print and `c.contract` collapses: that verb
        catches the disease outright, and is right for the handful of rows
        whose card says so with no throw in between.

        **The throw rides on the effect's own ending**, which is why no new
        moment had to be invented. `Encounter.finish` calls
        `effects.end_encounter`, and that fires `on_end` for everything live
        -- so a `When.ENCOUNTER` effect laid here is handed the end of the
        fight for free.

        `on_end` is handed no reason, though, and fires for a death and a
        broken hold alike. `effects.closing` is the discriminator and exists
        for exactly this: `Cast.aftereffect` reads it to *avoid* firing on a
        torn-down board, and this reads it to fire **only** then. A creature
        that dies mid-fight drops its exposure without a throw, which is the
        right answer and falls out rather than being special-cased.

        The throw itself is `c.save(bare=True)` -- "a saving throw against
        nothing in particular", which is what this is: there is no save-ends
        effect to shake off, only a d20 against 10 with the creature's save
        bonuses on it.
        """
        from .components import Afflictions

        who = self._who(on)
        if who is None:
            return None
        caught = self.world.get(who, Afflictions) or self.world.add(
            who, Afflictions()
        )
        if ref in caught.contracted or ref in caught.pending:
            return None
        caught.pending[ref] = stage
        effects = self.world.effects

        def settle() -> None:
            caught.pending.pop(ref, None)
            # Only the fight ending settles it. A hold broken early, or a
            # body leaving the board, takes the exposure with it unsettled.
            if not effects.closing:
                return
            if not self.save(on=who, bare=True, against=ref, bonus=bonus):
                self.contract(ref, on=who, stage=stage)

        return effects.apply(
            who, self.me, When.ENCOUNTER,
            label=f"{self.ref} exposed {ref}",
            on_end=[settle],
        )

    def per_day_left(self, ref: str, limit: int) -> int:
        """How many of a daily allowance are left today, for this creature.

        "A number of times per day" is a count that outlives an encounter,
        and `Powers.used` is not it -- both rests clear that, so a row
        counting against it is once per fight. `story.Sheet.per_day` is the
        real counter and its own note says "the rows still have to read it";
        this is the reading, off the board-side mirror.

        `limit` is what the card prints, because the card is the only place
        it is stated and it is often a modifier rather than a constant.
        """
        from .components import Powers

        known = self.world.get(self.me, Powers)
        if known is None:
            return limit
        return max(0, limit - known.per_day.get(ref, 0))

    def spend_per_day(self, ref: str, limit: int) -> bool:
        """Take one from a daily allowance. False when none is left.

        Returns whether the spend happened, so a row can gate the thing it
        was paying for -- and a row that ignores the answer has bought
        something for free, which is why this is not a bare increment.
        """
        from .components import Powers

        if self.per_day_left(ref, limit) <= 0:
            return False
        known = self.world.get(self.me, Powers) or self.world.add(
            self.me, Powers()
        )
        known.per_day[ref] = known.per_day.get(ref, 0) + 1
        return True

    def charge_left(self, key: str, limit: int = 1) -> int:
        """How much of a per-encounter charge is left, for this creature.

        A charge is a resource a row holds **across uses within one fight**
        and which is not the row's own use: the warlock's pact boon is the
        shape, one charge, spent to buy a rider and handed back on a cursed
        kill.

        **`Powers.used` is not it, and the reason is worth knowing before
        reaching for it.** A trait is `action=NONE` with no declared
        trigger, so `turns.arm_traits` calls `dsl.use(..., spend=True)` on
        every one at the start of a fight -- which means a trait declared
        `usage=ENCOUNTER` has its single use **spent at arming**, before
        round 1. Seven rows were written against that use and none of them
        could ever spend it. #529.

        `key` is a `<ref>:<what>` string the owning row coins, so two
        resources on one row stay apart and nothing collides with a real
        ref. `limit` is what the card prints, as `c.per_day_left` takes it.
        """
        from .components import Powers

        known = self.world.get(self.me, Powers)
        if known is None:
            return limit
        return max(0, limit - known.charges.get(key, 0))

    def spend_charge(self, key: str, limit: int = 1, *, on: int | None = None) -> bool:
        """Take one from a per-encounter charge. False when none is left.

        Returns whether the spend happened, so the row can gate what it was
        paying for -- and that False **is** the printed "if you spend" on
        every card of this shape. A row ignoring the answer has bought
        something for nothing, which is why this is not a bare increment.
        """
        from .components import Powers

        who = self.me if on is None else on
        known = self.world.get(who, Powers)
        if known is not None and known.charges.get(key, 0) >= limit:
            return False
        known = known if known is not None else self.world.add(who, Powers())
        known.charges[key] = known.charges.get(key, 0) + 1
        return True

    def restore_charge(self, key: str, *, on: int | None = None) -> bool:
        """Hand a spent charge back. False if none had been spent.

        The inverse of `c.spend_charge`, and the same shape as
        `c.restore_use` beside it: False when there was nothing to give
        back, which is the Requirement these lines print.
        """
        from .components import Powers

        who = self.me if on is None else on
        known = self.world.get(who, Powers)
        if known is None or known.charges.get(key, 0) <= 0:
            return False
        known.charges[key] -= 1
        self.world.bus.emit(Note(text=f"{who} regains a charge of {key}"))
        return True

    def exposed(
        self, ref: str = "", *, on: int | None = None, pending: bool = False
    ) -> bool:
        """Has this creature caught a disease -- that one, or any?

        With no ref it answers "any", which is what `m5100a0`'s aura asks and
        the commoner of the two printed questions.

        `pending=True` asks the **other** printed question instead: is a
        throw still owed on it. The two are different states on different
        dicts and a card that says "exposed" sometimes means either, so this
        makes a row say which rather than guessing -- the parameter name the
        tree's own marker asked for. #515.
        """
        from .components import Afflictions

        who = self._who(on)
        if who is None:
            return False
        caught = self.world.get(who, Afflictions)
        if caught is None:
            return False
        held = caught.pending if pending else caught.contracted
        if not held:
            return False
        return bool(held) if not ref else ref in held

    def forbid(
        self,
        ref: str = "",
        *,
        keyword: Keyword | None = None,
        lacking: Keyword | None = None,
        usage: Usage | Sequence[Usage] | None = None,
        attacks_only: bool = False,
        on: int | None = None,
        until: When = When.SAVE_ENDS,
    ) -> Effect | None:
        """Take a row away for a while. "Loses the ability to use ..."

        Not the same as spending it: the creature still has the row and
        simply cannot reach it, so it comes back when the effect ends.

        **Three sentences, and two of them are opposites.** Seven rows carried
        `c.forbid(keyword=)` as one marker and the cards read:

            keyword=   "cannot use powers that HAVE the polymorph keyword"
                       -- two items, imposed on a target, save ends.
                       `p12344`'s "cannot teleport" is the same sentence
                       about a different keyword.
            lacking=   "can't use weapon or implement attack powers that
                       LACK the beast form keyword" -- four form rows,
                       self-imposed, lasting as long as the shape.

        They are kept as two arguments and two sets rather than one inverted
        into the other, because **both can be true of one creature at once**
        and a single set could not say which direction each entry meant.

        `lacking=` also writes the printed exception: *"although you can
        sustain such powers"*. Every row the creature currently has standing
        is recorded as sustainable at the moment the restriction lands, so
        changing shape does not cancel the zone it was holding. A refusal
        written without that is the half most easily dropped and the one
        that would be most visible in play.

        **A fourth sentence names a whole usage category**, which no amount
        of refs could say: *"the target can't use encounter powers until the
        end of its next turn"* (`m5719a5`) and *"the target cannot use
        encounter or daily attack powers"* (`m5559a4`). `usage=` takes one
        or several, and `attacks_only=True` is that second card's narrowing
        -- an attack power being one whose header declares an `Attack`.

        The narrowing is a second set on `Powers` rather than a flag beside
        the first, the same argument as above: both sentences can be true of
        one creature at once, and one set with a flag could not say which
        entry the flag belonged to.

        **Not the same axis as an action category.** `m5948a5`'s "cannot
        take standard actions" is about what the creature may *do*, not
        which of its rows it may reach, and its docstring called the two
        "the identical missing capability". They are not: a creature barred
        from standard actions may still use a minor-action encounter power.
        That row keeps its own marker.

        #487, #613.
        """
        from .components import Powers

        who = self._who(on)
        if who is None:
            return None
        known = self.world.get(who, Powers)
        if known is None:
            return None
        usages = (
            () if usage is None else
            (usage,) if isinstance(usage, Usage) else tuple(usage)
        )
        if not ref and keyword is None and lacking is None and not usages:
            return None

        undo: list[Callable[[], None]] = []
        label = (f"{self.ref} forbids "
                 f"{ref or keyword or lacking or usages[0].value}")
        if ref:
            undo.append(lambda: known.forbidden.discard(ref))
        if keyword is not None:
            undo.append(lambda: known.forbidden_keywords.discard(keyword))
        if usages:
            barred = (known.forbidden_attack_usages if attacks_only
                      else known.forbidden_usages)
            # **Only what this call added.** A second restriction standing
            # over the first must not take the first's categories away when
            # it ends, which `discard` of the whole tuple would do.
            fresh = tuple(u for u in usages if u not in barred)
            undo.append(lambda: barred.difference_update(fresh))
        standing: set[str] = set()
        if lacking is not None:
            # What is already running is exempt, read **now** rather than when
            # the refusal is asked: the card says you may sustain "such
            # powers", meaning the ones you were already sustaining, not any
            # power you happen to have standing later.
            standing = {
                e.label.split()[0]
                for e in self.world.effects.of(who)
                if e.label and e.label.split()[0] in known.all
            }
            undo.append(lambda: known.required_keywords.discard(lacking))
            undo.append(lambda: known.sustainable.difference_update(standing))

        # The effect first. Adding to `forbidden` before it exists meant a
        # caller that swallowed the raise left the row taken away with
        # nothing alive to ever give it back.
        effect = self.world.effects.apply(
            who, self.me, until, label=label, on_end=undo,
            by=self.ref,
        )
        if effect is None:
            return None
        if ref:
            known.forbidden.add(ref)
        if keyword is not None:
            known.forbidden_keywords.add(keyword)
        if usages:
            (known.forbidden_attack_usages if attacks_only
             else known.forbidden_usages).update(usages)
        if lacking is not None:
            known.required_keywords.add(lacking)
            known.sustainable |= standing
        return effect

    def rolls_with(
        self,
        ref: str,
        ability: Ability,
        *,
        on: int | None = None,
        until: When = When.ENCOUNTER,
        when: Callable[[Any, int], bool] | None = None,
    ) -> Effect | None:
        """Make a named row attack with a different ability.

        "You may use Dexterity instead of Strength with any power
        associated with this feat" -- sixteen feats print a line of this
        shape and none could be written, because the ability a row attacks
        with is **header data**: one `Attack` object, fixed at import, and
        shared by every creature that ever holds the row. A feat cannot
        edit it without editing it for everybody.

        So the swap is recorded against the creature instead, and
        `Attack.ability_for` reads it before the header. The row is
        untouched and any number of characters may roll it differently.

        `when` is a `(world, eid)` predicate for a swap that only holds
        sometimes -- "when the weapon is thrown", "while wielding a bow".
        Those read what is in hand, which is a fact about the creature, so
        they can be answered here; a condition about the *attack in
        flight* cannot be, and wants a different mechanism.

        `until=When.ENCOUNTER` because the usual caller is a feat arming at
        the start of a fight, which is as permanent as this engine gets.
        """
        from .components import Powers

        who = self._who(on)
        if who is None:
            return None
        known = self.world.get(who, Powers)
        if known is None:
            return None
        entry = (ability, when)
        # The effect first, as `forbid` does: adding the swap before it
        # exists left a row rolling the wrong ability with nothing alive to
        # ever put it back.
        effect = self.world.effects.apply(
            who, self.me, until,
            label=f"{self.ref} rolls {ref} with {ability.value}",
            on_end=[lambda: _drop_roll(known, ref, entry)],
            by=self.ref,
        )
        if effect is None:
            return None
        known.rolls.setdefault(ref, []).insert(0, entry)
        return effect

    def change_dice(
        self,
        ref: str,
        dice: str,
        *,
        on: int | None = None,
        until: When = When.ENCOUNTER,
        when: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Effect | None:
        """Make a named row roll different dice.

        The sibling of `rolls_with` above and the same argument: the die a row
        rolls is written into its **body**, so "you add 1d10 to the roll,
        rather than 1d6" had nothing to change and 21 rows print a sentence of
        that shape. Recorded against the creature, so the row is untouched and
        any number of characters may roll it differently.

        **A row must read it to be changed**, with `dice_for` -- the same
        arrangement `Attack.ability_for` has with `rolls`. A `change_dice` on a
        row whose body still hard-codes its die is a modifier nothing
        consults, which is this component's commonest bug.

        `when` is a **context** predicate rather than `rolls_with`'s
        `(world, eid)` one, because these clauses narrow by what is being
        rolled -- "on a Nature check", "with a bow" -- and the row doing the
        rolling is the only thing that knows. It passes what it knows to
        `dice_for`.
        """
        from .components import Powers

        who = self._who(on)
        if who is None:
            return None
        known = self.world.get(who, Powers)
        if known is None:
            return None
        entry = (dice, when)
        effect = self.world.effects.apply(
            who, self.me, until,
            label=f"{self.ref} rolls {ref} as {dice}",
            on_end=[lambda: _drop_dice(known, ref, entry)],
            by=self.ref,
        )
        if effect is None:
            return None
        known.dice.setdefault(ref, []).insert(0, entry)
        return effect

    def change_amount(
        self,
        ref: str,
        amount: int,
        *,
        on: int | None = None,
        until: When = When.ENCOUNTER,
        when: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Effect | None:
        """Make a named mechanic hand out a different number.

        The third sibling of `change_dice` and `extend_move`, and the same
        argument a third time: the size of what a mechanic grants is written
        **inside its own body**, so "you grant a +3 bonus, rather than the
        normal +2" had nothing to change.

        Aiding another is where it was first needed. `MANOEUVRE_AID` is the
        symbol, and seven rows raise it -- three monster traits to +3, a feat
        and an item to +4, another feat and a racial power to +3.

        **A row must read it to be changed**, with `amount_for`. The same
        arrangement, and the same commonest bug: a `change_amount` on a
        mechanic whose body still hard-codes its number is a modifier nothing
        consults.

        **Defaults to the caster**, like `extend_move` and unlike
        `change_dice`. Every card printing this is about what *you* grant --
        "you grant a +3 bonus" -- where a die may belong to somebody else's
        power.
        """
        from .components import Powers

        who = self.me if on is None else on
        known = self.world.get(who, Powers)
        if known is None:
            return None
        entry = (amount, when)
        effect = self.world.effects.apply(
            who, self.me, until,
            label=f"{self.ref} makes {ref} grant {amount}",
            on_end=[lambda: _drop_amount(known, ref, entry)],
            by=self.ref,
        )
        if effect is None:
            return None
        known.amounts.setdefault(ref, []).append(entry)
        return effect

    def amount_for(
        self,
        ref: str,
        default: int,
        ctx: dict[str, Any] | None = None,
        *,
        who: int | None = None,
    ) -> int:
        """How big a number this mechanic hands out, after anything raising it.

        The read half of `change_amount`. `default` is what the rules print,
        so `aid_attack` asks `c.amount_for(MANOEUVRE_AID, 2)` and keeps
        working for everybody with nothing changing it.

        **The largest wins**, where `dice_for` takes the first that matches.
        An ally benefits from one aid per attack, so two rows raising the
        same grant are not additive and the better applies -- and taking the
        first would have made the answer depend on the order the effects were
        laid, which is not a rule anybody printed.

        `who` reads somebody else's store, for the one shape where the
        number belongs to the creature being *helped* rather than the one
        helping: "Heal checks made to aid you gain a +2 item bonus" is a
        fact about you that the aider has to find.
        
        **The body moved to `query.granted_amount`**, which sits below both
        this and `resolve.py`. `resolve._mark_penalty` asks the same
        question and holds no `Cast`, and repeating the four lines there is
        a second reader of one store -- the shape `Weapon.hands` drifted
        into (#562). One reader, two callers.
        """
        from .query import granted_amount

        return granted_amount(
            self.world, self.me if who is None else who, ref, default, ctx,
        )

    def pre_empt(
        self,
        ref: str,
        what: str,
        clause: Callable[[Any], Any],
        *,
        on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """"When you use <row>, you can X **instead of** Y."

        `what` names the clause being replaced, not the row -- `"pull"`,
        `"shift"`, `"temp_hp"` -- and the row has to read it with
        `instead_of`. That is the same deal `change_dice` makes, and its
        docstring says why it has to be this way: replacing the whole body
        of a row that does two things throws the other one away. `p5330`
        pulls *and* damages, and "slide instead of pulling" must not cost
        it the damage.

        **Nothing is asked here and nothing is asked in the body.** Each
        registration becomes its own entry in the action menu -- see
        `Powers.pre_empts` -- because a question put halfway through a body
        cannot be clicked on a card and cannot be scored by `policy/`.

        Call it once per candidate ref: a feat says "your covenant
        manifestation" and cannot know which of the two the character took.
        Nothing checks possession, because a feat lists rows the character
        may not have and a registration against a row never used never
        fires.

        Yours by default, like the rest of this family.
        """
        from .components import Powers

        # `_who` would resolve to the *target*, and these are armed by a
        # feat on its own character with nothing targeted -- the
        # `as_basic` convention rather than the `forbid` one.
        who = on if on is not None else self.me
        known = self.world.get(who, Powers)
        if known is None:
            return None
        entry = (clause, self.ref)
        key = (ref, what)
        # The effect first, as `forbid` and `rolls_with` do: registering
        # before it exists left a clause substituted with nothing alive to
        # ever put it back.
        effect = self.world.effects.apply(
            who, self.me, until,
            label=f"{self.ref} pre-empts {ref} {what}",
            by=self.ref,
        )
        if effect is None:
            return None
        known.pre_empts.setdefault(key, []).insert(0, entry)
        # Side state, so it lifts and comes back with the effect (#470). A
        # suspended registration must not keep offering its menu entry:
        # the option would still be clickable and would then run a clause
        # the character has temporarily lost.
        #
        # `on_suspend` **only**, never `on_end` as well. `Effects._lift`
        # runs this list from both the suspend path and the expiry path,
        # and its own note says why: one undo named once, so a verb holding
        # side state cannot subtract twice.
        effect.on_suspend.append(
            lambda: _drop_entry(known.pre_empts, key, entry)
        )
        effect.on_resume.append(
            lambda: known.pre_empts.setdefault(key, []).insert(0, entry)
        )
        return effect

    def substitutions(self, ref: str = "", *, of: int | None = None) -> list[str]:
        """Every clause substitution registered against a row, in menu order.

        One entry per `(what, clause)` pair, labelled with the ref of the
        row that registered it. The index into this list **plus one** is the
        `variant` an `Action` carries; 0 is always the card as printed.

        Flat rather than a product of the clauses: two feats replacing one
        clause are a choice among them, and no card in the corpus asks for
        two substitutions at once.
        """
        from .components import Powers

        who = self.me if of is None else of
        known = self.world.get(who, Powers)
        if known is None:
            return []
        want = ref or self.ref
        return [
            source
            for (on_ref, _what), entries in sorted(known.pre_empts.items())
            if on_ref == want
            for _clause, source in entries
        ]

    def instead_of(
        self, what: str, default: Callable[[], Any], *, on: int | None = None
    ) -> Any:
        """Run whatever this use substituted for this clause, or the clause.

        The read half of `pre_empt`, called inside the row being changed:

            c.instead_of("pull", lambda: c.pull(1, on=c.target))

        and the clause a feat registered is handed that same `Cast`:

            c.pre_empt("p5330", "pull", lambda using: using.slide(1))

        `default` is what the card prints, so the row keeps working
        unchanged for everybody who has nothing registered -- the contract
        `dice_for` holds. `on` names the creature the clause is about when
        that is not the row's current target.

        Reads `c.variant`, which `dsl.use` settled from the chosen menu
        entry **before** the body ran. So a row whose body runs once per
        target substitutes for every one of them without asking again,
        which is the bug a mid-body prompt would have had.
        """
        from .components import Powers

        # A fast path and **not** the guard: nearly every use in a fight is
        # variant 0, and this spares it building `flat`. Reverting it leaves
        # the driver green, because the range check below rejects 0 on its
        # own -- that is what actually enforces "variant 0 is the card as
        # printed", so do not read this line as the thing doing it.
        if not self.variant:
            return default()
        known = self.world.get(self.me, Powers)
        if known is None:
            return default()
        flat = [
            (on_what, clause)
            for (on_ref, on_what), entries in sorted(known.pre_empts.items())
            if on_ref == self.ref
            for clause, _source in entries
        ]
        if not 0 < self.variant <= len(flat):
            return default()
        picked_what, picked = flat[self.variant - 1]
        # The variant names one clause. Every *other* clause of the row is
        # still the printed one, which is what makes a row with two
        # substitutable clauses work at all.
        if picked_what != what:
            return default()
        # The using row's `Cast`, not the feat's. A substitution has to know
        # who is being hit, and the feat's own `c.target` went stale the
        # moment it finished arming -- the same reason `c.watch` hands its
        # callback the event.
        #
        # `on` overrides which creature that is, for a clause about somebody
        # other than the row's current target: `p2104`'s off-hand damage
        # lands on a second enemy the body picked, and a feat replacing it
        # has to be handed that one rather than the primary.
        was = self.target
        self.target = on if on is not None else was
        try:
            return picked(self)
        finally:
            self.target = was

    def instead_of_now(
        self, what: str, default: Callable[[], Any], *, on: int | None = None
    ) -> Any:
        """Offer a registered substitution **at the clause**, and run what is
        taken.

        The sibling of `instead_of`, for a clause that fires inside a watcher
        the row installed itself rather than from a body the menu reached.
        The invoker's covenant manifestation is the worked case: the row is
        used once at the start of a fight and all it does is install a
        `PowerResolved` watcher, so the push it later makes has no `Action`
        behind it and `Cast.variant` is 0 for ever.

        **This re-accepts the cost `instead_of` exists to avoid, knowingly.**
        A question asked inside a watcher is invisible to `policy/` -- the
        argument written three times over in `Action.augment`, `_variants`
        and `c.pre_empt`. What makes it acceptable here and not there: a
        manifestation is a *passive*, so there was never a menu entry whose
        score the substitution would have changed. The AI did not choose to
        manifest and cannot be asked to weigh manifesting differently.

        Do not reach for this when the row is clicked or offered by the
        dispatcher. `rt:r24-t0` looked like a watcher case and is not -- it
        carries `on=Trigger(Dropped, ...)`, so `Trigger._ask` offers its
        variants and `instead_of` reads them.

        `on` is the creature the clause is about, bound to `c.target` for
        the substitute's benefit. A watcher holds its subject in a closure
        and the clause cannot see one -- the marshal's bonus lands on
        whichever ally spent the action point, and a feat replacing it has
        to know which.

        Registration is the same `c.pre_empt(ref, what, clause)`; only the
        read differs.
        """
        from .components import Powers

        known = self.world.get(self.me, Powers)
        waiting = list(known.pre_empts.get((self.ref, what), ())) if known else []
        for clause, source in waiting:
            # Offered, never imposed: every card registering one of these
            # says "you can", so a declined offer leaves `default` running.
            if self.choose([source], f"{source} instead of {what}",
                           optional=True, decline=f"no, {what} as printed"):
                was = self.target
                self.target = on if on is not None else was
                try:
                    return clause(self)
                finally:
                    self.target = was
        return default()

    def retarget_defence(self, defence: Defense) -> bool:
        """Move the **triggering** attack onto another defence.

        **Named for the defence, because `c.retarget` means something else
        already.** Four rows mark `c.retarget()` for moving an attack onto a
        different *creature* -- `f3695`'s note calls that "a retarget rather
        than the `c.redirect` an interrupt row does with its own trigger".
        Calling this one `retarget` made all four report ready, which
        `todo.py` said on the first run after. The marker vocabulary already
        had the right name for this: the twelve rows here spell it
        `c.retarget_defence()`.

        "The attack targets Will instead", printed on the item blocks and
        powers that answer an `AttackDeclared`. `c.attacks_defence` is the
        standing form -- every attack you make, for a duration; this is the
        one in flight.

        **Only works from a row whose trigger declares `window=Window.BEFORE`.**
        `resolve.roll` is the resolve callback and reads `vs` off the event
        after the interrupt window closes, so a row offered in the ordinary
        window sets the field after it has been read and changes nothing.
        Returns False when there is no declared attack in hand, which is
        also what an author gets for forgetting the window. #509.
        """
        ev = self.trigger
        if ev is None or not hasattr(ev, "vs"):
            return False
        ev.vs = defence
        return True

    def leash(
        self,
        radius: int,
        *,
        to: int | None = None,
        square: tuple[int, int] | None = None,
        on: int | None = None,
        until: When = When.SAVE_ENDS,
    ) -> Effect | None:
        """Tether a creature: it may not get further than `radius` from
        something.

        "Cannot move more than 3 squares from the space it occupies",
        "cannot move more than 2 squares from a held creature". Fourteen rows
        print one, and the three near verbs are all wrong: `c.immobilized`
        and `c.no_walk` stop the creature dead, and nothing else measured
        distance from a remembered point.

        `to` names a creature, `square` a fixed point, and **neither given
        anchors it where it stands** -- which is the commonest printed form.
        A creature anchor moves with it, so a trap dragging its victim keeps
        the leash taut rather than snapping it.

        Read in `movement.reachable`, so a square beyond the tether is never
        offered rather than punished afterwards: these lines are
        restrictions, not penalties, and the UI and `policy/` both read that
        menu. #512.

        Defaults to `When.SAVE_ENDS`, which is what the cards print -- a
        tether is something you get out of, not something that times out.
        """
        from .components import Leash, Position

        who = self._who(on)
        if who is None:
            return None
        if to is None and square is None:
            at = self.world.get(who, Position)
            if at is None:
                return None
            square = at.square
        held = self.world.get(who, Leash) or self.world.add(who, Leash())
        before = (held.radius, held.to, held.square)
        held.radius, held.to, held.square = radius, to, square

        def undo() -> None:
            held.radius, held.to, held.square = before

        return self.world.effects.apply(
            who, self.me, until,
            label=f"{self.ref} leash {radius}",
            on_end=[undo],
            by=self.ref,
        )

    def attacks_defence(
        self,
        defence: Defense,
        *,
        from_: Defense | None = None,
        when: Callable[[dict[str, Any]], bool] | None = None,
        on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """Move this creature's attacks onto a different defence.

        "Your weapon attacks target Reflex instead of AC", printed on twelve
        rows across four fighter feats, an assassin feat and five item
        blocks.

        **The engine has always allowed this and the rows said it did not.**
        Their note reads *"`AttackDeclared.vs` is a field but `resolve.attack`
        reads its own local afterwards, so a listener rewriting it changes
        nothing"*, and `resolve.roll` has read `vs = declared.vs` since the
        commit whose comment says *"a row printing 'its attacks target Reflex
        instead of AC' set the field, changed nothing, and logged nothing"*.

        What is true, and is almost certainly how the wrong conclusion was
        reached: **an ordinary listener is too late.** `roll` is the resolve
        callback and runs after the interrupt window but before ordinary
        listeners, so a plain `c.watch` sees the event only once the defence
        has been read. This registers in `Window.BEFORE`, which is the whole
        of the difference and the reason to have a verb rather than twelve
        hand-rolled watches.

        `from_` narrows to attacks that *started* on a named defence, which
        three cards print. `when` reads the attack context, so "while you are
        insubstantial" and "with a weapon" are sayable. #509.
        """
        from .events import AttackDeclared, Window

        who = self.me if on is None else on

        def swap(ev: AttackDeclared) -> None:
            if ev.attacker != who:
                return
            # **The defence it started from**, which three of these cards
            # narrow on: "attacks against AC can instead be made against
            # Reflex", "a power that attacks Reflex may attack Fortitude
            # instead". A swap that fired whatever the row declared would
            # move an attack the card never mentions.
            if from_ is not None and ev.vs is not from_:
                return
            if when is not None and not when(getattr(ev, "ctx", None) or {
                "attacker": ev.attacker, "target": ev.target, "power": ev.power,
            }):
                return
            ev.vs = defence

        return self.watch(
            AttackDeclared, swap, until=until, window=Window.BEFORE,
            on=who, label=f"{self.ref} vs {defence.value}",
        )

    def waive(
        self,
        condition: Condition,
        *what: str,
        on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """Switch off part of what a condition costs, without lifting it.

        `c.waive(Condition.SQUEEZING, "attack", "halve_speed")` is "you take
        no penalty to attack rolls and move at full speed while squeezing".

        **Not `c.suppress`, and the difference is the whole reason this
        exists.** Suppressing squeezing would mean you are not squeezing --
        so you no longer fit in the space you squeezed into. Twelve rows
        print the other thing: still squeezing, and some of what it costs
        does not apply. A condition's cost is several knobs and the cards
        turn them one at a time.

        The words are `Rules` field names, and only the four a printed
        waiver ever names are accepted -- `attack`, `halve_speed`,
        `grants_ca`, `speed_cap`. `cannot_act` and the rest are not things a
        card relaxes, and accepting them would invite a row to try. An
        unrecognised word is a `KeyError`, which is the answer `c.within`
        and `c.grants_advantage` both give. #508.

        Defaults to the **caster**: every card printing this is about its own
        holder, and `c.surge_value` has the other bug on record.
        """
        from .components import Conditions
        from .conditions import _NEUTRAL

        unknown = [w for w in what if w not in _NEUTRAL]
        if unknown:
            raise KeyError(
                f"c.waive takes {sorted(_NEUTRAL)}, not {unknown[0]!r}: a"
                " condition's other rules are not things a card relaxes"
            )
        who = self.me if on is None else on
        held = self.world.get(who, Conditions) or self.world.add(who, Conditions())
        words = set(what)
        if not words:
            return None
        before = held.waived.setdefault(condition, set())
        added = words - before
        before |= words

        def undo() -> None:
            left = held.waived.get(condition)
            if left is not None:
                left -= added
                if not left:
                    held.waived.pop(condition, None)

        return self.world.effects.apply(
            who, self.me, until,
            label=f"{self.ref} waives {condition.value}",
            on_end=[undo],
            by=self.ref,
        )

    def extend_move(
        self,
        ref: str,
        squares_: int,
        *,
        on: int | None = None,
        until: When = When.ENCOUNTER,
        when: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Effect | None:
        """Make a named row move you further. `c.extend_move("p1449", 5)`.

        The sibling of `change_dice` and the same argument: the distance a
        row moves you is an **argument inside its own body**, so "one more
        square on every swordmage teleport" had nothing to change. Eleven
        rows print a sentence of that shape.

        **Not a second move laid beside the first.** Two hops of 1 and 8 are
        not one hop of 9 the moment anything is in the way, and that is the
        whole reason this is a modifier on the distance rather than another
        `c.teleport` -- `f1236`'s note said so before the verb existed.

        **A row must read it to be changed**, with `squares_for`, exactly as
        `change_dice` requires `dice_for`. A `extend_move` on a row whose
        body still hard-codes its distance is a modifier nothing consults,
        which is this component's commonest bug.

        `when` is a context predicate, so "if it ends next to a shrouded
        enemy" is sayable by the row that moves. #502.

        **Defaults to the caster, not to `c.target`.** Every card printing
        this is about your own move -- "one more square on every swordmage
        teleport you make" -- and the repo already has this bug on record
        once: `c.surge_value` fell through to the target and healed off the
        wrong creature's maximum while its docstring read as though it did
        not. `change_dice` still takes `_who`, which is right for it because
        a row may change the dice of somebody else's power.
        """
        from .components import Powers

        who = self.me if on is None else on
        known = self.world.get(who, Powers)
        if known is None:
            return None
        entry = (squares_, when)
        effect = self.world.effects.apply(
            who, self.me, until,
            label=f"{self.ref} moves {ref} {squares_:+d}",
            on_end=[lambda: _drop_squares(known, ref, entry)],
            by=self.ref,
        )
        if effect is None:
            return None
        known.extra_squares.setdefault(ref, []).insert(0, entry)
        return effect

    def extend_every(
        self,
        kind: str,
        squares_: int,
        *,
        on: int | None = None,
        until: When = When.ENCOUNTER,
        when: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Effect | None:
        """Lengthen **every move of a kind**. `c.extend_every("shift", 1)`.

        `extend_move` above keys on one row's ref, which is right for "this
        power teleports you further" and cannot say *any* of them. Eight
        rows print the other sentence -- "one extra square on every shift",
        "one more square on every swordmage teleport you make" -- and
        `f1393`'s note is the clearest statement of what was missing:
        *"both are distances a row names when it moves you; nothing
        lengthens one from the outside."*

        **Read by the movement verb, not by the row.** This is the one
        difference from `extend_move`, and it is what makes the kind
        knowable at all: a row calls `c.shift(2)` or `c.teleport(8)`, so
        the verb knows which kind this is and the row does not have to say.
        `c.squares_for` cannot do it -- twelve content sites call it as
        `c.squares_for(c.ref, 3)`, keyed on the ref by construction.

        So, unlike `extend_move`, **a row needs no change to be lengthened**
        and the usual warning is inverted: there is no "modifier nothing
        consults" hazard here, because `shift` and `teleport` consult it
        unconditionally.

        **It adds on top of `extend_move`**, for the same reason the entries
        within one ref add: two feats each granting a square grant two, and
        a row-specific square plus a kind-wide square is two squares.

        `c.shift(to=...)` is **not** lengthened. A named destination is an
        instruction rather than a distance -- "shift into the space it
        left" has no number to increase.

        Defaults to the caster, like `extend_move` and every movement verb
        beside it. Stored under the reserved `MOVE_KIND` key, so the gates,
        the durations and the removal all work unchanged.
        """
        return self.extend_move(
            MOVE_KIND + kind, squares_, on=on, until=until, when=when
        )

    def _stretch(self, mover: int, printed: int, dest: Square) -> int:
        """How far past its printed distance a move is about to carry.

        `c.extend_every` raises a **budget** and the decider need not spend
        it, so "did the creature take the extra square" is a question only
        the verb that offered the squares can answer -- it alone holds the
        print and the destination at the same moment. The answer rides out
        on `Moved.stretched_`; see that event's note for why it is a plain
        attribute and `f2459` for the card that wanted it. #572.

        `grid.distance`, which its own docstring calls "the **only** place
        the engine measures a distance" -- not `grid.between`, which takes
        two footprints rather than two squares. So this is **distance and
        not path cost**, which is the right half of the two: a square two
        away that cost three to enter through difficult terrain is not "one
        additional square" by any card's reading.

        Clamped at zero. A move shorter than its print spent none of the
        extra, and a negative number would read as a debt.
        """
        from .components import Position as _Pos
        from .grid import distance as _apart

        here = self.world.get(mover, _Pos)
        if here is None:
            return 0
        return max(0, _apart(here.square, dest) - printed)

    def _extra_every(self, mover: int, kind: str) -> int:
        """The kind-wide half of a move's distance, for `mover`.

        Deliberately not `squares_for`, which reads `self.me`: `c.shift(
        who=other)` lends a shift, and the squares belong to **whoever is
        moving**. Naming the attacker does not name the victim, and the
        same mistake is on record here for `c.basic` -- ten rows lent a
        swing that never happened.
        """
        from .components import Powers

        known = self.world.get(mover, Powers)
        if known is None:
            return 0
        # `power` is the row doing the moving, which is what makes the
        # narrowed cards sayable at all: four of the eight print "whenever
        # you teleport **with a swordmage power**" or "whenever you use a
        # martial encounter or daily power that allows you to shift", and
        # the gate needs the source row's own header to answer either.
        # `self.ref` is that row by construction -- a body calling
        # `c.shift` is the power granting the shift.
        seen = {"kind": kind, "who": mover, "power": self.ref}
        return sum(
            n
            for n, gate in known.extra_squares.get(MOVE_KIND + kind, ())
            if gate is None or gate(seen)
        )

    def squares_for(
        self, ref: str = "", default: int = 0, ctx: dict[str, Any] | None = None
    ) -> int:
        """How far this row moves this creature, after anything lengthening it.

        The read half of `extend_move`. `default` is what the card prints, so
        a row writes `c.teleport(c.squares_for(c.ref, 8))` and keeps working
        for everybody who has nothing changing it.

        **The entries add**, where `dice_for` takes the first that matches: a
        die is replaced and a distance is increased, so two feats each
        granting a square grant two. That is what the cards say and it is the
        one place these two verbs differ.
        """
        from .components import Powers

        known = self.world.get(self.me, Powers)
        if known is None:
            return default
        seen = ctx or {}
        extra = sum(
            n
            for n, gate in known.extra_squares.get(ref or self.ref, ())
            if gate is None or gate(seen)
        )
        return default + extra

    def dice_for(
        self, ref: str = "", default: str = "", ctx: dict[str, Any] | None = None
    ) -> str:
        """Which dice this row rolls for this creature, after any change.

        The read half of `change_dice`. `default` is what the card prints, so a
        row calls `c.roll(c.dice_for(c.ref, "1d6"))` and keeps working for
        everybody who has nothing changing it.
        """
        from .components import Powers

        known = self.world.get(self.me, Powers)
        if known is None:
            return default
        seen = ctx or {}
        for dice, gate in known.dice.get(ref or self.ref, ()):
            if gate is None or gate(seen):
                return dice
        return default

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
        when: Callable[[dict[str, Any]], bool] | None = None,
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
                # **The printed sentence this could not say.** Every word
                # above names a slice of the caster's own side, which is
                # right for "one ally gains combat advantage against the
                # target" -- and wrong for the other direction, where a
                # creature takes a drawback and *its enemies* are the ones
                # who gain. 8 monster rows print "grants combat advantage
                # to any enemy" (or "to all enemies"), and `m2330a2` was
                # written `to="team"` for want of this: 20 temporary hit
                # points and the penalty handed to its own allies.
                #
                # A specific enemy already worked -- 25 sites pass one by
                # id -- so the relation has always accepted enemies as
                # beneficiaries and only the side word was missing.
                "enemies": self.enemies(),
            }[to]
        if when is None:
            granted = self.world.effects.apply(
                who, self.me, until, label=f"{self.ref} advantage",
                relations=[(Relation.GRANTS_CA_TO, who, b) for b in beneficiaries],
                by=self.ref,
            )
        else:
            # **A gated grant cannot be a relation.** A `Relation` carries no
            # predicate, and `query.advantage` short-circuits `True` the moment it
            # holds, so there is nowhere for a condition to be asked. The gated form
            # therefore follows the pattern that function already uses for the
            # opposite sentence: a `Mod` read with `ca_ctx`, which is how
            # `no_advantage` and `unflankable` are written. 15 rows asked for this and
            # they are all narrow -- "grants combat advantage to you *while it is
            # bloodied*", "...to the ally you chose".
            #
            # The beneficiary list moves into the gate rather than being lost, so the
            # two forms answer "to whom" identically.
            allowed = set(beneficiaries)

            def gate(ctx: dict[str, Any], _w: Any = when, _a: Any = allowed) -> bool:
                return ctx.get("attacker") in _a and bool(_w(ctx))

            granted = self.world.effects.apply(
                who, self.me, until, label=f"{self.ref} advantage",
                mods=[(who, Mod(what="grants_ca_to", value=1, kind=self.ref,
                                label=self.ref, when=gate))],
                by=self.ref,
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

    def gains_advantage(
        self,
        when: Callable[[dict[str, Any]], bool],
        *,
        until: When = When.ENCOUNTER,
        on: int | None = None,
    ) -> Effect | None:
        """This creature has combat advantage whenever that is true of a swing.

        **The mirror of `grants_advantage` and a different sentence.** That one
        is about a creature: *it* grants advantage, so the relation and the
        modifier both sit on the creature granting it. Fifteen rows print the
        other side -- "you gain combat advantage against immobilized targets",
        "...with your cold powers against anything vulnerable to cold" -- and
        there is no creature to lay those on. The set is whatever happens to be
        immobilized at the moment of the swing, which is not knowable when the
        trait arms.

        So it lays a `Mod` on the **attacker**, and `query.has_combat_advantage`
        reads it there with the same `ca_ctx` the four existing routes get.
        `when` is required rather than defaulting to None: an ungated version of
        this is "you always have combat advantage against everything", which no
        card says and which would be a very quiet way to break every fight.

        The context carries `attacker`, `target` and `power`. The last is why
        these rows could not be written even once the gate existed -- "with your
        close blast powers" is a question about the row being used, and nothing
        passed one in. It is empty for a caller asking about a pair of creatures
        rather than a swing, so a gate wanting a keyword is correctly False
        there rather than accidentally true.
        """
        who = self._who(on)
        if who is None:
            return None
        return self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} gains advantage",
            mods=[(who, Mod(what="gains_ca_when", value=1, kind=self.ref,
                            label=self.ref, when=when))],
            by=self.ref,
        )

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
        label: str = "",
    ) -> Effect | None:
        """A numeric modifier with a duration.

        **`label` is for a body laying two PENALTIES from two different
        printed sources, and nothing else.** It defaults to this row's
        ref, which is what `Mods.total` buckets penalties by -- two
        penalties sharing a label do not add, the worse applies, which is
        4e's "two penalties from the same source" rule. Right for one row
        landing twice; wrong when one body pays two separate sentences.

        `m238a3` was the live instance: a zone laying a penalty for
        standing in it *and* a second for attacking somebody concealed by
        it. Both conditions hold at once whenever an enemy inside the fog
        attacks an ally inside it, the card means -4 there, and this
        returned -2 for as long as the row existed.

        **It does nothing for a bonus** and must not be reached for as if
        it did: bonuses bucket by `kind`, so two untyped ones already add
        and two of a type already collapse, both regardless of label. And
        it is **not** the credit mechanism `docs/AUTHORING.md` once said
        it was -- `audit._claimed` reads the *effect* label, which this
        does not touch, and under #550's convention the feat row is not
        fired at all so there is nothing to credit.

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
            what=key, value=value, kind=kind, when=when,
            label=f"{self.ref}:{label}" if label else self.ref,
            roll=(lambda: rng.roll(dice).total) if dice else None,
            dtype=types,
        )
        shown = f"+{dice}" if dice else f"{value:+d}"
        effect = self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} {key}{shown}", mods=[(who, mod)],
            by=self.ref,
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
            elif key == "skill" or key.startswith(("skill:", "ability")):
                # **A one-shot check bonus was spent by the next attack
                # roll too**, the same way the save was, and for the same
                # reason: the branch below took everything the three
                # tests above did not name. `skills.modifier` reads
                # `skill:<name>` and `skill`; `skills.ability_check`
                # reads `ability_check`. Seven sites in the tree carry
                # one, and two more hand-rolled the latch rather than
                # trust `once=`.
                #
                # Fifth time a branch of this method has spent a modifier
                # somewhere other than where it is read -- which is why
                # the `else` below no longer guesses.
                from .events import SkillCheck

                def spend_check(ev: SkillCheck) -> None:
                    if ev.actor == who:
                        self.world.effects.end(effect, "used")

                effect.subs.append(
                    self.world.bus.on(SkillCheck, spend_check, owner=who)
                )
            elif key == "forced":
                # **The shove is where a shove reduction is read**, inside
                # `ForcedMove`'s resolve callback, and two rows say so in
                # their own docstrings -- "spends the reduction on this
                # shove rather than on every one until the end of the
                # turn". Neither got it: `forced` fell through to the
                # attack-roll branch, so the reduction was spent by the
                # owner's next swing and stood for the second shove of the
                # window. Sixth instance of the same fault, and the last
                # one found by reading rather than by a row breaking.
                from .events import ForcedMove

                def spend_shove(ev: ForcedMove) -> None:
                    if ev.target == who:
                        self.world.effects.end(effect, "used")

                effect.subs.append(
                    self.world.bus.on(ForcedMove, spend_shove, owner=who)
                )
            elif key not in _SPENT_ON_ATTACK:
                # **Refused rather than guessed.** Every fix to this method
                # has been "add a branch for the key I just found", and the
                # `else` kept silently mis-spending the next one: a
                # `"forced"` or `"range"` or `"resist <type>"` one-shot was
                # ended by the owner's next *swing*, which is not where any
                # of them is read. `f3530` found the fifth instance and
                # could not write its row because of it.
                #
                # So an unrecognised key raises, naming itself, exactly as
                # a misused `dtype` does twenty lines above. A loud refusal
                # at authoring time is strictly better than a bonus spent
                # by the wrong roll, and it is what turned that misuse from
                # a bug into a typo. #544.
                raise ValueError(
                    f"c.bonus({key!r}, once=True) has no spend moment. "
                    "`once=` knows when these are read: "
                    f"{', '.join(sorted(_SPENT_ON_ATTACK))} (all consulted "
                    "before the roll, so the roll spends them), 'damage', "
                    "'save', a Defense, 'crit_range', and the check family "
                    "('skill', 'skill:<name>', 'ability_check'). For "
                    f"{key!r} there is no event to end the hold on, so it "
                    "would be spent by the next attack roll instead -- "
                    "which is the bug this refusal replaces. Lay it "
                    "without `once=` and end it yourself, or add the "
                    "branch here if the key has a moment."
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

    def my_weapon(self) -> Weapon | None:
        """The weapon **this row's item sits on**, or None.

        Factored out of `c.enhancement`, which needed exactly this and is
        now its first reader. The second is `i2842x1`, which prints "the
        proficiency bonus and enhancement bonus of this weapon" -- two
        columns off one object, so asking twice by two different routes
        was how the answers would have drifted apart.

        **Matched by `Weapon.item`, not by whatever magic is in hand.** A
        character carrying a magic sword and a magic bow has two, and the
        row belongs to one of them.

        `on=self.me`, not the default. `c.held` follows `c.target` like
        everything else that is about somebody else's body -- and this is
        about the caster's hand. Written without it first, and it returned
        1 for a +2 axe in silence, which is the fourth time this default
        has caught somebody on this project.
        """
        mine = self.ref.split("x")[0].split("p")[0]
        for w in self.held(on=self.me, what="magic"):
            if w.item == mine:
                return w
        return None

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
        own = self.my_weapon()
        if own is not None:
            return own.enhancement
        mine = self.ref.split("x")[0].split("p")[0]
        magic = self.held(on=self.me, what="magic")
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

    def revives_unless(self, *types: DamageType, on: int | None = None) -> None:
        """Say that this creature gets back up unless finished with `types`. #318.

        **Declaration only -- it implements nothing.** The row's own body is what
        keeps the creature alive, by watching its `Dropped` and healing inside that
        window, and it was already right. This records the *fact* so a policy can
        read it, because the scorer had no way to know the body on the floor was
        going to stand up: `threat_removed` skips anything at or below 0 hit points,
        so a troll lying at 0 was worth nothing to attack and the one row that ends
        it was never the best thing to do. Three of 24 level-10 fights ran to the
        40-round cap on exactly that, with the party healthy and the troll on 2 of
        109.

        Deliberately not a `Mod`: a modifier is a number read with a context, and
        this is a set of damage types. `Undying` holds it for the encounter.
        """
        from .components import Undying

        who = self._who(on)
        if who is None:
            return
        self.world.add(who, Undying(by=frozenset(types)))

    def _regen_suppressed(self, who: int, flag: str = "") -> Any:
        """A live "regeneration suppressed" hold on that creature, if any.

        `flag` names one regeneration's own hold; empty finds any of them,
        which is what `c.resume_regeneration` wants -- a card saying "its
        regeneration reactivates" does not name which clause switched it
        off.
        """
        for held in self.world.effects.of(who):
            if held.label == flag or (
                not flag and held.label.endswith(" regen suppressed")
            ):
                return held
        return None

    def regen_suppressed(self, *, on: int | None = None) -> bool:
        """Is this creature's regeneration switched off right now?

        The selector half, and the row printing it needs exactly this:
        `m2068a3` targets "one creature within 10 squares **whose
        regeneration is currently inactive**", so the body has to pick by
        the state rather than offer every ally and hope.
        """
        who = self._who(on) if on is not None else self.me
        return who is not None and self._regen_suppressed(who) is not None

    def resume_regeneration(self, *, on: int | None = None) -> bool:
        """"Its regeneration immediately reactivates." Switch it back on.

        The other side of `c.regeneration`'s `unless_damaged_by=` and
        `unless_struck_by=`: those lay a hold that the next tick consumes,
        and this ends it early so the next tick pays out instead.

        **Answers whether there was anything to resume**, which the one row
        printing this needs: `m2068a3` targets "one creature within 10
        squares **whose regeneration is currently inactive**", so a row
        that found nobody must not spend its minor action pretending
        otherwise.

        Ends every such hold on the creature rather than one, because a
        creature carrying two regenerations -- a printed line and a granted
        one -- has both switched off by the same blow, and the card says
        the regeneration reactivates rather than naming a clause.
        """
        who = self._who(on) if on is not None else self.me
        if who is None:
            return False
        found = False
        while (held := self._regen_suppressed(who)) is not None:
            self.world.effects.end(held, "its regeneration reactivates")
            found = True
        return found

    def regeneration(
        self,
        amount: int,
        *,
        until: When = When.ENCOUNTER,
        on: int | None = None,
        while_bloodied: bool = False,
        unless: Callable[[], bool] | None = None,
        unless_struck_by: str = "",
        unless_damaged_by: tuple[DamageType, ...] = (),
    ) -> Effect:
        """Heal this much at the start of each of that creature's turns.

        Written out by hand in eight files before this existed -- the same
        `TurnStart` watcher, the same `ev.ghost` guard, the same
        `ev.actor == me` test, eight times -- and `docs/AUTHORING.md` said
        regeneration was in the vocabulary while `grep` found one comment.

        `while_bloodied` is the commoner printed form of the two: a
        regenerating monster usually only does it while hurt.

        `unless` reads *state* at the moment of the tick, and is the other
        printed shape -- "if it starts its turn on the ground, its
        regeneration does not function that turn". Distinct from
        `c.suspend_when`, which is the *event* shape and switches the whole
        effect off until a stated clock: one stat block prints both clauses
        and needs both, so collapsing them into one kwarg would have made
        either clause unsayable on the row that wants the pair.

        **`ev.ghost` matters.** A ghost turn is the engine looking ahead,
        not a turn happening, and healing on one pays out for free every
        time a policy thinks about the board.
        """
        who = self._who(on) if on is not None else self.me
        if who is None:
            return None  # type: ignore[return-value]

        # **"Its regeneration does not function on its next turn after
        # damage from a <property> weapon."** Fifteen stat blocks print
        # that sentence about silver and every one of them had to say it
        # by hand -- the same `Hit` watch, the same consumed flag, the
        # same `unless` closure, fifteen times in twelve files. Folded in
        # here for the reason `regeneration` itself was: fifteen copies of
        # a two-part mechanism is fifteen chances to get the flag wrong,
        # and the flag is the part that is easy to get wrong.
        #
        # **Consumed by the tick it suppresses, not cleared on a clock.**
        # `m5798a1` settled that shape for the acid-and-fire version: the
        # read happens inside the `TurnStart` tick, so a second watch
        # counting turns would race it, and consuming says "the next tick,
        # whenever it comes" with nothing to order.
        #
        # **`Hit` and not `DamageApplied`**, which is the whole trap of
        # this family: `weapon_of` finds the swing through `ev.attacker`
        # and `DamageApplied` carries `source` instead, so a damage watch
        # would answer False for ever and every one of the fifteen rows
        # would audit clean while doing nothing.
        # **Two feeds, one flag**, because the mechanism is identical and
        # the *read* is not: a damage type is a field on `DamageApplied`,
        # and a weapon property can only be found through the `Hit` that
        # carries `attacker`. Four spellings had grown for one idea --
        # `suspended_by=`, `suppressed_by=`, `when=` and three rows that
        # hand-rolled it -- and a row cannot tell which of them will land.
        #
        # Deliberately **not** one parameter taking either kind. They read
        # off different events at different moments, and a single argument
        # whose type decides which would be the one-symbol-several-gaps
        # trap pointed at a signature.
        # **The flag lives on the creature, not in this closure, and that
        # is the #569 move again.** `c.latched`'s own docstring records why:
        # `features.extra_damage` kept its latch in a local dict, "so
        # nothing outside could ask whether the striker had already paid --
        # and two rows are exactly that question from two sides".
        #
        # Here the two sides are a clause that switches the regeneration off
        # and `m2068a3`, which **switches it back on**: "one <troll> within
        # 10 squares whose regeneration is currently inactive (as a result
        # of taking acid or fire damage) immediately reactivates the
        # regeneration". With the flag in a closure there was nothing to
        # reach, and that row has been re-marked three times looking for
        # the gap elsewhere -- twice at a `Cast` verb and once, by me, at
        # the ETL. #602.
        #
        # An `Effect` labelled with the laying ref rather than a `Mods` key:
        # the tree's idiom is that a hold carries the ref that laid it, so
        # `c.resume_regeneration` can find exactly this one and leave a
        # second regeneration on the same creature alone. Still **consumed
        # by the tick it suppresses and not cleared on a clock** --
        # `When.ENCOUNTER` with the tick ending it -- which is the shape
        # `m5798a1` settled.
        flag = f"{self.ref} regen suppressed"

        def mark() -> None:
            if not self._regen_suppressed(who, flag):
                self.world.effects.apply(
                    who, self.me, When.ENCOUNTER, label=flag, by=self.ref
                )

        if unless_struck_by:
            from .events import Hit

            def took(ev: Any) -> None:
                if ev.target == who and self.struck_by_property(
                    unless_struck_by, ev
                ):
                    mark()

            self.watch(
                Hit, took, until=until, on=who,
                label=f"{self.ref} struck by {unless_struck_by}",
            )
        if unless_damaged_by:
            from .events import DamageApplied

            wanted = frozenset(unless_damaged_by)

            def burned(ev: Any) -> None:
                # `ev.types()` and not `ev.dtype`, or a blow that is two
                # types at once is read as only the first -- #420's lesson,
                # and "acid or fire" is exactly the shape that trips on it.
                if ev.target == who and wanted & set(ev.types()):
                    mark()

            self.watch(
                DamageApplied, burned, until=until, on=who,
                label=f"{self.ref} damaged by type",
            )

        def suppressed() -> bool:
            held = self._regen_suppressed(who, flag)
            if held is None:
                return False
            self.world.effects.end(held, "the suppressed tick is spent")
            return True

        def tick(ev: Any) -> None:
            if ev.actor != who or ev.ghost:
                return
            if while_bloodied and not self.bloodied(on=who):
                return
            if unless is not None and unless():
                return
            if (unless_struck_by or unless_damaged_by) and suppressed():
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
        # **A handler is not re-entered by an event it caused itself.**
        # `c.heal` inside a `Healed` watcher emits another `Healed`, which
        # offers the same subscription again, which heals again -- until the
        # stack runs out. Four rows in the tree had already hand-rolled a
        # latch for exactly this and `i661p1`'s comment states the rule;
        # four more had not, and one of them took the whole audit down with
        # a `RecursionError` the moment items reached play.
        #
        # Scoped to **this** subscription and not to the event: a row whose
        # handler causes a `Hit` should still let every *other* row see that
        # hit, and only its own re-entry is the bug. One flag per `watch`,
        # which is what the four latches each were.
        running: list[int] = []

        def fire(ev: Any) -> None:
            # **A suspended effect's watcher does nothing.** Suspension lifts
            # installed state by itself, but a verb built out of `watch` holds
            # no installed state at all -- its whole effect is this handler --
            # so without the guard "its regeneration does not function" would
            # suspend an effect that went on healing. One check here covers
            # every watcher-shaped verb in the surface.
            if holder and holder[0].suspended:
                return
            if running:
                return
            before = len(self.world.bus.log)
            held = len(self.world.effects.live)
            # **Rewriting a field on the triggering event counts as doing
            # something**, and nothing else here can see it: the handler
            # emits no event and lays no effect, so both counts below are
            # unmoved. Snapshot only for a `once=` hold -- it is the only
            # caller that asks the question, and an ordinary watch should not
            # pay a dict copy per firing. See the `did` comment.
            was = dict(ev.__dict__) if once else None
            running.append(1)
            try:
                fn(ev)
            finally:
                running.clear()
            # `once` means "fire once", not "live for one event", and those
            # differ for every trigger with a guard -- which is most of them.
            # Ending unconditionally burned the effect on the first event of
            # the right *class*, so "the first time you hit a bloodied enemy"
            # was spent by the first attack that missed a healthy one.
            #
            # So the question is "did the handler do anything", and the way
            # it is asked has been wrong twice, both times by **enumerating
            # the ways of doing something** instead:
            #
            # * `c.summon` puts a creature on the board and in the order and
            #   emits nothing at all, so a once-only row whose whole effect
            #   is a summon never spent its hold and fired every round. The
            #   effect count was added for it.
            # * A handler whose whole effect is rewriting a field on its own
            #   event -- `ev.amount -= cut`, `ev.saved = True` -- moves
            #   neither count, so `once=` never spent and the hold fired on
            #   every matching event for its whole duration. Three rows in
            #   the tree, and the sharpest of them chose a `once=` watch
            #   *expressly* to avoid shaving every blow its ally took, which
            #   is what this bug made it do. #540.
            #
            # A field holding a mutable member that the handler changes in
            # place still reads as untouched -- `dict()` is one level deep.
            # No row does that today; a future one would need a third term
            # here, and the better answer then is for the handler to say so.
            did = (
                len(self.world.bus.log) > before
                or len(self.world.effects.live) != held
                or (was is not None and dict(ev.__dict__) != was)
            )
            if once and holder and did:
                self.world.effects.end(holder[0], "used")

        sub = self.world.bus.on(event, fire, window=window, owner=self.me)
        effect = self.world.effects.apply(
            who, self.me, until, label=label or f"{self.ref} trigger", subs=[sub],
            by=self.ref,
        )
        holder.append(effect)
        return effect

    def in_form(self, *names: str, on: int | None = None) -> bool:
        """Is the creature in one of the named forms? See `query.in_form`."""
        from .query import in_form

        who = self._who(on)
        return False if who is None else in_form(self.world, who, *names)

    def shifted(self, *, on: int | None = None) -> bool:
        """Has the creature taken a shape that is not its own?"""
        from .query import shifted

        who = self._who(on)
        return False if who is None else shifted(self.world, who)

    def kill(self, *, on: int | None = None, critical: bool = False) -> bool:
        """Reduce a creature to 0 hit points outright. Returns whether it moved.

        "A critical hit automatically reduces the creature to 0 hit points" is
        nine stat blocks, and it is **not damage** -- no amount is rolled, no
        resistance applies, nothing is halved by being insubstantial. Dealing
        a very large blow instead would be wrong at every one of those
        joints, and wrong again on a creature with damage immunity.

        Routed through `resolve._check_down`, which is the engine's one path
        out of zero: it announces `Dropped`, lets a row that answers its own
        downfall heal out of it, and then either kills or lays the dying
        conditions according to `Health.dying_at` -- 0 for a monster, below
        zero for a character. Setting the hit points and stopping would leave
        a creature at 0 that nothing had noticed.

        `critical` says whether a critical hit did it, which `Dropped` carries
        for the rows printing "reduced to 0 hit points, **but not by a
        critical hit**". Passing it on matters: those rows are the mirror of
        these, and a kill that claimed not to be a crit would arm them.
        """
        from .components import Health
        from .resolve import _check_down

        who = self._who(on)
        if who is None:
            return False
        health = self.world.get(who, Health)
        if health is None or health.hp <= 0:
            return False
        health.hp = 0
        _check_down(self.world, who, health, source=self.me, crit=critical,
                    power=self.ref)
        return True

    def aftereffect(
        self,
        held: Effect | None,
        clause: Callable[[], Any],
    ) -> Effect | None:
        """A second clause that lands when the first one ends.

        "The target is stunned until the end of its next turn.
        **Aftereffect:** the target takes a -2 penalty to attack rolls (save
        ends)" -- 22 rows print one, and it is a standard clause rather than
        a special case: when the hold goes, the aftereffect arrives.

        **Not `escalate=`, which is its mirror.** That one runs on a *failed*
        saving throw and worsens the hold in place; this runs when the hold
        is *over*, whether a save ended it or its clock did. A row given
        `escalate` for an Aftereffect line would pay out exactly when the
        card says it should not.

        **It does not fire when the encounter ends, nor when the creature
        holding it dies.** `on_end` is handed no reason and runs for every end
        alike, so without the guards every aftereffect in play would land as
        the board was torn down, and every one on a dying creature would land
        as `bereave` cleared it. `Effects.closing` covers the first;
        `query.alive` covers the second, and the audit found it -- `i1621p1`
        raised inside `_die`, two frames below `bereave`, reaching for a
        creature that was no longer on the board.

        **There is no "only on a save" switch and an attempt at one was
        deleted.** It read `held.ended`, which `end` sets *before* it runs
        `on_end` -- so the test was False on every call and the parameter did
        nothing, which is this component's commonest bug wearing a keyword.
        Telling a save from a clock needs the reason `on_end` is not given;
        if a card ever needs that distinction, that is the change to make.

        Returns the effect it was given, so a row can keep hold of it.
        """
        if held is None:
            return None

        def land() -> None:
            # No once-only latch: `end` returns early on an effect it has
            # already ended and `on_end` is run nowhere else, so this cannot
            # be reached twice. A latch was written and deleted -- the plant
            # test for it stayed green, which is the evidence.
            from .query import alive

            if self.world.effects.closing:
                return
            if not alive(self.world, held.owner):
                return
            clause()

        held.on_end.append(land)
        return held

    def suspend_when(
        self,
        held: Effect | None,
        event: type[Event],
        pred: Callable[[Any], bool] | None = None,
        *,
        for_: When = When.SONT,
        label: str = "",
    ) -> Effect | None:
        """Switch an effect off when something happens, and back on later.

        The printed sentence is "**when** it takes fire or radiant damage, it
        loses this trait **until** the start of its next turn", and it is said
        about regeneration, insubstantial, a vulnerability, an invisibility and
        a terrain-ignoring stance -- the same clause attached to five different
        traits, which is why this is one verb rather than a `suspended_by=` on
        each of them.

        **Not `c.effect(...)` plus an end.** Ending the trait spends its
        duration: an encounter-long regeneration would be gone for good after
        one hit, and a save-ends hold would stop owing its saving throw. The
        trait comes back.

        `for_` is clocked on whoever holds the effect, so the default
        `When.SONT` is *its* next turn, which is what the cards say. A second
        trigger while it is already off is ignored: "until the start of its
        next turn" said twice is one deadline, and it is the same deadline,
        because the clock does not depend on when the sentence was said.

        Returns the watcher, so a row can end the arrangement without ending
        the trait. `None` if there is no effect to suspend, which is what
        every `Cast` verb that can decline does.
        """
        if held is None:
            return None
        who = held.owner
        timer: list[Effect] = []

        def _arm(ev: Any) -> None:
            if held.ended or (pred is not None and not pred(ev)):
                return
            # **A second trigger while it is already off does nothing.**
            # `for_` is one clock on one creature, so a timer laid now and a
            # timer laid three events ago reach the same deadline -- which
            # makes this a guard against *accumulation*, not against a wrong
            # answer, and the plant test says so: removing it leaves the
            # driver green because five timers all resume at the same moment
            # and four of the five resumes are no-ops.
            #
            # Kept anyway, and asserted on the count rather than the
            # behaviour. Five live effects nobody can see is a slow leak, and
            # `watch` reads `len(effects.live)` to decide whether a `once=`
            # handler did anything -- so an arming that quietly laid an
            # effect would spend an unrelated once-only row's hold.
            if timer and not timer[0].ended:
                return
            self.world.effects.suspend(held)
            timer[:] = [
                self.world.effects.apply(
                    who, who, for_,
                    label=label or f"{self.ref} suspended",
                    on_end=[lambda: self.world.effects.resume(held)],
                    by=self.ref,
                )
            ]

        return self.watch(
            event, _arm, until=When.ENCOUNTER, on=who,
            label=label or f"{self.ref} suspends {held.label}",
        )

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
        obscured: str = "",
        exempt: frozenset[int] | set[int] | None = None,
        sustain: ActionType | None = None,
    ) -> int:
        """`obscured=Light.DIM` is "lightly obscured", `Light.DARK` is
        "heavily obscured" or a zone of darkness.

        **Not `blocks_sight`**, which is terrain and blinds both sides --
        `c.zone`'s long-standing caution against reaching for it here was
        correct and now has somewhere else to point. 12 rows asked for this
        kwarg and 14 more asked for `c.conceal_in()`; they are one gap. #424.

        **`exempt` is who the sight-blocking does not apply to**, and the
        common case is one id: `exempt={c.me}` for the eight cards printing
        a cloud that blinds everybody except the creature that made it.
        Without it those rows laid the zone and dropped the exemption, which
        inverts the ability -- the point of the card is that its owner sees
        and nobody else does.

        A set of ids, not a predicate. An exemption by *sense* or by
        *movement mode* is a different gap and those rows still carry a
        marker; see `Zone.exempt`.
        """
        return self.world.zones.create(
            self.me, label or self.ref, frozenset(area), until,
            difficult=difficult, blocks_sight=blocks_sight,
            obscured=obscured, exempt=exempt, sustain=sustain,
        )

    def aura(
        self,
        radius: int,
        *,
        label: str = "",
        until: When = When.ENCOUNTER,
        on: int | None = None,
        sustain: ActionType | None = None,
        difficult: bool | str = False,
    ) -> int:
        """An aura around a creature -- or around anything with a position.

        `on` is what it follows. It used to be the caster and nothing else,
        which is what made "each creature adjacent to the sphere" unsayable:
        `Zones.refresh` has always been willing to follow any entity with a
        `Position`, and only this signature insisted it be `self.me`.

        **`difficult` is "enemies treat squares in the aura as difficult
        terrain"**, which nine rows were marked blocked for while the field
        existed. `Zone.difficult` has always been there and `Zones.create`
        has always taken it; `Zones.aura` did not pass it on, so the only
        route was creating the aura and flipping the field by hand -- which
        `monsters.level_10.soldiers_sa._difficult_aura` does, and documents
        as a workaround. Found by `triage.py`'s first calibration run.
        """
        owner = self.me if on is None else on
        return self.world.zones.aura(
            owner, label or self.ref, radius, until, sustain,
            difficult=difficult,
        )

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

    def resize_aura(
        self, label: str = "", *, plus: int = 0, to: int = 0, cap: int = 0
    ) -> int:
        """Change a standing aura's radius in place, and say so.

        `Zones.refresh` re-cuts `zone.squares` from `zone.aura` on every tick,
        so the radius is live and one field is the whole lever. Two rows had
        worked that out and were mutating it by hand -- correctly -- and both
        sat in `audit.KNOWN_SILENT` because **nothing was announced**, so the
        audit had no event to credit and called a working row invisible. #375.

        `plus` widens by that much, `to` sets it outright, `cap` is the
        printed ceiling ("to a maximum of aura 5"). Returns the new radius, or
        0 if the caster has no such aura -- which is a real answer and not a
        failure: a row that widens its aura does nothing if nothing made one.
        """
        from .events import ZoneResized

        zid = self.my_aura(label=label)
        if not zid:
            return 0
        zone = dict(self.world.zones.all()).get(zid)
        if zone is None or zone.aura is None:
            return 0
        was = zone.aura
        now = to if to else was + plus
        if cap:
            now = min(cap, now)
        now = max(0, now)
        if now == was:
            # Nothing moved, so nothing is announced: a row already at its
            # printed ceiling has not done something, and crediting it would
            # be the over-crediting #216 was about.
            return was
        zone.aura = now
        # **Redrawn at once, not on the next tick.** `Zones.refresh` would get
        # to it anyway, but a row that widens its aura and then asks who is
        # standing in it would read the old footprint. Of the three hand-rolled
        # versions this replaces, only `level_13/lurkers_sa.py`'s called this --
        # so two of them had the stale-footprint window and the third did not,
        # which is the argument for one verb rather than three.
        self.world.zones.refresh()
        self.world.bus.emit(
            ZoneResized(zone=zid, actor=self.me, from_=was, to=now)
        )
        return now

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
        exempt: frozenset[int] | set[int] | None = None,
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
            blocks_sight=blocks_sight, exempt=exempt,
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
        when: Callable[[dict[str, Any]], bool] | None = None,
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

        `when` is the same gate `c.bonus` takes and is handed straight to it, so
        it is read where every other gated bonus is read, with the same context
        -- "+1 to attack inside the zone **against bloodied enemies**" is one
        lambda rather than a second kind of zone. Ten rows asked for it.
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
                what, value, on=who, until=When.ENCOUNTER, kind=kind, when=when
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

    def vulnerable_in(
        self,
        zone: int,
        amount: int,
        dtype: DamageType | None = None,
        *,
        side: str = "enemy",
        when: Callable[[dict[str, Any]], bool] | None = None,
    ) -> None:
        """"Each enemy within the zone gains vulnerable N while it is there."

        The mirror of `c.resist_in`, and it exists for the same reason that
        one does: vulnerability lives on `Defences`, not in `Mods`, so
        `c.grants_in` cannot carry it -- a modifier named "vulnerable"
        would install a key nothing reads and look like a working zone.

        **`side` defaults to `"enemy"` here**, where `c.resist_in` and
        `c.grants_in` default to `"team"`. That is the printed word on
        both sides of the split: a zone that *helps* says "you and your
        allies", and a zone that *hurts* says "each enemy within". A
        default of `"team"` would make the commonest call a vulnerability
        on the caster, which is the shape `c.bloodied()`'s target default
        already cost eight rows.

        `when` is handed to `c.vulnerable`, which keeps the entry as a
        `(dtype, amount, when)` triple on `Defences.vulnerable_when` for
        `resolve.deal_damage` to read -- #471. So the two scopes the cards
        print are both sayable and are different questions: a **damage
        type** is `dtype`, and "vulnerable 3 to **weapon** attacks" or "to
        **your** attacks" is the gate, read against a context carrying
        `source` and `power`. `features.sorcerer` is the worked example.

        It replaces two symbols, `c.vulnerable_in()` and
        `c.aura(vulnerable=)`, which were one gap written twice: an aura
        is a zone as far as `_while_inside` is concerned -- `c.grants_in`
        has always been handed `c.my_aura()` -- so there was never a
        second mechanism to build.
        """
        self._while_inside(
            zone,
            lambda who: self.vulnerable(
                amount, dtype, on=who, until=When.ENCOUNTER, when=when
            ),
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

    def light(
        self, radius: int = 2, *, on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """"You shed bright light in a 2-square radius."

        15 rows print it, and one of them records in its own docstring why it
        was left unwritten: *"a verb recording 'bright light out to 10
        squares' would be a modifier nothing consults, which is the commonest
        bug in this component."* That was correct until the light model
        landed; `query.light_level` is the reader, and it treats anything
        within `radius` as bright however dark the square is underneath.

        **Carried, not painted.** The radius lives on the creature so the
        light moves with it, which is what the printed line means and what a
        grid write could not do without repainting the map on every step.

        Lighting a dark board changes nothing on its own -- light only ever
        *removes* a concealment penalty, so on a board that was never
        darkened this is inert, which is the honest answer for a torch in
        daylight.
        """
        return self.bonus(
            "light_radius", max(1, radius), on=on if on is not None else self.me,
            until=until, kind=self.ref,
        )

    def unlit(self, *, on: int | None = None) -> bool:
        """Is this creature standing in dim light or darkness? Defaults to the
        **caster**, because every row that asks is about itself.

        Nineteen rows print "while you are in dim light or darkness" as a gate
        -- a saving-throw bonus, a defence bonus, ignoring difficult terrain,
        a teleport that must land somewhere unlit. They all want this one
        question, and opening it up nineteen times would be nineteen chances
        to read `Grid.light` slightly differently.

        **Safe inside a `when=` gate**, which is where most of these live: the
        lambda closes over the `Cast`, so it reaches the world without needing
        the modifier context to carry a square it does not have.

        The worst-lit square the creature occupies decides it, matching
        `query.light_concealment` -- a creature half in shadow is in shadow.
        """
        from .query import light_level, squares

        who = on if on is not None else self.me
        return any(
            light_level(self.world, sq) is not Light.BRIGHT
            for sq in squares(self.world, who)
        )

    def has_sense(self, sense: str, *, on: int | None = None) -> bool:
        """Does this creature have that sense? Defaults to `c.target`.

        The question three rows ask about somebody *else* -- "if the creature
        has darkvision", "creatures without darkvision are blinded". Granting
        a sense and asking after one are different jobs, and only the first
        had a verb.
        """
        from .query import has_sense as _has

        return _has(self.world, on if on is not None else self.target, sense)

    def darkvision(
        self, radius: int = 0, *, on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """"You have darkvision." Darkness does not conceal from you.

        21 rows print it, mostly racial. Read by `query.sees_in`, which the
        attack path consults through `query.light_concealment` -- so this is
        a sense that cancels a penalty rather than one that grants a bonus,
        and it covers dim light as well: a creature that sees in the dark is
        not inconvenienced by shade.

        A sense of yours, so it defaults to the **caster**, like
        `c.see_invisible` and `c.truesight`.
        """
        return self.bonus(
            "darkvision", radius or UNLIMITED_SENSE,
            on=on if on is not None else self.me, until=until, kind=self.ref,
        )

    def low_light(
        self, radius: int = 0, *, on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """"You have low-light vision." Dim light does not conceal from you.

        The weaker half of `c.darkvision`, and the distinction is the whole
        point for the 14 rows that print this one: darkness still conceals.
        `query.sees_in` is where the two come apart.
        """
        return self.bonus(
            "low_light", radius or UNLIMITED_SENSE,
            on=on if on is not None else self.me, until=until, kind=self.ref,
        )

    def blindsight(
        self, radius: int = 0, *, on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """"Blindsight 5". Light is irrelevant to you entirely.

        Stronger than `c.darkvision`: that one answers the dark, this one
        does not consult the light at all. Kept a separate key from
        `c.tremorsense` because the printed ranges differ and a creature may
        be granted one without the other -- `query.sees_in` answers True for
        either, which is all the light model needs to know.

        `radius` is the printed range and **is** read: `query.sees_in` is
        handed the distance to the creature being looked at, so a sense with
        a range stops answering past it. `0` means no limit, which is how the
        books print the commonest case.
        """
        return self.bonus(
            "blindsight", radius or UNLIMITED_SENSE,
            on=on if on is not None else self.me, until=until, kind=self.ref,
        )

    def tremorsense(
        self, radius: int = 0, *, on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """"Tremorsense 10". Senses through the ground, so light is irrelevant.

        Answers `query.sees_in` exactly as `c.blindsight` does. The two are
        not folded into one key because the printed lines are different
        senses with different ranges, and a later rule that cares which --
        a creature that is not touching the ground -- needs them apart.
        """
        return self.bonus(
            "tremorsense", radius or UNLIMITED_SENSE,
            on=on if on is not None else self.me, until=until, kind=self.ref,
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
        floor = self._reroll_floor()
        if floor > 1:
            return self._rolled_above(dice, floor)
        # **After the loop and never beside it.** "Reroll each die that shows
        # a 1 *until it shows a different number*" is strictly stronger than
        # "pick one of them, reroll it, and use the new result", so a
        # creature carrying both gets the loop and this is dead -- which is
        # the right answer and the reason these are two holds rather than
        # parameters on one. Three parallel `max()` reads would have mixed
        # one card's count into the other card's floor and come out *weaker*
        # than either card alone; `items/weapon_b.py` lays the loop on its
        # wielder, so a mage holding both is reachable and not theoretical.
        pick_floor, pick_n = self._reroll_pick()
        if pick_floor > 1 and pick_n > 0:
            return self._rolled_pick(dice, pick_floor, pick_n)
        first = self.world.rng.roll(dice).total
        if self.total("damage_twice_lower") > 0:
            return min(first, self.world.rng.roll(dice).total)
        if self._rolls_twice_higher():
            return max(first, self.world.rng.roll(dice).total)
        return first

    def _rolled_above(self, dice: str | int, floor: int) -> int:
        """Roll, then replace each die under `floor` until it is not.

        Per die rather than per expression: the card says "reroll each die
        that shows a 1", so the dice that came up fine keep their faces.

        **Capped twice, deliberately.** "Until it shows a different number"
        is a loop, and a threshold at or above a die's own face count would
        never terminate -- `below=3` on a d2 is not a card anybody printed,
        but a typo would be an infinite one, inside a damage roll, hanging
        the fight.

        So there are two guards and **neither is individually load-bearing**:
        planting either one alone leaves the driver green, because the other
        catches it. Planting *both* hangs. That is on purpose for a hazard
        this shape, and it is written down because a reader who plants one
        guard, sees green, and deletes it as dead code would be removing
        half of a pair rather than a redundancy.
        """
        rolled = self.world.rng.roll(dice)
        faces = _faces_of(dice)
        if faces <= 1 or floor > faces:
            return rolled.total
        for i, face in enumerate(rolled.dice):
            tries = 0
            while face < floor and tries < 10:
                face = self.world.rng.die(faces)
                tries += 1
            rolled.dice[i] = face
        return rolled.total

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
            borrower, self.me, until, label=f"{self.ref} origin", on_end=[undo],
            by=self.ref,
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
            who, self.me, until, label=f"{self.ref} ignored", on_end=[undo],
            by=self.ref,
        )

    # -- a number that lived in a closure ------------------------------------

    def quarry_damage(self) -> str:
        """The dice the ranger's quarry rider pays out, as an expression.

        It lives in a closure inside `cf:ranger-f1` and nothing could
        read it back, so "extra damage equal to your cf:ranger-f1 damage"
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

    def conceal_in(
        self, zone: int, *, side: str = "team", total: bool = False
    ) -> None:
        """"You and your allies have concealment while within the zone."

        The third of the zone-bounded grants, beside `c.cover_in` and
        `c.ignores_difficult_in`, and written for the same reason each of
        those was: `c.conceal` is per-creature and lasts a duration, so a
        row printing this as a plain `c.conceal` concealed its allies
        wherever they went and for as long as the clock ran -- a different
        and much stronger rule than standing in a cloud.

        Hung on the geometry like its two siblings: taken on entering, given
        back on leaving, and taken off everybody when the zone itself ends.
        A creature that walks in after the zone was laid is covered, which is
        what `_while_inside` asks per arrival rather than once.

        `total` is the printed difference between concealment and *total*
        concealment, which `c.conceal` already carries -- a few of these
        zones print the stronger word. #500.
        """
        self._while_inside(
            zone,
            lambda who: self.conceal(
                on=who, until=When.ENCOUNTER, total=total
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

    def reroll_ones(
        self,
        *,
        below: int = 2,
        pick: int = 0,
        keyword: Keyword | None = None,
        ref: str = "",
        on: int | None = None,
        until: When = When.ENCOUNTER,
        when: Callable[[dict[str, Any]], bool] | None = None,
    ) -> Effect | None:
        """"Reroll each damage die that shows a 1 until it shows a different
        number."

        **Not `c.reroll_damage`**, which rolls the whole expression twice and
        keeps the higher -- a different and stronger rule, and `f1378b`'s own
        note says six rows wanted this one instead. Here each low die is
        replaced individually and the rest of the roll stands.

        Recorded as a hold and read inside `_roll_damage`, where the dice are
        in hand: `DamageRolled` carries a total with no dice behind it, and a
        character's damage is rolled in the body rather than declared in a
        header, so there is nothing to look up afterwards. That is the same
        argument `reroll_damage` and `c.maximise` already make, and the same
        place they are read.

        `below` is the threshold, exclusive: the default 2 rerolls ones,
        which is what almost every card prints, and 3 is the one that says
        "a 1 or a 2".

        `keyword` and `ref` narrow it to what the card names -- the curse
        damage, one racial power, weapon dice only. Unqualified is every
        damage roll the creature makes, which only a couple of cards mean.

        **`pick` is the other printed shape, and it is weaker.** Some cards
        say "if any of the dice come up with a result of 1, **pick one of
        them**, reroll it, and use the new result" -- one die, one reroll,
        and the new face stands even if it is another 1. `pick=1` is that;
        `pick=0`, the default, is the loop in the first line of this
        docstring.

        It lays **its own holds** rather than adding a parameter to the
        loop's, which is the whole design decision here. The holds are read
        with `total()`, so three parallel reads of floor, count and tries
        would take the `max` of each independently -- and a creature holding
        one card of each shape would come out with the loop's floor, the
        pick's count of 1 and the pick's single try: **weaker than either
        card alone**. `_damage_roll` reads the loop first and this only if
        the loop is absent, so holding both gives the loop, which is what
        both cards together should mean.
        """
        who = on if on is not None else self.me
        what = "reroll_damage_pick" if pick else "reroll_damage_below"
        if ref:
            what = f"{what}@{ref}"
        elif keyword is not None:
            what = f"{what}:{keyword.value}"
        if pick:
            # Two holds, laid together and read together. The count is
            # keyed off the floor's own `what` so the pair cannot drift
            # apart, and `below` rides in the floor hold exactly as the
            # loop's does.
            self.bonus(f"{what}#n", pick, on=who, until=until, stacks=False,
                       when=when)
        # `stacks=False` because the floor is a `max`: a second identical
        # hold changes nothing and would only pile up effects -- a monster
        # whose own attack line prints the reroll lays one per swing
        # otherwise.
        #
        # No `kind=`, and `c.bonus` refuses the pair outright: `stacks=False`
        # already buckets under the laying row's ref, and a reroll floor is
        # not a *typed* bonus that a printed type could stack against.
        return self.bonus(what, below, on=who, until=until, stacks=False,
                          when=when)

    def _reroll_floor(self) -> int:
        """The threshold under which a damage die is rerolled, for *this* row.

        0 for everybody with nothing recorded, which is almost everybody.
        The row being rolled is what answers a qualified hold, the same way
        `_rolls_twice_higher` asks it.
        """
        seen = self._reroll_ctx()
        best = self.total("reroll_damage_below", ctx=seen)
        aimed = self.total(f"reroll_damage_below@{self.ref}", ctx=seen)
        best = max(best, aimed)
        from .dsl import get

        p = get(self.ref)
        if p is not None:
            for k in self.keywords_of(p):
                best = max(best,
                           self.total(f"reroll_damage_below:{k.value}", ctx=seen))
        return best

    def _reroll_ctx(self) -> dict[str, Any]:
        """What a gated reroll hold is asked, at the moment the dice are rolled.

        **Added with `reroll_ones(when=)` and not after it**, because a gate
        nothing passes a context to does not narrow -- `c.total`'s own
        docstring says so outright: *"Without it a `c.bonus(..., when=...)`
        cannot narrow, and every such bonus counts -- which is how a '+2 to
        saving throws **against poison**' came to be a bonus to every saving
        throw."* For a reroll that failure is a *widening*, so the parameter
        without this would have been worse than no parameter at all.

        The three keys every card of this family turns on, and the same
        spellings `resolve.attack` builds its context from: four printed
        lines narrow by **which creature is being hit** -- granting combat
        advantage, adjacent to you, inside the aura, the enemy you flank --
        and the row and the attacker are free beside it.
        """
        return {"power": self.ref, "target": self.target, "attacker": self.me}

    def _reroll_pick(self) -> tuple[int, int]:
        """The floor and the number of dice for the **pick-one** shape.

        `(0, 0)` for everybody with nothing recorded, which is almost
        everybody. Same three-key lookup as `_reroll_floor` -- unqualified,
        `@<the row being rolled>`, and per keyword -- because the cards
        printing this narrow themselves the same ways.

        Returned as a pair rather than read twice from the caller so the
        floor and the count cannot be answered by two different holds.
        """
        from .dsl import get

        # The same context `_reroll_floor` reads with, for the same reason:
        # the pick-one shape is laid by the same verb and would otherwise
        # have a gate nothing asks.
        seen = self._reroll_ctx()

        def best(prefix: str) -> int:
            got = max(self.total(prefix, ctx=seen),
                      self.total(f"{prefix}@{self.ref}", ctx=seen))
            p = get(self.ref)
            if p is not None:
                for k in self.keywords_of(p):
                    got = max(got, self.total(f"{prefix}:{k.value}", ctx=seen))
            return got

        floor = best("reroll_damage_pick")
        if floor <= 1:
            return 0, 0
        # The count hangs off the same three keys with `#n` on the end, so
        # whichever qualifier answered the floor answers the count too.
        got = max(self.total("reroll_damage_pick#n"),
                  self.total(f"reroll_damage_pick@{self.ref}#n"))
        p = get(self.ref)
        if p is not None:
            for k in self.keywords_of(p):
                got = max(got, self.total(f"reroll_damage_pick:{k.value}#n"))
        return floor, got

    def _rolled_pick(self, dice: str | int, floor: int, count: int) -> int:
        """Reroll at most `count` of the dice under `floor`, **once each**.

        The difference from `_rolled_above` is the whole of the card: that
        one loops until the die is not low, this one takes the new face as
        it comes. So there is no termination hazard here and none of the
        paired guards that one needs -- a single reroll cannot hang.

        Lowest dice first, because "pick one of them" is the player's choice
        and the player picks the worst one. That is a policy decision living
        in the kernel, which is normally wrong; it is here because the
        alternative is asking the AI to choose between dice, and no card
        makes the choice matter beyond "the lowest is best to replace".
        """
        rolled = self.world.rng.roll(dice)
        faces = _faces_of(dice)
        if faces <= 1 or floor > faces:
            return rolled.total
        low = sorted(
            (face, i) for i, face in enumerate(rolled.dice) if face < floor
        )
        for _face, i in low[:count]:
            rolled.dice[i] = self.world.rng.die(faces)
        return rolled.total

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
            self.total(f"damage_twice_higher:{k.value}") > 0
            for k in self.keywords_of(p)
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
            # **The row that laid it, not the row moving it.** Transferring
            # a hold to another creature does not make it somebody else's
            # effect, so its keywords must not change hands either. #580
            by=getattr(effect, "by", "") or effect.label,
            conditions=effect.conditions,
            mods=[(to if eid == old else eid, m) for eid, m in effect.mods],
            ongoing=effect.ongoing,
            save_mod=effect.save_mod + save_mod,
            escalate=effect.escalate,
        )

    # -- added for the tail-3 batch ------------------------------------------

    def no_walk(self, *, until: When = When.EONT, on: int | None = None) -> Effect | None:
        """"It cannot use move actions to walk or run." It may still shift.

        The mirror of `c.cannot_shift`, which bars the shift and leaves the walk.
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
        rattles = bool(p and Keyword.RATTLING in self.keywords_of(p))
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
            by=self.ref,
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

    def jump(
        self,
        squares_: int,
        *,
        on: int | None = None,
        toward: int | None = None,
        away_from: int | None = None,
    ) -> int:
        """A jump: ground crossed rather than walked over.

        "You can jump a number of squares equal to your Wisdom modifier, and
        the distance does not count toward your movement." Neither `c.move`
        nor `c.shift` says it -- a jump clears what is in the way -- so it is
        a move with the rough going and the bodies ignored for its length,
        paid for by the power rather than out of the turn.

        Defaults to the caster, like the movement methods beside it.

        `toward` and `away_from` are `c.move`'s, handed straight on, because a
        jump is a move and "it jumps 6 squares and then uses claw twice" needs
        the same bias: unranked, the leap landed at the lowest coordinate on
        the board and the two claws swung from out of reach.

        **It comes down somewhere legal.** The phasing that lets the leap
        clear a body also lets `movement.reachable` *offer* that body's square
        as the place to land -- `_clear` reads `phasing` itself, and only a
        flyer's destinations are filtered -- which `settle` would not undo
        until the end of the turn. Aimed, that square is the nearest one and
        so the first one taken, so the jumper landed inside the creature it
        was about to claw. `settle` after the phasing is given back puts it in
        the nearest square it fits in, which is beside its target.
        """
        from .movement import _clear, settle

        who = self.me if on is None else on
        if squares_ <= 0 or self.world.get(who, Position) is None:
            return 0
        over = self.phasing(until=When.EOT, on=who)
        rough = self.ignores_difficult(on=who, until=When.EOT)
        try:
            return self.move(squares_, who=who, toward=toward, away_from=away_from)
        finally:
            for held in (over, rough):
                if held is not None:
                    self.world.effects.end(held, "the jump ended")
            # Asked with the phasing already given back, so `_clear` answers
            # for a creature standing still rather than one passing through.
            # Only when the landing is illegal, because `settle` also brings a
            # flyer down and a legal leap must not do that.
            spot = self.world.get(who, Position)
            if spot is not None and not _clear(self.world, who, spot.squares):
                settle(self.world, who)

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

    def check(self, skill: str, dc: int = 0, *, who: int | None = None, bonus: int = 0, against: int | None = None):  # noqa: ANN201, E501
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
        # `against` is who the check is *about*, which seven rows need and
        # the event could not say: "if you successfully intimidate an
        # enemy" is a creature, not a number. `None` for a check about a
        # fact, which is most of them.
        return _check(self.world, roller, skill, dc, bonus=bonus,
                      target=against)

    def struck_by(self, ev: Any, *, kind: str = "", ref: str = "",
                  basic: bool = False) -> bool:
        """What kind of blow caused this event? Reads its `power`.

        Four `Dropped` rows and counting print "with a melee attack",
        "with a ranged attack", "with a melee basic attack" -- the event
        says *who* struck and, since `Dropped.power`, *what* struck, and
        this is the reading. `kind` is a `Range.kind`; `basic` asks
        whether the row is this creature's own basic attack.

        **Empty `power` never matches**, which is ongoing damage and a
        failed death save -- the deaths no blow caused.
        """
        from .components import Powers
        from .dsl import get as _get

        named = getattr(ev, "power", "") or ""
        declared = _get(named)
        if declared is None:
            return False
        if ref and declared.ref != ref:
            return False
        if kind and declared.reach.kind != kind:
            return False
        if basic:
            known = self.world.get(self.me, Powers)
            mine = getattr(known, "basic", "mba") if known else "mba"
            if named not in (mine, "mba"):
                return False
        return True

    def healed_by(self, ev: Any, *, ref: str = "", cls: str = "",
                  keyword: Keyword | None = None,
                  usage: Usage | tuple[Usage, ...] | None = None) -> bool:
        """Did this `Healed` come from a row matching the card's wording?

        `Healed.power` carries the ref, and ten rows narrow on it in four
        different ways -- "with any of your **cleric healing** powers", "by
        one of your **encounter or daily** powers", "your **primal
        healing** powers", "the amount healed by **p1455**". One reader
        rather than ten lookups, because the awkward part is the same every
        time and getting it wrong is silent.

        **An unnamed heal never matches.** `ev.power` is `""` for a surge
        nothing asked for and for a rest, so treating empty as a wildcard
        would pay every one of these riders out on a short rest. That is
        the control `drivers.healed_power` keeps.
        """
        from .dsl import get as _get

        declared = _get(getattr(ev, "power", "") or "")
        if declared is None:
            return False
        if ref and declared.ref != ref:
            return False
        if cls and declared.cls != cls:
            return False
        if keyword is not None and keyword not in declared.keywords:
            return False
        if usage is not None:
            wanted = usage if isinstance(usage, tuple) else (usage,)
            if declared.usage not in wanted:
                return False
        return True

    def ability_check(self, ability: Ability, dc: int = 0, *, who: int | None = None, bonus: int = 0):  # noqa: ANN201, E501
        """Roll a raw ability check. Truthy when it beat the DC.

        `c.ability_check(Ability.STR, 20)` for "make a DC 20 Strength
        check". **Not `c.check`**, which rolls a *skill*: fourteen rows
        carried a marker saying so, and the cards keep the two apart -- one
        prints "ability check or skill check" as two separate things.

        `who` defaults to the caster, as `c.check`'s does, and for the same
        reason: it is your check and nothing is being done *to* anybody.

        The result carries `.total` for the rows that halve the number
        instead of comparing it. See `skills.ability_check` for why this
        announces a `SkillCheck` under an `ability:<name>` key rather than
        inventing a skill.
        """
        from .skills import ability_check as _ability_check

        roller = self.me if who is None else who
        return _ability_check(self.world, roller, ability, dc, bonus=bonus)

    def shield_bonus(self, *, of: int | None = None) -> int:
        """What this creature's shield adds to AC and Reflex. 0 for none.

        Defaults to the **caster**: every one of the nine printed lines is
        about its own holder's shield. See `query.shield_bonus`.
        """
        from .query import shield_bonus as _shield_bonus

        return _shield_bonus(self.world, self.me if of is None else of)

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

    def reroll_check(
        self, *, keep: str = "new", bonus: int = 0, ev: Any = None
    ) -> int:
        """Roll a skill check again. `keep` is new, best or worst.

        The skill-check twin of `c.reroll_attack`, and six rows print it.
        Returns the **face of the second die**, or 0 if there was no check to
        reroll: one card pays the use back when the second roll is the worse
        of the two, and that cannot be read off the settled event.

        `bonus` is for "reroll it with a power bonus equal to your Wisdom
        modifier", which is one printed clause with the reroll.

        `ev=` names the check when it is not the trigger, for
        `c.reroll_attack`'s reason: a banked reroll is armed as a
        `c.watch`, and a watch handler closes over the row's `Cast`, whose
        `trigger` is not the roll being watched.
        """
        from .events import SkillCheck

        ev = ev if ev is not None else self.trigger
        if not isinstance(ev, SkillCheck):
            return 0
        fresh = self.world.rng.d20().total
        old = ev.natural
        ev.natural = {"new": fresh, "best": max(old, fresh), "worst": min(old, fresh)}[
            keep
        ]
        self.boost_check(bonus)
        self._announce_reroll(
            "check", old, ev.natural, actor=getattr(ev, "actor", self.me)
        )
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

    def regain_points(self, n: int = 1, *, on: int | None = None) -> int:
        """"You regain 1 power point." Yours, so it defaults to the caster.

        Not `c.transfer_points`, which is the verb this was first marked
        against and which **refuses self-targeting** -- `who == self.me`
        returns 0, correctly, because a transfer to yourself is not a
        printed line and would be free points. A row that gains a point
        from somewhere other than another character's pool had nothing to
        say.

        **Capped at the pool's maximum**, unlike a transfer: a transferred
        point is deliberately allowed over the receiver's ceiling, because
        the giver paid for it out of their own. Nobody pays for this one,
        so it may only refill what was spent. Returns how many were
        actually regained, which is 0 for a full pool -- and that 0 is the
        answer a row trading something away for a point needs, so it does
        not pay twice.
        """
        who = self._who(on) if on is not None else self.me
        if who is None or n <= 0:
            return 0
        pool = self._pool(who)
        room = max(0, pool.maximum - pool.points)
        got = min(n, room)
        if got <= 0:
            return 0
        pool.points += got
        self.world.bus.emit(Note(text=f"{who} regains {got} power point(s)"))
        return got

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

    def weapon_dice(
        self, dice: str, *, group: str = "", ref: str = "", on: int | None = None
    ) -> int:
        """Set the damage die of that creature's own weapons. Returns how many.

        **The sibling of `change_dice`, and deliberately not the same verb.**
        That one is keyed by the ref of a *row* and read by that row calling
        `dice_for`; six feats instead say "your unarmed damage die is 1d6", or
        a hand crossbow's, or a blowgun's -- the die of a **weapon**, which is
        a field on `Weapon` that nothing read through a modifier. One symbol
        serving both would go green for either need and be right for only one,
        which this repo has paid for before.

        It needs no reader, which is the whole argument for doing it this way.
        `Gear.weapons` holds `replace(w)` copies made per character by
        `chargen.spawn`, never the module-level weapons themselves -- measured,
        because mutating a shared singleton would have armed every character in
        the fight -- so the six places that read `weapon.damage` (`c.w`, three
        warlord rows, chargen's two) all see this with no change to any of
        them.

        `group` is a weapon group and matches the whole group; `ref` names one
        weapon exactly. Owned weapons count as well as held ones: a feat that
        raises the die of a weapon on the belt should still have done so by the
        time it is drawn.

        Absolute, never a step up, so arming the trait twice in a fight says
        the same thing twice.
        """
        who = self._who(on)
        if who is None:
            return 0
        gear = self.world.get(who, Gear)
        if gear is None:
            return 0
        from .events import WeaponChanged

        changed = 0
        for weapon in gear.weapons:
            if (group and weapon.group == group) or (ref and weapon.ref == ref):
                if weapon.damage != dice:
                    self.world.bus.emit(WeaponChanged(
                        actor=who, weapon=weapon.ref,
                        field="damage", what=dice,
                    ))
                weapon.damage = dice
                changed += 1
        return changed

    def gains_property(
        self,
        prop: str,
        *,
        group: str = "",
        ref: str = "",
        every: bool = False,
        on: int | None = None,
    ) -> int:
        """Lay a printed weapon property on that creature's weapons. Returns how many.

        `weapon_dice`'s mechanism, and the same argument for doing it this
        way: `Gear.weapons` holds per-character `replace(w)` copies, so the
        write needs no reader beyond the ones `Weapon.properties` already
        has -- `_high_crit` for a critical and `_weapon_is` for a printed
        Requirement. Nothing new reads it and nothing shared is mutated.

        **Not `counts_as`, which waives a Requirement.** That verb says "a
        warhammer satisfies a card asking for a light blade" and changes no
        weapon; this one changes the weapon. One symbol serving both would
        go green for either need and be right for only one.

        `group` matches a whole group, `ref` names one weapon, and `every`
        is the printed "weapons you wield" -- a blanket that `weapon_dice`
        deliberately does not offer, because a *die* set across a group
        would lower some of them while a property only ever adds. Arming
        the trait twice says the same thing twice.

        Promoted from `feats.general_s._gains_property`, which had served
        the unarmed run alone for as long as only feats wanted it. Twenty
        rows across the weapon, implement and feat trees print the same
        sentence about silver, and a content-local helper cannot be
        imported by all three trees without a seam nobody wants.
        """
        who = self._who(on)
        if who is None:
            return 0
        gear = self.world.get(who, Gear)
        if gear is None:
            return 0
        from .events import WeaponChanged

        laid = 0
        for weapon in gear.weapons:
            if (
                every
                or (group and weapon.group == group)
                or (ref and weapon.ref == ref)
            ):
                had = weapon.properties
                weapon.properties = weapon.properties | {prop}
                laid += 1
                # Announced because the write needs no reader and therefore
                # had no witness -- `ZoneResized`'s argument exactly. Only
                # when it changed something, so arming a trait twice says
                # the same thing once.
                if weapon.properties != had:
                    self.world.bus.emit(WeaponChanged(
                        actor=who, weapon=weapon.ref,
                        field="properties", what=prop,
                    ))
        return laid

    def weapon_range(
        self,
        *,
        ranged: tuple[int, int] | None = None,
        thrown: tuple[int, int] | None = None,
        group: str = "",
        ref: str = "",
        on: int | None = None,
    ) -> int:
        """Give that creature's weapons a printed range. Returns how many.

        The third of the `weapon_dice` family, after `gains_property`, and
        the same argument a third time: `Gear.weapons` holds `replace(w)`
        copies made per character by `chargen.spawn`, never the module-level
        weapons, so this **needs no reader** -- `resolve._long_range` and
        `c.w` already read these fields for everybody.

        **Five rows, and two different fields.** "Use any one-handed
        off-hand weapon as a heavy thrown weapon, normal range 5, long range
        10" is `thrown=`; "increase its range to 10/20" is `ranged=`. They
        are separate fields on `Weapon` on purpose, and that comment is the
        reason to keep them separate here: *"`Gear.ranged` means can be
        fired, and a dagger cannot be -- letting it answer that question
        hands a rogue a ranged basic attack it does not have."* A verb that
        collapsed them would do exactly that.

        **No `every=`**, unlike `gains_property`. That verb offers a blanket
        because a property only ever adds; a range *replaces*, so a blanket
        would shorten a bow to make a dagger throwable. `weapon_dice`
        withholds `every=` for the same reason and says so.

        Both may be given at once -- `f3641` makes one named weapon a thrown
        weapon and nothing else -- and giving neither is a no-op rather than
        an error, because a caller computing a range off a card may legally
        arrive with nothing to set.

        Announced on `WeaponChanged` like its two siblings, and only when it
        changed something, so arming a trait twice says the same thing once.
        """
        who = self._who(on)
        if who is None or (ranged is None and thrown is None):
            return 0
        gear = self.world.get(who, Gear)
        if gear is None:
            return 0
        from .events import WeaponChanged

        changed = 0
        for weapon in gear.weapons:
            if not ((group and weapon.group == group)
                    or (ref and weapon.ref == ref)):
                continue
            changed += 1
            # `named`, not `field`: `dataclasses.field` is imported at the
            # top of this module and a loop variable would shadow it.
            for named, want in (("ranged", ranged), ("thrown", thrown)):
                if want is None or getattr(weapon, named) == want:
                    continue
                setattr(weapon, named, want)
                self.world.bus.emit(WeaponChanged(
                    actor=who, weapon=weapon.ref,
                    field=named, what=f"{want[0]}/{want[1]}",
                ))
        return changed

    def struck_by_property(self, prop: str, ev: Any = None) -> bool:
        """Did the attack behind this event use a weapon with that property?

        The reading half of `gains_property`, and the shape fourteen
        monster traits print: "when it takes damage from a <property>
        weapon, its regeneration does not function on its next turn".

        `weapon_of` rather than `struck_with`, for the reason that method's
        own docstring gives: `struck_with` prefers whatever magic thing the
        attacker holds, which is right for a ki focus and wrong here -- a
        treated weapon is one weapon, and the other must not carry it.

        False when no weapon can be identified, which is the honest answer
        for an unarmed or implement attack and the one the printed sentence
        wants: a creature not struck *by a weapon* was not struck by one
        with the property.

        **Hand it an attack event, not a `DamageApplied`.** `weapon_of`
        finds the swing through `ev.attacker`, and `DamageApplied` carries
        `source` instead -- so a watch on damage would hand this an event
        with no attacker, get None, and answer False for ever. That is the
        trap this whole family is about and it is one word apart from
        working: watch `Hit`, which carries `attacker`, `target` and the
        power. The printed sentence costs nothing by it, because damage
        *from a weapon* arrives through a hit.
        """
        weapon = self.weapon_of(ev)
        return weapon is not None and prop in weapon.properties

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
        from_: DamageType | None = None,
        ranged: bool = False,
        ref: str = "",
        vs_kind: str = "",
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

        **`from_` narrows which blows it speaks for, and it turned out to
        be one mechanism rather than the two #613 split it into.** An
        unconditional override is `from_=None` and is what every card
        saying "all damage dealt by this weapon is fire" gets. Name a type
        and it becomes a *swap*: `from_=FIRE, dtype=ACID` is "all fire
        damage dealt using this staff as an implement is acid damage",
        which an override cannot say because it has no `from`. Name
        `UNTYPED` and it is the narrow behaviour this method used to have
        by accident -- "all **untyped** damage dealt by ranged attacks
        using this weapon changes to lightning".

        That history is worth keeping straight. `_typed` once recoloured a
        blow only where the card had named no type, so "all damage" quietly
        meant "the untyped part", and every item printing the loud sentence
        got the small thing. Removing it was right. The two cards that
        actually print the narrow sentence get it back by asking, which is
        the difference between a default and an option.

        `ranged=True` is the other half of `i3147x1`'s line and scopes the
        retype to a ranged attack. Read off `self.ranged`, the same flag
        `_weapon_dtype` uses to decide which weapon is swinging.

        **Reversibility needs nothing here.** "Another free action returns
        the damage to normal" is `c.endable` over the effect this returns,
        which is what `i2595p1` already does -- the drop is offered to the
        creature holding it, for a free action.

        **`ref` narrows to one named row** -- "`p1458` deals radiant damage
        instead of fire" -- and is the last of the four narrowings this
        label carries. It is compared against the row being *rolled*, which
        is what `_typed` already holds.

        **`vs_kind` narrows by the creature being hit**, which is the other
        half of that same card: "when used against **undead** targets". A
        creature kind rather than a predicate, deliberately -- `c.deals`
        lays a labelled effect and not a gated modifier, so there is no
        `when=` for a closure to ride, and a callable would have to live on
        the `Effect` where the page reads it. A kind is a closed vocabulary
        `query.kinds_of` already answers, it goes in the label beside the
        other three, and it cannot reach the wire. See `_retyped`.

        Held as a labelled effect rather than written onto the `Weapon`,
        because the weapon object is the character's and the change is
        usually for a fight. Yours, so it defaults to the caster.
        """
        who = on if on is not None else self.me
        for eff in list(self.world.effects.of(who)):
            if eff.label.startswith("deals:"):
                self.world.effects.end(eff, "deals another type now")
        through = Keyword.IMPLEMENT if implement else Keyword.WEAPON
        # **A fixed five-field key.** The label was `deals:<to>:<through>`
        # and nothing outside this file parses it -- the two other mentions
        # in the tree are docstrings using it as an example of a label that
        # is not a ref (#580). Fields rather than flags so `_retyped` reads
        # it by position and an empty one means "does not narrow".
        return self.world.effects.apply(
            who, self.me, until,
            label=(f"deals:{dtype.value}:{through.value}"
                   f":{from_.value if from_ is not None else ''}"
                   f":{'ranged' if ranged else ''}"
                   f":{ref}:{vs_kind}"),
            # A structured key, not a ref: `by` carries the row. #580
            by=self.ref,
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
        keywords = self.keywords_of(p) if p is not None else None
        retype = self._retyped(keywords, dtype)
        if retype is not None:
            return retype
        if dtype is not DamageType.UNTYPED:
            return dtype
        if keywords is not None and Keyword.WEAPON not in keywords:
            return dtype
        return self._weapon_dtype() or dtype

    def _retyped(
        self,
        keywords: Sequence[Keyword] | None,
        printed: DamageType = DamageType.UNTYPED,
    ) -> DamageType | None:
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

        **Five things can make a retype not cover a blow**, and `printed` is
        why this takes the type at all: the keyword it speaks through, the
        type it narrows to (`from_`), whether it is scoped to a ranged
        attack, the one row it names (`ref`), and the kind of creature being
        hit (`vs_kind`). An empty field does not narrow, which is what every
        card saying "all damage" wants.

        **Six fields now, and the padding is what keeps that safe.** A label
        written before any of them existed is three parts long and must go
        on meaning exactly what it meant; the split is padded for that, and
        the precedent is `from_` and `scope`, which were added the same way.
        """
        for eff in self.world.effects.of(self.me):
            if not eff.label.startswith("deals:"):
                continue
            # Positional, and padded: a label written before the two
            # narrowing fields existed has three parts and must keep
            # meaning exactly what it meant.
            parts = [*eff.label.split(":"), "", "", "", "", "", ""][1:7]
            said, through, only, scope, named, kind = parts
            if through and keywords is not None and Keyword(through) not in keywords:
                continue
            if only and DamageType(only) is not printed:
                continue
            if scope == "ranged" and not self.ranged:
                continue
            # One named row, compared against the row being rolled.
            if named and named != self.ref:
                continue
            # And the creature being hit. `c.is_kind` reads the same set
            # `query.kinds_of` answers from, so a stat block's own column
            # and a `c.set_origin` grant both count -- which is the whole
            # reason this is a kind and not a hand-rolled test.
            if kind and not self.is_kind(kind):
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
            who, self.me, until, label=f"{self.ref} decays {arm.ref}", on_end=[restore],
            by=self.ref,
        )

    def draw(self, ref: str = "", *, on: int | None = None) -> bool:
        """Take a stowed weapon up, paying nothing for it.

        "You can draw and attack with a dagger as part of the same standard
        action", "you can draw a weapon before making the attack" -- the
        row has already bought the action, so this is the taking-up on its
        own. `actions._wielding` is the other door and charges the printed
        minor; `draws_free` is what makes *that* door cheaper.

        `ref` names which weapon, for a card that says so. Without it the
        first stowed one is taken, which is what a card saying only "a
        weapon" means.

        False when there is nothing stowed to take, so a row can tell.
        """
        who = on if on is not None else self.me
        gear = self.world.get(who, Gear)
        if gear is None:
            return False
        wanted = [w for w in gear.weapons
                  if w.ref in gear.stowed and (not ref or w.ref == ref)]
        if not wanted:
            return False
        gear.wield(wanted[0])
        self.world.bus.emit(Note(text=f"{who} draws {wanted[0].ref}"))
        return True

    def stow(self, ref: str = "", *, on: int | None = None) -> bool:
        """Put a held weapon away. `draw` read backwards.

        One verb each way rather than one with a flag, because a row says
        one or the other and `c.stow()` reads as the card does. `Gear.wield`
        already stows whatever cannot share a hand with what is taken up,
        so this is only for a card that puts something away and takes up
        nothing.
        """
        who = on if on is not None else self.me
        gear = self.world.get(who, Gear)
        if gear is None:
            return False
        wanted = [w for w in gear.held if not ref or w.ref == ref]
        if not wanted:
            return False
        gear.stowed.add(wanted[0].ref)
        self.world.bus.emit(Note(text=f"{who} stows {wanted[0].ref}"))
        return True

    def draws_free(
        self,
        *,
        cost: ActionType = ActionType.FREE,
        per_turn: int = -1,
        only: str = "",
        on: int | None = None,
        until: When = When.ENCOUNTER,
    ) -> Effect | None:
        """Make taking a weapon up cost less than the printed minor action.

        "Once per turn, you can draw or sheathe a weapon as a free action
        instead of a minor action." The draw itself is already offered --
        `actions._wielding` has done it since a ranger who put the bow away
        could otherwise never pick it up -- and what these rows change is
        what it costs, which is a fact about the creature rather than about
        any row and so cannot sit in a header.

        `per_turn=-1` is a card printing no limit; `1` is the "once per
        turn" the racial trait prints, and `Gear.draws_left` is refilled at
        the start of each of this creature's turns.

        `only` narrows it to one weapon ref, for "you can draw and attack
        with a dagger as part of the same standard action" -- the cheap rate
        is that weapon's, and everything else still costs the printed minor.
        """
        who = on if on is not None else self.me
        gear = self.world.get(who, Gear)
        if gear is None:
            return None
        was = (gear.draw_cost, gear.draws_left, gear.draw_allowance,
               gear.draw_only)

        def restore() -> None:
            (gear.draw_cost, gear.draws_left, gear.draw_allowance,
             gear.draw_only) = was

        # The effect first, as `forbid` and `rolls_with` do.
        effect = self.world.effects.apply(
            who, self.me, until, label=f"{self.ref} draws for {cost.value}",
            by=self.ref,
        )
        if effect is None:
            return None
        gear.draw_cost = cost
        gear.draws_left = gear.draw_allowance = per_turn
        gear.draw_only = only
        # `on_suspend` only -- `Effects._lift` runs it on expiry too.
        effect.on_suspend.append(restore)

        def rearm() -> None:
            gear.draw_cost = cost
            gear.draws_left = gear.draw_allowance = per_turn
            gear.draw_only = only

        effect.on_resume.append(rearm)
        return effect

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
            self.world.bus.emit(
                Note(text=f"{self.ref} cannot disarm {who}: it holds no gear")
            )
            return False
        arm = weapon or gear.main
        if arm is None or arm not in gear.weapons:
            # **Say why.** Every monster in the game reaches this branch --
            # `loader.spawn` hands them `Gear()` with an empty `weapons`, so
            # `gear.main` is None -- and returning a bare False made a row
            # that tried to disarm a creature indistinguishable from one that
            # succeeded against an empty hand. Which the model cannot
            # currently tell apart either, and #518 is where that is decided;
            # this is only the half that is right under every answer.
            self.world.bus.emit(
                Note(text=f"{self.ref} cannot disarm {who}: nothing in hand")
            )
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
            by=self.ref,
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
                # `DEFENCES` and not the enum: `Defense.ANY` is an instruction
                # rather than a defence, and a creature holding a zero under
                # that key would be answering a question `query.defence`
                # resolves for itself.
                Defenses(values=dict.fromkeys(DEFENCES, 0), scale="none"),
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
            by=self.ref,
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


def _weapon_is(weapon: Any, word: str) -> bool:
    """Does this weapon answer to that word?

    The same three tests `Cast.wielding` makes of a printed Requirement --
    property, group, category -- **and the slug besides**, because a card
    saying "you can use a warhammer with ..." names one weapon and a
    warhammer has no group of its own to be named by.

    The slug is deliberately *not* added to `wielding`'s own test: 78 rows
    call it and widening what satisfies a Requirement would quietly let
    some of them through on a weapon their card never mentioned. Only the
    waiver side matches this loosely.
    """
    return bool(
        word
        and (
            word in weapon.properties
            or weapon.group == word
            or weapon.category == word
            or weapon.slug == word
        )
    )


def _faces_of(dice: str | int) -> int:
    """How many faces each die of this expression has. 0 for a flat number.

    Parsed the same way `_max_of` below parses it, and for the same reason
    its note gives: a flat damage line is a real expression and not a
    malformed one, so it has to answer rather than raise.
    """
    if isinstance(dice, int) or not dice or "d" not in dice:
        return 0
    _, _, rest = dice.partition("d")
    faces, sign, _tail = rest.partition("+")
    if not sign:
        faces, _sign, _tail = rest.partition("-")
    return int(faces) if faces.isdigit() else 0


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


def _drop_roll(known: Any, ref: str, entry: tuple) -> None:
    """Undo one `c.rolls_with`, leaving any others on the same row alone.

    By identity rather than by value: two feats may lay the same ability on
    the same row, and removing "a matching pair" would take both away when
    the first of them expired.
    """
    swaps = known.rolls.get(ref)
    if not swaps:
        return
    for i, held in enumerate(swaps):
        if held is entry:
            del swaps[i]
            break
    if not swaps:
        known.rolls.pop(ref, None)


def _drop_entry(store: dict, key: Any, entry: tuple) -> None:
    """Undo one `c.pre_empt`, by identity, for the reason above.

    Takes the dict rather than a named attribute on `Powers`, because the
    key is a `(ref, what)` pair rather than a bare ref.
    """
    held = store.get(key)
    if not held:
        return
    for i, sitting in enumerate(held):
        if sitting is entry:
            del held[i]
            break
    if not held:
        store.pop(key, None)


def _drop_squares(known: Any, ref: str, entry: tuple) -> None:
    """Undo one `c.extend_move`, by identity, for the reason `_drop_dice`
    gives: two feats may grant the same number of squares to the same row,
    and removing by value would take the wrong one off."""
    held = known.extra_squares.get(ref)
    if not held:
        return
    for i, one in enumerate(held):
        if one is entry:
            del held[i]
            break


def _drop_amount(known: Any, ref: str, entry: tuple) -> None:
    """Undo one `c.change_amount`, by identity, for the reason above."""
    held = known.amounts.get(ref)
    if not held:
        return
    for i, one in enumerate(held):
        if one is entry:
            del held[i]
            break
    if not held:
        known.amounts.pop(ref, None)


def _drop_dice(known: Any, ref: str, entry: tuple) -> None:
    """Undo one `c.change_dice`, by identity, for the reason above."""
    held = known.dice.get(ref)
    if not held:
        return
    for i, one in enumerate(held):
        if one is entry:
            del held[i]
            break
    if not held:
        known.dice.pop(ref, None)
