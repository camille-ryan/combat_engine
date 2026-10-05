"""Monster abilities, level 5, skirmishers, second sweep.

171 rows across the stat blocks `skirmishers.py` did not reach -- the split is
by *when* the work was done, not by what the creatures are. Twelve of the
forty-seven blocks in this slot print no abilities at all and have nothing to
decorate: m146, m15, m272, m2837, m2859, m2913, m2995, m3024, m455, m4852,
m493, m5034.

Conventions, inherited from the level-1 to level-4 sweeps and from this
level's `artillery_sa.py`, `brutes_sa.py`, `minions_sa.py` and `misc_sa.py`:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=10)`) and the damage line goes in the
  header as data, so an MM1 block can be rescaled to MM3 maths later;
* a **trait** costs no action, has no target, and arms whatever holds it,
  whatever action the compendium's column claims;
* a card that prints no range at all is melee 1; a printed band like "15/30"
  takes the short number;
* `half_on_miss=True` is header data only -- a Miss line is also written as
  `else: c.hit(half=True)`;
* a target restricted to a *state* the creature is suffering ("a prone
  creature", "a creature marked by it", "an immobilized creature") cannot
  live in `Target`, which filters on side and size only -- it is a
  Requirement that decides whether the row is offered at all, and a body
  redirect for when the chosen target does not qualify. The marker names
  which narrowing it is: `Target.condition` for a condition the creature
  carries, `Target.relation` for one that is about the attacker ("marked by
  it"), `Target.bloodied` for bloodied;
* a printed Requirement naming a weapon ("requires a scimitar") is not asked:
  a monster carries no `Gear`, and the blow is the block's own basic attack.

Three shapechangers (`m5597`, `m5599`, `m6121`) reuse the lycanthrope
machinery from `level_04/brutes.py` -- `_in_shape`, `_in_shapes` and
`_change_shape` -- rather than growing a fourth copy of it. Two cards
(`m3532a1`, `m3544a2`) lost their attack line to extraction entirely; both
roll through the block's own named basic attack instead, which is what the
printed total actually was, so nothing is lost and no marker is needed.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import (
    _any_enemy_suffering,
    _recharge_when_bloodied,
)
from combat_engine.content.monsters.level_01.brutes_sa import _crit_line
from combat_engine.content.monsters.level_01.skirmishers_sa import _moved_far
from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES
from combat_engine.content.monsters.level_02.lurkers_sa import (
    _has_an_opening,
    _triggering_enemy,
    _twice,
)
from combat_engine.content.monsters.level_02.soldiers_sa import (
    _missed_me_in_melee,
    _ref_of,
    _save_ends_on_me,
)
from combat_engine.content.monsters.level_03.artillery_sa import _death_throe
from combat_engine.content.monsters.level_03.skirmishers_sa import _mobile_attack
from combat_engine.content.monsters.level_04.brutes import (
    _change_shape,
    _in_shape,
    _is_bloodied,
)
from combat_engine.content.monsters.level_04.brutes_sa import _in_shapes
from combat_engine.content.monsters.level_05.artillery_sa import _bloodied_edge
from combat_engine.content.monsters.level_05.brutes_sa import _i_charged
from combat_engine.engine import (
    AC,
    AT_WILL,
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
    Damage,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Relation,
    UpTo,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.events import (
    AttackRolled,
    DamageApplied,
    Dropped,
    EffectApplied,
    Hit,
    InitiativeRolled,
    Miss,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    allies,
    distance_between,
    enemies,
    has_combat_advantage,
    team,
)
from combat_engine.engine.triggers import (
    Trigger,
    both,
    by_charge,
    by_me,
    by_melee,
    would_hit_me,
)

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _edge_on_target(c: Cast) -> Any:
    """"Extra damage against any target granting combat advantage to it."
    Held as a modifier gated at damage time -- the target of the hit being
    rolled, not the target `c` happened to start with."""

    def gate(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and has_combat_advantage(c.world, c.me, victim)

    return gate


def _hit_me_within(radius: int) -> Any:
    """"An enemy within N squares of it hits it with an attack." `targets_me`
    says nothing about distance, so both halves are asked here."""

    def check(world: World, me: int, ev: Any) -> bool:
        attacker = getattr(ev, "attacker", None)
        if getattr(ev, "target", None) != me or attacker is None:
            return False
        if team(world, attacker) is team(world, me):
            return False
        return distance_between(world, me, attacker) <= radius

    return check


def _target_unsupported(c: Cast) -> Any:
    """"A creature that has no allies adjacent to it" -- asked of the
    target's own side, not the caster's."""

    def gate(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None:
            return False
        return not any(
            distance_between(c.world, victim, mate) <= 1
            for mate in allies(c.world, victim)
        )

    return gate


def _any_enemy_marked_by_me(world: World, eid: int) -> bool:
    """"Targets a creature marked by it," as a Requirement deciding whether
    the row is offered at all."""
    return any(
        world.relations.holds(Relation.MARKED_BY, eid, foe) for foe in enemies(world, eid)
    )


def _took_damage(world: World, me: int, ev: Any) -> bool:
    """"It takes damage." `DamageApplied` names its subject `target`."""
    return getattr(ev, "target", None) == me


def _any_enemy_bloodied(world: World, eid: int) -> bool:
    return any(_is_bloodied(world, foe) for foe in enemies(world, eid))


def _brother_about_to_be_hit(world: World, me: int, ev: Any) -> bool:
    """"An attack hits the m6012's brother while they are adjacent to each
    other." "Brother" is another of the same stat block -- no name reaches
    this file, so sameness is read off `Ident.ref`."""
    from combat_engine.engine.components import Ident

    victim = getattr(ev, "target", None)
    if victim is None or victim == me:
        return False
    mine = world.get(me, Ident)
    theirs = world.get(victim, Ident)
    if mine is None or theirs is None or mine.ref != theirs.ref:
        return False
    if distance_between(world, me, victim) > 1:
        return False
    result = getattr(ev, "result", None)
    return bool(result and result.hit)


# ==========================================================================
# m1022
# ==========================================================================


@power(
    "m1022a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 5),
)
def m1022a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1022a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 5),
)
def m1022a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(2)


@power(
    "m1022a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1022a2(c: Cast) -> None:
    """"A single basic attack against each creature it moves adjacent to
    during this move." One square at a time, nobody struck twice."""
    struck: set[int] = set()
    for _ in range(c.speed_of()):
        c.shift(1)
        for foe in c.enemies():
            if foe in struck or c.distance(foe) > 1:
                continue
            struck.add(foe)
            c.basic(on=foe)


