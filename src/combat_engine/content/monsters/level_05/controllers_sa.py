"""Monster abilities, level 5, controllers.

Forty-four stat blocks, a hundred and seventy-five rows. `controllers.py`
holds the earlier sweep of this level and is not touched here; the split is
by *when* the work was done. Ten of the forty-four print no abilities at all
and so have nothing to decorate.

Conventions, all inherited from the level-1 to level-4 sweeps and from this
level's artillery, brutes, minions and misc files:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=10)`) and the damage line goes in the
  header as data, so an MM1 block can be rescaled to MM3 maths later;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it, whatever action the compendium's column claims;
* a card that prints no range at all is melee 1; a printed band such as
  "3/5" takes the shorter, normal number;
* a close burst or blast whose card names no target set takes **enemies**,
  except where the card says "creatures in the burst" outright;
* "can push/slide/knock prone" is read as the creature doing it -- there is
  no policy layer here to decline the beneficial half of its own attack;
* `half_on_miss=True` in the header is paired with `else: c.hit(half=True)`
  in the body every time; a bare `if c.strike(): c.hit()` would drop the
  Miss line the card prints.

Several shapes recur across this batch and have no ref of their own to live
in: a saving throw against "the most recent hold standing on it", a form
that a creature can take and shed, and a conjured companion with no stat
block. Each is written once, below, and called from every row that needs it.

A few clauses genuinely have no verb. `c.aftereffect()` (an automatic
consequence once a hold ends, no new roll) and `Damage(dtypes=)` (one roll of
two damage types) are both reused from elsewhere in the tree rather than
invented fresh, per `scripts/blocked.py --group`. The others are named at the
point they come up.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_01.artillery_sa import (
    _any_enemy_suffering,
    _recharge_when_bloodied,
)
from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES
from combat_engine.content.monsters.level_02.controllers_sa import (
    _let_it_swing,
    _let_it_swing_without_moving,
)
from combat_engine.content.monsters.level_02.lurkers_sa import (
    _has_been_hurt,
    _triggering_enemy,
    _twice,
)
from combat_engine.content.monsters.level_02.skirmishers_sa import _melee_only
from combat_engine.content.monsters.level_02.soldiers_sa import (
    _aquatic_edge,
    _missed_me_in_melee,
    _save_ends_on_me,
)
from combat_engine.content.monsters.level_03.brutes_sa import (
    _recharge_and_fire,
)
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_05.artillery_sa import _bloodied_edge
from combat_engine.content.monsters.level_05.brutes_sa import (
    _aura_penalty,
    _burn_and_backlash,
)
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
    Ranged,
    UpTo,
    Usage,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.components import Health
from combat_engine.engine.events import (
    AdjacencyLost,
    AttackDeclared,
    Bloodied,
    DamageApplied,
    Dropped,
    EffectApplied,
    Hit,
    Miss,
    PowerUsed,
    SavingThrow,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import distance_between, team
from combat_engine.engine.triggers import (
    Trigger,
    about_me,
    both,
    by_keyword,
    by_melee,
    by_ranged,
    either,
    targets_me,
)
from combat_engine.engine.types import Relation
from combat_engine.engine.zones import Zone

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _is_bloodied(world: World, eid: int) -> bool:
    health = world.get(eid, Health)
    return health is not None and health.bloodied


def _defs_vs_traps(c: Cast) -> None:
    """"+2 bonus to all defenses against traps." Three blocks print this
    verbatim; the attack context's `attacker` is the trap entity, which is
    the only place the word "trap" can be asked from."""
    for which in ALL_DEFENCES:
        c.bonus(
            which, 2, on=c.me, until=When.ENCOUNTER,
            when=lambda ctx: c.is_trap(ctx.get("attacker")),
        )


def _shake_off_latest_hold(c: Cast) -> None:
    """"It makes a saving throw against the triggering effect." The trigger
    names no effect of its own, so the most recent save-ends hold standing
    on it is what was just applied."""
    for eff in sorted(c.world.effects.of(c.me), key=lambda e: -e.id):
        if eff.when is When.SAVE_ENDS:
            c.world.effects.save(eff)
            return


def _grief_stricken(c: Cast, victim: int) -> None:
    """"Grief stricken (save ends). While so, vulnerable psychic 5 and
    dazed." Not a condition the engine has a name for, so its two
    components are laid as two holds rather than one -- an approximation of
    the card's single saving throw, noted rather than hidden."""
    c.condition(Condition.DAZED, until=When.SAVE_ENDS, on=victim)
    c.vulnerable(5, DamageType.PSYCHIC, until=When.SAVE_ENDS, on=victim)


def _in_shape(prefix: str, word: str) -> Any:
    """A printed Requirement naming one of a shapechanger's forms. A
    creature that has not changed shape yet passes every gate, the way
    `level_04/brutes.py`'s version of this does."""

    def gate(world: World, eid: int) -> bool:
        for effect in world.effects.of(eid):
            if effect.label.startswith(prefix):
                return effect.label.endswith(word)
        return True

    return gate


def _ally_hit_in_melee(world: World, me: int, ev: Hit) -> bool:
    """"An ally hits with a melee attack." `ally_within` has no radius-free
    form, and this trigger prints no distance at all."""
    attacker = getattr(ev, "attacker", None)
    if attacker is None or attacker == me:
        return False
    if team(world, attacker) is not team(world, me):
        return False
    return by_melee(world, me, ev)


# ==========================================================================
# m1505
# ==========================================================================


@power(
    "m1505a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 4),
)
def m1505a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1505a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 2, kind=LIMITED),
    dropped=("c.conceal_in()",),
)
def m1505a1(c: Cast) -> None:
    """"All creatures have concealment against it" makes the target's own
    attacks the hard ones to land -- the opposite direction from `c.conceal`,
    which gives concealment *to* a creature rather than making its attacks
    treat others as concealed. No verb says that half; the immobilize is
    exact."""
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


# ==========================================================================
# m3134
# ==========================================================================


@power(
    "m3134a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d10", 4),
)
def m3134a0(c: Cast) -> None:
    """"requires greatspear" is not a gate -- `Gear` is empty on every
    monster. The crit line replaces the header's damage rather than adding
    to it, so it is paid flat past the engine's own max-on-crit rule."""
    if c.strike(plus=_bloodied_edge(c)):
        if c.crit:
            c.flat(c.roll("1d6") + 14)
        else:
            c.hit()
        victim = c.target
        near = [f for f in c.enemies() if f != victim and c.adjacent_to(f, c.me)]
        if near:
            c.use_power("m3134a1", on=near[0])


