"""Monster abilities, level 12: the brutes `brutes.py` left undeclared.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=AC,
printed=17)` and `Damage("3d12", 0)` -- and the engine takes the level back
out of the attack and rescales the damage if a fight is being played on
another edition's maths. See `engine/scaling.py` and
`engine/monster_math.py`.

The conventions of the eleven levels below, and of `brutes.py` beside this
file, are kept:

* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it for the rest of the fight; several rows the database
  files as standard actions are plainly traits and are written as such;
* a card with no printed range at all is **melee 1**;
* a blast or burst reading "creatures in the blast/burst" is
  `EACH_CREATURE`; one naming no target set at all takes **enemies**;
* a printed "Effect (Immediate Interrupt)" is `action=INTERRUPT`, "Effect
  (Immediate Reaction)" is `ActionType.IMMEDIATE_REACTION`, and "No Action"
  is `action=FREE` -- whatever the database's action column says, because
  `WINDOW_OF` maps no window to `ActionType.NONE` and a declared trigger on
  one could never be offered at all;
* `half_on_miss=True` is card data only, so the Miss line is written out as
  `else: c.hit(half=True)` as well;
* a blow of two or more damage types rolled once keeps the first in the
  header and is marked `dropped=("Damage(dtypes=)",)`; two separately named
  amounts are two packets and need no marker;
* a parenthetical "(+N while bloodied)" beside a printed attack total is one
  attack line with two numbers, so the header keeps the printed one -- which
  is what rescales -- and the difference is handed to `c.strike(plus=...)`;
  two modifiers of one kind do not add, so this way there is only ever one;
* a helper written for an earlier level is imported rather than copied, and
  the two written for `brutes.py` beside this file are imported too.

Nine readings this file had to settle.

**Sustaining a grab needs nothing said; the payout does.** m4266a0 and
m4338a2 both print "Sustain Minor: it sustains the grab, and the target
takes N damage". A grab is cleared by an escape and by nothing else, so the
first half is already true of a grab that is simply left alone -- there is
no duration to renew. The half that would otherwise be lost is the damage,
which is a `When.SUSTAIN` hold on the victim with `c.on_sustain` paying it
out. `_grab_and_sustain` is that shape.

**A death throe's trigger arrives in the keywords column.** Six rows here
are filed as standard at-will actions whose keywords read "when reduced to 0
hit points": m1152a2, m1783a2, m4266a6, m4362a2, m5463a3 and m6156a1. Each
is written as the free action `Trigger(Dropped, about_me, ...)` it means, and
the trigger is handed on to any row it reaches for -- `use` only makes the
exception for a creature answering its own downfall while it can see that is
what is happening.

**A trample has to rank its own destinations.** `_trample` is imported from
`brutes.py`: a bare `c.overrun()` spends the creature's plain speed and,
with no decider installed, takes the lowest corner of the board, which walks
over nobody. m1098a2 and m4266a5 both want the squares ranked by who is in
the way. On a huge creature it can still find nobody beneath it, which is a
property of the generated boards and not of the row.

**Standing back up is the row's own body.** `c.revives_unless` is a
declaration for the AI policy and implements nothing, so m3797a1 and m4338a4
pair it with a `DamageApplied` watch remembering the type and a `Dropped`
watch doing the healing. The rise is taken inside the same window rather
than deferred to the creature's next turn: `_die` lifts the body off the
grid, so nothing can reach it in between to spend the window the card leaves
open, and a body that waits a round is one `threat_removed` has written off.

**Heads are a count on the board, not a duration.** m115807a2 destroys one
when the creature's hit points first cross three quarters, a half and a
quarter of its maximum -- the three printed numbers are those fractions, so
they are read off `Health` rather than written down -- and grows two back at
the start of its next turn unless cold or acid arrived first. m115807a5 and
m115807a6 read the count, and a5's printed "Recharge when it loses a head"
is `_recharge_on` watching the same damage.

**A form that is asked about has to leave a label.** m4338a2's printed
Requirement is "usable only in" the shape m4338a5 takes, and asking the
engine what form a creature is in is the standing gap `c.in_form()` names.
A label on the hold m4338a5 lays is the same question answered without it,
and `requires=` reads it, so neither row carries a marker.

**"Vulnerable to the m4307's attacks" is narrower than the verb.**
`c.vulnerable` has no `when=`, so m4307a2 lays the vulnerability against
everything and names the gap. The second thing it lays is a marker effect
with a label, which is what m4307a1's printed recharge sentence reads to ask
whether anybody carrying it has walked more than two squares off.

**Two of these cards come out of extraction damaged.** m1952a1's attack line
is "+13 vs ;" with no defence at all and its damage printed twice over, so
the roll is named rather than guessed and what plays is the sentence that
survived. m1938a0 and m1938a1 spell a *different* stat block's id for the
creature doing the healing; the creature is this one, and `c.me` is who
regains the hit points. See the report.

**A clause about what a creature counts as to somebody else.** m2343a1 and
m1152a3 have no combat content at all -- one is a statement about another
creature's effects, the other a sense of direction toward something that is
not on the board -- so both are `out_of_combat=True`.

Each stat block in ref order.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_02.lurkers_sa import _triggering_enemy
from combat_engine.content.monsters.level_03.skirmishers_sa import _shoved_by_hand
from combat_engine.content.monsters.level_04.skirmishers import _struck
from combat_engine.content.monsters.level_07.brutes import _living
from combat_engine.content.monsters.level_07.soldiers import _hands_free, _recharge_on
from combat_engine.content.monsters.level_08.brutes import _has_hold, _holding
from combat_engine.content.monsters.level_10.soldiers import _drag_beside
from combat_engine.content.monsters.level_11.soldiers import _charge
from combat_engine.content.monsters.level_12.brutes import _in_reach, _trample
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Health,
    Keyword,
    Melee,
    Ranged,
    Size,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.dsl import use
from combat_engine.engine.events import (
    ActionSpent,
    AttackDeclared,
    Bloodied,
    ConditionApplied,
    DamageApplied,
    DamageRolled,
    Dropped,
    ForcedMove,
    Hit,
    Miss,
    MoveEnd,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.grid import distance
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import alive, distance_between, is_, squares, team
from combat_engine.engine.triggers import Trigger, about_me, both, by_keyword, hits_me, targets_me

#: The three types m3844 deals as one blow.
_ELEMENTS = (DamageType.COLD, DamageType.FIRE, DamageType.LIGHTNING)

#: The two conditions m1938a2 and m5219a3 answer, beside being shoved.
_PINNED = (Condition.IMMOBILIZED, Condition.RESTRAINED)


# --------------------------------------------------------------------------
# shapes several stat blocks here share
# --------------------------------------------------------------------------


def _no_bigger_than(c: Cast, who: int, cap: Size) -> bool:
    """"A Medium or smaller target". `Size.order` and not `Size.squares`:
    Tiny, Small and Medium all occupy one square, so a comparison written
    against the footprint cannot tell them apart."""
    mine = c.size_of(on=who)
    return mine is not None and mine.order <= cap.order


def _feeds_on_blood(c: Cast, amount: int) -> None:
    """Temporary hit points each time it bloodies or finishes an enemy.

    `Bloodied` and `Dropped` both carry `source`, whoever crossed the line,
    so "each time **it**" is that field and not a guess off the log. Both are
    watched because the printed sentence names both moments and a creature
    taken from healthy to dead in one blow crosses both.
    """
    ref, mine = c.ref, c.me

    def fed(ev: Any) -> None:
        if getattr(ev, "source", None) != mine:
            return
        who = getattr(ev, "actor", None)
        if who is None or who == mine or team(c.world, who) is team(c.world, mine):
            return
        c.temp_hp(amount, on=mine)

    c.watch(Bloodied, fed, until=When.ENCOUNTER, on=mine, label=f"{ref} bloodied")
    c.watch(Dropped, fed, until=When.ENCOUNTER, on=mine, label=f"{ref} felled")


def _slowed_by(c: Cast, dtype: DamageType) -> None:
    """"Whenever it takes <type> damage, it is slowed until the end of its
    next turn." Read off `types()`, which answers for a blow of several."""
    me = c.me

    def felt(ev: DamageApplied) -> None:
        if ev.target == me and ev.amount > 0 and dtype in ev.types():
            c.slowed(on=me, until=When.EONT)

    c.watch(DamageApplied, felt, until=When.ENCOUNTER, on=me, label=c.ref)


