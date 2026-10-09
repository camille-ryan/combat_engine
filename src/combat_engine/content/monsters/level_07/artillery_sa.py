"""Monster abilities, level 7 artillery, second wave.

Twenty-one stat blocks, 75 rows. `artillery.py` does not exist at this level
yet, so there is no earlier sweep to split against; the role file is new.
Three blocks print no abilities at all and have nothing to decorate: m2987,
m720, m725.

Conventions, inherited from the level-5/6 artillery sweeps and this level's
own `brutes_sa.py`:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=N)`) and the damage line goes in the
  header as data;
* a **trait** costs no action, has no target, and arms the watches that
  hold it, whatever the compendium's action column claims;
* a printed range band such as "20/40" takes the first (normal) number; a
  card with no printed range at all is melee 1, including "Reach 0" (the
  nearest `Melee(n)` can say);
* a close burst, blast or area naming no target set takes **enemies**,
  except where it says "creatures in the burst" outright;
* `half_on_miss=True` is card data only -- a Miss line is also written as
  `else: c.hit(half=True)`;
* a recharge or encounter attack says `Damage(..., kind=LIMITED)`, a
  minion's flat damage `Damage("", n, kind=MINION)`;
* a blow of two damage types rolled as one keeps the first in the header
  and is marked `dropped=("Damage(dtypes=)",)` -- a *secondary*, separate
  amount of two types (not the header's own blow) is written with
  `c.flat(..., dtypes=(...))` instead, which needs no marker;
  "+N vs AC, or +N+1 against a bloodied target" keeps the printed total in
  the header and the difference is read live off `c.bloodied`.

One block (`m3378a4`) prints "Area burst 2" with no "within" radius at all,
unlike every other area burst in this file, which always names one --
written as `CloseBurst(2)` instead, the shape every other self-centered
reaction burst in the tree takes. Two "requires X" clauses (`m1802a2`,
`m2782a4`) name what reads as ammunition/weapon prerequisites and are not
tracked, the same simplification every thrown or two-handed weapon power
already gets elsewhere in this project.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_01.artillery_sa import _recharge_when_bloodied
from combat_engine.content.monsters.level_02.lurkers_sa import _triggering_enemy, _twice
from combat_engine.content.monsters.level_03.brutes_sa import _enemy_closed_on_me
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_04.brutes import _change_shape
from combat_engine.content.monsters.level_04.brutes_sa import _in_shapes
from combat_engine.content.monsters.level_07.brutes import _is_bloodied
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
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
    Keyword,
    Melee,
    Powers,
    Ranged,
    UpTo,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.events import AdjacencyGained, AttackRolled, Hit, TurnStart
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.triggers import Trigger, both, by_melee, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _would_hit_me(world: World, me: int, ev: AttackRolled) -> bool:
    """"Would be hit by an attack" -- read off the roll before it resolves,
    which is what lets the interrupt force a reroll instead of answering a
    `Hit` that has already happened."""
    return ev.target == me and ev.total >= ev.defence


def _my_crit(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and ev.critical


def _knows(c: Cast, who: int, ref: str) -> bool:
    powers = c.world.get(who, Powers)
    return powers is not None and ref in powers.known


_M6191_SHAPE = "m6191a5 "


# ==========================================================================
# m1119
# ==========================================================================


@power(
    "m1119a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 4, dtype=DamageType.POISON),
)
def m1119a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1119a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d8", 3, dtype=DamageType.FIRE, kind=LIMITED),
)
def m1119a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m1119a2",
    level=7,
    usage=DAILY,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.SLEEP],
    attack=Attack(vs=WILL, printed=12),
)
def m1119a2(c: Cast) -> None:
    victim = c.target

    def falls_unconscious(eff: Effect, v: int = victim) -> None:
        c.world.effects.end(eff, "it falls unconscious")
        c.condition(Condition.UNCONSCIOUS, until=When.SAVE_ENDS, on=v)

    if victim is not None and c.strike():
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=victim, escalate=falls_unconscious)


@power(
    "m1119a3",
    level=7,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_is_bloodied,
    requires_text="it must be bloodied",
)
def m1119a3(c: Cast) -> None:
    """"Conferred by amulet" is equipment flavour, not tracked."""
    c.temp_hp(14, on=c.me)


@power(
    "m1119a4",
    level=7,
    usage=DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    out_of_combat=True,
)
def m1119a4(c: Cast) -> None:
    """Deliberately inert: a disguise with no combat reading, and the DC 28
    Insight check it names is never rolled on a board that already knows
    what stands on it."""


# ==========================================================================
# m115727
# ==========================================================================


@power(
    "m115727a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("", 7, dtype=DamageType.FORCE, kind=MINION),
)
def m115727a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m115727a1",
    level=7,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m115727a1(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m1482
# ==========================================================================


@power(
    "m1482a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d6", 4, dtype=DamageType.LIGHTNING),
)
def m1482a0(c: Cast) -> None:
    if c.strike():
        c.hit()


_M1482_HIT = "it is hit by a melee attack"


@power(
    "m1482a1",
    level=7,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.LIGHTNING],
    trigger=_M1482_HIT,
    on=Trigger(Hit, both(targets_me, by_melee), _M1482_HIT),
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d6", 5, dtype=DamageType.LIGHTNING),
)
def m1482a1(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.push(1, on=foe)
        c.stunned(on=foe, until=When.EONT)


@power(
    "m1482a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d6", 5, dtype=DamageType.THUNDER),
)
def m1482a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# ==========================================================================
# m1802
# ==========================================================================


@power(
    "m1802a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 5),
)
def m1802a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1802a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d4", 5),
)
def m1802a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m1802a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    attack=Attack(vs=REF, printed=10),
    damage=Damage("4d4", 5, kind=LIMITED),
)
def m1802a2(c: Cast) -> None:
    """"Requires m1802a1" in the brief reads as an equipment prerequisite
    (a loaded weapon), not tracked -- the same simplification every thrown
    power already gets."""
    if c.strike():
        c.hit()
        c.slide(2)
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m1802a3",
    level=7,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it would be hit by an attack",
    on=Trigger(AttackRolled, _would_hit_me, "it would be hit by an attack"),
)
def m1802a3(c: Cast) -> None:
    c.reroll_attack(keep="new")


# ==========================================================================
# m1823
# ==========================================================================


@power(
    "m1823a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d4", 5),
)
def m1823a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.bloodied(c.me):
            c.flat(2)


@power(
    "m1823a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d8", 5, dtype=DamageType.NECROTIC),
)
def m1823a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.bloodied(c.me):
            c.flat(5, dtype=DamageType.NECROTIC)


@power(
    "m1823a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("3d10", 5, dtype=[DamageType.FIRE, DamageType.NECROTIC], kind=LIMITED),
)
def m1823a2(c: Cast) -> None:
    """The bloodied clause prints the same total both ways, so there is
    nothing conditional to add. The fire-and-necrotic blow is one roll of
    two types; `c.hit()` can only carry the one in the header."""
    if c.strike():
        c.hit()


@power(
    "m1823a3",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1823a3(c: Cast) -> None:
    me = c.me

    def crowded(ctx: dict, m: int = me) -> bool:
        who = ctx.get("target")
        if who is None:
            return False
        return len([a for a in (c.allies()) if a != m and c.adjacent_to(a, who)]) >= 2

    c.bonus("damage", 5, on=me, until=When.ENCOUNTER, when=crowded)


# ==========================================================================
# m2782
# ==========================================================================


@power(
    "m2782a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 5),
)
def m2782a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2782a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d10", 6),
)
def m2782a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2782a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    requires=_is_bloodied,
    requires_text="it must be bloodied",
)
def m2782a2(c: Cast) -> None:
    """`target=NO_TARGET` left `c.target` empty and `c.basic()` nothing to
    swing at -- a basic attack needs a chosen target like any other."""
    if c.target is not None:
        c.basic(on=c.target)
    c.heal(16, on=c.me)


@power(
    "m2782a3",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=10),
)
def m2782a3(c: Cast) -> None:
    if c.strike():
        c.push(2)


@power(
    "m2782a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d10", 6, kind=LIMITED),
)
def m2782a4(c: Cast) -> None:
    """"Requires battleaxe" is equipment, not tracked."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


