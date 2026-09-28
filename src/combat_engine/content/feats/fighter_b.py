"""Fighter feats, the second and larger batch.

`fighter.py` holds the first. This one is mostly the **weapon-style
family** -- twenty rows printed as a pair, a lesser feat naming a weapon
group and a greater one gated on the lesser -- and that family has one
gap running through all of it.

**"A power associated with this feat"** used to be the whole blocker
here, and it was never an engine gap. The printed `Associated Powers:`
list was reaching authors as prose; now `etl/build._associated_refs`
resolves it into refs, so the set is ordinary data and the clause is
one `ctx["power"] in ...` read. See `styles.py`.

**"In place of a melee basic attack"** -- the second benefit of most
greater style feats -- is `c.as_basic`, filed under the window the
card names: the charge, the opportunity attack, or the swing Combat
Challenge allows. It is a standing arrangement, so a card that also
prints a Trigger answers that with `c.watch` instead; see below.

The rest is ordinary riders on opportunity attacks, charges, crits and
marks, all of which the attack and damage contexts already answer.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FORT,
    MINOR,
    PERSONAL,
    REF,
    SELF,
    WILL,
    ActionType,
    Cast,
    Condition,
    ConditionEnded,
    DamageType,
    Dropped,
    Gear,
    Hit,
    Keyword,
    Miss,
    PowerUsed,
    SecondWind,
    Size,
    Trigger,
    When,
    about_me,
    power,
)
from combat_engine.engine.components import Position
from combat_engine.engine.dsl import get
from combat_engine.engine.events import ForcedMove, Moved, PowerResolved
from combat_engine.engine.grid import distance, neighbours
from combat_engine.engine.query import allies, enemies, flanked_by, holding
from combat_engine.engine.types import Forced

from .styles import among, hit_with_one_of, used_one_of

#: **A standing clause and a triggered one on the same card.** The
#: dispatcher only reaches a no-action row when its declared trigger
#: fires, so a row that also has to be *true* from the start of the
#: fight -- which "you can use this in place of a melee basic attack"
#: is -- is never armed. Those rows keep the printed Trigger as text
#: and answer it with `c.watch`, the shape `p7419` already uses.


_BIG = (Size.LARGE, Size.HUGE, Size.GARGANTUAN)


def _holding(c: Cast, *groups: str) -> bool:
    """Is the caster swinging one of these weapon groups?

    The same helper `fighter.py` defines, repeated rather than imported
    for the reason the two files are separate at all -- but read off
    `Gear.melee` here rather than `query.holding`, because half of this
    batch names a *grip* as well ("one-handed axe", "two-handed axe")
    and the grip lives on the weapon's properties.
    """
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return False
    return any(w.group in groups for w in gear.melee)


def _grip(c: Cast, *groups: str, hands: int) -> bool:
    """One of those groups, held in that many hands."""
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return False
    return any(
        w.group in groups and w.two_handed == (hands == 2)
        for w in gear.melee
    )


def _mine(me: int):  # noqa: ANN202
    def when(world, actor: int, ev: Any) -> bool:  # noqa: ANN001
        return ev.attacker == me

    return when


def _i_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me


def _i_crit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and ev.critical


def _i_missed_with_encounter(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me
        and p is not None
        and p.usage is ENCOUNTER
        and Keyword.MARTIAL in p.keywords
    )


def _i_dropped_someone(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return getattr(ev, "source", None) == me


def _my_long_shove(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """A push or a slide of mine, two squares or more.

    A pull is excluded because the printed line names the other two, and
    a polearm that drags something closer is not what it is about.
    """
    return (
        ev.source == me
        and ev.how in (Forced.PUSH, Forced.SLIDE)
        and ev.squares >= 2
    )


def _my_push(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.source == me and ev.how is Forced.PUSH


def _shield_power_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """A hit with a row whose printed Requirement is a shield.

    `Power.requires` is a callable and says nothing about itself, but
    `requires_text` is the sanitised sentence and twenty-seven rows in
    the tree read "needs a shield". That is the printed question
    exactly.
    """
    p = get(ev.power)
    return ev.attacker == me and p is not None and "shield" in p.requires_text


# -- the writable riders ----------------------------------------------------


@power("f806", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="your polearm or spear attack pushes or slides a target 2+",
       on=Trigger(ForcedMove, _my_long_shove, "you shove a target 2 squares"))
def f806(c: Cast) -> None:
    """Knocks the target prone after the forced movement.

    Declared on `ForcedMove` rather than on the hit, because the hit does
    not know how far anything went and this row's whole gate is the
    distance. The default window for a `NONE` row is `AFTER`, which is
    the printed "at the end of the forced movement".
    """
    if _holding(c, "polearm", "spear"):
        c.prone(on=c.trigger.target)


@power("f811", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you drop an enemy with a heavy blade",
       on=Trigger(Dropped, _i_dropped_someone, "you drop an enemy"))
def f811(c: Cast) -> None:
    """"Shift as a minor action" is a line in the action menu, not a
    bonus -- `c.grant_action` is the verb, and `on=c.me` because it
    defaults to `c.target` and this one is about the caster."""
    if not _holding(c, "heavy blade"):
        return
    c.grant_action("shift", MINOR, on=c.me, until=When.EOT)


@power("f816", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a power that requires a shield",
       on=Trigger(Hit, _shield_power_hit, "you hit with a shield power"))
def f816(c: Cast) -> None:
    """"Or until you stop using the shield" is asked per attack rather
    than latched, so putting the shield down ends it the moment it
    matters."""
    me = c.me
    for defence in (AC, REF):
        c.bonus(
            defence, 1, on=me, until=When.EONT,
            when=lambda ctx: c.wielding("shield"),
        )


@power("f817", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f817(c: Cast) -> None:
    """Adjacency is asked at the moment of the attack, not when the trait
    arms: both the ally and the marked enemy move."""
    me = c.me
    for friend in [a for a in allies(c.world, me) if a != me]:
        for defence in (AC, FORT, REF, WILL):
            c.bonus(
                defence, 1, on=friend, until=When.ENCOUNTER,
                when=lambda ctx, f=friend: (
                    c.adjacent_to(f, me)
                    and ctx.get("attacker") is not None
                    and c.marked(on=ctx["attacker"], by=me)
                ),
            )


@power("f1734", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1734(c: Cast) -> None:
    me = c.me
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("target") is not None
            and c.bloodied(on=ctx["target"])
            and c.marked(on=ctx["target"], by=me)
        ),
    )


@power("f1735", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1735(c: Cast) -> None:
    """The damage context carries `opportunity`, so this is one gate."""
    me = c.me
    c.bonus(
        "damage", c.wis_mod, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("opportunity", False) and _grip(c, *_ONE_HANDED, hands=1)
        ),
    )


#: Every melee group a one-handed weapon can belong to. The grip is the
#: question `_grip` asks; the group list is just "not an implement".
_ONE_HANDED = (
    "axe", "flail", "hammer", "heavy blade", "light blade", "mace",
    "pick", "spear", "staff", "unarmed",
)


@power("f1737", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1737(c: Cast) -> None:
    c.bonus(
        "damage", c.con_mod, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("opportunity", False) and _holding(c, "axe"),
    )


@power("f1740", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1740(c: Cast) -> None:
    """"A versatile weapon in both hands" is a *grip*, and `Gear` has no
    grip -- but it has everything the grip is made of. A versatile
    weapon is in both hands exactly when there is no shield and no
    second weapon, which is what `Gear.two_weapon` and `Gear.shield`
    between them say."""
    gear = c.world.get(c.me, Gear)
    if gear is None or gear.shield or gear.two_weapon:
        return
    if not any("versatile" in w.properties for w in gear.melee):
        return
    for defence in (AC, REF):
        c.bonus(defence, 2, on=c.me, until=When.ENCOUNTER)


@power("f1742", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with an opportunity attack with a spear",
       on=Trigger(Hit, _i_hit, "you hit"))
def f1742(c: Cast) -> None:
    """Slide the target into a square beside you.

    `getattr` on `opportunity`, because `resolve.attack` sets it
    afterwards as a plain attribute rather than a field of the event.

    **`c.slide` has no `to_adjacent`.** I invented one; its keywords are
    `on`, `anchor`, `to` and `by`, so the call raised `TypeError` every
    time the trigger fired. `to=` names the square outright, which is
    what the printed "to a space adjacent to you" wants -- left to the
    decider, a slide is a free choice and would as happily push the
    target away.
    """
    if not getattr(c.trigger, "opportunity", False) or not _holding(c, "spear"):
        return
    foe = c.trigger.target
    mine = c.world.get(c.me, Position)
    theirs = c.world.get(foe, Position)
    if mine is None or theirs is None:
        return
    beside = [
        sq for sq in neighbours(mine.square)
        if distance(sq, theirs.square) <= 1 and sq != theirs.square
    ]
    if beside:
        c.slide(1, on=foe, to=beside[0])


@power("f1971", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with an opportunity attack",
       on=Trigger(Hit, _i_hit, "you hit"))
def f1971(c: Cast) -> None:
    """Push, then step into the square that just emptied -- so the square
    is read *before* the push and the shift is aimed at it."""
    if not getattr(c.trigger, "opportunity", False):
        return
    foe = c.trigger.target
    pos = c.world.get(foe, Position)
    was = pos.square if pos is not None else None
    if was is not None and c.push(1, on=foe):
        c.shift(1, to=was)


@power("f1972", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1972(c: Cast) -> None:
    c.bonus(
        "damage", c.con_mod, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("charge", False)
            and _grip(c, *_ONE_HANDED, "polearm", hands=2)
        ),
    )


@power("f2329", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you miss with a martial encounter power")
def f2329(c: Cast) -> None:
    """Both halves now. The miss is a watch so that the substitution,
    which is a standing arrangement, has somewhere to be armed."""
    if not _holding(c, "heavy blade"):
        return
    c.as_basic("p200", "p608", window="challenge")

    def on_miss(ev: Any) -> None:
        if not _i_missed_with_encounter(c.world, c.me, ev):
            return
        if not _holding(c, "heavy blade"):
            return
        foe = ev.target
        c.bonus(
            "attack", 2, on=c.me, until=When.EONT, once=True,
            when=lambda ctx: ctx.get("target") == foe,
        )

    c.watch(Miss, on_miss, on=c.me, until=When.ENCOUNTER)


@power("f2340", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2340(c: Cast) -> None:
    """"Larger than you", so the comparison is against the caster's own
    size rather than a fixed Large."""
    me = c.me
    if _holding(c, "spear"):
        c.as_basic("p634", "p1428", window="charge")
    mine = c.size_of(me)  # `.order`, not `>`: Size is a StrEnum
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            _holding(c, "spear")
            and ctx.get("target") is not None
            and c.size_of(ctx["target"]).order > mine.order
        ),
    )


@power("f2345", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit")
def f2345(c: Cast) -> None:
    if not _holding(c, "flail", "mace"):
        return
    c.as_basic("p622", "p1428", window="challenge")

    def on_crit(ev: Any) -> None:
        if _i_crit(c.world, c.me, ev) and _holding(c, "flail", "mace"):
            c.push(1, on=ev.target)

    c.watch(Hit, on_crit, on=c.me, until=When.ENCOUNTER)


@power("f2351", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a martial encounter power")
def f2351(c: Cast) -> None:
    """"Any ally, while adjacent to you" -- so the adjacency is asked per
    attack and the ally may walk in and out of it."""
    me = c.me
    gear = c.world.get(me, Gear)
    if gear is None or not any(
        w.group in ("axe", "hammer", "mace") and "versatile" in w.properties
        for w in gear.melee
    ):
        return
    c.as_basic("p622", "p4330", window="charge")

    def on_hit(ev: Any) -> None:
        p = get(ev.power)
        if ev.attacker != me or p is None:
            return
        if p.usage is not ENCOUNTER or Keyword.MARTIAL not in p.keywords:
            return
        for friend in [a for a in allies(c.world, me) if a != me]:
            c.bonus(
                AC, 2, on=friend, until=When.EONT, kind="feat",
                when=lambda ctx, f=friend: c.adjacent_to(f, me),
            )

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER)


@power("f1310", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit with a two-handed axe")
def f1310(c: Cast) -> None:
    """Splash damage on a crit. Every adjacent enemy, including the one
    that was hit if it is still standing beside you.

    A watch rather than a declared trigger, for the reason at the head
    of this file: the second benefit is a standing arrangement and a
    row the dispatcher only reaches on its trigger is never armed.
    """
    if not _grip(c, "axe", hands=2):
        return
    c.as_basic("p622", "p608", window="challenge")

    def on_crit(ev: Any) -> None:
        if not _i_crit(c.world, c.me, ev) or not _grip(c, "axe", hands=2):
            return
        for foe in enemies(c.world, c.me):
            if c.adjacent(to=foe):
                c.flat(c.str_mod, on=foe)

    c.watch(Hit, on_crit, on=c.me, until=When.ENCOUNTER)


@power("f1318", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1318(c: Cast) -> None:
    """Two adjacencies, both asked at the moment of the attack: the ally
    beside you and the attacker beside you."""
    me = c.me
    if not _grip(c, "pick", "spear", hands=1):
        return
    c.as_basic("p10503", "p4320", window="challenge")
    for friend in [a for a in allies(c.world, me) if a != me]:
        for defence in (AC, REF):
            c.bonus(
                defence, 2, on=friend, until=When.ENCOUNTER, kind="feat",
                when=lambda ctx, f=friend: (
                    c.adjacent_to(f, me)
                    and ctx.get("attacker") is not None
                    and c.adjacent(to=ctx["attacker"])
                ),
            )


@power("f1320", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you push an enemy")
def f1320(c: Cast) -> None:
    """"Any enemy you push", so the push itself is the trigger -- a hit
    knows nothing about whether anybody moved."""
    if not _holding(c, "polearm"):
        return
    c.as_basic("p200", "p4330", window="charge")

    def on_push(ev: Any) -> None:
        if _my_push(c.world, c.me, ev) and _holding(c, "polearm"):
            c.grants_advantage(on=ev.target, until=When.EONT)

    c.watch(ForcedMove, on_push, on=c.me, until=When.ENCOUNTER)


@power("f1322", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit with a one-handed axe")
def f1322(c: Cast) -> None:
    """Knock it down, and punish it for getting up.

    I marked the second clause `c.provokes_on_stand()` on the reasoning
    that standing is an action in the menu with nothing to hang off.
    **It is announced**: `actions.py:809` ends the prone effect with
    `why="stood up"`, so `ConditionEnded` separates getting up on
    purpose from an effect merely expiring. That is the whole clause,
    and it is a watch.

    `once=True` on the watch, because the card says "the first time it
    stands up".
    """
    if not _grip(c, "axe", hands=1):
        return
    me = c.me
    c.as_basic("p2131", "p608", window="opportunity")

    def on_crit(hit: Any) -> None:
        if not _i_crit(c.world, me, hit) or not _grip(c, "axe", hands=1):
            return
        foe = hit.target
        c.prone(on=foe)

        def on_stand(ev: Any) -> None:
            if (
                ev.target == foe
                and ev.condition is Condition.PRONE
                and ev.why == "stood up"
            ):
                c.provoke(me, on=foe, why="stood up beside you")

        c.watch(ConditionEnded, on_stand, on=foe, until=When.EONT, once=True)

    c.watch(Hit, on_crit, on=me, until=When.ENCOUNTER)


# -- the style family, now that the lists resolve --------------------------
#
# Each list is written out beside the row that uses it. They do not
# overlap the way the printed pairs suggest: `f1317` and `f1318` look
# like a lesser and a greater of the same style and share no member.


@power("f1311", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit an unbloodied enemy with an associated power",
       on=Trigger(Hit, hit_with_one_of("p917", "p1758", "p1063"),
                  "you hit with an associated power"))
def f1311(c: Cast) -> None:
    """A shift after hitting something still at full strength.

    "Unbloodied" is asked after the blow landed, which is the only
    reading that makes sense: a hit that bloodies the target leaves it
    bloodied, and the printed line is about picking on the healthy.
    """
    if not _holding(c, "heavy blade"):
        return
    if not c.bloodied(on=c.trigger.target):
        c.shift(2)


@power("f1319", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you crit with an associated power",
       on=Trigger(Hit, lambda w, me, ev: (
           ev.attacker == me and ev.critical
           and ev.power in ("p1758", "p1063")
       ), "you crit with an associated power"))
def f1319(c: Cast) -> None:
    if _holding(c, "polearm"):
        c.prone(on=c.trigger.target)


@power("f1321", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("Moved.squares",),
       trigger="you hit an unbloodied enemy with an associated power",
       on=Trigger(Hit, hit_with_one_of("p4541", "p10592", "p997"),
                  "you hit with an associated power"))
def f1321(c: Cast) -> None:
    """Punishes an unbloodied target for walking away.

    A watch on the creature rather than a standing modifier, and gated
    on the *distance*, which is the printed "more than 2 squares".

    `Moved` has `from_` and `to` and **no `squares`** -- I reached for
    one, and a `getattr` default would have made the whole row silently
    false. The distance is measured between the two ends instead, which
    is one move action rather than a turn's total: a creature that
    walks two squares twice does not pay. That is the wrong reading of
    the card, so the shortfall is named rather than left in prose.

    `once=True`, because it is one payment however far it runs.
    """
    if not _grip(c, "axe", hands=1):
        return
    foe = c.trigger.target
    if c.bloodied(on=foe):
        return
    hurt = c.con_mod

    def on_move(ev: Any) -> None:
        if ev.actor == foe and distance(ev.from_, ev.to) > 2:
            c.flat(hurt, on=foe)

    c.watch(Moved, on_move, on=foe, until=When.EONT, once=True)


@power("f2326", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2326(c: Cast) -> None:
    """An attack bonus with three named rows against a bloodied enemy.
    A standing modifier rather than a trigger, because it is read while
    the attack is being rolled rather than after it lands."""
    me = c.me
    picked = among("p2105", "p10592", "p620")
    c.bonus(
        "attack", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            picked(ctx)
            and _holding(c, "heavy blade")
            and c.bloodied(on=ctx.get("target"))
        ),
    )


@power("f2339", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with an associated power",
       on=Trigger(Hit, hit_with_one_of("p10591", "p4542", "p1758"),
                  "you hit with an associated power"))
def f2339(c: Cast) -> None:
    if _holding(c, "spear"):
        c.slowed(on=c.trigger.target, until=When.EONT)


@power("f2343", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit an enemy granting you combat advantage",
       on=Trigger(Hit, hit_with_one_of("p4541", "p10592", "p997"),
                  "you hit with an associated power"))
def f2343(c: Cast) -> None:
    """The advantage is read off the hit's own result rather than asked
    of the board again: a one-shot grant has already been spent by the
    time the hit is announced, which is exactly the case this is
    printed for."""
    if not _holding(c, "flail", "mace"):
        return
    result = getattr(c.trigger, "result", None)
    if result is not None and result.advantage:
        c.penalty("attack", 2, on=c.trigger.target, until=When.EONT)


@power("f2347", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2347(c: Cast) -> None:
    """A damage bonus, so the gate is in the *damage* context -- which
    carries no `advantage`. The board is asked instead, which is right
    here and wrong for `f2343`: damage is rolled inside the same swing,
    before any one-shot grant has been cleared."""
    from combat_engine.engine.query import has_combat_advantage

    me = c.me
    picked = among("p2248", "p1505", "p1000", "p620")
    gear_ok = lambda: any(  # noqa: E731
        w.group in ("axe", "hammer", "mace") and "versatile" in w.properties
        for w in (c.world.get(me, Gear).melee if c.world.get(me, Gear) else ())
    )
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            picked(ctx)
            and gear_ok()
            and ctx.get("target") is not None
            and has_combat_advantage(c.world, me, ctx["target"])
        ),
    )


@power("f1317", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1317(c: Cast) -> None:
    """The skill bonus stands whatever is in hand; the substitution is
    gated on the weapon **and** on the shield, both asked once as the
    fight opens, which is where every other weapon-style row asks."""
    c.bonus("skill:insight", 2, on=c.me, until=When.ENCOUNTER, kind="feat")
    if _grip(c, "pick", "spear", hands=1) and c.wielding("shield"):
        c.as_basic("p2099", "p10888", window="opportunity")


@power("f2331", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.retarget_defence()",))
def f2331(c: Cast) -> None:
    """`p4541`, `p10471` or `p10593` may hit Reflex instead of AC. The
    list resolves; the defence a row rolls against is header data and
    four item blocks want the same verb."""


@power("f2071", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("feat.associated_powers", "c.coup_de_grace(bonus=)"))
def f2071(c: Cast) -> None:
    """The list is absent from the spec, but **not** from the page --
    that diagnosis was wrong. The card prints three members; an errata
    block sits between the benefit and the list, and `etl/feat._benefit`
    stops at an errata heading and takes the rest of its paragraph with
    it, so the list is cut off before the sanitiser ever sees it. Twelve
    other rows lose theirs the same way. Nothing here can be written
    until that truncation stops.

    Its other clause -- extra damage on a coup de grace -- has the verb
    but no way to add to what one deals.
    """


@power("f2332", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.retarget_defence()", "c.on_shift_away()"))
def f2332(c: Cast) -> None:
    """Both halves are gaps and they are different ones. `p622` and
    `p1019` may hit Reflex instead of AC, and the defence a row rolls
    against is header data. The other wants "an adjacent enemy shifts
    away from you", and while `Moved.kind_` is `"shift"` the event says
    nothing about which creature it went away from."""


# -- the swings Combat Challenge hands over ---------------------------------

#: The row the punishment is written as. The feature these prerequisites
#: name is the mark; `p7419` is the swing it allows, and `p7419` is what
#: calls `c.basic`, so that is the ref the grant is stamped with.
CHALLENGE = "p7419"


def _challenged(c: Cast, ev: Any) -> list[int]:
    """Who the swing Combat Challenge granted actually hit."""
    if ev.actor != c.me or ev.granted_by != c.me or ev.granted_via != CHALLENGE:
        return []
    return [roll.target for roll in ev.rolls if roll.hit]


@power("f1732", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1732(c: Cast) -> None:
    """Resistance is shrugged off inside `deal_damage`, so this is a
    standing waiver gated on the damage context rather than anything
    hung on the hit. No amount and no type: "all resistances"."""
    c.ignore_resistance(
        on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: (
            ctx.get("granted_by") == c.me and ctx.get("granted_via") == CHALLENGE
        ),
    )


@power("f1736", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1736(c: Cast) -> None:
    """"After you hit" -- so the use, not the `Hit`, which is announced
    with the blow still in the air."""
    def after(ev: Any) -> None:
        if _challenged(c, ev):
            c.shift(1)

    c.watch(PowerResolved, after, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} riposte shift")


@power("f2180", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2180(c: Cast) -> None:
    """Extra damage of the racial power's own type, which is a build
    choice `c.element` records -- the same read `p1448` itself makes.

    A separate packet rather than a damage modifier, because the type
    differs from the swing's and `deal_damage` takes one type per
    packet. The paragon and epic steps are out of scope.
    """
    def after(ev: Any) -> None:
        for foe in _challenged(c, ev):
            c.flat(3, dtype=c.element(on=c.me) or DamageType.UNTYPED, on=foe)

    c.watch(PowerResolved, after, until=When.ENCOUNTER, on=c.me,
            label=f"{c.ref} riposte damage")


@power("f795", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.race_option()", "c.deals(when=)"))
def f795(c: Cast) -> None:
    """**Re-aimed.** The granted swing is readable now -- it carries
    `granted_via`, and `f1732` beside it gates on exactly that. What is
    left is the other two thirds of the sentence: which manifestation a
    genasi is currently in is the choice `rt:r33-manifestation` says is
    recorded nowhere, and retyping one attack's damage is `c.deals` with
    a gate, which it does not take."""


# -- the rest of the gaps, each named exactly -------------------------------


@power("f798", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1628 against an enemy you have marked",
       on=Trigger(PowerUsed, used_one_of("p1628"),
                  "you use that racial power"))
def f798(c: Cast) -> None:
    """An attack bonus against a marked enemy the racial power was used
    on.

    "Until it is no longer marked by you" is not a `When`, so the hold
    runs to the end of the encounter and the gate asks the mark again on
    every roll -- which expires it at the right moment and, unlike a
    fixed duration, also gives it back if the enemy is marked afresh.
    Untyped: the card prints no word in front of the bonus.
    """
    for foe in c.trigger.targets:
        if not c.marked(on=foe):
            continue
        c.bonus(
            "attack", 1, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx, foe=foe: (
                ctx.get("target") == foe and c.marked(on=foe)
            ),
        )


@power("f803", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("ConditionApplied.power",))
def f803(c: Cast) -> None:
    """An attack bonus with one racial power, and damage to whatever it
    knocks down.

    A standing modifier rather than a trigger: the bonus is asked of
    every roll and `among` reads the ref off the attack context.

    The second clause is dropped. `ConditionApplied` carries `source`,
    `target`, `condition` and `duration` and **not** the power that
    applied them, so "enemies knocked prone *by this power*" cannot be
    told from any other prone this fighter lays -- and a watch without
    that gate would pay Strength-modifier damage on every one of them.
    """
    c.bonus("attack", 1, on=c.me, until=When.ENCOUNTER, when=among("p1767"))


@power("f805", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_reroll()",))
def f805(c: Cast) -> None:
    """Refunds `p1450` when the reroll it bought misses anyway. The power
    is named by ref and `c.restore_use` takes one -- what is missing is
    that nothing announces a roll was a reroll, which is the symbol the
    ranger's f761 dropped a clause for."""