# ==========================================================================
# m115791
# ==========================================================================


@power(
    "m115791a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115791a0(c: Cast) -> None:
    c.bonus("attack", 4, on=c.me, until=When.ENCOUNTER, when=_target_unsupported(c))


@power(
    "m115791a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115791a1(c: Cast) -> None:
    c.bonus(
        "damage", 5, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: c.is_hidden(from_=ctx.get("target")),
    )


@power(
    "m115791a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 6),
)
def m115791a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115791a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 5),
)
def m115791a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115791a4",
    level=5,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m115791a4(c: Cast) -> None:
    """The Stealth check is asked for free: `c.hide` is "becomes hidden" and
    already lasts until it attacks or the clock runs out, which is the
    printed shape -- the cover condition is a judgement call, not a gap."""
    c.shift(c.speed_of())
    c.hide(until=When.ENCOUNTER)


# ==========================================================================
# m1165
# ==========================================================================


@power(
    "m1165a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d4", 6),
)
def m1165a0(c: Cast) -> None:
    c.no_provoke(on=c.me, until=When.EOT)
    c.move(2)
    if c.strike():
        c.hit()


@power(
    "m1165a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d4", 2),
)
def m1165a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1165a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d4", 6, kind=LIMITED),
)
def m1165a2(c: Cast) -> None:
    c.shift(3)
    if c.strike():
        c.hit()


@power(
    "m1165a3",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1165a3(c: Cast) -> None:
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m1165a4",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m1165a4(c: Cast) -> None:
    """A disguise and nothing else -- none of this block's other rows are
    gated on a shape, so there is no attack this appearance change ever
    unlocks."""


# ==========================================================================
# m1498
# ==========================================================================


@power(
    "m1498a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 2),
)
def m1498a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1498a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 2),
)
def m1498a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1498a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m1498a2(c: Cast) -> None:
    """The javelin and the charge are two named rows rather than a number
    invented here; both roll through the block's own cards."""
    victim = c.target
    if victim is None:
        return
    c.use_power("m1498a1", on=victim)
    c.charge_at(victim)


@power(
    "m1498a3",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1498a3(c: Cast) -> None:
    me = c.me

    def paid() -> None:
        c.bonus("damage", 0, dice="1d8", on=me, until=When.SOTNT)

    _moved_far(c, me, 4, paid)


# ==========================================================================
# m1529
# ==========================================================================


@power(
    "m1529a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 3),
)
def m1529a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1529a1",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 3, kind=LIMITED),
)
def m1529a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m1529a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m1529a2(c: Cast) -> None:
    """Sending word to an off-board ally has nothing a fight reads; nothing
    on this board models "automatically sends its warning on dropping to 0
    hit points" either, for the same reason."""


