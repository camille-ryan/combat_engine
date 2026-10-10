"""Monster abilities, level 6: the blocks that print no role.

Eight stat blocks, forty-two rows. As at level 5, a role-less block here
reads like a companion's card -- full defences, a basic routine and a trick
or two -- rather than an encounter monster, which is a fact about the card
and not an error to fix.

Conventions, inherited from the role sweeps at this level and below:

* numbers load from `game.db`; the attack line is `Attack(vs=AC, printed=N)`
  exactly as the card prints it, and the damage line goes in the header as
  data;
* a **trait** costs no action, has no target, and arms whatever holds it,
  whatever the compendium's action column claims -- several here are filed
  under "standard" or "trait" and are read by what they actually do;
* a printed range band of "20/40" or "15/30" takes the short number; a card
  with no range at all is melee 1;
* "partial concealment or partial cover" is fully askable --
  `query.concealment_of` reads a creature's own carried modifier and
  `query.cover_between` traces the two positions -- so nothing here is
  marked for it;
* `c.mark`, never `c.condition(Condition.MARKED, ...)` -- only the first sets
  `Relation.MARKED_BY`.

Two numbers inside running prose ("m5973", "m5973's") do not match the ref
heading them ("m5970") -- a stray renumbering the extraction did not fully
settle. Read as the same creature throughout; nothing is guessed from it.
One other block's own body text doubles its ref oddly ("m6347'm6347"), which
is the same kind of leftover and is read the same way, as "it".
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ENEMY,
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
    STANDARD,
    ActionType,
    AreaBurst,
    Attack,
    Cast,
    CloseBurst,
    Condition,
    Cover,
    Damage,
    DamageType,
    Keyword,
    Melee,
    Ranged,
    Relation,
    Stats,
    UpTo,
    Usage,
    When,
    World,
    get,
    power,
)
from combat_engine.engine.events import (
    AttackRolled,
    Bloodied,
    ConditionApplied,
    Dropped,
    Miss,
    RelationSet,
    SavingThrow,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    concealment_of,
    cover_between,
    distance_between,
    enemies,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me, by_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _has_cover_or_concealment_gate(world: World, eid: int) -> bool:
    """"Partial concealment or partial cover" as an entry Requirement --
    concealment is a modifier the creature itself carries, cover is traced
    between two positions, so both are asked of the board rather than
    marked as unaskable."""
    if concealment_of(world, eid) >= Cover.PARTIAL:
        return True
    return any(cover_between(world, foe, eid) >= Cover.PARTIAL for foe in enemies(world, eid))


def _has_cover_or_concealment(c: Cast) -> bool:
    return _has_cover_or_concealment_gate(c.world, c.me)


def _has_partial_concealment_gate(world: World, eid: int) -> bool:
    return concealment_of(world, eid) >= Cover.PARTIAL


def _ranged_or_area(ctx: dict[str, Any]) -> bool:
    """"Ranged and area attacks" -- the two reach kinds the campaign's own
    `_shot_me_from_afar` already reads this way, excluding melee and close."""
    if ctx.get("ranged"):
        return True
    row = get(str(ctx.get("power") or ""))
    return row is not None and row.reach.kind in ("ranged", "area_burst")


def _lucky_reroll(c: Cast, bonus: int) -> None:
    """"Gains a +N racial bonus to the attack roll or the saving throw" on
    a miss or a failed save -- the same clause three creatures this wave
    print; `c.trigger` says which roll to redo."""
    ev = c.trigger
    if isinstance(ev, SavingThrow):
        c.reroll_save(bonus=bonus)
    else:
        c.reroll_attack(bonus=bonus)


_MISS_OR_FAILED_SAVE = "it misses with an attack or fails a saving throw"


def _failed_my_save(world: World, me: int, ev: SavingThrow) -> bool:
    return ev.actor == me and not ev.saved


#: "Dazed, immobilized, marked, or slowed by an attack" -- m6544a5's own four.
_M6544_CONDS = (Condition.DAZED, Condition.IMMOBILIZED, Condition.MARKED, Condition.SLOWED)


# ==========================================================================
# m4258
# ==========================================================================


@power(
    "m4258a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=6),
    damage=Damage("1d10", 4),
)
def m4258a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4258a1",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4258a1(c: Cast) -> None:
    """Active only while a friendly rider of level 6 or higher is actually
    mounted -- asked live in the gate rather than through `requires=`, which
    arms once and would refuse this permanently on a board with nobody
    riding yet. The rider's own concealment is re-granted each time a new
    qualifying rider is found; a stale grant on a former rider goes quietly
    inert because the gate always re-checks who is riding *now*."""
    me = c.me

    def rider_ok() -> bool:
        rider = c.rider()
        if rider is None or team(c.world, rider) is not team(c.world, me):
            return False
        stats = c.world.get(rider, Stats)
        return stats is not None and stats.level >= 6

    c.conceal(on=me, until=When.ENCOUNTER, when=lambda ctx: rider_ok() and _ranged_or_area(ctx))

    granted: dict[str, int | None] = {"rider": None}

    def watch_mount(_ev: Any = None) -> None:
        rider = c.rider()
        if rider is not None and rider != granted["rider"] and rider_ok():
            granted["rider"] = rider
            c.conceal(
                on=rider, until=When.ENCOUNTER,
                when=lambda ctx: rider_ok() and _ranged_or_area(ctx),
            )

    c.watch(RelationSet, watch_mount, until=When.ENCOUNTER, on=me, label=f"{c.ref} rider conceal")
    watch_mount()

    def missed(ev: Miss) -> None:
        if ev.target in (me, c.rider()) and rider_ok():
            c.shift(1, who=me)

    c.watch(Miss, missed, until=When.ENCOUNTER, on=me, label=f"{c.ref} evade")


@power(
    "m4258a2",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m4258a2(c: Cast) -> None:
    """`c.ride` has no size check at all, so this permission has nothing to
    lift -- complete and inert in a fight."""


# ==========================================================================
# m5588
# ==========================================================================


@power(
    "m5588a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DISEASE],
)
def m5588a0(c: Cast) -> None:
    """A standing affliction the creature already carries, not a roll
    anybody makes mid-fight: the penalty is laid once and the riposte
    watches for its own `Bloodied`."""
    me = c.me
    c.penalty("will", 2, on=me, until=When.ENCOUNTER)

    def bloodied(ev: Bloodied) -> None:
        if ev.actor != me:
            return
        mate = next((a for a in c.allies() if c.adjacent_to(a, me)), None)
        if mate is not None:
            c.basic(on=mate)

    c.watch(Bloodied, bloodied, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5588a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 6),
)
def m5588a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5588a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 7),
)
def m5588a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5588a3",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=UpTo(2),
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 3),
)
def m5588a3(c: Cast) -> None:
    """"Repeats the attack once against the same target or a different
    one" is two independent rolls, which is what a body called once per
    target of `UpTo(2)` already gives."""
    if c.strike():
        c.hit()


@power(
    "m5588a4",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("1d10", 7, kind=LIMITED),
)
def m5588a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)
        c.penalty("attack", 2, until=When.EONT)


@power(
    "m5588a5",
    level=6,
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_has_cover_or_concealment_gate,
    requires_text="it must have partial concealment or partial cover",
)
def m5588a5(c: Cast) -> None:
    c.hide()


@power(
    "m5588a6",
    level=6,
    usage=AT_WILL,
    once_per_round=True,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5588a6(c: Cast) -> None:
    """The first qualifying hit each round, not a chosen action."""
    from combat_engine.content.monsters.level_03.skirmishers_sa import _per_round_rider

    _per_round_rider(c, "1d6", lambda ev: bool(getattr(ev.result, "advantage", False)))


@power(
    "m5588a7",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_MISS_OR_FAILED_SAVE,
    on=(
        Trigger(Miss, by_me, "it misses with an attack"),
        Trigger(SavingThrow, _failed_my_save, "it fails a saving throw"),
    ),
)
def m5588a7(c: Cast) -> None:
    _lucky_reroll(c, 4)


# ==========================================================================
# m5970
# ==========================================================================


@power(
    "m5970a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 7),
)
def m5970a0(c: Cast) -> None:
    """"A bonus to the attack roll equal to the number of enemies adjacent
    to him" is counted off the board, before the roll."""
    plus = len(c.within(1, side="enemy"))
    if c.strike(plus=plus):
        c.hit()
        c.mark(until=When.EONT)


