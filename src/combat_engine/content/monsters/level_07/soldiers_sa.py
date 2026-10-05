"""Monster abilities, level 7, soldiers -- second sweep.

55 stat blocks. `level_07/soldiers.py` holds the earlier sweep of this level
and already wrote 13 of them in full (m108, m177, m249, m2890, m3002, m3048,
m3102, m324, m364, m4854, m494, m6369, m717) -- their brief carries no
undeclared row at all, so none of them appear below.

Conventions, the same ones the rest of the tree settled:

* numbers load from `game.db`; the attack line is `Attack(vs=AC, printed=N)`
  exactly as printed, and the damage line is header data so an MM1 block can
  be rescaled to MM3 maths later;
* a trait costs no action, has no target, and arms once at the start of the
  fight, whatever the compendium's action column claims;
* a printed Requirement naming the creature's own kit is not a gate (#366);
* "+N vs AC, or +N+1 while bloodied" on an attack line is the **caster's**
  own bloodied state, not the target's -- `_own_edge` below reads it, and it
  is a different question from the target-bloodied edge the artillery sweep
  settled;
* a handful of these stat blocks print a fragment of another identity beside
  their own ref in running prose: m1806 and m1078/m1489 print a bare race
  word ("gnoll", a leaked `r1`) where a flavour sentence named a race; m961's
  and m884's own cards misprint "m177" and "m5808" where they mean
  themselves; m5600's own card misprints "r3"; m5598's own card prints one
  proper name outright. None of those words is used below -- every row is
  written against its own ref, which is what "it" means throughout.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES, _saves_off_prone
from combat_engine.content.monsters.level_02.lurkers_sa import (
    _reach_kind,
    _recharge_when_using,
    _triggering_enemy,
    _twice,
)
from combat_engine.content.monsters.level_02.soldiers_sa import (
    _armed,
    _free_square_beside,
    _is_attack,
    _recharge_when_bloodied,
    _ref_of,
    _square_of,
)
from combat_engine.content.monsters.level_03.soldiers_sa import (
    _adjacent_foe_looks_away,
    _marked_shifts,
)
from combat_engine.content.monsters.level_04.brutes_sa import _change_shape, _in_shapes
from combat_engine.content.monsters.level_07.soldiers import (
    _aura,
    _hands_free,
    _has_hold,
    _holding,
)
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
    OPPORTUNITY,
    PERSONAL,
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
    Effect,
    Health,
    Keyword,
    Melee,
    Mod,
    Powers,
    Ranged,
    Relation,
    Size,
    Stats,
    Target,
    UpTo,
    Usage,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.dsl import use
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    ConditionEnded,
    DamageApplied,
    DamageRolled,
    Dropped,
    EffectApplied,
    Hit,
    Miss,
    Moved,
    MoveStart,
    PowerResolved,
    PowerUsed,
    SavingThrow,
    SurgeSpent,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.grid import distance as square_distance
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import distance_between, enemies, has_combat_advantage, is_, team
from combat_engine.engine.triggers import Trigger, about_me, by_melee

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------

#: "Immobilized, stunned, or unconscious" -- the common three-condition
#: target narrowing this role reaches for more than once.
_PINNED_THREE = (Condition.IMMOBILIZED, Condition.STUNNED, Condition.UNCONSCIOUS)

#: One more than the tuple above -- "dazed, stunned, unconscious, or
#: helpless", m1760a2's own four.
_HELPLESS_FOUR = (Condition.DAZED, Condition.STUNNED, Condition.UNCONSCIOUS, Condition.HELPLESS)


def _own_edge(c: Cast) -> int:
    """"+N vs AC, or +N+1 while bloodied" -- the caster's own state, read at
    the roll, not the target's."""
    return 1 if c.bloodied(c.me) else 0


def _bloodied_racial_edge(c: Cast, attack_bonus: int, damage_bonus: int = 0) -> None:
    """"A [race] gains a +1 racial bonus..." printed against a leaked race
    ref rather than a flavour word; written against the creature itself."""
    me = c.me
    c.bonus(
        "attack", attack_bonus, on=me, until=When.ENCOUNTER, kind="racial",
        when=lambda _ctx: c.bloodied(me),
    )
    if damage_bonus:
        c.bonus(
            "damage", damage_bonus, on=me, until=When.ENCOUNTER, kind="racial",
            when=lambda _ctx: c.bloodied(me),
        )


def _adjacent_enemy_shifts(world: World, me: int, ev: MoveStart) -> bool:
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or team(world, actor) is team(world, me):
        return False
    if getattr(ev, "kind_", "") != "shift":
        return False
    return distance_between(world, me, actor) <= 1


def _marked_by_me_shifts(world: World, me: int, ev: MoveStart) -> bool:
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or not world.relations.holds(Relation.MARKED_BY, me, actor):
        return False
    return getattr(ev, "kind_", "") == "shift"


def _marked_by_me_looks_away(world: World, me: int, ev: PowerUsed) -> bool:
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or not world.relations.holds(Relation.MARKED_BY, me, actor):
        return False
    if not _is_attack(ev.power):
        return False
    return me not in getattr(ev, "targets", ())


def _marked_within_looks_away(radius: int):  # noqa: ANN202
    def gate(world: World, me: int, ev: PowerUsed) -> bool:
        actor = getattr(ev, "actor", None)
        if actor is None or actor == me:
            return False
        if not world.relations.holds(Relation.MARKED_BY, me, actor):
            return False
        if distance_between(world, me, actor) > radius:
            return False
        if not _is_attack(ev.power):
            return False
        return me not in getattr(ev, "targets", ())

    return gate


def _marked_within_moves_away(radius: int):  # noqa: ANN202
    def gate(world: World, me: int, ev: MoveStart) -> bool:
        actor = getattr(ev, "actor", None)
        if actor is None or actor == me:
            return False
        if not world.relations.holds(Relation.MARKED_BY, me, actor):
            return False
        if getattr(ev, "kind_", "") in ("push", "pull", "slide"):
            return False
        return distance_between(world, me, actor) <= radius

    return gate


def _marks_and_burns_for_looking_away(c: Cast, victim: int, bonus: int, radius: int) -> None:
    """"Marks the target until the end of the encounter or until it uses this
    power again, and while marked the target takes N radiant damage whenever
    it ends its turn without attacking it." One designation at a time, and
    the punish is read off `PowerUsed` -- which carries the whole target list
    -- rather than `AttackDeclared`, which announces once per target and
    would double-count a burst."""
    me, ref = c.me, c.ref
    for eff in list(c.world.effects.live.values()):
        if eff.source == me and eff.label.startswith(ref):
            c.world.effects.end(eff, "it marked again")
    swung = [False]

    def noticed(ev: PowerUsed) -> None:
        p = get(ev.power)
        if ev.actor == victim and p is not None and p.is_attack and me in ev.targets:
            swung[0] = True

    def ignored(ev: TurnEnd) -> None:
        if ev.actor != victim or ev.ghost:
            return
        if not swung[0]:
            c.flat(bonus, dtype=DamageType.RADIANT, on=victim)
        swung[0] = False

    hold = c.mark(until=When.ENCOUNTER, on=victim)
    seen = c.watch(PowerUsed, noticed, until=When.ENCOUNTER, on=me, label=f"{ref} watched")
    burn = c.watch(TurnEnd, ignored, until=When.ENCOUNTER, on=me, label=f"{ref} burn")
    if hold is not None:
        hold.on_end.append(lambda: c.world.effects.end(seen, "the mark ended"))
        hold.on_end.append(lambda: c.world.effects.end(burn, "the mark ended"))


def _halves_a_hit_onto_me(c: Cast, radius: int) -> bool:
    """"Half the attack's damage is negated, and it takes the other half."
    The event's own amount is halved in place -- an interrupt is the window
    in which it is still a proposal -- and the same number lands here."""
    ev = c.trigger
    whole = max(0, getattr(ev, "amount", 0))
    if whole <= 0:
        return False
    share = whole // 2
    ev.amount = share
    c.flat(share, dtype=ev.dtype, on=c.me)
    return True


def _ally_near_is_struck(radius: int):  # noqa: ANN202
    def gate(world: World, me: int, ev: DamageRolled) -> bool:
        who = ev.target
        if who == me or team(world, who) is not team(world, me):
            return False
        p = get(ev.detail or "")
        return p is not None and p.is_attack and distance_between(world, me, who) <= radius

    return gate


# ==========================================================================
# m1042
# ==========================================================================


@power(
    "m1042a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d6", 5, dtype=DamageType.NECROTIC),
)
def m1042a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m1042a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=12), damage=Damage("2d6", 5, dtype=DamageType.NECROTIC),
)
def m1042a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None or not c.marked(on=victim, by=c.me):
        return
    had = c.spend_surge(on=victim)
    c.immobilized(until=When.SAVE_ENDS, on=victim)
    if not had:
        body = c.world.get(victim, Health)
        if body is not None:
            c.flat(body.max_hp // 4, dtype=DamageType.NECROTIC, on=victim)
    c.heal(5, on=c.me)


@power(
    "m1042a2", level=7, usage=Usage.RECHARGE, recharge=6, action=MINOR,
    reach=Ranged(20), target=NO_TARGET, keywords=[Keyword.NECROTIC],
    todo=("spec.monster_ref()",),
)
def m1042a2(c: Cast) -> None:
    """Raising destroyed undead as new creatures names a creature with no
    ref in this tree -- the gap `spec.monster_ref()` already waits on."""


# ==========================================================================
# m1072
# ==========================================================================


@power(
    "m1072a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=13), damage=Damage("2d6", 5),
)
def m1072a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m1072a1", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1072a1(c: Cast) -> None:
    """The gore rides along with its rider's charge, so it is a watch rather
    than a chooseable row of its own."""
    me = c.me

    def gore(ev: AttackDeclared) -> None:
        rider = c.rider()
        if rider is None or ev.attacker != rider or not getattr(ev, "charge", False):
            return
        if team(c.world, rider) is not team(c.world, me):
            return
        stats = c.world.get(rider, Stats)
        if stats is None or stats.level < 7:
            return
        c.use_power("m1072a0", on=ev.target)

    c.watch(AttackDeclared, gore, until=When.ENCOUNTER, on=me, label="m1072a1")


# ==========================================================================
# m1078
# ==========================================================================


@power(
    "m1078a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("1d12", 5),
)
def m1078a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m1078a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=UpTo(2), keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("2d6", 5),
)
def m1078a1(c: Cast) -> None:
    if c.strike():
        c.hit()


