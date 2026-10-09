"""Monster abilities, level 6, controllers -- second wave.

204 rows, matching `scripts/spec.py --monsters 6 --role controller`.
`controllers.py` holds the earlier sweep of this level and is untouched here;
ten of its stat blocks print no abilities at all and have nothing to decorate
(`m267`, `m2981`, `m2996`, `m307`, `m320`, `m325`, `m4795`, `m4804`, `m4887`,
`m885`).

Conventions, inherited from the level-1 through level-5 sweeps and this
level's own `controllers.py`:

* numbers load from `game.db`; the attack line is written exactly as printed
  and the damage line goes in the header as data;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it, whatever action the compendium's column claims;
* a card that prints no range at all is melee 1; a printed band such as
  "15/30" takes the shorter, normal number;
* a close burst or blast whose card names no target set takes **enemies**,
  except where the card says "creatures in the burst" outright;
* "can push/slide/knock prone" is read as the creature doing it;
* "+N vs AC" with a separate printed crit total that already equals the
  engine's own max-dice-plus-bonus needs no body code; one that does not
  (`m2241`'s "crit 2d6+N" lines) is paid as an explicit flat add in the crit
  branch, the way `level_05/controllers_sa.py`'s `m3134a0` already does;
* "until the end of **its** next turn" on an ordinary Hit clause is the
  printed 4e convention for "the attacker's next turn" and is the engine's
  own default (`When.EONT`) on every condition verb -- no override is
  written for it. `When.EOTNT` is reserved for the rarer case where the
  text is unambiguously about the *victim's* own next turn, independent of
  who cast the row (a death trigger, where the caster has just dropped).

Two spec artifacts, not names: `m1680`'s block refers to itself throughout as
"m977" and "m1680-m1680's m1680", and `m1526`'s block repeats its own ref for
what is clearly a nearby *trap*, not the creature. Both are read as self- or
trap-references, not as a second creature; said again in the report.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES
from combat_engine.content.monsters.level_02.controllers_sa import _let_it_swing, _swing_reach
from combat_engine.content.monsters.level_02.lurkers_sa import _twice
from combat_engine.content.monsters.level_02.skirmishers_sa import _melee_only
from combat_engine.content.monsters.level_03.brutes_sa import (
    _enemy_closed_on_me,
    _recharge_and_fire,
)
from combat_engine.content.monsters.level_06.controllers import DEFENCES, _all_defences
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
    ONE_ALLY,
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
    Keyword,
    Melee,
    MeleeOrRanged,
    Mod,
    Ranged,
    Target,
    UpTo,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.components import Health, Ident
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackDeclared,
    Bloodied,
    DamageApplied,
    Dropped,
    EffectApplied,
    Fell,
    Hit,
    PowerUsed,
    TurnEnd,
    TurnStart,
    ZoneEntered,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    distance_between,
    enemies,
    has_combat_advantage,
    is_,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me, both, by_melee, targets_me
from combat_engine.engine.types import Relation

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _trap_bonus(c: Cast, value: int) -> None:
    """"A bonus to all defenses against traps." The attack context's
    `attacker` is the trap entity, the only place "trap" can be asked from."""
    for which in ALL_DEFENCES:
        c.bonus(
            which, value, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: c.is_trap(ctx.get("attacker")),
        )


def _dominate_one_at_a_time(c: Cast, victim: int, *, until: When, save_mod: int = 0) -> Any:
    """"Can dominate only one creature at a time." The hold lives on the
    victim, not on the caster, so an earlier one is found by walking enemies
    for this row's own label."""
    for foe in c.enemies():
        if foe == victim:
            continue
        for eff in list(c.world.effects.of(foe)):
            if eff.label == c.ref and eff.source == c.me:
                c.world.effects.end(eff, "a new target took its place")
    return c.condition(Condition.DOMINATED, until=until, on=victim, save_mod=save_mod)


def _shake_off_latest_hold(c: Cast) -> None:
    """"It rolls a saving throw against the triggering effect." The trigger
    names no effect of its own, so the most recent save-ends hold standing
    on it is what was just applied."""
    for eff in sorted(c.world.effects.of(c.me), key=lambda e: -e.id):
        if eff.when is When.SAVE_ENDS:
            c.world.effects.save(eff)
            return


def _soft_landing(c: Cast, squares_: int) -> None:
    """"Treats any fall as N feet shorter and always lands on its feet."

    `c.cushion` reads `c.trigger`, so it only does anything answering a
    declared `Trigger(Fell, ...)` -- not from inside a plain `c.watch`,
    which never sets it. Partial cushioning can still leave the creature
    prone, which the printed line does not allow for; approximated with a
    cushion generous enough that an ordinary fall rarely leaves anything to
    answer."""
    c.cushion(squares_)


def _same_stock(c: Cast, who: int) -> bool:
    """Two creatures off the same stat block, the way a printed "another
    <this-creature>" is asked without a name to compare."""
    mine = c.world.get(c.me, Ident)
    theirs = c.world.get(who, Ident)
    return mine is not None and theirs is not None and mine.ref == theirs.ref


def _not_already_grabbing(world: World, eid: int) -> bool:
    return not world.relations.targets(Relation.GRABBED_BY, eid)


def _holds_somebody(world: World, eid: int) -> bool:
    return bool(world.relations.targets(Relation.GRABBED_BY, eid))


# ==========================================================================
# m1007
# ==========================================================================


