"""Barbarian feats, the second batch.

`barbarian.py` holds the first and names the gap this list is mostly
made of: **`Keyword.RAGE` does not exist**, so "while raging" is not a
state anything can ask about. Six rows here want it and name it
exactly, which is `docs/blocked.json`'s `cf:barbarian-rage` and the
four rows already waiting on the same symbol.

Three of the class features these ride on arrive as prose rather than
as refs, and two more want a weapon to be treated as something it is
not -- an off-hand blade or a chair leg thrown like a handaxe, which
is `c.make_thrown()` and `c.weapon_range()`.

What is left is four rows that turn on things the board already
announces: a mark laid on **you**, the burst of a ref'd feature, the
fear keyword, and the reach of the weapon in hand.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Bloodied,
    Cast,
    DamageApplied,
    DamageType,
    Hit,
    Keyword,
    PowerUsed,
    Trigger,
    When,
    power,
)
from combat_engine.engine.components import Health
from combat_engine.engine.dsl import get
from combat_engine.engine.events import PowerResolved
from combat_engine.engine.query import distance_between, team


def _took_the_charge(world, me: int, ev: object) -> bool:  # noqa: ANN001
    return ev.actor == me and ev.power == "p4809"

#: Rage is not a state anything holds: the class's daily attack rows
#: carry no keyword declaring it. `cf:barbarian-rage` waits on the same.
RAGE = ("Keyword.RAGE",)
#: A class feature named in prose with no ref.
FEATURE = ("c.class_feature()",)
#: "Use it as a heavy thrown weapon, normal range 5 and long range 10":
#: a change to what the weapon *is*, which nothing in `Gear` rewrites.
THROWN = ("c.make_thrown()", "c.weapon_range()")
#: "Instead of": a printed swap for something a class feature does inside
#: its own body. The feature has a ref now; declining half of what it does
#: is the operation nothing has.
INSTEAD = ("c.pre_empt(ref, clause)",)

_DEFENCES = (AC, FORT, REF, WILL)


def _i_used(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.actor == me and ev.power == ref

    return when


def _my_fear_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and p.cls == "barbarian"
        and Keyword.FEAR in p.keywords
    )


def _i_bloodied_it(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """Damage from a barbarian attack power of mine that took a creature
    across the halfway mark.

    `Bloodied` carries `source` now, but not the row that did it, so the
    crossing is still worked out from the blow: `DamageApplied.hp` is what
    is left afterwards and `amount` is what landed, so the hit points
    before it are their sum. `detail` is the ref of the row that dealt the
    damage -- `c.damage` stamps it with the caster's own ref -- which is
    where "with a barbarian attack power" is read.
    """
    if ev.source != me or ev.target == me or ev.amount <= 0:
        return False
    p = get(ev.detail)
    if p is None or p.cls != "barbarian" or not p.is_attack:
        return False
    health = world.get(ev.target, Health)
    if health is None:
        return False
    half = health.max_hp // 2
    return ev.hp > 0 and ev.hp <= half < ev.hp + ev.amount


# -- the rows that turn on something the board announces -------------------


@power("f1879", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1879(c: Cast) -> None:
    """A plain "+2 bonus", so untyped.

    `c.marked(on=c.me, by=them)` is the question -- `c.marked(on=them)`
    would ask whether *I* have marked *it*, which is the opposite
    sentence. The mark is asked per attack because it comes and goes.
    """
    c.bonus(
        "attack", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("target") is not None
            and c.marked(on=c.me, by=ctx["target"])
        ),
    )


@power("f2204", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p4932",
       on=Trigger(PowerUsed, _i_used("p4932"), "you use p4932"))
def f2204(c: Cast) -> None:
    """Allies in that feature's burst, which is not the same set as its
    targets -- it targets enemies. So the radius is read off the row's
    own header rather than guessed, and the allies standing inside it
    are found from the board."""
    p = get("p4932")
    radius = p.reach.size if p is not None else 5
    for friend in c.within(radius, side="ally"):
        for defence in _DEFENCES:
            c.bonus(defence, 1, on=friend, until=When.EONT)


@power("f2706", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2706(c: Cast) -> None:
    """Extra damage with one named row at exactly 2 squares.

    Both halves of the gate are asked per damage roll rather than when
    the trait is armed: a weapon can be swapped and the distance is the
    whole point of the clause. The damage context carries `power` and
    `target`, which is exactly the pair this needs.

    **The row named is `cf:barbarian-f2c0`.** The spec names it `p4807`,
    which is declared nowhere: the same card is declared under the feature
    ref that prints it, so the gate was false in every fight and said
    nothing about why. `cf:barbarian-f2c0` carries its own marker, so the
    clause is still inert -- but it is inert against a row that exists and
    goes live the day that row does.
    """
    c.bonus(
        "damage", c.con_mod, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("power") == "cf:barbarian-f2c0"
            and c.wielding("two-handed")
            and c.wielding("reach")
            and ctx.get("target") is not None
            and distance_between(c.world, c.me, ctx["target"]) == 2
        ),
    )


@power("f2792", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a barbarian fear power",
       on=Trigger(Hit, _my_fear_hit,
                  "you hit with a barbarian fear power"))
def f2792(c: Cast) -> None:
    """"A barbarian fear attack power" is two header fields and no
    naming gap at all: the class and the fear keyword."""
    c.push(1, on=c.trigger.target)


@power("f2883", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you bloody an enemy with a barbarian attack power",
       on=Trigger(DamageApplied, _i_bloodied_it, "you bloody an enemy"))
def f2883(c: Cast) -> None:
    """Both halves land now.

    The clause naming the row was dropped on the reading that nothing
    says which power dealt a blow; `DamageApplied.detail` does, and the
    predicate reads it. `Bloodied` is still the wrong event to hang this
    on -- it announces the crossing and not the amount, so the halfway
    line has to be re-derived from `hp` and `amount` either way.
    """
    c.temp_hp(c.cha_mod, on=c.me)


# -- rage, which nothing declares ------------------------------------------


@power("f1831", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RAGE)
def f1831(c: Cast) -> None:
    """An attack bonus after one of two racial powers, **while
    raging**. Both powers are refs now, so `used_one_of` would declare
    the trigger -- what is left is the rage gate, and a row that paid
    out of rage as well as in it would be wrong in every fight."""


@power("f1858", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RAGE)
def f1858(c: Cast) -> None:
    """Trade a die of weapon damage for ongoing damage, on a hit with
    "any rage power". Which rows those are is the same gap: nothing
    marks a row as one."""


@power("f1991", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Keyword.RAGE", "feat.category"))
def f1991(c: Cast) -> None:
    """A damage bonus while raging that grows with how many nearby
    allies have taken a feat of a particular category. `c.feat(ref)`
    asks about one feat by ref; nothing groups feats into the families
    the prerequisite lines name."""


@power("f2296", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=RAGE)
def f2296(c: Cast) -> None:
    """A melee damage bonus while raging, paid for by damage to
    yourself on a turn that hurt nobody. The self-harm half is a
    `TurnEnd` watcher and writable on its own -- but without the rage
    gate it would bite every turn of the fight."""


@power("f2705", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("Keyword.RAGE",))
def f2705(c: Cast) -> None:
    """Reroll the damage dice that come up 1, while raging and wielding
    a two-handed reach weapon. The weapon half is `c.wielding`; the
    other two are not there. `c.reroll_damage` rolls the whole
    expression twice and keeps the higher, which is a different and
    much larger thing."""


@power("f2885", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("Keyword.RAGE",))
def f2885(c: Cast) -> None:
    """Extra hit points from a second wind taken while raging.
    `SecondWind` is the moment now; nothing says a barbarian is raging,
    which is the half still missing."""


# -- class features named in prose -----------------------------------------


@power("f1834", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p4809",
       on=Trigger(PowerUsed, _took_the_charge, "you take that free charge"))
def f1834(c: Cast) -> None:
    """The prerequisite's feature hands over `p4809`, and that row's whole
    printed effect is "you charge an enemy" -- so the charge this rides on
    is the one it is about to make.

    The swing itself is announced under the basic attack's ref, not under
    `p4809`, so the hit is matched on `charge` and narrowed by the window
    instead: the watch is laid when `p4809` is used and dies with the turn,
    and a hand-rolled latch spends it on the first charging hit rather than
    on the first hit of any kind -- `c.watch(once=True)` would be spent by
    an event that did not match.
    """
    me = c.me
    spent: list[int] = []

    def landed(ev: Hit) -> None:
        if spent or ev.attacker != me or not getattr(ev, "charge", False):
            return
        spent.append(1)
        c.push(1, on=ev.target)

    c.watch(Hit, landed, until=When.EOT, on=me, label=c.ref)


@power("f1878", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.change_distance(ref, n)",))
def f1878(c: Cast) -> None:
    """Lengthens the shift `cf:barbarian-f1s3` grants. That feature is a
    declared row now, so this is no longer a naming gap -- but the 2 is a
    literal inside its own closure and the shift is offered from there, so
    there is nothing outside it to lengthen."""


@power("f1880", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1880(c: Cast) -> None:
    """Five more thunder off the same bloodying `cf:barbarian-f1s2` answers.

    Laid as its own burn on the same event rather than reached into the
    feature: the feature's amount is a literal in its closure. That makes
    two thunder instances where the card prints one, which differs only
    against thunder resistance.

    The once-a-round latch is keyed on the world's round exactly as the
    feature keys its own, so the two fire together and never apart. The
    leg is not asked again -- `chargen.meets` has already checked the
    feature is held, and the feature checks the leg.
    """
    me = c.me
    paid: dict[int, int] = {}

    def on_bloodied(ev: Bloodied) -> None:
        victim = ev.actor
        if ev.source != me or team(c.world, victim) is team(c.world, me):
            return
        if paid.get(me) == c.world.round:
            return
        paid[me] = c.world.round
        for foe in c.within(1, side="enemy"):
            c.flat(5, dtype=DamageType.THUNDER, on=foe)

    c.watch(Bloodied, on_bloodied, until=When.ENCOUNTER, on=me, label=c.ref)


#: The class feature both rows below ride on. Its body calls `c.basic`,
#: so the swing it hands over is stamped with this ref.
RAMPAGE = "cf:barbarian-f3"


@power("f2707", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2707(c: Cast) -> None:
    """A damage bonus on the free basic attack the class feature grants,
    at exactly 2 squares.

    The grip and the reach are asked inside the gate rather than when
    the trait arms: a barbarian can change hands, and the gate is read
    at the moment the damage is rolled. "2 squares away" is exactly 2 --
    the printed line is about a reach weapon's outer square, not about
    anything at 2 or more.
    """
    def far_enough(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return (
            ctx.get("granted_via") == RAMPAGE
            and ctx.get("granted_by") == c.me
            and c.wielding("two-handed")
            and c.wielding("reach")
            and foe is not None
            and distance_between(c.world, c.me, foe) == 2
        )

    c.bonus("damage", 2, on=c.me, until=When.ENCOUNTER, when=far_enough)


@power("f2884", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("Defences.immune_keywords",))
def f2884(c: Cast) -> None:
    """An attack penalty on whoever the class feature's free swing hits.

    Read off `PowerResolved` rather than the `Hit`: the use is what
    carries where the swing came from.

    Dropped: "a creature immune to fear is not subject to this penalty".
    `Defences` holds immunity per damage type and nothing records
    immunity to a *keyword*, so the narrowing has nothing to ask. Gating
    on it anyway would be silently false one way or the other.
    """
    def punished(ev: Any) -> None:
        if ev.actor != c.me or ev.granted_via != RAMPAGE or ev.granted_by != c.me:
            return
        for roll in ev.rolls:
            if roll.hit:
                c.penalty("attack", 2, on=roll.target, until=When.EONT)

    c.watch(PowerResolved, punished, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} rampage rider")


# -- weapons treated as something they are not -----------------------------


@power("f1841", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=THROWN)
def f1841(c: Cast) -> None:
    """Throw an off-hand blade like a handaxe, at 5/10. `Weapon` holds
    its properties and its range as data read before a row runs, and
    nothing rewrites either."""


@power("f1843", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=THROWN)
def f1843(c: Cast) -> None:
    """The same for whatever is lying about, plus a feat bonus when one
    is thrown. The bonus half cannot stand on its own either: an
    improvised weapon is not a thing `Gear` holds, so there is nothing
    for the gate to ask about."""


# -- an event nothing emits ------------------------------------------------


@power("f1992", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("events.Recharged",))
def f1992(c: Cast) -> None:
    """A damage bonus against an adjacent enemy that recharges a power.
    `actions.recharge` rolls the die and puts the row back silently --
    it emits nothing at all, so the moment this feat turns on is not
    one the bus ever mentions."""