def _adjacent_enemy_bloodied(world: World, me: int, ev: Bloodied) -> bool:
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or team(world, actor) is team(world, me):
        return False
    return distance_between(world, me, actor) <= 1


@power(
    "m1078a2", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d12", 9, kind=LIMITED),
)
def m1078a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.mark(until=When.EONT, on=victim)
    hold = c.slowed(until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return

    def slowed_by_this(ctx: dict) -> bool:
        return ctx.get("target") == victim and hold in c.world.effects.of(victim)

    # Both are "power bonus" on the card, in those words.
    for who in (c.me, *c.allies()):
        c.bonus("attack", 1, on=who, kind="power", until=When.ENCOUNTER,
                when=slowed_by_this)
        c.bonus("damage", 4, on=who, kind="power", until=When.ENCOUNTER,
                when=slowed_by_this)


@power(
    "m1078a3", level=7, usage=ENCOUNTER, action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL, target=NO_TARGET,
    trigger="an adjacent enemy becomes bloodied",
    on=Trigger(Bloodied, _adjacent_enemy_bloodied, "an adjacent enemy becomes bloodied"),
)
def m1078a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m1078a2")
    c.use_power("m1078a2", on=foe)


@power(
    "m1078a4", level=7, usage=ENCOUNTER, action=MINOR, reach=CloseBlast(3),
    target=EACH_ENEMY, keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d6", 5, dtype=DamageType.ACID, kind=LIMITED),
)
def m1078a4(c: Cast) -> None:
    if c.strike(plus=_own_edge(c)):
        c.hit()


@power("m1078a5", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1078a5(c: Cast) -> None:
    _bloodied_racial_edge(c, 1, 2)


# ==========================================================================
# m1158
# ==========================================================================


@power(
    "m1158a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13), damage=Damage("2d8", 5),
)
def m1158a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1158a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=REF, printed=13), damage=Damage("1d8", 5),
)
def m1158a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)
        c.grants_advantage(until=When.SAVE_ENDS)


@power(
    "m1158a2", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1),
    target=Target(side="enemy", count=1, label="one creature granting it combat advantage"),
    attack=Attack(vs=FORT, printed=13), damage=Damage("1d8", 5, kind=LIMITED),
    dropped=("Target.relation",),
)
def m1158a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not has_combat_advantage(c.world, c.me, victim):
        return
    if c.strike():
        c.hit()
        c.stunned(until=When.SAVE_ENDS)


# ==========================================================================
# m1489
# ==========================================================================


@power(
    "m1489a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d10", 6),
)
def m1489a0(c: Cast) -> None:
    if c.strike(plus=_own_edge(c)):
        c.hit()
        c.mark()


@power(
    "m1489a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d10", 6),
)
def m1489a1(c: Cast) -> None:
    victim = c.target
    if c.strike(plus=_own_edge(c)):
        c.hit()
    c.shift(1)
    second = next((f for f in c.enemies() if f != victim and c.distance(f) <= 1), None)
    if second is not None:
        c.basic(on=second)


@power(
    "m1489a2", level=7, usage=ENCOUNTER, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("2d10", 6, kind=LIMITED),
)
def m1489a2(c: Cast) -> None:
    if c.strike(plus=_own_edge(c)):
        c.hit()
        c.ongoing(5)


@power(
    "m1489a3", level=7, usage=ENCOUNTER, action=MINOR, reach=CloseBlast(3),
    target=EACH_OTHER, keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d6", 6, dtype=DamageType.POISON, kind=LIMITED),
)
def m1489a3(c: Cast) -> None:
    if c.strike(plus=_own_edge(c)):
        c.hit()


@power("m1489a4", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1489a4(c: Cast) -> None:
    _bloodied_racial_edge(c, 1)


# ==========================================================================
# m1745
# ==========================================================================


@power(
    "m1745a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d8", 4),
)
def m1745a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1745a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d8", 4),
)
def m1745a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=c.ref,
        conditions=(Condition.RESTRAINED,), ongoing=(5, DamageType.UNTYPED),
    )
    if hold is None:
        return
    for other in ("m1745a0", "m1745a1"):
        bar = c.forbid(other, on=c.me, until=When.SAVE_ENDS)
        if bar is not None:
            hold.on_end.append(lambda b=bar: c.world.effects.end(b, "no longer restrained"))


@power(
    "m1745a2", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=CloseBlast(3), target=EACH_ENEMY, keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d6", 2, dtype=DamageType.POISON, kind=LIMITED),
)
def m1745a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


# ==========================================================================
# m1760
# ==========================================================================


@power(
    "m1760a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=13), damage=Damage("2d6", 4),
)
def m1760a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1760a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(4),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=13), damage=Damage("1d6", 4),
)
def m1760a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m1760a2", level=7, usage=AT_WILL, action=MINOR, reach=Melee(4),
    target=Target(side="enemy", count=1, label="dazed, stunned, unconscious, or helpless creature"),
    attack=Attack(vs=FORT, printed=12), dropped=("Target.condition",),
)
def m1760a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not any(c.is_(cnd, victim) for cnd in _HELPLESS_FOUR):
        return
    if c.strike():
        spot = _free_square_beside(c, c.me)
        if spot is not None:
            c.pull(c.distance(victim), on=victim, to=spot)


@power(
    "m1760a3", level=7, usage=ENCOUNTER, action=STANDARD, reach=CloseBurst(1),
    target=EACH_OTHER, keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("1d6", 1, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m1760a3(c: Cast) -> None:
    victim = c.target
    if victim is None or c.is_kind("demon", on=victim):
        return
    if c.strike():
        c.hit()
        mods = [(victim, Mod(what=d, value=-2, kind="untyped", label=c.ref)) for d in ALL_DEFENCES]
        c.world.effects.apply(victim, c.me, When.SAVE_ENDS, label=c.ref, mods=mods)


# ==========================================================================
# m1798
# ==========================================================================


@power(
    "m1798a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d8", 5),
)
def m1798a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1798a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=FORT, printed=12), damage=Damage("1d8", 5),
)
def m1798a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2, on=c.me)
        victim = c.target
        if victim is not None:
            spot = _free_square_beside(c, c.me)
            if spot is not None:
                c.slide(2, on=victim, to=spot)


def _hit_with_m1798a1(world: World, me: int, ev: Hit) -> bool:
    return getattr(ev, "attacker", None) == me and getattr(ev, "power", "") == "m1798a1"


@power(
    "m1798a2", level=7, usage=ENCOUNTER, action=FREE, reach=PERSONAL, target=NO_TARGET,
    trigger="it hits a target with its m1798a1 ability",
    on=Trigger(Hit, _hit_with_m1798a1, "it hits with m1798a1"),
)
def m1798a2(c: Cast) -> None:
    """The extra two squares, on top of the two m1798a1 already moved -- the
    hit has already happened by the time this fires, so adding a second
    slide is what keeps both numbers true rather than rewriting the first."""
    victim = getattr(c.trigger, "target", None)
    c.slide(2, on=c.me)
    if victim is not None:
        spot = _free_square_beside(c, c.me)
        if spot is not None:
            c.slide(2, on=victim, to=spot)


# ==========================================================================
# m1806
# ==========================================================================


@power(
    "m1806a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d12", 5),
)
def m1806a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.bloodied(c.me):
            c.flat(2)
        c.mark()


@power(
    "m1806a1", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=CloseBurst(1), target=EACH_ENEMY, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("1d12", 5, kind=LIMITED),
)
def m1806a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.bloodied(c.me):
            c.flat(2)
        c.mark()


@power("m1806a2", level=7, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=NO_TARGET)
def m1806a2(c: Cast) -> None:
    c.shift(3)
    for foe in list(c.world.relations.targets(Relation.MARKED_BY, c.me)):
        c.pull(3, on=foe)


@power("m1806a3", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1806a3(c: Cast) -> None:
    me = c.me

    def flanked_by_my_side(ctx: dict) -> bool:
        victim = ctx.get("target")
        if victim is None or ctx.get("ranged"):
            return False
        return sum(1 for a in c.allies() if a != me and c.adjacent_to(a, victim)) >= 2

    c.bonus("damage", 5, on=me, until=When.ENCOUNTER, when=flanked_by_my_side)


# ==========================================================================
# m1981
# ==========================================================================


@power(
    "m1981a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=REF, printed=14), damage=Damage("2d6", 4),
)
def m1981a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m1981a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=Target(side="enemy", count=1, label="creature grabbed by it"),
    dropped=("Target.relation",),
)
def m1981a1(c: Cast) -> None:
    """The printed line is two damage fragments the extraction never
    resolved; the clear half of it -- automatic damage, no attack roll --
    is what is written."""
    held = _holding(c)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is not None:
        c.flat(c.roll("2d6") + 4, on=victim)


@power(
    "m1981a2", level=7, usage=Usage.RECHARGE, recharge=6, action=MINOR,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=12), damage=Damage("2d8", 6, dtype=DamageType.NECROTIC),
)
def m1981a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.spend_surge(on=c.target)


@power(
    "m1981a3", level=7, usage=ENCOUNTER, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
    todo=("c.split()",),
)
def m1981a3(c: Cast) -> None:
    """Splitting into two independent creatures that share one initiative
    count has no verb; nothing here plays."""


# ==========================================================================
# m2014
# ==========================================================================


