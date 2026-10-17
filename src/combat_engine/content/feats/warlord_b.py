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

**"You can choose to use this feat" was called a gap and is not one.**
Each of those cards prints a cost and a payoff -- take a -2 to hit and
an ally gains damage; charge and knock prone, but a miss lets the enemy
swing back -- and the claim here was that nothing lets a row offer a
*deal* at the moment of an attack. Two things say it. `c.may` is the
question ("a printed **may** is a real choice and has to be offered as
one" is its own docstring), and a `c.watch` on `AttackDeclared` in
`Window.BEFORE` is the moment: `resolve.attack` reads its modifiers
inside the callback that window precedes, so a penalty laid there is
read by the very roll being declared. Five of the six are written that
way now. The sixth wants to forgo dice another row is about to roll,
which is a different thing and still missing.

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
    AttackDeclared,
    Cast,
    DamageType,
    Gear,
    Healed,
    Hit,
    InitiativeRolled,
    Keyword,
    Miss,
    Moved,
    OpportunityWindow,
    PowerUsed,
    Ranged,
    SecondWind,
    SurgeSpent,
    Trigger,
    When,
    Window,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.grid import distance as squares_apart
from combat_engine.engine.query import (
    allies,
    distance_between,
    enemies,
    squares,
    team,
)

from .styles import among


def _used_wrath(world, me: int, ev) -> bool:  # noqa: ANN001
    return ev.actor == me and ev.power == "p1628"

#: **A standing clause and a triggered one on the same card.** The
#: dispatcher only reaches a no-action row when its declared trigger
#: fires, so a row that also has to be *true* from the start of the
#: fight -- "you can use this in place of a melee basic attack" is --
#: is never armed. Those rows keep the printed Trigger as text and
#: answer it with `c.watch`, the shape `p7419` already uses.
#:
#: **…nor turn a melee row into a ranged one, and the reach modifier is
#: not the way in.** `dsl._stretched` reads a `"reach"` modifier and
#: `area_of` widens the offer by it, which reads like the answer -- it is
#: what `c.as_ranged` is built on. Driven on a board it is inert twice
#: over: `_reach_of`'s weapon branch returns the wielded reach and throws
#: `area_of`'s stretched size away, which is every row printing "Melee
#: weapon" and so every power associated with these three feats; and
#: `_within_reach` never asks `_stretched` at all, so even a fixed-melee
#: row is *offered* at the stretched distance and then refused by
#: `actions.perform` before the action is spent. Measured: a `+9` reach on
#: the melee basic attack leaves it reaching 1 and `use()` answering
#: False. Both are engine faults rather than this clause's, and the clause
#: wants more than distance anyway -- the bow's dice, cover, and the
#: opening a ranged shot leaves all follow the range *kind*, which no
#: modifier changes.
AS_RANGED = ("c.recast(as_ranged=)",)
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


def _covering(c: Cast, foe: int) -> list[int]:
    """Which other creatures on `foe`'s side are giving it cover from me.

    **Now a thin call on `query.cover_granters`**, which is the same walk
    this used to do inline. It was the original and the shared reader was
    written later and differently -- by *removal* rather than by sole
    blocker -- which made it empty whenever two bodies each sufficed, so one
    item row paid out nothing on a normal board. The semantics here won and
    moved into `query`; this stays as the name three rows already call.
    #651.

    One difference, and it is the shared reader's to keep: it asks about the
    **target's own side** the way `cover_between` does, where this asked
    about *my* enemies. Identical whenever the target is an enemy, which is
    all three callers, and right rather than lucky when it is not.
    """
    from combat_engine.engine.query import cover_granters

    return cover_granters(c.world, c.me, foe)


def _next_swing(c: Cast, then: Any, *, foe: int | None = None) -> None:
    """Answer the outcome of the attack being declared, once.

    A deal struck in the `AttackDeclared` window pays out on the `Hit`
    or the `Miss` that follows it, and `once=` on the watch itself is
    the wrong latch: it is spent by the first event of that type
    whether the gate matched or not.
    """
    done = [False]

    def answer(ev: Any) -> None:
        if done[0] or ev.attacker != c.me:
            return
        if foe is not None and ev.target != foe:
            return
        done[0] = True
        then(ev)

    for what in (Hit, Miss):
        c.watch(what, answer, on=c.me, until=When.EOT, label=f"{c.ref} deal")


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


# -- p1590, which is a ref --------------------------------------------------


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


@power("f822", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1590",
       on=Trigger(PowerUsed, _my_word, "you use inspiring word"))
def f822(c: Cast) -> None:
    """Adds Intelligence to what inspiring word restores.

    **Re-aimed off `c.bonus(healing)`, which was never the hold.** `Mods`
    really is not consulted for healing -- but `Healed` is a `Decision`
    announced *before* the hit points go on, and `resolve.heal` reads
    `offered.amount` back after the window, which is the seam. Arming it
    here is in time because `PowerUsed` fires above p1590's body.
    """
    spent = [False]

    def more(ev: Any) -> None:
        if spent[0] or ev.source != c.me:
            return
        spent[0] = True
        ev.amount += c.int_mod

    c.watch(Healed, more, on=c.me, until=When.EOT, window=Window.BEFORE,
            label=f"{c.ref} heal rider")


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
       reach=PERSONAL, target=SELF,
       trigger="you hit with an associated power, or an adjacent marked "
               "enemy shifts away from you")
