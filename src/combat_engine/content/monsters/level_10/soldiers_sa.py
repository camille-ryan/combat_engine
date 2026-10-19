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

Gaps this file is the first to need, confirmed absent before marking:

* **A save penalty *can* be scoped to one named condition, and this list said
  it could not.** `Effects.save` builds a context -- its own comment names
  "against being immobilized or slowed" as the line it is for -- carrying
  `conditions`, `ongoing`, `dtype` and the laying row's keywords. So the
  narrowing is `c.penalty("save", n, when=...)` and m2064a0 is written.
  m1101a0 carried the same marker and its card has no such clause at all.
* **`c.regeneration` has a suppression hook**, `unless=`, whose docstring is
  "its regeneration does not function that turn". What m2068a3 is missing is
  on the other side: this stat block declares no regeneration anywhere for
  it to restart -- m2068a4 is the revives-unless trait -- so there is nothing
  to flip. Needs the block read, not a kwarg.
* **`Zones.aura` takes no `difficult=`.** `c.zone(difficult=True)` can make
  ground difficult but only `c.aura` follows its owner, so a *moving*
  "enemies treat the aura as difficult terrain" has no single call. Worked
  around below -- `c.aura` still returns a real `Zone` entity, and
  `Zone.difficult` is a plain mutable field on it -- so this is a workaround
  noted for the record, not a marker.
* **`crit_range` is read off the attacker, and that is the right side.**
  This file used to call it a gap: "any attack roll **against** the target
  can score a critical on 18-20" was read as a bonus wanting to sit on the
  far side of somebody else's attack. It does not. The wider range belongs
  to each attacker and the *gate* is what narrows it to one victim, which
  is how `p1074` prints the same sentence. m956a2 is written.

Two old gaps this brief hits again: `Condition.DISEASED` (no disease track)
and `ConditionApplied.cancel` (the condition is already on by the time that
event fires, so nothing can refuse it the way a `ForcedMove` can).
"""

from __future__ import annotations

from combat_engine.content.monsters.level_02.soldiers_sa import (
    _HELPLESS,
    _armed,
    _holding_nobody,
    _is_attack,
    _recharge_when_bloodied,
    _ref_of,
)
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
    Ident,
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
    ConditionEnded,
    DamageApplied,
    DamageRolled,
    Dropped,
    EffectApplied,
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
    bloodied,
    creatures,
    distance_between,
    has_combat_advantage,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me, by_melee, targets_me
from combat_engine.engine.zones import Zone

#: "slowed and cannot shift" and friends -- a disease track this engine
#: does not have at all. Reused wherever a card's own escalation names one.
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


def _landing_on(c: Cast, who: int, ev: EffectApplied) -> Effect | None:
    """The effect an `EffectApplied` is announcing, before it has bitten.

    `Effects.apply` installs the effect, announces it, and only **then** hands
    its conditions over -- so this is the one window in which a creature is
    being knocked prone and is not yet prone. `p4913` is the worked example of
    the same trick for a stun.
    """
    if ev.target != who:
        return None
    mine = [
        e
        for e in c.world.effects.live.values()
        if e.owner == who and not e.ended and e.label == ev.label
    ]
    # Guarded rather than `default=None`: that form makes the key's argument
    # `Effect | None` to a reader, and `e.id` is then an attribute on None.
    if not mine:
        return None
    return max(mine, key=lambda e: e.id)


def _saves_off_prone(c: Cast, who: int, ev: EffectApplied) -> bool:
    """"It can roll an immediate saving throw to avoid falling prone."

    **Not `ConditionApplied`, which is what the two rows using this were
    marked for.** That event is emitted from inside the handover above, so a
    row answering it is always too late and can only cure a condition that
    has already landed -- a different sentence, and a visibly different one
    for a creature whose other rows reward a prone target. `EffectApplied` is
    a few lines earlier and the condition can still be taken off the tuple.

    `ev.source == who` is left out: standing up and falling over are the
    creature's own doing and the printed line is about an attack.
    """
    landing = _landing_on(c, who, ev)
    if landing is None or Condition.PRONE not in landing.conditions:
        return False
    if ev.source == who:
        return False
    if not c.save(on=who, bare=True, against=f"{c.ref} prone"):
        return False
    landing.conditions = tuple(x for x in landing.conditions if x is not Condition.PRONE)
    c.note(f"{c.ref}: {who} saves against being knocked prone")
    return True


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


def _ca_synergy(c: Cast) -> None:
    """ "Gains combat advantage against an enemy if any of its allies has
    it too." `c.gains_advantage` asks the question every time the context
    is read, which is what a continuously-true trait like this wants."""
    me = c.me

    def shared(ctx: dict) -> bool:
        # The re-entrancy guard this used to carry locally now lives on
        # `query.has_combat_advantage` itself, so every row of this shape is
        # covered rather than only the two here. #376.
        victim = ctx.get("target")
        if victim is None:
            return False
        return any(has_combat_advantage(c.world, a, victim) for a in c.allies())

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
    recharge=3,
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


@power(
    "m1092a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=NO_TARGET,
    defect="the printed attack line names no defence",
)
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
    recharge=5,
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
)
def m1101a0(c: Cast) -> None:
    """ "If the target is a living creature already immobilized, stunned,
    or unconscious, the bite deals an extra 2d6."

    **The marker came off: this card prints no save penalty.** It was
    carried over from a sibling, and every clause the card does print --
    the damage, the save-ends immobilisation and the conditional 2d6
    against anything living and already held -- is here."""
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
    target=Target(
        "enemy", 1,
        label="target must be immobilized, stunned, or unconscious",
        conditions=frozenset(_HELPLESS),
    ),
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 6),
)
def m1101a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.stunned(until=When.SAVE_ENDS)


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
)
def m115863a2(c: Cast) -> None:
    """The disease contraction at the encounter's end has no track to land
    on; the damage and burn play."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.NECROTIC)
        c.contract("x5_23")