@power(
    "m2014a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=12), damage=Damage("2d4", 6, dtype=DamageType.NECROTIC),
)
def m2014a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.EONT)
    c.shift(2)


@power(
    "m2014a1", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.NECROTIC],
)
def m2014a1(c: Cast) -> None:
    """Passing through every creature's space on one run and striking each
    enemy entered is modelled as a line toward the far end of its move; a
    board where an ally stands between it and an enemy would make the
    printed "whose space it enters" differ from "under the line", which is
    the approximation here."""
    me = c.me
    before = _square_of(c, me)
    c.phasing(until=When.EOT, on=me)
    c.move(10, who=me)
    after = _square_of(c, me)
    if before is None or after is None:
        return
    bonus = c.world.scaling.trim(12, c.level)
    seen: set[int] = set()
    for sq in c.line(before, after):
        occ = c.world.grid.occupant(sq)
        if occ is None or occ == me or occ not in c.enemies() or occ in seen:
            continue
        seen.add(occ)
        if c.attack(bonus, FORT, on=occ):
            c.damage("2d4", 6, dtype=DamageType.NECROTIC, on=occ)
            c.dazed(until=When.SAVE_ENDS, on=occ)
        else:
            c.half_damage("2d4", 6, dtype=DamageType.NECROTIC, on=occ)


@power(
    "m2014a2", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET,
    dropped=("c.save(any_duration=)",),
)
def m2014a2(c: Cast) -> None:
    """"Moonlight or starlight" is a terrain tag read live, the same shape as
    an aquatic trait -- false on an ordinary board, true on the one the line
    is for. The second half -- letting a save end the weakened condition
    m2014a0 lays, which is a fixed-duration hold and not a save-ends one --
    cannot be asked: `c.save` only ever acts on a `When.SAVE_ENDS` effect."""
    me = c.me
    c.bonus(
        "damage", 0, dice="1d4", on=me, until=When.ENCOUNTER, dtype=DamageType.NECROTIC,
        when=lambda ctx: not ctx.get("ranged")
        and (c.terrain("moonlight") or c.terrain("starlight")),
    )


@power("m2014a3", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m2014a3(c: Cast) -> None:
    """The ritual half -- that raising the corpse does not destroy the
    spawn -- changes nothing the engine tracks and is left as flavour."""
    me = c.me
    waiting: list = []

    def slain(ev: Dropped) -> None:
        if ev.source != me or not c.is_kind("humanoid", on=ev.actor):
            return
        sq = _square_of(c, ev.actor)
        if sq is not None:
            waiting.append(sq)

    def rise(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me or not waiting:
            return
        for sq in waiting:
            c.summon("m2014", at=sq)
        waiting.clear()

    c.watch(Dropped, slain, until=When.ENCOUNTER, on=me, label="m2014a3 slain")
    c.watch(TurnStart, rise, until=When.ENCOUNTER, on=me, label="m2014a3 rise")


# ==========================================================================
# m2028
# ==========================================================================


@power(
    "m2028a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("2d8", 2),
)
def m2028a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2028a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d8", 1),
)
def m2028a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(5, dtype=DamageType.NECROTIC)
        c.push(1)
        c.prone()


@power(
    "m2028a2", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=CloseBurst(5), target=EACH_ENEMY, keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("3d8", 3, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m2028a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    victim = c.target
    if victim is not None and c.adjacent_to(victim, c.me):
        c.immobilized(until=When.EONT, on=victim)


@power(
    "m2028a3", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL,
    target=NO_TARGET, out_of_combat=True,
)
def m2028a3(c: Cast) -> None:
    """Tracking its own killer across planes has no combat meaning on a
    single board, where the distance to any creature present is already
    known."""
    c.note("m2028a3: while on the same plane as its killer, it knows the direction and distance")


@power("m2028a4", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m2028a4(c: Cast) -> None:
    me = c.me
    for which in ALL_DEFENCES:
        c.bonus(which, 2, on=me, until=When.ENCOUNTER, when=lambda _ctx: c.bloodied(me))


# ==========================================================================
# m2050
# ==========================================================================


@power(
    "m2050a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d10", 7),
)
def m2050a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m2050a1", level=7, usage=AT_WILL, action=OPPORTUNITY, reach=Melee(1),
    target=NO_TARGET, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("2d6", 5),
    trigger="a creature marked by it moves or shifts",
    on=Trigger(MoveStart, _marked_shifts, "a creature marked by it moves or shifts"),
)
def m2050a1(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


@power(
    "m2050a2", level=7, usage=ENCOUNTER, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("2d10", 7),
)
def m2050a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.effect(c.ref, on=victim, until=When.SAVE_ENDS)
    if hold is None:
        return
    me = c.me

    def lashback(ev: DamageApplied) -> None:
        if ev.source == victim:
            c.flat(5, on=victim)

    watcher = c.watch(
        DamageApplied, lashback, until=When.SAVE_ENDS, on=me, label=f"{c.ref} backlash"
    )
    hold.on_end.append(lambda: c.world.effects.end(watcher, "the hold ended"))


@power(
    "m2050a3", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL,
    target=NO_TARGET, dropped=("Effect.keywords",),
)
def m2050a3(c: Cast) -> None:
    """Narrowing to a save against an effect carrying the charm or fear
    keyword cannot be asked -- `Effect` carries conditions and ongoing
    damage, never the keyword of the power that applied it -- so this fires
    on any successful save against a save-ends hold instead, the same
    over-broad approximation `_crit_drops_it` takes elsewhere for a
    comparable gap."""
    me = c.me

    def answered(ev: SavingThrow) -> None:
        if ev.actor != me or not ev.saved:
            return
        foe = next((f for f in c.enemies() if c.adjacent(f)), None)
        if foe is not None:
            c.use_power("m2050a0", on=foe)

    c.watch(SavingThrow, answered, until=When.ENCOUNTER, on=me, label="m2050a3")


# ==========================================================================
# m2233
# ==========================================================================


@power(
    "m2233a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=12), damage=Damage("1d8", 5),
)
def m2233a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(1)
        c.grab()


@power(
    "m2233a1", level=7, usage=AT_WILL, action=MINOR, reach=Melee(2),
    target=Target(side="enemy", count=1, label="creature grabbed by it"),
    attack=Attack(vs=AC, printed=14), damage=Damage("1d6", 5), dropped=("Target.relation",),
)
def m2233a1(c: Cast) -> None:
    held = _holding(c)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is not None and c.strike(on=victim):
        c.hit(on=victim)


@power(
    "m2233a2", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL,
    target=NO_TARGET, todo=("Budget.opportunity_turn",),
)
def m2233a2(c: Cast) -> None:
    """"Can make opportunity attacks against all enemies in reach" lifts the
    one-opportunity-attack-per-turn budget for every one of them; nothing
    here can waive `Budget.opportunity_turn`."""


# ==========================================================================
# m2249
# ==========================================================================


@power(
    "m2249a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d8", 2),
)
def m2249a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", 0, dtype=DamageType.COLD)


@power(
    "m2249a1", level=7, usage=ENCOUNTER, action=STANDARD, reach=CloseBurst(3),
    target=EACH_ENEMY, keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("1d8", 3, dtype=DamageType.COLD, kind=LIMITED),
)
def m2249a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)


def _attacked_my_ally_not_me(world: World, me: int, ev: PowerUsed) -> bool:
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or team(world, actor) is team(world, me):
        return False
    if distance_between(world, me, actor) > 1:
        return False
    if not _is_attack(ev.power):
        return False
    targets = getattr(ev, "targets", ())
    if me in targets:
        return False
    return any(t != me and team(world, t) is team(world, me) for t in targets)


@power(
    "m2249a2", level=7, usage=AT_WILL, action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL, target=NO_TARGET, keywords=[Keyword.COLD],
    trigger="an adjacent enemy attacks its ally without also targeting it",
    on=Trigger(
        PowerUsed, _attacked_my_ally_not_me, "an adjacent enemy attacks its ally without it"
    ),
)
def m2249a2(c: Cast) -> None:
    hit_targets = getattr(c.trigger, "targets", ())
    allies_hit = [t for t in hit_targets if team(c.world, t) is team(c.world, c.me)]
    if allies_hit:
        c.ongoing(5, DamageType.COLD, on=allies_hit[0])


# ==========================================================================
# m3379
# ==========================================================================


@power(
    "m3379a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=14), damage=Damage("1d8", 7),
)
def m3379a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3379a1", level=7, usage=ENCOUNTER, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=14), damage=Damage("2d8", 7, kind=LIMITED),
)
def m3379a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            spot = _free_square_beside(c, victim)
            if spot is not None:
                c.shift(3, to=spot)


@power(
    "m3379a2", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=ONE_CREATURE, attack=Attack(vs=AC, printed=14),
    damage=Damage("1d8", 7, kind=LIMITED),
)
def m3379a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(2)
        victim = c.target
        if victim is None:
            return
        for mate in [a for a in c.allies() if a != c.me and c.adjacent_to(a, victim)][:2]:
            c.shift(2, who=mate)