@power(
    "m3134a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=8),
    damage=Damage("1d6", 3),
)
def m3134a1(c: Cast) -> None:
    if c.strike(plus=_bloodied_edge(c)):
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m3134a2",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d6", 3, dtype=DamageType.POISON, kind=LIMITED),
)
def m3134a2(c: Cast) -> None:
    if c.strike(plus=_bloodied_edge(c)):
        c.hit()


@power(
    "m3134a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=-2),
    trigger="an ally hits with a melee attack",
    on=Trigger(Hit, _ally_hit_in_melee, "an ally hits with a melee attack"),
)
def m3134a3(c: Cast) -> None:
    if c.strike():
        c.ongoing(5, DamageType.POISON)


@power(
    "m3134a4",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3134a4(c: Cast) -> None:
    c.bonus(
        "attack", 1, on=c.me, kind="racial", until=When.ENCOUNTER,
        when=lambda _ctx: c.bloodied(on=c.me),
    )


@power(
    "m3134a5",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.light()",),
)
def m3134a5(c: Cast) -> None:
    """Extinguishing every light source in the encounter has no verb at all
    -- `c.light()` is the reused symbol for the whole gap -- so nothing in
    this row works yet."""


# ==========================================================================
# m3219
# ==========================================================================


@power(
    "m3219a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d4", 2),
)
def m3219a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.slide(2)


@power(
    "m3219a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d6", 4, dtype=DamageType.NECROTIC),
)
def m3219a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            for which in ALL_DEFENCES:
                c.penalty(which, 2, on=victim, until=When.EONT)