def f2333(c: Cast) -> None:
    """Two triggered clauses on one card, so both are `c.watch` and the
    printed Trigger stays text: a declared `on=` arms one of them and the
    other is never reached.

    **The shift-away half is written now.** It was dropped on the reading
    that nothing says which creature a shift went away *from*. `Moved`
    says it: it is the only movement event carrying `from_` **and**
    `kind_`, so "an adjacent enemy shifts away from you" is one
    question asked of both ends of the step -- beside me before, not
    beside me after.
    """
    me = c.me
    if not _holding(c, "hammer", "pick"):
        return

    def on_hit(ev: Any) -> None:
        if ev.attacker != me or ev.power not in ("p158", "p1075"):
            return
        if not _holding(c, "hammer", "pick"):
            return
        near = [
            a for a in allies(c.world, me)
            if a != me and distance_between(c.world, me, a) <= 5
        ]
        if near:
            c.shift(2, who=near[0])

    def stepped_away(ev: Any) -> None:
        foe = ev.actor
        if getattr(ev, "kind_", "") != "shift" or foe == me:
            return
        if team(c.world, foe) is team(c.world, me):
            return
        # "marked by you **or your ally**", so the mark is asked of
        # everybody on my side: `c.marked` with no `by=` asks about me
        # alone, which is half the printed sentence.
        if not _holding(c, "hammer", "pick"):
            return
        if not any(c.marked(on=foe, by=a) for a in (me, *allies(c.world, me))):
            return
        mine = squares(c.world, me)
        was = any(squares_apart(ev.from_, sq) <= 1 for sq in mine)
        if was and not c.adjacent(to=foe):
            c.shift(1)

    c.watch(Hit, on_hit, on=me, until=When.ENCOUNTER,
            label=f"{c.ref} associated hit")
    c.watch(Moved, stepped_away, on=me, until=When.ENCOUNTER,
            label=f"{c.ref} shift away")


