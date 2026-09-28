"""Feet-slot magic items, heroic tier: their Properties and their Powers.

Nothing here declares an item. The level, the price and the slot are
columns in `game.db`; no feet item carries an enhancement bonus, so every
number below is the heroic one the card prints and a `Level 13:` line is
paragon and out of scope.

Four judgements run through the file.

* **A fall is negotiated.** `Fell` is a `Decision` whose `squares`,
  `soften` and `prone` the emitter reads back, so "half damage from a
  fall and you land on your feet" is exactly `ev.squares //= 2` with
  `ev.prone = False`, and "no damage at all" is `c.cushion()`. Nothing
  here has to guess at a number.
* **A shove is negotiated too, and only in the interrupt window.**
  `movement._shove` settles the distance inside its resolve callback, so
  an *immediate interrupt* can shorten or refuse a push and an *immediate
  reaction* cannot -- it resolves once the creature has already moved.
  The one row that prints "immediate reaction: you ignore the forced
  movement" therefore keeps the half it can do and carries a marker.
* **Running is not a move the engine has.** Four blocks are entirely
  about what running costs and what it gives, and all four carry
  `todo=("c.run()",)` rather than an approximation of a double move.
* **A skill modifier is real** and its context is `{actor, skill}` only,
  so "+2 to Athletics checks" is exact and "+2 to Athletics checks **to
  jump**" is the same flat modifier plus
  `dropped=("c.skill_circumstance()",)`.

"When you use your second wind" is `SecondWind`, which `Cast.second_wind`
emits from the one place a second wind is ever taken. The two rows here
watch it through `_on_second_wind`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    ENCOUNTER,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    ActionType,
    AttackDeclared,
    Bloodied,
    Cast,
    Condition,
    ConditionApplied,
    Fell,
    Forced,
    ForcedMove,
    Hit,
    Keyword,
    Miss,
    MoveEnd,
    MoveStart,
    Position,
    SecondWind,
    Square,
    Trigger,
    When,
    World,
    about_me,
    both,
    by_melee,
    power,
    query,
    spread,
    targets_me,
)

ITEM = "item"


# -- shared reading of the board --------------------------------------------


def _skills(c: Cast, value: int, *names: str, kind: str = "item") -> None:
    """Lay one item bonus per named skill. There is no key for a set."""
    for name in names:
        c.bonus(f"skill:{name}", value, on=c.me, until=When.ENCOUNTER, kind=kind)


def _holding(*conditions: Condition) -> Callable[[dict[str, Any]], bool]:
    """Save gate: the effect being saved against imposes one of these."""
    wanted = set(conditions)

    def gate(ctx: dict[str, Any]) -> bool:
        return bool(wanted & set(getattr(ctx.get("effect"), "conditions", ())))

    return gate


def _reach_gate(*kinds: str) -> Callable[[dict[str, Any]], bool]:
    """Which shape the power being used is, read back off the row."""

    def gate(ctx: dict[str, Any]) -> bool:
        from combat_engine.engine import get

        row = get(ctx.get("power") or "")
        return row is not None and row.reach is not None and any(
            row.reach.kind.startswith(k) for k in kinds
        )

    return gate


def _enemy_shifts(world: World, me: int, ev: Any) -> bool:
    """"An enemy adjacent to you shifts", asked on `MoveStart`."""
    return (
        ev.kind_ == "shift"
        and ev.actor != me
        and ev.actor in query.enemies(world, me)
    )


def _foe(c: Cast) -> int | None:
    """The other creature in whatever event this row is answering."""
    ev = c.trigger
    for name in ("attacker", "source", "actor"):
        who = getattr(ev, name, None)
        if who is not None and who != c.me:
            return who
    return c.target


def _after_charge(c: Cast, fn: Callable[[], None]) -> None:
    """"After charging, you can shift 1 square before your turn ends."

    A charge announces itself on the attack that ends it and nowhere
    else, so both outcomes are watched -- a charge that misses is still a
    charge -- and the round is latched so one run pays out once."""
    seen: list[int] = []

    def rider(ev: Any) -> None:
        if getattr(ev, "attacker", None) != c.me:
            return
        if not getattr(ev, "charge", False) or c.world.round in seen:
            return
        seen.append(c.world.round)
        fn()

    c.watch(Hit, rider, until=When.ENCOUNTER, on=c.me)
    c.watch(Miss, rider, until=When.ENCOUNTER, on=c.me)


def _on_second_wind(c: Cast, fn: Callable[[], None]) -> None:
    """Arm "when you use your second wind" for the rest of the fight.

    `SecondWind` is the announcement. This used to sniff `EffectApplied`
    for a label beginning "second-wind", which only matched when the
    action menu ran it: `c.second_wind(on=ally)` labels the effect with
    the *calling row's* ref, so a leader row handing somebody a second
    wind was silently invisible here.
    """

    def seen(ev: SecondWind) -> None:
        if ev.actor == c.me:
            fn()

    c.watch(SecondWind, seen, until=When.ENCOUNTER, on=c.me)


def _free_near(c: Cast, of: int, radius: int = 1) -> Square | None:
    """An unoccupied square beside somebody, for a "to" clause."""
    pos = c.world.get(of, Position)
    if pos is None:
        return None
    for sq in sorted(spread({pos.square}, radius)):
        if sq != pos.square and c.world.grid.occupant(sq) is None:
            return sq
    return None


def _half_fall(c: Cast, *, until: When = When.ENCOUNTER) -> None:
    """"Half damage from a fall, and you land on your feet."

    The dice are `ev.squares // SQUARES_PER_DIE`, so halving the distance
    halves the damage exactly -- which is better than guessing at a flat
    number to put in `soften`."""

    def landing(ev: Fell) -> None:
        if ev.actor == c.me:
            ev.squares = max(0, ev.squares // 2)
            ev.prone = False

    c.watch(Fell, landing, until=until, on=c.me)


# -- level 2 ----------------------------------------------------------------


@power("i1270p1", level=2, cls=ITEM, usage=DAILY, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
       trigger="you fall",
       on=Trigger(Fell, about_me, "you fall"))
def i1270p1(c: Cast) -> None:
    """`c.cushion` with no number takes all the damage off and keeps the
    wearer upright, which is both halves of the printed sentence."""
    c.cushion()
    c.teleport(5)


@power("i1670p1", level=2, cls=ITEM, usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="you are pushed, pulled or slid",
       on=Trigger(ForcedMove, targets_me, "you are pushed, pulled or slid"))
def i1670p1(c: Cast) -> None:
    """The shove settles its distance inside its own resolve callback, so
    an interrupt shortens it by writing to the event."""
    ev = c.trigger
    if isinstance(ev, ForcedMove):
        ev.squares = max(0, ev.squares - 1)
    c.prone(on=c.me)


@power("i448x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i448x1(c: Cast) -> None:
    _skills(c, 1, "acrobatics")


@power("i448p1", level=2, cls=ITEM, usage=AT_WILL, action=MINOR,
       reach=PERSONAL, target=SELF,
       requires=lambda world, eid: query.is_(world, eid, Condition.PRONE),
       requires_text="must be prone")
def i448p1(c: Cast) -> None:
    """Standing up is taking the condition off; there is no other verb.
    Being prone is an entry requirement rather than a guard in the body,
    so a standing creature is not offered a row that would do nothing --
    and the policy is not handed an at-will to take every turn."""
    c.cure(Condition.PRONE, on=c.me)


@power("i745x1", level=2, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i745x1(c: Cast) -> None:
    _after_charge(c, lambda: c.shift(1))


@power("i756p1", level=2, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION])
def i756p1(c: Cast) -> None:
    c.teleport(1)


# -- level 3 ----------------------------------------------------------------


@power("i2743x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2743x1(c: Cast) -> None:
    """`c.jump` crosses ground and asks for no check, so a bonus to the
    Athletics behind a jump has nothing to land on."""


@power("i2743p1", level=3, cls=ITEM, usage=DAILY, action=MOVE,
       reach=PERSONAL, target=SELF)
def i2743p1(c: Cast) -> None:
    c.jump(max(1, c.str_mod))


@power("i764x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i764x1(c: Cast) -> None:
    _skills(c, 2, "stealth")


@power("i842x1", level=3, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i842x1(c: Cast) -> None:
    _half_fall(c)


@power("i842p1", level=3, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF)
def i842p1(c: Cast) -> None:
    """"Your next Acrobatics *or* Athletics check" is one bonus spent
    once, so both are laid with `once=True` and whichever is rolled
    first takes it."""
    for skill in ("acrobatics", "athletics"):
        c.bonus(f"skill:{skill}", 5, on=c.me, until=When.ENCOUNTER,
                kind="power", once=True)


# -- level 4 ----------------------------------------------------------------


@power("i2193x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2193x1(c: Cast) -> None:
    """The bonus is the mount's, not the rider's, which is what `c.mount`
    is there to tell apart."""
    beast = c.mount()
    if beast is not None:
        c.bonus("speed", 1, on=beast, until=When.ENCOUNTER, kind="item")


@power("i3052x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3052x1(c: Cast) -> None:
    """Water is terrain, and crossing it for nothing is what
    `c.ignores_difficult` says; sinking at the end of a turn spent on it
    is the printed cost of standing still, not of moving."""
    c.ignores_difficult("water", on=c.me)


@power("i3052p1", level=4, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i3052p1(c: Cast) -> None:
    c.ignores_difficult("water", on=c.me)


@power("i3077x1", level=4, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.run()",))
def i3077x1(c: Cast) -> None:
    """Running is not a move the engine makes, so there is no distance
    for this to lengthen."""


@power("i3077p1", level=4, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, todo=("c.run()",))
def i3077p1(c: Cast) -> None:
    """Same gap: the trigger is a run, and nothing runs."""


# -- level 5 ----------------------------------------------------------------


@power("i1316x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.run()",))
def i1316x1(c: Cast) -> None:
    """The whole property is a discount on a penalty nothing applies."""


@power("i2012p1", level=5, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="an enemy adjacent to you shifts",
       on=Trigger(MoveStart, _enemy_shifts, "an adjacent enemy shifts"),
       dropped=("c.in_form()",))
def i2012p1(c: Cast) -> None:
    """`MoveStart`, not `MoveEnd`: by the time the shift has finished the
    enemy is no longer adjacent, which is precisely when the row should
    fire. Beast form is the half with no question to ask."""
    if c.adjacent(getattr(c.trigger, "actor", None)):
        c.shift(1)


@power("i2509x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2509x1(c: Cast) -> None:
    """Leaving no tracks is narrative; the two terrain clauses are not."""
    for kind in ("dirt", "sand", "silt", "water"):
        c.ignores_difficult(kind, on=c.me)


@power("i2509p1", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2509p1(c: Cast) -> None:
    for kind in ("silt", "water"):
        c.ignores_difficult(kind, on=c.me)


@power("i2583x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i2583x1(c: Cast) -> None:
    """Climbing costs no check here -- `movement.walk` never rolls one --
    so the whole printed property is out of combat."""


@power("i2583p1", level=5, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="you are hit by an effect that pushes, pulls or slides you",
       on=Trigger(ForcedMove, targets_me, "you are pushed, pulled or slid"),
       dropped=("c.cancel_forced()",))
def i2583p1(c: Cast) -> None:
    """Printed as an immediate *reaction*, and a shove settles its
    distance in the interrupt window -- so by the time this runs the
    creature has already been moved. The cost the row charges still
    lands."""
    c.slowed(on=c.me, until=When.SONT)


@power("i2733x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2733x1(c: Cast) -> None:
    _skills(c, 2, "acrobatics")


@power("i2733p1", level=5, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you are knocked prone",
       on=Trigger(ConditionApplied,
                  lambda world, me, ev: (
                      ev.target == me and ev.condition is Condition.PRONE),
                  "you are knocked prone"))
def i2733p1(c: Cast) -> None:
    c.cure(Condition.PRONE, on=c.me)


@power("i759p1", level=5, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="an effect slows you",
       on=Trigger(ConditionApplied,
                  lambda world, me, ev: (
                      ev.target == me and ev.condition is Condition.SLOWED),
                  "an effect slows you"))
def i759p1(c: Cast) -> None:
    c.save(on=c.me)


@power("i759p2", level=5, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF)
def i759p2(c: Cast) -> None:
    c.bonus("speed", 1, on=c.me, until=When.ENCOUNTER, kind="power")


@power("i763x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i763x1(c: Cast) -> None:
    """A climb speed equal to the walking one is "climb at normal speed",
    since a climb mode with no number is half speed."""
    c.mode("climb", c.speed_of(), on=c.me)


@power("i763p1", level=5, cls=ITEM, usage=DAILY, action=MOVE,
       reach=PERSONAL, target=SELF)
def i763p1(c: Cast) -> None:
    c.mode("climb", c.speed_of(), on=c.me, until=When.EOT)
    c.move(c.speed_of(), at="climb")


@power("i772x1", level=5, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i772x1(c: Cast) -> None:
    c.ignores_difficult("forest", on=c.me)


@power("i772p1", level=5, cls=ITEM, usage=DAILY, action=MOVE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION])
def i772p1(c: Cast) -> None:
    """`c.scenery` finds the tree if the board has one; a board with no
    trees on it still lets the wearer blink, which is the reading that
    does not make the row unusable everywhere."""
    trees = c.scenery("tree", within=4)
    where = _free_near(c, trees[0]) if trees else None
    c.teleport(4, to=where)


# -- level 6 ----------------------------------------------------------------


@power("i1333x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.charge_target()",))
def i1333x1(c: Cast) -> None:
    """`query.speed` is handed `{"charge": True}` and nothing else, so the
    run is longer against every enemy rather than only a marked one."""
    c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: bool(ctx.get("charge")))


@power("i1333p1", level=6, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
       trigger="an enemy marked by you attacks somebody else",
       on=Trigger(AttackDeclared,
                  lambda world, me, ev: ev.attacker != me and ev.target != me,
                  "an enemy attacks somebody else"))
def i1333p1(c: Cast) -> None:
    foe = _foe(c)
    if foe is None or not c.marked(on=foe):
        return
    where = _free_near(c, foe)
    if where is not None:
        c.teleport(20, to=where)


@power("i1402x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.run()",))
def i1402x1(c: Cast) -> None:
    """Both halves are gated on running, which nothing does."""


@power("i1445p1", level=6, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="a melee attack misses you",
       on=Trigger(Miss, both(targets_me, by_melee), "a melee attack misses you"))
def i1445p1(c: Cast) -> None:
    c.shift(1)


@power("i2176x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.item_set()",))
def i2176x1(c: Cast) -> None:
    """The size of the bonus is how many items of one set are worn, and
    nothing groups items into sets."""


@power("i2176p1", level=6, cls=ITEM, usage=DAILY, action=MOVE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ILLUSION])
def i2176p1(c: Cast) -> None:
    """Visible again "at the end of this action", which is the end of the
    turn's move -- `When.EOT` is the nearest hold the engine keeps."""
    c.invisible(on=c.me, until=When.EOT)
    c.move(c.speed_of())


