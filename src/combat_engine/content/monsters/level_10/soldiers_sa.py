"""Monster abilities, level 10, soldiers -- second sweep.

53 stat blocks carry a row here; eleven more (`m112`, `m116`, `m153`,
`m1578`, `m192`, `m201`, `m2962`, `m3014`, `m351`, `m4928`, `m4964`) printed
every row they have in `level_10/soldiers.py`, the earlier sweep of this
level, and so appear nowhere below.

Conventions kept from every level below this one:

* numbers load from `game.db` -- the attack line is `Attack(vs=AC,
  printed=N)` exactly as printed, and the damage line is header data so an
  MM1 block can be rescaled to MM3 maths later;
* a trait costs no action, has no target, and arms once at the start of the
  fight, whatever the compendium's action column claims;
* a printed Requirement naming the creature's own kit is not a gate (#366)
  and is left off;
* "until the end of **its** next turn", naming the target rather than the
  attacker, is `EOTNT`; naming the attacker is the usual `EONT` default and
  needs no `until=` at all. Several cards here misprint the creature's own
  id for itself (a sibling ref, or a shortened one) in a duration or
  trigger line -- every row below is written against its own ref regardless.
* a close burst or blast naming no target set takes **enemies**, and only
  "creatures in the burst/blast" written outright takes everyone.

Four gaps this file is the first to need, confirmed absent before marking:

* **No parameter scopes a save penalty to one named condition's saves.**
  `c.penalty` takes no `against=`, so "a -2 penalty to saves against the
  immobilized condition" cannot be laid narrower than every save the
  creature makes. m2064a0.
* **`c.regeneration` has no suppression state to restore.** It is a bare
  heal-on-TurnStart watch with nothing tracking *why* it might currently be
  off, so "reactivates a different creature's inactive regeneration" has no
  flag to flip. m2068a3.
* **`Zones.aura` takes no `difficult=`.** `c.zone(difficult=True)` can make
  ground difficult but only `c.aura` follows its owner, so a *moving*
  "enemies treat the aura as difficult terrain" has no single call. Worked
  around below -- `c.aura` still returns a real `Zone` entity, and
  `Zone.difficult` is a plain mutable field on it -- so this is a workaround
  noted for the record, not a marker.
* **`crit_range` is read only off the attacker.** `resolve._mods` hardcodes
  `attacker` when it looks the bonus up, so "any attack roll **against**
  the target can score a critical on 18-20" -- a bonus that would have to
  sit on the far side of somebody else's attack -- has nowhere to land.
  m956a2.

Two old gaps this brief hits again: `Condition.DISEASED` (no disease track)
and `ConditionApplied.cancel` (the condition is already on by the time that
event fires, so nothing can refuse it the way a `ForcedMove` can).
"""

from __future__ import annotations

from combat_engine.content.monsters.level_02.soldiers_sa import (
    _HELPLESS,
    _armed,
    _is_attack,
    _recharge_when_bloodied,
    _ref_of,
)
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.soldiers_sa import (
    _adjacent_enemy_shifts,
    _adjacent_foe_looks_away,
    _marked_adjacent_shifts,
    _secondary,
)
from combat_engine.content.monsters.level_07.lurkers import _shift_beside
from combat_engine.content.monsters.level_07.soldiers import (
    _aura,
    _holding,
)
from combat_engine.content.monsters.level_07.soldiers_sa import (
    _marked_by_me_looks_away,
    _marked_within_looks_away,
    _marked_within_moves_away,
)
from combat_engine.content.monsters.level_09.soldiers_sa import _entered_flank_with_me
from combat_engine.content.monsters.level_10.soldiers import (
    SHAKEN_OFF,
    _beside,
    _drag_beside,
    _qualified_rider,
    _release,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
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
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Health,
    Initiative,
    Keyword,
    Melee,
    MeleeOrRanged,
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
    Window,
    World,
    get,
    power,
    spread,
)
from combat_engine.engine.components import Budget
from combat_engine.engine.events import (
    AttackDeclared,
    Bloodied,
    DamageApplied,
    DamageRolled,
    Dropped,
    Hit,
    Miss,
    MoveEnd,
    MoveStart,
    PowerUsed,
    SavingThrow,
    TurnEnd,
    TurnStart,
    ZoneExited,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    alive,
    creatures,
    distance_between,
    flanked_by,
    has_combat_advantage,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me, by_melee, targets_me
from combat_engine.engine.zones import Zone

#: "slowed and cannot shift" and friends -- a disease track this engine
#: does not have at all. Reused wherever a card's own escalation names one.
_NO_DISEASE = ("Condition.DISEASED",)

#: Acid, cold, fire, lightning, poison -- the five elemental resist riders
#: m3832a4 lets the creature pick between.
_M3832_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.POISON,
)

#: Acid, cold, fire, lightning, thunder -- what m5160a5 answers with resist.
_M5160_ELEMENTS = (
    DamageType.ACID,
    DamageType.COLD,
    DamageType.FIRE,
    DamageType.LIGHTNING,
    DamageType.THUNDER,
)


def _has_ongoing(c: Cast, who: int, dtype: DamageType) -> bool:
    """Is that creature currently carrying a burn of this one type."""
    for eff in c.world.effects.of(who):
        burn = getattr(eff, "ongoing", None)
        if not burn:
            continue
        types = getattr(eff, "ongoing_types", ()) or (burn[1],)
        if dtype in types:
            return True
    return False


def _double_turn(c: Cast) -> None:
    """An elite or solo acting twice a round: a spliced second initiative
    slot, the shape `m192a0` (a level below) already settled."""
    init = c.world.get(c.me, Initiative)
    if init is not None:
        c.extra_turn(init.rolled + 10)
    c.note(f"{c.ref}: it may take two immediate actions a round, one between turns")


#: Two creatures that each "gain combat advantage if an ally has it" and
#: have no other source of it ask each other, forever -- `has_combat_
#: advantage` reads a `gains_ca_when` modifier, which calls this closure
#: again for the asking creature's own ally. Shared across every row using
#: this shape so the second asker, not just the first, sees the pair already
#: in flight and answers False instead of recursing.
_RESOLVING_CA: set[tuple[int, int]] = set()


def _ca_synergy(c: Cast) -> None:
    """ "Gains combat advantage against an enemy if any of its allies has
    it too." `c.gains_advantage` asks the question every time the context
    is read, which is what a continuously-true trait like this wants."""
    me = c.me

    def shared(ctx: dict) -> bool:
        victim = ctx.get("target")
        if victim is None:
            return False
        for a in c.allies():
            key = (a, victim)
            if key in _RESOLVING_CA:
                continue
            _RESOLVING_CA.add(key)
            try:
                if has_combat_advantage(c.world, a, victim):
                    return True
            finally:
                _RESOLVING_CA.discard(key)
        return False

    c.gains_advantage(shared, until=When.ENCOUNTER, on=me)


