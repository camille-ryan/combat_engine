"""Monster abilities, level 9, skirmishers -- the second wave.

`skirmishers.py` holds the earlier sweep of this level and is not touched
here. 170 rows across thirty-three stat blocks; every block in this slot
that has no abilities listed here was already finished there.

Conventions, inherited from the eight levels below and from this level's own
`skirmishers.py`:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=14)`) and the damage line goes in the
  header as data;
* a **trait** costs no action, has no target, and arms whatever holds it,
  whatever action the compendium's column claims;
* a card with no printed range is melee 1, even where the surrounding
  sentences plainly mean a thrown or loosed weapon -- `m1809a1` is that
  card, and the convention is followed over the guess;
* a printed range band like "6/12" takes the short number;
* a weapon Requirement ("requires net", "requires hand crossbow") is not
  asked -- a monster carries no `Gear`;
* `c.damage` already maximises its dice on a crit, so a printed "(crit
  1d6+17)" that is just the maximised total needs no body code;
* a card printing two damage types rolled once keeps the first in the
  header and carries the rest as a keyword (`dropped=("Damage(dtypes=)",)`);
* a card asking something of the target that is not its side or size goes on
  the target line where `Target` has a field for it -- `relation=` for a
  position held against the attacker, `conditions=` for a state, `bloodied=`
  for the wound -- and those rows need no `_restricted_to`, no `requires=`
  and no marker. What has no field is still read in the body, and the
  redirect carries the symbol naming what is asked: `Target.ongoing` for a
  creature taking ongoing damage of a named type, `Target.creature_kind` for
  a type word, `Target.any_of` where the card prints two alternatives and
  every field narrows. They are separate gaps and not one.

Nine helpers are imported rather than written again, from six levels below
and from this level's own `skirmishers.py`. Ten more are written here
because this batch is the first to need them: a shared "extra damage
against an enemy flanked by two of its own allies" clause that three stat
blocks print word for word, a reroll that answers an attack roll, a saving
throw or a skill check depending on which one actually came up, a
once-per-encounter memory of where and by whom a creature was first
bloodied, a step away from whoever triggered a fear effect (anchored on the
attacker rather than on the caster, which `c.flee` cannot say), and a "pay
hit points to shrug off a condition at the start of your turn" clause two
blocks print with different conditions and the same cost.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES
from combat_engine.content.monsters.level_02.lurkers_sa import _triggering_enemy
from combat_engine.content.monsters.level_02.skirmishers_sa import _melee_only
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.skirmishers import (
    _free_square_beside,
    _recharge_on,
)
from combat_engine.content.monsters.level_05.artillery_sa import _shot_me_from_afar
from combat_engine.content.monsters.level_05.skirmishers_sa import _edge_on_target
from combat_engine.content.monsters.level_08.skirmishers_sa import (
    _adjacent_foe,
    _ended_flanking,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
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
    REACTION,
    REF,
    SELF,
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
    Effect,
    Health,
    Keyword,
    Melee,
    Movement,
    Position,
    Powers,
    Ranged,
    Square,
    Target,
    UpTo,
    Usage,
    When,
    Window,
    World,
    distance,
    power,
    spread,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    ConditionApplied,
    DamageApplied,
    DamageRolled,
    Died,
    Dropped,
    Healed,
    Hit,
    Miss,
    MoveStart,
    SavingThrow,
    SkillCheck,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.movement import walk
from combat_engine.engine.query import (
    alive,
    combatants,
    distance_between,
    has_combat_advantage,
    team,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_me,
    by_melee,
    my_check,
    targets_me,
)

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _pack_tactics(c: Cast, amount: int) -> None:
    """"Extra damage on melee attacks against an enemy that has two or more
    of its allies adjacent to it" -- printed word for word on three stat
    blocks this wave, counted off the victim's ring rather than the
    attacker's."""

    def gate(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None or not _melee_only(ctx):
            return False
        near = sum(1 for a in c.allies() if a != c.me and c.adjacent_to(victim, a))
        return near >= 2

    c.bonus("damage", amount, on=c.me, until=When.ENCOUNTER, when=gate)


def _my_own_roll(world: World, me: int, ev: Any) -> bool:
    """Whichever of the three roll kinds this is, it has to be this
    creature's own -- the three events spell "who rolled" three different
    ways (`attacker`, `actor`, `actor`)."""
    who = getattr(ev, "attacker", None)
    if who is None:
        who = getattr(ev, "actor", None)
    return who == me


def _reroll_any_d20(c: Cast) -> None:
    """"An attack roll, a saving throw, an ability check, or a skill check"
    -- the broadest roll a card names, and `c.trigger` says which of the
    first three actually happened. There is no ability-check event
    distinct from a skill check, so that quarter of the sentence has
    nothing to answer; noted rather than invented."""
    ev = c.trigger
    if isinstance(ev, SavingThrow):
        c.reroll_save()
    elif isinstance(ev, SkillCheck):
        c.reroll_check()
    else:
        c.reroll_attack()


_M1814_MARK: dict[int, tuple[Square | None, int]] = {}


def _m1814_arm(c: Cast) -> None:
    """Remembers only the **first** bloodying -- a label on the watch
    itself is the guard, the same way `_recharge_on` guards its own
    re-arming."""
    me = c.me
    label = f"{c.ref} mark-watch"
    if any(e.label == label for e in c.world.effects.of(me)):
        return

    def mark(ev: Bloodied) -> None:
        if ev.actor != me or me in _M1814_MARK:
            return
        pos = c.world.get(me, Position)
        square = pos.square if pos is not None else None
        source = ev.source if ev.source is not None else -1
        _M1814_MARK[me] = (square, source)

    c.watch(Bloodied, mark, until=When.ENCOUNTER, on=me, label=label)


def _under_ongoing(world: World, who: int | None) -> bool:
    return who is not None and any(e.ongoing for e in world.effects.of(who))


def _step_away_from(c: Cast, squares_: int, anchor: int) -> int:
    """`c.flee` is anchored on the caster's own square, which is no use
    when the caster is the one fleeing; this is the same farthest-reachable
    walk, anchored on somebody else's square instead."""
    who = c.me
    paths = c.world.reachable_paths(who, squares_)
    if not paths:
        return 0
    anchor_pos = c.world.get(anchor, Position)
    if anchor_pos is None:
        return 0
    away = max(sorted(paths), key=lambda sq: distance(sq, anchor_pos.square))
    return walk(c.world, who, paths[away])


def _grit_through(c: Cast, conditions: tuple[Condition, ...], cost: int) -> None:
    """"At the start of its turn, it can take N damage and end one of
    these conditions" -- offered, not forced, since the card says *can*."""
    me = c.me

    def check(ev: TurnStart) -> None:
        if ev.actor != me:
            return
        active_bad = [cond for cond in conditions if c.is_(cond, on=me)]
        if not active_bad:
            return
        pick = c.choose(active_bad, f"{c.ref}: end which condition", optional=True)
        if pick is not None:
            c.cure(pick, on=me)
            c.flat(cost, on=me)

    c.watch(TurnStart, check, until=When.ENCOUNTER, on=me, label=f"{c.ref} grit")


def _adjacent_enemy_attacks_me(world: World, me: int, ev: AttackDeclared) -> bool:
    attacker = getattr(ev, "attacker", None)
    return (
        getattr(ev, "target", None) == me
        and attacker is not None
        and distance_between(world, me, attacker) <= 1
    )


def _hit_with_a4(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and getattr(ev, "power", "") == "m6080a4"


def _feared_at(world: World, me: int, ev: AttackDeclared) -> bool:
    """"Targeted by a power with the fear keyword" -- read off the row
    behind the attack, the way `_shot_me_from_afar` reads a reach kind."""
    if getattr(ev, "target", None) != me:
        return False
    from combat_engine.engine import get

    row = get(getattr(ev, "power", "") or "")
    return row is not None and Keyword.FEAR in row.keywords


# ==========================================================================
# m1014
# ==========================================================================


@power(
    "m1014a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d4", 6),
)
def m1014a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(4, dtype=DamageType.RADIANT)


@power(
    "m1014a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 6),
)
def m1014a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d4", 0, dtype=DamageType.RADIANT)


@power(
    "m1014a2",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 4, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m1014a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m1014a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    target=UpTo(2),
)
def m1014a3(c: Cast) -> None:
    """"Melee or ranged", twice -- its own basic attack, chosen fresh for
    each target rather than fixed for the whole use."""
    ranged = c.choose([False, True], f"{c.ref}: melee or ranged")
    c.basic(on=c.target, ranged=bool(ranged))


@power(
    "m1014a4",
    level=9,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it makes an attack roll, a saving throw, an ability check, or a skill check",
    on=(
        Trigger(AttackRolled, _my_own_roll, "it makes an attack roll"),
        Trigger(SavingThrow, _my_own_roll, "it makes a saving throw"),
        Trigger(SkillCheck, _my_own_roll, "it makes a skill check"),
    ),
)
def m1014a4(c: Cast) -> None:
    _reroll_any_d20(c)


@power(
    "m1014a5",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1014a5(c: Cast) -> None:
    c.bonus("damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


# ==========================================================================
# m1082
# ==========================================================================


@power(
    "m1082a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 6),
)
def m1082a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(2, dtype=DamageType.POISON)


@power(
    "m1082a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 6),
)
def m1082a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(2, dtype=DamageType.POISON)


@power(
    "m1082a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 6, kind=LIMITED),
)
def m1082a2(c: Cast) -> None:
    """"It can shift 2 squares before or after the attack (but not both)."""
    early = c.may(f"{c.ref}: step before the attack")
    if early:
        c.shift(2)
    if c.strike():
        c.hit()
        c.flat(2, dtype=DamageType.POISON)
    if not early:
        c.shift(2)


@power(
    "m1082a3",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1082a3(c: Cast) -> None:
    me = c.me

    def stung(ev: DamageApplied) -> None:
        if ev.target != me:
            return
        if DamageType.RADIANT in (ev.dtypes or (ev.dtype,)):
            c.penalty("attack", 2, on=me, until=When.SONT)

    c.watch(DamageApplied, stung, until=When.ENCOUNTER, on=me, label=f"{c.ref} seared")


@power(
    "m1082a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1082a4(c: Cast) -> None:
    c.bonus("escape", 2, kind="racial", on=c.me, until=When.ENCOUNTER)
    narrowed = {Condition.IMMOBILIZED, Condition.RESTRAINED}
    c.bonus(
        "save", 2, kind="racial", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("conditions", frozenset()) & narrowed),
    )


# ==========================================================================
# m115732
# ==========================================================================


@power(
    "m115732a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
)
def m115732a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            c.invisible(to=victim, on=c.me, until=When.SONT)


@power(
    "m115732a1",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m115732a1(c: Cast) -> None:
    """Shifts its speed and swings at every enemy it passes -- `AdjacencyGained`
    read from its own side, the shape `m3072a1` settled: `mover` has to be
    this creature, and the pair comes mirrored so `actor` is checked too or
    each neighbour counts twice."""
    me = c.me
    met: list[int] = []

    def closed(ev: AdjacencyGained) -> None:
        if ev.mover == me and ev.actor == me and ev.other in c.enemies() and ev.other not in met:
            met.append(ev.other)

    watcher = c.watch(AdjacencyGained, closed, until=When.EOT, on=me, label=c.ref)
    c.shift(c.speed_of())
    c.world.effects.end(watcher, "the shift is over")
    for who in met:
        c.use_power("m115732a0", on=who, spend=False, again=True)


@power(
    "m115732a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m115732a2(c: Cast) -> None:
    c.teleport(5)
    for foe in c.enemies():
        if c.adjacent(foe):
            c.gains_advantage(lambda ctx, f=foe: ctx.get("target") == f, on=c.me, until=When.EOT)


# ==========================================================================
# m115837
# ==========================================================================


@power(
    "m115837a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115837a0(c: Cast) -> None:
    c.no_provoke(on=c.me, until=When.ENCOUNTER, when=lambda _ctx: c.moving_as("charge", on=c.me))


@power(
    "m115837a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("4d4", 7),
)
def m115837a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115837a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 7),
)
def m115837a2(c: Cast) -> None:
    if c.strike():
        c.hit()


def _adjacent_damaged_me(world: World, me: int, ev: DamageApplied) -> bool:
    source = getattr(ev, "source", None)
    return (
        getattr(ev, "target", None) == me
        and source is not None
        and team(world, source) is not team(world, me)
        and distance_between(world, me, source) <= 1
    )


@power(
    "m115837a3",
    level=9,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger="an enemy adjacent to it deals damage to it",
    on=Trigger(DamageApplied, _adjacent_damaged_me, "an adjacent enemy damages it"),
)
def m115837a3(c: Cast) -> None:
    """One attack roll; the push-and-shift chases the same foe up to five
    times total if it keeps rolling adjacent after each shove."""
    foe = _triggering_enemy(c)
    if foe is None or not c.adjacent(foe):
        return
    if not c.attack(12, FORT, on=foe):
        return
    c.damage("1d6", 5, on=foe)
    for _ in range(5):
        if not c.adjacent(foe):
            break
        if c.push(1, on=foe) == 0:
            break
        c.shift(1)


# m147, m165: no rows -- everything for these two was written in
# `skirmishers.py`.


# ==========================================================================
# m1809
# ==========================================================================


@power(
    "m1809a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 5),
)
def m1809a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1809a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 6),
)
def m1809a1(c: Cast) -> None:
    """No range is printed on this card at all, so it takes melee 1 by the
    settled convention even though the sentences around it plainly mean a
    loosed weapon."""
    if c.strike():
        c.hit()


@power(
    "m1809a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    target=UpTo(2),
)
def m1809a2(c: Cast) -> None:
    c.use_power("m1809a1", on=c.target, spend=False, again=True)


@power(
    "m1809a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=12),
)
def m1809a3(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m1809a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=12),
)
def m1809a4(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.BLINDED, until=When.SAVE_ENDS)


@power(
    "m1809a5",
    level=9,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is hit by a ranged or an area attack",
    on=Trigger(Hit, _shot_me_from_afar(0), "it is shot or caught in a burst"),
)
def m1809a5(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.use_power("m1809a1", on=foe, spend=False, again=True)


@power(
    "m1809a6",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d6", 8, kind=LIMITED),
)
def m1809a6(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1809a7",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m1809a7(c: Cast) -> None:
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m1809a6")
    c.use_power("m1809a6", spend=False, again=True)


@power(
    "m1809a8",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    on=Trigger(AttackRolled, _my_own_roll, "it makes an attack roll"),
)
def m1809a8(c: Cast) -> None:
    c.reroll_attack(keep="new")


@power(
    "m1809a9",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1809a9(c: Cast) -> None:
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m1811
# ==========================================================================


@power(
    "m1811a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 4),
)
def m1811a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.bloodied():
            c.flat(2)
        c.ongoing(5)


@power(
    "m1811a1",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d8", 7, kind=LIMITED),
)
def m1811a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.bloodied():
            c.flat(2)
        c.ongoing(10)


@power(
    "m1811a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d8", 5, kind=LIMITED),
)
def m1811a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.bloodied():
            c.flat(2)
        c.slide(3)


@power(
    "m1811a3",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1811a3(c: Cast) -> None:
    _pack_tactics(c, 5)


# ==========================================================================
# m1814
# ==========================================================================


@power(
    "m1814a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=23),
    damage=Damage("2d6", 5),
)
def m1814a0(c: Cast) -> None:
    _m1814_arm(c)
    plus = 1 if c.me in _M1814_MARK else 0
    if c.strike(plus=plus):
        c.hit()
        if c.crit:
            c.flat(c.roll("1d6"))


@power(
    "m1814a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=23),
    damage=Damage("1d8", 5),
)
def m1814a1(c: Cast) -> None:
    _m1814_arm(c)
    plus = 1 if c.me in _M1814_MARK else 0
    if c.strike(plus=plus):
        c.hit()


@power(
    "m1814a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m1814a2(c: Cast) -> None:
    """Remembers only the first bloodying; the body chooses whichever of
    the two printed destinations is still standing, favouring a square
    beside the foe who struck the blow over the bare bloodying square."""
    _m1814_arm(c)
    mark = _M1814_MARK.get(c.me)
    if mark is None:
        return
    square, foe = mark
    dest = _free_square_beside(c, foe) if foe != -1 and alive(c.world, foe) else None
    if dest is None:
        dest = square
    if dest is not None:
        c.teleport(0, to=dest)


@power(
    "m1814a3",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1814a3(c: Cast) -> None:
    def gate(ctx: dict[str, Any]) -> bool:
        mark = _M1814_MARK.get(c.me)
        return bool(c.bloodied()) and mark is not None and ctx.get("target") == mark[1]

    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=gate)


@power(
    "m1814a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1814a4(c: Cast) -> None:
    _pack_tactics(c, 5)


# ==========================================================================
# m1832
# ==========================================================================


@power(
    "m1832a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 5),
)
def m1832a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1832a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target("enemy", 1, label="the target must be bloodied", bloodied=True),
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 5),
)
def m1832a1(c: Cast) -> None:
    """The defence bonus is the caster's, so it is laid `on=c.me` -- `c.bonus`
    follows the target otherwise."""
    if c.strike():
        c.hit()
        for d in ALL_DEFENCES:
            c.bonus(d, 2, kind="power", on=c.me, until=When.EONT)


@power(
    "m1832a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m1832a2(c: Cast) -> None:
    me = c.me
    pool = [w for w in combatants(c.world) if w == me or c.bloodied(on=w)]
    dest = None
    for who in pool:
        spot = c.here if who == me else _free_square_beside(c, who)
        if spot is not None and distance(c.here, spot) <= 10:
            dest = spot
            break
    if dest is not None:
        c.teleport(0, to=dest)


@power(
    "m1832a3",
    level=9,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    on=Trigger(Hit, both(by_me, by_melee), "it makes a successful melee attack"),
)
def m1832a3(c: Cast) -> None:
    if c.bloodied():
        c.shift(2)


@power(
    "m1832a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1832a4(c: Cast) -> None:
    _pack_tactics(c, 5)


# ==========================================================================
# m2080
# ==========================================================================


@power(
    "m2080a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d10", 3),
)
def m2080a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2080a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 3),
)
def m2080a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2080a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
)
def m2080a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m2080a0", on=victim, spend=False, again=True)
    got0 = c.landed
    c.use_power("m2080a1", on=victim, spend=False, again=True)
    got1 = c.landed
    if got0 and got1:
        c.ongoing(5, DamageType.PSYCHIC, on=victim)


@power(
    "m2080a3",
    level=9,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d6", 2, dtype=DamageType.PSYCHIC),
    trigger="it is reduced to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m2080a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2080a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2080a4(c: Cast) -> None:
    c.no_provoke(
        on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _under_ongoing(c.world, ctx.get("actor")),
    )


# m2976, m3013, m3072, m3116: no rows -- everything for these four was
# written in `skirmishers.py`.


# ==========================================================================
# m3317
# ==========================================================================


@power(
    "m3317a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d4", 5),
)
def m3317a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3317a1",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d4", 7, kind=LIMITED),
)
def m3317a1(c: Cast) -> None:
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    if c.strike():
        c.hit()


@power(
    "m3317a2",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(3),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION],
)
def m3317a2(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        c.invisible(to=victim, on=c.me, until=When.SONT)


@power(
    "m3317a3",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3317a3(c: Cast) -> None:
    c.bonus("damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m3317a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3317a4(c: Cast) -> None:
    """"On a dagger attack" is a weapon-specific narrowing nothing in the
    damage or attack context reads; applied to every attack rather than
    thrown away."""
    c.bonus("crit_range", 2, on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m3762
# ==========================================================================


@power(
    "m3762a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 5),
)
def m3762a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3762a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 5),
    charges=True,
)
def m3762a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
    c.shift(2)


@power(
    "m3762a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=SELF,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 5),
)
def m3762a2(c: Cast) -> None:
    """"Moves 6 squares and makes up to three attacks ... attacking a
    different target each time" -- `AdjacencyGained` read off its own move,
    the shape `m115732a1` and `m3072a1` share, capped at three and never
    repeating a victim."""
    me = c.me
    met: list[int] = []

    def closed(ev: AdjacencyGained) -> None:
        if ev.mover == me and ev.actor == me and ev.other in c.enemies() and ev.other not in met:
            met.append(ev.other)

    watcher = c.watch(AdjacencyGained, closed, until=When.EOT, on=me, label=c.ref)
    c.shift(6)
    c.world.effects.end(watcher, "the move is over")
    for who in met[:3]:
        if c.strike(on=who):
            c.hit(on=who)
            c.slide(1, on=who)


# ==========================================================================
# m3787
# ==========================================================================


@power(
    "m3787a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 4),
)
def m3787a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if len(c.within(1, of=c.me, side="enemy")) == 1:
            c.flat(5)


@power(
    "m3787a1",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m3787a1(c: Cast) -> None:
    """Disguise, pierced by an opposed check nothing on a board rolls."""


@power(
    "m3787a2",
    level=9,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m3787a2(c: Cast) -> None:
    """"Begins and ends adjacent to a tree, treant, or large-or-bigger
    plant" -- the board is asked at the start; nothing here can steer the
    destination the decider picks, so the end half is not re-checked."""
    if not (c.scenery("tree", within=1, of=c.me) or c.scenery("plant", within=1, of=c.me)):
        return
    c.teleport(8)


# ==========================================================================
# m3790
# ==========================================================================


@power(
    "m3790a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 4),
)
def m3790a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m3790a1",
    level=9,
    usage=Usage.RECHARGE,
    recharge=3,
    action=STANDARD,
    reach=Ranged(10),
    target=Target(
        "enemy", 1,
        label="only affects creatures taking ongoing poison damage",
        ongoing_types=frozenset({DamageType.POISON}),
    ),
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
)
def m3790a1(c: Cast) -> None:
    """"Only affects creatures taking ongoing poison damage" is the target
    line itself now, so the body's re-pick came out: an empty pool already
    refuses the row, from one place instead of two. The type is named rather
    than `ongoing=True`, which would accept a creature burning from
    somewhere else. `m3790a2` is the twin with the restriction lifted. #401."""
    if c.strike():
        c.condition(Condition.DAZED, Condition.SLOWED, until=When.SAVE_ENDS)


@power(
    "m3790a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
)
def m3790a2(c: Cast) -> None:
    """"Even if it hasn't recharged and even if the target isn't taking
    ongoing poison damage" -- an independent at-will version of the same
    attack is how both restrictions of `m3790a1` are lifted, since calling
    that row would still run its own gate."""
    victim = c.target
    if victim is None:
        return
    if c.strike(on=victim):
        c.condition(Condition.DAZED, Condition.SLOWED, until=When.SAVE_ENDS, on=victim)


@power(
    "m3790a3",
    level=9,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m3790a3(c: Cast) -> None:
    c.shift(3)


# m380: no rows -- everything for this block was written in
# `skirmishers.py`.


# ==========================================================================
# m3821
# ==========================================================================


@power(
    "m3821a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 5),
)
def m3821a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", 0, dtype=DamageType.COLD)
        c.shift(2)


@power(
    "m3821a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d4", 5),
    dropped=("c.no_opportunity_attacks()",),
)
def m3821a1(c: Cast) -> None:
    """"The target cannot make opportunity attacks until the end of her
    next turn" -- narrower than anything that exists: `c.cannot_attack`
    forbids every attack, not opportunity ones alone."""
    if c.strike():
        c.hit()


@power(
    "m3821a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    target=UpTo(2),
)
def m3821a2(c: Cast) -> None:
    """Two basic attacks, each melee or ranged, aimed when it is made.

    m3821a0's own rider steps it 2 squares on a hit and that is not optional,
    so it lands between the two swings and the second was being made from out
    of reach. The fix is here rather than in m3821a0: one `toward=` cannot
    serve two different targets, and the row that moves cannot know who is
    still owed a swing. A melee swing therefore takes whoever is in reach and
    has not been swung at yet; a ranged one keeps its printed target. The
    whole use runs on `c.first`.
    """
    if not c.first:
        return
    swung: list[int] = []
    for chosen in c.targets[:2]:
        ranged = bool(c.choose([False, True], f"{c.ref}: melee or ranged"))
        victim: int | None = chosen
        if not ranged and not c.adjacent(chosen):
            victim = next(
                (f for f in c.enemies() if f not in swung and c.adjacent(f)), None
            )
        if victim is None:
            continue
        swung.append(victim)
        c.basic(on=victim, ranged=ranged)


@power(
    "m3821a3",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d6", 5, kind=LIMITED),
)
def m3821a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()


@power(
    "m3821a4",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d6", 4, kind=LIMITED, half_on_miss=True),
)
def m3821a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.unconscious(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m3821a5",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="a creature flanks it",
    on=Trigger(MoveStart, _ended_flanking, "a creature's move leaves it flanked"),
)
def m3821a5(c: Cast) -> None:
    c.shift(2, share=True)
    foe = _adjacent_foe(c, c.ref)
    if foe is not None:
        c.flat(4, on=foe)


@power(
    "m3821a6",
    level=9,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m3821a6(c: Cast) -> None:
    c.mode("fly", 6, until=When.EOT, on=c.me)
    c.hover(0, on=c.me, until=When.EOT)


@power(
    "m3821a7",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3821a7(c: Cast) -> None:
    c.bonus("damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


_M3821_ACTED: set[int] = set()


def _m3821_track(c: Cast) -> None:
    label = f"{c.ref} acted-watch"
    if any(e.label == label for e in c.world.effects.of(c.me)):
        return

    def mark(ev: TurnStart) -> None:
        if not ev.ghost:
            _M3821_ACTED.add(ev.actor)

    c.watch(TurnStart, mark, until=When.ENCOUNTER, on=c.me, label=label)


@power(
    "m3821a8",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3821a8(c: Cast) -> None:
    _m3821_track(c)
    c.gains_advantage(
        lambda ctx: ctx.get("target") is not None and ctx.get("target") not in _M3821_ACTED,
        on=c.me, until=When.ENCOUNTER,
    )


# ==========================================================================
# m4186
# ==========================================================================


@power(
    "m4186a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 4),
)
def m4186a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.RADIANT)


@power(
    "m4186a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 4),
)
def m4186a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4186a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m4186a2(c: Cast) -> None:
    half = max(1, c.speed_of() // 2)
    c.teleport(half)
    foe1 = _adjacent_foe(c, c.ref)
    if foe1 is not None:
        c.use_power("m4186a1", on=foe1, spend=False, again=True)
    c.teleport(half)
    pool = [f for f in c.enemies() if c.adjacent(f) and f != foe1]
    foe2 = c.choose(pool, f"{c.ref}: second target") if pool else None
    if foe2 is not None:
        c.use_power("m4186a1", on=foe2, spend=False, again=True)


@power(
    "m4186a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_OTHER,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d6", 2, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m4186a3(c: Cast) -> None:
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


# ==========================================================================
# m4414
# ==========================================================================


@power(
    "m4414a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 8),
)
def m4414a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4414a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 9),
)
def m4414a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4414a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 8, kind=LIMITED),
    charges=True,
)
def m4414a2(c: Cast) -> None:
    c.ignores_difficult(on=c.me, until=When.EOT)
    c.no_provoke(on=c.me, until=When.EOT)
    if c.strike():
        c.hit()


@power(
    "m4414a3",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("query.in_motion",),
)
def m4414a3(c: Cast) -> None:
    """"+4 to AC and Reflex when targeted while moving" -- a plain walk sets
    nothing readable. `Movement.using` says what special mode a creature is
    in (fly, climb, burrow) and is explicitly blank for an ordinary move, so
    there is no live "is it moving right now" flag to gate on."""
    c.bonus("escape", 4, on=c.me, until=When.ENCOUNTER)


@power(
    "m4414a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4414a4(c: Cast) -> None:
    c.bonus("damage", 0, dice="1d8", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


# m461, m4782, m5018: no rows -- everything for these three was written in
# `skirmishers.py`.


# ==========================================================================
# m5183
# ==========================================================================


@power(
    "m5183a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 10),
)
def m5183a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if len(c.within(1, of=c.me, side="enemy")) == 1:
            c.damage("1d8", 0)


@power(
    "m5183a1",
    level=9,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5183a1(c: Cast) -> None:
    if not (c.scenery("tree", within=1, of=c.me) or c.scenery("plant", within=1, of=c.me)):
        return
    c.teleport(8)


@power(
    "m5183a2",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m5183a2(c: Cast) -> None:
    """Disguise, pierced by an opposed check nothing on a board rolls."""


@power(
    "m5183a3",
    level=9,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points and is killed",
    on=Trigger(Dropped, about_me, "it drops"),
    dropped=("c.grant_kind()",),
)
def m5183a3(c: Cast) -> None:
    """"Remains standing ... until the end of its next turn" -- held open
    by refusing to let the drop stick rather than by a second trip through
    death. The undead keyword the card also grants has nowhere to go: there
    is no verb that adds a kind word to a creature at runtime."""
    me = c.me

    def propped(ev: Dropped) -> None:
        if ev.actor != me:
            return
        health = c.world.get(me, Health)
        if health is not None and health.hp <= 0:
            health.hp = 1

    c.watch(Dropped, propped, until=When.EONT, on=me, label=f"{c.ref} propped")


# ==========================================================================
# m5292
# ==========================================================================


@power(
    "m5292a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5292a0(c: Cast) -> None:
    c.bonus("damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m5292a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
)
def m5292a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.PSYCHIC)


@power(
    "m5292a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
)
def m5292a2(c: Cast) -> None:
    victim1 = c.target
    if victim1 is not None and c.strike(on=victim1):
        c.hit(on=victim1)
    c.shift(2)
    pool = c.enemies()
    victim2 = c.choose(pool, f"{c.ref}: second target") if pool else None
    if victim2 is not None and c.strike(on=victim2):
        c.hit(on=victim2)


@power(
    "m5292a3",
    level=9,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    on=Trigger(Hit, both(targets_me, by_melee), "an enemy hits it with a melee attack"),
)
def m5292a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.use_power("m5292a1", on=foe, spend=False, again=True)
    c.shift(3)


# ==========================================================================
# m5303
# ==========================================================================


@power(
    "m5303a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.permit_charge()",),
)
def m5303a0(c: Cast) -> None:
    """"Can charge while burrowing." Nothing found in `actions.charge` or
    `can_walk` refuses a charge for a burrowing creature, so there is no
    restriction to lift and no verb that would demonstrate this either
    way."""


@power(
    "m5303a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("World.sunlight",),
)
def m5303a1(c: Cast) -> None:
    """Direct sunlight has nothing to ask -- the board has no concept of
    it. Taking radiant damage does, and is the half that plays."""
    me = c.me

    def stung(ev: DamageApplied) -> None:
        if ev.target != me:
            return
        if DamageType.RADIANT in (ev.dtypes or (ev.dtype,)):
            c.penalty("attack", 2, on=me, until=When.EONT)

    c.watch(DamageApplied, stung, until=When.ENCOUNTER, on=me, label=f"{c.ref} seared")


@power(
    "m5303a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 6),
)
def m5303a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.is_(Condition.SLOWED, on=c.target):
            c.immobilized(until=When.SAVE_ENDS)
        else:
            c.slowed(until=When.SAVE_ENDS)


@power(
    "m5303a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    attack=Attack(vs=REF, printed=11),
    damage=Damage("4d10", 3),
)
def m5303a3(c: Cast) -> None:
    """Surfaces first, if it is underground at all; the burst centres
    wherever it comes up. The free shift is offered per creature caught,
    which is what "can" says."""
    if c.first:
        if not c.moving_as("burrow", on=c.me):
            return
        c.move(4)
    if c.strike():
        c.hit()
        c.slide(2)
    if c.last:
        area = spread({c.here}, 2)
        c.zone(area, difficult=True, until=When.ENCOUNTER, label=c.ref)
        for who in c.in_squares(area, side="any"):
            if who != c.me and c.may(f"{c.ref}: shift", who=who):
                c.shift(3, who=who)


@power(
    "m5303a4",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m5303a4(c: Cast) -> None:
    c.shift(1)


# ==========================================================================
# m5603
# ==========================================================================


@power(
    "m5603a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5603a0(c: Cast) -> None:
    c.bonus("damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m5603a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 7),
)
def m5603a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5603a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d4", 7),
)
def m5603a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5603a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 7),
)
def m5603a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m5603a4",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    target=UpTo(2),
)
def m5603a4(c: Cast) -> None:
    c.use_power("m5603a3", on=c.target, spend=False, again=True)


@power(
    "m5603a5",
    level=9,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ZONE],
)
def m5603a5(c: Cast) -> None:
    """The squares it actually walks, read as a straight line between where
    it started and where it ended -- the decider does not hand back a path,
    only a destination."""
    start = c.here
    c.shift(6)
    end = c.here
    area = c.line(start, end) if start != end else {end}
    c.zone(area, difficult=True, until=When.ENCOUNTER, label=c.ref)


@power(
    "m5603a6",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it makes a Bluff check",
    on=Trigger(SkillCheck, my_check("bluff"), "it makes a Bluff check", window=Window.BEFORE),
)
def m5603a6(c: Cast) -> None:
    """"+5 bonus on the check" lands before the total is struck --
    `SkillCheck` finishes its bonus in the resolve step, so `BEFORE` is the
    window where adding to it still counts."""
    ev = c.trigger
    if ev is not None:
        ev.bonus += 5


@power(
    "m5603a7",
    level=9,
    usage=Usage.RECHARGE,
    recharge=5,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    on=Trigger(Hit, targets_me, "an enemy hits it"),
)
def m5603a7(c: Cast) -> None:
    c.ignores_difficult(on=c.me, until=When.EOT)
    c.shift(4)


# ==========================================================================
# m5702
# ==========================================================================


@power(
    "m5702a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5702a0(c: Cast) -> None:
    c.bonus("damage", 0, dice="1d8", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m5702a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5702a1(c: Cast) -> None:
    for word in ("rubble", "debris"):
        c.ignores_difficult(word, on=c.me, until=When.ENCOUNTER)


@power(
    "m5702a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
)
def m5702a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m5702a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d8", 8, kind=LIMITED),
)
def m5702a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)
        c.prone()


@power(
    "m5702a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m5702a4(c: Cast) -> None:
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    c.jump(c.speed_of())


# ==========================================================================
# m5819
# ==========================================================================


@power(
    "m5819a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d8", 4),
)
def m5819a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None and has_combat_advantage(c.world, c.me, victim):
            c.slowed(until=When.SAVE_ENDS)


@power(
    "m5819a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d8", 3, dtype=DamageType.POISON),
)
def m5819a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m5819a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m5819a2(c: Cast) -> None:
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    c.phasing(until=When.SONT)
    c.shift(c.speed_of())


@power(
    "m5819a3",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.DISEASE, Keyword.POISON],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("3d8", 6, dtype=DamageType.POISON, kind=LIMITED),
    trigger="it dies",
    on=Trigger(Died, about_me, "it dies"),
)
def m5819a3(c: Cast) -> None:
    """The burst, its poison damage and the disease all play now.

    The card contracts `x5_62` on a failed save *at the end of the
    encounter*, and this engine cannot tell that moment from the end of the
    fight -- so it lands on the hit, which is the closest this horizon
    allows and errs toward the creature catching it. #389 built the table;
    the stage does not advance, which is what the page prints."""
    if c.strike():
        c.hit()
        c.contract("x5_62")


# ==========================================================================
# m5869
# ==========================================================================


@power(
    "m5869a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m5869a0(c: Cast) -> None:
    """"Can't spend healing surges in the aura" reads as `c.no_healing`,
    which refuses healing outright rather than only surge-spending -- wider
    than the card, and the closest thing that exists. Reapplied each time
    the toll catches somebody standing in the aura at the end of their
    turn, rather than laid once for the whole fight, since membership
    changes every time somebody moves."""
    me = c.me
    c.aura(1, until=When.ENCOUNTER, label=c.ref)

    def toll(ev: TurnEnd) -> None:
        if ev.actor == me or not c.in_my_aura(ev.actor, label=c.ref):
            return
        if team(c.world, ev.actor) is team(c.world, me):
            return
        c.flat(5, dtype=DamageType.NECROTIC, on=ev.actor)
        c.temp_hp(5, on=me)
        c.no_healing(on=ev.actor, until=When.EOT)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} toll")


@power(
    "m5869a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5869a1(c: Cast) -> None:
    """Halves every blow except fire, force or radiant -- `c.insubstantial`
    halves without exception, so this is read and rewritten off
    `DamageRolled` instead. Taking fire or radiant switches the halving off
    until its own next turn; force passes through at full and does not
    touch that flag."""
    me = c.me
    label = f"{c.ref} open"

    def halve(ev: DamageRolled) -> None:
        if ev.target != me:
            return
        if ev.dtype in (DamageType.FIRE, DamageType.FORCE, DamageType.RADIANT):
            if ev.dtype is not DamageType.FORCE:
                c.effect(label, until=When.SONT, on=me)
            return
        if any(e.label == label for e in c.world.effects.of(me)):
            return
        ev.amount = ev.amount // 2

    c.watch(DamageRolled, halve, until=When.ENCOUNTER, on=me, label=f"{c.ref} half")


@power(
    "m5869a2",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5869a2(c: Cast) -> None:
    """Moving through openings of any size is not asked -- there is
    nothing that measures a gap by size. Sharing a creature's space and
    ending its turn there is."""
    c.shares_space(on=c.me, until=When.ENCOUNTER)


@power(
    "m5869a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("3d6", 7, dtype=DamageType.NECROTIC),
)
def m5869a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.vulnerable(5, DamageType.NECROTIC, until=When.EONT)


@power(
    "m5869a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d10", 2, dtype=[DamageType.NECROTIC, DamageType.PSYCHIC], kind=LIMITED),
)
def m5869a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m5869a5",
    level=9,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m5869a5(c: Cast) -> None:
    """Its only real speed is the fly in its stat block -- ground speed is
    0 -- so the shift borrows the difference the way `c.move(at=)` lends a
    mode's speed for the length of a move."""
    moves = c.world.get(c.me, Movement)
    fly_speed = moves.modes.get("fly", 0) if moves is not None else 0
    extra = max(0, fly_speed - c.speed_of())
    if extra:
        c.bonus("speed", extra, until=When.EOT, on=c.me, kind="untyped")
    c.shift(fly_speed)


# ==========================================================================
# m5908
# ==========================================================================


@power(
    "m5908a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5908a0(c: Cast) -> None:
    me = c.me

    def check(ev: TurnStart) -> None:
        if ev.actor != me or not c.marked(on=me):
            return
        if c.save(bare=True, against="mark"):
            for eff in list(c.world.effects.of(me)):
                if "mark" in eff.label:
                    c.world.effects.end(eff, "shaken off")

    c.watch(TurnStart, check, until=When.ENCOUNTER, on=me, label=f"{c.ref} shrug")


@power(
    "m5908a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 4),
)
def m5908a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None and has_combat_advantage(c.world, c.me, victim):
            c.flat(4)


@power(
    "m5908a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d6", 6),
)
def m5908a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None and has_combat_advantage(c.world, c.me, victim):
            c.flat(4)


@power(
    "m5908a3",
    level=9,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5908a3(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m6014
# ==========================================================================


@power(
    "m6014a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6014a0(c: Cast) -> None:
    me = c.me
    watched = (Condition.DAZED, Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.STUNNED)

    def check(ev: TurnStart) -> None:
        if ev.actor != me:
            return
        for cond in watched:
            if c.is_(cond, on=me) and c.save(bare=True, against=cond.value):
                c.cure(cond, on=me)

    c.watch(TurnStart, check, until=When.ENCOUNTER, on=me, label=f"{c.ref} grit")


@power(
    "m6014a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d4", 7),
)
def m6014a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None and has_combat_advantage(c.world, c.me, victim):
            c.damage("3d4", 0)


@power(
    "m6014a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d4", 7),
)
def m6014a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grants_advantage(to="team", until=When.SAVE_ENDS)


@power(
    "m6014a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    target=ONE_CREATURE,
)
def m6014a3(c: Cast) -> None:
    order = c.choose(["melee first", "ranged first"], f"{c.ref}: order") or "melee first"
    seq = ["m6014a1", "m6014a2"] if order == "melee first" else ["m6014a2", "m6014a1"]
    victim = c.target
    c.use_power(seq[0], on=victim, spend=False, again=True)
    c.shift(max(1, c.speed_of() // 2))
    c.use_power(seq[1], on=victim, spend=False, again=True)


@power(
    "m6014a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6014a4(c: Cast) -> None:
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    c.shift(c.speed_of())


@power(
    "m6014a5",
    level=9,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    on=Trigger(AttackDeclared, _adjacent_enemy_attacks_me, "an adjacent enemy attacks it"),
)
def m6014a5(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.use_power("m6014a1", on=foe, spend=False, again=True)


# ==========================================================================
# m6059
# ==========================================================================


@power(
    "m6059a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6059a0(c: Cast) -> None:
    c.bonus("damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m6059a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 5),
)
def m6059a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6059a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 6),
)
def m6059a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is None:
            return

        def worsen(eff: Effect) -> None:
            c.world.effects.end(eff, "the poison deepens")
            c.condition(until=When.SAVE_ENDS, on=victim, ongoing=(10, DamageType.POISON))

        c.condition(
            until=When.SAVE_ENDS, on=victim, ongoing=(5, DamageType.POISON), escalate=worsen,
        )


@power(
    "m6059a3",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=12),
)
def m6059a3(c: Cast) -> None:
    if c.strike():
        c.grants_advantage(until=When.EONT)


@power(
    "m6059a4",
    level=9,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m6059a4(c: Cast) -> None:
    """A disguised shape with no combat clause of its own -- pierced by an
    Insight check nothing on a board rolls."""


# ==========================================================================
# m6073
# ==========================================================================


@power(
    "m6073a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.ignore_hazards()",),
)
def m6073a0(c: Cast) -> None:
    """"Ignores all damage and effects from hazardous terrain." Nothing in
    the vocabulary grants immunity to a hazard or a zone's burn; `c.resist`
    and `c.immune` both ask about a creature's reaction to an attack or a
    condition, not about terrain."""


@power(
    "m6073a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6073a1(c: Cast) -> None:
    conditions = (
        Condition.DAZED, Condition.DOMINATED, Condition.IMMOBILIZED,
        Condition.RESTRAINED, Condition.SLOWED, Condition.STUNNED,
    )
    _grit_through(c, conditions, 10)


@power(
    "m6073a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
)
def m6073a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m6073a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m6073a3(c: Cast) -> None:
    for _ in range(3):
        c.teleport(5)
        foe = _adjacent_foe(c, c.ref)
        if foe is not None:
            c.use_power("m6073a2", on=foe, spend=False, again=True)


@power(
    "m6073a4",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=12),
    damage=Damage("3d8", 5, kind=LIMITED, half_on_miss=True),
    dropped=("actions.stand_up_cost",),
)
def m6073a4(c: Cast) -> None:
    """"Must spend a standard action to stand up (save ends)" raises the
    price of standing rather than forbidding it; nothing reads a surcharge
    on the stand action, only whether it is allowed at all."""
    if c.strike():
        c.hit()
        c.prone()
    else:
        c.hit(half=True)


@power(
    "m6073a5",
    level=9,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6073a5(c: Cast) -> None:
    for foe in [f for f in c.enemies() if c.adjacent(f)]:
        c.push(2, on=foe)
    c.mode("fly", c.speed_of(), until=When.EOT, on=c.me)
    c.move(c.speed_of())


@power(
    "m6073a6",
    level=9,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_OTHER,
    keywords=[Keyword.TELEPORTATION],
    attack=Attack(vs=FORT, printed=12),
)
def m6073a6(c: Cast) -> None:
    if c.strike():
        victim = c.target
        if victim is None:
            return
        pos = c.world.get(victim, Position)
        here = pos.square if pos is not None else None
        options = [sq for sq in c.area() if sq != here and c.world.grid.occupant(sq) is None]
        dest = c.choose(options, f"{c.ref}: where", optional=True) if options else None
        if dest is not None:
            c.teleport(0, who=victim, to=dest)


@power(
    "m6073a7",
    level=9,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    on=Trigger(Miss, targets_me, "an enemy misses it"),
)
def m6073a7(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    dest = _free_square_beside(c, foe)
    if dest is not None:
        c.teleport(0, to=dest)
    c.use_power("m6073a2", on=foe, spend=False, again=True)


@power(
    "m6073a8",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m6073a8(c: Cast) -> None:
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m6073a5")
    c.use_power("m6073a5", spend=False, again=True)


# ==========================================================================
# m6078
# ==========================================================================


@power(
    "m6078a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6078a0(c: Cast) -> None:
    """Grounds it by forbidding its own flying-move row rather than by
    clearing a mode flag nothing reads back in: `Movement.using` is cleared
    by the engine itself the moment it lands, so stopping it from
    re-launching is the real lever."""
    me = c.me

    def grounded(ev: DamageApplied) -> None:
        if ev.target != me or DamageType.RADIANT not in (ev.dtypes or (ev.dtype,)):
            return
        moves = c.world.get(me, Movement)
        if moves is not None and moves.using == "fly":
            c.fall(0, on=me)
            moves.using = ""
        c.forbid("m6078a3", on=me, until=When.EONT)

    c.watch(DamageApplied, grounded, until=When.ENCOUNTER, on=me, label=f"{c.ref} grounded")


@power(
    "m6078a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 8),
)
def m6078a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        known = c.world.get(c.me, Powers)
        if known is not None:
            known.restore("m6078a2")


@power(
    "m6078a2",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d6", 8, dtype=[DamageType.PSYCHIC, DamageType.NECROTIC],
                  kind=LIMITED),
    dropped=("Target.creature_kind",),
)
def m6078a2(c: Cast) -> None:
    """Two type filters `Target` cannot make -- "living creatures" and
    "undead and animates" -- are both asked here.

    **This row contradicted itself, which is why it is worth a note.** The
    keyword list said necrotic, the header said psychic, and the card says
    the one roll is both -- so whichever a reader consulted, it was half
    right. #423's walk catches exactly that shape.
    """
    victim = c.target
    if victim is None:
        return
    if c.is_kind("undead", on=victim) or c.is_kind("animate", on=victim):
        if c.may(f"{c.ref}: shift", who=victim):
            c.shift(2, who=victim)
        return
    if c.is_kind("construct", on=victim):
        return
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m6078a3",
    level=9,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6078a3(c: Cast) -> None:
    c.mode("fly", c.speed_of(), until=When.EOT, on=c.me)
    c.no_provoke(on=c.me, until=When.EOT)
    c.move(5)


@power(
    "m6078a4",
    level=9,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=Target(
        "other", 99, everyone=True,
        label="living creatures in the burst",
        # "Living" is not a negative set. Excluding `construct` as well
        # refuses the 25 blocks that carry *both* `living` and `construct`,
        # which the card calls living; excluding only `undead` admits a
        # non-living construct. The exact test is "not undead, and not
        # construct unless it carries living", which no any-of negative can
        # say. This is the faithful half -- what the body asked before the
        # conversion -- and the exception is marked. #411.
        kinds_without=frozenset({"undead"}),
    ),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d6", 2, dtype=DamageType.NECROTIC),
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
    dropped=("Target.living",),
)
def m6078a4(c: Cast) -> None:
    """"Living creatures" is the **negative** of two type words and not a
    positive `kinds={"living"}`: only 25 blocks in the corpus print that word
    and a character has no type line at all, so the positive form would refuse
    nearly every creature the card catches. `kinds_without` is what the body
    was already asking, and it is what `_living` means next door. #401."""
    if c.strike():
        c.hit()
        c.weakened(until=When.EONT)


# ==========================================================================
# m6080
# ==========================================================================


@power(
    "m6080a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m6080a0(c: Cast) -> None:
    me = c.me
    c.aura(2, until=When.ENCOUNTER, label=c.ref)

    def toll(ev: TurnStart) -> None:
        if ev.actor == me or team(c.world, ev.actor) is team(c.world, me):
            return
        if c.in_my_aura(ev.actor, label=c.ref):
            c.flat(5, on=ev.actor)

    c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} burn")


@power(
    "m6080a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6080a1(c: Cast) -> None:
    me = c.me
    c.aura(5, until=When.ENCOUNTER, label=c.ref)

    def halve(ev: Healed) -> None:
        if not c.bloodied():
            return
        if team(c.world, ev.target) is team(c.world, me):
            return
        if c.in_my_aura(ev.target, label=c.ref):
            ev.amount //= 2

    c.watch(Healed, halve, until=When.ENCOUNTER, on=me, label=f"{c.ref} sap")


@power(
    "m6080a2",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6080a2(c: Cast) -> None:
    """A second slot in the initiative order, not a second roll replacing
    the first. `c.reroll_initiative` is reached for only because nothing
    else rolls a fresh initiative count on demand; `c.extra_turn` is what
    turns a rolled count into a second turn."""
    second = c.reroll_initiative(on=c.me)
    c.extra_turn(at=second)


@power(
    "m6080a3",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6080a3(c: Cast) -> None:
    me = c.me
    downgrade = {
        Condition.DOMINATED: Condition.DAZED,
        Condition.STUNNED: Condition.DAZED,
        Condition.IMMOBILIZED: Condition.SLOWED,
        Condition.RESTRAINED: Condition.SLOWED,
    }

    def swap(ev: ConditionApplied) -> None:
        if ev.target != me:
            return
        softer = downgrade.get(ev.condition)
        if softer is None:
            return
        for eff in list(c.world.effects.of(me)):
            if ev.condition in eff.conditions:
                c.world.effects.end(eff, "softened")
                break
        c.condition(softer, until=When.SAVE_ENDS, on=me)
        c.flat(5, on=me)

    c.watch(ConditionApplied, swap, until=When.ENCOUNTER, on=me, label=f"{c.ref} grit")


@power(
    "m6080a4",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 5),
)
def m6080a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m6080a5",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d10", 5),
)
def m6080a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(4)
        foe = _adjacent_foe(c, c.ref)
        if foe is not None:
            c.use_power("m6080a4", on=foe, spend=False, again=True)


@power(
    "m6080a6",
    level=9,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
)
def m6080a6(c: Cast) -> None:
    veil = c.invisible(until=When.EONT)
    if veil is None:
        return
    me = c.me

    def reveal(ev: AttackRolled) -> None:
        if ev.attacker == me:
            c.world.effects.end(veil, "it attacked")

    seen = c.watch(AttackRolled, reveal, until=When.EONT, on=me, label=c.ref)
    veil.on_end.append(lambda: c.world.effects.end(seen, "no longer unseen"))


@power(
    "m6080a7",
    level=9,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.POISON],
    on=Trigger(Hit, _hit_with_a4, "it hits with m6080a4"),
)
def m6080a7(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    if c.attack(12, FORT, on=foe):
        c.spend_surge(on=foe)
        c.ongoing(5, DamageType.POISON, on=foe)


@power(
    "m6080a8",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    on=Trigger(Hit, targets_me, "an enemy hits it with a melee or ranged attack"),
)
def m6080a8(c: Cast) -> None:
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    c.shift(4)
    c.insubstantial(until=When.EOTNT)


# ==========================================================================
# m6172
# ==========================================================================


@power(
    "m6172a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6172a0(c: Cast) -> None:
    me = c.me

    def buffed(ev: TurnStart) -> None:
        if ev.actor != me:
            return
        for d in ALL_DEFENCES:
            c.bonus(d, 2, on=me, until=When.EOT)

    c.watch(TurnStart, buffed, until=When.ENCOUNTER, on=me, label=f"{c.ref} guard")


@power(
    "m6172a1",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 9),
)
def m6172a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None and has_combat_advantage(c.world, c.me, victim):
            c.flat(5)
        c.shift(1)


@power(
    "m6172a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d6", 5, kind=LIMITED),
    dropped=("Target.any_of",),
)
def m6172a2(c: Cast) -> None:
    """"One creature it is flanking, **or** one prone creature" is a
    disjunction, and the disjunction is now the whole gap: `Target.flanked`
    says the first half and `Target.conditions` says the second, but every
    field on a target line **narrows**, so declaring both would demand a
    prone creature it is also flanking -- refusing most of what the card
    allows. Until `Target.any_of` can hold two alternatives the pick stays in
    the body, where a qualifying creature in reach is found rather than the
    row thrown away. The marker named `Target.condition` as well until that
    field landed; the earlier spelling was `Target.flanked_by`, a symbol that
    could never arrive."""
    from combat_engine.engine.query import flanked_by as _flanked_by

    def qualifies(f: int) -> bool:
        return _flanked_by(c.world, f, c.me) or c.is_(Condition.PRONE, on=f)

    victim = _restricted_to(c, 1, qualifies)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.ongoing(10, on=victim)


@power(
    "m6172a3",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6172a3(c: Cast) -> None:
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    c.shift(max(1, c.speed_of() // 2))


# ==========================================================================
# m6439
# ==========================================================================


@power(
    "m6439a0",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6439a0(c: Cast) -> None:
    c.bonus("damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m6439a1",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6439a1(c: Cast) -> None:
    conditions = (
        Condition.DAZED, Condition.IMMOBILIZED, Condition.SLOWED,
        Condition.STUNNED, Condition.WEAKENED,
    )
    _grit_through(c, conditions, 10)


@power(
    "m6439a2",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
)
def m6439a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6439a3",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    target=UpTo(2),
)
def m6439a3(c: Cast) -> None:
    c.use_power("m6439a2", on=c.target, spend=False, again=True)


@power(
    "m6439a4",
    level=9,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m6439a4(c: Cast) -> None:
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    c.teleport(6)
    nearby = [f for f in c.enemies() if c.adjacent(f)]
    for f in nearby:
        c.gains_advantage(lambda ctx, f=f: ctx.get("target") == f, on=c.me, until=When.EOT)
    for _ in range(2):
        foe = c.choose(nearby, f"{c.ref}: target", optional=True) if nearby else None
        if foe is not None:
            c.use_power("m6439a2", on=foe, spend=False, again=True)


# ==========================================================================
# m6683
# ==========================================================================


@power(
    "m6683a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 8),
    dropped=("Power.reach_alt",),
)
def m6683a0(c: Cast) -> None:
    """"Melee 2, or 4 while bloodied." There is no field for an alternate
    reach the way `attack_alt`/`damage_alt` carry an alternate branch; the
    slide half, which does vary, is the body's to write."""
    if c.strike():
        c.hit()
        c.slide(4 if c.bloodied() else 2)


@power(
    "m6683a1",
    level=9,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    on=Trigger(Dropped, about_me, "it drops below 1 hit point"),
)
def m6683a1(c: Cast) -> None:
    c.summon("m6684", at=c.here)


# ==========================================================================
# m872
# ==========================================================================


@power(
    "m872a0",
    level=9,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 4),
)
def m872a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m872a1",
    level=9,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_OTHER,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
    damage=Damage("2d10", 6, kind=LIMITED),
)
def m872a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.slide(1)


@power(
    "m872a2",
    level=9,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.ILLUSION],
    attack=Attack(vs=WILL, printed=12),
)
def m872a2(c: Cast) -> None:
    if c.strike():
        c.grants_advantage(until=When.EONT)


@power(
    "m872a3",
    level=9,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    on=Trigger(AttackDeclared, _feared_at, "it is targeted by a power with the fear keyword"),
)
def m872a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        _step_away_from(c, 4, foe)


@power(
    "m872a4",
    level=9,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m872a4(c: Cast) -> None:
    """"If it shifts at least 1 square during its turn" is a per-turn fact,
    so the watch re-reads a tally cleared each time it steps rather than a
    standing flag that, once true, could never go false again."""
    me = c.me
    shifted: dict[int, bool] = {}

    def noted(ev: TurnStart) -> None:
        if ev.actor == me:
            shifted[me] = False

    c.watch(TurnStart, noted, until=When.ENCOUNTER, on=me, label=f"{c.ref} turn")
    c.bonus(
        "damage", 0, dice="1d6", on=me, until=When.ENCOUNTER,
        when=lambda ctx: _melee_only(ctx) and shifted.get(me, False),
    )

    def tally(_kind: str, _start: Any, _end: Any, steps: int) -> None:
        if steps >= 1:
            shifted[me] = True

    from combat_engine.content.monsters.level_06.skirmishers import _after_moving

    _after_moving(c, tally)
