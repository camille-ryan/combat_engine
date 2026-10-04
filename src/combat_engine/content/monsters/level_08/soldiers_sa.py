"""Monster abilities, level 8, soldiers -- second sweep.

62 stat blocks, 240 rows. `level_08/soldiers.py` holds the earlier sweep of
this level and is not touched here; nine blocks in this brief print no
ability at all (m2815, m3092, m3115, m393, m407, m4885, m4918, m61, m673) and
so have nothing to decorate.

Conventions, the same ones the rest of the tree settled:

* numbers load from `game.db`; the attack line is `Attack(vs=AC, printed=N)`
  exactly as printed, and the damage line is header data so an MM1 block can
  be rescaled to MM3 maths later;
* a trait costs no action, has no target, and arms once at the start of the
  fight, whatever the compendium's action column claims;
* a printed Requirement naming the creature's own kit is not a gate (#366);
* "until the end of the [creature]'s next turn" is `EONT`, which is already
  every condition shortcut's default -- most of this brief's marks, slows
  and immobilizes need no `until=` at all. "Until the end of **its** next
  turn", naming the victim rather than the caster, is the different duration
  `EOTNT`; the two are easy to swap and the difference is real.
* a close burst or blast naming no target set at all takes **enemies**, and
  only "creatures in the blast/burst" written outright takes everyone;
* a handful of these stat blocks misprint a fragment of another identity
  where a flavour sentence named a race or a sibling ref: m1584 prints
  "m719" for its own duration lines, and m1937's own trigger line prints
  "m1936" for itself. Neither word is a name -- both are ref-shaped
  misprints the same way AUTHORING already logs for other levels -- and
  every row below is written against its own ref.

Two gaps this file is the first to need, confirmed absent before marking:

* **No verb blocks standing up.** `c.cannot_shift` exists; nothing equivalent
  stops a prone creature from standing. `grep -n "cannot_stand" cast.py` and
  `vocab.py --brief` both come back empty. m5701a2.
* **No verb keeps a creature's ordinary turn economy after a charge.**
  `actions.py` zeroes `Budget.standard/move/minor` unconditionally once a
  charge resolves, with no override a row can reach. m5858a0.

One more, found while writing: `ConditionApplied` is a plain `Event`, fired
*after* a condition has already landed, while `ForcedMove` is a cancellable
`Decision`. "Makes a saving throw to negate the triggering effect" can only
be answered for the push/pull/slide half of m1937a3's trigger -- there is
nothing to interrupt for the immobilized/restrained half.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.soldiers_sa import (
    _HELPLESS,
    _armed,
    _free_square_beside,
    _is_attack,
    _pinned_enemy_in_reach,
    _prone_enemy_in_reach,
    _recharge_when_bloodied,
    _ref_of,
    _square_of,
    _step_into_vacated,
)
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.soldiers_sa import (
    _adjacent_enemy_shifts,
    _adjacent_foe_looks_away,
    _marked_adjacent_shifts,
    _marked_shifts,
    _secondary,
)
from combat_engine.content.monsters.level_07.soldiers import (
    _aura,
    _hands_free,
    _holding,
    _is_mounted,
    _recharge_on,
)
from combat_engine.content.monsters.level_07.soldiers_sa import (
    _marked_by_me_looks_away,
    _marked_within_looks_away,
    _marked_within_moves_away,
)
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
    OPPORTUNITY,
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
    Damage,
    DamageType,
    Health,
    Keyword,
    Melee,
    Powers,
    Ranged,
    Relation,
    Size,
    Square,
    Stats,
    Target,
    UpTo,
    Usage,
    When,
    Window,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    DamageApplied,
    DamageRolled,
    Dropped,
    ForcedMove,
    Hit,
    Moved,
    MoveStart,
    PowerUsed,
    SavingThrow,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.grid import distance as square_distance
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    creatures,
    distance_between,
    enemies,
    flanked_by,
    has_combat_advantage,
    squares,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me, by_melee

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------

_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.POISON,
)


def _chosen_element(c: Cast) -> DamageType:
    """"Depending on the creature's origin" -- chosen at the table, the same
    shape `level_05/soldiers_sa.py` already settled for a typed rider."""
    return (
        c.choose(list(_ELEMENTS), f"{c.ref}: which element") or DamageType.ACID
    )


def _would_force_move_me(world: World, me: int, ev: ForcedMove) -> bool:
    """`ForcedMove` names its subject `target`, not `actor` -- `about_me`
    reads only the latter and would be false here forever."""
    return getattr(ev, "target", None) == me


def _enemy_shifted_from_beside_me(world: World, me: int, ev: Moved) -> bool:
    """"An adjacent enemy shifts away from it." `Moved` is the one of the
    three move events that carries `from_`, which is the square being
    vacated and the one this row needs to measure "adjacent" against --
    by the time anything else fires the enemy has already left it."""
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or team(world, actor) is team(world, me):
        return False
    if getattr(ev, "kind_", "") != "shift":
        return False
    was = getattr(ev, "from_", None)
    return was is not None and any(square_distance(was, sq) <= 1 for sq in squares(world, me))


def _katar_strike(c: Cast, crit_total: int, *, crit_dtype: DamageType = DamageType.UNTYPED) -> None:
    """The shared katar swing: 1d6+3, maxing to 9 on a crit already. The
    printed crit line is higher than that, and what is written here is only
    the difference -- the bonus the header's own maxing does not cover."""
    if c.strike():
        c.hit()
        if c.crit:
            extra = crit_total - 9
            if extra > 0:
                c.flat(extra, dtype=crit_dtype)


def _katar_flurry(c: Cast) -> None:
    """"Makes two katar attacks" -- identical across the three creatures
    that print it, so the per-target state (two rolls, two possible
    victims) is handled in one pass guarded on `c.first`."""
    if not c.first:
        return
    for victim in c.targets[:2]:
        if _secondary(c, 13, AC, victim):
            c.damage("2d6", 5, on=victim)


def _katar_and_coil(
    c: Cast, crit_total: int, *, crit_dtype: DamageType = DamageType.UNTYPED
) -> None:
    """"Makes a katar attack. If it hits, a secondary attack coils shadow
    around the target." The katar swing is rolled by hand off its own
    numbers, because the card's own structured attack line for this entry
    -- what `cards.py` checks the header against -- is the coil that
    follows it, +11 vs Reflex, and not the swing."""
    victim = c.target
    if victim is None:
        return
    if not _secondary(c, 13, AC, victim):
        return
    c.damage("1d6", 3, on=victim)
    if c.crit:
        extra = crit_total - 9
        if extra > 0:
            c.flat(extra, dtype=crit_dtype)
    if c.strike(on=victim):
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=victim)


def _shadow_teleport(c: Cast) -> None:
    c.teleport(3)
    c.insubstantial(until=When.SONT)


def _slain_rises_as(c: Cast, ref: str, test: Any) -> None:
    """"When it kills [X], the slain creature rises at the start of its
    killer's next turn." `Dropped` names the killer; the rise itself waits
    for that killer's own `TurnStart`, which is the printed timing."""
    me = c.me
    waiting: list[Square] = []

    def slain(ev: Dropped) -> None:
        if ev.source != me or not test(ev.actor):
            return
        sq = _square_of(c, ev.actor)
        if sq is not None:
            waiting.append(sq)

    def rise(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not waiting:
            return
        for sq in waiting:
            c.summon(ref, at=sq)
        waiting.clear()

    c.watch(Dropped, slain, until=When.ENCOUNTER, on=me, label=f"{c.ref} slain")
    c.watch(TurnStart, rise, until=When.ENCOUNTER, on=me, label=f"{c.ref} rise")


def _crit_regains(c: Cast, radius: int, amount: int) -> None:
    """"Whenever it scores a critical hit, it and allies within N squares
    regain H hit points.\""""
    me = c.me

    def rally(ev: Hit) -> None:
        if ev.attacker != me or not ev.critical:
            return
        for who in (me, *[a for a in c.allies() if distance_between(c.world, me, a) <= radius]):
            c.heal(amount, on=who)

    c.watch(Hit, rally, until=When.ENCOUNTER, on=me, label=f"{c.ref} rally")


# ==========================================================================
# m1017
# ==========================================================================


@power(
    "m1017a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=14), damage=Damage("1d8", 5),
)
def m1017a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m1017a1", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=UpTo(2), attack=Attack(vs=AC, printed=13),
    damage=Damage("3d10", 5, kind=LIMITED),
)
def m1017a1(c: Cast) -> None:
    """Two claw attacks against up to two targets, settled together: the
    dazed rider asks about both ("hits a marked target" or "hits the same
    target twice"), which only the whole use can answer."""
    if not c.first:
        return
    hits: dict[int, int] = {}
    for victim in c.targets[:2]:
        if _secondary(c, 13, AC, victim):
            c.damage("3d10", 5, on=victim)
            hits[victim] = hits.get(victim, 0) + 1
    for victim, count in hits.items():
        if count >= 2 or c.marked(on=victim, by=c.me):
            c.dazed(on=victim)


@power(
    "m1017a2", level=8, usage=ENCOUNTER, action=ActionType.NONE, reach=Ranged(10),
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m1017a2(c: Cast) -> None:
    """"One other m1017 of its level or lower" is a kind-and-level search,
    not a target line `Target` can hold -- picked by hand within range."""
    me = c.me
    mate = next(
        (
            a
            for a in c.allies()
            if a != me
            and _ref_of(c, a) == "m1017"
            and distance_between(c.world, me, a) <= 10
            and ((s := c.world.get(a, Stats)) is None or s.level <= c.level)
        ),
        None,
    )
    if mate is None:
        return
    turns_left = [2]

    def grant(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != mate or not turns_left[0]:
            return
        turns_left[0] -= 1
        c.extra_action(cost=STANDARD, on=mate)

    c.watch(TurnStart, grant, until=When.ENCOUNTER, on=me, label="m1017a2 gift")


@power(
    "m1017a3", level=8, usage=AT_WILL, action=INTERRUPT, reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=14), damage=Damage("1d8", 5),
    trigger="an adjacent enemy marked by it shifts",
    on=Trigger(MoveStart, _marked_adjacent_shifts, "an adjacent enemy marked by it shifts"),
)
def m1017a3(c: Cast) -> None:
    """The claw attack is its own line, not a reuse of m1017a0 -- declared
    again here because this one is an interrupt, not a standard action."""
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


@power(
    "m1017a4", level=8, usage=ENCOUNTER, action=ActionType.NONE, reach=PERSONAL,
    target=NO_TARGET,
)
def m1017a4(c: Cast) -> None:
    """The keyword column files this beside "reduced to 0 hit points", but
    the printed sentence is about charging and names nothing about dying;
    the charge line is what is written."""
    c.bonus(
        "damage", 0, dice="1d8", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("charge")),
    )


# ==========================================================================
# m1061
# ==========================================================================


@power(
    "m1061a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d6", 3),
)
def m1061a0(c: Cast) -> None:
    _katar_strike(c, 15)


@power(
    "m1061a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=UpTo(2), keywords=[Keyword.WEAPON],
)
def m1061a1(c: Cast) -> None:
    _katar_flurry(c)


@power(
    "m1061a2", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=11),
)
def m1061a2(c: Cast) -> None:
    _katar_and_coil(c, 15)