def _grants_ca_until_it_swings(c: Cast, victim: int | None, *, on_miss_too: bool = False) -> None:
    """ "Grants combat advantage until it hits [or misses] the attacker."

    `c.grants_advantage` alone only answers the save-ends half; the early
    end on landing a blow back is the other half of the printed sentence
    and needs its own watch.
    """
    if victim is None:
        return
    hold = c.grants_advantage(until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return
    me = c.me

    def freed(ev: object) -> None:
        if getattr(ev, "attacker", None) == victim and getattr(ev, "target", None) == me:
            c.world.effects.end(hold, "it swung")

    c.watch(Hit, freed, until=When.SAVE_ENDS, on=me, once=True, label=f"{c.ref} freed-hit")
    if on_miss_too:
        c.watch(Miss, freed, until=When.SAVE_ENDS, on=me, once=True, label=f"{c.ref} freed-miss")


def _punish_departure(c: Cast, use_ref: str) -> None:
    """ "An enemy starts its turn adjacent but ends it not adjacent" --
    answered with a tracked set, since the two halves are asked a whole
    turn apart and a bare predicate cannot hold state between them."""
    me = c.me
    if not _armed(c, f"{c.ref} recharge"):
        _recharge_when_bloodied(c)
    was_adjacent: set[int] = set()

    def mark_start(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me:
            return
        if c.adjacent(ev.actor):
            was_adjacent.add(ev.actor)
        else:
            was_adjacent.discard(ev.actor)

    def check_end(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me:
            return
        if ev.actor in was_adjacent and not c.adjacent(ev.actor):
            was_adjacent.discard(ev.actor)
            c.shift(c.speed_of(me))
            c.use_power(use_ref, on=ev.actor, spend=False)

    c.watch(TurnStart, mark_start, until=When.ENCOUNTER, on=me, label=f"{c.ref} track")
    c.watch(TurnEnd, check_end, until=When.ENCOUNTER, on=me, label=f"{c.ref} punish")


def _racial_bloodied_attack_bonus(c: Cast, bonus: int) -> None:
    c.bonus(
        "attack",
        bonus,
        on=c.me,
        kind="racial",
        until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(c.me),
    )


def _difficult_aura(c: Cast, radius: int) -> None:
    """ "Enemies treat squares in the aura as difficult terrain."

    `c.aura` has no `difficult=` of its own -- the entity it returns is a
    plain `Zone` component, and `Zone.difficult` is a mutable field on it,
    so the workaround is to create the aura and then flip the field by
    hand. `ignores_difficult_in` is what keeps the caster's own side clear
    of its own ground.
    """
    zone_id = c.aura(radius, until=When.ENCOUNTER)
    zone = c.world.get(zone_id, Zone)
    if zone is not None:
        zone.difficult = True
    c.ignores_difficult_in(zone_id, side="team")


# ==========================================================================
# m1000
# ==========================================================================


@power(
    "m1000a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 6),
)
def m1000a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(3, dtype=DamageType.FORCE)
        c.mark()


@power(
    "m1000a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 1),
)
def m1000a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.flat(3, dtype=DamageType.FORCE)
        c.mark()


@power(
    "m1000a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FORCE],
)
def m1000a2(c: Cast) -> None:
    """ "Its weapons become energy, attacking Reflex instead of AC" --
    `AttackDeclared.vs` is a plain attribute read by `roll()` right after
    the event is emitted, the same lever AUTHORING logs for
    `AttackRolled.result`. A `window=BEFORE` watch swaps it before the die
    is cast, scoped to this creature's own weapon rows."""
    me = c.me

    def retarget(ev: AttackDeclared) -> None:
        if ev.attacker != me:
            return
        row = get(ev.power)
        if row is not None and Keyword.WEAPON in row.keywords:
            ev.vs = REF

    c.watch(
        AttackDeclared,
        retarget,
        until=When.SONT,
        on=me,
        window=Window.BEFORE,
        label=f"{c.ref} vs",
    )
    c.bonus("damage", 0, dice="1d10", dtype=DamageType.FORCE, on=me, until=When.SONT)


def _marked_adjacent_attacks_ally(world: World, me: int, ev: PowerUsed) -> bool:
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or not _is_attack(ev.power):
        return False
    if not world.relations.holds(Relation.MARKED_BY, me, actor):
        return False
    if distance_between(world, me, actor) > 1:
        return False
    return any(team(world, t) is team(world, me) for t in getattr(ev, "targets", ()))


@power(
    "m1000a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger="an adjacent enemy shifts or an adjacent enemy marked by it attacks an ally",
    on=[
        Trigger(MoveStart, when=_adjacent_enemy_shifts, text="an adjacent enemy shifts"),
        Trigger(
            PowerUsed,
            when=_marked_adjacent_attacks_ally,
            text="a marked adjacent enemy attacks an ally",
        ),
    ],
)
def m1000a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None:
        c.basic(on=foe)


@power("m1000a4", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1000a4(c: Cast) -> None:
    me = c.me

    def slid(ev: Hit) -> None:
        if ev.attacker == me and ev.critical:
            c.slide(1, on=ev.target)

    c.watch(Hit, slid, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m1087
# ==========================================================================


@power(
    "m1087a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 6),
)
def m1087a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m1087a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.POISON],
)
def m1087a1(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:2]:
        if _secondary(c, 17, AC, victim):
            c.damage("2d6", 6, on=victim)
            c.ongoing(5, DamageType.POISON, on=victim)


@power(
    "m1087a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=15),
)
def m1087a2(c: Cast) -> None:
    if c.strike():
        c.push(4)
        c.penalty("attack", 2, until=When.SAVE_ENDS)


@power(
    "m1087a3",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.SLEEP],
    attack=Attack(vs=WILL, printed=15),
)
def m1087a3(c: Cast) -> None:
    if c.strike():
        victim = c.target
        hold = c.unconscious(until=When.SAVE_ENDS)
        if hold is not None and victim is not None:

            def wake(ev: DamageApplied) -> None:
                if ev.target == victim:
                    c.world.effects.end(hold, "damage woke it")

            c.watch(
                DamageApplied,
                wake,
                until=When.SAVE_ENDS,
                on=victim,
                once=True,
                label=f"{c.ref} wake",
            )


@power(
    "m1087a4",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=15),
)
def m1087a4(c: Cast) -> None:
    """ "Must use a standard action on its next turn to attack its nearest
    ally, or loses its standard action" -- the compulsion is armed on the
    victim's own next `TurnStart` and spends its action directly: a basic
    attack if an ally is in melee reach, otherwise `Budget.standard` is
    zeroed by hand, the same field `actions.py` itself zeroes for a spent
    charge."""
    victim = c.target
    if not c.strike() or victim is None:
        return

    def compel(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != victim:
            return
        mate = next(
            (
                a
                for a in sorted(
                    creatures(c.world), key=lambda e: distance_between(c.world, victim, e)
                )
                if a != victim
                and team(c.world, a) is team(c.world, victim)
                and distance_between(c.world, victim, a) <= 1
            ),
            None,
        )
        if mate is not None:
            c.basic(who=victim, on=mate)
        else:
            budget = c.world.get(victim, Budget)
            if budget is not None:
                budget.standard = 0

    c.watch(TurnStart, compel, until=When.SONT, on=victim, once=True, label=f"{c.ref} charm")


@power(
    "m1087a5",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m1087a5(c: Cast) -> None:
    """Jumping as though it had a running start is already how `c.jump`
    works -- nothing gates it on one here -- and nothing in a fight rolls
    an Athletics check to jump distance for the +5 to have anything to add
    to, so neither half of this has a combat half to sit beside."""


@power("m1087a6", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1087a6(c: Cast) -> None:
    me = c.me

    def scorched(ev: DamageApplied) -> None:
        if ev.target == me and DamageType.RADIANT in ev.types():
            c.penalty("attack", 2, on=me, until=When.SONT)

    c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m1092
# ==========================================================================


@power(
    "m1092a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 6),
)
def m1092a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m1092a1", level=10, usage=AT_WILL, action=STANDARD, reach=Melee(2), target=NO_TARGET)
def m1092a1(c: Cast) -> None:
    """Up to four claws, no target more than twice. `Target` only ever
    offers distinct creatures, so the four swings are picked by hand."""
    hits: dict[int, int] = {}
    for _ in range(4):
        candidates = [f for f in c.enemies() if hits.get(f, 0) < 2]
        if not candidates:
            break
        victim = c.choose(sorted(candidates, key=c.distance), f"{c.ref}: which target")
        if victim is None:
            break
        if _secondary(c, 17, AC, victim):
            c.damage("2d8", 6, on=victim)
        hits[victim] = hits.get(victim, 0) + 1
    for victim, count in hits.items():
        if count >= 2:
            c.prone(on=victim)


@power(
    "m1092a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(1, within=10),
    target=EACH_ENEMY,
    attack=Attack(vs=FORT, printed=15),
)
def m1092a2(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED))


# ==========================================================================
# m1101
# ==========================================================================


@power(
    "m1101a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 5),
    dropped=("c.penalty(against=)",),
)
def m1101a0(c: Cast) -> None:
    """ "If the target is a living creature already immobilized, stunned,
    or unconscious, the bite deals an extra 2d6." The save-penalty half of
    this creature's own companion row names the same absent symbol; here
    it is the extra damage that plays."""
    victim = c.target
    already_held = (
        victim is not None
        and not c.is_kind("undead", on=victim)
        and any(c.is_(cond, on=victim) for cond in _HELPLESS)
    )
    if c.strike():
        c.hit()
        if already_held:
            c.damage("2d6", 0, on=victim)
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


@power(
    "m1101a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 6),
    dropped=("Target.kind",),
)
def m1101a1(c: Cast) -> None:
    """ "Target must be immobilized, stunned, or unconscious" -- `Target`
    filters on side, count and size and not on what a creature is
    suffering, so the restriction is enforced here instead."""
    victim = _restricted_to(c, 1, lambda f: any(c.is_(cond, on=f) for cond in _HELPLESS))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.stunned(until=When.SAVE_ENDS, on=victim)


# ==========================================================================
# m115863
# ==========================================================================


@power(
    "m115863a0", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET
)
def m115863a0(c: Cast) -> None:
    def eligible(who: int) -> bool:
        return (
            who in c.enemies()
            and not c.is_kind("undead", on=who)
            and not c.is_kind("construct", on=who)
        )

    def hold(who: int) -> Effect | None:
        return c.penalty("attack", 2, on=who, until=When.ENCOUNTER)

    _aura(c, 1, eligible, hold)


@power(
    "m115863a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 8),
)
def m115863a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)
        c.pull(2)
        c.grab()


@power(
    "m115863a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE, Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d12", 6, dtype=DamageType.NECROTIC),
    dropped=_NO_DISEASE,
)
def m115863a2(c: Cast) -> None:
    """The disease contraction at the encounter's end has no track to land
    on; the damage and burn play."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m115863a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 8, kind=LIMITED),
)
def m115863a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m115863a4",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(3),
    target=Target(side="enemy", count=1, label="creature grabbed by it"),
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("0", 10, dtype=DamageType.NECROTIC),
    dropped=("Target.kind",),
)
def m115863a4(c: Cast) -> None:
    held = _holding(c)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.heal(5, on=c.me)


# ==========================================================================
# m115893
# ==========================================================================


@power(
    "m115893a0", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET
)
def m115893a0(c: Cast) -> None:
    _difficult_aura(c, 2)


@power(
    "m115893a1", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET
)
def m115893a1(c: Cast) -> None:
    me = c.me

    def caught_fire(ev: DamageApplied) -> None:
        if ev.target == me and DamageType.FIRE in ev.types():
            c.ongoing(5, DamageType.FIRE, on=me)

    c.watch(DamageApplied, caught_fire, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m115893a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d12", 12),
)
def m115893a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m115893a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 7),
)
def m115893a3(c: Cast) -> None:
    if c.strike():
        c.hit()


def _enemy_moves_within(radius: int):  # noqa: ANN202
    def gate(world: World, me: int, ev: MoveStart) -> bool:
        actor = getattr(ev, "actor", None)
        if actor is None or actor == me or team(world, actor) is team(world, me):
            return False
        return distance_between(world, me, actor) <= radius

    return gate


@power(
    "m115893a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=13),
    trigger="an enemy within 2 squares of it moves",
    on=Trigger(MoveStart, when=_enemy_moves_within(2), text="an enemy within 2 squares moves"),
)
def m115893a4(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.grab(on=foe)


# ==========================================================================
# m1550
# ==========================================================================


@power(
    "m1550a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC),
)
def m1550a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.PSYCHIC)


@power(
    "m1550a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    keywords=[Keyword.PSYCHIC],
)
def m1550a1(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:2]:
        if _secondary(c, 17, AC, victim):
            c.damage("2d8", 5, dtype=DamageType.PSYCHIC, on=victim)
            c.ongoing(5, DamageType.PSYCHIC, on=victim)


@power(
    "m1550a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d12", 7, dtype=DamageType.PSYCHIC, half_on_miss=True),
)
def m1550a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.PSYCHIC)
    else:
        c.hit(half=True)


@power(
    "m1550a3",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, when=about_me, text="it is first bloodied"),
)
def m1550a3(c: Cast) -> None:
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m1550a2")
    c.use_power("m1550a2", spend=False)


@power("m1550a4", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m1550a4(c: Cast) -> None:
    me = c.me

    def burning(ctx: dict) -> bool:
        victim = ctx.get("target")
        return victim is not None and _has_ongoing(c, victim, DamageType.PSYCHIC)

    c.bonus("attack", 2, on=me, until=When.ENCOUNTER, when=burning)
    c.bonus("damage", 5, on=me, until=When.ENCOUNTER, when=burning)


# ==========================================================================
# m2025
# ==========================================================================


@power(
    "m2025a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 4),
)
def m2025a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EOTNT)


@power(
    "m2025a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 4, dtype=DamageType.NECROTIC),
)
def m2025a1(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        conds = [Condition.IMMOBILIZED]
        if victim is not None and c.marked(on=victim, by=c.me):
            conds.append(Condition.DAZED)
        c.condition(*conds, until=When.EOTNT)


_M2025_KILLS = (DamageType.FIRE, DamageType.RADIANT)


@power(
    "m2025a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m2025a2(c: Cast) -> None:
    """Refusing to die unless the killing blow is fire or radiant -- the
    `m1578a2` shape (a level below) settled this for a different kill
    pair; here it is this creature's own."""
    me = c.me
    down = f"{c.ref} down"
    c.revives_unless(*_M2025_KILLS, on=me)

    def get_up() -> None:
        health = c.world.get(me, Health)
        if health is not None and alive(c.world, me) and health.hp < 15:
            c.heal(15 - health.hp, on=me)

    def falls(ev: Dropped) -> None:
        if ev.actor != me:
            return
        damaged = next(
            (
                past
                for past in reversed(c.world.bus.log[: ev.seq])
                if getattr(past, "target", None) == me and hasattr(past, "dtype")
            ),
            None,
        )
        if damaged is not None and getattr(damaged, "dtype", None) in _M2025_KILLS:
            return
        c.heal(1, on=me)
        if any(eff.label == down for eff in c.world.effects.of(me)):
            return
        c.prone(on=me)
        hold = c.world.effects.apply(
            me, me, When.SONT, label=down, conditions=(Condition.UNCONSCIOUS,)
        )
        hold.on_end.append(get_up)

    c.watch(Dropped, falls, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m2052
# ==========================================================================


@power(
    "m2052a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("4d4", 5),
)
def m2052a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


def _looked_away_in_reach(radius: int):  # noqa: ANN202
    def gate(world: World, me: int, ev: PowerUsed) -> bool:
        actor = getattr(ev, "actor", None)
        if actor is None or actor == me or not _is_attack(ev.power):
            return False
        if team(world, actor) is team(world, me):
            return False
        if me in getattr(ev, "targets", ()):
            return False
        return distance_between(world, me, actor) <= radius

    return gate


@power(
    "m2052a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 5),
    trigger="an enemy within reach makes an attack that doesn't include it",
    on=Trigger(
        PowerUsed, when=_looked_away_in_reach(2), text="an enemy within reach attacks without it"
    ),
)
def m2052a1(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


@power(
    "m2052a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("4d4", 5),
)
def m2052a2(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            me = c.me

            def shifted(ev: MoveStart) -> None:
                if getattr(ev, "actor", None) != victim:
                    return
                c.basic(who=me, on=victim)

            c.watch(MoveStart, shifted, until=When.EONT, on=me, once=True, label=f"{c.ref} punish")


@power("m2052a3", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m2052a3(c: Cast) -> None:
    c.bonus(
        "attack",
        2,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: c.bloodied(ctx.get("target")),
    )


# ==========================================================================
# m2064
# ==========================================================================


@power(
    "m2064a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d12", 4),
    dropped=("c.penalty(against=)",),
)
def m2064a0(c: Cast) -> None:
    """ "The target takes a -2 penalty to saving throws against the
    immobilized condition" has no narrower penalty than every save the
    target makes to aim at; the extra damage half plays."""
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None and c.is_(Condition.IMMOBILIZED, on=victim):
            c.damage("3d6", 0, dtype=DamageType.PSYCHIC)


@power(
    "m2064a1",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=Target(side="enemy", count=1, max_size=Size.MEDIUM),
    attack=Attack(vs=FORT, printed=15),
)
def m2064a1(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


@power("m2064a2", level=10, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=SELF)
def m2064a2(c: Cast) -> None:
    c.mode("fly", 5, until=When.EOT, on=c.me)


# ==========================================================================
# m2067
# ==========================================================================


@power(
    "m2067a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 5),
)
def m2067a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m2067a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    charges=True,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d8", 5, kind=LIMITED),
)
def m2067a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power("m2067a2", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m2067a2(c: Cast) -> None:
    me = c.me

    def floored(ev: Hit) -> None:
        if ev.attacker == me and getattr(ev, "charge", False):
            c.prone(on=ev.target)

    c.watch(Hit, floored, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m2068
# ==========================================================================


@power(
    "m2068a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d6", 5),
)
def m2068a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", 0, dtype=DamageType.POISON)


@power(
    "m2068a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d6", 5),
)
def m2068a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", 0, dtype=DamageType.POISON)


@power(
    "m2068a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d6", 0, dtype=DamageType.ACID),
)
def m2068a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2068a3",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=NO_TARGET,
    todo=("c.regeneration(suppressed_by=)",),
)
def m2068a3(c: Cast) -> None:
    """ "Reactivates" a different m2068's regeneration -- `c.regeneration`
    is a bare heal-on-turn-start watch with no notion of being currently
    off, so there is no flag anywhere for this to flip."""


_M2068_KILLS = (DamageType.ACID, DamageType.FIRE)


@power(
    "m2068a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m2068a4(c: Cast) -> None:
    me = c.me
    down = f"{c.ref} down"
    c.revives_unless(*_M2068_KILLS, on=me)

    def get_up() -> None:
        health = c.world.get(me, Health)
        if health is not None and alive(c.world, me) and health.hp < 10:
            c.heal(10 - health.hp, on=me)

    def falls(ev: Dropped) -> None:
        if ev.actor != me:
            return
        damaged = next(
            (
                past
                for past in reversed(c.world.bus.log[: ev.seq])
                if getattr(past, "target", None) == me and hasattr(past, "dtype")
            ),
            None,
        )
        if damaged is not None and getattr(damaged, "dtype", None) in _M2068_KILLS:
            return
        c.heal(1, on=me)
        if any(eff.label == down for eff in c.world.effects.of(me)):
            return
        c.prone(on=me)
        hold = c.world.effects.apply(
            me, me, When.SONT, label=down, conditions=(Condition.UNCONSCIOUS,)
        )
        hold.on_end.append(get_up)

    c.watch(Dropped, falls, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m2087
# ==========================================================================


@power(
    "m2087a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 6),
)
def m2087a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2087a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
)
def m2087a1(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:2]:
        if _secondary(c, 15, AC, victim):
            c.damage("2d6", 5, on=victim)
            c.slide(2, on=victim)


@power(
    "m2087a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m2087a2(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None:
            mates = [a for a in c.allies() if a != c.me and c.adjacent_to(victim, a)]
            mate = c.choose(sorted(mates), f"{c.ref}: which ally") if mates else None
            if mate is not None:
                c.bonus("damage", 4, on=mate, until=When.EOT, once=True)
                c.basic(who=mate, on=victim)


@power(
    "m2087a3",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.HEALING],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 6, kind=LIMITED),
)
def m2087a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.heal(15, on=c.me)
    mates = [a for a in c.allies() if a != c.me and c.distance(a) <= 5]
    mate = c.choose(sorted(mates), f"{c.ref}: which ally") if mates else None
    if mate is not None:
        c.heal(15, on=mate)


@power(
    "m2087a4",
    level=10,
    usage=ENCOUNTER,
    action=MOVE,
    reach=Ranged(10),
    target=ONE_ALLY,
)
def m2087a4(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        c.extra_action(cost=MOVE, on=victim)


@power(
    "m2087a5",
    level=10,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    dropped=("c.escape(as_power=)",),
)
def m2087a5(c: Cast) -> None:
    """The shift-to-another-adjacent-square half is written; the half that
    lets this same row double as an escape attempt with its own +2 has no
    way to graft itself onto `c.escape`."""
    foes = [f for f in c.enemies() if c.adjacent(f)]
    foe = c.choose(sorted(foes), f"{c.ref}: which enemy") if foes else None
    if foe is None:
        return
    options = _beside(c, c.me, foe)
    if options:
        where = c.world.decide(c.me, "shift", options, f"{c.ref}: where")
        c.shift(1, to=where)


# ==========================================================================
# m2092
# ==========================================================================


@power(
    "m2092a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d12", 6),
)
def m2092a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(2)
        c.grab()


@power("m2092a1", level=10, usage=AT_WILL, action=STANDARD, reach=Melee(3), target=UpTo(2))
def m2092a1(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:2]:
        if _secondary(c, 15, AC, victim):
            c.damage("2d6", 5, on=victim)
            c.grab(on=victim)


@power(
    "m2092a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d12", 6),
    dropped=("Target.kind", *_NO_DISEASE),
)
def m2092a2(c: Cast) -> None:
    victim = _restricted_to(c, 1, lambda f: any(c.is_(cond, on=f) for cond in _HELPLESS))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.ongoing(10, DamageType.NECROTIC, on=victim)


@power("m2092a3", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m2092a3(c: Cast) -> None:
    me = c.me
    hold = c.bonus("stealth", 5, on=me, until=When.ENCOUNTER)

    def stop(ev: MoveEnd) -> None:
        if ev.actor == me and hold is not None:
            c.world.effects.end(hold, "it moved")

    c.watch(MoveEnd, stop, until=When.ENCOUNTER, on=me, label=f"{c.ref} watch")


# ==========================================================================
# m2254
# ==========================================================================


@power(
    "m2254a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d6", 6),
)
def m2254a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.EOTNT)
        c.ongoing(5, DamageType.FIRE)