@power(
    "m3219a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m3219a2(c: Cast) -> None:
    """"Two basic attacks" is `c.basic` called twice -- the generic basic
    attack, not either named at-will row -- following `_twice`'s shape."""
    c.basic(on=c.target)
    if c.last and len(c.targets) < 2:
        c.basic(on=c.target)


@power(
    "m3219a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 4, kind=LIMITED),
    dropped=("c.regeneration(when=)",),
)
def m3219a3(c: Cast) -> None:
    """Regeneration while a target is held by this power has no conditional
    form -- `c.regeneration` runs for a flat duration, not gated on a hold
    standing -- so that half is dropped. The hold itself is exact: one
    effect carries the burn and the immobilize, which is what makes one save
    end both."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            c.condition(
                Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim,
                ongoing=(5, DamageType.UNTYPED),
            )


@power(
    "m3219a4",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("2d6", 4, kind=LIMITED),
)
def m3219a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.bloodied():
            c.dazed(until=When.EONT)


@power(
    "m3219a5",
    level=5,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("query.dead_allies()",),
)
def m3219a5(c: Cast) -> None:
    """The shift is exact. Finding "one destroyed undead minion" to raise
    again has no query -- the board has no way to name a corpse -- so that
    half is dropped."""
    for mate in c.allies():
        if c.is_kind("undead", on=mate) and distance_between(c.world, c.me, mate) <= 10:
            c.shift(2, who=mate)


@power(
    "m3219a6",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m3219a6(c: Cast) -> None:
    c.insubstantial(on=c.me, until=When.EONT)
    c.phasing(on=c.me, until=When.EONT)


# ==========================================================================
# m3272
# ==========================================================================


def _m3272_beast_form(world: World, eid: int) -> bool:
    return any(e.label == "m3272a4 beast" for e in world.effects.of(eid))


@power(
    "m3272a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 3),
    requires=_m3272_beast_form,
    requires_text="usable only while in beast form",
)
def m3272a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3272a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 6),
    requires=lambda world, eid: not _m3272_beast_form(world, eid),
    requires_text="usable only while not in beast form",
)
def m3272a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.slide(2)


@power(
    "m3272a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 3),
    requires=_m3272_beast_form,
    requires_text="usable only while in beast form",
)
def m3272a2(c: Cast) -> None:
    _twice(c, "m3272a0")


@power(
    "m3272a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=9),
    requires=lambda world, eid: not _m3272_beast_form(world, eid),
    requires_text="usable only while not in beast form",
)
def m3272a3(c: Cast) -> None:
    if c.strike():
        victim = c.target
        if victim is None:
            return
        near = [w for w in c.within(1, of=victim, side="any") if w != victim]
        if near:
            c.basic(who=victim, on=near[0])


@power(
    "m3272a4",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING, Keyword.POLYMORPH],
)
def m3272a4(c: Cast) -> None:
    c.form(until=When.ENCOUNTER, revert=None, label="m3272a4 beast")
    c.regeneration(5, until=When.ENCOUNTER, on=c.me)
    c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER)


@power(
    "m3272a5",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_is_bloodied,
    requires_text="usable only while bloodied",
)
def m3272a5(c: Cast) -> None:
    c.bonus("speed", 2, on=c.me, until=When.ENCOUNTER)
    c.bonus(AC, 1, on=c.me, until=When.ENCOUNTER)
    c.bonus(REF, 1, on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m3291
# ==========================================================================


@power(
    "m3291a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 2),
)
def m3291a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            c.penalty(FORT, 2, on=victim, until=When.EONT)
            c.penalty(WILL, 2, on=victim, until=When.EONT)


@power(
    "m3291a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d6", 3, dtype=DamageType.NECROTIC),
)
def m3291a1(c: Cast) -> None:
    """Two separate dice, not one roll of two types: the necrotic half is
    the header and the cold half is paid on top."""
    if c.strike():
        c.hit()
        c.damage("1d6", 0, dtype=DamageType.COLD)


@power(
    "m3291a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d6", 3, dtype=DamageType.NECROTIC),
)
def m3291a2(c: Cast) -> None:
    """One effect carrying the slow and the penalty, so one saving throw
    ends both."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is None:
            return
        from combat_engine.engine import Mod

        c.world.effects.apply(
            victim, c.me, When.SAVE_ENDS,
            label=f"{c.ref} slow",
            conditions=(Condition.SLOWED,),
            mods=[(victim, Mod(what="attack", value=-2, kind="untyped", label=c.ref))],
        )


@power(
    "m3291a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("1d6", 3, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m3291a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            c.flee(c.speed_of(victim), on=victim)


@power(
    "m3291a4",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3291a4(c: Cast) -> None:
    c.reroll_attack(keep="new")


@power(
    "m3291a5",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.ignores_difficult(when=)",),
)
def m3291a5(c: Cast) -> None:
    """The whole of this row is a narrowing nothing can express: rough ground is
    ignored **when it shifts** and not when it walks.

    **It used to say `c.ignores_difficult(kind="shift")`, which did nothing.**
    That parameter names *which sort of terrain* -- its own docstring says "the
    labels are the ones the map and `c.zone(difficult=...)` give their squares",
    and those are `ice`, `rubble`, `water` and `web`. No square is ever labelled
    `shift`, so the waiver was laid against a terrain that does not exist and the
    row reported finished while being inert. `audit.py` credited it because
    laying the effect is an `EffectApplied` either way.

    Twenty-seven other rows wait on the same gap under this symbol, which is the
    general form: thirteen of them are about shifting and six about something
    else entirely -- not wearing heavy armour, standing beside a spirit
    companion, running.
    """


# ==========================================================================
# m3439
# ==========================================================================


@power(
    "m3439a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 2, dtype=DamageType.PSYCHIC),
)
def m3439a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3439a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("3d6", 2, dtype=DamageType.PSYCHIC),
)
def m3439a1(c: Cast) -> None:
    """The target's own choice is asked the way a chooser answers any other
    offered decision in this tree -- `c.choose` with no owner implied."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is None:
            return
        mate = next(
            (f for f in c.enemies() if f != victim and distance_between(c.world, victim, f) <= 5),
            None,
        )
        if mate is not None and c.choose(
            ["reduce the damage by 5", "take the full damage"],
            f"{c.ref}: reduce the blow?",
        ) == "reduce the damage by 5":
            c.reduce(5)
            c.flat(c.roll("2d6"), on=mate)


@power(
    "m3439a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
)
def m3439a2(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    hold = c.effect(f"{c.ref} compelled", until=When.SAVE_ENDS, on=victim)
    if hold is None or victim is None:
        return

    def spill(ev: TurnStart) -> None:
        if ev.actor != victim or ev.ghost:
            return
        if hold not in c.world.effects.of(victim):
            return
        for mate in c.within(1, of=victim, side="ally"):
            if mate != victim:
                c.flat(5, dtype=DamageType.PSYCHIC, on=mate)

    c.watch(TurnStart, spill, until=When.SAVE_ENDS, on=victim, label=f"{c.ref} spill")


@power(
    "m3439a3",
    level=5,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    trigger="an enemy misses it with a melee or ranged attack",
    on=Trigger(
        Miss, both(targets_me, either(by_melee, by_ranged)), "it is missed at range or in melee"
    ),
    dropped=("c.redirect(ev=)",),
)
def m3439a3(c: Cast) -> None:
    """No damage line at all -- the whole Hit is the slide. Rerolling *that
    same* miss and retargeting it at somebody else has no verb -- `c.redirect`
    turns an attack aside before it resolves, and this one already has."""
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.slide(3, on=foe)


@power(
    "m3439a4",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    requires=_any_enemy_suffering(Condition.HELPLESS, Condition.UNCONSCIOUS),
    requires_text="targets a helpless or unconscious creature",
)
def m3439a4(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.insubstantial(on=c.me, until=When.EONT)
    killed = c.coup_de_grace(on=victim)
    if killed:
        health = c.world.get(c.me, Health)
        if health is not None:
            c.heal(health.max_hp // 2, on=c.me)


@power(
    "m3439a5",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3439a5(c: Cast) -> None:
    c.threatens(2, on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m3556
# ==========================================================================


@power(
    "m3556a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d4", 4),
)
def m3556a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3556a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d4", 4),
)
def m3556a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)
        c.grab()


@power(
    "m3556a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.leash()",),
)
def m3556a2(c: Cast) -> None:
    """"Up to two tentacles at a time" releases the oldest catch when a
    third lands. "Can't move more than 2 squares from a held creature" has
    no tether verb and is the dropped half."""
    me = c.me

    def capped(ev: Any) -> None:
        if ev.kind_ is not Relation.GRABBED_BY or ev.source != me:
            return
        held = c.grabbing()
        if len(held) > 2:
            c.world.relations.clear(
                Relation.GRABBED_BY, me, held[0], "a third catch took its place"
            )

    from combat_engine.engine.events import RelationSet

    c.watch(RelationSet, capped, until=When.ENCOUNTER, on=me, label=f"{c.ref} cap")


@power(
    "m3556a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m3556a3(c: Cast) -> None:
    total = 0
    for victim in c.grabbing():
        total += c.flat(5, on=victim)
    if total:
        c.heal(total // 2, on=c.me)


# ==========================================================================
# m4152
# ==========================================================================


@power(
    "m4152a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 4, dtype=DamageType.COLD),
)
def m4152a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m4152a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 4),
)
def m4152a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4152a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 4),
)
def m4152a2(c: Cast) -> None:
    """The bite is this use's first target, the shift happens once, and the
    pair of claws lands on whoever else was offered -- or on the same
    creature again if the chooser spread nothing."""
    if c.strike():
        c.hit()
    if c.first:
        c.shift(2)
    if c.last and len(c.targets) < 2 and c.strike():
        c.hit()


@power(
    "m4152a3",
    level=5,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    trigger="an enemy misses it with a melee or close attack",
    on=Trigger(Miss, both(targets_me, by_melee), "a melee attack misses it"),
    attack=Attack(vs=FORT, printed=7),
    damage=Damage("1d6", 4),
)
def m4152a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)


@power(
    "m4152a4",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 5, kind=LIMITED),
    requires=_any_enemy_suffering(Condition.SLOWED, Condition.RESTRAINED),
    requires_text="targets slowed or restrained creatures",
)
def m4152a4(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.push(3)
        c.prone()


@power(
    "m4152a5",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d6", 4, dtype=DamageType.COLD, kind=LIMITED, half_on_miss=True),
    dropped=("c.aftereffect()",),
)
def m4152a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m4152a6",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m4152a6(c: Cast) -> None:
    _recharge_and_fire(c, "m4152a5")


@power(
    "m4152a7",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=7),
    dropped=("c.aftereffect()",),
)
def m4152a7(c: Cast) -> None:
    if c.strike():
        c.stunned(until=When.EONT)


# ==========================================================================
# m4190
# ==========================================================================


@power(
    "m4190a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 4),
)
def m4190a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", 0, dtype=DamageType.FORCE)
        c.slide(1)


@power(
    "m4190a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 3),
)
def m4190a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4190a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m4190a2(c: Cast) -> None:
    _twice(c, "m4190a1")


@power(
    "m4190a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=9),
)
def m4190a3(c: Cast) -> None:
    if c.strike():
        c.slide(1)
        c.grants_advantage(until=When.EONT)


@power(
    "m4190a4",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d10", 2, dtype=DamageType.FORCE, kind=LIMITED),
)
def m4190a4(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m4209
# ==========================================================================


def _attacked_with_keyword(word: Keyword) -> Any:
    def check(world: World, me: int, ev: Any) -> bool:
        if getattr(ev, "target", None) != me:
            return False
        return by_keyword(word)(world, me, ev)

    return check


@power(
    "m4209a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d6", 3, dtype=DamageType.LIGHTNING),
)
def m4209a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m4209a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("3d6", 3, dtype=DamageType.LIGHTNING),
    trigger="it is attacked with a lightning power",
    on=Trigger(
        AttackDeclared, _attacked_with_keyword(Keyword.LIGHTNING), "it is attacked with lightning"
    ),
)
def m4209a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4209a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.ZONE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d6", 3, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m4209a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    if c.first:
        from combat_engine.engine.events import ZoneEntered

        area = c.area()
        zone = c.zone(area, difficult=True, until=When.SONT, label=c.ref)

        def toll(ev: ZoneEntered) -> None:
            if ev.zone == zone:
                c.flat(5, dtype=DamageType.LIGHTNING, on=ev.actor)

        c.watch(ZoneEntered, toll, until=When.SONT, on=c.me, label=f"{c.ref} shock")


@power(
    "m4209a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m4209a3(c: Cast) -> None:
    c.shift(1)


@power(
    "m4209a4",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4209a4(c: Cast) -> None:
    _defs_vs_traps(c)


# ==========================================================================
# m4767
# ==========================================================================


@power(
    "m4767a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 3),
)
def m4767a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None and _secondary(c, 9, FORT, victim):
            c.condition(
                Condition.WEAKENED, until=When.SAVE_ENDS, on=victim,
                ongoing=(5, DamageType.POISON),
            )


@power(
    "m4767a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 4),
)
def m4767a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target

        def worsen(eff: Any) -> None:
            c.world.effects.end(eff, "it could no longer move at all")
            c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim)

        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, escalate=worsen)


@power(
    "m4767a2",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 3, kind=LIMITED),
)
def m4767a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        from combat_engine.content.monsters.level_05.artillery_sa import _one_save_for_both

        _one_save_for_both(c, "attack", 2, 2, DamageType.POISON)


@power(
    "m4767a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("3d6", 4, dtype=DamageType.POISON, kind=LIMITED),
    dropped=("c.ongoing(stacks=)",),
)
def m4767a3(c: Cast) -> None:
    """The base burn is exact. Stacking a *second*, bigger burn on top of an
    existing one -- rather than the larger-wins rule `c.ongoing` always
    applies -- has no override, so that half, and the save penalty that
    rides with it, is dropped."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m4767a4",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 15),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 4, dtype=DamageType.POISON, kind=LIMITED),
)
def m4767a4(c: Cast) -> None:
    if c.strike():
        c.hit()
    if c.first:
        c.summon("m2830", at=c.origin)