# m2987 prints no abilities -- nothing to decorate.


# ==========================================================================
# m3378
# ==========================================================================


@power(
    "m3378a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 2),
)
def m3378a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3378a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d4", 8),
)
def m3378a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3378a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d4", 4, dtype=DamageType.FIRE),
)
def m3378a2(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            for foe in c.within(1, of=victim, side="enemy"):
                if foe != victim:
                    c.flat(4, dtype=DamageType.FIRE, on=foe)


@power(
    "m3378a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d6", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m3378a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)
        c.prone()


_M3378_ADJ = "an enemy enters an adjacent square"


@power(
    "m3378a4",
    level=7,
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING, Keyword.TELEPORTATION],
    trigger=_M3378_ADJ,
    on=Trigger(AdjacencyGained, _enemy_closed_on_me, _M3378_ADJ),
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("4d6", 4, dtype=DamageType.LIGHTNING),
)
def m3378a4(c: Cast) -> None:
    """"Area burst 2" prints no "within" radius anywhere else in this file --
    written as a close burst centred on the caster, which is what every
    other self-targeted reaction burst here is. The recoil and the
    teleport are each a once-per-power line, not one per enemy the burst
    catches, so both are paid off whichever target resolves first."""
    if c.strike():
        dealt = c.hit()
        if c.first:
            c.flat(dealt // 2, dtype=DamageType.LIGHTNING, on=c.me)
    if c.first:
        c.teleport(5)


@power(
    "m3378a5",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    todo=("c.retype()",),
)
def m3378a5(c: Cast) -> None:
    """Refused in play: no verb overrides a row's own declared damage type
    at cast time, which is this trait's entire printed effect. Confirmed
    absent: `grep -n "def retype" src/combat_engine/engine/cast.py` and
    `uv run scripts/vocab.py --brief | grep retype` both empty.

    A separate symbol from `f1231`'s `c.retype_damage(dtypes=)` on purpose:
    that one adds a second type to what a named row deals, this one
    *replaces* the type outright, for a duration. Same missing machinery --
    reaching another row's damage type -- but one symbol going green would
    falsely finish the other, so they stay apart."""


# ==========================================================================
# m3624
# ==========================================================================


@power(
    "m3624a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 4),
)
def m3624a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3624a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 4),
)
def m3624a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3624a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 4, kind=LIMITED),
)
def m3624a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.EONT)