@power(
    "m1007a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m1007a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1007a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 5),
)
def m1007a1(c: Cast) -> None:
    """"-2 penalty to attack rolls and weakened (save ends both)" is one
    effect, a condition plus a modifier, so one throw ends both."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    mod = Mod(what="attack", value=-2, kind="untyped", label=c.ref)
    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=c.ref,
        conditions=(Condition.WEAKENED,), mods=[(victim, mod)],
    )


@power(
    "m1007a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    requires=_not_already_grabbing,
    requires_text="can grab only one creature at a time",
)
def m1007a2(c: Cast) -> None:
    if c.strike():
        c.grab()


@power(
    "m1007a3",
    level=6,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=10),
    requires=_holds_somebody,
    requires_text="must have a creature grabbed",
)
def m1007a3(c: Cast) -> None:
    """"Affects a target it has grabbed" is found off `c.grabbing` rather
    than a target filter -- there is nowhere else the victim could be."""
    victim = next(iter(c.grabbing()), None)
    if victim is None or not c.strike(on=victim):
        return
    c.shift(c.speed_of(), who=c.me, share=True)


@power(
    "m1007a4",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d4", 5),
    requires=_holds_somebody,
    requires_text="must have a creature grabbed",
)
def m1007a4(c: Cast) -> None:
    victim = next(iter(c.grabbing()), None)
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.dazed(on=victim)


@power(
    "m1007a5",
    level=6,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1007a5(c: Cast) -> None:
    """"The serpent allies within 10 squares" is read as `c.is_kind`'s
    closest available word for the kind; the card names no ally by id for
    this to check against instead."""
    me = c.me
    c.shift(4, who=me)
    for mate in c.allies():
        if c.is_kind("reptile", on=mate) and distance_between(c.world, me, mate) <= 10:
            c.shift(2, who=mate)


@power(
    "m1007a6",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m1007a6(c: Cast) -> None:
    """The shape change is exact. Which of a0/a1/a2 is "bite", "constrict"
    or the human-only weapon is not recoverable from mechanics alone -- the
    brief strips exactly the words that would say -- so no `requires=` gate
    is laid on any of them rather than guess and gate the wrong one. Said
    again in the report."""
    me = c.me
    which = c.choose(["natural form", "human form"], f"{c.ref}: which shape") or "natural form"
    c.form(until=When.ENCOUNTER, revert=MINOR, label=f"{c.ref} {which}")
    _ = me


# ==========================================================================
# m1011
# ==========================================================================


def _i_am_charging(world: World, me: int, ev: Any) -> bool:
    return ev.attacker == me and bool(getattr(ev, "charge", False))


@power(
    "m1011a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 3),
)
def m1011a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1011a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d4", 5, dtype=DamageType.ACID),
)
def m1011a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1011a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d4", 5, dtype=DamageType.ACID, kind=LIMITED),
)
def m1011a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized()


@power(
    "m1011a3",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it charges",
    on=Trigger(AttackDeclared, _i_am_charging, "it charges"),
)
def m1011a3(c: Cast) -> None:
    ev = c.trigger
    victim = getattr(ev, "target", None)
    if victim is None:
        return
    mate = next(
        (a for a in c.allies() if a != c.me and _same_stock(c, a)
         and distance_between(c.world, c.me, a) <= 5),
        None,
    )
    if mate is not None:
        c.charge_at(victim, who=mate)


# ==========================================================================
# m1025
# ==========================================================================


@power(
    "m1025a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 2),
)
def m1025a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1025a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=11),
)
def m1025a1(c: Cast) -> None:
    """The type is chosen at the table, so the header stays untyped and the
    body deals the roll. "-2 to all defenses" is one effect with four
    modifiers, not four."""
    if not c.strike():
        return
    element = c.choose(
        [DamageType.NECROTIC, DamageType.RADIANT], f"{c.ref}: necrotic or radiant"
    ) or DamageType.NECROTIC
    c.damage("1d4", 5, dtype=element)
    victim = c.target
    if victim is not None:
        _all_defences(c, -2, until=When.SAVE_ENDS, on=victim)


@power(
    "m1025a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=10),
)
def m1025a2(c: Cast) -> None:
    if c.strike():
        c.slide(1)
        c.prone()
        c.dazed()


@power(
    "m1025a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("1d4", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m1025a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            c.slide(2, on=victim)
            c.basic(who=victim, on=victim)


# ==========================================================================
# m1057
# ==========================================================================


def _m1057_human_form(world: World, eid: int) -> bool:
    return any(e.label == "m1057a5 human" for e in world.effects.of(eid))


@power(
    "m1057a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 5),
    requires=lambda world, eid: not _m1057_human_form(world, eid),
    requires_text="usable only while not in human form",
)
def m1057a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1057a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 4),
)
def m1057a1(c: Cast) -> None:
    """The disease track itself is a thing the engine does not model, as
    `level_08/brutes.py`'s `m259a0` already notes it for."""
    if c.strike():
        c.hit()
        c.ongoing(2, DamageType.UNTYPED)
        c.note(f"{c.ref}: the target contracts this stat block's disease")


@power(
    "m1057a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d6", 4, dtype=DamageType.FORCE),
)
def m1057a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1057a3",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    attack=Attack(vs=REF, printed=7),
    damage=Damage("2d8", 7, dtype=DamageType.COLD, kind=LIMITED),
)
def m1057a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EOT)


@power(
    "m1057a4",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1057a4(c: Cast) -> None:
    c.bonus(
        "damage", 1, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


@power(
    "m1057a5",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m1057a5(c: Cast) -> None:
    for eff in list(c.world.effects.of(c.me)):
        if eff.label.startswith("m1057a5"):
            c.world.effects.end(eff, "changed shape")
    which = c.choose(["natural form", "human form"], f"{c.ref}: which shape") or "natural form"
    c.form(until=When.ENCOUNTER, revert=MINOR, label=f"{c.ref} {which}")


@power(
    "m1057a6",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m1057a6(c: Cast) -> None:
    c.teleport(10)


# ==========================================================================
# m1059
# ==========================================================================


@power(
    "m1059a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 4),
)
def m1059a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            health = c.world.get(victim, Health)
            if health is not None and health.hp <= 0:
                c.temp_hp(5, on=c.me)


def _recharge_when_neighbor_bloodied(c: Cast, ref: str, radius: int = 1) -> None:
    me = c.me

    def bled(ev: Bloodied) -> None:
        if distance_between(c.world, me, ev.actor) <= radius:
            c.restore_use(ref, on=me)

    c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, once=True, label=f"{ref} recharge")


@power(
    "m1059a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d6", 8, kind=LIMITED),
    requires=lambda world, eid: any(
        has_combat_advantage(world, eid, foe) for foe in enemies(world, eid)
    ),
    requires_text="requires combat advantage",
)
def m1059a1(c: Cast) -> None:
    """The recharge-when-a-neighbor-bloodies clause is armed from the body,
    same shape as every other printed recharge condition in this tree. The
    Requirement cannot ask "against the target" before a target is chosen,
    so it is re-checked here against the one actually picked."""
    _recharge_when_neighbor_bloodied(c, c.ref)
    victim = c.target
    if victim is None or not has_combat_advantage(c.world, c.me, victim):
        return
    if c.strike(on=victim):
        c.hit()
        c.weakened(until=When.SAVE_ENDS)
        c.heal(36, on=c.me)


@power(
    "m1059a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d10", 3, dtype=DamageType.NECROTIC),
)
def m1059a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            c.gains_advantage(
                lambda ctx, v=victim: ctx.get("target") == v, until=When.EONT, on=c.me,
            )


@power(
    "m1059a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=9),
)
def m1059a3(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    held = _dominate_one_at_a_time(c, victim, until=When.SAVE_ENDS, save_mod=-2)
    if held is not None:
        held.on_end.append(lambda: c.dazed(until=When.SAVE_ENDS, on=victim))


def _only_one_zone(c: Cast) -> None:
    from combat_engine.engine.zones import Zone

    for zone in c.my_zones():
        body = c.world.get(zone, Zone)
        if body is not None and body.label == c.ref:
            c.dispel(zone)


@power(
    "m1059a4",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(1),
    target=EACH_OTHER,
    keywords=[Keyword.NECROTIC, Keyword.ZONE],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d6", 3, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1059a4(c: Cast) -> None:
    me = c.me
    if c.first:
        _only_one_zone(c)
        c.zone(c.area(), until=When.ENCOUNTER, label=c.ref)
        squares_ = frozenset(c.area())

        def toll(ev: TurnStart) -> None:
            if ev.ghost:
                return
            if ev.actor not in c.in_squares(squares_, side="any"):
                return
            if team(c.world, ev.actor) is not team(c.world, me):
                c.flat(c.roll("1d6") + 3, dtype=DamageType.NECROTIC, on=ev.actor)
            elif c.bloodied(on=ev.actor):
                c.heal(4, on=ev.actor)

        c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} zone")
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m1059a5",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m1059a5(c: Cast) -> None:
    """"Up to 1 hour" is `When.ENCOUNTER` -- no fight runs that long.
    `revert=MINOR` is the printed "end the effect as a minor action"."""
    shape = c.form(modes={"fly": 12}, until=When.ENCOUNTER, revert=MINOR, label=c.ref)
    held = c.cannot_attack(on=c.me, until=When.ENCOUNTER)
    ins = c.insubstantial(on=c.me, until=When.ENCOUNTER)
    for extra in (held, ins):
        if extra is not None:
            shape.on_end.append(lambda e=extra: c.world.effects.end(e, "reverted"))


# ==========================================================================
# m115822
# ==========================================================================


@power(
    "m115822a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.difficult_for()",),
)
def m115822a0(c: Cast) -> None:
    """"Squares in the aura are difficult terrain for that enemy" is terrain
    keyed to one creature rather than to the ground -- `c.zone(difficult=)`
    makes an area difficult for everybody, and there is no per-creature
    form of it. Nothing here works yet."""


@power(
    "m115822a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5),
)
def m115822a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m115822a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 5),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 7, dtype=DamageType.POISON, kind=LIMITED),
)
def m115822a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()
    else:
        c.grants_advantage()


