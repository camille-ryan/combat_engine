"""Monster abilities, level 6 artillery, second wave.

Twenty stat blocks, a hundred and thirty rows. `artillery.py` holds the
earlier sweep of this level and is not touched here.

Conventions, inherited from the level-1 to level-5 sweeps:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=11)`) and the damage line goes in the
  header as data;
* a **trait** costs no action, has no target, and arms the watches that
  hold it, whatever action the compendium's column claims;
* a printed range band such as "20/40" takes the normal (first) number;
* a card that prints no range at all is melee 1;
* a close burst, blast or area burst whose card names no target set takes
  **enemies**, except where it says "creatures in the burst" outright;
* a recharge or encounter attack says `Damage(..., kind=LIMITED)`, a
  minion's flat damage `Damage("", n, kind=MINION)`;
* `half_on_miss=True` is card data only -- a Miss line is also written as
  `else: c.hit(half=True)`.

Two name leaks in the raw text, both written around rather than copied,
per report: m3238a2's "the Wand" (a capitalised proper noun standing in
for "it"), and m999a2's "Veserabs" (this creature's own species name).
Neither word appears anywhere below; m999's immunity is written by
matching this row's own ref instead.

m3826a7's text ("the m492 gains a +2 bonus to AC while at least one
hobgoblin m3826 is adjacent to it") calls a large natural dragon solo a
hobgoblin and names a second dragon, already fully written in
`artillery.py`, as the beneficiary. Flagged in the report as a likely
extraction defect; written as literally as it can be without a name,
using `c.set_origin` for the one verb that *is* exactly "counts as a
hobgoblin for this purpose" and a ref match for the rest.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.lurkers_sa import _triggering_enemy
from combat_engine.content.monsters.level_02.soldiers_sa import _ref_of
from combat_engine.content.monsters.level_03.brutes_sa import _enemy_closed_on_me
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_04.brutes import _change_shape
from combat_engine.content.monsters.level_04.brutes_sa import _in_shapes
from combat_engine.content.monsters.level_04.lurkers_sa import _hit_me_since_my_turn
from combat_engine.content.monsters.level_05.artillery_sa import (
    _bloodied_edge,
    _one_save_for_both,
)
from combat_engine.content.monsters.level_05.lurkers_sa import (
    _DISLIKED_ROLL,
    _disliked_my_roll,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    INTERRUPT,
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
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Cover,
    Damage,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Ranged,
    Target,
    UpTo,
    Usage,
    When,
    power,
    spread,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackRolled,
    Bloodied,
    DamageApplied,
    Dropped,
    Hit,
    InitiativeRolled,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import cover_between, distance_between
from combat_engine.engine.triggers import Trigger, about_me, both, by_melee, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _hides_if_it_can(c: Cast) -> None:
    """Checked, not rolled -- the engine has no opposed Stealth check, so
    cover or concealment decides it outright."""
    foes = c.enemies()
    if not foes or any(cover_between(c.world, foe, c.me) is not Cover.NONE for foe in foes):
        c.hide()


def _physical(ctx: dict[str, Any]) -> bool:
    """"On melee and ranged attacks" -- a burst or blast does not qualify."""
    from combat_engine.engine import get

    row = get(ctx.get("power") or "")
    return row is not None and row.reach.kind in ("melee", "ranged")


def _recharge_when_bloodied(c: Cast) -> None:
    """"Recharge when first bloodied", printed on top of the die that stays
    in the header. Armed from the body, like the level-1 original."""
    me, ref = c.me, c.ref

    def bled(ev: Bloodied) -> None:
        if ev.actor == me:
            c.restore_use(ref, on=me)

    c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, once=True, label=f"{ref} recharge")


def _nearest_enemy(c: Cast) -> int | None:
    foes = c.enemies()
    return min(foes, key=c.distance, default=None) if foes else None


# ==========================================================================
# m1026
# ==========================================================================


@power(
    "m1026a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("3d4", 6),
)
def m1026a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1026a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d4", 9, dtype=DamageType.FORCE),
)
def m1026a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1026a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.RADIANT, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d6", 6, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m1026a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m1026a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d6", 8, dtype=DamageType.FIRE),
)
def m1026a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1026a4",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON, Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d6", 8, dtype=DamageType.POISON, kind=LIMITED),
)
def m1026a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        _one_save_for_both(c, "attack", 2, 5, DamageType.POISON)


def _implement_attack(ctx: dict[str, Any]) -> bool:
    from combat_engine.engine import get

    row = get(ctx.get("power") or "")
    return row is not None and Keyword.IMPLEMENT in row.keywords


@power(
    "m1026a5",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1026a5(c: Cast) -> None:
    """"Trigger: it makes an attack roll with an implement power." Laid as a
    standing bonus consumed by the first qualifying roll rather than a
    declared Trigger, which is what `c.bonus`'s own `when=`/`once=` already
    say for "your next attack roll of a kind"."""
    c.bonus("attack", 3, on=c.me, until=When.ENCOUNTER, once=True, when=_implement_attack)


# ==========================================================================
# m1029
# ==========================================================================


@power(
    "m1029a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 4),
)
def m1029a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1029a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d10", 5, dtype=DamageType.LIGHTNING),
)
def m1029a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1029a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d10", 5, dtype=DamageType.LIGHTNING),
)
def m1029a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m115778
# ==========================================================================


@power(
    "m115778a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 6),
)
def m115778a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115778a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ILLUSION, Keyword.IMPLEMENT, Keyword.RADIANT],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d6", 5, dtype=DamageType.RADIANT),
)
def m115778a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.SAVE_ENDS)


@power(
    "m115778a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.ILLUSION, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("2d6", 10, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m115778a2(c: Cast) -> None:
    """"Cannot see the m115778" is the target losing sight of the caster,
    not the other way round."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            c.invisible(to=victim, on=c.me, until=When.SAVE_ENDS)


