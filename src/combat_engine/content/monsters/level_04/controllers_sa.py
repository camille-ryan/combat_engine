"""Monster abilities, level 4, controllers: the second sweep.

`controllers.py` beside this file holds the first sweep of this level; the
split is by *when* the work was done rather than by what the creatures are,
and the conventions are that file's and the level-1 to level-3 sweeps':

* numbers load from `game.db` -- the attack line is written exactly as printed
  (`Attack(vs=WILL, printed=8)`) and the damage line goes in the header as
  data, so an MM1 block can be rescaled to MM3 maths later;
* a **trait** costs no action, has no target, and arms the watches that hold it
  for the rest of the fight. Several rows the database files as standard
  actions are plainly traits and are written as such;
* a blast or burst with **no printed target line** is read as enemies, which is
  the reading `controllers.py` settled and the one that does not set a monster
  on its own allies;
* "Aftereffect" is the hold's `on_end` and "Each Failed Saving Throw" is
  `escalate=`; "First Failed" is `escalate=` plus `_also`, which is idempotent;
* a printed target line that narrows by a *condition* has nowhere to live --
  `Target` filters side, count and size -- so `label=` records it for the card,
  the body redirects to a creature in reach that qualifies, a `requires=` keeps
  the row from being offered when nothing does, and `Target.kind` is the gap
  (#361);
* a row that recharges on a printed condition keeps the die in the header,
  because that is what `actions.recharge` rolls and what the card shows, and
  arms the condition on top of it.

Twenty-two helpers are imported rather than rewritten. Two of these blocks are
the same stat line twice over and one pair is the same leader at two refs, so
three local helpers carry the five rows they share.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import (
    _is_bloodied,
    _recharge_when_bloodied,
)
from combat_engine.content.monsters.level_01.brutes_sa import _crit_line
from combat_engine.content.monsters.level_01.misc_sa import _WILLING
from combat_engine.content.monsters.level_01.skirmishers import _ref_of
from combat_engine.content.monsters.level_01.skirmishers_sa import (
    _adjacent_foes,
    _crowd_around,
    _damaged_me,
)
from combat_engine.content.monsters.level_02.controllers_sa import (
    _holds_somebody,
    _not_grabbing,
    _recharge_on_miss,
)
from combat_engine.content.monsters.level_02.lurkers_sa import (
    _recharge_when_using,
    _triggering_enemy,
    _twice,
)
from combat_engine.content.monsters.level_02.soldiers_sa import _save_ends_on_me
from combat_engine.content.monsters.level_03.artillery_sa import _death_throe
from combat_engine.content.monsters.level_03.controllers_sa import (
    _ally_used,
    _also,
    _hold_while_inside,
    _in_reach_suffering,
    _let_it_swing,
)
from combat_engine.content.monsters.level_03.skirmishers import _free_square_beside
from combat_engine.content.monsters.level_03.skirmishers_sa import (
    _ongoing_of,
    _reachable,
    _while_bloodied,
)
from combat_engine.content.monsters.level_04.controllers import DEFENCES
from combat_engine.content.monsters.level_04.skirmishers import _has_advantage
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    STANDARD,
    WILL,
    Ability,
    ActionType,
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Health,
    Keyword,
    Melee,
    Powers,
    Ranged,
    Stats,
    Target,
    UpTo,
    Usage,
    When,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    DamageApplied,
    Dropped,
    EffectApplied,
    Hit,
    Miss,
    Moved,
    MoveStart,
    PowerUsed,
    TurnEnd,
    TurnStart,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    alive,
    distance_between,
    flanked_by,
    squares,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_melee,
    targets_me,
)

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _burning(world: World, who: int) -> bool:
    """Is that creature taking ongoing damage of any type?

    `_ongoing_of` next door answers it per damage type and wants a `Cast`; a
    `requires=` gate gets `(world, eid)` and nothing else, and the printed
    target line does not name a type.
    """
    return any(effect.ongoing for effect in world.effects.of(who))


def _crit_instead(c: Cast, dice: str, bonus: int, dtype: DamageType) -> None:
    """A printed "(crit NdX + n <type>) " line, which replaces the damage.

    `_crit_line` is this without a damage type; two rows on one block print a
    critical that is a different type from the blow that scored it, so the
    flat payment needs the type passed through. Rolled rather than declared,
    because `c.damage` maxes its dice on a critical and would read the wrong
    number off this header.
    """
    if c.crit:
        c.flat(c.roll(dice) + bonus, dtype=dtype)
    else:
        c.hit()


def _pass_the_swing(c: Cast) -> None:
    """"Miss: an adjacent ally makes a free basic attack."

    Adjacent to the caster, which is the only creature the printed line has
    to measure from. The ally needs a victim of its own: the row's target may
    be out of its reach entirely.
    """
    beside = sorted(a for a in c.within(1, side="ally") if a != c.me)
    friend = c.choose(beside, "which ally swings") if beside else None
    if friend is None:
        return
    reachable = sorted(c.within(1, of=friend, side="enemy"))
    foe = c.choose(reachable, "the ally makes a basic attack") if reachable else None
    if foe is not None:
        c.grant_attack(friend, on=foe)


def _slip_away(c: Cast) -> None:
    """"It and up to two allies within its line of sight shift 1 square."

    "Up to two" is offered twice and may be declined rather than taking the
    nearest two: which ally is worth moving is the whole decision.
    """
    c.shift(1)
    pool = sorted(a for a in c.allies() if alive(c.world, a) and c.can_see(a))
    for _ in range(2):
        if not pool:
            return
        friend = c.choose(pool, "which ally slips away too", optional=True)
        if friend is None:
            return
        pool.remove(friend)
        c.shift(1, who=friend)


def _tougher_when_hurt(c: Cast, value: int) -> None:
    """"+N bonus to all defences while bloodied."

    Gated on the wound rather than put on and taken off as hit points move:
    the gate is asked when the defence is read, so nothing has to watch the
    health bar and a heal above the line takes the bonus off by itself.
    """

    def hurt(_ctx: dict[str, Any]) -> bool:
        return c.bloodied(on=c.me)

    for defence in DEFENCES:
        c.bonus(defence, value, on=c.me, until=When.ENCOUNTER, when=hurt)


def _starts_turn_in(c: Cast, area: Any, fn: Callable[[int], None]) -> None:
    """What an enemy suffers for starting its turn inside a zone.

    `_starts_turn_in_zone` next door is this with the payout fixed at flat
    damage; several zones here lay a condition instead, so the payout is a
    callback.
    """
    me = c.me
    squares_ = frozenset(area)

    def toll(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in c.in_squares(squares_, side="enemy"):
            fn(ev.actor)

    c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} toll")


def _ally_starting_in_aura(
    c: Cast, radius: int, fn: Callable[[int], None]
) -> None:
    """An aura for the board to draw, and what an ally gets for waking in it.

    Who is inside is asked as the turn opens rather than kept as a list: the
    aura travels with the creature and a stored membership would be stale the
    moment either of them moved.
    """
    me = c.me
    c.aura(radius, until=When.ENCOUNTER, label=c.ref)

    def at_the_top(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.allies():
            return
        if distance_between(c.world, me, ev.actor) <= radius:
            fn(ev.actor)

    c.watch(TurnStart, at_the_top, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


def _mine(c: Cast) -> Callable[[int], bool]:
    """"Allies in the aura", as the pool `_hold_while_inside` asks for."""
    return lambda who: who in c.allies()


# --------------------------------------------------------------------------
# m1401
# --------------------------------------------------------------------------


@power(
    "m1401a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m1401a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m1401a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=Target("any", everyone=True, label="creatures in contact with the ground"),
    attack=Attack(vs=REF, printed=7),
    dropped=("Target.kind",),
)
def m1401a1(c: Cast) -> None:
    """"Affects only creatures in contact with the ground" is height off the
    floor, which `c.height` answers; what it cannot do is narrow the offer, so
    a flier in the burst is targeted and then left alone."""
    if c.height(on=c.target):
        return
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m1401a2",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.carrying(thing)",),
)
def m1401a2(c: Cast) -> None:
    """Extra damage near the thing it is set to watch.

    `c.guarding` is the relation the board sets when something is put in this
    creature's charge, so the adjacency half is real and fires whenever an
    encounter binds one. The other half is not askable: `c.carrying` takes a
    row's ref and there is no way to ask whether a creature is holding a
    particular entity.
    """

    def beside_my_charge(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and any(
            c.adjacent_to(thing, victim) for thing in c.guarding(of=c.me)
        )

    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=beside_my_charge,
    )


# --------------------------------------------------------------------------
# m1435
# --------------------------------------------------------------------------


@power(
    "m1435a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 1, dtype=DamageType.PSYCHIC),
)
def m1435a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.PSYCHIC)


@power(
    "m1435a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 2),
)
def m1435a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1435a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m1435a2(c: Cast) -> None:
    """Two swings even against one creature, which is what `_twice` is for."""
    _twice(c, "m1435a1")


@power(
    "m1435a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage(
        "1d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True
    ),
)
def m1435a3(c: Cast) -> None:
    """"Save ends both" is one hold carrying the daze and the burn, which is
    what makes one saving throw end both of them; the slide hangs off
    `escalate=`, which runs on every failed save as the card says."""
    _recharge_when_bloodied(c)
    if not c.strike():
        c.hit(half=True)
        return
    c.hit()

    def failed(eff: Effect) -> None:
        c.slide(3, on=eff.owner)

    c.condition(
        Condition.DAZED,
        until=When.SAVE_ENDS,
        ongoing=(5, DamageType.PSYCHIC),
        escalate=failed,
    )


def _dazed_or_stunned_within(radius: int) -> Callable[[World, int], bool]:
    """"Targets a stunned or dazed creature", as a gate on the offer."""

    def ok(world: World, eid: int) -> bool:
        from combat_engine.engine.query import is_

        return _reachable(
            world, eid, radius,
            lambda foe: is_(world, foe, Condition.STUNNED)
            or is_(world, foe, Condition.DAZED),
        )

    return ok


@power(
    "m1435a4",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=Target("enemy", 1, label="one stunned or dazed creature"),
    keywords=[Keyword.CHARM, Keyword.GAZE],
    attack=Attack(vs=WILL, printed=8),
    requires=_dazed_or_stunned_within(10),
    requires_text="a stunned or dazed enemy within 10 squares",
    dropped=("Target.kind",),
)
def m1435a4(c: Cast) -> None:
    """"Only one creature at a time" costs nothing here: the row is an
    encounter power and the hold runs out on its own turn, so a second
    victim is unreachable by construction."""
    victim = _in_reach_suffering(c, 10, Condition.STUNNED, Condition.DAZED)
    if victim is None:
        return
    if c.strike(on=victim):
        c.condition(Condition.DOMINATED, until=When.EONT, on=victim)


@power(
    "m1435a5",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("query.light_level(world, square)",),
)
def m1435a5(c: Cast) -> None:
    """Both halves of this are about how bright the creature's square is, and
    nothing on the board measures that."""


# --------------------------------------------------------------------------
# m1512
# --------------------------------------------------------------------------

#: The hazard the altar row throws its victim into, read off the board by ref.
_M1512_STREAM = "m3643"


@power(
    "m1512a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d4", 4),
)
def m1512a0(c: Cast) -> None:
    """The second die is a different type from the first, so it is paid in the
    body: one header damage line cannot carry two types."""
    if c.strike():
        c.hit()
        c.damage("1d6", dtype=DamageType.NECROTIC)


@power(
    "m1512a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d6", 6, dtype=DamageType.NECROTIC),
)
def m1512a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m1512a2",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("3d6", 6, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1512a2(c: Cast) -> None:
    """The throw is at a piece of the encounter rather than at a square, and
    the only thing an author is given to find it with is its ref -- so the
    board is asked for one and the victim is put beside it. Nothing there
    means the throw simply does not happen, which is the same as the hazard
    not being in this fight. The drop at the end is a real fall, so
    `c.fall` pays for it rather than a flat number standing in."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    feature = next(
        (w for w in c.within(20, side="any") if _ref_of(c, w) == _M1512_STREAM),
        None,
    )
    if feature is not None:
        sq = _free_square_beside(c, feature)
        if sq is not None:
            c.teleport(20, who=victim, to=sq)
    c.stunned(until=When.EONT, on=victim)
    c.weakened(until=When.SAVE_ENDS, on=victim)
    c.fall(2, on=victim)