@power(
    "m115822a3",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 5),
    target=EACH_ENEMY,
    keywords=[Keyword.ZONE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 4, kind=LIMITED, half_on_miss=True),
)
def m115822a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.slowed(until=When.SAVE_ENDS)
    if c.first:
        c.zone(c.area(), difficult=True, until=When.ENCOUNTER, label=c.ref)


@power(
    "m115822a4",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d6", 0),
    requires=lambda world, eid: bool(world.get(eid, Health) and world.get(eid, Health).bloodied),
    requires_text="usable only while bloodied",
)
def m115822a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed()


# ==========================================================================
# m115860
# ==========================================================================


@power(
    "m115860a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
)
def m115860a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m115860a1",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("3d6", 5, kind=LIMITED),
)
def m115860a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()
    c.push(2)


def _opportunity_attack_on_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and bool(getattr(ev, "opportunity", False))


@power(
    "m115860a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy makes an opportunity attack against it",
    on=Trigger(AttackDeclared, _opportunity_attack_on_me, "an enemy makes an opportunity attack"),
)
def m115860a2(c: Cast) -> None:
    """The counter is `m115860a0`, which is Melee 1, and an opportunity
    attack can come from further off than that -- a reach weapon threatens
    at 2 and a few rows at 3. The borrowed row is aimed by `on=`, which
    skips the reach check it would have applied to a target of its own, so
    the reach is asked here. No printed ranged alternative on this block, so
    out of reach means no counter."""
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None and c.distance(foe) <= c.reach("m115860a0"):
        c.use_power("m115860a0", on=foe)


@power(
    "m115860a3",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m115860a3(c: Cast) -> None:
    c.extra_action(STANDARD, on=c.me)


# ==========================================================================
# m1426
# ==========================================================================


@power(
    "m1426a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 1, dtype=DamageType.PSYCHIC),
)
def m1426a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.PSYCHIC)


@power(
    "m1426a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 2),
)
def m1426a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1426a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m1426a2(c: Cast) -> None:
    _twice(c, "m1426a1")


@power(
    "m1426a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m1426a3(c: Cast) -> None:
    if not c.strike():
        c.hit(half=True)
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.condition(
        Condition.DAZED, until=When.SAVE_ENDS, on=victim, ongoing=(5, DamageType.PSYCHIC),
        escalate=lambda eff: c.slide(3, on=victim),
    )
    _ = hold


@power(
    "m1426a4",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m1426a4(c: Cast) -> None:
    _recharge_and_fire(c, "m1426a3")


@power(
    "m1426a5",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.GAZE],
    attack=Attack(vs=WILL, printed=10),
    requires=lambda world, eid: any(
        is_(world, foe, Condition.STUNNED) or is_(world, foe, Condition.DAZED)
        for foe in enemies(world, eid)
    ),
    requires_text="targets a stunned or dazed creature",
)
def m1426a5(c: Cast) -> None:
    """A dominated target held one at a time -- the second dominate ends the
    first, same shape as `m1059a3`. The Requirement is about the board, not
    necessarily about whoever the chooser picked, so the body redirects to a
    qualifying enemy rather than bailing when the two disagree."""

    def _qualifies(who: int | None) -> bool:
        return who is not None and (
            c.is_(Condition.STUNNED, on=who) or c.is_(Condition.DAZED, on=who)
        )

    victim = c.target
    if not _qualifies(victim):
        victim = next((f for f in c.enemies() if _qualifies(f)), None)
    if victim is None or not c.strike(on=victim):
        return
    _dominate_one_at_a_time(c, victim, until=When.EONT)


@power(
    "m1426a6",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=10),
)
def m1426a6(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    held = c.stunned(until=When.EONT, on=victim)
    if held is not None and victim is not None:
        held.on_end.append(lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim))


@power(
    "m1426a7",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.restrict_actions()",),
)
def m1426a7(c: Cast) -> None:
    """The end-of-turn burn is exact. Limiting it to a single standard
    action while it starts its turn in sunlight has no verb that holds down
    which actions a turn may spend."""
    me = c.me

    def burn(ev: TurnEnd) -> None:
        if ev.actor == me and not ev.ghost and c.terrain("sunlight"):
            c.flat(85, on=me)

    c.watch(TurnEnd, burn, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m1481
# ==========================================================================


@power(
    "m1481a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 3),
)
def m1481a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m1481a1",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=10),
)
def m1481a1(c: Cast) -> None:
    if c.strike():
        c.slide(2)


@power(
    "m1481a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=NO_TARGET,
    keywords=[Keyword.POISON, Keyword.TELEPORTATION, Keyword.ZONE],
    dropped=("c.teleport(within=)",),
)
def m1481a2(c: Cast) -> None:
    """The gas is exact. "Can teleport 3 squares as a move action as long as
    it starts and ends within the zone" is a standing option gated on
    standing in a specific zone, and `c.teleport` takes no such gate."""
    me = c.me
    area = c.area()
    squares_ = frozenset(area)
    c.zone(area, difficult=True, until=When.ENCOUNTER, label=c.ref)

    def toll(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.in_squares(squares_, side="any"):
            return
        c.flat(5, dtype=DamageType.POISON, on=ev.actor)
        c.dazed(until=When.EONT, on=ev.actor)

    c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} gas")


# ==========================================================================
# m1526
# ==========================================================================


@power(
    "m1526a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 5),
)
def m1526a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1526a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 6),
)
def m1526a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1526a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.reset_trap()",),
)
def m1526a2(c: Cast) -> None:
    """"Resets an adjacent triggered trap it is aware of" -- read as a trap,
    not a second copy of itself; the number repeats because the extraction
    has nowhere else to put "trap". No verb resets one."""


@power(
    "m1526a3",
    level=6,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="a trap within 2 squares of it is triggered",
    todo=("events.TrapTriggered",),
)
def m1526a3(c: Cast) -> None:
    """No event announces a trap being triggered, so the window this shift
    answers never opens."""


@power(
    "m1526a4",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
)
def m1526a4(c: Cast) -> None:
    if c.target is not None:
        c.slide(1, on=c.target)


@power(
    "m1526a5",
    level=6,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(5),
    target=NO_TARGET,
    trigger="an enemy moves",
    todo=("c.trigger_trap()",),
)
def m1526a5(c: Cast) -> None:
    """"Triggers a trap it is aware of within range" -- same gap as `a2`:
    nothing here can set a trap off from a distance."""


@power(
    "m1526a6",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m1526a6(c: Cast) -> None:
    c.shift(1)


@power(
    "m1526a7",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1526a7(c: Cast) -> None:
    _trap_bonus(c, 4)


# ==========================================================================
# m1528
# ==========================================================================


@power(
    "m1528a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 3),
)
def m1528a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1528a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("1d8", 5, dtype=DamageType.PSYCHIC),
)
def m1528a1(c: Cast) -> None:
    """"Two different targets" is what a body called once per target already
    gives, the way `m914a2` reads the same printed shape."""
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m1528a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
)
def m1528a2(c: Cast) -> None:
    if c.target is not None:
        c.bonus("speed", 4, on=c.target, until=When.EONT)
        c.grant_action("shift", MINOR, squares_=2, on=c.target, until=When.EONT)


@power(
    "m1528a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
)
def m1528a3(c: Cast) -> None:
    if c.target is None:
        return
    c.bonus("attack", 2, on=c.target, until=When.EONT, when=_melee_only)
    c.bonus("damage", 2, on=c.target, until=When.EONT, when=_melee_only)


