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
from combat_engine.engine.events import (
    AttackDeclared,
    ConditionApplied,
    ForcedMove,
    Moved,
    PowerResolved,
    RelationCleared,
    RelationSet,
)
from combat_engine.engine.grid import distance, neighbours
from combat_engine.engine.query import allies, enemies, holding
from combat_engine.engine.types import Forced, Relation

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


@power("f1321", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit an unbloodied enemy with an associated power",
       on=Trigger(Hit, hit_with_one_of("p4541", "p10592", "p997"),
                  "you hit with an associated power"))
def f1321(c: Cast) -> None:
    """Punishes an unbloodied target for walking away.

    `Moved` has `from_` and `to` and **no `squares`**, which this row
    carried a marker for -- and does not need one. Every step announces
    both its ends, so the printed "more than 2 squares before the end of
    its next turn" is the *running total* of `distance(from_, to)`.
    Reading one move on its own, which is what was here, let a creature
    walk two squares twice and pay nothing.

    One payment however far it runs, so the tally latches once spent --
    `once=True` on the watch would end it on the first step instead.
    `EOTNT`, not `EONT`: the clock the card names is the enemy's.
    """
    if not _grip(c, "axe", hands=1):
        return
    foe = c.trigger.target
    if c.bloodied(on=foe):
        return
    hurt = c.con_mod
    walked = [0]

    def on_move(ev: Any) -> None:
        if ev.actor != foe or walked[0] < 0:
            return
        walked[0] += distance(ev.from_, ev.to)
        if walked[0] > 2:
            walked[0] = -1
            c.flat(hurt, on=foe)

    c.watch(Moved, on_move, on=foe, until=When.EOTNT)


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
       reach=PERSONAL, target=SELF, dropped=("c.retarget_defence()",))
def f2331(c: Cast) -> None:
    """**Re-aimed from `todo` to `dropped`.** The card has two printed
    sentences and only the second is missing: `p4541`, `p10471` or
    `p10593` may hit Reflex instead of AC, and the defence a row rolls
    against is header data with no verb to move it -- four item blocks
    want the same one. The skill bonus is the whole of the first
    sentence, stands whatever is in hand, and is worth playing."""
    c.bonus("skill:perception", 2, on=c.me, until=When.ENCOUNTER, kind="feat")