@power(
    "m1512a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=8),
)
def m1512a3(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m1657
# --------------------------------------------------------------------------


@power(
    "m1657a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 5, dtype=DamageType.COLD),
)
def m1657a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1657a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 4, dtype=DamageType.COLD),
)
def m1657a1(c: Cast) -> None:
    """"To a space adjacent to the target" names a destination rather than a
    distance, which is what `to=` is for -- a bare shift would ask the
    controller and on a quiet board walk the other way."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.slowed(until=When.EONT)
    near = [a for a in c.within(3, of=victim, side="ally") if a != c.me]
    mate = c.choose(near, "which ally closes in") if near else None
    if mate is None:
        return
    sq = _free_square_beside(c, victim)
    if sq is not None:
        c.shift(3, who=mate, to=sq)


@power(
    "m1657a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d10", 4, dtype=DamageType.COLD, kind=LIMITED),
)
def m1657a2(c: Cast) -> None:
    """"First Failed Saving Throw" is `escalate=`, which runs on every failed
    save; `_also` is idempotent, which is where "first" comes from. The
    immobilize joins the standing hold rather than becoming an effect of its
    own, so one saving throw still ends one printed sentence."""
    if not c.strike():
        return
    c.hit()

    def failed(eff: Effect) -> None:
        _also(c, eff, Condition.IMMOBILIZED)

    c.condition(Condition.SLOWED, until=When.SAVE_ENDS, escalate=failed)


# --------------------------------------------------------------------------
# m1918
# --------------------------------------------------------------------------


@power(
    "m1918a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=7),
)
def m1918a0(c: Cast) -> None:
    """The compendium leaves a bare numeral where a damage expression would
    go; there is no dice line behind it, so the hold is the whole of the
    Hit."""
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.EONT)


@power(
    "m1918a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("1d6", 4, dtype=DamageType.PSYCHIC),
)
def m1918a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty(WILL, 2, until=When.SAVE_ENDS)


@power(
    "m1918a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m1918a2(c: Cast) -> None:
    """Unseen on a clock and not until it swings: this card puts no condition
    on the veil beyond the start of its next turn."""
    c.invisible(on=c.me, until=When.SONT)


# --------------------------------------------------------------------------
# m3504
# --------------------------------------------------------------------------


@power(
    "m3504a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 2, dtype=DamageType.NECROTIC),
)
def m3504a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m3504a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d4", 4, dtype=DamageType.NECROTIC),
)
def m3504a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m3504a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("3d6", 4, dtype=DamageType.NECROTIC),
)
def m3504a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3504a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m3504a3(c: Cast) -> None:
    """Looking like something else, and a check to see through it. Neither
    half changes anything a fight resolves: nothing on a board asks what a
    creature appears to be."""


# --------------------------------------------------------------------------
# m3535
# --------------------------------------------------------------------------


@power(
    "m3535a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 0, dtype=DamageType.NECROTIC),
)
def m3535a0(c: Cast) -> None:
    """The reward is gated on the surge actually going: a creature with none
    left loses nothing and pays nothing, and `c.spend_surge` says so by
    coming back False."""
    if not c.strike():
        return
    c.hit()
    if c.is_(Condition.IMMOBILIZED) and c.spend_surge(on=c.target):
        c.heal(5, on=c.me)


@power(
    "m3535a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d6", 4, dtype=DamageType.COLD),
    dropped=("Damage(dtypes=)",),
)
def m3535a1(c: Cast) -> None:
    """One blow that is both types at once. The header carries one, so the
    second is the dropped half -- `c.ongoing` takes `dtypes` and `Damage`
    does not."""
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m3535a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("2d6", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3535a2(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m3535a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(10),
    target=Target("ally", 1, label="one destroyed undead ally of level 6 or lower"),
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    todo=("query.fallen(world, side)",),
)
def m3535a3(c: Cast) -> None:
    """`c.reanimate` is exactly the printed effect and the level cap and the
    minion clause are both askable -- what is missing is the target. Nothing
    enumerates the creatures that have already been destroyed: every pool an
    author is given (`c.allies`, `c.within`) filters out the dead, so the row
    cannot find the one creature it is about."""


# --------------------------------------------------------------------------
# m3540
# --------------------------------------------------------------------------


def _reach_word(ref: str) -> str:
    """Which range band a row was rolled at, for a rider that names two."""
    p = get(ref)
    return "" if p is None or p.reach is None else p.reach.kind


@power(
    "m3540a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 5),
    dropped=("c.reroll_ones()",),
)
def m3540a0(c: Cast) -> None:
    """"Or 1d8 + 7 while bloodied" is one expression or the other, so the
    bigger one is paid by hand rather than as a second standing bonus that
    would not stack with anything and would never come off. "Its next attack
    roll" is `once=True` on a hold that expires anyway."""
    if not c.strike():
        return
    if c.bloodied(on=c.me):
        c.damage("1d8", 7)
    else:
        c.hit()
    c.penalty("attack", 2, until=When.EOTNT, once=True)


@power(
    "m3540a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d6", 1),
)
def m3540a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


def _nobody_is_burning(c: Cast) -> None:
    """"Recharges when no enemy is taking ongoing damage."

    Asked at the top of every turn, which is the only moment the board is
    quiet enough for the sentence to be true of it. The die stays in the
    header because that is what `actions.recharge` rolls and what the card
    shows, and the two only ever agree to make the row available sooner.
    """
    me, ref = c.me, c.ref
    label = f"{ref} recharge"
    if any(effect.label == label for effect in c.world.effects.of(me)):
        return

    def quiet(ev: TurnStart) -> None:
        if ev.ghost:
            return
        if not any(_burning(c.world, foe) for foe in c.enemies()):
            c.restore_use(ref, on=me)

    c.watch(TurnStart, quiet, until=When.ENCOUNTER, on=me, label=label)


