"""Attack rolls, damage, healing, and dropping.

Two deliberate seams for triggered effects to reach into:

* `AttackDeclared` is emitted **before** the die is rolled, so an immediate
  interrupt can cancel the attack or change its target. An interrupt that
  merely stuns the attacker does not cancel anything by itself, so the roll
  re-checks that the attacker can still act -- that is a real 4e case and it
  fails silently if you only honour explicit cancels.
* `DamageRolled` is emitted **before** the damage lands and carries a mutable
  `amount`, which is where "reduce the damage by 5" and "the attack deals no
  damage to you" get written.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from .ammunition import hurl, nock, spend_load
from .components import Defences, Health, Mods
from .conditions import DROPPED
from .durations import When
from .events import (
    AttackDeclared,
    AttackRolled,
    Bloodied,
    DamageApplied,
    DamageRolled,
    Died,
    Dropped,
    EffectApplied,
    Healed,
    Hit,
    Miss,
    PowerUsed,
    SurgeSpent,
    TempHP,
)
from .grid import Square
from .query import (
    alive,
    attack_penalty,
    can_act,
    concealment_cap,
    concealment_of,
    concealment_waived,
    cover_between,
    cover_capped,
    cover_waived,
    deals_half,
    defence,
    has_combat_advantage,
    is_minion,
    light_concealment,
    power_conditions,
    takes_half,
)
from .rng import Roll
from .types import Condition, DamageType, Defense, Relation

if TYPE_CHECKING:
    from .ecs import World


@dataclass
class AttackResult:
    hit: bool = False
    critical: bool = False
    natural: int = 0
    total: int = 0
    target_defence: int = 0
    advantage: bool = False
    cancelled: bool = False
    #: Set by a row that says an attack simply hits -- "a close or area
    #: attack targeting you automatically hits". The outcome is recomputed
    #: from the die after the interrupt window, so a listener setting `hit`
    #: had it thrown away, and rigging `total` would be faking.
    forced: bool = False
    #: The counterpart of `forced`: set by a row that says a landed blow
    #: **misses** -- "the attack misses", through the illusion, turned aside.
    #:
    #: Needed for the same reason `forced` is, pointed the other way. The
    #: outcome is recomputed from the die below, so a row in the
    #: `AttackRolled` window that set `hit = False` had it thrown away --
    #: and the one row that worked around that rewrote `natural` to 1,
    #: which is the faking both `forced` and `treated` say not to do. It
    #: made the die lie to every later reader so that one disjunct of the
    #: recompute would come out false.
    #:
    #: A row in the `Hit` interrupt window can set `hit` directly and the
    #: `confirm` callback turns it into a real `Miss`; this flag is what
    #: makes the *earlier* window work too, so one verb serves both. #862.
    turned: bool = False
    #: **The weapon of record for this attack**, by ref, or `""` for an
    #: attack that came through none.
    #:
    #: Stamped by the swing itself and inherited by every rider that pays
    #: out inside it, which is the whole point: `Cast._swung_weapon` can
    #: only answer for a row carrying the **weapon keyword**, and a rider is
    #: a row of its own with its own `Cast` and no such keyword -- so the
    #: blow that bloodied on `i1688p1`'s board reported
    #: `Bloodied(power='f274', weapon='')` while the swing really did come
    #: through the weapon.
    #:
    #: **Set only by a weapon attack**, which is what keeps the gate's other
    #: direction intact: an implement power whose caster happens to hold a
    #: sword stamps nothing here, so a rider inside *that* attack inherits
    #: `""` rather than claiming the sword in the other hand. The negative
    #: control in `drivers.swung_weapon` is the same assertion from the
    #: other side.
    #:
    #: On the result rather than a world-level "attack in progress" field,
    #: because this object is already threaded through the whole attack and
    #: a rider reaches it as `ev.result`. #698, #653.
    weapon: str = ""
    #: Who the blow finally landed on. Usually the creature it was aimed at
    #: -- but an interrupt may move it, and then the body that rolled this
    #: has to be told, or it deals its damage to the one that was missed.
    target: int = 0
    #: "Treat the attack roll as odd", regardless of what the die shows.
    #: Set rather than rewriting `natural`, because the card says the
    #: *roll* counts as odd and not that the die landed differently --
    #: faking the die would change whether it hit and whether it crit,
    #: both of which are recomputed from `natural` after the interrupt
    #: window. Read through `parity`, never directly.
    treated: str = ""
    #: Every d20 face this attack has shown, in the order they were rolled.
    #: `natural` holds one, and anything that rolls again overwrites it --
    #: the avenger's two-roll benefit, `c.reroll_attack`, `keep=` below --
    #: so "you roll the same number on each die of the attack roll" and "if
    #: both of your attack rolls would hit" had nothing left to read.
    rolls: list[int] = field(default_factory=list)
    #: The refs that rolled this attack again, in order. `rolls` already said
    #: *that* it was rerolled -- more than one face -- and could not say by
    #: what, which is the half every rider on a reroll narrows on: the
    #: printed clauses say "the reroll your racial power grants", never "any
    #: reroll". A feat keyed to one power would otherwise pay out on a magic
    #: weapon's reroll too.
    #:
    #: Read at the **settled** outcome, which is where 14 of the 18 rows hang
    #: -- "a damage bonus when the reroll lands", "combat advantage when the
    #: forced second roll misses". The `Rerolled` event is the moment; this is
    #: the fact, still readable once the dust settles. #496.
    rerolled_by: list[str] = field(default_factory=list)
    #: **The best boost of each bonus type already applied to this roll**,
    #: by type word.
    #:
    #: `Cast.boost_roll` adds straight to `total` and carries no bonus
    #: type, so two item bonuses to the same attack roll both landed where
    #: the printed rule gives the larger of the two. `i1743x1` is the row
    #: that noticed -- *"23 rows in the tree lay one, across different
    #: slots, so the overlap is rare rather than impossible"*.
    #:
    #: Written only by a boost that names a type; a boost that names none
    #: is untyped and stacks, which is what every existing caller does and
    #: what the rule says about untyped bonuses.
    #:
    #: `repr=False` because this object's repr is in the event stream that
    #: `replay` records, and a new field there moves every fixture --
    #: which is a baseline write rather than a behaviour change.
    boosted: dict[str, int] = field(default_factory=dict, repr=False)
    #: **Is this swing a coup de grace?**
    #:
    #: `Cast.coup_de_grace` rolls the finisher through an ordinary
    #: `strike` and then sets `critical`, so by the time the damage is
    #: rolled the blow is indistinguishable from any other critical --
    #: and `f2071`'s *"1[W] extra on a coup de grace"* had nothing to gate
    #: on.
    #:
    #: **Not inferred from `critical` and a helpless target**, which is
    #: the tempting shortcut: a lucky natural 20 against a helpless
    #: creature is both of those and is not a coup de grace, which is a
    #: standard action somebody chose to take.
    #:
    #: On the result for the reason `weapon` one field up gives -- this
    #: object is already threaded through the whole attack -- and
    #: `repr=False` because the repr is in the stream `replay` records.
    finisher: bool = field(default=False, repr=False)

    @property
    def parity(self) -> str:
        """`"odd"` or `"even"`, honouring anything that dictated it.

        Two rows read `natural % 2` by hand, which is right until
        something says otherwise -- and a whole build turns on a row
        that does.
        """
        if self.treated:
            return self.treated
        return "even" if self.natural % 2 == 0 else "odd"

    def __bool__(self) -> bool:
        return self.hit


def situational_attack(
    world: World,
    attacker: int,
    target: int,
    power: str,
    ctx: dict[str, Any],
    *,
    ca: bool = False,
    charge: bool = False,
    ignore_cover: bool = False,
    branch: int = 0,
    among: tuple[int, ...] = (),
) -> int:
    """Everything the *situation* adds to an attack roll, and nothing the
    attacker brings to it.

    Extracted so the closed-form model in `expect.py` reads it out of the kernel
    rather than keeping its own copy. It had its own copy by omission -- it
    applied `_mods` alone -- so it priced away **combat advantage's +2**, cover,
    concealment, the prone penalty, long range and a mark. Measured on one rogue
    row with advantage: 12.70 against a simulated 15.24, and the whole of that
    gap was this. Two implementations of one rule is how they drift.
    """
    situational = attack_penalty(world, attacker)
    situational += _mods(world, attacker, "attack", ctx)
    if ca:
        situational += 2
    if charge:
        situational += 1   # the printed charge bonus
    if not ignore_cover:
        # **Each half is waived against its own number, and only then do
        # they meet.** Cover and concealment still do not add -- the larger
        # applies, which is the printed rule and stops a creature in a fog
        # bank behind a pillar being unhittable -- but taking the larger
        # *first* and asking one waiver about the pair made four printed
        # sentences unwritable: sight that passes concealment and not
        # cover. Waiving the pair would have let those creatures shoot
        # through a wall. #771.
        #
        # A standing waiver -- `c.ignore_cover` on the attacker or
        # `c.no_cover` on the target -- reads the same context the penalty
        # does, so "against enemies in the zone" is a gate rather than an
        # argument to one `c.strike`.
        from_cover = int(cover_between(
            world, attacker, target,
            ranged=_is_ranged(power, branch, world, attacker), ctx=ctx))
        # **Standing somewhere badly lit** is a fact about the square and
        # about who is looking, so it cannot be a modifier the target
        # carries the way `concealment_of` is. Reads `Grid.light`, which is
        # empty on every board until a row darkens one, so it is a no-op
        # until then. `query.light_concealment` cancels it for darkvision,
        # low-light vision, blindsight and tremorsense. It is concealment,
        # so the concealment waiver answers for it.
        from_concealment = max(
            int(concealment_of(world, target, ctx)),
            int(light_concealment(world, attacker, target)),
        )
        if from_cover <= cover_waived(world, attacker, target, ctx):
            from_cover = 0
        if from_concealment <= concealment_waived(
                world, attacker, target, ctx):
            from_concealment = 0
        # **A ceiling, read AFTER the waiver.** `f3452` prints
        # "creatures within 2 squares have concealment rather than TOTAL
        # concealment", which is neither a waiver nor a penalty: the
        # waiver is a threshold that sends the whole thing to zero, and
        # at the total grade it would clear the penalty altogether and
        # make the feat far stronger than print.
        #
        # After, so a card that waives concealment outright still does;
        # a ceiling on something already zero changes nothing. #1528.
        _ceiling = concealment_cap(world, attacker, target, ctx)
        if _ceiling is not None and from_concealment > _ceiling:
            from_concealment = max(0, _ceiling)
        worst = max(from_cover, from_concealment)
        # **A cap, which the waiver above cannot express.** `f2354` prints
        # "ignore cover and concealment and take only a -2 penalty against
        # a target that has total concealment or superior cover": the
        # ordinary grades are waived by the threshold above and what is
        # left is capped rather than removed. Zero for every creature
        # nothing has given a cap, so this costs one read.
        cap = cover_capped(world, attacker, target, ctx)
        if cap and worst > cap:
            worst = cap
        situational -= worst
    situational -= _long_range(world, attacker, target, power, branch, ctx)
    situational += _mark_penalty(world, attacker, among or (target,))
    situational += _underwater(world, attacker, target, power, ctx)
    situational -= _aimed_through(world, attacker, target)
    return situational


def _aimed_through(world: World, attacker: int, target: int) -> int:
    """A zone's penalty on whoever aims into or through it. `f1713b`.

    *"-2 to attack rolls against a creature inside the wall or on the
    other side of it"* -- the mirror of the `_in` family, which lays a
    zone's modifier on the creatures **standing in** it.

    **Two ways to be caught, and the second is what the card is
    distinctive for.** The target standing in the region is a membership
    test; *"on the other side"* is the traced line crossing it, which
    `_line` already answers -- so a shot whose path enters a wall square
    is through it, and diagonals stay counted the way the rest of the
    geometry counts them.

    **The membership test looks redundant and is not.** Deleting it left
    every arm of `drivers.aimed_through` green, because the traced line
    *ends on the target's square* -- so a Medium creature standing in the
    region is caught by the line branch anyway. It is live for a creature
    wider than one square: the line runs between one corner each,
    `min(here)` to `min(there)`, so a Large target with its near corner
    outside the region and its far corner inside is *inside the wall* by
    the card's first clause and off the traced line by the geometry. The
    rule poses exactly that, and with it the plant goes red.

    **Zone-held rather than per-enemy**, which is the loss `f1713b`'s own
    note measured about the `m238a3` shape: a gated `c.penalty` laid on
    each enemy misses one that joins the board after the wall goes up.

    The **largest** penalty rather than the sum, for the reason
    `World.crossing` takes the larger of two taxes: two walls of light
    between a shooter and its target are one worse shot, not two.

    Returns 0 on every board with no such zone, which is every board
    until a row lays one -- one loop over a list that is usually empty.
    """
    from .movement import _line
    from .query import squares as _squares
    from .query import team as _side_of

    worst = 0
    for _eid, zone in world.zones.all():
        if not zone.attack_penalty or not zone.squares:
            continue
        if zone.penalty_for == "enemy":
            mine = _side_of(world, zone.owner)
            theirs = _side_of(world, attacker)
            if mine == theirs:
                continue
        if _squares(world, target) & zone.squares:
            worst = max(worst, zone.attack_penalty)
            continue
        here = _squares(world, attacker)
        there = _squares(world, target)
        if here and there and any(
            sq in zone.squares for sq in _line(min(here), min(there))
        ):
            worst = max(worst, zone.attack_penalty)
    return worst


#: The two weapon groups the printed underwater rule exempts.
_SWIMMABLE_GROUPS = frozenset({"spear", "crossbow"})


#: The `Mods` key a card writes to waive the printed weapon penalty for
#: fighting underwater. Two rows print the sentence and want it at
#: different widths, which is why the waiver is a **gated** modifier
#: rather than a flag: `i3050x1` says *"you take no attack penalty when
#: using **this weapon** underwater"* and gates on `ctx["weapon"]`, where
#: `f2903b` says *"you take no penalties ... for using a weapon other
#: than a spear or crossbow"* and gates on nothing.
#:
#: Read in `_underwater` and written by `Cast.no_underwater_penalty`.
#: Named here so the key has exactly one spelling -- a second one would be
#: a waiver nothing consults, which is this component's commonest bug.
UNDERWATER_WAIVED = "underwater_weapon_ok"


def _underwater(world: World, attacker: int, target: int, power: str,
                ctx: dict[str, Any] | None = None) -> int:
    """The printed aquatic-combat modifiers to an attack roll. #949.

    DMG p.45, three of the four bullets -- the fourth is about movement and
    belongs to `movement.py`, not here:

        "creatures using powers that have the fire keyword take a -2 penalty
         to attack rolls"

        "characters using weapons from the spear and crossbow weapon groups
         take no penalties to attack rolls with those weapons while fighting
         underwater. characters using any other weapon take a -2 penalty"

        "aquatic: creatures native to watery environments have the aquatic
         ability. They gain a +2 bonus to attack rolls against opponents that
         do not have this ability."

    **In `situational_attack` and nowhere else**, because that function's own
    docstring is the argument: `expect.py` reads it out of the kernel rather
    than keeping its own copy, and when it kept one it priced away combat
    advantage, cover, concealment, prone, long range and a mark. A blanket
    modifier added anywhere else would be the same fault again.

    **A no-op on every dry board**, which is almost all of them: the first
    test is `world.terrain`, so nothing is read and nothing allocated unless
    a module declared the fight underwater. The same shape as `Grid.light`
    being empty until a row darkens a square.

    The three stack, and the book does not say otherwise: a fire power swung
    with a longsword by a land-dweller against a sahuagin is -2 for the
    keyword and -2 for the weapon, and the sahuagin's +2 is on *its* rolls
    rather than against these.
    """
    if "aquatic" not in getattr(world, "terrain", frozenset()):
        return 0
    from .components import Gear
    from .dsl import get
    from .types import Keyword

    out = 0
    declared = get(power)
    # **The power's own keywords, not the damage type.** A fire power is one
    # printed with the keyword; a power that happens to deal fire damage off
    # a rider is not what the sentence is about.
    if declared is not None and Keyword.FIRE in getattr(declared, "keywords", ()):
        out -= 2
    # **The weapon in hand decides, and only for a weapon attack.** A
    # creature swinging no weapon -- a monster's claw, an implement power --
    # takes no weapon penalty, because the printed sentence is about
    # "characters using weapons".
    gear = world.get(attacker, Gear)
    held = gear.main if gear is not None else None
    # **The printed waiver, read with the attack's own context.** Two rows
    # waive this sentence at different widths and the context is what lets
    # one spelling serve both: `ctx["weapon"]` is the ref that swung, so a
    # card naming its own weapon gates on it and a card naming none does
    # not. `_mods` is the reader every other gated modifier goes through.
    if (
        held is not None
        and (held.group or "") not in _SWIMMABLE_GROUPS
        and _mods(world, attacker, UNDERWATER_WAIVED, ctx or {}) <= 0
    ):
        out -= 2
    # **Aquatic against non-aquatic.** `monster.keywords` carries the word
    # for the creatures whose stat block prints it; a character has no such
    # keyword, so a land-dweller reads False on both sides and gets nothing.
    if _is_aquatic(world, attacker) and not _is_aquatic(world, target):
        out += 2
    return out


def _is_aquatic(world: World, eid: int) -> bool:
    """Does this creature's stat block print the aquatic ability?

    **`query.kinds_of`, not a field on a component.** The first draft read
    `Ident.keywords`, and `Ident` carries `ref`, `tag`, `book` and `role` and
    no keywords at all -- so it would have answered False for every creature
    in the game, silently, which is the failure mode `engine/CLAUDE.md` opens
    with. `kinds_of` is the reader that exists: it parses the stat block's own
    `keywords` column, adds `kind` and `origin`, and honours
    `c.set_origin`/`unorigin` -- so a creature *made* aquatic by a row counts
    too, which the printed sentence ("creatures native to watery
    environments have the aquatic ability") does not forbid.
    """
    from .query import kinds_of

    return "aquatic" in {w.lower() for w in kinds_of(world, eid)}


def settle(result: AttackResult, *, floor: int = 20) -> None:
    """**The hit-and-critical rule, in one place.** Reads the result as it
    stands and writes `hit` and `critical` from it.

    `floor` is the lowest natural that scores a critical -- `20 -
    crit_range` -- and it belongs to the **critical only**. The automatic
    hit is tied to the number the rule names: a natural 20 hits, a natural 1
    misses, and a widener says you *score a critical hit* on 19 or 20, which
    changes which hits become criticals and says nothing about what hits.

    The other half is that a high roll is not enough on its own: the die
    opens the door and the total still has to reach the defence, so a 20
    fourteen short of an AC is a plain hit and not a critical.

    `turned` outranks the die in both -- a blow a row has turned aside
    neither hits nor crits, whatever was rolled -- and `forced` is the
    counterpart pointed the other way: a row that said the attack simply
    hits is not un-hit by arithmetic.

    **`forced` is absent from the critical rather than negated in it**, and
    the difference is not cosmetic. Omitting it means a forced attack is not
    *made* a critical by the forcing, which is the whole of what the comment
    on the old recompute asked for; negating it would additionally stop a
    forced attack that rolled a natural 20 over the defence from critting,
    and a row saying "the attack hits" does not say "and the die did not
    land well". I wrote the negation first.

    **This existed eight times before it existed once, and five of the
    copies were wrong in four different ways.** Both branches here were
    wrong about `crit_range` -- in opposite directions, the hit reading the
    floor and the critical reading a bare 20 -- across `resolve.attack`,
    `Cast.boost_roll` and `Cast.reroll_attack`; two copies dropped the
    automatic hit entirely; one read a `critical` computed before the
    arithmetic it was recomputing after; and three content rows re-settled
    an outcome by hand after changing it, each missing a different term.
    Every one of those was a silently wrong number on a live path.

    So the rule has one home and `c.settle_attack()` is the door for a row
    that changes a number the outcome was judged from. #868.
    """
    against = result.target_defence
    result.critical = (
        not result.turned
        and result.natural >= floor
        and result.total >= against
    )
    result.hit = not result.turned and (
        result.forced
        or result.natural == 20
        or (result.natural != 1 and result.total >= against)
    )



def replay(
    world: World,
    actor: int,
    ref: str,
    target: int,
    result: AttackResult,
    *,
    branch: int = 0,
    augment: int = 0,
) -> bool:
    """Apply a power's outcome again, for one target, from a roll already made.

    *"You reroll the attack rolls that missed their targets and **use the new
    results**."* The reroll itself is `Cast.reroll_attack`, which updates the
    `AttackResult` and re-settles it -- but by `PowerResolved`, which is where
    *"missed with at least two"* is first knowable, the resolution has
    finished. So a miss turned into a hit lands no damage and no rider: the
    number changed and nothing read it.

    This re-runs the power's **body** for that one target with the rerolled
    result staged, so `c.strike()` returns it instead of rolling a third
    die, and the body's `if c.strike():` branch pays out what the new
    outcome owes. `#1314`.

    **Only the redo, and that is the triage.** `#1314`'s four rows are two
    gaps: `p10354` and `i1675p1` reroll only the rolls that **missed**, so
    there is nothing to take back and a redo alone finishes them. `f2448`
    rerolls hits as well, so a hit becoming a miss needs its damage undone
    -- which this does not do and must not pretend to. `i1676p1` wants the
    undo and no reroll at all and is `#1332`.

    **`index` is set so `c.first` and `c.last` are both False.** They key
    off `index == 0` and `index == len(targets) - 1`, and they are where a
    once-per-power line lives -- a zone, a conjuration, an Effect clause. A
    replay that left `index` at 0 would lay the zone a second time, which is
    the one way this could be worse than doing nothing. So the staged cast
    is given three targets and sits in the middle of them.

    **The use is not spent again and `PowerResolved` is not re-announced.**
    This is the same use finishing differently, not a second use: spending
    would charge a daily twice, and a second `PowerResolved` would re-offer
    every row triggered on one -- including the row that called this, which
    is an unbounded loop with a reroll in it.

    Returns whether the body ran. False when the row is unknown, which is
    the only way it can refuse.
    """
    from .cast import Cast
    from .dsl import get

    p = get(ref)
    if p is None:
        return False
    cast = Cast(
        world=world, me=actor, ref=ref, branch=branch, augment=augment,
        # Three, with this one in the middle: `c.first` and `c.last` are
        # both False, so a once-per-power clause does not fire twice.
        targets=[target, target, target],
        index=1,
        target=target,
        staged=result,
    )
    p.body(cast)
    return True

def attack(
    world: World,
    attacker: int,
    target: int,
    bonus: int,
    vs: Defense,
    power: str = "",
    *,
    advantage: bool | None = None,
    ignore_cover: bool = False,
    opportunity: bool = False,
    among: tuple[int, ...] = (),
    branch: int = 0,
    use: int = 0,
    dying: bool = False,
    charge: bool = False,
    granted_by: int = -1,
    granted_via: str = "",
    keep: str = "",
    hand: str = "main",
    as_: str = "",
    weapon: str = "",
    augment: int = 0,
    finisher: bool = False,
    instinctive: bool = False,
    origin: frozenset[Square] = frozenset(),
) -> AttackResult:
    """Roll one attack. `bonus` is everything the attacker brings to it;
    everything the *situation* brings is added here."""
    result = AttackResult()
    result.finisher = finisher
    # The weapon of record, stamped once at the top so every rider that
    # pays out inside this attack reads the same answer. See the field.
    result.weapon = weapon
    # Was this swing bought with an action point? Rides the same road
    # `opportunity` and `charge` do -- in the attack context and on all four
    # attack events -- because two printed rows are about exactly that
    # attack and neither could be written while nothing said so.
    bought = spent_action_point(world, attacker)
    # One piece of magic ammunition, drawn and spent as the shot is
    # declared. Rides the same road `opportunity` and `charge` do -- in
    # the attack context and on all four attack events -- because "an
    # attack using this ammunition" is about *this* shot and there was
    # nothing on the wire that said which one.
    drawn = nock(world, attacker, power, branch)
    # The same shot, the same gate: a costed loader is empty after it
    # fires and `actions` offers the reload. #725.
    spend_load(world, attacker, power, branch)
    # And the other kind of ranged weapon attack: a weapon thrown by hand
    # is spent by throwing it. `nock` declines a throw and `hurl` takes it,
    # so exactly one of the two pays for any given attack. #520.
    hurl(world, attacker, power, branch)

    def roll(declared: AttackDeclared) -> None:
        # Read back off the event, because an interrupt may have moved the
        # attack. The module docstring has promised since it was written
        # that "an immediate interrupt can cancel the attack or change its
        # target" -- and the closure captured the parameters instead, so
        # assigning `ev.target` did nothing at all and failed silently.
        # The defence too, not just who is swinging at whom. `vs` is on the
        # event and mutable and was read from the enclosing parameter both
        # times -- so a row printing "its attacks target Reflex instead of
        # AC" set the field, changed nothing, and logged nothing. Sixth of
        # this shape today; the module docstring warns about it directly.
        attacker, target = declared.attacker, declared.target
        vs = declared.vs
        result.target = target
        # `dying` is a death throe swinging on its way down. The killing
        # blow usually overshoots `dying_at` -- and always does for a minion
        # -- so the attacker is not alive by the time its own `Dropped` is
        # answered, and the whole burst declared and then cancelled.
        if (not dying and not can_act(world, attacker)) or not alive(world, target):
            result.cancelled = True
            return
        # **Proof against this named row.** `Powers.proof_against` maps a
        # ref to the temporary hit points the power grants instead, and
        # this is its only read site -- see that field for why, and for
        # the limit it states. Two cards print the clause and both are
        # attacks: `i3555x1`'s wielder is exempt from the disarm
        # `m4197a2` makes, and `m6272a0` turns up to four named arcane
        # attack powers into 5 temporary hit points.
        #
        # Before the roll, so nothing is announced: the card says the
        # power's only effect is the temporary hit points, and an
        # `AttackRolled` that misses is still a swing a rider can answer.
        # Cancelled the same way a dead target cancels it, which is the
        # one path callers already handle.
        from .components import Powers as _Powers

        _proof = world.get(target, _Powers)
        _owed = (_proof.proof_against or {}).get(power) if _proof else None
        if _owed is not None:
            result.cancelled = True
            if _owed > 0:
                from .cast import Cast as _Cast

                # **`on=target` and not the default.** `c.temp_hp`
                # falls through to `c.target`, which is None on a
                # freshly built `Cast` -- so without this the grant
                # silently did nothing and the substitution read 0.
                # Almost every `Cast` method defaults this way and it is
                # the commonest single mistake in this tree.
                _Cast(world=world, me=target, ref=power).temp_hp(
                    _owed, on=target)
            return

        ca = (
            has_combat_advantage(world, attacker, target, power, hand)
            if advantage is None else advantage
        )
        # `opportunity` is in the context because "+2 to AC against
        # opportunity attacks" cannot be written without it, and gating on
        # the power's ref instead catches a standard-action basic and misses
        # a creature whose opportunity attack is something else.
        #
        # **And `opportunity` alone was not enough**, which five rows said in
        # their own words before anything carried the answer: it says an
        # attack *is* an opportunity attack and never what provoked it, so
        # "against opportunity attacks you provoke with a ranged power" and
        # "provoked by this movement" could not be told apart and both paid
        # out for the other. Read off the window that is open right now --
        # see `World.provocation` -- rather than threaded through every
        # taker. Only when `opportunity` is true, so an ordinary attack
        # cannot inherit a provocation. #880.
        window = world.provocation if opportunity else None
        ctx = {
            "attacker": attacker,
            "target": target,
            "power": power,
            # **Where the swing comes FROM, which `attacker` does not
            # answer.** `p16653` prints "+4 to all defenses against attacks
            # that originate outside the zone", and the attacker's own
            # square is the wrong square exactly where the card is
            # interesting: a ranged attack's origin moves with
            # `c.cast_from`, and an area burst's origin is a placed square
            # with no creature in it at all.
            #
            # A frozenset, because an origin can be several squares -- a
            # Large creature's footprint, or a shaman with two spirits
            # lending at once. Empty when the caller did not say, which is
            # the honest answer rather than the attacker's square dressed
            # up as one.
            "origin": origin,
            "advantage": ca,
            "opportunity": opportunity,
            # What opened the window this swing is coming through. Three
            # keys because the rows split three ways: whether it was a row
            # at all (`provoked_by` empty means a move), which row, and how
            # the provoker was travelling.
            "provoked_by": str(getattr(window, "by", "") or ""),
            "provoked_kind": str(getattr(window, "kind_", "") or ""),
            "provoked_mode": str(getattr(window, "mode", "") or ""),
            # The provoking row's **shape**, in `reach`'s own vocabulary, so
            # "an opportunity attack you provoke when using a ranged or an
            # area power" is a gate in the words #644 already established
            # rather than a second registry lookup in every row.
            #
            # Needed because `provoked_by` being non-empty means only "a row
            # opened this", and `c.provoke` opens one for arbitrary rows --
            # so the ranged-or-area question is narrower than "not a move"
            # and `f2565` prints the narrower one.
            # **Which magic items were in the provoker's hand** when the
            # window opened, as a frozenset of item refs. Two rows ask
            # "with THIS weapon" / "through THIS dagger", and the weapon
            # of record is a parameter to this function -- decided when
            # the attack rolls, later than the use that opened the
            # window. See `dsl._survive_provoking` for why it is a set.
            "provoked_weapon": frozenset(
                getattr(window, "through", frozenset()) or frozenset()
            ) if window is not None else frozenset(),
            "provoked_reach": _reach_kind(
                str(getattr(window, "by", "") or ""), 0, world,
                getattr(window, "provoker", None),
            ) if window is not None else "",
            "charge": charge,
            # **Is a summon swinging on its own Instinctive Effect.**
            # `power`, `granted_by` and `granted_via` are identical on
            # the instinctive and the commanded path -- both roll the
            # block's `summon=` line under the block's ref -- so a card
            # charging a bonus to the instinctive action alone had
            # nothing to gate on, and `acting_independently` reads
            # False for both. `Cast.instinctive` is the one place that
            # knows. #1498.
            "instinctive": instinctive,
            # Who handed this swing over, and through which row. A bonus
            # to "the melee basic attack granted by your Combat
            # Challenge" is a gate on these two and nothing else, and
            # the keys were simply absent -- silently false, which is
            # what an inert feat looks like.
            "granted_by": granted_by,
            "granted_via": granted_via,
            "action_point": bought,
            # What shape the attack is, so "ranged attacks against this
            # target take +4" is a one-line gate rather than a registry
            # lookup duplicating `_is_ranged`.
            "ranged": _is_ranged(power, branch, world, attacker),
            # **The shape, not just "was it ranged".** `ranged` is a bool and
            # three of the four rows gating cover on the attack need more
            # than that: "melee attacks and ranged attacks" has to exclude a
            # close burst, and "ranged and area attacks" has to include one.
            # This is `Range.kind` verbatim -- melee | ranged | close_burst |
            # close_blast | area_burst | wall | personal -- so a gate reads
            # the same vocabulary `dsl.AREA_OR_CLOSE` is written in. #644.
            "reach": _reach_kind(power, branch, world, attacker),
            "branch": branch,
            # Which magic ammunition this shot came from, empty for every
            # attack that is not one. In the context as well as on the
            # events so a standing modifier can be gated on it.
            "ammo": drawn,
            # Which hand swung. `Cast.w(hand="off")` already picked the
            # off-hand weapon's dice, and then threw the fact away -- so
            # a rider gated on an off-hand attack read a key the context
            # did not carry, which is silently false rather than wrong.
            "hand": hand,
            # **What was swung, by ref and by group.** `result.weapon` has
            # carried the ref since the field was added and the context did
            # not, so a gate could ask which *hand* swung and never what
            # was in it -- and `"hand"` answers a different question:
            # `Gear.off` is the second held weapon, so a trait requiring the
            # off hand to be **empty** never sees a swing stamped `"off"`.
            #
            # `cf:fighter-weaponmaster-f3s2` is the worked case. It prints
            # *"a +2 enhancement bonus to the attack rolls of unarmed
            # attacks"* and carried `Attack.ctx(unarmed)`; the group is how
            # an unarmed swing is told from an armed one, since
            # `chargen.UNARMED` and `w3678` both file under the `unarmed`
            # group. `cf:monk-f1` asks the same question from the other
            # side.
            #
            # Both keys, because a card names one weapon as often as a
            # family -- the same reason `query.holding` matches a ref *and*
            # a group. Empty for an attack made through no weapon at all,
            # which is every implement power, so a gate reading them is
            # false there rather than wrong.
            "weapon": weapon,
            "group": _group_of(world, attacker, weapon),
            # **The arena-weapon substitution**, empty for everybody who
            # has not selected a pair. `Mod.applies` re-asks a *failed*
            # feat-kind gate with each of these laid over the context,
            # which is how `cf:fighter-weaponmaster-f3s0`'s printed
            # sharing reaches a predicate written inside another feat's
            # body. `#1276`.
            "arena_alt": _arena_alts(world, attacker, weapon),
            # **Which named swing this is**, empty for an ordinary attack.
            # `as_` already rode the events for the counter-attack case; the
            # context did not carry it, so a modifier on "a bull rush attack
            # roll" had nothing to gate on. Declared here because `lint.py`
            # derives the legal key set from this dict, and a key minted
            # elsewhere is a gate on a key no context carries. #501.
            "as_": as_,
            # **Is this a basic attack**, which the context could not say at
            # all. It carried eight shape keys and none of them answered the
            # commonest gate a feat prints -- "with basic attacks" -- so
            # every such row had to reach for `Powers` itself and compare
            # against a pair of refs, which missed the eleven rows printing
            # "counts as a basic attack". `Powers.every_basic` is the one
            # answer: the designated melee and ranged rows plus everything
            # that counts as one, and **not** the `instead` list, since a row
            # swung in place of a basic attack is not one. #522.
            # **At the form being swung.** Six rows print "you can use this
            # power *unaugmented* as a ranged basic attack", so the
            # designation -- which is the half that picks up a "with basic
            # attacks" modifier -- is false for every augmented use of them.
            # This read defaulted to the base form and so could not tell
            # them apart. #1298.
            "basic": _is_basic(world, attacker, power, augment),
            # **Is this the second roll, and whose doing?** Declared here,
            # with the defaults that say "no", because this is where the
            # attack context is built -- `lint.py` derives the legal key set
            # from this very dict, so a key `c.reroll_attack` invented on its
            # own would be a gate on a key no context carries, which is the
            # fault that walk exists to catch. `reroll_attack` overrides both
            # when it re-sums.
            #
            # `reroll_by` as well as the flag: the three rows that modify a
            # reroll each narrow to the one *their own* racial power forces,
            # and a bare flag would have them modify a magic weapon's reroll
            # too. #496.
            "reroll": False,
            "reroll_by": "",
            # **Everyone this attack is aimed at**, not just the one being
            # rolled against. "Attacks that do not include you as a target" is
            # a printed clause -- the mark penalty a few hundred lines down
            # implements exactly it, and correctly, by testing the whole target
            # set -- but a gated modifier could only see `target` and so could
            # not ask the same question. A rider that sharpens a mark had
            # nothing to gate on and read as unwritable.
            "among": tuple(among),
            # **Whether this swing was told to ignore cover outright**, as
            # an argument rather than through a standing waiver. In the
            # context because `Cast.reroll_attack` recomputes the
            # situational half against this same dict and has to pass the
            # value the first roll used -- a difference taken with it
            # False, over a swing resolved with it True, hands the reroll
            # back a cover penalty that was never charged.
            "ignore_cover": ignore_cover,
            # **What this attack's body is going to apply**, read off that
            # body with an `ast` walk -- `query.power_conditions`.
            #
            # The one key here about something that has **not happened
            # yet**, and two cards need exactly that: *"a +2 bonus to all
            # defences against any attack that **would** immobilize,
            # restrain or slow you"* (`f2364`, `f2365`). A defence is
            # settled before the attacking body runs, so there was nothing
            # on the board to test and both rows were marked for it.
            #
            # A `frozenset` under this name because the **saving-throw**
            # context has carried `"conditions"` that way all along, which
            # is what `f2365`'s note spotted: one context had it and the
            # other did not.
            #
            # A floor rather than an answer -- a body applying a condition
            # through a helper is invisible to the walk -- and that is the
            # safe direction for a card granting a defence. See the
            # reader's own note.
            "conditions": power_conditions(power),
        }

        situational = situational_attack(
            world, attacker, target, power, ctx,
            ca=ca, charge=charge, ignore_cover=ignore_cover,
            branch=branch, among=among,
        )

        d20 = world.rng.d20()
        natural = d20.total
        result.rolls.append(natural)
        # "Make the attack roll twice and use either result" is printed on
        # the attack line, so it is part of rolling and not something a body
        # can arrange afterwards: by the time `c.strike` has returned the
        # first roll has already decided hit or miss and paid out its riders.
        if keep:
            again = world.rng.d20().total
            result.rolls.append(again)
            natural = min(natural, again) if keep == "worst" else max(natural, again)
        total = natural + bonus + situational
        against = defence(world, target, vs, ctx)

        result.natural = natural
        result.total = total
        result.target_defence = against
        result.advantage = ca
        # Provisional, so an interrupt watching the roll can ask whether it
        # is about to be hit -- which is exactly when a shield gets raised.
        # A critical is not always a 20: "crits on a 17-20" is standard on
        # high-crit weapons and on solos, and the number was hard-coded in
        # both of the places it is decided.
        floor = 20 - _mods(world, attacker, "crit_range", ctx)
        # **Only ever read inside the `AttackRolled` window**, because the
        # recompute below overwrites both values unconditionally. So a plant
        # here proves nothing -- reverting this call alone leaves every
        # assertion in `drivers.crit_range` green -- and the plant goes on the
        # recompute. It is kept correct for the listener that asks "did it
        # hit" before the window closes, which is the same mechanism that
        # made four content copies of this rule dead code. #868.
        settle(result, floor=floor)

        rolled = AttackRolled(
            attacker=attacker,
            target=target,
            power=power,
            vs=vs,
            natural=natural,
            bonus=bonus + situational,
            total=total,
            defence=against,
            advantage=ca,
        )
        # The live `AttackResult` rides along as a plain attribute rather
        # than a field, so it never reaches the wire or a replay fixture.
        # It is what an interrupt that rerolls the attack has to reach --
        # without it `c.reroll_attack` had nothing to change and silently
        # did nothing at all.
        rolled.result = result
        # Everyone this one power use is aimed at, not just this
        # announcement. Rides as a plain attribute so it stays off the wire
        # and out of a replay fixture, like `result` beside it. Without it a
        # row triggering on being *left out* of an attack cannot tell a
        # burst that caught it from one that did not.
        rolled.among = among or (target,)
        # Which half of a two-branch row swung. `by_melee` reads the range
        # off the power, and a `MeleeOrRanged` row's range says "melee"
        # whichever branch was used -- so without this a ranged shot let a
        # creature react as though it had been swung at.
        rolled.branch = branch
        rolled.use = use
        # Was this an opportunity attack? Several rows key off that and no
        # event said so -- the flag lived only in the roll's own context, so
        # a creature could not react to being hit by one.
        rolled.opportunity = opportunity
        # And **what** provoked it, for the rows that narrow on the
        # provocation rather than on the swing that came back. Attached
        # like `opportunity` above and for the same reason: `i3085p1`
        # answers a `Hit`, and the `Hit` named only the return blow.
        # Empty when a move opened the window. #880.
        # A local rather than the dict read, because a ctx value is typed
        # as the union of everything a ctx holds; narrowing it once here is
        # a real fix where blessing it would only hide the union.
        provoked = str(ctx["provoked_by"])
        rolled.provoked_by = provoked  # ty: ignore[unresolved-attribute]
        # **And which magic items were in the provoker's hand**, for the
        # two rows that print *"with this weapon"* / *"through this
        # dagger"*. Attached beside `provoked_by` and for its reason: a
        # trigger answering the `Hit` has no ctx to read.
        through = ctx["provoked_weapon"]
        rolled.provoked_weapon = (  # ty: ignore[unresolved-attribute]
            frozenset(through) if isinstance(through, frozenset | set) else
            frozenset()
        )
        rolled.charge = charge
        # **Which swing this is, when one row makes two.** Hung on the event
        # the way `opportunity` and `charge` are. A row that grants a counter
        # -- p653's riposte -- rolls it longhand with `c.attack`, so both the
        # opening blow and the counter carried the same `power` and nothing
        # could tell them apart. Two feats print a clause about the counter
        # alone and had no way to ask.
        rolled.as_ = as_
        rolled.granted_by = granted_by
        rolled.granted_via = granted_via
        rolled.action_point = bought
        rolled.ammo = drawn
        # The context the modifiers were actually read with. `c.bonus(
        # once=True)` has to decide whether the bonus it is watching for
        # *applied*, and it was rebuilding a four-key context of its own --
        # so any `when=` gate reading `ranged`, `opportunity`, `charge` or
        # `branch` answered False there and the one-shot was never spent.
        # Forty-six gated one-shots in the tree were permanent bonuses.
        rolled.ctx = ctx
        world.bus.emit(rolled)

        # The defence is read **again**, after the roll has been announced.
        # An immediate interrupt fires in that window, and the whole point
        # of the commonest one is to raise your defence and turn a hit into
        # a miss -- which it could not do while the comparison had already
        # been made. The number on the event is what it was when the die
        # landed; this is what it is when the blow arrives.
        against = defence(world, target, vs, ctx)
        result.target_defence = against
        # From the **result**, not from the local `natural`/`total`. A
        # listener in the window above may have changed the die -- that is
        # the whole of what `c.reroll_attack` does -- and recomputing from
        # the locals threw the new number away and judged the old one. Every
        # reroll row in the tree was inert.
        floor = 20 - _mods(world, attacker, "crit_range", ctx)
        # **This is the authoritative judgement**, and the one a plant must
        # break: it runs after the interrupt window, re-reads the defence and
        # recomputes from the result rather than from the locals, because a
        # listener in that window may have changed the die -- which is the
        # whole of what `c.reroll_attack` does. Recomputing from the locals
        # threw the new number away and judged the old one, and every reroll
        # row in the tree was inert.
        settle(result, floor=floor)

        # The `Hit`/`Miss` carries it too, so a row can answer "when it is
        # hit by an opportunity attack".
        landed = (
            Hit(attacker=attacker, target=target, power=power, critical=result.critical)
            if result.hit
            else Miss(attacker=attacker, target=target, power=power)
        )
        # **Where the swing came FROM, which `attacker` does not answer.**
        # Ten rows across six symbols want this and six of them want to
        # *read* it: `i1832x1` and two monster abilities print "pushed away
        # from the attack's origin", `i1531p1` and `x2_117` want the origin
        # of the burst they are standing in, and `f2152b` pushes everybody
        # the blast touched away from where it was aimed. The attack
        # context has carried `origin` all along (`p16653`'s "attacks that
        # originate outside the zone") and the announcement did not.
        #
        # **A plain attribute, not a declared field, and the cost is
        # measured rather than assumed.** `_origin_squares` falls back to
        # the swinger's own squares, so this is non-empty on essentially
        # every attack -- a declared field would print on all **487**
        # `Hit`/`Miss` lines across the eight fixtures. `AttackResult`
        # rides here the same way and for the same reason, `#703`.
        #
        # That is the opposite call from `#1391`'s `purpose`, which **was**
        # declared: there the field was empty for every caller but one, so
        # it cost two fixture lines. The rule is to weigh the wire cost,
        # not to always declare.
        #
        # **A sorted tuple, never the frozenset**, which is `#1120`: a
        # frozenset is not JSON-serialisable and `wire()` is `asdict`, so
        # the day anybody does put this on the envelope it must not take
        # the log panel out. Sorted because `Square` ordering is otherwise
        # arbitrary across processes.
        landed.origin = tuple(sorted(origin))
        landed.result = result
        landed.among = among or (target,)
        landed.branch = branch
        landed.use = use
        landed.opportunity = opportunity
        landed.provoked_by = provoked  # ty: ignore[invalid-assignment]
        # **And what was in the provoker's hand**, for the same reason:
        # `i3085p1` answers a `Hit` and a trigger has no ctx to read.
        landed.provoked_weapon = (  # ty: ignore[invalid-assignment]
            rolled.provoked_weapon)
        landed.charge = charge
        landed.as_ = as_
        landed.granted_by = granted_by
        landed.granted_via = granted_via
        landed.action_point = bought
        landed.ammo = drawn
        # Which defence was attacked. `AttackDeclared` and `AttackRolled`
        # carry it as a field; the outcome did not, so "an attack against
        # your AC or Reflex misses you" had nothing to read on the one event
        # that says it missed. A plain attribute, like `result` above, so it
        # stays off the wire and out of a replay fixture.
        landed.vs = vs
        # Which hand swung. Already in the attack context and already
        # thrown away by the time anything could answer "when you hit with
        # an off-hand attack", which is the whole of a two-weapon feat's
        # printed trigger. Same plain attribute as `vs`.
        landed.hand = hand
        # The context, for the same reason `rolled.ctx` carries it above: a
        # row answering the settled outcome has to be able to read what the
        # attack *was*. `c.boost_roll` needs the crit range off it to judge a
        # boosted total by the same rule this function does -- without it the
        # verb falls back to a hard 20 and is wrong for every build that
        # widens the range, which is silently false rather than visibly so.
        landed.ctx = ctx

        # An immediate interrupt answering a hit may undo it -- a reroll on
        # "when you are hit" is the printed shape, and by the rules the hit
        # then never happened. `result.hit` was flipped and nothing looked
        # again: the `Hit` stayed in the log, no `Miss` was ever emitted,
        # and every rider hung on `Hit` had already paid out for a blow that
        # ended as a miss. Dozens of rows in the tree watch `Hit`.
        #
        # Checked in the resolve callback, which runs after the interrupts
        # and before the ordinary listeners -- so cancelling here stops the
        # riders as well as the announcement.
        def confirm(ev: Hit | Miss) -> None:
            if result.hit != isinstance(ev, Hit):
                ev.cancel("undone by an interrupt")

        def announce() -> Hit | Miss:
            # **`result.target`, not the local**, because a row answering
            # the first announcement may have moved the blow:
            # `c.redirect(recheck=True)` points a miss at somebody else
            # and re-judges it against that creature's defence, and the
            # re-announcement below is the only thing that then carries
            # the new outcome. Built from `target` it named the creature
            # that was spared, which is the half `c.redirect`'s own
            # docstring records getting wrong once before -- there about
            # the damage, here about the event.
            #
            # `result.target` is set beside the roll and is the same
            # number until something moves it, so this is identical for
            # every attack nobody redirects.
            at = int(getattr(result, "target", target) or target)
            ev = (
                Hit(attacker=attacker, target=at, power=power,
                    critical=result.critical)
                if result.hit
                else Miss(attacker=attacker, target=at, power=power)
            )
            # The second announcement site, and it needs the same -- see
            # the note above. A reader that found `origin` on one path and
            # not the other is the silent half of this component's
            # commonest bug.
            ev.origin = tuple(sorted(origin))
            ev.result = result
            ev.among = among or (target,)
            ev.branch = branch
            ev.as_ = as_
            ev.opportunity = opportunity
            ev.provoked_by = provoked  # ty: ignore[invalid-assignment]
            ev.charge = charge
            ev.granted_by = granted_by
            ev.granted_via = granted_via
            ev.action_point = bought
            ev.ammo = drawn
            ev.vs = vs
            ev.hand = hand
            ev.ctx = ctx
            return ev

        # Until the outcome stops changing. An *interrupt* answers before
        # the callback and is caught by `confirm`; a **free action or a
        # reaction** answers in the AFTER window, after the callback has
        # already passed -- so a reroll of that shape turned a miss into a
        # hit that was never announced, and every rider watching `Hit` was
        # skipped for a blow that landed.
        #
        # Twice is the practical bound: a second answer to the corrected
        # announcement is refused by the in-flight guard.
        for _ in range(3):
            was = result.hit
            world.bus.emit(landed, confirm)
            if not landed.cancelled and result.hit == was:
                break
            landed = announce()
        else:
            world.bus.emit(landed)

        # Attacking gives you away. Nothing broke hidden before, so a
        # creature that went unseen once stayed unseen for the rest of the
        # fight and drew combat advantage on every attack it ever made. A
        # row that keeps its concealment says so by hiding again -- which is
        # what the printed ones do, and it reads the same way.
        #
        # **Below the emit, and #390 asked for it to move above.** It was moved,
        # and `replay` refused it: six fixtures were the reordering alone and
        # `level-5-full` was not --
        #
        #     was: DamageRolled(amount=8,  detail='cf:rogue-scoundrel-f4')
        #     now: DamageRolled(amount=10, detail='mba')     2043 -> 1925 events
        #
        # A combat-advantage rider fires on `Hit` and asks whether the attacker
        # has it. Being hidden is what grants it, so clearing first makes every
        # such rider read the *post-attack* state and a rogue silently loses its
        # feature damage. The roll was already right; it is the riders that are
        # not. So the ordering stays and the real fix is to let a rider read the
        # attack-time state -- #446.
        world.relations.clear_source(Relation.HIDDEN_FROM, attacker, "attacked")

    announced = AttackDeclared(attacker=attacker, target=target, power=power, vs=vs)
    announced.among = among or (target,)
    announced.branch = branch
    announced.opportunity = opportunity
    announced.charge = charge
    announced.granted_by = granted_by
    announced.granted_via = granted_via
    announced.action_point = bought
    announced.ammo = drawn
    declared = world.bus.emit(announced, roll)
    if declared.cancelled:
        result.cancelled = True
    return result


def spent_action_point(world: World, eid: int) -> bool:
    """Is this creature acting on an action point right now?

    True for the whole of the turn the point was spent on, because the
    extra action it buys is not distinguishable from the rest of the turn
    once it is in the budget -- the engine hands out an action, not a
    labelled one. Wider than the printed sentence by the other actions of
    that turn, and narrower than nothing at all, which is what the four
    rows keyed off it had before.
    """
    from .components import ActionPoints

    points = world.get(eid, ActionPoints)
    return (
        points is not None
        and points.spent_round == world.round
        and world.turn == eid
    )


def _is_basic(
    world: World, attacker: int, power: str, augment: int = 0
) -> bool:
    """Does this attack count as a basic attack for this creature?

    Off `dsl.basics_of`, which folds the designated melee and ranged rows
    together with every known row whose header declares `basic=`. Separate
    from `_is_ranged` beside it because this one is about the creature as
    well as the row: the same ref is a basic attack for the warlock who
    took the card and is not one for anybody else.

    **And at the form being swung**, which is a third thing it is about.
    Five rows print *"you can use this power unaugmented as a ... basic
    attack"* and declare `basic_at=(0,)` for it, so an augmented use of one
    of them is not a basic attack and must not collect a modifier that says
    "with basic attacks". #1298.
    """
    from .dsl import basics_of

    return bool(power and power in basics_of(world, attacker, "", augment))


def _is_ranged(ref: str, branch: int = 0, world: World | None = None,
               actor: int | None = None) -> bool:
    """Is this row a ranged attack? Only those take cover from creatures.

    Read off the power's own range line rather than guessed, and False for a
    row nothing is declared for -- no cover is the safer wrong answer than
    a penalty nobody can explain. `branch` matters for a row printing two
    ranges: its melee half takes no cover from bodies and its ranged half
    does.
    """
    from .dsl import get, reach_of

    p = get(ref)
    if p is None:
        return False
    # **`dsl.reach_of` when there is a creature to ask about**, because a
    # reshape is per-character: fifteen rows print "use this ranged power as
    # a melee attack" and a cover penalty charged off the printed line would
    # shelter the target from a sword. Falls back to the print when no actor
    # is passed -- `expect.py`'s closed-form model and the two `Power`
    # methods with no world both arrive that way. #614.
    if world is not None and actor is not None:
        return reach_of(world, actor, p, branch).kind == "ranged"
    return p.reach_of(branch).kind == "ranged"


def _arena_alts(
    world: World | None, attacker: int, weapon: str
) -> tuple[dict[str, str], ...]:
    """The other arena weapons, as context substitutions.

    `cf:fighter-weaponmaster-f3s0` prints *"any of your feats that grant
    feat bonuses to attack rolls or damage rolls with one of your arena
    weapons apply to your other arena weapon as well"*. A feat's weapon
    gate is a predicate inside that feat's own body, so the only place
    the sharing can happen is where the predicate is **read** -- see
    `Mod.applies`, which asks a failed feat-kind gate again with each of
    these laid over the context.

    **Empty unless the swing was with one of the pair**, which is the
    whole of the printed condition and the reason this is cheap: every
    creature that has not selected arena weapons, and every swing with
    something else, gets `()` and no second predicate call.

    Each substitution carries both `weapon` and `group`, because a feat
    names one weapon as often as a family -- the same reason the attack
    context carries both.
    """
    if world is None or not weapon:
        return ()
    from .components import Gear

    gear = world.get(attacker, Gear)
    if gear is None or weapon not in gear.arena:
        return ()
    out: list[dict[str, str]] = []
    for other in gear.arena:
        if other == weapon:
            continue
        out.append({"weapon": other,
                    "group": _group_of(world, attacker, other)})
    return tuple(out)


def _group_of(world: World | None, attacker: int, weapon: str) -> str:
    """The `Weapon.group` of the weapon this swing went through, or `""`.

    Looked up on the attacker rather than passed in, because
    `resolve.attack` is handed the **ref** and a group is a fact about the
    object. `Gear.weapons` holds per-character `replace(w)` copies, so this
    reads whatever `c.weapon_group` or `c.improvised` has done to it rather
    than the module-level singleton -- which is the point of asking here
    and not at the call site.

    `""` for a swing through no weapon, for a creature with no `Gear`, and
    for a ref the hand does not hold. All three are the same answer to a
    gate: not this group.
    """
    if world is None or not weapon:
        return ""
    from .components import Gear

    gear = world.get(attacker, Gear)
    if gear is None:
        return ""
    for arm in gear.weapons:
        if arm.ref == weapon:
            return arm.group
    return ""


def _reach_kind(power: str, branch: int, world: World | None = None,
                actor: int | None = None) -> str:
    """`Range.kind` for this swing, or `""` for a row nothing is declared for.

    The same lookup `_is_ranged` does and deliberately not folded into it:
    that one answers a bool the whole kernel asks for, this one carries the
    word into the context so a row can ask a question the bool cannot
    express. Empty string rather than None for a missing row, so a gate's
    `ctx["reach"] in (...)` is false instead of raising.
    """
    from .dsl import get, reach_of

    p = get(power)
    if p is None:
        return ""
    # Through `dsl.reach_of` for the reason `_is_ranged` above records: the
    # whole point of `ctx["reach"]` is that a row can gate on the shape of
    # the attack, and the printed shape is the wrong answer for a creature
    # holding a reshape. #614.
    if world is not None and actor is not None:
        return reach_of(world, actor, p, branch).kind
    return p.reach_of(branch).kind


def _long_range(
    world: World, attacker: int, target: int, power: str, branch: int, ctx: dict
) -> int:
    """-2 for shooting past a ranged weapon's normal range.

    Only a **weapon** prints two numbers. A power whose range line reads
    "Ranged 10" has one, and no penalty anywhere in it, so this asks the
    weapon in hand rather than the row. Beyond the long range the shot is
    simply impossible, and nothing here enforces that -- the board is
    smaller than any long range in the table, so the cap has never had a
    situation to be wrong in, and charging a penalty for a distance that
    cannot happen would be worse than leaving it.

    A row that waives the penalty offsets it: `"long_range"` is a modifier
    like any other, so "you take no penalty at long range" is a +2 gated
    however its card gates it.

    The threshold is the **stretched** normal range, asked of the same
    `"range"` modifier `dsl._stretched` asks when it decides what may be
    aimed at, and with `"kind"` in the context because that is the key
    the targeting passes and a gate on a key its context lacks is
    silently false. Read raw, a line lengthening both a weapon's ranges
    moved the reach and left the -2 where it was, so every extra square
    it bought was targetable and penalised.
    """
    from .components import Gear
    from .dsl import _stretched, get
    from .query import distance_between
    from .types import Keyword

    p = get(power)
    from .dsl import keywords_of

    if p is None or Keyword.WEAPON not in keywords_of(world, attacker, p):
        return 0
    if p.reach_of(branch).kind != "ranged":
        return 0
    gear = world.get(attacker, Gear)
    weapon = gear.ranged if gear is not None else None
    if weapon is None or weapon.ranged is None:
        return 0
    normal = weapon.ranged[0] + _stretched(
        world, attacker, "ranged",
        {**ctx, "power": power, "range_kind": "ranged"},
        # The weapon's own short range is the base a doubling scales, so
        # the long-range penalty moves with the card rather than being
        # worked out from the printed number while the attack uses another.
        printed=weapon.ranged[0],
    )
    if distance_between(world, attacker, target) <= normal:
        return 0
    return max(0, 2 - _mods(world, attacker, "long_range", ctx))


def _mods(world: World, eid: int, what: str, ctx: dict) -> int:
    from .components import Mods

    mods = world.get(eid, Mods)
    return mods.total(what, ctx) if mods else 0


#: "Your attacks ignore all resistances", with no number printed on the
#: card. Stored as a number because `Mods` holds numbers, and larger than
#: any resistance a heroic-tier creature can have.
IGNORE_ALL = 999


def _split_mods(
    world: World, eid: int, what: str, ctx: dict
) -> dict[tuple[DamageType, ...], int]:
    from .components import Mods

    mods = world.get(eid, Mods)
    return mods.split(what, ctx) if mods else {}


def _add_mods(
    parts: list[tuple[tuple[DamageType, ...], int]],
    extra: dict[tuple[DamageType, ...], int],
) -> list[tuple[tuple[DamageType, ...], int]]:
    """Fold a `Mods.split` result into the blow.

    An untyped rider joins the power's own part, because it is whatever
    the power is. A typed one becomes a part of its own, merging with any
    earlier rider of exactly the same types.
    """
    if not extra:
        return parts
    out = list(parts)
    out[0] = (out[0][0], out[0][1] + extra.get((), 0))
    for types, value in extra.items():
        if not types or not value:
            continue
        for i, (had, seen) in enumerate(out[1:], start=1):
            if had == types:
                out[i] = (had, seen + value)
                break
        else:
            out.append((types, value))
    return out


def _rescale(
    parts: list[tuple[tuple[DamageType, ...], int]], total: int
) -> list[tuple[tuple[DamageType, ...], int]]:
    """Hold the typed split steady when something changes the total.

    Halving and "reduce the damage by 5" are written against one number
    and know nothing about parts, so the split is kept in proportion and
    the power's own part absorbs the rounding. Exact for the single-part
    case, which is every blow that has no typed rider.
    """
    was = sum(v for _, v in parts)
    if was == total:
        return parts
    if len(parts) == 1 or was <= 0:
        return [(parts[0][0], total), *((t, 0) for t, _ in parts[1:])]
    rest = [(t, v * total // was) for t, v in parts[1:]]
    return [(parts[0][0], total - sum(v for _, v in rest)), *rest]


def _ignored_resist(
    world: World, source: int, types: tuple[DamageType, ...], ctx: dict
) -> int:
    """How much of the target's resistance the attacker simply walks through.

    Read off the **attacker**, unlike every other term in `deal_damage`'s
    resistance arithmetic: "your attacks ignore the first 5 points of
    necrotic resistance" is a thing the character has, not a thing done to
    the creature in front of them.

    A rider of two types is walked through only as far as both are, which
    is the same `min` the resistance itself is read with.
    """
    specific = min(
        (_mods(world, source, f"ignore resist {t.value}", ctx) for t in types),
        default=0,
    )
    return _mods(world, source, "ignore resist", ctx) + specific


def _scoped_vuln(
    world: World, target: int, types: tuple[DamageType, ...], ctx: dict
) -> int:
    """Vulnerability that applies to only some of what reaches the creature.

    "Vulnerable 10 to the <monster>'s attacks", "vulnerable 3 to weapon
    attacks" -- `Defences.vulnerable` is a flat total with nowhere to record
    a scope, so these are kept as `(dtype, amount, when)` triples and read
    here, against the same context immunity and resistance are read against.

    `max` and not a sum, the same way the unscoped vulnerability above is
    read: two clauses making a creature vulnerable both apply, and 4e takes
    the largest rather than adding them. A `None` dtype is every type, which
    is what the attacker-scoped clauses print.
    """
    from .components import Defences

    held = world.get(target, Defences)
    if held is None or not held.vulnerable_when:
        return 0
    return max(
        (
            amount
            for dtype, amount, when in held.vulnerable_when
            if (dtype is None or dtype in types) and when(ctx)
        ),
        default=0,
    )


def _immunity_ignored(
    world: World, source: int, types: tuple[DamageType, ...], ctx: dict
) -> int | None:
    """`None` if the immunity stands, else the resistance it counts as instead.

    Two numbers rather than one flag because the cards print it both ways:
    "your attacks ignore poison immunity" is a zero, and "treat a creature
    immune to poison as if it had resist poison 20" is a twenty that the
    ignored points are then taken off.
    """
    on = _mods(world, source, "ignore immunity", ctx) or min(
        (_mods(world, source, f"ignore immunity {t.value}", ctx) for t in types),
        default=0,
    )
    if not on:
        return None
    return max(
        _mods(world, source, "immune as resist", ctx),
        max(
            (_mods(world, source, f"immune as resist {t.value}", ctx) for t in types),
            default=0,
        ),
    )


#: The mechanic a feat raises to say "a -3 penalty instead of the normal -2".
#: A symbol rather than a bare string because `c.change_amount` and
#: `c.amount_for` have to spell it the same way, and `c.bonus(once=)`'s
#: lesson is that nothing checks a key nobody wrote down -- five were
#: silently mis-spent before #544.
MARK_PENALTY = "mark"


def _mark_penalty(world: World, attacker: int, among: tuple[int, ...]) -> int:
    """A mark costs you 2 when you attack anyone but the creature that marked you.

    The penalty is for leaving your marker out of **the attack** -- not for
    being marked, and not for attacking a marked creature. `among` is every
    target of this one power use, which is the whole point: a burst is
    announced once per target, so judging this per announcement charged the
    penalty on every other target's roll even when the marker was caught in
    the same blast. The docstring said the right rule for a long time and
    the code underneath it did not implement it.
    """
    markers = world.relations.sources(Relation.MARKED_BY, attacker)
    if not markers or set(markers) & set(among):
        return 0
    # **The number belongs to the marker, and four feats raise it.** "Enemies
    # marked by you take a -3 penalty instead of the normal -2" is a fact
    # about whoever did the marking, so it is read off each of them -- which
    # is what `query.granted_amount`'s sibling `amount_for(who=)` exists for,
    # "the number belongs to the creature being helped rather than the one
    # helping". The worst applies, because a creature marked by two markers
    # suffers the worse mark and not their sum.
    from .query import granted_amount

    # **One key, and an established spelling.** The creature suffering the
    # mark is the one swinging, which is `attacker` everywhere else in this
    # file -- so a feat narrowing by it ("an **adjacent** enemy that is
    # marked by you") reads the word it already knows. No new ctx
    # vocabulary: #639 is open on `kind` meaning four things, and this is
    # not the moment to add a fifth name for a creature.
    seen = {"attacker": attacker}
    return -max(granted_amount(world, marker, MARK_PENALTY, 2, seen)
                for marker in markers)


# -- damage -----------------------------------------------------------------

def retract_miss(world: World, actor: int, power: str) -> int:
    """Un-apply what a resolved use did, for a use that missed everything.

    `i1676p1`: *"Trigger: you miss every target with an attack you make
    using this crossbow. Effect: you don't expend the use of that power.
    The power also has no effect on a miss, even if it normally does."*

    **The trigger is what makes this affordable, and `#1332` did not
    exploit it.** That issue raised three decisions -- how far an undo
    reaches, whether to record every resolution, and how to scope it --
    and the card answers all three by saying *every* target was missed.
    There is no hit half to preserve, so this does not have to tell a
    miss line from a hit line; and nothing has to be recorded on every
    attack in the game, because `Bus.log` already holds the use and
    `PowerUsed` already bounds it.

    So the undo is a walk back to this use's own `PowerUsed` and a
    reversal of what it announced:

    * every `EffectApplied` by this actor -- the hold is found by its
      label and source on the target it landed on, because the event
      carries no id;
    * every `DamageApplied` by this actor -- the points go back on.

    Returns how many things were reversed, which is a real answer at 0:
    a power whose miss line does nothing has nothing to take off.

    **Hit points are restored, not healed.** `c.heal` announces `Healed`
    and a dozen rows answer one, so healing here would pay out riders for
    a blow the card says never landed. An undo is not a heal. For the
    same reason nothing is emitted per reversal -- `#1332`'s own first
    decision is that the miss half should not have happened, and a log
    full of undo events is a different claim.

    **What it cannot reverse**, said plainly rather than left to be
    discovered: a miss that *moved* a creature or *spent* something.
    Putting a creature back is not the same as its never having moved --
    it has left and re-entered every zone on the way -- and this card's
    printed line is about effects and damage. No printed miss line in the
    tree moves anybody, measured; the day one does, this returns a count
    that is short and the row above it is the place to notice.
    """
    from .components import Health

    start = -1
    for n in range(len(world.bus.log) - 1, -1, -1):
        ev = world.bus.log[n]
        if (isinstance(ev, PowerUsed) and ev.actor == actor
                and ev.power == power):
            start = n
            break
    if start < 0:
        return 0
    undone = 0
    for ev in world.bus.log[start + 1:]:
        if isinstance(ev, EffectApplied) and ev.source == actor:
            for eff in list(world.effects.of(ev.target)):
                if eff.label == ev.label and eff.source == actor:
                    world.effects.end(eff, "the attack missed")
                    undone += 1
                    break
        elif isinstance(ev, DamageApplied) and ev.source == actor:
            health = world.get(ev.target, Health)
            if health is not None and ev.amount > 0:
                health.hp = min(health.max_hp, health.hp + ev.amount)
                undone += 1
    return undone



def deal_damage(
    world: World,
    source: int,
    target: int,
    amount: int,
    dtype: DamageType = DamageType.UNTYPED,
    detail: str = "",
    *,
    from_attack: bool = True,
    opportunity: bool = False,
    charge: bool = False,
    granted_by: int = -1,
    granted_via: str = "",
    miss: bool = False,
    crit: bool = False,
    finisher: bool = False,
    dtypes: Sequence[DamageType] = (),
    unpreventable: bool = False,
    weapon: str = "",
    #: Which hand swung, for the blows that came from a swing. `""` for
    #: every other sort of damage -- ongoing, a zone's burn, a trait's
    #: `c.flat` -- which is the honest answer rather than a default of
    #: `"main"` that would read as a main-hand hit.
    #:
    #: **The attack context has carried `hand` since `#501` and the damage
    #: context did not**, so "weapons that have the off-hand property deal
    #: +2 damage" had nothing to gate on while the *attack* half of the
    #: same card was exact. `cf:fighter-weaponmaster-f3s4` is the worked
    #: case and its note is what named this: it refused to approximate the
    #: step off `Gear.main`, because that pays the larger number on
    #: main-hand swings of a fighter whose main weapon happens to carry the
    #: property.
    hand: str = "",
    roll: Roll | None = None,
    reprice: Callable[[int], int] | None = None,
    by_attack: bool = False,
    #: **Which aiming of a two-range row this blow belongs to.** The
    #: attack context has carried `branch` all along and this did not, so
    #: the damage side answered for the row's **first** range always --
    #: which is the comment below the `ranged` key records as *"wrong for
    #: the handful that do"*.
    #:
    #: `f2202` is one of the handful: *"you can choose to make it a close
    #: blast 1 instead of a close blast 3. If you do, add 2 to the damage
    #: roll."* That is a rider on **which aiming was chosen**, and a
    #: `ctx` key was not enough -- the dict is built inside this
    #: function, so the branch has to reach the function first.
    #:
    #: Two keys move with it: `branch` itself, and `ranged`, which was
    #: computing off branch 0 by hand. #1521.
    branch: int = 0,
    #: **Half of this blow comes out as this type instead**, for a card
    #: printing a split rather than an override: *"half the damage dealt
    #: with this weapon is radiant damage"*. `Cast._halved_into` is the
    #: reader and `Cast.deals(half=True)` lays the hold; this only does
    #: the partition, so the label format stays `cast.py`'s business.
    #: #1522.
    half_as: DamageType | None = None,
) -> int:
    """Apply damage, honouring weakened, resistance, vulnerability and temp hp.

    `dtypes` is for a blow that is **several types at once** -- "1d8
    lightning and thunder damage" is one roll of two types, not two rolls.
    The printed rule is that such a blow is resisted only as far as the
    target resists *every* type in it, and is ignored only by an immunity
    covering all of them, which is exactly what the per-part arithmetic
    below already does for a typed rider. `dtype` stays the blow's primary
    type, which is what the events carry and what every existing reader
    asks about; leave `dtypes` empty for the ordinary one-type blow and
    nothing below changes by so much as a point.

    Returns what actually came off hit points.
    """
    health = world.get(target, Health)
    if health is None or not alive(world, target):
        return 0

    # Duplicates dropped rather than kept: "cold and cold" is cold, and a
    # repeated type would have `min(resist)` and `all(immune)` read the
    # same entry twice for no change and one more chance to be wrong.
    types: tuple[DamageType, ...] = tuple(dict.fromkeys(dtypes)) or (dtype,)
    dtype = types[0]

    # `opportunity` and `charge` too: a flat rider on either could not be
    # gated without them, since the ctx named only the first two. A gate on
    # a key the ctx does not carry is silently false, which is the worst
    # way for a rider to be wrong.
    #
    # **`dtype` for the same reason, and it was the commonest one left.**
    # "You gain a +1 bonus to the damage rolls of your fire powers" is a
    # whole family of feats and a long tail of item riders, and every one
    # of them had to gate on a key that was not here.
    #
    # It is read from the local rather than from the event below, and that
    # ordering is the point: a *weapon* that deals fire has to have said so
    # before this line, in `Cast.damage`'s dtype resolution. Set on a
    # `DamageRolled` listener instead, the type would change after the
    # bonus had been decided, and "my weapon deals fire" and "+1 with fire"
    # would disagree about the same blow.
    dmg_ctx = {
        "target": target,
        # **Who is dealing it, which this could not say.** The attack context has
        # carried `attacker` all along and this had eleven keys and no equivalent,
        # so a damage-side modifier gated on *who is swinging* could not be
        # written at all -- `i614p1`'s "enemies that are marked take -1 against
        # any creature other than the one that marked them" asks twice about the
        # dealer and once about the target. #302.
        #
        # `source` rather than `attacker`, because damage is dealt by things that
        # are not swings -- ongoing damage, a zone's burn, a trait's `c.flat` --
        # and for those the dealer is the effect's owner rather than somebody
        # taking a shot. `from_attack` below is how a gate tells the two apart,
        # so neither has to be guessed from a None.
        "source": source,
        "from_attack": from_attack,
        "power": detail,
        "opportunity": opportunity,
        "charge": charge,
        # The provenance of a granted swing, the same two keys the attack
        # context carries. "+2 to the damage roll of the basic attack you
        # granted" is a damage-side rider and had nothing to gate on.
        "granted_by": granted_by,
        "granted_via": granted_via,
        # **Was this blow a coup de grace?** `Cast.coup_de_grace` rolls
        # the finisher through an ordinary `strike`, so by the time the
        # damage is rolled the blow looks like any other critical --
        # `f2071` prints *"1[W] extra on a coup de grace"* and had
        # nothing to gate on. Carried on `AttackResult` and handed in
        # here by `Cast.damage`, not inferred from `crit` and a helpless
        # target: a lucky natural 20 against a helpless creature is both
        # of those and is not one.
        "finisher": finisher,
        # Which hand swung, empty for damage that came from no swing. The
        # attack context has carried this since #501; this one did not, so
        # a two-weapon card's attack half was exact and its damage half had
        # nothing to read. Read off `AttackResult.hand`, which `attack`
        # sets as a plain attribute for the reason `vs` is one -- it stays
        # off the wire and out of a replay fixture.
        "hand": hand,
        # **What was swung, by ref and by group -- the two keys the attack
        # context has carried since `#1276` and this one did not.** The
        # parameter was already here and simply never reached the
        # context, so the damage half of a card naming a weapon had
        # nothing to read while its attack half was exact. The same shape
        # of gap `hand` had, found the same way and from the same family:
        # `cf:fighter-weaponmaster-f3s0` prints *"feat bonuses to attack
        # rolls **or damage rolls** with one of your arena weapons"*, so
        # half of that clause lived here.
        "weapon": weapon,
        "group": _group_of(world, source, weapon),
        # The arena substitution, as on the attack context above.
        "arena_alt": _arena_alts(world, source, weapon),
        "dtype": dtype,
        "crit": crit,
        # **Asked of the board, not carried from the roll.** "+2 damage
        # against a creature granting you combat advantage" is a whole
        # family of feats, and the key was simply absent -- so each of
        # them either dropped the clause or called
        # `has_combat_advantage` by hand from inside its own gate, which
        # is the same question asked in the same place with more code.
        #
        # The caveat is real and is the reason this is not simply the
        # attack context's `advantage`: a *one-shot* grant is spent by
        # the attack roll, so by damage time the board says no and this
        # key says no with it. That is wrong for exactly those grants
        # and right for every standing one. Threading the rolled value
        # down would fix it and means an argument on six call sites
        # plus `Cast.damage` knowing its own result, which it does not.
        "advantage": (
            has_combat_advantage(world, source, target) if from_attack else False
        ),
        # **Melee or ranged, which only the attack context had.** Two
        # rows gated a damage bonus on `ctx["ranged"]` and, because the
        # key was absent, `not ctx.get("ranged", False)` read as True --
        # so a rider printed for melee paid on every shot as well. That
        # is the failure mode that is *too generous* rather than inert,
        # and nothing but reading the card would have caught it.
        #
        # Read off the row's own range line. `branch` is not carried
        # this far, so a power printing two ranges answers for its
        # first -- wrong for the handful that do, and right for
        # everything else.
        #
        # **`world` and `source` are passed**, so a reshape is honoured here
        # too. `deal_damage` has both, and the whole argument for a single
        # `dsl.reach_of` is that a grant honoured at one site and missed at
        # the next is a modifier nothing consults -- `durations.keywords_of`
        # records that as 22 sites and one miss. #614.
        "ranged": _is_ranged(detail, branch, world, source),
        # **Which aiming of a two-range row this is.** The attack context
        # has always had it; this did not, so a rider on the narrower of
        # two printed blasts had nothing to read. See the parameter's own
        # note. #1521.
        "branch": branch,
        # **Every type the blow is**, for the handful that are more than
        # one. `dtype` above is the primary and answers for all the blows
        # it always did; a gate that means "is there any thunder in this"
        # asks here, because `ctx["dtype"] is DamageType.THUNDER` is
        # silently false for a lightning-and-thunder blow.
        "dtypes": types,
    }
    # **The blow is a list of typed parts, not one number.** `parts[0]` is
    # what the power itself rolled, of the power's own type; a rider that
    # names a type of its own -- "your attacks deal 2 extra fire damage" --
    # is its own part, because those two points meet the target's fire
    # resistance whether or not the sword does. Every part but the first
    # exists only because some row asked for one, so a blow with no typed
    # rider is a single part and comes out of the arithmetic below
    # bit-for-bit what it did before this existed.
    parts: list[tuple[tuple[DamageType, ...], int]] = [(types, amount)]
    if from_attack:
        # A bonus to damage is a thing powers grant constantly -- "+4 damage
        # against the target until the end of the encounter" -- and for a
        # while this line was missing, so every one of them was stored and
        # never read. Nothing failed; the damage was simply never larger.
        parts = _add_mods(parts, _split_mods(world, source, "damage", dmg_ctx))
        amount = sum(v for _, v in parts)
    # **What a critical hit adds beyond maximising the dice.** 734 of the
    # heroic magic items print "Critical: +1d6 damage per plus" and the
    # engine had no hook for any of them: `Cast.damage` maxed the dice and
    # that was the whole of it, and `Mods` was read for `crit_range` --
    # how often you crit -- and never for what one is worth.
    #
    # Its own `what` rather than a `damage` mod gated on `crit`, because a
    # crit rider is rolled (`Mod.roll` already carries "+1d6") and because
    # the two stack differently: every item you hold adds its own.
    if crit:
        parts = _add_mods(parts, _split_mods(world, source, "crit_damage", dmg_ctx))
        amount = sum(v for _, v in parts)
    # The amount with every modifier in it and before *this* function's
    # halving, which is the quantity a changed die has to be priced against.
    whole = amount
    halved = False
    # **Two ways to be halved and one site that halves.** `deals_half` is
    # the *condition* -- weakened, derived off whatever is active -- and the
    # `"deals_half"` modifier is the conditional kind three printed rows
    # want: "with any attack that is not a basic attack", "against the
    # target", "creatures of that origin". Read with `dmg_ctx`, so a gate
    # can ask about the power, the target or who is dealing it. See
    # `Cast.deals_half`.
    mine = world.get(source, Mods)
    narrowed = (mine.total("deals_half", dmg_ctx)
                if mine is not None and mine.items else 0)
    if from_attack and (deals_half(world, source) or narrowed > 0):
        halved = True
        amount = amount // 2
        parts = _rescale(parts, amount)

    # **Half the blow re-typed, which is a SPLIT and not an override.**
    # `i991x1` prints *"half the damage dealt with this weapon is radiant
    # damage"*, and nothing could say it: a blow carries one type, or a
    # set of types that are all of it at once, and neither is a split.
    #
    # Done **here**, after every modifier and after the halving above, so
    # it is half of what the blow actually comes to rather than half of
    # the dice. One part is taken out proportionally and handed back
    # re-typed, so the target shrugs off only the half it resists and the
    # other half meets its own resistance -- which is the whole point of
    # the clause.
    #
    # `amount // 2` is the re-typed share, so an odd blow puts the extra
    # point in the ORIGINAL type. That is the conservative reading: the
    # card grants the new type, and granting it the rounding as well would
    # be the holder's gain on every odd number.
    if half_as is not None and amount > 0:
        share = amount // 2
        if share > 0:
            kept = _rescale(parts, amount - share)
            parts = [*[(t, v) for t, v in kept if v > 0], ((half_as,), share)]

    # **Who is taking credit for this blow, when it is not the row dealing
    # it.** A feat's damage clause written into the power it names is dealt
    # *by the power*, so `detail` is the power's ref and the feat goes
    # uncredited -- the damage half of #550, where `Cast.credit` covers the
    # effect half.
    #
    # **Beside `detail`, never instead of it.** `detail` is read by content
    # riders keyed to the power ("damage from this power", #731 watches the
    # applied event for exactly that), so substituting the feat's ref would
    # stop those matching -- the same overloading trap `Effect.by` has, and
    # the reason credit is its own channel there too.
    taking = getattr(getattr(world, "effects", None), "_credit", None)
    credited = taking[-1] if taking else ""
    announce = DamageRolled(
        source=source, target=target, amount=amount, dtype=dtype, detail=detail,
        # Empty for a one-type blow, so a listener that retypes by setting
        # `dtype` alone -- which is every one of them in the tree -- keeps
        # meaning what it has always meant.
        dtypes=types if len(types) > 1 else (),
    )
    announce.credit = credited  # ty: ignore[unresolved-attribute]
    # The context these mods were read with, for the same reason the attack
    # roll carries its own: `c.bonus(once=True)` decides whether the bonus
    # it is watching applied, and it was rebuilding a two-key context here.
    announce.ctx = dmg_ctx
    # **The dice behind the total, and what a changed face is worth.** Both
    # plain attributes, never fields: `Event.wire()` ships every declared
    # field, so a field here would reach the page and move all 290
    # `DamageRolled` lines across the seven replay fixtures. `AttackResult`
    # rides on `Hit` the same way and for the same reason, and that is the
    # precedent a row answering a damage roll was told to copy. #703.
    # **Re-pricing a rider that was NOT rolled from `roll.dice`.** A
    # critical's rider is the case: `_roll_damage_dice` returns `None` on a
    # crit -- every face is maximised, so no die was rolled -- which means
    # the `reprice` closure below is never even attached, and the rider's
    # own `+1d6 per plus` lives in `equipment._crit_rider`'s `Mod.roll()`
    # and is already summed into `whole`.
    #
    # So a row rerolling those faces reactively cannot price the change
    # from outside: `extra` is captured, and when the blow is halved
    # `ev.amount` is `got // 2`, which is not invertible. This hands back
    # the one quantity that makes it exact -- the amount with every
    # modifier in it, before this function's halving -- and applies the
    # halving itself.
    #
    # A plain attribute, never a field, for the reason the paragraph above
    # gives about `Event.wire()`: a field here would move all 290
    # `DamageRolled` lines across the seven fixtures. `i1761p1`, `#835`.
    def _recrit(delta: int, _w: int = whole, _h: bool = halved) -> int:
        got = _w + delta
        return got // 2 if _h else got

    announce.recrit = _recrit  # ty: ignore[unresolved-attribute]
    if roll is not None and reprice is not None:
        # `reprice` prices the dice as *the caller* did -- bonus,
        # enhancement, and `c.half_damage`'s own halving. Everything this
        # function added on top is independent of the faces, so it is one
        # constant, and the composition is exact rather than a
        # re-rolled approximation: re-running `_add_mods` would roll a
        # critical rider's "+1d6" a second time.
        extra = whole - reprice(roll.total)

        def _priced(total: int, _r: object = reprice, _x: int = extra) -> int:
            got = _r(total) + _x  # ty: ignore[call-non-callable]
            return got // 2 if halved else got

        announce.roll = roll  # ty: ignore[unresolved-attribute]
        announce.reprice = _priced  # ty: ignore[unresolved-attribute]
    # **What the blow is made of, by type.** `parts[0]` is what the power
    # itself rolled and every part after it is a rider that named a type of
    # its own -- which is the only place a rider's *amount* exists. Four
    # feats print "the extra necrotic damage" and read it off nothing:
    # `DamageRolled` carries one total, so a component of it could not be
    # picked out.
    #
    # A plain attribute and a tuple, for #703's reasons: a field would reach
    # the page and every replay fixture, and a tuple cannot be edited by a
    # listener into something `_rescale` would then disagree with.
    #
    # **It is the split as announced, before any listener moves
    # `ev.amount`.** A reader asking "how much of this is necrotic" wants
    # the blow as rolled; the redistribution below is what keeps the typed
    # parts consistent with whatever a listener did to the total, and a
    # reader that wanted the post-listener split would have to ask after
    # the emit, which no printed card does.
    announce.parts = tuple(parts)  # ty: ignore[unresolved-attribute]
    # **"Was an attack behind this blow", which `from_attack` is not.**
    # That flag means "offered damage modifiers": it is `True` by default
    # and only `Cast.absorb` and `falling` pass `False`, so a trait's flat
    # payout and an ongoing tick both arrive with it set. Two content rows
    # depend on that reading and argue it explicitly, so narrowing it would
    # silently drop five feature cards' riders.
    #
    # This is the other fact, and the three rows waiting wanted **opposite
    # values** of it -- which is what makes it discriminating where
    # `from_attack` is not. #731.
    announce.by_attack = by_attack  # ty: ignore[unresolved-attribute]
    rolled = world.bus.emit(announce)
    if rolled.cancelled:
        return 0
    amount = max(0, rolled.amount)
    parts = _rescale(parts, amount)
    # The type too. It is on the event and mutable, and every reader below
    # -- immunity, resistance, vulnerability, and the DamageApplied that is
    # announced -- used the local, so "its weapon attacks deal fire damage"
    # set the field and changed nothing.
    #
    # Two ways to say it and they mean different things. Setting `dtypes`
    # is "this blow is necrotic **and** poison" -- one part of two types,
    # which resistance reads as a unit. Setting `dtype` alone is the older
    # and commoner sentence, "this weapon deals fire **instead**", and it
    # overrides whatever the blow was, pair included.
    said = tuple(dict.fromkeys(rolled.dtypes))
    if said and said != types:
        new_types = said
    elif rolled.dtype != dtype:
        new_types = (rolled.dtype,)
    else:
        new_types = types
    if new_types != types:
        types = new_types
        dtype = types[0]
        rolled.dtype = dtype
        # Only the power's own part is retyped. A listener saying "this
        # attack deals cold" is speaking about the attack, not about the
        # fire rider a feat hung off it.
        parts = [(types, parts[0][1]), *parts[1:]]
    # Read back off the event, the way the attack reads its target back. A
    # listener may move the blow onto somebody else -- one creature stepping
    # in front of another -- and everything below this line used the local.
    #
    # `health` moves with it. It was bound before the emit, so the redirect
    # re-read `takes_half`, the defences and the announcement off the new
    # target while the hit points still came off the old one -- the wrong
    # creature was hurt, and `_check_down` was handed a mismatched pair.
    if rolled.target != target:
        target = rolled.target
        health = world.get(target, Health)
        if health is None or not alive(world, target):
            return 0

    # Every type in the blow, because the trait's exception is about the
    # damage source as a whole -- see `query.takes_half`. Read after the
    # redirect above, so a blow moved onto another creature is asked about
    # the types it actually carries.
    blow_types = frozenset(kind for kinds, _ in parts for kind in kinds)
    if (
        takes_half(world, target, blow_types, dmg_ctx)
        and not unpreventable
        and not _mods(world, source, "ignore insubstantial", dmg_ctx)
    ):
        # Insubstantial halves everything, and does it before resistance so a
        # creature with both does not get the better of the two twice.
        #
        # "The power deals full damage to insubstantial creatures" is the
        # attacker's line and so it is read off the attacker, beside the
        # resistance it is printed next to on most of the cards that have
        # either.
        amount = amount // 2
        parts = _rescale(parts, amount)

    # What the target's defences take off, summed across every step below
    # and announced on `DamageApplied`. `absorbed` is temporary hit points
    # and nothing else, and a row wanting "my resistance reduced this" was
    # reading it and getting False in every fight without temp hp.
    resisted = 0
    defences = world.get(target, Defences)
    # **`unpreventable` skips this whole block, vulnerability included.**
    # Ten cards print "this damage cannot be reduced or prevented in any
    # way" about damage a character takes *on purpose* -- paying hit points
    # to redirect an attack, to heal an ally, to raise a weapon's damage --
    # and the clause exists so the price cannot be dodged. Resistance and
    # immunity are exactly the dodge it forbids.
    #
    # Vulnerability goes with them, which is the one judgement here. A
    # vulnerability would *raise* the price rather than lower it, so
    # "cannot be reduced" does not bar it on the printed wording -- but
    # every one of the ten is a cost the row's own owner elects to pay, and
    # charging a character extra for electing to pay is not something any
    # of the cards says. Skipping the block whole is also the only reading
    # that cannot be got wrong by halves. Say so if a card ever wants the
    # other one.
    #
    # Temporary hit points are **not** touched, and that is deliberate:
    # they are spent below this block, and losing temp hp first is how hit
    # points work rather than a reduction of the blow. `absorbed` stays
    # honest.
    if defences is not None and not unpreventable:
        # Untyped damage is included. `c.resist(5)` with no type writes an
        # entry for every member *including* untyped, and this used to skip
        # the whole block for untyped -- so "resist 5 to all damage" was
        # read for fire and ignored for a sword, which is most of the
        # damage in a fight. The entry existed and was never consulted,
        # which reads exactly like a working defence.
        #
        # **Resistance and vulnerability are each spent once per blow**,
        # which is why the per-part figures are capped at the largest one
        # rather than summed. A creature with resist 5 to everything, hit
        # for 10 with a sword and 5 with a fire rider, shrugs off five
        # points and not ten: it has one resistance, not one per part.
        # Vulnerability is the printed version of the same rule -- only the
        # highest applies.
        live: list[list[int]] = []
        worst_vuln = 0
        # Parts an immunity removed outright. Counted into `resisted` with
        # the rest: the printed rows asking about it say "if the damage is
        # reduced", and an immunity reduces it the hardest.
        ignored = 0
        # Not `types`: that is the blow's own, read again below, and the
        # loop variable used to be spelled the same.
        for part_types, value in parts:
            resist = min(defences.resist.get(t, 0) for t in part_types)
            if all(t in defences.immune for t in part_types):
                # Immunity is not resistance and is not capped with it: a
                # part the target is immune to is simply not there.
                # `c.ignore_resistance(immunity=...)` is the only thing
                # that reopens it, and the printed form of that line is
                # usually "treat immunity as resist 20" rather than a
                # blanket ignore.
                becomes = _immunity_ignored(world, source, part_types, dmg_ctx)
                if becomes is None:
                    ignored += value
                    continue
                resist = max(resist, becomes)
            resist = max(
                0, resist - _ignored_resist(world, source, part_types, dmg_ctx)
            )
            worst_vuln = max(
                worst_vuln,
                max(defences.vulnerable.get(t, 0) for t in part_types),
                _scoped_vuln(world, target, part_types, dmg_ctx),
            )
            live.append([value, resist])
        resisted += ignored
        if not live:
            amount = 0
        else:
            # Vulnerability goes on before resistance comes off, which is
            # the printed order, and it goes on the power's own part so
            # that a single-part blow -- every blow in the tree that has
            # no typed rider -- lands on exactly the arithmetic this did
            # before parts existed.
            live[0][0] += worst_vuln
            shrugged = min(
                sum(min(v, r) for v, r in live), max(r for _, r in live)
            )
            amount = max(0, sum(v for v, _ in live) - shrugged)
            resisted += shrugged

    # Resistance that only applies to some of the damage that comes in --
    # "but only when the damage is from ranged or area attacks". `Defences`
    # holds a flat number per type and has nowhere to put a condition, so a
    # gated resistance written there would have shrugged off everything and
    # been strictly stronger than the printed line. `c.resist(when=...)`
    # lays a modifier instead and this is the only thing that reads it.
    immune_to_all = all(
        t in getattr(world.get(target, Defences), "immune", ()) for t in types
    )
    if amount and not immune_to_all:
        # **The whole damage context, not a hand-picked six.** This built its
        # own dict and dropped seven of `dmg_ctx`'s keys -- `target`,
        # `from_attack`, `granted_by`, `granted_via`, `crit`, `advantage` and
        # `ranged` -- so a gate on any of them was False forever, with `.get`'s
        # default hiding it. `ranged` is the one that matters: `c.resist`'s own
        # docstring gives "but only when the damage is from ranged or area
        # attacks" as the motivating example, which is to say the one sentence
        # the feature was built for could not be written. Measured across the 33
        # `c.resist(when=)` sites, four inline gates read a dropped key.
        #
        # `dtype` stays a **string** and `dtypes` is still added here: that is
        # the contract these 33 gates were written against, and swapping in
        # `dmg_ctx`'s enum would trade seven silently-false keys for one. Purely
        # additive is the whole point -- no gate that works today changes.
        resist_ctx = {**dmg_ctx, "dtype": dtype.value, "dtypes": types}
        gated = _mods(world, target, "resist", resist_ctx) + min(
            # **The smallest of the per-type resistances, not their sum.**
            # A blow that is lightning *and* thunder is shrugged off only
            # as far as the target resists both, so a gated "resist 10
            # lightning" and nothing against thunder stops none of it.
            # One type in `types` is every blow in the tree that is not a
            # pair, and `min` over one is that number.
            # The per-type read gets the same widened context, with its own
            # type named: a gate on "resist 10 cold from ranged attacks" is
            # asking about this `t`, not about the blow's whole type set.
            _mods(world, target, f"resist {t.value}", {**resist_ctx, "dtype": t.value})
            for t in types
        )
        left = max(
            0, amount - max(0, gated - _ignored_resist(world, source, types, dmg_ctx))
        )
        resisted += amount - left
        amount = left

    # "The creature takes no damage from an attack that misses" -- the
    # minion clause, printed on anything standing at one hit point. Nothing
    # in the damage context could say whether the blow landed, so `miss` is
    # handed in; only a miss pays for the lookup.
    # `source` as well as the row, so the clause can be scoped to one
    # attacker -- "no damage from **its** attacks that deal damage on a
    # miss". #747.
    # **And a minion gets it for free, which is where it was missing.** The
    # waiver above is a modifier a row lays, and both this comment and
    # `c.no_miss_damage`'s docstring already called it "the minion clause" --
    # but nothing ever laid it *for* a minion, so the rule it is named after
    # was the one case it did not cover.
    #
    # The cost of the gap is not an edge case. All 384 minions have exactly
    # 1 hit point, so any damage at all kills one by arithmetic, and a
    # miss-damage line is commonest on the area powers that get pointed at a
    # pack of them. So a controller cleared the whole pack on a miss.
    #
    # Read off the creature rather than armed at spawn, deliberately: arming
    # 384 stat blocks with a modifier would make the rule a property of how
    # each was built, and a spawned or reflavoured minion would miss it.
    # `only a miss pays for the lookup` still holds -- `miss and amount`
    # guards both halves. #950.
    if miss and amount and (
        is_minion(world, target)
        or _mods(world, target, "no_miss_damage",
                 {"power": detail, "source": source})
    ):
        amount = 0
    # **The weaker printed form: halved rather than removed.**
    #
    # **A creature holding both takes the stronger, and the `and amount`
    # guard is what makes that true -- not the `elif`.** Proven by a
    # plant: turning this into a second `if` left all four assertions
    # green, because the branch above sets `amount = 0` and the guard
    # then refuses. So the `elif` is a style choice, and the "both held"
    # assertion cannot tell the two spellings apart -- recorded because I
    # first wrote the opposite, corrected a true comment into a false one,
    # and the plant caught it rather than any gate.
    #
    # "Unless it is ongoing damage" needs no test: ongoing damage is not a
    # miss, so its ticks never arrive here. The miss damage that *imposed*
    # the ongoing is halved, which is the sentence read exactly.
    #
    # Rounded down, as every halving in this engine is. `i3239x1`.
    elif miss and amount and _mods(
        world, target, "half_miss_damage",
        {"power": detail, "source": source},
    ):
        amount //= 2

    absorbed = min(health.temp, amount)
    health.temp -= absorbed
    landed = amount - absorbed

    was_bloodied = health.bloodied
    health.hp -= landed
    landed_ev = DamageApplied(
        source=source,
        target=target,
        amount=landed,
        dtype=dtype,
        absorbed=absorbed,
        hp=health.hp,
        detail=detail,
        dtypes=types if len(types) > 1 else (),
        resisted=resisted,
    )
    landed_ev.credit = credited  # ty: ignore[unresolved-attribute]
    # **The same provenance on the applied event**, because that is the one
    # the three rows of #731 watch: the printed trigger is damage that
    # *landed*, and a blow a resistance ate whole is not it. Attaching it
    # only to `DamageRolled` would have left all three unable to read it.
    landed_ev.by_attack = by_attack  # ty: ignore[unresolved-attribute]
    # An attribute, not a field -- see `DamageApplied.weapon`. A field
    # reached every replay fixture and all seven diverged.
    landed_ev.weapon = weapon  # ty: ignore[unresolved-attribute]
    world.bus.emit(landed_ev)
    if not was_bloodied and health.bloodied and health.hp > 0:
        # `detail` is the row that struck, the same value `DamageApplied`
        # above carries. Five rows print the blow's *shape* or its weapon
        # and `source` alone cannot say either.
        #
        # **And `weapon` for the same reason one step further on.** `power`
        # says which row swung and not which weapon it swung, because a
        # weapon power and a basic attack can both be made with either hand
        # -- so "you bloody an enemy with an attack that uses the augmented
        # weapon" had nothing to ask. #653.
        crossed = Bloodied(actor=target, source=source, power=detail)
        crossed.weapon = weapon  # ty: ignore[unresolved-attribute]
        world.bus.emit(crossed)
    _check_down(world, target, health, source, crit, detail, weapon)
    return landed


def heal(
    world: World, source: int, target: int, amount: int, power: str = "",
    most: int = 0,
) -> int:
    health = world.get(target, Health)
    if health is None or amount <= 0:
        return 0
    if health.hp <= 0:
        health.hp = 0  # healing from below zero starts at zero, not at the deficit
        _revive(world, target)
    # Announced *before* the hit points go on, so "the target regains half
    # the normal hit points from healing effects" has a seam. It used to add
    # first and announce after, which left a row like that clawing the
    # surplus back off `Health` -- the total came out right and the number
    # in the log did not.
    offered = Healed(
        source=source, target=target, amount=amount, hp=health.hp,
        power=power, most=most,
    )
    if world.bus.emit(offered).cancelled:
        return 0
    before = health.hp
    health.hp = min(health.max_hp, health.hp + max(0, offered.amount))
    offered.amount = health.hp - before
    offered.hp = health.hp
    return health.hp - before


def spend_surge(
    world: World, eid: int, *,
    source: int = 0, granted_by: int = 0, power: str = "", healed: int = 0,
) -> bool:
    """Take one healing surge off a creature. False if it had none, or if
    something refused it.

    The only place a surge is decremented. Four sites were each doing it by
    hand and none announced it, so "when a creature spends a healing surge"
    was a sentence the engine could not observe.

    **A proposal now, not an announcement.** `SurgeSpent` is a `Decision`, so
    "the target cannot spend healing surges" is writable (`c.no_surges`, 14
    rows). The decrement is passed as `emit`'s second argument rather than
    done here, which is what `Decision`'s own docstring requires:

    > *"A proposal is refused by a listener and honoured by the emitter, and
    > four separate bugs came from an emitter that announced something and
    > then went ahead from its own local variables."*

    So a refused surge leaves the pool untouched, and the caller learns it
    from the return rather than from the pool.

    `left` is announced as what the pool *would* be and corrected by the
    resolve, so a BEFORE listener reads the proposal and an AFTER listener
    reads the fact. The alternative -- announcing the pre-spend value --
    would have the two windows disagree about the same field.
    """
    health = world.get(eid, Health)
    if health is None:
        return False
    # **A lent pool, once this creature's own is empty.** One card prints
    # *"you can spend the target's healing surges as if they were your
    # own"*, which is a pool extension rather than a substitution -- so a
    # spender with surges of his own spends those, and `surges_from` is 0
    # on everybody who was never lent to, leaving every other spend on the
    # path it was already on. `Health.surges_from` has the argument.
    pool, paid_by = health, 0
    if health.surges <= 0 and health.surges_from:
        lent = world.get(health.surges_from, Health)
        if lent is not None:
            pool, paid_by = lent, health.surges_from
    # **One emptiness test for both pools**, which is why there is no
    # `lent.surges > 0` above: an empty lender falls through to here exactly
    # as an empty own pool does. That guard was written and a plant removing
    # it passed -- it was redundant, and a redundant guard beside a real one
    # reads as if the two cases differed.
    if pool.surges <= 0:
        return False

    def take(ev: SurgeSpent) -> None:
        pool.surges -= 1
        ev.left = pool.surges

    spent = world.bus.emit(
        SurgeSpent(
            actor=eid, left=pool.surges - 1, source=source,
            granted_by=granted_by, power=power, healed=healed,
            pool=paid_by,
        ),
        take,
    )
    return not spent.cancelled


def temp_hp(
    world: World, source: int, target: int, amount: int, power: str = ""
) -> None:
    """Temporary hit points do not stack -- the larger pool wins."""
    health = world.get(target, Health)
    if health is None:
        return
    # **A term to add to, which nothing had.** "+2 to the number of
    # temporary hit points you gain" is printed on several feats and
    # `temp_hp` consulted `Mods` for nothing at all, so those rows had no
    # number to raise -- the gap their markers named after the power.
    #
    # Read off the **receiver**, because the printed line is about the
    # creature gaining them ("you gain") rather than whoever granted them.
    from .components import Mods

    mods = world.get(target, Mods)
    if mods is not None and mods.items:
        amount += mods.total("temp_hp", {"target": target, "power": power})
    # **A refusal, read off the receiver like the term above it.** Three
    # rows print *"cannot ... gain temporary hit points"* -- `p14204`,
    # `i3337p1` and `m5496a0` -- and `TempHP` is a plain notification
    # emitted *after* `health.temp` is written, so a listener could not
    # refuse one: by the time it heard, the points were already there.
    # `c.no_healing` has `Healed` to cancel because that one is a
    # `Decision`; this had nothing of the kind.
    #
    # A `Mods` key rather than a second event, because that is what the
    # `temp_hp` term one block up already is, and because the printed
    # clause is a standing state of the creature rather than a moment:
    # the three cards all say "cannot", for a duration.
    #
    # Checked **before** the non-stacking test, so a refused grant cannot
    # displace a pool the creature already has -- the opposite order would
    # let a 0 overwrite a standing 5.
    if mods is not None and mods.items and mods.total(
        "no_temp_hp", {"target": target, "power": power}
    ) > 0:
        return
    # The non-stacking rule is applied *after* the term, so a raised pool
    # can beat a standing one -- checking first would have thrown the
    # bonus away whenever the unraised number happened to tie.
    # **Announced either way, which it was not.** A grant no bigger than
    # the standing pool used to return here in silence -- so a row whose
    # whole observable act is the pool spent its round and said nothing,
    # and a card paying for *using* the feature never fired. `f3781` is
    # that card and `TempHP.swallowed` is what tells the two cases
    # apart.
    #
    # The pool itself is still left alone: temporary hit points do not
    # stack and the larger wins. Only the announcement changed.
    eaten = amount <= health.temp
    if not eaten:
        health.temp = amount
    world.bus.emit(
        TempHP(source=source, target=target, amount=amount, power=power,
               swallowed=eaten)
    )


# -- going down -------------------------------------------------------------


def _check_down(world: World, eid: int, health: Health,
                source: int | None = None, crit: bool = False,
                power: str = "", weapon: str = "",
                silent: bool = False) -> None:
    from .query import is_

    if health.hp > 0:
        return
    # Announced whichever way it went. `Dropped` used to mean only "dying,
    # not dead", so it never fired for a minion -- whose `dying_at` is 0 --
    # nor for any blow that overshot, which in play is most kills. The
    # printed sentence every row using it carries is "drops to 0 hit points
    # **or fewer**", and those rows were missing almost every death.
    went_down = Dropped(
        actor=eid, dead=health.hp <= health.dying_at, source=source,
        # The row that did it. Both callers already know it -- the damage
        # path carries `detail` and `Cast.kill` has `self.ref` -- so this
        # costs a parameter rather than a new fact, the same argument
        # `critical` below makes.
        power=power,
        # Whether the blow that did it was a critical. `crit` is already
        # in scope at the one site that calls this, so "but not by a
        # critical hit" costs a parameter rather than a new fact. #428.
        critical=crit,
        # A destruction nothing may answer -- `Dropped.silent`, read in
        # `triggers._offer`. #1567.
        silent=silent,
    )
    # **The weapon it came through, as an attribute rather than a field.**
    # Exactly `Bloodied.weapon` one event over and for its reasons: `power`
    # says which row swung and not which weapon it swung, and three rows
    # carry `dropped=("Dropped.weapon",)` for want of the difference.
    #
    # An attribute, so it stays off `Event.wire()` and out of the fixtures --
    # the `Effect.by` precedent, which is also why `Bloodied` does it this
    # way. #698.
    went_down.weapon = weapon  # ty: ignore[unresolved-attribute]
    world.bus.emit(went_down)
    # Read hit points again. A row that answers its own `Dropped` by healing
    # itself -- the shape the `dying` flag exists for -- was healed inside
    # the emit and then knocked unconscious, prone and dying regardless,
    # because this decided all of that from the reading it took on the way
    # in. `heal`'s own revival cannot help: the "dropped" effect does not
    # exist yet, so there is nothing for it to clear.
    if health.hp > 0:
        return
    if health.hp <= health.dying_at:
        _die(world, eid)
        return
    # **Damage restarts the clock on a stabilised character.** Stabilising
    # stops the death saves; it does not make somebody proof against being
    # hit again. Without this a character stabilised by a Heal check and
    # then hit stays `STABLE` and never rolls another save -- safer, lying
    # down, while being attacked. #1074.
    if is_(world, eid, Condition.STABLE):
        for eff in list(world.effects.of(eid)):
            if Condition.STABLE in eff.conditions:
                world.effects.end(eff, "hit again")
    if not is_(world, eid, Condition.DYING):
        world.effects.apply(
            eid, eid, When.ENCOUNTER, label="dropped", conditions=DROPPED
        )


def restore_hp(world: World, eid: int, hp: int) -> str:
    """Put a creature at a hit point total, with whatever that total means.

    The spawn-side counterpart to `_drop`. `resolve` could reach every state
    a dying or dead creature is in and only ever as a **consequence of
    damage**, so a record of a downed character could not be fielded: a
    sheet at -26 came back onto the board at 0 hit points, `alive`,
    `conscious` and able to act, because the conditions that give a negative
    total its meaning are applied by the damage path. #1022.

    Returns what it decided -- `"dead"`, `"dropped"` or `""` -- so a caller
    restoring a party can report it rather than inferring it from the
    numbers afterwards.

    **The three-way decision is `_drop`'s, deliberately shared in shape
    rather than in code.** Sharing the function is what cannot be done: that
    one emits `Dropped` and reads hit points *after* the emit so a row
    healing itself in answer is honoured. Neither applies here -- nothing
    attacked, and there is nobody to answer -- so the branch is restated and
    this docstring is the record that the two must move together. The
    boundaries are `health.dying_at` and `0`, read from the component rather
    than written down twice.

    **It does not emit `Dropped` or `Died`, and that is the design call
    `#1022` asked to have made rather than assumed.** Those events say
    *this just happened*; at a restore it did not, and a story-side listener
    pricing a knockdown would count a character who went down two fights
    ago. What it *does* go through is `effects.apply`, so the conditions
    arrive with a `ConditionApplied` -- `_die`'s own comment records the
    trap, where `Relations.set` imposing a grab without that event left
    thirteen rows armed and unable to fire.

    **Call it before `Encounter.start`**, which is the second thing `#1022`
    asked to have stated. A trait reads its state when it arms -- the reason
    `story/` sets `world.milestones` before `start()` -- so a character who
    is already dying when once-per-fight traits arm is a different board
    from one dropped after. Before is the honest order: the character
    *arrived* in that state. This does not enforce it, because `resolve`
    cannot see whether an encounter has started without reaching for one.
    """
    health = world.get(eid, Health)
    if health is None:
        return ""
    # Clear whatever a previous restore or a previous fight left, so the
    # call is idempotent and a creature cannot be both dead and dropped.
    _revive(world, eid)
    health.hp = max(health.dying_at, min(hp, health.max_hp))
    if health.hp > 0:
        return ""
    if health.hp <= health.dying_at:
        world.effects.apply(
            eid, eid, When.ENCOUNTER, label="dead",
            conditions=(Condition.DEAD,),
        )
        world.grid.lift(eid)
        return "dead"
    world.effects.apply(
        eid, eid, When.ENCOUNTER, label="dropped", conditions=DROPPED
    )
    return "dropped"


def _revive(world: World, eid: int) -> None:
    """Healing a dying creature clears what dropping it imposed.

    `"dead"` is cleared here too, so the two are symmetrical -- but note that
    nothing in this engine *raises* the dead, so in practice this only matters
    for a creature healed in the same breath as being killed. Resurrection is
    not modelled and this is not it. #399.
    """
    for eff in world.effects.of(eid):
        if eff.label in ("dropped", "dead"):
            world.effects.end(eff, "healed")
    health = world.get(eid, Health)
    if health is not None:
        health.failures = 0


def _die(world: World, eid: int) -> None:
    """Kill a creature. The body stays an entity; the initiative slot stays too.

    Anything this creature was imposing on somebody else that is measured in
    turns keeps running until its slot comes around -- see `Effects.bereave`
    and `Encounter.advance`. Only what nothing could ever end is cleared now.
    """
    world.bus.emit(Died(actor=eid))
    world.effects.bereave(eid, "died")
    # **Applied through the ordinary door, after `bereave`.** Through
    # `effects.apply` so a `ConditionApplied` is emitted and anything watching
    # for one can see it -- `Relations.set` imposing a grab without that event
    # left thirteen rows armed and unable to fire, and this is the same trap.
    # After `bereave`, or the hold this creature has just been given would be
    # among the ones torn down. #399.
    world.effects.apply(
        eid, eid, When.ENCOUNTER, label="dead", conditions=(Condition.DEAD,)
    )
    for kind, source, target in list(world.relations._live):
        # Relations carried by a live effect expire with it. A bare one --
        # a grab, most often -- ends now, because a corpse holds nobody.
        if eid in (source, target) and not world.effects.carries(kind, source, target):
            world.relations.clear(kind, source, target, "died")
    world.grid.lift(eid)