@power(
    "m1061a3", level=8, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m1061a3(c: Cast) -> None:
    _shadow_teleport(c)


# ==========================================================================
# m115805
# ==========================================================================


@power(
    "m115805a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL,
    target=NO_TARGET,
)
def m115805a0(c: Cast) -> None:
    me = c.me

    def punish(ev: Hit) -> None:
        if ev.attacker != me or not getattr(ev.result, "advantage", False):
            return
        c.immobilized(until=When.EOTNT, on=ev.target)

    c.watch(Hit, punish, until=When.ENCOUNTER, on=me, label="m115805a0")


@power(
    "m115805a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d8", 7),
)
def m115805a1(c: Cast) -> None:
    """"Effect" is its own labelled line here, so the mark lands on a miss
    too."""
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m115805a2", level=8, usage=AT_WILL, action=INTERRUPT, reach=Melee(1),
    target=NO_TARGET, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d8", 8),
    trigger="an enemy marked by it makes an attack that doesn't include it",
    on=Trigger(PowerUsed, _marked_by_me_looks_away, "a marked enemy attacks without it"),
)
def m115805a2(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
    c.penalty("attack", 2, on=foe, until=When.EOT)


# ==========================================================================
# m115836
# ==========================================================================


@power(
    "m115836a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d10", 8),
)
def m115836a0(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.use_power("m115836a1", on=victim, spend=False)


@power(
    "m115836a1", level=8, usage=AT_WILL, action=MINOR, reach=Melee(1),
    target=ONE_CREATURE, once_per_round=True,
    attack=Attack(vs=FORT, printed=11), damage=Damage("1d6", 0),
)
def m115836a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m115836a2", level=8, usage=AT_WILL, action=INTERRUPT, reach=Melee(1),
    target=NO_TARGET, attack=Attack(vs=REF, printed=11), damage=Damage("1d6", 5),
    trigger="an enemy adjacent to it shifts",
    on=Trigger(MoveStart, _adjacent_enemy_shifts, "an enemy adjacent to it shifts"),
)
def m115836a2(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.immobilized(until=When.EOT, on=foe)
        spot = _free_square_beside(c, c.me)
        if spot is not None:
            c.slide(2, on=foe, to=spot)


# ==========================================================================
# m115847
# ==========================================================================


@power(
    "m115847a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d8", 7),
)
def m115847a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m115847a1", level=8, usage=AT_WILL, action=STANDARD, reach=Ranged(10),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d8", 7),
)
def m115847a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115847a2", level=8, usage=AT_WILL, action=STANDARD, reach=CloseBlast(2),
    target=EACH_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d8", 7),
)
def m115847a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


# ==========================================================================
# m115916
# ==========================================================================


@power(
    "m115916a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL,
    target=NO_TARGET,
)
def m115916a0(c: Cast) -> None:
    """Half damage is a standing watch rather than `c.resist`, so force
    passes it untouched; a radiant hit turns the watch off until its own
    turn starts again."""
    me = c.me
    active = [True]

    def halved(ev: DamageRolled) -> None:
        if ev.target != me or not active[0] or DamageType.FORCE in ev.types():
            return
        ev.amount -= ev.amount // 2

    def shaken(ev: DamageApplied) -> None:
        if ev.target == me and DamageType.RADIANT in ev.types():
            active[0] = False

    def recovers(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor == me:
            active[0] = True

    c.watch(
        DamageRolled, halved, until=When.ENCOUNTER, on=me, window=Window.BEFORE,
        label="m115916a0 half",
    )
    c.watch(DamageApplied, shaken, until=When.ENCOUNTER, on=me, label="m115916a0 shaken")
    c.watch(TurnStart, recovers, until=When.ENCOUNTER, on=me, label="m115916a0 recovers")


@power(
    "m115916a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL,
    target=NO_TARGET,
)
def m115916a1(c: Cast) -> None:
    _slain_rises_as(c, "m115915", lambda who: c.is_kind("humanoid", on=who))


@power(
    "m115916a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=11), damage=Damage("2d8", 2, dtype=DamageType.NECROTIC),
)
def m115916a2(c: Cast) -> None:
    """"Grants combat advantage and takes ongoing damage (save ends both)"
    is two different machineries -- a relation and a Mod -- so they cannot
    share one effect the way `_one_save_for_both` shares a modifier and a
    burn. Two separate save-ends holds is a more generous approximation
    than one, never a stingier one."""
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.SAVE_ENDS)
        c.ongoing(5, DamageType.NECROTIC, until=When.SAVE_ENDS)
    c.mark()


@power(
    "m115916a3", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.ILLUSION],
)
def m115916a3(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m115916a2", on=victim, spend=False)
    if not c.landed:
        return
    me = c.me
    for who in creatures(c.world):
        if who != me and who != victim:
            c.invisible(on=who, to=victim, until=When.SAVE_ENDS)


# ==========================================================================
# m1483
# ==========================================================================


@power(
    "m1483a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=15), damage=Damage("2d6", 7),
)
def m1483a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1483a1", level=8, usage=Usage.RECHARGE, recharge=6, action=INTERRUPT,
    reach=Melee(1), target=NO_TARGET, keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13), damage=Damage("1d6", 5, dtype=DamageType.FIRE, kind=LIMITED),
    trigger="an adjacent enemy shifts",
    on=Trigger(MoveStart, _adjacent_enemy_shifts, "an adjacent enemy shifts"),
)
def m1483a1(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
    c.shift(1)


@power("m1483a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1), target=UpTo(2))
def m1483a2(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:2]:
        if _secondary(c, 15, AC, victim):
            c.damage("2d6", 7, on=victim)


@power(
    "m1483a3", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(2), target=ONE_CREATURE, keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=15), damage=Damage("2d8", 7, dtype=DamageType.FIRE, kind=LIMITED),
)
def m1483a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


# ==========================================================================
# m1506
# ==========================================================================


@power(
    "m1506a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d6", 3),
)
def m1506a0(c: Cast) -> None:
    _katar_strike(c, 17)


@power(
    "m1506a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=UpTo(2), keywords=[Keyword.WEAPON],
)
def m1506a1(c: Cast) -> None:
    _katar_flurry(c)


@power(
    "m1506a2", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=11),
)
def m1506a2(c: Cast) -> None:
    _katar_and_coil(c, 17)


