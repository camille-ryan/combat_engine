"""Warlord feats, the second batch.

Three things run through this list.

**Combat Leader is implemented, under another name.** The feats gate on
`cf:warlord-marshal-f3`; the tree declares the same feature as
`cf:warlord-marshal-f3` in `features/leaders_sc.py`, hand-named before
the class-feature table existed. That mismatch is worth knowing and is
not worth working around here: the printed question is "an ally who
benefits from Combat Leader", and the feature's own body says what that
means -- an ally within 10 who can see you. `_led` asks it the same
way, so the two cannot disagree about the set.

**"You can choose to use this feat" is a real gap and there are five of
them.** Each prints a cost and a payoff -- take a -2 to hit and an ally
gains damage; charge and knock prone, but a miss lets the enemy swing
back. The engine has no way for a row to offer a *deal* at the moment
of an attack, so writing them would either hand out the payoff free or
charge the cost unasked. `c.opt_in()`.

**The action point is the warlord's best-served trigger.**
`ActionPointSpent` is real and points are really spent, so four more
rows here are ordinary.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    ENCOUNTER,
    FREE,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    ActionPointSpent,
    ActionType,
    Cast,
    DamageType,
    Gear,
    Hit,
    InitiativeRolled,
    Keyword,
    Miss,
    PowerUsed,
    Ranged,
    SecondWind,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.query import allies, distance_between, enemies, team

from .styles import among, hit_with_one_of


def _used_wrath(world, me: int, ev) -> bool:  # noqa: ANN001
    return ev.actor == me and ev.power == "p1628"

#: A row that offers a deal -- a cost for a payoff -- at the moment of an
#: attack. Nothing in the engine asks that question.
OPT_IN = ("c.opt_in()",)
#: **A standing clause and a triggered one on the same card.** The
#: dispatcher only reaches a no-action row when its declared trigger
#: fires, so a row that also has to be *true* from the start of the
#: fight -- "you can use this in place of a melee basic attack" is --
#: is never armed. Those rows keep the printed Trigger as text and
#: answer it with `c.watch`, the shape `p7419` already uses.
#: …nor turn a melee row into a ranged one.
AS_RANGED = ("c.recast(reach=)",)
#: A racial power named in prose rather than by ref.
RACIAL = ("c.on_racial_power()",)

#: Inspiring word, named by ref in three of these prerequisites.
WORD = "p1590"


def _led(c: Cast) -> list[int]:
    """The allies Combat Leader reaches.

    Asked the way the feature itself asks it -- within 10 and able to
    see me -- rather than by looking for a mark the feature does not
    leave. Two versions of one question are two chances to disagree.
    """
    me = c.me
    return [
        a for a in allies(c.world, me)
        if a != me and distance_between(c.world, me, a) <= 10 and c.can_see(a)
    ]


def _my_point(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me


def _ally_point(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    from combat_engine.engine.query import team

    return ev.actor != me and team(world, ev.actor) == team(world, me)


def _my_word(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.actor == me and ev.power == WORD


def _i_crit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and ev.critical


def _my_martial_encounter_miss(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.attacker == me and p is not None
        and p.usage is ENCOUNTER and Keyword.MARTIAL in p.keywords
    )


def _my_martial_encounter_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return _my_martial_encounter_miss(world, me, ev)


def _holding(c: Cast, *groups: str) -> bool:
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return False
    carried = (*gear.melee, *([gear.ranged] if gear.ranged else ()))
    return any(w.group in groups for w in carried)


def _versatile(c: Cast, *groups: str) -> bool:
    gear = c.world.get(c.me, Gear)
    return gear is not None and any(
        w.group in groups and "versatile" in w.properties for w in gear.melee
    )


# -- the action point -------------------------------------------------------


def _ally_in_sight(world: Any, me: int, ev: Any) -> bool:
    """An ally other than you, with a clear line to you.

    Line of *sight* is not modelled; `line_of_effect` is the nearest thing
    the grid has and it is the same question about walls.
    """
    from combat_engine.engine.components import Position

    who = getattr(ev, "actor", None)
    if who is None or who == me or team(world, who) is not team(world, me):
        return False
    a, b = world.get(who, Position), world.get(me, Position)
    return (a is not None and b is not None
            and world.grid.line_of_effect(a.square, b.square))


@power("f2064", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally in your line of sight spends an action point",
       on=Trigger(ActionPointSpent, _ally_point, "an ally spends a point"))
def f2064(c: Cast) -> None:
    """"Before or after the attack" is a choice with no way to say the
    ordering, and the point is already spent by the time this is
    offered -- so the slide happens now, which is "before"."""
    who = c.trigger.actor
    if c.can_see(who):
        c.slide(1, on=who)


@power("f2065", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you spend an action point to make an extra attack",
       on=Trigger(ActionPointSpent, _my_point, "you spend an action point"))
def f2065(c: Cast) -> None:
    """Half the Intelligence modifier, rounded down, on one nearby ally's
    next swing. The bonus is spent on the first roll rather than left
    standing, which is what "his or her next attack roll" says."""
    me = c.me
    near = [
        a for a in allies(c.world, me)
        if a != me and distance_between(c.world, me, a) <= 3
    ]
    if not near:
        return
    c.bonus("attack", c.int_mod // 2, on=near[0], until=When.EONT, once=True)


@power("f2302", level=1, cls="", usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="an ally you can see spends an action point",
       on=Trigger(ActionPointSpent, _ally_point, "an ally spends a point"))
def f2302(c: Cast) -> None:
    who = c.trigger.actor
    if not c.can_see(who):
        return
    amount = 5 + c.level // 2
    for dtype in (DamageType.FIRE, DamageType.POISON):
        c.resist(amount, dtype, on=who, until=When.EONT)


# -- inspiring word, which is a ref -----------------------------------------


@power("f2063", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=NO_TARGET,
       trigger="you use p1590",
       on=Trigger(PowerUsed, _my_word, "you use inspiring word"))
def f2063(c: Cast) -> None:
    """`PowerUsed.targets` is a list, and inspiring word aims at one --
    but the plural is what the event carries and reading a singular
    through `getattr` is how a row ends up silently inert."""
    for who in c.trigger.targets:
        c.temp_hp(c.cha_mod, on=who)


@power("f822", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.bonus(healing)",))
def f822(c: Cast) -> None:
    """Adds Intelligence to what inspiring word restores. The power is a
    ref and `PowerUsed` fires before its body -- but the amount is
    computed inside that body by `c.heal`, and `Mods` is not consulted
    for healing at all, so there is nothing to add to."""


# -- Combat Leader ----------------------------------------------------------


@power("f2057", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2057(c: Cast) -> None:
    """"Until the end of his or her first turn" is `When.EOT` measured on
    the ally rather than on me, which is what `on=` already means: the
    effect's clock is the creature it sits on, and the first turn of the
    fight is the next one that creature takes."""
    for friend in _led(c):
        c.bonus(AC, 2, on=friend, until=When.EOT)


@power("f2062", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you roll initiative",
       on=Trigger(InitiativeRolled, lambda w, me, ev: ev.actor == me,
                  "you roll initiative"))
def f2062(c: Cast) -> None:
    """Declared on the event rather than as a trait: `triggers.arm` runs
    before `_roll_initiative` and traits are armed after, so a trait
    could never answer the opening roll."""
    for friend in _led(c):
        c.slide(1, on=friend)


@power("f2055", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you roll initiative",
       on=Trigger(InitiativeRolled, lambda w, me, ev: ev.actor == me,
                  "you roll initiative"))
def f2055(c: Cast) -> None:
    """Trades four points of your own place in the order for two allies'.

    `c.initiative` moves a creature in the order after the roll, which
    is the only thing that can say this -- `Initiative.bonus` is read
    before the d20 and would be too late.

    The two bonuses are different sizes and the card does not say which
    ally gets which, so the larger goes to the ally standing further
    off: the one with furthest to come is the one worth moving up.
    """
    friends = sorted(
        _led(c), key=lambda a: distance_between(c.world, c.me, a), reverse=True
    )
    if not friends:
        return
    c.initiative(-4, on=c.me)
    bigger, smaller = sorted((c.cha_mod, c.int_mod), reverse=True)
    c.initiative(bigger, on=friends[0])
    if len(friends) > 1:
        c.initiative(smaller, on=friends[1])


# -- the style greaters -----------------------------------------------------


@power("f2072", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit with a two-handed axe")
def f2072(c: Cast) -> None:
    gear = c.world.get(c.me, Gear)
    if gear is None or not any(
        w.group == "axe" and w.two_handed for w in gear.melee
    ):
        return
    c.as_basic("p1556", "p4567", window="opportunity")

    def on_crit(ev: Any) -> None:
        if not _i_crit(c.world, c.me, ev):
            return
        for foe in enemies(c.world, c.me):
            if c.adjacent(to=foe):
                c.flat(c.str_mod, on=foe)

    c.watch(Hit, on_crit, on=c.me, until=When.ENCOUNTER)


@power("f2327", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you miss with a martial encounter power")
def f2327(c: Cast) -> None:
    if not _holding(c, "heavy blade"):
        return
    c.as_basic("p158", "p450", window="opportunity")

    def on_miss(ev: Any) -> None:
        if not _my_martial_encounter_miss(c.world, c.me, ev):
            return
        if not _holding(c, "heavy blade"):
            return
        foe = ev.target
        c.bonus(
            "attack", 2, on=c.me, until=When.EONT, once=True,
            when=lambda ctx: ctx.get("target") == foe,
        )

    c.watch(Miss, on_miss, on=c.me, until=When.ENCOUNTER)


@power("f2342", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2342(c: Cast) -> None:
    """`Size.order`, not `>`: `Size` is a `StrEnum` and a bare comparison
    sorts the words alphabetically."""
    me = c.me
    if _holding(c, "spear"):
        c.as_basic("p1556", "p450", window="charge")
    mine = c.size_of(me)
    c.bonus(
        "damage", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            _holding(c, "spear")
            and ctx.get("target") is not None
            and c.size_of(ctx["target"]).order > mine.order
        ),
    )


@power("f2344", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you score a critical hit")
def f2344(c: Cast) -> None:
    if not _holding(c, "flail", "mace"):
        return
    c.as_basic("p4567", "p1065", window="charge")

    def on_crit(ev: Any) -> None:
        if _i_crit(c.world, c.me, ev) and _holding(c, "flail", "mace"):
            c.grants_advantage(on=ev.target, until=When.EONT, to="team")

    c.watch(Hit, on_crit, on=c.me, until=When.ENCOUNTER)


@power("f2348", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you hit with a martial encounter power")
def f2348(c: Cast) -> None:
    me = c.me
    if not _versatile(c, "axe", "hammer", "mace"):
        return
    c.as_basic("p1074", "p1065", window="charge")

    def on_hit(ev: Any) -> None:
        if not _my_martial_encounter_hit(c.world, me, ev):
            return
        for friend in [a for a in allies(c.world, me) if a != me]:
            c.bonus(
                AC, 2, on=friend, until=When.EONT, kind="feat",
                when=lambda ctx, f=friend: c.adjacent_to(f, me),
            )

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER)


@power("f2333", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.on_shift_away()",),
       trigger="you hit with an associated power",
       on=Trigger(Hit, hit_with_one_of("p158", "p1075"),
                  "you hit with an associated power"))
def f2333(c: Cast) -> None:
    """An ally's free shift on a named hit. The feat's other clause --
    shifting yourself when an adjacent marked enemy shifts away -- is
    dropped, because `Moved.kind_` says a shift happened and nothing
    says which creature it went away from."""
    me = c.me
    if not _holding(c, "hammer", "pick"):
        return
    near = [
        a for a in allies(c.world, me)
        if a != me and distance_between(c.world, me, a) <= 5
    ]
    if near:
        c.shift(2, who=near[0])


@power("f2353", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=AS_RANGED)
def f2353(c: Cast) -> None:
    """Two named rows shoot past cover and concealment.

    **`cover` and `concealment` are not keys the attack context has.**
    `resolve.attack` builds it with `attacker, target, power, advantage,
    opportunity, charge, action_point, ranged, branch, hand` -- so a
    gate reading either was silently false and this waiver never once
    applied. `c.ignore_cover` is the verb, and it writes into the
    `ignore_cover` modifier that `query.cover_waived` actually reads.

    The second benefit, casting a melee row at range, is dropped: reach
    is header data the menu reads before anything runs.
    """
    me = c.me
    picked = among("p1556", "p1075")
    c.ignore_cover(
        on=me, until=When.ENCOUNTER,
        when=lambda ctx: (
            picked(ctx)
            # crossbow/bow/sling, not "hand crossbow"/"shortbow":
            # those are weapons, and `Gear.group` only ever holds a
            # group. Gating on one was silently false forever.
            and _holding(c, "crossbow", "bow", "sling")
        ),
    )


@power("f1312", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an enemy misses you with a melee attack")
def f1312(c: Cast) -> None:
    """The shift is a watch rather than a declared trigger so that the
    substitution, which is standing, has somewhere to be armed."""
    if not _holding(c, "heavy blade"):
        return
    c.as_basic("p1413", "p1075", window="opportunity")

    def on_miss(ev: Any) -> None:
        p = get(ev.power)
        if ev.target != c.me or p is None or p.reach.kind != "melee":
            return
        if _holding(c, "heavy blade"):
            c.shift(1)

    c.watch(Miss, on_miss, on=c.me, until=When.ENCOUNTER)


@power("f2070", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       todo=("c.cover_from()", "c.recast(reach=)"))
def f2070(c: Cast) -> None:
    """Punishes whatever is giving your target cover, and casts `p1556`
    or `p1074` at range. Cover is a number the attack context carries
    and nothing says *which* creature is casting it; reach is header
    data. An item block wants the first of those too."""


@power("f2336", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=AS_RANGED,
       trigger="you attack with a bow or crossbow",
       on=Trigger(Hit, lambda w, me, ev: ev.attacker == me, "you attack"))
def f2336(c: Cast) -> None:
    """No opportunity attack from the creature you are shooting at.

    Declared on the hit rather than on the declaration, unlike the
    ranger's `f2337`: this row's exemption lasts the turn, so granting
    it after the first shot still covers the rest of them. The first
    shot of a turn goes unprotected, which is a shortfall of one swing
    rather than of the clause, and it is why `f2337` is written the
    other way.
    """
    if _holding(c, "bow", "crossbow"):
        c.no_provoke(from_=c.trigger.target, on=c.me, until=When.EOT)


# -- the deals the engine cannot offer --------------------------------------


def _deal(ref: str, what: str) -> None:
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=OPT_IN)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = (
        f"{what} Nothing lets a row offer a cost for a payoff at the "
        "moment of an attack, so writing it would either hand out the "
        "payoff free or charge the cost unasked."
    )


_deal("f944", "A -2 to hit, and an ally beside the target hits harder.")
_deal("f2051", "An action-point attack that trades advantage either way.")
_deal("f2059", "A charge that knocks down, or invites a swing back.")
_deal("f2060", "A charge bonus handed to an ally instead of taken.")
_deal("f2052", "Inspiring word's target trades defence for damage.")
_deal("f814", "Inspiring word's extra dice traded for a saving throw.")


# -- the rest, each gap named -----------------------------------------------


@power("f2054", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an ally with line of sight to you uses his or her second wind",
       on=Trigger(SecondWind, _ally_in_sight, "an ally in sight is winded"))
def f2054(c: Cast) -> None:
    """The ally's own next turn is the clock, not yours."""
    c.bonus("save", c.cha_mod, on=c.trigger.actor, until=When.EOTNT)