# ==========================================================================
# m3643
# ==========================================================================


@power(
    "m3643a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(0),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d4", 0),
)
def m3643a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m3643a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("1d10", 5, dtype=DamageType.NECROTIC),
    dropped=("c.insubstantial(to=)",),
)
def m3643a1(c: Cast) -> None:
    """"Treats the m3643 as insubstantial" is insubstantial against one
    named foe only, and applying it broadly would halve damage from
    everybody rather than from this target.

    **Re-pointed from `c.insubstantial(when=)` to `(to=)`.** The gap is a
    *scope*, not a condition -- the trait is never switched off, it only
    faces one way -- and `c.invisible` already spells a one-sided version of
    itself `to=`. Filed under the old symbol it would have reported ready
    when #470's suspension landed, which answers a different sentence
    entirely.
    """
    if c.strike():
        c.hit()


@power(
    "m3643a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d8", 5, dtype=DamageType.NECROTIC),
)
def m3643a2(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.EONT)
        if victim is not None:
            for foe in c.within(1, of=victim, side="enemy"):
                if foe != victim:
                    c.flat(5, dtype=DamageType.NECROTIC, on=foe)
                    c.slowed(on=foe, until=When.EONT)


@power(
    "m3643a3",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3643a3(c: Cast) -> None:
    c.zone({c.here}, blocks_sight=True, until=When.EONT, label=c.ref)


# ==========================================================================
# m3982
# ==========================================================================


@power(
    "m3982a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.POISON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 6),
)
def m3982a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(c.roll("1d6"), dtypes=(DamageType.LIGHTNING, DamageType.POISON))


_M3982_HIT = "it is hit by a melee attack"


@power(
    "m3982a1",
    level=7,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3982_HIT,
    on=Trigger(Hit, both(targets_me, by_melee), _M3982_HIT),
)
def m3982a1(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.use_power("m3982a0", on=foe)
        c.shift(1)


@power(
    "m3982a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d8", 4, dtype=DamageType.LIGHTNING),
)
def m3982a2(c: Cast) -> None:
    """"See also bloodied spark" points at this creature's own `m3982a6`
    rider -- nothing extra to add here."""
    if c.strike():
        c.hit()


@power(
    "m3982a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
)
def m3982a3(c: Cast) -> None:
    c.use_power("m3982a2", on=c.target)


@power(
    "m3982a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d8", 4, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m3982a4(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()


@power(
    "m3982a5",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d12", 4, dtype=DamageType.LIGHTNING, kind=LIMITED, half_on_miss=True),
)
def m3982a5(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(5, DamageType.LIGHTNING))
        c.hit()
    else:
        c.hit(half=True)
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m3982a6",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3982a6(c: Cast) -> None:
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me or ev.power != "m3982a2" or not c.bloodied(me):
            return
        if ev.target is not None:
            c.ongoing(5, DamageType.LIGHTNING, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label="m3982a6")


# ==========================================================================
# m4001
# ==========================================================================


@power(
    "m4001a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m4001a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4001a1",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d4", 5, dtype=DamageType.NECROTIC),
)
def m4001a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4001a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("3d6", 5, kind=LIMITED, half_on_miss=True),
)
def m4001a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)


@power(
    "m4001a3",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
)
def m4001a3(c: Cast) -> None:
    """A summoned ally the leader puts on the board mid-fight, named by its
    own ref rather than a word. Its exact square within range and its
    precise initiative slot are both `c.summon`'s own defaults."""
    c.summon("m5447")


# ==========================================================================
# m5732
# ==========================================================================


@power(
    "m5732a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 4),
)
def m5732a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5732a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d6", 4),
)
def m5732a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5732a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=UpTo(2),
)
def m5732a2(c: Cast) -> None:
    _twice(c, "m5732a1")