def _rises_unless(c: Cast, hp: int, *types: DamageType, prone: bool = False) -> None:
    """It gets back up unless one of those types put it down, and only once.

    `Dropped` says who struck the blow and not what with, so the damage type
    comes off the `DamageApplied` immediately before it -- the blow that
    crossed the line, and the only one that can be. `c.revives_unless` is the
    declaration that stops the policy writing the creature off; this watch is
    what actually stands it up.
    """
    me = c.me
    c.revives_unless(*types, on=me)
    last = {"finished": False}
    risen = {"count": 0}

    def took(ev: DamageApplied) -> None:
        if ev.target == me:
            last["finished"] = any(t in ev.types() for t in types)

    def rise(ev: Dropped) -> None:
        if ev.actor != me or last["finished"] or risen["count"]:
            return
        risen["count"] += 1
        if c.reanimate(on=me, hp=hp) and prone:
            c.prone(on=me)

    c.watch(DamageApplied, took, until=When.ENCOUNTER, on=me, label=f"{c.ref} last blow")
    c.watch(Dropped, rise, until=When.ENCOUNTER, on=me, label=f"{c.ref} rises")


def _grab_and_sustain(
    c: Cast, victim: int, amount: int, dtype: DamageType = DamageType.UNTYPED
) -> None:
    """Take hold, and pay out each time the printed Sustain Minor is paid.

    A grab is cleared by an escape and nothing else, so "it sustains the
    grab" needs nothing said -- there is no duration to renew. The clause
    that does need saying is the damage, which is a hold on the victim with
    the sustain cost the card prints.
    """
    c.grab(on=victim)
    held = c.effect(f"{c.ref} hold", until=When.SUSTAIN, sustain=MINOR, on=victim)
    c.on_sustain(held, lambda: c.flat(amount, dtype=dtype, on=victim))


def _drains(c: Cast, victim: int, amount: int) -> None:
    """"The target loses a healing surge, and it regains N hit points."

    `c.spend_surge` is a surge spent for nothing, which is what losing one
    is. The hit points go to `c.me` -- the card spells another stat block's
    id here, and the creature doing the draining is this one.
    """
    c.spend_surge(on=victim)
    c.heal(amount, on=c.me)


def _saves_off(c: Cast, ref: str, radius: int) -> None:
    """The interrupt m1938a2 and m5219a3 both print: make a saving throw,
    and on a save negate what provoked it and swing for free.

    `bare=True` because there is no standing save-ends effect to roll
    against -- the throw is against the thing arriving this instant. The
    trigger is handed to the swing: a free action out of turn is only
    allowed while the dispatcher can see what is being answered.
    """
    if not c.save(on=c.me, bare=True):
        return
    c.cancel()
    victim = _in_reach(c, radius, c.ref)
    if victim is not None:
        use(c.world, c.me, ref, targets=[victim], spend=False, trigger=c.trigger)


def _after_charge(c: Cast, fn: Callable[[], None]) -> None:
    """A trait that pays out at the end of a charge, hit or miss.

    The charge flag rides on `Hit` and `Miss` as a plain attribute, and a
    charge makes exactly one attack -- so one callback on both events fires
    once per charge, and the payout lands after the charge attack has
    resolved rather than before it, which is what "after the charge" means.
    `AttackDeclared` carries the flag too and would be the wrong moment.
    """
    me = c.me

    def done(ev: Any) -> None:
        if getattr(ev, "attacker", None) != me or not getattr(ev, "charge", False):
            return
        fn()

    for kind in (Hit, Miss):
        c.watch(kind, done, until=When.ENCOUNTER, on=me, label=f"{c.ref} {kind.__name__}")


def _aura_bite(c: Cast, radius: int, amount: int, dtype: DamageType) -> None:
    """"Aura N: an enemy that ends its turn in the aura takes N damage."

    Membership is asked at the moment the turn ends rather than diffed:
    `c.in_my_aura` is the same question the printed sentence asks, and the
    aura is the thing the UI draws.
    """
    me, label = c.me, c.ref
    c.aura(radius, label=label, until=When.ENCOUNTER)

    def ending(ev: TurnEnd) -> None:
        who = ev.actor
        if getattr(ev, "ghost", False) or who == me:
            return
        if team(c.world, who) is team(c.world, me):
            return
        if c.in_my_aura(who, label=label):
            c.flat(amount, dtype=dtype, on=who)

    c.watch(TurnEnd, ending, until=When.ENCOUNTER, on=me, label=f"{label} ring")


def _twice(c: Cast, ref: str) -> None:
    """"It uses <row> twice." Each use picks its own target, which is what a
    row printing no target of its own leaves open."""
    for _ in range(2):
        victim = _in_reach(c, c.reach(ref), c.ref)
        if victim is None:
            return
        use(c.world, c.me, ref, targets=[victim], spend=False)


def _enemy_ends_within(squares_: int) -> Callable[[World, int, Any], bool]:
    """"An enemy ends its turn within N squares of it."""

    def test(world: World, me: int, ev: Any) -> bool:
        who = getattr(ev, "actor", None)
        if who is None or getattr(ev, "ghost", False) or who == me:
            return False
        if team(world, who) is team(world, me):
            return False
        return distance_between(world, me, who) <= squares_

    return test


def _adjacent_enemy_falls(world: World, me: int, ev: Any) -> bool:
    """"When an adjacent enemy becomes bloodied or is reduced to 0 hit
    points." Sides are compared directly rather than through `query.enemies`,
    which filters out the dead -- and a creature that has just dropped is
    half of what this trigger is about."""
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    if team(world, who) is team(world, me):
        return False
    return distance_between(world, me, who) <= 1


def _ally_bloodied_within_6(world: World, me: int, ev: Bloodied) -> bool:
    """"An enemy bloodies an ally within 6 squares of it." `actor` is who was
    bloodied and `source` is who did it, so both halves are on the event."""
    who, by = ev.actor, getattr(ev, "source", None)
    if by is None or who == me or team(world, who) is not team(world, me):
        return False
    return distance_between(world, me, who) <= 6


def _blow_before(world: World, ev: Any, victim: int) -> DamageApplied | None:
    """The blow that caused this `Bloodied` or `Dropped`.

    Neither event carries what it was dealt with, and both are emitted from
    inside the damage that caused them. So the attribution exists in exactly
    one place -- the log -- and the nearest earlier blow on that creature is
    the one to read.
    """
    for past in reversed(world.bus.log[: ev.seq]):
        if isinstance(past, DamageApplied) and past.target == victim:
            return past
    return None


def _bloodied_by_row(ref: str) -> Callable[[World, int, Bloodied], bool]:
    """"An enemy is bloodied by its <named> attack" -- the row matters, and
    this stat block has two attacks that could do it."""

    def test(world: World, me: int, ev: Bloodied) -> bool:
        if getattr(ev, "source", None) != me:
            return False
        blow = _blow_before(world, ev, ev.actor)
        return blow is not None and blow.detail == ref

    return test


def _pinned_down(world: World, me: int, ev: ConditionApplied) -> bool:
    return ev.target == me and ev.condition in _PINNED


def _shoved(world: World, me: int, ev: ForcedMove) -> bool:
    return ev.target == me


# ==========================================================================
# m1098
# ==========================================================================


@power(
    "m1098a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 6),
)
def m1098a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m1098a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    charges=True,
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d10", 6),
)
def m1098a1(c: Cast) -> None:
    """The row *is* the charge, so the flag goes up by hand and the header
    rolls: `c.charge_at` reaches its swing through `use`, and the row it
    would reach for is this one, already in flight."""
    victim = c.target
    if victim is None:
        return

    def blow() -> None:
        if not c.strike(on=victim):
            return
        c.hit(on=victim)
        if _no_bigger_than(c, victim, Size.MEDIUM):
            c.push(3, on=victim)
            c.prone(on=victim)

    _charge(c, victim, blow)


