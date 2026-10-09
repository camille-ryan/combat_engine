"""Monster abilities, level 8, skirmishers -- the second wave.

`skirmishers.py` holds the earlier sweep of this level and is not touched
here. 179 rows across thirty-nine stat blocks; every block in this slot that
has no abilities listed here was already finished there.

Conventions, inherited from the seven levels below and from this level's own
`skirmishers.py`:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=13)`) and the damage line goes in the
  header as data;
* a **trait** costs no action, has no target, and arms whatever holds it,
  whatever action the compendium's column claims;
* a card with no printed range is melee 1; a printed band like "15/30" takes
  the short number;
* `half_on_miss=True` is header data only -- the Miss branch is also written
  by hand;
* a printed Requirement naming a weapon is not asked -- a monster carries no
  `Gear`; a Requirement naming a fact about the *target* (combat advantage,
  a condition) is asked in the body, and a target that fails it is a use
  spent on nothing rather than a refusal, the same reading `m1741a1` settled
  on three levels down;
* "+N, or +M against a bloodied/dazed/etc target" and "whichever of two
  defences is lower" are both read off the board at the moment of the swing
  with a bare `c.attack`, with the printed line's first number kept in the
  header;
* a card printing two damage types rolled once keeps the first in the header
  and carries the rest as a keyword (`dropped=("Damage(dtypes=)",)`).

Two cards print a ref other than their own block's as the actor -- `m2077a4`
and `m2077a5` say `r36`, the same shape `level_06` and `level_08`'s first
sweep each met once already -- and both are read as naming this creature,
the same way `m4981a3` reads a shorter ref as this creature when the
sentence plainly has no one else to be about.

Nine helpers are imported rather than written again, from the six levels
below and from this level's own `skirmishers.py`. Four more are written here
because this batch is the first to need them: a shared-miss gate between a
mount and its rider (the relation's `targets`, never its `sources` -- the
one mistake this role has made three times elsewhere), a "would be hit"
interrupt that forces a stray roll to a natural 1 rather than faking the
outcome field, a step-by-step rampage that re-checks who is adjacent after
each square, and a flanking reaction that has to wait for the mover to have
actually arrived.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES
from combat_engine.content.monsters.level_03.brutes import _taking_ongoing
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.skirmishers import (
    _free_square_beside,
    _is_bloodied,
    _recharge_on,
)
from combat_engine.content.monsters.level_03.skirmishers_sa import (
    _mobile_attack,
    _per_round_rider,
)
from combat_engine.content.monsters.level_05.artillery_sa import _one_save_for_both
from combat_engine.content.monsters.level_06.skirmishers import _after_moving
from combat_engine.content.monsters.level_07.skirmishers import _dodges_openings
from combat_engine.content.monsters.level_08.skirmishers import (
    _adjacent_foe,
    _covered_ground,
    _steps_either_side,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
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
    Effect,
    Ident,
    Keyword,
    Melee,
    MeleeOrRanged,
    Ranged,
    Relation,
    Stats,
    UpTo,
    Usage,
    When,
    World,
    power,
    use,
)
from combat_engine.engine.events import (
    AttackRolled,
    Bloodied,
    ConditionApplied,
    DamageApplied,
    Dropped,
    EffectApplied,
    Hit,
    Miss,
    MoveEnd,
    MoveStart,
    SurgeSpent,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.grid import distance
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    allies,
    concealment_of,
    cover_between,
    defence,
    distance_between,
    enemies,
    flanked_by,
    has_combat_advantage,
    team,
)
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_me,
    by_melee,
    enemy_within,
    targets_me,
)

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _rider_mount_hit(world: World, me: int, ev: Hit) -> bool:
    """`me`'s mount was just hit by a melee attack -- the relation's
    `sources`, read off the rider, never its `targets`."""
    mounts = world.relations.sources(Relation.RIDDEN_BY, me)
    return bool(mounts) and ev.target == mounts[0] and by_melee(world, ev.attacker, ev)


def _ended_flanking(world: World, me: int, ev: MoveEnd) -> bool:
    """An enemy's move just ended with it flanking -- asked of `MoveEnd`,
    because `MoveStart` fires before anybody has moved and cannot say
    where the mover ends up."""
    return ev.actor in enemies(world, me) and flanked_by(world, me, ev.actor)


def _rolled_would_hit(world: World, me: int, ev: AttackRolled) -> bool:
    """The roll an interrupt answers, read off the provisional result the
    event already carries rather than waited for -- `AttackRolled` fires
    before `Hit`/`Miss` exist at all."""
    return ev.target == me and ev.result.hit


# ==========================================================================
# Skirmishers
# ==========================================================================


# --------------------------------------------------------------------------
# m1071
# --------------------------------------------------------------------------


@power(
    "m1071a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 4),
)
def m1071a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m1071a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1071a1(c: Cast) -> None:
    """A rider of 8th level or higher, while it carries one -- re-checked
    whenever a new one mounts up, since `c.rider` can change mid-fight."""
    me = c.me
    held: list[Effect] = []

    def refresh(_ev: Any = None) -> None:
        for eff in held:
            c.world.effects.end(eff, "rider changed")
        held.clear()
        rider = c.rider()
        if rider is None:
            return
        stats = c.world.get(rider, Stats)
        if stats is None or stats.level < 8:
            return
        held.append(
            c.bonus(
                AC, 2, on=rider, until=When.ENCOUNTER,
                when=lambda ctx: bool(ctx.get("opportunity")),
            )
        )
        held.append(
            c.bonus(
                "attack", 2, on=rider, until=When.ENCOUNTER,
                when=lambda ctx: (
                    c.terrain("water") and not c.is_kind("aquatic", on=ctx.get("target"))
                ),
            )
        )

    refresh()
    c.watch(TurnStart, refresh, until=When.ENCOUNTER, on=me, label=f"{c.ref} mount")


@power("m1071a2", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1071a2(c: Cast) -> None:
    """Breathing in water is already true of a board with no drowning
    mechanic to exempt it from; the attack bonus is the real half."""
    c.bonus(
        "attack", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: c.terrain("water") and not c.is_kind("aquatic", on=ctx.get("target")),
    )


# --------------------------------------------------------------------------
# m1120
# --------------------------------------------------------------------------


@power(
    "m1120a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 4),
)
def m1120a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1120a1",
    level=8,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.FEAR],
    attack=Attack(vs=WILL, printed=13),
    out_of_combat=True,
)
def m1120a1(c: Cast) -> None:
    """The whole printed Effect is an interrogation -- a question answered,
    not a roll a fight ever makes. Nothing here has combat meaning."""


@power("m1120a2", level=8, usage=AT_WILL, action=MINOR, reach=PERSONAL, target=NO_TARGET)
def m1120a2(c: Cast) -> None:
    near = min((f for f in c.enemies() if c.can_see(f)), key=c.distance, default=None)
    if near is None:
        return
    c.curse(on=near)

    def rider(ev: Hit) -> None:
        if ev.attacker == c.me and c.cursed(on=ev.target):
            c.damage("1d6", on=ev.target, detail=c.ref)

    if not any(e.label == c.ref for e in c.world.effects.of(c.me)):
        c.watch(Hit, rider, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "m1120a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("1d6", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
    dropped=("c.deny_action()",),
)
def m1120a3(c: Cast) -> None:
    """Losing a standard action on its next turn has no verb; the damage
    and the Will penalty are written."""
    if c.strike():
        c.hit()
        c.penalty(WILL, 2, until=When.SAVE_ENDS)


@power(
    "m1120a4",
    level=8,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.FORCE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("3d10", 3, dtype=DamageType.FORCE),
)
def m1120a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


# --------------------------------------------------------------------------
# m1146
# --------------------------------------------------------------------------


@power(
    "m1146a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 2),
)
def m1146a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1146a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 3),
)
def m1146a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1146a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 2),
)
def m1146a2(c: Cast) -> None:
    c.shift(2)
    if c.strike():
        c.hit()


@power("m1146a3", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1146a3(c: Cast) -> None:
    def when(ctx: dict[str, Any]) -> bool:
        return bool(ctx.get("advantage")) and not ctx.get("ranged")

    c.bonus("damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER, when=when)


@power(
    "m1146a4",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_is_bloodied,
    requires_text="it must be bloodied",
)
def m1146a4(c: Cast) -> None:
    c.regeneration(4, until=When.ENCOUNTER, while_bloodied=True)


# --------------------------------------------------------------------------
# m1167
# --------------------------------------------------------------------------


@power(
    "m1167a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d12", 5),
)
def m1167a0(c: Cast) -> None:
    """The crit line is one point of its own under the engine's own
    max-dice total; nothing extra is written."""
    if c.strike():
        c.hit()


@power(
    "m1167a1",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d12", 5),
    no_provoke=True,
)
def m1167a1(c: Cast) -> None:
    c.move(7)
    if c.strike():
        c.hit()
    c.shift(3)


@power(
    "m1167a2", level=8, usage=Usage.RECHARGE, recharge=6, action=MOVE,
    reach=PERSONAL, target=NO_TARGET,
)
def m1167a2(c: Cast) -> None:
    c.shift(3)


@power(
    "m1167a3",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    requires_text="it must have cover or concealment",
)
def m1167a3(c: Cast) -> None:
    """"Cover or concealment" is read as concealment -- the only one of
    the two that is a fact about this creature rather than a line to an
    attacker who may not even be there yet."""
    if concealment_of(c.world, c.me) is Cover.NONE:
        return
    c.check("stealth", bonus=2)
    c.hide(until=When.ENCOUNTER)


@power("m1167a4", level=8, usage=ENCOUNTER, action=MINOR, reach=PERSONAL, target=NO_TARGET)
def m1167a4(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, once=True,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


# --------------------------------------------------------------------------
# m1184
# --------------------------------------------------------------------------


@power(
    "m1184a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
)
def m1184a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1184a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d8", 5, kind=LIMITED),
)
def m1184a1(c: Cast) -> None:
    _steps_either_side(c, 2)


@power(
    "m1184a2",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=13),
)
def m1184a2(c: Cast) -> None:
    victim = _restricted_to(c, 2, lambda f: c.height(on=f) == 0)
    if victim is None:
        return
    if c.strike(on=victim):
        c.prone(on=victim)


@power(
    "m1184a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d10", 4, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m1184a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power("m1184a4", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1184a4(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


@power(
    "m1184a5",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.ignores_hazards()",),
)
def m1184a5(c: Cast) -> None:
    """Taking no damage from a surface that would normally deal it has no
    verb; the shift over ground or liquid, passing through enemy spaces,
    and ignoring difficult terrain are written."""
    c.ignores_difficult(on=c.me, until=When.EOT)
    c.phasing(until=When.EOT)
    c.shift(6)


# --------------------------------------------------------------------------
# m1818
# --------------------------------------------------------------------------


@power(
    "m1818a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d6", 7, dtype=DamageType.PSYCHIC),
)
def m1818a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1818a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("1d6", 7, dtype=DamageType.PSYCHIC),
)
def m1818a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        mates = sorted(
            a for a in allies(c.world, victim) if distance_between(c.world, victim, a) <= 1
        )
        pick = c.choose(mates, f"{c.ref}: which ally") if mates else None
        if pick is not None:
            c.basic(on=pick, who=victim)


@power(
    "m1818a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("3d6", 7, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m1818a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)
        c.dazed(until=When.SAVE_ENDS)


_M1818_MOVED = "an enemy within 10 squares of the m1818 moves or shifts"


@power(
    "m1818a3",
    level=8,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=WILL, printed=11),
    trigger=_M1818_MOVED,
    on=Trigger(MoveStart, enemy_within(10), _M1818_MOVED),
)
def m1818a3(c: Cast) -> None:
    victim = c.trigger.actor  # type: ignore[union-attr]
    if c.strike(on=victim):
        c.push(3, on=victim)
        c.cancel()


@power("m1818a4", level=8, usage=ENCOUNTER, action=STANDARD, reach=Ranged(5), target=ONE_CREATURE)
def m1818a4(c: Cast) -> None:
    """No attack roll of its own. The +5 has to land before the roll it
    boosts is judged, so it is added to `AttackRolled`'s own `result` --
    the same object `Hit` carries -- and the automatic crit is written on
    that `Hit`, once the roll it boosted is known to have landed."""
    victim = c.target
    if victim is None:
        return
    mine = team(c.world, c.me)
    state: dict[str, Any] = {"result": None}

    def boosted(ev: Any) -> None:
        if state["result"] is not None or ev.target != victim:
            return
        if ev.ctx.get("ranged") or team(c.world, ev.attacker) is not mine:
            return
        ev.result.total += 5
        state["result"] = ev.result

    def upgraded(ev: Hit) -> None:
        if ev.result is state["result"]:
            ev.result.critical = True

    c.watch(AttackRolled, boosted, until=When.ENCOUNTER, on=c.me, label=c.ref)
    c.watch(Hit, upgraded, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} crit")


# --------------------------------------------------------------------------
# m1819
# --------------------------------------------------------------------------


@power(
    "m1819a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 9),
)
def m1819a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1819a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 9),
)
def m1819a1(c: Cast) -> None:
    """Can use any melee weapon for the shot -- no equipment system
    distinguishes one weapon's dice from another here, so the numbers are
    the same either way."""
    if c.strike():
        c.hit()


@power(
    "m1819a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=11),
    damage=Damage("3d6", 9, kind=LIMITED),
    dropped=("c.disarm(catch=)",),
)
def m1819a2(c: Cast) -> None:
    """`c.disarm` always drops the weapon to the ground; there is no way
    to catch one in a free hand instead."""
    if c.strike():
        c.hit()
        c.disarm(on=c.target)


@power(
    "m1819a3",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="when it successfully catches a weapon a target drops",
    todo=("c.disarm(catch=)",),
)
def m1819a3(c: Cast) -> None:
    """Can never fire: catching a disarmed weapon has no verb at all."""


@power(
    "m1819a4",
    level=8,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m1819a4(c: Cast) -> None:
    c.teleport(3)
    c.insubstantial(until=When.SONT)


@power(
    "m1819a5", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    out_of_combat=True,
)
def m1819a5(c: Cast) -> None:
    """Weapon proficiency is already baked into the printed attack bonus;
    there is nothing left for a fight to do with the fact itself."""


# --------------------------------------------------------------------------
# m1826
# --------------------------------------------------------------------------


@power(
    "m1826a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d4", 5),
)
def m1826a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.is_(Condition.PRONE, on=c.target):
            c.flat(c.roll("2d6"))


_M1826_CLAW = "m1826 makes a successful claw attack"


@power(
    "m1826a1",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 5),
    trigger=_M1826_CLAW,
    on=Trigger(Hit, lambda w, me, ev: ev.attacker == me and ev.power == "m1826a0", _M1826_CLAW),
)
def m1826a1(c: Cast) -> None:
    victim = c.trigger.target  # type: ignore[union-attr]
    if c.strike(on=victim):
        c.hit(on=victim)
        c.ongoing(10, DamageType.POISON, on=victim)


@power(
    "m1826a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d4", 5),
)
def m1826a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.is_(Condition.PRONE, on=c.target):
            c.flat(c.roll("2d6"))
    c.shift(2)


@power(
    "m1826a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d4", 5, kind=LIMITED),
)
def m1826a3(c: Cast) -> None:
    struck: set[int] = set()
    remaining = c.speed_of()
    while remaining > 0:
        c.shift(1)
        remaining -= 1
        foe = next((f for f in c.enemies() if c.adjacent(f) and f not in struck), None)
        if foe is None:
            continue
        struck.add(foe)
        if c.strike(on=foe):
            c.hit(on=foe)


@power(
    "m1826a4",
    level=8,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=11),
    dropped=("Power.reach_alt",),
)
def m1826a4(c: Cast) -> None:
    """The wider burst while bloodied has nothing to declare it with --
    `reach` is fixed at the header and targeting runs before this body
    sees anything -- so the printed burst 2 is what is offered."""
    if c.strike():
        c.push(c.speed_of(), on=c.target)
        c.prone()


_M1826_BLOODIED = "the m1826 is first bloodied"


@power(
    "m1826a5",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M1826_BLOODIED,
    on=Trigger(Bloodied, about_me, _M1826_BLOODIED),
)
def m1826a5(c: Cast) -> None:
    c.extra_action(ActionType.STANDARD)


# --------------------------------------------------------------------------
# m1930
# --------------------------------------------------------------------------


@power(
    "m1930a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
)
def m1930a0(c: Cast) -> None:
    early = c.may("shift before the attack")
    if early:
        c.shift(2)
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)
    if not early:
        c.shift(2)


@power(
    "m1930a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d4", 6, kind=LIMITED),
)
def m1930a1(c: Cast) -> None:
    struck: set[int] = set()
    remaining = 9
    attacks_left = 3
    while remaining > 0 and attacks_left > 0:
        c.shift(1)
        remaining -= 1
        foe = next((f for f in c.enemies() if c.adjacent(f) and f not in struck), None)
        if foe is None:
            continue
        struck.add(foe)
        attacks_left -= 1
        if c.strike(on=foe):
            c.hit(on=foe)
            c.ongoing(5, DamageType.NECROTIC, on=foe)
    if remaining > 0:
        c.shift(remaining)


@power("m1930a2", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1930a2(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


@power("m1930a3", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1930a3(c: Cast) -> None:
    c.gains_advantage(
        lambda ctx: _taking_ongoing(c, ctx.get("target"), DamageType.NECROTIC),
        on=c.me, until=When.ENCOUNTER,
    )


# --------------------------------------------------------------------------
# m2010
# --------------------------------------------------------------------------


@power(
    "m2010a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5),
)
def m2010a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2010a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d8", 6, kind=LIMITED),
    requires_text="it must have combat advantage against the target",
)
def m2010a1(c: Cast) -> None:
    """A target without combat advantage is a use spent on nothing -- the
    chooser picks the target, this just declines to swing at the wrong
    one, the reading `m1741a1` settled on."""
    _recharge_on(c, Bloodied, lambda ev: c.adjacent(ev.actor))
    if not has_combat_advantage(c.world, c.me, c.target):
        return
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)
        c.heal(24)


@power("m2010a2", level=8, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m2010a2(c: Cast) -> None:
    _mobile_attack(c, 6, shifting=True)


# --------------------------------------------------------------------------
# m2077
# --------------------------------------------------------------------------


@power(
    "m2077a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 5),
)
def m2077a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2077a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 4),
)
def m2077a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m2077a2", level=8, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m2077a2(c: Cast) -> None:
    """Two different weapons, one swing each; the second drops the +4 the
    printed line takes away. The 2 squares of shift are spent up front,
    which is one of the three arrangements the card allows."""
    c.shift(2)
    foe = _adjacent_foe(c, c.ref)
    if foe is not None and c.attack(13, AC, on=foe):
        c.damage("1d10", 5, on=foe)
    foe2 = _adjacent_foe(c, c.ref)
    if foe2 is not None and c.attack(13, AC, on=foe2):
        c.damage("1d6", 0, on=foe2)


@power(
    "m2077a3", level=8, usage=ENCOUNTER, action=STANDARD, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m2077a3(c: Cast) -> None:
    near = sorted(c.enemies(), key=lambda f: (c.distance(f), f))
    victim = c.choose(near, f"{c.ref}: which enemy") if near else None
    if victim is None:
        return
    use(c.world, c.me, "m2077a1", targets=[victim], spend=False)
    c.charge_at(victim)


_M2077_HITS = "it hits an enemy with an attack"


@power(
    "m2077a4",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2077_HITS,
    on=Trigger(Hit, by_me, _M2077_HITS),
)
def m2077a4(c: Cast) -> None:
    """The card names a different ref as the actor; it is plainly this
    creature, the same reading `m4981a3` settled on."""
    ev = c.trigger
    victim = getattr(ev, "target", None)
    if victim is None:
        return
    if c.weapon_of(ev) is not None:
        c.flat(c.roll(c.w()), on=victim)
    else:
        c.flat(c.roll("1d8"), on=victim)


_M2077_BLOODIED = "the m2077 is first bloodied"


@power(
    "m2077a5",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M2077_BLOODIED,
    on=Trigger(Bloodied, about_me, _M2077_BLOODIED),
)
def m2077a5(c: Cast) -> None:
    c.temp_hp(5, on=c.me)


# --------------------------------------------------------------------------
# m3183
# --------------------------------------------------------------------------


@power(
    "m3183a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 6),
    dropped=("c.reroll_damage(ones=)",),
)
def m3183a0(c: Cast) -> None:
    """The crit is its own dice, not the engine's double -- `c.damage` is
    called by hand so the necrotic replaces the weapon's d10 instead of
    doubling it. Rerolling 1s against a bloodied target has no verb that
    reaches a single face; `c.reroll_damage` redoes the whole roll."""
    if c.strike():
        if c.crit:
            c.damage("2d8", 16, dtype=DamageType.NECROTIC)
        else:
            c.hit()


@power(
    "m3183a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5),
    requires_text="it must be mounted",
)
def m3183a1(c: Cast) -> None:
    """Whichever of AC or Reflex is lower, read off the board at the
    moment of the swing rather than guessed from the header."""
    if c.mount() is None or c.target is None:
        return
    weaker = REF if defence(c.world, c.target, REF) < defence(c.world, c.target, AC) else AC
    ca = has_combat_advantage(c.world, c.me, c.target)
    if c.attack(13, weaker):
        c.hit()
        if c.crit or ca:
            c.prone()


@power(
    "m3183a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 6),
)
def m3183a2(c: Cast) -> None:
    if c.strike():
        if c.crit:
            c.damage("2d8", 16, dtype=DamageType.NECROTIC)
        else:
            c.hit()
    if c.first:
        for foe in c.enemies():
            if c.adjacent(foe):
                c.flat(5, on=foe)
                c.grants_advantage(on=foe, until=When.EONT)


@power(
    "m3183a3",
    level=8,
    usage=AT_WILL,
    action=REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d6", 5),
    trigger="m3183's mount is hit by a melee attack",
    on=Trigger(Hit, _rider_mount_hit, "m3183's mount is hit by a melee attack"),
)
def m3183a3(c: Cast) -> None:
    attacker = c.trigger.attacker  # type: ignore[union-attr]
    mount = c.mount()
    if c.strike(on=attacker):
        c.hit(on=attacker)
    if mount is not None:
        c.resist(10, on=mount, until=When.EOT)


@power("m3183a4", level=8, usage=ENCOUNTER, action=MINOR, reach=CloseBurst(10), target=EACH_ALLY)
def m3183a4(c: Cast) -> None:
    c.temp_hp(10, on=c.target)
    c.bonus("attack", 1, kind="power", until=When.EONT)


@power("m3183a5", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3183a5(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("charge")) and c.mount() is not None,
    )


@power(
    "m3183a6", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    out_of_combat=True,
)
def m3183a6(c: Cast) -> None:
    """Mount abilities a rider gains are already granted by the mount's
    own rows, so there is nothing left for this one to grant. The skill
    substitution is a circumstance on checks no fight here rolls --
    nothing in this row has combat meaning."""


@power("m3183a7", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3183a7(c: Cast) -> None:
    """Declaration-and-watch, the shape `c.revives_unless` uses for a
    damage type -- but the printed gate is the killer's **kind**, so it is
    read off `c.kinds_of` directly. Rising in its own chambers after 24
    hours is outside any encounter and has nothing here to do; what
    matters on a board is that a mortal blow does not actually finish it."""
    me = c.me

    def killed(ev: Dropped) -> None:
        if ev.actor != me or not ev.dead or ev.source is None:
            return
        if "immortal" in c.kinds_of(on=ev.source):
            return
        c.heal(1, on=me)

    c.watch(Dropped, killed, until=When.ENCOUNTER, on=me, label=c.ref)


# --------------------------------------------------------------------------
# m3289
# --------------------------------------------------------------------------


@power(
    "m3289a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 7),
)
def m3289a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3289a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 7),
)
def m3289a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3289a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    no_provoke=True,
)
def m3289a2(c: Cast) -> None:
    near = sorted(c.enemies(), key=lambda f: (c.distance(f), f))
    victim = c.choose(near, f"{c.ref}: which enemy") if near else None
    if victim is None:
        return
    if c.charge_at(victim):
        c.flat(c.roll("1d8"), on=victim)


_M3289_ROLL = "m3289 makes an attack roll"


@power(
    "m3289a3",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3289_ROLL,
    on=Trigger(AttackRolled, by_me, _M3289_ROLL),
)
def m3289a3(c: Cast) -> None:
    c.reroll_attack(keep="new")


_M3289_MELEE = "an enemy makes a melee attack against the m3289"


@power(
    "m3289a4",
    level=8,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3289_MELEE,
    on=Trigger(Hit, both(targets_me, by_melee), _M3289_MELEE),
)
def m3289a4(c: Cast) -> None:
    c.shift(2)


@power("m3289a5", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3289a5(c: Cast) -> None:
    c.ignores_difficult("shift", on=c.me, until=When.ENCOUNTER)


@power("m3289a6", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3289a6(c: Cast) -> None:
    """Re-granted whenever a new mount is taken -- the relation can
    change mid-fight."""
    me = c.me
    held: list[Effect] = []

    def refresh(_ev: Any = None) -> None:
        for eff in held:
            c.world.effects.end(eff, "dismounted")
        held.clear()
        mount = c.mount()
        if mount is not None:
            granted = c.grant_row("m3289a5", on=mount, until=When.ENCOUNTER)
            if granted is not None:
                held.append(granted)

    refresh()
    c.watch(TurnStart, refresh, until=When.ENCOUNTER, on=me, label=c.ref)


# --------------------------------------------------------------------------
# m3309
# --------------------------------------------------------------------------


@power(
    "m3309a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 7),
)
def m3309a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3309a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.LIGHTNING],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d8", 7, dtype=DamageType.LIGHTNING),
)
def m3309a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power("m3309a2", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3309a2(c: Cast) -> None:
    def rider(ev: Hit) -> None:
        if ev.attacker == c.me and bool(getattr(ev.result, "advantage", False)):
            c.flat(c.roll("2d6"), dtype=DamageType.THUNDER, on=ev.target)
            c.slide(1, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power("m3309a3", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3309a3(c: Cast) -> None:
    c.shift_as(MOVE, 2, on=c.me, until=When.ENCOUNTER)


# --------------------------------------------------------------------------
# m3310
# --------------------------------------------------------------------------


@power(
    "m3310a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 4),
)
def m3310a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3310a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 4),
)
def m3310a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3310a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
)
def m3310a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.bonus(
        "damage", 0, dice="2d6", on=c.me, once=True, until=When.EONT,
        when=lambda ctx: ctx.get("target") == victim,
    )


@power(
    "m3310a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=11),
)
def m3310a3(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.BLINDED, Condition.SLOWED, until=When.SAVE_ENDS)


@power("m3310a4", level=8, usage=AT_WILL, action=MINOR, reach=PERSONAL, target=NO_TARGET)
def m3310a4(c: Cast) -> None:
    c.ignores_difficult("shift", on=c.me, until=When.EOT)
    c.shift(3)


# --------------------------------------------------------------------------
# m3471
# --------------------------------------------------------------------------


@power(
    "m3471a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 7),
)
def m3471a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3471a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 7, kind=LIMITED),
    requires_text="it must have combat advantage against the target",
)
def m3471a1(c: Cast) -> None:
    """A target without combat advantage is a use spent on nothing. The
    scimitar Requirement is not asked -- a monster carries no Gear."""
    if not has_combat_advantage(c.world, c.me, c.target):
        return
    if c.strike():
        if c.crit:
            c.damage("2d8", 22)
        else:
            c.hit()
        _one_save_for_both(c, AC, 2, 10, DamageType.UNTYPED)


_M3471_MELEE = "m3471 is hit or missed by a melee attack"


@power(
    "m3471a2",
    level=8,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    trigger=_M3471_MELEE,
    on=(
        Trigger(Hit, both(targets_me, by_melee), _M3471_MELEE),
        Trigger(Miss, both(targets_me, by_melee), _M3471_MELEE),
    ),
)
def m3471a2(c: Cast) -> None:
    attacker = c.trigger.attacker  # type: ignore[union-attr]
    c.shift(1)
    c.basic(on=attacker)


@power("m3471a3", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3471a3(c: Cast) -> None:
    c.no_provoke(on=c.me, until=When.ENCOUNTER, when=lambda ctx: bool(ctx.get("charge")))


@power(
    "m3471a4",
    level=8,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires_text="while bloodied",
    todo=("c.immediate_actions()",),
)
def m3471a4(c: Cast) -> None:
    """Letting `m3471a2` answer twice a round while bloodied needs a way
    to grant a second immediate action for one named row; nothing does
    that."""


_M3471_HITS = "m3471 hits with a melee attack"


@power(
    "m3471a5",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3471_HITS,
    on=Trigger(Hit, both(by_me, by_melee), _M3471_HITS),
)
def m3471a5(c: Cast) -> None:
    c.shift(1)


_M3471_EFFECT = "m3471 becomes subject to an effect"


@power(
    "m3471a6",
    level=8,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3471_EFFECT,
    on=Trigger(EffectApplied, targets_me, _M3471_EFFECT),
)
def m3471a6(c: Cast) -> None:
    c.save()


# --------------------------------------------------------------------------
# m3593
# --------------------------------------------------------------------------


@power(
    "m3593a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 5),
)
def m3593a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3593a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 2),
    dropped=("c.contract()",),
)
def m3593a1(c: Cast) -> None:
    """Contracting the printed disease has no verb -- there is no disease
    track on a board. The damage and the ongoing are written."""
    if c.strike():
        c.hit()
        c.ongoing(5, on=c.target)


@power(
    "m3593a2", level=8, usage=AT_WILL, action=MINOR, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.POLYMORPH], dropped=("c.forbid(tied_to=)",),
)
def m3593a2(c: Cast) -> None:
    """The disguise is appearance and is noted. Losing the bite for as
    long as the new shape holds needs `c.forbid` tied to the shape's own
    end rather than a fixed timer, which is not available."""
    c.form(until=When.ENCOUNTER, label=c.ref)


@power("m3593a3", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3593a3(c: Cast) -> None:
    def when(ctx: dict[str, Any]) -> bool:
        return bool(ctx.get("advantage")) and not ctx.get("ranged")

    c.bonus("damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER, when=when)


# --------------------------------------------------------------------------
# m3650
# --------------------------------------------------------------------------


@power(
    "m3650a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d12", 6),
)
def m3650a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3650a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d12", 6, kind=LIMITED),
)
def m3650a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(3)
    c.basic()


_M3650_DOWN = "the m3650 drops to 0 hit points"


@power(
    "m3650a2",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC, Keyword.POLYMORPH],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC),
    trigger=_M3650_DOWN,
    on=Trigger(Dropped, about_me, _M3650_DOWN),
)
def m3650a2(c: Cast) -> None:
    """Dies either way; the new shape it takes has nothing left to fight
    in and is noted, not implemented."""
    killer = getattr(c.trigger, "source", None)
    if killer is None:
        return
    if c.strike(on=killer):
        c.hit(on=killer)
        c.dazed(on=killer, until=When.EONT)


@power(
    "m3650a3", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    todo=("c.charge_at(at=)",),
)
def m3650a3(c: Cast) -> None:
    """`c.charge_at` picks its own walk-in square; there is no way to name
    a different adjacent one instead."""


@power(
    "m3650a4", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m3650a4(c: Cast) -> None:
    """Appearance only, so the body just notes the shape; nothing in a
    fight reads it."""
    me = c.me

    def killed(ev: Dropped) -> None:
        if ev.source != me or not ev.dead or "humanoid" not in c.kinds_of(on=ev.actor):
            return
        c.note(f"{c.ref}: takes on the slain creature's form")

    c.watch(Dropped, killed, until=When.ENCOUNTER, on=me, label=c.ref)


# --------------------------------------------------------------------------
# m3675
# --------------------------------------------------------------------------


@power(
    "m3675a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 5),
)
def m3675a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(1)


@power(
    "m3675a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
)
def m3675a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3675a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
)
def m3675a2(c: Cast) -> None:
    def hidden_from(f: int) -> bool:
        mine = concealment_of(c.world, c.me) is not Cover.NONE
        return mine or cover_between(c.world, f, c.me) is not Cover.NONE

    victim = _restricted_to(c, 5, hidden_from)
    if victim is None:
        return
    c.gains_advantage(lambda ctx, v=victim: ctx.get("target") == v, on=c.me, until=When.EOT)


@power("m3675a3", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3675a3(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


@power("m3675a4", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3675a4(c: Cast) -> None:
    _dodges_openings(c, 2)


_M3675_HIT = "the m3675 would be hit by an attack"


@power(
    "m3675a5",
    level=8,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M3675_HIT,
    on=Trigger(AttackRolled, _rolled_would_hit, _M3675_HIT),
)
def m3675a5(c: Cast) -> None:
    c.reroll_attack(keep="new")


# --------------------------------------------------------------------------
# m4255
# --------------------------------------------------------------------------


@power(
    "m4255a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 3),
)
def m4255a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(c.roll("1d6"), dtype=DamageType.RADIANT)


@power(
    "m4255a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RADIANT],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d6", 5, dtype=[DamageType.FIRE, DamageType.RADIANT]),
)
def m4255a1(c: Cast) -> None:
    if c.strike():
        c.hit()


_M4255_MISS = "a melee attack misses m4255"


@power(
    "m4255a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4255_MISS,
    on=Trigger(Miss, both(targets_me, by_melee), _M4255_MISS),
)
def m4255a2(c: Cast) -> None:
    attacker = c.trigger.attacker  # type: ignore[union-attr]
    c.shift(1)
    c.use_power("m4255a0", on=attacker, spend=False)
    if c.landed:
        c.push(2, on=attacker)
        c.prone(on=attacker)


@power(
    "m4255a3", level=8, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
)
def m4255a3(c: Cast) -> None:
    foe = _adjacent_foe(c, c.ref)
    hits = 0
    same_target: int | None = None
    for _ in range(2):
        if foe is None:
            break
        c.use_power("m4255a0", on=foe, spend=False)
        if c.landed:
            hits += 1
            same_target = foe
        c.shift(2)
        foe = _adjacent_foe(c, c.ref)
    if hits == 2 and same_target is not None:
        c.ongoing(5, DamageType.RADIANT, on=same_target)
        c.push(2, on=same_target)


@power(
    "m4255a4", level=8, usage=Usage.RECHARGE, recharge=6, action=MOVE, reach=PERSONAL,
    target=NO_TARGET, no_provoke=True,
)
def m4255a4(c: Cast) -> None:
    c.jump(6)


@power(
    "m4255a5", level=8, usage=Usage.RECHARGE, recharge=6, action=STANDARD, reach=PERSONAL,
    target=NO_TARGET, keywords=[Keyword.HEALING],
)
def m4255a5(c: Cast) -> None:
    options = [c.me, *c.allies()]
    victim = c.choose(options, f"{c.ref}: who heals")
    if victim is not None:
        c.heal(39, on=victim)


# --------------------------------------------------------------------------
# m4324
# --------------------------------------------------------------------------


@power(
    "m4324a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 7),
)
def m4324a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(1)


@power(
    "m4324a1",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d10", 7, kind=LIMITED),
)
def m4324a1(c: Cast) -> None:
    """A flail Requirement is not asked -- a monster carries no Gear. A
    target without combat advantage is a use spent on nothing."""
    if not has_combat_advantage(c.world, c.me, c.target):
        return
    if c.strike():
        c.hit()
        c.slide(1)
        c.prone()
    c.shift(1)


_M4324_MELEE = "a melee attack hits or misses m4324"


@power(
    "m4324a2",
    level=8,
    usage=AT_WILL,
    action=INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 5),
    requires_text="it must be wielding two flails",
    trigger=_M4324_MELEE,
    on=Trigger(AttackRolled, both(targets_me, by_melee), _M4324_MELEE),
)
def m4324a2(c: Cast) -> None:
    ev = c.trigger
    vs = getattr(ev, "vs", AC)
    c.bonus(vs, 2, on=c.me, once=True, until=When.EOT)
    if c.strike(on=ev.attacker):  # type: ignore[union-attr]
        c.hit(on=ev.attacker)  # type: ignore[union-attr]


_M4324_MISS = "a melee or close attack misses m4324"


@power(
    "m4324a3",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4324_MISS,
    on=Trigger(Miss, targets_me, _M4324_MISS),
)
def m4324a3(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m4508
# --------------------------------------------------------------------------


@power(
    "m4508a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
)
def m4508a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4508a1",
    level=8,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 5),
)
def m4508a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4508a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 5, kind=LIMITED),
)
def m4508a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    if c.first:
        me = c.me

        def ended(ev: TurnEnd) -> None:
            if ev.actor in c.enemies() and c.adjacent(ev.actor):
                c.flat(5, on=ev.actor)

        c.watch(TurnEnd, ended, until=When.SONT, on=me, label=c.ref)


@power("m4508a3", level=8, usage=AT_WILL, action=MOVE, reach=PERSONAL, target=NO_TARGET)
def m4508a3(c: Cast) -> None:
    c.shift(2)


@power("m4508a4", level=8, usage=ENCOUNTER, action=MINOR, reach=PERSONAL, target=NO_TARGET)
def m4508a4(c: Cast) -> None:
    c.cure(Condition.MARKED, on=c.me)


@power("m4508a5", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4508a5(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


# --------------------------------------------------------------------------
# m5127
# --------------------------------------------------------------------------


@power(
    "m5127a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d6", 5, dtype=DamageType.FIRE),
)
def m5127a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5127a1", level=8, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.FIRE], attack=Attack(vs=REF, printed=13),
)
def m5127a1(c: Cast) -> None:
    c.shift(2)
    foe = _adjacent_foe(c, c.ref)
    if foe is not None and c.strike(on=foe):
        c.ongoing(15, DamageType.FIRE, on=foe)
    c.shift(3)


@power(
    "m5127a2", level=8, usage=AT_WILL, action=MOVE, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION], dropped=("c.terrain(at=)",),
)
def m5127a2(c: Cast) -> None:
    """Landing beside a square of fire has no verb to aim a teleport at
    terrain; landing beside a creature already burning is written."""
    foe = next((f for f in c.enemies() if _taking_ongoing(c, f, DamageType.FIRE)), None)
    spot = _free_square_beside(c, foe) if foe is not None else None
    c.teleport(10, to=spot)


_M5127_MISS = "an attack misses the m5127"


@power(
    "m5127a3",
    level=8,
    usage=AT_WILL,
    action=ActionType.OPPORTUNITY,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5127_MISS,
    on=Trigger(Miss, targets_me, _M5127_MISS),
)
def m5127a3(c: Cast) -> None:
    c.shift(1)


# --------------------------------------------------------------------------
# m5293
# --------------------------------------------------------------------------


@power(
    "m5293a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.THUNDER, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d4", 7, dtype=DamageType.THUNDER),
)
def m5293a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m5293a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d8", 7),
)
def m5293a1(c: Cast) -> None:
    victim = _restricted_to(c, 1, lambda f: c.is_(Condition.DAZED, on=f))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.stunned(on=victim, until=When.EONT)


@power(
    "m5293a2",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d12", 5, kind=LIMITED),
)
def m5293a2(c: Cast) -> None:
    """The before/after shift is made once, taken before -- spread across
    every target of one burst use is not worth two branches that would
    have to agree with each other."""
    if c.first:
        c.shift(2)
    if c.strike():
        c.hit()
        if c.is_(Condition.DAZED) or c.is_(Condition.STUNNED):
            c.flat(c.roll("1d12"))
        c.slide(2)


@power(
    "m5293a3", level=8, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m5293a3(c: Cast) -> None:
    c.teleport(5)
    for d in ALL_DEFENCES:
        c.bonus(d, 2, on=c.me, until=When.EONT)


@power("m5293a4", level=8, usage=AT_WILL, action=MOVE, reach=PERSONAL, target=NO_TARGET)
def m5293a4(c: Cast) -> None:
    c.shift(5)


_M5293_DMG = "the m5293 takes damage"


@power(
    "m5293a5",
    level=8,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    trigger=_M5293_DMG,
    on=Trigger(DamageApplied, targets_me, _M5293_DMG),
)
def m5293a5(c: Cast) -> None:
    """The early end -- "until after it hits or misses" -- is not asked;
    the fixed end of its next turn is the safe upper bound that is
    written."""
    c.invisible(until=When.EONT)


# --------------------------------------------------------------------------
# m5614
# --------------------------------------------------------------------------


@power("m5614a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5614a0(c: Cast) -> None:
    from combat_engine.content.monsters.level_07.brutes import _aura

    def eligible(who: int) -> bool:
        return who in c.enemies()

    def hold(who: int) -> Effect | None:
        return c.penalty("attack", 2, on=who, until=When.ENCOUNTER)

    _aura(c, 1, eligible, hold)


@power(
    "m5614a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 9),
)
def m5614a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5614a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 9),
)
def m5614a2(c: Cast) -> None:
    early = c.may("step before the attack")
    if early:
        c.shift(2)
    ca = has_combat_advantage(c.world, c.me, c.target)
    if c.strike():
        c.hit()
        if ca:
            c.flat(c.roll("2d6"), dtype=DamageType.NECROTIC)
    if not early:
        c.shift(2)


def _m5614_held(world: World, me: int, ev: ConditionApplied) -> bool:
    held = (Condition.IMMOBILIZED, Condition.SLOWED, Condition.RESTRAINED)
    return ev.target == me and ev.condition in held


_M5614_HELD = "m5614 is subjected to an effect that immobilizes, slows, or restrains her"


@power(
    "m5614a3",
    level=8,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5614_HELD,
    on=Trigger(ConditionApplied, _m5614_held, _M5614_HELD),
)
def m5614a3(c: Cast) -> None:
    c.cure(c.trigger.condition, on=c.me)  # type: ignore[union-attr]
    c.insubstantial(until=When.EONT)
    c.phasing(until=When.EONT)


# --------------------------------------------------------------------------
# m5630
# --------------------------------------------------------------------------


@power("m5630a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5630a0(c: Cast) -> None:
    """Nothing in this engine restricts the actions a charge leaves you --
    the second half of the printed trait is already true here."""
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("charge")),
    )


@power(
    "m5630a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d6", 6),
)
def m5630a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.crit:
            c.ongoing(5, on=c.target)


@power("m5630a2", level=8, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m5630a2(c: Cast) -> None:
    for _ in range(2):
        foe = _adjacent_foe(c, c.ref)
        if foe is not None:
            c.use_power("m5630a1", on=foe, spend=False)


@power(
    "m5630a3",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.COLD, Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("3d6", 8, kind=LIMITED, half_on_miss=True),
)
def m5630a3(c: Cast) -> None:
    def worse(eff: Effect) -> None:
        c.world.effects.end(eff, "worsened")
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS, on=eff.owner, ongoing=(5, DamageType.COLD)
        )

    if c.strike():
        c.hit()
        burn = c.ongoing(5, DamageType.COLD, until=When.SAVE_ENDS)
        if burn is not None:
            burn.escalate = worse
    else:
        c.hit(half=True)


_M5630_FLANK = "an enemy ends its movement flanking the m5630"


@power(
    "m5630a4",
    level=8,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M5630_FLANK,
    on=Trigger(MoveEnd, _ended_flanking, _M5630_FLANK),
)
def m5630a4(c: Cast) -> None:
    if c.may("shift instead of moving its speed"):
        c.shift(1)
    else:
        c.move(c.speed_of())


_M5630_HIT = "an enemy within 5 squares of the m5630 hits it with an attack"


@power(
    "m5630a5",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.COLD],
    trigger=_M5630_HIT,
    on=Trigger(Hit, both(targets_me, enemy_within(5)), _M5630_HIT),
)
def m5630a5(c: Cast) -> None:
    attacker = c.trigger.attacker  # type: ignore[union-attr]
    c.flat(10, dtype=DamageType.COLD, on=attacker)
    c.push(2, on=attacker)


# --------------------------------------------------------------------------
# m5963
# --------------------------------------------------------------------------


@power("m5963a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5963a0(c: Cast) -> None:
    """The one-use window is not re-armed each turn -- a judgment call
    against a card that names a window this board has no clock for
    beyond "fire damage, then the next hit.\""""
    me = c.me
    armed = {"on": False}

    def took_fire(ev: DamageApplied) -> None:
        if ev.target == me and DamageType.FIRE in ev.types():
            armed["on"] = True

    def rider(ev: Hit) -> None:
        if ev.attacker == me and armed["on"]:
            armed["on"] = False
            c.flat(5, dtype=DamageType.FIRE, on=ev.target)

    c.watch(DamageApplied, took_fire, until=When.ENCOUNTER, on=me, label=f"{c.ref} lit")
    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=f"{c.ref} burn")


