"""Monster abilities, level 10, brutes.

132 rows across 33 stat blocks. `brutes.py` holds the earlier sweep of this
level and is not touched here. Nine blocks in the brief print no abilities
at all (m2931, m3043, m3069, m3450, m396, m4982, m4983, m707, m87) and so
have nothing to decorate.

Conventions, inherited from the earlier sweeps:

* numbers load from `game.db` -- the attack line is written exactly as
  printed and the damage line goes in the header as data;
* a **trait** costs no action, has no target, and arms the watches that
  hold it, whatever the compendium's action column claims;
* a card with no printed range at all is melee 1;
* a close burst or blast naming no target set takes enemies, except where
  the card says "creatures in the burst" outright;
* `half_on_miss=True` is card data only -- the Miss branch is written by
  hand every time it is declared;
* a blow of two damage types rolled once keeps the first in the header and
  is marked `dropped=("Damage(dtypes=)",)`; two separately named amounts of
  different types are a header blow plus a second `c.flat`, needing no
  marker;
* "Requirement: must be in <form>" is asked in the body, never `requires=`
  on a trait -- `turns.arm_traits_of` arms a trait once and a Requirement
  that starts false is refused for the whole fight;
* "rolls initiative twice" / "an initiative of 10 + its check" is
  `c.extra_turn(at=init.rolled + 10)` -- a whole second slot, which is all
  the primitive says, and what the slot is spent on is the policy's
  business (`m492a2`'s own call, repeated here for three solos);
* a flavour name sitting where this creature's own ref, or another block's
  ref, belongs is extraction noise and is treated as this row's own
  attack throughout, never as a cross-reference.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.lurkers_sa import _triggering_enemy
from combat_engine.content.monsters.level_07.brutes_sa import _ridden_by_seventh_level
from combat_engine.content.monsters.level_09.brutes_sa import _revives_once
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    PERSONAL,
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
    Damage,
    DamageType,
    Initiative,
    Keyword,
    Melee,
    Movement,
    Ranged,
    Relation,
    Size,
    Square,
    Target,
    UpTo,
    Usage,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    ConditionApplied,
    DamageApplied,
    Dropped,
    Escaped,
    Hit,
    Moved,
    MoveStart,
    TurnEnd,
    TurnStart,
    ZoneEntered,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import distance_between, flanked_by, has_combat_advantage, team
from combat_engine.engine.triggers import Trigger, about_me, by_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _adjacent_empty_square(c: Cast, who: int) -> Square | None:
    """A square next to `who` with nobody standing in it."""
    from combat_engine.engine.grid import neighbours
    from combat_engine.engine.query import squares as _squares

    theirs = _squares(c.world, who)
    if not theirs:
        return None
    for sq in neighbours(next(iter(theirs))):
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            return sq
    return None


def _has_mode(c: Cast, who: int | None, mode: str) -> bool:
    if who is None:
        return False
    move = c.world.get(who, Movement)
    return move is not None and mode in move.modes


def _revive_as_undead(c: Cast, label: str) -> None:
    """"Remains standing, gains the undead keyword, continues to fight
    until the end of its next turn." Stood up inside the `Dropped` window
    at 1 hit point, the shape `m5193a4` settled; guarded so the second,
    genuine `Dropped` finds nothing left to do."""
    me = c.me
    if any(e.label == label for e in c.world.effects.of(me)):
        return
    c.effect(label, until=When.ENCOUNTER, on=me)

    def rise(ev: Dropped) -> None:
        if ev.actor == me:
            c.reanimate(on=me, hp=1)
            c.set_origin("undead", on=me, until=When.EONT)

    c.watch(Dropped, rise, until=When.ENCOUNTER, on=me, label=f"{label} rise")


def _swarm_traits(c: Cast) -> None:
    """"Can occupy the same space as another creature... cannot be
    pulled, pushed, or slid by melee or ranged attacks... can squeeze
    through any opening" -- the shared swarm chassis, written once rather
    than twice since `m115889` and `m6079` print it verbatim."""
    from combat_engine.content.monsters.level_08.brutes import _squeezes_freely

    c.shares_space(on=c.me, until=When.ENCOUNTER, difficult=True)

    def melee_or_ranged(ctx: dict[str, Any]) -> bool:
        row = get(ctx.get("power", "") or "")
        return row is not None and row.reach.kind in ("melee", "ranged")

    c.resist_forced(999, on=c.me, until=When.ENCOUNTER, when=melee_or_ranged)
    _squeezes_freely(c)


def _swarm_burn_aura(c: Cast, radius: int, amount: int) -> None:
    """"Takes ongoing damage (save ends); if already taking untyped
    ongoing damage, that damage increases" -- the aura toll that stacks
    onto a standing burn instead of opening a second one."""
    me = c.me
    ring = c.aura(radius, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def toll(who: int) -> None:
        if who == me or team(c.world, who) is team(c.world, me):
            return
        existing = next(
            (
                e for e in c.world.effects.of(who)
                if e.ongoing and e.ongoing[1] is DamageType.UNTYPED
            ),
            None,
        )
        if existing is not None:
            amt, dtype = existing.ongoing
            existing.ongoing = (amt + amount, dtype)
        else:
            c.ongoing(amount, on=who)

    def entered(ev: Any) -> None:
        if ev.zone == ring:
            toll(ev.actor)

    def start(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(ring):
            toll(ev.actor)

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} enter")
    c.watch(TurnStart, start, until=When.ENCOUNTER, on=me, label=f"{c.ref} start")


# ==========================================================================
# m115806
# ==========================================================================

_M115806_HEADS: dict[int, int] = {}
_M115806_PENDING: dict[int, bool] = {}
_M115806_SHIELDED: dict[int, bool] = {}


@power(
    "m115806a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115806a0(c: Cast) -> None:
    c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)


@power(
    "m115806a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("actions.legal(free_despite_stun=)",),
)
def m115806a1(c: Cast) -> None:
    """"While stunned or dominated, can take free actions" has no hook --
    those conditions block every action through the same gate a free
    action also has to pass, and nothing in `actions.legal` carves out an
    exception for one word of condition."""


@power(
    "m115806a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115806a2(c: Cast) -> None:
    me = c.me
    _M115806_HEADS[me] = 4
    _M115806_PENDING[me] = False
    _M115806_SHIELDED[me] = False
    from combat_engine.engine import Health

    stats = c.world.get(me, Health)
    thresholds = (
        [stats.max_hp * 3 // 4, stats.max_hp // 2, stats.max_hp // 4] if stats is not None else []
    )
    crossed: set[int] = set()

    def lost_head(ev: DamageApplied) -> None:
        if ev.target != me:
            return
        hp_now = c.world.get(me, Health)
        if hp_now is None:
            return
        for i, bound in enumerate(thresholds):
            if i not in crossed and hp_now.hp < bound:
                crossed.add(i)
                _M115806_HEADS[me] = max(1, _M115806_HEADS.get(me, 4) - 1)
                _M115806_PENDING[me] = True
                _M115806_SHIELDED[me] = False
        if DamageType.FIRE in ev.types() or DamageType.ACID in ev.types():
            _M115806_SHIELDED[me] = True

    def regrow(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        if _M115806_PENDING.get(me) and not _M115806_SHIELDED.get(me):
            _M115806_HEADS[me] = min(4, _M115806_HEADS.get(me, 4) + 2)
        _M115806_PENDING[me] = False
        _M115806_SHIELDED[me] = False

    c.watch(DamageApplied, lost_head, until=When.ENCOUNTER, on=me, label=f"{c.ref} heads")
    c.watch(TurnStart, regrow, until=When.ENCOUNTER, on=me, label=f"{c.ref} regrow")


@power(
    "m115806a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115806a3(c: Cast) -> None:
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


@power(
    "m115806a4",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d10", 0),
)
def m115806a4(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115806a5",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    # The reach of the row it repeats: m115806a4 is melee 2. A personal reach
    # found nobody, so this never ran at all (#427).
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m115806a5(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    heads = _M115806_HEADS.get(c.me, 4)
    bonus = 15 if heads == 1 else 5 if heads == 2 else 0
    for _ in range(max(heads, 1)):
        c.use_power("m115806a4", on=victim)
        if c.landed and bonus:
            c.flat(bonus, on=victim)


_M115806_NEARBY_END = "an enemy ends its turn within 2 squares of it"


def _enemy_ends_within_2(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "actor", None)
    if who is None or ev.ghost or team(world, who) is team(world, me):
        return False
    return distance_between(world, me, who) <= 2


@power(
    "m115806a6",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M115806_NEARBY_END,
    on=Trigger(TurnEnd, _enemy_ends_within_2, _M115806_NEARBY_END),
)
def m115806a6(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.use_power("m115806a4", on=foe)
        c.use_power("m115806a4", on=foe)


# ==========================================================================
# m115842
# ==========================================================================


@power(
    "m115842a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("", 11, kind=MINION),
)
def m115842a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if not c.grabbing():
            c.grab()


_M115842_DOWN = "a non-fire attack reduces it to 0 hit points"


@power(
    "m115842a1",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=Ranged(10),
    target=NO_TARGET,
    trigger=_M115842_DOWN,
    on=Trigger(Dropped, about_me, _M115842_DOWN),
    attack=Attack(vs=WILL, printed=13),
)
def m115842a1(c: Cast) -> None:
    killer = c.trigger.source if c.trigger is not None else None
    if killer is None or c.is_kind("fire", on=killer):
        return
    last = next(
        (e for e in reversed(c.world.bus.log) if isinstance(e, DamageApplied) and e.target == c.me),
        None,
    )
    if last is not None and DamageType.FIRE in last.types():
        return
    if c.strike(on=killer):
        c.half_healing(on=killer, until=When.SAVE_ENDS)


# ==========================================================================
# m115848
# ==========================================================================


@power(
    "m115848a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("4d8", 5),
)
def m115848a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115848a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 7),
)
def m115848a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115848a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=13),
)
def m115848a2(c: Cast) -> None:
    """The push, the shift alongside it and the per-square damage all
    play as one combined shove rather than a square at a time -- `c.push`
    already reports how far it actually got."""
    victim = c.target
    if victim is None or not c.strike():
        return
    total = 1 + c.speed_of()
    moved = c.push(total, on=victim)
    c.prone(on=victim)
    extra = max(0, moved - 1)
    if extra:
        c.flat(c.roll(f"{extra}d8"), on=victim)
    if moved:
        c.shift(moved)


# ==========================================================================
# m115889
# ==========================================================================


@power(
    "m115889a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115889a0(c: Cast) -> None:
    _swarm_burn_aura(c, 1, 5)


@power(
    "m115889a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115889a1(c: Cast) -> None:
    _swarm_traits(c)


@power(
    "m115889a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 1),
)
def m115889a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


_M115889_FLED = "an enemy moves away from it"


def _enemy_fled(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "actor", None)
    if who is None or team(world, who) is team(world, me):
        return False
    before = getattr(ev, "from_", None)
    if before is None:
        return False
    from combat_engine.engine import distance as _d
    from combat_engine.engine.query import squares as _sq

    mine = _sq(world, me)
    was = min((_d(before, s) for s in mine), default=99)
    now = distance_between(world, me, who)
    return now > was


@power(
    "m115889a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    no_provoke=True,
    trigger=_M115889_FLED,
    on=Trigger(Moved, _enemy_fled, _M115889_FLED),
)
def m115889a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    dest = _adjacent_empty_square(c, foe)
    c.shift(c.speed_of(), to=dest)


# ==========================================================================
# m2069
# ==========================================================================


@power(
    "m2069a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d6", 7),
)
def m2069a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M2069_FLANKED = "an enemy moves into a position that flanks it"


def _flanked_just_now(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "actor", None)
    if who is None or team(world, who) is team(world, me):
        return False
    return flanked_by(world, me, who)


@power(
    "m2069a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=11),
    trigger=_M2069_FLANKED,
    on=Trigger(Moved, _flanked_just_now, _M2069_FLANKED),
)
def m2069a1(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.prone(on=foe)


@power(
    "m2069a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.second_initiative()",),
)
def m2069a2(c: Cast) -> None:
    """"Rolls initiative twice, gets two turns a round" wants a second,
    independent roll -- `c.extra_turn` only ever takes a count handed to
    it. The immediate-action refresh each turn has nowhere further to
    attach once that gap is open."""


@power(
    "m2069a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("Effect.keywords",),
)
def m2069a3(c: Cast) -> None:
    """Dazed and stunned both play -- named conditions, read straight off
    the standing effect. "Charm effects that a save can end" has nowhere
    to ask from here: an `Effect` carries conditions and a damage type,
    never the keywords of the row that laid it, so "a charm effect" as
    opposed to any other save-ends hold cannot be told apart."""
    me = c.me

    def auto_save(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me:
            return
        for eff in list(c.world.effects.of(me)):
            if eff.when is When.SAVE_ENDS and (
                Condition.DAZED in eff.conditions or Condition.STUNNED in eff.conditions
            ):
                c.world.effects.end(eff, "automatic save")

    c.watch(TurnEnd, auto_save, until=When.ENCOUNTER, on=me, label=f"{c.ref} auto-save")


@power(
    "m2069a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m2069a4(c: Cast) -> None:
    _revives_once(c, 10, DamageType.ACID, DamageType.FIRE, delayed=True)


# ==========================================================================
# m2071
# ==========================================================================


@power(
    "m2071a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d6", 5),
)
def m2071a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2071a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d6", 5),
)
def m2071a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m2071a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2071a2(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: c.is_(Condition.PRONE, on=ctx.get("target")),
    )


@power(
    "m2071a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.speed_of(while_charging=)",),
)
def m2071a3(c: Cast) -> None:
    """"Can make a1 against any creature in its [reach]" asks nothing
    `a1` does not already offer -- it is at-will and carries no recharge
    for this to bypass. The speed bump while charging with it has no
    hook: nothing scopes a speed bonus to the one action a charge is."""


# ==========================================================================
# m2081
# ==========================================================================


@power(
    "m2081a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 5),
)
def m2081a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m2081a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 5),
)
def m2081a1(c: Cast) -> None:
    victim = c.target
    if victim is not None and not c.is_(Condition.IMMOBILIZED, on=victim):
        for foe in c.enemies():
            if foe != victim and c.adjacent(foe):
                c.provoke(foe, on=c.me)
    if c.strike():
        c.hit()
        c.heal(10, on=c.me)


_M2081_MISSED = "it is missed by a melee attack from an adjacent attacker"


@power(
    "m2081a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2081_MISSED,
    on=Trigger(Hit, lambda w, m, ev: (
        getattr(ev, "target", None) == m
        and not getattr(ev, "hit", True)
        and getattr(ev, "attacker", None) is not None
        and distance_between(w, m, ev.attacker) <= 1
    ), _M2081_MISSED),
)
def m2081a2(c: Cast) -> None:
    from combat_engine.content.monsters.level_01.artillery_sa import _recharge_when_bloodied

    _recharge_when_bloodied(c)
    foe = _triggering_enemy(c)
    if foe is None:
        return
    c.no_provoke(on=c.me, until=When.EOT)
    c.use_power("m2081a1", on=foe)


# ==========================================================================
# m2086
# ==========================================================================


@power(
    "m2086a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 4),
)
def m2086a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m2086a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2086a1(c: Cast) -> None:
    me = c.me
    c.bonus(
        "attack", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: (t := ctx.get("target")) is not None and flanked_by(c.world, t, me),
    )


# ==========================================================================
# m2326
# ==========================================================================


@power(
    "m2326a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 4),
)
def m2326a0(c: Cast) -> None:
    victim = c.target
    hits = 0
    for _ in range(2):
        if c.strike(on=victim):
            c.hit(on=victim)
            hits += 1
    if hits == 2:
        c.push(2, on=victim)


@power(
    "m2326a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 5),
)
def m2326a1(c: Cast) -> None:
    """A second head's own pair of swings -- no defence word printed, read
    as the common default (`AC`)."""
    victim = c.target
    for _ in range(2):
        if c.strike(on=victim):
            c.hit(on=victim)


@power(
    "m2326a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger="an adjacent enemy shifts",
    on=Trigger(MoveStart, lambda w, m, ev: (
        getattr(ev, "kind_", "") == "shift"
        and getattr(ev, "actor", None) is not None
        and team(w, ev.actor) is not team(w, m)
        and distance_between(w, m, ev.actor) <= 1
    ), "an adjacent enemy shifts"),
)
def m2326a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.basic(on=foe)


# ==========================================================================
# m2331
# ==========================================================================


@power(
    "m2331a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 4),
)
def m2331a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


_M2331_BLOODIED = "it is first bloodied"


@power(
    "m2331a1",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2331_BLOODIED,
    on=Trigger(Bloodied, about_me, _M2331_BLOODIED),
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d6", 4),
)
def m2331a1(c: Cast) -> None:
    """"Moves 5 squares away from the creature that bloodied it" --
    `c.flee` always runs its target away from the *caster*, which is the
    wrong direction for a row where the caster is the one running. The
    farthest-reachable-square search `c.flee` does internally is repeated
    here against the bloodier instead. Who is attacked along the way is
    approximated by whoever stands within one square of the line the
    flight actually takes, rather than tracked square by square."""
    me = c.me
    bloodier = getattr(c.trigger, "source", None) or getattr(c.trigger, "actor", None)
    start = c.here
    paths = c.world.reachable_paths(me, 5)
    if paths:
        from combat_engine.engine import distance as _d
        from combat_engine.engine.movement import walk
        from combat_engine.engine.query import squares as _sq

        anchor = start
        if bloodier is not None:
            theirs = _sq(c.world, bloodier)
            if theirs:
                anchor = next(iter(theirs))
        away = max(sorted(paths), key=lambda sq: _d(sq, anchor))
        walk(c.world, me, paths[away])
    path = c.line(start, c.here)
    for foe in c.enemies():
        if any(_on_line(c, foe, sq) for sq in path) and c.strike(on=foe):
            c.hit(on=foe)
            c.push(2, on=foe)
            c.prone(on=foe)


def _on_line(c: Cast, who: int, sq: Square) -> bool:
    from combat_engine.engine import distance as _d
    from combat_engine.engine.query import squares as _sq

    return any(_d(sq, s) <= 1 for s in _sq(c.world, who))


@power(
    "m2331a2",
    level=10,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.summon(count=)",),
)
def m2331a2(c: Cast) -> None:
    """"Each square it formerly occupied now contains one m2332" splits
    one creature into several at once -- `c.summon` makes exactly one
    creature per call and names nowhere for the vacated footprint to
    go."""


# ==========================================================================
# m2596
# ==========================================================================


@power(
    "m2596a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 6),
)
def m2596a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m2596a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="slowed creatures only",
        conditions=frozenset({Condition.SLOWED}),
    ),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d10", 6),
)
def m2596a1(c: Cast) -> None:
    """"Slowed creatures only" is the target line, so an unslowed creature is
    never offered and the body has no re-pick left."""
    if c.strike():
        c.hit()


@power(
    "m2596a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d10", 6, kind=LIMITED),
)
def m2596a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)
        c.slowed(until=When.EONT)


# ==========================================================================
# m3752
# ==========================================================================


@power(
    "m3752a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 6),
)
def m3752a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3752a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 6),
)
def m3752a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m3752a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m3752a2(c: Cast) -> None:
    """Requirement: bloodied, asked in the body."""
    if not c.bloodied(c.me):
        return
    victim = c.target
    c.use_power("m3752a0", on=victim)
    c.use_power("m3752a0", on=victim)
    c.use_power("m3752a1", on=victim)


@power(
    "m3752a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 4, dtype=DamageType.POISON, kind=LIMITED),
)
def m3752a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(10, DamageType.POISON))


# ==========================================================================
# m3833
# ==========================================================================


@power(
    "m3833a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3833a0(c: Cast) -> None:
    me = c.me

    def bonus_dmg(ev: Hit) -> None:
        rider = c.rider()
        if rider is None or ev.attacker != rider or not getattr(ev, "charge", False):
            return
        if not _ridden_by_seventh_level(c.world, me):
            return
        c.flat(10, on=ev.target)

    c.watch(Hit, bonus_dmg, until=When.ENCOUNTER, on=me, label=f"{c.ref} rider")


@power(
    "m3833a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 8),
)
def m3833a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3833a2",
    level=10,
    usage=AT_WILL,
    action=MOVE,
    reach=Melee(0),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d10", 8),
)
def m3833a2(c: Cast) -> None:
    for foe in c.overrun():
        if c.strike(on=foe):
            c.hit(on=foe)
            c.prone(on=foe)


# ==========================================================================
# m3924
# ==========================================================================


@power(
    "m3924a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 6),
)
def m3924a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3924a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("3d8", 5, kind=LIMITED),
)
def m3924a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


# ==========================================================================
# m3984
# ==========================================================================


@power(
    "m3984a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d6", 5),
)
def m3984a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3984a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3984a1(c: Cast) -> None:
    me = c.me
    c.bonus(
        # Untyped: the card prints "+2 bonus to attack rolls", no type word.
        "attack", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )
    c.bonus(
        "damage", 0, dice="1d6", on=me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


# ==========================================================================
# m4014
# ==========================================================================


@power(
    "m4014a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d8", 5),
)
def m4014a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m4014a1",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(2),
    target=Target(side="enemy", count=1, label="immobilized by it"),
    attack=Attack(vs=FORT, printed=11),
    dropped=("Relation.IMMOBILIZED_BY", "c.sight_range(shared_only=)"),
)
def m4014a1(c: Cast) -> None:
    """The restrained hold and the recurring damage both play.

    The printed target is "a creature immobilized by it", which `Relation`
    has no member for -- the six it carries are the grab, the mark,
    domination, hiding, the curse and the quarry -- so `Target.relation`
    cannot say this one and the pick stays in the body. Filtering on the
    bare `Condition.IMMOBILIZED` would be wider than the card: it would
    accept a creature held by somebody else entirely.

    "Line of sight and line of effect only to the m4014, and no creature
    has it to the target" has no vision gate narrow enough to lay only
    between two named creatures -- `c.sight_range` shrinks a radius, not
    a line to one other creature."""
    victim = next((f for f in c.grabbing() if c.is_(Condition.IMMOBILIZED, on=f)), None)
    if victim is None or not c.strike(on=victim):
        return
    # No damage on the hit itself: the printed 3d8 + 5 lands at the start of
    # this creature's turn while the hold lasts, which is the `tick` below.
    # `c.hit()` raises without a damage line and was the wrong call here.
    c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=victim)
    me = c.me

    def tick(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == me:
            c.flat(c.roll("3d8") + 5, dtype=DamageType.NECROTIC, on=victim)

    c.watch(TurnStart, tick, until=When.SAVE_ENDS, on=me, label=f"{c.ref} {victim}")


@power(
    "m4014a2",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(2),
    target=Target(
        side="enemy", count=1,
        label="one creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d8", 5),
)
def m4014a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


# ==========================================================================
# m4250
# ==========================================================================


@power(
    "m4250a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 6, dtype=DamageType.RADIANT),
)
def m4250a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4250a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("3d8", 6, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m4250a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m4250a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d10", 6, kind=LIMITED),
)
def m4250a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.RADIANT)


def _hit_me_or_adjacent_ally_melee(world: World, me: int, ev: Any) -> bool:
    target = getattr(ev, "target", None)
    attacker = getattr(ev, "attacker", None)
    if target is None or attacker is None:
        return False
    row = get(getattr(ev, "power", "") or "")
    if row is None or row.reach.kind != "melee":
        return False
    if target == me:
        return True
    return team(world, target) is team(world, me) and distance_between(world, me, target) <= 1


_M4250_ALLY_HIT = "it or an adjacent ally is hit by a melee attack"


@power(
    "m4250a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M4250_ALLY_HIT,
    on=Trigger(Hit, _hit_me_or_adjacent_ally_melee, _M4250_ALLY_HIT),
)
def m4250a3(c: Cast) -> None:
    from combat_engine.content.monsters.level_01.artillery_sa import _recharge_when_bloodied

    _recharge_when_bloodied(c)
    foe = _triggering_enemy(c)
    if foe is not None:
        c.basic(on=foe)


# ==========================================================================
# m4392
# ==========================================================================


@power(
    "m4392a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
)
def m4392a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(c.roll("1d8") + 3, dtype=DamageType.ACID)


@power(
    "m4392a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5, kind=LIMITED),
)
def m4392a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


_M4392_BLOODIED = "it is first bloodied"


@power(
    "m4392a2",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    trigger=_M4392_BLOODIED,
    on=Trigger(Bloodied, about_me, _M4392_BLOODIED),
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d8", 5, dtype=DamageType.ACID, kind=LIMITED),
)
def m4392a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty(AC, 4, until=When.SAVE_ENDS)


# ==========================================================================
# m4448
# ==========================================================================


@power(
    "m4448a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("4d6", 5, half_on_miss=True),
)
def m4448a0(c: Cast) -> None:
    res = c.strike()
    if res:
        if res.critical:
            c.flat(c.roll("2d6") + 29)
        else:
            c.hit()
        c.prone()
    else:
        c.hit(half=True)


@power(
    "m4448a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 2, half_on_miss=True),
)
def m4448a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
    else:
        c.hit(half=True)


@power(
    "m4448a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("4d6", 5, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m4448a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m4448a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE, half_on_miss=True),
)
def m4448a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m4448a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.second_initiative()",),
)
def m4448a4(c: Cast) -> None:
    """"Rolls initiative once for each opponent it faces" is an
    open-ended number of independent rolls -- the same gap `c.extra_turn`
    cannot close for a fixed second slot, only wider."""


@power(
    "m4448a5",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.immune(all=)", "Effect.when(retime=)"),
)
def m4448a5(c: Cast) -> None:
    """Ignoring damage and forced movement both play. "Does not suffer
    from any effect a save can end" has no blanket form -- `c.immune`
    only ever waives named conditions, never every save-ends hold at
    once. Retiming an end-of-turn effect to its own next turn has no
    hook either: nothing rewrites which creature's turn boundary an
    effect answers to after the fact."""
    me = c.me
    c.resist(9999, None, until=When.ENCOUNTER, on=me)
    c.immovable(until=When.ENCOUNTER, on=me)


@power(
    "m4448a6",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("query.zones_near()",),
)
def m4448a6(c: Cast) -> None:
    """Destroying an adjacent conjuration plays. A plain terrain zone has
    no "near me" query the way a conjuration does -- `c.conjurations`
    exists for the first half and nothing mirrors it for the second."""
    me = c.me

    def check(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me:
            return
        for cid in c.conjurations(within=1, side="any"):
            c.dispel(cid)

    c.watch(TurnEnd, check, until=When.ENCOUNTER, on=me, label=f"{c.ref} destroy")


# ==========================================================================
# m4663
# ==========================================================================


@power(
    "m4663a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("", 8, dtype=DamageType.FORCE, kind=MINION),
)
def m4663a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4663a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("", 8, dtype=DamageType.FORCE, kind=MINION),
)
def m4663a1(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    me = c.me
    from combat_engine.engine.query import squares as _squares

    dest = next(iter(_squares(c.world, victim)), None)
    c.teleport(1, to=dest, share=True)
    c.ongoing(5, DamageType.FORCE, until=When.ENCOUNTER)

    def shared(ev: Hit) -> None:
        if ev.target == me and ev.attacker != victim:
            c.also_hits(on=victim, ev=ev)

    c.watch(Hit, shared, until=When.ENCOUNTER, on=me, label=f"{c.ref} {victim}")


# ==========================================================================
# m5185
# ==========================================================================


@power(
    "m5185a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 6, dtype=DamageType.FIRE, kind=MINION),
)
def m5185a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m5185a1",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("", 6, dtype=DamageType.FIRE, kind=MINION),
)
def m5185a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


# ==========================================================================
# m5190
# ==========================================================================


@power(
    "m5190a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m5190a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def toll(who: int) -> None:
        if who != me and team(c.world, who) is not team(c.world, me):
            c.flat(8, dtype=DamageType.POISON, on=who)

    def entered(ev: Any) -> None:
        if ev.zone == ring:
            toll(ev.actor)

    def start(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(ring):
            toll(ev.actor)

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} enter")
    c.watch(TurnStart, start, until=When.ENCOUNTER, on=me, label=f"{c.ref} start")


@power(
    "m5190a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d10", 5, dtype=DamageType.POISON),
)
def m5190a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


# ==========================================================================
# m5211
# ==========================================================================


@power(
    "m5211a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("4d6", 8),
)
def m5211a0(c: Cast) -> None:
    c.bonus(
        "damage", 5, on=c.me, until=When.ENCOUNTER, when=lambda _ctx: c.bloodied(on=c.me),
    )
    if c.strike():
        c.hit()


@power(
    "m5211a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    damage=Damage("4d6", 8, kind=LIMITED),
    attack=Attack(vs=AC, printed=13),
)
def m5211a1(c: Cast) -> None:
    c.bonus(
        "damage", 5, on=c.me, until=When.ENCOUNTER, when=lambda _ctx: c.bloodied(on=c.me),
    )
    if c.strike():
        c.hit()
        c.prone()


_M5211_DOWN = "it drops to 0 hit points and is killed"


@power(
    "m5211a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5211_DOWN,
    on=Trigger(Dropped, about_me, _M5211_DOWN),
)
def m5211a2(c: Cast) -> None:
    _revive_as_undead(c, "m5211a2")


_M5211_LANDED = "it bloodies an enemy or reduces one to 0 hit points or fewer"


@power(
    "m5211a3",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5211_LANDED,
    on=(
        Trigger(Bloodied, by_me, _M5211_LANDED),
        Trigger(Dropped, by_me, _M5211_LANDED),
    ),
)
def m5211a3(c: Cast) -> None:
    c.temp_hp(c.roll("1d10") + 4, on=c.me)


_M5211_ALLY_HIT = "an enemy within 2 squares attacks an ally"


def _ally_attacked_within(world: World, me: int, ev: Any) -> bool:
    target = getattr(ev, "target", None)
    attacker = getattr(ev, "attacker", None)
    if target is None or attacker is None or target == me:
        return False
    if team(world, target) is not team(world, me) or team(world, attacker) is team(world, me):
        return False
    return distance_between(world, me, attacker) <= 2


@power(
    "m5211a4",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5211_ALLY_HIT,
    on=Trigger(AttackDeclared, _ally_attacked_within, _M5211_ALLY_HIT),
)
def m5211a4(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    c.restore_use("m5211a1", on=c.me)
    c.use_power("m5211a1", on=foe)


# ==========================================================================
# m5529
# ==========================================================================


@power(
    "m5529a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5529a0(c: Cast) -> None:
    me = c.me

    def burrowing_vs_grounded(ctx: dict[str, Any]) -> bool:
        return c.moving_as("burrow", on=me) and not _has_mode(c, ctx.get("target"), "burrow")

    c.bonus("damage", 2, kind="power", on=me, until=When.ENCOUNTER, when=burrowing_vs_grounded)


@power(
    "m5529a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7),
)
def m5529a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5529a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 7),
)
def m5529a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.grab()
    me = c.me

    def ends(ev: Escaped) -> None:
        if ev.holder == me and ev.actor == victim:
            c.ongoing(5, on=victim)

    c.watch(Escaped, ends, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} {victim}")


@power(
    "m5529a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5529a3(c: Cast) -> None:
    victim = next(iter(c.grabbing()), None)
    if victim is not None:
        c.flat(c.roll("3d8") + 7, on=victim)


_M5529_NEAR_BLOODIED = "it starts its turn within 5 squares of a bloodied creature"


def _bloodied_creature_near_start(world: World, me: int, ev: Any) -> bool:
    """"Within 5 squares of a bloodied creature" names neither side, so
    this reads every creature on the board rather than only enemies."""
    if ev.ghost or ev.actor != me:
        return False
    from combat_engine.engine import Health
    from combat_engine.engine.query import creatures

    for k in creatures(world):
        if k == me or distance_between(world, me, k) > 5:
            continue
        hp = world.get(k, Health)
        if hp is not None and hp.hp * 2 <= hp.max_hp:
            return True
    return False


@power(
    "m5529a4",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5529_NEAR_BLOODIED,
    on=Trigger(TurnStart, _bloodied_creature_near_start, _M5529_NEAR_BLOODIED),
)
def m5529a4(c: Cast) -> None:
    me = c.me
    for who in list(c.grabbing()):
        for eff in list(c.world.effects.of(who)):
            if eff.owner == me and "grab" in eff.label:
                c.world.effects.end(eff, "the grab ends")
    foe = next((f for f in c.enemies() if c.adjacent(f)), None)
    if foe is not None:
        c.use_power("m5529a1", on=foe)


# ==========================================================================
# m5578
# ==========================================================================


def _m5578_grapple(c: Cast, victim: int) -> None:
    if not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.dazed(on=victim, until=When.SAVE_ENDS)
    c.temp_hp(10, on=c.me)


@power(
    "m5578a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d6", 5),
)
def m5578a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m5578a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="the target must be immobilized, stunned, or unconscious",
        conditions=frozenset({
            Condition.IMMOBILIZED, Condition.STUNNED, Condition.UNCONSCIOUS,
        }),
    ),
    attack=Attack(vs=AC, printed=13),
    damage=Damage("5d6", 5),
)
def m5578a1(c: Cast) -> None:
    """The printed Requirement is three alternative states, which is one
    `Target.conditions` set -- so it narrows the pool rather than gating the
    row, and the refusal is the pool being empty."""
    victim = c.target
    if victim is not None:
        _m5578_grapple(c, victim)


@power(
    "m5578a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("5d6", 5, kind=LIMITED),
)
def m5578a2(c: Cast) -> None:
    """"Against each enemy adjacent to her, even if the enemy is not
    immobilized, stunned, or unconscious" is `a1`'s own formula without
    `a1`'s own restriction, so the shared grapple payout is reused rather
    than `use_power`, which would reapply the Requirement this row means
    to waive."""
    if c.adjacent(c.target):
        _m5578_grapple(c, c.target)


@power(
    "m5578a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("3d8", 5),
)
def m5578a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(4)
        c.prone()
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m5596
# ==========================================================================

_M5596_WOLF = "m5596a7 beast"
_M5596_HYBRID = "m5596a7 hybrid"


def _m5596_form(c: Cast) -> str:
    labels = {e.label for e in c.world.effects.of(c.me)}
    if _M5596_WOLF in labels:
        return "wolf"
    if _M5596_HYBRID in labels:
        return "hybrid"
    return "human"


@power(
    "m5596a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5596a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(5, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def vs_bloodied(ctx: dict[str, Any]) -> bool:
        return c.bloodied(on=ctx.get("target"))

    c.grants_in(ring, "attack", 2, side="ally", kind="power", when=vs_bloodied)
    c.grants_in(ring, "damage", 5, side="ally", kind="power", when=vs_bloodied)


@power(
    "m5596a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.silvered()",),
)
def m5596a1(c: Cast) -> None:
    """5 a turn plays. Suspending it specifically after a silvered
    weapon's damage has no reader -- a weapon's material is not a fact
    the damage context carries, so there is nothing to ask what it was
    forged from."""
    me = c.me

    def tick(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == me:
            c.heal(5, on=me)

    c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} regen")


@power(
    "m5596a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 5),
)
def m5596a2(c: Cast) -> None:
    """Requirement: beast or hybrid form, asked in the body."""
    if _m5596_form(c) == "human":
        return
    victim = c.target
    plus = 2 if victim is not None and c.bloodied(on=victim) else 0
    extra = 5 if plus else 0
    if c.strike(plus=plus):
        c.damage("2d10", 5 + extra)
        c.prone()


@power(
    "m5596a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d12", 10),
    dropped=("c.condition(disease=)",),
)
def m5596a3(c: Cast) -> None:
    """Requirement: wolf or hybrid form, asked in the body. The blow
    lands; contracting a disease at the end of the encounter has nowhere
    to go -- there is no disease model in this engine at all, no stages
    and no progression to fail a save into."""
    if _m5596_form(c) == "human":
        return
    victim = c.target
    plus = 2 if victim is not None and c.bloodied(on=victim) else 0
    if c.strike(plus=plus):
        c.hit()


@power(
    "m5596a4",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 6),
)
def m5596a4(c: Cast) -> None:
    """Requirement: humanoid or hybrid form, asked in the body."""
    if _m5596_form(c) == "wolf":
        return
    victim = c.target
    plus = 2 if victim is not None and c.bloodied(on=victim) else 0
    extra = 5 if plus else 0
    if c.strike(plus=plus):
        c.damage("2d10", 6 + extra)


@power(
    "m5596a5",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5596a5(c: Cast) -> None:
    """Requirement: hybrid form, asked in the body."""
    if _m5596_form(c) != "hybrid":
        return
    foe = next(iter(c.enemies()), None)
    c.basic(on=foe)
    c.basic(on=foe)
    c.flat(5, on=c.me)


@power(
    "m5596a6",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5596a6(c: Cast) -> None:
    """Requirement: beast form, asked in the body."""
    if _m5596_form(c) != "wolf":
        return
    c.shift(6)
    foe = next(iter(c.enemies()), None)
    if foe is not None:
        c.use_power("m5596a2", on=foe)


@power(
    "m5596a7",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m5596a7(c: Cast) -> None:
    me = c.me
    was = _m5596_form(c)
    for label in (_M5596_WOLF, _M5596_HYBRID):
        existing = next((e for e in c.world.effects.of(me) if e.label == label), None)
        if existing is not None:
            c.world.effects.end(existing, "changes form")
    choice = c.choose(["human", "wolf", "hybrid"], f"{c.ref}: which form") or "wolf"
    if choice == "human":
        c.resize(Size.MEDIUM, on=me)
        return
    c.effect(_M5596_WOLF if choice == "wolf" else _M5596_HYBRID, until=When.ENCOUNTER, on=me)
    c.resize(Size.LARGE, on=me)
    if was == "human":
        for foe in c.enemies():
            if c.adjacent(foe):
                c.push(1, on=foe)


@power(
    "m5596a8",
    level=10,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=Target(side="ally", count=1, label="ally"),
)
def m5596a8(c: Cast) -> None:
    from combat_engine.engine import Powers

    mate = c.target
    if mate is None:
        return
    c.temp_hp(10, on=mate)
    known = c.world.get(mate, Powers)
    if known is not None and "m5596a2" in known.all:
        foe = next(iter(c.enemies()), None)
        if foe is not None:
            c.use_power("m5596a2", on=foe, who=mate, spend=False)


_M5596_HIT = "an adjacent enemy hits it with a melee weapon attack"


def _hit_by_adjacent_melee_weapon(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    attacker = getattr(ev, "attacker", None)
    if attacker is None or distance_between(world, me, attacker) > 1:
        return False
    row = get(getattr(ev, "power", "") or "")
    return row is not None and row.reach.kind == "melee" and Keyword.WEAPON in row.keywords


@power(
    "m5596a9",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M5596_HIT,
    on=Trigger(Hit, _hit_by_adjacent_melee_weapon, _M5596_HIT),
)
def m5596a9(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.basic(on=foe)


# ==========================================================================
# m5621
# ==========================================================================


def _ends_dazing_stunning_dominating(c: Cast) -> None:
    me = c.me

    def clear(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me:
            return
        for eff in list(c.world.effects.of(me)):
            if set(eff.conditions) & {Condition.DAZED, Condition.STUNNED, Condition.DOMINATED}:
                c.world.effects.end(eff, "ends its turn")

    c.watch(TurnEnd, clear, until=When.ENCOUNTER, on=me, label=f"{c.ref} clear")


def _extra_turn_or_instead(c: Cast) -> None:
    """A solo's second slot: `c.extra_turn` says what the printed free
    action gets translated to, and what happens in it is the policy's
    business -- `m492a2`'s own call. "If it cannot act for being stunned
    or dominated, that effect ends instead" is the one half this row can
    still say for itself."""
    me = c.me
    init = c.world.get(me, Initiative)
    if init is not None:
        c.extra_turn(at=init.rolled + 10)

    def instead(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        for eff in list(c.world.effects.of(me)):
            if set(eff.conditions) & {Condition.STUNNED, Condition.DOMINATED}:
                c.world.effects.end(eff, f"{c.ref}")

    c.watch(TurnStart, instead, until=When.ENCOUNTER, on=me, label=f"{c.ref} instead")


@power(
    "m5621a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5621a0(c: Cast) -> None:
    _ends_dazing_stunning_dominating(c)


@power(
    "m5621a1",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5621a1(c: Cast) -> None:
    _extra_turn_or_instead(c)


@power(
    "m5621a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5621a2(c: Cast) -> None:
    c.bonus(
        "crit_range", 3, on=c.me, until=When.ENCOUNTER, when=lambda _ctx: c.bloodied(on=c.me),
    )


@power(
    "m5621a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d10", 6, dtype=DamageType.COLD, half_on_miss=True),
)
def m5621a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m5621a4",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d8", 9),
)
def m5621a4(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5621a5",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d10", 9, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
)
def m5621a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.slowed(until=When.EONT)


_M5621_FLANK_HIT = "an enemy flanking it hits it"


def _flanking_enemy_hits(world: World, me: int, ev: Any) -> bool:
    attacker = getattr(ev, "attacker", None)
    if getattr(ev, "target", None) != me or attacker is None:
        return False
    return flanked_by(world, me, attacker)


@power(
    "m5621a6",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(2),
    target=NO_TARGET,
    trigger=_M5621_FLANK_HIT,
    on=Trigger(Hit, _flanking_enemy_hits, _M5621_FLANK_HIT),
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("3d6", 8),
)
def m5621a6(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.push(5, on=foe)


_M5621_BLOODIED = "it is first bloodied"


@power(
    "m5621a7",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5621_BLOODIED,
    on=Trigger(Bloodied, about_me, _M5621_BLOODIED),
)
def m5621a7(c: Cast) -> None:
    c.restore_use("m5621a5", on=c.me)
    c.use_power("m5621a5", spend=False)


_M5621_HIT_NEARBY = "an enemy within 5 squares hits it with an attack"


def _hit_me_from_nearby(world: World, me: int, ev: Any) -> bool:
    attacker = getattr(ev, "attacker", None)
    if getattr(ev, "target", None) != me or attacker is None:
        return False
    return distance_between(world, me, attacker) <= 5


@power(
    "m5621a8",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.COLD],
    trigger=_M5621_HIT_NEARBY,
    on=Trigger(Hit, _hit_me_from_nearby, _M5621_HIT_NEARBY),
)
def m5621a8(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.flat(10, dtype=DamageType.COLD, on=foe)
        c.push(2, on=foe)


# ==========================================================================
# m5997
# ==========================================================================


@power(
    "m5997a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5997a0(c: Cast) -> None:
    me = c.me
    c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    c.gains_advantage(
        on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.in_my_aura(ctx.get("target"), label=f"{c.ref} aura"),
    )


@power(
    "m5997a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5997a1(c: Cast) -> None:
    me = c.me

    def burned(ev: DamageApplied) -> None:
        if ev.target == me and DamageType.FIRE in ev.types():
            c.ongoing(5, DamageType.FIRE, on=me)

    c.watch(DamageApplied, burned, until=When.ENCOUNTER, on=me, label=f"{c.ref} catches")


@power(
    "m5997a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5997a2(c: Cast) -> None:
    """Both halves swap a condition for a milder one, and neither can do it
    by rewriting the effect.

    **The stun half used to, and was inert.** It rewrote
    `eff.conditions`, which `Effects.apply` reads *once* -- to count the
    condition into `Conditions` -- and `Effects.end` reads again to count
    it back out. Nothing re-reads it in between. So after a stun landed,
    this left the creature stunned (the count was already incremented) and
    not dazed (nothing ever incremented that), and at the end of the hold
    the stun would never have been counted out either. Driven: stunned=1,
    dazed=0, against a card that says dazed instead.

    The timing is the whole of it, and `p4913` is the row that gets it
    right: it declares on `EffectApplied`, which is emitted a few lines
    *before* the conditions are handed over, so there the rewrite is the
    correct lever. This row answers `ConditionApplied`, which is emitted
    from inside that handover and therefore always too late.

    So both halves now go through the component. Dominated arrives through
    `Relation.DOMINATED_BY` and was already done this way -- the stun half
    simply joins it.
    """
    me = c.me

    def swap_stun(ev: ConditionApplied) -> None:
        if ev.target != me or ev.condition is not Condition.STUNNED:
            return
        c.cure(Condition.STUNNED, on=me)
        c.dazed(on=me, until=When.SAVE_ENDS)

    def swap_dominate(ev: Any) -> None:
        if ev.kind_ is not Relation.DOMINATED_BY or ev.target != me:
            return
        c.world.relations.clear(Relation.DOMINATED_BY, ev.source, me, "m5997a2")
        c.dazed(on=me, until=When.SAVE_ENDS)

    from combat_engine.engine.events import RelationSet

    c.watch(ConditionApplied, swap_stun, until=When.ENCOUNTER, on=me, label=f"{c.ref} stun")
    c.watch(RelationSet, swap_dominate, until=When.ENCOUNTER, on=me, label=f"{c.ref} dominate")


@power(
    "m5997a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d8", 9, dtype=DamageType.NECROTIC),
)
def m5997a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.no_healing(on=c.target, until=When.EONT)


@power(
    "m5997a4",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 4, dtype=DamageType.NECROTIC),
)
def m5997a4(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.grab()
    c.ongoing(5, DamageType.NECROTIC, until=When.ENCOUNTER)
    me = c.me

    def ends(ev: Escaped) -> None:
        if ev.holder == me and ev.actor == victim:
            for eff in c.world.effects.of(victim):
                if eff.ongoing and eff.ongoing[1] is DamageType.NECROTIC:
                    c.world.effects.end(eff, "the grab ends")

    c.watch(Escaped, ends, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} {victim}")


@power(
    "m5997a5",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5997a5(c: Cast) -> None:
    victim = c.target
    choice = c.choose(["once", "twice"], f"{c.ref}: how many bites") or "once"
    c.use_power("m5997a3", on=victim)
    if choice == "twice":
        c.use_power("m5997a3", on=victim)
    other = next((f for f in c.enemies() if f != victim), None)
    if other is not None:
        c.use_power("m5997a4", on=other)


@power(
    "m5997a6",
    level=10,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m5997a6(c: Cast) -> None:
    c.shift(c.speed_of())
    c.resist(10, None, until=When.EOT, on=c.me, when=lambda ctx: bool(ctx.get("opportunity")))


@power(
    "m5997a7",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5997a7(c: Cast) -> None:
    victim = next(iter(c.grabbing()), None)
    if victim is None:
        return
    c.push(4, on=victim)
    c.flat(c.roll("1d10") + 5, on=victim)
    c.prone(on=victim)
    for eff in list(c.world.effects.of(c.me)):
        if "grab" in eff.label and str(victim) in eff.label:
            c.world.effects.end(eff, "released")


# ==========================================================================
# m6079
# ==========================================================================


@power(
    "m6079a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6079a0(c: Cast) -> None:
    _swarm_burn_aura(c, 1, 5)


@power(
    "m6079a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6079a1(c: Cast) -> None:
    _swarm_traits(c)


@power(
    "m6079a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 1),
)
def m6079a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m6079a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    no_provoke=True,
    trigger=_M115889_FLED,
    on=Trigger(Moved, _enemy_fled, _M115889_FLED),
)
def m6079a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    dest = _adjacent_empty_square(c, foe)
    c.shift(c.speed_of(), to=dest)


# ==========================================================================
# m6117
# ==========================================================================

_M6117_ELEMENT: dict[int, DamageType] = {}


@power(
    "m6117a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6117a0(c: Cast) -> None:
    _ends_dazing_stunning_dominating(c)


@power(
    "m6117a1",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6117a1(c: Cast) -> None:
    _extra_turn_or_instead(c)


@power(
    "m6117a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6117a2(c: Cast) -> None:
    me = c.me

    def roll_type(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        n = c.roll("1d6")
        _M6117_ELEMENT[me] = (
            DamageType.FIRE if n <= 2 else DamageType.ACID if n == 3
            else DamageType.COLD if n <= 5 else DamageType.LIGHTNING
        )

    c.watch(TurnStart, roll_type, until=When.ENCOUNTER, on=me, label=f"{c.ref} element")


@power(
    "m6117a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.ACID, Keyword.COLD, Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d12", 6),
)
def m6117a3(c: Cast) -> None:
    victim = c.target
    element = _M6117_ELEMENT.get(c.me, DamageType.FIRE)
    if c.strike():
        c.damage("2d12", 6, dtype=element)
        c.grab()
        amount = 10 if victim is not None and c.bloodied(on=victim) else 5
        c.ongoing(amount, element, until=When.ENCOUNTER)


@power(
    "m6117a4",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 11),
)
def m6117a4(c: Cast) -> None:
    """"If she targets only one creature, she can make this attack twice
    against that creature" -- caught with `c.first`, since the body
    already runs once per chosen target and a single target would
    otherwise only ever see one swing."""
    if len(c.targets) == 1:
        if not c.first:
            return
        victim = c.targets[0]
        for _ in range(2):
            if c.strike(on=victim):
                c.hit(on=victim)
                c.prone(on=victim)
        return
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6117a5",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE, Keyword.ACID, Keyword.COLD, Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d12", 10, kind=LIMITED, half_on_miss=True),
)
def m6117a5(c: Cast) -> None:
    element = _M6117_ELEMENT.get(c.me, DamageType.FIRE)
    amount = 18 if c.bloodied(c.me) else 10
    if c.strike():
        c.damage("2d12", amount, dtype=element)
    else:
        c.half_damage("2d12", amount, dtype=element)


@power(
    "m6117a6",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    trigger="a melee attack damages it",
    on=Trigger(DamageApplied, lambda w, m, ev: (
        ev.target == m
        and (row := get(getattr(ev, "power", "") or "")) is not None
        and row.reach.kind == "melee"
    ), "a melee attack damages it"),
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d10", 6),
)
def m6117a6(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


_M6117_BLOODIED = "it is first bloodied"


@power(
    "m6117a7",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE, Keyword.ACID, Keyword.COLD, Keyword.LIGHTNING],
    trigger=_M6117_BLOODIED,
    on=Trigger(Bloodied, about_me, _M6117_BLOODIED),
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d12", 18, kind=LIMITED, half_on_miss=True),
)
def m6117a7(c: Cast) -> None:
    element = _M6117_ELEMENT.get(c.me, DamageType.FIRE)
    if c.strike():
        c.damage("2d12", 18, dtype=element)
        c.push(2)
    else:
        c.half_damage("2d12", 18, dtype=element)


# ==========================================================================
# m6151
# ==========================================================================


@power(
    "m6151a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 11, kind=MINION),
)
def m6151a0(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    bonus = 2 if victim is not None and has_combat_advantage(c.world, c.me, victim) else 0
    c.flat(11 + bonus)


# ==========================================================================
# m6177
# ==========================================================================


@power(
    "m6177a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 11, kind=MINION),
)
def m6177a0(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    allies_adjacent = 0
    if victim is not None:
        allies_adjacent = sum(1 for a in c.allies() if c.adjacent_to(victim, a))
    c.flat(11 + allies_adjacent)


# ==========================================================================
# m6284
# ==========================================================================


@power(
    "m6284a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6284a0(c: Cast) -> None:
    me = c.me
    c.aura(3, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def granted(ev: Dropped) -> None:
        if team(c.world, ev.actor) is not team(c.world, me):
            return
        if not c.in_my_aura(ev.actor, label=f"{c.ref} aura"):
            return
        foe = next(iter(c.enemies()), None)
        if foe is not None:
            c.basic(who=ev.actor, on=foe)

    c.watch(Dropped, granted, until=When.ENCOUNTER, on=me, label=f"{c.ref} rally")


@power(
    "m6284a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 10),
)
def m6284a1(c: Cast) -> None:
    res = c.strike()
    if res:
        if res.critical:
            c.flat(c.roll("1d8") + 26)
        else:
            c.hit()


@power(
    "m6284a2",
    level=10,
    once_per_round=True,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="one enemy it is flanking",
        flanked=True,
    ),
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 0),
)
def m6284a2(c: Cast) -> None:
    if c.strike():
        c.hit()


_M6284_DAMAGES = "its attack damages an enemy"


@power(
    "m6284a3",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6284_DAMAGES,
    on=Trigger(DamageApplied, by_me, _M6284_DAMAGES),
)
def m6284a3(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.flat(c.roll("1d10"), on=victim)