@power("f2353", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2353(c: Cast) -> None:
    """Two named rows shoot past cover and concealment.

    **`cover` and `concealment` are not keys the attack context has.**
    `resolve.attack` builds it with `attacker, target, power, advantage,
    opportunity, charge, action_point, ranged, branch, hand` -- so a
    gate reading either was silently false and this waiver never once
    applied. `c.ignore_cover` is the verb, and it writes into the
    `ignore_cover` modifier that `query.cover_waived` actually reads.

    The second benefit, casting a melee row at range, stays dropped --
    see `AS_RANGED`, which records what was measured. The reach modifier
    looks like the answer and is inert on exactly these rows.
    
    **The ranged aiming is written now, and `AS_RANGED` was right about why
    it could not be.** That constant records the measurement: a `"reach"`
    modifier is read only for a line the header already declares melee, so
    it lengthens the swing and never makes it a shot -- `reach.kind` decides
    provoking, `c.ranged`, `by_ranged` and the `ranged` context key, and all
    four would still say melee.

    `c.reshape_area(optional=True)` contributes an **aiming** instead, which
    `dsl.branches_for` offers and `dsl.reach_of` resolves (#614). Both halves
    of the card hold: "**instead of** a melee power" is a choice, so the
    printed melee aiming stays on the menu.

    `Ranged(..., by_weapon=True)` and not a number: the card gates on the
    weapon in hand, so the range is that weapon's, which is what
    `dsl._reach_of` resolves `by_weapon` to. Only the heroic associated rows
    are named -- the paragon ones belong to the band above.
    """
    if _holding(c, "crossbow", "bow", "sling"):
        for ref in ("p1556", "p1075"):
            c.reshape_area(
                lambda _r: Ranged(0, by_weapon=True),
                ref=ref,
                optional=True,
                on=c.me,
                until=When.ENCOUNTER,
            )
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
       trigger="you hit an enemy another enemy is giving cover")
def f2070(c: Cast) -> None:
    """Punishes whatever is giving your target cover.

    **Re-aimed off `c.cover_from()`.** Cover is not a number anything
    stores -- it is traced at the moment of the attack -- so *which*
    creature is casting it is asked the same way, by tracing the line
    once per candidate with that candidate as the only blocker. See
    `_covering`. Casting a melee row at range stays dropped -- see
    `AS_RANGED` for what was driven and why the reach modifier is not it.
    
    **The ranged aiming is written now, and `AS_RANGED` was right about why
    it could not be.** That constant records the measurement: a `"reach"`
    modifier is read only for a line the header already declares melee, so
    it lengthens the swing and never makes it a shot -- `reach.kind` decides
    provoking, `c.ranged`, `by_ranged` and the `ranged` context key, and all
    four would still say melee.

    `c.reshape_area(optional=True)` contributes an **aiming** instead, which
    `dsl.branches_for` offers and `dsl.reach_of` resolves (#614). Both halves
    of the card hold: "**instead of** a melee power" is a choice, so the
    printed melee aiming stays on the menu.

    `Ranged(..., by_weapon=True)` and not a number: the card gates on the
    weapon in hand, so the range is that weapon's, which is what
    `dsl._reach_of` resolves `by_weapon` to. Only the heroic associated rows
    are named -- the paragon ones belong to the band above.
    """
    if _holding(c, "bow"):
        for ref in ("p1556", "p1074"):
            c.reshape_area(
                lambda _r: Ranged(0, by_weapon=True),
                ref=ref,
                optional=True,
                on=c.me,
                until=When.ENCOUNTER,
            )
    me = c.me

    def punish(ev: Any) -> None:
        if ev.attacker != me or not _holding(c, "bow"):
            return
        blockers = _covering(c, ev.target)
        if blockers:
            c.flat(c.str_mod, on=blockers[0])

    c.watch(Hit, punish, on=me, until=When.ENCOUNTER,
            label=f"{c.ref} cover punished")