@power(
    "m1098a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d8", 6),
)
def m1098a2(c: Cast) -> None:
    """It walks over whoever is standing in the way.

    Nothing waives the opportunity attacks and nothing should: the printed
    line says the movement provokes them. The trample attack has no ref of
    its own, so the roll is this row's own header aimed at each creature
    `_trample` reports it walked through.
    """
    for victim in _trample(c, c.speed_of()):
        if victim not in c.enemies() or not alive(c.world, victim):
            continue
        if c.strike(on=victim):
            c.hit(on=victim)
            c.prone(on=victim)


@power(
    "m1098a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1098a3(c: Cast) -> None:
    """Two of its own rows, and the card offers three ways to pick them.

    "In any order" is a choice with no mechanical weight here -- neither
    half changes what the other can reach -- so the pair is offered and the
    order is the one printed first.
    """
    plans = ["m1098a0 then m1098a1", "m1098a0 then m1098a2", "m1098a0 twice"]
    plan = c.choose(plans, "m1098a3: which pair") or plans[-1]
    second = "m1098a1" if plan.endswith("a1") else "m1098a2" if plan.endswith("a2") else "m1098a0"
    first = _in_reach(c, 2, c.ref)
    if first is not None:
        use(c.world, c.me, "m1098a0", targets=[first], spend=False)
    if second == "m1098a2":
        use(c.world, c.me, "m1098a2", spend=False)
        return
    victim = _in_reach(c, 2, c.ref)
    if victim is not None:
        use(c.world, c.me, second, targets=[victim], spend=False)


# ==========================================================================
# m1152
# ==========================================================================

_M1152_BLED = "its attack bloodies an enemy"
_M1152_FELLED = "it is reduced to 0 hit points"


@power(
    "m1152a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 8),
)
def m1152a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m1152a1",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=14),
    trigger=_M1152_BLED,
    on=Trigger(Bloodied, when=_bloodied_by_row("m1152a0"), text=_M1152_BLED),
)
def m1152a1(c: Cast) -> None:
    """No damage on the hit line at all: the hold is the whole of it.

    "Cursed with" is read as the curse it says plus the domination the same
    sentence names -- `c.curse` on its own lasts the fight and means nothing
    to a creature that is not a warlock's quarry, so the condition is what
    carries the printed consequence.
    """
    victim = _triggering_enemy(c)
    if victim is None or not c.strike(on=victim):
        return
    c.curse(on=victim)
    c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)


@power(
    "m1152a2",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=14),
    trigger=_M1152_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M1152_FELLED),
)
def m1152a2(c: Cast) -> None:
    """Filed as a standard at-will and plainly a death throe: the trigger
    arrives in the keywords column, and a creature may answer its own
    downfall because the dispatcher makes the exception for this shape."""
    if c.strike():
        c.curse()
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m1152a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m1152a3(c: Cast) -> None:
    """Distance and direction to something that is not on the board. There
    is no fight in it, and nothing to invent one from."""


# ==========================================================================
# m115807
# ==========================================================================

_M115807_HEADS: dict[int, int] = {}
_M115807_PENDING: dict[int, bool] = {}
_M115807_SHIELDED: dict[int, bool] = {}
_M115807_NEARBY_END = "an enemy ends its turn within 2 squares of it"


@power(
    "m115807a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115807a0(c: Cast) -> None:
    c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)


@power(
    "m115807a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("actions.legal(free_despite_stun=)",),
)
def m115807a1(c: Cast) -> None:
    """"While stunned or dominated, it can take free actions" has no hook --
    those conditions block every action through the same gate a free action
    also has to pass, and nothing in `actions.legal` carves out an exception
    for one word of condition."""


@power(
    "m115807a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115807a2(c: Cast) -> None:
    """Four heads, and the three printed thresholds are three quarters, a
    half and a quarter of its maximum -- so they are read off `Health`
    rather than written down. A head grows back at the start of its next
    turn unless cold or acid reached it inside the window."""
    me = c.me
    _M115807_HEADS[me] = 4
    _M115807_PENDING[me] = False
    _M115807_SHIELDED[me] = False
    stats = c.world.get(me, Health)
    bounds = (
        [stats.max_hp * 3 // 4, stats.max_hp // 2, stats.max_hp // 4]
        if stats is not None
        else []
    )
    crossed: set[int] = set()

    def lost_head(ev: DamageApplied) -> None:
        if ev.target != me:
            return
        now = c.world.get(me, Health)
        if now is None:
            return
        for i, bound in enumerate(bounds):
            if i not in crossed and now.hp < bound:
                crossed.add(i)
                _M115807_HEADS[me] = max(1, _M115807_HEADS.get(me, 4) - 1)
                _M115807_PENDING[me] = True
                _M115807_SHIELDED[me] = False
        if DamageType.COLD in ev.types() or DamageType.ACID in ev.types():
            _M115807_SHIELDED[me] = True

    def regrow(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        if _M115807_PENDING.get(me) and not _M115807_SHIELDED.get(me):
            _M115807_HEADS[me] = min(4, _M115807_HEADS.get(me, 4) + 2)
        _M115807_PENDING[me] = False
        _M115807_SHIELDED[me] = False

    c.watch(DamageApplied, lost_head, until=When.ENCOUNTER, on=me, label=f"{c.ref} heads")
    c.watch(TurnStart, regrow, until=When.ENCOUNTER, on=me, label=f"{c.ref} regrow")


@power(
    "m115807a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115807a3(c: Cast) -> None:
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


@power(
    "m115807a4",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d12", 0),
)
def m115807a4(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115807a5",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 5, dtype=DamageType.FIRE, kind=LIMITED),
)
def m115807a5(c: Cast) -> None:
    """The printed "Recharge when it loses a head" sits on top of the die the
    database files: `_recharge_on` watches the same damage m115807a2 counts
    heads off, and compares the count with what it last saw. The two only
    ever agree to make the row available sooner."""
    me = c.me
    if c.first:
        seen = {"heads": _M115807_HEADS.get(me, 4)}

        def shorter(ev: DamageApplied) -> bool:
            now = _M115807_HEADS.get(me, 4)
            lost = now < seen["heads"]
            seen["heads"] = now
            return lost

        _recharge_on(c, DamageApplied, shorter)
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.FIRE)
        c.push(3)


@power(
    "m115807a6",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=ONE_CREATURE,
)
def m115807a6(c: Cast) -> None:
    """One attack per head, and the fewer it has the harder each one lands.

    The bonus is flat damage after the fact rather than a modifier: it is
    printed as a bonus to the damage rolls of *these* attacks and nothing
    else, and a held modifier would follow the creature out of the row.
    """
    victim = c.target
    if victim is None:
        return
    heads = _M115807_HEADS.get(c.me, 4)
    bonus = 15 if heads == 1 else 5 if heads == 2 else 0
    for _ in range(max(heads, 1)):
        if not alive(c.world, victim):
            return
        pick = c.choose(["m115807a4", "m115807a5"], f"{c.ref}: which attack") or "m115807a4"
        c.use_power(pick, on=victim)
        if c.landed and bonus:
            c.flat(bonus, on=victim)


@power(
    "m115807a7",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M115807_NEARBY_END,
    on=Trigger(TurnEnd, when=_enemy_ends_within(2), text=_M115807_NEARBY_END),
)
def m115807a7(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    for _ in range(2):
        c.use_power("m115807a4", on=foe)


# ==========================================================================
# m115936
# ==========================================================================


@power(
    "m115936a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m115936a0(c: Cast) -> None:
    _aura_bite(c, 1, 10, DamageType.POISON)


@power(
    "m115936a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115936a1(c: Cast) -> None:
    """Three clauses, and the third is already true of the grid.

    Sharing its square lives on the creature being entered rather than on
    the mover. The shove immunity is gated: `c.immovable` would refuse a
    push from anywhere and the printed line refuses only melee and ranged
    attacks, so it is written as a shortening large enough to swallow any of
    them with the reach read off the row that shoved. Squeezing through the
    narrowest opening needs nothing -- the smallest gap the grid has is one
    square, which this creature already fits.
    """
    c.shares_space(difficult=True)
    c.resist_forced(99, when=_shoved_by_hand)


@power(
    "m115936a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 8, dtype=DamageType.POISON),
)
def m115936a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


# ==========================================================================
# m1783
# ==========================================================================

_M1783_FELLED = "it is reduced to 0 hit points or fewer"


@power(
    "m1783a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 6),
)
def m1783a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1783a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d10", 6, kind=LIMITED),
)
def m1783a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m1783a2",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d6", 5),
    trigger=_M1783_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M1783_FELLED),
)
def m1783a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m1909
# ==========================================================================


@power(
    "m1909a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d10", 5, dtype=DamageType.COLD),
    dropped=("Damage(dtypes=)",),
)
def m1909a0(c: Cast) -> None:
    """One roll of two types, and `Damage` holds one. The cold half is
    declared and the necrotic half of the same packet is the named gap."""
    if c.strike():
        c.hit()


@power(
    "m1909a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d10", 5, dtype=DamageType.COLD, kind=LIMITED),
    dropped=("Damage(dtypes=)",),
)
def m1909a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)