@power(
    "m115778a3",
    level=6,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION, Keyword.TELEPORTATION],
)
def m115778a3(c: Cast) -> None:
    """Two decoys at 1 hit point, same scores and defences as the caster --
    `Summon(hp=1)` with no attack line of its own. A `Companion` already
    sits outside `query.allies`, which is exactly "cannot flank" and
    "cannot use powers" without a line of code."""
    from combat_engine.engine import Summon
    from combat_engine.engine.events import AttackRolled

    c.teleport(5)
    me = c.me
    for _ in range(2):
        c.summon_inline(Summon(hp=1, size="small"))

    def swung(ev: AttackRolled) -> None:
        if ev.attacker == me:
            for comp in c.companions():
                c.world.despawn(comp)

    c.watch(
        AttackRolled, swung, until=When.ENCOUNTER, on=me, once=True,
        label=f"{c.ref} duplicates",
    )


@power(
    "m115778a4",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m115778a4(c: Cast) -> None:
    """Deliberately inert: the disguise changes how up to three allies look
    and nothing a fight rolls, and the Insight-vs-Bluff check it names is not
    one the board makes."""


# ==========================================================================
# m1182
# ==========================================================================


@power(
    "m1182a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 4, dtype=DamageType.FIRE),
)
def m1182a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1182a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d10", 4, dtype=DamageType.FIRE),
)
def m1182a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1182a2",
    level=6,
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d6", 4, dtype=DamageType.FIRE),
    trigger="it is hit by a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "it is hit by a melee attack"),
)
def m1182a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