@power(
    "m3540a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=Target("enemy", 1, label="one creature taking ongoing damage"),
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("2d6", 4, kind=LIMITED),
    requires=lambda world, eid: _reachable(
        world, eid, 10, lambda foe: _burning(world, foe)
    ),
    requires_text="an enemy within 10 squares taking ongoing damage",
    dropped=("Target.kind",),
)
def m3540a2(c: Cast) -> None:
    """The printed penalty is one sentence covering four numbers, so it is
    four holds with one clock; "checks" is the skill key, which is what every
    check the board rolls goes through."""
    _nobody_is_burning(c)
    victim = c.target
    if victim is not None and not _burning(c.world, victim):
        victim = next(
            (foe for foe in sorted(_adjacent_foes(c, 10), key=c.distance)
             if _burning(c.world, foe)),
            None,
        )
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.prone(on=victim)
    c.penalty("attack", 2, on=victim, until=When.EONT)
    c.penalty("skill", 2, on=victim, until=When.EONT)
    for defence in DEFENCES:
        c.penalty(defence, 2, on=victim, until=When.EONT)


_M3540_IMPLEMENT_HIT = "the creature hits with an implement attack"


def _my_implement_hit(world: World, me: int, ev: Hit) -> bool:
    if ev.attacker != me:
        return False
    p = get(ev.power)
    return p is not None and Keyword.IMPLEMENT in p.keywords


@power(
    "m3540a3",
    level=4,
    usage=Usage.DAILY,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3540_IMPLEMENT_HIT,
    on=Trigger(Hit, _my_implement_hit, _M3540_IMPLEMENT_HIT),
)
def m3540a3(c: Cast) -> None:
    """The extra damage goes where the triggering blow landed, which is what
    the event names rather than this row's own target -- a `NO_TARGET` free
    action has none."""
    ev = c.trigger
    victim = getattr(ev, "target", None)
    if victim is not None:
        c.damage("1d10", on=victim)


@power(
    "m3540a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3540a4(c: Cast) -> None:
    """A gate on the damage context rather than a hold put on and taken off:
    who is standing where changes between one blow and the next. The printed
    line names two range bands, and a close burst is neither of them."""

    def mobbed(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None or not _crowd_around(c, victim, least=2):
            return False
        return _reach_word(ctx.get("power") or "") in ("melee", "ranged")

    c.bonus("damage", 5, on=c.me, until=When.ENCOUNTER, when=mobbed)


# --------------------------------------------------------------------------
# m3546
# --------------------------------------------------------------------------


@power(
    "m3546a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 4),
)
def m3546a0(c: Cast) -> None:
    if c.strike():
        _crit_instead(c, "2d6", 14, DamageType.THUNDER)


@power(
    "m3546a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 4),
    requires_text="a particular weapon in hand",
    dropped=("spec.weapon_ref()",),
)
def m3546a1(c: Cast) -> None:
    """The Requirement names a specific weapon, and the only handle on one is
    its printed name -- so the gate is the dropped half and the benefit is
    written. "Any ally who hits the target" is a watch on the victim rather
    than on the allies: one hold, and it does not have to be re-laid when
    somebody new walks up."""
    victim = c.target
    if victim is None or not c.strike():
        return
    _crit_instead(c, "2d6", 14, DamageType.THUNDER)
    me = c.me

    def paid(ev: Hit) -> None:
        if ev.target == victim and ev.attacker != me and ev.attacker in c.allies():
            c.temp_hp(4, on=ev.attacker)

    c.watch(Hit, paid, until=When.EONT, on=me, label=f"{c.ref} reward")


_M3546_CLOSES = "the target moves nearer to the creature"


@power(
    "m3546a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.RADIANT],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("1d6", 3, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m3546a2(c: Cast) -> None:
    """"Moves nearer" is a comparison of two distances, and `Moved` is the
    only one of the three movement events that carries `from_` -- so the
    question is asked there and nowhere else."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    me = c.me

    def closed(ev: Moved) -> None:
        if ev.actor != victim or ev.from_ is None:
            return
        was = min(
            max(abs(ev.from_[0] - sq[0]), abs(ev.from_[1] - sq[1]))
            for sq in squares(c.world, me)
        )
        if distance_between(c.world, me, victim) < was:
            c.damage("1d6", 3, dtype=DamageType.RADIANT, on=victim)

    c.watch(Moved, closed, until=When.EOTNT, on=me, once=True, label=c.ref)


@power(
    "m3546a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 4, kind=LIMITED),
    requires_text="a particular weapon in hand",
    dropped=("spec.weapon_ref()",),
)
def m3546a3(c: Cast) -> None:
    """The allies' bonus is laid on each of them gated on this victim, which
    is where the attack context carries the question: a hold on the target
    cannot say whose roll it helps."""
    victim = c.target
    if victim is None or not c.strike():
        return
    _crit_instead(c, "2d6", 24, DamageType.THUNDER)
    for mate in c.allies():
        c.bonus(
            "attack", 2, on=mate, until=When.EONT,
            when=lambda ctx: ctx.get("target") == victim,
        )


@power(
    "m3546a4",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target("ally", 1, label="the creature or one of its allies"),
    keywords=[Keyword.HEALING],
    dropped=("etl.monster.attack_defence()",),
)
def m3546a4(c: Cast) -> None:
    """The compendium prints an attack line with no defence behind it (#360),
    so there is no roll to make and none is invented; the heal and the step
    are the printed Hit and they are paid. `Target("ally")` rather than
    `other_ally` because the card names the creature itself first."""
    mate = c.target
    if mate is None:
        return
    c.heal(12, on=mate)
    c.slide(1, on=mate)


_M3546_ALLY_FELLED = "an ally within 10 squares bloodies or drops an enemy"


def _ally_felled_somebody(world: World, me: int, ev: Any) -> bool:
    """Whoever crossed the line, on either event, is `source`.

    `Bloodied` carries it the way `Dropped` does, so one predicate answers
    both halves of the printed sentence.
    """
    who = getattr(ev, "source", None)
    if who is None or who == me:
        return False
    from combat_engine.engine.query import team

    return (
        team(world, who) is team(world, me)
        and distance_between(world, me, who) <= 10
    )


@power(
    "m3546a5",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3546_ALLY_FELLED,
    on=(
        Trigger(Bloodied, _ally_felled_somebody, _M3546_ALLY_FELLED),
        Trigger(Dropped, _ally_felled_somebody, _M3546_ALLY_FELLED),
    ),
)
def m3546a5(c: Cast) -> None:
    """Both printed halves are declared: "bloodies an enemy" is `Bloodied` and
    "reduces an enemy to 0 hit points" is `Dropped`, and declaring one of them
    would look finished and be half a card."""
    ev = c.trigger
    mate = getattr(ev, "source", None)
    if mate is not None:
        c.temp_hp(6, on=mate)


_M3546_SAVE_ENDS = "the creature suffers an effect a save can end"


@power(
    "m3546a6",
    level=4,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M3546_SAVE_ENDS,
    on=Trigger(EffectApplied, _save_ends_on_me, _M3546_SAVE_ENDS),
)
def m3546a6(c: Cast) -> None:
    """`EffectApplied` rather than `ConditionApplied`: a hold carrying nothing
    but ongoing damage announces no condition and would never offer this."""
    c.save(on=c.me)


# --------------------------------------------------------------------------
# m3555
# --------------------------------------------------------------------------


@power(
    "m3555a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4, dtype=DamageType.NECROTIC),
)
def m3555a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3555a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m3555a1(c: Cast) -> None:
    """The miss hands the swing to a neighbour of the *target*, which is a
    different question from a neighbour of the caster."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
        c.slide(1)
        return
    beside = sorted(a for a in c.within(1, of=victim, side="ally") if a != c.me)
    if beside:
        c.grant_attack(beside[0], on=victim)


_M3555_MISSED_MELEE = "the creature is missed by a melee attack"


@power(
    "m3555a2",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M3555_MISSED_MELEE,
    on=Trigger(Miss, both(targets_me, by_melee), _M3555_MISSED_MELEE),
)
def m3555a2(c: Cast) -> None:
    _slip_away(c)


@power(
    "m3555a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3555a3(c: Cast) -> None:
    """Asked as the roll is looked up rather than held on each enemy: who is
    standing next to whom changes between one swing and the next, and a hold
    laid once would be wrong by the time it was read."""

    def pinned(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and any(
            mate != c.me and c.adjacent_to(mate, victim) for mate in c.allies()
        )

    c.gains_advantage(pinned, until=When.ENCOUNTER, on=c.me)


# --------------------------------------------------------------------------
# m3559
# --------------------------------------------------------------------------


@power(
    "m3559a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 2),
)
def m3559a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m3559a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 1),
)
def m3559a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m3559a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=8),
)
def m3559a2(c: Cast) -> None:
    """"If it attacks during its next turn" is the declaration and not the
    outcome, so the watch is on `AttackDeclared`: a miss is still an attack
    and still pays for it. `once=True`, because the card charges once."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.penalty("attack", 2, on=victim, until=When.EONT)

    def swung(ev: AttackDeclared) -> None:
        if ev.attacker == victim:
            c.damage("2d6", 6, dtype=DamageType.NECROTIC, on=victim)

    c.watch(
        AttackDeclared, swung, until=When.EOTNT, on=c.me, once=True,
        label=f"{c.ref} reprisal",
    )


_M3559_ALLY_SLIPPED = "an ally uses m3559a4"


@power(
    "m3559a3",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=Ranged(10),
    target=NO_TARGET,
    trigger=_M3559_ALLY_SLIPPED,
    on=Trigger(PowerUsed, _ally_used("m3559a4"), _M3559_ALLY_SLIPPED),
    dropped=("etl.monster.attack_defence()",),
)
def m3559a3(c: Cast) -> None:
    """The compendium prints an attack line with no defence behind it (#360);
    the Effect is what the card pays out and it is paid. The ally is read off
    the triggering event rather than off `ev.targets`, which on a `NO_TARGET`
    reaction names nobody."""
    mate = _triggering_enemy(c)
    if mate is not None and mate in c.allies():
        _let_it_swing(c, mate, step=2)


@power(
    "m3559a4",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M3555_MISSED_MELEE,
    on=Trigger(Miss, both(targets_me, by_melee), _M3555_MISSED_MELEE),
)
def m3559a4(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m3568
# --------------------------------------------------------------------------


@power(
    "m3568a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 2, dtype=DamageType.NECROTIC),
)
def m3568a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m3568a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=6),
    damage=Damage("1d4", 4, dtype=DamageType.NECROTIC),
)
def m3568a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m3568a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("3d6", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m3568a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3568a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m3568a3(c: Cast) -> None:
    """The same disguise as m3504a3 at a harder check. Nothing a fight
    resolves asks what a creature appears to be."""


# --------------------------------------------------------------------------
# m3979
# --------------------------------------------------------------------------


@power(
    "m3979a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 4),
)
def m3979a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3979a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d6", 4, dtype=DamageType.ACID),
)
def m3979a1(c: Cast) -> None:
    """"Save ends both" is one hold carrying the weakness and the burn, which
    is what makes one saving throw end both."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.WEAKENED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.ACID),
        )


# --------------------------------------------------------------------------
# m4202
# --------------------------------------------------------------------------


@power(
    "m4202a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d4", 4),
)
def m4202a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m4202a1",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d4", 4, kind=LIMITED),
)
def m4202a1(c: Cast) -> None:
    """The swing is written out rather than borrowed from m4202a0: that row
    slides the target 3 squares and this card does not, so lending it would
    add a printed sentence that is not there. The step comes after every
    attack, which is what `c.last` is for."""
    if c.strike():
        c.hit()
        c.prone()
    if c.last:
        c.shift(1)


