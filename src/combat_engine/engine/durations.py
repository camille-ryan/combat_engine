"""How long things last.

One `Effect` is one thing a power did that has not finished happening: a
condition, some modifiers, a relation, ongoing damage, a registered trigger,
or several at once. It knows how to take itself back apart, so ending it is
never a matter of remembering what it did.

**The latch.** "Until the end of your next turn" is the one duration engines
get wrong. Applied on somebody else's turn it expires at the end of your next
turn -- the very next one. Applied on *your own* turn, your next turn is the
one after the current one, so the current turn's end has to be skipped.
`latch` is that skipped boundary, and it is set from whose turn it is at the
moment of application. Without it, half of 4e's effects expire a full turn
early and every fight quietly reads wrong.

The start-of-turn durations need no latch: your current turn has already
started, so the next `TurnStart` naming you is already your next turn.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from .components import Conditions, Health, Mod, Mods
from .events import (
    ConditionApplied,
    ConditionEnded,
    EffectApplied,
    EffectExpired,
    EffectSuspended,
    Escaped,
    Note,
    SavingThrow,
    TurnEnd,
    TurnStart,
)
from .query import immune_to
from .types import ActionType, Condition, DamageType, Relation

if TYPE_CHECKING:
    from .ecs import World
    from .events import Sub


class When(StrEnum):
    INSTANT = "instant"
    #: The end of the turn happening right now. Distinct from EONT, which
    #: latches past it to the end of your *next* turn -- a power reading
    #: "on your next attack this turn" needs this one and had no spelling.
    EOT = "end of this turn"
    EONT = "end of source's next turn"
    SONT = "start of source's next turn"
    EOTNT = "end of target's next turn"
    SOTNT = "start of target's next turn"
    SAVE_ENDS = "save ends"
    ENCOUNTER = "end of encounter"
    STANCE = "stance"
    SUSTAIN = "sustain"
    #: "Restrained **until escape**", "immobilized and cannot stand (until
    #: escape)". The clock is the held creature getting out, which is an
    #: event and not a turn boundary -- four rows print it and all four hung
    #: the condition on `ENCOUNTER` instead, so it outlasted the grab.
    #:
    #: Ended by `_on_escape` on a **successful** `Escaped`, and `Escaped` is
    #: emitted for a failed attempt too, which is the trap: gating on the
    #: event alone frees the creature the first time it tries.
    ESCAPE = "until it escapes"


#: Durations whose clock is the creature the effect sits on rather than the
#: creature that applied it.
_TARGET_CLOCKED = {When.EOTNT, When.SOTNT, When.SAVE_ENDS}

#: Durations that no turn boundary will ever end. If the creature holding one
#: up dies, nothing is coming to clear it, so death has to.
#: `ESCAPE` belongs here and not in `_TARGET_CLOCKED`: that set is about
#: *whose turn* drives the clock, and no turn is involved in getting out of a
#: grab. What this set means is that nothing routine will ever end it, so if
#: the grabber dies, death has to -- which is the right answer for a hold
#: that only its holder sustains.
_UNREACHABLE = {When.ENCOUNTER, When.STANCE, When.SUSTAIN, When.ESCAPE}


@dataclass
class Effect:
    id: int
    label: str
    owner: int
    source: int
    when: When
    clock: int
    latch: bool = False
    conditions: tuple[Condition, ...] = ()
    mods: list[tuple[int, Mod]] = field(default_factory=list)
    relations: list[tuple[Relation, int, int]] = field(default_factory=list)
    ongoing: tuple[int, DamageType] | None = None
    #: The whole type of the burn, for one that is more than a single type
    #: -- "ongoing 5 fire and radiant damage" is five points a turn that
    #: are both, and it is shrugged off only as far as the creature
    #: resists both. Empty means "just `ongoing[1]`", which is every burn
    #: that is of one type. Kept beside `ongoing` rather than inside it so
    #: that the readers asking `eff.ongoing[1]` go on answering.
    ongoing_types: tuple[DamageType, ...] = ()
    #: The printed DC to escape this grab, when the card states a flat number
    #: instead of leaving it to the grabber's defence.
    #:
    #: **It replaces the defence, it does not add to it.** 53 of the 58 rows
    #: printing one print a number matching neither the grabber's Fortitude nor
    #: its Reflex, and almost always lower -- so held creatures were 3 to 7
    #: points harder to free than their cards say. `grab_defence` stays
    #: additive and is a different sentence ("a bonus to your defences when
    #: preventing an escape"). #421.
    #:
    #: `0` is "no printed DC", which is the common case and keeps the computed
    #: defence. Lives on the `Effect` rather than on the relation because a
    #: relation carries no numbers, and one creature can be held by two
    #: grabbers with different printed DCs.
    escape_dc: int = 0
    save_mod: int = 0
    #: Runs on a failed save. This is how "and worsens" powers are written.
    escalate: Callable[[Effect], None] | None = None
    subs: list[Sub] = field(default_factory=list)
    on_end: list[Callable[[], None]] = field(default_factory=list)
    #: Runs each time the effect is sustained. A sustain line that also
    #: deals damage or moves somebody has a payout half, and the clock
    #: refreshing was all that ever happened -- so that half was silently
    #: dropped from every row of that shape in the game.
    on_sustain: list[Callable[[], None]] = field(default_factory=list)
    sustained: int = -1
    #: What keeping this going costs, for a `When.SUSTAIN` effect. The
    #: printed line names it -- "Sustain Minor" is the common one.
    sustain_cost: ActionType | None = None
    #: What ending it *deliberately* costs, when the printed line offers
    #: that -- "reverting to your normal form is a minor action". Distinct
    #: from `sustain_cost`: one keeps a thing alive, the other kills it.
    drop_cost: ActionType | None = None
    #: What ending it deliberately *buys*, when the printed line offers a
    #: trade rather than a dismissal -- "the ally can end the effect as a
    #: free action to teleport", "the target can end the effect by taking
    #: 5 damage". Runs only for a deliberate drop, which is why it cannot
    #: be an `on_end`: those fire for the clock and the saving throw too,
    #: and a payout owed for choosing is not owed for waiting.
    drop_then: Callable[[], None] | None = None
    ended: bool = False
    #: Lifted but not ended -- everything it installed is off the creature and
    #: the effect is still standing, still clocked, still owed its saving
    #: throw. The printed shape is "when it takes fire damage it loses this
    #: trait until the start of its next turn": the trait does not *end*, or
    #: an encounter-long duration would be spent by one hit, and the creature
    #: would never get it back.
    #:
    #: Readers consult nothing. `suspend` runs the same teardown `end` runs,
    #: so a suspended condition is absent from `Conditions`, a suspended mod
    #: is out of `Mods`, and a suspended relation is cleared -- which is why
    #: 325 importers of `query` did not have to learn the word.
    suspended: bool = False
    #: Hooks for state the effect holds that `apply` did not install -- a
    #: label in `Movement.ignores`, a number in `Defences.vulnerable`. Those
    #: verbs maintain their own side state, so they lift and restore it
    #: themselves. An effect carrying only installed state needs neither.
    on_suspend: list[Callable[[], None]] = field(default_factory=list)
    on_resume: list[Callable[[], None]] = field(default_factory=list)
    #: A replacement **shape** for another row's area. `Mod.value` is an
    #: `int`, so `c.bonus("blast_size", n)` can stretch a burst and can
    #: never turn one into a blast -- which is the one word the six cards
    #: under #614 need and no integer can say. This is that one layer up:
    #: the modifier arrangement is proven (`dsl._stretched` has three live
    #: consumers), and what it lacks is a carrier for a `Range`.
    #:
    #: **A callable on the printed range, not a fixed `Range`.** `i2467p1`
    #: prints "its area changed to 1 square (**within the same range**)",
    #: so the replacement is derived from what it replaces and a literal
    #: could not say it -- the `within` is the power's, not the wand's.
    #:
    #: Here rather than in `Mods` so expiry comes free: an ordinary turn
    #: boundary or a saving throw takes it off with everything else the
    #: effect installed, and `suspend` lifts it for nothing extra.
    #:
    #: Typed loosely because `Range` lives in `dsl`, which imports this
    #: module. See `dsl._reshaped`, the one reader.
    reshape: Callable[[Any], Any] | None = None
    #: What the reshape applies to, read the way `_stretched`'s modifiers
    #: are: a predicate on a context carrying the row being measured and
    #: its printed kind. Without it a wand that reshapes "the next area
    #: burst" would reshape a melee swing.
    reshape_when: Callable[[dict[str, Any]], bool] | None = None
    #: A standing replacement for a row's **target line**, beside the
    #: replacement for its shape above.
    #:
    #: Two heroic weapon blocks turn a single-target ranged basic attack into
    #: "a burst 1 centered on the target", and the sentence goes on to say
    #: "each **target** hit" -- so the line itself widens. Reshaping the
    #: range alone left `_auto_targets` honouring the printed
    #: `ONE_CREATURE`, which made the burst hit exactly one creature: the
    #: right shape drawn on the board and the wrong number of rolls. A board
    #: with only one enemy in the burst cannot tell those apart, and a plant
    #: is what found it.
    #:
    #: Read by `dsl.target_of`, the door the way `dsl.reach_of` is the door
    #: for `reshape`. Shares `reshape_when`, because a card rewriting both
    #: rewrites them for the same attack. #712.
    retarget: Any = None
    #: **Does the reshape replace the printed shape, or offer an alternative
    #: to it?** `False` replaces, which is what every caller meant until now
    #: and what `i2467p1` needs: the wand's *activation* is the choice, and
    #: once it is used the new area is forced for that one attack.
    #:
    #: `True` adds an aiming instead. Eleven heroic rows print "you can
    #: **choose** to make it X **instead of** Y", where both shapes stay on
    #: the menu -- replacing would take the printed one away and leave a
    #: sorcerer unable to throw the close blast its card still lists, which
    #: is worse than the card rather than merely different. #614.
    #:
    #: Read by `dsl.branches_for`, which turns each one in force into an
    #: extra branch index, and by `dsl.reach_of`, which resolves that index.
    reshape_optional: bool = False
    #: **Who rolls the saving throw that ends this**, when that is not the
    #: creature the effect sits on. `0` means "the owner", which is every
    #: effect in the tree but one.
    #:
    #: `durations.save` read `eff.owner` for *three* different questions --
    #: who rolls, whose save bonus applies, and who the `SavingThrow` is
    #: announced for -- so an effect that benefits one creature and is
    #: ended by another's save could not be written at all. `i806p1`
    #: prints "reduce the value of any resistance the target has against
    #: **your** attack by 5 (save ends)": the `Mod` must sit on the
    #: attacker, because that is what narrows the clause to your attack,
    #: while the printed clock is a throw made by the target. A
    #: `SAVE_ENDS` duration there had the attacker rolling to end its own
    #: benefit.
    #:
    #: **Separate from `clock`, which is a different question.** `clock`
    #: decides *when* the throw is taken (`eff.clock == ev.actor` at a
    #: turn's end); this decides *whose throw it is*. Reassigning `clock`
    #: alone moved the timing and left the roll with the wrong creature,
    #: which is why #874 could not be solved with the field that already
    #: existed. A row wanting the target's save at the target's turn end
    #: sets both.
    #:
    #: `p2919` is the near miss and does not generalise: it carries a
    #: save-ends hold for somebody else by laying a **relation** on the
    #: target, which works because a relation is directional. A `Mod` is
    #: read off the creature it sits on, so it cannot move. #874.
    saver: int = 0

    @property
    def rolls_the_save(self) -> int:
        """The creature whose saving throw ends this -- `saver` or `owner`."""
        return self.saver or self.owner

    def __str__(self) -> str:
        bits = [self.label or "effect", self.when.value]
        if self.ongoing:
            kinds = " and ".join(
                t.value for t in (self.ongoing_types or (self.ongoing[1],))
            )
            bits.append(f"ongoing {self.ongoing[0]} {kinds}")
        return f"e{self.id}[{', '.join(bits)}]"


def _with_weapon(ev: object, eff: object) -> object:
    """Hang the weapon the hold came through on the announcement.

    **An attribute, not a field**, for the reason `Effect.by` is one: a
    field reaches the wire and every replay fixture, and which arm swung is
    not a change in how a fight resolves. Declared as a field first and all
    seven fixtures diverged.

    **Two emit sites, which is why this is a function.** `ConditionApplied`
    is announced when an effect is installed *and* when a suspended one
    comes back, and patching only the first left the stamp empty on the path
    a `c.condition` from a `Cast` actually takes -- measured, `[''] wanted
    w3612`, with the effect itself carrying the ref correctly. #653.
    """
    ev.weapon = getattr(eff, "weapon", "")  # ty: ignore[unresolved-attribute]
    return ev


def keywords_of(which: object) -> frozenset:
    """The keywords of the row that laid an effect.

    Takes the **effect** or its label. Pass the effect where you have one:
    it carries `by`, the ref of the row that laid it, and the label does
    not always. Six sites in `cast.py` label by content rather than by ref
    -- `c.ongoing` writes `"ongoing 5"`, `c.deals` writes
    `"deals:fire:weapon"` -- and for those the label answers nothing while
    `by` answers correctly. #580.

    `Effect` carries no keywords, and giving it some would mean every
    site that lays one passing them down. It does not have to: an
    effect's label is the ref of the row that laid it -- `c.effect`,
    `c.bonus` and `c.condition` all stamp it -- and the row knows its
    own keywords.

    So "a +2 bonus to saving throws against **charm** effects" is
    answerable today, and eighteen rows were carrying
    `SavingThrow.keywords` for want of the lookup. A label that is not
    a ref, or a ref no longer declared, answers the empty set rather
    than raising: a made-up label is a row saying the effect is its
    own, not a row making a claim about keywords.
    """
    from .dsl import get

    # The effect knows which row laid it; a bare label only sometimes does.
    by = getattr(which, "by", None)
    label = by if by else (which if isinstance(which, str)
                           else getattr(which, "label", "") or "")
    p = get(label.split()[0]) if label else None
    # **`frozenset`, not the tuple `Power.keywords` is.** The annotation
    # said frozenset and the return did not, so `{Keyword.FEAR} & ...`
    # raised `TypeError` -- and the audit board never lays a
    # keyword-bearing hold, so three rows written that way passed clean
    # and only a hand-driven board found it.
    # **The header, because there is no creature here to ask about.** This
    # takes a label and nothing else, so `dsl.keywords_of` cannot be used:
    # a keyword a feat granted one character is invisible at this site.
    # It matters for one row -- `f1538` grants `FEAR` to every attack, and
    # a save against a fear effect reads this -- so `f1538` keeps a marker
    # naming it rather than being written and quietly half-working. #483.
    return frozenset(p.keywords) if p is not None else frozenset()


class Effects:
    """Every live effect, and the turn boundaries that end them."""

    def __init__(self, world: World) -> None:
        self.world = world
        self.live: dict[int, Effect] = {}
        #: True only while `end_encounter` is tearing the board down. Read by
        #: `Cast.aftereffect`, which must not fire then.
        self.closing = False
        self._next = 0
        world.bus.on(TurnStart, self._on_turn_start)
        # Last in its window. Expiry is the close of the turn, not the start
        # of its ending -- a row reading "if the target ends its next turn
        # ..." had its watch removed before the watch could answer.
        world.bus.on(TurnEnd, self._on_turn_end, late=True)
        world.bus.on(Escaped, self._on_escape)

    def _on_escape(self, ev: Escaped) -> None:
        """A `When.ESCAPE` hold ends when its own grab is broken.

        **Both halves of the match are load-bearing.**

        `ev.success` -- `Escaped` is emitted for a failed attempt as well,
        because "whenever a creature fails an escape attempt against you" is
        printed as often as the other half. An unguarded subscription frees
        the creature the first time it struggles.

        `eff.source == ev.holder` -- a creature can be held by two grabbers
        at once, which `Effect.grab_dc`'s own note states ("one creature can
        be held by two grabbers with different printed DCs"). Getting out of
        one grab must not lift a hold hung on the other, and a board with a
        single grabber cannot tell the two readings apart.
        """
        if not ev.success:
            return
        for eff in list(self.live.values()):
            if (
                eff.when is When.ESCAPE
                and eff.owner == ev.actor
                and eff.source == ev.holder
            ):
                self.end(eff, "it escaped")

    # -- applying ------------------------------------------------------------

    def apply(
        self,
        owner: int,
        source: int,
        when: When,
        *,
        label: str = "",
        conditions: Iterable[Condition] = (),
        mods: Iterable[tuple[int, Mod]] = (),
        relations: Iterable[tuple[Relation, int, int]] = (),
        ongoing: tuple[int, DamageType] | None = None,
        ongoing_types: tuple[DamageType, ...] = (),
        escape_dc: int = 0,
        save_mod: int = 0,
        escalate: Callable[[Effect], None] | None = None,
        subs: Iterable[Sub] = (),
        on_end: Iterable[Callable[[], None]] = (),
        on_suspend: Iterable[Callable[[], None]] = (),
        on_resume: Iterable[Callable[[], None]] = (),
        sustain_cost: ActionType | None = None,
        drop_cost: ActionType | None = None,
        reshape: Callable[[Any], Any] | None = None,
        reshape_when: Callable[[dict[str, Any]], bool] | None = None,
        retarget: Any = None,
        reshape_optional: bool = False,
        by: str = "",
        weapon: str = "",
        saver: int = 0,
    ) -> Effect:
        # Ongoing damage of one type does not stack -- the highest applies.
        # The rule lived in `Cast.ongoing` alone, and this is the door a
        # "save ends both" hold goes through when it carries a burn *and* a
        # condition on one saving throw, which is the commonest shape at
        # paragon. So the same blade swung twice laid two burns here while
        # `c.ongoing` correctly refused the second.
        if ongoing is not None:
            amount, dtype = ongoing
            # **Same type** means the same *set* of types. A burn that is
            # fire and radiant at once is not the fire burn already
            # standing -- neither supersedes the other, and the printed
            # rule only ever compares like with like.
            mine = tuple(ongoing_types) or (dtype,)
            standing = [
                e for e in self.of(owner)
                if e.ongoing is not None
                and (tuple(e.ongoing_types) or (e.ongoing[1],)) == mine
            ]
            worst = max((e.ongoing[0] for e in standing), default=0)
            if worst >= amount:
                # Nothing to add. The caller still gets an effect back, so a
                # row that applies a condition alongside its burn is not
                # silently dropped -- only the burn is.
                ongoing = None
                ongoing_types = ()
            else:
                for e in standing:
                    self.end(e, "superseded by worse of the same type")

        # "You cannot be slowed until the end of your next turn" is refused
        # here rather than by the callers, because every route to a
        # condition -- `c.condition`, an escalating save-ends rider, a
        # monster trait -- comes through this one door. The rest of the
        # effect still lands: a hold that slows *and* burns is only immune
        # to half of itself.
        conditions = list(conditions)
        # `label` is the laying row's ref for every content call that passes
        # one, which is what a keyword-narrowed immunity needs (#309). A few
        # engine sites label with a plain word -- "dead", "dropped", "fall",
        # "surprised" -- and those resolve to no row, so a gate asking for a
        # keyword is correctly False rather than wrongly true.
        refused = [
            c for c in conditions
            if immune_to(self.world, owner, c, source, label)
        ]
        if refused:
            conditions = [c for c in conditions if c not in refused]
            self.world.bus.emit(
                Note(text=f"{owner} is immune to "
                          f"{', '.join(c.value for c in refused)}")
            )

        self._next += 1
        clock = owner if when in _TARGET_CLOCKED else source
        eff = Effect(
            id=self._next,
            label=label,
            owner=owner,
            source=source,
            when=when,
            clock=clock,
            latch=(when in (When.EONT, When.EOTNT) and self.world.turn == clock),
            conditions=tuple(conditions),
            mods=list(mods),
            relations=list(relations),
            ongoing=ongoing,
            ongoing_types=tuple(ongoing_types) if ongoing else (),
            escape_dc=escape_dc,
            save_mod=save_mod,
            escalate=escalate,
            subs=list(subs),
            on_end=list(on_end),
            on_suspend=list(on_suspend),
            on_resume=list(on_resume),
            sustained=self.world.round,
            sustain_cost=sustain_cost,
            drop_cost=drop_cost,
            reshape=reshape,
            reshape_when=reshape_when,
            retarget=retarget,
            reshape_optional=reshape_optional,
            saver=saver,
        )
        # **The ref of the row that laid this, as a plain attribute.**
        #
        # `keywords_of` below has always answered "which keywords does this
        # effect have" by taking the **first word of the label** and looking
        # it up as a ref -- which works because almost every site labels with
        # its own ref, and silently fails for the few that label by content.
        # `c.ongoing` writes `"ongoing 5"` and `c.deals` writes
        # `"deals:fire:weapon"`, so a psychic monster's burn answered *no
        # keywords* and `p16438`'s augment -- "make a saving throw against any
        # charm or psychic effect at the start of your turn" -- was told the
        # psychic effect was not psychic. 62 rows carry a watched keyword and
        # lay a label of that shape. #580.
        #
        # **An attribute, not a field**, on Camille's call and for the reason
        # `Moved.kind_` records: a field would reach the wire and every replay
        # fixture, neither of which is a change in how a fight resolves.
        #
        # **Defaulted from the label**, so all 333 call sites keep exactly
        # today's behaviour and only the six in `cast.py` that label by
        # content need to say anything.
        eff.by = by or (label.split()[0] if label else "")
        # **And which weapon the blow came through**, an attribute for the
        # reason `by` above is one. `ConditionApplied.power` answers the
        # clause's keyword and the attack's shape and says nothing about
        # which arm did it, so "when you immobilize a target with a melee
        # attack **using this weapon**" had nothing to ask. Defaulted empty,
        # so all 333 call sites keep today's behaviour and only `c.condition`
        # says anything. #653.
        eff.weapon = weapon
        self.live[eff.id] = eff

        # Everything the effect installs goes on **before** anything is
        # announced. It used to emit `ConditionApplied` first, so a listener
        # that ended the effect during that emit -- which any reaction
        # watching for a condition can do -- ran `end()` while the mods list
        # was still empty. `end()` removed nothing, `apply()` then installed
        # them anyway, and the creature kept a modifier with no live effect
        # left to ever take it off. A permanent -2 to attack, from a save-ends
        # effect that had already been saved against.
        self._install_state(eff)

        # Announced for every effect, not only the ones that impose a
        # condition. A save-ends effect carrying nothing but ongoing damage
        # said nothing at all, so "subject to an effect a save can end"
        # could only be declared on the half of the cases that daze you.
        self.world.bus.emit(
            EffectApplied(
                source=source, target=owner, duration=when.value,
                label=eff.label, save_ends=when is When.SAVE_ENDS,
            )
        )
        self._warn_sustainless(eff)

        self._install_conditions(eff, source, when.value)

        if when is When.INSTANT:
            self.end(eff, "instant")
        return eff

    def worsen(self, eff: Effect, cond: Condition, source: int = 0) -> bool:
        """Add a condition to a hold that is already standing.

        "First Failed Saving Throw: the target is **also** dazed (save ends
        both)" is **one** effect carrying two conditions, because that is what
        makes one save end both -- a second save-ends effect laid beside it
        hands the victim a second saving throw against one printed sentence.

        **Joining `eff.conditions` is not enough and looks like it is.** `end`
        reads the mutated tuple, so teardown works perfectly: the hold expires
        and clears a daze it never imposed. What the tuple alone does not reach
        is `Conditions`, the cache `apply` fills as it installs and every
        `query.is_` reads -- so the effect said "dazed" and every question about
        the creature said no. Finished-looking and inert, and measured that way.

        This is why it is here rather than in content. The three steps -- join
        the tuple, reach `Conditions`, emit `ConditionApplied` -- were a helper
        in a level-3 monster file, imported across two other content files and
        reaching into `engine.components` from a component that has no business
        there. #367.

        Returns whether anything changed, so a second failed save does not
        double a condition the first one already imposed.
        """
        if cond in eff.conditions:
            return False
        eff.conditions = (*eff.conditions, cond)
        # Made when missing, for `_install_conditions`'s reason -- and this
        # site is the worse of the two to leave, because it is the escalation
        # a *failed save* imposes: the one moment the fiction is at its most
        # pointed, returning False and saying nothing. #635.
        conds = self.world.get(eff.owner, Conditions)
        if conds is None:
            conds = self.world.add(eff.owner, Conditions())
        if not conds.add(cond):
            return False
        self.world.bus.emit(_with_weapon(
            ConditionApplied(
                source=source or eff.owner, target=eff.owner,
                condition=cond, duration=eff.when.value,
                # The row that laid the effect. `by` is defaulted from the
                # label, so this is the ref for all 333 call sites without
                # any of them saying anything.
                power=eff.by,  # ty: ignore[unresolved-attribute]
            ),
            eff,
        ))
        return True

    # -- installing and lifting ----------------------------------------------
    #
    # Expiring an effect and suspending one remove exactly the same state. The
    # only difference is whether the effect is still standing afterwards -- so
    # one lift serves both, and that is the whole reason these are factored
    # out. Two teardown paths that were *meant* to match is how a modifier
    # gets left on a creature with no effect behind it, which this file has
    # already paid for once.

    def _install_state(self, eff: Effect) -> None:
        """Lay the mods and relations. Called before the announce, see `apply`."""
        for eid, mod in eff.mods:
            holder = self.world.get(eid, Mods)
            if holder is None:
                holder = self.world.add(eid, Mods())
            holder.items.append(mod)
        for kind, s, t in eff.relations:
            # `eff.by` is the ref of the row that laid this effect, stamped
            # at `apply`. Passing it here is what gives every mark its
            # provenance for free -- the alternative was widening the
            # three-tuple above and moving ten content sites. #875.
            self.world.relations.set(
                kind, s, t, via=getattr(eff, "by", "") or "",
            )

    def _install_conditions(self, eff: Effect, source: int, duration: str) -> None:
        """Lay the conditions and announce each one that was not already held.

        **The component is made when it is missing**, which is what `Mods`
        three lines above this has always done and what conditions did not.
        A creature without a `Conditions` component silently swallowed every
        condition ever laid on it: no state, no `ConditionApplied`, and no
        complaint -- while `c.dazed` returned a complete `Effect` carrying
        `conditions=(DAZED,)`, so the caller had every reason to think it
        worked. The exact silently-false shape this component's own file
        warns about.

        Three creature-spawning sites lack the component --
        `Cast.call_companion`'s no-stat-block branch, `Cast.summon_inline`,
        and the spawn at `cast.py:4610` -- so **no called familiar, spirit or
        inline summon could be dazed, slowed, immobilised or stunned.** The
        engine could not even kill one: `resolve._die` applies
        `Condition.DEAD` through this door, so a dead familiar read as alive
        and, being a `Companion` with `passive` still False, as *actively
        standing there*.

        Fixed here rather than at the three sites because fixing those one at
        a time is what produced this. `call_companion`'s own comments record
        the same class of bug twice already -- a missing `Ident` that made the
        renderer raise, a missing `Stats` that blew up four rows -- and both
        were found at once because they **raised**. This one does not. #635.
        """
        conds = self.world.get(eff.owner, Conditions)
        if conds is None and eff.conditions:
            conds = self.world.add(eff.owner, Conditions())
        for c in eff.conditions:
            if conds is not None and conds.add(c):
                self.world.bus.emit(
                    _with_weapon(
                        ConditionApplied(
                            source=source, target=eff.owner, condition=c,
                            duration=duration, power=eff.by,  # ty: ignore[unresolved-attribute]
                        ),
                        eff,
                    )
                )

    def _lift(self, eff: Effect, why: str) -> None:
        """Take off everything the effect installed. It stays standing.

        `on_suspend` runs here and **not** in `end`, which is what makes the
        accounting exact: a verb holding side state of its own -- a label in
        `Movement.ignores`, a number in `Defences.vulnerable` -- names its
        undo once, and that undo runs once whether the effect is suspended or
        expired. Put the same undo in both lists and `vulnerable 5` would
        subtract ten.
        """
        conds = self.world.get(eff.owner, Conditions)
        for c in eff.conditions:
            if conds is not None and conds.remove(c):
                self.world.bus.emit(ConditionEnded(target=eff.owner, condition=c, why=why))
        for eid, mod in eff.mods:
            holder = self.world.get(eid, Mods)
            if holder is not None and mod in holder.items:
                holder.items.remove(mod)
        for kind, s, t in eff.relations:
            self.world.relations.clear(kind, s, t, why)
        for fn in eff.on_suspend:
            fn()

    def suspend(self, eff: Effect, why: str = "suspended") -> bool:
        """Lift the effect without ending it. Returns whether anything moved.

        "When it takes fire or radiant damage it loses this trait until the
        start of its next turn" is this, and `end` is the wrong verb for it
        twice over: the encounter-long duration would be spent by one hit, and
        a save-ends hold would stop owing its saving throw.

        The subscriptions stay registered and go quiet instead -- `Cast.watch`
        checks the flag before running the handler -- because re-registering a
        sub on resume would mean storing the event class and window to rebuild
        it from, and a watcher that fires while suspended is the same bug as a
        modifier that still applies.
        """
        if eff.ended or eff.suspended:
            return False
        eff.suspended = True
        self._lift(eff, why)
        # **Announced, because a lifted modifier is otherwise invisible.**
        # `_lift` emits what a condition leaving needs and nothing for a
        # modifier, so a row whose whole content is suspension did its work
        # and read silent. See `EffectSuspended`.
        self.world.bus.emit(
            EffectSuspended(actor=eff.owner, what=str(eff), why=why)
        )
        return True

    def resume(self, eff: Effect) -> bool:
        """Put back what `suspend` lifted. Returns whether anything moved."""
        if eff.ended or not eff.suspended:
            return False
        eff.suspended = False
        self._install_state(eff)
        self._install_conditions(eff, eff.source, eff.when.value)
        for fn in eff.on_resume:
            fn()
        self.world.bus.emit(
            EffectSuspended(actor=eff.owner, what=str(eff), why="resumed",
                            back=True)
        )
        return True

    # -- ending --------------------------------------------------------------

    def end(self, eff: Effect, why: str = "expired") -> None:
        if eff.ended:
            return
        eff.ended = True
        self.live.pop(eff.id, None)

        # **A suspended effect has already been lifted.** Lifting twice emits
        # a second `ConditionEnded` for a condition nobody holds, and
        # decrements a refcount another effect is relying on.
        if not eff.suspended:
            self._lift(eff, why)
        for sub in eff.subs:
            self.world.bus.off(sub)
        for fn in eff.on_end:
            fn()
        if eff.when is not When.INSTANT:
            self.world.bus.emit(EffectExpired(actor=eff.owner, what=str(eff), why=why))

    def cure(self, owner: int, conditions: Iterable[Condition]) -> list[Condition]:
        """Strip standing conditions off a creature. Returns what went.

        Not `end`: a printed "remove one condition from the target" takes
        the condition and leaves the rest of the effect that carried it, so
        a save-ends hold that dazes *and* burns keeps burning. Ending the
        whole effect would also hand back the saving throw it is still
        owed.

        The relational ones -- marked, grabbed, dominated -- are held by
        `relations` and only mirrored into `Conditions`, so clearing the
        count alone would leave the mark itself standing and the creature
        marked by somebody with no mark on it.
        """
        from .relations import IMPLIES

        wanted = set(conditions)
        gone: list[Condition] = []
        conds = self.world.get(owner, Conditions)
        for kind, cond in IMPLIES.items():
            if cond not in wanted:
                continue
            for source in self.world.relations.sources(kind, owner):
                self.world.relations.clear(kind, source, owner, "removed")
                gone.append(cond)
        for eff in list(self.live.values()):
            if eff.owner != owner:
                continue
            dropped = [c for c in eff.conditions if c in wanted]
            if not dropped:
                continue
            eff.conditions = tuple(c for c in eff.conditions if c not in wanted)
            for c in dropped:
                if conds is not None and conds.remove(c):
                    self.world.bus.emit(
                        ConditionEnded(target=owner, condition=c, why="removed")
                    )
            gone.extend(dropped)
            if not eff.conditions and not eff.mods and not eff.relations \
                    and eff.ongoing is None and not eff.subs:
                self.end(eff, "removed")
        return gone

    def forget(self, eid: int, why: str = "left play") -> None:
        """End everything `eid` is either end of. Total removal only."""
        for eff in list(self.live.values()):
            if eff.owner == eid or eff.source == eid or eff.clock == eid:
                self.end(eff, why)

    def bereave(self, eid: int, why: str = "died") -> None:
        """Clean up after a creature's death without cutting durations short.

        A daze that lasts "until the end of your next turn" does **not** end
        the instant you are killed. It ends when you would have acted -- the
        effect runs to your slot in the initiative order and expires there.
        `Encounter` keeps the dead in the order and ticks a silent turn for
        exactly this, so a turn-clocked effect needs no help here.

        What does need help is everything with no clock to reach:

        * effects *on* the corpse, which are meaningless now;
        * effects it was the source of that expire at the end of the
          encounter, on a stance, or on being sustained -- nothing will ever
          come to end those, so they would hang forever.

        A save-ends effect is clocked on whoever is suffering it, so the
        source dying is none of its business either way.
        """
        for eff in list(self.live.values()):
            on_the_corpse = eff.owner == eid
            nothing_will_end_it = eff.source == eid and eff.when in _UNREACHABLE
            # A zone is *somewhere*, not something the dead creature is
            # still doing, so its own effect outlives whoever lit it. A
            # death throe that sets a fire "until the end of the encounter"
            # had it lit and swept away in the same breath -- `Dropped`
            # fires the throe and `_die` calls this immediately after -- and
            # the row read as finished. `end_encounter` is what ends these.
            if nothing_will_end_it and self.world.get(eff.owner, Health) is None:
                continue
            if on_the_corpse or nothing_will_end_it:
                self.end(eff, why)

    def end_encounter(self) -> None:
        # **Flagged while it runs, because an aftereffect must not land on a
        # finished fight.** `on_end` fires for every end alike -- a save, a
        # clock, a death, the encounter closing -- and it is handed no reason,
        # so a clause that is supposed to follow a hold ending would also
        # follow the whole board being torn down. `Cast.aftereffect` reads
        # this.
        self.closing = True
        try:
            for eff in list(self.live.values()):
                self.end(eff, "encounter over")
        finally:
            self.closing = False

    def of(self, owner: int) -> list[Effect]:
        return [e for e in self.live.values() if e.owner == owner]

    def stance_of(self, eid: int) -> Effect | None:
        """The stance this creature is in, if any. At most one, ever."""
        for eff in self.live.values():
            if eff.when is When.STANCE and eff.owner == eid:
                return eff
        return None

    def mark_by(self, who: int, marker: int) -> Effect | None:
        """The live mark `marker` has on `who`, if any.

        At most one, for the same reason `stance_of` returns one:
        `Relation.MARKED_BY` allows a creature a single marker.

        Here rather than in a row, because a row that wants to *hold* a mark
        would otherwise hand-roll this relation walk -- and a read
        hand-written in several files is the bug, not the rows. `stance_of`
        above is the shape. #834.
        """
        # **The newest, not the first found.** More than one mark effect can
        # be live at once -- the relation allows a single marker but the
        # effects stack, and a board that arms traits has one standing
        # before any row runs. Adopting the older one set the exception on
        # an effect the lapse was not armed on, so the lapse still fired and
        # the mark still dropped: correct-looking and useless.
        # `drivers.mark_lapses` caught it by asserting which effect came
        # back rather than only the outcome.
        found: Effect | None = None
        for eff in self.live.values():
            if (
                eff.owner == who
                and (found is None or eff.id > found.id)
                and any(rel is Relation.MARKED_BY and src == marker and dst == who
                        for rel, src, dst in eff.relations)
            ):
                found = eff
        return found

    def sustaining(self, source: int) -> list[Effect]:
        """What this creature is keeping going, and would lose by not.

        A zone's effect is owned by the *zone entity*, so nothing a caster
        owns mentions it -- which meant the one creature whose action keeps
        it alive was the one creature that could not see it.
        """
        return sorted(
            (
                e
                for e in self.live.values()
                if e.source == source and e.sustain_cost is not None
            ),
            key=lambda e: e.id,
        )

    def clocked_on(self, eid: int) -> list[Effect]:
        """Live effects waiting on this creature's turn boundaries."""
        return [
            e
            for e in self.live.values()
            if e.clock == eid and e.when not in _UNREACHABLE and e.when is not When.INSTANT
        ]

    def carries(self, kind: Relation, source: int, target: int) -> bool:
        """Is this relation held up by a live effect that will end it?"""
        return any(
            (kind, source, target) in eff.relations for eff in self.live.values()
        )

    def sustain(self, eff: Effect) -> None:
        eff.sustained = self.world.round
        for fn in list(eff.on_sustain):
            fn()

    # -- the clock -----------------------------------------------------------

    def _rolls_early(self, eff: Effect) -> bool:
        """Does this effect's saving throw happen at the start of the turn?

        Three rows move one: "saving throws against charm, fear or psychic
        effects at the start of your turn", "against ongoing untyped damage
        at the start of your turn **instead of** at the end", and a psionic
        augment that does the same for the encounter. All three narrow on
        what the effect *is*, so the selector is a predicate over the same
        save context `save` already builds -- `keywords`, `ongoing`,
        `dtype`, `conditions` -- rather than a new vocabulary.

        Held as a gated `Mod` because that is what `Mods` holds and what
        `c.bonus(when=)` already means; `c.save_early` is the writer.

        **Not `cf:warden-f0`.** That feature is an *extra* throw taken from
        a `TurnStart` watch, and its own docstring says the ordinary
        end-of-turn one still happens when it fails. A move and an addition
        are different sentences and this is only the first. #671.
        """
        holder = self.world.get(eff.owner, Mods)
        if holder is None or not holder.items:
            return False
        ctx = {
            "actor": eff.owner,
            "effect": eff,
            "label": eff.label,
            "conditions": frozenset(eff.conditions),
            "ongoing": eff.ongoing is not None,
            "dtype": eff.ongoing[1] if eff.ongoing else None,
            "dtypes": eff.ongoing_types or (
                (eff.ongoing[1],) if eff.ongoing else ()
            ),
            "keywords": keywords_of(eff),
        }
        return holder.total("save_early", ctx) > 0

    def _on_turn_start(self, ev: TurnStart) -> None:
        for eff in list(self.live.values()):
            if eff.ongoing is not None and eff.owner == ev.actor:
                amount, dtype = eff.ongoing
                self.world.damage(
                    eff.source, eff.owner, amount, dtype, detail=str(eff),
                    dtypes=eff.ongoing_types,
                )
            if (
                eff.when is When.SAVE_ENDS
                and eff.clock == ev.actor
                and self._rolls_early(eff)
            ):
                self.save(eff, when_="early")
            if eff.when is When.SONT and eff.clock == ev.actor:
                self.end(eff, "start of turn")
            elif eff.when is When.SOTNT and eff.clock == ev.actor:
                if eff.latch:
                    eff.latch = False
                else:
                    self.end(eff, "start of turn")

    def _on_turn_end(self, ev: TurnEnd) -> None:
        # **One sustain action per power, not per thing it put on the
        # board.** Every `c.conjure` makes its own effect carrying
        # `sustain_cost=MINOR`, and this charged the budget once each -- so
        # a row conjuring two kept one and lost the other at this very turn
        # end, and a row conjuring three lost two. The printed rule is one
        # sustain for the power. Carried across the sweep rather than inside
        # `_sustain_by_default`, because the ledger belongs to *this* turn
        # end and not to any one effect. #819.
        paid: set[tuple[int, str]] = set()
        for eff in list(self.live.values()):
            if eff.clock != ev.actor:
                continue
            if eff.when is When.EOT:
                self.end(eff, "end of turn")
            elif eff.when in (When.EONT, When.EOTNT):
                # **A refreshed condition announces nothing, and that reads as a
                # stuck one.** When a second effect carries a condition the
                # creature already has, `apply` does not re-emit
                # `ConditionApplied` -- it is already true -- and `end` does not
                # emit `ConditionEnded` while another live effect still holds it.
                # Both are right. The consequence is that a creature re-dazed
                # every round shows one application, then nothing until teardown,
                # which was filed as a seven-round duration bug on exactly that
                # evidence. The latch below was correct the whole time. If a
                # duration looks stuck, count the applications first.
                if eff.latch:
                    eff.latch = False
                else:
                    self.end(eff, "end of turn")
            elif eff.when is When.SAVE_ENDS:
                # **Skipped when something moved this throw to the start of
                # the turn**, which is a *move* and not an extra: `i499x1`
                # spells the consequence out -- "if you fail any of these
                # saving throws, you do not make a saving throw to end that
                # effect at the end of your turn" -- and that falls out of
                # the skip rather than needing a clause of its own. #671.
                if not self._rolls_early(eff):
                    self.save(eff)
            elif (
                eff.when is When.SUSTAIN
                and eff.sustained < self.world.round
                and not self._sustain_by_default(eff, paid)
            ):
                self.end(eff, "not sustained")

    def _warn_sustainless(self, eff: Effect) -> None:
        """A `When.SUSTAIN` effect nobody can sustain lapses after a round.

        `c.zone`, `c.aura`, `c.hazard`, `c.conjure` and `c.effect` all pass
        a `sustain_cost`; `c.watch` and `c.bonus` have no way to, so an
        effect they create with `When.SUSTAIN` gets none -- and
        `_sustain_by_default` refuses it, so it ends after one round
        looking exactly like a duration that was written wrong. Said out
        loud rather than left to be discovered.
        """
        if eff.when is When.SUSTAIN and eff.sustain_cost is None:
            self.world.bus.emit(
                Note(text=f"{eff.label or eff} is sustained but costs nothing "
                          "to sustain, so nothing can keep it going")
            )

    def _sustain_by_default(
        self, eff: Effect, paid: set[tuple[int, str]] | None = None
    ) -> bool:
        """Keep a sustained effect going if its action was never spent.

        The printed rule makes forgetting the default: sustain it or lose it.
        That is a bad default for anybody playing a board rather than reading
        a sheet -- the commonest way to lose a zone is not choosing to, it is
        ending your turn. So this inverts it. The effect persists unless the
        action it needs went somewhere else, which is a choice actually made
        rather than one forgotten.

        Two effects both wanting a minor means the second one lapses, which
        is right: there is only one minor, and spending it here spends it.

        **Asked through `Encounter.spend` rather than off `Budget` by name**,
        and the old `getattr(budget, cost.value, 0) <= 0` was wrong twice:

        * **five of the eight `ActionType` members name no `Budget` field.**
          `Budget` has `standard`, `move`, `minor`, `immediate_round` and
          `opportunity_turn`; `free`, `immediate_interrupt`,
          `immediate_reaction`, `opportunity` and `none` are not fields, so
          the `getattr` default fired and each read as a slot already at
          zero. Measured before and after on the same board:

              sustain=free          kept by default:  False -> True
              sustain=minor         kept by default:  True  -> True
              sustain=opportunity   kept by default:  False -> True

          A `sustain=FREE` effect was therefore dropped at the first
          turn-end of a later round, and one live row prints that cost.
        * **it missed the downgrades.** A creature with a standard left and
          no minor may pay a minor, which `DOWNGRADES` knows and a direct
          read of one slot cannot -- so a sustain could lapse with an action
          still in hand.

        `Encounter.spend` is the one place that answers both, and it stamps
        the round and turn markers that the immediate and opportunity costs
        are kept on rather than decrementing a count that does not exist.
        #776.
        """
        cost = eff.sustain_cost
        if cost is None:
            return False
        # The row that laid it, so two conjurations from one power share one
        # action. `by` falls back to the label for an effect that reached
        # here without going through `apply`.
        row = (eff.source, getattr(eff, "by", "") or eff.label)
        if paid is not None and row in paid:
            self.sustain(eff)
            self.world.bus.emit(Note(text=f"{eff.label or eff} sustained"))
            return True
        held = self.world.encounter
        if held is None or not held.spend(eff.source, cost):
            return False
        if paid is not None:
            paid.add(row)
        self.sustain(eff)
        self.world.bus.emit(Note(text=f"{eff.label or eff} sustained"))
        return True

    def save(
        self, eff: Effect, *, when_: str = "end", granted_via: str = "",
    ) -> None:
        """Roll a saving throw against one effect now.

        `when_` is **where in the turn** this throw is being taken and
        `granted_via` is **the row that handed it over**. Neither was
        recorded, in the context or on the event, and seven rows narrow on
        one or the other -- `f2553` is declared, fires, and pays its +2 on
        both of the turn's throws because nothing could say which this was.
        #671, #672.
        """
        # **`rolls_the_save`, not `owner`, for all three questions here.**
        # They are one creature for every effect but `i806p1`'s, where
        # the `Mod` sits on the attacker and the printed throw is the
        # target's. #874.
        saver = eff.rolls_the_save
        holder = self.world.get(saver, Mods)
        # With a context. It was called with none, so a `when=` gate on a
        # save bonus ran against `{}` and anything reading a key was
        # silently false -- "enemies within the aura take -2 to saving
        # throws" could not be written the obvious way.
        # `conditions` and `ongoing` as well as the label, because that is
        # what the printed lines actually narrow on: "a +2 bonus to saving
        # throws against **poison**", "against being immobilized or
        # slowed", "against ongoing damage". Gating on the label alone
        # meant matching whatever string the row that laid the effect
        # happened to choose, which is its ref more often than not.
        ctx = {
            "actor": saver,
            "effect": eff,
            "label": eff.label,
            "conditions": frozenset(eff.conditions),
            "ongoing": eff.ongoing is not None,
            "dtype": eff.ongoing[1] if eff.ongoing else None,
            # Every type the burn is, for one that is more than one. A
            # gate meaning "against ongoing fire damage" asks here, since
            # `ctx["dtype"] is FIRE` is false for a fire-and-radiant burn.
            "dtypes": eff.ongoing_types or (
                (eff.ongoing[1],) if eff.ongoing else ()
            ),
            # Read off the row that laid it -- see `keywords_of`. The
            # printed lines that want this say "against charm effects",
            # "against poison", "against fear", and there were eighteen
            # of them marked for a field `Effect` does not carry.
            # **The effect, not its label.** The label is the laying ref for
            # most sites and the printed amount for `c.ongoing`, so passing
            # it answered "no keywords" for every burn -- which is the half
            # of #580 that reaches a *rule*: "a +2 to saves against charm
            # and psychic effects" never saw a psychic burn.
            "keywords": keywords_of(eff),
            # **Which of the turn's throws, and whose doing.** "A +2 bonus
            # to saving throws made at the start of your turn" and "a
            # saving throw granted by your `cf:warden-f0` class feature"
            # are both gates on the throw rather than on the effect, and
            # the context carried nothing about the throw at all.
            "when_": when_,
            "granted_via": granted_via,
        }
        bonus = eff.save_mod + (holder.total("save", ctx) if holder else 0)
        roll = self.world.rng.d20()
        saved = roll.total + bonus >= 10
        # Read back. The outcome is announced first so a listener can
        # change it -- "the target automatically fails the saving throw" is
        # a printed line and had nowhere to go -- and then acted on.
        rolled = self.world.bus.emit(
            SavingThrow(
                actor=saver,
                against=str(eff),
                natural=roll.total,
                bonus=bonus,
                saved=saved,
                # On the event as well as in the context: `f1941` and
                # `f2554` **trigger** on the throw rather than modifying
                # it, and a `when=` gate is no use to a watcher.
                when_=when_,
                granted_via=granted_via,
                keywords=frozenset(ctx["keywords"]),
            )
        )
        # Refusing it is not the same as failing it. A cancelled save never
        # happened: the effect stays and nothing escalates, where a failed
        # one worsens. Making this a `Decision` and reading only `saved`
        # promised a cancel that did nothing -- the exact shape the `Bus`
        # docstring warns about, in the fix for it.
        if rolled.cancelled:
            return
        saved = rolled.saved
        if saved:
            self.end(eff, "saved")
        elif eff.escalate is not None:
            eff.escalate(eff)
