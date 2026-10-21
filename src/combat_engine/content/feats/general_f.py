"""General feats: the racial batch.

There is still no race, and none of that matters for the *benefit*. The
prerequisite is a column `chargen.meets` enforces at build time, and
`AUTHORING.md` says outright that a gate the engine cannot yet express
is not a reason to skip a feat. So these are written on their merits.

What decides each one is whether the racial power it rides on arrives
as a **ref** or as a **name**. `p1448`, `p1450`, `p1452`, `p1628`,
`p2473`, `p2485`, `p1831` and `p2339` are all refs in these
prerequisites, which makes a rider on one an ordinary trigger. The rest
-- infernal wrath, fade away, second chance called by name in the
benefit line rather than the gate -- are prose and carry
`c.on_racial_power()`.

Two smaller gaps come out of this batch and both are build-time rather
than in-fight. "You gain proficiency with all spears" changes what a
character may pick up, which is `chargen`'s business and not a `Cast`'s;
and "choose a new elemental manifestation" is a build choice that the
class feature does not record.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.features.racial import _holds
from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionPointSpent,
    ActionType,
    Cast,
    Condition,
    ConditionEnded,
    DamageRolled,
    DamageType,
    Hit,
    Keyword,
    PowerUsed,
    SecondWind,
    Size,
    TempHP,
    Trigger,
    When,
    ally_within,
    power,
)
from combat_engine.engine.components import Stats
from combat_engine.engine.dsl import get
from combat_engine.engine.query import allies, distance_between, enemies

#: A racial power the benefit line names in prose rather than by ref.
RACIAL = ("c.on_racial_power()",)
#: Which weapons a character may pick up is settled when it is built.
PROFICIENCY = ("chargen.proficiency()",)

_BIG = (Size.LARGE, Size.HUGE, Size.GARGANTUAN)

#: The five manifestations `f602` forks on, by the ref of the power each one
#: comes with, against the damage type the card prints for it.
#:
#: The card spells the fork as `rt:r33-s0` through `rt:r33-s4`, which are
#: sub-option refs and not rows -- but `racial_trait` carries each one's spec
#: and every spec **names its power**, which is the ref `RaceLine.granted`
#: puts in `Powers.known`. So the join is read off the compendium rather than
#: guessed, and it is the same join `RaceLine._manifestation_for` makes.
#:
#: The race prints thirteen manifestations now and this card five. A
#: character holding one of the other eight is not on this card and gets
#: nothing, which is why the five are listed here rather than taken from
#: `features/racial.py`.
_MANIFESTED_DAMAGE = {
    "p1766": DamageType.FIRE,
    "p1767": DamageType.FORCE,
    "p1769": DamageType.THUNDER,
    "p1770": DamageType.ACID,
    "p1828": DamageType.COLD,
}

#: The five the breath feat may be sworn to, in the card's own order.
_BREATH_TYPES = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.POISON,
)


def _used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _woke_up(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """The unconscious that dropping laid, ending. `ConditionEnded` names
    its subject `target`, so `about_me` is false on it forever."""
    return ev.target == me and ev.condition is Condition.UNCONSCIOUS


def _bigger_than_me(c: Cast, who: int) -> bool:
    """`Size.order`, not `>`: `Size` is a `StrEnum` and a bare
    comparison sorts the words alphabetically."""
    return c.size_of(who).order > c.size_of(c.me).order


# -- the ordinary standing bonuses ------------------------------------------


@power("f7", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f7(c: Cast) -> None:
    """Two larger enemies adjacent, counted per attack rather than at
    arming: a creature that is surrounded at the top of the round is
    not necessarily surrounded when the blow lands."""
    me = c.me
    c.bonus(
        AC, 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: sum(
            1 for f in enemies(c.world, me)
            if c.adjacent(to=f) and _bigger_than_me(c, f)
        ) >= 2,
    )


@power("f44", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f44(c: Cast) -> None:
    """Fire *or* fear, and both are real `Keyword` members -- the damage
    types are keywords on a card as well as types on a roll, which is
    why `Keyword.FIRE` exists beside `DamageType.FIRE`."""
    me = c.me
    wanted = (Keyword.FIRE, Keyword.FEAR)
    hot = lambda ctx: (  # noqa: E731
        (p := get(ctx.get("power", ""))) is not None
        and any(k in p.keywords for k in wanted)
    )
    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=hot)
    c.bonus("damage", 1, on=me, until=When.ENCOUNTER, when=hot)


@power("f47", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f47(c: Cast) -> None:
    c.bonus("save", 1, on=c.me, until=When.ENCOUNTER, kind="feat")


@power("f77", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f77(c: Cast) -> None:
    """Asked per blow, because being bloodied is a state that arrives in
    the middle of a fight and this feat is printed for exactly that."""
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(on=me),
    )


@power("f193", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f193(c: Cast) -> None:
    """"Large or larger" is a fixed floor, not a comparison with your own
    size -- unlike `f7` a line above, which says "larger than you"."""
    me = c.me
    for defence in (AC, REF):
        c.bonus(
            defence, 1, on=me, until=When.ENCOUNTER,
            when=lambda ctx: (
                ctx.get("attacker") is not None
                and c.size_of(ctx["attacker"]) in _BIG
            ),
        )


@power("f215", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you spend an action point",
       on=Trigger(ActionPointSpent, lambda w, me, ev: ev.actor == me,
                  "you spend an action point"))
def f215(c: Cast) -> None:
    """"During any action you gain" -- so the bonus stands for the rest
    of the turn rather than being spent on one roll: a point can buy an
    action that attacks more than once."""
    c.bonus("attack", 3, on=c.me, until=When.EOT)


@power("f288", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f288(c: Cast) -> None:
    """The Insight half is a check rather than a fight. The initiative
    half is real and is handed out at arming -- `Initiative.bonus` is
    read before the d20, and a trait is armed after the opening rolls,
    so `c.initiative` is what moves an ally in the order."""
    me = c.me
    for friend in allies(c.world, me):
        if friend != me and distance_between(c.world, me, friend) <= 10:
            c.initiative(1, on=friend)


@power("f446", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f446(c: Cast) -> None:
    me = c.me
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            not ctx.get("ranged", False)
            and ctx.get("target") is not None
            and any(
                a != me and c.adjacent_to(a, ctx["target"])
                for a in allies(c.world, me)
            )
        ),
    )


@power("f599", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f599(c: Cast) -> None:
    """The save bonus is narrowed to charm effects.

    When I wrote this the saving-throw context carried no `keywords`
    and the gate was silently false. It carries them now, derived from
    the row that laid the effect by `durations.keywords_of` -- so the
    narrowing is real rather than a sentence in a docstring.
    """
    me = c.me
    c.bonus(WILL, 1, on=me, until=When.ENCOUNTER, kind="feat")
    c.bonus(
        "save", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: Keyword.CHARM in ctx.get("keywords", ()),
    )


@power("f596", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f596(c: Cast) -> None:
    """Three clauses about dragons, and the shape matters.

    A row may hold either a printed trigger or a standing modifier, not
    both -- if this were declared `on=Trigger(Hit, ...)` its body would
    run only on a critical hit, and the two attack bonuses would never
    be laid at all. So it is a trait, and the crit clause is a `c.watch`
    laid from inside it. That is what `c.watch` is for.

    `c.is_kind` reads the creature's printed type, which is what "a
    dragon" means here rather than anything about its name.
    """
    me = c.me
    is_dragon = lambda who: who is not None and c.is_kind("dragon", on=who)  # noqa: E731
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: is_dragon(ctx.get("target")),
    )
    # The second point while bloodied, as its own kind so `Mods.total`
    # keeps both rather than taking the larger of one type.
    c.bonus(
        "attack", 1, on=me, until=When.ENCOUNTER, kind=f"{c.ref}:bloodied",
        when=lambda ctx: c.bloodied(on=me) and is_dragon(ctx.get("target")),
    )

    def on_crit(ev: Any) -> None:
        p = get(ev.power)
        if (
            ev.attacker == me and ev.critical and is_dragon(ev.target)
            and p is not None
            and p.reach.kind in ("melee", "close_burst", "close_blast")
        ):
            stats = c.world.get(ev.target, Stats)
            c.temp_hp(stats.level if stats is not None else 1, on=me)

    c.watch(Hit, on_crit, on=me, until=When.ENCOUNTER)


@power("f609", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you return to consciousness",
       on=Trigger(ConditionEnded, _woke_up, "you come back up"))
def f609(c: Cast) -> None:
    """Pays out on coming back up in the same fight.

    Re-read: the moment does exist. Dropping lays an effect labelled
    "dropped" carrying unconscious, prone and dying, and `resolve._revive`
    ends it -- and `Effects.end` announces a `ConditionEnded` per
    condition it was carrying. So "return to consciousness" is the
    unconscious one going away, and "in the same encounter" is implied
    by the effect having been laid this fight.

    A plain "+1 bonus" with no type word printed, so untyped.
    """
    c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER)
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER)


# -- riders on a racial power that is a ref ---------------------------------


@power("f203", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1628",
       on=Trigger(Hit, lambda w, me, ev: (
           ev.attacker == me and ev.power == "p1628"
       ), "you hit with that racial power"))
def f203(c: Cast) -> None:
    """Declared on the hit rather than on the use, because the printed
    line is "in addition to any damage you deal" -- a push handed out
    before the roll would land on a miss too."""
    c.push(1, on=c.trigger.target)


@power("f445", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2485",
       on=Trigger(PowerUsed, _used("p2485"), "you use that racial power"))
def f445(c: Cast) -> None:
    c.temp_hp(5, on=c.me)


@power("f443", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.race_components()",))
def f443(c: Cast) -> None:
    """Scales a racial power's temporary hit points by how many of a
    race's components the character carries. The power is a ref; the
    components are a racial trait nothing models, and there is no race
    on a character to carry them."""


@power("f444", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2485",
       on=Trigger(PowerUsed, _used("p2485"), "you use that racial power"))
def f444(c: Cast) -> None:
    """Widens what a racial power's saving throw may be made against,
    and adds to it.

    The widening is the power's own business -- it is the one that
    rolls the save, and this row cannot reach inside it. What this row
    *can* say is the +2, laid as a one-shot save bonus so it is spent
    on the throw the power is about to make. The widening is dropped.
    """
    c.bonus("save", 2, on=c.me, until=When.EOT, once=True, kind="feat")


@power("f471", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p2339",
       on=Trigger(PowerUsed, _used("p2339"), "you use that power"))
def f471(c: Cast) -> None:
    for who in c.trigger.targets:
        c.temp_hp(c.cha_mod, on=who)


@power("f216", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.penalty(on_attacker=)",))
def f216(c: Cast) -> None:
    """**Re-pointed. The reroll half landed in #496 and was not the hold.**

    `f217` one row down is the same sentence and is now written in three
    lines, because its +2 lands on the holder's own roll and a standing
    modifier gated on `reroll_by` reaches it. This one does not: `p1452`
    makes the creature *attacking you* roll again, and
    `resolve._mods(world, attacker, "attack", ctx)` reads the attacker's
    own `Mods`. A penalty imposed by the defender has nowhere to sit.

    Laying it on every enemy at arming is the near miss and is wrong: it
    misses anything that joins the fight later, and the hole is invisible.
    What is wanted is a penalty the defender carries and the attacker's roll
    consults -- which is a real engine gap and not this row's to invent.
    """


@power("f217", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f217(c: Cast) -> None:
    """+2 on the new attack roll `p1450` buys.

    A **standing** modifier, not a triggered one, and that is the whole
    simplification: the gate `reroll_by` only answers true while
    `c.reroll_attack` is re-summing, so a bonus laid once at arming applies
    to exactly the rolls the card names and to nothing else. No trigger, no
    arming, no window to get the ordering wrong. #496.

    `reroll_by` rather than a bare `reroll`: the card says the roll *this*
    racial power forces, so a magic weapon`s reroll must not pick it up.
    """
    c.bonus(
        # No `kind=`: the card prints no bonus type, so it is untyped.
        # `bonuses.py` reads the card and caught the invented type.
        "attack", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("reroll_by") == "p1450",
    )


@power("f287", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f287(c: Cast) -> None:
    """Widens a named racial power's blast, 3 to 5.

    Re-read: the header is data, but `dsl.area_of` asks `_stretched`
    for an extra size *before* it spreads the squares, and hands it
    `{"power": p.ref}` -- so a `"blast_size"` modifier gated on the ref
    widens exactly one row and nothing else the character throws. The
    printed "you can choose to" is not offered: a wider blast only adds
    candidates and `Target` filters them by side."""
    c.bonus("blast_size", 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("power") == "p1448")


@power("f601", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f601(c: Cast) -> None:
    """Widens two named racial powers, a burst and a range.

    Same route as f287. `_stretched` reads `"blast_size"` for a burst
    and `"range"` for a ranged line, so the two clauses are two gated
    modifiers; `area_of` stretches `r.size` before `_reach_of` is asked,
    and `_reach_of` hands a non-weapon range straight back, so the
    ranged square is counted once."""
    me = c.me
    c.bonus("blast_size", 1, on=me, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("power") == "p2473")
    c.bonus("range", 5, on=me, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("power") == "p1831")


@power("f387", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f387(c: Cast) -> None:
    """Changes what damage type one named racial power deals.

    Re-read: `c.deals` is still the wrong verb, because it rewrites every
    weapon attack the character makes. But it is not the only way to
    retype a blow. `DamageRolled` is a `Decision` whose `dtype` is
    writable and whose `detail` is the ref of the row that rolled it --
    `c.damage` passes `detail or self.ref` -- and `resolve.deal_damage`
    reads the type back off the event after both windows, so one named
    row's line can be retyped without touching anything else.

    The choice the card prints is made once, when the trait arms. Which
    type the breath already deals is a racial choice nothing records, so
    all five printed options are offered.
    """
    me = c.me
    kind = c.choose(list(_BREATH_TYPES), "which damage type for p1448")
    if kind is None:
        return

    def retype(ev: DamageRolled) -> None:
        if ev.source == me and ev.detail == "p1448":
            ev.dtype = kind

    c.watch(DamageRolled, retype, until=When.ENCOUNTER, on=me, label=c.ref)


@power("f602", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f602(c: Cast) -> None:
    """A typed +3 on every melee basic attack `p3322` grants.

    **Written, and the half this waited on was never missing.** The old
    note said the manifestation was "recorded nowhere" and that
    `rt:r33-t0` carried a marker saying so. That row carries no marker:
    it forks thirteen ways on which of the thirteen *powers*
    `RaceLine.granted` put in `Powers.known`, because the whole of the
    choice is which power comes with it. `_MANIFESTED_DAMAGE` is the same
    read, narrowed to the five legs this card prints.

    `_holds` and not `c.knows`: `c.knows` answers who **on the board**
    has a row, so it is true for a character standing next to somebody
    else's manifestation.

    The gate is `granted_via`, which is what `f603` -- the other half of
    the same printed feature -- is written against. No melee test beside
    it: `p3322` grants a melee basic attack and nothing else, so the
    provenance key is the whole of the printed clause.

    `dtype=`, because the +3 is of the manifestation's type where the
    weapon's own damage is not, so those three points meet a resistance
    on their own terms.

    Not written, and not a gap: "if you are currently manifesting more
    than one element, choose one damage type when making the attack". A
    second manifestation is `f604`, which is marked, and `granted` deals
    exactly one -- so there is never a second type to choose between."""
    manifested = next(
        (ref for ref in _MANIFESTED_DAMAGE if _holds(c, ref)), ""
    )
    if not manifested:
        return
    c.bonus(
        "damage", 3, dtype=_MANIFESTED_DAMAGE[manifested], on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("granted_via") == "p3322",
    )


@power("f604", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("chargen.race_choice()",))
def f604(c: Cast) -> None:
    """Learns a second elemental manifestation and lets a rest switch
    between them. The manifestation is a racial choice, and there is no
    race on a character to hold one."""


# -- the bard's virtues -----------------------------------------------------
#
# The prerequisites name `cf:bard-f1s0` and `cf:bard-f1s2` by ref, and
# neither is a row: `cf:bard-f1` writes both of those virtues *inline*,
# forking on the derived `second-int` and `second-con` legs, and only the
# third virtue got a row of its own (`cf:bard-f1s1`). So the feature is
# reachable as a name and not as a moment.


@power("f469", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_feature_power()",))
def f469(c: Cast) -> None:
    """Rides on the virtue that slides an ally. That slide is one
    `c.slide` among many inside `cf:bard-f1`'s `Miss` handler, and
    `Forced` names who moved and not which row moved them, so there is
    no moment to answer."""


@power("f470", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("cf:bard-f1s2",))
def f470(c: Cast) -> None:
    """Rides on the virtue that grants temporary hit points.

    **Written, and the gate names the holder on purpose.** The old note
    here said gating on `cf:bard-f1` "would catch every virtue it writes",
    and that is the half that is wrong: `features/leaders_sb.py`'s
    `bard_virtue` returns at the end of its `f1s0` leg and returns again
    unless `c.build("f1s2")`, so the row's *only* `c.temp_hp` sits inside
    the `f1s2` branch. A `TempHP` carrying `power == "cf:bard-f1"` is
    therefore this option paying, exactly rather than merely nearly --
    `f1009` banked the same argument on `cf:barbarian-f1`, and it stops
    being exact the day the feature pays a pool on a second leg.

    `ev.source` is checked because the card says "when **you** grant": a
    second bard's virtue paying an ally is not this feat, and `c.watch`'s
    `on=` is ownership rather than a filter.

    `When.EOTNT` and not `EONT`: the card carries a revision replacing
    "your next turn" with "his or her next turn", so the clock is the
    ally's. `once=True` is "the next damage roll". Untyped, because the
    card prints no word in front of the bonus.

    **Dropped: the feat still cannot be dealt**, and that is not a clause
    here. Its printed prerequisite is `{"ref": "cf:bard-f1s2"}`, which
    `chargen.meets` answers against the dealt list, and no row declares
    the sub-option -- #416's inline-leg gap, whose comments refuse
    declaring the legs because it would put the same card in a menu twice.
    `dropped=` rather than `todo=` for `f1009`'s reason: the row plays if
    it is ever held, and `legal_feats` refuses a `todo=` row outright.
    """

    def paid(ev: TempHP) -> None:
        if ev.source != c.me or ev.power != "cf:bard-f1" or ev.target == c.me:
            return
        c.bonus("damage", 2, on=ev.target, until=When.EOTNT, once=True)

    c.watch(TempHP, paid, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power("f472", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an ally within 10 squares of you uses second wind",
       on=Trigger(SecondWind, ally_within(10),
                  "an ally within 10 squares takes a second wind"))
def f472(c: Cast) -> None:
    """The temporary hit points go to the ally who was winded, whom the
    event names -- `c.temp_hp` would otherwise follow `c.target`, which on
    a PERSONAL row is you."""
    c.temp_hp(c.cha_mod, on=c.trigger.actor)


# -- proficiency, which is settled when the character is built --------------


@power("f64", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, proficiency=("w3598",))
def f64(c: Cast) -> None:
    """Both halves now. The grant is header data `chargen` reads when the
    character is built, and one ref stands for the whole printed group
    the way the chassis deals one weapon per proficiency line.
    """
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER, kind="feat",
        # "spear" is a group; the card's other half is *longswords*, a
        # weapon rather than the whole heavy blade group. Widened here
        # rather than narrowed, and said so, because `chargen` hands out
        # exactly one heavy blade and it is the longsword.
        when=lambda ctx: _wielding_group(c, "spear", "heavy blade"),
    )


@power("f69", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       proficiency=("w3603", "w3607"))
def f69(c: Cast) -> None:
    """Same shape as f64, for axes and hammers.

    Hammer *is* a printed group and the weapon table carries it; what
    the engine had was no hammer to hand anybody, so the arm of the gate
    reading it was false in every fight. The grant is what makes it
    true, and both halves of the card are written.
    """
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER, kind="feat",
        when=lambda ctx: _wielding_group(c, "axe", "hammer"),
    )


def _wielding_group(c: Cast, *groups: str) -> bool:
    from combat_engine.engine.components import Gear

    gear = c.world.get(c.me, Gear)
    return gear is not None and any(w.group in groups for w in gear.melee)


# -- not a fight ------------------------------------------------------------


@power("f60", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f60(c: Cast) -> None:
    """Overland travel, tracks, and two skill bonuses. None of it is a
    fight."""


@power("f607", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f607(c: Cast) -> None:
    """A shared Perception check with a chosen ally. A check, not a
    fight."""
