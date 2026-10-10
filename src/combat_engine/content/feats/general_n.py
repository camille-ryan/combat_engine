"""General feats, the fourteenth batch: the skill-swap cards, the
elemental legacy chain, and the long martial tail.

Four shapes carry most of this file.

**The swap feat and its card.** Fifteen rows here read "you can exchange
a power you know for `fNNNb`", and the card beside them is the real
work. The parent hands the card over with `c.grant_row`; giving a power
*up* is a build-time exchange and carries `chargen.power_swap()`
throughout. Writing the parent as a grant rather than a marker is what
puts the card on a board at all.

**`PowerResolved` carries `rolls`, and that is what "you hit only one of
them" is asked of.** `dsl.use` appends one `AttackResult` per target
that swung, and each names the creature it finally landed on -- so three
area-attack riders that would otherwise have been blind (`f2150`,
`f2152b`, `f2153b`) are ordinary rows. `PowerUsed` cannot answer any of
them: it is announced above the body and no attack has been rolled.

**`c.resist` takes the highest; it no longer adds.** This file was
written while it added, and two rows were written against that: `f2320`
laid 3 to reach a printed 5, and `f2129b` laid a bare 5 for "increase
fire resistance by 5". Under the rule the code now has, the first came
to 3 and the second threw away whatever was standing. A printed *total*
is now the number to pass; a printed *increase* has to read
`c.resistances` and add to it.

**A triggered `action=NONE` row spends a use each time it fires**, so
everything here whose printed benefit has no limit is `AT_WILL`. The
three that do print one -- "the first time you are bloodied", "once per
encounter" -- are `ENCOUNTER`, and that is the card speaking.

Weapon groups are a closed set, so the khopesh/scimitar/falchion row and
the shortbow rows can only be marked: `chargen.FALCHION` and
`chargen.SHORTBOW` join the family earlier waves started.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.features import CHANNEL_DIVINITY
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    SELF,
    STANDARD,
    WILL,
    Ability,
    ActionSpent,
    ActionType,
    Attack,
    Bloodied,
    Cast,
    CloseBurst,
    Condition,
    Cover,
    DamageApplied,
    DamageRolled,
    DamageType,
    Dropped,
    Gear,
    Healed,
    Hit,
    Keyword,
    Melee,
    Miss,
    Moved,
    PowerResolved,
    Powers,
    PowerUsed,
    Ranged,
    RoundStart,
    SavingThrow,
    SecondWind,
    Size,
    SurgeSpent,
    Swap,
    Target,
    TotalDefence,
    Trigger,
    TurnStart,
    Usage,
    When,
    Window,
    about_me,
    both,
    by_charge,
    distance,
    get,
    power,
)
from combat_engine.engine.basic import MELEE, RANGED
from combat_engine.engine.query import (
    allies,
    concealment_of,
    distance_between,
    enemies,
    flanked_by,
    spread,
    squares,
    team,
)

#: A racial power or trait the benefit names in prose rather than by ref.
RACIAL = ("c.on_racial_power()",)
#: The `rt:r6-t3` choice: an at-will borrowed from another
#: class, picked at build time and recorded nowhere. The same symbol
#: `features/racial._option` carries.
RACE_OPTION = ("c.race_option()",)
#: Nothing announces that a roll was a reroll.
REROLL = ("c.on_reroll()",)
#: Which weapons a character may pick up is settled when it is built.
PROFICIENCY = ("chargen.proficiency()",)
#: "You can swap a power you know for this one." The card is handed over;
#: giving one up is a build-time exchange.
SWAP = ("chargen.power_swap()",)
#: A class feature named in prose with no `cf:` row behind it.
FEATURE = ("c.class_feature()",)
#: Another class's feature whose options each refuse themselves off
#: `c.build`, so handing one to a character of a different class hands
#: over a row whose body returns on its first line. The grant itself is
#: `c.grant_row` and the choice is `c.borrow_row`; what is missing is a
#: way to put a character on a leg of a class it did not take.
BORROW = ("c.set_build()",)

DIVINE = [Keyword.DIVINE]
WEAPON = [Keyword.WEAPON]
ALL_DEFENCES = (AC, FORT, REF, WILL)
_AREA = ("close_burst", "close_blast", "area_burst")
_CLOSE_OR_AREA = _AREA
_MELEE_REACH = ("melee", "close_burst", "close_blast")

#: `Size` is a `StrEnum`, so "larger than you" has to be an explicit
#: ladder rather than a comparison.
_SIZES = (
    Size.TINY,
    Size.SMALL,
    Size.MEDIUM,
    Size.LARGE,
    Size.HUGE,
    Size.GARGANTUAN,
)

#: The four elements the legacy chain names, in one place.
_LEGACY = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
)


# -- small shared questions -------------------------------------------------


def _used(ref: str):  # noqa: ANN202
    """`PowerUsed` names its subject `actor`, which `by_me` never reads."""

    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _resolved(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _size_rank(c: Cast, who: int) -> int:
    """Where this creature stands on the printed size ladder. `c.size_of`
    answers `MEDIUM` for anything with no footprint of its own."""
    return _SIZES.index(c.size_of(on=who))


def _i_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me


def _i_crit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and ev.critical


def _i_am_bloodied(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me


def _by_my_hand(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """`Dropped` and `Bloodied` both name their striker `source`."""
    return ev.source == me and ev.actor != me


def _granted(ref: str, card: str, **kw: Any):  # noqa: ANN202
    """The parent half of a feat whose benefit is "you gain <card>"."""

    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, **kw)
    def parent(c: Cast) -> None:
        c.grant_row(card, on=c.me, until=When.ENCOUNTER)

    parent.__name__ = ref
    parent.__doc__ = f"Hands over {card}, which is the whole of the feat."
    return parent


def _keywords(ref: str) -> frozenset:
    p = get(ref)
    return frozenset(p.keywords) if p is not None else frozenset()


def _reach_kind(ref: str) -> str:
    p = get(ref)
    return p.reach.kind if p is not None and p.reach is not None else ""


def _ref_in(c: Cast, *refs: str) -> bool:
    """A card naming weapons rather than a group; the table keys on ref."""
    gear = c.world.get(c.me, Gear)
    return gear is not None and any(w.ref in refs for w in gear.held)


def _group_in(c: Cast, *groups: str) -> bool:
    gear = c.world.get(c.me, Gear)
    return gear is not None and any(w.group in groups for w in gear.held)


def _basic_refs(c: Cast, *, ranged: bool = True) -> tuple[str, ...]:
    """What this creature's basic attack actually **is**.

    `Powers.basic` is a monster's own row more often than `mba`, so a
    damage gate comparing against the engine's default alone is false for
    anything that replaced it.
    """
    known = c.world.get(c.me, Powers)
    melee = (known.basic if known else "") or MELEE
    if not ranged:
        return (melee,)
    shot = (known.ranged if known else "") or RANGED
    return (melee, shot)


def _rba(c: Cast) -> str:
    """This creature's ranged basic attack, whatever replaced the default."""
    known = c.world.get(c.me, Powers)
    return (known.ranged if known else "") or RANGED


def _throwing(world, eid: int) -> bool:  # noqa: ANN001
    """Is a thrown weapon in hand? A `c.rolls_with` `when`, so it is handed
    `(world, eid)` and asked again at every roll rather than once at arming.

    `endswith`, because the property is written both bare and qualified --
    `"heavy thrown"` is a property and `"thrown" in properties` misses it.
    """
    gear = world.get(eid, Gear)
    return bool(gear) and any(
        prop.endswith("thrown") for w in gear.held for prop in w.properties
    )


def _drawing_a_bow(world, eid: int) -> bool:  # noqa: ANN001
    gear = world.get(eid, Gear)
    return bool(gear) and any(w.group == "bow" for w in gear.held)


def _adjacent_square(c: Cast, who: int, square: Any) -> bool:
    #: `query.squares`, not `squares_of` -- the latter is a method on the
    #: grid and importing it from `query` raised at the first call.
    return any(distance(s, square) <= 1 for s in squares(c.world, who))


def _keeps_a_familiar(world, eid: int) -> bool:  # noqa: ANN001
    """A `requires=` gate, so it gets `(world, eid)` and no `Cast`.

    A card whose whole printed Effect is about "your familiar" has
    nothing to do without one, and offering it anyway is a row that
    fires and does nothing -- which is what a wrong power looks like.
    """
    from combat_engine.engine.components import Companion

    return any(
        world.get(e, Companion).owner == eid for e in world.having(Companion)
    )


