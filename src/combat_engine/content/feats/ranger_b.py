"""Ranger feats, the second batch.

`ranger.py` holds the first, and the same two-way split runs through
this one. The quarry is nameable -- `cf:ranger-f1` is in these
prerequisites and `c.quarry` lays the relation -- and the beast
companion does not exist, so the eight rows that talk to one carry
`c.beast()` beside the ten already waiting.

What is new here is the **weapon-style family**, which the ranger shares
with the fighter and the warlord. A style feat's benefit is gated on
"a power associated with this feat", and the printed
`Associated Powers:` list resolves only where a member happens to be a
ref; the rest arrive as names, which this project may not read. So the
set is unknowable and those clauses carry `feat.associated_powers`. The
*greater* feat of each pair prints two benefits, and the first is very
often ordinary -- which is why most of them play with one clause
dropped rather than being refused outright.

`f2384` is the one to read. "It takes damage if it shifts before the end
of your next turn" is a watch laid on the creature that was hit, and
`c.watch` plus `Moved.kind_` say it exactly.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionPointSpent,
    ActionType,
    Cast,
    Dropped,
    Gear,
    Hit,
    Keyword,
    Miss,
    Moved,
    Relation,
    Trigger,
    When,
    Window,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import AttackDeclared
from combat_engine.engine.query import allies, enemies

#: The unknowable list, and the substitution that would want it anyway.
ASSOCIATED = ("feat.associated_powers",)
AS_BASIC = ("feat.associated_powers", "c.as_basic(ref)")
#: There is no beast companion. Ten rows in `ranger.py` already wait.
BEAST = ("c.beast()",)
#: Nothing announces that the class's extra damage was about to be paid.
EXTRA = ("c.on_extra_damage()",)

#: The conditions f2367 narrows its save penalty to.
_STUNNING = ("dazed", "stunned")


def _is_my_quarry(c: Cast, who: int | None) -> bool:
    """The same question `ranger.py` asks, and the same way -- the
    relation table is the only thing that remembers a quarry."""
    return who is not None and c.world.relations.holds(
        Relation.QUARRY_OF, c.me, who
    )


def _holding(c: Cast, *groups: str) -> bool:
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return False
    return any(w.group in groups for w in (*gear.melee, *([gear.ranged] if gear.ranged else [])))


def _martial(p, *, usage=None) -> bool:  # noqa: ANN001
    if p is None or Keyword.MARTIAL not in p.keywords:
        return False
    return usage is None or p.usage in usage


def _my_martial_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and _martial(get(ev.power))


def _my_martial_encounter_miss(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and _martial(get(ev.power), usage=(ENCOUNTER,))


def _my_martial_encounter_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and _martial(get(ev.power), usage=(ENCOUNTER,))


def _i_crit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and ev.critical


def _my_point(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me


def _hit_quarry_with(ref: str):  # noqa: ANN202
    def when(world, me: int, ev: Any) -> bool:  # noqa: ANN001
        return (
            ev.attacker == me
            and ev.power == ref
            and world.relations.holds(Relation.QUARRY_OF, me, ev.target)
        )

    return when


# -- the quarry half --------------------------------------------------------


@power("f787", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f787(c: Cast) -> None:
    """Cancels the cover and concealment penalty against the quarry.

    Both are a flat -2 the attack context applies, so handing the +2
    back against exactly those targets is the printed sentence. Read off
    the relation per attack rather than fixed at arming, because the
    quarry moves from creature to creature over a fight.
    """
    c.bonus(
        "attack", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            _is_my_quarry(c, ctx.get("target"))
            and (ctx.get("cover", 0) or ctx.get("concealment", 0))
        ),
    )


@power("f808", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f808(c: Cast) -> None:
    """"No other creatures within 3 squares of it" -- allies of the
    target and of the caster alike, and the caster itself does not
    count, since the printed line is about the target standing alone
    rather than about who is beside you."""
    from combat_engine.engine.query import distance_between

    me = c.me

    def alone(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        if foe is None or ctx.get("ranged", False):
            return False
        return not any(
            other not in (foe, me)
            and distance_between(c.world, foe, other) <= 3
            for other in (*enemies(c.world, me), *allies(c.world, me))
        )

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=alone)


@power("f1232", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=EXTRA,
       trigger="you reduce your quarry to 0 hit points",
       on=Trigger(Dropped, lambda w, me, ev: (
           getattr(ev, "source", None) == me
           and w.relations.holds(Relation.QUARRY_OF, me, ev.actor)
       ), "you drop your quarry"))
def f1232(c: Cast) -> None:
    """A new quarry the moment the old one falls.

    The nearest standing enemy, because a quarry you cannot reach is the
    feat doing nothing. The second sentence -- reapplying the class's
    extra damage on the new target -- is dropped: nothing announces that
    the extra damage was paid, so "even if you already used it" has no
    counter to override.
    """
    from combat_engine.engine.query import distance_between

    me = c.me
    standing = [f for f in enemies(c.world, me) if not _is_my_quarry(c, f)]
    if not standing:
        return
    c.quarry(on=min(standing, key=lambda f: distance_between(c.world, me, f)))


@power("f2183", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit your quarry with p1448",
       on=Trigger(Hit, _hit_quarry_with("p1448"), "you breathe on your quarry"))
def f2183(c: Cast) -> None:
    foe = c.trigger.target
    c.bonus(
        "attack", 2, on=c.me, until=When.EONT,
        when=lambda ctx: ctx.get("target") == foe,
    )


@power("f1665", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.bonus(dtype=)",),
       trigger="you hit your quarry with p8278",
       on=Trigger(Hit, _hit_quarry_with("p8278"), "you hit your quarry"))
def f1665(c: Cast) -> None:
    """Extra damage on every later blow against that target.

    The *type* is dropped rather than the clause: the printed extra is
    necrotic and `c.bonus` carries `dice` but no damage type, so it
    rolls untyped -- which is wrong against anything that resists
    necrotic. The same gap the assassin's f1809 named.
    """
    foe = c.trigger.target
    c.bonus(
        "damage", c.con_mod, on=c.me, until=When.EONT,
        when=lambda ctx: ctx.get("target") == foe,
    )


@power("f2389", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you spend an action point",
       on=Trigger(ActionPointSpent, _my_point, "you spend an action point"))
def f2389(c: Cast) -> None:
    """"Before or after" is a choice with no way to express the ordering,
    and the point has already been spent by the time this is offered --
    so the shift happens now, which is "before"."""
    c.shift(2)


@power("f815", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def f815(c: Cast) -> None:
    """Perception and Stealth during an extended rest. Not a fight."""


# -- the greater style feats whose first benefit is ordinary ----------------


@power("f1309", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=ASSOCIATED,
       trigger="you score a critical hit with a two-handed axe",
       on=Trigger(Hit, _i_crit, "you crit"))
def f1309(c: Cast) -> None:
    """Splash damage on a crit. The second benefit -- Dexterity in place
    of Strength on the associated powers -- is dropped."""
    gear = c.world.get(c.me, Gear)
    if gear is None or not any(
        w.group == "axe" and w.two_handed for w in gear.melee
    ):
        return
    for foe in enemies(c.world, c.me):
        if c.adjacent(to=foe):
            c.flat(c.dex_mod, on=foe)


@power("f2328", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=AS_BASIC,
       trigger="you miss with a martial encounter power",
       on=Trigger(Miss, _my_martial_encounter_miss, "you miss"))
def f2328(c: Cast) -> None:
    if not _holding(c, "heavy blade"):
        return
    foe = c.trigger.target
    c.bonus(
        "attack", 2, on=c.me, until=When.EONT, once=True,
        when=lambda ctx: ctx.get("target") == foe,
    )


@power("f2341", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=AS_BASIC)
def f2341(c: Cast) -> None:
    """"Larger than you", so `Size.order` and not `>`: `Size` is a
    `StrEnum` and a bare comparison sorts the words alphabetically."""
    me = c.me
    mine = c.size_of(me)
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            _holding(c, "spear")
            and ctx.get("target") is not None
            and c.size_of(ctx["target"]).order > mine.order
        ),
    )


@power("f2346", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=AS_BASIC,
       trigger="you score a critical hit",
       on=Trigger(Hit, _i_crit, "you crit"))
def f2346(c: Cast) -> None:
    if _holding(c, "flail", "mace"):
        c.push(1, on=c.trigger.target)


@power("f2349", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=AS_BASIC,
       trigger="you hit with a martial encounter power",
       on=Trigger(Hit, _my_martial_encounter_hit, "you hit"))
def f2349(c: Cast) -> None:
    me = c.me
    gear = c.world.get(me, Gear)
    if gear is None or not any(
        w.group in ("axe", "hammer", "mace") and "versatile" in w.properties
        for w in gear.melee
    ):
        return
    for friend in [a for a in allies(c.world, me) if a != me]:
        c.bonus(
            AC, 2, on=friend, until=When.EONT, kind="feat",
            when=lambda ctx, f=friend: c.adjacent_to(f, me),
        )


@power("f2367", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=ASSOCIATED,
       trigger="you hit with a martial power",
       on=Trigger(Hit, _my_martial_hit, "you hit"))
def f2367(c: Cast) -> None:
    """A save penalty narrowed to two conditions. The saving throw's
    context carries the conditions the effect holds, which is what makes
    the narrowing sayable rather than a blanket penalty."""
    gear = c.world.get(c.me, Gear)
    if gear is None or not any(
        w.group in ("hammer", "flail", "mace") and not w.two_handed
        for w in gear.melee
    ):
        return
    c.penalty(
        "save", 2, on=c.trigger.target, until=When.EONT,
        when=lambda ctx: any(
            str(x.value) in _STUNNING for x in ctx.get("conditions", ())
        ),
    )


@power("f2373", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=ASSOCIATED)
def f2373(c: Cast) -> None:
    """Takes the combat-advantage bonus away from adjacent enemies.

    Written as a penalty that exactly cancels it rather than as a
    suppression, because combat advantage is worked out inside
    `resolve.attack` and reaches the modifiers only as the `advantage`
    key -- so the place to answer it is the same context that carries
    it.
    """
    me = c.me
    gear = c.world.get(me, Gear)
    if gear is None or not any(
        w.group == "heavy blade" and "versatile" in w.properties
        for w in gear.melee
    ):
        return
    for foe in enemies(c.world, me):
        c.penalty(
            "attack", 2, on=foe, until=When.ENCOUNTER,
            when=lambda ctx, f=foe: (
                ctx.get("advantage", False)
                and ctx.get("target") == me
                and c.adjacent(to=f)
            ),
        )


@power("f2384", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=ASSOCIATED,
       trigger="you hit with a martial power",
       on=Trigger(Hit, _my_martial_hit, "you hit"))
def f2384(c: Cast) -> None:
    """Punishes the target for shifting.

    A watch on the creature rather than a standing modifier: the printed
    line pays out on a *move*, and `Moved.kind_` is what separates a
    shift from a walk. `once=True` because "it takes damage" is one
    payment, not one per square.
    """
    if not _holding(c, "flail"):
        return
    foe = c.trigger.target
    hurt = c.wis_mod

    def on_shift(ev: Any) -> None:
        if ev.actor == foe and getattr(ev, "kind_", "") == "shift":
            c.flat(hurt, on=foe)

    c.watch(Moved, on_shift, on=foe, until=When.EONT, once=True)


@power("f2337", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=ASSOCIATED,
       trigger="you attack with a bow or crossbow",
       on=Trigger(AttackDeclared, lambda w, me, ev: ev.attacker == me,
                  "you attack", window=Window.BEFORE))
def f2337(c: Cast) -> None:
    """No opportunity attack from the creature you are shooting at.

    Declared `BEFORE` the attack, because the provocation happens as the
    shot is taken -- an `AFTER` window would grant the exemption once
    the reprisal had already been made. `c.no_provoke(from_=)` names the
    one creature the printed line exempts, which is not the same as not
    provoking at all.
    """
    if _holding(c, "bow", "crossbow"):
        c.no_provoke(from_=c.trigger.target, on=c.me, until=When.EOT)


# -- the style feats that are nothing but the unknowable list ---------------


def _style(ref: str, what: str, *, wants: tuple[str, ...] = ASSOCIATED) -> None:
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=wants)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = (
        f"{what} The `Associated Powers:` list arrives as printed names, "
        "which this project may not read, so the set is unknowable."
    )


_style("f2069", "One pushes the enemy it hits.")
_style("f2325", "One punishes whatever is giving your target cover.",
       wants=AS_BASIC)
_style("f2335", "One gains the rattling keyword.")
_style("f2352", "One pays a speed bonus on a hit.")
_style("f2355", "One shoots past cover and concealment.")
_style("f2386", "One pays extra when you are hidden from the target.")
_style("f2361", "One uses Dexterity, and your shifts grow by a square.",
       wants=("feat.associated_powers", "c.extend_shift()"))
_style("f2387", "One lets you shift before the attack; the other clause "
                "is a Perception penalty, which is not a fight.")
_style("f2334", "One lets you shift before the attack, and the other "
                "clause answers an enemy shifting away from you.",
       wants=("feat.associated_powers", "c.on_shift_away()"))


# -- the beast companion, which does not exist ------------------------------


def _beast(ref: str, what: str, *, wants: tuple[str, ...] = BEAST) -> None:
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=wants)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = f"{what} There is no beast companion to do it to."


_beast("f804", "A defence bonus for the companion, and a racial reroll "
               "spent on its behalf.",
       wants=("c.beast()", "c.on_racial_power()"))
_beast("f824", "More hit points for one particular companion.")
_beast("f828", "The companion answers whatever damages you.")
_beast("f1240", "The companion changes origin and rides a racial teleport.")
_beast("f1381", "The companion shares two named racial powers.")
_beast("f1718", "You and the companion both ignore concealment near it.")
_beast("f2031", "The companion gains combat advantage where you flank.")
_beast("f2100", "An attack bonus when nobody is nearer than you two.")


# -- the class's extra damage, which announces nothing ----------------------


@power("f807", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=EXTRA)
def f807(c: Cast) -> None:
    """A second helping of the class's extra damage after an action
    point. The point is a real event; what is missing is that nothing
    announces the extra damage was paid, so there is no once-a-round
    counter to override."""


@power("f1722", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=EXTRA)
def f1722(c: Cast) -> None:
    """Pays the class's extra damage on a *miss*. Same gap as f807, from
    the other side: the once-a-round limit is what the row is spending,
    and nothing counts it."""