@power(
    "m115863a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=5,
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
    target=Target(
        side="enemy",
        count=1,
        label="creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=13),
    # Flat damage is an empty dice string, not "0": `Cast.hit` tests
    # `if dice` and "0" is truthy, so it reached `rng.roll` and raised
    # `not a dice expression: '0'`. The card prints a flat 10.
    damage=Damage("", 10, dtype=DamageType.NECROTIC),
)
def m115863a4(c: Cast) -> None:
    if c.strike():
        c.hit()
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
    recharge=5,
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
    defect="the printed attack line names no defence",
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
)
def m2064a0(c: Cast) -> None:
    """ "A -2 penalty to saving throws against the immobilized condition"
    is written, and the marker was wrong about there being nothing to aim
    at. `Effects.save` hands the gate a context carrying the `conditions`
    the effect being saved against imposes -- its own comment names this
    exact printed shape -- so the penalty narrows to the immobilisation and
    leaves every other save alone.

    `SONT`, because the card says "until the start of the m2064's next
    turn" and the attacker is the source."""
    victim = c.target
    if c.strike():
        c.hit()
        if victim is not None and c.is_(Condition.IMMOBILIZED, on=victim):
            c.damage("3d6", 0, dtype=DamageType.PSYCHIC)
        c.penalty(
            "save", 2, on=victim, until=When.SONT,
            when=lambda ctx: Condition.IMMOBILIZED in ctx.get("conditions", ()),
        )


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
    recharge=5,
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
    recharge=5,
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
)
def m2068a3(c: Cast) -> None:
    """One of its own within 10 squares gets its regeneration back.

    **The old docstring had the clause backwards**, which is worth saying
    first because it is why this row was re-marked three times. It said
    "the creature has regeneration and this clause switches it off". The
    card switches it **on**: "one <creature> within 10 squares whose
    regeneration is currently inactive (as a result of taking acid or fire
    damage) immediately reactivates the regeneration."

    The markers followed the misreading. `c.regeneration(suppressed_by=)`
    was one of four spellings the verb had already collapsed into
    `unless_damaged_by=`; `c.undouse()` was filed on the reading that the
    block files no regeneration at all, which its page refutes; and
    `etl.monster.regeneration` -- mine -- was right that nothing recorded
    the amount, and wrong that the amount was the gap.

    **The gap was that the suppression lived in a closure.**
    `c.regeneration` kept it in a local `{"skip": False}`, so nothing
    outside could ask whether a creature's regeneration was off, let alone
    switch it back on. That is the state `c.latched`'s docstring describes
    for the striker latch and #569 fixed there for the same reason: two
    rows are the same question from two sides. The hold is an `Effect`
    labelled with the laying ref now, `c.regen_suppressed` asks and
    `c.resume_regeneration` answers.

    Picks by the state rather than by proximity alone, because the card
    says "whose regeneration is currently inactive" -- so a minor action is
    not spent when there is nobody to spend it on.
    """
    kin = [
        other
        for other in c.within(10, side="team")
        if other != c.me
        and (who := c.world.get(other, Ident)) is not None
        and who.ref == "m2068"
        and c.regen_suppressed(on=other)
    ]
    if not kin:
        return
    pick = c.choose(sorted(kin), "whose regeneration comes back")
    if pick is not None:
        c.resume_regeneration(on=pick)

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
    defect="the printed attack line names no defence",
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
    recharge=4,
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
)
def m2087a5(c: Cast) -> None:
    """Both halves. `c.escape` needed no `as_power=`: its docstring *is*
    this sentence -- "you immediately use the escape action ... costs
    whatever the row that called it cost" -- and the printed +2 is its
    `bonus=`. This row is the move action, so the attempt is already
    priced.

    Asked rather than taken, because the card prints "can also": a creature
    that is held and would rather reposition keeps that option, and the
    shift that follows a successful escape is one square and not five.
    """
    me = c.me
    if c.grabbed_by(on=me) and c.may("escape instead of shifting", who=me):
        if c.escape(on=me, bonus=2):
            c.shift(1, who=me)
        return
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