@power(
    "m1529a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m1529a3(c: Cast) -> None:
    c.shift(1)


@power(
    "m1529a4",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1529a4(c: Cast) -> None:
    for which in ALL_DEFENCES:
        c.bonus(
            which, 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: c.is_trap(ctx.get("attacker")),
        )


# ==========================================================================
# m2002
# ==========================================================================


@power(
    "m2002a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    damage=Damage("1d6", 2, dtype=DamageType.NECROTIC),
)
def m2002a0(c: Cast) -> None:
    """No "+N vs Defence" survived extraction at all -- the card's own Hit
    line names no roll, so this lands automatically, the way the spec gives
    it rather than one invented here."""
    c.damage("1d6", 2, dtype=DamageType.NECROTIC)
    c.blinded(until=When.EONT)


@power(
    "m2002a1",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d8", 4, dtype=DamageType.NECROTIC),
    requires=_any_enemy_bloodied,
    requires_text="it targets a bloodied enemy",
    dropped=("Target.bloodied",),
)
def m2002a1(c: Cast) -> None:
    victim = c.target
    if victim is not None and not c.bloodied(on=victim):
        victim = next((f for f in c.enemies() if c.bloodied(on=f)), None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.ongoing(5, DamageType.NECROTIC, on=victim)


@power(
    "m2002a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=6),
    damage=Damage("2d6", 5, kind=LIMITED),
)
def m2002a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    if c.first:
        c.shift(3)


# ==========================================================================
# m2778
# ==========================================================================


@power(
    "m2778a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 5),
)
def m2778a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2778a1",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    requires=_is_bloodied,
    requires_text="usable only while bloodied",
)
def m2778a1(c: Cast) -> None:
    c.basic(on=c.target)
    c.heal(15, on=c.me)


@power(
    "m2778a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2778a2(c: Cast) -> None:
    _mobile_attack(c, max(1, c.speed_of() // 2))


@power(
    "m2778a3",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it charges",
    on=Trigger(Hit, _i_charged, "it charges"),
)
def m2778a3(c: Cast) -> None:
    c.grant_action("shift", MOVE, on=c.me, until=When.EOT)


# ==========================================================================
# m3245
# ==========================================================================


@power(
    "m3245a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 4),
)
def m3245a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m3245a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 4),
    requires=_any_enemy_marked_by_me,
    requires_text="it targets a creature marked by it",
    dropped=("Target.relation",),
)
def m3245a1(c: Cast) -> None:
    victim = c.target
    if victim is not None and not c.marked(on=victim):
        victim = next((f for f in c.enemies() if c.marked(on=f)), None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.slide(2, on=victim)
        c.slowed(until=When.SAVE_ENDS, on=victim)


@power(
    "m3245a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
)
def m3245a2(c: Cast) -> None:
    _recharge_when_bloodied(c)
    c.shift(1, who=c.target)
    c.bonus("damage", 2, on=c.target, until=When.EONT, once=True)


@power(
    "m3245a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=ONE_ALLY,
)
def m3245a3(c: Cast) -> None:
    """"The m3245 or an ally" retaliates -- written as m3245 itself, since
    nothing picks which ally more faithfully than that."""
    mate = c.target
    if mate is None:
        return
    foe = next((f for f in c.enemies() if distance_between(c.world, mate, f) <= 1), None)
    if foe is None:
        return
    me = c.me

    def retaliate(ev: Hit) -> None:
        if ev.attacker != foe or ev.target != mate:
            return
        c.basic(on=foe)

    c.watch(Hit, retaliate, until=When.EOT, on=me, once=True, label=f"{c.ref} retaliate")
    c.provoke(foe, on=mate)


@power(
    "m3245a4",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, by_me, "it drops"),
)
def m3245a4(c: Cast) -> None:
    _death_throe(c)


# ==========================================================================
# m3254
# ==========================================================================


@power(
    "m3254a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 6),
)
def m3254a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d8", 14)


@power(
    "m3254a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    requires=_has_an_opening,
    requires_text="it has combat advantage against the target",
)
def m3254a1(c: Cast) -> None:
    _twice(c, "m3254a0")


@power(
    "m3254a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3254a2(c: Cast) -> None:
    c.no_provoke(on=c.me, until=When.ENCOUNTER, when=lambda _ctx: c.charge)


@power(
    "m3254a3",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it hits with a melee attack",
    on=Trigger(Hit, by_me, "it hits with a melee attack"),
)
def m3254a3(c: Cast) -> None:
    c.shift(1)


@power(
    "m3254a4",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is subjected to an effect that a save can end",
    on=Trigger(EffectApplied, _save_ends_on_me, "an effect a save can end lands on it"),
)
def m3254a4(c: Cast) -> None:
    label = getattr(c.trigger, "label", "")
    c.save(on=c.me, against=label)


# ==========================================================================
# m3529
# ==========================================================================


@power(
    "m3529a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 4, dtype=DamageType.NECROTIC),
)
def m3529a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.spend_surge(on=c.target)
        c.shift(3)


@power(
    "m3529a1",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it suffers an effect that a save can end",
    on=Trigger(EffectApplied, _save_ends_on_me, "an effect a save can end lands on it"),
)
def m3529a1(c: Cast) -> None:
    label = getattr(c.trigger, "label", "")
    c.save(on=c.me, against=label)


# ==========================================================================
# m3532
# ==========================================================================


@power(
    "m3532a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d4", 5),
)
def m3532a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(2)


@power(
    "m3532a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m3532a1(c: Cast) -> None:
    """"Two different targets" is what `UpTo(2)` already enforces. The
    printed attack line did not survive extraction, so each swing rolls
    through the named basic attack instead of a number invented here.

    m3532a0's own rider steps it 2 squares, and that step lands *between* the
    two swings -- so the second target was being hit from out of reach. The
    fix is here and not in m3532a0: one `toward=` cannot serve two different
    creatures, and the row that moves cannot know who is still owed a swing.
    So each swing is aimed when it is made, at someone in reach who has not
    been swung at yet, and the whole use runs on `c.first`.
    """
    if not c.first:
        return
    swung: list[int] = []
    for chosen in c.targets[:2]:
        victim = chosen if c.adjacent(chosen) else None
        if victim is None:
            victim = next(
                (f for f in c.enemies() if f not in swung and c.adjacent(f)), None
            )
        if victim is None:
            continue
        swung.append(victim)
        c.use_power("m3532a0", on=victim)


@power(
    "m3532a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3532a2(c: Cast) -> None:
    me = c.me

    def drain(ev: Hit) -> None:
        if ev.attacker != me or not by_melee(c.world, me, ev):
            return
        if has_combat_advantage(c.world, me, ev.target):
            c.spend_surge(on=ev.target)

    c.watch(Hit, drain, until=When.ENCOUNTER, on=me, label=f"{c.ref} drain")


@power(
    "m3532a3",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it suffers an effect that a save can end",
    on=Trigger(EffectApplied, _save_ends_on_me, "an effect a save can end lands on it"),
)
def m3532a3(c: Cast) -> None:
    label = getattr(c.trigger, "label", "")
    c.save(on=c.me, against=label)


# ==========================================================================
# m3544
# ==========================================================================


@power(
    "m3544a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 6),
)
def m3544a0(c: Cast) -> None:
    if c.strike():
        _crit_line(c, "1d8", 14)


@power(
    "m3544a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    charges=True,
)
def m3544a1(c: Cast) -> None:
    """The attack line lost both its defence and its damage in extraction --
    "+8 vs " with nothing after. What survived is the charge itself, the
    exemption for leaving the square, and the shift after -- so the swing
    rolls through the block's own basic attack rather than a number
    invented here."""
    foe = next(iter(c.enemies()), None)
    if foe is None:
        return
    c.no_provoke(on=c.me, until=When.EOT)
    c.charge_at(foe)
    c.shift(1)


@power(
    "m3544a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m3544a2(c: Cast) -> None:
    """One swing of the printed basic attack per target.

    What broke the second swing is not in this row at all: m3544a4 is a free
    action on any melee hit of its own and it steps 1 square, so it fires
    between the two swings here. The fix is in this row rather than in
    m3544a4 -- that row is a card in its own right, it cannot know a swing is
    pending, and one `toward=` cannot serve two different creatures. So each
    swing is aimed when it is made, at someone in reach who has not been
    swung at yet, and the whole use runs on `c.first`.
    """
    if not c.first:
        return
    swung: list[int] = []
    for chosen in c.targets[:2]:
        victim = chosen if c.adjacent(chosen) else None
        if victim is None:
            victim = next(
                (f for f in c.enemies() if f not in swung and c.adjacent(f)), None
            )
        if victim is None:
            continue
        swung.append(victim)
        c.use_power("m3544a0", on=victim)


@power(
    "m3544a3",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3544a3(c: Cast) -> None:
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m3544a4",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it hits with a melee attack",
    on=Trigger(Hit, by_me, "it hits with a melee attack"),
)
def m3544a4(c: Cast) -> None:
    c.shift(1)


@power(
    "m3544a5",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it suffers an effect that a save can end",
    on=Trigger(EffectApplied, _save_ends_on_me, "an effect a save can end lands on it"),
)
def m3544a5(c: Cast) -> None:
    label = getattr(c.trigger, "label", "")
    c.save(on=c.me, against=label)


# ==========================================================================
# m4000
# ==========================================================================


@power(
    "m4000a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 4, dtype=DamageType.NECROTIC),
)
def m4000a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None and c.attack(c.world.scaling.trim(8, c.level), FORT, on=victim):
            c.spend_surge(on=victim)


@power(
    "m4000a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 5),
)
def m4000a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m4000a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
)
def m4000a2(c: Cast) -> None:
    """"Before, between, or after" is taken before, and ranked `toward=` the
    creature both swings are for: three unranked squares were enough to walk
    out of reach of the thing it was about to bite."""
    c.shift(3, toward=c.target)
    c.use_power("m4000a0", on=c.target)
    c.use_power("m4000a1", on=c.target)


@power(
    "m4000a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("1d8", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4000a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


# ==========================================================================
# m4249
# ==========================================================================


@power(
    "m4249a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 7),
)
def m4249a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(2)


@power(
    "m4249a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 6),
)
def m4249a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4249a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("1d6", 8, dtype=DamageType.RADIANT, kind=LIMITED),
    requires=_has_an_opening,
    requires_text="it has combat advantage against the target",
)
def m4249a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m4249a3",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4249a3(c: Cast) -> None:
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


# ==========================================================================
# m4305
# ==========================================================================


@power(
    "m4305a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 6),
)
def m4305a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4305a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
    requires=_any_enemy_suffering(Condition.PRONE),
    requires_text="it targets a prone creature",
    dropped=("Target.condition",),
)
def m4305a1(c: Cast) -> None:
    victim = c.target
    if victim is not None and not c.is_(Condition.PRONE, on=victim):
        victim = next((f for f in c.enemies() if c.is_(Condition.PRONE, on=f)), None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)


@power(
    "m4305a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4305a2(c: Cast) -> None:
    _mobile_attack(c, max(1, c.speed_of() // 2))


@power(
    "m4305a3",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is missed by a melee attack",
    on=Trigger(Miss, _missed_me_in_melee, "a melee attack misses it"),
)
def m4305a3(c: Cast) -> None:
    c.shift(1)


@power(
    "m4305a4",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it hits with a charge attack",
    on=Trigger(Hit, both(by_me, by_charge), "it hits with a charge attack"),
)
def m4305a4(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    c.flat(c.roll("1d6"), on=victim)
    c.prone(on=victim)


# ==========================================================================
# m4418
# ==========================================================================


@power(
    "m4418a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 4),
)
def m4418a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4418a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 4),
)
def m4418a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4418a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(3),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 4, dtype=DamageType.NECROTIC),
)
def m4418a2(c: Cast) -> None:
    if c.first:
        c.shift(6)
    if c.strike():
        c.hit()


@power(
    "m4418a3",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=NO_TARGET,
    todo=("spec.monster_ref()",),
)
def m4418a3(c: Cast) -> None:
    """The brief names what appears in prose and gives it no ref, so there is
    nothing to hand `c.summon` -- which exists, and was the wrong thing to mark.
    Three other rows wait on the same gap under this symbol."""


@power(
    "m4418a4",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, by_me, "it drops"),
)
def m4418a4(c: Cast) -> None:
    c.blinded(until=When.SAVE_ENDS)


@power(
    "m4418a5",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4418a5(c: Cast) -> None:
    c.bonus("damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m4418a6",
    level=5,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4418a6(c: Cast) -> None:
    c.bonus(AC, 4, on=c.me, until=When.EOT, when=lambda ctx: bool(ctx.get("opportunity")))
    c.move(4)
    near = frozenset(f for f in c.enemies() if c.distance(f) <= 1)
    c.gains_advantage(lambda ctx: ctx.get("target") in near, on=c.me, until=When.EOT)


# ==========================================================================
# m4639
# ==========================================================================


@power(
    "m4639a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 2),
)
def m4639a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4639a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("1d10", 5, dtype=DamageType.PSYCHIC),
)
def m4639a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m4639a2",
    level=5,
    usage=AT_WILL,
    action=REACTION,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
    trigger="it is hit or missed by an attack",
    on=(
        Trigger(Hit, lambda w, me, ev: getattr(ev, "target", None) == me, "it is hit"),
        Trigger(Miss, lambda w, me, ev: getattr(ev, "target", None) == me, "it is missed"),
    ),
)
def m4639a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.vulnerable(10, DamageType.PSYCHIC, on=foe, until=When.EONT)


@power(
    "m4639a3",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    trigger="it takes damage",
    on=Trigger(DamageApplied, _took_damage, "it takes damage"),
)
def m4639a3(c: Cast) -> None:
    c.hide(until=When.EONT)


@power(
    "m4639a4",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it damages an enemy",
    on=Trigger(Hit, by_me, "it damages an enemy"),
)
def m4639a4(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.penalty(WILL, 2, on=victim, until=When.SAVE_ENDS)


# ==========================================================================
# m5084
# ==========================================================================


@power(
    "m5084a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("query.charging()",),
)
def m5084a0(c: Cast) -> None:
    """Nothing asks whether a creature is mid-charge from the defending
    side; the attack context's `charge` flag names the attacker's charge,
    not this creature's own."""


@power(
    "m5084a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 8),
)
def m5084a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m5084a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m5084a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m5084a3",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it hits an enemy",
    on=Trigger(Hit, by_me, "it hits an enemy"),
)
def m5084a3(c: Cast) -> None:
    hit = getattr(c.trigger, "target", None)
    foe = next((f for f in c.enemies() if f != hit), hit)
    if foe is not None:
        c.charge_at(foe)


@power(
    "m5084a4",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, by_me, "it drops"),
)
def m5084a4(c: Cast) -> None:
    c.extra_action(ActionType.STANDARD, on=c.me)


# ==========================================================================
# m5337
# ==========================================================================


@power(
    "m5337a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m5337a0(c: Cast) -> None:
    """"Melee attacks" narrows the gate to the reach kind, which is read off
    the power rather than guessed from `ranged`."""
    edge = _edge_on_target(c)

    def gate(ctx: dict[str, Any]) -> bool:
        from combat_engine.engine import get

        row = get(str(ctx.get("power") or ""))
        return row is not None and row.reach.kind == "melee" and edge(ctx)

    c.bonus(
        "damage", 0, dice="1d6", dtype=DamageType.PSYCHIC, on=c.me, until=When.ENCOUNTER, when=gate
    )


@power(
    "m5337a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 8),
)
def m5337a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(2)


@power(
    "m5337a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("2d6", 4),
    requires=_has_an_opening,
    requires_text="it targets a creature granting it combat advantage",
    dropped=("Target.relation",),
)
def m5337a2(c: Cast) -> None:
    victim = c.target
    if victim is not None and not has_combat_advantage(c.world, c.me, victim):
        victim = next(
            (f for f in c.enemies() if has_combat_advantage(c.world, c.me, f)), None
        )
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.condition(Condition.DAZED, Condition.IMMOBILIZED, until=When.EONT, on=victim)


@power(
    "m5337a3",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=ONE_CREATURE,
    dropped=("c.forbid(relation=)",),
)
def m5337a3(c: Cast) -> None:
    """The CA half is exact. "Cannot become hidden from it" has nowhere to live.

    The gap is a **verb**, not the relation: `Relation.HIDDEN_FROM` exists and
    always did, so a marker naming it could only ever report arrived. `c.forbid`
    takes a row and already takes a `keyword=` on five other rows, so a
    `relation=` is the same widening and the symbol that can go green."""
    victim = c.target
    if victim is not None:
        c.grants_advantage(on=victim, until=When.ENCOUNTER)


# ==========================================================================
# m5404
# ==========================================================================


@power(
    "m5404a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 4),
)
def m5404a0(c: Cast) -> None:
    if c.strike():
        if c.result and c.result.advantage:
            c.damage("2d6", 4)
        else:
            c.hit()


@power(
    "m5404a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 4),
)
def m5404a1(c: Cast) -> None:
    c.mode("fly", c.speed_of(), until=When.EOT, on=c.me)
    half = max(1, c.speed_of() // 2)
    c.move(half, at="fly")
    if c.strike():
        c.hit()
        c.slide(2)
    c.move(c.speed_of() - half, at="fly")


@power(
    "m5404a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=REF, printed=8),
    dropped=("c.contract(ref)",),
)
def m5404a2(c: Cast) -> None:
    """The whole of the Hit line is "exposed to" a disease ref; nothing
    contracts one."""
    c.strike()


@power(
    "m5404a3",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("1d8", 4, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m5404a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m5404a4",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    trigger="it hits with a melee or a ranged attack",
    on=Trigger(Hit, by_me, "it hits with an attack"),
)
def m5404a4(c: Cast) -> None:
    c.penalty("attack", 2, until=When.EONT)


# ==========================================================================
# m5561
# ==========================================================================


@power(
    "m5561a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m5561a0(c: Cast) -> None:
    if c.strike():
        victim = c.target
        if victim is not None and c.is_(Condition.DAZED, on=victim):
            c.damage("3d8", 4)
        else:
            c.hit()


@power(
    "m5561a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=8),
)
def m5561a1(c: Cast) -> None:
    victim = c.target
    plus = 2 if victim is not None and c.is_(Condition.PRONE, on=victim) else 0
    if c.strike(plus=plus):
        c.dazed(until=When.SAVE_ENDS)
        moved = c.shift(c.speed_of())
        if moved and victim is not None:
            c.pull(c.speed_of(), on=victim)


@power(
    "m5561a2",
    level=5,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=8),
)
def m5561a2(c: Cast) -> None:
    for caught in c.overrun():
        if c.strike(on=caught):
            c.prone(on=caught)


# ==========================================================================
# m5597
# ==========================================================================

#: The prefix on m5597a5's hold, so the three gated rows can read which of
#: the block's three shapes is in force.
_M5597_SHAPE = "m5597a5 "
_M5597_SHAPES = ("wolf", "human", "hybrid")


@power(
    "m5597a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.silvered()",),
)
def m5597a0(c: Cast) -> None:
    c.regeneration(5)


@power(
    "m5597a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 4),
    requires=_in_shapes(_M5597_SHAPE, "wolf", "hybrid"),
    requires_text="it must be in its wolf or hybrid form",
)
def m5597a1(c: Cast) -> None:
    if c.strike():
        victim = c.target
        if victim is not None and c.is_(Condition.PRONE, on=victim):
            c.damage("2d6", 9)
        else:
            c.hit()
        c.slide(1)


@power(
    "m5597a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 6),
    requires=_in_shapes(_M5597_SHAPE, "wolf", "hybrid"),
    requires_text="it must be in its wolf or hybrid form",
    dropped=("c.contract(ref)",),
)
def m5597a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5597a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 7),
    requires=_in_shapes(_M5597_SHAPE, "human", "hybrid"),
    requires_text="it must be in its human or hybrid form",
)
def m5597a3(c: Cast) -> None:
    if c.strike():
        victim = c.target
        if victim is not None and c.is_(Condition.PRONE, on=victim):
            c.damage("1d6", 11)
        else:
            c.hit()


@power(
    "m5597a4",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    charges=True,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 6),
    requires=_in_shapes(_M5597_SHAPE, "wolf", "hybrid"),
    requires_text="it must be in its wolf or hybrid form",
)
def m5597a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
        c.shift(max(1, c.speed_of() // 2))


@power(
    "m5597a5",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m5597a5(c: Cast) -> None:
    _change_shape(c, _M5597_SHAPE, _M5597_SHAPES)


# ==========================================================================
# m5599
# ==========================================================================

_M5599_SHAPE = "m5599a4 "
_M5599_SHAPES = ("rat", "human", "hybrid")


@power(
    "m5599a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.silvered()",),
)
def m5599a0(c: Cast) -> None:
    c.regeneration(5)


@power(
    "m5599a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d4", 6),
    requires=_in_shapes(_M5599_SHAPE, "human", "hybrid"),
    requires_text="it must be in its human or hybrid form",
)
def m5599a1(c: Cast) -> None:
    if c.strike():
        victim = c.target
        if victim is not None and has_combat_advantage(c.world, c.me, victim):
            c.damage("4d4", 6)
        else:
            c.hit()


@power(
    "m5599a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 5),
    requires=_in_shapes(_M5599_SHAPE, "rat", "hybrid"),
    requires_text="it must be in its rat or hybrid form",
    dropped=("c.contract(ref)",),
)
def m5599a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None and has_combat_advantage(c.world, c.me, victim):
            c.ongoing(5, on=victim)


@power(
    "m5599a3",
    level=5,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_in_shape(_M5599_SHAPE, "rat"),
    requires_text="it must be in its rat form",
)
def m5599a3(c: Cast) -> None:
    c.shift(c.speed_of())


@power(
    "m5599a4",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m5599a4(c: Cast) -> None:
    _change_shape(c, _M5599_SHAPE, _M5599_SHAPES)


# ==========================================================================
# m5747
# ==========================================================================


@power(
    "m5747a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5747a0(c: Cast) -> None:
    me = c.me
    c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    for foe in c.enemies():
        c.grants_advantage(
            on=foe, to="team", until=When.ENCOUNTER,
            when=lambda _ctx, f=foe: c.bloodied(on=f) and distance_between(c.world, me, f) <= 1,
        )


@power(
    "m5747a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5747a1(c: Cast) -> None:
    me = c.me
    c.aura(3, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    for mate in c.allies():
        if not c.is_kind("drake", on=mate):
            continue
        near = lambda _ctx, m=mate: distance_between(c.world, me, m) <= 3  # noqa: E731
        c.bonus("damage", 2, on=mate, kind="power", until=When.ENCOUNTER, when=near)
        c.bonus("save", 2, on=mate, kind="power", until=When.ENCOUNTER, when=near)


@power(
    "m5747a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5747a2(c: Cast) -> None:
    """"Makes a saving throw. If he saves, those effects end" reads as one
    roll shared by every matching hold -- rolled once and applied to each,
    rather than the engine's ordinary one-roll-per-effect `Effects.save`."""
    me = c.me
    conds = (Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.SLOWED)

    def brace(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        matching = [e for e in c.world.effects.of(me) if any(cd in e.conditions for cd in conds)]
        if not matching:
            return
        if c.save(on=me, bare=True):
            for eff in matching:
                c.world.effects.end(eff, "shook it off")

    c.watch(TurnStart, brace, until=When.ENCOUNTER, on=me, label=f"{c.ref} brace")


@power(
    "m5747a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m5747a3(c: Cast) -> None:
    if c.strike(plus=_bloodied_edge(c)):
        c.hit()


@power(
    "m5747a4",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d8", 4),
)
def m5747a4(c: Cast) -> None:
    c.shift(2)
    if c.strike(plus=_bloodied_edge(c)):
        c.hit()
        if c.result and c.result.advantage:
            c.dazed(until=When.EONT)


@power(
    "m5747a5",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 6, dtype=DamageType.FIRE),
)
def m5747a5(c: Cast) -> None:
    if c.strike(plus=_bloodied_edge(c)):
        c.hit()


@power(
    "m5747a6",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger="an enemy within 10 squares of it hits it with an attack",
    on=Trigger(Hit, _hit_me_within(10), "an enemy within 10 squares hits it"),
)
def m5747a6(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.flat(c.roll("1d6") + 6, dtype=DamageType.FIRE, on=foe)


# ==========================================================================
# m5843
# ==========================================================================


@power(
    "m5843a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5843a0(c: Cast) -> None:
    me = c.me
    c.aura(3, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    for mate in c.allies():
        c.bonus(
            "save", 2, on=mate, kind="power", until=When.ENCOUNTER,
            when=lambda _ctx, m=mate: distance_between(c.world, me, m) <= 3,
        )


@power(
    "m5843a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5843a1(c: Cast) -> None:
    me = c.me

    def gate(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None:
            return False
        return any(distance_between(c.world, mate, victim) <= 1 for mate in c.allies())

    c.gains_advantage(gate, on=me, until=When.ENCOUNTER)


@power(
    "m5843a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m5843a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5843a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 5),
)
def m5843a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m5843a4",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5843a4(c: Cast) -> None:
    foe1 = next(iter(c.enemies()), None)
    if foe1 is None:
        return
    c.use_power("m5843a2", on=foe1)
    c.shift(3)
    foe2 = next(
        (f for f in c.enemies() if f != foe1 and distance_between(c.world, c.me, f) <= 10),
        foe1,
    )
    c.use_power("m5843a3", on=foe2)


@power(
    "m5843a5",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=ONE_CREATURE,
    requires=_is_bloodied,
    requires_text="it must be bloodied",
)
def m5843a5(c: Cast) -> None:
    victim = c.target
    if c.basic(on=victim):
        c.flat(c.roll("2d6"), on=victim)
    else:
        c.flat(c.roll("1d6"), on=c.me)


@power(
    "m5843a6",
    level=5,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy hits it with an attack",
    on=Trigger(AttackRolled, would_hit_me, "an enemy's attack would hit it"),
)
def m5843a6(c: Cast) -> None:
    c.reroll_attack(keep="new")


# ==========================================================================
# m5892
# ==========================================================================


@power(
    "m5892a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5892a0(c: Cast) -> None:
    me = c.me

    def shake(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        c.cure(Condition.IMMOBILIZED, Condition.SLOWED, on=me)

    c.watch(TurnStart, shake, until=When.ENCOUNTER, on=me, label=f"{c.ref} loose")


@power(
    "m5892a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5892a1(c: Cast) -> None:
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m5892a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 9),
)
def m5892a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m5892a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m5892a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m5892a4",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger="an enemy within 10 squares of it hits her with an attack",
    on=Trigger(Hit, _hit_me_within(10), "an enemy within 10 squares hits her"),
)
def m5892a4(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.flat(c.roll("1d6") + 3, dtype=DamageType.FIRE, on=foe)


# ==========================================================================
# m5923
# ==========================================================================


@power(
    "m5923a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5923a0(c: Cast) -> None:
    """The cover-or-concealment half is not asked -- there is no reliable
    "does it have cover right now" query at the moment initiative rolls --
    so the Stealth check is offered unconditionally, which is the generous
    side of the same judgement call."""
    me = c.me

    def opener(ev: InitiativeRolled) -> None:
        if getattr(ev, "actor", None) != me:
            return
        c.hide(until=When.ENCOUNTER)

    c.watch(
        InitiativeRolled, opener, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} opener"
    )


@power(
    "m5923a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5923a1(c: Cast) -> None:
    c.bonus("crit_range", 1, on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m5923a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m5923a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)
    c.shift(1)


@power(
    "m5923a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("3d6", 6, kind=LIMITED),
)
def m5923a3(c: Cast) -> None:
    """"Each time it hits the target, it can shift 1 extra square and slide
    the target 1 extra square (save ends)" is paid as a standing rider on
    this victim rather than re-derived: the first hit lays a save-ends mark
    and a watch pays the extra out on every later hit while the mark
    stands."""
    _recharge_when_bloodied(c)
    c.shift(2)
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.slide(2, on=victim)
    boosted = c.effect(f"{c.ref} rattled", until=When.SAVE_ENDS, on=victim)
    if boosted is None:
        return
    me = c.me

    def extra(ev: Hit) -> None:
        if ev.attacker != me or ev.target != victim:
            return
        if boosted not in c.world.effects.of(victim):
            return
        c.shift(1)
        c.slide(1, on=victim)

    c.watch(Hit, extra, until=When.SAVE_ENDS, on=me, label=f"{c.ref} rattled watch")


@power(
    "m5923a4",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5923a4(c: Cast) -> None:
    c.teleport(c.speed_of())


@power(
    "m5923a5",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    trigger="it takes damage",
    on=Trigger(DamageApplied, _took_damage, "it takes damage"),
)
def m5923a5(c: Cast) -> None:
    c.hide(until=When.EONT)


# ==========================================================================
# m5943
# ==========================================================================


@power(
    "m5943a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 3),
)
def m5943a0(c: Cast) -> None:
    c.shift(1)
    if c.strike():
        victim = c.target
        if victim is not None and has_combat_advantage(c.world, c.me, victim):
            c.damage("3d6", 3)
        else:
            c.hit()


@power(
    "m5943a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 3),
)
def m5943a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m5943a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5943a2(c: Cast) -> None:
    """"Recharge if neither attack hits" is a second, immediate way back up
    besides the die in the header."""
    victim = c.target
    if victim is None:
        return
    c.use_power("m5943a0", on=victim)
    first = c.landed
    c.use_power("m5943a1", on=victim)
    second = c.landed
    if not first and not second:
        c.restore_use(c.ref, on=c.me)


# ==========================================================================
# m6012
# ==========================================================================


@power(
    "m6012a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6012a0(c: Cast) -> None:
    """"Flanking with the m6012's brother" is read as flanking alongside
    another of the same stat block -- no name reaches this file."""

    def flanked_with_brother(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None:
            return False
        return any(
            _ref_of(c, mate) == _ref_of(c, c.me)
            and c.distance(mate) <= 1
            and distance_between(c.world, mate, victim) <= 1
            for mate in c.allies()
        )

    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))
    c.bonus("damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER, when=flanked_with_brother)


@power(
    "m6012a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m6012a1(c: Cast) -> None:
    c.shift(2)
    if c.strike():
        c.hit()
    c.shift(2)


@power(
    "m6012a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("2d8", 4, kind=LIMITED, half_on_miss=True),
)
def m6012a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)
    else:
        c.hit(half=True)


@power(
    "m6012a3",
    level=5,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an attack hits the m6012's brother while they are adjacent to each other",
    on=Trigger(AttackRolled, _brother_about_to_be_hit, "an attack hits its brother"),
)
def m6012a3(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is None:
        return
    for which in ALL_DEFENCES:
        c.bonus(which, 4, on=victim, until=When.EONT, kind="power")


# ==========================================================================
# m6121
# ==========================================================================

_M6121_SHAPE = "m6121a6 "
_M6121_SHAPES = ("jackal", "human")


@power(
    "m6121a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6121a0(c: Cast) -> None:
    me = c.me

    def grant(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.allies():
            return
        if distance_between(c.world, me, ev.actor) <= 3:
            c.grant_action("shift", MINOR, on=ev.actor, until=When.EOT)

    c.watch(TurnStart, grant, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")
    c.aura(3, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)


@power(
    "m6121a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6121a1(c: Cast) -> None:
    def worse(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        return victim is not None and any(
            c.is_(cd, on=victim)
            for cd in (Condition.DAZED, Condition.HELPLESS, Condition.PRONE, Condition.STUNNED)
        )

    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))
    c.bonus("damage", 0, dice="1d12", on=c.me, until=When.ENCOUNTER, when=worse)


@power(
    "m6121a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
    requires=_in_shape(_M6121_SHAPE, "jackal"),
    requires_text="it must be in its jackal form",
)
def m6121a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m6121a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("4d4", 4),
    requires=_in_shape(_M6121_SHAPE, "human"),
    requires_text="it must be in its human form",
)
def m6121a3(c: Cast) -> None:
    if c.strike():
        if c.crit:
            c.flat(c.roll("2d4") + 20)
        else:
            c.hit()
        c.shift(1)


@power(
    "m6121a4",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("2d4", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m6121a4(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return

    def worsen(eff: Any) -> None:
        c.world.effects.end(eff, "fell unconscious")
        c.condition(Condition.UNCONSCIOUS, until=When.EONT, on=victim)

    held = c.condition(Condition.DAZED, until=When.SAVE_ENDS, on=victim, escalate=worsen)
    if held is None:
        return

    def wake(ev: DamageApplied) -> None:
        if ev.target == victim and held in c.world.effects.of(victim):
            c.world.effects.end(held, "damage broke the sleep")

    c.watch(DamageApplied, wake, until=When.SAVE_ENDS, on=victim, label=f"{c.ref} wake")


@power(
    "m6121a5",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(10),
    target=UpTo(2, side="ally"),
)
def m6121a5(c: Cast) -> None:
    _recharge_when_bloodied(c)
    mate = c.target
    if mate is None:
        return
    c.shift(1, who=mate)
    foe = next((f for f in c.enemies() if distance_between(c.world, mate, f) <= 1), None)
    if foe is not None:
        c.basic(who=mate, on=foe)
    else:
        far = next(iter(c.enemies()), None)
        if far is not None:
            c.charge_at(far, who=mate)


@power(
    "m6121a6",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m6121a6(c: Cast) -> None:
    """The equipment-fusion clause has nothing to read -- a monster carries
    no `Gear` for a form to absorb -- so only the shape, the shift and the
    drop-reversion are paid."""
    me = c.me
    label = f"{c.ref} revert"
    if not any(e.label == label for e in c.world.effects.of(me)):

        def revert(ev: Dropped) -> None:
            if ev.actor != me:
                return
            for eff in list(c.world.effects.of(me)):
                if eff.label.startswith(_M6121_SHAPE):
                    c.world.effects.end(eff, "reverted to jackal form")
            c.form(until=When.ENCOUNTER, revert=MINOR, label=f"{_M6121_SHAPE}jackal")

        c.watch(Dropped, revert, until=When.ENCOUNTER, on=me, label=label)
    _change_shape(c, _M6121_SHAPE, _M6121_SHAPES)
    c.shift(3)


# ==========================================================================
# m6476
# ==========================================================================


def _is_living(c: Cast, who: int) -> bool:
    """"Living creature" has no `Keyword` of its own; the undead and the
    construct ones are the project's two negatives for it."""
    return not (c.is_kind("undead", on=who) or c.is_kind("construct", on=who))


@power(
    "m6476a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6476a0(c: Cast) -> None:
    me = c.me
    c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def slow(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if distance_between(c.world, me, ev.actor) <= 1 and _is_living(c, ev.actor):
            c.slowed(on=ev.actor, until=When.EONT)

    c.watch(TurnStart, slow, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura watch")


@power(
    "m6476a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m6476a1(c: Cast) -> None:
    c.shift(1)
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)
    c.shift(1)


@power(
    "m6476a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("4d6", 6),
    requires=_any_enemy_suffering(
        Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.STUNNED, Condition.UNCONSCIOUS
    ),
    requires_text="it targets an immobilized, restrained, stunned or unconscious creature",
    dropped=("Target.condition",),
)
def m6476a2(c: Cast) -> None:
    states = (Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.STUNNED, Condition.UNCONSCIOUS)
    victim = c.target
    if victim is not None and not any(c.is_(s, on=victim) for s in states):
        victim = next((f for f in c.enemies() if any(c.is_(s, on=f) for s in states)), None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.stunned(on=victim, until=When.SAVE_ENDS)
        c.no_healing(on=victim, until=When.SAVE_ENDS)


@power(
    "m6476a3",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d12", 8, dtype=DamageType.NECROTIC),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, by_me, "it drops"),
)
def m6476a3(c: Cast) -> None:
    victim = c.target
    if victim is None or not _is_living(c, victim):
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.ongoing(5, DamageType.NECROTIC, on=victim)


# ==========================================================================
# m6495
# ==========================================================================


@power(
    "m6495a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6495a0(c: Cast) -> None:
    c.no_provoke(on=c.me, until=When.ENCOUNTER, when=lambda _ctx: c.charge)


@power(
    "m6495a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m6495a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m6495a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
)
def m6495a2(c: Cast) -> None:
    _twice(c, "m6495a1")


@power(
    "m6495a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_ALLY,
)
def m6495a3(c: Cast) -> None:
    c.grant_action("shift", FREE, squares_=3, on=c.target, until=When.EOT)


@power(
    "m6495a4",
    level=5,
    usage=ENCOUNTER,
    action=REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is subjected to an effect that a save can end",
    on=Trigger(EffectApplied, _save_ends_on_me, "an effect a save can end lands on it"),
)
def m6495a4(c: Cast) -> None:
    label = getattr(c.trigger, "label", "")
    c.save(on=c.me, against=label)


# ==========================================================================
# m6597
# ==========================================================================


@power(
    "m6597a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6597a0(c: Cast) -> None:
    c.bonus("damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m6597a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6597a1(c: Cast) -> None:
    def gate(ctx: dict[str, Any]) -> bool:
        victim = ctx.get("target")
        if victim is None:
            return False
        return any(c.marked(on=victim, by=ally) for ally in c.allies())

    c.gains_advantage(gate, on=c.me, until=When.ENCOUNTER)


@power(
    "m6597a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m6597a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6597a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
)
def m6597a3(c: Cast) -> None:
    if c.first:
        c.shift(1)
    _twice(c, "m6597a2")


@power(
    "m6597a4",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6597a4(c: Cast) -> None:
    _recharge_when_bloodied(c)
    c.shift(4)
    near = frozenset(f for f in c.enemies() if c.distance(f) <= 1)
    c.gains_advantage(lambda ctx: ctx.get("target") in near, on=c.me, until=When.EOT)


# ==========================================================================
# m842
# ==========================================================================


@power(
    "m842a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d4", 3),
)
def m842a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m842a1",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 6, kind=LIMITED),
)
def m842a1(c: Cast) -> None:
    c.move(2)
    if c.strike():
        c.hit()


@power(
    "m842a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MARTIAL, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d4", 6, kind=LIMITED),
)
def m842a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    mate = next((a for a in c.allies() if c.distance(a) <= 1), None)
    if mate is not None:
        c.swap(mate)


@power(
    "m842a3",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m842a3(c: Cast) -> None:
    c.gains_advantage(
        lambda ctx: c.is_(Condition.SURPRISED, on=ctx.get("target")), on=c.me, until=When.ENCOUNTER
    )


@power(
    "m842a4",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m842a4(c: Cast) -> None:
    c.bonus(
        AC, 2, on=c.me, kind="racial", until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "m842a5",
    level=5,
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an attack hits it",
    on=Trigger(AttackRolled, would_hit_me, "an attack would hit it"),
)
def m842a5(c: Cast) -> None:
    c.reroll_attack(keep="new")


@power(
    "m842a6",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m842a6(c: Cast) -> None:
    me, ref = c.me, c.ref
    spent: dict[str, int] = {}

    def bonus_dmg(ev: Hit) -> None:
        if ev.attacker != me or spent.get("round") == c.world.round:
            return
        if not (ev.result and ev.result.advantage):
            return
        spent["round"] = c.world.round
        c.flat(c.roll("2d6"), on=ev.target)

    c.watch(Hit, bonus_dmg, until=When.ENCOUNTER, on=me, label=ref)


# ==========================================================================
# m878
# ==========================================================================


@power(
    "m878a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 3),
)
def m878a0(c: Cast) -> None:
    if c.strike(plus=_bloodied_edge(c)):
        c.hit()


@power(
    "m878a1",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 3, dtype=DamageType.FIRE, kind=LIMITED),
)
def m878a1(c: Cast) -> None:
    if c.strike(plus=_bloodied_edge(c)):
        c.hit()


@power(
    "m878a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d10", 3),
)
def m878a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m878a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    damage=Damage("3d6", 3, kind=LIMITED),
    attack=Attack(vs=REF, printed=8),
)
def m878a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            for who in c.within(1, of=victim, side="any"):
                if who != victim and who != c.me:
                    c.flat(c.roll("1d6") + 3, dtype=DamageType.FIRE, on=who)


@power(
    "m878a4",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d10", 3, dtype=DamageType.FIRE, kind=LIMITED),
)
def m878a4(c: Cast) -> None:
    if c.strike(plus=_bloodied_edge(c)):
        c.hit()
        c.ongoing(5, DamageType.FIRE)


@power(
    "m878a5",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m878a5(c: Cast) -> None:
    c.bonus(
        "attack", 1, on=c.me, kind="racial", until=When.ENCOUNTER,
        when=lambda _ctx: c.bloodied(),
    )


@power(
    "m878a6",
    level=5,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m878a6(c: Cast) -> None:
    c.teleport(3)
    for which in ALL_DEFENCES:
        c.bonus(which, 2, on=c.me, kind="power", until=When.EONT)
