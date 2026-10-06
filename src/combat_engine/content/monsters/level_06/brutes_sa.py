"""Monster abilities, level 6, brutes -- the second wave.

`brutes.py` holds the earlier sweep of this level and is not touched here;
the split is by *when* the work was done. 46 stat blocks, 179 rows.

Conventions, all inherited from the level-1 to level-5 sweeps and from
`brutes.py`'s own docstring:

* numbers load from `game.db` -- the attack line is written exactly as
  printed and the damage line goes in the header as data;
* a **trait** costs no action, has no target, and arms what holds it;
* a card with no printed range is melee 1; a printed band such as "10/20"
  takes the short number;
* a close burst or blast whose card names no target set takes enemies,
  except where it says "creatures in the burst" outright;
* `half_on_miss=True` is card data only -- the Miss branch is written by
  hand every time it is declared;
* several stat blocks here print the attack line for one ability leaking
  into the next ("+7 vs ; 1d10+4 damage.."), which is this spec tool's own
  extraction noise and not a printed sentence -- the real content is the
  rest of that block's line, and is what is implemented.

Several cards use the wrong id for themselves ("the m862", "the m5780
m5780") where every sibling card correctly says "the <this block>". Read as
"it" throughout -- these are extraction glitches, not a second creature,
except where a genuinely different ref is named alongside a real relation
(m4741's m4743, m6115's m6114), which are kept as refs and never resolved
to a name.

Helpers are imported from `level_06/brutes.py` and the four levels below it
rather than written twice. The ones written here are shapes this batch is
the first to need: a forced-move interrupt that cancels the move outright,
a "hasn't acted yet this encounter" gate, an aftereffect chained off an
ongoing's own end, and a few shapeshifter rows that follow the established
`c.in_form()` / `c.contract(ref)` markers rather than building shape
tracking the engine has nowhere else.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import (
    _recharge_when_bloodied,
)
from combat_engine.content.monsters.level_01.brutes_sa import (
    _crit_line,
    _felled_by_a_crit,
)
from combat_engine.content.monsters.level_02.soldiers_sa import (
    _crit_drops_it,
    _save_ends_on_me,
)
from combat_engine.content.monsters.level_03.brutes import _squeezes_freely
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_05.brutes_sa import _against_the_state
from combat_engine.content.monsters.level_06.brutes import (
    DEFENCES,
    _aura,
    _felled_by_me,
    _is_bloodied,
    _living,
    _melee_ctx,
    _recharge_on,
    _same_row,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_ALLY,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    ActionType,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Cover,
    Damage,
    DamageType,
    Ident,
    Keyword,
    Melee,
    Mod,
    Ranged,
    Relation,
    Target,
    Usage,
    When,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.dsl import use
from combat_engine.engine.events import (
    Bloodied,
    ConditionApplied,
    ConditionEnded,
    DamageApplied,
    Dropped,
    EffectApplied,
    ForcedMove,
    Hit,
    Miss,
    Moved,
    MoveStart,
    PowerUsed,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.grid import distance
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    concealment_of,
    distance_between,
    enemies,
    flanked_by,
    squares,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me, both, by_melee, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _ridden_by_sixth_level(world: World, me: int) -> bool:
    """"While mounted by a friendly rider of 6th level or higher."

    The level-4/5 sweeps wrote one of these per tier rather than a single
    parametrised helper, so this one matches that shape rather than
    reaching past it.
    """
    from combat_engine.engine import Stats

    for rider in world.relations.targets(Relation.RIDDEN_BY, me):
        if team(world, rider) is team(world, me):
            stats = world.get(rider, Stats)
            if stats is not None and stats.level >= 6:
                return True
    return False


def _hurt_me_from_nearby(radius: int) -> Any:
    """"It takes damage from an attack by a creature within N squares of it."

    Read off `DamageApplied`, which is the event that finally knows what hit
    landed and who threw it; `source` is the attacker, not the power.
    """

    def check(world: World, me: int, ev: Any) -> bool:
        if getattr(ev, "target", None) != me:
            return False
        source = getattr(ev, "source", None)
        if source is None or team(world, source) is team(world, me):
            return False
        return distance_between(world, me, source) <= radius

    return check


def _hurt_by_an_enemy(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    source = getattr(ev, "source", None)
    return source is not None and team(world, source) is not team(world, me)


def _grabbing_count(world: World, eid: int) -> int:
    return len(world.relations.targets(Relation.GRABBED_BY, eid))


def _stood_up_adjacent(world: World, me: int, ev: ConditionEnded) -> bool:
    """"An adjacent enemy stands up from prone." `ConditionEnded` fires the
    moment the condition actually comes off, whether the creature chose to
    stand or something else cured it -- the card means the first of those."""
    return (
        ev.condition is Condition.PRONE
        and ev.target in enemies(world, me)
        and distance_between(world, me, ev.target) <= 1
    )


def _forced_on_me(world: World, me: int, ev: ForcedMove) -> bool:
    return ev.target == me


def _mobbed_by(c: Cast, minimum: int, *, melee_only: bool = True) -> Any:
    """"The attacks deal extra damage to an enemy adjacent to N or more of
    its allies." The caster is left out of the count -- the line is about
    its *allies*, and every stat block here that prints this leaves itself
    out of its own crowd."""
    me = c.me

    def gate(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None or (melee_only and not _melee_ctx(ctx)):
            return False
        return sum(1 for a in c.within(1, of=who, side="ally") if a != me) >= minimum

    return gate


def _slide_toward(c: Cast, victim: int, anchor: int, squares_: int) -> bool:
    """Slide `victim` up to `squares_` squares toward a square adjacent to
    `anchor`, picking the closest such square to where the victim already
    stands -- the same "pick the nearer qualifying square" shape
    `_step_toward` in `brutes.py` uses for a voluntary shift, here for a
    forced one that has nowhere of its own to anchor against."""
    theirs = squares(c.world, anchor)
    mine = next(iter(squares(c.world, victim)), None)
    if mine is None or not theirs:
        return False
    ring = {sq for s in theirs for sq in spread({s}, 1)} - theirs
    if not ring:
        return False
    dest = min(ring, key=lambda sq: distance(sq, mine))
    return bool(c.slide(squares_, on=victim, to=dest))


# ==========================================================================
# m1012
# ==========================================================================


@power(
    "m1012a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d10", 3),
)
def m1012a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1012a1",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d6", 3, dtype=DamageType.ACID, kind=LIMITED),
)
def m1012a1(c: Cast) -> None:
    """The acid burn is read off who it is grabbing, not stored separately:
    the grab already ends itself on an escape, and a creature no longer
    held should simply stop coming up in the search."""
    if not c.strike():
        return
    c.hit()
    c.grab()
    c.prone()
    me = c.me

    def burn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.grabbing(of=me):
            return
        c.flat(5, dtype=DamageType.ACID, on=ev.actor)

    c.watch(TurnStart, burn, until=When.ENCOUNTER, on=me, label=f"{c.ref} acid")


_M1012_NEAR = "it takes damage from an attack by a creature within 2 squares of it"


@power(
    "m1012a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d6", 3, kind=LIMITED),
    trigger=_M1012_NEAR,
    on=Trigger(DamageApplied, _hurt_me_from_nearby(2), _M1012_NEAR),
)
def m1012a2(c: Cast) -> None:
    foe = getattr(c.trigger, "source", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.pull(2, on=foe)
        c.grab(on=foe)


_M1012_KIN_CHARGE = "a m1012 charges"


def _kin_charged(world: World, me: int, ev: Hit) -> bool:
    attacker = ev.attacker
    if attacker is None or attacker == me or not bool(getattr(ev, "charge", False)):
        return False
    ident = world.get(attacker, Ident)
    return (
        ident is not None
        and ident.ref == "m1012"
        and distance_between(world, me, attacker) <= 5
    )


@power(
    "m1012a3",
    level=6,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1012_KIN_CHARGE,
    on=Trigger(Hit, _kin_charged, _M1012_KIN_CHARGE),
)
def m1012a3(c: Cast) -> None:
    """"One other m1012" is answered by `me` here: each copy's own row
    watches for a sibling's charge, so the one that reacts is, by
    construction, a different creature than the one that charged."""
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.charge_at(victim)


# ==========================================================================
# m1067
# ==========================================================================


@power(
    "m1067a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 5),
)
def m1067a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1067a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 5),
)
def m1067a1(c: Cast) -> None:
    if c.strike():
        c.hit()


def _rider_swung_melee(world: World, me: int, ev: PowerUsed) -> bool:
    rider = ev.actor
    if rider not in world.relations.targets(Relation.RIDDEN_BY, me):
        return False
    if not _ridden_by_sixth_level(world, me) or not ev.targets:
        return False
    row = get(ev.power)
    return row is not None and row.is_attack and row.reach.kind == "melee"


_M1067_RIDER = (
    "while mounted by a friendly rider of 6th level or higher, "
    "its rider makes a melee attack"
)


@power(
    "m1067a2",
    level=6,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1067_RIDER,
    on=Trigger(PowerUsed, _rider_swung_melee, _M1067_RIDER),
)
def m1067a2(c: Cast) -> None:
    victim = next(iter(getattr(c.trigger, "targets", ())), None)
    if victim is not None:
        c.use_power("m1067a0", on=victim)


# ==========================================================================
# m115823
# ==========================================================================


@power(
    "m115823a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 6),
)
def m115823a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m115823a1",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 4),
    requires=_is_bloodied,
    requires_text="the m115823 must be bloodied",
)
def m115823a1(c: Cast) -> None:
    if c.strike():
        c.hit()


_M115823_HURT = "it takes damage from an enemy"


@power(
    "m115823a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=CloseBlast(2),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d8", 6, kind=LIMITED),
    trigger=_M115823_HURT,
    on=Trigger(DamageApplied, _hurt_by_an_enemy, _M115823_HURT),
)
def m115823a2(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.prone()


# ==========================================================================
# m115825
# ==========================================================================


@power(
    "m115825a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.regeneration(suspended_by=)",),
)
def m115825a0(c: Cast) -> None:
    """Regeneration lands; the silver that switches it off does not --
    nothing marks a weapon as silvered for `c.regeneration` to read."""
    c.regeneration(5)


@power(
    "m115825a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 3),
    dropped=("c.in_form()",),
)
def m115825a1(c: Cast) -> None:
    """The Requirement names a shape nothing records -- the attack plays
    regardless of which form it is in, which is the dropped half."""
    if not c.strike():
        return
    victim = c.target
    if victim is not None and c.bloodied(victim):
        c.damage("2d8", 8)
    else:
        c.hit()
    c.prone()


@power(
    "m115825a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 7),
    dropped=("c.in_form()", "c.contract(ref)"),
)
def m115825a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115825a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 4),
    dropped=("c.in_form()",),
)
def m115825a3(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    if victim is not None and c.bloodied(victim):
        c.damage("2d8", 9)
    else:
        c.hit()


@power(
    "m115825a4",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.in_form()",),
)
def m115825a4(c: Cast) -> None:
    """"Uses claw and bite" against whatever this creature is menacing;
    with no target line of its own, both named rows are aimed by hand."""
    victim = next(iter(sorted(c.within(1, side="enemy"))), None)
    if victim is not None:
        c.use_power("m115825a1", on=victim)
        c.use_power("m115825a2", on=victim)
    c.flat(5, on=c.me)


@power(
    "m115825a5",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m115825a5(c: Cast) -> None:
    """Appearance only: the three shapes it can choose cost nothing and
    change nothing a board reads -- the real split, which form gates which
    attack, is already dropped on those rows for want of shape tracking."""


# ==========================================================================
# m115845
# ==========================================================================


@power(
    "m115845a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 6),
)
def m115845a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115845a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 5),
)
def m115845a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115845a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("4d10", 4, kind=LIMITED, half_on_miss=True),
)
def m115845a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.prone()
    else:
        c.hit(half=True)
        c.prone()


# ==========================================================================
# m1503
# ==========================================================================


@power(
    "m1503a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 4),
)
def m1503a0(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    if victim is not None and c.is_(Condition.PRONE, on=victim):
        c.damage("1d10", 9)
    else:
        c.hit()


@power(
    "m1503a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m1503a1(c: Cast) -> None:
    """m1503a0 through the row that prints it, twice, so its damage line
    stays in one place."""
    victim = c.target
    if victim is None:
        return
    landed = 0
    for _ in range(2):
        c.use_power("m1503a0", on=victim)
        if c.landed:
            landed += 1
    if landed == 2:
        c.prone(on=victim)


_M1503_DOWN = "the m1503 drops to 0 hit points"


@power(
    "m1503a2",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M1503_DOWN,
    on=Trigger(Dropped, about_me, _M1503_DOWN),
)
def m1503a2(c: Cast) -> None:
    who = next(iter(sorted(c.within(1, side="enemy"))), None)
    if who is not None:
        use(c.world, c.me, "m1503a0", targets=[who], spend=False, trigger=c.trigger)


@power(
    "m1503a3",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1503a3(c: Cast) -> None:
    me = c.me
    c.bonus(
        "damage", 5, until=When.ENCOUNTER, on=me, when=lambda ctx: bool(ctx.get("charge"))
    )

    def gore(ev: Hit) -> None:
        if ev.attacker != me or not bool(getattr(ev, "charge", False)):
            return
        c.push(2, on=ev.target)
        c.prone(on=ev.target)

    c.watch(Hit, gore, until=When.ENCOUNTER, on=me, label="m1503a3")


# ==========================================================================
# m1929
# ==========================================================================


@power(
    "m1929a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 7),
)
def m1929a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if not c.grabbing():
            c.grab()


@power(
    "m1929a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m1929a1(c: Cast) -> None:
    """No attack roll at all -- the whole of the printed line is automatic
    damage to whichever one creature it has grabbed."""
    victim = next(iter(c.grabbing()), None)
    if victim is not None:
        c.damage("1d10", 7, dtype=DamageType.NECROTIC, on=victim)


@power(
    "m1929a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d8", 11, dtype=DamageType.ACID),
    dropped=("Damage(dtypes=)",),
)
def m1929a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.BLINDED, until=When.SAVE_ENDS)


# ==========================================================================
# m1958
# ==========================================================================


@power(
    "m1958a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("4d6", 3, dtype=DamageType.NECROTIC),
)
def m1958a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


_M1958_STOOD = "an adjacent enemy stands up"


@power(
    "m1958a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    trigger=_M1958_STOOD,
    on=Trigger(ConditionEnded, _stood_up_adjacent, _M1958_STOOD),
)
def m1958a1(c: Cast) -> None:
    who = getattr(c.trigger, "target", None)
    if who is not None:
        c.use_power("m1958a0", on=who)


@power(
    "m1958a2",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1958a2(c: Cast) -> None:
    """"At the end of its creator's next turn" is paid as the end of the
    very next turn this creature takes after the kill rather than tracked
    out two turns, which is the simpler of two readings and the one that
    does not need a counter of its own."""
    me = c.me

    def rise(ev: Dropped) -> None:
        if not _felled_by_me(c.world, me, ev):
            return
        if not _living(c, ev.actor) or not c.is_kind("humanoid", on=ev.actor):
            return
        spot = next(iter(squares(c.world, ev.actor)), None)

        def later(end: TurnEnd) -> None:
            if end.ghost or end.actor != me:
                return
            c.summon("m119", at=spot)
            c.world.effects.end(hold[0], "it rose")

        hold = [
            c.watch(
                TurnEnd, later, until=When.ENCOUNTER, on=me, once=True, label="m1958a2 rise"
            )
        ]

    c.watch(Dropped, rise, until=When.ENCOUNTER, on=me, label="m1958a2")


# ==========================================================================
# m2232
# ==========================================================================


@power(
    "m2232a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 4),
)
def m2232a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2232a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 4),
)
def m2232a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m2232a2",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m2232a2(c: Cast) -> None:
    """Asked at the moment of the hit, not laid as a standing rider: the
    victim it names was dazed by an *earlier* blow, and a watcher sees that
    state before this same swing's own daze (if any) has been applied."""
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker == me and c.is_(Condition.DAZED, on=ev.target):
            c.ongoing(5, DamageType.PSYCHIC, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label="m2232a2")