@power(
    "m1528a4",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m1528a4(c: Cast) -> None:
    c.shift(1)


# ==========================================================================
# m1680
# ==========================================================================


@power(
    "m1680a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 4),
)
def m1680a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d4", 0, dtype=DamageType.NECROTIC)


@power(
    "m1680a1",
    level=6,
    usage=AT_WILL,
    action=MOVE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 4, dtype=DamageType.NECROTIC),
)
def m1680a1(c: Cast) -> None:
    """A flyby attack: half its speed spent either side of the swing. The
    self-reference is read plainly -- the block names itself "m977" and
    "m1680-m1680's m1680" throughout, both garbled copies of "it"."""
    c.no_provoke(on=c.me, until=When.EOT)
    half = max(1, c.speed_of() // 2)
    c.move(half, at="fly")
    if c.strike():
        c.hit()
    c.move(half, at="fly")


@power(
    "m1680a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("3d6", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1680a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m1680a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("3d6", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m1680a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()


@power(
    "m1680a4",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.SLEEP],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("3d6", 4, kind=LIMITED),
)
def m1680a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.unconscious(until=When.SAVE_ENDS)


@power(
    "m1680a5",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1680a5(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


@power(
    "m1680a6",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is damaged by a necrotic attack",
    on=Trigger(
        DamageApplied,
        lambda world, me, ev: ev.target == me and ev.dtype == DamageType.NECROTIC,
        "it is damaged by a necrotic attack",
    ),
)
def m1680a6(c: Cast) -> None:
    c.heal(13, on=c.me)


# ==========================================================================
# m1919
# ==========================================================================


@power(
    "m1919a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=9),
)
def m1919a0(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    _dominate_one_at_a_time(c, victim, until=When.SAVE_ENDS)


@power(
    "m1919a1",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(6),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=9),
)
def m1919a1(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    c.push(4, on=victim)
    if victim is not None and c.scenery("wall", within=1, of=victim):
        c.prone(on=victim)


@power(
    "m1919a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(4),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("1d6", 6, dtype=DamageType.PSYCHIC),
)
def m1919a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty(WILL, 2, until=When.SAVE_ENDS)


# ==========================================================================
# m1985
# ==========================================================================


@power(
    "m1985a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("", 5, dtype=DamageType.NECROTIC, kind=MINION),
)
def m1985a0(c: Cast) -> None:
    """"If another m1985a0 attack has hit the target since the end of its
    last turn" is read with a marker effect: the first hit in the window
    plants it, the second finds it standing and immobilizes instead."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    label = f"{c.ref} marked"
    if any(e.label == label for e in c.world.effects.of(victim)):
        c.immobilized(on=victim)
    else:
        c.effect(label, until=When.EOTNT, on=victim)


@power(
    "m1985a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=9),
    requires=lambda world, eid: any(
        is_(world, foe, Condition.IMMOBILIZED) for foe in enemies(world, eid)
    ),
    requires_text="targets an immobilized creature",
)
def m1985a1(c: Cast) -> None:
    """Recharges when a creature adjacent to it becomes bloodied, armed the
    same way the ordinary self-bloodied recharge is elsewhere, but for
    anyone nearby. "Loses a healing surge" is `c.spend_surge` -- it already
    spends one for nothing, which is exactly the printed line."""
    me = c.me

    def bled(ev: Bloodied) -> None:
        if distance_between(c.world, me, ev.actor) <= 2:
            c.restore_use(c.ref, on=me)

    c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} recharge")
    victim = c.target
    if victim is None or not c.is_(Condition.IMMOBILIZED, on=victim):
        return
    if c.strike(on=victim) and not c.spend_surge(on=victim):
        c.flat(c.surge_value(on=victim), on=victim)


@power(
    "m1985a2",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m1985a2(c: Cast) -> None:
    """Appearance only -- disguised as a living humanoid until it attacks or
    is hit, with no combat mechanic riding on the disguise itself."""


# ==========================================================================
# m2241
# ==========================================================================


def _recharge_on_skeleton_raised(c: Cast) -> None:
    me, ref = c.me, c.ref

    def raised(ev: PowerUsed) -> None:
        if ev.actor == me and ev.power == "m2241a4":
            c.restore_use(ref, on=me)

    c.watch(PowerUsed, raised, until=When.ENCOUNTER, on=me, label=f"{ref} recharge")


@power(
    "m2241a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 2),
)
def m2241a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2241a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d4", 6, dtype=DamageType.FORCE),
)
def m2241a1(c: Cast) -> None:
    """The printed crit total (14) is already what the engine's own
    max-dice-plus-bonus gives 2d4+6, so no body code is needed for it."""
    if c.strike():
        c.hit()


@power(
    "m2241a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d6", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m2241a2(c: Cast) -> None:
    """The printed crit (22) is six over the engine's own max (16), so the
    excess is paid as a flat add in the crit branch, same shape as
    `level_05/controllers_sa.py`'s `m3134a0`."""
    _recharge_on_skeleton_raised(c)
    if c.strike():
        if c.crit:
            c.hit()
            c.flat(6, dtype=DamageType.NECROTIC)
        else:
            c.hit()
        victim = c.target
        if victim is not None and c.is_kind("undead", on=victim):
            c.heal(10, on=victim)


@power(
    "m2241a3",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d8", 10, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m2241a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)
        c.prone()


@power(
    "m2241a4",
    level=6,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION],
)
def m2241a4(c: Cast) -> None:
    c.summon("m2242")


# ==========================================================================
# m2539
# ==========================================================================


@power(
    "m2539a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d4", 0),
)
def m2539a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d4", 0, dtype=DamageType.COLD)
        c.immobilized()


@power(
    "m2539a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d6", 4, dtype=DamageType.COLD),
)
def m2539a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        c.vulnerable(5, DamageType.COLD, until=When.EONT, on=victim)
        c.slowed(until=When.EONT, on=victim)


@power(
    "m2539a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d6", 4, kind=LIMITED),
    dropped=("c.douse(zone=)",),
)
def m2539a2(c: Cast) -> None:
    """Push, prone and the difficult-terrain area all land. Extinguishing
    mundane fire and the fire-keyed zone or conjuration of whoever made it
    is the gap `c.douse(zone=)` already names elsewhere in the tree."""
    if c.strike():
        c.hit()
        c.push(2, anchor=c.origin)
        c.prone()
    if c.first:
        c.zone(c.area(), difficult=True, until=When.EONT, label=c.ref)


@power(
    "m2539a3",
    level=6,
    usage=Usage.DAILY,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.IMPLEMENT],
)
def m2539a3(c: Cast) -> None:
    c.resist(10, DamageType.FIRE, on=c.me, until=When.EONT)


# ==========================================================================
# m3255
# ==========================================================================


