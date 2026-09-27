"""Ranger feats, the second batch.

`ranger.py` holds the first, and the split that used to run through
this one has closed on both sides. The quarry is nameable --
`cf:ranger-f1` is in these prerequisites and `c.quarry` lays the
relation -- and the beast companion is a creature on the board now, so
the eight rows that talk to one read it with `c.beast()`.

What is new here is the **weapon-style family**, which the ranger shares
with the fighter and the warlord. A style feat's benefit is gated on "a
power associated with this feat", and that list now resolves into refs
-- see `styles.py` and `etl/build._associated_refs`. It was never an
engine gap; the printed list was reaching authors as prose. Two real
gaps are left behind it: `c.as_basic(ref)`, for the greater feats whose
second benefit is standing in for a basic attack, and
`c.ability_for(ref)`, for the ones that swap Dexterity in for Strength
on named rows.

`f2384` is the one to read. "It takes damage if it shifts before the end
of your next turn" is a watch laid on the creature that was hit, and
`c.watch` plus `Moved.kind_` say it exactly.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionPointSpent,
    ActionType,
    Cast,
    Condition,
    DamageApplied,
    Dropped,
    Gear,
    Hit,
    Keyword,
    Miss,
    Moved,
    PowerUsed,
    Relation,
    Trigger,
    When,
    Window,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import AttackDeclared
from combat_engine.engine.query import allies, distance_between, enemies, flanked_by

from .styles import among, hit_with_one_of, used_one_of

#: Knowing the list does not let a named row stand in for the basic…
AS_BASIC = ("c.as_basic(ref)",)
#: …nor change which ability a named row rolls.
ABILITY = ("c.ability_for(ref)",)
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


def _quarry_hurt_me(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """Did this ranger's quarry just take hit points off it?

    `DamageApplied` rather than `Hit`, because the card says "damages
    you" -- an attack that hits for nothing did not.
    """
    return (
        ev.target == me
        and ev.amount > 0
        and world.relations.holds(Relation.QUARRY_OF, me, ev.source)
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

    **`cover` and `concealment` are not keys the attack context has.**
    `resolve.attack` builds it with `attacker, target, power, advantage,
    opportunity, charge, action_point, ranged, branch, hand` -- so a
    gate reading either was silently false and this waiver never once
    applied. `c.ignore_cover` is the verb, and it writes into the
    `ignore_cover` modifier that `query.cover_waived` actually reads.

    Read off the relation per attack rather than fixed at arming,
    because the quarry moves from creature to creature over a fight.
    """
    c.ignore_cover(
        on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _is_my_quarry(c, ctx.get("target")),
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


@power("f2183", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
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


@power("f2389", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
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
       reach=PERSONAL, target=SELF, dropped=ABILITY,
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


@power("f2367", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you hit with a martial power",
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
       reach=PERSONAL, target=SELF, dropped=ABILITY)
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
       reach=PERSONAL, target=SELF, dropped=ABILITY,
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
       reach=PERSONAL, target=SELF, dropped=ABILITY,
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


# -- the style feats, now that the lists resolve ---------------------------


@power("f2069", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with an associated power",
       on=Trigger(Hit, hit_with_one_of("p919", "p10890"),
                  "you hit with an associated power"))
def f2069(c: Cast) -> None:
    if _holding(c, "bow"):
        c.push(1, on=c.trigger.target)


@power("f2352", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with an associated power",
       on=Trigger(Hit, hit_with_one_of("p971", "p919", "p10890"),
                  "you hit with an associated power"))
def f2352(c: Cast) -> None:
    """"Until the end of your turn", so `When.EOT` and not `EONT` -- a
    speed bonus that outlived the turn it was bought for would be worth
    twice what the card prints."""
    if _holding(c, "crossbow", "bow", "sling"):
        c.bonus("speed", 1, on=c.me, until=When.EOT)


@power("f2386", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2386(c: Cast) -> None:
    """Extra damage with two named rows against anything you are hidden
    from. `query.hidden_from` answers the hiding, and a damage bonus is
    the right shape because the printed extra is a flat modifier."""
    from combat_engine.engine.query import hidden_from

    me = c.me
    picked = among("p917", "p10733")
    c.bonus(
        "damage", c.int_mod, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            picked(ctx)
            and _holding(c, "bow", "crossbow")
            and ctx.get("target") in hidden_from(c.world, me)
        ),
    )


@power("f2355", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2355(c: Cast) -> None:
    """Shoots past cover, and mostly past total cover.

    **The groups are a closed set.** `chargen` only ever sets `group`
    to axe, bow, crossbow, heavy blade, implement, light blade, mace,
    spear, staff or unarmed -- "hand crossbow" and "shortbow" are
    *weapons*, not groups, so gating on them was silently false
    forever and the row was narrower than the card in a way nothing
    would have noticed.

    **`cover` and `concealment` are not keys the attack context has.**
    `resolve.attack` builds it with `attacker, target, power, advantage,
    opportunity, charge, action_point, ranged, branch, hand` -- so a
    gate reading either was silently false and this waiver never once
    applied. `c.ignore_cover` is the verb, and it writes into the
    `ignore_cover` modifier that `query.cover_waived` actually reads.

    `partial=True` is the card's two numbers in one call.
    Ordinary cover and concealment are a -2 the attack context applies,
    so +2 cancels them exactly. Superior cover and total concealment are
    -5, and the card leaves a -2 standing, so the bonus there is +3 --
    written as the difference rather than as a suppression, because
    that is how the penalty reaches the roll.
    """
    me = c.me
    picked = among("p529", "p1521")

    def mine(ctx: dict) -> bool:
        return picked(ctx) and _holding(c, "crossbow", "bow", "sling")

    # `partial=True` waives the ordinary -2 and leaves superior cover
    # standing, which is the card's two numbers said in one call --
    # `ignore_cover` is a modifier `query.cover_waived` reads, so the
    # two rungs do not need writing out.
    c.ignore_cover(on=me, until=When.ENCOUNTER, partial=True, when=mine)


def _shift_before(ref: str, squares: int, groups: tuple[str, ...],
                  refs: tuple[str, ...], what: str,
                  wants: tuple[str, ...] = ()) -> None:
    """"You can shift N squares **before** the attack."

    `PowerUsed` fires before the body, which is the only reason this
    clause is sayable at all -- by the time a `Hit` is announced the
    attack has happened and "before" has gone.
    """

    # `AT_WILL`, not `ENCOUNTER`: a triggered trait spends a use every
    # time it fires, and neither card prints a limit. Written inside a
    # helper, so the tree-wide sweep could not see it.
    @power(ref, level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, dropped=wants,
           trigger="you attack with an associated power",
           on=Trigger(PowerUsed, used_one_of(*refs),
                      "you use an associated power"))
    def feat(c: Cast) -> None:
        if _holding(c, *groups):
            c.shift(squares)

    feat.__name__ = ref
    feat.__doc__ = what


_shift_before(
    "f2387", 2, ("bow", "crossbow"), ("p529", "p1521"),
    """Shift before the shot. The feat's other clause is a Perception
    penalty, which is a check rather than a fight and so is not a
    dropped mechanic.""",
)
_shift_before(
    "f2334", 2, ("hammer", "pick"), ("p4405", "p10614"),
    """Shift before the swing. The other clause -- answering an adjacent
    marked enemy that shifts away -- is dropped: `Moved.kind_` says a
    shift happened and nothing says which creature it went away
    from.""",
    wants=("c.on_shift_away()",),
)


@power("f2325", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.cover_from()", "c.as_basic(ref)"))
def f2325(c: Cast) -> None:
    """Punishes whatever is giving your target cover, and lets `p529` or
    `p4389` stand in for a ranged basic. The list resolves now; neither
    clause does. Cover is a number the attack context carries and
    nothing says *which* creature is casting it, which an item block
    also wants."""


@power("f2335", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.add_keyword()",))
def f2335(c: Cast) -> None:
    """Gives `p919`, `p10890` or `p970` the rattling keyword. The list
    resolves; `Power.keywords` is header data read before anything runs
    and nothing adds to it for a turn."""


@power("f2361", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.extend_shift()", "c.ability_for(ref)"))
def f2361(c: Cast) -> None:
    """Both clauses are gaps and they are different ones. Nothing adds
    to the distance a shift somebody else's row grants, and nothing
    changes which ability a named row rolls."""


# -- the beast companion ----------------------------------------------------
#
# Read `c.beast()` inside the gate, never above it: the beast can be
# killed and called again and a captured id goes quietly stale.

#: The printed categories two of these rows pay out for, by ref. A
#: category is what the beast was called with, so this is the same
#: question `chargen` answered when the style was taken.
_BOAR = "comp:2"
_WOLF = "comp:8"


@power("f804", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.on_racial_power()",))
def f804(c: Cast) -> None:
    """The beast is harder to catch on the way past.

    The defence side of the attack context is the rich one -- it is handed
    `opportunity` -- so this is a gate that answers rather than a bonus
    that is always on. Dropped: spending a racial row on the beast's
    behalf, and that row is not in the tree.
    """
    pet = c.beast()
    if pet is not None:
        c.bonus(AC, 2, on=pet, until=When.ENCOUNTER,
                when=lambda ctx: bool(ctx.get("opportunity")))


@power("f824", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f824(c: Cast) -> None:
    """Hit points for one category of beast, and only that one.

    There is no modifier for a maximum, so this moves `Health` itself --
    and then has to be safe to arm twice, because a world that runs two
    encounters arms every trait again and the beast is not rebuilt between
    them. The printed total is recomputed from the database and compared,
    which is the only honest way to ask "has this already been added".
    """
    from combat_engine.content.loader import companion as _block
    from combat_engine.engine.components import Health

    pet = c.beast(category=_BOAR)
    health = c.world.get(pet, Health) if pet is not None else None
    if health is None:
        return
    block = _block(_BOAR)
    printed = block.hp_base + block.hp_per_level * c.level
    if health.max_hp >= printed + c.level:
        return
    health.max_hp += c.level
    health.hp += c.level


@power("f828", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="your quarry damages you with an attack",
       on=Trigger(DamageApplied, _quarry_hurt_me, "your quarry damages you"))
def f828(c: Cast) -> None:
    """The beast answers whatever hurt its ranger.

    Two bonuses rather than one: `attack` and `damage` are separate keys,
    and a row writing only the first is half a card. Both untyped -- the
    text prints no word in front of "bonus".
    """
    pet = c.beast()
    if pet is None:
        return
    foe = c.trigger.source
    for what in ("attack", "damage"):
        c.bonus(what, 1, on=pet, until=When.EONT,
                when=lambda ctx, f=foe: ctx.get("target") == f)


@power("f1240", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.on_death_save()", "c.on_racial_power()"))
def f1240(c: Cast) -> None:
    """Two clauses of four.

    The saving-throw context carries the conditions being saved against,
    so "against the unconscious condition" is a real gate. The origin is
    a swap rather than an addition -- the companion's stat block prints
    one already -- which is what `instead_of` is for. Dropped: the
    death-saving-throw half, which does not go through the same roll,
    and the teleport rider on a racial row that is not in the tree. The
    Stealth bonus is a skill and belongs to no fight.
    """
    pet = c.beast()
    if pet is None:
        return
    c.set_origin("shadow", on=pet, until=When.ENCOUNTER, instead_of="natural")
    c.bonus(
        "save", 2, on=pet, until=When.ENCOUNTER,
        when=lambda ctx: Condition.UNCONSCIOUS in ctx.get("conditions", ()),
    )


@power("f1381", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_racial_power()",))
def f1381(c: Cast) -> None:
    """The beast shares the effect of either of two racial rows. Neither
    row is in the tree, so there is no effect to share."""


@power("f1718", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1718(c: Cast) -> None:
    """Neither of you squints at anything standing next to the beast.

    Wider than the card by one word: `c.ignore_cover` waives cover and
    concealment together -- `query.cover_waived` is asked once for both --
    and the printed sentence names only concealment. There is no
    concealment-only form, and the alternative is to say nothing at all.
    """
    def beside_the_beast(ctx: dict[str, Any]) -> bool:
        pet = c.beast()
        victim = ctx.get("target")
        return pet is not None and victim is not None and c.adjacent_to(pet, victim)

    pet = c.beast()
    for who in [c.me, *([pet] if pet is not None else [])]:
        c.ignore_cover(on=who, until=When.ENCOUNTER, when=beside_the_beast)


@power("f2031", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2031(c: Cast) -> None:
    """Combat advantage for one category of beast, while its ranger flanks.

    "While you are flanking" is a state that changes every time anybody
    moves, and `c.grants_advantage` lays a relation with a duration and
    takes no gate. So the question is asked at the only moment it decides
    anything -- as the beast declares its attack, in the interrupt window
    before the roll -- and the grant is spent by that one swing.
    """
    def about_to_swing(ev: AttackDeclared) -> None:
        pet = c.beast(category=_WOLF)
        if pet is None or ev.attacker != pet:
            return
        if flanked_by(c.world, ev.target, c.me):
            c.grants_advantage(on=ev.target, to=pet, until=When.EONT, once=True)

    c.watch(AttackDeclared, about_to_swing, on=c.me, until=When.ENCOUNTER,
            window=Window.BEFORE)


@power("f2100", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2100(c: Cast) -> None:
    """Prime shot, measured from whichever of the two of you is closer.

    The errata'd text, which is the one the database carries: the class
    feature it used to require is the one this style gives up, so the
    bonus is this row's own and applies to melee as well as ranged.
    A companion is left out of `c.allies` on purpose, so the beast cannot
    be the ally that spoils it.
    """
    def nobody_nearer(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None:
            return False
        pet = c.beast()
        ours = distance_between(c.world, c.me, victim)
        if pet is not None:
            ours = min(ours, distance_between(c.world, pet, victim))
        return not any(
            distance_between(c.world, mate, victim) < ours
            for mate in c.allies()
            if mate != c.me
        )

    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, when=nobody_nearer)


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
