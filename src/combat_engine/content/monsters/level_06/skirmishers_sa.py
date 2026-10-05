"""Monster abilities, level 6, skirmishers, second sweep.

176 rows across the thirty-eight stat blocks `skirmishers.py` did not reach --
the split is by *when* the work was done, not by what the creatures are.
Fourteen of the fifty-two blocks in this slot print no abilities at all and
have nothing to decorate: m2850, m2895, m297, m2977, m2991, m3009, m3062,
m3091, m404, m408, m429, m4794, m4916, m664.

Conventions, inherited from the five levels below and from this level's own
`skirmishers.py`:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=11)`) and the damage line goes in the
  header as data;
* a **trait** costs no action, has no target, and arms whatever holds it,
  whatever action the compendium's column claims; several rows here print no
  action word at all beside a trigger and are written as traits for the same
  reason;
* a card that prints no range at all is melee 1; a printed band like "15/30"
  takes the short number;
* `half_on_miss=True` is header data only -- a Miss line is also written as
  `else: c.hit(half=True)`;
* a printed Requirement naming a weapon is not asked -- a monster carries no
  `Gear`, and the blow is the block's own basic attack.

Two cards (`m1741a2`, `m3284a2`) print a Requirement naming a ref of this
very campaign's own numbering rather than a weapon or a location that exists
on a board; both are read as flavour and dropped, which loses nothing a
fight can tell the difference about. `m1741a2`'s own Effect line also names
a second ref that is not a zone this creature owns -- read the same way.

Two cards -- `m3237a1` and `m3642a1` -- print a capitalised short word where
the sentence wants a pronoun, and in both the word is part of the creature's
own printed name rather than an ordinary noun. Both rows write "it".

**The words themselves are not repeated here, and the first version of this
note repeated them.** `leaks.py` reported it: one of the two is part of two
creatures' names, so writing it down to explain the judgement put a printed
name into a tracked file, which is the one rule with no exceptions -- "not a
comment, a docstring, a variable, a column". Naming the refs is enough for
anybody who needs to check the call.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01 import aquatic_edge
from combat_engine.content.monsters.level_01.skirmishers_sa import _by_hand
from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES
from combat_engine.content.monsters.level_02.skirmishers_sa import _blinding_cloud
from combat_engine.content.monsters.level_03.artillery_sa import _death_throe
from combat_engine.content.monsters.level_03.brutes import _taking_ongoing
from combat_engine.content.monsters.level_03.skirmishers import _is_bloodied
from combat_engine.content.monsters.level_03.skirmishers_sa import (
    _adjacent_foes,
    _armed,
    _mobile_attack,
    _nearest,
    _per_round_rider,
    _shift_up_to,
)
from combat_engine.content.monsters.level_04.brutes import _change_shape
from combat_engine.content.monsters.level_04.brutes_sa import _in_shapes
from combat_engine.content.monsters.level_04.skirmishers import _struck
from combat_engine.content.monsters.level_04.skirmishers_sa import _hit_me_since_my_turn
from combat_engine.content.monsters.level_05.skirmishers import _airborne
from combat_engine.content.monsters.level_06.skirmishers import _mobbed
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ENEMY,
    EACH_OTHER,
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
    MeleeOrRanged,
    Movement,
    Position,
    Powers,
    Ranged,
    Relation,
    Size,
    Stats,
    UpTo,
    Usage,
    When,
    Window,
    World,
    power,
)
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    ConditionApplied,
    DamageApplied,
    Dropped,
    ForcedMove,
    Hit,
    InitiativeRolled,
    Miss,
    Moved,
    SkillCheck,
    TurnEnd,
    TurnStart,
    ZoneEntered,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    defence,
    distance_between,
    enemies,
    has_combat_advantage,
    team,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    ally_within,  # noqa: F401 -- kept beside the rest of the trigger kit
    both,
    by_charge,  # noqa: F401
    by_melee,
    by_opportunity,
    by_ranged,
    either,
    targets_me,
    targets_my_side,
)

_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _melee_ca_rider(c: Cast, *, dice: str = "", flat: int = 0) -> None:
    """Extra damage on a melee hit against a target granting combat advantage.

    Untyped and standing for the fight: `ctx["advantage"]` is read straight
    off the damage context rather than re-derived, and `ranged` is what
    keeps a ranged basic attack out of a line that only ever says "melee"."""

    def when(ctx: dict[str, Any]) -> bool:
        return bool(ctx.get("advantage")) and not ctx.get("ranged")

    c.bonus("damage", flat, dice=dice, on=c.me, until=When.ENCOUNTER, when=when)


def _revenge_bonus(c: Cast, extra: int) -> None:
    """+1 to the next attack roll, and `extra` more damage, against anyone
    that struck this creature since its own last turn.

    **Asked at the moment of the swing, not when the action is spent.** The
    window the card names runs from this creature's last turn to its next
    attack, so a set snapshotted here is already wrong if anybody hits it in
    between -- and an early return on an empty set means the row does nothing
    at all when it is used before being hit, which is when a monster most often
    spends a minor action. `level_04/lurkers_sa.py`'s `m915a4` settled this
    shape; this is the same reading.
    """
    c.bonus(
        "attack",
        1,
        on=c.me,
        kind="power",
        once=True,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") in _hit_me_since_my_turn(c),
    )

    def rider(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target in _hit_me_since_my_turn(c):
            c.flat(extra, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=c.me, once=True, label=c.ref)


def _attacked_me_since_my_turn(c: Cast) -> set[int]:
    """Who has swung at this creature since its own last turn began --
    `_hit_me_since_my_turn`'s cousin, asking of every attack rather than
    only the ones that landed."""
    out: set[int] = set()
    for ev in reversed(c.world.bus.log):
        if isinstance(ev, TurnStart) and ev.actor == c.me and not ev.ghost:
            break
        if isinstance(ev, AttackDeclared) and ev.target == c.me:
            out.add(ev.attacker)
    return out


def _knows(c: Cast, who: int, ref: str) -> bool:
    """Does that creature carry this row -- `_same_row`'s cousin, asking of
    an ability rather than a stat block."""
    powers = c.world.get(who, Powers)
    return powers is not None and ref in powers.known


def _melee_ca_damage(c: Cast, low: str, high: str) -> None:
    """ "NdX, or MdY if the target grants combat advantage" -- one roll,
    picked before the die is cast rather than bolted on after."""
    ca = has_combat_advantage(c.world, c.me, c.target)
    if c.strike():
        c.damage(high if ca else low)


def _bite_or_claws(c: Cast, combo: tuple[str, str], solo: str) -> None:
    """ "Uses X and Y, or uses X twice" -- a choice the policy makes once."""
    if c.choose(["combo", "solo"], f"{c.ref}: routine") == "solo":
        _struck(c, solo, 2)
    else:
        _struck(c, combo[0], 1)
        _struck(c, combo[1], 1)


# ==========================================================================
# Skirmishers
# ==========================================================================


# --------------------------------------------------------------------------
# m1030
# --------------------------------------------------------------------------


@power(
    "m1030a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4),
)
def m1030a0(c: Cast) -> None:
    """The crit line is one point better than the engine's own max-dice total."""
    plus = 1 if c.bloodied() else 0
    if c.strike(plus=plus):
        c.hit()
        if c.crit:
            c.flat(1)