@power("m3379a3", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3379a3(c: Cast) -> None:
    me = c.me

    def near_me(ctx: dict) -> bool:
        victim = ctx.get("target")
        return victim is not None and not ctx.get("ranged") and c.adjacent_to(me, victim)

    for mate in c.allies():
        if mate != me:
            c.bonus("damage", 3, on=mate, until=When.ENCOUNTER, when=near_me)


# ==========================================================================
# m3615
# ==========================================================================


@power(
    "m3615a0", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.DISEASE, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=10), damage=Damage("2d6", 2, kind=LIMITED),
)
def m3615a0(c: Cast) -> None:
    """"Contracts worms" is a disease track outside combat; noted on the
    first failed save rather than invented."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    held = c.ongoing(10, DamageType.NECROTIC, on=victim, until=When.SAVE_ENDS)
    if held is None or victim is None:
        return

    def failed(ev: SavingThrow) -> None:
        if ev.actor == victim and ev.against == held.label and not ev.saved:
            c.note(f"{c.ref}: it contracts worms")

    c.watch(SavingThrow, failed, until=When.SAVE_ENDS, on=c.me, once=True, label=f"{c.ref} worms")


# ==========================================================================
# m3783
# ==========================================================================


@power(
    "m3783a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d8", 6),
)
def m3783a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m3783a1", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=UpTo(2),
)
def m3783a1(c: Cast) -> None:
    """"Recharges when first bloodied" is `_recharge_when_bloodied`, armed
    once. The numbers are the scimitar's own line, m3783a0, used rather than
    copied."""
    if c.first:
        _recharge_when_bloodied(c)
    victim = c.target
    if victim is not None:
        use(c.world, c.me, "m3783a0", targets=[victim], spend=False)
    if c.first:
        c.shift(1)


@power(
    "m3783a2", level=7, usage=ENCOUNTER, action=MOVE, reach=PERSONAL,
    target=SELF, keywords=[Keyword.TELEPORTATION],
)
def m3783a2(c: Cast) -> None:
    c.teleport(5)


@power(
    "m3783a3", level=7, usage=ENCOUNTER, action=STANDARD, reach=PERSONAL,
    target=SELF, keywords=[Keyword.POLYMORPH], dropped=("c.reach(set=)",),
)
def m3783a3(c: Cast) -> None:
    """Growing, the push it causes and the damage bonus all play. Its melee
    reach becoming 2 while grown does not: `c.reach` has no setter, so a
    row's printed range cannot change mid-fight."""
    me = c.me
    grown = c.resize(Size.LARGE, on=me, until=When.ENCOUNTER)
    if grown is None:
        return
    c.bonus(
        "damage", 5, on=me, until=When.ENCOUNTER,
        when=lambda _ctx: grown in c.world.effects.of(me),
    )
    c.endable(grown, cost=ActionType.FREE)


# ==========================================================================
# m3820
# ==========================================================================


@power(
    "m3820a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.ACID, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d10", 3, dtype=DamageType.ACID),
)
def m3820a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3820a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=UpTo(2), keywords=[Keyword.ACID, Keyword.WEAPON],
)
def m3820a1(c: Cast) -> None:
    """Both swings and the splash they trigger are handled in one pass,
    guarded on `c.first`: the hit bookkeeping has to live across both
    targets, which the dsl's own per-target call cannot carry."""
    if not c.first:
        return
    bonus = c.world.scaling.trim(14, c.level)
    struck: set[int] = set()
    for victim in c.targets[:2]:
        if c.attack(bonus, AC, on=victim):
            c.damage("1d10", 3, dtype=DamageType.ACID, on=victim)
            struck.add(victim)
    if struck:
        for foe in c.enemies():
            if foe not in struck and c.adjacent(foe):
                c.flat(3, dtype=DamageType.ACID, on=foe)


@power(
    "m3820a2", level=7, usage=ENCOUNTER, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=14), damage=Damage("2d10", 4, kind=LIMITED, half_on_miss=True),
)
def m3820a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    else:
        c.hit(half=True)
    c.weakened(until=When.SAVE_ENDS)


@power(
    "m3820a3", level=7, usage=AT_WILL, action=STANDARD, reach=CloseBurst(2),
    target=EACH_ENEMY, keywords=[Keyword.LIGHTNING, Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d10", 4, dtype=DamageType.LIGHTNING),
)
def m3820a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3820a4", level=7, usage=AT_WILL, action=MINOR, reach=CloseBurst(2),
    target=ONE_CREATURE, keywords=[Keyword.TELEPORTATION],
)
def m3820a4(c: Cast) -> None:
    """One mark at a time, re-laid rather than stacked; the punish is the
    immediate reaction `Encounter.spend` already limits, armed the way
    m4593a4's riposte is."""
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

    if _armed(c, f"{ref} teleport"):
        return

    def looked_away(ev: PowerUsed) -> None:
        foe = ev.actor
        if foe == me or not c.world.relations.holds(Relation.MARKED_BY, me, foe):
            return
        if me in ev.targets or distance_between(c.world, me, foe) > 10:
            return
        p = get(ev.power)
        if p is None or not p.is_attack:
            return
        spot = _free_square_beside(c, me)
        if spot is None:
            return
        c.teleport(10, who=foe, to=spot)
        c.grants_advantage(on=foe, to="team", until=When.EONT)

    c.watch(PowerUsed, looked_away, until=When.ENCOUNTER, on=me, label=f"{ref} teleport")


@power(
    "m3820a5", level=7, usage=Usage.RECHARGE, recharge=6, action=MOVE, reach=PERSONAL,
    target=SELF, keywords=[Keyword.ILLUSION, Keyword.TELEPORTATION],
)
def m3820a5(c: Cast) -> None:
    c.teleport(6)
    c.invisible(on=c.me)


# ==========================================================================
# m4212
# ==========================================================================


@power(
    "m4212a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("2d8", 2),
)
def m4212a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


def _m4212_ward(c: Cast) -> int | None:
    prefix = "m4212a1 ward:"
    for eff in c.world.effects.of(c.me):
        if eff.label.startswith(prefix):
            try:
                return int(eff.label[len(prefix):])
            except ValueError:
                return None
    return None


@power("m4212a1", level=7, usage=AT_WILL, action=MINOR, reach=Ranged(10), target=ONE_ALLY)
def m4212a1(c: Cast) -> None:
    """One ward at a time, re-designated rather than stacked. "Or object" has
    nowhere to go -- nothing in this tree can target an object -- so only the
    ally half is written."""
    me, ref = c.me, c.ref
    for eff in list(c.world.effects.of(me)):
        if eff.label.startswith(f"{ref} ward:"):
            c.world.effects.end(eff, "re-designated")
    victim = c.target
    if victim is None:
        return
    c.effect(f"{ref} ward:{victim}", until=When.ENCOUNTER, on=me)
    if _armed(c, f"{ref} shelter"):
        return

    def shelter(ev: DamageRolled) -> None:
        current = _m4212_ward(c)
        if current is None or ev.target != current:
            return
        if c.world.relations.holds(Relation.MARKED_BY, me, ev.source):
            ev.amount = max(0, ev.amount // 2)

    c.watch(DamageRolled, shelter, until=When.ENCOUNTER, on=me, label=f"{ref} shelter")


@power(
    "m4212a2", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL,
    target=NO_TARGET, dropped=("c.halt(on=)",),
)
def m4212a2(c: Cast) -> None:
    """The attack bonus plays. Stopping the struck creature's move outright
    has no verb -- `c.halt(on=)` is the gap."""
    c.bonus(
        "attack", 3, on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("opportunity")),
    )


@power("m4212a3", level=7, usage=AT_WILL, action=MINOR, reach=PERSONAL, target=NO_TARGET)
def m4212a3(c: Cast) -> None:
    c.shift(1)


@power("m4212a4", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4212a4(c: Cast) -> None:
    me = c.me
    for which in ALL_DEFENCES:
        c.bonus(
            which, 2, on=me, until=When.ENCOUNTER,
            when=lambda ctx: c.is_trap(who=ctx.get("attacker")),
        )


# ==========================================================================
# m4253
# ==========================================================================


@power(
    "m4253a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d10", 5),
)
def m4253a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m4253a1", level=7, usage=ENCOUNTER, action=STANDARD, reach=Ranged(5),
    target=ONE_CREATURE, keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d4", 6, kind=LIMITED),
)
def m4253a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    burn = c.ongoing(5, DamageType.POISON, on=victim, until=When.SAVE_ENDS)
    grant = c.grants_advantage(on=victim, to="team", until=When.SAVE_ENDS)
    if burn is not None and grant is not None:
        burn.on_end.append(lambda: c.world.effects.end(grant, "saved"))


@power(
    "m4253a2", level=7, usage=ENCOUNTER, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.FEAR, Keyword.WEAPON],
    attack=Attack(vs=WILL, printed=12), damage=Damage("2d10", 8, kind=LIMITED),
)
def m4253a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        c.penalty("attack", 2, until=When.EONT, on=victim)
        if victim is not None and c.marked(on=victim, by=c.me):
            c.dazed(until=When.EONT, on=victim)


# ==========================================================================
# m4509
# ==========================================================================


@power(
    "m4509a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d12", 3),
)
def m4509a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m4509a1", level=7, usage=AT_WILL, action=MINOR, reach=CloseBurst(5), target=ONE_CREATURE)
def m4509a1(c: Cast) -> None:
    """One designated foe at a time; `c.gains_advantage`'s own default label
    is what lets a second use find and clear the first."""
    me, ref = c.me, c.ref
    victim = c.target
    if victim is None:
        return
    for eff in list(c.world.effects.of(me)):
        if eff.label == f"{ref} gains advantage":
            c.world.effects.end(eff, "re-designated")
    c.gains_advantage(when=lambda ctx: ctx.get("target") == victim, until=When.ENCOUNTER, on=me)


@power(
    "m4509a2", level=7, usage=AT_WILL, action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1), target=NO_TARGET, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d12", 7),
    trigger="an adjacent enemy shifts",
    on=Trigger(MoveStart, _adjacent_enemy_shifts, "an adjacent enemy shifts"),
)
def m4509a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


@power(
    "m4509a3", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=ONE_CREATURE, attack=Attack(vs=AC, printed=14),
    damage=Damage("2d12", 3, kind=LIMITED),
)
def m4509a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is None:
            return
        for foe in [f for f in c.enemies() if distance_between(c.world, f, victim) <= 2]:
            c.teleport(3, who=foe)