@power(
    "m2254a1",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 4, dtype=DamageType.FIRE),
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, when=about_me, text="it drops to 0 hit points"),
)
def m2254a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power("m2254a2", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m2254a2(c: Cast) -> None:
    c.bonus(
        "damage",
        5,
        dtype=DamageType.FIRE,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: (
            bool(ctx.get("target")) and c.is_(Condition.IMMOBILIZED, on=ctx.get("target"))
        ),
    )


# ==========================================================================
# m2784
# ==========================================================================


@power(
    "m2784a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 5),
)
def m2784a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark(until=When.EOTNT)


@power(
    "m2784a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
)
def m2784a1(c: Cast) -> None:
    if not c.first:
        return
    hits: dict[int, int] = {}
    for victim in c.targets[:2]:
        if _secondary(c, 15, AC, victim):
            c.damage("1d10", 5, on=victim)
            c.mark(on=victim, until=When.EOTNT)
            hits[victim] = hits.get(victim, 0) + 1
    for victim, count in hits.items():
        if count >= 2:
            c.prone(on=victim)


@power(
    "m2784a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON],
    requires=lambda world, eid: (lambda h: h is not None and h.bloodied)(world.get(eid, Health)),
    requires_text="usable only while bloodied",
)
def m2784a2(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        c.basic(on=victim)
    c.heal(53, on=c.me)


@power("m2784a3", level=10, usage=ENCOUNTER, action=MINOR, reach=PERSONAL, target=NO_TARGET)
def m2784a3(c: Cast) -> None:
    for ally in c.allies():
        if c.is_kind("orc", on=ally) and c.can_see(ally):
            c.restore_use("m2784a2", on=ally)


@power(
    "m2784a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_ALLY,
)
def m2784a4(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    near = sorted(c.enemies(), key=lambda f: distance_between(c.world, mate, f))
    foe = c.choose(near, f"{c.ref}: which enemy charges") if near else None
    if foe is not None:
        c.charge_at(foe, who=mate)


# ==========================================================================
# m3273
# ==========================================================================


@power(
    "m3273a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 5),
)
def m3273a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", 0, dtype=DamageType.POISON)
        c.mark(until=When.EOTNT)


@power(
    "m3273a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 5),
)
def m3273a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", 0, dtype=DamageType.POISON)
        c.mark(until=When.EOTNT)
        c.condition(Condition.IMMOBILIZED, until=When.EOTNT)


@power(
    "m3273a2",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(3),
    target=Target(side="enemy", count=1, label="creature marked by it"),
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=FORT, printed=13),
    dropped=("Target.kind", *_NO_DISEASE),
)
def m3273a2(c: Cast) -> None:
    victim = _restricted_to(c, 3, lambda f: c.marked(on=f, by=c.me))
    if victim is None:
        return
    c.strike(on=victim)


@power("m3273a3", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3273a3(c: Cast) -> None:
    c.bonus(
        "damage",
        0,
        dice="1d6",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: (
            bool(ctx.get("target"))
            and not ctx.get("ranged")
            and c.bloodied(ctx.get("target"))
            and c.marked(on=ctx.get("target"), by=c.me)
        ),
    )


# ==========================================================================
# m3335
# ==========================================================================


@power(
    "m3335a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 8),
)
def m3335a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power("m3335a1", level=10, usage=AT_WILL, action=STANDARD, reach=Melee(1), target=UpTo(2))
def m3335a1(c: Cast) -> None:
    if not c.first:
        return
    hits: dict[int, int] = {}
    for victim in c.targets[:2]:
        if _secondary(c, 17, AC, victim):
            c.damage("1d10", 8, on=victim)
            hits[victim] = hits.get(victim, 0) + 1
    for count in hits.values():
        if count >= 2:
            c.restore_use("m3335a2", on=c.me)


@power(
    "m3335a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 3, kind=LIMITED),
)
def m3335a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)
        c.mark()


@power(
    "m3335a3",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    trigger="it is struck in combat",
    on=Trigger(Hit, when=targets_me, text="it is struck in combat"),
)
def m3335a3(c: Cast) -> None:
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is not None:
        c.ongoing(5, DamageType.FIRE, on=attacker)


# ==========================================================================
# m3795
# ==========================================================================


@power(
    "m3795a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 4),
)
def m3795a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m3795a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=Target(side="enemy", count=1, label="creature grabbed by it"),
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 4),
    dropped=("Target.kind",),
)
def m3795a1(c: Cast) -> None:
    held = _holding(c)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.ongoing(5, on=victim)