@power("f2061", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an ally with line of sight to you uses his or her second wind",
       on=Trigger(SecondWind, _ally_in_sight, "an ally in sight is winded"))
def f2061(c: Cast) -> None:
    """Half your level, rounded down, is the printed term."""
    c.temp_hp(c.cha_mod + c.level // 2, on=c.trigger.actor)


@power("f2058", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_surge()",))
def f2058(c: Cast) -> None:
    """Splits a healing surge between you and a neighbour. `SurgeSpent`
    is announced and `c.surge_value` is readable -- what is missing is
    getting in before the hit points land, since the event fires after
    the pool is decremented and the healing is already done."""


@power("f2056", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.aid_another()",))
def f2056(c: Cast) -> None:
    """Raises what the aid another action grants. There is no aid
    another action: `actions.legal` offers attacks, moves, powers and
    the standard menu, and helping somebody else is not on it."""


@power("f2053", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_provoked()",))
def f2053(c: Cast) -> None:
    """An ally shifts when an enemy provokes from you. `LeftAdjacent` is
    the movement that provokes, but it fires for every departure
    whether an opportunity attack follows or not -- and this row is
    printed for the provocation, not the walk."""


@power("f827", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1628",
       on=Trigger(PowerUsed, _used_wrath, "you use that racial power"))
def f827(c: Cast) -> None:
    """`p1628` is `NO_TARGET` and aims itself at the enemy on its own
    trigger, so "the target" is read there and not off `ev.targets`,
    which is empty.

    "Your allies" and not you, which is `to="ally"`; the clock is the
    target's own next turn.
    """
    foe = getattr(getattr(c.trigger, "trigger", None), "attacker", None)
    if foe is not None:
        c.grants_advantage(on=foe, to="ally", until=When.EOTNT)


@power("f1070", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f1070(c: Cast) -> None:
    """A polearm counted as an implement.

    `c.as_implement` rewrites the group of what is in hand, which is
    exactly the printed line -- and the reason it exists. Untiered
    rather than heroic, so it is outside the wave's denominator, but it
    is one call and leaving it out would be leaving work on the floor.
    """
    if _holding(c, "polearm"):
        c.as_implement(on=c.me)


@power("f1068", level=1, cls="", usage=ENCOUNTER, action=MINOR,
       reach=Ranged(10), target=ONE_CREATURE)
def f1068(c: Cast) -> None:
    """A curse of the feat's own, and the only row in this file that
    costs an action.

    I marked this `c.curse()` on the reasoning that the warlock's curse
    is a class feature nothing else may lay. `scripts/todo.py` went red
    on the next run: `c.curse` is an ordinary verb and it is
    *relational*, which is exactly what this needs -- two cursers on a
    board read their own and not each other's.

    The payoff is a `c.watch` rather than a second row, because the
    feat is one card: hit anything you have cursed and an ally of your
    choice gets combat advantage on its next swing. "Of your choice" is
    the nearest ally, since a bonus handed to somebody out of reach of
    the target is the feat doing nothing.

    The light it sheds is flavour and lights nothing the engine models.
    """
    from combat_engine.engine.query import distance_between

    me = c.me
    foe = c.target
    if foe is None:
        return
    c.curse(on=foe)

    def on_hit(ev: Any) -> None:
        if ev.attacker != me or not c.cursed(on=ev.target):
            return
        near = [a for a in allies(c.world, me) if a != me]
        if near:
            chosen = min(
                near, key=lambda a: distance_between(c.world, ev.target, a)
            )
            c.grants_advantage(on=ev.target, to=chosen, once=True)

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER)
