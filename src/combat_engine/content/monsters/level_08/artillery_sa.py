"""Monster abilities, level 8, artillery, second wave.

Thirty-one stat blocks, 111 rows. `artillery.py` holds the earlier sweep of
this level and is not touched here; nine of the thirty-one print no
abilities at all and have nothing to decorate: m215, m2833, m2852, m2884,
m2975, m3085, m398, m4716, m655.

Conventions, inherited from the level 1-7 artillery sweeps:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=N)`) and the damage line goes in the
  header as data;
* a **trait** costs no action, has no target, and arms the watches that
  hold it, whatever the compendium's action column claims -- several blocks
  here print "standard" in that column for a passive line with no attack at
  all, and are written as traits regardless;
* a card with no printed range at all is melee 1;
* a close burst, blast or area naming no target set takes **enemies**,
  except where it says "creatures in the burst" outright;
* `half_on_miss=True` is card data only -- a Miss line is also written as
  `else: c.hit(half=True)`;
* a recharge or encounter attack says `Damage(..., kind=LIMITED)`, a
  minion's flat damage `Damage("", n, kind=MINION)`;
* a blow of two damage types rolled as one keeps the first in the header
  and is marked `dropped=("Damage(dtypes=)",)`; two *separately named*
  amounts of different types (not one roll) are written as a header blow
  plus a `c.flat(..., dtype=)` second one, which needs no marker;
* "+N vs AC, or +N+1 against/while bloodied" keeps the printed total in the
  header and the difference is read live off `c.bloodied`.

Four helpers are new here: `_moves_closer` generalises the level-4/5
"if the target moves nearer on its next turn" shape to any payout, not just
one more attack roll; `_two_allies_flank` is "extra damage to an enemy with
two or more of its allies adjacent" shared by two blocks; `_bloodied_bonus`
and `_bloodied_target_edge` are the two different "while bloodied" checks
this wave needed -- one asks the caster, the other asks the target, and they
are not the same question.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import _recharge_when_bloodied
from combat_engine.content.monsters.level_01.brutes_sa import _crit_line
from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES
from combat_engine.content.monsters.level_02.lurkers_sa import _triggering_enemy
from combat_engine.content.monsters.level_03.brutes_sa import _enemy_closed_on_me
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_CREATURE,
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
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Mod,
    Position,
    Ranged,
    Usage,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackRolled,
    Bloodied,
    Hit,
    Miss,
    Moved,
    PowerUsed,
    SavingThrow,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import distance_between, squares, team, unseen_by
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_melee,
    by_ranged,
    either,
    would_hit_me,
)

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _moves_closer(c: Cast, victim: int, then: Callable[[], None]) -> None:
    """"If the target moves closer to it on its next turn." `Moved` is the
    only one of the three movement events that carries `from_`, so the
    distance comparison is made there, once, against the square the move
    started from."""
    me = c.me

    def closed(ev: Moved) -> None:
        if ev.actor != victim or ev.from_ is None:
            return
        was = min(
            max(abs(ev.from_[0] - sq[0]), abs(ev.from_[1] - sq[1]))
            for sq in squares(c.world, me)
        )
        if distance_between(c.world, me, victim) < was:
            then()

    c.watch(Moved, closed, until=When.EOTNT, on=me, once=True, label=f"{c.ref} closer")


def _two_allies_flank(c: Cast) -> Callable[[dict[str, Any]], bool]:
    """"Extra damage to an enemy with two or more of its allies adjacent to
    it." Asked of the damage context's own target rather than kept as a
    snapshot, since who is adjacent to whom changes every time anyone moves.
    """

    def surrounded(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None:
            return False
        return len([a for a in c.allies() if a != c.me and c.adjacent_to(a, who)]) >= 2

    return surrounded


def _bloodied_bonus(c: Cast) -> int:
    """"+N vs AC, while bloodied" -- the caster's own state."""
    return 1 if c.bloodied(c.me) else 0


def _bloodied_target_edge(c: Cast) -> int:
    """"+N vs AC against a bloodied target" -- `c.bloodied()` with no `on=`
    already reads `c.target`, which is the right side for this one."""
    return 1 if c.target is not None and c.bloodied() else 0


def _implement_only(ctx: dict[str, Any]) -> bool:
    """"With implement attacks" -- asked of the damage context."""
    row = get(str(ctx.get("power") or ""))
    return row is not None and Keyword.IMPLEMENT in row.keywords