# ==========================================================================
# m3121
# ==========================================================================


@power(
    "m3121a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("3d4", 6),
)
def m3121a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "2d4", 18)


@power(
    "m3121a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("4d4", 6),
    requires=_is_bloodied,
    requires_text="the m3121 must be bloodied",
)
def m3121a1(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "2d4", 22)
    else:
        c.hit(half=False)
    c.heal(10, on=c.me)


@power(
    "m3121a2",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3121a2(c: Cast) -> None:
    def bleeding(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and c.bloodied(who)

    c.bonus("damage", 0, dice="2d4", on=c.me, until=When.ENCOUNTER, when=bleeding)


# ==========================================================================
# m3184
# ==========================================================================


@power(
    "m3184a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 6),
)
def m3184a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3184a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d8", 6),
)
def m3184a1(c: Cast) -> None:
    for caught in c.overrun():
        if c.strike(on=caught):
            c.hit(on=caught)
            c.blinded(until=When.SONT, on=caught)


@power(
    "m3184a2",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_ridden_by_sixth_level,
    requires_text="while mounted by a friendly rider of 6th level or higher",
)
def m3184a2(c: Cast) -> None:
    rider = c.rider()
    if rider is None or not _ridden_by_sixth_level(c.world, c.me):
        return
    c.conceal(on=rider, until=When.ENCOUNTER)


# ==========================================================================
# m3195
# ==========================================================================


@power(
    "m3195a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 5),
)
def m3195a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
        c.mark(until=When.EONT)


@power(
    "m3195a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 5),
)
def m3195a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)
        c.mark(until=When.EONT)


