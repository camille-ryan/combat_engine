"""Ranger feats, the third batch.

`ranger.py` and `ranger_b.py` hold the first two, and the same split
runs through this one: eighteen of the twenty-seven rows in the tree
that talk to a beast companion now live across the three files, and
eleven of them are here. Their prerequisites all carry the same opaque
term, which is the gap `docs/blocked.json` records as
`cf:ranger-style-beast`, so they all carry `c.beast()`.

Two things this batch found that were thought to be gaps.

**Standing up is announced.** `actions.legal` offers a `stand`, and
performing it ends the prone effect with `why="stood up"` -- so
`ConditionEnded` says both that a creature stood and that it stood on
purpose. That is `f2391` outright, and it is also the clause
`fighter_b.f1322` dropped as `c.provokes_on_stand()`: with the event in
hand, `c.provoke` opens the window. `f2712` writes it.

**"Shift to a square adjacent to the enemy" is an instruction, not a
choice.** `c.shift(to=)` takes the square, and `World.reachable_squares`
gives the candidates, so `_shift_beside` narrows them rather than
handing the decider a free shift that may walk the other way.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AT_WILL,
    ENCOUNTER,
    PERSONAL,
    SELF,
    ActionType,
    Cast,
    Condition,
    ConditionEnded,
    Gear,
    Hit,
    Keyword,
    Miss,
    PowerUsed,
    Relation,
    Trigger,
    When,
    power,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.grid import between
from combat_engine.engine.query import squares

from .styles import used_one_of

#: There is no beast companion. Eighteen rows across three files wait.
BEAST = ("c.beast()",)
#: Nothing announces that the class's extra damage was about to be paid.
EXTRA = ("c.on_extra_damage()",)
#: `c.no_provoke` exempts a creature or everything, and nothing between.
NARROW = ("c.no_provoke(when=)",)


def _holding(c: Cast, *groups: str) -> bool:
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return False
    carried = (*gear.melee, *([gear.ranged] if gear.ranged else ()))
    return any(w.group in groups for w in carried)


def _grip(c: Cast, *groups: str, hands: int) -> bool:
    gear = c.world.get(c.me, Gear)
    if gear is None:
        return False
    return any(
        w.group in groups and w.two_handed == (hands == 2) for w in gear.melee
    )


def _i_hit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me


def _missed_my_quarry_charging(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    """A charge of mine that missed the quarry.

    `charge` rides on `Miss` as a plain attribute, the way `opportunity`
    does, so it is read with a default rather than declared. The quarry
    is a relation and `c.is_quarry` is the same question from a `Cast`;
    a predicate is handed the world instead.
    """
    return (
        ev.attacker == me
        and bool(getattr(ev, "charge", False))
        and world.relations.holds(Relation.QUARRY_OF, me, ev.target)
    )


def _i_crit(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return ev.attacker == me and ev.critical


def _martial_encounter(ref: str) -> bool:
    p = get(ref)
    return (
        p is not None
        and Keyword.MARTIAL in p.keywords
        and p.usage is ENCOUNTER
    )


def _my_ranger_attack(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    p = get(ev.power)
    return (
        ev.actor == me
        and p is not None
        and p.cls == "ranger"
        and p.attack is not None
    )


def _i_stood(world, me: int, ev: Any) -> bool:  # noqa: ANN001
    return (
        ev.target == me
        and ev.condition is Condition.PRONE
        and ev.why == "stood up"
    )


def _shift_beside(c: Cast, squares_: int, foe: int) -> bool:
    """Shift, but only into a square next to that enemy.

    `c.shift` with no `to=` hands the decider every reachable square,
    which for a row that says "to a square adjacent to the enemy" is a
    different power. Filtering first and naming the square is the
    printed instruction.
    """
    theirs = squares(c.world, foe)
    mine = squares(c.world, c.me)
    options = [
        sq for sq in c.world.reachable_squares(c.me, squares_)
        if sq not in mine and between({sq}, theirs) <= 1
    ]
    return bool(options) and c.shift(to=options[0])


# -- the quarry half, and the board ----------------------------------------


@power("f2390", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       trigger="you use a ranger attack power",
       on=Trigger(PowerUsed, _my_ranger_attack, "you use a ranger power"))
def f2390(c: Cast) -> None:
    """"When you move as part of using a ranger attack power".

    `PowerUsed` is announced above the body, so the waiver is standing
    by the time the row's own movement happens -- which is the only
    reason this is sayable. It is held to the end of the turn rather
    than to the end of the move, because nothing marks where a power's
    movement stops; that costs the ranger rough ground it walked over
    later in the same turn, and no more.
    """
    c.ignores_difficult(on=c.me, until=When.EOT)


@power("f2391", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you stand up",
       on=Trigger(ConditionEnded, _i_stood, "you stand up"))
def f2391(c: Cast) -> None:
    """Standing is an action in the menu and it announces itself: the
    prone effect ends with `why="stood up"`, which separates getting up
    on purpose from an effect simply expiring."""
    c.shift(1)


@power("f2406", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=NARROW,
       trigger="you make a melee attack",
       on=Trigger(Hit, lambda w, me, ev: (
           ev.attacker == me
           and (p := get(ev.power)) is not None and p.reach.kind == "melee"
       ), "you attack in melee"))
def f2406(c: Cast) -> None:
    """The exemption is granted to everybody rather than to thrown
    attacks only: `c.no_provoke` names one creature to be exempt from,
    or all of them, and carries no gate on what the shot was made with.
    So the clause plays and the narrowing to thrown weapons is what is
    dropped."""
    c.no_provoke(on=c.me, until=When.SONT)


@power("f2439", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def f2439(c: Cast) -> None:
    """Melee feeds ranged and ranged feeds melee, against the one enemy.

    A trait with a watch rather than a declared trigger, because the row
    answers every hit for the rest of the fight and a declared trigger
    would fire the whole body once per event. The damage context carries
    `power`, so "the next *ranged* attack" is asked of that row's range
    line. `once=True`: it is the next attack, not every attack.

    Untiered, so the +4 and +6 rungs are out of scope; the heroic number
    is the whole of it here.
    """
    me = c.me

    def paid(ev: Any) -> None:
        if ev.attacker != me:
            return
        p = get(ev.power)
        if p is None:
            return
        want = "melee" if p.reach.kind == "ranged" else "ranged"
        foe = ev.target
        c.bonus(
            "damage", 2, on=me, until=When.EONT, once=True,
            when=lambda ctx: (
                ctx.get("target") == foe
                and (q := get(ctx.get("power", ""))) is not None
                and q.reach.kind == want
            ),
        )

    c.watch(Hit, paid, on=me, until=When.ENCOUNTER)


# -- the style feats, now that the associated lists resolve ----------------


@power("f2708", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("Weapon.high_crit",),
       trigger="an enemy misses you, or you use an associated power",
       on=(Trigger(Miss, lambda w, me, ev: (
               ev.target == me
               and (p := get(ev.power)) is not None and p.reach.kind == "melee"
           ), "an enemy misses you in melee"),
           Trigger(PowerUsed, used_one_of("p4404", "p1521"),
                   "you use an associated power")))
def f2708(c: Cast) -> None:
    """Two printed clauses on two events, and the same shift either way
    -- one is worth a square and the other two, so the body has to know
    which fired. "Before your attack" is sayable because `PowerUsed` is
    announced above the body.

    What is dropped is the narrowing: the printed weapon is a heavy
    blade *with the high crit property*, and no weapon in the tree
    carries that property, so the row asks only for the group.
    """
    if not _holding(c, "heavy blade"):
        return
    c.shift(1 if isinstance(c.trigger, Miss) else 2)


@power("f2712", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.ability_for(ref)",),
       trigger="you score a critical hit with a one-handed axe",
       on=Trigger(Hit, _i_crit, "you crit"))
def f2712(c: Cast) -> None:
    """Prone, and a swing at it when it gets back up.

    The second half was dropped as `c.provokes_on_stand()` by the
    fighter's f1322, and it need not be: the stand action ends the prone
    effect with `why="stood up"`, so `ConditionEnded` is the trigger and
    `c.provoke` is the window. `once=True` is "the first time".

    What is dropped is Strength in place of Dexterity on the associated
    rows, which is header data the roll reads before anything runs.
    """
    if not _grip(c, "axe", hands=1):
        return
    me, foe = c.me, c.trigger.target
    c.prone(on=foe)

    def stood(ev: Any) -> None:
        if (
            ev.target == foe
            and ev.condition is Condition.PRONE
            and ev.why == "stood up"
        ):
            c.provoke(me, on=foe, why=c.ref)

    c.watch(ConditionEnded, stood, on=foe, until=When.EONT, once=True)


@power("f2803", level=1, cls="", usage=AT_WILL, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, trigger="you hit an enemy",
       on=Trigger(Hit, _i_hit, "you hit"))
def f2803(c: Cast) -> None:
    """Both clauses close the distance, and both name where the shift
    ends, so `_shift_beside` picks the square rather than the decider.
    One trigger with two branches: a row declared `on=` lays no standing
    modifiers, and neither half of this is one."""
    if not _holding(c, "scimitar"):
        return
    ev = c.trigger
    if ev.power in ("p10625", "p4385"):
        _shift_beside(c, 3, ev.target)
    elif _martial_encounter(ev.power):
        _shift_beside(c, 1, ev.target)
        c.push(1, on=ev.target)


# -- the rest, each gap named -----------------------------------------------


@power("f2398", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.on_racial_bonus()",))
def f2398(c: Cast) -> None:
    """Raises the attack bonus a racial trait grants, against the
    quarry. The quarry half is a relation and readable; the trait is a
    ref with no row behind it, so there is no bonus to find and raise
    and no circumstance to copy."""


@power("f2415", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.use_power()",))
def f2415(c: Cast) -> None:
    """Turns a racial power into an immediate interrupt against the
    quarry. The trigger is sayable and the power is a ref; what is
    missing is a row using another row now. `c.recast` changes what an
    action costs and `c.grant_row` hands one over -- neither fires
    one."""


@power("f2417", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=NARROW)
def f2417(c: Cast) -> None:
    """No opportunity attack for circling an enemy you are already
    beside. `c.no_provoke` is a standing exemption from one creature or
    from all, and this one holds only for a move that ends adjacent to
    the same enemy -- which is not known at `MoveStart` and is too late
    at `MoveEnd`."""


@power("f2419", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.expend_row()",),
       trigger="you miss your quarry with a charge",
       on=Trigger(Miss, _missed_my_quarry_charging,
                  "you miss your quarry with a charge"))
def f2419(c: Cast) -> None:
    """A reroll of a missed charge against the quarry.

    The **price** is dropped: nothing spends a row from outside it, so
    `p6189` is not expended and the reroll is had for nothing. That is
    why this stays `ENCOUNTER` rather than `AT_WILL` -- the racial power
    it should cost is an encounter power, so once a fight is the nearest
    honest cap, and without it the row would reroll every missed charge.

    The reroll mutates the live `AttackResult` and `resolve.attack`
    judges the defence again once the window closes, so `result.hit` is
    read back rather than `c.landed`, which is this row's own attack and
    there is not one.
    """
    result = getattr(c.trigger, "result", None)
    if result is None or not c.reroll_attack():
        return
    if result.hit:
        c.damage(c.w(), on=c.trigger.target)


@power("f2428", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=EXTRA)
def f2428(c: Cast) -> None:
    """Trades one die of the class's extra damage for a slow. The dice
    live in a closure inside `cf:ranger-quarry` and nothing announces
    that they are about to be paid, so there is no moment to intercept
    and nothing to take a die off."""


@power("f2467", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=EXTRA)
def f2467(c: Cast) -> None:
    """The same trade as f2428, bought for a push instead of a slow."""


@power("f2462", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.quarry(nearest=False)",))
def f2462(c: Cast) -> None:
    """Lets the second-nearest enemy be named quarry.

    `c.quarry` takes whoever it is handed and `cf:ranger-quarry` takes
    its target like any other row, so the restriction this feat lifts is
    not enforced anywhere -- writing the row would be granting a
    permission already held. Marked rather than left out, because the
    day the restriction arrives this is the row that relaxes it. The
    warlock's `c.curse(nearest=False)` is the same shape.
    """


@power("f2469", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.extend_shift()",))
def f2469(c: Cast) -> None:
    """Two extra squares on a shift a martial encounter or daily power
    grants. Nothing adds to the distance somebody else's row moves you,
    and the shift is inside that row's body. `f2361` waits on the
    same."""


@power("f2473", level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.low_light()",))
def f2473(c: Cast) -> None:
    """Low-light vision, and the whole benefit is that. There are no
    light levels, so there is nothing for the sight to see through --
    the same gap `skills.py` named from its other side."""


# -- the beast companion, which does not exist ------------------------------


def _beast(ref: str, what: str) -> None:
    @power(ref, level=1, cls="", usage=ENCOUNTER, action=ActionType.NONE,
           reach=PERSONAL, target=SELF, todo=BEAST)
    def feat(c: Cast) -> None: ...

    feat.__name__ = ref
    feat.__doc__ = f"{what} There is no beast companion to do it to."


_beast("f2402", "Saves, a longer leash, and the companion immobilises.")
_beast("f2422", "Saves, a longer leash, and its charge pushes.")
_beast("f2425", "Saves, a longer leash, and its target grants advantage.")
_beast("f2447", "Saves, a longer leash, and it grabs what it hits.")
_beast("f2453", "Saves, a longer leash, and its charge swings twice.")
_beast("f2461", "Saves, a longer leash, and it knocks its target down.")
_beast("f2465", "Saves, a longer leash, and its target pays for walking off.")
_beast("f2474", "Saves, a longer leash, a slow and an attack penalty.")
_beast("f2464", "The companion shares two named racial powers.")
_beast("f2967", "The companion's critical hits carry the weapon's dice.")
_beast("f2970", "A skill, and the companion heals when you spend a surge.")