@power(
    "m1182a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("3d6", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m1182a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            for who in c.within(1, of=victim, side="any"):
                if who != victim and who != c.me and _secondary(c, 11, REF, who):
                    c.damage("1d10", 4, dtype=DamageType.FIRE, on=who)


@power(
    "m1182a4",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("3d6", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m1182a4(c: Cast) -> None:
    """"Any creature that starts its turn adjacent to the target" watches the
    *target*'s neighbours, not this creature's -- `c.ongoing` already
    defaults to save-ends and refuses a weaker duplicate, so a creature
    caught on consecutive turns is not burned twice for it."""
    victim = c.target
    if c.strike():
        c.hit()
    if victim is None:
        return
    me = c.me

    def scorch(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == victim:
            return
        if c.adjacent_to(ev.actor, victim):
            c.ongoing(5, DamageType.FIRE, on=ev.actor)

    c.watch(TurnStart, scorch, until=When.ENCOUNTER, on=me, label=f"{c.ref} scorch")


# ==========================================================================
# m1531
# ==========================================================================


@power(
    "m1531a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 2),
)
def m1531a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1531a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d8", 5, dtype=DamageType.FIRE),
)
def m1531a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m1531a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ALLY,
    keywords=[Keyword.HEALING],
)
def m1531a2(c: Cast) -> None:
    c.heal(10)


@power(
    "m1531a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
)
def m1531a3(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    dtype = c.choose(list(DamageType), f"{c.ref}: resist which damage type") or DamageType.FIRE
    c.resist(10, dtype, on=mate, until=When.ENCOUNTER)


@power(
    "m1531a4",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m1531a4(c: Cast) -> None:
    c.shift(1)


@power(
    "m1531a5",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=11),
    trigger="an enemy moves adjacent to it",
    on=Trigger(AdjacencyGained, _enemy_closed_on_me, "an enemy moves adjacent to it"),
)
def m1531a5(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.push(3, on=foe)
        c.weakened(on=foe, until=When.SAVE_ENDS)


# ==========================================================================
# m1939
# ==========================================================================


@power(
    "m1939a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 6, dtype=DamageType.NECROTIC),
)
def m1939a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1939a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d6", 8, dtype=DamageType.NECROTIC),
)
def m1939a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m1939a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 10, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1939a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(5)
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m1939a3",
    level=6,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger="an enemy moves adjacent to it",
    on=Trigger(AdjacencyGained, _enemy_closed_on_me, "an enemy moves adjacent to it"),
)
def m1939a3(c: Cast) -> None:
    c.shift(1)
    foe = _triggering_enemy(c)
    if foe is not None:
        c.use_power("m1939a1", on=foe)
        if c.landed:
            c.prone(on=foe)


# ==========================================================================
# m2780
# ==========================================================================


@power(
    "m2780a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 5, kind=MINION),
)
def m2780a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2780a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("", 5, dtype=DamageType.FIRE, kind=MINION),
)
def m2780a1(c: Cast) -> None:
    """"Requires bomb" is an ammunition prerequisite; nothing in this engine
    tracks ammunition, the same simplification every thrown weapon already
    gets."""
    if c.strike():
        c.hit()


@power(
    "m2780a2",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger="it is reduced to 0 hit points and no enemy is adjacent to it",
    on=Trigger(Dropped, about_me, "it is reduced to 0 hit points"),
)
def m2780a2(c: Cast) -> None:
    """Checked at the moment it drops: no living enemy already adjacent, and
    then it runs at the nearest one and swings with a fire-boosted basic."""
    me = c.me
    if any(distance_between(c.world, me, foe) <= 1 for foe in c.enemies()):
        return
    foe = _nearest_enemy(c)
    if foe is None:
        return
    c.bonus("damage", 5, dtype=DamageType.FIRE, on=me, until=When.EONT, once=True)
    c.charge_at(foe)
    c.basic(on=foe)


# ==========================================================================
# m3238
# ==========================================================================


@power(
    "m3238a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 4),
)
def m3238a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3238a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d8", 4, dtype=DamageType.PSYCHIC),
)
def m3238a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3238a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.IMPLEMENT],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("1d10", 5),
)
def m3238a2(c: Cast) -> None:
    """The brief's "the Wand" is a leaked proper noun standing in for "it" --
    written as "it" here, per the report."""
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m3238a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("3d8", 4, kind=LIMITED),
)
def m3238a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m3238a4",
    level=6,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    trigger="it takes damage",
    on=Trigger(DamageApplied, targets_me, "it takes damage"),
)
def m3238a4(c: Cast) -> None:
    from combat_engine.content.monsters.level_03.skirmishers import _vanish_until_it_swings

    _vanish_until_it_swings(c, When.EONT)


@power(
    "m3238a5",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3238a5(c: Cast) -> None:
    me = c.me

    def rolled(ev: InitiativeRolled) -> None:
        if ev.actor == me:
            _hides_if_it_can(c)

    c.watch(
        InitiativeRolled, rolled, until=When.ENCOUNTER, on=me, once=True,
        label=f"{c.ref} open",
    )


# ==========================================================================
# m3304
# ==========================================================================


@power(
    "m3304a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 2),
)
def m3304a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3304a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d4", 8, dtype=DamageType.FIRE),
)
def m3304a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3304a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d4", 4, dtype=DamageType.FIRE),
)
def m3304a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            for who in c.within(1, of=victim, side="enemy"):
                if who != victim:
                    c.flat(4, dtype=DamageType.FIRE, on=who)


@power(
    "m3304a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d6", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m3304a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)
        c.prone()


@power(
    "m3304a4",
    level=6,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING, Keyword.TELEPORTATION],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 4, dtype=DamageType.LIGHTNING, kind=LIMITED),
    trigger="an enemy enters an adjacent square",
    on=Trigger(AdjacencyGained, _enemy_closed_on_me, "an enemy enters an adjacent square"),
)
def m3304a4(c: Cast) -> None:
    if c.strike():
        c.hit()
    if c.last:
        c.teleport(5)


# ==========================================================================
# m3314
# ==========================================================================


@power(
    "m3314a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4),
)
def m3314a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3314a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 5),
)
def m3314a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3314a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 5, kind=LIMITED),
)
def m3314a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grants_advantage(to="team", until=When.SAVE_ENDS)


@power(
    "m3314a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 5, kind=LIMITED),
)
def m3314a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m3314a4",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3314a4(c: Cast) -> None:
    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, when=lambda ctx: bool(ctx.get("ranged")))