@power(
    "m5970a1",
    level=6,
    usage=ENCOUNTER,
    uses=2,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d10", 9, dtype=DamageType.RADIANT, kind=LIMITED),
)
def m5970a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m5970a2",
    level=6,
    usage=DAILY,
    action=MINOR,
    reach=Melee(1),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m5970a2(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    c.heal(14, on=mate)
    c.save(on=mate)


@power(
    "m5970a3",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_MISS_OR_FAILED_SAVE,
    on=(
        Trigger(Miss, by_me, "it misses with an attack"),
        Trigger(SavingThrow, _failed_my_save, "it fails a saving throw"),
    ),
)
def m5970a3(c: Cast) -> None:
    _lucky_reroll(c, 4)


# ==========================================================================
# m5979
# ==========================================================================


@power(
    "m5979a0",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 6),
)
def m5979a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5979a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5979a1(c: Cast) -> None:
    """"Shifts up to 3 squares and can use [the basic attack] against up to
    three enemies during the shift" -- one square at a time, one swing per
    newly adjacent foe not yet struck."""
    struck: set[int] = set()
    for _ in range(3):
        c.shift(1)
        foe = next((f for f in c.enemies() if c.adjacent(f) and f not in struck), None)
        if foe is None:
            continue
        struck.add(foe)
        c.use_power("m5979a0", on=foe)