@power(
    "m3195a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m3195a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m3195a0", on=victim)
    c.use_power("m3195a1", on=victim)


def _marked_enemy_moves(world: World, me: int, ev: MoveStart) -> bool:
    return (
        ev.actor != me
        and ev.actor in enemies(world, me)
        and world.relations.holds(Relation.MARKED_BY, me, ev.actor)
    )


_M3195_SLIPPED = "an adjacent enemy marked by it would move or shift"


@power(
    "m3195a3",
    level=6,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    trigger=_M3195_SLIPPED,
    on=Trigger(MoveStart, _marked_enemy_moves, _M3195_SLIPPED),
)
def m3195a3(c: Cast) -> None:
    c.shift(1)
    if c.target is not None:
        c.basic(on=c.target)


# ==========================================================================
# m3226
# ==========================================================================


@power(
    "m3226a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 5),
)
def m3226a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(3)


@power(
    "m3226a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d4", 7),
)
def m3226a1(c: Cast) -> None:
    if c.strike():
        c.hit()


def _rider_missed_opportunity(world: World, me: int, ev: Miss) -> bool:
    rider = ev.attacker
    if rider not in world.relations.targets(Relation.RIDDEN_BY, me):
        return False
    return _ridden_by_sixth_level(world, me) and bool(getattr(ev, "opportunity", False))


_M3226_RIDER = (
    "while mounted by a friendly rider of 6th level or higher, "
    "its rider misses with an opportunity attack"
)


@power(
    "m3226a2",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M3226_RIDER,
    on=Trigger(Miss, _rider_missed_opportunity, _M3226_RIDER),
)
def m3226a2(c: Cast) -> None:
    foe = next(iter(sorted(c.within(1, side="enemy"))), None)
    if foe is not None:
        c.use_power("m3226a1", on=foe)


# ==========================================================================
# m3281
# ==========================================================================


@power(
    "m3281a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d12", 7),
)
def m3281a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d12", 19)


@power(
    "m3281a1",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d12", 0, kind=LIMITED),
)
def m3281a1(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "2d12", 12)
        c.ongoing(5)


@power(
    "m3281a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    requires=_is_bloodied,
    requires_text="the m3281 must be bloodied",
)
def m3281a2(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        c.use_power("m3281a0", on=victim)
    c.heal(21, on=c.me)


@power(
    "m3281a3",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
)
def m3281a3(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    c.bonus("damage", 2, on=mate, until=When.EOT, once=True)
    c.command(mate, charge=True)


# ==========================================================================
# m3286
# ==========================================================================


@power(
    "m3286a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d12", 5),
)
def m3286a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d12", 17)


@power(
    "m3286a1",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.HEALING, Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d6", 2, dtype=DamageType.PSYCHIC, kind=LIMITED),
    requires=_is_bloodied,
    requires_text="the m3286 must be bloodied",
)
def m3286a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    if c.first:
        c.heal(10, on=c.me)


# ==========================================================================
# m3302
# ==========================================================================


@power(
    "m3302a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
)
def m3302a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3302a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 7),
)
def m3302a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3302a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d8", 5, kind=LIMITED),
)
def m3302a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.push(3)
    c.prone()
    spare = next(
        (f for f in c.enemies() if f != victim and c.adjacent_to(f, victim)), None
    )
    if spare is not None and _secondary(c, 7, REF, spare):
        c.damage("2d8", 5, on=spare)


_M3302_BLED = "the m3302 is first bloodied"


@power(
    "m3302a3",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3302_BLED,
    on=Trigger(Bloodied, about_me, _M3302_BLED),
)
def m3302a3(c: Cast) -> None:
    c.temp_hp(5, on=c.me)
    victim = next(iter(sorted(c.within(1, side="enemy"))), None)
    if victim is not None:
        c.use_power("m3302a0", on=victim)
        c.use_power("m3302a1", on=victim)


# ==========================================================================
# m3458
# ==========================================================================


@power(
    "m3458a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("", 6, kind=MINION),
)
def m3458a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.crit:
            c.prone()


# ==========================================================================
# m3986
# ==========================================================================


@power(
    "m3986a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("4d4", 4),
)
def m3986a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m3986a1",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d6", 4),
)
def m3986a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


# ==========================================================================
# m3995
# ==========================================================================


@power(
    "m3995a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 6),
)
def m3995a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3995a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=7),
)
def m3995a1(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.BLINDED, until=When.SAVE_ENDS)


# ==========================================================================
# m4032
# ==========================================================================


@power(
    "m4032a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 6),
)
def m4032a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4032a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d8", 8),
)
def m4032a1(c: Cast) -> None:
    for caught in c.overrun():
        if c.strike(on=caught):
            c.hit(on=caught)
            c.prone(on=caught)