@power("m1030a1", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1030a1(c: Cast) -> None:
    """Melee only; a ranged basic keeps the untouched line."""
    _melee_ca_rider(c, dice="2d6")


@power(
    "m1030a2",
    level=6,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy makes an opportunity attack against it",
    on=Trigger(
        AttackDeclared,
        both(targets_me, by_opportunity),
        "an enemy makes an opportunity attack against it",
    ),
)
def m1030a2(c: Cast) -> None:
    c.condition(Condition.BLINDED, on=c.trigger.attacker, until=When.SAVE_ENDS)  # type: ignore[union-attr]


@power("m1030a3", level=6, usage=ENCOUNTER, action=MINOR, reach=PERSONAL, target=NO_TARGET)
def m1030a3(c: Cast) -> None:
    """Picks from whoever has hit it since its own last turn."""
    _revenge_bonus(c, 2)


# --------------------------------------------------------------------------
# m1117
# --------------------------------------------------------------------------


@power(
    "m1117a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 6),
)
def m1117a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1117a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 6),
)
def m1117a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1117a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m1117a2(c: Cast) -> None:
    _struck(c, "m1117a1", 2)


@power(
    "m1117a3",
    level=6,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger="it is missed by a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "it is missed by a melee attack"),
)
def m1117a3(c: Cast) -> None:
    c.shift(2)
    _struck(c, "m1117a1", 1)


@power("m1117a4", level=6, usage=ENCOUNTER, action=MINOR, reach=CloseBurst(1), target=NO_TARGET)
def m1117a4(c: Cast) -> None:
    _blinding_cloud(c, 1)


# --------------------------------------------------------------------------
# m115887
# --------------------------------------------------------------------------


@power(
    "m115887a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET
)
def m115887a0(c: Cast) -> None:
    """Grounded for a turn; it only falls if it was actually aloft."""

    def grounded(ev: DamageApplied) -> None:
        if ev.target != c.me or DamageType.RADIANT not in ev.types():
            return
        was_up = c.height() > 0
        hold = c.effect(f"{c.ref} grounded", until=When.EONT, on=c.me)
        moves = c.world.get(c.me, Movement)
        if hold is not None and moves is not None and "fly" in moves.modes:
            speed = moves.modes.pop("fly")
            hold.on_end.append(lambda: moves.modes.setdefault("fly", speed))
        if was_up:
            c.fall(c.height())

    c.watch(DamageApplied, grounded, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "m115887a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
)
def m115887a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.restore_use("m115887a2", on=c.me)


@power(
    "m115887a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d6", 7, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m115887a2(c: Cast) -> None:
    """Undead in the blast shift for free; only the living are attacked."""
    if "undead" in c.kinds_of():
        c.shift(2)
        return
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m115887a3",
    level=6,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    no_provoke=True,
)
def m115887a3(c: Cast) -> None:
    c.move(4, at="fly")


@power(
    "m115887a4",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("", 5, dtype=DamageType.NECROTIC),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m115887a4(c: Cast) -> None:
    """Its own undead kin stand in the burst untouched."""
    if "undead" in c.kinds_of():
        return
    if c.strike():
        c.hit()
        c.weakened(until=When.EONT)


# --------------------------------------------------------------------------
# m1486
# --------------------------------------------------------------------------


@power(
    "m1486a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("3d4", 3),
)
def m1486a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1486a1",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d4", 2, kind=LIMITED),
)
def m1486a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, on=c.target)
        c.dazed(until=When.SAVE_ENDS)


@power("m1486a2", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1486a2(c: Cast) -> None:
    """The first resistance the target of `m1486a1` is carrying, if any."""

    def absorb(ev: Hit) -> None:
        if ev.attacker != c.me or ev.power != "m1486a1":
            return
        res = c.resistances(on=ev.target)
        if not res:
            return
        dtype = next(iter(res))
        c.resist(5, dtype, on=c.me, until=When.ENCOUNTER)
        c.deals(dtype, on=c.me, until=When.ENCOUNTER)

    c.watch(Hit, absorb, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "m1486a3",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m1486a3(c: Cast) -> None:
    """Nothing in the engine wakes a sleeping or unconscious-by-sleep
    creature on damage in the first place, so there is no rule here to
    suppress -- complete and inert in a fight."""


# --------------------------------------------------------------------------
# m1520
# --------------------------------------------------------------------------


@power(
    "m1520a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
)
def m1520a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1520a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
)
def m1520a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(1)


@power(
    "m1520a2",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_is_bloodied,
    requires_text="it must be bloodied",
)
def m1520a2(c: Cast) -> None:
    foe = next((e for e in c.enemies() if c.bloodied(on=e)), None)
    if foe is None:
        return
    _shift_up_to(c, 2, toward=foe)


# --------------------------------------------------------------------------
# m1737
# --------------------------------------------------------------------------


@power(
    "m1737a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 6),
)
def m1737a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1737a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 6),
)
def m1737a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1737a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 6),
)
def m1737a2(c: Cast) -> None:
    c.shift(1)
    if c.strike():
        c.hit()


@power(
    "m1737a3",
    level=6,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=Ranged(15),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 6),
    trigger="it or an ally is attacked by a creature",
    on=Trigger(AttackDeclared, targets_my_side, "it or an ally is attacked by a creature"),
)
def m1737a3(c: Cast) -> None:
    attacker = c.trigger.attacker  # type: ignore[union-attr]
    if c.strike(on=attacker):
        c.hit(on=attacker)
        c.penalty("attack", 6, on=attacker, once=True, until=When.ENCOUNTER)


@power(
    "m1737a4",
    level=6,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("3d8", 0, half_on_miss=True),
)
def m1737a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, on=c.target, until=When.ENCOUNTER)
    else:
        c.hit(half=True)
        c.penalty("attack", 1, on=c.target, until=When.ENCOUNTER)