@power(
    "m2092a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=UpTo(2),
    defect="the printed attack line names no defence",
)
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
    target=Target(
        "enemy", 1,
        label="target must be immobilized, stunned, or unconscious",
        conditions=frozenset(_HELPLESS),
    ),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d12", 6),
)
def m2092a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.NECROTIC)
        c.contract("x5_22")


@power("m2092a3", level=10, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m2092a3(c: Cast) -> None:
    me = c.me
    hold = c.bonus("skill:stealth", 5, on=me, until=When.ENCOUNTER)

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
    requires=lambda world, eid: bloodied(world, eid),
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
    recharge=4,
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
    target=Target(
        side="enemy",
        count=1,
        label="creature marked by it",
        relation=Relation.MARKED_BY,
    ),
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=FORT, printed=13),
    dropped=("etl.monster.inline_disease()",),
)
def m3273a2(c: Cast) -> None:
    """The Hit is written: `c.contract` records the infection and `c.exposed`
    is what reads it, and a disease caught in a fight never advances a stage
    anyway -- there is no extended rest for it to be checked at, which
    `c.contract`'s own docstring calls the card rather than a gap.

    **The ref handed over is this row's own**, which is the clause still
    dropped. The stat block prints the disease inline instead of pointing at
    a page, so the ETL minted no `x5_` row for it and there is nothing else to
    name -- so two blocks inflicting one disease would record two refs, and a
    row asking `c.exposed("x5_...")` about it answers no."""
    if c.strike():
        c.contract(c.ref)


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
    recharge=4,
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
    target=Target(
        side="enemy",
        count=1,
        label="usable only against a grabbed target",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 4),
)
def m3795a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


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
    target=Target(
        side="enemy",
        count=1,
        label="creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    reach=Melee(2),
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("1d8", 4, dtype=DamageType.POISON),
)
def m4007a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS)


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
)
def m4144a2(c: Cast) -> None:
    """Both halves, and the prone half is the one that was marked missing.

    It is taken off the effect as it lands -- see `_saves_off_prone` -- so the
    creature never falls at all, which is what "to prevent it or its rider
    from falling prone" says. The rider is asked for live each time rather
    than closed over, because a mount can be mounted and left mid-fight and
    the whole trait is gated on who is up there.
    """
    me = c.me

    def qualified(_ctx: dict) -> bool:
        return _qualified_rider(c) is not None

    c.resist_forced(1, on=me, until=When.ENCOUNTER, when=qualified)

    def landing(ev: EffectApplied) -> None:
        rider = _qualified_rider(c)
        if rider is None:
            return
        for who in (me, rider):
            if _saves_off_prone(c, who, ev):
                return

    c.watch(EffectApplied, landing, until=When.ENCOUNTER, on=me, label=c.ref)


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
    recharge=5,
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
    target=Target(
        side="enemy",
        count=1,
        label="creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d10", 7),
)
def m5160a3(c: Cast) -> None:
    """ "Cannot escape the grab until it saves against this effect" is not
    modelled -- the grab and the restrained hold stay two independent
    things, which is the more generous reading rather than a stingier one."""
    if c.strike():
        c.hit()
        c.condition(
            Condition.RESTRAINED, until=When.SAVE_ENDS, ongoing=(10, DamageType.UNTYPED)
        )
    else:
        c.restore_use(c.ref, on=c.me)