@power("f948", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.forbid_action()",))
def f948(c: Cast) -> None:
    """A prone creature you are grabbing cannot stand. `c.grabbing`
    answers the grab and `Condition.PRONE` the rest, but standing is a
    line in the action menu that nothing can take away -- `c.grant_action`
    adds one and there is no opposite."""


@power("f1733", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.feature_ability()",))
def f1733(c: Cast) -> None:
    """Swaps which ability a named class feature reads. The feature is
    `cf:fighter-weaponmaster-f2` and is named by ref in this feat's own
    prerequisite, so this is not a naming gap -- the ability is written
    into that feature's body and nothing rewrites one."""


@power("f1738", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_shift_away()",))
def f1738(c: Cast) -> None:
    """An interrupt when a marked neighbour shifts or attacks past you.
    The attack half could be said off `AttackDeclared`; the shift half
    cannot, for the same reason f2332 cannot, and a row that answered
    only half its trigger would fire on the wrong occasions rather than
    on too few."""


@power("f1739", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.extend()",),
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f1739(c: Cast) -> None:
    """The extra hit points play. Lengthening the second wind's own
    defence bonus does not: nothing moves a standing effect's duration,
    and re-laying it would stack rather than replace."""
    if not holding(c.world, c.me, "shield") or c.wis_mod <= 0:
        return
    c.heal(c.wis_mod, on=c.me)


@power("f1741", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("query.shield_bonus()",))
def f1741(c: Cast) -> None:
    """"Your shield bonus also applies to Fortitude." `Gear.shield` is a
    bool and the light-or-heavy number was folded into the defence
    totals at spawn, so the amount to apply is not recoverable -- which
    is a different gap from not knowing whether a shield is held."""


@power("f1743", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1743(c: Cast) -> None:
    """Wisdom instead of Dexterity on initiative.

    `Initiative.bonus` is read before the d20, and a trait is armed
    *after* the opening rolls -- so setting the component is too late for
    the fight it matters most in. `c.initiative` exists for exactly this
    and moves the creature in the order after the fact, which is what
    `Encounter.adjust_initiative` is for. The adjustment is the
    difference between the two abilities, so it is a swap and not a
    second bonus.

    The Insight and Perception halves are checks, not a fight.
    """
    c.initiative(c.wis_mod - c.dex_mod, on=c.me)


@power("f1969", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.reroll_ones()",))
def f1969(c: Cast) -> None:
    """Lets the ally you flank with reroll damage dice showing a 1.

    The flanking half is written and is the gate the printed line puts
    first; the reroll is dropped, because `c.reroll_damage` rolls the
    whole expression twice, which is a different and better outcome than
    rerolling the ones. The same symbol the assassin's f1789 wants.
    """
    me = c.me
    if not _grip(c, *_ONE_HANDED, "polearm", hands=2):
        return
    for friend in [a for a in allies(c.world, me) if a != me]:
        c.bonus(
            "damage", 0, on=friend, until=When.ENCOUNTER,
            when=lambda ctx, f=friend: (
                ctx.get("target") is not None
                and flanked_by(c.world, ctx["target"], me)
                and flanked_by(c.world, ctx["target"], f)
            ),
        )


@power("f1970", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("spec.power_ref()",))
def f1970(c: Cast) -> None:
    """+1 damage with the weapon style chosen for a class feature. The
    prerequisite is an unparsed clause, the feature is named in prose,
    and the style it records is not asked anywhere."""