@power("m1506a3", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1506a3(c: Cast) -> None:
    me = c.me

    def flanked_by_me(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and flanked_by(c.world, victim, me)

    for who in (me, *c.allies()):
        c.bonus("damage", 0, dice="1d6", on=who, until=When.ENCOUNTER, when=flanked_by_me)


@power("m1506a4", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1506a4(c: Cast) -> None:
    c.bonus("crit_range", 1, on=c.me, until=When.ENCOUNTER)


@power("m1506a5", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1506a5(c: Cast) -> None:
    _crit_regains(c, 5, 4)


@power(
    "m1506a6", level=8, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m1506a6(c: Cast) -> None:
    _shadow_teleport(c)


# ==========================================================================
# m1584
# ==========================================================================


def _has_ca_in_melee(world: World, eid: int) -> bool:
    return any(
        has_combat_advantage(world, eid, foe) and distance_between(world, eid, foe) <= 1
        for foe in enemies(world, eid)
    )


@power(
    "m1584a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("2d4", 5),
)
def m1584a0(c: Cast) -> None:
    """The duration line prints "m719" where it means itself -- the same
    ref-shaped misprint AUTHORING already logs for other levels."""
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m1584a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=12), damage=Damage("1d4", 5),
)
def m1584a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1584a2", level=8, usage=AT_WILL, action=MINOR, reach=Melee(1),
    target=ONE_CREATURE, once_per_round=True,
    attack=Attack(vs=FORT, printed=12), damage=Damage("1d6", 5),
    requires=_has_ca_in_melee,
    requires_text="it must have combat advantage against an adjacent creature",
)
def m1584a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not has_combat_advantage(c.world, c.me, victim):
        return
    if c.strike():
        c.hit()
        c.half_healing(on=victim, until=When.EONT)


@power(
    "m1584a3", level=8, usage=AT_WILL, action=STANDARD, reach=Ranged(10),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d6", 5),
)
def m1584a3(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m1768
# ==========================================================================


@power(
    "m1768a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15), damage=Damage("2d8", 5),
)
def m1768a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed()


@power(
    "m1768a1", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=CloseBurst(2), target=EACH_ENEMY, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("3d6", 5, kind=LIMITED),
)
def m1768a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed()


@power("m1768a2", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1768a2(c: Cast) -> None:
    me = c.me

    def reward() -> None:
        c.bonus("attack", 2, on=me, until=When.EONT)
        c.bonus("save", 2, on=me, until=When.EONT)

    def crit(ev: Hit) -> None:
        if ev.attacker == me and ev.critical:
            reward()

    def bloodied(ev: Bloodied) -> None:
        if ev.source == me:
            reward()

    c.watch(Hit, crit, until=When.ENCOUNTER, on=me, label="m1768a2 crit")
    c.watch(Bloodied, bloodied, until=When.ENCOUNTER, on=me, label="m1768a2 bloody")


# ==========================================================================
# m1779
# ==========================================================================


@power(
    "m1779a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15), damage=Damage("2d6", 3),
)
def m1779a0(c: Cast) -> None:
    """"Until another creature marks it" is not modelled -- marks from two
    sources are left to coexist rather than one silently replacing the
    other."""
    if c.strike():
        c.hit()
        c.mark(until=When.ENCOUNTER)


@power(
    "m1779a1", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=CloseBurst(1), target=EACH_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("3d10", 5, kind=LIMITED),
)
def m1779a1(c: Cast) -> None:
    """The shift afterwards covers the whole burst, so it is counted and
    spent once rather than once per target. Where it ends -- adjacent to
    somebody else -- is left to the decider, the same as any other bare
    shift in this tree."""
    if not c.first:
        return
    hits = 0
    for victim in c.targets:
        if _secondary(c, 13, AC, victim):
            c.damage("3d10", 5, on=victim)
            hits += 1
    if hits:
        c.shift(hits)


@power(
    "m1779a2", level=8, usage=AT_WILL, action=FREE, reach=PERSONAL, target=NO_TARGET,
    trigger="an adjacent enemy shifts away from it",
    on=Trigger(Moved, _enemy_shifted_from_beside_me, "an adjacent enemy shifts away from it"),
)
def m1779a2(c: Cast) -> None:
    was = getattr(c.trigger, "from_", None)
    _step_into_vacated(c, was)


# ==========================================================================
# m1937
# ==========================================================================


@power(
    "m1937a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.HEALING],
    attack=Attack(vs=AC, printed=15), damage=Damage("1d10", 5),
)
def m1937a0(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    c.damage("1d6", 0, dtype=_chosen_element(c))
    c.grab()
    victim = c.target
    if victim is not None:
        c.spend_surge(on=victim)
    c.heal(5)


@power(
    "m1937a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=Target(side="enemy", count=1, label="creature grabbed by it"),
    attack=Attack(vs=AC, printed=15), damage=Damage("2d6", 5),
    dropped=("Target.kind",),
)
def m1937a1(c: Cast) -> None:
    held = _holding(c)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
    c.shift(3, share=True)
    c.flat(c.roll("1d10") + 5, dtype=DamageType.NECROTIC, on=victim)


@power(
    "m1937a2", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=CloseBlast(5), target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=13), damage=Damage("3d8", 5, kind=LIMITED),
)
def m1937a2(c: Cast) -> None:
    if not c.first:
        return
    element = _chosen_element(c)
    for victim in c.targets:
        if _secondary(c, 13, REF, victim):
            c.damage("3d8", 5, dtype=element, on=victim)


@power(
    "m1937a3", level=8, usage=AT_WILL, action=INTERRUPT, reach=PERSONAL, target=NO_TARGET,
    trigger="it would be immobilized, restrained, pushed, pulled, or slid",
    on=Trigger(ForcedMove, _would_force_move_me, "it would be pushed, pulled, or slid"),
    dropped=("ConditionApplied.cancel",),
)
def m1937a3(c: Cast) -> None:
    """Only the forced-move half can be caught before it lands:
    `ForcedMove` is a cancellable `Decision` and `ConditionApplied` is a
    plain `Event`, announced after the condition is already on -- there is
    nothing to interrupt for the immobilized/restrained half. Its own
    trigger line misprints "m1936" for itself."""
    if c.save(bare=True, on=c.me):
        c.cancel()


@power("m1937a4", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1937a4(c: Cast) -> None:
    """"Free-willed" is not modelled -- the risen copy stands on its
    killer's own side, the same approximation m115916a1 already takes."""
    _slain_rises_as(c, "m1937", lambda who: _ref_of(c, who) == "m1937")


# ==========================================================================
# m1994
# ==========================================================================


@power(
    "m1994a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=15), damage=Damage("1d8", 4, dtype=DamageType.NECROTIC),
)
def m1994a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if _armed(c, "m1994a1 used"):
            c.condition(
                Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=c.target,
                ongoing=(10, DamageType.NECROTIC),
            )
        else:
            c.condition(
                Condition.SLOWED, until=When.SAVE_ENDS, on=c.target,
                ongoing=(5, DamageType.NECROTIC),
            )


@power(
    "m1994a1", level=8, usage=ENCOUNTER, action=ActionType.NONE, reach=CloseBurst(2),
    target=EACH_ENEMY, keywords=[Keyword.NECROTIC, Keyword.ZONE],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m1994a1(c: Cast) -> None:
    """The darkvision exemption on the zone is not modelled -- nothing in
    this tree tracks who has it. The flag this lays is read by m1994a0,
    which is the half of the sentence that upgrades its own burn."""
    me = c.me
    if c.first:
        for eff in list(c.world.effects.of(me)):
            c.world.effects.end(eff, "the darkness rose")
        c.zone(spread({c.here}, 2), until=When.ENCOUNTER, blocks_sight=True, label=f"{c.ref} dark")
        c.effect("m1994a1 used", until=When.ENCOUNTER, on=me)
    c.flat(c.roll("2d6") + 4, dtype=DamageType.NECROTIC, on=c.target)


# ==========================================================================
# m2505
# ==========================================================================


@power(
    "m2505a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d6", 3),
)
def m2505a0(c: Cast) -> None:
    _katar_strike(c, 15, crit_dtype=DamageType.NECROTIC)


@power(
    "m2505a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=UpTo(2), keywords=[Keyword.WEAPON],
)
def m2505a1(c: Cast) -> None:
    _katar_flurry(c)


@power(
    "m2505a2", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=11),
)
def m2505a2(c: Cast) -> None:
    _katar_and_coil(c, 15, crit_dtype=DamageType.NECROTIC)


@power(
    "m2505a3", level=8, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m2505a3(c: Cast) -> None:
    _shadow_teleport(c)


# ==========================================================================
# m2627
# ==========================================================================


@power(
    "m2627a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=15), damage=Damage("1d8", 2),
)
def m2627a0(c: Cast) -> None:
    plus = 1 if c.bloodied(c.me) else 0
    if c.strike(plus=plus):
        c.hit()
        c.slowed()
        c.ongoing(5)


@power("m2627a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m2627a1(c: Cast) -> None:
    """"No penalty from concealment against bloodied targets" is the
    attack-roll penalty concealment imposes, lifted only in that one case."""
    c.ignore_cover(
        on=c.me, until=When.ENCOUNTER, partial=True,
        when=lambda ctx: bool(ctx.get("target")) and c.bloodied(ctx.get("target")),
    )


@power("m2627a2", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m2627a2(c: Cast) -> None:
    c.conceal(on=c.me, until=When.ENCOUNTER, when=lambda _ctx: c.terrain("bright"))


@power("m2627a3", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m2627a3(c: Cast) -> None:
    """Insubstantial and phasing both stand while unbloodied and both come
    off together the moment it crosses the line -- one watch rather than
    two matching ones."""
    me = c.me
    insub = c.insubstantial(on=me, until=When.ENCOUNTER)
    phase = c.phasing(on=me, until=When.ENCOUNTER)

    def falls(ev: Bloodied) -> None:
        if ev.actor != me:
            return
        if insub is not None:
            c.world.effects.end(insub, "bloodied")
        if phase is not None:
            c.world.effects.end(phase, "bloodied")

    c.watch(Bloodied, falls, until=When.ENCOUNTER, on=me, label="m2627a3 watch")


# ==========================================================================
# m3674
# ==========================================================================


@power(
    "m3674a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15), damage=Damage("1d8", 5),
)
def m3674a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m3674a1", level=8, usage=AT_WILL, action=OPPORTUNITY, reach=Melee(1),
    target=NO_TARGET, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15), damage=Damage("1d8", 5),
    trigger="an enemy marked by it moves or shifts",
    on=Trigger(MoveStart, _marked_shifts, "an enemy marked by it moves or shifts"),
)
def m3674a1(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.prone(on=foe)


@power(
    "m3674a2", level=8, usage=ENCOUNTER, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=13), damage=Damage("2d4", 5, kind=LIMITED),
)
def m3674a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.FIRE)


@power(
    "m3674a3", level=8, usage=AT_WILL, action=MINOR, reach=Melee(1),
    target=ONE_CREATURE, once_per_round=True, keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=13), damage=Damage("1d4", 0, dtype=DamageType.FIRE),
)
def m3674a3(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m3780
# ==========================================================================


def _is_dismounted(world: World, eid: int) -> bool:
    return not _is_mounted(world, eid)


@power(
    "m3780a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15), damage=Damage("2d6", 5),
    requires=_is_mounted, requires_text="it must be mounted",
)
def m3780a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3780a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15), damage=Damage("1d8", 7),
)
def m3780a1(c: Cast) -> None:
    if c.strike():
        if c.crit:
            c.damage("2d8", 15)
        else:
            c.hit()


@power(
    "m3780a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=UpTo(2), keywords=[Keyword.WEAPON],
    requires=_is_dismounted, requires_text="it must be dismounted",
)
def m3780a2(c: Cast) -> None:
    """The wider crit range belongs to these two swings only, so it is laid
    before either roll and taken off again once both are made."""
    if not c.first:
        return
    c.bonus("crit_range", 1, on=c.me, until=When.EOT)
    for victim in c.targets[:2]:
        if _secondary(c, 15, AC, victim):
            c.damage("1d8", 7, on=victim)


@power(
    "m3780a3", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON], charges=True,
    attack=Attack(vs=AC, printed=15), damage=Damage("2d6", 5),
    requires=lambda world, eid: _is_mounted(world, eid) and True,
    requires_text="it must be mounted and charging, and must have a lance",
)
def m3780a3(c: Cast) -> None:
    """"Charging" is not a fact about the creature `requires=` can read in
    advance -- the lance half of the Requirement is its own kit and not a
    gate either, per #366."""
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()


@power(
    "m3780a4", level=8, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m3780a4(c: Cast) -> None:
    beast = c.mount()
    c.teleport(5, share=beast is not None)


@power(
    "m3780a5", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    out_of_combat=True,
)
def m3780a5(c: Cast) -> None:
    """Nothing in a fight rolls an athletics, acrobatics, endurance or
    stealth check, and "any special mount abilities it confers" names no
    system this engine has -- the whole printed benefit is out of reach
    for the same reason a lock-picking bonus is, and none of it sits
    beside a combat half, so the row is inert whole rather than
    partially."""


@power(
    "m3780a6", level=8, usage=ENCOUNTER, action=STANDARD, reach=PERSONAL, target=SELF,
    keywords=[Keyword.POLYMORPH],
    requires=_is_dismounted, requires_text="it must be dismounted",
    dropped=("c.reach(set=)",),
)
def m3780a6(c: Cast) -> None:
    """Growing, the push it causes and the damage bonus all play. Its
    melee reach becoming 2 while grown does not: `c.reach` has no setter,
    the same gap `m3783a3` already names."""
    me = c.me
    grown = c.resize(Size.LARGE, on=me, until=When.ENCOUNTER)
    if grown is None:
        return
    here = _square_of(c, me)
    if here is not None:
        for sq in squares(c.world, me):
            occ = c.world.grid.occupant(sq)
            if occ is not None and occ != me:
                c.push(1, on=occ)
    c.bonus(
        "damage", 5, on=me, until=When.ENCOUNTER,
        when=lambda _ctx: grown in c.world.effects.of(me),
    )
    c.endable(grown, cost=FREE)


# ==========================================================================
# m4012
# ==========================================================================


@power(
    "m4012a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15), damage=Damage("1d8", 4, dtype=DamageType.FIRE),
)
def m4012a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m4012a1", level=8, usage=AT_WILL, action=MINOR, reach=Melee(1),
    target=Target(side="enemy", count=1, label="creature grabbed by it"),
    once_per_round=True, keywords=[Keyword.FIRE],
    attack=Attack(vs=FORT, printed=13), damage=Damage("1d6", 5),
    dropped=("Target.kind",),
)
def m4012a1(c: Cast) -> None:
    held = _holding(c)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.damage("1d4", 0, dtype=DamageType.FIRE, on=victim)


@power(
    "m4012a2", level=8, usage=AT_WILL, action=MINOR, reach=Melee(1),
    target=ONE_CREATURE, once_per_round=True, keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13), damage=Damage("1d8", 4),
)
def m4012a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d4", 0, dtype=DamageType.FIRE)
        c.grab()


@power("m4012a3", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4012a3(c: Cast) -> None:
    me = c.me

    def scorched(ev: Hit) -> None:
        if ev.target != me or not by_melee(c.world, me, ev):
            return
        c.vulnerable(5, DamageType.FIRE, until=When.EONT, on=ev.attacker)

    c.watch(Hit, scorched, until=When.ENCOUNTER, on=me, label="m4012a3")


# ==========================================================================
# m4165
# ==========================================================================


@power(
    "m4165a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=15), damage=Damage("1d10", 6),
)
def m4165a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", 0, dtype=DamageType.ACID)


@power(
    "m4165a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=15), damage=Damage("1d8", 6),
)
def m4165a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power("m4165a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2), target=UpTo(3))
def m4165a2(c: Cast) -> None:
    """Two claws and a bite, each at its own printed line: the claws reuse
    m4165a0's and the bite reuses m4165a1's, rolled directly against up to
    three targets."""
    if not c.first:
        return
    lines = [("1d10", 6, DamageType.ACID), ("1d10", 6, DamageType.ACID), ("1d8", 6, None)]
    for victim, (dice, bonus, dtype) in zip(c.targets[:3], lines, strict=False):
        if _secondary(c, 15, AC, victim):
            c.damage(dice, bonus, on=victim)
            if dtype is not None:
                c.damage("1d6", 0, dtype=dtype, on=victim)


@power(
    "m4165a3", level=8, usage=Usage.RECHARGE, recharge=0, action=STANDARD,
    reach=CloseBlast(5), target=EACH_ENEMY, keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 4, dtype=DamageType.ACID, kind=LIMITED),
)
def m4165a3(c: Cast) -> None:
    """Recharges when a companion it summoned drops to 0, not on a die --
    the number stays 0 in the header because there is no die to roll; the
    watch below is what actually brings it back."""
    me = c.me
    if c.first and not _armed(c, "m4165a3 recharge"):
        def spirit_fell(ev: Dropped) -> None:
            if _ref_of(c, ev.actor) == "m4166" and ev.actor in [
                who for who in creatures(c.world)
            ]:
                c.restore_use("m4165a3", on=me)

        c.watch(Dropped, spirit_fell, until=When.ENCOUNTER, on=me, label="m4165a3 recharge")
    if c.strike():
        c.hit()
        spot = next(iter(sorted(c.area())), None)
        if spot is not None:
            c.summon("m4166", at=spot)


@power(
    "m4165a4", level=8, usage=ENCOUNTER, action=FREE, reach=PERSONAL, target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m4165a4(c: Cast) -> None:
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m4165a3")
    c.use_power("m4165a3", spend=False)


@power(
    "m4165a5", level=8, usage=ENCOUNTER, action=STANDARD, reach=CloseBurst(5),
    target=EACH_ENEMY, keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=13),
)
def m4165a5(c: Cast) -> None:
    if c.strike():
        hold = c.stunned()
        victim = c.target
        if hold is not None and victim is not None:
            def aftermath() -> None:
                c.penalty("attack", 2, on=victim, until=When.SAVE_ENDS)

            hold.on_end.append(aftermath)


# ==========================================================================
# m4296
# ==========================================================================


@power(
    "m4296a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=REF, printed=15), damage=Damage("2d6", 2),
)
def m4296a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m4296a1", level=8, usage=ENCOUNTER, action=STANDARD, reach=CloseBurst(3),
    target=Target(side="enemy", count=99, everyone=True, label="slowed or immobilized creature"),
    attack=Attack(vs=FORT, printed=11), dropped=("Target.kind",),
)
def m4296a1(c: Cast) -> None:
    """Buries a creature already slowed or pinned down.

    Aimed rather than abandoned: `Target` cannot filter on a condition, so the
    chooser hands this row whoever is nearest, and returning threw it away while
    somebody else in the burst qualified. `Target.kind` is the gap, as it is for
    the 112 other rows of this shape.
    """
    victim = _restricted_to(
        c, 3, lambda f: c.is_(Condition.SLOWED, f) or c.is_(Condition.IMMOBILIZED, f)
    )
    if victim is None:
        return
    hold = c.effect(f"{c.ref} buried", until=When.SAVE_ENDS, on=victim)
    if hold is None or not c.strike(on=victim):
        return
    c.condition(Condition.RESTRAINED, Condition.BLINDED, until=When.SAVE_ENDS, on=victim)

    def failed(ev: SavingThrow) -> None:
        if ev.actor == victim and not ev.saved:
            c.flat(5, on=victim)
            c.heal(5)

    c.watch(SavingThrow, failed, until=When.SAVE_ENDS, on=c.me, label=f"{c.ref} grind")

    def half_buried() -> None:
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim)
        c.prone(on=victim)

    hold.on_end.append(half_buried)