@power(
    "m3314a5",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m3314a5(c: Cast) -> None:
    """Deliberately inert: the hiding this engine resolves is checked off
    cover and concealment, not rolled, so a penalty to a Stealth check it
    never makes has no combat clause to be part of."""


# ==========================================================================
# m3826
# ==========================================================================


@power(
    "m3826a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 5),
)
def m3826a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(c.roll("1d6"), dtype=DamageType.LIGHTNING)


@power(
    "m3826a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d4", 5),
)
def m3826a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3826a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(3),
)
def m3826a2(c: Cast) -> None:
    """Gore once, claw twice -- the three attacks share this row's target
    list in the order the card prints them."""
    ref = "m3826a0" if c.index == 0 else "m3826a1"
    c.use_power(ref, on=c.target)


@power(
    "m3826a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    no_provoke=True,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d12", 5, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
)
def m3826a3(c: Cast) -> None:
    """No burst or blast size survived extraction for a breath that prints
    "does not provoke" and "Miss: Half" -- both breath tells. Written melee,
    per the convention for a card with no printed reach at all; flagged in
    the report as a likely gap in the source text."""
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m3826a4",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m3826a4(c: Cast) -> None:
    from combat_engine.engine import Powers, use

    known = c.world.get(c.me, Powers)
    if known is None:
        return
    known.restore("m3826a3")
    use(c.world, c.me, "m3826a3")


@power(
    "m3826a5",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=11),
)
def m3826a5(c: Cast) -> None:
    victim = c.target
    if c.strike():
        held = c.stunned(until=When.EONT)
        if held is not None and victim is not None:
            held.on_end.append(
                lambda v=victim: c.penalty("attack", 2, on=v, until=When.SAVE_ENDS)
            )


@power(
    "m3826a6",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d6", 4, dtype=DamageType.LIGHTNING, half_on_miss=True),
)
def m3826a6(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m3826a7",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3826a7(c: Cast) -> None:
    """A trait, whatever the compendium's "standard" column claims. The
    beneficiary is a specific other dragon, already fully written in
    `artillery.py`'s m492 block, found here by matching its ref rather than
    a name -- see the module docstring. `c.set_origin` is the exact verb for
    "counts as its allies' kind for the purpose of [another creature's] ability"."""
    me = c.me
    c.set_origin("hobgoblin", on=me, until=When.ENCOUNTER)
    for ally in c.allies():
        if _ref_of(c, ally) == "m492":
            c.bonus(
                AC, 2, on=ally, until=When.ENCOUNTER,
                when=lambda _ctx, a=ally: c.adjacent_to(a, me),
            )


# ==========================================================================
# m3991
# ==========================================================================


@power(
    "m3991a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 5),
)
def m3991a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3991a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d4", 6, dtype=DamageType.FORCE),
)
def m3991a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3991a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
)
def m3991a2(c: Cast) -> None:
    c.use_power("m3991a1", on=c.target)


@power(
    "m3991a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("3d6", 5, dtype=DamageType.FORCE, kind=LIMITED, half_on_miss=True),
)
def m3991a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m3991a4",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m3991a4(c: Cast) -> None:
    """Deliberately inert: a disguise with no combat reading."""


# ==========================================================================
# m4120
# ==========================================================================


@power(
    "m4120a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 2),
)
def m4120a0(c: Cast) -> None:
    if c.strike(plus=_bloodied_edge(c)):
        c.hit()


@power(
    "m4120a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 5, dtype=DamageType.FIRE),
)
def m4120a1(c: Cast) -> None:
    if c.strike(plus=_bloodied_edge(c)):
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m4120a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("1d6", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4120a2(c: Cast) -> None:
    if c.strike(plus=_bloodied_edge(c)):
        c.hit()
        c.ongoing(5, DamageType.PSYCHIC)


@power(
    "m4120a3",
    level=6,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger="it is hit by a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "it is hit by a melee attack"),
)
def m4120a3(c: Cast) -> None:
    c.teleport(5)


@power(
    "m4120a4",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4120a4(c: Cast) -> None:
    """**Asked at the moment of the swing, not when the minor action is spent.**
    The window runs from this creature's last turn to its next attack, so a set
    taken here is already wrong if anybody hits it in between -- and returning
    early on an empty set means the row does nothing at all when it is used
    before being hit, which is when a monster usually spends a minor.
    `level_04/lurkers_sa.py`'s `m915a4` settled this shape."""
    me = c.me
    c.bonus(
        "attack", 1, kind="power", on=me, until=When.ENCOUNTER, once=True,
        when=lambda ctx: ctx.get("target") in _hit_me_since_my_turn(c),
    )
    c.bonus(
        "damage", 5, on=me, until=When.ENCOUNTER, once=True,
        when=lambda ctx: ctx.get("target") in _hit_me_since_my_turn(c),
    )


# ==========================================================================
# m4145
# ==========================================================================


@power(
    "m4145a0",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 40),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("4d6", 0, kind=LIMITED),
    dropped=("Range(minimum=)",),
)
def m4145a0(c: Cast) -> None:
    """"Minimum range 10" has nowhere to go -- `Range` has no such field."""
    if c.strike():
        c.hit()


# ==========================================================================
# m4646
# ==========================================================================


@power(
    "m4646a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d4"),
)
def m4646a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4646a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d4", 6, dtype=DamageType.FORCE),
)
def m4646a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4646a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 6, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m4646a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m4646a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d6", 5, dtype=DamageType.NECROTIC),
)
def m4646a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4646a4",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d6", 5, dtype=DamageType.POISON, kind=LIMITED),
)
def m4646a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        _one_save_for_both(c, "attack", 2, 5, DamageType.POISON)