@power(
    "m5160a4",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(1),
    target=EACH_OTHER,
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
    target=Target(
        "enemy", 1,
        label="one creature, or the creature it is holding if it holds one",
        only_grabbed=True,
    ),
    damage=Damage("2d10", 6),
    attack=Attack(vs=AC, printed=15),
)
def m5434a0(c: Cast) -> None:
    """**The restriction the block prints belongs here**, and it was on
    `m5434a1` instead. That card says: while the creature has somebody
    grabbed, it can attack only with *this* row, which it must use against the
    grabbed creature. Both halves were on the wrong row -- `m5434a1` narrowed
    *itself* to the held creature, while this one, the row the sentence is
    actually about, took any target on the board. #655."""
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
    requires=_holding_nobody,
    requires_text="it must not already have a creature grabbed",
)
def m5434a1(c: Cast) -> None:
    """ "While it has a creature grabbed, it can attack only with `m5434a0`,
    which it must use against the grabbed creature."

    **That sentence is about the creature, not about the row it is printed
    on**, and reading it the other way is what the tree had. This row used to
    narrow *itself* to whoever was held -- discarding `c.target` for
    `sorted(held)[0]` -- which is the opposite of the card twice over: while
    something is grabbed this row may not be used at all, and `m5434a0` is the
    one that must take the held creature.

    So the clause splits. The target restriction moved to `m5434a0` as
    `only_grabbed=True`; what stays here is the half that was never written,
    a `requires=` standing the row down while the grip holds. #655.

    The release loop below is the printed "it can grab only one creature at a
    time", and it survives the gate: with the requirement in force this row
    only ever runs holding nobody, so the loop now frees nobody and is kept
    because `c.grab` is not the only way a grip can arrive."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
        _drag_beside(c, victim, c.me, 2)
        for prev in _holding(c):
            if prev != victim:
                _release(c, prev)
        c.grab()


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
    recharge=5,
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
    target=Target(
        "enemy", 1,
        label="one dazed creature",
        conditions=frozenset({Condition.DAZED}),
    ),
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 9),
)
def m5541a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("3d8", 0, dtype=DamageType.PSYCHIC)
        c.mark(until=When.SAVE_ENDS)


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
    damage=Damage("3d8", 9, dtype=[DamageType.NECROTIC, DamageType.POISON]),
    trigger="it is first bloodied",
    on=Trigger(Bloodied, when=about_me, text="it is first bloodied"),
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
    target=EACH_OTHER,
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
    recharge=5,
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
    recharge=5,
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
    recharge=5,
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
    target=Target(
        side="enemy",
        count=1,
        label="creature marked by it",
        relation=Relation.MARKED_BY,
    ),
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 11, dtype=DamageType.POISON),
)
def m5709a1(c: Cast) -> None:
    """Three failed saves, each worse than the last: the first turns the
    poison into an immobilize-and-ongoing-10 hold, and the second (fired
    from *that* hold's own escalation) is the fall into unconsciousness.
    `escalate` fires on every failure and nothing guards against nesting
    it a second time."""
    victim = c.target
    if not c.strike():
        return
    c.hit()

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
    recharge=5,
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
    Will-targeted attack -- immunity to every condition, gated on the
    attacking power targeting Will.

    **The gate asked the context for a `vs` key and nothing writes one**, so
    the immunity never applied once and the creature was missing a defensive
    trait in every fight it was ever in. It audited green throughout: the row
    fires and lays a modifier, and only the modifier's question was
    unanswerable. #591.

    `symbols.py` carried it in `KNOWN_DEAD` while it was broken and that
    entry is **gone**, which is the mechanism working as designed -- the
    allowance went red the moment the repair landed rather than outliving it.
    What holds the repair now is `drivers.an_immunity_gated_on_the_attacking
    _defence`, which lays a condition through `Effects.apply` from a Will
    attack, from an AC attack, and from a label naming no row at all.

    The eight rows that ask this question elsewhere read `ev.vs` off
    `AttackDeclared` or `AttackRolled`, which genuinely carry it -- but
    those are watchers, and this is a standing `when=` gate handed a damage
    context rather than an event. So it asks the **power** the context does
    name: `power` is the second-busiest key in the tree at 383 reads, and a
    row's declared `Attack(vs=...)` is the defence it rolls against.

    **Two rows in the tree declare `Defense.ANY` and this will miss them**,
    of 10,078 that declare an attack at all and 1,213 that declare Will. A
    miss leaves the creature without an immunity it should have, which is
    the direction to err -- `m5808a0`'s rule, a row stronger than its card
    being worse than one weaker. Granting on `ANY` would hand it immunity
    against attacks that never targeted Will.
    """
    from combat_engine.engine.dsl import get as _get

    def targets_will(ctx: dict[str, object]) -> bool:
        rolled = _get(str(ctx.get("power") or ""))
        attack = getattr(rolled, "attack", None) if rolled else None
        return getattr(attack, "vs", None) is WILL

    c.immune(
        *list(Condition),
        on=c.me,
        until=When.ENCOUNTER,
        when=targets_will,
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
)
def m5808a0(c: Cast) -> None:
    """"Can enter the spaces of Medium or Small enemies" is a permission that
    belongs to the **mover**, and the engine only has the other side of it.

    `movement._clear` asks `shares_space(world, occupant)` -- is this creature
    enterable by anybody -- and takes no account of who is doing the entering.
    So the nearest thing writable here is `c.shares_space` laid on every
    Medium-or-smaller enemy, which says something much larger than the card:
    their squares would open to the whole board, not to this creature. A row
    stronger than its printed line is worse than an absent one, so it is left
    out.

    The marker used to read `c.shares_space(always=)`, which names the wrong
    gap: an always-on form of that verb would still lay the property on the
    wrong creature.

    **And now it shares a symbol with `m6655a1`**, which printed the same
    permission unnarrowed and sat on `Movement.through_creatures`. One gap
    under two names could not go green for either row. This card is that
    permission plus a predicate on the occupant's size and side. #626.

    **Written now.** `movement.may_enter` is the mover's side of the
    question `shares_space` asks of the occupant, consulted by
    `movement._clear` beside it -- a creature gets through if either says
    so. #626.
    
    `sizes` and `side` are arguments rather than a `when=` gate: the
    predicate needs the occupant's size and allegiance and only the world
    answers those, where a gate sees the context alone. The other two cards
    of this family print no size and pass none.
        """
    c.may_enter(sizes=(Size.MEDIUM, Size.SMALL), side="enemy",
                on=c.me, until=When.ENCOUNTER)



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
    recharge=5,
    action=STANDARD,
    reach=Melee(2),
    target=Target(
        side="enemy",
        count=1,
        label="it must be flanking the target",
        flanked=True,
    ),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d10", 7, kind=LIMITED),
)
def m5971a3(c: Cast) -> None:
    """The printed Requirement is the target line: `flanked=` and not
    `grants_ca=`, because a prone or dazed creature grants combat advantage
    without being flanked and this card asks for the flank."""
    victim = c.target
    if c.strike():
        c.hit()
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
    recharge=5,
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
)
def m6060a2(c: Cast) -> None:
    """One saving throw per attempt to knock it down, taken while the effect
    is landing. See `_saves_off_prone` for why that window and not
    `ConditionApplied`, which is what this row was marked for.

    It matters in play on this stat block in particular: m6060a0 pays extra
    damage to a prone target and m6060a5 answers one standing up, so a trait
    that let the prone land and then cured it would hand the creature both of
    its own riders against itself."""
    me = c.me

    def landing(ev: EffectApplied) -> None:
        _saves_off_prone(c, me, ev)

    c.watch(EffectApplied, landing, until=When.ENCOUNTER, on=me, label=c.ref)


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