@power(
    "m3255a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 6),
)
def m3255a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3255a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 6),
)
def m3255a1(c: Cast) -> None:
    """"Requires a longsword" is not a gate -- `Gear` is empty on every
    monster. The penalty is laid only against the caster's own allies'
    attacks, which is the printed narrowing."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    me = c.me
    mods = [
        (
            victim,
            Mod(
                what=d.value, value=-1, kind="untyped", label=c.ref,
                when=lambda ctx, m=me: team(c.world, ctx.get("attacker")) is team(c.world, m),
            ),
        )
        for d in DEFENCES
    ]
    c.world.effects.apply(victim, me, When.EONT, label=c.ref, mods=mods)


@power(
    "m3255a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=NO_TARGET,
)
def m3255a2(c: Cast) -> None:
    for mate in c.within(5, of=c.me, side="ally")[:2]:
        c.shift(5, who=mate)
        foe = next((f for f in c.enemies() if c.adjacent_to(f, mate)), None)
        if foe is None:
            continue
        c.basic(who=mate, on=foe)
        if c.landed:
            c.mark(on=foe, until=When.EONT, by=mate)


@power(
    "m3255a3",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d6", 0, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m3255a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            c.slide(1, on=mate)


@power(
    "m3255a4",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is subjected to an effect that a save can end",
    on=Trigger(EffectApplied, targets_me, "an effect a save can end lands on it"),
)
def m3255a4(c: Cast) -> None:
    _shake_off_latest_hold(c)


# ==========================================================================
# m3440
# ==========================================================================


@power(
    "m3440a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 3, dtype=DamageType.PSYCHIC),
)
def m3440a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None and c.is_(Condition.SLOWED, on=victim):
            c.dazed(on=victim)
        else:
            c.slowed(on=victim)


@power(
    "m3440a1",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("", 5, dtype=DamageType.PSYCHIC),
)
def m3440a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed()


@power(
    "m3440a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SUMMONING],
)
def m3440a2(c: Cast) -> None:
    c.ignore_resistance(insubstantial=True, on=c.me, until=When.EOT)
    c.flat(5, on=c.me)
    c.summon("m3436")


@power(
    "m3440a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.SUMMONING],
)
def m3440a3(c: Cast) -> None:
    """Recharges when it is first bloodied, armed from the body."""
    me, ref = c.me, c.ref

    def bled(ev: Bloodied) -> None:
        if ev.actor == me:
            c.restore_use(ref, on=me)

    c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, once=True, label=f"{ref} recharge")
    c.ignore_resistance(insubstantial=True, on=c.me, until=When.EOT)
    c.flat(20, on=c.me)
    c.summon("m3440")


@power(
    "m3440a4",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    requires=lambda world, eid: any(
        is_(world, foe, Condition.HELPLESS) or is_(world, foe, Condition.UNCONSCIOUS)
        for foe in enemies(world, eid)
    ),
    requires_text="targets a helpless or unconscious creature",
    dropped=("Defences.insubstantial", "c.lose_mode()"),
)
def m3440a4(c: Cast) -> None:
    """The coup de grace and the heal land. "Loses insubstantial and its fly
    speed" has nothing to take away or set aside -- `Defences` carries no
    insubstantial column and `c.mode` only ever raises a speed -- the same
    pair `level_03/soldiers_sa.py`'s `m3437a2` already names. The body
    redirects to a qualifying enemy the way the Requirement itself asks,
    since the chooser's pick and the board's answer are not always the
    same creature."""

    def _senseless(who: int | None) -> bool:
        return who is not None and (
            c.is_(Condition.HELPLESS, on=who) or c.is_(Condition.UNCONSCIOUS, on=who)
        )

    victim = c.target
    if not _senseless(victim):
        victim = next((f for f in c.enemies() if _senseless(f)), None)
    if victim is None:
        return
    killed = c.coup_de_grace(on=victim)
    if killed:
        health = c.world.get(c.me, Health)
        if health is not None:
            c.heal(health.max_hp // 2, on=c.me)


# ==========================================================================
# m3499
# ==========================================================================


@power(
    "m3499a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 5),
)
def m3499a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3499a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("1d10", 5, dtype=[DamageType.NECROTIC, DamageType.PSYCHIC], kind=LIMITED),
)
def m3499a1(c: Cast) -> None:
    """One roll of two types; the header keeps the first and the second
    rides as a keyword, the same trade `level_05/artillery_sa.py`'s
    `m5886a1` already makes.

    "Moves its speed and makes a basic attack against a target of the
    m3499's choice": the quarry is chosen first so `c.run_at` can walk the
    victim into reach of it -- `c.move` would hand the destinations to the
    decider unordered -- and the swing is still gated on reach, because the
    move may not close the gap. The old fallback aimed the swing at the
    m3499 itself when no other enemy was on the board; a creature does not
    choose to be hit, so now there is simply no swing."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is None:
            return
        quarry = min(
            (f for f in c.enemies() if f != victim),
            key=lambda f: (distance_between(c.world, victim, f), f),
            default=None,
        )
        if quarry is None:
            return
        c.run_at(quarry, who=victim)
        if distance_between(c.world, victim, quarry) <= _swing_reach(c, victim):
            c.basic(who=victim, on=quarry)


@power(
    "m3499a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("1d10", 5, dtype=DamageType.NECROTIC),
)
def m3499a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()


@power(
    "m3499a3",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=Target(side="ally", count=1, label="destroyed undead creature"),
    keywords=[Keyword.HEALING],
    dropped=("query.dead_allies()",),
)
def m3499a3(c: Cast) -> None:
    """Finding a destroyed ally to raise has no query -- the same gap
    `level_05/controllers_sa.py`'s `m3219a5` already names. If the board
    still exposes a fallen ally as a target, `c.reanimate` pays out."""
    victim = c.target
    if victim is None:
        return
    c.reanimate(on=victim, hp=15)


# ==========================================================================
# m3637
# ==========================================================================


@power(
    "m3637a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d10", 2),
)
def m3637a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty(FORT, 2, until=When.EONT)
        c.penalty(WILL, 2, until=When.EONT)


@power(
    "m3637a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 4),
)
def m3637a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)
        c.effect("m3637a1 hit", until=When.EOT, on=c.me)


@power(
    "m3637a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 5, dtype=[DamageType.COLD, DamageType.NECROTIC], kind=LIMITED),
)
def m3637a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m3637a3",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("1d8", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3637a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            c.push(c.speed_of(victim) + 4, on=victim)


@power(
    "m3637a4",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3637a4(c: Cast) -> None:
    c.reroll_attack(keep="new")


@power(
    "m3637a5",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=lambda world, eid: any(
        e.label == "m3637a1 hit" for e in world.effects.of(eid)
    ),
    requires_text="usable only in the same turn after hitting with m3637a1",
)
def m3637a5(c: Cast) -> None:
    c.temp_hp(12, on=c.me)


@power(
    "m3637a6",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3637a6(c: Cast) -> None:
    """Rough ground costs it nothing while it shifts, and nothing else.

    `when="shift"` is the narrowing every one of these cards prints and this
    verb could not say. It is spent in the *search*: a square of difficult
    terrain costs two, a shift is one, so without the exemption the square is
    never offered as a shift destination at all.
    """
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER, when="shift")


# ==========================================================================
# m3761
# ==========================================================================


@power(
    "m3761a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 3),
)
def m3761a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3761a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d8", 6, dtype=DamageType.FORCE),
)
def m3761a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)
        c.immobilized()


@power(
    "m3761a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("3d6", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3761a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m3761a3",
    level=6,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3761a3(c: Cast) -> None:
    """"One ally of 6th level or lower" is approximated as any ally within
    range -- there is no per-creature level filter to carry the cap."""
    mate = next((a for a in c.allies() if distance_between(c.world, c.me, a) <= 5), None)
    if mate is not None:
        _let_it_swing(c, mate)


@power(
    "m3761a4",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it suffers an effect that a save can end",
    on=Trigger(EffectApplied, targets_me, "an effect a save can end lands on it"),
)
def m3761a4(c: Cast) -> None:
    _shake_off_latest_hold(c)


# ==========================================================================
# m4252
# ==========================================================================


@power(
    "m4252a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 3),
)
def m4252a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", 0, dtype=DamageType.RADIANT)


@power(
    "m4252a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.DIVINE],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d6", 4, dtype=DamageType.RADIANT),
)
def m4252a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None and c.is_(Condition.SLOWED, on=victim):
            c.immobilized(on=victim)
        else:
            c.slowed(on=victim)