@power("m5963a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5963a1(c: Cast) -> None:
    """If a single attack targets both it and its rider, a miss against
    either is a miss against both. Caught on `AttackRolled`, before
    `resolve.attack` turns the roll into a `Hit` or `Miss` -- forcing the
    natural to 1 is the same lever `c.reroll_attack` pulls, and
    `resolve.attack` reads it back once the window closes. Only the roll
    that resolves **second** of the pair can be corrected this way; if the
    first one already landed as a hit, the damage is already applied by
    the time the second is known, and this does not undo it."""
    me = c.me
    pending: dict[tuple[int, tuple[int, ...]], Any] = {}

    def rolled(ev: AttackRolled) -> None:
        rider = c.rider()
        if rider is None or me not in ev.among or rider not in ev.among:
            return
        if ev.target not in (me, rider):
            return
        key = (ev.attacker, ev.among)
        first = pending.pop(key, None)
        if first is None:
            pending[key] = ev
            return
        if not first.result.hit and ev.result.hit:
            ev.result.natural = 1

    c.watch(AttackRolled, rolled, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5963a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 5),
)
def m5963a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        amount = 10 if bool(getattr(c.result, "advantage", False)) else 5
        c.ongoing(amount, DamageType.FIRE)


@power(
    "m5963a3", level=8, usage=AT_WILL, action=MINOR, reach=Melee(2), target=ONE_CREATURE,
    once_per_round=True, attack=Attack(vs=REF, printed=11),
)
def m5963a3(c: Cast) -> None:
    if c.strike():
        hold = c.grab()
        if hold is not None:
            c.grants_advantage(
                on=c.target, until=When.ENCOUNTER,
                when=lambda ctx: ctx.get("target") in c.grabbing(),
            )