@power(
    "m4509a4", level=7, usage=ENCOUNTER, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=14),
    damage=Damage("3d12", 3, kind=LIMITED, half_on_miss=True),
)
def m4509a4(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        c.invisible(to=victim, until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.invisible(to=victim, until=When.EONT)


@power("m4509a5", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4509a5(c: Cast) -> None:
    c.resist_forced(1, on=c.me)
    _saves_off_prone(c)


# ==========================================================================
# m5504
# ==========================================================================


@power(
    "m5504a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("2d8", 6),
)
def m5504a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m5504a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=Target(side="enemy", count=1, label="prone creature"),
    keywords=[Keyword.WEAPON], attack=Attack(vs=AC, printed=12), damage=Damage("2d8", 6),
    dropped=("Target.condition",),
)
def m5504a1(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.is_(Condition.PRONE, victim):
        return
    if not c.strike():
        return
    c.hit()
    hold = c.slowed(until=When.EONT, on=victim)
    if hold is None:
        return

    def stood(ev: ConditionEnded) -> None:
        if ev.target == victim and ev.condition is Condition.PRONE:
            c.ongoing(5, on=victim)

    watcher = c.watch(
        ConditionEnded, stood, until=When.EONT, on=c.me, once=True, label=f"{c.ref} watch"
    )
    hold.on_end.append(lambda: c.world.effects.end(watcher, "the slow ended"))


@power(
    "m5504a2", level=7, usage=AT_WILL, action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1), target=NO_TARGET, keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=10), damage=Damage("2d8", 6),
    trigger="a creature marked by it shifts or attacks without including it",
    on=[
        Trigger(MoveStart, _marked_by_me_shifts, "a creature marked by it shifts"),
        Trigger(PowerUsed, _marked_by_me_looks_away, "a creature marked by it attacks without it"),
    ],
)
def m5504a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.prone(on=foe)


# ==========================================================================
# m5576
# ==========================================================================


@power(
    "m5576a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=12), damage=Damage("2d8", 3),
    dropped=("c.grab(dc=)",),
)
def m5576a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m5576a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=Target(side="enemy", count=1, label="immobilized, stunned, or unconscious creature"),
    attack=Attack(vs=AC, printed=12), damage=Damage("3d6", 3), dropped=("Target.condition",),
)
def m5576a1(c: Cast) -> None:
    victim = c.target
    if victim is None or not any(c.is_(cnd, victim) for cnd in _PINNED_THREE):
        return
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m5576a2", level=7, usage=ENCOUNTER, action=STANDARD, reach=CloseBlast(5),
    target=EACH_ENEMY, keywords=[Keyword.FEAR, Keyword.THUNDER],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("4d6", 4, dtype=DamageType.THUNDER, kind=LIMITED),
)
def m5576a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)
        victim = c.target
        mods = [(victim, Mod(what=d, value=-2, kind="untyped", label=c.ref)) for d in ALL_DEFENCES]
        c.world.effects.apply(victim, c.me, When.SAVE_ENDS, label=c.ref, mods=mods)


@power(
    "m5576a3", level=7, usage=AT_WILL, action=FREE, reach=PERSONAL, target=NO_TARGET,
    trigger="a creature adjacent to it shifts",
    on=Trigger(MoveStart, _adjacent_enemy_shifts, "a creature adjacent to it shifts"),
)
def m5576a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.use_power("m5576a0", on=foe)


# ==========================================================================
# m5577
# ==========================================================================


@power("m5577a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5577a0(c: Cast) -> None:
    me = c.me

    def drained(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in _holding(c):
            return
        if not c.spend_surge(on=ev.actor):
            c.flat(10, on=ev.actor)

    c.watch(TurnEnd, drained, until=When.ENCOUNTER, on=me, label="m5577a0")


@power(
    "m5577a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=12), damage=Damage("2d8", 3),
    dropped=("c.grab(dc=)",),
)
def m5577a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m5577a2", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=Target(side="enemy", count=1, label="immobilized, stunned, or unconscious creature"),
    attack=Attack(vs=AC, printed=12), damage=Damage("4d6", 5), dropped=("Target.condition",),
)
def m5577a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not any(c.is_(cnd, victim) for cnd in _PINNED_THREE):
        return
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


def _adjacent_foe_hit_me(world: World, me: int, ev: Hit) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    attacker = getattr(ev, "attacker", None)
    return attacker is not None and distance_between(world, me, attacker) <= 1


@power(
    "m5577a3", level=7, usage=AT_WILL, action=FREE, reach=Melee(1), target=NO_TARGET,
    attack=Attack(vs=REF, printed=12),
    trigger="a creature adjacent to it hits it",
    on=Trigger(Hit, _adjacent_foe_hit_me, "a creature adjacent to it hits it"),
)
def m5577a3(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None and c.strike(on=foe):
        c.prone(on=foe)


# ==========================================================================
# m5598
# ==========================================================================

_M5598_SHAPE = "m5598a6 "
_M5598_SHAPES = ("snake", "human", "hybrid")


def _m5598_free_to_grab(world: World, eid: int) -> bool:
    return _in_shapes(_M5598_SHAPE, "snake", "hybrid")(world, eid) and _hands_free(world, eid)


def _m5598_holding(world: World, eid: int) -> bool:
    return _in_shapes(_M5598_SHAPE, "snake", "hybrid")(world, eid) and _has_hold(world, eid)


def _m5598_steady(world: World, eid: int) -> bool:
    return not is_(world, eid, Condition.SLOWED)


@power(
    "m5598a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL,
    target=NO_TARGET, dropped=("c.silvered()",),
)
def m5598a0(c: Cast) -> None:
    """The silvered-weapon suspension has no verb; the regeneration itself
    plays."""
    c.regeneration(5, until=When.ENCOUNTER, on=c.me)


@power(
    "m5598a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("2d10", 4),
    requires=_in_shapes(_M5598_SHAPE, "human", "hybrid"),
    requires_text="it must be in its human or hybrid form",
)
def m5598a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m5598a2", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.POISON],
    attack=Attack(vs=REF, printed=12), damage=Damage("1d8", 6, dtype=DamageType.POISON),
    requires=_in_shapes(_M5598_SHAPE, "snake", "hybrid"),
    requires_text="it must be in its snake or hybrid form",
    dropped=("c.contract(ref)",),
)
def m5598a2(c: Cast) -> None:
    """The end-of-encounter disease check has no mechanism; the attack bonus
    while already grabbing the target, and the ongoing poison, both play."""
    victim = c.target
    grabbing = victim is not None and victim in _holding(c)
    if c.strike(plus=2 if grabbing else 0):
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m5598a3", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=REF, printed=12),
    damage=Damage("1d8", 6, half_on_miss=True),
    requires=_m5598_free_to_grab,
    requires_text="it must be in its snake or hybrid form and not grabbing a creature",
    dropped=("c.grab(dc=)",),
)
def m5598a3(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        c.hit(half=True)
        return
    c.hit()
    if victim is None:
        return
    c.grab(on=victim)
    squeeze = c.effect(c.ref, on=victim, until=When.SUSTAIN, sustain=MINOR)

    def crush() -> None:
        c.flat(10, on=victim)
        c.dazed(until=When.EONT, on=victim)

    c.on_sustain(squeeze, crush)


@power(
    "m5598a4", level=7, usage=AT_WILL, action=MOVE, reach=PERSONAL, target=NO_TARGET,
    requires=_m5598_holding,
    requires_text="it must be in its snake or hybrid form and grabbing a creature",
)
def m5598a4(c: Cast) -> None:
    held = _holding(c)
    c.move(c.speed_of(), who=c.me)
    for victim in held:
        if not c.adjacent(victim):
            c.pull(c.speed_of(), on=victim)


@power(
    "m5598a5", level=7, usage=AT_WILL, action=MOVE, reach=PERSONAL, target=NO_TARGET,
    requires=_m5598_steady, requires_text="it must not be slowed",
)
def m5598a5(c: Cast) -> None:
    c.shift(4)
    for mate in c.allies():
        c.shift(2, who=mate)


@power(
    "m5598a6", level=7, usage=AT_WILL, action=MINOR, reach=PERSONAL,
    target=SELF, keywords=[Keyword.POLYMORPH],
)
def m5598a6(c: Cast) -> None:
    _change_shape(c, _M5598_SHAPE, _M5598_SHAPES)


@power(
    "m5598a7", level=7, usage=AT_WILL, action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1), target=NO_TARGET, keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=12), damage=Damage("1d8", 6),
    trigger="an enemy marked by it moves, shifts, or attacks without including it",
    on=[
        Trigger(MoveStart, _marked_by_me_shifts, "an enemy marked by it shifts"),
        Trigger(PowerUsed, _marked_by_me_looks_away, "an enemy marked by it attacks without it"),
    ],
)
def m5598a7(c: Cast) -> None:
    """The printed recoil names a flavour word rather than this creature's
    own ref; written as itself."""
    foe = _triggering_enemy(c)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.world.effects.apply(
            foe, c.me, When.SAVE_ENDS, label=c.ref,
            conditions=(Condition.WEAKENED,),
            mods=[(foe, Mod(what="attack", value=-2, kind="untyped", label=c.ref))],
        )
        c.flat(5, on=c.me)


# ==========================================================================
# m5600
# ==========================================================================


@power("m5600a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5600a0(c: Cast) -> None:
    me = c.me
    _aura(
        c, 10, lambda who: who != me and who in c.allies() and c.is_kind("fey", on=who),
        lambda who: c.bonus("crit_range", 1, until=When.ENCOUNTER, on=who),
    )


@power(
    "m5600a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("2d8", 6),
)
def m5600a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.result is not None and c.result.advantage:
            c.prone()


@power(
    "m5600a2", level=7, usage=AT_WILL, action=STANDARD, reach=Ranged(10),
    target=ONE_CREATURE, keywords=[Keyword.FORCE, Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=10), damage=Damage("2d6", 4, dtype=DamageType.FORCE),
)
def m5600a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5600a3", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("3d8", 8, kind=LIMITED),
)
def m5600a3(c: Cast) -> None:
    if c.first:
        c.as_basic(c.ref, window="opportunity", until=When.ENCOUNTER)
    if c.strike():
        c.hit()
        c.condition(Condition.RESTRAINED, until=When.EONT)
        if c.result is not None and c.result.advantage:
            c.prone()