@power("i2387x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2387x1(c: Cast) -> None:
    _skills(c, 2, "acrobatics", "athletics", "stealth")


@power("i3220x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3220x1(c: Cast) -> None:
    """Rough water stays difficult, which is why the exemption is named
    rather than blanket."""
    c.ignores_difficult("water", on=c.me)


@power("i748x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i748x1(c: Cast) -> None:
    """`c.jump` asks for no Athletics check, so the printed bonus has no
    roll in a fight to reach."""


@power("i748p1", level=6, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF)
def i748p1(c: Cast) -> None:
    """`c.jump` takes squares, so the Athletics check the card rolls is
    folded into the distance: the modifier plus the three squares the
    running start is worth."""
    c.jump(3 + max(0, c.str_mod))


@power("i752x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i752x1(c: Cast) -> None:
    c.ignores_difficult("ice", on=c.me)


@power("i753x1", level=6, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i753x1(c: Cast) -> None:
    c.bonus("save", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=_holding(Condition.SLOWED, Condition.IMMOBILIZED,
                          Condition.RESTRAINED))


@power("i753p1", level=6, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def i753p1(c: Cast) -> None:
    """A saving throw off-turn, against whichever hold is standing."""
    c.save(on=c.me)


# -- level 7 ----------------------------------------------------------------


@power("i1005p1", level=7, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="an enemy misses you with an attack",
       on=Trigger(Miss, targets_me, "an enemy misses you"))
def i1005p1(c: Cast) -> None:
    """The augment is a power point spent to hand the use straight back,
    which is what `c.restore_use` is for."""
    c.shift(1)
    if c.points() >= 1 and c.may("augment the boots"):
        c.spend_points(1)
        c.restore_use(c.ref, on=c.me)


@power("i1149p1", level=7, cls=ITEM, usage=DAILY, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="you are hit by a power that pushes, pulls or slides you",
       on=Trigger(ForcedMove, targets_me, "you are pushed, pulled or slid"))
def i1149p1(c: Cast) -> None:
    """`ForcedMove` is a proposal its emitter reads back, and an interrupt
    is the window in which refusing it still counts."""
    c.cancel()


@power("i2368x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.bull_rush()",))
def i2368x1(c: Cast) -> None:
    """A bull rush is not an attack the engine names. The forced-movement
    half is exact: `c.forces` is handed `how` and `power`."""
    close = _reach_gate("close", "melee")
    c.forces(1, on=c.me,
             when=lambda ctx: (
                 ctx.get("how") in (Forced.PUSH, Forced.SLIDE)
                 and close(ctx)))


@power("i3214x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i3214x1(c: Cast) -> None:
    _skills(c, 2, "stealth")


@power("i3214p1", level=7, cls=ITEM, usage=DAILY, action=MOVE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.ILLUSION])
def i3214p1(c: Cast) -> None:
    """"Hidden (invisible and silent)" is `c.hide`, which stays on until
    something gives the wearer away."""
    c.hide(until=When.EOT)
    c.move(c.speed_of())


@power("i767x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i767x1(c: Cast) -> None:
    _on_second_wind(c, lambda: c.shift(2))


@power("i773x1", level=7, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i773x1(c: Cast) -> None:
    """`MoveEnd` rather than `MoveStart`: the shift has to have happened
    for the bonus to be the reward the card describes."""

    def shifted(ev: MoveEnd) -> None:
        if ev.actor != c.me or ev.kind_ != "shift":
            return
        c.bonus(AC, 1, on=c.me, until=When.EONT, kind="item")
        c.bonus(REF, 1, on=c.me, until=When.EONT, kind="item")

    c.watch(MoveEnd, shifted, until=When.ENCOUNTER, on=c.me)


@power("i773p1", level=7, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def i773p1(c: Cast) -> None:
    c.shift(2)


# -- level 8 ----------------------------------------------------------------


@power("i1478x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.prone_square()",))
def i1478x1(c: Cast) -> None:
    """Falling into a *different* square has no verb -- `c.prone` takes
    no destination. The advantage half is gated on being prone, so
    nothing else the wearer grants is cancelled with it."""
    c.no_advantage(on=c.me, until=When.ENCOUNTER,
                   when=lambda ctx: c.is_(Condition.PRONE, on=c.me))


@power("i2123x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i2123x1(c: Cast) -> None:
    _skills(c, 2, "acrobatics", "athletics")


@power("i2123p1", level=8, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF)
def i2123p1(c: Cast) -> None:
    """The defence gate is laid before the move so it is standing while
    the openings the move gives are taken."""
    c.bonus(AC, 2, on=c.me, until=When.EOT, kind="item",
            when=lambda ctx: bool(ctx.get("opportunity")))
    c.move(c.speed_of() + 1)


@power("i2670p1", level=8, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def i2670p1(c: Cast) -> None:
    """"If you move or are moved you lose these" is written as a gate on
    the square rather than as an effect somebody has to remember to end:
    the gate is asked each time a defence is read."""
    from combat_engine.engine import FORT, WILL

    start = c.here
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=c.me, until=When.SONT, kind="power",
                when=lambda ctx: c.here == start)


@power("i2734p1", level=8, cls=ITEM, usage=ENCOUNTER, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="you are subject to a push, pull or slide",
       on=Trigger(ForcedMove, targets_me, "you are pushed, pulled or slid"))
def i2734p1(c: Cast) -> None:
    """A slide of the wearer's own, after the shove -- which is why this
    one works as the printed reaction where refusing a shove would not."""
    c.slide(1, on=c.me)


@power("i2734p2", level=8, cls=ITEM, usage=DAILY, action=MOVE,
       reach=PERSONAL, target=SELF, no_provoke=True)
def i2734p2(c: Cast) -> None:
    """Height is a number the grid keeps, so "moving vertically if you
    wish" and the fall that follows are the engine's own business."""
    c.move(c.speed_of())


@power("i3219x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3219x1(c: Cast) -> None:
    """Marching for a day and what it costs the day after."""


@power("i3462p1", level=8, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF, keywords=[Keyword.TELEPORTATION],
       dropped=("c.moved_by_power()",))
def i3462p1(c: Cast) -> None:
    """The Requirement is that an attack power moved you this turn, and
    nothing records why a creature moved."""
    c.teleport(c.speed_of())


@power("i727x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i727x1(c: Cast) -> None:
    c.ignores_difficult("vehicle", on=c.me)


@power("i727p1", level=8, cls=ITEM, usage=DAILY, action=STANDARD,
       reach=PERSONAL, target=SELF)
def i727p1(c: Cast) -> None:
    """Jump, then use one of your own at-will attack powers. Both halves
    of "one of your at-will attack powers" are offered -- `c.borrowed_rows`
    filters the way the printed lines do and takes one range at a time --
    and the +1 is `once=True` because it is for that row's attack roll
    and not for the rest of the turn.

    The chosen row picks its own targets: it is being used, not aimed by
    this one, so no `on=`."""
    c.jump(c.speed_of())
    options = [
        *c.borrowed_rows(c.me, melee=True),
        *c.borrowed_rows(c.me, melee=False),
    ]
    if not options:
        return
    chosen = c.choose(options, "which at-will attack to use") or options[0]
    c.bonus("attack", 1, on=c.me, until=When.EOT, kind="power", once=True)
    c.use_power(chosen)


@power("i755p1", level=8, cls=ITEM, usage=ENCOUNTER, action=INTERRUPT,
       reach=PERSONAL, target=SELF,
       trigger="an attack would teleport you",
       on=Trigger(MoveStart,
                  lambda world, me, ev: (
                      ev.actor == me and ev.kind_ == "teleport"),
                  "you would be teleported"))
def i755p1(c: Cast) -> None:
    """`MoveStart` is a proposal, so refusing it in the interrupt window
    is what "you do not teleport" means."""
    c.cancel()


@power("i758x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i758x1(c: Cast) -> None:
    """No type word on the card, so the bonus is untyped."""
    c.bonus(REF, 1, on=c.me, until=When.ENCOUNTER)


@power("i840x1", level=8, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.skill_circumstance()",))
def i840x1(c: Cast) -> None:
    _skills(c, 3, "athletics")
    _half_fall(c)


@power("i840p1", level=8, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF,
       trigger="you fall 10 feet or more",
       on=Trigger(Fell,
                  lambda world, me, ev: ev.actor == me and ev.squares >= 2,
                  "you fall two squares or more"))
def i840p1(c: Cast) -> None:
    """Ten feet is two squares. `c.cushion` with no number is "no damage
    and consequently not prone", which is the whole sentence."""
    c.cushion()


# -- level 9 ----------------------------------------------------------------


@power("i3215x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i3215x1(c: Cast) -> None:
    """`c.jump` asks for no Athletics check, so the printed bonus has no
    roll in a fight to reach."""


@power("i3215p1", level=9, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF, no_provoke=True)
def i3215p1(c: Cast) -> None:
    c.jump(10)


@power("i3216p1", level=9, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF)
def i3216p1(c: Cast) -> None:
    """`c.hover` goes up and stays up; the descent at the end is what the
    duration running out already does, without falling damage."""
    c.hover(4, on=c.me, until=When.EONT)


@power("i3218x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.move_through_enemies()",))
def i3218x1(c: Cast) -> None:
    """Only the overhead modes pass over an occupied square, and nothing
    lets a walker through one."""


@power("i751p1", level=9, cls=ITEM, usage=ENCOUNTER, action=MINOR,
       reach=PERSONAL, target=SELF)
def i751p1(c: Cast) -> None:
    c.extra_action(MOVE, on=c.me)


@power("i754x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i754x1(c: Cast) -> None:
    c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: c.bloodied(on=c.me))


@power("i754p1", level=9, cls=ITEM, usage=DAILY, action=REACTION,
       reach=PERSONAL, target=SELF,
       trigger="you become bloodied",
       on=Trigger(Bloodied, about_me, "you become bloodied"))
def i754p1(c: Cast) -> None:
    c.shift(max(1, c.speed_of() // 2))


@power("i757x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i757x1(c: Cast) -> None:
    """Tracks, and how hard they are to read. Not a fight."""


@power("i765x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.wearing()",))
def i765x1(c: Cast) -> None:
    """Which armour a character has on is not a question the engine
    answers, so the bonus stands whatever is worn."""
    c.bonus("speed", 1, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i774x1", level=9, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.on_grab_attack()",))
def i774x1(c: Cast) -> None:
    """A grab is an ordinary attack the engine does not label, so the
    attack half of the property has nothing to gate on."""
    _skills(c, 2, "athletics")


@power("i774p1", level=9, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, dropped=("c.on_grab_attack()",))
def i774p1(c: Cast) -> None:
    c.bonus("skill:athletics", 4, on=c.me, until=When.EONT, kind="item")


# -- level 10 ---------------------------------------------------------------


@power("i2518p1", level=10, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, dropped=("c.roll_gate()",))
def i2518p1(c: Cast) -> None:
    """"Roll 5 or lower and you may reroll" is a condition on the die, and
    a modifier is decided before the die is read."""
    c.bonus("speed", 2, on=c.me, until=When.EONT, kind="power")


@power("i3016x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, todo=("c.wall_walk()",))
def i3016x1(c: Cast) -> None:
    """The grid keeps a height and no surface to stand on sideways."""


@power("i3016p1", level=10, cls=ITEM, usage=DAILY, action=MINOR,
       reach=PERSONAL, target=SELF, todo=("c.wall_walk()",))
def i3016p1(c: Cast) -> None:
    """Same gap, for the whole encounter instead of one turn."""


@power("i570x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i570x1(c: Cast) -> None:
    c.forces(1, on=c.me, when=lambda ctx: ctx.get("how") is Forced.PUSH)
    _after_charge(c, lambda: c.shift(1))


@power("i761x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF, dropped=("c.wearing()",))
def i761x1(c: Cast) -> None:
    c.bonus("speed", 1, on=c.me, until=When.ENCOUNTER, kind="item")


@power("i761p1", level=10, cls=ITEM, usage=ENCOUNTER, action=FREE,
       reach=PERSONAL, target=SELF, out_of_combat=True)
def i761p1(c: Cast) -> None:
    """Swimming, which no fight rolls. Declared inert so the action menu
    stops offering a free action whose whole payout is a bonus to a check
    that never happens."""


@power("i776x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF)
def i776x1(c: Cast) -> None:
    c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER, kind="item",
            when=lambda ctx: bool(ctx.get("charge")))


@power("i776p1", level=10, cls=ITEM, usage=DAILY, action=FREE,
       reach=PERSONAL, target=SELF, todo=("c.charge_with()",))
def i776p1(c: Cast) -> None:
    """A charge ends in a basic attack or a bull rush and nothing lets
    another row be substituted for the swing."""


@power("i802x1", level=10, cls=ITEM, action=ActionType.NONE,
       reach=PERSONAL, target=SELF,
       dropped=("c.skill_circumstance()",))
def i802x1(c: Cast) -> None:
    c.ignores_difficult("forest", on=c.me)
    _skills(c, 4, "acrobatics", "athletics")


@power("i802p1", level=10, cls=ITEM, usage=ENCOUNTER, action=MOVE,
       reach=PERSONAL, target=SELF)
def i802p1(c: Cast) -> None:
    c.mode("climb", c.speed_of(), on=c.me, until=When.EOT)
    c.no_advantage(on=c.me, until=When.EOT)
