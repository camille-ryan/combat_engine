"""Sorcerer feats, the second batch.

Six of these read a class feature, and the difference between the ones
that are written and the ones that carry a marker is whether the feature
has a ref. The **soul** does -- `cf:sorcerer-f0`, in
`content/powers/sorcerer/souls.py` -- and it keeps which type it is sworn
to in a marker effect, so `soul_of` and `soul_resist` answer "your Spell
Source resistance" directly and four rows here turn on that. The cosmic
cycle and the temporary-hit-point feature do not, and those carry
`c.class_feature()` like the fifteen rows elsewhere that want the same
thing.

The other recurring shape is **parity**: three cards ask the player to
call even or odd before a roll and pay out when the call lands. One of the
three is an attack roll, which `AttackRolled.natural` announces before the
damage is rolled, so it is writable; the other two are an initiative check
and a class feature's own d10, and neither moment is announced at all.

`usage=AT_WILL` throughout -- none of these prints a once-per-encounter
limit, and a triggered row is asked `usable` every time it is offered.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.powers.sorcerer.souls import (
    soul_damage,
    soul_of,
    soul_resist,
    wear_soul,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    FORT,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Cast,
    DamageType,
    Forced,
    Gear,
    Keyword,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import AttackRolled, Bloodied, ForcedMove, Hit
from combat_engine.engine.types import Usage

#: The cosmic cycle and the Guild-Training-shaped features arrive as
#: printed prose with no ref, which is the gap fifteen rows already name.
FEATURE = ("c.class_feature()",)


def _storm(ctx: dict[str, Any]) -> bool:
    """An arcane power carrying either of the two printed keywords."""
    p = get(str(ctx.get("power") or ""))
    return (
        p is not None
        and Keyword.ARCANE in p.keywords
        and (Keyword.LIGHTNING in p.keywords or Keyword.THUNDER in p.keywords)
    )


def _my_sorcerer_slide(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.source == me
        and ev.how is Forced.SLIDE
        and p is not None
        and p.cls == "sorcerer"
    )


def _my_daily_roll(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and p.cls == "sorcerer"
        and p.usage is Usage.DAILY
    )


#: One call per daily power per round, keyed by caster. "For one attack
#: roll" is the printed scope and a burst rolls once per target, so
#: without this the choice would be offered -- and paid -- on every one.
_CALLED: dict[int, tuple[str, int]] = {}


# -- the soul, which has a ref and can therefore be read --------------------


@power("f1167", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1167(c: Cast) -> None:
    """An aura rather than a loop over whoever is adjacent right now:
    "each ally adjacent to you" follows the sorcerer around the board, and
    `c.resist_in` is the one verb that carries resistance into a zone --
    `c.grants_in` cannot, because resistance lives on `Defences` and a
    modifier named "resist" is read by nothing.

    Which type, and how much, are both the feature's own answers.
    """
    kind = soul_of(c)
    if kind is None:
        return
    c.resist_in(c.aura(1), soul_resist(c.level), kind, side="ally")


@power("f3430", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f3430(c: Cast) -> None:
    """Added rather than relaid: `c.resist` sums into `Defences.resist`
    for the type, so 2 on top of whatever the soul already laid is the
    printed increase and does not have to know what that was."""
    gear = c.world.get(c.me, Gear)
    kind = soul_of(c)
    if kind is None or gear is None or gear.armour != "leather":
        return
    c.resist(2, kind, on=c.me, until=When.ENCOUNTER)


@power("f1233", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1233(c: Cast) -> None:
    """"Instead of rolling" is sayable because the roll has already
    happened: traits arm in the order the creature knows its rows and the
    class feature comes before the feats, so `wear_soul` finds a sworn
    type to end. It ends the marker and the resistance together, which is
    why the swap is one call rather than a search.

    Gated on the build, because the other leg does not roll at all.
    """
    if not c.build("wild"):
        return
    kind = c.choose(
        [DamageType.COLD, DamageType.NECROTIC], f"{c.ref}: which resistance"
    )
    if kind is not None:
        wear_soul(c, kind)


@power("f2045", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2045(c: Cast) -> None:
    """The amount and the type are both writable now.

    The damage the card hands `f2023b` is the wild leg's own clause --
    `soul_damage` over the ability that leg keys off -- and a feat's
    granted card is an ordinary ref, so gating a damage modifier on it is
    the whole of the first half.

    "The same type as your current Wild Soul damage type" is the build's
    own element and `c.element` is the reader for it. A build that
    recorded none leaves the rider untyped, which is where it was.
    """
    if not c.build("wild"):
        return
    c.bonus(
        "damage", c.dex_mod + soul_damage(c.level), on=c.me,
        until=When.ENCOUNTER, dtype=c.element(),
        when=lambda ctx: ctx.get("power") == "f2023b",
    )


# -- standing modifiers -----------------------------------------------------


@power("f1159", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1159(c: Cast) -> None:
    """A trait with a watch rather than a declared trigger: the skill
    bonus is a standing modifier, and a row declaring `on=` runs only when
    the trigger fires, so a modifier laid in it is never laid at all.

    Combat advantage is why the damage half cannot be a gated modifier.
    The damage context carries `target`, `power`, `dtype`, `opportunity`,
    `charge` and `crit` and **no `advantage`**, and asking
    `has_combat_advantage` again at damage time is too late -- a one-shot
    grant has already been spent. `Hit` carries the live `AttackResult`,
    so the bonus is laid from there, for that blow and that enemy only,
    and is read by the `c.damage` the power's own body goes on to call.
    """
    me = c.me
    step = 2 + 2 * (c.level >= 11) + 2 * (c.level >= 21)
    c.bonus("skill:stealth", 1, kind="feat", on=me, until=When.ENCOUNTER)

    def on_hit(ev: Hit) -> None:
        p = get(ev.power)
        if (
            ev.attacker != me
            or p is None
            or p.cls != "sorcerer"
            or not (Keyword.POISON in p.keywords or Keyword.PSYCHIC in p.keywords)
            or not getattr(getattr(ev, "result", None), "advantage", False)
        ):
            return
        foe, ref = ev.target, ev.power
        c.bonus(
            "damage", step, kind="feat", on=me, until=When.EOT, once=True,
            when=lambda ctx: (
                ctx.get("target") == foe and ctx.get("power") == ref
            ),
        )

    c.watch(Hit, on_hit, until=When.ENCOUNTER, on=me)


@power("f1161", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1161(c: Cast) -> None:
    """+1, and +2 while bloodied, written as a +1 and a gated **+2** of
    the same kind. Two feat bonuses do not add and the larger wins, so
    the natural-looking pair -- a +1 and a gated +1 -- would come to +1
    forever and look exactly like a working rider.

    The tier ladder doubles on the bloodied leg at every step, which is
    what the printed 2/4 and 3/6 come to.
    """
    me = c.me
    step = 1 + (c.level >= 11) + (c.level >= 21)
    c.bonus("damage", step, kind="feat", on=me, until=When.ENCOUNTER, when=_storm)
    c.bonus(
        "damage", 2 * step, kind="feat", on=me, until=When.ENCOUNTER,
        when=lambda ctx: _storm(ctx) and c.bloodied(me),
    )


@power("f3431", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.trained(skill)",))
def f3431(c: Cast) -> None:
    """Both feat bonuses are ordinary `skill:` modifiers. The training is
    dropped rather than approximated as a flat +5: `engine/skills.py` says
    there is no training model at all, so nothing would read the flag and
    adding the number would make this character trained in a way no other
    character in the game can be."""
    c.bonus("skill:intimidate", 2, kind="feat", on=c.me, until=When.ENCOUNTER)
    c.bonus("skill:streetwise", 2, kind="feat", on=c.me, until=When.ENCOUNTER)


# -- declared triggers ------------------------------------------------------


@power("f1163", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1163(c: Cast) -> None:
    """"The first time you become bloodied" is latched here rather than
    with `c.watch(once=True)`: that spends itself on the first `Bloodied`
    of anybody's, and an ally going down is not this sentence.

    A plain "+1 bonus" prints no type word, so no `kind=`.

    The breath weapon half is one `c.ignore_resistance`, and two things
    in it are read rather than written. The type is the build's own
    element, which is what Dragon Soul records and `c.element` reads --
    a build that recorded none leaves this half inert, which is right,
    because the printed condition is the two types matching. The value
    is the heroic 5 that the soul grants, the same number
    `cf:sorcerer-f0s1` lays. p1448 is the breath weapon the card means.
    """
    me = c.me
    element = c.element(on=me)
    if element is not None:
        c.ignore_resistance(
            5, element, on=me, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("power") == "p1448",
        )
    done: list[bool] = []

    def on_blood(ev: Bloodied) -> None:
        if ev.actor != me or done:
            return
        done.append(True)
        for defence in (FORT, REF, WILL):
            c.bonus(defence, 1, on=me, until=When.ENCOUNTER)

    c.watch(Bloodied, on_blood, until=When.ENCOUNTER, on=me)


@power("f2805", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("cf:sorcerer-f0s3",),
       trigger="you slide a target with a sorcerer attack",
       on=Trigger(ForcedMove, _my_sorcerer_slide, "you slide a target"))
def f2805(c: Cast) -> None:
    """`ForcedMove` rather than `Moved`: it is the only one of the two
    that says who did the shoving and with which row. `Moved` carries the
    creature, both ends of the step and `kind_`, and no source at all, so
    "targets **you** slide" could not be asked of it.

    The feature named beside the attacks has a ref -- the prerequisite
    prints `cf:sorcerer-f0s3` -- and no row: that soul is one of the four
    the class page prints and only two are declared. So the dropped
    clause names the row it is waiting for rather than the shape of the
    absence. The day that leg lands, this is one line.
    """
    c.penalty(AC, 2, on=c.trigger.target, until=When.EONT)


@power("f2808", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you make an attack roll with a daily sorcerer power",
       on=Trigger(AttackRolled, _my_daily_roll, "you roll for a daily"))
def f2808(c: Cast) -> None:
    """`AttackRolled` carries `natural` and is announced before the hit
    and before any damage, so a damage bonus laid here is read by the
    `c.damage` the power's body goes on to call.

    The call is a real `c.choose`, handed two options and nothing else --
    a decider answering it cannot see the die it is guessing at. The
    latch keeps "for one attack roll" honest across a burst, which rolls
    once per target and would otherwise pay on each.
    """
    ev = c.trigger
    now = (ev.power, c.world.round)
    if _CALLED.get(c.me) == now:
        return
    _CALLED[c.me] = now
    pick = c.choose(["even", "odd"], f"{c.ref}: even or odd")
    if pick is None or (ev.natural % 2 == 0) != (pick == "even"):
        return
    foe, ref = ev.target, ev.power
    c.bonus(
        "damage", c.cha_mod, kind="feat", on=c.me, until=When.EOT, once=True,
        when=lambda ctx: ctx.get("target") == foe and ctx.get("power") == ref,
    )


# -- narrative only ---------------------------------------------------------


@power("f2804", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f2804(c: Cast) -> None:
    """Untrained skill checks and nothing else. Deliberately inert rather
    than unwritten: no fight turns on one, and `engine/skills.py` has no
    training model to tell a trained check from an untrained one even if
    a fight did."""


# -- features named in prose ------------------------------------------------


@power("f1160", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("events.ShortRested",))
def f1160(c: Cast) -> None:
    """Skill and initiative bonuses that differ by cosmic phase.
    `cf:sorcerer-f0s0` is declared and refused in play for want of a rest
    anything announces, so no phase is ever set and there is nothing to
    branch on. Same symbol that row waits on."""


@power("f2026", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("events.ShortRested",))
def f2026(c: Cast) -> None:
    """Gives `f2023b` a two-type damage line sized by the source's own
    damage bonus.

    Re-aimed. Two types at once is `c.damage(dtypes=)` now, and handing
    a damage line to a named row is an ordinary `Hit` trigger against
    that ref -- `invoker_b.f2032` already rides this very card that way.
    What is left is the number: the bonus belongs to `cf:sorcerer-f0s0`,
    which is refused in play because its phase is chosen at a rest
    nothing announces, so there is no amount to deal. Same symbol
    `f1160` above waits on.
    """


@power("f3433", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.counts_as(group=)", "c.proficient(group)"))
def f3433(c: Cast) -> None:
    """Two weapons made usable and then made to count as a third group
    for the purpose of casting. `Weapon.group` is a plain string on the
    component and nothing rewrites one, and proficiency is a number the
    chassis hands out rather than something a row can grant."""


# -- the parity the engine cannot hear --------------------------------------


@power("f2806", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_feature_roll()",))
def f2806(c: Cast) -> None:
    """Calls a half of the class feature's d10 before it is rolled and
    replaces the result when the call lands.

    Unusually, the feature itself *is* modelled -- `souls.sorcerer_soul`
    rolls the die and `souls.wear_soul` would swear the replacement. What
    is missing is the moment: the roll happens while the trait arms and
    is announced to nobody, so the call can only be made after the answer
    is known, which would make the choice free every time.
    """


@power("f2807", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_initiative_roll()",))
def f2807(c: Cast) -> None:
    """The same call against an initiative check. `turns._roll_initiative`
    rolls for everybody before any trait is armed and announces the
    numbers rather than the dice, so there is no parity to read and no
    window to read it in."""


@power("f1162", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.on_reroll()",))
def f1162(c: Cast) -> None:
    """A slide or a shift depending on the parity of `p1452`'s reroll.
    `c.slide` and `c.shift` are the easy half and the power is a ref, so
    the whole hold is the roll: `c.reroll_attack` takes a reroll but
    announces neither that one happened nor what it came up."""