def _recharge_on_miss(c: Cast) -> None:
    """"Recharge if the attack misses" -- a die every round plus one more
    chance the moment this very row whiffs."""
    me, ref = c.me, c.ref

    def missed(ev: Miss) -> None:
        if ev.attacker == me and ev.power == ref:
            c.restore_use(ref, on=me)

    c.watch(Miss, missed, until=When.ENCOUNTER, on=me, once=True, label=f"{ref} recharge")


def _minus_all_defences(c: Cast, victim: int, amount: int) -> Effect | None:
    """"Takes a -N penalty to all defenses (save ends)" -- four mods bundled
    under one roll, the way `_one_save_for_both` bundles a mod with a burn."""
    mods = [
        (victim, Mod(what=which, value=-amount, kind="untyped", label=c.ref))
        for which in ALL_DEFENCES
    ]
    return c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=f"{c.ref} defences", mods=mods
    )


def _enemy_save_in_sight(world: World, me: int, ev: SavingThrow) -> bool:
    """"An enemy within sight succeeds on a saving throw" -- "within sight"
    read as not unseen to this creature, the same fact `c.can_see` tests."""
    if not ev.saved:
        return False
    who = ev.actor
    if team(world, who) is team(world, me):
        return False
    return not unseen_by(world, me, who)


# ==========================================================================
# m1038
# ==========================================================================


@power(
    "m1038a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d4", 0),
)
def m1038a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m1038a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d6", 4, dtype=DamageType.NECROTIC),
)
def m1038a1(c: Cast) -> None:
    """A grasping hand's reach, written `Melee(10)` rather than ranged: the
    card's own Effect has it entering the target's square, which is a
    melee creature's business."""
    victim = c.target
    if victim is not None and c.strike():
        c.hit()

        def burn_more(v: int = victim) -> None:
            c.flat(c.roll("1d6") + 4, dtype=DamageType.NECROTIC, on=v)

        _moves_closer(c, victim, burn_more)


@power(
    "m1038a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(3, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d6", 4, dtype=DamageType.NECROTIC, kind=LIMITED, half_on_miss=True),
)
def m1038a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)
    else:
        c.hit(half=True)


@power(
    "m1038a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 10, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1038a3(c: Cast) -> None:
    """The daze and the grab land together; the "enters the target's space"
    clause is a shift into that square with `share=True`. The sustain's own
    check is live, not assumed: it reads both positions again at the moment
    it tries, which is exactly "if the hand is forced out, it cannot
    sustain" asked rather than guessed at."""
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.dazed(on=victim, until=When.EONT)
    hold = c.grab(on=victim)
    me = c.me
    vpos = c.world.get(victim, Position)
    if vpos is not None:
        c.shift(to=vpos.square, share=True)
    c.immobilized(on=me, until=When.EONT)

    def sustain_more() -> None:
        here = c.world.get(me, Position)
        there = c.world.get(victim, Position)
        if here is None or there is None or here.square != there.square:
            return
        c.flat(10, dtype=DamageType.NECROTIC, on=victim)
        c.immobilized(on=me, until=When.EONT)

    if hold is not None:
        c.on_sustain(hold, sustain_more)


# ==========================================================================
# m1046
# ==========================================================================


@power(
    "m1046a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8"),
)
def m1046a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1046a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d4", 5, dtype=DamageType.FORCE),
)
def m1046a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1046a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d4", 5, dtype=DamageType.FORCE),
)
def m1046a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1046a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d8", 5, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m1046a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1046a4",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 5, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m1046a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m1046a5",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d6", 5, dtype=DamageType.ACID, kind=LIMITED),
)
def m1046a5(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m1079
# ==========================================================================


@power(
    "m1079a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 2),
)
def m1079a0(c: Cast) -> None:
    if c.strike(plus=_bloodied_bonus(c)):
        c.hit()


@power(
    "m1079a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d6", 4, dtype=DamageType.LIGHTNING),
)
def m1079a1(c: Cast) -> None:
    if c.strike(plus=_bloodied_bonus(c)):
        c.hit()