@power("m3795a2", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3795a2(c: Cast) -> None:
    c.threatens(2)


_M3795_KILLS = (DamageType.ACID, DamageType.FIRE)


@power(
    "m3795a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m3795a3(c: Cast) -> None:
    me = c.me
    down = f"{c.ref} down"
    c.revives_unless(*_M3795_KILLS, on=me)

    def get_up() -> None:
        health = c.world.get(me, Health)
        if health is not None and alive(c.world, me) and health.hp < 10:
            c.heal(10 - health.hp, on=me)

    def falls(ev: Dropped) -> None:
        if ev.actor != me:
            return
        damaged = next(
            (
                past
                for past in reversed(c.world.bus.log[: ev.seq])
                if getattr(past, "target", None) == me and hasattr(past, "dtype")
            ),
            None,
        )
        if damaged is not None and getattr(damaged, "dtype", None) in _M3795_KILLS:
            return
        c.heal(1, on=me)
        if any(eff.label == down for eff in c.world.effects.of(me)):
            return
        c.prone(on=me)
        hold = c.world.effects.apply(
            me, me, When.SONT, label=down, conditions=(Condition.UNCONSCIOUS,)
        )
        hold.on_end.append(get_up)

    c.watch(Dropped, falls, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m3832
# ==========================================================================


@power(
    "m3832a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 5),
)
def m3832a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3832a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 5),
)
def m3832a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        for ally in c.allies():
            c.bonus("attack", 2, on=ally, until=When.EONT)


@power(
    "m3832a2",
    level=10,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d6", 4, dtype=DamageType.FIRE),
)
def m3832a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3832a3",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=10),
)
def m3832a3(c: Cast) -> None:
    if c.strike():
        c.stunned(until=When.EONT)


@power(
    "m3832a4",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy hits or misses this creature",
    on=[
        Trigger(Hit, when=targets_me, text="an enemy hits this creature"),
        Trigger(Miss, when=targets_me, text="an enemy misses this creature"),
    ],
)
def m3832a4(c: Cast) -> None:
    dtype = c.choose(list(_M3832_ELEMENTS), f"{c.ref}: which energy")
    if dtype is not None:
        c.resist(5, dtype, on=c.me, until=When.ENCOUNTER)


@power("m3832a5", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3832a5(c: Cast) -> None:
    _racial_bloodied_attack_bonus(c, 1)


@power("m3832a6", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3832a6(c: Cast) -> None:
    me = c.me

    def floored(ev: Hit) -> None:
        if ev.attacker == me and getattr(ev, "opportunity", False):
            c.prone(on=ev.target)

    c.watch(Hit, floored, until=When.ENCOUNTER, on=me, label=c.ref)


@power("m3832a7", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m3832a7(c: Cast) -> None:
    me = c.me

    def alone(ctx: dict) -> bool:
        return _melee_ctx(ctx) and len([f for f in c.enemies() if c.adjacent(f)]) == 1

    c.bonus("attack", 2, on=me, until=When.ENCOUNTER, when=alone)


def _melee_ctx(ctx: dict) -> bool:
    """Is the attack this modifier is being read for a melee one?"""
    row = get(ctx.get("power") or "")
    if row is None or row.reach is None:
        return False
    branch = ctx.get("branch", 0)
    reach = row.reach_of(branch) if hasattr(row, "reach_of") else row.reach
    return getattr(reach, "kind", "") == "melee"


# ==========================================================================
# m4003
# ==========================================================================


@power(
    "m4003a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 5),
)
def m4003a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m4003a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10", 7),
)
def m4003a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m4003a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m4003a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.maximise(on=c.me, until=When.EOT, critical=True)
    c.basic(on=victim)


def _missed_me_melee(world: World, me: int, ev: Miss) -> bool:
    return getattr(ev, "target", None) == me and by_melee(world, me, ev)


@power(
    "m4003a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d4", 4),
    trigger="an enemy misses it with a melee attack",
    on=Trigger(Miss, when=_missed_me_melee, text="an enemy misses it with a melee attack"),
)
def m4003a3(c: Cast) -> None:
    attacker = getattr(c.trigger, "attacker", None)
    me = c.me
    if attacker is not None and c.strike(on=attacker):
        c.hit(on=attacker)
        c.grab(on=attacker)

        def tick(ev: TurnStart) -> None:
            if ev.ghost or ev.actor != attacker or attacker not in _holding(c):
                return
            c.flat(5, on=attacker)

        c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} grip {attacker}")


@power(
    "m4003a4",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 5),
)
def m4003a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power("m4003a5", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4003a5(c: Cast) -> None:
    me = c.me

    def felled(ev: Dropped) -> None:
        if ev.actor == me:
            c.grant_action_point(1, on=me)

    c.watch(Dropped, felled, until=When.ENCOUNTER, on=me, once=True, label=c.ref)


# ==========================================================================
# m4007
# ==========================================================================


@power(
    "m4007a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=20),
    damage=Damage("1d10", 5),
)
def m4007a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power("m4007a1", level=10, usage=AT_WILL, action=STANDARD, reach=Melee(2), target=UpTo(2))
def m4007a1(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:2]:
        if _secondary(c, 20, AC, victim):
            c.damage("1d10", 5, on=victim)
            c.mark(on=victim)


@power(
    "m4007a2",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    target=Target(side="enemy", count=1, label="creature grabbed by it"),
    reach=Melee(2),
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("1d8", 4, dtype=DamageType.POISON),
    dropped=("Target.kind",),
)
def m4007a2(c: Cast) -> None:
    held = _holding(c)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim)


@power(
    "m4007a3",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=14),
)
def m4007a3(c: Cast) -> None:
    if c.strike():
        c.slide(3)
        c.grab()


def _ally_dropped_within(radius: int):  # noqa: ANN202
    def gate(world: World, me: int, ev: Dropped) -> bool:
        actor = getattr(ev, "actor", None)
        if actor is None or actor == me or team(world, actor) is not team(world, me):
            return False
        return distance_between(world, me, actor) <= radius

    return gate


@power(
    "m4007a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
    trigger="an ally within 5 squares of it drops to 0 hit points",
    on=Trigger(Dropped, when=_ally_dropped_within(5), text="an ally within 5 squares drops to 0"),
)
def m4007a4(c: Cast) -> None:
    c.heal(15, on=c.me)


# ==========================================================================
# m4144
# ==========================================================================


@power(
    "m4144a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 6),
)
def m4144a0(c: Cast) -> None:
    if c.strike():
        c.hit()


def _adjacent_enemy_moves(world: World, me: int, ev: MoveStart) -> bool:
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or team(world, actor) is team(world, me):
        return False
    return distance_between(world, me, actor) <= 1


def _not_flying(world: World, eid: int) -> bool:
    from combat_engine.engine.query import moving_as

    return not moving_as(world, eid, "fly")


@power(
    "m4144a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d8", 6),
    requires=_not_flying,
    requires_text="it must not be flying",
    trigger="an adjacent enemy shifts or moves into a nonadjacent square",
    on=Trigger(MoveStart, when=_adjacent_enemy_moves, text="an adjacent enemy moves"),
)
def m4144a1(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.prone(on=foe)


@power(
    "m4144a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("ConditionApplied.cancel",),
)
def m4144a2(c: Cast) -> None:
    """The forced-move half -- one square less -- is real. The half that
    lets it or its rider save against being knocked prone has nothing to
    interrupt: `ConditionApplied` fires after the condition is already on,
    the same gap `m1937a3` (a level below) already names."""
    me = c.me

    def qualified(_ctx: dict) -> bool:
        rider = c.rider()
        if rider is None:
            return False
        stats = c.world.get(rider, Stats)
        return stats is not None and stats.level >= 10

    c.resist_forced(1, on=me, until=When.ENCOUNTER, when=qualified)


# ==========================================================================
# m4265
# ==========================================================================


@power(
    "m4265a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 6),
)
def m4265a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m4265a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 6),
)
def m4265a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4265a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 6, half_on_miss=True),
)
def m4265a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)
        c.grants_advantage(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m4265a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
)
def m4265a3(c: Cast) -> None:
    first_opts = sorted(c.enemies(), key=c.distance)
    v1 = c.choose(first_opts, f"{c.ref}: first target") if first_opts else None
    if v1 is not None and _secondary(c, 17, AC, v1):
        c.damage("1d10", 6, on=v1)
    c.shift(2)
    remaining = [f for f in c.enemies() if f != v1]
    v2 = (
        c.choose(sorted(remaining, key=c.distance), f"{c.ref}: second target")
        if remaining
        else None
    )
    if v2 is not None and _secondary(c, 17, AC, v2):
        c.damage("2d6", 6, on=v2)