# ==========================================================================
# m5134
# ==========================================================================


@power(
    "m5134a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5134a0(c: Cast) -> None:
    me = c.me
    c.aura(2, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    for mate in c.allies():
        c.bonus(
            "damage", 5, on=mate, until=When.ENCOUNTER,
            when=lambda _ctx, m=mate: distance_between(c.world, me, m) <= 2,
        )


@power(
    "m5134a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5134a1(c: Cast) -> None:
    _aquatic_edge(c)


@power(
    "m5134a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d10", 7),
)
def m5134a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m5134a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    requires=_any_enemy_suffering(Condition.DAZED),
    requires_text="targets a dazed creature",
    dropped=("c.lose_surge()",),
)
def m5134a3(c: Cast) -> None:
    if c.strike():
        c.weakened(until=When.EONT)


# ==========================================================================
# m5312
# ==========================================================================


@power(
    "m5312a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m5312a0(c: Cast) -> None:
    me = c.me
    c.aura(2, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    for who in [*c.allies(), *c.enemies()]:
        for which in ALL_DEFENCES:
            c.penalty(
                which, 1, on=who, until=When.ENCOUNTER,
                when=lambda _ctx, w=who: (
                    distance_between(c.world, me, w) <= 2
                    and not c.is_kind("undead", on=w)
                ),
            )


@power(
    "m5312a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d6", 3, dtype=DamageType.NECROTIC),
)
def m5312a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            _grief_stricken(c, victim)


@power(
    "m5312a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("1d8", 4, dtype=DamageType.PSYCHIC),
)
def m5312a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m5312a3",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("2d8", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m5312a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            _grief_stricken(c, victim)


# ==========================================================================
# m5384
# ==========================================================================


@power(
    "m5384a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5384a0(c: Cast) -> None:
    for which in ALL_DEFENCES:
        _aura_penalty(c, 3, which, 1)


@power(
    "m5384a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("2d6", 4),
)
def m5384a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5384a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 5, dtype=DamageType.FORCE),
)
def m5384a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m5384a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("4d6", 4, kind=LIMITED),
)
def m5384a3(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    if c.bloodied(on=victim):
        _burn_and_backlash(c, 5, DamageType.PSYCHIC, victim)
        return
    hold = c.effect(f"{c.ref} marked", until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return

    def spent(ev: PowerUsed) -> None:
        if ev.actor != victim or hold not in c.world.effects.of(victim):
            return
        row = get(ev.power or "")
        if row is not None and row.usage in (Usage.DAILY, Usage.ENCOUNTER):
            c.flat(5, dtype=DamageType.PSYCHIC, on=victim)

    c.watch(PowerUsed, spent, until=When.SAVE_ENDS, on=victim, label=f"{c.ref} backlash")


@power(
    "m5384a4",
    level=5,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m5384a4(c: Cast) -> None:
    c.move(5, at="fly")


# ==========================================================================
# m5602
# ==========================================================================


@power(
    "m5602a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 4, dtype=DamageType.NECROTIC),
)
def m5602a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5602a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 2, dtype=DamageType.POISON),
)
def m5602a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(
            Condition.SLOWED, Condition.WEAKENED, until=When.SAVE_ENDS,
            ongoing=(5, DamageType.NECROTIC),
        )


@power(
    "m5602a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("4d6", 5, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m5602a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.EONT)
    if c.first:
        mate = next(iter(c.allies()), None)
        if mate is not None:
            c.temp_hp(5, on=mate)


@power(
    "m5602a3",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.CONJURATION, Keyword.IMPLEMENT, Keyword.NECROTIC, Keyword.POISON],
    dropped=("c.conjure(side=)", "c.conjuration_hp()", "Damage(dtypes=)"),
)
def m5602a3(c: Cast) -> None:
    """Conjures the viper, retiring an older one first -- "can have only one
    at a time." Allies passing through its square while enemies cannot, and the
    ten-damage destruction that pays ten back to m5602, have no verb. The
    opportunity bite when an enemy leaves its side is real.

    **"She can also move the viper up to 6 squares" is `speed=`**, which
    `c.conjure` already takes -- its docstring says so in as many words. An
    earlier version of this row marked it `dropped=("c.move_zone()",)`, which
    was wrong twice: that verb exists too, and nothing here needed it."""
    me = c.me
    for old in c.conjurations():
        c.world.despawn(old)
    viper = c.conjure(until=When.ENCOUNTER, sustain=None, solid=True,
                      speed=6, label=c.ref)
    if not viper:
        return

    def bit(ev: AdjacencyLost) -> None:
        if ev.other != viper or team(c.world, ev.actor) is team(c.world, me):
            return
        if _secondary(c, 9, REF, ev.actor):
            c.damage("1d10", 4, dtype=DamageType.NECROTIC, on=ev.actor)

    c.watch(AdjacencyLost, bit, until=When.ENCOUNTER, on=me, label=f"{c.ref} bite")

    def gone(ev: Dropped) -> None:
        if ev.actor == me:
            c.world.despawn(viper)

    c.watch(Dropped, gone, until=When.ENCOUNTER, on=me, label=f"{c.ref} falls")


@power(
    "m5602a4",
    level=5,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d10", 4, dtype=DamageType.NECROTIC),
    dropped=("Damage(dtypes=)",),
)
def m5602a4(c: Cast) -> None:
    """Measured from the viper, via `from_=`, not from m5602."""
    viper = next(iter(c.conjurations()), None)
    if viper is None:
        return
    if c.strike(from_=viper):
        c.hit()


# ==========================================================================
# m5653
# ==========================================================================


@power(
    "m5653a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5653a0(c: Cast) -> None:
    """"Can make Thievery checks against any creature within 10 squares it is
    aware of" is a skill-check range extension with nothing else printed, and
    no board rolls Thievery mid-fight."""


@power(
    "m5653a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m5653a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5653a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=8),
)
def m5653a2(c: Cast) -> None:
    """One hold, read from both ends: the bonus it grants the dominated
    target and m5653's own `REMOVED` both check whether this same effect is
    still standing, so the one saving throw that ends it ends all three
    printed clauses together."""
    victim = c.target
    if victim is None or not c.strike():
        return
    hold = c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return
    me = c.me
    c.bonus(
        "attack", 2, on=victim, until=When.ENCOUNTER,
        when=lambda _ctx: hold in c.world.effects.of(victim),
    )
    c.bonus(
        "damage", 2, on=victim, until=When.ENCOUNTER,
        when=lambda _ctx: hold in c.world.effects.of(victim),
    )
    removed = c.condition(Condition.REMOVED, on=me, until=When.ENCOUNTER)

    def returns(ev: TurnStart) -> None:
        if ev.actor != victim or ev.ghost or hold in c.world.effects.of(victim):
            return
        if removed is not None and removed in c.world.effects.of(me):
            c.world.effects.end(removed, "the dominated creature broke free")
        c.teleport(5, who=me)

    c.watch(TurnStart, returns, until=When.ENCOUNTER, on=me, label=f"{c.ref} vanish")


@power(
    "m5653a3",
    level=5,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5653a3(c: Cast) -> None:
    c.teleport(3)


@power(
    "m5653a4",
    level=5,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5653a4(c: Cast) -> None:
    """A single square turned to grease: difficult terrain, and anybody but
    m5653 who willingly enters it falls. `ZoneEntered` is exactly that
    moment."""
    from combat_engine.engine.events import ZoneEntered

    zone = c.zone({c.here}, difficult=True, until=When.ENCOUNTER, label=c.ref)

    def tripped(ev: ZoneEntered) -> None:
        if ev.zone == zone and ev.actor != c.me:
            c.prone(on=ev.actor)

    c.watch(ZoneEntered, tripped, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} grease")


# ==========================================================================
# m5672
# ==========================================================================


@power(
    "m5672a0",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5672a0(c: Cast) -> None:
    me = c.me
    acted: set[int] = set()

    def mark(ev: TurnStart) -> None:
        if not ev.ghost:
            acted.add(ev.actor)

    c.watch(TurnStart, mark, until=When.ENCOUNTER, on=me, label=f"{c.ref} roll")
    c.bonus(
        "damage", 0, on=me, until=When.ENCOUNTER, dice="1d10",
        when=lambda ctx: ctx.get("target") not in acted,
    )


@power(
    "m5672a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5672a1(c: Cast) -> None:
    me = c.me

    def earned(ev: Miss) -> None:
        if not _missed_me_in_melee(c.world, me, ev):
            return
        foe = getattr(ev, "attacker", None)
        if foe is not None:
            c.gains_advantage(
                until=When.EONT, on=me,
                when=lambda ctx, f=foe: ctx.get("target") == f,
            )

    c.watch(Miss, earned, until=When.ENCOUNTER, on=me, label=f"{c.ref} opening")


@power(
    "m5672a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m5672a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5672a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.POLYMORPH],
    attack=Attack(vs=FORT, printed=8),
)
def m5672a3(c: Cast) -> None:
    """"Cannot use powers" is read as `Condition.SHAPED` -- "cannot take
    standard actions" -- the one card in the table that means close to the
    printed line."""
    victim = c.target
    if victim is not None and any(
        e.label == c.ref for e in c.world.effects.of(victim)
    ):
        other = next((f for f in c.enemies() if f != victim), None)
        if other is None:
            return
        victim = other
    if victim is None or not c.strike(on=victim):
        return
    hold = c.condition(
        Condition.SHAPED, Condition.SLOWED, until=When.EONT, on=victim,
    )
    if hold is None:
        return

    def broken(ev: DamageApplied) -> None:
        if ev.target == victim and hold in c.world.effects.of(victim):
            c.world.effects.end(hold, "the frog took damage")

    c.watch(DamageApplied, broken, until=When.EONT, on=victim, label=f"{c.ref} frog")


@power(
    "m5672a4",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("1d8", 4, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
)
def m5672a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)
    else:
        c.hit(half=True)


# ==========================================================================
# m5836
# ==========================================================================


@power(
    "m5836a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6),
)
def m5836a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5836a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d8", 5, dtype=DamageType.FIRE, half_on_miss=True),
)
def m5836a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
    else:
        c.hit(half=True)


@power(
    "m5836a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_CREATURE,
    attack=Attack(vs=FORT, printed=8),
    dropped=("c.zone(obscured=)",),
)
def m5836a2(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DAZED, until=When.SAVE_ENDS, ongoing=(10, DamageType.UNTYPED))
    if c.first:
        c.zone(c.area(), until=When.ENCOUNTER, label=c.ref)


@power(
    "m5836a3",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_CREATURE,
    attack=Attack(vs=REF, printed=8),
)
def m5836a3(c: Cast) -> None:
    if c.strike():
        c.prone()
        c.vulnerable(5, DamageType.FIRE, until=When.ENCOUNTER)


@power(
    "m5836a4",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m5836a4(c: Cast) -> None:
    c.move(c.speed_of())


# ==========================================================================
# m5856
# ==========================================================================


@power(
    "m5856a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5856a0(c: Cast) -> None:
    c.regeneration(4, until=When.ENCOUNTER, on=c.me, while_bloodied=True)


@power(
    "m5856a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 8),
)
def m5856a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m5856a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("2d8", 4, dtype=DamageType.PSYCHIC),
)
def m5856a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)
    else:
        c.slowed(until=When.EONT)


@power(
    "m5856a3",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=8),
)
def m5856a3(c: Cast) -> None:
    if c.strike():
        c.push(3)
        c.immobilized(until=When.SAVE_ENDS)
    else:
        c.push(1)


# ==========================================================================
# m5946
# ==========================================================================


@power(
    "m5946a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 6, dtype=DamageType.COLD),
)
def m5946a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5946a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("2d6", 3, dtype=DamageType.COLD),
)
def m5946a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None and c.is_(Condition.SLOWED, on=victim):
            c.immobilized(until=When.EONT)
        else:
            c.slowed(until=When.EONT)


@power(
    "m5946a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("3d8", 6, dtype=DamageType.COLD, kind=LIMITED),
)
def m5946a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


# ==========================================================================
# m5968
# ==========================================================================


@power(
    "m5968a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 9),
)
def m5968a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5968a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 9),
)
def m5968a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5968a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 6),
)
def m5968a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    pool = [c.me] + [a for a in c.allies() if c.adjacent_to(a, c.me)]
    pick = c.choose(pool, f"{c.ref}: who gets the +1?") or c.me
    c.bonus(AC, 1, on=pick, kind="power", until=When.EONT)