@power(
    "m1079a2",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d6", 4, kind=LIMITED),
)
def m1079a2(c: Cast) -> None:
    """Chosen once for the whole blast, not once per target -- the printed
    line names one element for the breath, not a pick per victim. The type
    stays off the header so the rescale still has one untyped number to
    read."""
    if not c.first:
        if c.strike(plus=_bloodied_bonus(c)):
            c.damage("1d6", 4, dtype=_M1079A2_PICK.get(c.me, DamageType.COLD))
        return
    options = [DamageType.COLD, DamageType.FIRE]
    element = c.choose(options, f"{c.ref}: cold or fire") or DamageType.COLD
    _M1079A2_PICK[c.me] = element
    if c.strike(plus=_bloodied_bonus(c)):
        c.damage("1d6", 4, dtype=element)


_M1079A2_PICK: dict[int, DamageType] = {}


@power(
    "m1079a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.ACID],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("1d8", 4, dtype=DamageType.ACID, kind=LIMITED),
)
def m1079a3(c: Cast) -> None:
    """The lingering acid is a zone rather than a one-shot burst: the toll
    is asked at the start and the end of each turn, and a dict caps it at
    one hit per creature per round rather than two."""
    if c.strike(plus=_bloodied_bonus(c)):
        c.hit()
    if not c.first:
        return
    zone = c.zone(c.area(), until=When.EONT, label=c.ref)
    me = c.me
    tolled: dict[int, int] = {}

    def toll(ev: Any) -> None:
        if ev.ghost:
            return
        who = ev.actor
        if who not in c.world.zones.occupants(zone) or tolled.get(who) == ev.round:
            return
        tolled[who] = ev.round
        c.flat(10, dtype=DamageType.ACID, on=who)

    c.watch(TurnStart, toll, until=When.EONT, on=me, label=f"{c.ref} start")
    c.watch(TurnEnd, toll, until=When.EONT, on=me, label=f"{c.ref} end")


@power(
    "m1079a4",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.COLD],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d6", 6, dtype=DamageType.COLD, kind=LIMITED),
)
def m1079a4(c: Cast) -> None:
    if c.strike(plus=_bloodied_bonus(c)):
        c.hit()
    if c.first:
        c.zone(c.area(), difficult=True, until=When.EONT, label=c.ref)


@power(
    "m1079a5",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1079a5(c: Cast) -> None:
    """A trait, whatever the compendium's action column claims -- "a r1
    gains a racial bonus" is this creature's own printed Dragonborn Fury,
    `r1` standing in for the race the way `cls` does on a racial row."""
    me = c.me
    c.bonus(
        "attack", 1, kind="racial", on=me, until=When.ENCOUNTER, when=lambda _ctx: c.bloodied(me)
    )


_M1079_STRUCK = "it would be hit by a melee or ranged attack"


@power(
    "m1079a6",
    level=8,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1079_STRUCK,
    on=Trigger(
        AttackRolled, when=both(would_hit_me, either(by_melee, by_ranged)), text=_M1079_STRUCK
    ),
)
def m1079a6(c: Cast) -> None:
    me = c.me
    vs = getattr(c.trigger, "vs", None)
    c.ignores_difficult(on=me, until=When.EOT)
    if vs is not None:
        c.bonus(vs, 2, on=me, until=When.EOT)
    c.shift(2)
    foe = _triggering_enemy(c)
    if foe is not None:
        c.push(2, on=foe)


# ==========================================================================
# m1116
# ==========================================================================


@power(
    "m1116a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d4", 4),
)
def m1116a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M1116_TARGETED = "it is targeted by a melee attack"


@power(
    "m1116a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.FIRE],
    trigger=_M1116_TARGETED,
    on=Trigger(AttackRolled, both(lambda w, m, ev: ev.target == m, by_melee), _M1116_TARGETED),
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d6", 4, dtype=DamageType.FIRE),
)
def m1116a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1116a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("3d6", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m1116a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1116a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1116a3(c: Cast) -> None:
    """A recharge power with its own extra recharge clause -- "when first
    bloodied" arms early on top of the die every round, the shape
    `_recharge_when_bloodied` already names."""
    _recharge_when_bloodied(c)
    c.use_power("m1116a2")


@power(
    "m1116a4",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m1116a4(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m1149
# ==========================================================================


@power(
    "m1149a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d8", 4, dtype=DamageType.PSYCHIC),
)
def m1149a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m1149a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d6", 3),
)
def m1149a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            _minus_all_defences(c, victim, 2)


@power(
    "m1149a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d6", 3),
)
def m1149a2(c: Cast) -> None:
    """"Subject to the penalties of m1149a1" is read off that row's own
    label -- `c.suffering` matches it by substring, so there is nothing to
    track here beyond what that row already wrote down."""
    victim = c.target
    if victim is not None and c.strike():
        c.hit()
        if victim in c.suffering("m1149a1 defences"):
            c.flat(c.roll("2d6"))