def _hit_me_melee(world: World, me: int, ev: Hit) -> bool:
    return getattr(ev, "target", None) == me and by_melee(world, me, ev)


@power(
    "m4265a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10", 6),
    trigger="it is hit by a melee attack",
    on=Trigger(Hit, when=_hit_me_melee, text="it is hit by a melee attack"),
)
def m4265a4(c: Cast) -> None:
    attacker = getattr(c.trigger, "attacker", None)
    if attacker is not None and c.strike(on=attacker):
        c.hit(on=attacker)
        c.dazed(on=attacker)


@power("m4265a5", level=10, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=SELF)
def m4265a5(c: Cast) -> None:
    c.phasing(until=When.EOT, on=c.me)
    c.shift(c.speed_of(c.me))


@power("m4265a6", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4265a6(c: Cast) -> None:
    c.bonus(
        "damage",
        0,
        dice="1d8",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: (
            bool(ctx.get("target")) and has_combat_advantage(c.world, c.me, ctx.get("target"))
        ),
    )


# ==========================================================================
# m4268
# ==========================================================================


@power(
    "m4268a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 7),
)
def m4268a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m4268a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 7),
    trigger="an enemy marked by it makes an attack that does not include it",
    on=Trigger(PowerUsed, when=_marked_by_me_looks_away, text="a marked enemy attacks without it"),
)
def m4268a1(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.push(1, on=foe)


@power(
    "m4268a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=14),
    damage=Damage("2d8", 5),
)
def m4268a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4268a3",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, when=about_me, text="it is first bloodied"),
)
def m4268a3(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    choice = c.choose(["attack", "shift"], f"{c.ref}: {mate}")
    if choice == "attack":
        near = sorted(
            (f for f in c.enemies() if c.adjacent_to(mate, f)),
            key=lambda f: distance_between(c.world, mate, f),
        )
        foe = c.choose(near, f"{c.ref}: {mate}'s target") if near else None
        if foe is not None:
            c.basic(who=mate, on=foe)
    else:
        c.shift(3, who=mate)


@power("m4268a4", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m4268a4(c: Cast) -> None:
    c.bonus(
        AC,
        2,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: any(
            _ref_of(c, a) in ("m4268", "m4267") for a in c.allies() if c.adjacent(a)
        ),
    )


# ==========================================================================
# m5160
# ==========================================================================


@power("m5160a0", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5160a0(c: Cast) -> None:
    c.regeneration(5, until=When.ENCOUNTER, on=c.me)


@power(
    "m5160a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("4d6", 4),
)
def m5160a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grab()


@power(
    "m5160a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("4d6", 4),
)
def m5160a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(3)


@power(
    "m5160a3",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(2),
    target=Target(side="enemy", count=1, label="creature grabbed by it"),
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d10", 7),
    dropped=("Target.kind",),
)
def m5160a3(c: Cast) -> None:
    """ "Cannot escape the grab until it saves against this effect" is not
    modelled -- the grab and the restrained hold stay two independent
    things, which is the more generous reading rather than a stingier one."""
    held = _holding(c)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.condition(
            Condition.RESTRAINED, until=When.SAVE_ENDS, on=victim, ongoing=(10, DamageType.UNTYPED)
        )
    else:
        c.restore_use(c.ref, on=c.me)


@power(
    "m5160a4",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_CREATURE,
    attack=Attack(vs=REF, printed=13),
)
def m5160a4(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(10, DamageType.UNTYPED))


@power(
    "m5160a5",
    level=10,
    usage=ENCOUNTER,
    uses=2,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it takes acid, cold, fire, lightning, or thunder damage",
    on=Trigger(
        DamageApplied,
        when=targets_me,
        text="it takes acid, cold, fire, lightning, or thunder damage",
    ),
)
def m5160a5(c: Cast) -> None:
    dealt = [t for t in _M5160_ELEMENTS if t in c.trigger.types()]
    if dealt:
        c.resist(10, dealt[0], on=c.me, until=When.ENCOUNTER)


# ==========================================================================
# m5331
# ==========================================================================


@power(
    "m5331a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 7),
)
def m5331a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m5331a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 6),
)
def m5331a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power("m5331a2", level=10, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m5331a2(c: Cast) -> None:
    for _ in range(2):
        near = sorted(c.enemies(), key=c.distance)
        victim = c.choose(near, f"{c.ref}: which target") if near else None
        if victim is not None:
            c.basic(on=victim)


@power(
    "m5331a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
)
def m5331a3(c: Cast) -> None:
    if c.first and not _armed(c, f"{c.ref} recharge"):
        _recharge_when_bloodied(c)
    c.mark()


@power(
    "m5331a4",
    level=10,
    usage=AT_WILL,
    action=OPPORTUNITY,
    reach=Melee(2),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 5),
    trigger="an enemy marked by it and within 2 squares moves",
    on=Trigger(
        MoveStart, when=_marked_within_moves_away(2), text="a marked enemy within 2 squares moves"
    ),
)
def m5331a4(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
    c.shift(1)


# ==========================================================================
# m5434
# ==========================================================================


@power(
    "m5434a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    damage=Damage("2d10", 6),
    attack=Attack(vs=AC, printed=15),
)
def m5434a0(c: Cast) -> None:
    victim = c.target
    bonus = 10 if (victim is not None and victim in _holding(c)) else 6
    if c.strike():
        c.damage("2d10", bonus)


@power(
    "m5434a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("4d6", 5),
    dropped=("Target.kind",),
)
def m5434a1(c: Cast) -> None:
    """ "While it has a creature grabbed, it can attack only with bite,
    which it must use against the grabbed creature" -- enforced on the
    target the way every other restriction `Target` cannot carry is."""
    held = _holding(c)
    victim = (
        c.target if not held else (c.target if c.target in held else next(iter(sorted(held)), None))
    )
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        _drag_beside(c, victim, c.me, 2)
        for prev in _holding(c):
            if prev != victim:
                _release(c, prev)
        c.grab(on=victim)


def _ridden_by_qualified(world: World, eid: int) -> bool:
    for rider in world.relations.sources(Relation.RIDDEN_BY, eid):
        stats = world.get(rider, Stats)
        if stats is not None and stats.level >= 10:
            return True
    return False


@power(
    "m5434a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    charges=True,
    requires=_ridden_by_qualified,
    requires_text="it must be mounted by a friendly rider of 10th level or higher",
)
def m5434a2(c: Cast) -> None:
    for victim in c.overrun():
        if victim in c.enemies():
            c.push(1, on=victim)
            c.prone(on=victim)
    rider = _qualified_rider(c)
    if rider is not None:
        near = sorted(c.enemies(), key=lambda f: distance_between(c.world, rider, f))
        foe = c.choose(near, f"{c.ref}: rider's target") if near else None
        if foe is not None:
            c.basic(who=rider, on=foe)


# ==========================================================================
# m5495
# ==========================================================================


@power(
    "m5495a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("4d6", 4),
)
def m5495a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5495a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 6),
)
def m5495a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d8", 3, dtype=DamageType.PSYCHIC)
        c.mark()


@power(
    "m5495a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 4),
)
def m5495a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m5495a3", level=10, usage=AT_WILL, action=STANDARD, reach=PERSONAL, target=NO_TARGET)
def m5495a3(c: Cast) -> None:
    branch = c.choose(["melee", "ranged"], f"{c.ref}: which combo") or "melee"
    near = sorted(c.enemies(), key=c.distance)
    if branch == "melee":
        v1 = c.choose(near, f"{c.ref}: first target") if near else None
        if v1 is not None:
            c.use_power("m5495a1", on=v1, spend=False)
        v2 = c.choose(near, f"{c.ref}: second target") if near else None
        if v2 is not None:
            c.use_power("m5495a0", on=v2, spend=False)
    else:
        for _ in range(2):
            v = c.choose(near, f"{c.ref}: target") if near else None
            if v is not None:
                c.use_power("m5495a2", on=v, spend=False)


@power(
    "m5495a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5495a4(c: Cast) -> None:
    c.no_provoke(until=When.EOT, on=c.me)
    c.jump(4)
    near = sorted(c.enemies(), key=c.distance)
    v1 = c.choose(near, f"{c.ref}: first target") if near else None
    if v1 is not None:
        c.use_power("m5495a1", on=v1, spend=False)
        if c.landed:
            c.slide(3, on=v1)
    c.jump(3)
    near = sorted(c.enemies(), key=c.distance)
    v2 = c.choose(near, f"{c.ref}: second target") if near else None
    if v2 is not None:
        c.use_power("m5495a1", on=v2, spend=False)


@power(
    "m5495a5",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("4d6", 4, dtype=DamageType.PSYCHIC),
)
def m5495a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m5495a6",
    level=10,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5495a6(c: Cast) -> None:
    if not _armed(c, f"{c.ref} recharge"):
        _recharge_when_bloodied(c)
    c.no_provoke(until=When.EOT, on=c.me)
    c.jump(7)


def _marked_adjacent_attacks_or_moves(world: World, me: int, ev: object) -> bool:
    if isinstance(ev, MoveStart):
        return _marked_adjacent_shifts(world, me, ev)
    return _marked_within_looks_away(1)(world, me, ev)


@power(
    "m5495a7",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d6", 3),
    trigger="an adjacent marked enemy moves, shifts, or attacks without including it",
    on=[
        Trigger(MoveStart, when=_marked_adjacent_shifts, text="an adjacent marked enemy shifts"),
        Trigger(
            PowerUsed,
            when=_marked_within_looks_away(1),
            text="an adjacent marked enemy attacks without it",
        ),
    ],
)
def m5495a7(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)
        c.prone(on=foe)
        c.slowed(on=foe)


# ==========================================================================
# m5541
# ==========================================================================


@power("m5541a0", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5541a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER)

    def gnaw(ev: TurnStart) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.actor not in c.world.zones.occupants(ring):
            return
        c.slowed(on=ev.actor, until=When.SOTNT)

    c.watch(TurnStart, gnaw, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5541a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d8", 5),
)
def m5541a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5541a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 9),
    dropped=("Target.kind",),
)
def m5541a2(c: Cast) -> None:
    victim = _restricted_to(c, 1, lambda f: c.is_(Condition.DAZED, on=f))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.damage("3d8", 0, dtype=DamageType.PSYCHIC, on=victim)
        c.mark(until=When.SAVE_ENDS, on=victim)