@power("m1737a5", level=6, usage=ENCOUNTER, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m1737a5(c: Cast) -> None:
    # Untyped: the card prints "+2 bonus to AC" and names no bonus type.
    c.bonus(
        AC, 2, on=c.me, until=When.ENCOUNTER, when=lambda ctx: ctx.get("opportunity")
    )


@power(
    "m1737a6",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
)
def m1737a6(c: Cast) -> None:
    """As `m1124a5`: name the nearest enemy, then one extra die a round."""
    foe = _nearest(c)
    if foe is None:
        return
    for old in c.world.relations.targets(Relation.QUARRY_OF, c.me):
        if old != foe:
            c.world.relations.clear(Relation.QUARRY_OF, c.me, old, c.ref)
    c.quarry(on=foe)
    if not _armed(c, c.ref):
        _per_round_rider(c, "1d6", lambda ev: c.is_quarry(on=ev.target))


def _enemy_arrived_beside(world: World, me: int, ev: Moved) -> bool:
    return (
        ev.kind_ == ""
        and ev.actor in enemies(world, me)
        and distance_between(world, me, ev.actor) <= 1
    )


@power(
    "m1737a7",
    level=6,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy moves adjacent to it",
    on=Trigger(Moved, _enemy_arrived_beside, "an enemy moves adjacent to it"),
)
def m1737a7(c: Cast) -> None:
    c.shift(3)


# --------------------------------------------------------------------------
# m1741
# --------------------------------------------------------------------------


def _m1741_bite(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON, on=c.target)


def _m1741_lance(c: Cast, on: int | None = None) -> None:
    if c.strike(on=on):
        c.hit(on=on)
        c.dazed(on=on, until=When.SAVE_ENDS)
        c.slowed(on=on, until=When.SAVE_ENDS)


@power(
    "m1741a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 3),
)
def m1741a0(c: Cast) -> None:
    _m1741_bite(c)


@power(
    "m1741a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("", 0, kind=LIMITED),
)
def m1741a1(c: Cast) -> None:
    """Only a creature already taking ongoing poison qualifies; a chosen
    target without it is a use spent on nothing, which is a targeting
    question and not a correctness one."""
    if not _taking_ongoing(c, c.target, DamageType.POISON):
        return
    _m1741_lance(c)


@power(
    "m1741a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("", 0),
)
def m1741a2(c: Cast) -> None:
    """The same lance as `m1741a1`, free of its recharge and its poison
    Requirement -- the printed "even if" clause names both. The Requirement
    above it names a ref rather than a weapon or a place on this board, and
    the Effect's own second half names a ref that is not a zone this
    creature owns -- both read as flavour left over from a reprint, and
    dropped."""
    _m1741_lance(c)


@power("m1741a3", level=6, usage=AT_WILL, action=MOVE, reach=PERSONAL, target=NO_TARGET)
def m1741a3(c: Cast) -> None:
    c.shift(3)


# --------------------------------------------------------------------------
# m1807
# --------------------------------------------------------------------------


@power(
    "m1807a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 4),
)
def m1807a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m1807a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d10", 4),
)
def m1807a1(c: Cast) -> None:
    c.shift(1)
    if c.strike():
        c.hit()
    c.shift(1)


# --------------------------------------------------------------------------
# m1816
# --------------------------------------------------------------------------


@power(
    "m1816a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4),
)
def m1816a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m1816a1", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1816a1(c: Cast) -> None:
    """Read as "its allies" -- a flanking aura for whoever is adjacent to it."""
    me = c.me
    held: dict[int, Effect] = {}

    def recount(_ev: Any = None) -> None:
        near = {foe for foe in enemies(c.world, me) if distance_between(c.world, me, foe) <= 1}
        for foe in list(held):
            if foe not in near:
                c.world.effects.end(held.pop(foe), "no longer adjacent")
        for foe in near - set(held):
            held[foe] = c.grants_advantage(on=foe, to="team", until=When.ENCOUNTER)

    recount()
    c.watch(Moved, recount, until=When.ENCOUNTER, on=me, label=f"{c.ref} moved")
    c.watch(TurnStart, recount, until=When.ENCOUNTER, on=me, label=f"{c.ref} turn")


@power("m1816a2", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1816a2(c: Cast) -> None:
    """Two adjacent allies, or one if the rider qualifies -- read below."""

    def gate(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if ctx.get("ranged") or victim is None:
            return False
        needed = 2
        rider = c.rider()
        if rider is not None:
            stats = c.world.get(rider, Stats)
            if stats is not None and stats.level >= 6 and _knows(c, rider, "m1816a2"):
                needed = 1
        return _mobbed(c, victim, needed)

    c.bonus("damage", 5, on=c.me, until=When.ENCOUNTER, when=gate)


@power("m1816a3", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1816a3(c: Cast) -> None:
    """The charge exception to `m1816a2`'s ally count, and its extra point
    when there happens to be one anyway. A separate rider rather than folded
    into `m1816a2`, so each ref still audits as its own thing."""

    def rider(ev: Hit) -> None:
        if ev.attacker != c.me or not getattr(ev, "charge", False):
            return
        if ev.target is None:
            return
        rider_eid = c.rider()
        if rider_eid is None:
            return
        stats = c.world.get(rider_eid, Stats)
        if stats is None or stats.level < 6 or not _knows(c, rider_eid, "m1816a2"):
            return
        amount = 6 if _mobbed(c, ev.target, 1) else 5
        c.flat(amount, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=c.me, label=c.ref)


# --------------------------------------------------------------------------
# m1936
# --------------------------------------------------------------------------


@power("m1936a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1936a0(c: Cast) -> None:
    _melee_ca_rider(c, dice="2d6")


@power("m1936a1", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1936a1(c: Cast) -> None:
    """A Medium living humanoid it kills rises as a new one of its own kind
    at the start of its next turn -- a fresh `c.summon`, not the original
    reanimated as itself."""
    me = c.me
    pending: list[tuple[int, int]] = []

    def killed(ev: Dropped) -> None:
        if ev.source != me or not ev.dead:
            return
        kinds = c.kinds_of(on=ev.actor)
        if "humanoid" not in kinds or "undead" in kinds or "construct" in kinds:
            return
        if c.size_of(on=ev.actor) != Size.MEDIUM:
            return
        pos = c.world.get(ev.actor, Position)
        if pos is not None:
            pending.append(pos.square)

    def rise(ev: TurnStart) -> None:
        if ev.actor != me or not pending:
            return
        for sq in pending:
            c.summon("m1936", at=sq)
        pending.clear()

    c.watch(Dropped, killed, until=When.ENCOUNTER, on=me, label=f"{c.ref} kill")
    c.watch(TurnStart, rise, until=When.ENCOUNTER, on=me, label=f"{c.ref} rise")


@power(
    "m1936a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 0),
)
def m1936a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(5, dtype=DamageType.NECROTIC)
        c.grab()
        c.spend_surge(on=c.target)
        c.heal(5, on=c.me)


@power(
    "m1936a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    requires_text="it must have a creature grabbed",
)
def m1936a3(c: Cast) -> None:
    victim = next(iter(c.grabbing()), None)
    if victim is None:
        return
    c.shift(3, share=True)
    c.damage("2d6", 3, dtype=DamageType.NECROTIC, on=victim)


def _immob_or_restrained(world: World, me: int, ev: ConditionApplied) -> bool:
    return ev.target == me and ev.condition in (Condition.IMMOBILIZED, Condition.RESTRAINED)


@power(
    "m1936a4",
    level=6,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is immobilized, restrained, pulled, pushed, or slid",
    on=(
        Trigger(ConditionApplied, _immob_or_restrained, "it is immobilized or restrained"),
        Trigger(ForcedMove, targets_me, "it is pulled, pushed, or slid"),
    ),
)
def m1936a4(c: Cast) -> None:
    if c.save():
        c.cancel()


# --------------------------------------------------------------------------
# m2504
# --------------------------------------------------------------------------


@power(
    "m2504a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 3),
)
def m2504a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2504a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
)
def m2504a1(c: Cast) -> None:
    """Three basic swings spent across a 6-square shift, no foe struck twice."""
    struck: set[int] = set()
    remaining = 6
    for _ in range(3):
        step = max(1, remaining // 3) if remaining else 0
        if step:
            c.shift(min(step, remaining))
            remaining -= step
        foe = next((f for f in _adjacent_foes(c) if f not in struck), None)
        if foe is None:
            continue
        struck.add(foe)
        if c.basic(on=foe):
            c.flat(c.roll("1d6"), dtype=DamageType.NECROTIC, on=foe)
    if remaining > 0:
        c.shift(remaining)


@power(
    "m2504a2",
    level=6,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m2504a2(c: Cast) -> None:
    c.teleport(3)
    c.insubstantial(on=c.me, until=When.SONT)


# --------------------------------------------------------------------------
# m3237
# --------------------------------------------------------------------------


@power(
    "m3237a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 6),
)
def m3237a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3237a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 6),
)
def m3237a1(c: Cast) -> None:
    """It shifts, not a named thing -- see the module docstring."""
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m3237a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 5, kind=LIMITED),
)
def m3237a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    if c.first:
        c.shift(2)


# --------------------------------------------------------------------------
# m3284
# --------------------------------------------------------------------------


@power(
    "m3284a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 6),
)
def m3284a0(c: Cast) -> None:
    plus = 1 if c.bloodied(on=c.me) else 0
    if c.strike(plus=plus):
        c.hit()
    c.shift(2)


@power(
    "m3284a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 6),
)
def m3284a1(c: Cast) -> None:
    plus = 1 if c.bloodied(on=c.me) else 0
    if c.strike(plus=plus):
        c.hit()
    c.shift(2)


@power(
    "m3284a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 6),
)
def m3284a2(c: Cast) -> None:
    """The printed Requirement names a ref, not a weapon -- see the module
    docstring; nothing here enforces it."""
    plus = 1 if c.bloodied(on=c.me) else 0
    if c.strike(plus=plus):
        c.hit()
        c.prone()


@power(
    "m3284a3",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 5, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m3284a3(c: Cast) -> None:
    plus = 1 if c.bloodied(on=c.me) else 0
    if c.strike(plus=plus):
        c.hit()


# --------------------------------------------------------------------------
# m3465
# --------------------------------------------------------------------------


@power(
    "m3465a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 4),
)
def m3465a0(c: Cast) -> None:
    """Capped at the first three targets of this use, which is what "up to
    3" ever reaches out of a burst 1."""
    if c.strike():
        c.hit()
        if c.index < 3:
            c.shift(1)


@power(
    "m3465a1",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
    attack=Attack(vs=WILL, printed=9),
)
def m3465a1(c: Cast) -> None:
    foe = next((e for e in c.enemies() if c.marked(on=c.me, by=e)), None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.cure(Condition.MARKED, on=c.me)


@power(
    "m3465a2",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 2),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m3465a2(c: Cast) -> None:
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m3473
# --------------------------------------------------------------------------


@power(
    "m3473a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 3),
)
def m3473a0(c: Cast) -> None:
    _m1741_bite(c)


@power(
    "m3473a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("", 0, kind=LIMITED),
)
def m3473a1(c: Cast) -> None:
    if not _taking_ongoing(c, c.target, DamageType.POISON):
        return
    _m1741_lance(c)


@power(
    "m3473a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("", 0),
)
def m3473a2(c: Cast) -> None:
    """Against any creature that has swung at it since its own last turn,
    free of `m3473a1`'s recharge and its poison Requirement."""
    foes = _attacked_me_since_my_turn(c)
    if not foes:
        return
    victim = c.choose(sorted(foes), f"{c.ref}: which attacker")
    if victim is None:
        return
    _m1741_lance(c, on=victim)


@power("m3473a3", level=6, usage=AT_WILL, action=MOVE, reach=PERSONAL, target=NO_TARGET)
def m3473a3(c: Cast) -> None:
    c.shift(3)


# --------------------------------------------------------------------------
# m3641
# --------------------------------------------------------------------------


@power(
    "m3641a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 7),
)
def m3641a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3641a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 6),
)
def m3641a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3641a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 7),
)
def m3641a2(c: Cast) -> None:
    """A counter-swing if the target attacks it, armed on the hit rather
    than kept as a standing watch for everybody it has ever struck."""
    if c.strike():
        c.hit()
        victim = c.target

        def retaliate(ev: AttackDeclared) -> None:
            if ev.actor == victim:
                c.basic(on=victim)

        c.watch(AttackDeclared, retaliate, until=When.EONT, on=c.me, once=True, label=c.ref)