@power(
    "m5968a3",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=8),
)
def m5968a3(c: Cast) -> None:
    if c.strike():
        c.dazed(until=When.EONT)
        choice = c.choose(["knock prone", "slide 5"], f"{c.ref}: prone or slide?") or "knock prone"
        if choice == "knock prone":
            c.prone()
        else:
            c.slide(5)


@power(
    "m5968a4",
    level=5,
    usage=ENCOUNTER,
    uses=2,
    once_per_round=True,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m5968a4(c: Cast) -> None:
    c.surge(bonus=c.roll("1d6") + 5)


# ==========================================================================
# m6118
# ==========================================================================


@power(
    "m6118a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6118a0(c: Cast) -> None:
    me = c.me
    c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)

    def toll(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or team(c.world, ev.actor) is team(c.world, me):
            return
        if c.bloodied(on=ev.actor) and distance_between(c.world, me, ev.actor) <= 1:
            c.flat(5, on=ev.actor)

    c.watch(TurnStart, toll, until=When.ENCOUNTER, on=me, label=f"{c.ref} toll")


@power(
    "m6118a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 2),
)
def m6118a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d10", 0, dtype=DamageType.NECROTIC)
        c.slowed(until=When.EONT)


@power(
    "m6118a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
)
def m6118a2(c: Cast) -> None:
    _twice(c, "m6118a1")


@power(
    "m6118a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("2d8", 4, dtype=DamageType.PSYCHIC),
)
def m6118a3(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.grants_advantage(until=When.SAVE_ENDS, to="team", on=victim)
    if hold is None:
        return
    tag = str(hold)

    def failed(ev: SavingThrow) -> None:
        if ev.actor == victim and ev.against == tag and not ev.saved:
            c.dazed(until=When.EONT, on=victim)

    c.watch(SavingThrow, failed, until=When.SAVE_ENDS, on=victim, once=True, label=f"{c.ref} daze")


@power(
    "m6118a4",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.THUNDER],
    attack=Attack(vs=WILL, printed=8),
    damage=Damage("2d10", 4, dtype=DamageType.THUNDER, kind=LIMITED, half_on_miss=True),
    requires=_has_been_hurt,
    requires_text="must have taken damage during the encounter",
)
def m6118a4(c: Cast) -> None:
    _recharge_when_bloodied(c)
    if c.strike():
        c.hit()
        c.push(2)
    else:
        c.hit(half=True)
        c.push(1)


@power(
    "m6118a5",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m6118a5(c: Cast) -> None:
    c.extra_action(STANDARD, on=c.me)


# ==========================================================================
# m6152
# ==========================================================================


@power(
    "m6152a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d6", 2),
)
def m6152a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m6152a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=ONE_ALLY,
)
def m6152a1(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    c.shift(1, who=mate)
    if c.adjacent_to(mate, c.me):
        foe = next((f for f in c.enemies() if c.adjacent_to(f, mate)), None)
        if foe is not None:
            c.basic(who=mate, on=foe)


# ==========================================================================
# m6344
# ==========================================================================


@power(
    "m6344a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.hide(auto=)",),
)
def m6344a0(c: Cast) -> None:
    """"If it has partial concealment, it can make a Stealth check to
    become hidden" is an active attempt a trait has no action to spend on;
    nothing here arms a standing permission to try, so nothing works yet."""


@power(
    "m6344a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4),
)
def m6344a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6344a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 6),
)
def m6344a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m6344a3",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("1d10", 3, kind=LIMITED, half_on_miss=True),
)
def m6344a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(
            Condition.IMMOBILIZED, until=When.SAVE_ENDS,
            ongoing=(5, DamageType.POISON),
        )
    else:
        c.hit(half=True)
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m6344a4",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
    dropped=("Target.creature_kind",),
)
def m6344a4(c: Cast) -> None:
    """"One nonminion plant ally or two minion plant allies" is approximated
    as one ally; `Target` has no plant-and-minion-count filter."""
    mate = c.target
    if mate is None:
        return
    _let_it_swing(c, mate)