_M6060_STANDS = "an adjacent enemy stands up"

#: What `actions.legal` writes when the stand action ends a prone hold. The
#: word is the whole distinguisher, so it is a constant rather than a literal
#: in the predicate.
_STOOD_UP = "stood up"


def _adjacent_enemy_stood(world: World, me: int, ev: ConditionEnded) -> bool:
    """Standing up is announced, and not by `ActionSpent`.

    `actions.legal` ends every prone hold with the reason `"stood up"` and
    `Effects._lift` passes that reason straight into `ConditionEnded`, so the
    printed trigger is a prone condition ending for that one reason. Prone
    expiring any other way -- the effect cleared, the creature killed -- comes
    through with a different `why` and is not this sentence.
    """
    if ev.condition is not Condition.PRONE or ev.why != _STOOD_UP:
        return False
    # `team` directly rather than `query.enemies`, which filters the dead and
    # is the wrong question about a creature that has just got up.
    mine, theirs = team(world, me), team(world, ev.target)
    if ev.target == me or theirs is None or theirs == mine:
        return False
    return distance_between(world, me, ev.target) <= 1


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
    trigger=_M6060_STANDS,
    on=Trigger(ConditionEnded, when=_adjacent_enemy_stood, text=_M6060_STANDS),
)
def m6060a5(c: Cast) -> None:
    """Declared on `ConditionEnded`, not on `ActionSpent`, which is what this
    row was marked for: `ActionSpent` carries only `actor` and an
    `ActionType`, so a stand cannot be told from any other move-costed
    action. The condition ending says which action it was, in `why`.

    A reaction, so it resolves after the creature is up -- which is the
    printed order and also the only order in which a fresh m6060a4 or this
    row's own prone rider means anything."""
    foe = getattr(c.trigger, "target", None)
    if foe is None or not c.strike(on=foe):
        return
    c.hit(on=foe)
    c.prone(on=foe)


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
    target=Target(
        side="enemy",
        count=1,
        label="creature granting combat advantage to it",
        grants_ca=True,
    ),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=15),
)
def m6176a2(c: Cast) -> None:
    if c.strike():
        c.prone()


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
    recharge=5,
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
    recharge=5,
    action=STANDARD,
    reach=CloseBlast(2),
    target=EACH_OTHER,
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
    target=Target(
        side="enemy",
        count=1,
        label="creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d12", 10),
)
def m6642a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()


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
    target=Target(side="enemy", everyone=True, affected_by="m6686a0",
                  label="each creature affected by m6686a0 in the burst"),
)
def m6686a1(c: Cast) -> None:
    """Slides whatever its own aura has caught.

    **Written: the restriction moved into the header.** The body enforced it
    and the row played, but the interface and `policy/` read the decorator
    *without running anything* -- so the row was offered against creatures
    the card forbids and then declined. `Target.affected_by` reads
    `Effect.by`, and the refusal a player now sees is the printed
    restriction itself.

    The hand-rolled check this replaces read `e.label == "m6686a0"`, and the
    header reads `Effect.by` instead -- which is the robust field. #580 added
    `by` precisely because six `cast.py` sites label by *content* rather
    than by ref, so a label comparison answers nothing for an effect laid
    through one of them.
    """
    victim = c.target
    if victim is None:
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
)
def m939a0(c: Cast) -> None:
    """ "Immobilized (until escape)" is `When.ESCAPE`. It was laid
    indefinite, so the hold outlived the grab it describes -- and the
    printed Requirement counts immobilised creatures, so a hold that never
    ended also locked the row out of the fight permanently after two
    uses."""
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.ESCAPE)