@power(
    "m4646a5",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.IMPLEMENT],
)
def m4646a5(c: Cast) -> None:
    """"Requires wand" is an equipment prerequisite this engine does not
    track, the same simplification every implement power already gets."""
    c.bonus("attack", 3, on=c.me, until=When.ENCOUNTER, once=True)


# ==========================================================================
# m4771
# ==========================================================================


@power(
    "m4771a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 5),
)
def m4771a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4771a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d4", 5),
)
def m4771a1(c: Cast) -> None:
    """"The dagger returns" is ammunition flavour, not tracked."""
    if c.strike():
        c.hit()


@power(
    "m4771a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
)
def m4771a2(c: Cast) -> None:
    c.use_power("m4771a1", on=c.target)


@power(
    "m4771a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 4, kind=LIMITED, half_on_miss=True),
)
def m4771a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.UNTYPED)
    else:
        c.hit(half=True)


@power(
    "m4771a4",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger="it hits with m4771a1",
    on=Trigger(Hit, by_melee, "it hits with m4771a1"),
)
def m4771a4(c: Cast) -> None:
    """Fires manually off the dagger's own Hit rather than the declared
    trigger above -- see the body; the recharge condition ("when the target
    saves against the effect") is read back off `SavingThrow.against`, which
    is `str(effect)` for the effect that laid it, so holding the same object
    this call returns is what makes the match exact."""
    from combat_engine.engine.events import SavingThrow

    ev = c.trigger
    if not isinstance(ev, Hit) or ev.attacker != c.me or ev.power != "m4771a1":
        return
    victim = ev.target
    if victim is None:
        return
    held = c.ongoing(10, on=victim, until=When.SAVE_ENDS)
    if held is None:
        return
    me, ref = c.me, c.ref

    def recharged(saved_ev: SavingThrow) -> None:
        if saved_ev.actor == victim and saved_ev.saved and saved_ev.against == str(held):
            c.restore_use(ref, on=me)

    c.watch(
        SavingThrow, recharged, until=When.SAVE_ENDS, on=me, once=True,
        label=f"{ref} recharge",
    )