@power(
    "m6344a5",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m6344a5(c: Cast) -> None:
    c.summon("m6341", at=c.here)


# ==========================================================================
# m6473
# ==========================================================================


@power(
    "m6473a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d4", 3),
)
def m6473a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m6473a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("1d8", 5, dtype=DamageType.PSYCHIC),
)
def m6473a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m6473a2",
    level=5,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=9),
    dropped=("c.no_walk(toward=)",),
)
def m6473a2(c: Cast) -> None:
    """The grant is exact. Barring the target from closing the distance
    specifically has no directional movement verb, so that half is dropped."""
    if c.strike():
        c.grants_advantage(until=When.EONT)


@power(
    "m6473a3",
    level=5,
    usage=ENCOUNTER,
    uses=2,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m6473a3(c: Cast) -> None:
    mate = c.target
    c.surge(bonus=3)
    if mate is not None:
        c.slide(1, on=mate)


# ==========================================================================
# m6574
# ==========================================================================

_M6574_SHAPE = "m6574a7 "


def _m6574_bat_form(world: World, eid: int) -> bool:
    return any(
        e.label.startswith(_M6574_SHAPE) and e.label.endswith("bat")
        for e in world.effects.of(eid)
    )


@power(
    "m6574a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m6574a0(c: Cast) -> None:
    me = c.me
    c.aura(2, label=f"{c.ref} aura", until=When.ENCOUNTER, on=me)
    for mate in c.allies():
        c.bonus(
            "damage", 5, on=mate, until=When.ENCOUNTER, dtype=DamageType.NECROTIC,
            when=lambda _ctx, m=mate: (
                c.is_kind("undead", on=m) and distance_between(c.world, me, m) <= 2
            ),
        )


@power(
    "m6574a1",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.RADIANT],
)
def m6574a1(c: Cast) -> None:
    me = c.me

    def burn(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        if c.terrain("sunlight"):
            c.flat(5, dtype=DamageType.RADIANT, on=me)

    c.watch(TurnStart, burn, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6574a2",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    out_of_combat=True,
)
def m6574a2(c: Cast) -> None:
    """An extended rest is never taken mid-encounter."""


@power(
    "m6574a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d8", 4, dtype=DamageType.NECROTIC),
)
def m6574a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6574a4",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    requires=lambda world, eid: not _m6574_bat_form(world, eid),
    requires_text="usable only while not in bat form",
)
def m6574a4(c: Cast) -> None:
    choice = c.choose(
        ["claw twice", "claw once, and let an undead ally swing"], f"{c.ref}: pick"
    ) or "claw twice"
    if choice == "claw twice":
        _twice(c, "m6574a3")
    else:
        c.use_power("m6574a3")
        mate = next(
            (
                a
                for a in c.allies()
                if c.is_kind("undead", on=a) and distance_between(c.world, c.me, a) <= 5
            ),
            None,
        )
        if mate is not None:
            _let_it_swing_without_moving(c, mate)