@power(
    "m939a1",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=Target(
        "enemy", 1,
        label="immobilized living creature only",
        conditions=frozenset({Condition.IMMOBILIZED}),
        # `living=` is the exact test #411 wrote down and nothing could
        # say: not undead, and not construct unless it carries living.
        # `kinds_without={"undead"}` stood here as the faithful half,
        # with the construct exception carried as a marker.
        living=True,
    ),
    attack=Attack(vs=FORT, printed=15),
    #: Flat 4, no dice: the empty string is how `Damage` says that. `"0"`
    #: reaches `rng.roll` and raises -- found by driving this row.
    damage=Damage("", 4),
)
def m939a1(c: Cast) -> None:
    """The whole target line is the header's now: `conditions=` for the
    immobilisation and `kinds_without=` for "living", so the redirect that
    asked both by hand came out.

    **`Target.living` was the right symbol after all**, and the two
    re-points away from it were each correct at the time. It first went to
    `chargen.kind_words()` because `query.kinds_of` was empty for a player
    character, so a positive word aimed at the party yielded an empty pool
    -- true then, fixed by #542, which gives every character `natural` and
    `humanoid`. What remained was #411's exception, and that was never a
    field on `Target` nor anything `chargen` could store: it is one `if` in
    `query.living`.

    Both halves landed. #542 gives every character `natural` and
    `humanoid`, so there are words to read; `query.living` is the test
    itself, and it is the word-wins-where-present spelling rather than a
    plain absence, because two races print "both living and undead" and
    twenty-five stat blocks print both living and construct.
    """
    if c.strike():
        c.hit()
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
)
def m956a2(c: Cast) -> None:
    """ "Any attack roll against the target can score a critical hit on
    18-20" wanted no `side=` on `resolve._mods` after all. The wider range
    belongs to the **attackers** -- it is read off whoever is rolling -- and
    the gate on the damage context is what keeps it to this one creature.
    `p1074` prints the same sentence and is written exactly this way.

    `c.bonus` already defaults to `When.EONT`, which is the printed "until
    the end of m956's next turn" measured from the creature that laid it.
    """
    victim = c.target
    if not c.strike():
        return
    c.hit()
    if victim is None:
        return
    against = lambda ctx: ctx.get("target") == victim  # noqa: E731
    for shooter in [c.me, *c.allies()]:
        c.bonus("crit_range", 2, on=shooter, when=against)


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