@power(
    "m5600a4", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=PERSONAL, target=NO_TARGET,
)
def m5600a4(c: Cast) -> None:
    c.shift(c.speed_of())
    victim = next((f for f in c.enemies() if c.adjacent(f)), None)
    if victim is not None:
        c.use_power("m5600a1", on=victim)


@power(
    "m5600a5", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.CHARM, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("2d8", 6, kind=LIMITED),
)
def m5600a5(c: Cast) -> None:
    """"Recharge on a miss" is a watch on `Miss`, armed once, on top of the
    ordinary die the header already rolls."""
    me, ref = c.me, c.ref
    if not _armed(c, f"{ref} comeback"):
        def refresh(ev: Miss) -> None:
            if ev.attacker == me and getattr(ev, "power", "") == ref:
                c.restore_use(ref, on=me)

        c.watch(Miss, refresh, until=When.ENCOUNTER, on=me, label=f"{ref} comeback")
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.effect(f"{ref} beguiled", on=victim, until=When.SAVE_ENDS)
    if hold is None:
        return

    def struck(ev: Hit) -> None:
        if ev.target != me or ev.attacker == victim:
            return
        if team(c.world, ev.attacker) is not team(c.world, victim):
            return
        if distance_between(c.world, victim, ev.attacker) <= 1:
            c.use_power("m5600a1", on=ev.attacker, who=victim)

    watcher = c.watch(Hit, struck, until=When.SAVE_ENDS, on=me, label=f"{ref} beguile watch")
    hold.on_end.append(lambda: c.world.effects.end(watcher, "no longer beguiled"))


@power(
    "m5600a6", level=7, usage=ENCOUNTER, action=MOVE, reach=PERSONAL,
    target=SELF, keywords=[Keyword.TELEPORTATION],
)
def m5600a6(c: Cast) -> None:
    c.teleport(5)


@power(
    "m5600a7", level=7, usage=AT_WILL, action=MINOR, reach=CloseBurst(10),
    target=ONE_CREATURE, keywords=[Keyword.RADIANT],
)
def m5600a7(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        _marks_and_burns_for_looking_away(c, victim, 4, 10)


@power(
    "m5600a8", level=7, usage=Usage.RECHARGE, recharge=6, action=MINOR,
    reach=PERSONAL, target=NO_TARGET,
)
def m5600a8(c: Cast) -> None:
    for eff in [e for e in c.world.effects.of(c.me) if e.when is When.SAVE_ENDS]:
        c.world.effects.save(eff)


@power(
    "m5600a9", level=7, usage=AT_WILL, action=INTERRUPT, reach=CloseBurst(5), target=NO_TARGET,
    trigger="an attack damages an ally within 5 squares of it",
    on=Trigger(DamageRolled, _ally_near_is_struck(5), "an attack damages an ally within 5 squares"),
)
def m5600a9(c: Cast) -> None:
    """The recoil is printed against a leaked ref rather than this
    creature's own; written as itself."""
    _halves_a_hit_onto_me(c, 5)


# ==========================================================================
# m5733
# ==========================================================================


@power(
    "m5733a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("1d10", 10),
)
def m5733a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        hold = c.mark(until=When.EONT)
        victim = c.target
        if hold is not None and victim is not None:
            grant = c.grants_advantage(on=victim, to="team", until=When.EONT)
            if grant is not None:
                hold.on_end.append(lambda: c.world.effects.end(grant, "the mark ended"))


@power(
    "m5733a1", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=PERSONAL, target=NO_TARGET,
)
def m5733a1(c: Cast) -> None:
    if c.first:
        _recharge_when_bloodied(c)
    chosen: set[int] = set()
    victim = next(iter(sorted(c.enemies())), None)
    if victim is not None:
        chosen.add(victim)
        c.charge_at(victim)
    near = [a for a in c.allies() if a != c.me and distance_between(c.world, c.me, a) <= 5]
    for mate in near[:2]:
        other = next((f for f in c.enemies() if f not in chosen), None)
        if other is not None:
            chosen.add(other)
            c.charge_at(other, who=mate)


def _me_or_near_ally_held(world: World, me: int, ev: EffectApplied) -> bool:
    victim = getattr(ev, "target", None)
    if victim is None or not getattr(ev, "save_ends", False):
        return False
    if victim == me:
        return True
    if team(world, victim) is not team(world, me):
        return False
    return distance_between(world, me, victim) <= 5


@power(
    "m5733a2", level=7, usage=ENCOUNTER, action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL, target=NO_TARGET,
    trigger="it or an ally within 5 squares is subjected to an effect that a save can end",
    on=Trigger(EffectApplied, _me_or_near_ally_held, "it or a near ally suffers a save-ends hold"),
)
def m5733a2(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    label = getattr(c.trigger, "label", "")
    if victim is not None:
        c.save(on=victim, against=label)


# ==========================================================================
# m5782
# ==========================================================================


@power("m5782a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5782a0(c: Cast) -> None:
    me = c.me

    def steady(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        if any(_ref_of(c, w) == "m5782" for w in c.within(1, side="any") if w != me):
            c.save(on=me)

    c.watch(TurnStart, steady, until=When.ENCOUNTER, on=me, label="m5782a0")


@power(
    "m5782a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("2d8", 6),
)
def m5782a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5782a2", level=7, usage=AT_WILL, action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1), target=NO_TARGET, keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=10), damage=Damage("2d8", 6),
    trigger="an adjacent enemy uses an attack power that doesn't include it as a target",
    on=Trigger(PowerUsed, _adjacent_foe_looks_away, "an adjacent enemy looks away"),
)
def m5782a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.push(1, on=foe)
        c.prone(on=foe)


def _ally_near_dropped(radius: int):  # noqa: ANN202
    def gate(world: World, me: int, ev: Dropped) -> bool:
        victim = getattr(ev, "actor", None)
        if victim is None or victim == me or team(world, victim) is not team(world, me):
            return False
        return distance_between(world, me, victim) <= radius

    return gate


@power(
    "m5782a3", level=7, usage=ENCOUNTER, action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(1), target=EACH_ENEMY, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("2d8", 9, kind=LIMITED),
    trigger="an ally within 5 squares drops to 0 hit points",
    on=Trigger(Dropped, _ally_near_dropped(5), "an ally within 5 squares drops"),
)
def m5782a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


# ==========================================================================
# m5791
# ==========================================================================


@power("m5791a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5791a0(c: Cast) -> None:
    me = c.me
    c.aura(2, until=When.ENCOUNTER, on=me)

    def spent(ev: SurgeSpent) -> None:
        if ev.actor in c.enemies() and distance_between(c.world, me, ev.actor) <= 2:
            c.slowed(until=When.SOTNT, on=ev.actor)

    c.watch(SurgeSpent, spent, until=When.ENCOUNTER, on=me, label="m5791a0")


@power(
    "m5791a1", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL,
    target=NO_TARGET, dropped=("c.insubstantial(except_=)",),
)
def m5791a1(c: Cast) -> None:
    """`c.insubstantial` halves every damage type; the printed exception for
    force and radiant, and the clause that drops the trait for a turn after
    taking radiant, both need that exception to exist first."""
    c.insubstantial(on=c.me, until=When.ENCOUNTER)


@power(
    "m5791a2", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=12), damage=Damage("2d8", 6),
)
def m5791a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m5791a3", level=7, usage=ENCOUNTER, action=STANDARD, reach=CloseBlast(5),
    target=EACH_ENEMY, keywords=[Keyword.PSYCHIC, Keyword.THUNDER],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("2d10", 11, dtype=DamageType.THUNDER, kind=LIMITED, half_on_miss=True),
)
def m5791a3(c: Cast) -> None:
    """The extended-rest escalation toward death never resolves inside a
    single encounter and is noted rather than modelled."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is None:
            return
        c.curse(on=victim, until=When.ENCOUNTER)
        me = c.me

        def missed_everyone(ev: PowerResolved) -> None:
            if ev.actor != victim or not c.cursed(on=victim):
                return
            p = get(ev.power)
            if p is None or not p.is_attack:
                return
            rolls = getattr(ev, "rolls", ())
            if not rolls or any(r.hit for r in rolls):
                return
            c.flat(3, dtype=DamageType.PSYCHIC, on=victim)

        c.watch(PowerResolved, missed_everyone, until=When.ENCOUNTER, on=me, label=f"{c.ref} curse")
        c.note(
            f"{c.ref}: at the end of each extended rest, it rolls Religion DC 16 to end the "
            "curse; three failures and the target dies"
        )
    else:
        c.hit(half=True)


@power(
    "m5791a4", level=7, usage=AT_WILL, action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBlast(3), target=NO_TARGET, keywords=[Keyword.FEAR, Keyword.THUNDER],
    attack=Attack(vs=FORT, printed=10), damage=Damage("2d10", 4, dtype=DamageType.THUNDER),
    trigger="a marked enemy within 3 squares willingly moves away",
    on=Trigger(MoveStart, _marked_within_moves_away(3), "a marked enemy within 3 squares moves"),
)
def m5791a4(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.grants_advantage(on=foe, until=When.EONT, to="team")


# ==========================================================================
# m5841
# ==========================================================================


@power(
    "m5841a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("2d8", 6),
)
def m5841a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m5841a1", level=7, usage=ENCOUNTER, action=STANDARD, reach=Ranged(5),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON], no_provoke=True,
    attack=Attack(vs=AC, printed=12), damage=Damage("3d6", 5, kind=LIMITED),
)
def m5841a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED))
    else:
        c.immobilized(until=When.EONT)


@power(
    "m5841a2", level=7, usage=AT_WILL, action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL, target=NO_TARGET,
    trigger="a marked enemy within 5 squares looks away",
    on=Trigger(
        PowerUsed, _marked_within_looks_away(5), "a marked enemy within 5 squares looks away"
    ),
)
def m5841a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m5841a1")
    c.use_power("m5841a1", on=foe)


# ==========================================================================
# m5889
# ==========================================================================


@power(
    "m5889a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("2d10", 4),
)
def m5889a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power("m5889a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(2), target=UpTo(2))
def m5889a1(c: Cast) -> None:
    _twice(c, "m5889a0")


@power("m5889a2", level=7, usage=ENCOUNTER, action=MINOR, reach=CloseBurst(2), target=EACH_ALLY)
def m5889a2(c: Cast) -> None:
    mate = c.target
    if mate is not None:
        c.basic(who=mate)


@power(
    "m5889a3", level=7, usage=AT_WILL, action=OPPORTUNITY, reach=Melee(1),
    target=NO_TARGET, attack=Attack(vs=REF, printed=10), damage=Damage("2d6", 0),
    trigger="an adjacent enemy shifts",
    on=Trigger(MoveStart, _adjacent_enemy_shifts, "an adjacent enemy shifts"),
)
def m5889a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.prone(on=foe)


# ==========================================================================
# m5934
# ==========================================================================


@power(
    "m5934a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.FEAR, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("2d8", 6),
)
def m5934a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        me = c.me
        if victim is not None:
            c.penalty(
                "attack", 2, on=victim, until=When.ENCOUNTER,
                when=lambda ctx: ctx.get("target") == me,
            )


@power(
    "m5934a1", level=7, usage=Usage.RECHARGE, recharge=6, action=MINOR,
    reach=CloseBlast(5), target=ONE_CREATURE, attack=Attack(vs=WILL, printed=10),
)
def m5934a1(c: Cast) -> None:
    if c.strike():
        c.pull(4)
        c.grants_advantage(until=When.EONT)


def _adjacent_foe_ignores_me(world: World, me: int, ev: PowerUsed) -> bool:
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or team(world, actor) is team(world, me):
        return False
    if distance_between(world, me, actor) > 1:
        return False
    if not _is_attack(ev.power):
        return False
    return me not in getattr(ev, "targets", ())


@power(
    "m5934a2", level=7, usage=AT_WILL, action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL, target=NO_TARGET,
    trigger="an adjacent enemy shifts or uses an attack power that doesn't include it",
    on=[
        Trigger(MoveStart, _adjacent_enemy_shifts, "an adjacent enemy shifts"),
        Trigger(PowerUsed, _adjacent_foe_ignores_me, "an adjacent enemy attacks without it"),
    ],
)
def m5934a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.basic(on=foe)


# ==========================================================================
# m5949
# ==========================================================================


@power(
    "m5949a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=12), damage=Damage("1d8", 5, dtype=DamageType.NECROTIC),
)
def m5949a0(c: Cast) -> None:
    me = c.me
    if not _armed(c, "m5949a0 scorch watch"):
        def scorched(ev: DamageApplied) -> None:
            if ev.target == me and ev.dtype is DamageType.RADIANT:
                c.effect("m5949a0 scorched", on=me, until=When.EONT)

        c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label="m5949a0 scorch watch")
    if not c.strike():
        return
    c.hit()
    victim = c.target
    c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim)
    scorched_now = any(e.label == "m5949a0 scorched" for e in c.world.effects.of(me))
    if victim is not None and not scorched_now:
        c.spend_surge(on=victim)


def _enemy_saved_nearby(radius: int):  # noqa: ANN202
    def gate(world: World, me: int, ev: SavingThrow) -> bool:
        if not ev.saved or ev.actor not in enemies(world, me):
            return False
        return distance_between(world, me, ev.actor) <= radius

    return gate


@power(
    "m5949a1", level=7, usage=AT_WILL, action=OPPORTUNITY, reach=CloseBurst(5),
    target=NO_TARGET, keywords=[Keyword.NECROTIC], attack=Attack(vs=FORT, printed=10),
    trigger="an enemy within 5 squares makes a successful saving throw",
    on=Trigger(SavingThrow, _enemy_saved_nearby(5), "an enemy within 5 squares saves successfully"),
)
def m5949a1(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.strike(on=foe):
        c.flat(5, dtype=DamageType.NECROTIC, on=foe)
        c.grants_advantage(on=foe, until=When.EONT)


# ==========================================================================
# m5990
# ==========================================================================


def _m5990_shield(c: Cast, who: int) -> Effect | None:
    umbrella = c.effect(f"m5990a0 shield {who}", on=who, until=When.ENCOUNTER)
    if umbrella is None:
        return None
    for which in ALL_DEFENCES:
        bonus = c.bonus(which, 2, on=who, until=When.ENCOUNTER)
        if bonus is not None:
            umbrella.on_end.append(lambda b=bonus: c.world.effects.end(b, "left the aura"))
    return umbrella


@power("m5990a0", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5990a0(c: Cast) -> None:
    me = c.me
    _aura(c, 5, lambda who: who != me and who in c.allies(), lambda who: _m5990_shield(c, who))


@power(
    "m5990a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("1d10", 10),
)
def m5990a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m5990a2", level=7, usage=AT_WILL, action=STANDARD, reach=Ranged(5),
    target=ONE_CREATURE, keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=10),
)
def m5990a2(c: Cast) -> None:
    """"First Failed Saving Throw: falls unconscious instead" replaces the
    weakened hold rather than adding to it, the same escalate shape
    artillery's `_sleep` uses."""
    if not c.strike():
        return
    victim = c.target

    def worsen(eff: Effect) -> None:
        c.world.effects.end(eff, "weakened further")
        c.condition(Condition.UNCONSCIOUS, until=When.SAVE_ENDS, on=victim)

    c.condition(Condition.WEAKENED, until=When.SAVE_ENDS, on=victim, escalate=worsen)


def _ally_dropped_visible(world: World, me: int, ev: Dropped) -> bool:
    victim = getattr(ev, "actor", None)
    return victim is not None and victim != me and team(world, victim) is team(world, me)


@power(
    "m5990a3", level=7, usage=AT_WILL, action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL, target=NO_TARGET,
    trigger="an ally it can see is reduced to 0 hit points",
    on=Trigger(Dropped, _ally_dropped_visible, "an ally it can see drops"),
)
def m5990a3(c: Cast) -> None:
    me = c.me
    mate = next((a for a in c.allies() if a != me and distance_between(c.world, me, a) <= 5), None)
    if mate is None:
        return
    c.shift(3, who=mate)
    c.basic(who=mate)


# ==========================================================================
# m6072
# ==========================================================================


@power(
    "m6072a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("2d8", 6),
)
def m6072a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m6072a1", level=7, usage=ENCOUNTER, action=STANDARD, reach=Ranged(5),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON], no_provoke=True,
    attack=Attack(vs=AC, printed=12), damage=Damage("3d6", 5, kind=LIMITED),
)
def m6072a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED))
    else:
        c.immobilized(until=When.EONT)