@power("m4296a2", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4296a2(c: Cast) -> None:
    me = c.me

    def exposed(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return (
            victim is not None
            and not ctx.get("ranged")
            and has_combat_advantage(c.world, me, victim)
        )

    c.bonus("damage", 0, dice="1d6", on=me, until=When.ENCOUNTER, when=exposed)


@power("m4296a3", level=8, usage=AT_WILL, action=MOVE, reach=PERSONAL, target=SELF)
def m4296a3(c: Cast) -> None:
    c.shift(1)
    c.move(2, at="burrow")


# ==========================================================================
# m4308
# ==========================================================================


@power(
    "m4308a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15), damage=Damage("1d8", 8),
)
def m4308a0(c: Cast) -> None:
    """"+17 against bloodied targets" is this creature's own edge against
    the target's state, not the caster's -- `c.bloodied(victim)`, asked
    before the roll, same as every other target-bloodied edge in this
    tree."""
    victim = c.target
    plus = 2 if victim is not None and c.bloodied(victim) else 0
    if c.strike(plus=plus):
        c.hit()
        c.mark()


@power(
    "m4308a1", level=8, usage=AT_WILL, action=INTERRUPT, reach=Melee(1),
    target=NO_TARGET, trigger="an enemy marked by it shifts",
    on=Trigger(MoveStart, _marked_shifts, "an enemy marked by it shifts"),
)
def m4308a1(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None:
        c.basic(on=foe)


# ==========================================================================
# m4370
# ==========================================================================


@power(
    "m4370a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d10", 5),
)
def m4370a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power("m4370a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1), target=UpTo(2))
def m4370a1(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:2]:
        c.basic(on=victim)


@power(
    "m4370a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=Target(side="enemy", count=1, label="enemy marked by it"),
    keywords=[Keyword.WEAPON], attack=Attack(vs=AC, printed=13), damage=Damage("3d10", 5),
    dropped=("Target.kind",),
)
def m4370a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.marked(on=victim, by=c.me):
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.immobilized(until=When.SAVE_ENDS, on=victim)


@power(
    "m4370a3", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=CloseBlast(5), target=EACH_ENEMY, keywords=[Keyword.RADIANT],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d8", 5, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m4370a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()
    if c.last:
        for mate in c.within(5, of=c.me, side="ally"):
            c.temp_hp(10, on=mate)
        c.temp_hp(10, on=c.me)


@power(
    "m4370a4", level=8, usage=AT_WILL, action=INTERRUPT, reach=CloseBurst(10),
    target=NO_TARGET, keywords=[Keyword.FEAR, Keyword.GAZE, Keyword.RADIANT],
    attack=Attack(vs=WILL, printed=12), damage=Damage("1d8", 3, dtype=DamageType.RADIANT),
    trigger="an enemy marked by her makes an attack that doesn't include her",
    on=Trigger(
        PowerUsed, _marked_within_looks_away(10), "a marked enemy within 10 attacks without her"
    ),
)
def m4370a4(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.penalty("damage", 2, on=foe, until=When.EONT)


@power(
    "m4370a5", level=8, usage=AT_WILL, action=MINOR, reach=PERSONAL, target=SELF,
    keywords=[Keyword.POLYMORPH], out_of_combat=True,
)
def m4370a5(c: Cast) -> None:
    """A disguise with no stated mechanical change -- nothing in a fight
    asks what shape she is wearing."""


# ==========================================================================
# m4382
# ==========================================================================


@power(
    "m4382a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.LIGHTNING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15), damage=Damage("2d8", 3, dtype=DamageType.LIGHTNING),
)
def m4382a0(c: Cast) -> None:
    """"Until another mark supersedes this one" is the one-mark-at-a-time
    shape `m3820a4` already settled -- the previous target's mark comes off
    by hand before this one is laid."""
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            me, ref = c.me, c.ref
            for old in list(c.world.relations.targets(Relation.MARKED_BY, me)):
                if old == victim:
                    continue
                for eff in list(c.world.effects.of(old)):
                    if eff.label == f"{ref} mark":
                        c.world.effects.end(eff, ref)
            c.mark(until=When.ENCOUNTER, on=victim)


@power(
    "m4382a1", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.LIGHTNING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 3, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m4382a1(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is None:
        return
    spot = _free_square_beside(c, c.me)
    if spot is not None:
        c.teleport(8, who=victim, to=spot)
    for foe in list(c.enemies()):
        if foe != victim and c.adjacent_to(foe, victim) and _secondary(c, 15, AC, foe):
            c.damage("2d8", 3, dtype=DamageType.LIGHTNING, on=foe)


def _marked_within_hit_without_me(radius: int) -> Any:
    """"A marked enemy within N squares hits with an attack that doesn't
    include it" -- `Hit` rather than `PowerUsed`, because the printed line
    asks whether the swing *landed* elsewhere, not merely that one was
    made."""

    def gate(world: World, me: int, ev: Hit) -> bool:
        foe = getattr(ev, "attacker", None)
        if foe is None or foe == me or ev.target == me:
            return False
        if not world.relations.holds(Relation.MARKED_BY, me, foe):
            return False
        return distance_between(world, me, foe) <= radius

    return gate


@power(
    "m4382a2", level=8, usage=AT_WILL, action=REACTION, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=(
        "an enemy marked by it and within 10 squares hits with an attack "
        "that doesn't include it"
    ),
    on=Trigger(Hit, _marked_within_hit_without_me(10), "a marked enemy within 10 hits without it"),
)
def m4382a2(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    spot = _free_square_beside(c, foe)
    if spot is not None:
        c.teleport(10, to=spot)
    c.basic(on=foe)


@power(
    "m4382a3", level=8, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=SELF,
)
def m4382a3(c: Cast) -> None:
    """"Ignoring difficult and hazardous terrain and squeezing penalties"
    is three separate exemptions, all for this one move."""
    c.ignores_difficult(on=c.me, until=When.EOT)
    c.shift(6)


# ==========================================================================
# m4749
# ==========================================================================


@power(
    "m4749a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d12", 8),
)
def m4749a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m4749a1", level=8, usage=AT_WILL, action=STANDARD, reach=Ranged(10),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11), damage=Damage("1d8", 8),
)
def m4749a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4749a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d12", 8),
)
def m4749a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(2)
    c.use_power("m4749a0", on=c.target, spend=False)


@power(
    "m4749a3", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=CloseBurst(2), target=EACH_ENEMY, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d12", 6, kind=LIMITED),
)
def m4749a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4749a4", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Ranged(10), target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=11), damage=Damage("2d8", 8, kind=LIMITED),
)
def m4749a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            c.bonus(
                "crit_range", 3, on=c.me, until=When.ENCOUNTER,
                when=lambda ctx, v=victim: ctx.get("target") == v,
            )


@power(
    "m4749a5", level=8, usage=AT_WILL, action=REACTION, reach=Ranged(5),
    target=NO_TARGET, keywords=[Keyword.HEALING],
)
def m4749a5(c: Cast) -> None:
    """"A m4749 ally or any ally within range" is read as any ally within
    5 squares, since the first half of the sentence names only itself
    again."""
    me = c.me

    def rewarded(ev: Hit) -> None:
        if not ev.critical:
            return
        if ev.attacker != me and distance_between(c.world, me, ev.attacker) > 5:
            return
        if team(c.world, ev.attacker) is not team(c.world, me):
            return
        c.heal(10, on=ev.attacker)

    c.watch(Hit, rewarded, until=When.ENCOUNTER, on=me, label="m4749a5")


# ==========================================================================
# m4755
# ==========================================================================


@power(
    "m4755a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15), damage=Damage("2d6", 5),
)
def m4755a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m4755a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.DISEASE],
    attack=Attack(vs=FORT, printed=13), damage=Damage("2d6", 5),
    requires=_hands_free, requires_text="it must not be grabbing a creature",
)
def m4755a1(c: Cast) -> None:
    """The disease itself is out of combat's reach -- nothing here tracks
    a progression outside the fight -- so only the grab and the secondary
    attack play."""
    if not c.strike():
        return
    c.hit()
    c.grab()
    victim = c.target
    if victim is not None:
        _secondary(c, 19, WILL, victim)


@power(
    "m4755a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=Target(side="enemy", count=1, label="creature grabbed by it"),
    damage=Damage("2d8", 4), dropped=("Target.kind",),
)
def m4755a2(c: Cast) -> None:
    held = _holding(c)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is not None:
        c.damage("2d8", 4, on=victim)


@power(
    "m4755a3", level=8, usage=Usage.RECHARGE, recharge=6, action=INTERRUPT,
    reach=PERSONAL, target=NO_TARGET,
    trigger="it is hit by a melee attack",
    on=Trigger(
        Hit, lambda w, me, ev: ev.target == me and by_melee(w, me, ev),
        "a melee attack hits it",
    ),
)
def m4755a3(c: Cast) -> None:
    c.halve()
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.basic(on=foe)


@power(
    "m4755a4", level=8, usage=AT_WILL, action=MINOR, reach=PERSONAL, target=SELF,
    keywords=[Keyword.POLYMORPH], out_of_combat=True,
)
def m4755a4(c: Cast) -> None:
    """The alternate forms carry no stated mechanical difference in this
    brief -- the shapeshift itself is cosmetic here."""


# ==========================================================================
# m5096
# ==========================================================================


@power("m5096a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5096a0(c: Cast) -> None:
    """A second immediate action while bloodied: `Encounter.spend` is
    what limits one to a round, so the exemption is read where that is
    enforced rather than modelled with a second budget."""
    me = c.me
    c.bonus("immediate_actions", 1, on=me, until=When.ENCOUNTER, when=lambda _ctx: c.bloodied(me))


@power("m5096a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5096a1(c: Cast) -> None:
    me = c.me

    def drained(ev: Hit) -> None:
        if ev.attacker != me or not c.world.relations.holds(Relation.MARKED_BY, me, ev.target):
            return
        c.spend_surge(on=ev.target)

    c.watch(Hit, drained, until=When.ENCOUNTER, on=me, label="m5096a1")


@power(
    "m5096a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d10", 5),
)
def m5096a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m5096a3", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=CloseBurst(1), target=EACH_ENEMY, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d10", 10, kind=LIMITED),
)
def m5096a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m5096a4", level=8, usage=AT_WILL, action=INTERRUPT, reach=Melee(1),
    target=NO_TARGET, keywords=[Keyword.WEAPON],
    trigger="an enemy adjacent to it shifts",
    on=Trigger(MoveStart, _adjacent_enemy_shifts, "an enemy adjacent to it shifts"),
)
def m5096a4(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None:
        c.basic(on=foe)


# ==========================================================================
# m5128
# ==========================================================================


@power("m5128a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5128a0(c: Cast) -> None:
    me = c.me

    def toll(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me or team(c.world, ev.actor) is team(c.world, me):
            return
        if distance_between(c.world, me, ev.actor) <= 1:
            c.mark(until=When.EONT, on=ev.actor)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label="m5128a0 aura")


@power("m5128a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5128a1(c: Cast) -> None:
    c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)


@power(
    "m5128a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=13), damage=Damage("2d8", 7),
)
def m5128a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5128a3", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=13), damage=Damage("2d8", 7),
    requires=_hands_free, requires_text="it must not have a creature grabbed",
    dropped=("c.grab(dc=)",),
)
def m5128a3(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        c.pull(1)
        if victim is not None and c.adjacent(victim):
            c.grab()


@power(
    "m5128a4", level=8, usage=AT_WILL, action=MINOR, reach=PERSONAL, target=NO_TARGET,
    once_per_round=True, keywords=[Keyword.NECROTIC],
)
def m5128a4(c: Cast) -> None:
    """A bloodied Requirement is a board fact, not its own kit -- asked
    live rather than gated, since it can stop being true mid-fight."""
    if not c.bloodied(c.me):
        return
    held = _holding(c)
    if not held:
        return
    victim = held[0]
    c.damage("1d8", 4, dtype=DamageType.NECROTIC, on=victim)
    c.save(bare=True, on=c.me)


@power(
    "m5128a5", level=8, usage=ENCOUNTER, uses=2, action=FREE, reach=PERSONAL,
    target=NO_TARGET,
    trigger="it takes acid, cold, fire, lightning, or thunder damage",
    on=Trigger(
        DamageApplied,
        lambda w, me, ev: ev.target == me
        and bool(
            set(ev.types())
            & {
                DamageType.ACID, DamageType.COLD, DamageType.FIRE,
                DamageType.LIGHTNING, DamageType.THUNDER,
            }
        ),
        "it takes acid, cold, fire, lightning, or thunder damage",
    ),
)
def m5128a5(c: Cast) -> None:
    hit_types = set(getattr(c.trigger, "types", lambda: ())())
    elements = hit_types & {
        DamageType.ACID, DamageType.COLD, DamageType.FIRE, DamageType.LIGHTNING, DamageType.THUNDER,
    }
    for dtype in elements:
        c.resist(5, dtype, on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m5325
# ==========================================================================


@power("m5325a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5325a0(c: Cast) -> None:
    me = c.me
    c.bonus(
        "damage", 0, dice="1d6", on=me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("target")) and c.bloodied(ctx.get("target")),
    )


@power(
    "m5325a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d8", 7),
)
def m5325a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5325a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=Target(side="enemy", count=1, label="creature marked by it"),
    keywords=[Keyword.WEAPON], attack=Attack(vs=AC, printed=15), damage=Damage("2d8", 7),
    dropped=("Target.kind",),
)
def m5325a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.marked(on=victim, by=c.me):
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.immobilized(on=victim)


@power(
    "m5325a3", level=8, usage=AT_WILL, action=MINOR, reach=CloseBurst(5),
    target=EACH_ENEMY, once_per_round=True, keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=9),
)
def m5325a3(c: Cast) -> None:
    if c.strike():
        c.pull(3)
        c.mark()