def _scaled(c: Cast, what: str, count: Callable[[dict[str, Any]], int],
            cap: int = 8, **kw: Any) -> None:
    """A bonus whose size is counted when the roll happens.

    `c.bonus` takes a fixed number, and "a bonus equal to the number of
    your allies adjacent to that enemy" is not one. So it is laid as
    `cap` separate +1s, each with a `kind` of its own -- two of the same
    kind do not stack and the larger wins, which would have made the
    whole thing +1 forever -- and each gated on the count reaching its
    own step.
    """
    for step in range(1, cap + 1):
        c.bonus(
            what, 1, on=c.me, until=When.ENCOUNTER,
            kind=f"{c.ref}:{what}:{step}",
            when=lambda ctx, n=step: count(ctx) >= n,
            **kw,
        )


# -- ridden on a power the spec hands over as a ref -------------------------


@power("f1348", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you take cold or fire damage",
       on=Trigger(DamageApplied, lambda w, me, ev: (
           ev.target == me and ev.amount > 0
           and ev.dtype in (DamageType.COLD, DamageType.FIRE)
       ), "you take cold or fire damage"))
def f1348(c: Cast) -> None:
    """`DamageApplied` rather than `DamageRolled`: the printed line is
    "when you take" it, and resistance may leave nothing to take."""
    c.temp_hp(c.wis_mod, on=c.me)


@power("f1350", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with or are damaged by a radiant attack",
       on=(
           Trigger(Hit, lambda w, me, ev: (
               ev.attacker == me and Keyword.RADIANT in _keywords(ev.power)
           ), "you hit with a radiant attack"),
           Trigger(DamageApplied, lambda w, me, ev: (
               ev.target == me and ev.amount > 0
               and ev.dtype is DamageType.RADIANT
           ), "you are damaged by radiant damage"),
       ))
def f1350(c: Cast) -> None:
    """Both halves declared. The keyword is read off the row for the
    attack you make and off the damage type for the one you take --
    `DamageApplied` drops the power, and radiant is a `Keyword` and a
    `DamageType` with the same word behind both."""
    c.temp_hp(c.con_mod, on=c.me)


@power("f1359", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use one of the associated powers",
       on=Trigger(PowerUsed, lambda w, me, ev: (
           ev.actor == me
           and ev.power in ("p569", "p7152", "p1580", "p835")
       ), "you use one of the associated powers"))
def f1359(c: Cast) -> None:
    """The Associated Powers family, and one of the few where the spec
    prints refs rather than names -- so this one is hangable where the
    twenty-two marked `feat.associated_powers` are not.

    `PowerUsed` is announced above the body, which is exactly right
    here: the bonus has to be standing before the power rolls damage.
    The Diplomacy half is a check rather than a fight.
    """
    me = c.me
    near = sum(1 for f in enemies(c.world, me) if c.adjacent(to=f))
    if near:
        c.bonus(
            "damage", near, on=me, until=When.EOT,
            when=lambda ctx: ctx.get("power") == c.trigger.power,
        )


_granted("f1360", "f1360b")