@power(
    "m5541a3",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=13),
)
def m5541a3(c: Cast) -> None:
    if c.strike():
        c.dazed(until=When.SONT)


@power(
    "m5541a4",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.POISON],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("3d8", 9, dtype=DamageType.NECROTIC),
    trigger="it is first bloodied",
    on=Trigger(Bloodied, when=about_me, text="it is first bloodied"),
    dropped=("Damage(dtypes=)",),
)
def m5541a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)


# ==========================================================================
# m5549
# ==========================================================================


@power(
    "m5549a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d12", 5),
)
def m5549a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5549a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d8", 7, dtype=DamageType.PSYCHIC),
)
def m5549a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(2)
    c.mark()


@power(
    "m5549a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(5),
    target=NO_TARGET,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=13),
    trigger="an enemy marked by and within 5 squares of it attacks without including it",
    on=Trigger(
        PowerUsed,
        when=_marked_within_looks_away(5),
        text="a marked enemy within 5 squares attacks without it",
    ),
)
def m5549a2(c: Cast) -> None:
    actor = getattr(c.trigger, "actor", None)
    if actor is None:
        return
    c.penalty("attack", 2, on=actor, until=When.INSTANT)
    c.dazed(until=When.SAVE_ENDS, on=actor)


# ==========================================================================
# m5660
# ==========================================================================


@power(
    "m5660a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d12", 5),
)
def m5660a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m5660a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    damage=Damage("3d12", 5, kind=LIMITED),
    attack=Attack(vs=AC, printed=15),
)
def m5660a1(c: Cast) -> None:
    victim = c.target
    bonus = 10 if (victim is not None and c.bloodied(victim)) else 5
    if c.strike():
        c.damage("3d12", bonus)
        c.mark()


@power(
    "m5660a2",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=ONE_ALLY,
)
def m5660a2(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    choice = c.choose(["charge", "attack"], f"{c.ref}: {mate}")
    if choice == "charge":
        near = sorted(c.enemies(), key=lambda f: distance_between(c.world, mate, f))
        foe = c.choose(near, f"{c.ref}: which enemy") if near else None
        if foe is not None:
            c.charge_at(foe, who=mate)
    else:
        near = sorted(
            (f for f in c.enemies() if c.adjacent_to(mate, f)),
            key=lambda f: distance_between(c.world, mate, f),
        )
        foe = c.choose(near, f"{c.ref}: which enemy") if near else None
        if foe is not None:
            c.basic(who=mate, on=foe)


def _marked_within_attacks_ally(radius: int):  # noqa: ANN202
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
        return any(team(world, t) is team(world, me) for t in getattr(ev, "targets", ()))

    return gate


@power(
    "m5660a3",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy marked by and within 5 squares of it attacks one of its allies",
    on=Trigger(
        PowerUsed, when=_marked_within_attacks_ally(5), text="a marked enemy attacks an ally"
    ),
)
def m5660a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    _shift_beside(c, foe, 5)
    c.use_power("m5660a0", on=foe, spend=False)


@power(
    "m5660a4",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, when=about_me, text="it drops to 0 hit points"),
)
def m5660a4(c: Cast) -> None:
    candidates = [c.me] + [a for a in c.allies() if c.distance(a) <= 10]
    who = c.choose(candidates, f"{c.ref}: who acts") or c.me
    c.extra_action(cost=STANDARD, on=who)


# ==========================================================================
# m5676
# ==========================================================================


@power("m5676a0", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5676a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER)

    def bite(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.actor not in c.world.zones.occupants(ring):
            return
        c.flat(5, on=ev.actor)

    c.watch(TurnEnd, bite, until=When.ENCOUNTER, on=me, label=c.ref)


@power("m5676a1", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5676a1(c: Cast) -> None:
    c.bonus("attack", 2, on=c.me, until=When.ENCOUNTER, when=lambda ctx: c.bloodied(c.me))
    c.bonus("damage", 3, on=c.me, until=When.ENCOUNTER, when=lambda ctx: c.bloodied(c.me))


@power(
    "m5676a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 8),
)
def m5676a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power(
    "m5676a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 7, kind=LIMITED),
)
def m5676a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5676a4",
    level=10,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 6),
)
def m5676a4(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike():
        return
    c.hit()
    mod = Mod(what="attack", value=-2, kind="untyped", label=c.ref)
    c.world.effects.apply(
        victim,
        c.me,
        When.SAVE_ENDS,
        label=f"{c.ref} hex",
        ongoing=(5, DamageType.POISON),
        mods=[(victim, mod)],
    )


# ==========================================================================
# m5697
# ==========================================================================


@power("m5697a0", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5697a0(c: Cast) -> None:
    _difficult_aura(c, 2)


@power("m5697a1", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5697a1(c: Cast) -> None:
    c.cannot_shift(on=c.me, until=When.ENCOUNTER)


@power(
    "m5697a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 10),
)
def m5697a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed()


@power(
    "m5697a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 5, kind=LIMITED),
)
def m5697a3(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    was_slowed = c.is_(Condition.SLOWED, on=victim)
    if c.strike():
        c.hit()
        if was_slowed:
            c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)
        else:
            c.slowed(until=When.SAVE_ENDS)


# ==========================================================================
# m5709
# ==========================================================================


@power(
    "m5709a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 11),
)
def m5709a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.mark()


@power(
    "m5709a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 11, dtype=DamageType.POISON),
    dropped=("Target.kind",),
)
def m5709a1(c: Cast) -> None:
    """Three failed saves, each worse than the last: the first turns the
    poison into an immobilize-and-ongoing-10 hold, and the second (fired
    from *that* hold's own escalation) is the fall into unconsciousness.
    `escalate` fires on every failure and nothing guards against nesting
    it a second time."""
    victim = _restricted_to(c, 1, lambda f: c.marked(on=f, by=c.me))
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)

    def second(_eff: Effect) -> None:
        c.unconscious(until=When.SAVE_ENDS, on=victim)

    def first(_eff: Effect) -> None:
        c.condition(
            Condition.IMMOBILIZED,
            until=When.SAVE_ENDS,
            on=victim,
            ongoing=(10, DamageType.POISON),
            escalate=second,
        )

    c.condition(until=When.SAVE_ENDS, on=victim, ongoing=(5, DamageType.POISON), escalate=first)


@power(
    "m5709a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=NO_TARGET,
)
def m5709a2(c: Cast) -> None:
    """ "The target makes a saving throw against m5709a1's effect. The
    target cannot succeed but can fail" -- `Effects.save` forces an
    off-cadence save right now, and a one-shot `SavingThrow` watch rigs
    its outcome the way `c.unsave` would from inside one."""
    affected = [
        f
        for f in c.enemies()
        if c.distance(f) <= 5 and any(e.label == "m5709a1" for e in c.world.effects.of(f))
    ]
    victim = c.choose(sorted(affected), f"{c.ref}: which creature") if affected else None
    if victim is None:
        return
    hold = next((e for e in c.world.effects.of(victim) if e.label == "m5709a1"), None)
    if hold is None:
        return

    def fail(ev: SavingThrow) -> None:
        if ev.actor == victim:
            c.unsave(ev)

    c.watch(SavingThrow, fail, until=When.INSTANT, on=victim, once=True, label=f"{c.ref} rig")
    c.world.effects.save(hold)


def _hit_me_with_ally_adjacent(world: World, me: int, ev: DamageRolled) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    return any(
        a != me and team(world, a) is team(world, me) and distance_between(world, me, a) <= 1
        for a in creatures(world)
    )


@power(
    "m5709a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy damages it with a melee or ranged attack while an ally is adjacent",
    on=Trigger(
        DamageRolled, when=_hit_me_with_ally_adjacent, text="damaged while an ally is adjacent"
    ),
)
def m5709a3(c: Cast) -> None:
    ev = c.trigger
    ev.amount = max(0, ev.amount - 10)
    allies = [a for a in c.allies() if c.adjacent(a)]
    mate = c.choose(sorted(allies), f"{c.ref}: which ally") if allies else None
    if mate is not None:
        c.flat(10, on=mate)


# ==========================================================================
# m5788
# ==========================================================================


@power("m5788a0", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5788a0(c: Cast) -> None:
    """ "Takes damage as normal, but ignores all other effects" of a
    Will-targeted attack -- approximated as immunity to every condition
    while the attack context's `vs` is Will, which is as close as a
    blanket exemption gets without a dedicated verb."""
    c.immune(
        *list(Condition),
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("vs") is WILL,
    )


@power(
    "m5788a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 9),
)
def m5788a1(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None and c.adjacent(victim):
            c.damage("2d8", 0, on=victim)


@power(
    "m5788a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("4d4", 8),
)
def m5788a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5788a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an adjacent enemy shifts or attacks without including it",
    on=[
        Trigger(MoveStart, when=_adjacent_enemy_shifts, text="an adjacent enemy shifts"),
        Trigger(
            PowerUsed, when=_adjacent_foe_looks_away, text="an adjacent enemy attacks without it"
        ),
    ],
)
def m5788a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None:
        c.basic(on=foe)


# ==========================================================================
# m5808
# ==========================================================================


@power(
    "m5808a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.shares_space(always=)",),
)
def m5808a0(c: Cast) -> None:
    """ "Can enter the spaces of Medium or Small enemies" wants a standing
    movement permission against any such enemy it ever meets.
    `c.shares_space` pairs the caster with one named creature for a
    duration; there is no blanket, always-on form of it."""


@power("m5808a1", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5808a1(c: Cast) -> None:
    c.cannot_shift(on=c.me, until=When.ENCOUNTER)


@power(
    "m5808a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d12", 5),
)
def m5808a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.mark()


@power("m5808a3", level=10, usage=AT_WILL, action=STANDARD, reach=Melee(2), target=UpTo(2))
def m5808a3(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:2]:
        if _secondary(c, 15, AC, victim):
            c.damage("2d12", 5, on=victim)
            c.mark(on=victim)


@power(
    "m5808a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d12", 10, kind=LIMITED),
)
def m5808a4(c: Cast) -> None:
    if not _armed(c, f"{c.ref} recharge"):
        _recharge_when_bloodied(c)
    if c.first:
        for foe in c.overrun():
            if foe in c.enemies():
                c.prone(on=foe)
    if c.strike():
        c.hit()
        c.ongoing(5)


def _master_damaged_within(radius: int):  # noqa: ANN202
    def gate(world: World, me: int, ev: DamageRolled) -> bool:
        masters = world.relations.sources(Relation.MASTER_OF, me)
        master = masters[0] if masters else None
        if master is None or getattr(ev, "target", None) != master:
            return False
        return distance_between(world, me, master) <= radius

    return gate


@power(
    "m5808a5",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="its master is damaged by an attack and is within 2 squares of it",
    on=Trigger(
        DamageRolled, when=_master_damaged_within(2), text="its master is damaged within 2 squares"
    ),
)
def m5808a5(c: Cast) -> None:
    ev = c.trigger
    half = ev.amount // 2
    ev.amount -= half
    c.flat(half, on=c.me)


# ==========================================================================
# m5875
# ==========================================================================


@power(
    "m5875a0", level=10, usage=ENCOUNTER, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET
)
def m5875a0(c: Cast) -> None:
    _double_turn(c)


@power("m5875a1", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5875a1(c: Cast) -> None:
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
        DamageRolled,
        halved,
        until=When.ENCOUNTER,
        on=me,
        window=Window.BEFORE,
        label=f"{c.ref} half",
    )
    c.watch(DamageApplied, shaken, until=When.ENCOUNTER, on=me, label=f"{c.ref} shaken")
    c.watch(TurnStart, recovers, until=When.ENCOUNTER, on=me, label=f"{c.ref} recovers")


@power(
    "m5875a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d12", 7),
)
def m5875a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.ongoing(5, DamageType.NECROTIC)
    c.mark()