_M4202_FELLED = "the creature drops to 0 hit points"


@power(
    "m4202a2",
    level=4,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD, Keyword.POLYMORPH],
    trigger=_M4202_FELLED,
    on=Trigger(Dropped, about_me, _M4202_FELLED),
)
def m4202a2(c: Cast) -> None:
    """The corpse becomes terrain, so it is a wall in its own square rather
    than a zone: a zone is something creatures stand in and this is something
    they cannot. The toll is "until the end of its current turn", which is
    `When.EOT` measured on whoever woke up next to it."""
    here = c.here
    c.wall(1, at=here, solid=True, until=When.ENCOUNTER, label=c.ref)
    ring = spread({here}, 2)

    def bitten(who: int) -> None:
        c.flat(5, dtype=DamageType.COLD, on=who)
        c.slowed(on=who, until=When.EOT)

    _starts_turn_in(c, ring, bitten)


@power(
    "m4202a3",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4202a3(c: Cast) -> None:
    """"All enemies within its weapon's reach" is the threatened ring, which
    `movement._threat` fixes at one square unless a row raises it."""
    c.threatens(2, on=c.me)


# --------------------------------------------------------------------------
# m4620
# --------------------------------------------------------------------------


@power(
    "m4620a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4620a0(c: Cast) -> None:
    """`MoveStart` and not `MoveEnd`: the flanking ally has to still be where
    it was for the printed sentence to be true, and by `MoveEnd` the enemy has
    left. `query.flanked_by` asks the real question -- two allies on opposite
    sides -- rather than counting neighbours."""
    me = c.me
    c.aura(10, until=When.ENCOUNTER, label=c.ref)

    def bolted(ev: MoveStart) -> None:
        foe = ev.actor
        if getattr(ev, "kind_", "") not in _WILLING:
            return
        if foe not in c.enemies() or distance_between(c.world, me, foe) > 10:
            return
        pinning = [a for a in c.allies() if flanked_by(c.world, foe, a)]
        if pinning:
            c.grant_attack(pinning[0], on=foe)

    c.watch(MoveStart, bolted, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m4620a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 5),
)
def m4620a1(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d8", 13)


@power(
    "m4620a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d8", 6, kind=LIMITED),
    dropped=("c.place_scenery()",),
)
def m4620a2(c: Cast) -> None:
    """"Save ends both" is one hold carrying the immobilize and the burn. The
    Special is the dropped half: the row would have to leave an object in a
    square and recharge when somebody picks it up, and nothing a row can say
    puts an object on the board -- `c.scenery` only reads what is already
    there."""
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED))


#: Who the burst caught, for the Effect line that swings at one of them.
_M4620_STRUCK: list[int] = []


@power(
    "m4620a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("1d6", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4620a3(c: Cast) -> None:
    """The Effect names "one creature he hit with this power", so who was hit
    has to be remembered across the burst: the body is called once per target
    and the list is cleared on the first of them, which is safe because one
    use resolves completely before another begins."""
    if c.first:
        _M4620_STRUCK.clear()
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)
        if c.target is not None:
            _M4620_STRUCK.append(c.target)
    if c.last and _M4620_STRUCK:
        reachable = [f for f in _M4620_STRUCK if distance_between(c.world, c.me, f) <= 1]
        foe = c.choose(sorted(reachable), "which one it swings at") if reachable else None
        if foe is not None:
            c.basic(on=foe)


#: The pair of holds the order lays, kept so the next order can take them off.
_M4620_ORDER: list[Effect] = []


@power(
    "m4620a4",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(10),
    target=Target("other_ally", 1, label="one ally in line of sight"),
)
def m4620a4(c: Cast) -> None:
    """"Until he uses this power again" is one standing pair at a time, so the
    previous one is taken down by label before the new one goes on -- two
    untyped +2s would otherwise both be live on two different allies. "Or
    until he drops to 0 hit points" is a watch on the caster's own fall."""
    mate = c.target
    if mate is None:
        return
    me = c.me
    for eff in _M4620_ORDER:
        c.world.effects.end(eff, "it gave a new order")
    _M4620_ORDER.clear()
    for key in ("attack", "save"):
        held = c.bonus(key, 2, on=mate, until=When.ENCOUNTER)
        if held is not None:
            _M4620_ORDER.append(held)

    def felled(ev: Dropped) -> None:
        if ev.actor != me:
            return
        for eff in _M4620_ORDER:
            c.world.effects.end(eff, "its captain fell")
        _M4620_ORDER.clear()

    c.watch(Dropped, felled, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} end")


_M4620_FIRST_BLOODIED = "the creature is first bloodied"


@power(
    "m4620a5",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M4620_FIRST_BLOODIED,
    on=Trigger(Bloodied, about_me, _M4620_FIRST_BLOODIED),
)
def m4620a5(c: Cast) -> None:
    """"First" costs nothing to say: `Bloodied` is announced once, on the
    crossing, and the row is an encounter power either way."""
    for defence in DEFENCES:
        c.bonus(defence, 5, on=c.me, until=When.EONT)


@power(
    "m4620a6",
    level=4,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4202_FELLED,
    on=Trigger(Dropped, about_me, _M4202_FELLED),
)
def m4620a6(c: Cast) -> None:
    _death_throe(c)


# --------------------------------------------------------------------------
# m4634
# --------------------------------------------------------------------------


@power(
    "m4634a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d8", 1, dtype=DamageType.PSYCHIC),
)
def m4634a0(c: Cast) -> None:
    """"Instead takes ongoing 5 and is dominated (save ends both)" is the same
    burn with a condition joined to it, which is why `_also` is the whole of
    it: a second save-ends hold would hand the victim a second saving throw
    against one printed sentence. "The tendril remains attached until the
    target saves" is that hold's own lifetime and needs nothing more."""
    if not c.strike():
        return
    c.hit()

    def failed(eff: Effect) -> None:
        _also(c, eff, Condition.DOMINATED)

    burn = c.ongoing(5, DamageType.PSYCHIC)
    if burn is not None:
        burn.escalate = failed


@power(
    "m4634a1",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(3),
    target=UpTo(2),
)
def m4634a1(c: Cast) -> None:
    _twice(c, "m4634a0")


@power(
    "m4634a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("1d10", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4634a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("save", 2, until=When.SAVE_ENDS)


@power(
    "m4634a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d8", 3, dtype=DamageType.FORCE, kind=LIMITED),
)
def m4634a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


_M4634_HURT = "the creature takes damage"


@power(
    "m4634a4",
    level=4,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M4634_HURT,
    on=Trigger(DamageApplied, _damaged_me, _M4634_HURT),
)
def m4634a4(c: Cast) -> None:
    c.shift(6)


# --------------------------------------------------------------------------
# m4644
# --------------------------------------------------------------------------


@power(
    "m4644a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 2),
)
def m4644a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4644a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("1d6", 3),
)
def m4644a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m4644a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=7),
)
def m4644a2(c: Cast) -> None:
    """No damage line at all: the Hit is the burn and the weakness, held as
    one effect so one saving throw ends both."""
    if c.strike():
        c.condition(
            Condition.WEAKENED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.NECROTIC),
        )