@power(
    "m6574a5",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("2d10", 2),
    requires=_any_enemy_suffering(
        Condition.DAZED, Condition.DOMINATED, Condition.STUNNED, Condition.UNCONSCIOUS,
    ),
    requires_text="targets a dazed, dominated, stunned, or unconscious creature",
)
def m6574a5(c: Cast) -> None:
    if c.strike():
        dealt = c.hit()
        c.heal(dealt, on=c.me)


@power(
    "m6574a6",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=8),
)
def m6574a6(c: Cast) -> None:
    """"A creature that can see m6574" is approximated as the caster's own
    sight of the target, which is usually reciprocal."""
    victim = c.target
    if victim is None or not c.can_see(victim):
        return
    if c.strike(on=victim):
        choice = c.choose(
            ["dominated", "take damage instead"], f"{c.ref}: dominated or hurt?"
        ) or "dominated"
        if choice == "dominated":
            c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)
        else:
            c.damage("2d8", 6, dtype=DamageType.PSYCHIC)


@power(
    "m6574a7",
    level=5,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m6574a7(c: Cast) -> None:
    me = c.me
    for eff in list(c.world.effects.of(me)):
        if eff.label.startswith(_M6574_SHAPE):
            c.world.effects.end(eff, "changed shape")
    which = c.choose(["bat", "mist"], f"{c.ref}: which shape") or "bat"
    shape = c.form(
        modes={"fly": 10}, until=When.ENCOUNTER, revert=MINOR, label=f"{_M6574_SHAPE}{which}"
    )
    if which == "mist":
        for held in (
            c.insubstantial(on=me, until=When.ENCOUNTER),
            c.cannot_attack(on=me, until=When.ENCOUNTER),
        ):
            if held is not None:
                shape.on_end.append(lambda h=held: c.world.effects.end(h, "retook its true form"))
    c.shift(10)


# ==========================================================================
# m821
# ==========================================================================


@power(
    "m821a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d6", 5),
)
def m821a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m821a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("2d8", 8, dtype=DamageType.NECROTIC),
)
def m821a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.penalty(AC, 2, until=When.EONT)


@power(
    "m821a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m821a2(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    c.bonus("attack", 5, on=mate, until=When.EONT)
    c.heal(10, on=mate)


@power(
    "m821a3",
    level=5,
    usage=AT_WILL,
    action=FREE,
    reach=Melee(1),
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m821a3(c: Cast) -> None:
    near = [f for f in c.enemies() if c.adjacent(to=f)]
    if near:
        c.basic(on=near[0])
    else:
        foe = next(iter(c.enemies()), None)
        if foe is not None:
            c.basic(on=foe, ranged=True)


@power(
    "m821a4",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m821a4(c: Cast) -> None:
    c.bonus(
        "attack", 2, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _melee_only(ctx) and c.bloodied(on=c.me),
    )
    c.bonus(
        "damage", 3, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _melee_only(ctx) and c.bloodied(on=c.me),
    )


# ==========================================================================
# m829
# ==========================================================================


@power(
    "m829a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=7),
    damage=Damage("1d8", 3),
)
def m829a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m829a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=7),
    damage=Damage("1d8", 5),
)
def m829a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        mate = next(iter(c.allies()), None)
        if mate is not None and victim is not None:
            c.bonus(
                "attack", 2, on=mate, kind="power", until=When.ENCOUNTER, once=True,
                when=lambda ctx, v=victim: ctx.get("target") == v,
            )


@power(
    "m829a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=WILL, printed=7),
)
def m829a2(c: Cast) -> None:
    if c.strike():
        victim = c.target
        if victim is not None:
            c.flee(c.speed_of(victim) + 1, on=victim)


@power(
    "m829a3",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
)
def m829a3(c: Cast) -> None:
    pick = c.choose(["attack", "a saving throw"], f"{c.ref}: boost which?") or "attack"
    if pick == "attack":
        c.bonus("attack", 1, on=c.me, until=When.EONT, once=True)
    else:
        c.bonus("save", 1, on=c.me, until=When.EONT, once=True)


@power(
    "m829a4",
    level=5,
    usage=ENCOUNTER,
    uses=2,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m829a4(c: Cast) -> None:
    c.surge(bonus=c.roll("1d6"))


# ==========================================================================
# m893
# ==========================================================================


@power(
    "m893a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 1),
)
def m893a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m893a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d10", 4, dtype=DamageType.FIRE),
)
def m893a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m893a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 15),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m893a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m893a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 15),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d8", 0, dtype=DamageType.POISON, kind=LIMITED),
)
def m893a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m893a4",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("1d8", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m893a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, Condition.DAZED, until=When.SAVE_ENDS)