@power("f2071", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.coup_de_grace(bonus=)",))
def f2071(c: Cast) -> None:
    """**Re-aimed.** The truncation this row was marked for is fixed:
    the spec prints all three associated refs now, so the long clause is
    an ordinary gated damage bonus and the row plays.

    Two modifiers rather than one, because +5 for helpless or
    immobilized *replaces* the +2 for slowed rather than adding to it,
    and both are untyped, which stacks. So the +2 excludes the case the
    +5 covers.

    The coup de grace half is dropped: `c.coup_de_grace` rolls the whole
    finisher itself and the damage context has no key saying a blow is
    one, so "1[W] extra on a coup de grace" has nothing to gate on.
    """
    me = c.me
    picked = among("p10592", "p1758", "p620")

    def pinned_down(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return foe is not None and (
            c.is_(Condition.HELPLESS, on=foe) or c.is_(Condition.IMMOBILIZED, on=foe)
        )

    def slowed_only(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return (
            foe is not None
            and not pinned_down(ctx)
            and c.is_(Condition.SLOWED, on=foe)
        )

    c.bonus("skill:intimidate", 2, on=me, until=When.ENCOUNTER, kind="feat")
    c.bonus("damage", 5, on=me, until=When.ENCOUNTER,
            when=lambda ctx: (picked(ctx) and _grip(c, "axe", hands=2)
                              and pinned_down(ctx)))
    c.bonus("damage", 2, on=me, until=When.ENCOUNTER,
            when=lambda ctx: (picked(ctx) and _grip(c, "axe", hands=2)
                              and slowed_only(ctx)))


def _where(world, who: int):  # noqa: ANN001, ANN202
    pos = world.get(who, Position)
    return pos.square if pos is not None else None


def _shifted_away(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """An enemy that was next to me shifted, and ended further off.

    `Moved` rather than `MoveEnd`, because by the end the creature has
    gone and "adjacent" is false exactly when the row should fire. It is
    the one movement event carrying `from_`, so the adjacency is asked
    of where the enemy *was* and the direction is the two ends compared.
    """
    if getattr(ev, "kind_", "") != "shift" or ev.actor not in enemies(world, me):
        return False
    here = _where(world, me)
    if here is None:
        return False
    was = distance(ev.from_, here)
    return was <= 1 and distance(ev.to, here) > was


def _marked_by_my_side(c: Cast, foe: int) -> bool:
    return any(c.marked(on=foe, by=a) for a in allies(c.world, c.me))


@power("f2332", level=1, cls="", usage=AT_WILL,
       action=ActionType.IMMEDIATE_REACTION, reach=PERSONAL, target=SELF,
       dropped=("c.retarget_defence()",),
       trigger="an adjacent enemy marked by you or an ally shifts away",
       on=Trigger(Moved, _shifted_away, "an adjacent enemy shifts away"))
def f2332(c: Cast) -> None:
    """**Re-aimed.** "An adjacent enemy shifts away from you" is
    sayable after all -- see `_shifted_away`, which asks the adjacency of
    `Moved.from_` rather than of where the creature is once it has gone.
    The printed action is the limit, so this is at-will and an immediate
    reaction rather than a once-a-fight trait (#210).

    Still dropped: `p622` and `p1019` hitting Reflex instead of AC is
    header data, the same gap `f2331` names.
    """
    if not _grip(c, "hammer", "pick", hands=1):
        return
    if _marked_by_my_side(c, c.trigger.actor):
        c.shift(1)


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
       todo=("c.deals(when=)",))
def f795(c: Cast) -> None:
    """**Re-aimed twice, and down to one symbol.** The granted swing is
    readable -- it carries `granted_via`, and `f1732` beside it gates on
    exactly that. Which manifestation the character is in is readable
    too: `rt:r33-t0` no longer claims the choice is recorded
    nowhere, it is the one of the thirteen racial rows in `Powers.known`,
    and `c.element` names the type that leg is sworn to.

    What is genuinely left is the middle of the sentence: retyping one
    attack's damage. `c.deals` is an unconditional override held as a
    labelled effect and read by `Cast._retyped`, which sees no context,
    so "only the swing Combat Challenge granted" cannot be attached to
    it. Laying and ending the override around the swing would recolour
    everything else in the window, which is worse than not saying it."""


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
       reach=PERSONAL, target=SELF)
def f803(c: Cast) -> None:
    """An attack bonus with one racial power, and damage to whatever it
    knocks down.

    A standing modifier rather than a trigger: the bonus is asked of
    every roll and `among` reads the ref off the attack context.

    **The second clause no longer needs `ConditionApplied.power`.** That
    event does carry no power, but the question is answerable without
    one: `PowerUsed` is announced *before* the body runs and its targets
    are already chosen, so the set of targets still standing is taken
    there and compared against the same set once `PowerResolved` lands.
    Whoever went down in between was knocked down by this row and by
    nothing else, which is stricter than a gate on the event would be.
    """
    me = c.me
    upright: set[int] = set()

    def before(ev: Any) -> None:
        if ev.actor != me or ev.power != "p1767":
            return
        upright.clear()
        upright.update(
            t for t in ev.targets if not c.is_(Condition.PRONE, on=t)
        )

    def after(ev: Any) -> None:
        if ev.actor != me or ev.power != "p1767":
            return
        for foe in upright:
            if c.is_(Condition.PRONE, on=foe):
                c.flat(c.str_mod, on=foe)
        upright.clear()

    c.bonus("attack", 1, on=me, until=When.ENCOUNTER, when=among("p1767"))
    c.watch(PowerUsed, before, until=When.ENCOUNTER, on=me, label=f"{c.ref} before")
    c.watch(PowerResolved, after, until=When.ENCOUNTER, on=me, label=f"{c.ref} after")


@power("f805", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you reroll an opportunity attack with p1450 and miss",
       on=Trigger(PowerResolved, used_one_of("p1450"), "you use p1450"))
def f805(c: Cast) -> None:
    """Refunds `p1450` when the reroll it bought misses anyway.

    Nothing announces that a roll *was* a reroll and nothing has to:
    `p1450` is an interrupt on `AttackRolled` whose whole body is the
    reroll, so the attack that event names is the rerolled one by
    construction. `PowerResolved.trigger` hands it over and it carries
    `opportunity` as a plain attribute, which is this card's gate where
    the rogue's `f819` reads `advantage` off the same event.

    The outcome is recomputed after the interrupt window, so the miss is
    waited for rather than read.
    """
    rolled = c.trigger.trigger
    if rolled is None or not getattr(rolled, "opportunity", False):
        return
    victim = rolled.target

    def refund(ev: Miss) -> None:
        if ev.attacker == c.me and ev.target == victim:
            c.restore_use("p1450")

    c.watch(Miss, refund, on=c.me, until=When.EOT, once=True)


@power("f948", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f948(c: Cast) -> None:
    """A prone creature you are grabbing cannot stand.

    This was marked for `c.forbid_action()` on the grounds that standing
    is a menu line nothing can take away. It can: `Condition.PINNED` is
    `Rules(no_stand=True)` and `actions.legal` reads it, which is the
    printed sentence exactly and not an approximation.

    Both halves of "prone *and* grabbed" can arrive in either order, so
    each is watched and the other is asked of the board.

    **The grab's end is a `RelationCleared`, not a `ConditionEnded`.**
    A grab is a relation mirrored into `Conditions`, and `Effects.cure`
    clears the relation without announcing the condition -- so a watch
    on `ConditionEnded` never fired and the pin outlived the grab. That
    was driven by hand both ways before this was written.
    """
    me = c.me

    def hold(who: int) -> None:
        if who in c.grabbing(of=me) and c.is_(Condition.PRONE, on=who):
            c.condition(Condition.PINNED, on=who, until=When.ENCOUNTER)

    def on_prone(ev: ConditionApplied) -> None:
        if ev.condition is Condition.PRONE:
            hold(ev.target)

    def on_grab(ev: RelationSet) -> None:
        if ev.kind_ is Relation.GRABBED_BY and ev.source == me:
            hold(ev.target)

    def loose(ev: RelationCleared) -> None:
        if ev.kind_ is Relation.GRABBED_BY and ev.source == me:
            c.cure(Condition.PINNED, on=ev.target)

    for foe in c.grabbing(of=me):
        hold(foe)
    c.watch(ConditionApplied, on_prone, until=When.ENCOUNTER, on=me,
            label=f"{c.ref} prone")
    c.watch(RelationSet, on_grab, until=When.ENCOUNTER, on=me,
            label=f"{c.ref} grab")
    c.watch(RelationCleared, loose, until=When.ENCOUNTER, on=me,
            label=f"{c.ref} free")


@power("f1733", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1733(c: Cast) -> None:
    """Swaps which ability `cf:fighter-weaponmaster-f2` reads.

    Nothing rewrites a feature's body, and nothing has to. That feature
    lays one untyped attack bonus of the caster's Wisdom modifier gated
    on `opportunity`, and untyped bonuses **add** -- so the difference
    between the two abilities, laid under the same gate, comes to the
    Dexterity modifier and nothing else. Negative differences bucket by
    the row's own ref, so a Dexterity-poorer fighter subtracts cleanly
    instead of colliding with somebody else's penalty.

    The brawling leg takes `cf:fighter-weaponmaster-f0` in place of that
    feature and gets no bonus to correct, so it is left alone.
    """
    if c.build("brawling"):
        return
    c.bonus("attack", c.dex_mod - c.wis_mod, on=c.me, until=When.ENCOUNTER,
            kind="untyped", when=lambda ctx: bool(ctx.get("opportunity")))


def _adjacent_enemy_shifts(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """A neighbour of mine shifted. Where it went is not this card's
    business -- only that it was next to me when it started."""
    if getattr(ev, "kind_", "") != "shift" or ev.actor not in enemies(world, me):
        return False
    here = _where(world, me)
    return here is not None and distance(ev.from_, here) <= 1


def _adjacent_enemy_swings_elsewhere(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """`AttackDeclared` is announced once per target and names one, so
    "an attack that doesn't include you as a target" is that one field.
    `leaves_me_out` reads `among`, which this event does not carry."""
    if ev.attacker == me or ev.target == me or ev.attacker not in enemies(world, me):
        return False
    here, there = _where(world, me), _where(world, ev.attacker)
    return here is not None and there is not None and distance(there, here) <= 1


@power("f1738", level=1, cls="", usage=AT_WILL,
       action=ActionType.IMMEDIATE_INTERRUPT, reach=PERSONAL, target=SELF,
       trigger="a marked adjacent enemy shifts or attacks past you",
       on=(Trigger(Moved, _adjacent_enemy_shifts, "a marked neighbour shifts"),
           Trigger(AttackDeclared, _adjacent_enemy_swings_elsewhere,
                   "a marked neighbour attacks somebody else")))
def f1738(c: Cast) -> None:
    """An interrupt when a marked neighbour shifts or attacks past you.

    Both halves are sayable and the row is declared against both, which
    is what `on=` taking a sequence is for. The shift half was marked
    unwritable; it is not, because `Moved` carries `from_` and the
    adjacency the card names is the one *before* the step.

    The printed action is the limit, so at-will and an immediate
    interrupt rather than a once-a-fight trait (#210).
    """
    if not holding(c.world, c.me, "shield"):
        return
    ev = c.trigger
    foe = ev.actor if isinstance(ev, Moved) else ev.attacker
    if not c.marked(on=foe, by=c.me):
        return
    friend = c.choose(c.within(1, side="ally"), "which ally")
    if friend is None:
        return
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=friend, until=When.SONT)


@power("f1739", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use your second wind",
       on=Trigger(SecondWind, about_me, "you use your second wind"))
def f1739(c: Cast) -> None:
    """Extra hit points, and the defence bonus held a turn longer.

    Nothing moves a standing effect's duration, which is what this was
    marked for -- but the duration does not have to move. `second_wind`
    lays +2 to each defence until the start of the caster's next turn,
    untyped, and untyped modifiers add. So the window that wants
    changing is the only one written: the row cancels the short bonus
    where it overlaps and lays its own to the end of the next turn, and
    the creature is +2 throughout rather than +4 and then nothing.

    A penalty buckets by the ref of the row that laid it, so the -2 is
    this row's alone and cannot swallow anybody else's.
    """
    if not holding(c.world, c.me, "shield"):
        return
    if c.wis_mod > 0:
        c.heal(c.wis_mod, on=c.me)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, -2, on=c.me, until=When.SONT)
        c.bonus(defence, 2, on=c.me, until=When.EONT)


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
       reach=PERSONAL, target=SELF, todo=("c.reroll_ones(when=)",))
def f1969(c: Cast) -> None:
    """Lets the ally you flank with reroll damage dice showing a 1.

    **Re-aimed from `dropped` to `todo`.** The whole printed benefit is
    the reroll; what was written beside the marker was a flanking gate
    on a bonus of *zero*, which lays an effect, satisfies the audit and
    changes no number in any fight. A row that plays and does nothing is
    worse than one that is refused, so the gate goes with it.

    `c.reroll_damage` is not the verb: it rolls the whole expression
    again, which is a different and better outcome than rerolling the
    ones. The same symbol the assassin's f1789 wants.
    """


@power("f1970", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("Gear.off_hand", "Build.armour", "Weapon.improvised"))
def f1970(c: Cast) -> None:
    """+1 damage with the weapon style chosen for a class feature.

    The style is asked now: every leg of `chargen.BUILDS["fighter"]` is
    one of the six printed talents, and `cf:fighter-weaponmaster-f3`
    reads two of them as a grip. This is the same gate on the damage
    side, and it checks what is in hand rather than restating the leg --
    a fighter on the great-weapon leg who has swapped to one hand is not
    getting it.

    The other four legs are the ones `cf:fighter-talent-rest` is blocked
    on and the symbols are its: an empty or occupied off hand, an armour
    field on `Build`, and improvised weapons. Each would be a gate that
    is false for every fighter in the tree, so they are dropped rather
    than guessed at.
    """
    me, world = c.me, c.world
    if not (c.build("great-weapon") or c.build("guardian")):
        return
    two_handed = c.build("great-weapon")

    def style(ctx: dict[str, Any]) -> bool:
        declared = get(str(ctx.get("power", "")))
        gear = world.get(me, Gear)
        held = gear.main if gear is not None else None
        return (
            declared is not None
            and Keyword.WEAPON in declared.keywords
            and held is not None
            and held.two_handed == two_handed
        )

    c.bonus("damage", 1, on=me, until=When.ENCOUNTER, when=style)