@power(
    "m1909a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD, Keyword.NECROTIC],
)
def m1909a2(c: Cast) -> None:
    """The shift comes first because the printed sentence puts it there, and
    a step taken afterwards could not bring anybody into reach."""
    c.shift(1)
    victim = _in_reach(c, 1, c.ref)
    if victim is not None:
        use(c.world, c.me, "m1909a0", targets=[victim], spend=False)


# ==========================================================================
# m1938
# ==========================================================================

_M1938_HELD = "it would be immobilized, restrained, pushed, pulled or slid"


@power(
    "m1938a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 3),
)
def m1938a0(c: Cast) -> None:
    """"Plus 5 necrotic damage" is a second packet rather than a second type
    on the first, so it is rolled flat beside the header's own and needs no
    marker. The hit points go to `c.me`: the card spells another stat
    block's id for the creature that regains them."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.flat(5, dtype=DamageType.NECROTIC)
    c.grab(on=victim)
    _drains(c, victim, 10)


@power(
    "m1938a1",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(2),
    target=NO_TARGET,
    once_per_round=True,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=13),
    requires=_has_hold,
    requires_text="it must have a creature grabbed",
)
def m1938a1(c: Cast) -> None:
    """"Targets a creature grabbed by it" is narrower than any `Target` can
    say, so the Requirement carries the caster's half and the body picks.

    The Effect is written before the attack, which is one of the two orders
    the card allows, and `_drag_beside` is what "pulling the target with it"
    means on a grid: the grab survives the move either way, so the pull is
    the part that has to be said.
    """
    held = sorted(_holding(c.world, c.me))
    victim = c.choose(held, f"{c.ref}: which of them it drags") if held else None
    if victim is None:
        return
    c.shift(2)
    _drag_beside(c, victim, c.me, 2)
    if c.strike(on=victim):
        _drains(c, victim, 10)


@power(
    "m1938a2",
    level=12,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1938_HELD,
    on=(
        Trigger(ConditionApplied, when=_pinned_down, text=_M1938_HELD),
        Trigger(ForcedMove, when=_shoved, text=_M1938_HELD),
    ),
)
def m1938a2(c: Cast) -> None:
    """Both halves of the printed trigger are declared: a condition arriving
    and a shove arriving are two events, and declaring one of them would
    look finished and answer half the sentence."""
    _saves_off(c, "m1938a0", 2)


@power(
    "m1938a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1938a3(c: Cast) -> None:
    """A Large living humanoid it kills gets up on its side next turn.

    The rise is held to the start of the creature's own next turn, as
    printed, because nothing else about the row is urgent -- the body is not
    reachable in between and there is no window to lose. "Free-willed" has
    nowhere to go: `c.summon` puts a creature on a side, and the only side
    the engine can give it is the one that made it. Noted rather than
    marked, because a third team is a board question and not a verb.
    """
    me = c.me

    def slain(ev: Dropped) -> None:
        who = ev.actor
        if getattr(ev, "source", None) != me or who == me:
            return
        if not _living(c, who) or not c.is_kind("humanoid", on=who):
            return
        if c.size_of(on=who) is not Size.LARGE:
            return
        pending = {"due": True}

        def wake(turn: TurnStart) -> None:
            if turn.ghost or turn.actor != me or not pending["due"]:
                return
            pending["due"] = False
            c.summon("m1938")

        c.watch(TurnStart, wake, until=When.ENCOUNTER, on=me, label=f"{c.ref} rises")

    c.watch(Dropped, slain, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m1952
# ==========================================================================

_M1952_NEARBY_FALLS = "an adjacent enemy becomes bloodied or is reduced to 0 hit points"


@power(
    "m1952a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 5),
)
def m1952a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m1952a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
    dropped=("etl.monster.attack_defence()",),
)
def m1952a1(c: Cast) -> None:
    """The card's own attack line comes out of extraction as "+13 vs ;" with
    no defence at all, and a damage expression beside it that belongs to no
    sentence. Neither can be declared without inventing a number, so the
    roll is named rather than guessed and what plays is the sentence that
    survived: two of its own slams."""
    _twice(c, "m1952a0")


@power(
    "m1952a2",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d12", 5),
    trigger=_M1952_NEARBY_FALLS,
    on=(
        Trigger(Bloodied, when=_adjacent_enemy_falls, text=_M1952_NEARBY_FALLS),
        Trigger(Dropped, when=_adjacent_enemy_falls, text=_M1952_NEARBY_FALLS),
    ),
)
def m1952a2(c: Cast) -> None:
    """Both printed moments are declared. `PowerUsed.targets` is not the
    triggering enemy and is no stand-in for it, so the victim comes off the
    event being answered."""
    victim = _triggering_enemy(c)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.heal(57, on=c.me)


# ==========================================================================
# m1968
# ==========================================================================


@power(
    "m1968a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 7, dtype=DamageType.NECROTIC),
    dropped=("c.contract(ref)",),
)
def m1968a0(c: Cast) -> None:
    """The bloodied line is a second expression rather than a rider, so the
    header keeps the printed one and the other is rolled here; the two
    points on the attack are a plus rather than a bonus, because two
    bonuses of one kind do not add. The disease the hit line names is the
    gap: nothing gives a creature one."""
    hard = c.bloodied(c.me)
    if not c.strike(plus=2 if hard else 0):
        return
    if hard:
        c.damage("3d8", 9, dtype=DamageType.NECROTIC)
    else:
        c.hit()


# ==========================================================================
# m2343
# ==========================================================================


@power(
    "m2343a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 7),
)
def m2343a0(c: Cast) -> None:
    hard = c.bloodied(c.me)
    if not c.strike(plus=2 if hard else 0):
        return
    if hard:
        c.damage("3d8", 9)
    else:
        c.hit()


@power(
    "m2343a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m2343a1(c: Cast) -> None:
    """The whole printed line is what this creature counts as to a kind of
    creature that is not on the board. Nothing in a fight reads it, and the
    sentence names no effect to hang on anything."""


# ==========================================================================
# m3797
# ==========================================================================


@power(
    "m3797a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 10, kind=MINION),
)
def m3797a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3797a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m3797a1(c: Cast) -> None:
    """Acid or fire finishes it; anything else only puts it down.

    The printed window -- "remains at 0 hit points until the start of its
    next turn" -- cannot be played out: `_die` lifts the body off the grid,
    so nothing can reach it in between to spend the window, and a minion
    that waits a round is one the policy has already written off. So the
    rise is taken inside the same window the drop is announced in, prone,
    which is what the card leaves standing.
    """
    _rises_unless(c, 1, DamageType.ACID, DamageType.FIRE, prone=True)


# ==========================================================================
# m3844
# ==========================================================================

_M3844_BURSTS = "it is first bloodied, and again when it is reduced to 0 hit points"
_M3844_HURT = "it takes damage"


@power(
    "m3844a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.FIRE, Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 5),
)
def m3844a0(c: Cast) -> None:
    """The hit damage is untyped as printed and only the burn is elemental,
    so the header needs no type and the three go on the ongoing, which
    `c.ongoing` takes as a set."""
    if c.strike():
        c.hit()
        c.ongoing(10, dtypes=_ELEMENTS)


@power(
    "m3844a1",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.FIRE, Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("3d10", 6, dtype=DamageType.COLD),
    dropped=("Damage(dtypes=)",),
    trigger=_M3844_BURSTS,
    on=(
        Trigger(Bloodied, when=about_me, text=_M3844_BURSTS),
        Trigger(Dropped, when=about_me, text=_M3844_BURSTS),
    ),
)
def m3844a1(c: Cast) -> None:
    """Twice a fight, and the second time is on the way down. One roll of
    three types, and `Damage` holds one."""
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m3844a2",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3844a2(c: Cast) -> None:
    c.shift(4)


@power(
    "m3844a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD, Keyword.FIRE, Keyword.LIGHTNING],
    trigger=_M3844_HURT,
    on=Trigger(DamageApplied, when=targets_me, text=_M3844_HURT),
)
def m3844a3(c: Cast) -> None:
    """No attack roll printed at all, so none is rolled: the five lands on
    everybody adjacent. `c.flat` with `dtypes` is one blow of three types,
    which is what resistance has to read as a unit."""
    for foe in sorted(c.within(1, side="enemy")):
        c.flat(5, dtypes=_ELEMENTS, on=foe)


# ==========================================================================
# m4266
# ==========================================================================

_M4266_HIT = "it is hit by an attack"
_M4266_FELLED = "it drops to 0 hit points"
_M4266_BLED = "it is first bloodied"
_M4266_PINNED = "m4266a4 restrained"


@power(
    "m4266a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d12", 4),
    requires=_hands_free,
    requires_text="it cannot use this while grabbing a creature",
)
def m4266a0(c: Cast) -> None:
    """The printed Requirement is a fact about the caster and belongs in the
    header. "Sustain Minor: it sustains the grab, and the target takes 10
    damage" is the grab left alone -- nothing but an escape clears one -- and
    the damage on a sustain hold."""
    victim = c.target
    if victim is None or not c.strike():
        return
    if c.bloodied(c.me):
        c.damage("2d12", 9)
    else:
        c.hit()
    c.prone(on=victim)
    _grab_and_sustain(c, victim, 10)


@power(
    "m4266a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 8),
)
def m4266a1(c: Cast) -> None:
    if not c.strike():
        return
    if c.bloodied(c.me):
        c.damage("2d8", 13)
    else:
        c.hit()
    c.pull(2)


@power(
    "m4266a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=NO_TARGET,
)
def m4266a2(c: Cast) -> None:
    """Four attacks, each at a different creature.

    The first m4266a0 to land takes hold, and m4266a0's own Requirement then
    refuses the second -- which is the printed interaction and not a row
    that failed, so `use` is left to say no.
    """
    spent: set[int] = set()
    for ref in ("m4266a0", "m4266a0", "m4266a1", "m4266a1"):
        pool = [
            foe
            for foe in sorted(c.enemies())
            if foe not in spent and c.distance(foe) <= 3 and alive(c.world, foe)
        ]
        if not pool:
            return
        victim = c.choose(pool, f"{c.ref}: who {ref} takes")
        if victim is None:
            return
        spent.add(victim)
        use(c.world, c.me, ref, targets=[victim], spend=False)


@power(
    "m4266a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d10", 5),
    trigger=_M4266_HIT,
    on=Trigger(Hit, when=hits_me, text=_M4266_HIT),
)
def m4266a3(c: Cast) -> None:
    victim = _triggering_enemy(c)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.slide(3, on=victim)
    c.prone(on=victim)


@power(
    "m4266a4",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(3),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d12", 8),
    requires=_has_hold,
    requires_text="usable only while it has a creature grabbed",
)
def m4266a4(c: Cast) -> None:
    """"Only one target can be restrained in this way at a time" is read as
    the standing hold going when a new one lands, which is the only reading
    under which the row can be used twice at all."""
    held = sorted(_holding(c.world, c.me))
    victim = c.choose(held, f"{c.ref}: which of them it pins") if held else None
    if victim is None or not c.strike(on=victim):
        return
    if c.bloodied(c.me):
        c.damage("2d12", 13, on=victim)
    else:
        c.hit(on=victim)
    for standing in sorted(c.suffering(_M4266_PINNED)):
        c.end_effect(on=standing, against=_M4266_PINNED, why=c.ref)
        c.cure(Condition.RESTRAINED, on=standing)
    c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=victim)
    c.effect(_M4266_PINNED, until=When.SAVE_ENDS, on=victim)
    c.escape(on=victim, auto=True)


@power(
    "m4266a5",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d10", 10),
)
def m4266a5(c: Cast) -> None:
    """It walks over whoever is standing in the way. On a board this creature
    fills, there may be nobody beneath it to find, which is a property of the
    generated squares rather than of the row."""
    hard = c.bloodied(c.me)
    for victim in _trample(c, c.speed_of()):
        if victim not in c.enemies() or not alive(c.world, victim):
            continue
        if not c.strike(on=victim):
            continue
        if hard:
            c.damage("1d10", 15, on=victim)
        else:
            c.hit(on=victim)
        c.slide(2, on=victim)


@power(
    "m4266a6",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d8", 8, half_on_miss=True),
    trigger=_M4266_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M4266_FELLED),
)
def m4266a6(c: Cast) -> None:
    """`half_on_miss` is card data and no line of the engine reads it, so the
    Miss sentence is written out as well."""
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m4266a7",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("3d8", 8, dtype=DamageType.THUNDER, kind=LIMITED, half_on_miss=True),
    trigger=_M4266_BLED,
    on=Trigger(Bloodied, when=about_me, text=_M4266_BLED),
)
def m4266a7(c: Cast) -> None:
    """No range printed at all, which the levels below read as melee 1. The
    ongoing damage is untyped where the blow is thunder, exactly as the two
    sentences are printed."""
    if c.strike():
        c.hit()
        c.ongoing(5)
    else:
        c.hit(half=True)


@power(
    "m4266a8",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d8", 8),
)
def m4266a8(c: Cast) -> None:
    """The rubble it leaves is the burst's own squares, laid once for the
    whole use rather than once per creature caught in it."""
    if c.strike():
        c.hit()
    if c.first:
        c.zone(c.area(), difficult=True, until=When.ENCOUNTER, label=c.ref)


# ==========================================================================
# m4307
# ==========================================================================

_M4307_SOFT = "m4307a2 vulnerability"
_M4307_ATTACKED = "an enemy attacks it"


@power(
    "m4307a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d12", 7),
)
def m4307a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4307a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=2,
    action=MINOR,
    reach=CloseBlast(2),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=15),
)
def m4307a1(c: Cast) -> None:
    """No damage on the hit line: the shove is the whole of it.

    The printed recharge sentence is asked at the start of its own turn, of
    whoever is carrying the hold m4307a2 lays -- which is why that row
    leaves a labelled marker beside the vulnerability rather than relying on
    the vulnerability being findable.
    """
    me = c.me
    if c.first:

        def pushed_off(ev: TurnStart) -> bool:
            if ev.ghost or ev.actor != me:
                return False
            return any(distance_between(c.world, me, who) > 2 for who in c.suffering(_M4307_SOFT))

        _recharge_on(c, TurnStart, pushed_off)
    if c.strike():
        c.push(2)


@power(
    "m4307a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.vulnerable(when=)",),
    trigger=_M4307_ATTACKED,
    on=Trigger(AttackDeclared, when=targets_me, text=_M4307_ATTACKED),
)
def m4307a2(c: Cast) -> None:
    """"Vulnerable 10 to the m4307's attacks" is narrower than the verb can
    say: `c.vulnerable` takes no gate, so what lands is vulnerable 10 to
    everything. The labelled hold beside it is what m4307a1's printed
    recharge sentence reads."""
    foe = _triggering_enemy(c)
    if foe is None:
        return
    c.vulnerable(10, on=foe, until=When.EONT)
    c.effect(_M4307_SOFT, until=When.EONT, on=foe)


# ==========================================================================
# m4338
# ==========================================================================

_M4338_OOZE = "m4338a5 sludge"
_M4338_BLED = "its attack bloodies an enemy"


def _in_sludge(world: World, eid: int) -> bool:
    """The printed Requirement on m4338a2, asked of the hold m4338a5 lays.

    Asking the engine what shape a creature is wearing is the standing gap
    `c.in_form()` names; a label on the hold is the same question answered
    without it, so neither row has to carry a marker.
    """
    return any(eff.label == _M4338_OOZE for eff in world.effects.of(eid))


@power(
    "m4338a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 7),
)
def m4338a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4338a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
)
def m4338a1(c: Cast) -> None:
    _twice(c, "m4338a0")


@power(
    "m4338a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=13),
    requires=_in_sludge,
    requires_text="usable only in the shape m4338a5 takes",
)
def m4338a2(c: Cast) -> None:
    """No damage on the hit line: the hold is the whole of it.

    "It can move normally while grabbing, pulling the grabbed target with
    him" is a watch on its own movement -- the grab survives a move either
    way, so the pull is the part that has to be said -- and "only one target
    at a time" lets the standing hold go when a new one lands.
    """
    victim = c.target
    if victim is None:
        return
    for other in sorted(_holding(c.world, c.me)):
        if other != victim:
            c.escape(on=other, auto=True)
    if not c.strike():
        return
    _grab_and_sustain(c, victim, 10, DamageType.ACID)
    me = c.me

    def dragged(ev: MoveEnd) -> None:
        if ev.actor != me:
            return
        for who in sorted(_holding(c.world, me)):
            _drag_beside(c, who, me, 99)

    c.watch(MoveEnd, dragged, until=When.ENCOUNTER, on=me, label=f"{c.ref} drag")


@power(
    "m4338a3",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(2),
    target=NO_TARGET,
    trigger=_M4338_BLED,
    on=Trigger(Bloodied, when=_bloodied_by_row("m4338a0"), text=_M4338_BLED),
)
def m4338a3(c: Cast) -> None:
    """Whether the free claw landed cannot be read off `use`, which reports
    that a row could be used and not that it connected, so the hit is
    counted off the bus."""
    victim = _triggering_enemy(c)
    if victim is None:
        return
    for who in sorted(set(_struck(c, "m4338a0", 1, victim))):
        for defence in (AC, FORT, REF, WILL):
            c.penalty(defence, 2, until=When.SAVE_ENDS, on=who)


@power(
    "m4338a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m4338a4(c: Cast) -> None:
    """Acid or fire finishes him; anything else buys a turn. The printed
    "starts his next turn with 10 hit points" is taken in the window the
    drop is announced in, for the reason `_rises_unless` gives: a body off
    the grid cannot be reached in between, so nothing is lost by it and a
    corpse the policy has written off is."""
    _rises_unless(c, 10, DamageType.ACID, DamageType.FIRE)


@power(
    "m4338a5",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m4338a5(c: Cast) -> None:
    """"The benefits of the ooze keyword" is what the shape counts as, and
    `c.set_origin` is that sentence: a creature considered one of a kind for
    the purpose of effects that read the word. The form carries the label
    m4338a2's Requirement asks for, and the printed way back out is the
    minor action `c.form` already gives it."""
    c.form(until=When.ENCOUNTER, revert=MINOR, label=_M4338_OOZE)
    c.set_origin("ooze", on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m4362
# ==========================================================================

_M4362_FELLED = "it is reduced to 0 hit points"


@power(
    "m4362a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d10", 5),
    dropped=("c.contract(ref)",),
)
def m4362a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4362a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d10", 5, kind=LIMITED),
    dropped=("c.contract(ref)",),
)
def m4362a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10)


@power(
    "m4362a2",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=REF, printed=13),
    dropped=("c.contract(ref)",),
    trigger=_M4362_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M4362_FELLED),
)
def m4362a2(c: Cast) -> None:
    """No damage on the hit line: the burn and the disease are the whole of
    it, so nothing calls `c.hit` and the header declares none."""
    if c.strike():
        c.ongoing(10)


# ==========================================================================
# m4483
# ==========================================================================


@power(
    "m4483a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 6),
)
def m4483a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4483a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 0, kind=LIMITED, half_on_miss=True),
    requires_text="requires a reach weapon",
)
def m4483a1(c: Cast) -> None:
    """The printed Requirement names a weapon rather than a property, and a
    monster carries no `Gear` for `c.wielding` to read -- so it is shown as
    the card's entry condition and not gated, which would refuse the row in
    every fight."""
    if c.strike():
        c.hit()
        c.prone()
    else:
        c.hit(half=True)


@power(
    "m4483a2",
    level=12,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4483a2(c: Cast) -> None:
    """"To any other square adjacent to that enemy" is an instruction, not a
    choice of anywhere in range, so the destinations are the squares beside
    the enemy it names and `c.shift(to=)` is handed one of them."""
    near = [foe for foe in sorted(c.enemies()) if c.adjacent(foe)]
    foe = c.choose(near, f"{c.ref}: which enemy it circles") if near else None
    if foe is None:
        return
    theirs, here = squares(c.world, foe), c.here
    options = sorted(
        sq
        for sq in c.world.reachable_squares(c.me, c.speed_of())
        if sq != here and theirs and min(distance(sq, s) for s in theirs) == 1
    )
    if not options:
        return
    c.shift(to=c.world.decide(c.me, "shift", options, f"{c.ref}: where it slips"))


# ==========================================================================
# m5219
# ==========================================================================

_M5219_HELD = "it is immobilized, restrained, pulled, pushed or slid"


@power(
    "m5219a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.jump(no_provoke=)",),
)
def m5219a0(c: Cast) -> None:
    """A jump is a move with the rough going and the bodies ignored for its
    length, and nothing waives the opening it gives. `c.no_provoke` is
    board-wide and for a duration, so laying it would exempt every ordinary
    walk as well -- the gap is the jump's own exemption."""