@power(
    "m3641a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 0, kind=LIMITED),
)
def m3641a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grants_advantage(on=c.target, until=When.EONT)


@power(
    "m3641a4",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 6, kind=LIMITED, half_on_miss=True),
)
def m3641a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)
    else:
        c.hit(half=True)


@power(
    "m3641a5",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m3641a5(c: Cast) -> None:
    """A disguise with nothing for a fight to read -- appearance has no shape here."""


@power("m3641a6", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3641a6(c: Cast) -> None:
    _per_round_rider(c, "2d8", lambda ev: bool(getattr(ev.result, "advantage", False)))


@power("m3641a7", level=6, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=NO_TARGET)
def m3641a7(c: Cast) -> None:
    c.shift(3)


# --------------------------------------------------------------------------
# m3642
# --------------------------------------------------------------------------


@power(
    "m3642a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 5),
)
def m3642a0(c: Cast) -> None:
    plus = 1 if c.bloodied() else 0
    if c.strike(plus=plus):
        c.hit()
        c.flat(c.roll("1d6"), dtype=DamageType.FIRE)


@power("m3642a1", level=6, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m3642a1(c: Cast) -> None:
    """It, not a named thing -- see the module docstring. Attacks whichever
    of AC or Reflex is lower on the chosen foe, same weapon damage as its
    basic strike."""
    half = max(1, c.speed_of() // 2)
    c.move(half)
    foe = next(iter(_adjacent_foes(c)), None)
    if foe is not None:
        c.no_provoke(from_=foe, on=c.me, until=When.EOT)
        weaker = REF if defence(c.world, foe, REF) < defence(c.world, foe, AC) else AC
        if c.attack(9, weaker, on=foe):
            c.damage("1d6", 5, on=foe)
    remaining = c.speed_of() - half
    if remaining > 0:
        c.move(remaining)


@power(
    "m3642a2",
    level=6,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is reduced to 0 hit points",
    on=Trigger(Dropped, about_me, "it is reduced to 0 hit points"),
)
def m3642a2(c: Cast) -> None:
    _death_throe(c)


@power("m3642a3", level=6, usage=ENCOUNTER, action=MINOR, reach=PERSONAL, target=NO_TARGET)
def m3642a3(c: Cast) -> None:
    _revenge_bonus(c, 3)


@power(
    "m3642a4",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m3642a4(c: Cast) -> None:
    """Fires whenever answered; "during its turn" is asked at that moment
    rather than armed into the gate."""

    def burn(ev: Hit) -> None:
        if ev.target == c.me and by_melee(c.world, ev.attacker, ev) and c.turn_of() == c.me:
            c.ongoing(3, DamageType.FIRE, on=ev.attacker)

    c.watch(Hit, burn, until=When.ENCOUNTER, on=c.me, label=c.ref)


# --------------------------------------------------------------------------
# m3775
# --------------------------------------------------------------------------


@power(
    "m3775a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 7),
)
def m3775a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        amount = 5 if c.bloodied(on=c.me) else 2
        c.ongoing(amount, on=c.target)


@power(
    "m3775a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    no_provoke=True,
)
def m3775a1(c: Cast) -> None:
    _mobile_attack(c, 6)


# --------------------------------------------------------------------------
# m3789
# --------------------------------------------------------------------------


@power(
    "m3789a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 4),
)
def m3789a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m3994
# --------------------------------------------------------------------------


@power(
    "m3994a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 4),
)
def m3994a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3994a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage(kind=LIMITED),
)
def m3994a1(c: Cast) -> None:
    if c.is_(Condition.DEAFENED, on=c.target):
        return
    if c.strike():
        for d in ALL_DEFENCES:
            c.penalty(d, 2, on=c.target, until=When.EONT)


@power("m3994a2", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3994a2(c: Cast) -> None:
    me = c.me
    gained: set[int] = set()

    def teleported(ev: Moved) -> None:
        if ev.actor != me or ev.kind_ != "teleport":
            return
        gained.clear()
        for foe in c.enemies():
            if c.adjacent(foe):
                gained.add(foe)
                c.gains_advantage(lambda ctx, f=foe: ctx.get("target") == f, on=me, until=When.EOT)

    def pushed(ev: Hit) -> None:
        if ev.attacker == me and ev.target in gained:
            c.push(1, on=ev.target)

    c.watch(Moved, teleported, until=When.ENCOUNTER, on=me, label=f"{c.ref} tp")
    c.watch(Hit, pushed, until=When.ENCOUNTER, on=me, label=f"{c.ref} push")


# --------------------------------------------------------------------------
# m4119
# --------------------------------------------------------------------------


@power(
    "m4119a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 4),
)
def m4119a0(c: Cast) -> None:
    c.shift(2)
    if c.strike():
        c.hit()
        c.flat(c.roll("1d6"), dtype=DamageType.ACID)
    c.shift(2)


@power(
    "m4119a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4),
)
def m4119a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m4119a2", level=6, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m4119a2(c: Cast) -> None:
    _struck(c, "m4119a1", 2)
    c.shift(2)


@power(
    "m4119a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    no_provoke=True,
)
def m4119a3(c: Cast) -> None:
    _mobile_attack(c, 10)


@power(
    "m4119a4",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d10", 4, dtype=DamageType.ACID, kind=LIMITED, half_on_miss=True),
)
def m4119a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m4119a5",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m4119a5(c: Cast) -> None:
    c.restore_use("m4119a4", on=c.me)
    c.use_power("m4119a4")


@power(
    "m4119a6",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=7),
)
def m4119a6(c: Cast) -> None:
    if c.strike():
        c.stunned(until=When.EONT)
        c.penalty("attack", 2, on=c.target, until=When.SAVE_ENDS)


# --------------------------------------------------------------------------
# m4246
# --------------------------------------------------------------------------


@power("m4246a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4246a0(c: Cast) -> None:
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def toll(ev: TurnStart) -> None:
        if ev.actor == me or ev.ghost or team(c.world, ev.actor) is team(c.world, me):
            return
        if not c.in_my_aura(ev.actor):
            return
        c.flat(5, on=ev.actor)

    c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power("m4246a1", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4246a1(c: Cast) -> None:
    """A radius-0 zone re-cut on every move, so it blocks sight from its
    own square and blinds whoever shares it -- itself excepted."""
    me = c.me
    ring = [c.zone({c.here}, label=c.ref, until=When.ENCOUNTER, blocks_sight=True)]
    held: dict[int, Effect] = {}

    def recheck(_ev: Any = None) -> None:
        c.world.zones.end(ring[0], "moved")
        ring[0] = c.zone({c.here}, label=c.ref, until=When.ENCOUNTER, blocks_sight=True)
        here = c.world.zones.occupants(ring[0])
        for who in list(held):
            if who not in here:
                c.world.effects.end(held.pop(who), "left")
        for who in here:
            if who != me and who not in held:
                held[who] = c.blinded(on=who, until=When.ENCOUNTER)

    c.watch(Moved, recheck, until=When.ENCOUNTER, on=me, label=f"{c.ref} self")


@power(
    "m4246a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d4", 3),
)
def m4246a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m4246a3",
    level=6,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m4246a3(c: Cast) -> None:
    here = c.here
    held = c.condition(Condition.REMOVED, on=c.me, until=When.SONT)
    if held is None:
        return

    def back() -> None:
        from combat_engine.engine.grid import spread

        options = sorted(
            sq
            for sq in spread({here}, 5)
            if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
        )
        if options:
            dest = c.world.decide(c.me, "teleport", options, f"{c.ref}: return")
            c.teleport(5, to=dest)

    held.on_end.append(back)


# --------------------------------------------------------------------------
# m4260
# --------------------------------------------------------------------------


@power(
    "m4260a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 5),
)
def m4260a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4260a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 5),
)
def m4260a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4260a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 5),
)
def m4260a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4260a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m4260a3(c: Cast) -> None:
    _struck(c, "m4260a0", 1)
    c.shift(1)
    _struck(c, "m4260a1", 1)
    c.shift(1)


@power(
    "m4260a4",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d6", 4, kind=LIMITED),
    trigger="it is hit or missed by a melee attack",
    on=(
        Trigger(Hit, both(targets_me, by_melee), "it is hit by a melee attack"),
        Trigger(Miss, both(targets_me, by_melee), "it is missed by a melee attack"),
    ),
)
def m4260a4(c: Cast) -> None:
    attacker = c.trigger.attacker  # type: ignore[union-attr]
    if c.strike(on=attacker):
        c.hit(on=attacker)
        c.grants_advantage(on=attacker, until=When.EONT)


@power(
    "m4260a5",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 5, kind=LIMITED),
)
def m4260a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)
        c.grants_advantage(on=c.target, until=When.SAVE_ENDS)
        c.slide(2)