_M1149A3_SAVE = "an enemy within sight succeeds on a saving throw"


@power(
    "m1149a3",
    level=8,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1149A3_SAVE,
    on=Trigger(SavingThrow, _enemy_save_in_sight, _M1149A3_SAVE),
)
def m1149a3(c: Cast) -> None:
    c.reroll_save(keep="new")


# ==========================================================================
# m115774
# ==========================================================================


@power(
    "m115774a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115774a0(c: Cast) -> None:
    c.bonus("damage", 5, on=c.me, until=When.ENCOUNTER, when=_two_allies_flank(c))


@power(
    "m115774a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 7),
)
def m115774a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.bloodied(c.me):
            c.flat(2)


@power(
    "m115774a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(30),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 5),
)
def m115774a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.bloodied(c.me):
            c.flat(2)


@power(
    "m115774a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 5, kind=LIMITED),
)
def m115774a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.bloodied(c.me):
            c.flat(2)
        c.ongoing(5)


# ==========================================================================
# m1164
# ==========================================================================


@power(
    "m1164a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d4"),
)
def m1164a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1164a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d6", 4, dtype=DamageType.NECROTIC),
)
def m1164a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m1164a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d8", 4, dtype=DamageType.LIGHTNING),
)
def m1164a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1164a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d6", 4, kind=LIMITED),
)
def m1164a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m1164a4",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID, Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d10", 6, dtype=DamageType.ACID, kind=LIMITED, half_on_miss=True),
)
def m1164a4(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m1164a5",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1164a5(c: Cast) -> None:
    """"If m1164 includes at least one ally in an area attack" is asked of
    *that* use's own target list, not of the board generally -- `PowerUsed`
    names the targets before the body runs, which is the one moment this is
    askable, so the finding is cached under the power's own ref until the
    next use of it overwrites it."""
    me = c.me
    active: set[str] = set()

    def mark(ev: PowerUsed) -> None:
        if ev.actor != me:
            return
        row = get(ev.power or "")
        if row is None or row.reach.kind not in ("area_burst", "close_blast"):
            return
        if any(t in c.allies() for t in ev.targets):
            active.add(ev.power)
        else:
            active.discard(ev.power)

    c.watch(PowerUsed, mark, until=When.ENCOUNTER, on=me, label=f"{c.ref} mark")
    c.bonus(
        "damage", 0, dice="1d6", on=me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("power") in active,
    )


@power(
    "m1164a6",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m1164a6(c: Cast) -> None:
    c.shift(1)


# ==========================================================================
# m1756
# ==========================================================================


@power(
    "m1756a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8"),
)
def m1756a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1756a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 5),
)
def m1756a1(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            c.penalty("speed", 1, on=victim, until=When.EONT)


@power(
    "m1756a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d6", 5),
)
def m1756a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1756a3",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1756a3(c: Cast) -> None:
    me = c.me
    c.bonus(AC, 2, on=me, until=When.ENCOUNTER, when=lambda _ctx: not c.bloodied(me))
    c.bonus(REF, 2, on=me, until=When.ENCOUNTER, when=lambda _ctx: not c.bloodied(me))


# ==========================================================================
# m3321
# ==========================================================================