@power(
    "m4032a2",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_ridden_by_sixth_level,
    requires_text="while mounted by a friendly rider of 6th level or higher with the feat",
)
def m4032a2(c: Cast) -> None:
    rider = c.rider()
    if rider is None or not _ridden_by_sixth_level(c.world, c.me):
        return
    if not c.feat("m3183", on=rider):
        return
    c.bonus(
        "attack", 1, on=rider, until=When.ENCOUNTER, when=lambda ctx: bool(ctx.get("charge"))
    )


# ==========================================================================
# m4121
# ==========================================================================


@power(
    "m4121a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m4121a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


# ==========================================================================
# m4188
# ==========================================================================


@power(
    "m4188a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 6, dtype=DamageType.ACID, kind=MINION),
)
def m4188a0(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m4643
# ==========================================================================


@power(
    "m4643a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 8),
)
def m4643a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d10", 20)


@power(
    "m4643a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m4643a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    landed = 0
    for _ in range(2):
        c.use_power("m4643a0", on=victim)
        if c.landed:
            landed += 1
    if landed == 2:
        c.prone(on=victim)


@power(
    "m4643a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 8, kind=LIMITED),
)
def m4643a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()


@power(
    "m4643a3",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
)
def m4643a3(c: Cast) -> None:
    """Two separate holds, both save-ends: `c.mark` has no door to carry a
    bonus through, so there is nowhere to combine them into the one
    saving throw the card's single "(save ends)" would otherwise read as."""
    victim = c.target
    if victim is None:
        return
    c.mark(until=When.SAVE_ENDS, on=victim)
    c.grants_advantage(until=When.SAVE_ENDS, on=victim, to="team")


@power(
    "m4643a4",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.bull_rush()",),
)
def m4643a4(c: Cast) -> None:
    """Nothing plays: there is no bull rush action for this trait to
    modify the push of."""


_M4643_DOWN = "the m4643 is reduced to 0 hit points or fewer"


@power(
    "m4643a5",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON, Keyword.FEAR],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 8),
    trigger=_M4643_DOWN,
    on=Trigger(Dropped, about_me, _M4643_DOWN),
)
def m4643a5(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d10", 20)
        c.penalty("attack", 2, until=When.EONT)


# ==========================================================================
# m4724
# ==========================================================================


@power(
    "m4724a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 5),
)
def m4724a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4724a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 5, kind=LIMITED),
)
def m4724a1(c: Cast) -> None:
    if c.strike():
        c.hit()


_M4724_FELLED = "the m4724 bloodies or drops an enemy to 0 hit points"


@power(
    "m4724a2",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=9),
    on=[
        Trigger(Bloodied, when=_felled_by_me, text="the m4724 bloodies an enemy"),
        Trigger(Dropped, when=_felled_by_me, text="or drops one to 0 hit points"),
    ],
    trigger=_M4724_FELLED,
)
def m4724a2(c: Cast) -> None:
    victim = c.target
    me = c.me
    if c.strike():
        c.push(1)
        if victim is not None:
            c.penalty(
                "attack",
                2,
                on=victim,
                until=When.SAVE_ENDS,
                when=lambda ctx: ctx.get("target") == me,
            )


@power(
    "m4724a3",
    level=6,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4724a3(c: Cast) -> None:
    c.cure(Condition.MARKED, on=c.me)
    c.shift(2)


# ==========================================================================
# m4741
# ==========================================================================


@power(
    "m4741a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m4741a0(c: Cast) -> None:
    """The card prints no escape clause at all -- only a cap of two held
    creatures, which the body enforces. It was marked `c.grab(dc=)` for a
    number its page does not give."""
    if c.strike():
        c.hit()
        if len(c.grabbing()) < 2:
            c.grab()


@power(
    "m4741a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
)
def m4741a1(c: Cast) -> None:
    c.use_power("m4741a0", on=c.target)


@power(
    "m4741a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    requires=lambda world, eid: _grabbing_count(world, eid) > 0,
    requires_text="the m4741 must have a creature grabbed",
    attack=Attack(vs=FORT, printed=7),
    dropped=("c.engulf()",),
)
def m4741a2(c: Cast) -> None:
    """The absorb half -- pulled into its space, ongoing damage while held,
    temporary hit points each turn it is still holding somebody, and an
    automatic expulsion past a damage threshold -- all plays. What does
    not is the sealed-off line of sight, the "at-will attacks only" clause
    on the swallowed creature, and the goblin-corpse alternative, none of
    which this engine has a hook for."""
    held = c.grabbing()[:2]
    if not held:
        return
    me, here = c.me, c.here
    for victim in held:
        if not c.strike(on=victim):
            continue
        c.pull(1, on=victim, to=here)
        hold = c.ongoing(5, on=victim)
        if hold is None:
            continue

        def expel(ev: DamageApplied, v: int = victim, h: Any = hold) -> None:
            if ev.target != me or ev.amount < 16:
                return
            c.world.effects.end(h, "the m4741 was struck too hard")

        c.watch(DamageApplied, expel, until=When.ENCOUNTER, on=me, label=f"m4741a2 {victim}")

    def feed(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not c.grabbing():
            return
        c.temp_hp(5, on=me)

    c.watch(TurnStart, feed, until=When.ENCOUNTER, on=me, label="m4741a2 feed")


@power(
    "m4741a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.flat(unpreventable=)",),
)
def m4741a3(c: Cast) -> None:
    spot = next(iter(c.world.reachable_squares(c.me, 1)), None)
    spawn = c.summon("m4743", at=spot)
    if spawn is not None and spawn >= 0:
        c.basic(who=spawn)
    c.flat(10, on=c.me)


_M4741_DOWN = "the m4741 is reduced to 0 hit points"


@power(
    "m4741a4",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=7),
    damage=Damage("3d6", 4, kind=LIMITED),
    trigger=_M4741_DOWN,
    on=Trigger(Dropped, about_me, _M4741_DOWN),
)
def m4741a4(c: Cast) -> None:
    if c.strike():
        c.hit()
    if c.first:
        c.zone(spread({c.here}, 1), difficult=True, until=When.ENCOUNTER, label=c.ref)


# ==========================================================================
# m4748
# ==========================================================================


@power(
    "m4748a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 7),
)
def m4748a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4748a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 5),
)
def m4748a1(c: Cast) -> None:
    if c.strike():
        c.hit()