@power(
    "m5732a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(6),
    target=UpTo(3),
)
def m5732a3(c: Cast) -> None:
    """"Uses m5732a1 three times" is the same spread-or-stack shape `_twice`
    answers for two; no ready helper says it for three, so the top-up is
    written here directly rather than a new helper for one row."""
    c.use_power("m5732a1", on=c.target)
    if c.last:
        for _ in range(3 - len(c.targets)):
            c.use_power("m5732a1", on=c.target)


@power(
    "m5732a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5732a4(c: Cast) -> None:
    _recharge_when_bloodied(c)
    c.shift(4)
    foe = next((f for f in c.enemies() if c.distance(f) <= 6), None)
    if foe is not None:
        c.use_power("m5732a1", on=foe)


@power(
    "m5732a5",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    no_provoke=True,
)
def m5732a5(c: Cast) -> None:
    c.jump(7)


# ==========================================================================
# m5781
# ==========================================================================


@power(
    "m5781a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5781a0(c: Cast) -> None:
    me, ref = c.me, c.ref

    def dawn(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        if any(_knows(c, w, ref) for w in c.within(1, of=me, side="ally") if w != me):
            # `bare=True` rolls against nothing and ends nothing -- the
            # printed line names "one effect that a save can end", which is
            # the ordinary save-ends search this call makes without it.
            c.save(on=me)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=ref)


@power(
    "m5781a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("", 6, kind=MINION),
)
def m5781a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5781a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("", 6, kind=MINION),
)
def m5781a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5781a3",
    level=7,
    usage=AT_WILL,
    once_per_round=True,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it scores a critical hit against an enemy",
    on=Trigger(Hit, _my_crit, "it scores a critical hit against an enemy"),
)
def m5781a3(c: Cast) -> None:
    foe = getattr(c.trigger, "target", None)
    if foe is not None:
        c.bonus("attack", 2, kind="power", on=c.me, until=When.EOT, once=True)
        c.basic(on=foe)


# ==========================================================================
# m6191
# ==========================================================================


@power(
    "m6191a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6191a0(c: Cast) -> None:
    from combat_engine.engine import get

    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me or ev.target is None:
            return
        row = get(ev.power or "")
        if row is not None and Keyword.FIRE in row.keywords:
            c.vulnerable(5, DamageType.FIRE, on=ev.target, until=When.EONT)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label="m6191a0")


@power(
    "m6191a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    requires=_in_shapes(_M6191_SHAPE, "human", "hybrid"),
    requires_text="it must be in human or hybrid form",
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 5),
)
def m6191a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6191a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    requires=_in_shapes(_M6191_SHAPE, "human", "hybrid"),
    requires_text="it must be in human or hybrid form",
    attack=Attack(vs=REF, printed=12),
    damage=Damage("3d4", 4, dtype=DamageType.FIRE),
)
def m6191a2(c: Cast) -> None:
    """"If it targets only one creature with this power, it can make this
    attack twice against that creature" -- asked once for the whole use,
    off how many targets it actually has."""
    victim = c.target
    if c.strike():
        c.hit()
    if c.first and len(c.targets) == 1 and victim is not None and c.strike(on=victim):
        c.hit(on=victim)