@power(
    "m3321a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 6),
)
def m3321a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3321a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 5),
)
def m3321a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3321a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 5, kind=LIMITED),
)
def m3321a2(c: Cast) -> None:
    """"Requires a crossbow" is equipment, not tracked."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m3321a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.TELEPORTATION, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d10", 5, dtype=DamageType.COLD, kind=LIMITED),
)
def m3321a3(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    held = c.condition(Condition.REMOVED, until=When.EONT, on=victim)
    if held is not None:
        held.on_end.append(lambda v=victim: c.dazed(on=v, until=When.SONT))


@power(
    "m3321a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=5,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy shifts or moves adjacent to it",
    on=Trigger(AdjacencyGained, _enemy_closed_on_me, "an enemy shifts or moves adjacent to it"),
)
def m3321a4(c: Cast) -> None:
    c.shift(2)
    foe = _triggering_enemy(c)
    if foe is not None:
        c.use_power("m3321a1", on=foe)


# ==========================================================================
# m3784
# ==========================================================================


@power(
    "m3784a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 7),
)
def m3784a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d8", 15)


@power(
    "m3784a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d4", 7, dtype=DamageType.FORCE),
)
def m3784a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3784a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 7),
)
def m3784a2(c: Cast) -> None:
    """"Her scimitar immediately returns to her hand" is where the thing
    physically is and nothing else -- no combat line reads it."""
    if c.strike():
        _crit_line(c, "2d8", 15)


@power(
    "m3784a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def m3784a3(c: Cast) -> None:
    first = c.target
    if first is None:
        return
    landed = bool(c.use_power("m3784a2", on=first))
    if not landed:
        return
    nxt = min(
        (f for f in c.enemies() if f != first and c.distance(f) <= 10),
        key=lambda f: c.distance(f),
        default=None,
    )
    if nxt is not None:
        c.use_power("m3784a2", on=nxt)


@power(
    "m3784a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d10", 7, dtype=DamageType.FIRE, kind=LIMITED),
)
def m3784a4(c: Cast) -> None:
    """"Requires a scimitar" is equipment, not tracked; the reforming
    scimitar is the same physical-location note as `m3784a2`."""
    if c.strike():
        c.hit()


@power(
    "m3784a5",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m3784a5(c: Cast) -> None:
    c.teleport(5)


@power(
    "m3784a6",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m3784a6(c: Cast) -> None:
    c.conceal(on=c.me, until=When.ENCOUNTER, total=True, when=lambda _ctx: not c.bloodied(c.me))


# ==========================================================================
# m452
# ==========================================================================


@power(
    "m452a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d4", 3),
)
def m452a0(c: Cast) -> None:
    if c.strike(plus=_bloodied_target_edge(c)):
        c.hit()


@power(
    "m452a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d8", 6, dtype=DamageType.FIRE),
)
def m452a1(c: Cast) -> None:
    if c.strike(plus=_bloodied_target_edge(c)):
        c.hit()
        c.ongoing(5, DamageType.FIRE)
        c.slide(1)


_M452_HIT = "it is hit by a melee attack"


@power(
    "m452a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger=_M452_HIT,
    on=Trigger(Hit, both(lambda w, m, ev: ev.target == m, by_melee), _M452_HIT),
)
def m452a2(c: Cast) -> None:
    c.teleport(5)


@power(
    "m452a3",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m452a3(c: Cast) -> None:
    """Who hurt it lately is asked as the attack rolls, not snapshotted
    now -- the window named "since its last turn" is still open while the
    bonus stands. `m915a4` is the shape this follows."""
    from combat_engine.content.monsters.level_04.lurkers_sa import _hit_me_since_my_turn

    me = c.me

    def paid_back(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") in _hit_me_since_my_turn(c)

    c.bonus("attack", 1, on=me, kind="power", until=When.ENCOUNTER, once=True, when=paid_back)
    c.bonus("damage", 5, on=me, until=When.ENCOUNTER, once=True, when=paid_back)


# ==========================================================================
# m5123
# ==========================================================================


@power(
    "m5123a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 8),
)
def m5123a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5123a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 6),
)
def m5123a1(c: Cast) -> None:
    """"Any m5123 deals 3 extra damage against the target" reaches every
    creature of this one's own kind, not only this caster -- so the gated
    bonus is laid on each of them, keyed to this specific victim."""
    from combat_engine.content.monsters.level_02.soldiers_sa import _ref_of
    from combat_engine.engine.query import creatures

    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is None:
        return
    for kin in creatures(c.world):
        if _ref_of(c, kin) == "m5123":
            c.bonus(
                "damage", 3, on=kin, until=When.EONT,
                when=lambda ctx, v=victim: ctx.get("target") == v,
            )


@power(
    "m5123a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 6, kind=LIMITED),
)
def m5123a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(c.roll("1d6"), dtype=DamageType.FORCE)
        c.prone()


# ==========================================================================
# m5231
# ==========================================================================


@power(
    "m5231a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("", 6, kind=MINION),
)
def m5231a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5231a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("", 6, kind=MINION),
)
def m5231a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5231a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5231a2(c: Cast) -> None:
    """"Keeps its speed at its full value" -- read as immune to the one
    condition that reduces it."""
    c.immune(Condition.SLOWED, until=When.ENCOUNTER, on=c.me)


# ==========================================================================
# m5629
# ==========================================================================


@power(
    "m5629a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5629a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(5, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    for which in ALL_DEFENCES:
        c.bonus(
            which, 5, kind="power", on=me, until=When.ENCOUNTER,
            when=lambda ctx, z=ring: ctx.get("attacker") is not None
            and ctx.get("attacker") not in c.world.zones.occupants(z),
        )


@power(
    "m5629a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 7),
)
def m5629a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5629a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 5, dtype=DamageType.COLD),
)
def m5629a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m5629a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.COLD, Keyword.WEAPON, Keyword.ZONE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 3, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
)
def m5629a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
    if c.first:
        zone = c.zone(c.area(), until=When.ENCOUNTER, label=c.ref)
        me = c.me

        def toll(ev: TurnEnd) -> None:
            if not ev.ghost and ev.actor in c.world.zones.occupants(zone):
                c.flat(5, dtype=DamageType.COLD, on=ev.actor)

        c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} zone toll")


_M5629_RING = "an enemy within 5 squares hits it with an attack"


def _hit_by_nearby_enemy(world: World, me: int, ev: Hit) -> bool:
    return ev.target == me and distance_between(world, me, ev.attacker) <= 5


@power(
    "m5629a4",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.COLD],
    trigger=_M5629_RING,
    on=Trigger(Hit, _hit_by_nearby_enemy, _M5629_RING),
)
def m5629a4(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.flat(10, dtype=DamageType.COLD, on=foe)
        c.push(2, on=foe)


# ==========================================================================
# m5643
# ==========================================================================


@power(
    "m5643a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5643a0(c: Cast) -> None:
    c.bonus("damage", 5, on=c.me, until=When.ENCOUNTER, when=_two_allies_flank(c))


@power(
    "m5643a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7),
)
def m5643a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5643a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d10", 5),
)
def m5643a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5643a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d6", 5, dtype=DamageType.RADIANT),
)
def m5643a3(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.strike():
        c.hit()
        _moves_closer(c, victim, lambda: c.flat(10, dtype=DamageType.RADIANT, on=victim))


@power(
    "m5643a4",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.POISON],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("3d8", 10, dtype=DamageType.POISON, kind=LIMITED, half_on_miss=True),
)
def m5643a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)
    else:
        c.hit(half=True)


@power(
    "m5643a5",
    level=8,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5643a5(c: Cast) -> None:
    options = [f for f in c.enemies() if c.can_see(f)]
    picked = c.choose(options, f"{c.ref}: mark a target") if options else None
    if picked is None:
        return
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.EOT,
        when=lambda ctx, v=picked: ctx.get("target") == v and _implement_only(ctx),
    )


@power(
    "m5643a6",
    level=8,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=Melee(1),
    target=NO_TARGET,
    trigger="an enemy enters a square adjacent to it",
    on=Trigger(AdjacencyGained, _enemy_closed_on_me, "an enemy enters a square adjacent to it"),
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 11),
)
def m5643a6(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


# ==========================================================================
# m5731
# ==========================================================================


@power(
    "m5731a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m5731a0(c: Cast) -> None:
    from combat_engine.content.monsters.level_02.skirmishers_sa import _aura_holds

    me = c.me
    ring = c.aura(2, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    _aura_holds(c, ring, lambda who: c.vulnerable(5, DamageType.FIRE, on=who, until=When.ENCOUNTER))


@power(
    "m5731a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE),
)
def m5731a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5731a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=13),
)
def m5731a2(c: Cast) -> None:
    if c.strike():
        c.ongoing(10, DamageType.FIRE)


@power(
    "m5731a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT, Keyword.ZONE],
)
def m5731a3(c: Cast) -> None:
    me = c.me
    zone = c.zone(
        c.area(), blocks_sight=True, difficult=True, until=When.SUSTAIN, sustain=MINOR, label=c.ref
    )

    def scorch(eid: int) -> None:
        if zone in c.my_zones():
            c.flat(10, dtype=DamageType.FIRE, on=eid)

    def entered(ev: Any) -> None:
        if ev.zone == zone:
            scorch(ev.actor)

    def ends_turn(ev: TurnEnd) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(zone):
            scorch(ev.actor)

    from combat_engine.engine.events import ZoneEntered

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} enter")
    c.watch(TurnEnd, ends_turn, until=When.ENCOUNTER, on=me, label=f"{c.ref} end")


@power(
    "m5731a4",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d6", 10, dtype=DamageType.FIRE),
)
def m5731a4(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    c.slide(3, on=victim)
    if any(eff.ongoing and eff.ongoing[1] is DamageType.FIRE for eff in c.world.effects.of(victim)):
        c.dazed(on=victim, until=When.SAVE_ENDS)


# ==========================================================================
# m5964
# ==========================================================================


@power(
    "m5964a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7, dtype=DamageType.LIGHTNING),
)
def m5964a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m5964a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.LIGHTNING, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 2, dtype=DamageType.LIGHTNING),
)
def m5964a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m5964a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=11),
)
def m5964a2(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(10, DamageType.LIGHTNING))
    else:
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.LIGHTNING))


@power(
    "m5964a3",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5964a3(c: Cast) -> None:
    me = c.me
    held = c.hover(4, on=me, until=When.SUSTAIN, sustain=MOVE)
    if held is not None:
        c.on_sustain(held, lambda: c.move(1))


# ==========================================================================
# m5978
# ==========================================================================


@power(
    "m5978a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d8", 5),
)
def m5978a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m5978a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d6", 5, dtype=DamageType.FORCE),
)
def m5978a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5978a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE, kind=LIMITED),
)
def m5978a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m5978a3",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m5978a3(c: Cast) -> None:
    c.teleport(10)


# ==========================================================================
# m6361
# ==========================================================================


@power(
    "m6361a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
)
def m6361a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(2, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def cast_implement(ev: PowerUsed) -> None:
        if ev.actor != me:
            return
        row = get(ev.power or "")
        if row is None or Keyword.IMPLEMENT not in row.keywords:
            return
        for foe in c.enemies():
            if foe in c.world.zones.occupants(ring):
                c.flat(5, dtypes=(DamageType.FIRE, DamageType.NECROTIC), on=foe)

    c.watch(PowerUsed, cast_implement, until=When.ENCOUNTER, on=me, label=f"{c.ref} brand")


@power(
    "m6361a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 5, dtype=[DamageType.FIRE, DamageType.NECROTIC]),
)
def m6361a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6361a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=13),
)
def m6361a2(c: Cast) -> None:
    if c.strike():
        c.ongoing(10, dtypes=(DamageType.FIRE, DamageType.NECROTIC))


@power(
    "m6361a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT, Keyword.THUNDER],
    attack=Attack(vs=REF, printed=13),
    damage=Damage(
        "2d8",
        9,
        dtype=[DamageType.FIRE, DamageType.THUNDER],
        kind=LIMITED,
        half_on_miss=True,
    ),
)
def m6361a3(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        c.prone()
        if victim is not None and any(eff.ongoing for eff in c.world.effects.of(victim)):
            c.dazed(on=victim, until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


_M6361_ROLL = "it makes an attack roll or a damage roll"


def _by_me_attack_roll(world: World, me: int, ev: AttackRolled) -> bool:
    return ev.attacker == me


@power(
    "m6361a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=0,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6361_ROLL,
    on=Trigger(AttackRolled, _by_me_attack_roll, _M6361_ROLL),
    dropped=("c.reroll_damage_once()",),
)
def m6361a4(c: Cast) -> None:
    """Only the attack-roll half of "an attack roll or a damage roll" is
    declared: `c.reroll_damage` rerolls every matching roll until a
    duration runs out, not the one roll this trigger names, and there is no
    one-shot form. Confirmed absent: `grep -n "def reroll_damage"
    cast.py` shows only the standing form, and `vocab.py --brief` lists no
    other. "Cannot be reduced in any way" is why this reaches for
    `c.flat`, which does not run the resistance pipeline `c.damage` does.
    """
    _recharge_when_bloodied(c)
    c.reroll_attack(keep="new")
    for mate in c.allies():
        if distance_between(c.world, c.me, mate) <= 10:
            c.flat(15, dtype=DamageType.NECROTIC, on=mate)


# ==========================================================================
# m6405
# ==========================================================================


@power(
    "m6405a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6405a0(c: Cast) -> None:
    c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)


@power(
    "m6405a1",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.blocks_occupancy()",),
)
def m6405a1(c: Cast) -> None:
    """Refused in play: nothing names a creature's own square as
    unenterable against phasing, insubstantial movement or a shift that
    shares space -- `c.shares_space` only grants the opposite, letting
    others in rather than keeping them out. Confirmed absent:
    `grep -n "def blocks_occupancy" cast.py` and
    `uv run scripts/vocab.py --brief | grep blocks_occupancy` are both
    empty."""


@power(
    "m6405a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 4),
)
def m6405a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6405a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d6", 4),
)
def m6405a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m6405a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d8", 11, kind=LIMITED, half_on_miss=True),
    recharge_when=Trigger(Bloodied, about_me,
        "when first bloodied"),
)
def m6405a4(c: Cast) -> None:
    """"Close burst 1, or 2 if bloodied" keeps the printed baseline in the
    header, the way a bloodied attack bonus keeps its own printed total
    there -- a burst's radius has no live `plus=` to read the difference
    through, so the wider footprint while bloodied is not modelled."""
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m6405a5",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6405a5(c: Cast) -> None:
    me = c.me
    c.cure(Condition.SLOWED, Condition.IMMOBILIZED, on=me)
    c.ignores_difficult(on=me, until=When.EOT)
    c.shift(5)


# ==========================================================================
# m6547
# ==========================================================================


@power(
    "m6547a0",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6547a0(c: Cast) -> None:
    me = c.me

    def ranged_cast(ev: PowerUsed) -> None:
        if ev.actor != me:
            return
        row = get(ev.power or "")
        if row is not None and row.reach.kind == "ranged":
            c.no_provoke(on=me, until=When.EOT)

    c.watch(PowerUsed, ranged_cast, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6547a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7),
)
def m6547a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6547a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 8),
)
def m6547a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6547a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6547a3(c: Cast) -> None:
    which = c.choose(["m6547a1", "m6547a2"], f"{c.ref}: battleaxe or shortbow") or "m6547a1"
    foe = next(iter(c.enemies()), None)
    if foe is not None:
        c.use_power(which, on=foe)
        c.use_power(which, on=foe)


@power(
    "m6547a4",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 15, kind=LIMITED),
)
def m6547a4(c: Cast) -> None:
    _recharge_on_miss(c)
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


# ==========================================================================
# m898
# ==========================================================================


@power(
    "m898a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 3),
)
def m898a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m898a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d10", 8),
)
def m898a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m898a2",
    level=8,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger="an enemy enters an adjacent square",
    on=Trigger(AdjacencyGained, _enemy_closed_on_me, "an enemy enters an adjacent square"),
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 8),
)
def m898a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


@power(
    "m898a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("1d6", 8),
)
def m898a3(c: Cast) -> None:
    victim = c.target
    if victim is not None and c.strike():
        c.hit()
        _moves_closer(c, victim, lambda: c.flat(c.roll("1d6") + 8, on=victim))


@power(
    "m898a4",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 8, dtype=DamageType.POISON, kind=LIMITED),
)
def m898a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


_M898A5_ROLL = "it makes an attack roll, a skill check, an ability check, or a saving throw"


def _by_me_rolling(world: World, me: int, ev: AttackRolled) -> bool:
    return ev.attacker == me


@power(
    "m898a5",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ARCANE],
    trigger=_M898A5_ROLL,
    on=Trigger(AttackRolled, _by_me_rolling, _M898A5_ROLL),
)
def m898a5(c: Cast) -> None:
    """Of the four rolls the card names, only the attack roll is declared:
    `c.reroll_attack` reads `c.trigger`, which is only set inside a row the
    dispatcher offered, so the trigger has to be one `AttackRolled` and not
    a plain "usable any time" free action -- there is no single event this
    engine fires for "any of these four kinds of roll." A skill check, an
    ability check or a saving throw rerolled the same way has no hook here.
    """
    c.reroll_attack(keep="best")


@power(
    "m898a6",
    level=8,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m898a6(c: Cast) -> None:
    me = c.me
    options = sorted(
        (f for f in c.enemies() if c.can_see(f) and not c.cursed(on=f)),
        key=lambda f: c.distance(f),
    )
    foe = options[0] if options else None
    if foe is None:
        return
    c.curse(on=foe, until=When.ENCOUNTER)

    def rider(ev: Hit) -> None:
        if ev.attacker != me or ev.target != foe:
            return
        row = get(ev.power or "")
        if row is not None and Keyword.ARCANE in row.keywords:
            c.flat(c.roll("1d6"), on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=f"{c.ref} curse rider")