@power(
    "m5979a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("2d6", 6),
)
def m5979a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m5979a3",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points",
    on=Trigger(Dropped, about_me, "it drops to 0 hit points"),
)
def m5979a3(c: Cast) -> None:
    c.extra_action(cost=STANDARD, on=c.me)


# ==========================================================================
# m6279
# ==========================================================================


@power("m6279a0", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6279a0(c: Cast) -> None:
    c.bonus(
        "damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: bool(ctx.get("advantage")),
    )


@power("m6279a1", level=6, usage=AT_WILL, action=ActionType.NONE, reach=PERSONAL, target=NO_TARGET)
def m6279a1(c: Cast) -> None:
    """"Living enemies take a -2 penalty to attack rolls while in the
    aura" -- the same clause `m115898a0` prints; the set is asked fresh off
    distance and kind each time rather than kept as a stale membership
    list."""
    c.aura(1, label=f"{c.ref} aura", until=When.ENCOUNTER, on=c.me)
    me = c.me
    for foe in c.enemies():
        c.penalty(
            "attack", 2, on=foe, until=When.ENCOUNTER,
            when=lambda ctx, f=foe: (
                distance_between(c.world, me, f) <= 1
                and not (c.is_kind("undead", on=f) or c.is_kind("construct", on=f))
            ),
        )


@power(
    "m6279a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 7),
)
def m6279a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6279a3",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 7, kind=LIMITED),
)
def m6279a3(c: Cast) -> None:
    """"If m6279 targets only one creature, she can make this attack
    twice against that creature" is asked once for the whole use, off how
    many targets it actually has -- the solo case strikes the same
    creature a second time rather than running per target."""
    victim = c.target
    if c.strike():
        c.hit()
        if c.bloodied(on=victim):
            c.use_power("m6279a2", on=victim)
    if c.first and len(c.targets) == 1 and victim is not None and c.strike(on=victim):
        c.hit(on=victim)
        if c.bloodied(on=victim):
            c.use_power("m6279a2", on=victim)


@power(
    "m6279a4",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d6", 7, kind=LIMITED),
)
def m6279a4(c: Cast) -> None:
    c.shift(2)
    if c.strike():
        c.hit()
    c.shift(2)
    if _has_cover_or_concealment(c):
        c.hide()


@power("m6279a5", level=6, usage=ENCOUNTER, action=MINOR, reach=PERSONAL, target=NO_TARGET)
def m6279a5(c: Cast) -> None:
    foe = next((e for e in c.enemies() if c.can_see(e)), None)
    if foe is None:
        return
    c.conceal(on=c.me, until=When.EONT, when=lambda ctx, f=foe: ctx.get("attacker") == f)


# ==========================================================================
# m6347
# ==========================================================================


@power(
    "m6347a0",
    level=6,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    requires=_has_partial_concealment_gate,
    requires_text="it must have partial concealment",
)
def m6347a0(c: Cast) -> None:
    c.hide()


@power(
    "m6347a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 7),
)
def m6347a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m6347a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d8", 7),
)
def m6347a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m6347a3",
    level=6,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d6", 7, dtype=DamageType.POISON, kind=LIMITED, half_on_miss=True),
)
def m6347a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, ongoing=(5, DamageType.POISON))
    else:
        c.hit(half=True)
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m6347a4",
    level=6,
    usage=ENCOUNTER,
    uses=2,
    once_per_round=True,
    action=MINOR,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    keywords=[Keyword.HEALING],
)
def m6347a4(c: Cast) -> None:
    c.spend_surge(on=c.target)


@power("m6347a5", level=6, usage=ENCOUNTER, action=MINOR, reach=Ranged(10), target=ONE_ALLY)
def m6347a5(c: Cast) -> None:
    mate = c.target
    if mate is None:
        return
    c.shift(1, who=mate)
    c.basic(who=mate)


@power(
    "m6347a6",
    level=6,
    usage=DAILY,
    action=FREE,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d6", 7, dtype=DamageType.POISON),
    trigger="it dies",
    on=Trigger(Dropped, about_me, "it dies"),
    dropped=("c.emerge()",),
)
def m6347a6(c: Cast) -> None:
    """The poison blow plays. The disease it seeds on an end-of-encounter
    save, and the creature's own replacement emerging from a dead or
    diseased body, are both named gaps: nothing stages a disease and
    nothing spawns a creature off a delayed end-of-encounter check."""
    if c.strike():
        c.hit()
        c.contract("x5_91")