@power(
    "m4252a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.DIVINE, Keyword.RADIANT],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d6", 5, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m4252a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m4252a3",
    level=6,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4252a3(c: Cast) -> None:
    mate = next((a for a in c.allies() if c.can_see(a)), None)
    if mate is not None:
        _let_it_swing(c, mate)


@power(
    "m4252a4",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m4252a4(c: Cast) -> None:
    me = c.me
    pool = [me] + [a for a in c.allies() if c.adjacent_to(a, me)]
    pick = c.choose(pool, f"{c.ref}: who regains 20?") or me
    c.heal(20, on=pick)


# ==========================================================================
# m5087
# ==========================================================================


@power(
    "m5087a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5087a0(c: Cast) -> None:
    me = c.me
    c.aura(10, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def bled(ev: Bloodied) -> None:
        mate = ev.source
        if mate is None or team(c.world, mate) is not team(c.world, me):
            return
        if distance_between(c.world, me, mate) <= 10:
            c.basic(who=mate, on=ev.actor)

    c.watch(Bloodied, bled, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m5087a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m5087a1(c: Cast) -> None:
    """Regeneration 5, switched off for a turn by acid or fire.

    The pause is `c.suspend_when` and not an end-and-relay: the trait is
    encounter-long, so ending it would spend it on the first splash of acid
    and it would never come back.
    """
    heals = c.regeneration(5, until=When.ENCOUNTER, on=c.me)
    c.suspend_when(
        heals, DamageApplied,
        lambda ev: ev.target == c.me
        and bool({DamageType.ACID, DamageType.FIRE} & {ev.dtype, *ev.dtypes}),
        for_=When.EONT,
    )


@power(
    "m5087a2",
    level=6,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it falls",
    on=Trigger(Fell, about_me, "it is falling"),
)
def m5087a2(c: Cast) -> None:
    _soft_landing(c, 2)


@power(
    "m5087a3",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m5087a3(c: Cast) -> None:
    """The false-death shape `docs/AUTHORING.md` points at: `DamageApplied`
    is read for the killing blow's type and `Dropped` for the fall, with the
    rise deferred to the creature's own next turn rather than paid at once,
    which is the printed difference from `m3533a3`."""
    me = c.me
    last: dict[str, bool] = {"lethal": False}

    def took(ev: DamageApplied) -> None:
        if ev.target == me:
            last["lethal"] = ev.dtype in (DamageType.ACID, DamageType.FIRE)

    def drop(ev: Dropped) -> None:
        if ev.actor == me and not last["lethal"]:
            c.prone(on=me)

    def rise(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost or last["lethal"]:
            return
        health = c.world.get(me, Health)
        if health is not None and health.hp <= 0:
            c.reanimate(on=me, hp=5)

    c.watch(DamageApplied, took, until=When.ENCOUNTER, on=me, label=f"{c.ref} last blow")
    c.watch(Dropped, drop, until=When.ENCOUNTER, on=me, label=f"{c.ref} falls")
    c.watch(TurnStart, rise, until=When.ENCOUNTER, on=me, label=f"{c.ref} rises")


@power(
    "m5087a4",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 3),
)
def m5087a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m5087a5",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("2d6", 0),
)
def m5087a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            c.bonus("attack", 2, on=mate, until=When.SONT)


@power(
    "m5087a6",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m5087a6(c: Cast) -> None:
    c.extra_action(STANDARD, on=c.me)


# ==========================================================================
# m5091
# ==========================================================================


@power(
    "m5091a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 5),
)
def m5091a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5091a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
)
def m5091a1(c: Cast) -> None:
    """"Requires m5091 to be wielding a [weapon]" is not a gate -- `Gear` is
    empty on every monster."""
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    c.condition(
        Condition.RESTRAINED, until=When.SAVE_ENDS, on=victim,
        escalate=lambda eff: c.flat(c.roll("1d6") + 2, on=victim),
    )


@power(
    "m5091a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("3d6", 6, kind=LIMITED),
)
def m5091a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.dazed()


@power(
    "m5091a3",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m5091a3(c: Cast) -> None:
    c.extra_action(STANDARD, on=c.me)


# ==========================================================================
# m5395
# ==========================================================================


@power(
    "m5395a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5395a0(c: Cast) -> None:
    c.bonus(
        AC, 2, on=c.me, until=When.ENCOUNTER, when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power(
    "m5395a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("3d6", 3),
)
def m5395a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    mate = next((a for a in c.allies() if distance_between(c.world, c.me, a) <= 5), None)
    if mate is not None:
        c.shift(1, who=mate)


@power(
    "m5395a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 3, dtype=DamageType.POISON),
)
def m5395a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.vulnerable(5, DamageType.POISON, until=When.SONT)


@power(
    "m5395a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d10", 3, kind=LIMITED),
)
def m5395a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            c.heal(5, on=mate)


@power(
    "m5395a4",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("3d6", 4, kind=LIMITED),
)
def m5395a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


# ==========================================================================
# m5409
# ==========================================================================


@power(
    "m5409a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5409a0(c: Cast) -> None:
    me = c.me

    def slide_away(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if distance_between(c.world, me, ev.actor) <= 3:
            c.slide(1, on=ev.actor)

    c.aura(3, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    c.watch(TurnStart, slide_away, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m5409a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 4),
)
def m5409a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d8", 0, dtype=DamageType.FORCE)
        c.slide(1)


@power(
    "m5409a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 4),
)
def m5409a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5409a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m5409a3(c: Cast) -> None:
    _twice(c, "m5409a2")


@power(
    "m5409a4",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d10", 4, dtype=DamageType.FORCE, kind=LIMITED, half_on_miss=True),
)
def m5409a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m5409a5",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=10),
)
def m5409a5(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    held = c.stunned(until=When.EONT, on=victim)
    if held is not None and victim is not None:
        held.on_end.append(lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim))


@power(
    "m5409a6",
    level=6,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=8),
)
def m5409a6(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    me = c.me
    if victim is not None:
        c.penalty(
            "attack", 2, on=victim, until=When.EONT,
            when=lambda ctx, m=me: ctx.get("target") == m,
        )
        c.grants_advantage(until=When.EONT, on=victim)


@power(
    "m5409a7",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m5409a7(c: Cast) -> None:
    """Appearance only -- a unique human form with no combat mechanic of
    its own."""


@power(
    "m5409a8",
    level=6,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d8", 4),
    trigger="an enemy moves into an adjacent square",
    on=Trigger(AdjacencyGained, _enemy_closed_on_me, "an enemy closes on it"),
)
def m5409a8(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.prone(on=foe)
    c.shift(1)
    c.move(3, at="fly")


@power(
    "m5409a9",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m5409a9(c: Cast) -> None:
    _recharge_and_fire(c, "m5409a4")


# ==========================================================================
# m5530
# ==========================================================================


@power(
    "m5530a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m5530a0(c: Cast) -> None:
    me = c.me
    c.aura(5, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def tick(ev: TurnStart) -> None:
        if ev.ghost or team(c.world, ev.actor) is not team(c.world, me):
            return
        if distance_between(c.world, me, ev.actor) <= 5:
            c.heal(3, on=ev.actor)

    c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m5530a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4),
)
def m5530a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m5530a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d8", 4, dtype=DamageType.POISON, kind=LIMITED),
)
def m5530a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()


@power(
    "m5530a3",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.ZONE],
    attack=Attack(vs=REF, printed=9),
)
def m5530a3(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)
    if c.first:
        c.zone(c.area(), difficult=True, until=When.ENCOUNTER, label=c.ref)


# ==========================================================================
# m5611
# ==========================================================================


@power(
    "m5611a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5611a0(c: Cast) -> None:
    me = c.me

    def slid(ev: TurnEnd) -> None:
        if ev.ghost or team(c.world, ev.actor) is team(c.world, me):
            return
        if distance_between(c.world, me, ev.actor) <= 2:
            c.slide(2, on=ev.actor)

    c.aura(2, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    c.watch(TurnEnd, slid, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m5611a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
)
def m5611a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.note(f"{c.ref}: at the end of the encounter the target saves or contracts this disease")


@power(
    "m5611a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d6", 2),
)
def m5611a2(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED))
        c.hit()


@power(
    "m5611a3",
    level=6,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it takes acid, cold, fire, lightning, or thunder damage",
    on=Trigger(
        DamageApplied,
        lambda world, me, ev: ev.target == me and ev.dtype in (
            DamageType.ACID, DamageType.COLD, DamageType.FIRE,
            DamageType.LIGHTNING, DamageType.THUNDER,
        ),
        "it takes acid, cold, fire, lightning or thunder damage",
    ),
)
def m5611a3(c: Cast) -> None:
    ev = c.trigger
    c.resist(5, getattr(ev, "dtype", DamageType.UNTYPED), on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m5935
# ==========================================================================


@power(
    "m5935a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5935a0(c: Cast) -> None:
    """"While bloodied" is re-asked every round rather than gated once --
    `c.vulnerable` and the save penalty take no `when=`, so each tick lasts
    only until the m5935's own next turn and is refreshed, or dropped, by
    the next one."""
    me = c.me

    def tick(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost or not c.bloodied(on=me):
            return
        for foe in c.within(5, of=me, side="enemy"):
            c.vulnerable(5, DamageType.PSYCHIC, until=When.EONT, on=foe)
            c.penalty("save", 2, on=foe, until=When.EONT)

    c.aura(5, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m5935a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 5),
)
def m5935a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.slide(1)


@power(
    "m5935a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC),
)
def m5935a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)
    else:
        c.slowed()


@power(
    "m5935a3",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("3d6", 4, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
)
def m5935a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.dazed()


@power(
    "m5935a4",
    level=6,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m5935a4(c: Cast) -> None:
    near = [w for w in c.within(3, of=c.me, side="any") if w != c.me]
    pick = c.choose(near, f"{c.ref}: swap with someone?", optional=True) if near else None
    if pick is not None:
        c.swap(pick)
        c.grants_advantage(until=When.EONT, on=pick)
    else:
        c.teleport(3)


# ==========================================================================
# m6011
# ==========================================================================


@power(
    "m6011a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 7),
)
def m6011a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()


@power(
    "m6011a1",
    level=6,
    usage=ENCOUNTER,
    uses=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    attack=Attack(vs=REF, printed=9),
)
def m6011a1(c: Cast) -> None:
    if not c.strike():
        return
    pick = c.roll("1d4")
    victim = c.target
    if pick == 1:
        c.ongoing(10, DamageType.FIRE)
    elif pick == 2:
        c.damage("2d6", 0, dtype=DamageType.COLD)
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)
    elif pick == 3:
        c.damage("2d6", 0, dtype=DamageType.RADIANT)
        c.condition(Condition.BLINDED, until=When.SAVE_ENDS)
    else:
        c.temp_hp(5, on=victim)
        c.condition(Condition.DAZED, until=When.SAVE_ENDS)


@power(
    "m6011a2",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 7, kind=LIMITED),
)
def m6011a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6011a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6011a3(c: Cast) -> None:
    _recharge_when_neighbor_bloodied(c, c.ref, radius=0)
    me = c.me
    c.shift(4, who=me)
    for foe in c.enemies():
        if c.adjacent_to(foe, me):
            c.gains_advantage(
                lambda ctx, f=foe: ctx.get("target") == f, until=When.EONT, on=me,
            )


@power(
    "m6011a4",
    level=6,
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=EACH_ENEMY,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m6011a4(c: Cast) -> None:
    c.blinded(until=When.EOTNT)


# ==========================================================================
# m6019
# ==========================================================================


@power(
    "m6019a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6019a0(c: Cast) -> None:
    c.bonus(
        "attack", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: c.terrain("water") and not c.is_kind("aquatic", on=ctx.get("target")),
    )


@power(
    "m6019a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5),
)
def m6019a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.slide(1)


@power(
    "m6019a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 5),
)
def m6019a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None and c.is_(Condition.SLOWED, on=victim):
            c.immobilized(until=When.SAVE_ENDS, on=victim)
        else:
            c.slowed(until=When.SAVE_ENDS, on=victim)


@power(
    "m6019a3",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("3d8", 5, kind=LIMITED, half_on_miss=True),
)
def m6019a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
    else:
        c.hit(half=True)


@power(
    "m6019a4",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=9),
    trigger="an enemy adjacent to it hits it with a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "an adjacent enemy hits it in melee"),
)
def m6019a4(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not c.strike(on=foe):
        return
    c.grab(on=foe)
    c.cannot_attack(on=foe, until=When.ENCOUNTER)
    me = c.me
    c.bonus(
        "attack", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx, f=foe, m=me: ctx.get("target") == f and f in c.grabbing(of=m),
    )


# ==========================================================================
# m6024
# ==========================================================================


@power(
    "m6024a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6024a0(c: Cast) -> None:
    _trap_bonus(c, 2)


@power(
    "m6024a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
)
def m6024a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m6024a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
)
def m6024a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6024a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 2, kind=LIMITED),
)
def m6024a3(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    pick = c.choose(["fire", "slide", "immobilize"], f"{c.ref}: which effect") or "fire"
    if pick == "fire":
        c.ongoing(5, DamageType.FIRE, on=victim)
    elif pick == "slide":
        c.slide(4, on=victim)
    else:
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim)


@power(
    "m6024a4",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d10", 3, kind=LIMITED, half_on_miss=True),
    dropped=("c.cannot_attack(opportunity=)",),
)
def m6024a4(c: Cast) -> None:
    """The ongoing damage and the drag land. "Cannot make opportunity
    attacks" is not a `Condition` this engine has, which is the gap
    `c.cannot_attack(opportunity=)` already names."""
    if not c.strike():
        c.hit(half=True)
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.ongoing(5, DamageType.UNTYPED, on=victim)
    if hold is None:
        return

    def drag(ev: TurnStart) -> None:
        if ev.actor != victim or ev.ghost:
            return
        if hold in c.world.effects.of(victim):
            c.slide(4, on=victim)

    c.watch(TurnStart, drag, until=When.SAVE_ENDS, on=victim, label=f"{c.ref} drag")


@power(
    "m6024a5",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m6024a5(c: Cast) -> None:
    c.shift(1)


@power(
    "m6024a6",
    level=6,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d10", 4, dtype=DamageType.FIRE),
    trigger="an enemy moves adjacent to it",
    on=Trigger(AdjacencyGained, _enemy_closed_on_me, "an enemy closes on it"),
)
def m6024a6(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.push(1, on=foe)


# ==========================================================================
# m6051
# ==========================================================================


@power(
    "m6051a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 5, dtype=DamageType.COLD),
)
def m6051a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m6051a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 2, dtype=DamageType.FIRE, kind=LIMITED),
)
def m6051a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2, anchor=c.origin)
        c.prone()


@power(
    "m6051a2",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4, kind=LIMITED),
)
def m6051a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    mod = Mod(what="attack", value=-2, kind="untyped", label=c.ref)
    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=c.ref,
        mods=[(victim, mod)], ongoing=(5, DamageType.POISON),
    )


@power(
    "m6051a3",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6051a3(c: Cast) -> None:
    c.widen_areas(1, on=c.me, until=When.EONT)


# ==========================================================================
# m6351
# ==========================================================================


@power(
    "m6351a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d8", 5, dtype=DamageType.LIGHTNING),
)
def m6351a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6351a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.ZONE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 4, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m6351a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)
    if not c.first:
        return
    area = c.area()
    squares_ = frozenset(area)
    me = c.me
    tolled_at: dict[int, int] = {}
    zone = c.zone(area, difficult=True, until=When.SONT, label=c.ref)

    def shock(who: int) -> None:
        if tolled_at.get(who) == c.world.round:
            return
        tolled_at[who] = c.world.round
        c.flat(5, dtype=DamageType.LIGHTNING, on=who)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone:
            shock(ev.actor)

    def began(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.in_squares(squares_, side="any"):
            shock(ev.actor)

    c.watch(ZoneEntered, entered, until=When.SONT, on=me, label=f"{c.ref} shock")
    c.watch(TurnStart, began, until=When.SONT, on=me, label=f"{c.ref} shock turn")


@power(
    "m6351a2",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d10", 5, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m6351a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m6351a3",
    level=6,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m6351a3(c: Cast) -> None:
    c.teleport(8)
    c.forbid("m6351a1", on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m6447
# ==========================================================================


@power(
    "m6447a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it falls",
    on=Trigger(Fell, about_me, "it is falling"),
)
def m6447a0(c: Cast) -> None:
    _soft_landing(c, 4)


@power(
    "m6447a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 6),
)
def m6447a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    if c.result is not None and c.result.advantage:
        c.damage("1d6", 0)
    c.immobilized(until=When.EONT)


@power(
    "m6447a2",
    level=6,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
)
def m6447a2(c: Cast) -> None:
    if c.strike():
        c.grants_advantage(until=When.SONT)


# ==========================================================================
# m6470
# ==========================================================================


def _m6470_shape(world: World, eid: int) -> str | None:
    for e in world.effects.of(eid):
        if e.label.startswith("m6470a4 "):
            return e.label.removeprefix("m6470a4 ")
    return None


@power(
    "m6470a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.silvered()", "c.regeneration(suspended_by=)"),
)
def m6470a0(c: Cast) -> None:
    """The regeneration plays. Suspending it for a turn needs two things that
    are both missing, so both are named.

    **It is not the same gap as `m5087a1`'s, and sharing one symbol would make
    neither able to go green.** Of the 16 rows carrying
    `c.regeneration(suspended_by=)`, 15 suspend on a **damage type** -- acid or
    fire, force or psychic, psychic -- which `DamageType` already holds and only
    the parameter is wanting. This one suspends on damage from a **silvered
    weapon**, which is a weapon material nothing in the engine models at all;
    `c.silvered()` is where 17 rows already wait for it. Giving the parameter to
    `suspended_by=` would report this row ready while it still had nowhere to ask
    the question."""
    c.regeneration(5, until=When.ENCOUNTER, on=c.me)


@power(
    "m6470a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 7),
    requires=lambda world, eid: _m6470_shape(world, eid) != "human",
    requires_text="usable only while in wolf or hybrid form",
)
def m6470a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.note(f"{c.ref}: the target saves at the end of the encounter or contracts this disease")


@power(
    "m6470a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 7, dtype=DamageType.RADIANT),
    requires=lambda world, eid: _m6470_shape(world, eid) != "wolf",
    requires_text="usable only while in human or hybrid form",
)
def m6470a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.EONT)


@power(
    "m6470a3",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d6", 4, dtype=DamageType.RADIANT, kind=LIMITED),
    requires=lambda world, eid: (
        _m6470_shape(world, eid) != "wolf"
        and bool(world.get(eid, Health) and world.get(eid, Health).bloodied)
    ),
    requires_text="usable only while bloodied and in human or hybrid form",
)
def m6470a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded()


@power(
    "m6470a4",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m6470a4(c: Cast) -> None:
    for eff in list(c.world.effects.of(c.me)):
        if eff.label.startswith("m6470a4 "):
            c.world.effects.end(eff, "changed shape")
    which = c.choose(["wolf", "human", "hybrid"], f"{c.ref}: which form") or "hybrid"
    c.form(until=When.ENCOUNTER, revert=None, label=f"m6470a4 {which}")


# ==========================================================================
# m6674
# ==========================================================================


@power(
    "m6674a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6674a0(c: Cast) -> None:
    me = c.me

    def tick(ev: TurnStart) -> None:
        if ev.ghost or team(c.world, ev.actor) is team(c.world, me):
            return
        if not c.is_(Condition.UNCONSCIOUS, on=ev.actor):
            return
        if distance_between(c.world, me, ev.actor) > 3:
            return
        if not c.spend_surge(on=ev.actor):
            c.flat(c.surge_value(on=ev.actor), on=ev.actor)

    c.aura(3, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} aura")


@power(
    "m6674a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d4", 6),
)
def m6674a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()


@power(
    "m6674a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("2d6", 7, dtype=DamageType.PSYCHIC),
)
def m6674a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized()


@power(
    "m6674a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m6674a3(c: Cast) -> None:
    c.basic(on=c.target)
    if c.last and len(c.targets) < 2:
        c.basic(on=c.target)


@power(
    "m6674a4",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.SLEEP],
    attack=Attack(vs=WILL, printed=9),
)
def m6674a4(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    if c.is_(Condition.DAZED, on=victim) or c.is_(Condition.IMMOBILIZED, on=victim):
        c.unconscious(until=When.SAVE_ENDS, on=victim)
        return

    def worsen(eff: Any) -> None:
        c.world.effects.end(eff, "it fell unconscious")
        c.unconscious(until=When.SAVE_ENDS, on=victim)

    c.condition(
        Condition.DAZED, Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim, escalate=worsen,
    )


@power(
    "m6674a5",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m6674a5(c: Cast) -> None:
    """Appearance only -- a disguise with an Insight check to see through it
    and no combat mechanic of its own."""


@power(
    "m6674a6",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m6674a6(c: Cast) -> None:
    """Removed from play is `Condition.REMOVED`, read back the way
    `level_05/controllers_sa.py`'s `m5653a2` already reads it."""
    me = c.me
    removed = c.condition(Condition.REMOVED, on=me, until=When.ENCOUNTER)

    def returns(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        if removed is not None and removed in c.world.effects.of(me):
            c.world.effects.end(removed, "it returns from the feywild")
        c.teleport(10)
        c.invisible(on=me, until=When.EOT)

    c.watch(TurnStart, returns, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} vanish")


# ==========================================================================
# m6675
# ==========================================================================


@power(
    "m6675a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6675a0(c: Cast) -> None:
    c.bonus(
        "crit_range", 2, until=When.ENCOUNTER, on=c.me,
        when=lambda ctx: c.bloodied(c.me),
    )


@power(
    "m6675a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 5),
)
def m6675a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m6675a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d8", 5, dtype=DamageType.NECROTIC),
)
def m6675a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("save", 2, until=When.SAVE_ENDS)


@power(
    "m6675a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(5),
    target=Target(
        side="ally", count=1, label="undead ally",
        kinds=frozenset({"undead"}),
    ),
    keywords=[Keyword.HEALING, Keyword.IMPLEMENT],
)
def m6675a3(c: Cast) -> None:
    """The type word is the target line now and the body's redirect came out.
    Positive rather than negative because an undead block always carries the
    word -- 756 of them do -- so nothing qualifying is refused. #401."""
    if c.target is not None:
        c.heal(10)


# ==========================================================================
# m891
# ==========================================================================


@power(
    "m891a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 5),
    requires=_not_already_grabbing,
    requires_text="can grab only one creature at a time",
)
def m891a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m891a1",
    level=6,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 5, kind=LIMITED),
    requires=_not_already_grabbing,
    requires_text="can grab only one creature at a time",
)
def m891a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m891a2",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ACID],
)
def m891a2(c: Cast) -> None:
    me = c.me

    def toll(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        for victim in c.grabbing():
            c.flat(c.roll("1d8") + 2, dtype=DamageType.ACID, on=victim)

    c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m891a3",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m891a3(c: Cast) -> None:
    c.threatens(4, on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m916
# ==========================================================================


@power(
    "m916a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 4),
)
def m916a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m916a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_CREATURE,
    attack=Attack(vs=REF, printed=9),
)
def m916a1(c: Cast) -> None:
    """"Affects only creatures in contact with the ground" is approximated
    as everyone the burst catches -- there is no flight check cheap enough
    to be worth the filter on a board this small."""
    if c.strike():
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


@power(
    "m916a2",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m916a2(c: Cast) -> None:
    """"Against targets adjacent to the secret door" is asked of the board
    for real: `c.scenery` finds one if the fixture is on it, and if it is
    not this simply never fires, which is a board limitation and not a gap."""
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(c.scenery("secret door", within=1, of=ctx.get("target"))),
    )