@power(
    "m6072a2", level=7, usage=AT_WILL, action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL, target=NO_TARGET,
    trigger="a marked enemy within 5 squares looks away",
    on=Trigger(
        PowerUsed, _marked_within_looks_away(5), "a marked enemy within 5 squares looks away"
    ),
)
def m6072a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is None:
        return
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m6072a1")
    c.use_power("m6072a1", on=foe)


# ==========================================================================
# m6193
# ==========================================================================


@power(
    "m6193a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("2d8", 4),
)
def m6193a0(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    me, ref = c.me, c.ref
    anchor = _square_of(c, me)

    def departs(ev: Moved) -> None:
        if ev.actor != victim or ev.kind_ in ("push", "pull", "slide"):
            return
        if ev.from_ is None or anchor is None:
            return
        if square_distance(ev.from_, anchor) <= 1 and not c.adjacent(victim):
            c.flat(7, on=victim)

    c.watch(Moved, departs, until=When.EONT, on=me, once=True, label=f"{ref} punish {victim}")


@power(
    "m6193a1", level=7, usage=AT_WILL, action=STANDARD, reach=Ranged(10),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("2d8", 6),
)
def m6193a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6193a2", level=7, usage=ENCOUNTER, action=STANDARD, reach=CloseBurst(1),
    target=EACH_ENEMY, keywords=[Keyword.HEALING, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("2d8", 4),
)
def m6193a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.heal(c.roll("2d6"), on=c.me)


def _adjacent_foe_melees_my_ally(world: World, me: int, ev: AttackDeclared) -> bool:
    attacker = getattr(ev, "attacker", None)
    if attacker is None or attacker == me or team(world, attacker) is team(world, me):
        return False
    if distance_between(world, me, attacker) > 1 or not by_melee(world, me, ev):
        return False
    victim = getattr(ev, "target", None)
    return victim is not None and victim != me and team(world, victim) is team(world, me)


@power(
    "m6193a3", level=7, usage=AT_WILL, action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL, target=NO_TARGET,
    trigger="an adjacent enemy makes a melee attack against its ally",
    on=Trigger(AttackDeclared, _adjacent_foe_melees_my_ally, "an adjacent enemy melees its ally"),
)
def m6193a3(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not c.redirect(to=c.me):
        return
    c.use_power("m6193a0", on=foe)


# ==========================================================================
# m884
# ==========================================================================


@power(
    "m884a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(2),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d12", 5),
)
def m884a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m884a1", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(2), target=ONE_CREATURE, damage=Damage("3d10", 5, kind=LIMITED),
)
def m884a1(c: Cast) -> None:
    me = c.me
    bonus = c.world.scaling.trim(12, c.level)
    if c.attack(bonus, AC, on=c.target):
        c.damage("3d10", 5)
    for caught in c.overrun():
        if c.size_of(on=caught) < c.size_of(on=me):
            c.push(1, on=caught)
            c.prone(on=caught)
    c.effect("m884a1 rampage", on=me, until=When.EOT)