# ==========================================================================
# m6371
# ==========================================================================


@power(
    "m6371a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m6371a0(c: Cast) -> None:
    """Nothing in the engine charges extra movement for climbing without a
    climb speed, and nothing grants combat advantage automatically for
    doing it -- there is no rule here to lift, so this is complete and
    inert in a fight."""


@power(
    "m6371a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 5),
)
def m6371a1(c: Cast) -> None:
    from combat_engine.engine.query import has_combat_advantage

    c.shift(1)
    if c.strike():
        c.hit()
        if has_combat_advantage(c.world, c.me, c.target):
            c.flat(3)


@power(
    "m6371a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=11),
    damage=Damage("1d8", 5),
)
def m6371a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power("m6371a3", level=6, usage=ENCOUNTER, action=MOVE, reach=PERSONAL, target=NO_TARGET)
def m6371a3(c: Cast) -> None:
    c.shift(max(1, c.speed_of() // 2))


# ==========================================================================
# m6544
# ==========================================================================


@power(
    "m6544a0",
    level=6,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6544a0(c: Cast) -> None:
    """Rough ground costs her nothing while she shifts, and nothing else.

    `when="shift"` is the narrowing every one of these cards prints and this
    verb could not say. It is spent in the *search*: a square of difficult
    terrain costs two, a shift is one, so without the exemption the square is
    never offered as a shift destination at all.
    """
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER, when="shift")


@power(
    "m6544a1",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d8", 7),
)
def m6544a1(c: Cast) -> None:
    """The step is ranked `toward=` its own target. The card gives it no
    direction, and m6544a3 is this row followed by m6544a2 at the same
    creature -- so this step lands between the two swings, and unranked it put
    the second out of reach. Ranking only: `World.decide` still sees every
    square."""
    if c.strike():
        c.hit()
    c.shift(1, toward=c.target)


@power(
    "m6544a2",
    level=6,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("1d6", 7),
)
def m6544a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(1)


@power(
    "m6544a3",
    level=6,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6544a3(c: Cast) -> None:
    """Both of its own basic attacks, run at a shared -2; "if both hit" is
    read off each call's own `c.landed` rather than reimplemented here."""
    victim = next((f for f in c.enemies() if c.adjacent(f)), None)
    if victim is None:
        return
    c.penalty("attack", 2, on=c.me, until=When.EOT)
    c.use_power("m6544a1", on=victim)
    first_hit = c.landed
    c.use_power("m6544a2", on=victim)
    second_hit = c.landed
    if first_hit and second_hit:
        c.flat(5, on=victim)


@power(
    "m6544a4",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it makes an attack roll",
    on=Trigger(AttackRolled, by_me, "it makes an attack roll"),
)
def m6544a4(c: Cast) -> None:
    c.reroll_attack(keep="new")


@power(
    "m6544a5",
    level=6,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is dazed, immobilized, marked, or slowed by an attack",
    # **Two triggers, because a mark is not a condition.** `Relations.set`
    # writes `marked_by` and announces only `RelationSet`, so the "marked"
    # quarter of this card never fired on `ConditionApplied` -- `lint.py`'s
    # `_relation_only_conditions` walk caught it. The other three arrive the
    # ordinary way. `level_02/artillery_sa.py` settled this shape.
    on=(
        Trigger(
            ConditionApplied,
            lambda w, m, ev: ev.target == m and ev.condition in _M6544_CONDS,
            "it is dazed, immobilized or slowed",
        ),
        Trigger(
            RelationSet,
            lambda w, m, ev: (getattr(ev, "kind_", None) is Relation.MARKED_BY
                              and ev.target == m),
            "it is marked",
        ),
    ),
)
def m6544a5(c: Cast) -> None:
    """A save against whichever of the four just landed.

    **The marked quarter needs its own path.** Three of the conditions arrive
    as an effect carrying them, so `Effects.save` has something to roll
    against. A mark is a *relation* -- `Relations.set` writes `marked_by` and
    announces only `RelationSet` -- so there is no effect to find, and the
    loop below would come back empty. `c.save(bare=True)` rolls the die on its
    own and `c.cure` takes the mark off, which is what "the effect ends" means
    for a mark.
    """
    for eff in sorted(c.world.effects.of(c.me), key=lambda e: -e.id):
        if eff.conditions and any(cnd in eff.conditions for cnd in _M6544_CONDS):
            c.world.effects.save(eff)
            return
    if c.is_(Condition.MARKED, on=c.me) and c.save(bare=True, on=c.me):
        c.cure(Condition.MARKED, on=c.me)