@power(
    "m5875a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=13),
    trigger="an enemy enters a square flanking it",
    on=Trigger(MoveEnd, when=_entered_flank_with_me, text="an enemy enters a square flanking it"),
)
def m5875a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.push(3, on=foe)


# ==========================================================================
# m5971
# ==========================================================================


@power("m5971a0", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5971a0(c: Cast) -> None:
    c.threatens(2)


@power(
    "m5971a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d10", 7),
)
def m5971a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power("m5971a2", level=10, usage=AT_WILL, action=STANDARD, reach=Melee(2), target=UpTo(2))
def m5971a2(c: Cast) -> None:
    if not c.first:
        return
    picked: set[int] = set()
    for victim in c.targets[:2]:
        if victim in picked:
            continue
        picked.add(victim)
        c.use_power("m5971a1", on=victim, spend=False)


@power(
    "m5971a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d10", 7, kind=LIMITED),
    dropped=("Target.kind",),
)
def m5971a3(c: Cast) -> None:
    victim = _restricted_to(c, 2, lambda f: flanked_by(c.world, f, c.me))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        for mate in c.allies():
            if mate != c.me and c.adjacent_to(victim, mate):
                c.grant_attack(mate, on=victim)


@power(
    "m5971a4",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=CloseBurst(10),
    target=EACH_ALLY,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, when=about_me, text="it is first bloodied"),
)
def m5971a4(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    choice = c.choose(["attack", "shift"], f"{c.ref}: {mate}")
    if choice == "attack":
        near = sorted(
            (f for f in c.enemies() if c.adjacent_to(mate, f)),
            key=lambda f: distance_between(c.world, mate, f),
        )
        foe = c.choose(near, f"{c.ref}: {mate}'s target") if near else None
        if foe is not None:
            c.basic(who=mate, on=foe)
    else:
        c.shift(3, who=mate)


@power(
    "m5971a5",
    level=10,
    usage=ENCOUNTER,
    uses=3,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.draw_card()",),
)
def m5971a5(c: Cast) -> None:
    """Drawing a card and using "the power associated with it" names a deck
    this engine has no model for and no refs for the powers it would hold."""


# ==========================================================================
# m5973
# ==========================================================================


@power(
    "m5973a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(3),
    keywords=[Keyword.WEAPON],
)
def m5973a0(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:3]:
        if _secondary(c, 15, AC, victim):
            c.damage("2d10", 6, on=victim)


@power(
    "m5973a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d10", 8, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m5973a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()


@power(
    "m5973a2",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=CloseBurst(10),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d10", 8, dtype=DamageType.RADIANT),
)
def m5973a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(3)


@power(
    "m5973a3",
    level=10,
    usage=ENCOUNTER,
    uses=3,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.draw_card()",),
)
def m5973a3(c: Cast) -> None:
    """Drawing a card and using "the power associated with it" names a deck
    this engine has no model for and no refs for the powers it would hold."""


def _adjacent_creature_shifts(world: World, me: int, ev: MoveStart) -> bool:
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or getattr(ev, "kind_", "") != "shift":
        return False
    return distance_between(world, me, actor) <= 1


def _adjacent_creature_looks_away(world: World, me: int, ev: PowerUsed) -> bool:
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or not _is_attack(ev.power):
        return False
    if distance_between(world, me, actor) > 1:
        return False
    return me not in getattr(ev, "targets", ())


@power(
    "m5973a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.RADIANT],
    trigger="a creature adjacent to it shifts or attacks without including it",
    on=[
        Trigger(MoveStart, when=_adjacent_creature_shifts, text="an adjacent creature shifts"),
        Trigger(
            PowerUsed,
            when=_adjacent_creature_looks_away,
            text="an adjacent creature attacks without it",
        ),
    ],
)
def m5973a4(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None:
        c.flat(10, dtype=DamageType.RADIANT, on=foe)


# ==========================================================================
# m5981
# ==========================================================================


@power("m5981a0", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5981a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(2, until=When.ENCOUNTER)

    def worsen(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor == me or ev.actor not in c.enemies():
            return
        if ev.actor not in c.world.zones.occupants(ring):
            return
        if not c.is_(Condition.SLOWED, on=ev.actor):
            return
        c.cure(Condition.SLOWED, on=ev.actor)
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=ev.actor)

    c.watch(TurnEnd, worsen, until=When.ENCOUNTER, on=me, label=c.ref)


@power("m5981a1", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m5981a1(c: Cast) -> None:
    me = c.me

    def burned(ev: DamageApplied) -> None:
        if ev.target != me or DamageType.FIRE not in ev.types():
            return
        mods = [
            (me, Mod(what=d, value=-2, kind="untyped", label=c.ref)) for d in (AC, FORT, REF, WILL)
        ]
        c.world.effects.apply(me, me, When.SAVE_ENDS, label=f"{c.ref} brittle", mods=mods)

    c.watch(DamageApplied, burned, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5981a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 9, dtype=DamageType.COLD),
)
def m5981a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, Condition.CANNOT_SHIFT, until=When.SAVE_ENDS)


@power("m5981a3", level=10, usage=AT_WILL, action=MINOR, reach=Ranged(10), target=ONE_CREATURE)
def m5981a3(c: Cast) -> None:
    me = c.me
    victim = c.target
    if victim is None:
        return
    label = c.ref
    for other in creatures(c.world):
        if other == victim:
            continue
        for eff in list(c.world.effects.of(other)):
            if eff.label == label:
                c.world.effects.end(eff, "cursed a different creature")
    c.world.effects.apply(victim, me, When.ENCOUNTER, label=label, conditions=(Condition.SLOWED,))


# ==========================================================================
# m5986
# ==========================================================================


@power(
    "m5986a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m5986a0(c: Cast) -> None:
    me = c.me

    def eligible(who: int) -> bool:
        return who in c.enemies()

    def hold(who: int) -> Effect | None:
        mods = [
            (who, Mod(what=d, value=-2, kind="untyped", label=c.ref)) for d in (AC, FORT, REF, WILL)
        ]
        return c.world.effects.apply(who, me, When.ENCOUNTER, label=f"{c.ref} weak", mods=mods)

    zone = _aura(c, 1, eligible, hold)

    def left(ev: ZoneExited) -> None:
        if ev.zone == zone and c.marked(on=ev.actor, by=me):
            c.flat(10, dtype=DamageType.PSYCHIC, on=ev.actor)

    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=me, label=f"{c.ref} zap")


@power(
    "m5986a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
)
def m5986a1(c: Cast) -> None:
    if not c.first:
        return
    for victim in c.targets[:2]:
        if _secondary(c, 15, AC, victim):
            if c.crit:
                c.flat(25, on=victim)
                c.damage("2d12", 0, on=victim)
            else:
                c.damage("2d8", 9, on=victim)
            c.mark(on=victim)


@power(
    "m5986a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("1d8", 8, dtype=DamageType.PSYCHIC),
)
def m5986a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.stunned(until=When.SAVE_ENDS)


def _enemy_bloodied_my_ally(radius: int):  # noqa: ANN202
    def gate(world: World, me: int, ev: Bloodied) -> bool:
        source = getattr(ev, "source", None)
        victim = getattr(ev, "actor", None)
        if source is None or team(world, source) is team(world, me):
            return False
        if victim is None or victim == me or team(world, victim) is not team(world, me):
            return False
        return distance_between(world, me, source) <= radius

    return gate


@power(
    "m5986a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(5),
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("1d8", 8, dtype=DamageType.PSYCHIC),
    trigger="an enemy within 5 squares of it bloodies an ally",
    on=Trigger(
        Bloodied, when=_enemy_bloodied_my_ally(5), text="an enemy within 5 squares bloodies an ally"
    ),
)
def m5986a3(c: Cast) -> None:
    foe = getattr(c.trigger, "source", None)
    if foe is not None and c.strike(on=foe):
        c.hit(on=foe)


@power(
    "m5986a4",
    level=10,
    usage=ENCOUNTER,
    uses=3,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("c.draw_card()",),
)
def m5986a4(c: Cast) -> None:
    """Drawing a card and using "the power associated with it" names a deck
    this engine has no model for and no refs for the powers it would hold."""


# ==========================================================================
# m6060
# ==========================================================================


@power("m6060a0", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6060a0(c: Cast) -> None:
    c.bonus(
        "damage",
        0,
        dice="1d8",
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: (
            _melee_ctx(ctx)
            and bool(ctx.get("target"))
            and c.is_(Condition.PRONE, on=ctx.get("target"))
        ),
    )


@power("m6060a1", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6060a1(c: Cast) -> None:
    c.resist_forced(1, on=c.me, until=When.ENCOUNTER)


@power(
    "m6060a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    todo=("ConditionApplied.cancel",),
)
def m6060a2(c: Cast) -> None:
    """ "Can make a saving throw to avoid falling prone" has nothing to
    interrupt: `ConditionApplied` fires only after the prone condition is
    already on, and there is no other half of this trait to write."""


@power(
    "m6060a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 7),
)
def m6060a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed()


@power(
    "m6060a4",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d6", 3),
)
def m6060a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6060a5",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 8),
    todo=("ActionSpent.word",),
)
def m6060a5(c: Cast) -> None:
    """ "Trigger: an adjacent enemy stands up." `ActionSpent` carries only
    `actor` and `cost` (an `ActionType`) -- `.kind` resolves, but it is
    `Event`'s own serialisation property and answers "ActionSpent" for
    every row of this type, not the legal word that paid for it. There is
    no field saying *which* word (`stand`, `shift`, ...) was spent, so
    standing up cannot be told apart from any other move-costed action."""


# ==========================================================================
# m6176
# ==========================================================================


@power("m6176a0", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6176a0(c: Cast) -> None:
    _ca_synergy(c)


@power(
    "m6176a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 9),
)
def m6176a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        _grants_ca_until_it_swings(c, c.target)


@power(
    "m6176a2",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=15),
    dropped=("Target.kind",),
)
def m6176a2(c: Cast) -> None:
    victim = _restricted_to(c, 1, lambda f: has_combat_advantage(c.world, c.me, f))
    if victim is None:
        return
    if c.strike(on=victim):
        c.prone(on=victim)


@power(
    "m6176a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=0,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6176a3(c: Cast) -> None:
    _punish_departure(c, "m6176a2")


# ==========================================================================
# m6179
# ==========================================================================


@power("m6179a0", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6179a0(c: Cast) -> None:
    _ca_synergy(c)


@power(
    "m6179a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 9),
)
def m6179a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        _grants_ca_until_it_swings(c, c.target)


@power(
    "m6179a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=Ranged(5),
    target=NO_TARGET,
)
def m6179a2(c: Cast) -> None:
    for ally in c.allies():
        if c.distance(ally) <= 5:
            c.grant_action("shift", FREE, squares_=max(1, c.speed_of(ally) // 2), on=ally)


@power(
    "m6179a3",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 7),
)
def m6179a3(c: Cast) -> None:
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None and has_combat_advantage(c.world, c.me, victim):
            c.prone(on=victim)


@power(
    "m6179a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=0,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6179a4(c: Cast) -> None:
    _punish_departure(c, "m6179a3")


# ==========================================================================
# m6282
# ==========================================================================


@power("m6282a0", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6282a0(c: Cast) -> None:
    for ally in c.allies():
        if c.distance(ally) <= 5:
            c.initiative(2, on=ally)


@power("m6282a1", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6282a1(c: Cast) -> None:
    c.threatens(2)


@power(
    "m6282a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("4d4", 8),
)
def m6282a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m6282a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("4d4", 8, kind=LIMITED),
)
def m6282a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6282a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an adjacent enemy shifts 1 square",
    on=Trigger(MoveStart, when=_adjacent_enemy_shifts, text="an adjacent enemy shifts"),
)
def m6282a4(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None:
        c.use_power("m6282a2", on=foe, spend=False)


# ==========================================================================
# m6365
# ==========================================================================


@power(
    "m6365a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 9),
)
def m6365a0(c: Cast) -> None:
    victim = c.target
    if c.strike():
        if c.crit:
            c.flat(25, on=victim)
            c.damage("2d8", 0, dtype=DamageType.NECROTIC, on=victim)
        else:
            c.hit()
        _grants_ca_until_it_swings(c, victim, on_miss_too=True)


@power("m6365a1", level=10, usage=AT_WILL, action=MINOR, reach=PERSONAL, target=NO_TARGET)
def m6365a1(c: Cast) -> None:
    me = c.me
    removable = [Condition.DAZED, Condition.IMMOBILIZED, Condition.RESTRAINED, Condition.SLOWED]
    present = [cond for cond in removable if c.is_(cond, on=me)]
    cured = c.cure(*present, on=me)
    if cured:
        c.flat(5 * len(cured), on=me)


@power(
    "m6365a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(2),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 9),
    trigger="an adjacent enemy willingly shifts",
    on=Trigger(MoveStart, when=_adjacent_enemy_shifts, text="an adjacent enemy shifts"),
)
def m6365a2(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    if c.strike(on=foe):
        if c.crit:
            c.flat(25, on=foe)
            c.damage("2d8", 0, dtype=DamageType.NECROTIC, on=foe)
        else:
            c.hit(on=foe)
        c.prone(on=foe)


def _hit_with(ref: str):  # noqa: ANN202
    def gate(world: World, me: int, ev: Hit) -> bool:
        return ev.attacker == me and ev.power == ref

    return gate


@power(
    "m6365a3",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger="it hits with m6365a0",
    on=Trigger(Hit, when=_hit_with("m6365a0"), text="it hits with m6365a0"),
)
def m6365a3(c: Cast) -> None:
    victim = getattr(c.trigger, "target", None)
    if victim is not None:
        c.ongoing(10, dtype=DamageType.NECROTIC, on=victim)
    c.zone(spread({c.here}, 1), until=When.ENCOUNTER, difficult=True)


# ==========================================================================
# m6642
# ==========================================================================


@power("m6642a0", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6642a0(c: Cast) -> None:
    """Breathing underwater has no drowning rules in this engine to answer
    to; the attack-bonus half plays."""
    c.bonus(
        "attack",
        2,
        on=c.me,
        until=When.ENCOUNTER,
        when=lambda ctx: (
            c.terrain("aquatic")
            and bool(ctx.get("target"))
            and not c.is_kind("aquatic", on=ctx.get("target"))
        ),
    )


@power(
    "m6642a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 6),
)
def m6642a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d10", 0, dtype=DamageType.POISON)
        c.grab()


@power(
    "m6642a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(side="enemy", count=1, label="creature grabbed by it"),
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d12", 10),
    dropped=("Target.kind",),
)
def m6642a2(c: Cast) -> None:
    held = _holding(c)
    victim = c.target if c.target in held else next(iter(sorted(held)), None)
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.dazed(on=victim)


# ==========================================================================
# m6686
# ==========================================================================


@power(
    "m6686a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=MeleeOrRanged(1, 5),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 6),
)
def m6686a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED))


@power(
    "m6686a1",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    dropped=("Target.kind",),
)
def m6686a1(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    if not any(e.label == "m6686a0" for e in c.world.effects.of(victim)):
        return
    c.slide(2, on=victim)


# ==========================================================================
# m939
# ==========================================================================


def _m939a0_capped(world: World, eid: int) -> bool:
    count = 0
    for cr in creatures(world):
        if any(
            Condition.IMMOBILIZED in e.conditions and e.label == "m939a0"
            for e in world.effects.of(cr)
        ):
            count += 1
    return count < 2


@power(
    "m939a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d6", 5),
    requires=_m939a0_capped,
    requires_text="it cannot use this attack if two creatures are already immobilized by it",
    dropped=("When.ESCAPE",),
)
def m939a0(c: Cast) -> None:
    """ "Immobilized (until escape)" has no door: `When` has no escape-tied
    member, so the hold is laid indefinite (`ENCOUNTER`) rather than
    properly ending on a successful escape attempt."""
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.ENCOUNTER)


@power(
    "m939a1",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("0", 4),
    dropped=("Target.kind",),
)
def m939a1(c: Cast) -> None:
    victim = _restricted_to(
        c, 1, lambda f: c.is_(Condition.IMMOBILIZED, on=f) and not c.is_kind("undead", on=f)
    )
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.heal(4, on=c.me)


# ==========================================================================
# m948
# ==========================================================================


@power(
    "m948a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 6),
)
def m948a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m948a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=17),
)
def m948a1(c: Cast) -> None:
    me = c.me
    victim = c.target
    if c.strike():
        c.pull(2)
        c.grab()
        if victim is not None:
            c.flat(5, dtype=DamageType.NECROTIC, on=victim)
            c.heal(5, on=me)

            def drain(ev: TurnStart) -> None:
                if ev.ghost or ev.actor != victim or victim not in _holding(c):
                    return
                c.flat(5, dtype=DamageType.NECROTIC, on=victim)
                c.heal(5, on=me)

            c.watch(TurnStart, drain, until=When.ENCOUNTER, on=me, label=f"{c.ref} drain {victim}")


@power(
    "m948a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 6),
)
def m948a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


@power(
    "m948a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 6, dtype=DamageType.NECROTIC),
)
def m948a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)


# ==========================================================================
# m953
# ==========================================================================


@power(
    "m953a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 9),
)
def m953a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m953a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=13),
    trigger="an enemy moves into a position that flanks it",
    on=Trigger(
        MoveEnd, when=_entered_flank_with_me, text="an enemy moves into a flanking position"
    ),
)
def m953a1(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.push(3, on=foe)


@power(
    "m953a2", level=10, usage=ENCOUNTER, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET
)
def m953a2(c: Cast) -> None:
    _double_turn(c)


@power("m953a3", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m953a3(c: Cast) -> None:
    me = c.me

    def clear(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me:
            return
        c.cure(*SHAKEN_OFF, on=me)

    c.watch(TurnEnd, clear, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m956
# ==========================================================================


@power(
    "m956a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 8),
)
def m956a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m956a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 8),
)
def m956a1(c: Cast) -> None:
    victim = c.target
    me = c.me
    if c.strike():
        c.hit()
        if victim is not None:

            def shifted(ev: MoveStart) -> None:
                if getattr(ev, "actor", None) != victim or getattr(ev, "kind_", "") != "shift":
                    return
                mates = c.allies()
                mate = (
                    c.choose(sorted(mates), f"{c.ref}: whose opportunity attack") if mates else None
                )
                if mate is not None:
                    c.basic(who=mate, on=victim)

            c.watch(MoveStart, shifted, until=When.EONT, on=me, label=f"{c.ref} punish")


@power(
    "m956a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d10", 8),
    dropped=("resolve._mods(side=)",),
)
def m956a2(c: Cast) -> None:
    """ "Any attack roll against the target can score a critical hit on
    18-20" wants `crit_range` read off the defender's side of somebody
    else's attack, and `resolve._mods` only ever reads it off the
    attacker."""
    if c.strike():
        c.hit()


@power(
    "m956a3",
    level=10,
    usage=ENCOUNTER,
    uses=2,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m956a3(c: Cast) -> None:
    victim = c.target
    if victim is not None:
        c.surge(on=victim, bonus=c.roll("2d6"))


@power(
    "m956a4",
    level=10,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d6", 4, dtype=DamageType.LIGHTNING),
)
def m956a4(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m956a5", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m956a5(c: Cast) -> None:
    _racial_bloodied_attack_bonus(c, 1)


@power(
    "m956a6",
    level=10,
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.HEALING],
)
def m956a6(c: Cast) -> None:
    c.heal(25, on=c.me)