@power(
    "m4644a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(10),
    target=Target("other_ally", 99, everyone=True, label="each ally in the burst"),
    once_per_round=True,
)
def m4644a3(c: Cast) -> None:
    """`other_ally` and not `EACH_ALLY`: the card says "all allies" and the
    latter's pool includes the caster (#364), which reads as "you or your
    allies" and is a different sentence."""
    # Untyped: the card prints "+5 speed" and names no bonus type anywhere.
    c.bonus("speed", 5, on=c.target, until=When.EONT)


@power(
    "m4644a4",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=Target("other_ally", 99, everyone=True, label="bloodied allies in the burst"),
    keywords=[Keyword.HEALING],
    dropped=("Target.kind",),
)
def m4644a4(c: Cast) -> None:
    """The restriction is on the ally's state, which `Target` cannot narrow,
    so the burst takes every ally and the wound is asked here."""
    mate = c.target
    if mate is not None and c.bloodied(on=mate):
        c.heal(15, on=mate)


# --------------------------------------------------------------------------
# m4687
# --------------------------------------------------------------------------

#: The lesser block this leader fields and reads its trait against.
_M4687_ROTTER = "m499"


@power(
    "m4687a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 3),
)
def m4687a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4687a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=9),
)
def m4687a1(c: Cast) -> None:
    """"Adjacent to the target **after** the slide" is why the neighbours are
    asked once the slide has happened and not before."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.slide(3, on=victim)
    beside = sorted(a for a in c.within(1, of=victim, side="ally") if a != c.me)
    if beside:
        c.grant_attack(beside[0], on=victim)


@power(
    "m4687a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(10),
    target=Target("other_ally", 4, label="up to four allies of one lesser kind"),
    dropped=("Target.kind",),
)
def m4687a2(c: Cast) -> None:
    """The printed line names a particular lesser block, and the only handle
    on one is its ref -- which `Target` cannot filter on, so the pool is every
    ally and the kind is asked here."""
    mate = c.target
    if mate is not None and _ref_of(c, mate) == _M4687_ROTTER:
        _let_it_swing(c, mate)


@power(
    "m4687a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4687a3(c: Cast) -> None:
    """`c.summon` puts each one on the board *and* in the initiative order,
    which is what "appear" means for something that then takes turns. The
    squares are found one at a time, because each arrival takes one."""
    for _ in range(4):
        sq = _free_square_beside(c, c.me)
        if sq is None:
            return
        c.summon(_M4687_ROTTER, at=sq)


@power(
    "m4687a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4687a4(c: Cast) -> None:
    """The grab is laid by the leader on the lesser creature's behalf, which
    `by=` is for: `c.grab` without it would record the wrong captor and every
    "escape from it" question would be asked of the wrong creature."""
    me = c.me

    def latched(ev: Hit) -> None:
        if ev.attacker == me or ev.attacker not in c.allies():
            return
        if _ref_of(c, ev.attacker) != _M4687_ROTTER:
            return
        if distance_between(c.world, me, ev.attacker) > 2:
            return
        c.grab(on=ev.target, by=ev.attacker)

    c.watch(Hit, latched, until=When.ENCOUNTER, on=me, label=c.ref)


# --------------------------------------------------------------------------
# m4766
# --------------------------------------------------------------------------


@power(
    "m4766a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.POISON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 3),
)
def m4766a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m4766a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d6", 3),
    requires=_has_advantage,
    requires_text="must have combat advantage",
)
def m4766a1(c: Cast) -> None:
    """The secondary attack is rolled with the level taken back out by hand:
    only one line fits in the header, and `world.scaling.trim` is what the
    header itself would have done to it."""
    if not c.strike():
        return
    c.hit()
    if c.attack(c.world.scaling.trim(7, c.level), FORT):
        c.ongoing(5, DamageType.POISON)


@power(
    "m4766a2",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=8),
    once_per_round=True,
)
def m4766a2(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


def _dull_beast(c: Cast, who: int) -> bool:
    """"An allied natural beast with Intelligence 1, or anything spidery."

    Two different printed handles on one target line: a creature type plus an
    ability score, or a single keyword. `Stats` is where the score lives.
    """
    if c.is_kind("spider", on=who):
        return True
    stats = c.world.get(who, Stats)
    return (
        c.is_kind("beast", on=who)
        and stats is not None
        and stats.score(Ability.INT) <= 1
    )


@power(
    "m4766a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=Target("other_ally", 1, label="one adjacent dull beast or spider ally"),
    dropped=("Target.kind",),
)
def m4766a3(c: Cast) -> None:
    """Three printed benefits and the chooser picks one, which is what the
    card says and not an author's preference. The middle one needs *which* of
    the creature's rows recharges, so its `Powers.known` is read and the
    recharge rows are the candidates -- `c.restore_use` then `c.use_power` is
    "recharges and the target uses it immediately"."""
    mate = c.target
    if mate is None or not _dull_beast(c, mate):
        return
    rechargeable = [
        ref
        for ref in getattr(c.world.get(mate, Powers), "known", ())
        if (p := get(ref)) is not None and p.usage is Usage.RECHARGE
    ]
    options = ["sharper", "poisoned"]
    if rechargeable:
        options.insert(1, "again")
    pick = c.choose(options, "which boon")
    if pick == "sharper":
        c.bonus("damage", 4, on=mate, until=When.EOTNT)
    elif pick == "again":
        ref = rechargeable[0]
        c.restore_use(ref, on=mate)
        c.use_power(ref, who=mate)
    elif pick == "poisoned":

        def bit(ev: Hit) -> None:
            if ev.attacker == mate and _reach_word(ev.power) == "melee":
                c.ongoing(5, DamageType.POISON, on=ev.target)

        c.watch(
            Hit, bit, until=When.ENCOUNTER, on=c.me, once=True,
            label=f"{c.ref} venom",
        )


@power(
    "m4766a4",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.ignores_difficult(when=)",),
)
def m4766a4(c: Cast) -> None:
    """The web half is a terrain word and plays. The other half is difficult
    terrain narrowed by *what made it*, and `c.ignores_difficult` waives a
    kind of terrain or all of it with nothing in between."""
    c.ignores_difficult("web", on=c.me)


# --------------------------------------------------------------------------
# m4927, m5033 -- in controllers.py
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# m5148
# --------------------------------------------------------------------------


@power(
    "m5148a0",
    level=4,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5148a0(c: Cast) -> None:
    """Filed as a standard action and plainly a trait, the same one m728a2
    carries at the same number."""
    _tougher_when_hurt(c, 3)


@power(
    "m5148a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 4),
)
def m5148a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        return
    _pass_the_swing(c)


_M5148_MISSED_MELEE = "an enemy misses the creature with a melee attack"


@power(
    "m5148a2",
    level=4,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger=_M5148_MISSED_MELEE,
    on=Trigger(Miss, both(targets_me, by_melee), _M5148_MISSED_MELEE),
)
def m5148a2(c: Cast) -> None:
    _slip_away(c)


# --------------------------------------------------------------------------
# m5314
# --------------------------------------------------------------------------


@power(
    "m5314a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5314a0(c: Cast) -> None:
    """The exemption is asked as each roll is looked up rather than when the
    enemy walks in: whether it is being puppeted changes inside the aura, and
    a hold laid once on entry would be wrong a round later. "Skill checks and
    ability checks" is the one `skill` key, which is what every check the
    board rolls goes through."""
    ring = c.aura(2, until=When.ENCOUNTER, label=c.ref)

    def unfree(who: int) -> Callable[[dict[str, Any]], bool]:
        return lambda _ctx: not c.is_(Condition.DOMINATED, on=who)

    def lay(who: int) -> list[Effect | None]:
        gate = unfree(who)
        return [
            c.penalty("attack", 2, on=who, until=When.ENCOUNTER, when=gate),
            c.penalty("skill", 2, on=who, until=When.ENCOUNTER, when=gate),
        ]

    _hold_while_inside(c, ring, lambda who: who in c.enemies(), lay)


@power(
    "m5314a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d8", 4, dtype=DamageType.NECROTIC),
)
def m5314a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.no_healing(until=When.EONT)


@power(
    "m5314a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("1d10", 4, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m5314a2(c: Cast) -> None:
    """"Uses a free action to make an at-will attack ... against a creature of
    the caster's choice" is `c.grant_attack`, which hands the swing over and
    lets the row doing the handing pick the victim."""
    _recharge_when_using(c, "m5314a5")
    victim = c.target
    if victim is None:
        return
    if not c.strike():
        c.hit(half=True)
        c.dazed(until=When.EONT)
        return
    c.hit()
    theirs = sorted(a for a in c.within(99, of=victim, side="ally") if a != victim)
    mark = c.choose(theirs, "who it is turned on") if theirs else None
    if mark is not None:
        c.grant_attack(victim, on=mark)


@power(
    "m5314a3",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=8),
    once_per_round=True,
    requires=_while_bloodied,
    requires_text="the creature must be bloodied",
)
def m5314a3(c: Cast) -> None:
    """The Requirement is asked again here, because `turns.arm_traits_of`
    aside, `requires=` is only ever read by `dsl.usable` and a row can be
    reached without it."""
    if not _is_bloodied(c.world, c.me):
        return
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.EONT)


_M5314_NEIGHBOUR_HURT = "an adjacent enemy takes damage"


def _adjacent_enemy_hurt(world: World, me: int, ev: DamageApplied) -> bool:
    from combat_engine.engine.query import enemies

    who = getattr(ev, "target", None)
    return (
        who is not None
        and who in enemies(world, me)
        and distance_between(world, me, who) <= 1
    )


@power(
    "m5314a4",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=CloseBurst(1),
    target=Target("enemy", 1, label="the triggering enemy"),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=6),
    damage=Damage("1d6", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
    trigger=_M5314_NEIGHBOUR_HURT,
    on=Trigger(DamageApplied, _adjacent_enemy_hurt, _M5314_NEIGHBOUR_HURT),
)
def m5314a4(c: Cast) -> None:
    """"The triggering enemy" is read off the event, not off `ev.targets`: an
    immediate action declares a target and then aims itself at whoever the
    trigger named."""
    victim = getattr(c.trigger, "target", None) or c.target
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.dazed(until=When.EONT, on=victim)


@power(
    "m5314a5",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M4202_FELLED,
    on=Trigger(Dropped, about_me, _M4202_FELLED),
)
def m5314a5(c: Cast) -> None:
    """Off the board and then back on it with half its hit points. The return
    is paid by `c.reanimate`, which gives the corpse a square again -- a heal
    cannot, because the creature is already down -- and the relocation waits
    for the turn the card says it waits for."""
    me = c.me
    health = c.world.get(me, Health)
    half = max(1, (health.max_hp // 2) if health is not None else 1)
    c.condition(Condition.REMOVED, until=When.SONT, on=me)

    def returns(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        if not alive(c.world, me):
            c.reanimate(on=me, hp=half, until=When.ENCOUNTER)
        c.teleport(5, who=me)

    c.watch(TurnStart, returns, until=When.SONT, on=me, once=True, label=c.ref)


# --------------------------------------------------------------------------
# m5402
# --------------------------------------------------------------------------


@power(
    "m5402a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 0),
)
def m5402a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5402a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT],
)
def m5402a1(c: Cast) -> None:
    """Printed as an Effect with no attack line, so there is no roll and the
    damage is flat -- `c.flat` rather than `c.damage`, which would be dice."""
    c.flat(5, dtype=DamageType.FORCE)


@power(
    "m5402a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d8", 4, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m5402a2(c: Cast) -> None:
    """The secondary is measured from the *primary target* and rolled with the
    level taken back out by hand, since only one attack line fits in a header.
    "Ends its turn more than 5 squares away while slowed" is a `TurnEnd` watch
    that asks both halves, because either can have changed."""
    primary = c.target
    if primary is None or not c.strike():
        return
    c.hit()
    near = sorted(
        foe for foe in c.enemies()
        if foe != primary and distance_between(c.world, primary, foe) <= 5
    )
    for foe in near[:2]:
        if not c.attack(c.world.scaling.trim(8, c.level), REF, on=foe):
            continue
        c.flat(4, dtype=DamageType.LIGHTNING, on=foe)
        c.slowed(until=When.SAVE_ENDS, on=foe)
        _stray_shock(c, primary, foe)


def _stray_shock(c: Cast, primary: int, foe: int) -> None:
    """The toll for ending a turn too far from where the storm is anchored."""

    def drifted(ev: TurnEnd) -> None:
        if ev.actor != foe or ev.ghost:
            return
        if not c.is_(Condition.SLOWED, on=foe):
            return
        if distance_between(c.world, primary, foe) > 5:
            c.flat(5, dtype=DamageType.LIGHTNING, on=foe)
            c.prone(on=foe)

    c.watch(TurnEnd, drifted, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} drift")


@power(
    "m5402a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d6", 4, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m5402a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.dazed(until=When.SAVE_ENDS)


_M5402_AIMED_AT = "the creature is the target of a melee or ranged attack"


def _aimed_at_me_by_hand(world: World, me: int, ev: AttackDeclared) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    p = get(getattr(ev, "power", "") or "")
    return p is not None and p.reach is not None and p.reach.kind in ("melee", "ranged")


@power(
    "m5402a4",
    level=4,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    trigger=_M5402_AIMED_AT,
    on=Trigger(AttackDeclared, _aimed_at_me_by_hand, _M5402_AIMED_AT),
)
def m5402a4(c: Cast) -> None:
    """"The defence targeted by the triggering attack" is a plain attribute on
    the event, set by `resolve.attack` and not declared on the dataclass."""
    which = getattr(c.trigger, "vs", None)
    if which is not None:
        c.bonus(which, 4, on=c.me, until=When.EONT)


# --------------------------------------------------------------------------
# m5415
# --------------------------------------------------------------------------


@power(
    "m5415a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5),
)
def m5415a0(c: Cast) -> None:
    """"Grants combat advantage" with nobody named is to everybody, which is
    `to="team"` read from the caster's side."""
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.EOTNT, to="team")