# --------------------------------------------------------------------------
# m6003
# --------------------------------------------------------------------------


@power("m6003a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6003a0(c: Cast) -> None:
    def rider(ev: Hit) -> None:
        if ev.attacker != c.me or not bool(getattr(ev.result, "advantage", False)):
            return
        roll = c.roll("1d4")
        if roll == 1:
            c.dazed(on=ev.target, until=When.SAVE_ENDS)
        elif roll == 2:
            c.immobilized(on=ev.target, until=When.SAVE_ENDS)
        elif roll == 3:
            c.slowed(on=ev.target, until=When.SAVE_ENDS)
        else:
            c.ongoing(5, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power(
    "m6003a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7),
)
def m6003a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m6003a2", level=8, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m6003a2(c: Cast) -> None:
    total = c.roll("1d6") + 2
    half = max(1, total // 2)
    c.shift(half)
    foe = _adjacent_foe(c, c.ref)
    if foe is not None:
        c.use_power("m6003a1", on=foe, spend=False)
    c.shift(total - half)


_M6003_HIT = "m6003 is hit by a melee or a ranged attack"


@power(
    "m6003a3",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6003_HIT,
    on=Trigger(AttackRolled, _rolled_would_hit, _M6003_HIT),
)
def m6003a3(c: Cast) -> None:
    if c.roll("1d20") >= 10:
        c.trigger.result.natural = 1  # type: ignore[union-attr]


# --------------------------------------------------------------------------
# m6063
# --------------------------------------------------------------------------


@power("m6063a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6063a0(c: Cast) -> None:
    from combat_engine.content.monsters.level_07.brutes import _aura

    def eligible(who: int) -> bool:
        return who in c.allies() and not c.is_kind("elf", on=who)

    def hold(who: int) -> Effect | None:
        return c.bonus("perception", 2, on=who, kind="racial", until=When.ENCOUNTER)

    _aura(c, 5, eligible, hold)


@power("m6063a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6063a1(c: Cast) -> None:
    _covered_ground(c, "1d6", 3, When.SONT)

    def far_enough(_kind: str, start: Any, end: Any, _steps: int) -> None:
        if start is None or c.turn_of() != c.me or distance(start, end) < 3:
            return
        for d in ALL_DEFENCES:
            c.bonus(d, 2, on=c.me, until=When.SONT)

    _after_moving(c, far_enough)


@power("m6063a2", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6063a2(c: Cast) -> None:
    c.ignores_difficult("shift", on=c.me, until=When.ENCOUNTER)


@power(
    "m6063a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 4),
)
def m6063a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m6063a4", level=8, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m6063a4(c: Cast) -> None:
    for _ in range(2):
        foe = _adjacent_foe(c, c.ref)
        if foe is not None:
            c.use_power("m6063a3", on=foe, spend=False)


@power(
    "m6063a5",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 4),
)
def m6063a5(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(c.speed_of())
    foe = _adjacent_foe(c, c.ref)
    if foe is not None and c.attack(15, AC, on=foe):
        c.damage("3d6", 4, on=foe)


_M6063_ROLL = "m6063 makes an attack roll and dislikes the result"


@power(
    "m6063a6",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6063_ROLL,
    on=Trigger(AttackRolled, by_me, _M6063_ROLL),
)
def m6063a6(c: Cast) -> None:
    c.reroll_attack(keep="new")


# --------------------------------------------------------------------------
# m6071
# --------------------------------------------------------------------------


@power(
    "m6071a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 6),
)
def m6071a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m6071a1", level=8, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m6071a1(c: Cast) -> None:
    half = max(1, c.speed_of() // 2)
    c.shift(half)
    foe = _adjacent_foe(c, c.ref)
    bloodied_before = c.bloodied(on=foe) if foe is not None else False
    if foe is not None:
        c.use_power("m6071a0", on=foe, spend=False)
    if foe is not None and not bloodied_before and c.bloodied(on=foe):
        c.use_power("m6071a0", on=foe, spend=False)
    c.shift(c.speed_of() - half)


_M6071_DOWN = "the m6071 drops to 0 hit points"


@power(
    "m6071a2",
    level=8,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6071_DOWN,
    on=Trigger(Dropped, about_me, _M6071_DOWN),
)
def m6071a2(c: Cast) -> None:
    c.extra_action(ActionType.STANDARD)


# --------------------------------------------------------------------------
# m6429
# --------------------------------------------------------------------------


@power("m6429a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6429a0(c: Cast) -> None:
    def gate(ctx: dict[str, Any]) -> bool:
        mount = c.mount()
        if mount is None:
            return False
        ident = c.world.get(mount, Ident)
        if ident is None or ident.ref != "m3227":
            return False
        foe = ctx.get("target")
        if foe is None:
            return False
        return not c.world.relations.sources(Relation.RIDDEN_BY, foe)

    c.gains_advantage(gate, on=c.me, until=When.ENCOUNTER)


@power("m6429a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6429a1(c: Cast) -> None:
    _dodges_openings(c, 2)


@power(
    "m6429a2",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("3d6", 6, half_on_miss=True),
)
def m6429a2(c: Cast) -> None:
    ca = has_combat_advantage(c.world, c.me, c.target)
    if c.strike():
        c.hit()
    elif ca:
        c.hit(half=True)


@power("m6429a3", level=8, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m6429a3(c: Cast) -> None:
    for _ in range(2):
        c.shift(3)
        foe = _adjacent_foe(c, c.ref)
        if foe is not None:
            c.use_power("m6429a2", on=foe, spend=False)


_M6429_START = "m6429 starts his turn immobilized, restrained, or slowed"


@power(
    "m6429a4",
    level=8,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6429_START,
    on=Trigger(TurnStart, about_me, _M6429_START),
)
def m6429a4(c: Cast) -> None:
    if any(c.is_(cond) for cond in (Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.SLOWED)):
        c.save()


_M6429_HIT = "an enemy hits m6429 with an attack"


@power(
    "m6429a5",
    level=8,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M6429_HIT,
    on=Trigger(AttackRolled, _rolled_would_hit, _M6429_HIT),
)
def m6429a5(c: Cast) -> None:
    c.reroll_attack(keep="new")


# --------------------------------------------------------------------------
# m6436
# --------------------------------------------------------------------------


@power("m6436a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6436a0(c: Cast) -> None:
    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, when=lambda ctx: bool(c.grabbing()))


@power(
    "m6436a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d8", 7),
    requires_text="it must not be grabbing a creature",
)
def m6436a1(c: Cast) -> None:
    if c.grabbing():
        return
    if c.strike():
        c.hit()
        c.grab()
        victim = c.target

        def burn(_ev: Any = None) -> None:
            if victim in c.grabbing():
                c.flat(5, on=victim)

        c.watch(TurnStart, burn, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} burn")


@power(
    "m6436a2", level=8, usage=Usage.RECHARGE, recharge=6, action=MOVE, reach=PERSONAL,
    target=NO_TARGET, keywords=[Keyword.TELEPORTATION],
)
def m6436a2(c: Cast) -> None:
    c.teleport(5, share=True)


@power(
    "m6436a3", level=8, usage=AT_WILL, action=MINOR, reach=Melee(1), target=ONE_CREATURE,
    once_per_round=True, keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d6", 9),
)
def m6436a3(c: Cast) -> None:
    victim = _restricted_to(c, 1, lambda f: f in c.grabbing())
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        hold = c.weakened(on=victim, until=When.SAVE_ENDS)
        if hold is not None:
            victim_id = victim

            def released(_ev: Any = None) -> None:
                if victim_id not in c.grabbing():
                    c.world.effects.end(hold, "no longer grabbed")

            c.watch(TurnEnd, released, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} release")


# --------------------------------------------------------------------------
# m6558
# --------------------------------------------------------------------------


@power("m6558a0", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6558a0(c: Cast) -> None:
    zone = c.aura(3, until=When.ENCOUNTER)

    def spent(ev: SurgeSpent) -> None:
        if ev.actor in c.enemies() and ev.actor in c.world.zones.occupants(zone):
            c.half_healing(on=ev.actor, until=When.EOT)

    c.watch(SurgeSpent, spent, until=When.ENCOUNTER, on=c.me, label=c.ref)


@power("m6558a1", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6558a1(c: Cast) -> None:
    """Breathing underwater is already true of a board with no drowning
    mechanic to exempt it from; the attack bonus is the real half."""
    c.bonus(
        "attack", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: c.terrain("aquatic") and not c.is_kind("aquatic", on=ctx.get("target")),
    )


@power(
    "m6558a2", level=8, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    todo=("c.extra_turn(script=)",),
)
def m6558a2(c: Cast) -> None:
    """`c.extra_turn` hands back a whole ordinary turn at a count, not a
    scripted shift-and-claws -- there is no way to pin just this action
    to a fixed initiative count without handing the policy a free turn
    instead."""


@power(
    "m6558a3",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 12),
)
def m6558a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(2)


@power("m6558a4", level=8, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m6558a4(c: Cast) -> None:
    for _ in range(2):
        foe = _adjacent_foe(c, c.ref)
        if foe is not None:
            c.use_power("m6558a3", on=foe, spend=False)


@power(
    "m6558a5",
    level=8,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("3d6", 6, kind=LIMITED),
)
def m6558a5(c: Cast) -> None:
    """The printed target is "creatures in the blast", everyone rather
    than only enemies."""
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m6558a6",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("4d6", 8, dtype=DamageType.PSYCHIC, half_on_miss=True),
)
def m6558a6(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m6558a7", level=8, usage=AT_WILL, action=MINOR, reach=PERSONAL, target=NO_TARGET,
    keywords=[Keyword.POLYMORPH], narrative=("skill:insight",),
)
def m6558a7(c: Cast) -> None:
    """Appearance only -- the Insight check to see through it is a
    circumstance with no roll this board makes."""
    c.form(until=When.ENCOUNTER, label=c.ref)


# --------------------------------------------------------------------------
# m840
# --------------------------------------------------------------------------


@power(
    "m840a0",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 1),
)
def m840a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m840a1",
    level=8,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d4", 9),
)
def m840a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m840a2",
    level=8,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("1d4", 4),
)
def m840a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


def _revenge_bonus_m840(c: Cast, extra: int) -> None:
    from combat_engine.content.monsters.level_04.lurkers_sa import _hit_me_since_my_turn

    c.bonus(
        "attack", 1, on=c.me, kind="power", once=True, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") in _hit_me_since_my_turn(c),
    )

    def rider(ev: Hit) -> None:
        if ev.attacker == c.me and ev.target in _hit_me_since_my_turn(c):
            c.flat(extra, on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=c.me, once=True, label=c.ref)


@power("m840a3", level=8, usage=ENCOUNTER, action=MINOR, reach=PERSONAL, target=NO_TARGET)
def m840a3(c: Cast) -> None:
    _revenge_bonus_m840(c, 5)


@power("m840a4", level=8, usage=ENCOUNTER, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m840a4(c: Cast) -> None:
    """"Has not yet acted" is tracked by who has started a turn, read at
    the moment of each attack rather than snapshotted once, since the set
    only grows."""
    me = c.me
    acted: set[int] = set()

    def started(ev: TurnStart) -> None:
        acted.add(ev.actor)

    c.gains_advantage(lambda ctx: ctx.get("target") not in acted, on=me, until=When.ENCOUNTER)
    c.watch(TurnStart, started, until=When.ENCOUNTER, on=me, label=c.ref)


@power("m840a5", level=8, usage=ENCOUNTER, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m840a5(c: Cast) -> None:
    _per_round_rider(c, "2d6", lambda ev: bool(getattr(ev.result, "advantage", False)))


@power("m840a6", level=8, usage=ENCOUNTER, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m840a6(c: Cast) -> None:
    c.bonus(
        "attack", 1, on=c.me, kind="racial", until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(on=ctx.get("target")),
    )