@power(
    "m5219a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 9),
)
def m5219a1(c: Cast) -> None:
    """"Plus 5 necrotic damage" is a second packet rather than a second type
    on the first, so it is rolled flat beside the header's own."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.flat(5, dtype=DamageType.NECROTIC)
    c.grab(on=victim)
    _drains(c, victim, 10)


@power(
    "m5219a2",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(2),
    target=NO_TARGET,
    once_per_round=True,
    attack=Attack(vs=FORT, printed=15),
    requires=_has_hold,
    requires_text="it must have a creature grabbed",
)
def m5219a2(c: Cast) -> None:
    """No damage on the hit line: the surge is the whole of it. The Effect
    runs before the attack, which is one of the two orders the card allows,
    and the pull is what "pulling the target with it" means on a grid."""
    held = sorted(_holding(c.world, c.me))
    victim = c.choose(held, f"{c.ref}: which of them it drags") if held else None
    if victim is None:
        return
    c.shift(2)
    _drag_beside(c, victim, c.me, 2)
    if c.strike(on=victim):
        c.spend_surge(on=victim)


@power(
    "m5219a3",
    level=12,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5219_HELD,
    on=(
        Trigger(ConditionApplied, when=_pinned_down, text=_M5219_HELD),
        Trigger(ForcedMove, when=_shoved, text=_M5219_HELD),
    ),
)
def m5219a3(c: Cast) -> None:
    _saves_off(c, "m5219a1", 2)


# ==========================================================================
# m5463
# ==========================================================================

_M5463_FELLED = "it drops to 0 hit points"


@power(
    "m5463a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5463a0(c: Cast) -> None:
    _slowed_by(c, DamageType.COLD)


@power(
    "m5463a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("4d8", 5, dtype=DamageType.FIRE),
)
def m5463a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5463a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m5463a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)
        c.ongoing(5, DamageType.FIRE)


@power(
    "m5463a3",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 6, dtype=DamageType.FIRE, kind=LIMITED),
    dropped=("c.kill()",),
    trigger=_M5463_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M5463_FELLED),
)
def m5463a3(c: Cast) -> None:
    """"Save ends both" is one hold carrying the condition and the burn, so
    `c.condition` takes the ongoing rather than a second call that would
    have its own saving throw.

    "This ongoing fire damage ignores the resistance provided by petrified"
    is written as the creature's own fire ignoring resistance: the burn is
    sourced from it, and by the time it ticks there is nothing else of its
    left to over-reach. "The m5463 is destroyed" is the named gap -- a
    creature at 0 hit points is dying, and nothing finishes one off.
    """
    if c.first:
        c.ignore_resistance(dtype=DamageType.FIRE, on=c.me)
    if c.strike():
        c.hit()
        c.condition(
            Condition.PETRIFIED, until=When.SAVE_ENDS, ongoing=(10, DamageType.FIRE)
        )


# ==========================================================================
# m5483
# ==========================================================================


@power(
    "m5483a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5483a0(c: Cast) -> None:
    """Whatever it has hold of comes along, and does not get a swing at it
    for going. The grab survives a move on its own -- nothing but an escape
    clears one -- so the clauses that need saying are the drag and the
    exemption, which is handed out per grabbed creature rather than
    board-wide."""
    me = c.me

    def dragged(ev: MoveEnd) -> None:
        if ev.actor != me:
            return
        for who in sorted(_holding(c.world, me)):
            c.no_provoke(from_=who, on=me, until=When.EOT)
            _drag_beside(c, who, me, 99)

    c.watch(MoveEnd, dragged, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5483a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("", 13, kind=MINION),
)
def m5483a1(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.strike():
        c.hit()
        c.grab(on=victim)


@power(
    "m5483a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("", 13, kind=MINION),
    requires=_has_hold,
    requires_text="it must have a creature grabbed",
)
def m5483a2(c: Cast) -> None:
    """"One creature grabbed by it" is narrower than any `Target` can say, so
    the Requirement carries the caster's half and the body picks."""
    held = sorted(_holding(c.world, c.me))
    victim = c.choose(held, f"{c.ref}: which of them it crushes") if held else None
    if victim is not None and c.strike(on=victim):
        c.hit(on=victim)
        c.prone(on=victim)