@power(
    "m5415a1",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=8),
    requires=_while_bloodied,
    requires_text="the creature must be bloodied",
)
def m5415a1(c: Cast) -> None:
    """Both holds are laid with one clock, because "save ends both" is one
    saving throw; the Requirement is asked again here, since nothing reads the
    header's copy of it once the row has been reached."""
    if not _is_bloodied(c.world, c.me):
        return
    if c.strike():
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)
        c.grants_advantage(until=When.SAVE_ENDS, to="team")


@power(
    "m5415a2",
    level=4,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(6),
    target=Target("other_ally", 1, label="one ally within 6 squares"),
    once_per_round=True,
    requires=lambda world, eid: not _is_bloodied(world, eid),
    requires_text="the creature must not be bloodied",
)
def m5415a2(c: Cast) -> None:
    """"Its speed" is the ally's, read off the board rather than assumed: a
    slowed or hobbled ally moves what it can."""
    if _is_bloodied(c.world, c.me):
        return
    mate = c.target
    if mate is not None:
        c.move(c.speed_of(mate), who=mate)


# --------------------------------------------------------------------------
# m5490
# --------------------------------------------------------------------------


@power(
    "m5490a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d10", 7),
)
def m5490a0(c: Cast) -> None:
    """The slide is an Effect line, so it happens whether or not the blow
    landed -- which is the difference between it and a Hit rider."""
    if c.strike():
        c.hit()
    c.slide(3)


@power(
    "m5490a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=Target("enemy", 1, label="one enemy in the burst"),
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d10", 7, kind=LIMITED),
)
def m5490a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m5490a2",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=5),
    damage=Damage("3d6", 4, kind=LIMITED),
)
def m5490a2(c: Cast) -> None:
    """The Effect is about allies, who are not targets of this row, so they
    are found in the blast's own squares once for the whole use."""
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.prone()
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            if mate != c.me:
                c.shift(3, who=mate)


@power(
    "m5490a3",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M4202_FELLED,
    on=Trigger(Dropped, about_me, _M4202_FELLED),
)
def m5490a3(c: Cast) -> None:
    """A bare saving throw against nothing in particular, and what it buys is
    a waiver rather than hit points: the creature is still at 0 and still
    falls when the clock runs out."""
    if c.save(on=c.me, bare=True, against=f"{c.ref} grit"):
        c.ignore_condition(
            Condition.UNCONSCIOUS, Condition.DYING, on=c.me, until=When.EONT
        )


# --------------------------------------------------------------------------
# m5890
# --------------------------------------------------------------------------


@power(
    "m5890a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    narrative=("skill:perception", "skill:stealth"),
)
def m5890a0(c: Cast) -> None:
    """"Cannot be surprised" is a real immunity and is laid. The other half is
    a bonus to two skills, and the circumstance is what the aura narrows: no
    Perception or Stealth check is rolled to resolve a fight, so the bonus has
    nowhere to go and nothing is missing."""
    ring = c.aura(10, until=When.ENCOUNTER, label=c.ref)

    def steady(who: int) -> list[Effect | None]:
        return [c.immune(Condition.SURPRISED, on=who, until=When.ENCOUNTER)]

    _hold_while_inside(c, ring, _mine(c), steady)


@power(
    "m5890a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 3),
)
def m5890a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m5890a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.RADIANT],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d8", 4, dtype=DamageType.LIGHTNING),
    dropped=("Damage(dtypes=)",),
)
def m5890a2(c: Cast) -> None:
    """"If the target was already immobilized" is asked before the new hold
    goes on, which is the only moment the word "already" is true. The header
    carries one of the two damage types; the second is the dropped half."""
    if not c.strike():
        c.slowed(until=When.EONT)
        return
    already = c.is_(Condition.IMMOBILIZED)
    c.hit()
    if already:
        c.dazed(until=When.EONT)
    else:
        c.immobilized(until=When.EONT)


@power(
    "m5890a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d8", 3, dtype=DamageType.POISON, kind=LIMITED, half_on_miss=True),
)
def m5890a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.grants_advantage(until=When.SAVE_ENDS, to="team")


# --------------------------------------------------------------------------
# m6116
# --------------------------------------------------------------------------


@power(
    "m6116a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.threatens(when=)",),
)
def m6116a0(c: Cast) -> None:
    """The ring is widened, which is most of the card. What is dropped is
    "against bloodied creatures": `c.threatens` sets a distance and the window
    opens for everybody inside it."""
    c.threatens(2, on=c.me)