def _just_rampaged(world: World, eid: int) -> bool:
    return any(e.label == "m884a1 rampage" for e in world.effects.of(eid))


@power(
    "m884a2", level=7, usage=AT_WILL, action=FREE, reach=CloseBurst(1),
    target=EACH_OTHER, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d12", 5),
    requires=_just_rampaged, requires_text="it must have just used its rampage",
)
def m884a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


def _master_near_is_struck(radius: int):  # noqa: ANN202
    def gate(world: World, me: int, ev: DamageRolled) -> bool:
        masters = world.relations.sources(Relation.MASTER_OF, me)
        who = ev.target
        if who not in masters:
            return False
        p = get(ev.detail or "")
        if p is None or not p.is_attack:
            return False
        return distance_between(world, me, who) <= radius

    return gate


@power(
    "m884a3", level=7, usage=Usage.RECHARGE, recharge=6, action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL, target=NO_TARGET,
    trigger="its master is within 2 squares and is hit by an attack",
    on=Trigger(DamageRolled, _master_near_is_struck(2), "its master within 2 squares is hit"),
)
def m884a3(c: Cast) -> None:
    ev = c.trigger
    whole = max(0, getattr(ev, "amount", 0))
    if whole <= 0:
        return
    share = whole // 2
    ev.amount = whole - share
    c.flat(share, dtype=ev.dtype, on=c.me)


@power(
    "m884a4", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL,
    target=NO_TARGET, todo=("c.passes_through()",),
)
def m884a4(c: Cast) -> None:
    """Moving through a smaller creature's space -- while still refusing to
    end its own move there -- has no verb; `c.phasing` is for terrain, not
    for other creatures' squares."""


@power("m884a5", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m884a5(c: Cast) -> None:
    c.cannot_shift(on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m897
# ==========================================================================


@power(
    "m897a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("2d6", 6, dtype=DamageType.FIRE),
)
def m897a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m897a1", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("2d6", 6, dtype=DamageType.FIRE),
)
def m897a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if c.push(2) and victim is not None:
            spot = _free_square_beside(c, victim)
            if spot is not None:
                c.shift(2, to=spot)


@power(
    "m897a2", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d6", 6, dtype=DamageType.FIRE, kind=LIMITED),
)
def m897a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)
        c.prone()


@power(
    "m897a3", level=7, usage=ENCOUNTER, action=MINOR, reach=Ranged(3),
    target=ONE_CREATURE, keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=12), damage=Damage("1d8", 3, kind=LIMITED),
)
def m897a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        mod = Mod(what="attack", value=-2, kind="untyped", label=c.ref)
        c.world.effects.apply(
            c.target, c.me, When.SAVE_ENDS, label=c.ref,
            mods=[(c.target, mod)], ongoing=(2, DamageType.POISON),
        )


@power(
    "m897a4", level=7, usage=Usage.RECHARGE, recharge=6, action=MINOR,
    reach=Melee(1), target=ONE_ALLY, keywords=[Keyword.FIRE, Keyword.HEALING],
)
def m897a4(c: Cast) -> None:
    mate = c.target if c.target is not None else c.me
    c.heal(25, on=mate)

    def scorch(ev: AttackDeclared) -> None:
        if ev.target == mate:
            c.flat(5, dtype=DamageType.FIRE, on=ev.attacker)

    c.watch(AttackDeclared, scorch, until=When.EONT, on=mate, label=f"{c.ref} brand {mate}")


# ==========================================================================
# m944
# ==========================================================================


@power(
    "m944a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14), damage=Damage("1d10", 5),
)
def m944a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m944a1", level=7, usage=ENCOUNTER, action=STANDARD, reach=CloseBlast(3),
    target=EACH_ENEMY, keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d6", 4, dtype=DamageType.POISON, kind=LIMITED),
)
def m944a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


# ==========================================================================
# m961
# ==========================================================================


@power(
    "m961a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("1d8", 4),
)
def m961a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m961a1", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.COLD, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d8", 4, dtype=DamageType.COLD, kind=LIMITED),
)
def m961a1(c: Cast) -> None:
    if c.first:
        c.as_basic(c.ref, window="opportunity", until=When.ENCOUNTER)
    if c.strike():
        c.hit()
        hold = c.condition(Condition.RESTRAINED, until=When.EONT)
        if hold is not None:
            for other in ("m961a0", "m961a1"):
                bar = c.forbid(other, on=c.me, until=When.EONT)
                if bar is not None:
                    hold.on_end.append(lambda b=bar: c.world.effects.end(b, "no longer restrained"))


@power("m961a2", level=7, usage=ENCOUNTER, action=STANDARD, reach=Ranged(10), target=ONE_CREATURE)
def m961a2(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        _marks_and_burns_for_looking_away(c, victim, 4, 10)


@power(
    "m961a3", level=7, usage=ENCOUNTER, action=MOVE, reach=PERSONAL,
    target=SELF, keywords=[Keyword.TELEPORTATION],
)
def m961a3(c: Cast) -> None:
    c.teleport(5)


def _m961_ally_near_is_struck(world: World, me: int, ev: DamageRolled) -> bool:
    who = ev.target
    if who == me or team(world, who) is not team(world, me):
        return False
    p = get(ev.detail or "")
    return p is not None and p.is_attack and distance_between(world, me, who) <= 5


@power(
    "m961a4", level=7, usage=AT_WILL, action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL, target=NO_TARGET,
    trigger="an ally within 5 squares of it is damaged",
    on=Trigger(DamageRolled, _m961_ally_near_is_struck, "an ally within 5 squares is damaged"),
)
def m961a4(c: Cast) -> None:
    """The recoil is printed against a leaked ref rather than this
    creature's own; written as itself."""
    _halves_a_hit_onto_me(c, 5)


# ==========================================================================
# m992
# ==========================================================================


@power(
    "m992a0", level=7, usage=AT_WILL, action=STANDARD, reach=Melee(1),
    target=ONE_CREATURE, attack=Attack(vs=AC, printed=14), damage=Damage("1d8", 5),
)
def m992a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power("m992a1", level=7, usage=ENCOUNTER, action=STANDARD, reach=Melee(1), target=UpTo(2))
def m992a1(c: Cast) -> None:
    """Two basic attacks: at one target twice, or at two targets once each --
    `c.targets` says which, the same choice `UpTo(2)` offers elsewhere."""
    if not c.first:
        return
    targets_ = c.targets
    if not targets_:
        return
    if len(targets_) == 1:
        victim = targets_[0]
        hits = sum(1 for _ in range(2) if c.basic(on=victim))
        if hits >= 2:
            c.dazed(until=When.SAVE_ENDS, on=victim)
    else:
        for victim in targets_[:2]:
            c.basic(on=victim)


@power(
    "m992a2", level=7, usage=Usage.RECHARGE, recharge=6, action=STANDARD,
    reach=Melee(1), target=ONE_CREATURE, keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12), damage=Damage("1d8", 5),
)
def m992a2(c: Cast) -> None:
    """"Recharges after it uses m992a3" is a watch on that use, not the die;
    the number stays in the header as what `actions.recharge` rolls."""
    _recharge_when_using(c, "m992a3")
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m992a3", level=7, usage=Usage.RECHARGE, recharge=6, action=MINOR,
    reach=PERSONAL, target=SELF,
)
def m992a3(c: Cast) -> None:
    me = c.me
    for which in ALL_DEFENCES:
        c.bonus(which, 2, on=me, until=When.EONT)
    c.bonus("skill:perception", 2, on=me, until=When.EONT)


def _missed_me(world: World, me: int, ev: Miss) -> bool:
    return getattr(ev, "target", None) == me


@power(
    "m992a4", level=7, usage=Usage.RECHARGE, recharge=6, action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL, target=NO_TARGET,
    trigger="it is missed by a melee or ranged attack",
    on=Trigger(Miss, _missed_me, "it is missed by a melee or ranged attack"),
)
def m992a4(c: Cast) -> None:
    """The reroll is the same power used again by its own attacker against a
    new target, which `c.use_power(who=)` lends without spending a second
    use."""
    ev = c.trigger
    attacker = getattr(ev, "attacker", None)
    ref = getattr(ev, "power", "")
    if attacker is None or not ref:
        return
    melee = _reach_kind(ref) == "melee"
    radius = 1 if melee else 3

    def near_attacker(f: int) -> bool:
        return f != attacker and distance_between(c.world, attacker, f) <= radius

    victim = next((f for f in c.enemies() if near_attacker(f)), None)
    if victim is None:
        return
    c.use_power(ref, on=victim, who=attacker, spend=False)
    me = c.me
    if not _armed(c, "m992a4 recharge"):
        def moved(mv: Moved) -> None:
            if mv.actor == me:
                c.restore_use("m992a4", on=me)

        c.watch(Moved, moved, until=When.ENCOUNTER, on=me, label="m992a4 recharge")


@power("m992a5", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m992a5(c: Cast) -> None:
    me = c.me
    c.bonus(
        "damage", 0, dice="1d6", on=me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")) and not ctx.get("ranged"),
    )


@power("m992a6", level=7, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m992a6(c: Cast) -> None:
    """`c.no_miss_damage` is unconditional -- a touch wider than "only an
    area or close attack" -- and the retaliation reads the damage type off
    the header of whatever just missed."""
    me = c.me
    c.no_miss_damage(on=me, until=When.ENCOUNTER)

    def scorned(ev: Miss) -> None:
        if getattr(ev, "target", None) != me:
            return
        attacker = getattr(ev, "attacker", None)
        if attacker is None:
            return
        p = get(getattr(ev, "power", "") or "")
        if p is None or p.reach.kind not in ("close_burst", "close_blast", "area_burst"):
            return
        dtype = p.damage.dtype if p.damage is not None else DamageType.UNTYPED
        c.flat(5, dtype=dtype, on=attacker)

    c.watch(Miss, scorned, until=When.ENCOUNTER, on=me, label="m992a6")