def _hit_with_a1(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and ev.power == "m4748a1"


_M4748_FOLLOWUP = "it hits with the previous attack"


@power(
    "m4748a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 7),
    trigger=_M4748_FOLLOWUP,
    on=Trigger(Hit, _hit_with_a1, _M4748_FOLLOWUP),
)
def m4748a2(c: Cast) -> None:
    who = getattr(c.trigger, "target", None)
    if who is not None and c.strike(on=who):
        c.hit(on=who)


@power(
    "m4748a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d6", 5),
)
def m4748a3(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m5089
# ==========================================================================


@power(
    "m5089a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5089a0(c: Cast) -> None:
    me = c.me

    def scald(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if c.bloodied(me) and distance_between(c.world, me, ev.actor) <= 1:
            c.flat(5, on=ev.actor)

    c.watch(TurnStart, scald, until=When.ENCOUNTER, on=me, label="m5089a0")


@power(
    "m5089a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 6),
)
def m5089a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5089a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5089a2(c: Cast) -> None:
    """The shift happens first, so each attack is aimed at whoever it is
    beside once it is done moving rather than measured from where it
    started -- an approximation of "during the shift" that skips no enemy
    actually within reach by the end of it."""
    c.shift(3)
    for foe in sorted(c.within(1, side="enemy"))[:3]:
        c.use_power("m5089a1", on=foe)


@power(
    "m5089a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 6),
)
def m5089a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


_M5089_DOWN = "the m5089 drops to 0 hit points"


@power(
    "m5089a4",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5089_DOWN,
    on=Trigger(Dropped, about_me, _M5089_DOWN),
)
def m5089a4(c: Cast) -> None:
    c.extra_action(cost=ActionType.STANDARD, on=c.me)


# ==========================================================================
# m5215
# ==========================================================================


@power(
    "m5215a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5215a0(c: Cast) -> None:
    me = c.me
    c.aura(3, until=When.ENCOUNTER)

    def drag(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or distance_between(c.world, me, ev.actor) > 3:
            return
        c.slide(1, on=ev.actor)

    c.watch(TurnStart, drag, until=When.ENCOUNTER, on=me, label="m5215a0")


@power(
    "m5215a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 9),
    dropped=("c.in_form()",),
)
def m5215a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5215a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 6),
    dropped=("c.in_form()",),
)
def m5215a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5215a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("4d8", 7, kind=LIMITED),
)
def m5215a3(c: Cast) -> None:
    c.shift(3)
    if c.strike():
        c.hit()


@power(
    "m5215a4",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("3d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
    dropped=("c.in_form()", "c.borrow_row(seen=)"),
)
def m5215a4(c: Cast) -> None:
    """The psychic half is exact; "gains a use of a power it has seen the
    target use this encounter" has no seen-powers ledger to read from."""
    me = c.me
    _recharge_on(c, Miss, lambda ev: ev.attacker == me and ev.power == "m5215a4")
    if c.strike():
        c.hit()


@power(
    "m5215a5",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m5215a5(c: Cast) -> None:
    """Appearance only; see `m5215a1`/`m5215a2`."""


# ==========================================================================
# m5405
# ==========================================================================


@power(
    "m5405a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5405a0(c: Cast) -> None:
    me = c.me

    def hurt(_ctx: dict[str, Any]) -> bool:
        return c.bloodied(me)

    for d in DEFENCES:
        c.bonus(d, 2, until=When.ENCOUNTER, on=me, when=hurt)


@power(
    "m5405a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m5405a1(c: Cast) -> None:
    c.regeneration(5)


@power(
    "m5405a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 6),
    dropped=("c.in_form()",),
)
def m5405a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5405a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 6),
    dropped=("c.in_form()", "c.contract(ref)"),
)
def m5405a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10 if c.bloodied(c.me) else 5)


@power(
    "m5405a4",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=Target(side="enemy", count=1, label="one bloodied creature", bloodied=True),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("3d6", 6, kind=LIMITED),
    dropped=("c.in_form()",),
)
def m5405a4(c: Cast) -> None:
    """`Target.bloodied` is the target line, so the gate and the re-pick both
    came out; the printed Requirement about the shape is the one still
    unsaid."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5405a5",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m5405a5(c: Cast) -> None:
    """Appearance only; see `m5405a2`/`m5405a3`."""


_M5405_DOWN = "the m5405 drops to 0 hit points"


@power(
    "m5405a6",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M5405_DOWN,
    on=Trigger(Dropped, about_me, _M5405_DOWN),
)
def m5405a6(c: Cast) -> None:
    who = next(iter(sorted(c.within(1, side="enemy"))), None)
    if who is None:
        return
    first = c.choose(["m5405a2", "m5405a3"], "m5405a6") or "m5405a2"
    order = [first, "m5405a3" if first == "m5405a2" else "m5405a2"]
    for ref in order:
        if use(c.world, c.me, ref, targets=[who], spend=False, trigger=c.trigger):
            return


@power(
    "m5405a7",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    on=[Trigger(Dropped, when=_felled_by_me, text="the m5405 drops an enemy to 0 hit points")],
    trigger="the m5405 reduces an enemy to 0 hit points",
)
def m5405a7(c: Cast) -> None:
    c.grant_action_point(1, on=c.me)


_M5405_HIT = "the m5405 is hit by a melee attack"


@power(
    "m5405a8",
    level=6,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger=_M5405_HIT,
    on=Trigger(Hit, both(targets_me, by_melee), _M5405_HIT),
)
def m5405a8(c: Cast) -> None:
    who = getattr(c.trigger, "attacker", None)
    if who is None:
        return
    first = c.choose(["m5405a2", "m5405a3"], "m5405a8") or "m5405a2"
    order = [first, "m5405a3" if first == "m5405a2" else "m5405a2"]
    for ref in order:
        if c.use_power(ref, on=who):
            return


# ==========================================================================
# m5501
# ==========================================================================


@power(
    "m5501a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 8, kind=MINION),
)
def m5501a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M5501_DOWN = "the m5501 drops to 0 hit points"


@power(
    "m5501a1",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 8, kind=MINION),
    trigger=_M5501_DOWN,
    on=Trigger(Dropped, about_me, _M5501_DOWN),
)
def m5501a1(c: Cast) -> None:
    who = next(iter(sorted(c.within(1, side="enemy"))), None)
    if who is None:
        return
    use(c.world, c.me, "m5501a1", targets=[who], spend=False, trigger=c.trigger)
    if c.strike(on=who):
        c.hit(on=who)
        c.slowed(until=When.SAVE_ENDS, on=who)


# ==========================================================================
# m5591
# ==========================================================================


@power(
    "m5591a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.regeneration(suspended_by=)",),
)
def m5591a0(c: Cast) -> None:
    c.regeneration(5)


@power(
    "m5591a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5591a1(c: Cast) -> None:
    me = c.me

    def hurt(_ctx: dict[str, Any]) -> bool:
        return c.bloodied(me)

    for d in DEFENCES:
        c.bonus(d, 2, until=When.ENCOUNTER, on=me, when=hurt)


@power(
    "m5591a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 6),
    dropped=("c.in_form()", "c.contract(ref)"),
)
def m5591a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10 if c.bloodied(c.me) else 5)


@power(
    "m5591a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 9),
    dropped=("c.in_form()",),
)
def m5591a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5591a4",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m5591a4(c: Cast) -> None:
    """Appearance only; see `m5591a2`/`m5591a3`."""


_M5591_DOWN = "the m5591 drops to 0 hit points"


@power(
    "m5591a5",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M5591_DOWN,
    on=Trigger(Dropped, about_me, _M5591_DOWN),
)
def m5591a5(c: Cast) -> None:
    who = next(iter(sorted(c.within(1, side="enemy"))), None)
    if who is None:
        return
    first = c.choose(["m5591a2", "m5591a3"], "m5591a5") or "m5591a2"
    order = [first, "m5591a3" if first == "m5591a2" else "m5591a2"]
    for ref in order:
        if use(c.world, c.me, ref, targets=[who], spend=False, trigger=c.trigger):
            return


# ==========================================================================
# m5633
# ==========================================================================


@power(
    "m5633a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5633a0(c: Cast) -> None:
    c.bonus("damage", 5, until=When.ENCOUNTER, on=c.me, when=_mobbed_by(c, 2, melee_only=False))


@power(
    "m5633a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 4, dtype=DamageType.POISON),
)
def m5633a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m5633a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(side="enemy", count=1, label="one bloodied creature", bloodied=True),
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("3d10", 5),
)
def m5633a2(c: Cast) -> None:
    """"One bloodied creature" is `Target.bloodied`, so an unbloodied creature
    is never in the pool and the Requirement is that emptiness."""
    if c.strike():
        c.hit()
        c.prone()


# ==========================================================================
# m5645
# ==========================================================================


@power(
    "m5645a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5645a0(c: Cast) -> None:
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def toll(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if distance_between(c.world, me, ev.actor) > 1:
            return
        crowd = sum(1 for a in c.within(1, of=ev.actor, side="ally") if a != me)
        c.flat(10 if crowd >= 2 else 5, on=ev.actor)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label="m5645a0")


@power(
    "m5645a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5645a1(c: Cast) -> None:
    c.shares_space(on=c.me, until=When.ENCOUNTER, difficult=True)
    _squeezes_freely(c)

    def melee_or_ranged(ctx: dict[str, Any]) -> bool:
        p = get(ctx.get("power") or "")
        return p is not None and p.reach.kind in ("melee", "ranged")

    c.resist_forced(99, on=c.me, until=When.ENCOUNTER, when=melee_or_ranged)


@power(
    "m5645a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 7),
)
def m5645a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.immobilized(until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return
    me = c.me

    def check(ev: Moved) -> None:
        if not c.adjacent_to(me, victim):
            c.world.effects.end(hold, "no longer adjacent")

    c.watch(Moved, check, until=When.SAVE_ENDS, on=victim, label=f"{c.ref} leash")


# ==========================================================================
# m5675
# ==========================================================================


@power(
    "m5675a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5675a0(c: Cast) -> None:
    me = c.me
    acted: set[int] = set()

    def mark(ev: TurnEnd) -> None:
        if not ev.ghost:
            acted.add(ev.actor)

    def fresh(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        return who is not None and who not in acted

    c.watch(TurnEnd, mark, until=When.ENCOUNTER, on=me, label="m5675a0 tracker")
    c.bonus("damage", 0, dice="1d10", on=me, until=When.ENCOUNTER, when=fresh)


@power(
    "m5675a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d12", 3),
)
def m5675a1(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    was_bloodied = victim is not None and c.bloodied(victim)
    if c.bloodied(c.me):
        c.damage("2d12", 8)
    else:
        c.hit()
    if victim is not None and not was_bloodied and c.bloodied(victim):
        c.flat(5, on=victim)


_M5675_SAVE = "it is subjected to an effect that a save can end"


@power(
    "m5675a2",
    level=6,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5675_SAVE,
    on=Trigger(EffectApplied, _save_ends_on_me, _M5675_SAVE),
)
def m5675a2(c: Cast) -> None:
    for eff in sorted(c.world.effects.of(c.me), key=lambda e: -e.id):
        if eff.when is When.SAVE_ENDS:
            c.world.effects.save(eff)
            return


# ==========================================================================
# m5737
# ==========================================================================


@power(
    "m5737a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5737a0(c: Cast) -> None:
    """"Creatures in the aura" is either side -- the aura is a hazard, not
    a buff -- so membership is diffed by the zone the way `_aura` does it,
    and the vulnerability comes off again the moment anybody steps out."""
    _aura(
        c,
        1,
        lambda who: True,
        lambda who: c.vulnerable(5, DamageType.FIRE, until=When.ENCOUNTER, on=who),
    )


@power(
    "m5737a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 6, dtype=DamageType.FIRE),
)
def m5737a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5737a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d10", 2, dtype=DamageType.FIRE),
)
def m5737a2(c: Cast) -> None:
    for caught in c.overrun():
        if c.strike(on=caught):
            c.hit(on=caught)
            c.prone(on=caught)
            c.ongoing(5, DamageType.FIRE, on=caught)


def _im_disabled(world: World, me: int, ev: ConditionApplied) -> bool:
    return ev.target == me and ev.condition in (
        Condition.IMMOBILIZED,
        Condition.RESTRAINED,
        Condition.STUNNED,
    )


_M5737_PINNED = "it is immobilized, restrained, or stunned"


@power(
    "m5737a3",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("3d10", 4, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
    trigger=_M5737_PINNED,
    on=Trigger(ConditionApplied, _im_disabled, _M5737_PINNED),
)
def m5737a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
    else:
        c.hit(half=True)


# ==========================================================================
# m5780
# ==========================================================================


@power(
    "m5780a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5780a0(c: Cast) -> None:
    me = c.me

    def commune(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        if not any(_same_row(c, a, "m5780") for a in c.within(1, side="ally")):
            return
        for eff in sorted(c.world.effects.of(me), key=lambda e: -e.id):
            if eff.when is When.SAVE_ENDS:
                c.world.effects.save(eff)
                return

    c.watch(TurnStart, commune, until=When.ENCOUNTER, on=me, label="m5780a0")


@power(
    "m5780a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("3d8", 4, dtype=DamageType.NECROTIC),
)
def m5780a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.vulnerable(5, DamageType.NECROTIC, until=When.EONT)


@power(
    "m5780a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
)
def m5780a2(c: Cast) -> None:
    _recharge_when_bloodied(c)
    c.use_power("m5780a1", on=c.target)


# ==========================================================================
# m5839
# ==========================================================================


@power(
    "m5839a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 6),
)
def m5839a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5839a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 6),
)
def m5839a1(c: Cast) -> None:
    """"Then shift 1 square to a square the target vacated" is the *target's*
    square, `c.there`, read before the push -- `c.here` is the attacker's own,
    so the step was into the square it was already standing in and did
    nothing. It is what keeps the pair adjacent, and that is what m5839a2's
    second swing needs: without it the push left the target 2 squares away and
    the second swing landed from out of reach."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    vacated = c.there
    c.push(1, on=victim)
    c.shift(1, to=vacated)


@power(
    "m5839a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5839a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    for _ in range(2):
        c.use_power("m5839a1", on=victim)
        if not c.landed:
            c.restore_use("m5839a2")


@power(
    "m5839a3",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=9),
)
def m5839a3(c: Cast) -> None:
    if c.strike():
        c.push(1)


# ==========================================================================
# m5851
# ==========================================================================


@power(
    "m5851a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5851a0(c: Cast) -> None:
    me = c.me

    def flanking(who: int) -> Any:
        def gate(ctx: dict[str, Any]) -> bool:
            victim = ctx.get("target")
            return victim is not None and flanked_by(c.world, victim, who)

        return gate

    _aura(
        c,
        5,
        lambda who: who != me and who in c.allies(),
        lambda who: c.bonus(
            "damage", 2, kind="power", on=who, until=When.ENCOUNTER, when=flanking(who)
        ),
    )


@power(
    "m5851a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5851a1(c: Cast) -> None:
    me = c.me

    def hurt(_ctx: dict[str, Any]) -> bool:
        return c.bloodied(me)

    for d in DEFENCES:
        c.bonus(d, 2, kind="power", until=When.ENCOUNTER, on=me, when=hurt)


@power(
    "m5851a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 4),
)
def m5851a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m5851a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5851a3(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    landed = 0
    for _ in range(2):
        c.use_power("m5851a2", on=victim)
        if c.landed:
            landed += 1
    if landed == 2:
        mods = [(victim, Mod(what=d, value=-2, kind="power", label=c.ref)) for d in DEFENCES]
        c.world.effects.apply(
            victim,
            c.me,
            When.SAVE_ENDS,
            label=f"{c.ref}",
            mods=mods,
            ongoing=(5, DamageType.UNTYPED),
        )


@power(
    "m5851a4",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 5, kind=LIMITED, half_on_miss=True),
)
def m5851a4(c: Cast) -> None:
    """"To a square adjacent to one or more of his enemies" -- m5851's own
    enemies, which from the slid target's point of view is its *own*
    allies, so the throw lands it among its own side for the splash to
    catch them. The destination is the qualifying square nearest the
    target's own square, to keep the slide as short as the card allows."""
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)
    victim = c.target
    if victim is None:
        return
    others = [f for f in c.enemies() if f != victim]
    if others:
        nearest = min(others, key=lambda o: distance_between(c.world, victim, o))
        _slide_toward(c, victim, nearest, 3)
    for foe in c.within(1, of=victim, side="enemy"):
        if foe != victim:
            c.flat(10, on=foe)
            c.prone(on=foe)


# ==========================================================================
# m6062
# ==========================================================================


@power(
    "m6062a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6062a0(c: Cast) -> None:
    me = c.me

    def roll(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        d6 = c.roll("1d6")
        if d6 <= 2:
            c.dazed(until=When.SONT, on=me)
        elif d6 >= 5:
            c.bonus(
                "damage",
                0,
                dice="3d6",
                on=me,
                until=When.SONT,
                when=_melee_ctx,
            )

    c.watch(TurnStart, roll, until=When.ENCOUNTER, on=me, label="m6062a0")


@power(
    "m6062a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("3d8", 4),
)
def m6062a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6062a2",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m6062a2(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    c.spend_surge(on=mate)
    c.penalty("attack", 2, on=mate, until=When.EONT)


# ==========================================================================
# m6115
# ==========================================================================


@power(
    "m6115a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.set_origin(by=)",),
)
def m6115a0(c: Cast) -> None:
    """Nothing plays: sharing senses with a named sibling and letting that
    sibling fire its own powers from this creature's square both need a
    way to authorise a *different* creature's row, which nothing here
    grants."""


_M6115_DOWN = "the m6115 drops to 0 hit points"


@power(
    "m6115a1",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("", 6, kind=MINION),
    trigger=_M6115_DOWN,
    on=Trigger(Dropped, about_me, _M6115_DOWN),
)
def m6115a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    if c.first:
        mate = next(
            (
                a
                for a in c.allies()
                if _same_row(c, a, "m6114") and distance_between(c.world, c.me, a) <= 5
            ),
            None,
        )
        if mate is not None:
            c.slide(1, on=mate)


# ==========================================================================
# m6343
# ==========================================================================


@power(
    "m6343a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6343a0(c: Cast) -> None:
    me = c.me
    _aura(
        c,
        2,
        lambda who: who != me and who in c.allies() and c.is_kind("plant", on=who),
        lambda who: c.bonus("damage", 2, on=who, until=When.ENCOUNTER),
    )


@power(
    "m6343a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.hide(when=)",),
)
def m6343a1(c: Cast) -> None:
    """The check and the hide both play; `c.hide` takes no standing gate,
    so the partial-concealment condition is asked by hand in a watch
    instead of declared the way `c.bonus`'s `when=` reads it."""
    me = c.me

    def try_hide(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or c.is_hidden():
            return
        if concealment_of(c.world, me) is not Cover.PARTIAL:
            return
        if c.check("stealth"):
            c.hide(until=When.ENCOUNTER)

    c.watch(TurnStart, try_hide, until=When.ENCOUNTER, on=me, label="m6343a1")


@power(
    "m6343a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 8),
)
def m6343a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6343a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(2),
    target=Target(
        side="ally", count=1,
        label="minion plant ally",
        kinds=frozenset({"plant"}),
    ),
    dropped=("Target.minion",),
)
def m6343a3(c: Cast) -> None:
    """The type word is the target line now. "Minion" has no field, so the
    redirect stays for that half -- and it still asks the kind of the
    creatures it scans, because `c.allies()` is the raw pool and not the
    narrowed one."""
    mate = c.target
    if mate is None or not c.is_minion(on=mate):
        mate = next(
            (
                a
                for a in c.allies()
                if c.is_minion(on=a)
                and c.is_kind("plant", on=a)
                and distance_between(c.world, c.me, a) <= 2
            ),
            None,
        )
    if mate is None:
        return
    choice = c.choose(["basic attack", "charge"], "m6343a3") or "basic attack"
    c.command(mate, charge=choice == "charge")


_M6343_INTERRUPTED = "an adjacent enemy hits it with an attack"


def _hit_me_adjacent(world: World, me: int, ev: Hit) -> bool:
    if ev.target != me or ev.attacker not in enemies(world, me):
        return False
    return distance_between(world, me, ev.attacker) <= 1


@power(
    "m6343a4",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 7, kind=LIMITED),
    trigger=_M6343_INTERRUPTED,
    on=Trigger(Hit, _hit_me_adjacent, _M6343_INTERRUPTED),
)
def m6343a4(c: Cast) -> None:
    _recharge_when_bloodied(c)
    who = getattr(c.trigger, "attacker", None)
    if who is not None and c.strike(on=who):
        c.hit(on=who)
        c.push(2, on=who)


_M6343_BLED = "the m6343 is first bloodied"


@power(
    "m6343a5",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.POISON, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d8", 7, dtype=DamageType.POISON),
    trigger=_M6343_BLED,
    on=Trigger(Bloodied, about_me, _M6343_BLED),
)
def m6343a5(c: Cast) -> None:
    if c.target is not None and c.is_kind("plant", on=c.target):
        return
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)
    if c.first:
        c.zone(spread({c.here}, 1), until=When.ENCOUNTER, label=c.ref)


# ==========================================================================
# m6451
# ==========================================================================


def _hit_by_arcane(world: World, me: int, ev: DamageApplied) -> bool:
    if ev.target != me:
        return False
    row = get(ev.detail or "")
    return row is not None and Keyword.ARCANE in row.keywords


_M6451_ARCANE = "it takes damage from an arcane attack"


@power(
    "m6451a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger=_M6451_ARCANE,
    on=Trigger(DamageApplied, _hit_by_arcane, _M6451_ARCANE),
)
def m6451a0(c: Cast) -> None:
    me = c.me
    for who in c.within(2, side="any"):
        if who != me:
            c.flat(5, dtype=DamageType.NECROTIC, on=who)


@power(
    "m6451a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6451a1(c: Cast) -> None:
    me = c.me

    def dropped_by_crit(ev: Hit) -> None:
        if ev.target == me and ev.critical:
            _crit_drops_it(c)

    c.watch(Hit, dropped_by_crit, until=When.ENCOUNTER, on=me, label="m6451a1")


@power(
    "m6451a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 7),
)
def m6451a2(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    if victim is not None and victim in c.grabbing():
        c.damage("3d10", 7)
    else:
        c.hit()


@power(
    "m6451a3",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 7, kind=LIMITED),
    dropped=("c.grab(dc=)",),
)
def m6451a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


_M6451_SURVIVED = "the m6451 is reduced to 0 hit points, but not by a critical hit"


@power(
    "m6451a4",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6451_SURVIVED,
    on=Trigger(Dropped, about_me, _M6451_SURVIVED),
)
def m6451a4(c: Cast) -> None:
    if _felled_by_a_crit(c):
        return
    if c.roll("1d20") >= 15:
        c.reanimate(on=c.me, hp=1)


def _killed_by_arcane(c: Cast) -> bool:
    for ev in reversed(c.world.bus.log):
        if isinstance(ev, Hit) and ev.target == c.me:
            row = get(ev.power or "")
            return row is not None and Keyword.ARCANE in row.keywords
    return False


_M6451_ARCANE_DEATH = "the m6451 is killed by an arcane attack"


@power(
    "m6451a5",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.ARCANE, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d10", 6, dtype=DamageType.NECROTIC),
    trigger=_M6451_ARCANE_DEATH,
    on=Trigger(Dropped, about_me, _M6451_ARCANE_DEATH),
)
def m6451a5(c: Cast) -> None:
    if c.first and not _killed_by_arcane(c):
        return
    if c.strike():
        c.hit()


# ==========================================================================
# m6489
# ==========================================================================


@power(
    "m6489a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 7),
)
def m6489a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6489a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4),
)
def m6489a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6489a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m6489a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m6489a0", on=victim)
    landed = 0
    for _ in range(2):
        c.use_power("m6489a1", on=victim)
        if c.landed:
            landed += 1
    if landed == 2:
        c.prone(on=victim)


@power(
    "m6489a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d8", 7, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m6489a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)
    else:
        c.hit(half=True)


def _enemy_left_nearby(world: World, me: int, ev: Any) -> bool:
    actor = getattr(ev, "actor", None)
    return (
        actor is not None
        and actor != me
        and actor in enemies(world, me)
        and distance_between(world, me, actor) <= 2
    )


_M6489_LEFT = "an enemy leaves a square within 2 squares of it"


@power(
    "m6489a4",
    level=6,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 7),
    trigger=_M6489_LEFT,
    on=Trigger(MoveStart, _enemy_left_nearby, _M6489_LEFT),
)
def m6489a4(c: Cast) -> None:
    who = getattr(c.trigger, "actor", None)
    if who is not None and c.strike(on=who):
        c.hit(on=who)
        c.prone(on=who)


_M6489_BLED = "it is first bloodied"


@power(
    "m6489a5",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d8", 7, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
    trigger=_M6489_BLED,
    on=Trigger(Bloodied, about_me, _M6489_BLED),
)
def m6489a5(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)
    if not c.first:
        return
    me = c.me
    c.forbid("m6489a3", on=me, until=When.ENCOUNTER)
    hold = c.ongoing(10, DamageType.FIRE, on=me)
    if hold is not None:
        hold.on_end.append(lambda: c.ongoing(5, DamageType.FIRE, on=me))


# ==========================================================================
# m6550
# ==========================================================================


@power(
    "m6550a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.regeneration(suspended_by=)",),
)
def m6550a0(c: Cast) -> None:
    c.regeneration(5)