@power("f1360b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=DIVINE, group=CHANNEL_DIVINITY)
def f1360b(c: Cast) -> None:
    """"Any enemy he or she flanks" is asked per roll, not at the grant:
    a flank is made and broken inside a turn, and `query.flanked_by` is
    the question from the beneficiary's side."""
    me = c.me
    who = c.choose([me, *c.within(3, side="ally")], "who gains the bonus")
    if who is None:
        who = me
    c.bonus(
        "attack", 2, on=who, until=When.EONT,
        when=lambda ctx: (
            ctx.get("target") is not None
            and flanked_by(c.world, ctx["target"], who)
        ),
    )


@power("f2131", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1628",
       on=Trigger(PowerResolved, _resolved("p1628"), "you use that power"))
def f2131(c: Cast) -> None:
    """`PowerResolved` rather than `PowerUsed`: the racial power picks
    its targets before the body, but the opening this lays is the
    consequence of the whole use rather than the declaration.

    "Provokes opportunity attacks from your allies **when it attacks
    you**" is a window opened per attack, so it is a watch rather than a
    standing grant.
    """
    me = c.me
    friends = [a for a in allies(c.world, me) if a != me]
    for foe in c.trigger.targets:

        def open_up(ev: Any, foe: int = foe) -> None:
            if ev.attacker != foe or ev.target != me:
                return
            for friend in friends:
                c.provoke(friend, on=foe, why=c.ref)

        c.watch(Hit, open_up, on=me, until=When.EOTNT)


@power("f2176", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1448",
       on=Trigger(PowerResolved, _resolved("p1448"), "you use that power"),
       dropped=("c.retarget_side()",))
def f2176(c: Cast) -> None:
    """The ally bonus plays. Narrowing the racial power to enemies only
    does not: whom a row targets is header data chosen before the body,
    and nothing rewrites one mid-use. That the allies are in the area is
    what makes them targets at all, so `ev.targets` finds them."""
    me = c.me
    friends = set(allies(c.world, me))
    for who in c.trigger.targets:
        if who in friends:
            c.bonus("attack", 1, on=who, until=When.EONT)


@power("f2178", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with p1448",
       on=Trigger(Hit, lambda w, me, ev: (
           ev.attacker == me and ev.power == "p1448"
       ), "you hit a creature with that power"))
def f2178(c: Cast) -> None:
    c.mark(on=c.trigger.target, until=When.EONT)


@power("f2208", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with p1448",
       on=Trigger(Hit, lambda w, me, ev: (
           ev.attacker == me and ev.power == "p1448"
       ), "you hit a creature with that power"))
def f2208(c: Cast) -> None:
    c.grants_advantage(on=c.trigger.target, until=When.SONT)


@power("f2201", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use a channel divinity power",
       on=Trigger(PowerUsed, lambda w, me, ev: (
           ev.actor == me
           and (p := get(ev.power)) is not None
           and p.group == CHANNEL_DIVINITY
       ), "you use a channel divinity power"))
def f2201(c: Cast) -> None:
    """The feature arrives as a `group` on the row rather than as a ref,
    which is enough: `PowerUsed` names the power and `get` reads its
    group off the header."""
    me = c.me
    for foe in enemies(c.world, me):
        if c.bloodied(on=foe) and distance_between(c.world, me, foe) <= 5:
            for defence in ALL_DEFENCES:
                c.penalty(defence, 2, on=foe, until=When.EONT)


@power("f2242", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.shift_as(when=)",))
def f2242(c: Cast) -> None:
    """`c.shift_as` grants an action outright and has nowhere to hang a
    gate, so the question is asked once a turn instead: standing next to
    somebody your p1831 is holding at the top of your turn buys the
    better shift for that turn alone. Granting it for the fight, which
    is what this row used to do, is the printed line without its
    condition."""
    me = c.me

    def each_turn(ev: Any) -> None:
        if ev.actor != me or ev.ghost:
            return
        if any(c.adjacent(to=who) for who in c.suffering("p1831")):
            c.shift_as(MOVE, 2, on=me, until=When.EOT)

    c.watch(TurnStart, each_turn, on=me, until=When.ENCOUNTER)


_granted("f2243", "f2243b")


@power("f2243b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_REACTION, reach=Ranged(5), target=NO_TARGET,
       keywords=[Keyword.DIVINE, Keyword.POISON], group=CHANNEL_DIVINITY,
       trigger="an enemy within 5 squares saves against a condition",
       on=Trigger(SavingThrow, lambda w, me, ev: (
           ev.saved and ev.actor != me
       ), "an enemy within range saves"))
def f2243b(c: Cast) -> None:
    """`SavingThrow` names its subject `actor`, so `by_me` and
    `targets_me` are both false on it and the predicate is written out.
    The side and the range are asked in the body, where the board is."""
    who = c.trigger.actor
    if who in enemies(c.world, c.me) and c.distance(who) <= 5:
        c.ongoing(5, DamageType.POISON, on=who)


@power("f2245", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you succeed on a saving throw",
       on=Trigger(SavingThrow, lambda w, me, ev: (
           ev.actor == me and ev.saved
       ), "you succeed on a saving throw"))
def f2245(c: Cast) -> None:
    """The hide is conditioned on the cover you already have, which
    `query.concealment_of` answers -- superior concealment is the -5
    that `c.conceal(total=True)` sets, and the printed line wants that
    or superior cover."""
    c.shift(1)
    if concealment_of(c.world, c.me) is Cover.SUPERIOR:
        c.hide()


@power("f2255", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you take a move action",
       on=Trigger(ActionSpent, lambda w, me, ev: (
           ev.actor == me and ev.cost is ActionType.MOVE
       ), "you take a move action"))
def f2255(c: Cast) -> None:
    """`ActionSpent` is the only announcement that an action was taken
    at all, and `Encounter.spend` emits it before the action runs --
    which is where "you can **also** move your familiar" belongs."""
    fam = c.familiar()
    if fam is not None:
        c.move(c.speed_of(fam), who=fam)


@power("f2287", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit a bloodied foe",
       on=Trigger(Hit, lambda w, me, ev: ev.attacker == me,
                  "you hit an enemy"))
def f2287(c: Cast) -> None:
    """Bloodied is asked in the body rather than the predicate: the blow
    that bloodies is the one this is printed for, and `Hit` fires before
    the damage lands."""
    foe = c.trigger.target
    if not c.bloodied(on=foe):
        return
    me = c.me
    c.penalty("attack", 2, on=foe, until=When.EONT,
              when=lambda ctx: ctx.get("target") == me)


@power("f2288", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2288(c: Cast) -> None:
    """A trait, not a trigger: flanking is a fact about two positions
    that is true or false at the moment the blow lands, so every gate
    here is asked of the damage context rather than at arming.

    Each ally carries the bonus only while **it** is flanking the same
    foe with me, which is what "allies you flank with" reads.
    """
    me = c.me

    def worth_it(ctx: dict[str, Any], who: int) -> bool:
        foe = ctx.get("target")
        return (
            foe is not None and c.bloodied(on=foe)
            and flanked_by(c.world, foe, me)
            and flanked_by(c.world, foe, who)
        )

    for who in [me, *(a for a in allies(c.world, me) if a != me)]:
        c.bonus(
            "damage", 2, on=who, until=When.ENCOUNTER,
            when=lambda ctx, who=who: worth_it(ctx, who),
        )


@power("f2294", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an enemy saves against ongoing damage",
       on=Trigger(SavingThrow, lambda w, me, ev: (
           ev.saved and ev.actor != me and "ongoing " in ev.against
       ), "an enemy saves against ongoing damage"),
       dropped=("SavingThrow.source",))
def f2294(c: Cast) -> None:
    """"Ongoing damage" is readable -- `SavingThrow.against` is
    `str(effect)`, and `Effect.__str__` spells out "ongoing N type".
    Whose ongoing damage it was is not on the event, so this pays out on
    any enemy's successful save rather than only on one you imposed."""
    who = c.trigger.actor
    if who in enemies(c.world, c.me):
        c.flat(max(c.cha_mod, c.int_mod), dtype=DamageType.COLD, on=who)


@power("f2297", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with an augmented psionic power",
       on=Trigger(Hit, lambda w, me, ev: (
           ev.attacker == me and Keyword.PSIONIC in _keywords(ev.power)
       ), "you hit with a psionic power"),
       )
def f2297(c: Cast) -> None:
    """"Augmented" is `c.points_spent`, which counts what went into that
    row this encounter. What is dropped is "of your powers": `c.vulnerable`
    writes a flat number into `Defences` with nowhere to hang a gate, so
    an ally's fire gets the benefit of it too."""
    foe = c.trigger.target
    if c.points_spent(c.trigger.power) <= 0:
        return
    # "The fire and the psychic damage **of your powers**" -- scoped to
    # this character's own attacks, which is what was dropped. Unscoped it
    # made the enemy vulnerable to everybody's fire.
    me = c.me
    mine = lambda ctx: ctx.get("source") == me  # noqa: E731
    for kind in (DamageType.FIRE, DamageType.PSYCHIC):
        c.vulnerable(2, kind, on=foe, until=When.EONT, when=mine)


@power("f2299", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you shift",
       on=Trigger(Moved, lambda w, me, ev: (
           ev.actor == me and ev.kind_ == "shift"
       ), "you shift"))
def f2299(c: Cast) -> None:
    """`Moved` is the only one of the three movement events that carries
    `from_`, and "an ally adjacent to your **starting** square" is asked
    of nothing else. `MoveEnd` knows where you arrived and not where you
    left."""
    start = c.trigger.from_
    me = c.me
    for friend in allies(c.world, me):
        if friend != me and _adjacent_square(c, friend, start):
            c.slide(1, on=friend)
            return


@power("f2321", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use f2319b",
       on=Trigger(PowerResolved, _resolved("f2319b"), "you use that power"))
def f2321(c: Cast) -> None:
    """One roll, so `once=True`: a +2 held to the end of the next turn
    would buy every attack in between."""
    c.bonus("attack", 2, on=c.me, until=When.EONT, once=True)


@power("f2322", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you are first bloodied",
       on=Trigger(Bloodied, about_me, "you are bloodied"))
def f2322(c: Cast) -> None:
    """`ENCOUNTER` is right here and nowhere else in this file: the card
    prints "the first time ... in each encounter", so a use spent on the
    first firing is the printed limit rather than an accident."""
    c.restore_use("f2319b", on=c.me)


@power("f2433", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1628",
       on=Trigger(PowerResolved, _resolved("p1628"), "you use that power"))
def f2433(c: Cast) -> None:
    """The racial power is named in prose here, but `f2131`'s gate in the
    same batch spells it `p1628`, so the trigger is a ref rather than a
    guess. `c.bonus(dice=)` is how an extra `[W]` is added to a roll that
    has not happened yet."""
    c.bonus(
        "damage", 0, dice=c.w(), on=c.me, until=When.EONT, once=True,
        when=lambda ctx: (
            Keyword.MARTIAL in _keywords(ctx.get("power", ""))
            and Keyword.WEAPON in _keywords(ctx.get("power", ""))
        ),
    )


# -- the skill-swap cards ---------------------------------------------------


_granted("f2103", "f2103b", swap=Swap(3, Usage.ENCOUNTER))


@power("f2103b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(REF, vs=WILL), dropped=("c.pick_pocket()",))
def f2103b(c: Cast) -> None:
    """"Dexterity or Charisma" with one ability in the header: the roll
    carries the difference as `plus=` and the damage line reads the
    larger modifier directly.

    "Grants combat advantage to **all** attackers" is `to="team"` --
    the relation names one beneficiary at a time, and my side is who it
    matters to. Picking the pocket is a free-action Thievery check with
    no combat consequence and nowhere to put its result.
    """
    edge = max(0, c.cha_mod - c.dex_mod)
    if c.strike(plus=edge):
        c.damage(c.w(), max(c.dex_mod, c.cha_mod))
        c.grants_advantage(to="team", until=When.EONT)
    if c.first:
        c.shift(1)


_granted("f2104", "f2104b", swap=Swap(6, utility=True))


@power("f2104b", level=1, cls="", usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF)
def f2104b(c: Cast) -> None:
    """The errata'd text, which drops the trigger line and makes the whole
    thing an Effect. A grab is a `Condition` like the other three, so one
    `c.cure` says all of it."""
    c.cure(
        Condition.GRABBED, Condition.SLOWED, Condition.IMMOBILIZED,
        Condition.RESTRAINED, on=c.me,
    )
    c.shift(1)


_granted("f2105", "f2105b", swap=Swap(9, Usage.DAILY))


@power("f2105b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Melee(1), target=ONE_CREATURE, keywords=WEAPON,
       attack=Attack(REF, vs=AC),
       dropped=("c.phasing(through=)", "c.pick_pocket()"))
def f2105b(c: Cast) -> None:
    """The Effect runs first, as printed: the shift is what brings you
    into reach. Moving through the target's space on the way is the
    dropped clause -- `c.phasing` goes through terrain and has no way to
    name one creature -- and so is the free-action Thievery check, which
    was going unsaid here while f2103b named it.

    The secondary attack is rolled by hand with `c.attack`, because a
    header carries one attack line and this card prints two.
    """
    foe = c.target
    if foe is None:
        return
    edge = max(0, c.cha_mod - c.dex_mod)
    c.shift(4)
    if c.strike(plus=edge):
        c.damage(c.w(2))
    else:
        c.shift(1)
    if c.attack(c.dex_ + edge, AC, on=foe):
        c.damage(c.w(), on=foe)
    c.shift(c.speed_of())


_granted("f2106", "f2106b", swap=Swap(3, Usage.ENCOUNTER))


@power("f2106b", level=1, cls="", usage=ENCOUNTER, action=STANDARD,
       reach=Melee(1),
       target=Target(side="enemy", count=1,
                     label="granting you combat advantage", grants_ca=True),
       keywords=WEAPON, attack=Attack(FORT, vs=FORT))
def f2106b(c: Cast) -> None:
    """`grants_ca=True` rather than a `relation`: the stored grant is only
    part of the answer, since flanking is computed and never stored. The
    prerequisite stays a column -- `chargen.meets` enforces it and
    `Power.requires` is the wrong tool for a fact that cannot change
    mid-fight.

    "Falls prone if it takes damage while dazed **from this attack**" is
    a watch tied to the hold this row laid, so a daze from anywhere else
    does not set it off.
    """
    edge = max(0, c.cha_mod - c.str_mod)
    if not c.strike(plus=edge):
        return
    c.damage(c.w(), max(c.str_mod, c.cha_mod))
    held = c.dazed(until=When.EONT)
    foe = c.target
    if held is None or foe is None:
        return

    def topple(ev: Any) -> None:
        if ev.target == foe and ev.amount > 0 and held.live:
            c.prone(on=foe)

    c.watch(DamageApplied, topple, on=c.me, until=When.EONT, once=True)


_granted("f2107", "f2107b", swap=Swap(6, utility=True))


@power("f2107b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_REACTION, reach=PERSONAL, target=SELF,
       keywords=[Keyword.FEAR],
       trigger="you are hit or missed by an attack",
       on=(
           Trigger(Hit, lambda w, me, ev: ev.target == me and ev.attacker != me,
                   "you are hit by an attack"),
           Trigger(Miss, lambda w, me, ev: ev.target == me and ev.attacker != me,
                   "you are missed by an attack"),
       ),
       dropped=("c.immune(keyword=)",))
def f2107b(c: Cast) -> None:
    """Both halves of "hit or missed" are declared; declaring one would
    have looked finished. Creatures immune to fear are the dropped
    clause -- immunity in this engine is to conditions, not keywords."""
    c.grants_advantage(on=c.trigger.attacker, until=When.EONT)


_granted("f2108", "f2108b", swap=Swap(9, Usage.DAILY))


@power("f2108b", level=1, cls="", usage=DAILY, action=STANDARD,
       reach=Melee(1),
       target=Target(side="enemy", count=1,
                     label="granting you combat advantage", grants_ca=True),
       keywords=WEAPON, attack=Attack(FORT, vs=FORT))
def f2108b(c: Cast) -> None:
    """The Effect lands whether the attack does, which is what "Effect"
    means, so both watches are armed outside the hit branch.

    Standing up is announced as `ConditionEnded` on prone and nothing
    else, and `c.provoke` is the verb that opens a window for one named
    attacker.
    """
    foe = c.target
    edge = max(0, c.cha_mod - c.str_mod)
    if c.strike(plus=edge):
        c.damage(c.w(), max(c.str_mod, c.cha_mod))
    else:
        c.half_damage(c.w(), max(c.str_mod, c.cha_mod))
    if foe is None:
        return
    me = c.me

    def stood(ev: Any) -> None:
        if ev.target == foe and ev.condition is Condition.PRONE:
            c.provoke(me, on=foe, why=c.ref)

    from combat_engine.engine import ConditionEnded

    c.watch(ConditionEnded, stood, on=me, until=When.ENCOUNTER)

    def follow_up(ev: Any) -> None:
        if (
            ev.attacker == me and ev.target == foe
            and c.turn_of() == me
            and _reach_kind(ev.power) in _MELEE_REACH
        ):
            c.prone(on=foe)

    c.watch(Hit, follow_up, on=me, until=When.ENCOUNTER)


# The light is an *action* the feat grants -- "as a minor action, you can
# shed bright light out to 4 squares until you end it as a free action" --
# not a standing effect. `c.light` exists now and writing it here would
# shed the light permanently, which is a different and better feat.
_granted("f2117", "f2117b", swap=Swap(2, utility=True),
         dropped=("c.grant_action('light')",))


@power("f2117b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.DIVINE, Keyword.RADIANT],
       trigger="you hit an enemy with an attack",
       on=Trigger(Hit, _i_hit, "you hit an enemy with an attack"))
def f2117b(c: Cast) -> None:
    """"Cannot benefit from invisibility" is `c.truesight(of=)`, which is
    the one named-creature shape of the sense -- laid on everybody on my
    side, because the printed line takes the invisibility away rather
    than granting me one pair of eyes."""
    foe = c.trigger.target
    c.damage("1d6", dtype=DamageType.RADIANT, on=foe)
    c.grants_advantage(on=foe, to="team", until=When.EONT)
    for who in [c.me, *(a for a in allies(c.world, c.me) if a != c.me)]:
        c.truesight(of=foe, on=who, until=When.EONT)


_granted("f2151", "f2151b", swap=Swap(6, utility=True))


@power("f2151b", level=1, cls="", usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, todo=("events.DieRolled",))
def f2151b(c: Cast) -> None:
    """Both halves want the same thing that does not exist: nothing
    announces an individual damage die, so neither "you roll a 1 on a
    damage die" nor "reroll any 1 or 2" has anywhere to stand."""


_granted("f2152", "f2152b", swap=Swap(6, utility=True))


@power("f2152b", level=1, cls="", usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with an area or close attack power",
       on=Trigger(PowerResolved, lambda w, me, ev: (
           ev.actor == me and _reach_kind(ev.power) in _AREA
           and any(r.hit for r in ev.rolls)
       ), "you hit with an area or close attack power"),
       dropped=("c.origin_of()",))
def f2152b(c: Cast) -> None:
    """Everybody the attack touched is pushed. What is dropped is the
    square they are pushed *from*: the printed line measures from the
    attack's origin and nothing records where a resolved power was
    aimed, so this pushes away from the caster -- which is the same
    square for a close burst and not for an area one."""
    for who in c.trigger.targets:
        c.push(5, on=who)


_granted("f2153", "f2153b", swap=Swap(6, utility=True))


@power("f2153b", level=1, cls="", usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with an area attack power",
       on=Trigger(PowerResolved, lambda w, me, ev: (
           ev.actor == me and _reach_kind(ev.power) == "area_burst"
           and any(r.hit for r in ev.rolls)
       ), "you hit with an area attack power"))
def f2153b(c: Cast) -> None:
    """"Each creature you hit" is `PowerResolved.rolls`: one
    `AttackResult` per swing, each naming the creature the blow finally
    landed on. `ev.targets` would knock down the ones that were missed
    as well."""
    for roll in c.trigger.rolls:
        if roll.hit and roll.target:
            c.prone(on=roll.target)


_granted("f2154", "f2154b", swap=Swap(9, utility=True))


@power("f2154b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def f2154b(c: Cast) -> None:
    """"Including insubstantial" is its own argument, because insubstantial
    is a halving read a few lines above resistance and not a resistance.

    "Ranged, area, or close" is the row's own reach line, read back off
    the power the damage context names -- `ctx["ranged"]` is melee or not
    and would let a close burst through. Held until the end of your next
    turn rather than spent on the first blow: a burst is announced once
    per target and a one-shot would cover only the first of them."""

    def reaching(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power", ""))
        return p is not None and p.reach.kind in (
            "ranged", "close_burst", "close_blast", "area_burst"
        )

    c.ignore_resistance(
        None, on=c.me, until=When.EONT, immunity=True, insubstantial=True,
        when=reaching,
    )


_granted("f2155", "f2155b", swap=Swap(6, utility=True))


@power("f2155b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def f2155b(c: Cast) -> None:
    """"The **next** ranged attack roll" is `once=True`.

    The one-shot is spent on `AttackRolled` and only when the `when=`
    gate is true of the real attack context, so a melee swing in between
    does not eat it. The regain-on-a-miss is `c.restore_use` against
    this row's own ref."""
    me = c.me
    c.ignore_cover(
        on=me, until=When.EONT, once=True,
        when=lambda ctx: bool(ctx.get("ranged", False)),
    )

    def missed(ev: Any) -> None:
        if ev.attacker == me:
            c.restore_use(c.ref, on=me)

    c.watch(Miss, missed, on=me, until=When.EONT, once=True)


_granted("f2891", "f2891b", swap=Swap(6, utility=True))


@power("f2891b", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=DIVINE,
       requires=_keeps_a_familiar, requires_text="you must have a familiar",
       dropped=("c.grants_in(advantage=)",))
def f2891b(c: Cast) -> None:
    """The light itself is not a combat effect. What is is "enemies grant
    combat advantage while within 3 squares of your familiar", and that
    is a standing area condition: `c.grants_in` carries numbers into a
    zone and combat advantage is a relation, so this is laid on whoever
    is inside the radius when the power goes off."""
    fam = c.familiar()
    if fam is None:
        return
    for foe in c.within(3, of=fam, side="enemy"):
        c.grants_advantage(on=foe, to="team", until=When.EONT)


# -- the divine free-action cards -------------------------------------------


_granted("f2138", "f2138b")


@power("f2138b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=CloseBurst(3), target=SELF,
       keywords=[Keyword.DIVINE, Keyword.HEALING],
       trigger="you bloody an enemy or reduce one to 0 hit points",
       on=(Trigger(Dropped, _by_my_hand, "you reduce an enemy to 0 hit points"),
           Trigger(Bloodied, _by_my_hand, "you bloody an enemy")))
def f2138b(c: Cast) -> None:
    """The surge is spent by the caster and the hit points land on whoever
    is chosen, which is what "gains hit points **as if** it spent the
    healing surge" reads.
    """
    me = c.me
    who = c.choose([me, *c.within(3, side="ally")], "who gains the surge")
    if who is None:
        who = me
    if c.spend_surge(on=me):
        c.heal(c.surge_value(of=who), on=who)


_granted("f2140", "f2140b")


@power("f2140b", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_REACTION, reach=Ranged(5), target=NO_TARGET,
       keywords=[Keyword.DIVINE, Keyword.HEALING], group=CHANNEL_DIVINITY,
       trigger="you or an ally within 5 squares is crit or bloodied",
       on=(
           Trigger(Hit, lambda w, me, ev: ev.critical, "a critical hit lands"),
           Trigger(Bloodied, lambda w, me, ev: True, "somebody is bloodied"),
       ))
def f2140b(c: Cast) -> None:
    """Two events for one printed trigger, and the side and the range are
    asked in the body: `Hit` names its victim `target` and `Bloodied`
    names its subject `actor`, so no one predicate covers both."""
    me = c.me
    ev = c.trigger
    who = getattr(ev, "target", None)
    if who is None:
        who = ev.actor
    if who != me and who not in allies(c.world, me):
        return
    if c.distance(who) > 5:
        return
    if c.may("spend a healing surge", who=who):
        c.surge(on=who)


# -- the elemental legacy chain ---------------------------------------------


@power("f2319", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2319(c: Cast) -> None:
    """The card and the resistance both, which is why this is not
    `_granted`."""
    c.grant_row("f2319b", on=c.me, until=When.ENCOUNTER)
    for dtype in _LEGACY:
        c.resist(2, dtype, on=c.me, until=When.ENCOUNTER)


@power("f2319b", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF,
       keywords=[Keyword.ACID, Keyword.COLD, Keyword.FIRE, Keyword.LIGHTNING],
       trigger="you hit an enemy with an attack",
       on=Trigger(Hit, _i_hit, "you hit an enemy with an attack"))
def f2319b(c: Cast) -> None:
    """The type is chosen at use, which is what "acid, cold, fire **or**
    lightning" means on a card that carries all four keywords."""
    pick = c.choose(list(_LEGACY), "which damage type")
    c.flat(3, dtype=pick or DamageType.FIRE, on=c.trigger.target)


@power("f2318", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2318(c: Cast) -> None:
    """`query.speed` reads `Mods.total("speed", ...)`, so a gated speed
    bonus is a real thing rather than a number nobody looks at."""
    me = c.me
    c.bonus("speed", 1, on=me, until=When.ENCOUNTER,
            when=lambda ctx: c.bloodied(on=me))


@power("f2320", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2320(c: Cast) -> None:
    """**Five**, the printed total. This row used to lay 3 on the grounds
    that f2319 -- which this feat requires -- had already laid 2 and
    `c.resist` added them; it takes the highest now, so the arithmetic
    that made 3 right makes it a resistance two points short."""
    for dtype in _LEGACY:
        c.resist(5, dtype, on=c.me, until=When.ENCOUNTER)


# -- the diabolic and intimidating cards ------------------------------------


@power("f2129", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2129(c: Cast) -> None:
    """A trait, not a trigger, because the row has to do two things: hand
    over the card and arm the crit rider. Declared `on=Trigger(Hit, ...)`
    the grant would never happen at all.

    Taking the old racial power away is written now: the race's own
    power is `p1628`, which is a ref, so `c.forbid` has something to
    name and "replace" is both halves rather than one.
    """
    me = c.me
    c.grant_row("f2129b", on=me, until=When.ENCOUNTER)
    c.forbid("p1628", on=me, until=When.ENCOUNTER)

    def avenge(ev: Any) -> None:
        if ev.target != me or not ev.critical:
            return
        foe = ev.attacker
        c.bonus(
            "attack", 2, on=me, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx: ctx.get("target") == foe,
        )

    c.watch(Hit, avenge, on=me, until=When.ENCOUNTER)


@power("f2129b", level=1, cls="", usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.POLYMORPH],
       dropped=("c.bonus(of_ref=)",))
def f2129b(c: Cast) -> None:
    """Raising the attack bonus that *another* row grants is the dropped
    clause: m1031a4's bonus lives inside its own effect and nothing can
    reach in and rewrite one.

    "**Increase** fire resistance by 5" is read off `c.resistances` and
    added. A bare `c.resist(5)` was right while the method added; it
    takes the highest now, so on the race that prints this -- which
    already resists fire -- it was throwing the standing figure away.
    """
    me = c.me
    c.form(until=When.ENCOUNTER, label=c.ref)
    c.regeneration(2, on=me, until=When.ENCOUNTER)
    standing = c.resistances(on=me).get(DamageType.FIRE, 0)
    c.resist(standing + 5, DamageType.FIRE, on=me, until=When.ENCOUNTER)
    c.bonus("damage", 2, on=me, until=When.ENCOUNTER)
    c.grant_row("f2129c", on=me, until=When.ENCOUNTER)


@power("f2129c", level=1, cls="", usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you hit an enemy with an attack",
       on=Trigger(Hit, _i_hit, "you hit an enemy with an attack"))
def f2129c(c: Cast) -> None:
    me = c.me
    foe = c.trigger.target
    c.damage("1d10", on=foe)
    c.penalty("attack", max(c.int_mod, c.cha_mod), on=foe,
              until=When.SAVE_ENDS,
              when=lambda ctx: ctx.get("target") == me)


_granted("f2130", "f2130b", swap=Swap(2, utility=True))


@power("f2130b", level=1, cls="", usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with an attack",
       on=Trigger(Hit, _i_hit, "you hit an enemy with an attack"),
       dropped=("SkillCheck.target",))
def f2130b(c: Cast) -> None:
    """Half the printed trigger is declared. `SkillCheck` says who rolled
    and against what skill but never who it was aimed at, so "the
    creature you intimidated" has no referent; the attack half does.

    The aftereffect is the same penalty again, for a turn, once the save
    lands -- `When.EOTNT`, because the card clocks it on the *target's* next
    turn and not the caster's. The Intimidate bonus is a check, not a fight.
    """
    me = c.me
    victim = c.trigger.target
    held = c.penalty("attack", c.cha_mod, on=victim, until=When.SAVE_ENDS,
                     when=lambda ctx: ctx.get("target") == me)
    c.aftereffect(held, lambda: c.penalty(
        "attack", c.cha_mod, on=victim, until=When.EOTNT,
        when=lambda ctx: ctx.get("target") == me))


@power("f2132", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2132(c: Cast) -> None:
    """Two clauses, both written.

    The initiative swap is the *difference* between the two modifiers,
    laid with `c.initiative` -- `c.bonus("initiative", ...)` is read by
    nothing. A trait is armed after the opening rolls, so this moves the
    character in the order rather than changing the roll.

    "Has not yet acted" is not a state anything holds, so the row keeps
    its own roll. `ev.ghost` is the guard: a ghost turn is the policy
    looking ahead, and counting one would retire every victim before the
    first real turn.
    """
    me = c.me
    if c.cha_mod != c.dex_mod:
        c.initiative(c.cha_mod - c.dex_mod, on=me)

    acted: set[int] = set()

    def note_turn(ev: Any) -> None:
        if not ev.ghost:
            acted.add(ev.actor)

    c.watch(TurnStart, note_turn, on=me, until=When.ENCOUNTER)

    def sting(ev: Any) -> None:
        if ev.attacker != me or ev.target in acted:
            return
        foe = ev.target
        c.penalty("attack", c.cha_mod, on=foe, until=When.EONT,
                  when=lambda ctx: ctx.get("target") == me)

    c.watch(Hit, sting, on=me, until=When.ENCOUNTER)


# -- the elf bloodline and the concealment tail -----------------------------


@power("f2156", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2156(c: Cast) -> None:
    """A Stealth bonus for nearby allies and nothing else."""


@power("f2157", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, proficiency=("w3611",))
def f2157(c: Cast) -> None:
    """Light blade is a group the engine carries, so the damage half is
    exact, and the grant is header data `chargen` reads at build time."""
    me = c.me
    c.bonus("damage", 2, on=me, until=When.ENCOUNTER, kind="feat",
            when=lambda ctx: _group_in(c, "light blade"))


@power("f2158", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you take the total defence action while you have concealment",
       on=Trigger(TotalDefence, about_me, "you take the total defence action"))
def f2158(c: Cast) -> None:
    """Total defence is an action now and announces itself, so the moment
    this row is printed for finally arrives.

    "While you have **any** concealment" is `Cover.NONE` being the only
    answer that fails -- partial and total both count, which is why this
    asks `concealment_of` rather than a label.
    """
    if concealment_of(c.world, c.me) is not Cover.NONE:
        c.invisible(on=c.me, until=When.SONT)


@power("f2159", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you are first bloodied",
       on=Trigger(Bloodied, about_me, "you are bloodied"))
def f2159(c: Cast) -> None:
    """`ENCOUNTER` is the printed limit: "the first time you are bloodied
    in an encounter" is exactly one firing."""
    c.conceal(on=c.me, until=When.EONT)


@power("f2160", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you spend a healing surge",
       on=Trigger(SurgeSpent, lambda w, me, ev: ev.actor == me,
                  "you spend a healing surge"))
def f2160(c: Cast) -> None:
    """`SurgeSpent` names its subject `actor`, so `by_me` is false on it.
    Total concealment is `Cover.SUPERIOR`, which is what
    `c.conceal(total=True)` sets and `query.concealment_of` reads back."""
    if concealment_of(c.world, c.me) is Cover.SUPERIOR:
        c.heal(c.wis_mod, on=c.me)


@power("f2161", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, lambda w, me, ev: ev.actor == me,
                  "you use your second wind"))
def f2161(c: Cast) -> None:
    """`Cast.second_wind` announces itself and *then* lays +2 on all four
    defences until the start of your next turn, so a handler answering
    the event cannot end a thing that does not exist yet. Giving the
    bonus up is therefore written as an equal untyped penalty over the
    same clock: untyped modifiers add, so the pair comes to nothing and
    the character is left exactly where the card says.

    "If you already have concealment, you instead gain total
    concealment" is read off `query.concealment_of`, which answers
    `Cover.NONE` rather than None when there is none.
    """
    me = c.me
    if not c.may("give up the second wind defence bonus", who=me):
        return
    for defence in ALL_DEFENCES:
        c.penalty(defence, 2, on=me, until=When.SONT)
    already = concealment_of(c.world, me) is not Cover.NONE
    c.conceal(on=me, until=When.EONT, total=already)


# -- the martial tail -------------------------------------------------------


@power("f2392", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2392(c: Cast) -> None:
    """Three conditions at once -- first enemy, first round, has not yet
    acted -- and the row keeps its own book for two of them. The round
    is counted from `RoundStart` rather than assumed, because a trait
    armed at the top of the fight outlives the round it was armed in."""
    me = c.me
    acted: set[int] = set()
    round_ = [1]

    def note_round(ev: Any) -> None:
        round_[0] = ev.round

    def note_turn(ev: Any) -> None:
        if not ev.ghost:
            acted.add(ev.actor)

    c.watch(RoundStart, note_round, on=me, until=When.ENCOUNTER)
    c.watch(TurnStart, note_turn, on=me, until=When.ENCOUNTER)

    def opener(ev: Any) -> None:
        if ev.attacker != me or round_[0] != 1 or ev.target in acted:
            return
        c.damage("1d6", on=ev.target)

    c.watch(Hit, opener, on=me, until=When.ENCOUNTER, once=True)


@power("f2394", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2394(c: Cast) -> None:
    """An armour check penalty on skill checks, which is not a fight."""


@power("f2395", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2395(c: Cast) -> None:
    """Same as f2394, for the other half of the skill list."""


@power("f2397", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       obsolete="a charge may now end anywhere its attack reaches")
def f2397(c: Cast) -> None:
    """Superseded, not unfinished. It let a charge stop closer than it had to,
    and the rule it worked around is gone: a charge may end at the reach of
    whatever it swings rather than adjacent, which `actions._charges` now does.

    Was `todo=("c.charge_at(stop=)",)`, which is the wrong marker for this --
    `scripts/todo.py` would have reported the row ready the day that verb
    arrived, for a row nobody will ever want. Camille's call."""


@power("f2403", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2403(c: Cast) -> None:
    """Mace is one of the ten groups, and "melee basic attack" is asked
    of the damage context's `power` against `Powers.basic` -- which is
    the creature's own row, not always the engine's `mba`."""
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("power") in _basic_refs(c, ranged=False)
            and _group_in(c, "mace")
        ),
    )


@power("f2410", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2410(c: Cast) -> None:
    """"Undamaged" is `c.wounded` read the other way round: it is true of
    anything that has lost a single hit point."""
    me = c.me
    c.bonus(
        "damage", c.wis_mod, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("power") in _basic_refs(c)
            and ctx.get("target") is not None
            and not c.wounded(on=ctx["target"])
        ),
    )


@power("f2418", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2418(c: Cast) -> None:
    """The size of the bonus is counted when the blow lands, which
    `c.bonus` cannot take -- so it is eight +1s with eight kinds, each
    gated on the count reaching its own step. Eight is every square
    around a medium creature.

    Both contexts carry `opportunity`, which is the one gate the damage
    side is rich enough for.
    """
    me = c.me

    def flankers(ctx: dict[str, Any]) -> int:
        foe = ctx.get("target")
        if foe is None or not ctx.get("opportunity"):
            return 0
        return sum(
            1 for a in allies(c.world, me)
            if a != me and c.adjacent_to(foe, a)
        )

    _scaled(c, "attack", flankers)
    _scaled(c, "damage", flankers)


@power("f2452", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit with a charge",
       on=Trigger(Hit, both(_i_crit, by_charge),
                  "you crit with a charge attack"))
def f2452(c: Cast) -> None:
    """`by_charge` reads `ev.charge`, which `resolve.attack` sets on the
    `Hit` as a plain attribute after the event class was declared."""
    foe = c.trigger.target
    c.push(1, on=foe)
    c.prone(on=foe)


@power("f2457", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, lambda w, me, ev: ev.actor == me,
                  "you use your second wind"))
def f2457(c: Cast) -> None:
    """The same trade as f2161, bought with attack rolls instead of
    concealment, and written the same way: the +2 the second wind is
    about to lay is cancelled by an equal untyped penalty on the same
    clock rather than refused, because the event is announced above the
    line that lays it."""
    me = c.me
    if not c.may("give up the second wind defence bonus", who=me):
        return
    for defence in ALL_DEFENCES:
        c.penalty(defence, 2, on=me, until=When.SONT)
    c.bonus("attack", 2, on=me, until=When.EONT)


@power("f2458", level=1, cls="", usage=ENCOUNTER,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL, target=SELF,
       trigger="you are damaged by an attack",
       on=Trigger(DamageRolled, lambda w, me, ev: (
           ev.target == me and ev.source != me and ev.amount > 0
       ), "you are damaged by an attack"))
def f2458(c: Cast) -> None:
    """The feat changes what *action* a second wind costs, and the only
    way to say that is to declare the interrupt and take one.
    `DamageRolled` is the `Decision` the blow passes through, so the
    +2 to defences is standing before the damage lands, which is the
    whole point of the printed line."""
    c.second_wind(on=c.me)


@power("f2454", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2454(c: Cast) -> None:
    """Martial practices are rituals by another name: not a fight."""


# -- the area-attack riders -------------------------------------------------


@power("f2150", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit only one of two or more targets",
       on=Trigger(PowerResolved, lambda w, me, ev: (
           ev.actor == me and _reach_kind(ev.power) in _CLOSE_OR_AREA
           and len(ev.targets) >= 2
           and sum(1 for r in ev.rolls if r.hit) == 1
       ), "you hit only one creature with a close or area power"))
def f2150(c: Cast) -> None:
    """`PowerResolved` is the only event that can answer this: it carries
    every roll the use made, and `AttackResult.target` names who each one
    finally landed on. `PowerUsed` is announced before a die is thrown
    and `Hit` sees one victim at a time."""
    for roll in c.trigger.rolls:
        if roll.hit and roll.target:
            c.damage("1d6", on=roll.target)
            return


# -- the familiar tail ------------------------------------------------------


@power("f2256", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.familiar_state()",))
def f2256(c: Cast) -> None:
    """Rides on the familiar changing mode. `c.familiar_mode` sets one
    and announces nothing, so there is no moment to ride."""


@power("f2257", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.familiar_state()",))
def f2257(c: Cast) -> None:
    """Holds a destroyed familiar in its active state for a turn. Same
    gap as f2256, from the other end -- nothing says it was destroyed
    and nothing holds a mode past it."""


@power("f2258", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.familiar_state()",))
def f2258(c: Cast) -> None:
    """Cheapens the action that switches a familiar's mode.
    `c.grant_action` understands `shift` and `stand` and silently eats
    anything else, so writing it that way would look finished."""


# -- riders on a racial power named only in prose ---------------------------


@power("f2096", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.no_provoke(once=)",))
def f2096(c: Cast) -> None:
    """Laid at the top of each of the caster's turns while bloodied, and
    held to the end of it. "The **first** time you leave a square" is the
    dropped half: `c.no_provoke` holds for a duration and cannot be spent
    on one step, so this covers the whole turn's movement."""
    me = c.me

    def each_turn(ev: Any) -> None:
        if ev.actor == me and not ev.ghost and c.bloodied(on=me):
            c.no_provoke(on=me, until=When.EOT)

    c.watch(TurnStart, each_turn, on=me, until=When.ENCOUNTER)


@power("f2097", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="the first time each encounter you use p1452",
       on=Trigger(PowerUsed, _used("p1452"), "you use that racial power"))
def f2097(c: Cast) -> None:
    """"If the attack still hits you" is the *reroll's* outcome, and
    `PowerUsed` is announced above the body -- so at this moment the
    second roll has not been made. The row therefore arms a one-shot
    watch for the blow that follows and hands the use back only if one
    lands. `once=True` means "fire once and do something", so a miss
    does not spend it.

    `ENCOUNTER` here is the card's own "the first time ... in an
    encounter", not the default this directory otherwise avoids.
    """
    me = c.me

    def struck(ev: Any) -> None:
        if ev.target == me:
            c.restore_use("p1452", on=me)

    c.watch(Hit, struck, on=me, until=When.EOT, once=True)


@power("f2099", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("Weapon.brutal", "c.weapon_range()"))
def f2099(c: Cast) -> None:
    """Both halves are about one named weapon. Bow is a group and
    shortbow is not, and brutal is a weapon property nothing carries."""


@power("f2101", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2101(c: Cast) -> None:
    """Two rituals and a Nature bonus."""


@power("f2102", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1452 and the enemy rerolling is larger than you",
       on=Trigger(PowerResolved, _resolved("p1452"),
                  "you use that racial power"))
def f2102(c: Cast) -> None:
    """"After the attack is completed" is what picks `PowerResolved`
    over `PowerUsed`: the reroll is the whole point of the card and
    `PowerUsed` is announced before the body runs.

    `Size` is a `StrEnum` and carries no order of its own, so the
    printed ladder is spelled out in `_SIZES` and compared by index.
    """
    mine = _size_rank(c, c.me)
    for foe in c.trigger.targets:
        if _size_rank(c, foe) > mine:
            c.shift(max(1, c.speed_of() // 2))
            return


@power("f2408", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit an enemy with a martial power",
       on=Trigger(Hit, lambda w, me, ev: (
           ev.attacker == me and Keyword.MARTIAL in _keywords(ev.power)
       ), "you hit an enemy with a martial power"))
def f2408(c: Cast) -> None:
    """"Damage as if you had hit with p1448" **is** `c.as_though_hit_by`,
    which runs the named row's body against one creature with its attack
    forced to land -- so the amount and the type both come off p1448's
    own line, including the element `c.element` records. The earlier
    reading, that this wanted a damage expression nothing could borrow,
    was written before that verb existed.

    `by=c.me` rather than letting `c.knows` search the board: the price
    is the caster's own racial use, so the caster is the owner, and a
    bare search would find any dragonborn standing nearby.
    """
    foe = c.trigger.target
    if foe is None or not c.expend_row("p1448", on=c.me):
        return
    c.as_though_hit_by("p1448", on=foe, by=c.me)


@power("f2442", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RACE_OPTION)
def f2442(c: Cast) -> None:
    """Re-aimed: the trait is `rt:r6-t3` and it is declared. The
    card it hands over is a 1st-level at-will borrowed from another
    class, chosen when the character is built, and nothing records the
    choice -- so there is no ref to hand a second use to."""


@power("f2450", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1452",
       on=Trigger(PowerUsed, _used("p1452"), "you use that racial power"),
       dropped=("c.uncrit()",))
def f2450(c: Cast) -> None:
    """Nothing announces that a roll is a second one, but nothing has to:
    `PowerUsed` is announced *above* the body, so at this moment p1452's
    reroll has not been made and a one-shot penalty laid here is
    standing for it and for nothing else. `PowerUsed.trigger` is the
    blow that provoked the racial power, and it is the only thing that
    names the attacker -- the row itself is `SELF`.

    The one-shot is spent on the next attack roll that attacker makes,
    which is the reroll. Denying the critical is the dropped half.
    """
    blow = getattr(c.trigger, "trigger", None)
    foe = getattr(blow, "attacker", None)
    if foe is None:
        return
    c.penalty("attack", 5, on=foe, until=When.EOT, once=True)


@power("f2244", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2244(c: Cast) -> None:
    """`p2473` is the racial power and it is declared; `c.zone` labels a
    zone with the ref of the row that laid it when nothing else is
    given, so "your cloud" is the caster's zone labelled `p2473` and
    `c.my_zones` can now tell it from the rest.

    A standing damage modifier rather than a trigger: the zone comes and
    goes and the gate is asked afresh on every blow. The 11th and 21st
    level steps are out of scope, and no type word is printed in front
    of the bonus, so it is untyped.
    """
    me = c.me

    def in_the_cloud(ctx: dict[str, Any]) -> bool:
        from combat_engine.engine.zones import Zone

        who = ctx.get("target")
        if who is None:
            return False
        for zid in c.my_zones():
            held = c.world.get(zid, Zone)
            if held is not None and held.label == "p2473" and who in c.in_squares(
                held.squares
            ):
                return True
        return False

    c.bonus("damage", 4, on=me, until=When.ENCOUNTER, kind="feat",
            when=in_the_cloud)


@power("f2175", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you take damage of the type your p1448 deals",
       on=Trigger(DamageApplied, lambda w, me, ev: (
           ev.target == me and ev.amount > 0
       ), "you take damage"),
       dropped=("cf:sorcerer-f0s1",))
def f2175(c: Cast) -> None:
    """The second half plays. p1448's type is `c.element`, which is where
    the racial choice is recorded and what p1448's own body rolls with,
    and "the type you have resistance to" is asked of `c.resistances`
    rather than of the one feature the card names -- `cf:sorcerer-f0s1`
    has no row, so naming it would make the row inert, while the
    question the card is really asking is answerable off the character.

    `DamageApplied` is after resistance, which is the printed "after the
    damage dealt is reduced by your resistance". The keyword half --
    calling the racial power arcane -- is the standing gap.
    """
    me = c.me
    mine = c.element(on=me)
    if mine is None or c.resistances(on=me).get(mine, 0) <= 0:
        return
    if c.trigger.dtype is not mine:
        return
    c.restore_use("p1448", on=me)
    # "Considered an arcane attack power": a keyword this invoker's copy
    # of the row carries, which `dsl.keywords_of` merges with the header.
    c.counts_as_keyword("p1448", Keyword.ARCANE)
@power("f2179", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.deals(ref=)",))
def f2179(c: Cast) -> None:
    """Changes the damage type of one named power. `c.deals` overrides
    what a creature's *weapon* attacks roll and has no way to name a
    row, which would make this touch everything the character does."""


@power("f2202", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.recast(reach=)",))
def f2202(c: Cast) -> None:
    """Narrows a blast and pays for it in damage. Reach is header data
    the action menu reads before anything runs, and nothing rewrites
    one."""


@power("f2206", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2206(c: Cast) -> None:
    """Rolls `p1448` off a chosen ability from now on.

    The card names the row outright, so there is nothing to resolve. The
    *ability* is "choose one" and is settled once when the feat is taken,
    which nothing records -- so it takes the best modifier on the sheet,
    the same answer a player writes down and the same reading `f1103b`
    gives its three-way choice.

    Attack and damage both, which is one call: `c.attack_mod` resolves
    through `Attack.ability_for`, so a damage line that says "your
    attacking ability modifier" follows the swap without being told.
    """
    best = max(Ability, key=c.stats.mod)
    c.rolls_with("p1448", best, on=c.me, until=When.ENCOUNTER)


@power("f2203", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you reduce an enemy to 0 hit points",
       on=Trigger(Dropped, lambda w, me, ev: (
           ev.source == me and ev.actor != me
       ), "you drop an enemy"))
def f2203(c: Cast) -> None:
    """`ENCOUNTER` is the card's own "once per encounter", so spending the
    use on the first firing is the printed limit. `Dropped` carries
    `source` and no `target`, which is the field this needs."""
    if c.may("spend a healing surge", who=c.me):
        c.surge(on=c.me)


# -- build-time, and the rows that are not a fight --------------------------


@power("f1217", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=BORROW)
def f1217(c: Cast) -> None:
    """Another class's feature hands over a power of the taker's choice.

    Re-aimed. The `cf:` ref is declared now and so are its three
    options, so the borrowing is no longer the hold -- `c.grant_row`
    hands a feature over and `c.borrow_row` picks one out of a list.
    The hold is one step further in: each option gates itself on a leg
    of its own class, `cf:swordmage-f1s0` with a `requires=on_leg(...)`
    in the header and the other two inside the body, so a character who
    took this feat is handed a row that refuses itself. Nothing puts a
    character on another class's leg."""


@power("f1351", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.alignment()", "Mods.applied()"))
def f1351(c: Cast) -> None:
    """Adds whatever a named power put on an attack roll to the damage
    roll too, and only against an evil immortal. Alignment is not a thing
    a creature carries, and nothing reads back how much a modifier
    contributed to a roll that is already made."""


@power("f1352", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you regain hit points after dropping",
       on=Trigger(Healed, lambda w, me, ev: (
           ev.target == me and ev.amount > 0 and ev.hp == 0
       ), "you regain hit points while down"))
def f1352(c: Cast) -> None:
    """The moment is on `Healed` after all. `resolve.heal` floors a
    negative total at 0 and calls `_revive` *before* it announces, so a
    `Healed` carrying `hp == 0` is exactly "you were at or below 0 and
    are coming back" and nothing else reaches that reading.

    Standing costs nothing to say: `_revive` has already taken off the
    prone the drop imposed, so what is left of the printed line is the
    shift.
    """
    c.shift(1, who=c.me)


@power("f2149", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.chosen_weapon_group()",))
def f2149(c: Cast) -> None:
    """Widens two other feats from the weapon group each was taken for to
    every group. Both are refs, and what is missing is the *choice* each
    of them recorded -- a feat's arguments are not stored anywhere.
    Re-aimed onto the symbol f233 itself is blocked on, since f233 is
    half of this row's own gate and the two want the same thing."""


@power("f2241", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("chargen.skill_training()",),
       proficiency=("w:ki-focus",))
def f2241(c: Cast) -> None:
    """The power is a ref, so the middle clause is the one that plays.
    Skill training and what a character may wield are both settled when
    it is built."""
    c.grant_row("p9401", on=c.me, until=When.ENCOUNTER)


@power("f2246", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2246(c: Cast) -> None:
    """Climbing walls and an Acrobatics bonus."""


@power("f2290", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2290(c: Cast) -> None:
    """Drawing and stowing small objects, and Thievery with your hands
    full. The feat says outright that it grants no attack."""


@power("f2301", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       proficiency=("w3637", "w3639", "w3597", "w3602",
                    "w3609", "w3633"))
def f2301(c: Cast) -> None:
    """Six named weapons rather than a group, and the weapon table carries
    all six by ref -- so the bonus is gated exactly. Gating on heavy blade
    would have handed it to every longsword as well, a number quietly too
    generous in every fight. Heroic tier, so +2."""
    c.bonus(
        "damage", 2, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: _ref_in(
            c, "w3637", "w3639", "w3597", "w3602",
            "w3609", "w3633",
        ),
    )


@power("f2420", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       proficiency=("w3607", "w3608"))
def f2420(c: Cast) -> None:
    """Hammer and pick are printed groups the weapon table carries and
    `chargen` now deals, so the gate is asked. Heroic tier, so +2."""
    c.bonus(
        "damage", 2, on=c.me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: _group_in(c, "hammer", "pick"),
    )


@power("f2441", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.retrain_on_rest()",))
def f2441(c: Cast) -> None:
    """Not the one-way trade `chargen.power_swap` applies: this one
    exchanges two powers the character already knows, back and forth,
    once per extended rest. Nothing models a rest as a moment at which
    a hand is re-dealt."""


@power("f2443", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.retrain_on_rest()",))
def f2443(c: Cast) -> None:
    """Same as f2441 for a utility power."""


@power("f2445", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.retrain_on_rest()",))
def f2445(c: Cast) -> None:
    """Same as f2441 for an at-will."""


@power("f2446", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.retrain_on_rest()",))
def f2446(c: Cast) -> None:
    """Same as f2441 for an encounter power."""


@power("f2444", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.aid_another()",))
def f2444(c: Cast) -> None:
    """Rewrites what the aid attack action grants. Aiding is not an
    action this engine offers, so there is nothing to rewrite."""


@power("f2455", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2455(c: Cast) -> None:
    """Dexterity instead of Strength on a thrown ranged basic attack.

    Laid as a **conditional** swap rather than decided here: a trait arms
    once at the start of a fight and what is in hand changes during one,
    so a swap settled now would be wrong the moment the thrower drew a
    bow. `when` is asked at each roll instead.

    This row is only worth anything because `basic.RANGED` now tells the
    weapons apart -- a bow or a light thrown weapon is Dexterity, a
    **heavy thrown** one is Strength. While it rolled Dexterity for
    everything, the engine already granted what this feat grants and the
    row was a no-op that looked finished.

    "With which you have proficiency" is not gated. Nothing models a
    character's weapon proficiencies, and `chargen` only deals a build
    weapons it is proficient with -- so holding it *is* the proficiency
    here. A gate on `Weapon.proficiency` would have read the bonus, which
    is 2 on everything and true always.
    """
    c.rolls_with(_rba(c), Ability.DEX, on=c.me, until=When.ENCOUNTER,
                 when=_throwing)


@power("f2896", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2896(c: Cast) -> None:
    """The same shape as f2455: a bow, and Wisdom in place of Dexterity."""
    c.rolls_with(_rba(c), Ability.WIS, on=c.me, until=When.ENCOUNTER,
                 when=_drawing_a_bow)


@power("f2889", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("SkillCheck.target",))
def f2889(c: Cast) -> None:
    """Widens who benefits from a Bluff that wins combat advantage.
    `SkillCheck` never says who a check was aimed at, so "the enemy" has
    no referent."""


@power("f2893", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("compendium.silvered",))
def f2893(c: Cast) -> None:
    """Counts attacks as silvered against one creature. Silver is a
    material nothing on a weapon or a blow carries."""


@power("f2894", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       proficiency=("w3630",))
def f2894(c: Cast) -> None:
    """All three clauses. The weapon table keys on the ref, so the bonus
    is narrowed to the shortbow rather than widened to the bow group --
    which would have paid a longbow as well. Heroic tier, so +1."""
    me = c.me
    holding = lambda ctx: _ref_in(c, "w3630")  # noqa: E731
    if _ref_in(c, "w3630"):
        c.as_implement(on=me)
    c.bonus("damage", 1, on=me, until=When.ENCOUNTER, kind="feat",
            when=holding)


@power("f2897", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2897(c: Cast) -> None:
    """Cold and radiant are both `Keyword` members as well as damage
    types, and the damage context carries the row that is rolling -- so
    "with cold powers and radiant powers" is exact."""
    me = c.me
    wanted = (Keyword.COLD, Keyword.RADIANT)
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: any(
            k in _keywords(ctx.get("power", "")) for k in wanted
        ),
    )


@power("f2898", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2898(c: Cast) -> None:
    """Nothing announces a pact boon, but the condition behind this one
    is readable: `cf:warlock-f1` pays the fey leg out of a `Dropped`
    watch on a cursed enemy, so this arms the same question rather than
    waiting for a word that is never said.

    `Window.BEFORE`, because that boon's own watch teleports the warlock
    away and the square this row is about is the one being left -- by
    the default window it has already gone. `query.spread` of the
    caster's own squares is "the square you leave and each square
    adjacent to it".

    Lightly obscured is carried as the zone's cover: `c.cover_in` is the
    one way a patch of ground shelters what stands in it, and
    `resolve.attack` takes the larger of cover and concealment, so the
    -2 a blow meets is the printed one either way.
    """
    me = c.me
    if not c.build("fey"):
        return

    def boon(ev: Any) -> None:
        if ev.actor == me or team(c.world, ev.actor) == team(c.world, me):
            return
        if not c.cursed(on=ev.actor):
            return
        here = squares(c.world, me)
        if not here:
            return
        c.cover_in(c.zone(spread(here, 1), until=When.SONT), side="any")

    c.watch(Dropped, boon, on=me, until=When.ENCOUNTER, window=Window.BEFORE)


@power("f2900", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2900(c: Cast) -> None:
    """A language, a skill bonus and a disguise check. No fight in it."""