# ==========================================================================
# m5496
# ==========================================================================

_M5496_FELLED = "an attack that does not deal radiant damage reduces it to 0 hit points"


def _felled_without_radiant(world: World, me: int, ev: Dropped) -> bool:
    if ev.actor != me:
        return False
    blow = _blow_before(world, ev, me)
    return blow is not None and DamageType.RADIANT not in blow.types()


@power(
    "m5496a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("", 12, kind=MINION),
    dropped=("c.no_healing(temp_hp=)", "c.half_healing(amount=)"),
)
def m5496a0(c: Cast) -> None:
    """Both halves of the hold are named gaps and neither is reachable:
    nothing bars temporary hit points by themselves, and healing can be
    halved but not docked a flat amount. The damage is what plays."""
    if c.strike():
        c.hit()


@power(
    "m5496a1",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5496_FELLED,
    on=Trigger(Dropped, when=_felled_without_radiant, text=_M5496_FELLED),
)
def m5496a1(c: Cast) -> None:
    """"An attack that does not deal radiant damage" is read off the blow
    before the `Dropped`, which is the only thing that knows what the wound
    was made of. The beneficiary is a nonminion of its own kind, which is
    `c.is_minion` and `c.is_kind` and not the ally pool on its own."""
    pool = [
        mate
        for mate in sorted(c.allies())
        if mate != c.me
        and not c.is_minion(on=mate)
        and c.is_kind("undead", on=mate)
        and c.distance(mate) <= 10
    ]
    mate = c.choose(pool, f"{c.ref}: who it feeds") if pool else None
    if mate is not None:
        c.temp_hp(5, on=mate)