@power(
    "m6550a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6550a1(c: Cast) -> None:
    me = c.me

    def hurt(_ctx: dict[str, Any]) -> bool:
        return c.bloodied(me)

    for d in DEFENCES:
        c.bonus(d, 2, until=When.ENCOUNTER, on=me, when=hurt)


@power(
    "m6550a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 6),
    dropped=("c.in_form()", "c.contract(ref)"),
)
def m6550a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10 if c.bloodied(c.me) else 5)


@power(
    "m6550a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 9),
    dropped=("c.in_form()",),
)
def m6550a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6550a4",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m6550a4(c: Cast) -> None:
    """Appearance only; see `m6550a2`/`m6550a3`."""


_M6550_DOWN = "the m6550 drops to 0 hit points"


@power(
    "m6550a5",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M6550_DOWN,
    on=Trigger(Dropped, about_me, _M6550_DOWN),
)
def m6550a5(c: Cast) -> None:
    who = next(iter(sorted(c.within(1, side="enemy"))), None)
    if who is None:
        return
    first = c.choose(["m6550a2", "m6550a3"], "m6550a5") or "m6550a2"
    order = [first, "m6550a3" if first == "m6550a2" else "m6550a2"]
    for ref in order:
        if use(c.world, c.me, ref, targets=[who], spend=False, trigger=c.trigger):
            return