@power(
    "m6116a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6116a1(c: Cast) -> None:
    """`DamageApplied` carries what the blow was, so the type is read off the
    event rather than guessed. `c.escape(auto=True)` is the release without a
    check, because the card gives the captive no roll to make."""
    me = c.me

    def scorched(ev: DamageApplied) -> None:
        if getattr(ev, "target", None) != me:
            return
        kinds = set(getattr(ev, "dtypes", ()) or ())
        if getattr(ev, "dtype", None) is not None:
            kinds.add(ev.dtype)
        if DamageType.RADIANT not in kinds:
            return
        for victim in c.grabbing(of=me):
            c.escape(on=victim, auto=True)

    c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6116a2",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m6116a2(c: Cast) -> None:
    """Looking like scenery, and a check to tell. Nothing a fight resolves
    asks what a creature appears to be."""


@power(
    "m6116a3",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d4", 6),
    dropped=("c.grab(dc=)",),
)
def m6116a3(c: Cast) -> None:
    """The pull is an Effect line and lands either way. The printed escape DC
    is the dropped half -- `c.grab` takes no number."""
    if c.strike():
        c.hit()
        c.grab()
    c.pull(1)


@power(
    "m6116a4",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=Target("enemy", 1, label="one creature the creature is grabbing"),
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d6", 3, dtype=DamageType.POISON),
    requires=_holds_somebody,
    requires_text="must be grabbing a creature",
    dropped=("Target.kind",),
)
def m6116a4(c: Cast) -> None:
    """Two escalations on one hold, and `escalate=` fires on every failure --
    so the failures are counted and the first adds one condition, the second
    the other. `_also` joining the standing hold is what makes "save ends
    all" one saving throw rather than three."""
    held = c.grabbing(of=c.me)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    misses: list[int] = []

    def failed(eff: Effect) -> None:
        misses.append(1)
        if len(misses) == 1:
            _also(c, eff, Condition.WEAKENED)
        else:
            _also(c, eff, Condition.DOMINATED)

    burn = c.ongoing(5, DamageType.POISON, on=victim)
    if burn is not None:
        burn.escalate = failed


@power(
    "m6116a5",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=Target("enemy", 1, label="one creature the creature is grabbing"),
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d8", 6, kind=LIMITED),
    requires=_holds_somebody,
    requires_text="must be grabbing a creature",
    dropped=("Target.kind",),
)
def m6116a5(c: Cast) -> None:
    """The printed recharge is a condition rather than a die, so the die stays
    in the header -- that is what `actions.recharge` rolls -- and the two
    sentences the card gives are armed on top of it: one is answered on
    `Bloodied` with this creature as the `source`, the other on its own grab
    landing on somebody already hurt."""
    me, ref = c.me, c.ref

    def fed(ev: Bloodied) -> None:
        if getattr(ev, "source", None) == me:
            c.restore_use(ref, on=me)

    def caught(ev: Hit) -> None:
        if ev.attacker == me and c.bloodied(on=ev.target) and ev.target in c.grabbing(of=me):
            c.restore_use(ref, on=me)

    c.watch(Bloodied, fed, until=When.ENCOUNTER, on=me, label=f"{ref} recharge")
    c.watch(Hit, caught, until=When.ENCOUNTER, on=me, label=f"{ref} haul")
    held = c.grabbing(of=me)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.heal(10, on=me)


# --------------------------------------------------------------------------
# m6119
# --------------------------------------------------------------------------


@power(
    "m6119a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6119a0(c: Cast) -> None:
    """Two holds per ally with one lifetime, which is what the list form of
    `_hold_while_inside` is for; the pool is narrowed by what the ally *is*,
    which is read off its stat block."""
    ring = c.aura(3, until=When.ENCOUNTER, label=c.ref)

    def kin(who: int) -> bool:
        return who in c.allies() and (
            c.is_kind("beast", on=who) or c.is_kind("goblin", on=who)
        )

    def lay(who: int) -> list[Effect | None]:
        return [
            c.bonus("damage", 2, on=who, until=When.ENCOUNTER, kind="power"),
            c.bonus("save", 2, on=who, until=When.ENCOUNTER, kind="power"),
        ]

    _hold_while_inside(c, ring, kin, lay)


@power(
    "m6119a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 3),
)
def m6119a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.EONT, to="team")


@power(
    "m6119a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d8", 3),
)
def m6119a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(3)


@power(
    "m6119a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d8", 3, dtype=DamageType.POISON, kind=LIMITED),
)
def m6119a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m6119a4",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ZONE],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d6", 3, kind=LIMITED),
)
def m6119a4(c: Cast) -> None:
    """The zone is laid once for the whole use, which is what `c.first` is
    for. "Until the start of its next turn" is the clock on the slow, and it
    is measured on whoever woke up in there rather than on the caster."""
    if c.first:
        area = c.area()
        c.zone(area, until=When.ENCOUNTER, label=c.ref)
        _starts_turn_in(c, area, lambda who: c.slowed(on=who, until=When.SOTNT))
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


_M6119_MISSED = "an attack misses the creature"