# ==========================================================================
# m5544
# ==========================================================================


@power(
    "m5544a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5544a0(c: Cast) -> None:
    """Three sorts of rough ground named one at a time, which is the shape
    `c.ignores_difficult` takes: a bare call would exempt every sort,
    including the ones the card leaves standing."""
    for kind in ("rubble", "uneven stone", "earthen construction"):
        c.ignores_difficult(kind, on=c.me, until=When.ENCOUNTER)


@power(
    "m5544a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5544a1(c: Cast) -> None:
    _slowed_by(c, DamageType.THUNDER)


@power(
    "m5544a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("4d8", 7),
)
def m5544a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5544a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("4d12", 9, kind=LIMITED, half_on_miss=True),
)
def m5544a3(c: Cast) -> None:
    """The printed "Recharge when first bloodied" sits on top of the die the
    database files, and the Effect runs first: the walk is what brings
    anybody into reach of a melee 1 attack at all."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: getattr(ev, "actor", None) == me)
    victim = c.target
    if victim is None:
        return
    c.run_at(victim)
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()
    else:
        c.hit(half=True)
        c.prone()


# ==========================================================================
# m5564
# ==========================================================================


@power(
    "m5564a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5564a0(c: Cast) -> None:
    """"Whenever an enemy in the aura takes a standard or a move action" is
    `ActionSpent`, which `Encounter.spend` is the one door to -- `PowerUsed`
    misses a plain walk and counts a move-action power twice.

    "Multiple such auras stack, dealing up to 10 damage" needs nothing: each
    of these creatures arms its own, five of them come to ten, and the cap
    is what five minions can field.
    """
    me, label = c.me, c.ref
    c.aura(1, label=label, until=When.ENCOUNTER)

    def acted(ev: ActionSpent) -> None:
        who = ev.actor
        if who == me or ev.cost not in (STANDARD, MOVE):
            return
        if team(c.world, who) is team(c.world, me):
            return
        if c.in_my_aura(who, label=label):
            c.flat(2, on=who)

    c.watch(ActionSpent, acted, until=When.ENCOUNTER, on=me, label=f"{label} ring")


@power(
    "m5564a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("", 12, kind=MINION),
)
def m5564a1(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m5691
# ==========================================================================

_M5691_HURT = "it takes damage while it is insubstantial"


def _hurt_while_thin(world: World, me: int, ev: DamageRolled) -> bool:
    return ev.target == me and is_(world, me, Condition.INSUBSTANTIAL)


@power(
    "m5691a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("", 9, kind=MINION),
)
def m5691a0(c: Cast) -> None:
    """A minion's printed critical is a second flat number rather than dice,
    so it replaces the damage rather than maxing it -- the engine's own rule
    would read the wrong number off this header."""
    if not c.strike():
        return
    if c.crit:
        c.flat(15)
    else:
        c.hit()
    c.insubstantial(on=c.me, until=When.SONT)


@power(
    "m5691a1",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m5691a1(c: Cast) -> None:
    c.teleport(3)
    c.insubstantial(on=c.me, until=When.SONT)


@power(
    "m5691a2",
    level=12,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5691_HURT,
    on=Trigger(DamageRolled, when=_hurt_while_thin, text=_M5691_HURT),
)
def m5691a2(c: Cast) -> None:
    """`DamageRolled` rather than `DamageApplied`: "it ignores the triggering
    damage" has to answer a blow that has been rolled and not yet dealt,
    which is the interrupt window `c.reduce` writes into."""
    ev = c.trigger
    if ev is None or not c.save(on=c.me, bare=True):
        return
    c.reduce(getattr(ev, "amount", 0), ev)


# ==========================================================================
# m5712
# ==========================================================================


@power(
    "m5712a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5712a0(c: Cast) -> None:
    """A bare `c.ignore_resistance` is the blanket form the card prints --
    no cap and no type -- and it lives on the attacker, which is the one
    thing about it that is easy to get backwards."""
    c.ignore_resistance(on=c.me, until=When.ENCOUNTER)


@power(
    "m5712a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("4d6", 11),
)
def m5712a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5712a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 5),
)
def m5712a2(c: Cast) -> None:
    """"If the target ends this push adjacent to any of its allies" is asked
    after the shove has landed, which is the only moment it can be true, and
    `c.grant_attack` is handed the victim by name -- `who` is who swings and
    `on` is who gets hit, and without the second the swing would aim at
    whatever this row's own target happened to be."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.push(3, on=victim)
    near = [
        mate
        for mate in sorted(c.allies())
        if mate != c.me and distance_between(c.world, mate, victim) <= 1
    ]
    mate = c.choose(near, f"{c.ref}: who takes the opening") if near else None
    if mate is not None:
        c.grant_attack(mate, on=victim)


@power(
    "m5712a3",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("5d6", 11, kind=LIMITED, half_on_miss=True),
)
def m5712a3(c: Cast) -> None:
    """The Effect is printed outside the hit line, so the shove lands on a
    miss too."""
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)
    c.push(1)