@power("f2336", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
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
    
    **The ranged aiming is written now, and `AS_RANGED` was right about why
    it could not be.** That constant records the measurement: a `"reach"`
    modifier is read only for a line the header already declares melee, so
    it lengthens the swing and never makes it a shot -- `reach.kind` decides
    provoking, `c.ranged`, `by_ranged` and the `ranged` context key, and all
    four would still say melee.

    `c.reshape_area(optional=True)` contributes an **aiming** instead, which
    `dsl.branches_for` offers and `dsl.reach_of` resolves (#614). Both halves
    of the card hold: "**instead of** a melee power" is a choice, so the
    printed melee aiming stays on the menu.

    `Ranged(..., by_weapon=True)` and not a number: the card gates on the
    weapon in hand, so the range is that weapon's, which is what
    `dsl._reach_of` resolves `by_weapon` to. Only the heroic associated rows
    are named -- the paragon ones belong to the band above.
    
    **`AT_WILL`, not `ENCOUNTER`, and the lint caught it the moment the
    marker came off.** A triggered trait declared `ENCOUNTER` is spent on
    its first firing, and this card prints no limit -- so the row would have
    paid out once a fight where the page pays every time. The check only
    applies to a row claiming to be finished, which is exactly why removing
    a marker is the moment a header gets audited.
    """
    if _holding(c, "bow", "crossbow"):
        for ref in ("p4569", "p1065"):
            c.reshape_area(
                lambda _r: Ranged(0, by_weapon=True),
                ref=ref,
                optional=True,
                on=c.me,
                until=When.ENCOUNTER,
            )
    if _holding(c, "bow", "crossbow"):
        c.no_provoke(from_=c.trigger.target, on=c.me, until=When.EOT)


# -- the deals, offered ------------------------------------------------------


@power("f944", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you make a melee attack")
def f944(c: Cast) -> None:
    """A -2 to hit, and an ally beside the target hits harder.

    The window is `AttackDeclared` in `Window.BEFORE`, which is the only
    place the cost can be charged: `resolve.attack` totals its modifiers
    inside the callback that window precedes, so a penalty laid here is
    read by this roll and one laid on the `Hit` is a round late.

    "Another ally adjacent to the target" leaves me out, and the nearest
    such ally takes the bonus -- one handed to somebody who cannot reach
    the target is the feat doing nothing.
    """
    me = c.me

    def offer(ev: Any) -> None:
        p = get(ev.power)
        if ev.attacker != me or p is None or p.reach.kind != "melee":
            return
        if not c.may("take -2 to hit so an ally hits this enemy harder"):
            return
        foe = ev.target
        c.penalty("attack", 2, on=me, until=When.EOT, once=True)

        def settle(done: Any) -> None:
            if not isinstance(done, Hit):
                return
            near = [
                a for a in allies(c.world, me)
                if a != me and c.adjacent_to(foe, a)
            ]
            if near:
                c.bonus("damage", 3, on=near[0], until=When.EONT,
                        when=lambda ctx: ctx.get("target") == foe)

        _next_swing(c, settle, foe=foe)

    c.watch(AttackDeclared, offer, on=me, until=When.ENCOUNTER,
            window=Window.BEFORE, label=f"{c.ref} offer")


@power("f2051", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you spend an action point to make an extra attack",
       on=Trigger(ActionPointSpent, _my_point, "you spend an action point"))
def f2051(c: Cast) -> None:
    """Advantage traded either way on the action point's extra attack.

    The point is spent before the attack is declared, so the deal is
    struck here and `_next_swing` reads which way it went. "You grant
    combat advantage to the enemy" is `to=<that enemy>`: the words
    `c.grants_advantage` takes name *my* side, and this hands it to
    theirs.
    """
    if not c.may("trade combat advantage on this action point's attack"):
        return

    def settle(ev: Any) -> None:
        if isinstance(ev, Hit):
            c.grants_advantage(on=ev.target, to="team", until=When.EONT)
        else:
            c.grants_advantage(on=c.me, to=ev.target, until=When.EONT)

    _next_swing(c, settle)


@power("f2059", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you charge")
def f2059(c: Cast) -> None:
    """A charge that knocks down, or invites a swing back.

    `charge` rides on `AttackDeclared` as a plain attribute, so the deal
    is offered on the charge itself rather than on every attack.
    """
    me = c.me

    def offer(ev: Any) -> None:
        if ev.attacker != me or not getattr(ev, "charge", False):
            return
        if not c.may("risk a free swing back to knock this enemy prone"):
            return
        foe = ev.target

        def settle(done: Any) -> None:
            if isinstance(done, Hit):
                c.prone(on=foe)
            else:
                c.basic(who=foe, on=me)

        _next_swing(c, settle, foe=foe)

    c.watch(AttackDeclared, offer, on=me, until=When.ENCOUNTER,
            window=Window.BEFORE, label=f"{c.ref} offer")


@power("f2060", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you charge")
def f2060(c: Cast) -> None:
    """The charge bonus handed to an ally instead of taken.

    The printed charge bonus is +1 and `resolve.attack` adds it
    unconditionally, so forgoing it is a -1 on this roll and nothing
    else. "One ally with line of sight to you" is `_ally_in_sight`'s
    question asked the other way round, so it is asked with the grid's
    `line_of_effect` for the same reason.
    """
    me = c.me

    def offer(ev: Any) -> None:
        from combat_engine.engine.components import Position

        if ev.attacker != me or not getattr(ev, "charge", False):
            return
        here = c.world.get(me, Position)
        near = [
            a for a in allies(c.world, me)
            if a != me
            and (there := c.world.get(a, Position)) is not None
            and here is not None
            and c.world.grid.line_of_effect(there.square, here.square)
        ]
        if not near or not c.may("give up the charge bonus so an ally hits"):
            return
        foe = ev.target
        c.penalty("attack", 1, on=me, until=When.EOT, once=True)
        c.bonus("attack", 2, on=near[0], until=When.EONT, once=True,
                when=lambda ctx: ctx.get("target") == foe)

    c.watch(AttackDeclared, offer, on=me, until=When.ENCOUNTER,
            window=Window.BEFORE, label=f"{c.ref} offer")


@power("f2052", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1590",
       on=Trigger(PowerUsed, _my_word, "you use inspiring word"))
def f2052(c: Cast) -> None:
    """Inspiring word's target trades defence for damage.

    The choice is the **target's**, which is what `c.may(who=)` is for:
    it asks the creature the clause is about rather than the caster, and
    whose defence is being sold decides whether it is worth selling.

    "Grants combat advantage" with nobody named is every enemy of mine,
    one relation each, since `c.grants_advantage`'s words name my side
    and this is a gift to the other.
    """
    for who in c.trigger.targets:
        if not c.may("grant combat advantage to hit harder", who=who):
            continue
        for foe in enemies(c.world, c.me):
            c.grants_advantage(on=who, to=foe, until=When.SONT)
        c.bonus("damage", c.cha_mod, on=who, until=When.EONT, once=True)


@power("f814", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use p1590",
       on=Trigger(PowerUsed, _my_word, "you use inspiring word"))
def f814(c: Cast) -> None:
    """Inspiring word's extra dice traded for a saving throw.

    **The cost really is separable, which the old marker denied.** p1590
    pays in two calls -- `c.surge`, then `c.heal(c.roll("1d6"))` -- so the
    extra dice arrive as a `Healed` of their own, and `Healed` is a
    `Decision` read back by `resolve.heal`. `SurgeSpent` carries `power`
    and `source`, so the first `Healed` after it is the surge the card does
    not touch and the second is the dice the card buys with.

    Armed here rather than standing, because `PowerUsed` fires above
    p1590's body -- and the creature is taken off `SurgeSpent.actor`, not
    off `ev.targets`: p1590 chooses who it heals inside its own body, so
    the declared target is the wrong name for whoever got the hit points.

    At-will, because the cap the card prints is p1590's own two uses.
    """
    me = c.me
    paying: dict[str, int] = {}

    def surged(ev: SurgeSpent) -> None:
        if ev.source == me and ev.power == WORD:
            paying["who"], paying["seen"] = ev.actor, 0

    def forgo(ev: Healed) -> None:
        who = paying.get("who")
        if who is None or ev.source != me or ev.target != who:
            return
        paying["seen"] += 1
        if paying["seen"] < 2:
            return  # the surge itself, which the feat does not buy with
        paying.pop("who")
        if ev.amount <= 0 or not c.may("forgo the extra healing for a save"):
            return
        ev.amount = 0
        c.save(on=who)

    c.watch(SurgeSpent, surged, on=me, until=When.EOT,
            label=f"{c.ref} word surge")
    c.watch(Healed, forgo, on=me, until=When.EOT, window=Window.BEFORE,
            label=f"{c.ref} forgone")


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
       reach=PERSONAL, target=SELF)
def f2058(c: Cast) -> None:
    """Splits a healing surge between you and a neighbour.

    **Re-aimed off `c.on_surge()` and then written.** The claim was that
    the healing is already done by the time anything can see it. It is
    not: `resolve.spend_surge` announces `SurgeSpent` and *then* calls
    `heal`, which announces `Healed` **before** the hit points go on and
    reads `amount` back afterwards. So the surge marks the heal that is
    coming and the `Healed` window divides it.

    "In any proportion" is halved, since nothing carries a proportion,
    and the neighbour is the first adjacent ally.
    """
    me = c.me
    coming = [False]

    def surged(ev: Any) -> None:
        if ev.actor == me:
            coming[0] = True

    def divide(ev: Any) -> None:
        if not coming[0] or ev.target != me:
            return
        coming[0] = False
        near = [a for a in allies(c.world, me) if a != me and c.adjacent(to=a)]
        share = ev.amount // 2
        if not near or share <= 0:
            return
        ev.amount -= share
        c.heal(share, on=near[0])

    c.watch(SurgeSpent, surged, on=me, until=When.ENCOUNTER,
            label=f"{c.ref} surge")
    c.watch(Healed, divide, on=me, until=When.ENCOUNTER,
            window=Window.BEFORE, label=f"{c.ref} divided")


@power("f2056", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2056(c: Cast) -> None:
    """"Whenever you or an ally who can hear you and who has line of sight
    to you takes the aid another, aid attack, or aid defense action, the
    bonus granted to the target equals +4 instead of +2."

    **Laid on every ally as well as on the wearer**, because the printed
    benefit is theirs: it is the ally's own aid action whose number changes.
    `MANOEUVRE_AID` covers all three actions the card names, so none of them
    is spelled out.

    "Who can hear you" is every ally -- hearing is not on the board, which
    `powers/warlord/level_6_b.py` records in the same words. Line of sight
    is the grid's `line_of_effect`, the same substitution `_ally_in_sight`
    makes and for the same reason: it is the question about walls.

    **"An ally can benefit from this feat only once per attack" needs no
    code.** `amount_for` takes the largest matching entry rather than
    summing them, so a second copy of this changes nothing -- which is the
    clause, and is why that reader was built to take a maximum.
    """
    from combat_engine.engine.cast import MANOEUVRE_AID
    from combat_engine.engine.components import Position

    me = c.me
    c.change_amount(MANOEUVRE_AID, 4, on=me, until=When.ENCOUNTER)
    mine = c.world.get(me, Position)
    for friend in allies(c.world, me):
        theirs = c.world.get(friend, Position)
        if (mine is None or theirs is None
                or not c.world.grid.line_of_effect(theirs.square, mine.square)):
            continue
        c.change_amount(MANOEUVRE_AID, 4, on=friend, until=When.ENCOUNTER)


@power("f2053", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="an enemy provokes an opportunity attack from you")
def f2053(c: Cast) -> None:
    """An ally shifts when an enemy provokes from you.

    **Re-aimed off `c.on_provoked()`.** `LeftAdjacent` really does fire
    for every departure -- but `OpportunityWindow` is the provocation
    itself: `actor` is who may swing, `provoker` is who set it off, and
    `why` says what they did. It is opened by `movement`, by `dsl` for a
    ranged power used in a threatened square, and by `c.provoke`, which
    is every way a provocation happens.

    "To a square not adjacent to the provoking enemy" is `away_from=` that
    enemy: the ally's squares are offered farthest-from-it first, so the
    step leaves the enemy's reach whenever any square it can reach does.
    Ranking and not a veto -- a decider that wants a nearer square still
    sees it, which is the same bargain `toward=` strikes on the rows that
    must close.
    """
    me = c.me

    def provoked(ev: Any) -> None:
        if ev.actor != me:
            return
        near = [a for a in allies(c.world, me) if a != me and c.adjacent(to=a)]
        if near and c.int_mod > 0:
            c.shift(c.int_mod, who=near[0], away_from=ev.provoker)

    c.watch(OpportunityWindow, provoked, on=me, until=When.ENCOUNTER,
            label=f"{c.ref} provoked")


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