# ==========================================================================
# m5527
# ==========================================================================


@power("m5527a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5527a0(c: Cast) -> None:
    c.resist_forced(1, on=c.me, until=When.ENCOUNTER)


@power("m5527a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5527a1(c: Cast) -> None:
    """The same save-to-stay-up trait `level_02/artillery_sa.py` already
    wrote for a different creature."""
    from combat_engine.content.monsters.level_02.artillery_sa import _saves_off_prone

    _saves_off_prone(c)


@power(
    "m5527a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("4d4", 6),
)
def m5527a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m5527a3", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=11), damage=Damage("2d8", 7),
)
def m5527a3(c: Cast) -> None:
    """"Falls prone if it moves more than half its speed" is a window
    rather than a condition -- watched on the move itself, for the rest of
    this creature's own next turn."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    me = c.me
    threshold = max(1, c.speed_of(victim) // 2)

    def overextended(ev: Moved) -> None:
        if ev.actor != victim:
            return
        if getattr(ev, "kind_", "") in ("walk", "run", "shift") and ev.squares > threshold:
            c.prone(on=victim)

    c.watch(Moved, overextended, until=When.EONT, on=me, label="m5527a3")


@power(
    "m5527a4", level=8, usage=ENCOUNTER, action=MINOR, reach=Ranged(5),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=11),
)
def m5527a4(c: Cast) -> None:
    if c.strike():
        c.prone()
        c.immobilized()


@power(
    "m5527a5", level=8, usage=AT_WILL, action=INTERRUPT, reach=PERSONAL, target=NO_TARGET,
    trigger="an enemy marked by it shifts away from a square adjacent to it",
    on=Trigger(
        MoveStart, _marked_adjacent_shifts, "an enemy marked by it shifts away from beside it"
    ),
)
def m5527a5(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None:
        c.use_power("m5527a3", on=foe, spend=False)


# ==========================================================================
# m5582
# ==========================================================================


@power("m5582a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5582a0(c: Cast) -> None:
    me = c.me
    _aura(
        c, 10,
        lambda who: who != me,
        lambda who: c.vulnerable(5, None, until=When.ENCOUNTER, on=who),
    )


@power(
    "m5582a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=15), damage=Damage("2d6", 5),
    dropped=("c.grab(dc=)",),
)
def m5582a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m5582a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=Target(side="enemy", count=1, label="immobilized, stunned, or unconscious creature"),
    keywords=[Keyword.HEALING], attack=Attack(vs=AC, printed=13), damage=Damage("3d8", 5),
    requires=_pinned_enemy_in_reach,
    requires_text="an adjacent enemy must be immobilized, stunned, or unconscious",
    dropped=("Target.kind",),
)
def m5582a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not any(c.is_(held, victim) for held in _HELPLESS):
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.dazed(until=When.SAVE_ENDS, on=victim)
        c.heal(10)


@power("m5582a3", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1), target=EACH_ENEMY)
def m5582a3(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.adjacent(victim) and _secondary(c, 15, AC, victim):
        c.damage("2d6", 5, on=victim)


@power(
    "m5582a4", level=8, usage=ENCOUNTER, action=STANDARD, reach=CloseBurst(2),
    target=EACH_CREATURE, attack=Attack(vs=AC, printed=13), damage=Damage("3d8", 5),
)
def m5582a4(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.pull(1, on=victim)
    use_result = c.use_power("m5582a2", on=victim, spend=False)
    # "Even if the target is not immobilized, stunned, or unconscious": the
    # borrowed row's own gate would refuse that, so the attack is rolled
    # here directly instead of delegating to it.
    if not use_result and c.strike(on=victim):
        c.hit(on=victim)
        c.dazed(until=When.SAVE_ENDS, on=victim)
        c.heal(10)


@power(
    "m5582a5", level=8, usage=AT_WILL, action=MINOR, reach=CloseBlast(2),
    target=ONE_CREATURE, once_per_round=True, keywords=[Keyword.CHARM, Keyword.HEALING],
    attack=Attack(vs=WILL, printed=13),
)
def m5582a5(c: Cast) -> None:
    """"The target of the m5582a5 attack can choose to be hit automatically"
    hands a decision to a controlled creature this engine never asks; the
    forced basic swing and the temporary hit points both play."""
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    foe = next((f for f in c.enemies() if f != victim), None)
    if foe is None:
        return
    landed = c.basic(on=foe, who=victim)
    if landed:
        c.temp_hp(10, on=victim)


@power(
    "m5582a6", level=8, usage=AT_WILL, action=INTERRUPT, reach=Melee(1),
    target=NO_TARGET, attack=Attack(vs=AC, printed=15), damage=Damage("1d8", 5),
    trigger="a grabbed creature attempts to escape",
    on=Trigger(
        PowerUsed,
        lambda w, me, ev: ev.actor in w.relations.targets(Relation.GRABBED_BY, me),
        "a creature it is grabbing attempts to escape",
    ),
)
def m5582a6(c: Cast) -> None:
    """Asked loosely -- any action by a creature it is grabbing, since
    `PowerUsed` is what this tree watches escape attempts through and the
    event does not say which kind of action was spent."""
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


# ==========================================================================
# m5594
# ==========================================================================


@power(
    "m5594a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d8", 8),
)
def m5594a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5594a1", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.HEALING],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d8", 8, kind=LIMITED),
)
def m5594a1(c: Cast) -> None:
    """A miss recharges this very row, so the restore happens from inside
    its own failed use rather than from a watch on somebody else's turn."""
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)
        held = c.ongoing(5, on=c.target, until=When.SAVE_ENDS)
        victim = c.target
        if held is not None and victim is not None:
            me = c.me

            def paid(ev: DamageApplied) -> None:
                if ev.target != victim or ev.detail != "m5594a1 ongoing":
                    return
                mate = next(
                    (
                        who
                        for who in creatures(c.world)
                        if who != me and (c.is_kind("fey", on=who) or c.is_kind("plant", on=who))
                        and team(c.world, who) is not team(c.world, victim)
                    ),
                    None,
                )
                if mate is not None:
                    c.heal(ev.amount, on=mate)

            c.watch(DamageApplied, paid, until=When.SAVE_ENDS, on=c.me, label="m5594a1 feed")
    else:
        known = c.world.get(c.me, Powers)
        if known is not None:
            known.restore("m5594a1")


@power(
    "m5594a2", level=8, usage=ENCOUNTER, action=MINOR, reach=CloseBurst(2),
    target=ONE_CREATURE, keywords=[Keyword.CHARM],
    narrative=("skill:nature",),
)
def m5594a2(c: Cast) -> None:
    """The Nature check that halves the penalty-to-saves clause rolls
    nothing a fight consults -- the penalty itself plays without it."""
    victim = c.target
    if victim is None:
        return
    for what in (AC, FORT, REF, WILL, "attack"):
        c.penalty(what, 2, on=victim, until=When.SAVE_ENDS)


# ==========================================================================
# m5624
# ==========================================================================