@power(
    "m5712a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_ALLY,
)
def m5712a4(c: Cast) -> None:
    """The caster is named in the printed line beside the targets, so its own
    temporary hit points and its own bonus are laid once for the whole use
    rather than once per ally caught in the burst. "+4 power bonus" is the
    word the card prints in front of "bonus" and nothing else."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: getattr(ev, "actor", None) == me)
    if c.first:
        c.temp_hp(10, on=me)
        c.bonus(AC, 4, kind="power", until=When.EONT, on=me)
    if c.target is not None and c.target != me:
        c.temp_hp(10)


# ==========================================================================
# m6081
# ==========================================================================

_M6081_STRUCK = "an enemy hits it with a weapon attack"


@power(
    "m6081a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6081a0(c: Cast) -> None:
    """Radiant puts it on the floor. Read off `types()`, which answers for a
    blow of several, and prone lasts until it stands rather than for a
    duration -- which is what the printed sentence means by falling."""
    me = c.me

    def felt(ev: DamageApplied) -> None:
        if ev.target == me and ev.amount > 0 and DamageType.RADIANT in ev.types():
            c.prone(on=me)

    c.watch(DamageApplied, felt, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6081a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d12", 12),
)
def m6081a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6081a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(2),
    target=EACH_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d6", 12, dtype=DamageType.NECROTIC, kind=LIMITED),
    trigger=_M6081_STRUCK,
    on=Trigger(Hit, when=both(hits_me, by_keyword(Keyword.WEAPON)), text=_M6081_STRUCK),
)
def m6081a2(c: Cast) -> None:
    """"Living creatures in the burst" is narrower than `EACH_CREATURE`, so
    the lifeless are skipped in the body rather than thrown away by a
    return -- somebody else in the burst still qualifies.

    The new creature "rolls initiative and acts on its turn", which is
    `c.summon` and not `loader.spawn`: the second alone makes an entity that
    stands there and never acts. The side it joins is the only one the
    engine can give it, which is this creature's own.
    """
    victim = c.target
    if victim is None or not _living(c, victim):
        return
    small = _no_bigger_than(c, victim, Size.MEDIUM)
    if not c.strike():
        return
    c.hit()
    if small and not alive(c.world, victim):
        c.summon("m6081")


# ==========================================================================
# m6156
# ==========================================================================

_M6156_FELLED = "it drops to 0 hit points"


@power(
    "m6156a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("", 12, kind=MINION),
)
def m6156a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6156a1",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M6156_FELLED,
    on=Trigger(Dropped, when=about_me, text=_M6156_FELLED),
)
def m6156a1(c: Cast) -> None:
    """One last swing on the way down, and landing it buys a hit point.

    Whether the swing landed cannot be read off `use`, so the hit is counted
    off the bus. `c.reanimate` is what "instead drops to 1 hit point" comes
    to once the drop has already been announced -- the trigger is the drop,
    so there is no earlier moment to interrupt.
    """
    victim = _in_reach(c, 1, c.ref)
    if victim is None:
        return
    if _struck(c, "m6156a0", 1, victim):
        c.reanimate(on=c.me, hp=1)


# ==========================================================================
# m6189
# ==========================================================================


@power(
    "m6189a0",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6189a0(c: Cast) -> None:
    """A free swing at somebody else once the charge has resolved.

    The charge flag rides on `Hit` and `Miss`, which is after the charge
    attack has landed or not -- `AttackDeclared` carries it too and would
    pay out before the charge it is answering.
    """

    def extra() -> None:
        pool = [foe for foe in sorted(c.enemies()) if c.adjacent(foe) and alive(c.world, foe)]
        victim = c.choose(pool, f"{c.ref}: who else she reaches") if pool else None
        if victim is not None:
            use(c.world, c.me, "m6189a2", targets=[victim], spend=False)

    _after_charge(c, extra)


@power(
    "m6189a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6189a1(c: Cast) -> None:
    _feeds_on_blood(c, 10)


@power(
    "m6189a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 6),
)
def m6189a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.FIRE)


@power(
    "m6189a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
)
def m6189a3(c: Cast) -> None:
    _twice(c, "m6189a2")


# ==========================================================================
# m6522
# ==========================================================================

_M6522_BLED = "an enemy is bloodied by its m6522a0 attack"


@power(
    "m6522a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("5d6", 8),
)
def m6522a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6522a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d4", 10),
)
def m6522a1(c: Cast) -> None:
    """The printed range is a short one and a long one; `Ranged` carries the
    short, which is the number every reader of this row uses, and the long
    range is a penalty the engine applies to a distance it is not given."""
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.POISON)


@power(
    "m6522a2",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M6522_BLED,
    on=Trigger(Bloodied, when=_bloodied_by_row("m6522a0"), text=_M6522_BLED),
)
def m6522a2(c: Cast) -> None:
    """Which of its two attacks did it matters, and nothing on `Bloodied`
    says: the blow before it in the log carries the row's ref in `detail`,
    which is the only place the attribution exists."""
    victim = _triggering_enemy(c)
    if victim is not None:
        use(c.world, c.me, "m6522a0", targets=[victim], spend=False, trigger=c.trigger)


# ==========================================================================
# m6525
# ==========================================================================

_M6525_BLED = "an enemy bloodies an ally within 6 squares of it"


@power(
    "m6525a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("", 12, kind=MINION),
)
def m6525a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6525a1",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6525_BLED,
    on=Trigger(Bloodied, when=_ally_bloodied_within_6, text=_M6525_BLED),
)
def m6525a1(c: Cast) -> None:
    """The triggering enemy is `Bloodied.source` and not the event's actor,
    which is the ally that was hurt. `c.charge_at` runs and swings with
    whatever this creature's basic attack actually is."""
    ev = c.trigger
    victim = getattr(ev, "source", None) if ev is not None else None
    if victim is not None and alive(c.world, victim):
        c.charge_at(victim)


# ==========================================================================
# m761
# ==========================================================================


@power(
    "m761a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.FIRE],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 7),
)
def m761a0(c: Cast) -> None:
    """"Plus 2d6 fire damage" is a second packet rather than a second type on
    the first, so it is rolled beside the header's own and needs no
    marker."""
    if c.strike():
        c.hit()
        c.damage("2d6", dtype=DamageType.FIRE)


@power(
    "m761a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
)
def m761a1(c: Cast) -> None:
    """The card prints "+16 vs AC;" with no damage beside it and then the
    sentence that matters, which is two of its own swings. Nothing is
    declared here: the attack line belongs to the row being used."""
    _twice(c, "m761a0")


@power(
    "m761a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m761a2(c: Cast) -> None:
    """`c.grant_attack` is handed both halves by name: `who` is who swings
    and `on` is who gets hit, and a grant with no `on` aims at this row's own
    target -- which a `NO_TARGET` row has not got."""
    me = c.me
    _recharge_on(c, Bloodied, lambda ev: getattr(ev, "actor", None) == me)
    pool = [mate for mate in sorted(c.allies()) if mate != me and c.distance(mate) <= 10]
    mate = c.choose(pool, f"{c.ref}: who swings") if pool else None
    if mate is None:
        return
    foes = [
        foe
        for foe in sorted(c.enemies())
        if distance_between(c.world, mate, foe) <= 1 and alive(c.world, foe)
    ]
    victim = c.choose(foes, f"{c.ref}: who they swing at") if foes else None
    if victim is not None:
        c.grant_attack(mate, on=victim)


@power(
    "m761a3",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m761a3(c: Cast) -> None:
    """A swing at everything else in reach once the charge has resolved.

    "Each enemy within its reach" is read from the row that does the
    swinging rather than from a number written here, so a creature whose
    reach is lengthened reaches further with this too.
    """

    def sweep() -> None:
        span = c.reach("m761a0")
        for foe in sorted(c.enemies()):
            if c.distance(foe) <= span and alive(c.world, foe):
                use(c.world, c.me, "m761a0", targets=[foe], spend=False)

    _after_charge(c, sweep)


@power(
    "m761a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m761a4(c: Cast) -> None:
    _feeds_on_blood(c, 10)