# ==========================================================================
# m894
# ==========================================================================


@power(
    "m894a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 1),
)
def m894a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m894a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d10", 4, dtype=DamageType.FIRE),
)
def m894a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m894a2",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(3),
    keywords=[Keyword.FIRE],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 2, dtype=DamageType.FIRE, kind=LIMITED),
)
def m894a2(c: Cast) -> None:
    """"Up to three creatures within 5 squares of each other, wielding melee
    weapons" is approximated as three targets; neither narrowing has a
    `Target` filter to carry it, the same simplification `m914a2` already
    made for "three different targets". The save-ends pair is one effect."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            from combat_engine.engine import Mod

            c.world.effects.apply(
                victim, c.me, When.SAVE_ENDS,
                label=f"{c.ref} burn",
                mods=[(victim, Mod(what="attack", value=-2, kind="untyped", label=c.ref))],
                ongoing=(5, DamageType.FIRE),
            )


@power(
    "m894a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 15),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m894a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m894a4",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 15),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d8", 0, dtype=DamageType.POISON, kind=LIMITED),
)
def m894a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m894a5",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 3),
)
def m894a5(c: Cast) -> None:
    """The standard-action sustain-and-reattack is exact; the printed extra
    "as a move action, move the zone" option is not wired in -- it would be
    a second, independent action on a row that has only the one."""
    area = c.area()

    def attack_all() -> None:
        for foe in c.in_squares(area, side="enemy"):
            if c.strike(on=foe):
                c.hit(on=foe)
                c.condition(Condition.DAZED, until=When.SAVE_ENDS, on=foe)

    if c.first:
        zone = c.zone(area, until=When.SUSTAIN, sustain=STANDARD, label=c.ref)
        body = c.world.get(zone, Zone)
        if body is not None:
            c.on_sustain(body.effect, attack_all)
    attack_all()


# ==========================================================================
# m896
# ==========================================================================


@power(
    "m896a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d10", 1),
)
def m896a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m896a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d10", 4, dtype=DamageType.FIRE),
)
def m896a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m896a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 15),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("1d8", 4, dtype=DamageType.FIRE, kind=LIMITED),
)
def m896a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m896a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 15),
    target=EACH_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d8", 0, dtype=DamageType.POISON, kind=LIMITED),
)
def m896a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m896a4",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("1d8", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m896a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, Condition.DAZED, until=When.SAVE_ENDS)


# ==========================================================================
# m918
# ==========================================================================


@power(
    "m918a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 2),
)
def m918a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m918a1",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("2d10", 5, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m918a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m918a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("2d6", 5, dtype=DamageType.FORCE, kind=LIMITED),
)
def m918a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m918a3",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d8", 5, dtype=DamageType.FORCE, kind=LIMITED, half_on_miss=True),
)
def m918a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()
    else:
        c.hit(half=True)


@power(
    "m918a4",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it suffers an effect that a save can end",
    on=Trigger(EffectApplied, _save_ends_on_me, "an effect a save can end lands on it"),
)
def m918a4(c: Cast) -> None:
    _shake_off_latest_hold(c)


# ==========================================================================
# m932
# ==========================================================================


@power(
    "m932a0",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m932a0(c: Cast) -> None:
    _defs_vs_traps(c)


@power(
    "m932a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("3d4", 4),
)
def m932a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m932a2",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d8", 4),
)
def m932a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m932a3",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=8),
)
def m932a3(c: Cast) -> None:
    """"Roll a d4" picks the element -- a die the card rolls, not a choice
    anybody makes."""
    if not c.strike():
        return
    pick = c.roll("1d4")
    if pick == 1:
        c.damage("1d8", 4, dtype=DamageType.FIRE)
        c.ongoing(5, DamageType.FIRE)
    elif pick == 2:
        c.damage("2d6", 4, dtype=DamageType.COLD)
        c.immobilized(until=When.SAVE_ENDS)
    elif pick == 3:
        c.damage("1d8", 4, dtype=DamageType.LIGHTNING)
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.damage("1d6", 4, dtype=DamageType.POISON)
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.POISON))


@power(
    "m932a4",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m932a4(c: Cast) -> None:
    c.shift(1)


@power(
    "m932a5",
    level=5,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.COLD, Keyword.FIRE, Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=8),
    damage=Damage("2d6", 5, kind=LIMITED),
    dropped=("Damage(dtypes=)",),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops"),
)
def m932a5(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m932a6",
    level=5,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
    trigger="it takes damage",
    on=Trigger(DamageApplied, targets_me, "it takes damage"),
)
def m932a6(c: Cast) -> None:
    c.teleport(c.roll("1d6"))


# ==========================================================================
# m938
# ==========================================================================


@power(
    "m938a0",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 5),
)
def m938a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m938a1",
    level=5,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.POISON],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d6", 2, dtype=DamageType.POISON),
)
def m938a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m938a2",
    level=5,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.IMPLEMENT],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("1d6", 2, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m938a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m938a3",
    level=5,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 3),
)
def m938a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target

        def worsen(_eff: Any) -> None:
            c.flat(c.roll("1d6"), on=victim)

        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, escalate=worsen)


@power(
    "m938a4",
    level=5,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m938a4(c: Cast) -> None:
    c.shift(1)


@power(
    "m938a5",
    level=5,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m938a5(c: Cast) -> None:
    _defs_vs_traps(c)