@power(
    "m6191a3",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.FIRE, Keyword.IMPLEMENT],
    requires=_in_shapes(_M6191_SHAPE, "human", "hybrid"),
    requires_text="it must be in human or hybrid form",
    attack=Attack(vs=WILL, printed=10),
)
def m6191a3(c: Cast) -> None:
    me = c.me
    victim = c.target
    if c.strike():
        c.ongoing(5, DamageType.FIRE)
        if victim is not None:
            c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim)
    if c.first:
        zone = c.aura(5, label="m6191a3 light", until=When.EONT, on=me, sustain=MINOR)
        for foe in c.enemies():
            c.penalty(
                "save", 2, on=foe, until=When.EONT,
                when=lambda _ctx, z=zone, f=foe: f in c.world.zones.occupants(z),
            )


@power(
    "m6191a4",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.store_roll()",),
)
def m6191a4(c: Cast) -> None:
    """Refused in play: there is no way to bank one d20 result and later
    substitute it for an arbitrary roll made by an arbitrary creature the
    caster can see."""


@power(
    "m6191a5",
    level=7,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m6191a5(c: Cast) -> None:
    _change_shape(c, _M6191_SHAPE, ("true", "human", "hybrid"))


_M6191_ADJ = "an enemy ends its move adjacent to the m6191"


@power(
    "m6191a6",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger=_M6191_ADJ,
    on=Trigger(AdjacencyGained, _enemy_closed_on_me, _M6191_ADJ),
)
def m6191a6(c: Cast) -> None:
    _recharge_when_bloodied(c)
    foe = _triggering_enemy(c)
    if foe is not None:
        c.push(1, on=foe)


# ==========================================================================
# m6446
# ==========================================================================


@power(
    "m6446a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 8, dtype=DamageType.PSYCHIC),
)
def m6446a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6446a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    no_provoke=True,
)
def m6446a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    roll = c.roll("1d6")
    if roll <= 2:
        if _secondary(c, 12, REF, victim):
            c.damage("2d8", 6, dtype=DamageType.FIRE, on=victim)
    elif roll <= 4:
        if _secondary(c, 12, WILL, victim):

            def falls_unconscious(eff: Effect, v: int = victim) -> None:
                c.world.effects.end(eff, "it falls unconscious")
                c.condition(Condition.UNCONSCIOUS, until=When.SAVE_ENDS, on=v)

            c.condition(
                Condition.SLOWED, until=When.SAVE_ENDS, on=victim, escalate=falls_unconscious
            )
    else:
        if _secondary(c, 12, FORT, victim):
            c.damage("1d10", 6, on=victim)
            c.ongoing(5, on=victim)


# ==========================================================================
# m6513
# ==========================================================================


@power(
    "m6513a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6513a0(c: Cast) -> None:
    c.cannot_be_flanked(on=c.me, until=When.ENCOUNTER)


@power(
    "m6513a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    no_provoke=True,
)
def m6513a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    which = c.choose(["cold", "fear", "daze"], f"{c.ref}: which ray") or "cold"
    if which == "cold":
        if _secondary(c, 12, REF, victim):
            c.flat(7, dtype=DamageType.COLD, on=victim)
    elif which == "fear":
        if _secondary(c, 12, WILL, victim):
            c.grants_advantage(on=victim, until=When.EONT)
            c.penalty("attack", 2, on=victim, until=When.EONT)
    else:
        if _secondary(c, 12, FORT, victim):
            c.dazed(on=victim, until=When.EONT)


@power(
    "m6513a2",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=NO_TARGET,
    out_of_combat=True,
)
def m6513a2(c: Cast) -> None:
    """Deliberately inert: levitating or manipulating an object is not a
    creature target and has no combat meaning the board resolves."""


# m720 and m725 print no abilities -- nothing to decorate.


# ==========================================================================
# m951
# ==========================================================================


@power(
    "m951a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 4, dtype=DamageType.PSYCHIC),
)
def m951a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m951a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d10", 5, dtype=DamageType.PSYCHIC),
)
def m951a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m951a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("1d10", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m951a2(c: Cast) -> None:
    """"Requires longbow" is equipment, not tracked."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m955
# ==========================================================================


@power(
    "m955a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 2),
)
def m955a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m955a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 3),
)
def m955a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m955a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=14),
    damage=Damage("3d8", 3, kind=LIMITED),
)
def m955a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