@power(
    "m6119a5",
    level=4,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M6119_MISSED,
    on=Trigger(Miss, targets_me, _M6119_MISSED),
)
def m6119a5(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m6397
# --------------------------------------------------------------------------


@power(
    "m6397a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6397a0(c: Cast) -> None:
    """The bonus is against "enemies in the aura", so it is a gate on the
    damage context rather than part of the hold: who is inside changes
    between one blow and the next."""
    ring = c.aura(2, until=When.ENCOUNTER, label=c.ref)

    def kin(who: int) -> bool:
        return who in c.allies() and (
            c.is_kind("spider", on=who) or c.is_kind("drow", on=who)
        )

    def inside(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and victim in c.world.zones.occupants(ring)

    def lay(who: int) -> list[Effect | None]:
        return [
            c.bonus("damage", 2, on=who, until=When.ENCOUNTER, when=inside)
        ]

    _hold_while_inside(c, ring, kin, lay)


@power(
    "m6397a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 2),
)
def m6397a1(c: Cast) -> None:
    """Two clocks on one hold -- a saving throw, and leaving the aura -- so
    the save-ends hold is laid and the departure ends it early. `ZoneExited`
    is the one announcement of the second."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    opening = c.grants_advantage(on=victim, to="team", until=When.SAVE_ENDS)
    if opening is None:
        return
    ring = c.my_aura("m6397a0")

    def left(ev: ZoneExited) -> None:
        if ev.actor == victim and ev.zone == ring:
            c.world.effects.end(opening, "it left the ring")

    c.watch(
        ZoneExited, left, until=When.ENCOUNTER, on=c.me, once=True,
        label=f"{c.ref} ring",
    )


@power(
    "m6397a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 3),
)
def m6397a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.POISON),
        )


@power(
    "m6397a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(5),
    target=Target("enemy", 1, label="one creature taking ongoing poison damage"),
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=7),
    requires=lambda world, eid: _reachable(
        world, eid, 5,
        lambda foe: any(
            eff.ongoing and eff.ongoing[1] is DamageType.POISON
            for eff in world.effects.of(foe)
        ),
    ),
    requires_text="an enemy within 5 squares taking ongoing poison damage",
    dropped=("Target.kind",),
)
def m6397a3(c: Cast) -> None:
    """"The ongoing poison damage increases by 5" has exactly one hold to find,
    because a burn of one type does not stack and `c.ongoing` refuses a weaker
    one: the standing amount is read off the effect and a stronger burn
    supersedes it. The weakness joins that hold, so one save ends both."""
    _recharge_on_miss(c)
    victim = _burning_with_poison(c)
    if victim is None or not c.strike(on=victim):
        return
    standing = _ongoing_of(c, victim, DamageType.POISON)
    worse = c.ongoing(standing + 5, DamageType.POISON, on=victim)
    if worse is not None:
        _also(c, worse, Condition.WEAKENED)


def _burning_with_poison(c: Cast) -> int | None:
    """The target if it qualifies, else the nearest enemy in reach that does."""

    def ok(foe: int) -> bool:
        return _ongoing_of(c, foe, DamageType.POISON) > 0

    if c.target is not None and ok(c.target):
        return c.target
    return next(
        (foe for foe in sorted(_adjacent_foes(c, 5), key=c.distance) if ok(foe)),
        None,
    )


@power(
    "m6397a4",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=7),
    dropped=("c.no_conceal()",),
)
def m6397a4(c: Cast) -> None:
    """The opening is laid and plays. What is dropped is the other half:
    nothing takes the benefit of concealment or invisibility *away from the
    creature that has it* -- `c.see_invisible` and `c.ignore_cover` are the
    watcher's side of the same question and would be the wrong creature."""
    if c.strike():
        c.grants_advantage(until=When.EONT, to="team")


@power(
    "m6397a5",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(5),
    target=Target("other_ally", 1, label="one spider ally or drow ally"),
    keywords=[Keyword.HEALING],
    dropped=("Target.kind",),
)
def m6397a5(c: Cast) -> None:
    """A printed Effect with no attack line, so there is no roll: the ally
    pays and the caster is paid. The kind is asked here, since `Target` cannot
    filter on what a creature is."""
    mate = c.target
    if mate is None:
        return
    if not (c.is_kind("spider", on=mate) or c.is_kind("drow", on=mate)):
        return
    c.flat(10, on=mate)
    c.heal(10, on=c.me)


# --------------------------------------------------------------------------
# m6563
# --------------------------------------------------------------------------


@power(
    "m6563a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6563a0(c: Cast) -> None:
    """The step is offered rather than taken: "can shift" is the ally's
    choice, and `c.shift` with a bare distance asks for a destination."""

    def rouse(who: int) -> None:
        if c.is_kind("construct", on=who):
            c.shift(1, who=who)

    _ally_starting_in_aura(c, 3, rouse)


@power(
    "m6563a1",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6563a1(c: Cast) -> None:
    """`Moved` and not `MoveEnd`, because the captive has to be put down
    relative to where the captor has arrived. The destination is named rather
    than a distance given -- "a space of its choice adjacent to it" -- which
    is what `to=` is for; a teleport, because the haul is not the captive's
    own movement and must not provoke."""
    me = c.me

    def hauled(ev: Moved) -> None:
        if ev.actor != me:
            return
        for victim in c.grabbing(of=me):
            sq = _free_square_beside(c, me)
            if sq is not None:
                c.teleport(99, who=victim, to=sq)

    c.watch(Moved, hauled, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6563a2",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d4", 6),
    requires=_not_grabbing,
    requires_text="can grab only one creature at a time",
    dropped=("c.grab(dc=)",),
)
def m6563a2(c: Cast) -> None:
    """"Only one creature at a time" is the Requirement, asked again here
    because nothing reads the header's copy once the row is reached. The
    printed escape DC is the dropped half."""
    if not _not_grabbing(c.world, c.me):
        return
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m6563a3",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=7),
    requires=_holds_somebody,
    requires_text="must be grabbing a creature",
)
def m6563a3(c: Cast) -> None:
    """The burst is centred on the *pushed creature* and not on the caster, so
    it is measured by hand from where that creature ended up: `c.area` would
    draw it around the thrower. The attack is rolled with the level taken back
    out, since the header's own line is measured from the wrong square."""
    me, ref = c.me, c.ref

    def still_holding(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost and c.grabbing(of=me):
            c.restore_use(ref, on=me)

    c.watch(
        TurnStart, still_holding, until=When.ENCOUNTER, on=me,
        label=f"{ref} recharge",
    )
    victim = next(iter(sorted(c.grabbing(of=me))), None)
    if victim is None:
        return
    c.escape(on=victim, auto=True)
    c.push(3, on=victim)
    ring = spread(squares(c.world, victim), 1)
    for foe in c.in_squares(ring, side="any"):
        if foe == me:
            continue
        if c.attack(c.world.scaling.trim(7, c.level), REF, on=foe):
            c.damage("1d4", 4, on=foe)
            c.prone(on=foe)


# --------------------------------------------------------------------------
# m6575
# --------------------------------------------------------------------------


@power(
    "m6575a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 5, dtype=DamageType.NECROTIC),
)
def m6575a0(c: Cast) -> None:
    """"The target loses necrotic resistance or immunity" is the caster's
    waiver gated on that one victim, not a hold on the victim: the damage
    context carries `target`, so the narrowing is exact and no other
    creature's resistance is touched."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.ignore_resistance(
        dtype=DamageType.NECROTIC,
        immunity=True,
        on=c.me,
        until=When.EONT,
        when=lambda ctx: ctx.get("target") == victim,
    )


@power(
    "m6575a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d6", 5, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m6575a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED,
            until=When.SAVE_ENDS,
            ongoing=(5, DamageType.NECROTIC),
        )


@power(
    "m6575a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.ZONE],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("2d6", 0, kind=LIMITED),
    dropped=("c.grant_action('move_zone')",),
)
def m6575a2(c: Cast) -> None:
    """The zone, its toll and the short sight it imposes all play. What is
    dropped is the minor action that walks it: `c.move_zone` exists and
    `c.grant_action` knows four words, none of them this one, so nothing ever
    offers the move."""
    if c.first:
        area = c.area()
        c.zone(area, until=When.ENCOUNTER, label=c.ref)

        def choked(who: int) -> None:
            c.flat(5, on=who)
            c.sight_range(3, on=who, until=When.EOT)

        _starts_turn_in(c, area, choked)
    if c.strike():
        c.hit()


_M6575_KILLED = "an enemy drops the creature to 0 hit points"


@power(
    "m6575a3",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger=_M6575_KILLED,
    on=Trigger(Dropped, about_me, _M6575_KILLED),
)
def m6575a3(c: Cast) -> None:
    """"The triggering enemy" is `Dropped.source`, which is whoever crossed
    the line, and None when nothing did -- a creature that bled out from its
    own burn pays nobody back."""
    killer = getattr(c.trigger, "source", None)
    if killer is not None:
        c.damage("2d6", 11, dtype=DamageType.NECROTIC, on=killer)


# --------------------------------------------------------------------------
# m6596
# --------------------------------------------------------------------------


@power(
    "m6596a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d8", 2),
)
def m6596a0(c: Cast) -> None:
    """The guard goes up whether or not the blow landed in the printed order,
    but the card hangs it on the Hit, so that is where it is."""
    if not c.strike():
        return
    c.hit()
    c.bonus(AC, 1, on=c.me, until=When.EONT, kind="power")
    beside = sorted(a for a in c.within(1, side="ally") if a != c.me)
    mate = c.choose(beside, "which ally shelters with it") if beside else None
    if mate is not None:
        c.bonus(AC, 1, on=mate, until=When.EONT, kind="power")


@power(
    "m6596a1",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.IMPLEMENT],
    attack=Attack(vs=WILL, printed=8),
)
def m6596a1(c: Cast) -> None:
    """"Can choose to" is the chooser's, not the author's."""
    if not c.strike():
        return
    c.dazed(until=When.EONT)
    if c.choose(["prone", "slide"], "floor it or move it") == "prone":
        c.prone()
    else:
        c.slide(2)


@power(
    "m6596a2",
    level=4,
    usage=ENCOUNTER,
    uses=2,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target("any", 1, label="one creature in the burst"),
    keywords=[Keyword.HEALING],
)
def m6596a2(c: Cast) -> None:
    """"2/Encounter" is `uses=2` and not a second row. "The target can spend a
    healing surge" is the target's own surge, which is what `c.surge` spends
    when it is pointed at somebody else."""
    if c.target is not None:
        c.surge(on=c.target)


# --------------------------------------------------------------------------
# m6601
# --------------------------------------------------------------------------


@power(
    "m6601a0",
    level=4,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6601a0(c: Cast) -> None:
    """"As long as it is not bloodied" is asked as each turn opens rather than
    armed and disarmed by a pair of watches: the creature can be healed back
    above the line and a hold laid once would never come off."""

    def shelter(who: int) -> None:
        if not c.bloodied(on=c.me):
            c.temp_hp(3, on=who)

    _ally_starting_in_aura(c, 5, shelter)


@power(
    "m6601a1",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5),
)
def m6601a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m6601a2",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=7),
    damage=Damage("1d8", 8, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m6601a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m6601a3",
    level=4,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d6", 6, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m6601a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


_M6601_BLOODIED_BY = "an enemy bloodies the creature with an attack"


@power(
    "m6601a4",
    level=4,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_M6601_BLOODIED_BY,
    on=Trigger(Bloodied, about_me, _M6601_BLOODIED_BY),
)
def m6601a4(c: Cast) -> None:
    """`Bloodied` carries `source`, which is the enemy the grudge is against;
    the bonus is then gated on that creature and on the range band, because
    "melee attack rolls and melee damage rolls" is not every roll."""
    foe = getattr(c.trigger, "source", None)
    if foe is None:
        return

    def against_it(ctx: dict[str, Any]) -> bool:
        return (
            ctx.get("target") == foe
            and _reach_word(ctx.get("power") or "") == "melee"
        )

    for key in ("attack", "damage"):
        c.bonus(key, 2, on=c.me, until=When.ENCOUNTER, when=against_it)


# --------------------------------------------------------------------------
# m6606
# --------------------------------------------------------------------------

_M6606_HELD = (
    Condition.IMMOBILIZED,
    Condition.PRONE,
    Condition.RESTRAINED,
)


@power(
    "m6606a0",
    level=4,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d8", 4),
)
def m6606a0(c: Cast) -> None:
    """The three states are asked before the blow is paid, which is when the
    printed sentence is about them -- a creature knocked down by something
    else this round is already one of them."""
    if not c.strike():
        return
    pinned = any(c.is_(cond) for cond in _M6606_HELD)
    c.hit()
    if pinned:
        c.dazed(until=When.EONT)


@power(
    "m6606a1",
    level=4,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_CREATURE,
    attack=Attack(vs=REF, printed=7),
    dropped=("c.place_scenery()",),
)
def m6606a1(c: Cast) -> None:
    """The hold and the toll for failing to shake it play, and the toll is
    `escalate=`, which runs on every failed save as the card says. The printed
    recharge is the dropped half: it needs the row to leave an object in a
    square and come back when the creature walks over and picks it up, and
    nothing a row can say puts an object on the board."""
    if not c.strike():
        return

    def failed(eff: Effect) -> None:
        c.flat(5, on=eff.owner)

    c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, escalate=failed)


@power(
    "m6606a2",
    level=4,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=Target("enemy", 1, label="one enemy in the burst"),
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=7),
)
def m6606a2(c: Cast) -> None:
    if c.strike():
        c.push(1)


@power(
    "m6606a3",
    level=4,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger=_M3546_SAVE_ENDS,
    on=Trigger(EffectApplied, _save_ends_on_me, _M3546_SAVE_ENDS),
)
def m6606a3(c: Cast) -> None:
    c.save(on=c.me)