@power("m5624a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5624a0(c: Cast) -> None:
    """"Against creatures other than marchers" is a kind word this card's
    own text supplies no ref for -- read as "other than it", the one
    reading that needs no name."""
    me = c.me
    _aura(
        c, 2,
        lambda who: who != me and team(c.world, who) is not team(c.world, me),
        lambda who: c.penalty(
            "attack", 2, on=who, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("target") != me,
        ),
    )


@power(
    "m5624a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    todo=("c.blocks_entry()",),
)
def m5624a1(c: Cast) -> None:
    """Ordinary movement already cannot end inside an occupied square, so
    the only thing this trait could add is closing the exception phasing
    and teleportation normally open -- `c.shares_space` is the opposite
    shape, letting entry happen as difficult terrain, which is not this
    card. Nothing here plays."""


@power(
    "m5624a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("3d6", 5),
)
def m5624a2(c: Cast) -> None:
    """The opportunity half -- using this against a target that shifts
    before its own next turn -- is the standing `c.threatens` shape rather
    than a second declared row, since the card names no separate line for
    it."""
    if c.strike():
        c.hit()
    c.threatens(2, on=c.me, until=When.EONT)


@power("m5624a3", level=8, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=SELF)
def m5624a3(c: Cast) -> None:
    for cnd in (Condition.SLOWED, Condition.IMMOBILIZED):
        c.cure(cnd)
    c.ignores_difficult(on=c.me, until=When.EOT)
    c.shift(5)


@power(
    "m5624a4", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
    todo=("spec.monster_ref()",),
)
def m5624a4(c: Cast) -> None:
    """It is already at 0 hit points by the time this fires -- nothing
    needs saying for "is destroyed", the same reading `level_05/brutes_sa.py`
    already settled. The four creatures that appear in its place name a
    kind with no ref in this tree, the same gap `m1042a2` already waits
    on."""


# ==========================================================================
# m5628
# ==========================================================================


@power("m5628a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5628a0(c: Cast) -> None:
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


@power("m5628a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5628a1(c: Cast) -> None:
    me = c.me

    def scorched(ev: DamageApplied) -> None:
        if ev.target == me and DamageType.FIRE in ev.types():
            c.ongoing(5, DamageType.FIRE, until=When.SAVE_ENDS, on=me)

    c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label="m5628a1")


@power(
    "m5628a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=13), damage=Damage("1d12", 10),
)
def m5628a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m5628a3", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2), target=UpTo(2))
def m5628a3(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:2]:
        if _secondary(c, 13, AC, victim):
            c.damage("1d12", 10, on=victim)


@power(
    "m5628a4", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=CloseBlast(3), target=EACH_CREATURE, keywords=[Keyword.COLD],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d12", 5, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
)
def m5628a4(c: Cast) -> None:
    """"Recharge when first bloodied" is on top of the die, the same two
    ways back `_recharge_when_bloodied` already settled."""
    if c.first:
        _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


def _enemy_within_looks_away(radius: int) -> Any:
    """"An enemy within N squares uses an attack power that doesn't include
    it" -- `_marked_within_looks_away`'s unmarked cousin: distance and
    attack-hood are the only two narrowings this card prints."""

    def gate(world: World, me: int, ev: PowerUsed) -> bool:
        actor = getattr(ev, "actor", None)
        if actor is None or actor == me or team(world, actor) is team(world, me):
            return False
        if distance_between(world, me, actor) > radius or not _is_attack(ev.power):
            return False
        return me not in getattr(ev, "targets", ())

    return gate


@power(
    "m5628a5", level=8, usage=AT_WILL, action=OPPORTUNITY, reach=Melee(2),
    target=NO_TARGET, attack=Attack(vs=REF, printed=11), damage=Damage("2d12", 3),
    trigger="an enemy within 2 squares uses an attack power that doesn't include it",
    on=Trigger(PowerUsed, _enemy_within_looks_away(2), "an enemy within 2 attacks without it"),
)
def m5628a5(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


@power(
    "m5628a6", level=8, usage=ENCOUNTER, action=FREE, reach=CloseBurst(5),
    target=NO_TARGET, keywords=[Keyword.COLD],
    trigger="an enemy within 5 squares hits it with an attack",
    on=Trigger(
        Hit,
        lambda w, me, ev: ev.target == me and getattr(ev, "attacker", None) is not None,
        "an enemy hits it",
    ),
)
def m5628a6(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.flat(10, dtype=DamageType.COLD, on=foe)
        c.push(2, on=foe)


# ==========================================================================
# m4747
# ==========================================================================


def _declared_melee_attack(world: World, me: int, ev: AttackDeclared) -> bool:
    if getattr(ev, "attacker", None) != me:
        return False
    row = get(getattr(ev, "power", "") or "")
    return row is not None and row.reach.kind == "melee"


@power(
    "m4747a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15), damage=Damage("1d8", 5),
)
def m4747a0(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
    if victim is not None and _secondary(c, 13, FORT, victim):
        c.ongoing(5, DamageType.POISON, on=victim, until=When.SAVE_ENDS)


@power(
    "m4747a1", level=8, usage=AT_WILL, action=FREE, reach=PERSONAL, target=NO_TARGET,
    once_per_round=True,
    trigger="it makes a melee attack",
    on=Trigger(AttackDeclared, _declared_melee_attack, "it makes a melee attack"),
)
def m4747a1(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    mate = next(
        (a for a in c.allies() if _ref_of(c, a) == "m6618" and c.adjacent_to(a, victim)),
        None,
    )
    if mate is not None:
        c.basic(on=victim, who=mate)


# ==========================================================================
# m5646
# ==========================================================================


@power("m5646a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5646a0(c: Cast) -> None:
    me = c.me

    def mobbed(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None:
            return False
        return len([a for a in c.allies() if a != me and c.adjacent_to(a, victim)]) >= 2

    c.bonus("damage", 5, on=me, until=When.ENCOUNTER, when=mobbed)


@power(
    "m5646a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=13), damage=Damage("2d8", 7),
)
def m5646a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m5646a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, attack=Attack(vs=REF, printed=11), damage=Damage("1d12", 8),
    requires=_hands_free, requires_text="it must have no creature grabbed",
    dropped=("c.grab(dc=)",),
)
def m5646a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m5646a3", level=8, usage=Usage.RECHARGE, recharge=6, action=MINOR,
    target=Target(side="enemy", count=1, label="creature grabbed by it"),
    reach=Melee(1), attack=Attack(vs=FORT, printed=11), damage=Damage("1d6", 3, kind=LIMITED),
    dropped=("Target.kind",),
)
def m5646a3(c: Cast) -> None:
    if c.first:
        _recharge_when_bloodied(c)
    held = _holding(c)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is not None and c.strike(on=victim):
        c.hit(on=victim)
        c.blinded(until=When.SAVE_ENDS, on=victim)


# ==========================================================================
# m5666
# ==========================================================================


@power("m5666a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5666a0(c: Cast) -> None:
    me = c.me
    suppressed = [False]

    def tick(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        if suppressed[0]:
            suppressed[0] = False
            return
        body = c.world.get(me, Health)
        if body is not None and body.hp > 0:
            c.heal(5, on=me)

    def scorched(ev: DamageApplied) -> None:
        if ev.target == me and bool({DamageType.FIRE, DamageType.ACID} & set(ev.types())):
            suppressed[0] = True

    c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label="m5666a0 regen")
    c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label="m5666a0 scorched")


@power("m5666a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5666a1(c: Cast) -> None:
    """The same shape `m3533a3` already settled: `Dropped` names the blow,
    not what struck it, so the finishing damage type is read off the
    `DamageApplied` immediately before it."""
    me = c.me
    c.revives_unless(DamageType.ACID, DamageType.FIRE, on=me)
    finished = {"yes": False}

    def took(ev: DamageApplied) -> None:
        if ev.target == me:
            finished["yes"] = bool({DamageType.ACID, DamageType.FIRE} & set(ev.types()))

    def fall(ev: Dropped) -> None:
        if ev.actor != me or finished["yes"]:
            return
        c.reanimate(on=me, hp=11)

    c.watch(DamageApplied, took, until=When.ENCOUNTER, on=me, label="m5666a1 last blow")
    c.watch(Dropped, fall, until=When.ENCOUNTER, on=me, label="m5666a1 rise")


@power(
    "m5666a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=13), damage=Damage("2d6", 9),
    dropped=("c.grab(dc=)",),
)
def m5666a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        if len(_holding(c)) < 2:
            c.grab()


@power(
    "m5666a3", level=8, usage=AT_WILL, action=FREE, reach=Melee(1), target=NO_TARGET,
    attack=Attack(vs=REF, printed=11), damage=Damage("1d8", 4),
    trigger="a creature it is grabbing attacks it or escapes the grab",
    on=Trigger(
        PowerUsed,
        lambda w, me, ev: ev.actor in w.relations.targets(Relation.GRABBED_BY, me)
        and (me in getattr(ev, "targets", ()) or _is_attack(ev.power)),
        "a creature it is grabbing attacks it or escapes",
    ),
)
def m5666a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


@power(
    "m5666a4", level=8, usage=ENCOUNTER, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m5666a4(c: Cast) -> None:
    c.extra_action(cost=STANDARD, on=c.me)


# ==========================================================================
# m5670
# ==========================================================================


@power("m5670a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5670a0(c: Cast) -> None:
    me = c.me

    def blocked(ev: MoveStart) -> None:
        if getattr(ev, "kind_", "") == "teleport" and distance_between(c.world, me, ev.actor) <= 2:
            ev.cancel()

    c.watch(MoveStart, blocked, until=When.ENCOUNTER, on=me, label="m5670a0 aura")


@power("m5670a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5670a1(c: Cast) -> None:
    me = c.me
    acted: set[int] = set()

    def mark_acted(ev: TurnStart) -> None:
        if not ev.ghost:
            acted.add(ev.actor)

    c.watch(TurnStart, mark_acted, until=When.ENCOUNTER, on=me, label="m5670a1 watch")
    c.bonus(
        "damage", 0, dice="1d10", on=me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") is not None and ctx.get("target") not in acted,
    )


@power(
    "m5670a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d6", 9),
)
def m5670a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark()
    me = c.me
    if not _armed(c, "m5670a2 punish"):
        def punished(ev: PowerUsed) -> None:
            if _marked_by_me_looks_away(c.world, me, ev):
                c.flat(5, dtype=DamageType.NECROTIC, on=ev.actor)

        c.watch(PowerUsed, punished, until=When.ENCOUNTER, on=me, label="m5670a2 punish")


@power("m5670a3", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2), target=UpTo(2))
def m5670a3(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:2]:
        c.use_power("m5670a2", on=victim, spend=False)


@power(
    "m5670a4", level=8, usage=ENCOUNTER, action=MINOR, reach=CloseBurst(1),
    target=EACH_ENEMY, attack=Attack(vs=WILL, printed=11),
)
def m5670a4(c: Cast) -> None:
    if c.strike():
        c.dazed()


# ==========================================================================
# m5701
# ==========================================================================


@power("m5701a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5701a0(c: Cast) -> None:
    c.ignores_difficult("rubble", on=c.me, until=When.ENCOUNTER)


@power(
    "m5701a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d6", 9),
)
def m5701a1(c: Cast) -> None:
    if c.strike():
        c.hit()


def _adjacent_enemy_fell(world: World, me: int, ev: Any) -> bool:
    actor = getattr(ev, "target", None)
    if actor is None or actor == me or team(world, actor) is team(world, me):
        return False
    if getattr(ev, "condition", None) is not Condition.PRONE:
        return False
    return distance_between(world, me, actor) <= 1


@power(
    "m5701a2", level=8, usage=Usage.RECHARGE, recharge=0, action=STANDARD,
    reach=Melee(1), target=Target(side="enemy", count=1, label="prone creature"),
    attack=Attack(vs=AC, printed=13), damage=Damage("3d6", 9, kind=LIMITED),
    requires=_prone_enemy_in_reach, requires_text="an adjacent enemy must be prone",
    dropped=("Target.kind", "c.cannot_stand()"),
)
def m5701a2(c: Cast) -> None:
    """"Cannot stand until the end of its next turn" has no verb -- there
    is no `c.cannot_stand`, only `c.cannot_shift`. The recharge is a
    condition, not a die, so it stays 0 in the header."""
    if c.first and not _armed(c, "m5701a2 recharge"):
        import combat_engine.engine.events as _events

        _recharge_on(
            c, _events.ConditionApplied,
            lambda ev: _adjacent_enemy_fell(c.world, c.me, ev),
        )
    victim = c.target
    if victim is None or not c.is_(Condition.PRONE, victim):
        return
    if c.strike(on=victim):
        c.hit(on=victim)


@power(
    "m5701a3", level=8, usage=AT_WILL, action=MINOR, reach=CloseBlast(3),
    target=EACH_ENEMY, keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=11),
)
def m5701a3(c: Cast) -> None:
    if c.strike():
        c.pull(2)


@power(
    "m5701a4", level=8, usage=AT_WILL, action=INTERRUPT, reach=Melee(1), target=NO_TARGET,
    keywords=[Keyword.WEAPON], attack=Attack(vs=AC, printed=13), damage=Damage("2d6", 9),
    trigger="an adjacent enemy moves away from it or attacks without it",
    on=[
        Trigger(MoveStart, _adjacent_enemy_shifts, "an adjacent enemy shifts away"),
        Trigger(PowerUsed, _adjacent_foe_looks_away, "an adjacent enemy attacks without it"),
    ],
)
def m5701a4(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.prone(on=foe)


# ==========================================================================
# m5818
# ==========================================================================


@power("m5818a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5818a0(c: Cast) -> None:
    me = c.me

    def toll(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or team(c.world, ev.actor) is team(c.world, me):
            return
        if distance_between(c.world, me, ev.actor) <= 1:
            c.slowed(until=When.SONT, on=ev.actor)

    c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label="m5818a0 aura")


@power("m5818a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5818a1(c: Cast) -> None:
    """"Cannot be pulled, pushed, or slid by melee or ranged attacks" is
    approximated as resisting any forced move outright -- a burst or a
    zone shoving it is rarer than the melee/ranged case this is really
    about, and the approximation is the generous direction."""
    c.shares_space(on=c.me, until=When.ENCOUNTER, difficult=True)
    c.resist_forced(99, on=c.me, until=When.ENCOUNTER)


@power(
    "m5818a2", level=8, usage=AT_WILL, action=STANDARD, reach=CloseBurst(2),
    target=EACH_ENEMY, keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d8", 5, dtype=DamageType.POISON),
)
def m5818a2(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None and c.is_(Condition.SLOWED, victim):
            c.damage("1d8", 0, dtype=DamageType.POISON)
        spot = _free_square_beside(c, c.me)
        if spot is not None and victim is not None:
            c.slide(1, on=victim, to=spot)


# ==========================================================================
# m5830
# ==========================================================================


@power("m5830a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5830a0(c: Cast) -> None:
    me = c.me
    for mate in c.allies():
        c.bonus(
            "save", 5, on=mate, until=When.ENCOUNTER, kind="power",
            when=lambda ctx, who=mate: distance_between(c.world, me, who) <= 3,
        )


@power("m5830a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5830a1(c: Cast) -> None:
    me = c.me

    def halved(ev: DamageRolled) -> None:
        if ev.target != me or DamageType.FORCE in ev.types():
            return
        ev.amount -= ev.amount // 2

    c.watch(
        DamageRolled, halved, until=When.ENCOUNTER, on=me, window=Window.BEFORE, label="m5830a1"
    )


@power("m5830a2", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5830a2(c: Cast) -> None:
    """"An ally who also has this trait" is read as another of its own
    kind -- the trait is this stat block's own, so another creature
    carrying it is another copy of it."""
    me = c.me

    def fallen(ev: Dropped) -> None:
        if ev.actor == me or _ref_of(c, ev.actor) != _ref_of(c, me):
            return
        if distance_between(c.world, me, ev.actor) <= 5:
            c.bonus("attack", 2, on=me, until=When.EONT, kind="power")

    c.watch(Dropped, fallen, until=When.ENCOUNTER, on=me, label="m5830a2")


@power(
    "m5830a3", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.PSYCHIC, Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d6", 9, dtype=DamageType.PSYCHIC),
    dropped=("Damage(dtypes=)",),
)
def m5830a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark()
    c.slowed()


@power(
    "m5830a4", level=8, usage=AT_WILL, action=REACTION, reach=CloseBurst(5),
    target=NO_TARGET, keywords=[Keyword.PSYCHIC],
    trigger="an enemy marked by it and within 5 squares attacks without it",
    on=Trigger(
        PowerUsed, _marked_within_looks_away(5), "a marked enemy within 5 attacks without it"
    ),
)
def m5830a4(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    c.condition(
        Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=foe, ongoing=(10, DamageType.PSYCHIC)
    )


# ==========================================================================
# m5835
# ==========================================================================


@power("m5835a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5835a0(c: Cast) -> None:
    me = c.me

    def rattled(ev: Hit) -> None:
        if not ev.critical or team(c.world, ev.attacker) is not team(c.world, me):
            return
        if distance_between(c.world, me, ev.attacker) > 5:
            return
        c.dazed(until=When.SAVE_ENDS, on=ev.target)

    c.watch(Hit, rattled, until=When.ENCOUNTER, on=me, label="m5835a0")


@power(
    "m5835a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d10", 5),
)
def m5835a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark()


@power("m5835a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2), target=UpTo(2))
def m5835a2(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:2]:
        c.use_power("m5835a1", on=victim, spend=False)


@power(
    "m5835a3", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=CloseBurst(2), target=EACH_ENEMY, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d10", 7, kind=LIMITED),
)
def m5835a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty(AC, 2, until=When.SAVE_ENDS)


@power(
    "m5835a4", level=8, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5835a4(c: Cast) -> None:
    c.teleport(3)
    c.insubstantial(until=When.SONT)


@power(
    "m5835a5", level=8, usage=AT_WILL, action=INTERRUPT, reach=Melee(2), target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger="an enemy within 2 squares marked by him moves or attacks without him",
    on=[
        Trigger(MoveStart, _marked_within_moves_away(2), "a marked enemy within 2 moves"),
        Trigger(
            PowerUsed, _marked_within_looks_away(2), "a marked enemy within 2 attacks without him"
        ),
    ],
)
def m5835a5(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    c.bonus("crit_range", 3, on=c.me, until=When.EOT)
    c.use_power("m5835a1", on=foe, spend=False)


# ==========================================================================
# m5858
# ==========================================================================


@power(
    "m5858a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    todo=("c.ignores_charge_lockout()",),
)
def m5858a0(c: Cast) -> None:
    """`actions.py` zeroes `Budget.standard/move/minor` unconditionally
    once a charge resolves, with no per-creature override a row can reach.
    Nothing here plays."""


@power("m5858a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5858a1(c: Cast) -> None:
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


@power(
    "m5858a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=13), damage=Damage("1d10", 5),
)
def m5858a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    already_burning = victim is not None and any(
        getattr(eff, "ongoing", None) for eff in c.world.effects.of(victim)
    )
    c.ongoing(10 if already_burning else 5)


@power(
    "m5858a3", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(2), target=ONE_CREATURE, attack=Attack(vs=REF, printed=11),
    damage=Damage("3d12", 6, kind=LIMITED, half_on_miss=True),
)
def m5858a3(c: Cast) -> None:
    victim = c.target
    was_bloodied = victim is not None and c.bloodied(victim)
    if c.strike():
        c.hit()
        c.prone()
        if victim is not None and not was_bloodied and c.bloodied(victim):
            c.temp_hp(5)
    else:
        c.hit(half=True)


@power(
    "m5858a4", level=8, usage=Usage.RECHARGE, recharge=0, action=MINOR,
    reach=Melee(1), target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13), damage=Damage("1d10", 5),
    dropped=("c.grab(dc=)",),
)
def m5858a4(c: Cast) -> None:
    """Recharges on a condition, not a die -- 0 in the header, and the
    watch below is what brings it back. The "keeps the target adjacent as
    it moves, without provoking" half is a standing no-provoke gated on
    still holding somebody."""
    me = c.me
    if c.first and not _armed(c, "m5858a4 recharge"):
        def loosened(ev: TurnStart) -> None:
            if ev.actor == me and not _holding(c):
                known = c.world.get(me, Powers)
                if known is not None:
                    known.restore("m5858a4")

        c.watch(TurnStart, loosened, until=When.ENCOUNTER, on=me, label="m5858a4 recharge")
    if not c.strike():
        return
    c.hit()
    c.grab()
    victim = c.target
    if victim is not None:
        c.ongoing(10, on=victim, until=When.SAVE_ENDS)
    c.no_provoke(on=me, until=When.ENCOUNTER, when=lambda ctx: bool(_holding(c)))


def _would_drop_me(world: World, me: int, ev: DamageRolled) -> bool:
    if ev.target != me:
        return False
    body = world.get(me, Health)
    return body is not None and ev.amount >= body.hp


@power(
    "m5858a5", level=8, usage=ENCOUNTER, action=INTERRUPT, reach=PERSONAL, target=NO_TARGET,
    trigger="an attack would reduce it to 0 hit points",
    on=Trigger(DamageRolled, _would_drop_me, "an attack would reduce it to 0 hit points"),
)
def m5858a5(c: Cast) -> None:
    """Caught on the proposal rather than the announcement: `Dropped`
    fires only after the hit point loss has already happened, which is too
    late to keep it off 0. Mutating the live `DamageRolled.amount` is read
    back by `deal_damage`, so zeroing it here is what actually keeps it
    standing."""
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m5858a3")
    c.shift(c.speed_of())
    foe = next(iter(c.enemies()), None)
    if foe is None:
        return
    c.use_power("m5858a3", on=foe, spend=False)
    body = c.world.get(foe, Health)
    if body is not None and body.hp <= 0:
        c.trigger.amount = 0
        me_body = c.world.get(c.me, Health)
        if me_body is not None:
            me_body.hp = 20


# ==========================================================================
# m5974
# ==========================================================================


@power(
    "m5974a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d10", 5),
)
def m5974a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m5974a1", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d10", 5, kind=LIMITED),
)
def m5974a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed()
        c.cannot_shift()


@power(
    "m5974a2", level=8, usage=AT_WILL, action=INTERRUPT, reach=Melee(1),
    target=NO_TARGET, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15), damage=Damage("3d10", 5),
    trigger="an enemy marked by her makes an attack that doesn't include her",
    on=Trigger(PowerUsed, _marked_by_me_looks_away, "a marked enemy attacks without her"),
)
def m5974a2(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


# ==========================================================================
# m6004
# ==========================================================================


@power("m6004a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6004a0(c: Cast) -> None:
    me = c.me
    held = (Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.SLOWED)

    def extra_try(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        for eff in list(c.world.effects.of(me)):
            if any(cnd in getattr(eff, "conditions", ()) for cnd in held):
                c.world.effects.save(eff)

    c.watch(TurnStart, extra_try, until=When.ENCOUNTER, on=me, label="m6004a0")


@power(
    "m6004a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d8", 7),
)
def m6004a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed()


@power(
    "m6004a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d8", 7),
)
def m6004a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6004a3", level=8, usage=AT_WILL, action=STANDARD, reach=Ranged(5),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d8", 7),
)
def m6004a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


def _damaged_while_bloodied(world: World, me: int, ev: DamageRolled) -> bool:
    if ev.target != me:
        return False
    body = world.get(me, Health)
    return body is not None and body.hp * 2 <= body.max_hp


@power(
    "m6004a4", level=8, usage=ENCOUNTER, action=INTERRUPT, reach=PERSONAL, target=NO_TARGET,
    trigger="an attack damages it while it is bloodied",
    on=Trigger(DamageRolled, _damaged_while_bloodied, "an attack damages it while bloodied"),
)
def m6004a4(c: Cast) -> None:
    c.temp_hp(10)


# ==========================================================================
# m6020
# ==========================================================================


@power("m6020a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6020a0(c: Cast) -> None:
    me = c.me

    def rallying_cry(ev: Hit) -> None:
        if ev.attacker != me or not by_melee(c.world, me, ev):
            return
        victim = ev.target
        for mate in c.allies():
            c.bonus(
                "attack", 2, on=mate, until=When.EONT, kind="untyped",
                when=lambda ctx, v=victim: ctx.get("target") == v,
            )
            c.bonus(
                "damage", 2, on=mate, until=When.EONT, kind="untyped",
                when=lambda ctx, v=victim: ctx.get("target") == v,
            )

    c.watch(Hit, rallying_cry, until=When.ENCOUNTER, on=me, label="m6020a0")


@power(
    "m6020a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d8", 7),
)
def m6020a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark()


@power("m6020a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1), target=UpTo(2))
def m6020a2(c: Cast) -> None:
    """"If he hits the same target with both" implies two squares of
    choice, so `UpTo(2)` stays; whether the chooser ever offers the same
    creature twice is a board question, not this row's."""
    if not c.first:
        return
    victims = c.targets[:2]
    first_hits = 0
    for victim in victims:
        if _secondary(c, 13, AC, victim):
            c.damage("2d8", 7, on=victim)
            if victim == victims[0]:
                first_hits += 1
    if len(victims) == 2 and victims[0] == victims[1] and first_hits == 2:
        c.slowed(until=When.SAVE_ENDS, on=victims[0])


@power(
    "m6020a3", level=8, usage=ENCOUNTER, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("3d10", 5, half_on_miss=True),
)
def m6020a3(c: Cast) -> None:
    me = c.me
    bonus = len([a for a in c.allies() if distance_between(c.world, me, a) <= 5])
    if c.strike():
        c.hit()
        if bonus:
            c.flat(bonus)
    else:
        c.hit(half=True)


@power(
    "m6020a4", level=8, usage=Usage.RECHARGE, recharge=6, action=MINOR,
    reach=CloseBurst(5), target=EACH_ALLY,
)
def m6020a4(c: Cast) -> None:
    mate = c.target
    if mate is not None:
        c.shift(3, who=mate)


@power(
    "m6020a5", level=8, usage=AT_WILL, action=REACTION, reach=PERSONAL, target=NO_TARGET,
    trigger="an enemy adjacent to him and marked by him shifts away from him",
    on=Trigger(MoveStart, _marked_adjacent_shifts, "a marked adjacent enemy shifts away"),
)
def m6020a5(c: Cast) -> None:
    fled = getattr(c.trigger, "actor", None)
    other = next((f for f in c.enemies() if f != fled), None)
    if other is not None:
        c.charge_at(other)


# ==========================================================================
# m6068
# ==========================================================================


@power("m6068a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6068a0(c: Cast) -> None:
    """A silvered weapon is not a tag `Gear()` ever carries -- the #366
    shape -- so the exception never triggers and the regeneration simply
    always runs."""
    c.regeneration(5, on=c.me, until=When.ENCOUNTER)


@power(
    "m6068a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=13), damage=Damage("2d6", 7),
)
def m6068a1(c: Cast) -> None:
    victim = c.target
    edge = victim is not None and (c.bloodied(victim) or c.is_(Condition.PRONE, victim))
    if c.strike():
        if edge:
            c.damage("2d6", 11)
        else:
            c.hit()
    c.mark()


@power(
    "m6068a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=13), damage=Damage("2d8", 3),
)
def m6068a2(c: Cast) -> None:
    """The curse of lycanthropy is a disease track with no save-by-save
    progression modelled here -- noted rather than invented, the same
    shape `m3615a0` already settled."""
    victim = c.target
    if c.strike():
        c.hit()
        c.prone()
        if victim is not None and c.is_kind("humanoid", on=victim) and c.bloodied(victim):
            c.note(f"{c.ref}: it gains the curse of lycanthropy (stage 1)")


@power("m6068a3", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1), target=ONE_CREATURE)
def m6068a3(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    hits = 0
    for _ in range(2):
        edge = c.bloodied(victim) or c.is_(Condition.PRONE, victim)
        if _secondary(c, 13, AC, victim):
            c.damage("2d6", 11 if edge else 7, on=victim)
            hits += 1
    if hits == 2:
        c.use_power("m6068a2", on=victim, spend=False)
        if c.landed:
            c.flat(5, on=victim)


@power(
    "m6068a4", level=8, usage=AT_WILL, action=MINOR, reach=PERSONAL, target=SELF,
    keywords=[Keyword.POLYMORPH], out_of_combat=True,
)
def m6068a4(c: Cast) -> None:
    """Every row here fights the same regardless of shape, so the shift
    between forms changes nothing a fight reads."""


# ==========================================================================
# m6268
# ==========================================================================


@power("m6268a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6268a0(c: Cast) -> None:
    def pinned(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and c.is_(Condition.IMMOBILIZED, victim)

    c.gains_advantage(pinned, until=When.ENCOUNTER, on=c.me)


@power(
    "m6268a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d8", 7),
)
def m6268a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m6268a2", level=8, usage=AT_WILL, action=INTERRUPT, reach=Melee(1),
    target=NO_TARGET, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d8", 7),
    trigger="an enemy marked by him makes an attack that doesn't include him",
    on=Trigger(PowerUsed, _marked_by_me_looks_away, "a marked enemy attacks without him"),
)
def m6268a2(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.penalty("attack", 2, on=foe, until=When.EOT)


# ==========================================================================
# m6419
# ==========================================================================


@power("m6419a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6419a0(c: Cast) -> None:
    me = c.me

    def shielded(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or not c.is_minion(ev.actor):
            return
        same_side = team(c.world, ev.actor) is team(c.world, me)
        if same_side and distance_between(c.world, me, ev.actor) <= 3:
            c.temp_hp(5, on=ev.actor)

    c.watch(TurnStart, shielded, until=When.ENCOUNTER, on=me, label="m6419a0")


@power(
    "m6419a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d8", 7),
)
def m6419a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m6419a2", level=8, usage=ENCOUNTER, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m6419a2(c: Cast) -> None:
    me = c.me
    for which in (AC, FORT, REF, WILL):
        c.bonus(which, 2, on=me, until=When.ENCOUNTER, kind="power")


# ==========================================================================
# m6435
# ==========================================================================


def _grabbing_at_most_one(world: World, eid: int) -> bool:
    return len(world.relations.targets(Relation.GRABBED_BY, eid)) <= 1


@power(
    "m6435a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=13), damage=Damage("2d6", 9),
    requires=_grabbing_at_most_one, requires_text="it must not be grabbing more than one creature",
    dropped=("c.grab(dc=)",),
)
def m6435a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m6435a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=13), damage=Damage("2d6", 9),
)
def m6435a1(c: Cast) -> None:
    victim = c.target
    held = victim is not None and victim in _holding(c)
    if c.strike():
        if held:
            c.damage("4d6", 9)
        else:
            c.hit()


@power("m6435a2", level=8, usage=AT_WILL, action=MOVE, reach=PERSONAL, target=SELF)
def m6435a2(c: Cast) -> None:
    c.move(max(1, c.speed_of() // 2))
    for who in _holding(c):
        spot = _free_square_beside(c, c.me)
        if spot is not None:
            c.pull(99, on=who, to=spot)


# ==========================================================================
# m6535
# ==========================================================================


@power("m6535a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6535a0(c: Cast) -> None:
    me = c.me
    _aura(
        c, 1,
        lambda who: who != me and team(c.world, who) is not team(c.world, me),
        lambda who: c.penalty(
            "attack", 2, on=who, until=When.ENCOUNTER,
            when=lambda ctx: ctx.get("target") != me,
        ),
    )


@power("m6535a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6535a1(c: Cast) -> None:
    """`Dropped` names who struck the blow and not what with, so the
    finishing power is read off the `DamageApplied` immediately before
    it, the same shape `m3533a3` already settled."""
    me = c.me

    def finishing_blow(ev: DamageApplied) -> None:
        if ev.source == me and ev.detail == "m6535a2" and ev.hp <= 0:
            c.temp_hp(5, on=me)

    c.watch(DamageApplied, finishing_blow, until=When.ENCOUNTER, on=me, label="m6535a1")


@power(
    "m6535a2", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d8", 7),
)
def m6535a2(c: Cast) -> None:
    if c.strike():
        if c.crit:
            c.flat(23)
            c.damage("1d6", 0, dtype=DamageType.NECROTIC)
        else:
            c.hit()


@power(
    "m6535a3", level=8, usage=AT_WILL, action=STANDARD, reach=Ranged(15),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d8", 7),
)
def m6535a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6535a4", level=8, usage=ENCOUNTER, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.THUNDER],
)
def m6535a4(c: Cast) -> None:
    victim = c.target
    c.use_power("m6535a2", on=victim, spend=False)
    if c.landed and victim is not None:
        for foe in c.enemies():
            if foe != victim and c.adjacent_to(foe, victim):
                c.damage("2d6", 0, dtype=DamageType.THUNDER, on=foe)
                c.prone(on=foe)


@power(
    "m6535a5", level=8, usage=AT_WILL, action=INTERRUPT, reach=Melee(1), target=NO_TARGET,
    trigger="an enemy willingly leaves a square adjacent to her",
    on=Trigger(MoveStart, _adjacent_enemy_shifts, "an enemy leaves a square adjacent to her"),
)
def m6535a5(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    c.use_power("m6535a2", on=foe, spend=False)
    if c.landed:
        c.prone(on=foe)


# ==========================================================================
# m6546
# ==========================================================================


@power(
    "m6546a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d8", 7),
)
def m6546a0(c: Cast) -> None:
    victim = c.target
    was_bloodied = victim is not None and c.bloodied(victim)
    if c.strike():
        c.hit()
        if victim is not None and not was_bloodied and c.bloodied(victim):
            c.dazed(on=victim)
    c.mark()


@power(
    "m6546a1", level=8, usage=AT_WILL, action=STANDARD, reach=Ranged(5),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d6", 9),
)
def m6546a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6546a2", level=8, usage=AT_WILL, action=MINOR, reach=PERSONAL, target=NO_TARGET,
    once_per_round=True,
)
def m6546a2(c: Cast) -> None:
    mate = next((a for a in c.allies() if c.can_see(a)), None)
    if mate is None:
        return
    foe = next((f for f in c.enemies() if c.adjacent_to(mate, f)), None)
    if foe is None:
        return
    landed = (
        c.charge_at(foe, who=mate) if not c.adjacent_to(mate, foe) else c.basic(on=foe, who=mate)
    )
    if landed:
        c.flat(5, on=foe)


@power(
    "m6546a3", level=8, usage=AT_WILL, action=REACTION, reach=Melee(1), target=NO_TARGET,
    trigger="an enemy marked by her makes an attack that doesn't include her",
    on=Trigger(PowerUsed, _marked_by_me_looks_away, "a marked enemy attacks without her"),
)
def m6546a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    if c.basic(on=foe):
        c.flat(5, on=foe)


# ==========================================================================
# m919
# ==========================================================================


@power(
    "m919a0", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d12", 9),
)
def m919a0(c: Cast) -> None:
    """"Plus an additional 2d12 on a crit" is part of this same attack's
    own damage, so the extra die is maximised along with the rest -- the
    same 4e crit rule the first die already gets."""
    if c.strike():
        c.hit()
        if c.crit:
            c.damage("2d12", 0)


@power(
    "m919a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.DIVINE, Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d12", 9, dtype=DamageType.RADIANT),
)
def m919a1(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None and c.marked(on=victim, by=c.me):
            c.flat(3, dtype=DamageType.RADIANT)


@power(
    "m919a2", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.DIVINE, Keyword.THUNDER, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d12", 9, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m919a2(c: Cast) -> None:
    if c.first:
        _recharge_when_bloodied(c)
    victim = c.target
    c.bonus(
        "crit_range", 2, on=c.me, until=When.EOT,
        when=lambda ctx, v=victim: (
            v is not None and ctx.get("target") == v and c.marked(on=v, by=c.me)
        ),
    )
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m919a3", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.DIVINE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d12", 9, dtype=DamageType.RADIANT),
)
def m919a3(c: Cast) -> None:
    me = c.me
    nearby = len([f for f in c.enemies() if c.adjacent_to(me, f)])
    if c.strike(plus=nearby):
        c.hit()


@power(
    "m919a4", level=8, usage=AT_WILL, action=MINOR, reach=CloseBurst(5),
    target=ONE_CREATURE, keywords=[Keyword.DIVINE, Keyword.RADIANT],
)
def m919a4(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    me, ref = c.me, c.ref
    for old in list(c.world.relations.targets(Relation.MARKED_BY, me)):
        if old == victim:
            continue
        for eff in list(c.world.effects.of(old)):
            if eff.label == f"{ref} mark":
                c.world.effects.end(eff, ref)
    c.mark(until=When.ENCOUNTER, on=victim)

    def looked_away(ev: PowerUsed) -> None:
        foe = ev.actor
        if foe == me or not c.world.relations.holds(Relation.MARKED_BY, me, foe):
            return
        if me in ev.targets or not _is_attack(ev.power):
            return
        c.penalty("attack", 2, on=foe, until=When.EOT)
        c.flat(6, dtype=DamageType.RADIANT, on=foe)

    if not _armed(c, f"{ref} watch"):
        c.watch(PowerUsed, looked_away, until=When.ENCOUNTER, on=me, label=f"{ref} watch")


@power(
    "m919a5", level=8, usage=ENCOUNTER, action=MINOR, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.DIVINE],
)
def m919a5(c: Cast) -> None:
    c.bonus("damage", 5, on=c.me, until=When.EOT, once=True, kind="untyped")


@power(
    "m919a6", level=8, usage=AT_WILL, action=REACTION, reach=PERSONAL, target=NO_TARGET,
    trigger="it is hit by a melee attack",
    on=Trigger(
        Hit, lambda w, me, ev: ev.target == me and by_melee(w, me, ev),
        "a melee attack hits it",
    ),
)
def m919a6(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.basic(on=foe)


@power(
    "m919a7", level=8, usage=ENCOUNTER, action=STANDARD, reach=PERSONAL, target=SELF,
    keywords=[Keyword.HEALING],
)
def m919a7(c: Cast) -> None:
    me = c.me
    c.spend_surge(on=me)
    c.heal(41, on=me)
    for which in (AC, FORT, REF, WILL):
        c.bonus(which, 2, on=me, until=When.SONT)


# ==========================================================================
# m954
# ==========================================================================


@power("m954a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m954a0(c: Cast) -> None:
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


@power(
    "m954a1", level=8, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d10", 5),
)
def m954a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m954a2", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(2), target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d10", 5, kind=LIMITED),
)
def m954a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()


@power(
    "m954a3", level=8, usage=AT_WILL, action=STANDARD, reach=Ranged(15),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d8", 7),
)
def m954a3(c: Cast) -> None:
    if c.strike():
        c.hit()