# ==========================================================================
# m6637
# ==========================================================================


@power(
    "m6637a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 8),
    requires=lambda world, eid: _grabbing_count(world, eid) < 2,
    requires_text="the m6637 must be grabbing fewer than two creatures",
    dropped=("c.grab(dc=)",),
)
def m6637a0(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    c.grab()
    victim = c.target
    me = c.me
    if victim is None:
        return

    def leech(ev: TurnStart) -> None:
        if ev.ghost or victim not in c.grabbing(of=me):
            return
        c.flat(15, on=victim)

    c.watch(TurnStart, leech, until=When.ENCOUNTER, on=me, label=f"m6637a0 {victim}")


@power(
    "m6637a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=lambda world, eid: _grabbing_count(world, eid) == 0,
    requires_text="the m6637 must be grabbing no creatures",
)
def m6637a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m6637a0", on=victim)
    c.use_power("m6637a0", on=victim)


_M6637_DOWN = "the m6637 starts its turn with 0 hit points or fewer"


@power(
    "m6637a2",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(20),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.HEALING],
    attack=Attack(vs=WILL, printed=9),
    trigger=_M6637_DOWN,
    on=Trigger(TurnStart, about_me, _M6637_DOWN),
)
def m6637a2(c: Cast) -> None:
    """"Each enemy that can see it" is approximated as each enemy in the
    burst -- the burst's own line-of-sight filtering already keeps out
    anyone behind a wall, which is most of what "can see it" means."""
    if not isinstance(c.trigger, TurnStart) or getattr(c.trigger, "actor", None) != c.me:
        return
    victim = c.target
    if victim is None:
        return
    hold = None
    if c.strike(on=victim):
        hold = c.stunned(until=When.EONT, on=victim)
    else:
        c.dazed(until=When.EONT, on=victim)
        c.flee(c.speed_of(victim), on=victim)
    if hold is not None:
        hold.on_end.append(
            lambda v=victim: (c.dazed(until=When.EONT, on=v), c.flee(c.speed_of(v), on=v))
        )
    if c.first:
        c.heal(88, on=c.me)