@power(
    "m4260a6",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=8),
    no_provoke=True,
)
def m4260a6(c: Cast) -> None:
    """ "Lightly obscured" reads as a penalty on the target's own attacks
    against anything not adjacent to it -- the only direction the card
    says is affected."""
    obscured = c.target
    if not c.strike():
        return

    def when(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return (
            ctx.get("attacker") == obscured
            and victim is not None
            and distance_between(c.world, obscured, victim) > 1
        )

    c.penalty("attack", 2, on=obscured, until=When.EONT, when=when)


@power("m4260a7", level=6, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=NO_TARGET)
def m4260a7(c: Cast) -> None:
    c.cure(Condition.MARKED, on=c.me)
    c.shift(6)


@power("m4260a8", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4260a8(c: Cast) -> None:
    _melee_ca_rider(c, dice="2d6")


@power(
    "m4260a9",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m4260a9(c: Cast) -> None:
    """A free action economy clause: drawing and using an item cost the same
    action. Nothing on this board rolls a separate draw action to waive."""


# --------------------------------------------------------------------------
# m4306
# --------------------------------------------------------------------------


@power(
    "m4306a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 6),
)
def m4306a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.charge:
            c.flat(c.roll("1d8"))


@power(
    "m4306a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.move(through=)",),
)
def m4306a1(c: Cast) -> None:
    """Entering an enemy's square mid-move has no verb; the move and the
    attack that follows it are written in full."""
    c.move(c.speed_of())
    foe = next(iter(_adjacent_foes(c)), None)
    if foe is not None and c.attack(9, REF, on=foe):
        c.damage("1d6", 6, on=foe)
        c.prone(on=foe)


@power(
    "m4306a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m4306a2(c: Cast) -> None:
    _mobile_attack(c, c.speed_of())


# --------------------------------------------------------------------------
# m5299
# --------------------------------------------------------------------------


@power(
    "m5299a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 4),
)
def m5299a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5299a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    no_provoke=True,
)
def m5299a1(c: Cast) -> None:
    c.move(6, at="fly")
    foe = next(iter(_adjacent_foes(c)), None)
    if foe is None:
        return
    c.basic(on=foe)
    if has_combat_advantage(c.world, c.me, foe):
        c.use_power("m5299a4", on=foe)


@power(
    "m5299a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    charges=True,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 10, kind=LIMITED),
)
def m5299a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power("m5299a3", level=6, usage=AT_WILL, action=MOVE, reach=PERSONAL, target=NO_TARGET)
def m5299a3(c: Cast) -> None:
    c.shift(1)
    c.move(5, at="fly")


@power(
    "m5299a4",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    once_per_round=True,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 4),
)
def m5299a4(c: Cast) -> None:
    if not has_combat_advantage(c.world, c.me, c.target):
        return
    if c.strike():
        c.hit()


# --------------------------------------------------------------------------
# m5455
# --------------------------------------------------------------------------


@power("m5455a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5455a0(c: Cast) -> None:
    _melee_ca_rider(c, flat=5)


@power(
    "m5455a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 4),
)
def m5455a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m5455a2", level=6, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m5455a2(c: Cast) -> None:
    for _ in range(2):
        c.shift(2)
        foe = next(iter(_adjacent_foes(c)), None)
        if foe is not None:
            c.basic(on=foe)


@power(
    "m5455a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5455a3(c: Cast) -> None:
    me = c.me

    def punish(ev: Hit) -> None:
        if ev.target == me and getattr(ev, "opportunity", False):
            c.flat(10, on=ev.attacker)

    watch = c.watch(Hit, punish, until=When.EOT, on=me, label=c.ref)
    c.move(c.speed_of())
    c.world.effects.end(watch, "move over")


@power(
    "m5455a4",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("1d8", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m5455a4(c: Cast) -> None:
    c.shift(c.speed_of())
    if c.strike():
        c.hit()
        c.grants_advantage(on=c.target, until=When.EONT)


# --------------------------------------------------------------------------
# m5491
# --------------------------------------------------------------------------


@power(
    "m5491a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m5491a0(c: Cast) -> None:
    me = c.me
    c.aura(2, until=When.ENCOUNTER)

    def toll(ev: TurnStart) -> None:
        if ev.actor == me or ev.ghost or team(c.world, ev.actor) is team(c.world, me):
            return
        if not c.in_my_aura(ev.actor):
            return
        c.flat(5 + c.total("m5491a0 boost", on=me), dtype=DamageType.NECROTIC, on=ev.actor)

    c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power("m5491a1", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5491a1(c: Cast) -> None:
    me = c.me
    ring = c.aura(5, until=When.ENCOUNTER)
    held: dict[int, Effect] = {}

    def recheck(_ev: Any = None) -> None:
        bloodied_now = c.bloodied(on=me)
        here = set(c.world.zones.occupants(ring))
        for who in list(held):
            if who not in here or not bloodied_now or team(c.world, who) is team(c.world, me):
                c.world.effects.end(held.pop(who), "no longer applies")
        if not bloodied_now:
            return
        for who in here:
            if who != me and team(c.world, who) is not team(c.world, me) and who not in held:
                held[who] = c.half_healing(on=who, until=When.ENCOUNTER)

    recheck()
    c.watch(ZoneEntered, recheck, until=When.ENCOUNTER, on=me, label=f"{c.ref} in")
    c.watch(ZoneExited, recheck, until=When.ENCOUNTER, on=me, label=f"{c.ref} out")
    c.watch(Bloodied, recheck, until=When.ENCOUNTER, on=me, label=f"{c.ref} blood")
    c.watch(TurnStart, recheck, until=When.ENCOUNTER, on=me, label=f"{c.ref} turn")


@power("m5491a2", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5491a2(c: Cast) -> None:
    c.extra_turn(c.roll("1d20") + c.dex_mod)


@power("m5491a3", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5491a3(c: Cast) -> None:
    c.immovable(on=c.me, until=When.ENCOUNTER)

    def stay_up(ev: ConditionApplied) -> None:
        if ev.target == c.me and ev.condition is Condition.PRONE and c.save():
            c.cure(Condition.PRONE, on=c.me)

    c.watch(ConditionApplied, stay_up, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "m5491a4",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 3),
)
def m5491a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, on=c.target, until=When.EONT)


@power(
    "m5491a5",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 3),
)
def m5491a5(c: Cast) -> None:
    c.shift(4)
    if c.strike():
        c.hit()


@power(
    "m5491a6",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m5491a6(c: Cast) -> None:
    held = c.invisible(on=c.me, until=When.EONT)
    if held is None:
        return

    def ended_early(ev: AttackDeclared) -> None:
        if ev.actor == c.me:
            c.world.effects.end(held, "it attacked")

    c.watch(AttackDeclared, ended_early, until=When.EONT, on=c.me, once=True, label=c.ref)


@power(
    "m5491a7",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage(kind=LIMITED),
    trigger="it hits an enemy with m5491a5",
    on=Trigger(
        Hit,
        lambda world, me, ev: ev.attacker == me and ev.power == "m5491a5",
        "it hits an enemy with m5491a5",
    ),
)
def m5491a7(c: Cast) -> None:
    victim = c.trigger.target  # type: ignore[union-attr]
    if c.strike(on=victim):
        c.spend_surge(on=victim)
        # Untyped, and deliberately: the card is not granting a bonus at all --
        # the aura "deals 10 instead of 5" -- so this is the difference between
        # the two numbers. A substitution has to stack with whatever is there or
        # the aura pays the old figure.
        c.bonus("m5491a0 boost", 5, on=c.me, until=When.EONT)


@power(
    "m5491a8",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy hits it with a melee or a ranged attack",
    on=Trigger(
        Hit,
        both(targets_me, either(by_melee, by_ranged)),
        "an enemy hits it with a melee or a ranged attack",
    ),
)
def m5491a8(c: Cast) -> None:
    c.shift(4)
    c.insubstantial(on=c.me, until=When.EONT)


# --------------------------------------------------------------------------
# m5610
# --------------------------------------------------------------------------


@power(
    "m5610a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
)
def m5610a0(c: Cast) -> None:
    me = c.me
    c.aura(1, until=When.ENCOUNTER)
    held: dict[int, Effect] = {}

    def recheck(_ev: Any = None) -> None:
        here = {foe for foe in c.enemies() if c.in_my_aura(foe)}
        for foe in list(held):
            if foe not in here:
                c.world.effects.end(held.pop(foe), "left aura")
        for foe in here - set(held):
            held[foe] = c.grants_advantage(on=foe, to="team", until=When.ENCOUNTER)

    recheck()
    c.watch(Moved, recheck, until=When.ENCOUNTER, on=me, label=f"{c.ref} moved")
    c.watch(TurnStart, recheck, until=When.ENCOUNTER, on=me, label=f"{c.ref} turn")


@power(
    "m5610a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 3),
    dropped=("c.disease()",),
)
def m5610a1(c: Cast) -> None:
    """The blow is exact; the disease a failed end-of-encounter save hands
    over has no track to carry it."""
    if c.strike():
        c.hit()


@power(
    "m5610a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 2),
)
def m5610a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    if c.first:
        c.shift(1)


@power(
    "m5610a3",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    uses=2,
    trigger="it takes acid, cold, fire, lightning, or thunder damage",
    on=Trigger(
        DamageApplied,
        lambda world, me, ev: ev.target == me and bool(set(ev.types()) & set(_ELEMENTS)),
        "it takes elemental damage",
    ),
)
def m5610a3(c: Cast) -> None:
    ev = c.trigger
    hits = [t for t in ev.types() if t in _ELEMENTS]  # type: ignore[union-attr]
    if not hits:
        return
    for old in list(c.world.effects.of(c.me)):
        if old.label == f"{c.ref} resist":
            c.world.effects.end(old, "replaced")
    held = c.resist(5, hits[0], on=c.me, until=When.ENCOUNTER)
    if held is not None:
        held.label = f"{c.ref} resist"


# --------------------------------------------------------------------------
# m5664
# --------------------------------------------------------------------------


@power(
    "m5664a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5),
)
def m5664a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5664a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5),
)
def m5664a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m5664a2", level=6, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m5664a2(c: Cast) -> None:
    c.shift(c.speed_of())
    foe = next(iter(_adjacent_foes(c)), None)
    if foe is None:
        return
    before = c.bloodied(on=foe)
    if c.basic(on=foe) and not before and c.bloodied(on=foe):
        c.basic(on=foe)


@power(
    "m5664a3",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m5664a3(c: Cast) -> None:
    c.extra_action(ActionType.STANDARD, on=c.me)


# --------------------------------------------------------------------------
# m5756
# --------------------------------------------------------------------------


@power(
    "m5756a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD],
)
def m5756a0(c: Cast) -> None:
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def toll(ev: TurnEnd) -> None:
        if ev.actor == me or ev.ghost or team(c.world, ev.actor) is team(c.world, me):
            return
        if not c.in_my_aura(ev.actor):
            return
        c.flat(5, dtype=DamageType.COLD, on=ev.actor)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m5756a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    narrative=("skill:acrobatics",),
)
def m5756a1(c: Cast) -> None:
    """As `m4602a1`: shared space and immunity to being shoved by hand are
    the two halves that land. Squeezing through an opening large enough for
    one of the swarm's creatures is an acrobatics circumstance, and a board
    has no openings between squares to narrow -- the check never comes up,
    so the clause has no combat meaning rather than a missing one."""
    c.shares_space(on=c.me, until=When.ENCOUNTER, difficult=True)
    c.resist_forced(
        99,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: _by_hand(str(ctx.get("power") or "")),
    )


@power(
    "m5756a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("3d6", 4, dtype=DamageType.COLD),
)
def m5756a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.crit:
            c.immobilized(until=When.SAVE_ENDS)
    c.shift(2)


# --------------------------------------------------------------------------
# m5837
# --------------------------------------------------------------------------


@power("m5837a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5837a0(c: Cast) -> None:
    me = c.me
    c.aura(5, until=When.ENCOUNTER)

    def boost_init(ev: InitiativeRolled) -> None:
        if ev.actor != me and ev.actor in c.allies() and c.in_my_aura(ev.actor):
            c.initiative(4, on=ev.actor)

    def boost_stealth(ev: SkillCheck) -> None:
        if ev.skill == "stealth" and ev.actor in c.allies() and c.in_my_aura(ev.actor):
            ev.bonus += 4

    c.watch(InitiativeRolled, boost_init, until=When.ENCOUNTER, on=me, label=f"{c.ref} init")
    c.watch(
        SkillCheck,
        boost_stealth,
        until=When.ENCOUNTER,
        on=me,
        window=Window.BEFORE,
        label=f"{c.ref} stealth",
    )


@power("m5837a1", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5837a1(c: Cast) -> None:
    from combat_engine.content.monsters.level_05.skirmishers import _advantage_over

    me = c.me

    def choose() -> tuple[int, list[int]]:
        return me, [f for f in enemies(c.world, me) if c.marked(on=me, by=f)]

    _advantage_over(c, choose)


@power(
    "m5837a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 4),
)
def m5837a2(c: Cast) -> None:
    ca = has_combat_advantage(c.world, c.me, c.target)
    if c.strike():
        dealt = c.damage("3d6" if ca else "2d6", 7 if ca else 4)
        if dealt > 20:
            c.unconscious(until=When.SAVE_ENDS)


@power("m5837a3", level=6, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m5837a3(c: Cast) -> None:
    _struck(c, "m5837a2", 1)
    c.move(c.speed_of())
    _struck(c, "m5837a2", 1)


@power(
    "m5837a4",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m5837a4(c: Cast) -> None:
    c.teleport(c.speed_of())


@power(
    "m5837a5",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 4, dtype=DamageType.POISON, kind=LIMITED),
)
def m5837a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)
        c.ongoing(5, DamageType.POISON, on=c.target)
    else:
        c.immobilized(until=When.EONT)


# --------------------------------------------------------------------------
# m5891
# --------------------------------------------------------------------------


@power(
    "m5891a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.silvered()",),
)
def m5891a0(c: Cast) -> None:
    """Regeneration plays; nothing marks a weapon as silvered, so the
    suspension clause has no property to read."""
    c.regeneration(5, until=When.ENCOUNTER, on=c.me)


@power(
    "m5891a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 9),
    requires=_in_shapes("m5891a5", "human", "hybrid"),
    requires_text="it must be in human or hybrid form",
)
def m5891a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5891a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 3),
    requires=_in_shapes("m5891a5", "wolf", "hybrid"),
    requires_text="it must be in wolf or hybrid form",
)
def m5891a2(c: Cast) -> None:
    bloodied_foe = c.bloodied(on=c.target)
    if c.strike():
        c.damage("2d10", 8 if bloodied_foe else 3)
        c.shift(4)


@power(
    "m5891a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 9),
    requires=_in_shapes("m5891a5", "wolf", "hybrid"),
    requires_text="it must be in wolf or hybrid form",
    dropped=("c.disease()",),
)
def m5891a3(c: Cast) -> None:
    """The bite and the prone are exact; the disease a failed end-of-encounter
    save hands over has no track to carry it."""
    if c.strike():
        c.hit()
        c.prone()


@power("m5891a4", level=6, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m5891a4(c: Cast) -> None:
    _bite_or_claws(c, ("m5891a2", "m5891a1"), "m5891a1")


@power(
    "m5891a5",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m5891a5(c: Cast) -> None:
    _change_shape(c, "m5891a5", ("human", "wolf", "hybrid"))


# --------------------------------------------------------------------------
# m6274
# --------------------------------------------------------------------------


@power(
    "m6274a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 8),
)
def m6274a0(c: Cast) -> None:
    c.shift(3)
    _melee_ca_damage(c, "2d6", "3d6")


@power(
    "m6274a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6274a1(c: Cast) -> None:
    _struck(c, "m6274a0", 2)
    c.bonus(AC, 2, on=c.me, until=When.SONT, kind="power")


@power(
    "m6274a2",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(1),
    target=NO_TARGET,
    keywords=[Keyword.ZONE],
)
def m6274a2(c: Cast) -> None:
    _blinding_cloud(c, 1)


# --------------------------------------------------------------------------
# m6353
# --------------------------------------------------------------------------


@power("m6353a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6353a0(c: Cast) -> None:
    c.no_provoke(on=c.me, until=When.ENCOUNTER)


@power("m6353a1", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6353a1(c: Cast) -> None:
    me = c.me
    stash: dict[str, int] = {}

    def toggle(_ev: Any = None) -> None:
        moves = c.world.get(me, Movement)
        if moves is None:
            return
        if c.bloodied(on=me):
            if "fly" in moves.modes:
                stash["speed"] = moves.modes.pop("fly")
        elif "fly" not in moves.modes and stash.get("speed"):
            moves.modes["fly"] = stash.pop("speed")

    toggle()
    c.watch(Bloodied, toggle, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6353a2",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m6353a2(c: Cast) -> None:
    def healed(ev: DamageApplied) -> None:
        if ev.target == c.me and DamageType.LIGHTNING in ev.types():
            c.heal(5, on=c.me)

    c.watch(DamageApplied, healed, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "m6353a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 2),
)
def m6353a3(c: Cast) -> None:
    ca = has_combat_advantage(c.world, c.me, c.target)
    if c.strike():
        c.damage("2d8", 8 if ca else 2)


@power(
    "m6353a4",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d12", 8, dtype=DamageType.LIGHTNING),
    requires=_airborne,
    requires_text="it must be flying",
)
def m6353a4(c: Cast) -> None:
    moves = c.world.get(c.me, Movement)
    fly_speed = (moves.modes.get("fly") if moves else 0) or 0
    if c.strike():
        c.hit()
    c.move(fly_speed // 2, at="fly")


# --------------------------------------------------------------------------
# m6430
# --------------------------------------------------------------------------


@power(
    "m6430a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m6430a0(c: Cast) -> None:
    """Who may climb on is the rider's own power to spend, not this row's."""


@power(
    "m6430a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6430a1(c: Cast) -> None:
    me = c.me

    def both_charge(ev: AttackDeclared) -> None:
        rider = c.rider()
        if rider is None or ev.attacker != rider or not getattr(ev, "charge", False):
            return
        c.basic(on=ev.target)

    c.watch(AttackDeclared, both_charge, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6430a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5),
)
def m6430a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6430a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d8", 7, kind=LIMITED),
)
def m6430a3(c: Cast) -> None:
    c.shift(1)
    if c.strike():
        c.hit()
        c.ongoing(5, on=c.target)


# --------------------------------------------------------------------------
# m6655
# --------------------------------------------------------------------------


@power(
    "m6655a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m6655a0(c: Cast) -> None:
    me = c.me
    c.aura(1, until=When.ENCOUNTER)

    def toll(ev: TurnEnd) -> None:
        if ev.actor == me or ev.ghost or team(c.world, ev.actor) is team(c.world, me):
            return
        if not c.in_my_aura(ev.actor):
            return
        c.flat(5, dtype=DamageType.FIRE, on=ev.actor)
        c.stunned(on=ev.actor, until=When.EONT)

    c.watch(TurnEnd, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m6655a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.move(through=)",),
)
def m6655a1(c: Cast) -> None:
    """Entering an occupied square has no verb; everything that leans on it
    below instead reads "adjacent" for "in its square"."""


@power(
    "m6655a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 8, dtype=DamageType.FIRE),
)
def m6655a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6655a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 8, dtype=DamageType.FIRE),
)
def m6655a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power("m6655a4", level=6, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m6655a4(c: Cast) -> None:
    _bite_or_claws(c, ("m6655a3", "m6655a2"), "m6655a2")


@power(
    "m6655a5",
    level=6,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6655a5(c: Cast) -> None:
    """Widens the standing aura in place, which `Zones.refresh` re-cuts
    from `zone.aura` every tick -- the only lever that reaches a radius
    already spawned."""
    zid = c.my_aura(label="m6655a0")
    if not zid:
        return
    zone = dict(c.world.zones.all()).get(zid)
    if zone is not None and zone.aura is not None:
        zone.aura = min(5, zone.aura + 2)


@power(
    "m6655a6",
    level=6,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
)
def m6655a6(c: Cast) -> None:
    c.cure(Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.SLOWED, on=c.me)
    struck: set[int] = set()
    for _ in range(c.speed_of()):
        c.shift(1)
        foe = next((f for f in _adjacent_foes(c) if f not in struck), None)
        if foe is not None:
            struck.add(foe)
            if c.basic(on=foe):
                c.ongoing(5, DamageType.FIRE, on=foe)


@power(
    "m6655a7",
    level=6,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger="it takes fire damage",
    on=Trigger(
        DamageApplied,
        lambda world, me, ev: ev.target == me and DamageType.FIRE in ev.types(),
        "it takes fire damage",
    ),
)
def m6655a7(c: Cast) -> None:
    struck: set[int] = set()
    for _ in range(c.speed_of()):
        c.shift(1)
        for foe in _adjacent_foes(c):
            if foe not in struck:
                struck.add(foe)
                c.flat(5, dtype=DamageType.FIRE, on=foe)


# --------------------------------------------------------------------------
# m6662
# --------------------------------------------------------------------------


@power("m6662a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6662a0(c: Cast) -> None:
    aquatic_edge(c)


@power(
    "m6662a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
)
def m6662a1(c: Cast) -> None:
    ca = has_combat_advantage(c.world, c.me, c.target)
    if c.strike():
        c.hit()
        if ca:
            c.flat(c.roll("1d6"))


@power(
    "m6662a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6662a2(c: Cast) -> None:
    _struck(c, "m6662a1", 2)


@power(
    "m6662a3",
    level=6,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    once_per_round=True,
    requires_text="it must be in water and have cover or concealment",
)
def m6662a3(c: Cast) -> None:
    if not c.terrain("water"):
        return
    c.hide(until=When.ENCOUNTER)


@power(
    "m6662a4",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(2),
    target=NO_TARGET,
    requires_text="it must be in water, within 1 square of ground made of fine particles or debris",
)
def m6662a4(c: Cast) -> None:
    if not c.terrain("water"):
        return
    zone = c.zone(c.area(), label=c.ref, until=When.SONT)
    for who in c.world.zones.occupants(zone):
        c.conceal(on=who, until=When.SONT)


# --------------------------------------------------------------------------
# m937
# --------------------------------------------------------------------------


@power(
    "m937a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 5),
)
def m937a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m937a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d8", 5, kind=LIMITED),
)
def m937a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m937a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 6, kind=LIMITED),
)
def m937a2(c: Cast) -> None:
    if not c.is_(Condition.PRONE, on=c.target):
        return
    if c.strike():
        c.hit()


@power("m937a3", level=6, usage=AT_WILL, action=MINOR, reach=PERSONAL, target=NO_TARGET)
def m937a3(c: Cast) -> None:
    c.shift(1)


@power("m937a4", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m937a4(c: Cast) -> None:
    # Untyped: the card prints "+2 bonus to all defenses" and names no type.
    for d in ALL_DEFENCES:
        c.bonus(
            d,
            2,
            on=c.me,
            until=When.ENCOUNTER,
            when=lambda ctx: c.is_trap(ctx.get("attacker")),
        )