@power(
    "m4771a5",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m4771a5(c: Cast) -> None:
    """Deliberately inert: a disguise with no combat reading."""


@power(
    "m4771a6",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m4771a6(c: Cast) -> None:
    """Moving on water as solid ground is already true of a board with no
    water-penalty mechanic to exempt it from."""


# ==========================================================================
# m5368
# ==========================================================================


@power(
    "m5368a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5368a0(c: Cast) -> None:
    """Rough ground costs it nothing while it shifts, and nothing else.

    `when="shift"` is the narrowing every one of these cards prints and this
    verb could not say. It is spent in the *search*: a square of difficult
    terrain costs two, a shift is one, so without the exemption the square is
    never offered as a shift destination at all.
    """
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER, when="shift")


@power(
    "m5368a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 5),
)
def m5368a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m5368a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 5),
)
def m5368a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5368a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 5),
)
def m5368a3(c: Cast) -> None:
    """"Its allies" is read as its present allies, the same simplification a
    dynamic membership grant always takes here."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            for ally in c.allies():
                c.gains_advantage(
                    lambda ctx, v=victim: ctx.get("target") == v, until=When.EONT, on=ally,
                )


@power(
    "m5368a4",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(20),
    target=ONE_ALLY,
    keywords=[Keyword.WEAPON],
)
def m5368a4(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    c.flat(5, on=mate)
    c.save(on=mate, bonus=2)


@power(
    "m5368a5",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_DISLIKED_ROLL,
    on=Trigger(AttackRolled, _disliked_my_roll, _DISLIKED_ROLL),
)
def m5368a5(c: Cast) -> None:
    c.reroll_attack(keep="new")


# ==========================================================================
# m5460
# ==========================================================================


@power(
    "m5460a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 8),
)
def m5460a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5460a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(30),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d10", 8, dtype=DamageType.LIGHTNING),
)
def m5460a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            other = next(
                (
                    f
                    for f in c.enemies()
                    if f != victim and distance_between(c.world, f, victim) <= 5
                ),
                None,
            )
            if other is not None:
                c.flat(5, dtype=DamageType.LIGHTNING, on=other)


@power(
    "m5460a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING, Keyword.THUNDER, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage(
        "2d10",
        4,
        dtype=[DamageType.LIGHTNING, DamageType.THUNDER],
        kind=LIMITED,
        half_on_miss=True,
    ),
)
def m5460a2(c: Cast) -> None:
    _recharge_when_bloodied(c)
    victim = c.target
    if c.strike():
        c.hit()
        c.prone()
        if victim is not None:
            c.slide(2, on=victim)
    else:
        c.hit(half=True)
        if victim is not None:
            c.slide(1, on=victim)
    if c.first:
        area = spread({c.here}, 1)
        zone = c.zone(area, until=When.SONT, label=c.ref)
        me = c.me

        def toll(ev: TurnEnd) -> None:
            if ev.ghost or ev.actor not in c.enemies():
                return
            if ev.actor in c.world.zones.occupants(zone):
                c.flat(10, dtypes=(DamageType.THUNDER, DamageType.LIGHTNING), on=ev.actor)

        c.watch(TurnEnd, toll, until=When.SONT, on=me, label=f"{c.ref} zone")


@power(
    "m5460a3",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
    dropped=("c.fall(forced=)",),
)
def m5460a3(c: Cast) -> None:
    """"Must land or fall at the end of each move" has nothing to enforce it
    -- nothing calls `c.fall` automatically at the end of a move."""
    c.mode("fly", 8, on=c.me, until=When.ENCOUNTER)


@power(
    "m5460a4",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
    todo=("c.grant_action(standard)",),
)
def m5460a4(c: Cast) -> None:
    """"Takes a standard action" names no word `actions.legal` knows --
    `c.grant_action` only ever understands shift, stand, escape and
    second_wind, and a fifth word is carried and does nothing."""


# ==========================================================================
# m5673
# ==========================================================================


@power(
    "m5673a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5673a0(c: Cast) -> None:
    me = c.me
    acted: set[int] = set()

    def opened(ev: TurnStart) -> None:
        if not ev.ghost:
            acted.add(ev.actor)

    c.watch(TurnStart, opened, until=When.ENCOUNTER, on=me, label=f"{c.ref} roster")
    c.bonus(
        "damage", 0, dice="1d10", on=me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") not in acted,
    )


@power(
    "m5673a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 5),
)
def m5673a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5673a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d8", 5, dtype=DamageType.FIRE),
)
def m5673a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m5673a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d10", 9, dtype=DamageType.COLD, kind=LIMITED),
)
def m5673a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


# ==========================================================================
# m5840
# ==========================================================================


@power(
    "m5840a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 7),
)
def m5840a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5840a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 5),
)
def m5840a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5840a2",
    level=6,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("Attack(vs=)",),
)
def m5840a2(c: Cast) -> None:
    """Retargeting its own ranged attack's defence line is not sayable:
    `Attack.vs` is fixed at declaration, not switchable per use."""
    c.bonus("damage", 5, on=c.me, until=When.EOT, when=_physical)


@power(
    "m5840a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5840a3(c: Cast) -> None:
    _recharge_when_bloodied(c)
    c.bonus(AC, 2, on=c.me, until=When.SONT)
    c.bonus(REF, 2, on=c.me, until=When.SONT)


# ==========================================================================
# m5878
# ==========================================================================


def _near_m5879(c: Cast) -> bool:
    return any(_ref_of(c, who) == "m5879" for who in c.within(10, of=c.me, side="any"))


@power(
    "m5878a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5878a0(c: Cast) -> None:
    """A manually-armed watch, not a declared trigger: `c.reroll_save` only
    means anything inside a dispatched row, and this is a standing trait.
    Mutating the `SavingThrow` directly is the same operation that verb
    does internally, against the fixed DC 10 every save in this engine
    resolves at."""
    me = c.me

    def reroll(ev: Any) -> None:
        if ev.actor != me or not _near_m5879(c):
            return
        again = c.world.rng.d20().total
        if again > ev.natural:
            ev.natural = again
            ev.saved = (ev.natural + ev.bonus) >= 10

    from combat_engine.engine.events import SavingThrow

    c.watch(SavingThrow, reroll, until=When.ENCOUNTER, on=me, label=f"{c.ref} twice")


@power(
    "m5878a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 5),
)
def m5878a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5878a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.POISON],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d8", 5, dtype=DamageType.POISON),
)
def m5878a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5878a3",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d10", 3, dtype=DamageType.POISON, kind=LIMITED, half_on_miss=True),
)
def m5878a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m5878a4",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m5878a4(c: Cast) -> None:
    c.shift(1)


@power(
    "m5878a5",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(10),
    target=Target(side="ally", everyone=True, label="kobold allies in the burst"),
    dropped=("Target.creature_kind",),
)
def m5878a5(c: Cast) -> None:
    """The species restriction cannot be read **off this block**, so it is
    dropped rather than used to refuse the row for every ally regardless.

    Not because the engine cannot hold a species: `kinds_of` reads the
    `keywords`, `kind` and `origin` columns, 101 distinct words across the
    corpus, and this creature's own species is one of them -- `m5445` carries it
    in both `keywords` and `kind`, so `m5445a3` asks the identical question with
    `c.is_kind` and fires. This block carries only its size, origin, type and the
    parenthetical, and not the species word, so the same call is false for its
    own kin. Two blocks of one species extracted differently, which is an ETL
    inconsistency rather than a missing capability."""
    c.temp_hp(5)
    c.grant_action("shift", ActionType.FREE, on=c.target)


@power(
    "m5878a6",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=9),
    trigger="an enemy ends its movement adjacent to it",
    on=Trigger(AdjacencyGained, _enemy_closed_on_me, "an enemy ends its movement adjacent to it"),
)
def m5878a6(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    if c.strike(on=foe):
        c.push(3, on=foe)
        c.immobilized(on=foe, until=When.SAVE_ENDS)
    else:
        c.push(3, on=foe)
        c.slowed(on=foe, until=When.SAVE_ENDS)


# ==========================================================================
# m5939
# ==========================================================================


@power(
    "m5939a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m5939a0(c: Cast) -> None:
    me = c.me

    def closed(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me:
            return
        if c.adjacent_to(ev.actor, me):
            c.ongoing(5, DamageType.POISON, on=ev.actor)

    c.watch(TurnEnd, closed, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m5939a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 8),
)
def m5939a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5939a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d6", 3, dtype=DamageType.NECROTIC),
)
def m5939a2(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:

            def worsen(eff: Effect) -> None:
                c.world.effects.end(eff, "worsened")
                c.immobilized(on=victim, until=When.SAVE_ENDS)

            c.condition(
                Condition.SLOWED, until=When.SAVE_ENDS, on=victim,
                ongoing=(5, DamageType.POISON), escalate=worsen,
            )


@power(
    "m5939a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d6", 3, dtype=DamageType.NECROTIC, kind=LIMITED, half_on_miss=True),
)
def m5939a3(c: Cast) -> None:
    """"Centred on a creature taking ongoing poison" is a placement rule for
    the burst's origin and not this row's to enact -- the decider places
    bursts, this just rolls one."""
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.POISON)
    else:
        c.hit(half=True)
        c.ongoing(5, DamageType.POISON)


# ==========================================================================
# m5957
# ==========================================================================

_M5957_SHAPE = "m5957a5 "
_M5957_SHAPES = ("wolf", "human", "hybrid")


@power(
    "m5957a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.silvered()",),
)
def m5957a0(c: Cast) -> None:
    c.regeneration(5, until=When.ENCOUNTER, on=c.me)


@power(
    "m5957a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 2),
    requires=_in_shapes(_M5957_SHAPE, "human", "hybrid"),
    requires_text="it must be in humanoid or hybrid form",
)
def m5957a1(c: Cast) -> None:
    if c.strike():
        c.damage("2d6", 6 if c.bloodied() else 2)


@power(
    "m5957a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 2),
    requires=_in_shapes(_M5957_SHAPE, "wolf", "hybrid"),
    requires_text="it must be in beast or hybrid form",
    dropped=("c.contract(ref)",),
)
def m5957a2(c: Cast) -> None:
    """Disease contraction has no verb -- the same symbol twenty other rows
    already wait on. The damage half is exact."""
    if c.strike():
        c.damage("2d6", 6 if c.bloodied() else 2)


@power(
    "m5957a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d10", 9, dtype=DamageType.LIGHTNING),
)
def m5957a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5957a4",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d10", 5, dtype=DamageType.THUNDER),
)
def m5957a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()


@power(
    "m5957a5",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m5957a5(c: Cast) -> None:
    _change_shape(c, _M5957_SHAPE, _M5957_SHAPES)


# ==========================================================================
# m6023
# ==========================================================================


@power(
    "m6023a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m6023a0(c: Cast) -> None:
    from combat_engine.engine.events import SurgeSpent

    ring = c.aura(2, until=When.ENCOUNTER)
    me = c.me

    def spent(ev: SurgeSpent) -> None:
        if ev.actor in c.enemies() and ev.actor in c.world.zones.occupants(ring):
            c.weakened(on=ev.actor, until=When.EOTNT)

    c.watch(SurgeSpent, spent, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m6023a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6023a1(c: Cast) -> None:
    """Breathing underwater is already true of a board with no drowning
    mechanic to exempt it from. The attack bonus is the real half."""
    c.bonus(
        "attack", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: c.terrain("water") and not c.is_kind("aquatic", on=ctx.get("target")),
    )


@power(
    "m6023a2",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m6023a2(c: Cast) -> None:
    me = c.me

    def crit(ev: Hit) -> None:
        if ev.target == me and getattr(ev.result, "critical", False):
            c.heal(5, on=ev.attacker)

    c.watch(Hit, crit, until=When.ENCOUNTER, on=me, label=f"{c.ref} backlash")


@power(
    "m6023a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4),
)
def m6023a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6023a4",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 3, dtype=DamageType.ACID),
)
def m6023a4(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            if c.is_(Condition.IMMOBILIZED, on=victim):
                c.ongoing(5, DamageType.ACID, on=victim)
            else:
                c.immobilized(on=victim, until=When.EONT)


@power(
    "m6023a5",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.POISON, Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d10", 6, dtype=[DamageType.POISON, DamageType.THUNDER], kind=LIMITED),
)
def m6023a5(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m6114
# ==========================================================================


@power(
    "m6114a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC, Keyword.POISON],
)
def m6114a0(c: Cast) -> None:
    ring = c.aura(1, until=When.ENCOUNTER)
    me = c.me

    def toll(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.flat(5, dtypes=(DamageType.NECROTIC, DamageType.POISON), on=ev.actor)

    c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m6114a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6114a1(c: Cast) -> None:
    from combat_engine.engine.components import Position

    me = c.me
    pending: dict[str, Any] = {"at": None}

    def slain(ev: Dropped) -> None:
        if getattr(ev, "source", None) != me or not ev.dead:
            return
        if c.is_kind("humanoid", on=ev.actor) and not c.is_kind("undead", on=ev.actor):
            pos = c.world.get(ev.actor, Position)
            pending["at"] = pos.square if pos else None

    def dawn(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost and pending["at"] is not None:
            c.summon("m115915", at=pending["at"])
            pending["at"] = None

    c.watch(Dropped, slain, until=When.ENCOUNTER, on=me, label=f"{c.ref} rise")
    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=f"{c.ref} rise2")


@power(
    "m6114a2",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6114a2(c: Cast) -> None:
    from combat_engine.content.monsters.level_03.skirmishers_sa import _shoved_by_hand

    c.shares_space(on=c.me, difficult=True, until=When.ENCOUNTER)
    c.resist_forced(99, on=c.me, until=When.ENCOUNTER, when=_shoved_by_hand)


def _adjacent_free_square(c: Cast, square: Any) -> Any | None:
    """An unoccupied square adjacent to an arbitrary point -- `Cast.
    _free_square_near` only ever looks near the caster."""
    for sq in sorted(spread({square}, 1) - {square}):
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None:
            return sq
    return None


@power(
    "m6114a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    no_provoke=True,
    keywords=[Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d6", 7, dtype=[DamageType.NECROTIC, DamageType.POISON]),
)
def m6114a3(c: Cast) -> None:
    from combat_engine.engine.components import Position

    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            pos = c.world.get(victim, Position)
            if pos is not None:
                sq = _adjacent_free_square(c, pos.square)
                if sq is not None:
                    c.summon("m6115", at=sq)


@power(
    "m6114a4",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 7, dtype=[DamageType.NECROTIC, DamageType.POISON], kind=LIMITED),
)
def m6114a4(c: Cast) -> None:
    """"The m6114a0 increases to aura 2 until the end of its next turn" --
    `c.widen_areas` is the verb for growing a standing area of this
    creature's own, which an aura is."""
    if c.strike():
        c.hit()
    if c.last:
        c.widen_areas(1, on=c.me, until=When.EONT)


@power(
    "m6114a5",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    no_provoke=True,
)
def m6114a5(c: Cast) -> None:
    _recharge_when_bloodied(c)
    c.move(9, at="burrow")


@power(
    "m6114a6",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m6114a6(c: Cast) -> None:
    c.use_power("m6114a3")
    c.use_power("m6114a3")