# ==========================================================================
# m895
# ==========================================================================


@power(
    "m895a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 4),
)
def m895a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m895a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m895a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m895a0", on=victim)
    c.use_power("m895a0", on=victim)


@power(
    "m895a2",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 3, kind=LIMITED),
)
def m895a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=f"{c.ref}",
        ongoing=(2, DamageType.POISON),
        mods=[(victim, Mod(what="attack", value=-2, kind="untyped", label=c.ref))],
    )


_M895_FORCED = "it is subjected to a pull, a push, or a slide effect"


@power(
    "m895a3",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M895_FORCED,
    on=Trigger(ForcedMove, _forced_on_me, _M895_FORCED),
)
def m895a3(c: Cast) -> None:
    c.cancel()
    c.immobilized(until=When.EONT, on=c.me)


_M895_BLED = "the m895 is first bloodied"


@power(
    "m895a4",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    trigger=_M895_BLED,
    on=Trigger(Bloodied, about_me, _M895_BLED),
)
def m895a4(c: Cast) -> None:
    from combat_engine.engine import Size

    c.resize(Size.LARGE, on=c.me)
    c.threatens(2, until=When.ENCOUNTER)
    c.bonus("damage", 5, until=When.ENCOUNTER, on=c.me, when=_melee_ctx)


# ==========================================================================
# m993
# ==========================================================================


@power(
    "m993a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("4d4", 4, dtype=DamageType.FORCE),
)
def m993a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.crit:
            c.ongoing(c.roll("1d6"), DamageType.FORCE)


@power(
    "m993a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d4", 1),
)
def m993a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m993a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d4", 3, dtype=DamageType.FORCE),
)
def m993a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


_M993_STOOD = "an adjacent target stands from prone"


@power(
    "m993a3",
    level=6,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger=_M993_STOOD,
    on=Trigger(ConditionEnded, _stood_up_adjacent, _M993_STOOD),
)
def m993a3(c: Cast) -> None:
    who = getattr(c.trigger, "target", None)
    if who is not None:
        c.basic(on=who)


@power(
    "m993a4",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m993a4(c: Cast) -> None:
    c.bonus(
        "damage",
        0,
        dice="2d4",
        on=c.me,
        until=When.ENCOUNTER,
        when=_against_the_state(c, Condition.PRONE),
    )
