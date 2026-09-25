"""Monster abilities, level 12: the controllers.

A stat block's numbers load from `game.db`; this is only its behaviour. The
attack and damage lines are written exactly as printed -- `Attack(vs=WILL,
printed=15)` and `Damage("3d8", 6)` -- and the engine takes the level back
out of the attack and rescales the damage.

The conventions of the eleven levels below are kept: a row printed under an
action heading that is plainly a trait is declared `ActionType.NONE`; a stat
block printing no range at all means melee 1; a **close** burst or blast
with no printed target line is `EACH_ENEMY` and an **area** burst with none
is `EACH_CREATURE`; a cross-referenced id is read as the row every sentence
plainly means; and a helper written for an earlier level is imported rather
than copied.

Paragon brings elites and solos, and eight readings this file had to settle.

**Two turns a round** is a second slot in the initiative order, which is all
`c.extra_turn` says -- and the counts below put the second slot ten under
the first. The other half of the printed line is `Budget.immediate_round`,
which `Encounter.can_spend` compares against the round: stamping it out of
date at the top of each of the creature's turns *is* "its ability to take
immediate actions refreshes on each of its turns".

**"Treated as a critical hit"** is set on the live `AttackResult` inside the
`Hit` window, which is before the striking body rolls its damage and is
where `c.damage` reads the question. `c.maximise` cannot say it here: it
reads the damage line of the row that *applied* it, and the row that applies
this one has none.

**A charge whose blow is the row's own attack line** raises `c.charge` by
hand and walks with `c.run_at`, because `c.charge_at` reaches the swing
through `use` and `use` refuses to re-enter a row already in flight -- which
a row that *is* the charge always is. The reading m3113a2 settled on.

**"It automatically saves against ..."** is a success, and there is no
auto-success to roll: the hold is ended instead, which is the same outcome
with nothing faked. Which holds are charms is read off the keywords of the
row named in the effect's own label.

**An aura that grows over three turns** is a field on the zone, moved and
refreshed rather than torn down and relaid -- relaying announces a full set
of exits and entries and pays every watcher twice. m4841a4 settled it a
level down and m4842a4 is the same row five levels up.

**A zone that penalises or exposes whoever stands in it** is held per
occupant and diffed by `ZoneEntered`/`ZoneExited`: a zone's own fields make
squares rough or blind and carry no modifiers. "Enemies treat the squares as
difficult terrain" is the one exception -- the roughness is a field, given a
label, and this creature's own side is excused from it by name.

**A sustained hold on a creature** is `effects.apply(..., sustain_cost=...)`
with `c.on_sustain` for the payout. `until=When.SUSTAIN` on `c.watch` or
`c.bonus` would make an effect nobody can sustain, because only the area
methods pass a cost along.

**A creature brought in mid-fight never turns its traits on.**
`Encounter._arm_traits` runs once, at `start`, and `join` does not arm
anything -- so a summoned minion's aura is silently absent. `_wake_traits`
does it by hand where a row summons one. See the report.

Each stat block in ref order.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_04.skirmishers import _has_advantage
from combat_engine.content.monsters.level_05.skirmishers import _reach_kind
from combat_engine.content.monsters.level_07.controllers import (
    _hurt_in_melee,
    _rearms_when_bloodied,
)
from combat_engine.content.monsters.level_07.soldiers import _recharge_on
from combat_engine.content.monsters.level_09.brutes import _volley
from combat_engine.content.monsters.level_11.controllers import (
    EVERY_DEFENCE,
    _held_and_softened,
)
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    EACH_CREATURE,
    EACH_ENEMY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
    ONE_OTHER_ALLY,
    PERSONAL,
    REF,
    STANDARD,
    WILL,
    ActionType,
    AreaBurst,
    Attack,
    AttackDeclared,
    Bloodied,
    Budget,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageApplied,
    DamageType,
    Died,
    Dropped,
    Effect,
    Health,
    Hit,
    Ident,
    Initiative,
    Keyword,
    Melee,
    Mod,
    Movement,
    Powers,
    Ranged,
    Relation,
    TurnEnd,
    TurnStart,
    UpTo,
    Usage,
    When,
    Window,
    World,
    ZoneEntered,
    about_me,
    get,
    power,
    spread,
    use,
)
from combat_engine.engine.events import AdjacencyGained, DamageRolled, ZoneExited
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    adjacent,
    alive,
    distance_between,
    has_combat_advantage,
    squares,
    team,
)
from combat_engine.engine.triggers import Trigger
from combat_engine.engine.zones import Zone


def _braced(c: Cast, who: int, amount: int, *, label: str) -> Effect:
    """"A +N bonus to all defenses", as one effect rather than four.

    Four separate effects is four things to take off again when the creature
    walks out of the aura that gave them, and `Mods.total` reads the mods off
    whichever effects are live either way.
    """
    mods = [
        Mod(what=defended.value, value=amount, kind="power", label=label)
        for defended in EVERY_DEFENCE
    ]
    return c.world.effects.apply(
        who, c.me, When.ENCOUNTER, label=label, mods=[(who, m) for m in mods]
    )


def _ring_of(world: World, eid: int, label: str) -> tuple[int, Zone] | None:
    """That creature's own aura, by the label the row that laid it gave it."""
    for zid, zone in world.zones.all():
        if zone.label == label and zone.owner == eid:
            return zid, zone
    return None


def _wake_traits(c: Cast, who: int) -> None:
    """Turn on the traits of a creature that was not here when the fight began.

    `Encounter._arm_traits` runs once, at `start`, and `Encounter.join` --
    which is what `c.summon` puts a new creature into the order with -- does
    not arm anything. So a summoned minion's aura simply never existed. See
    the report.
    """
    known = c.world.get(who, Powers)
    for ref in list(known.all) if known is not None else []:
        p = get(ref)
        if p is not None and p.action is ActionType.NONE:
            use(c.world, who, ref, spend=True)


def _is_minion(world: World, eid: int) -> bool:
    """One hit point is what a minion is, and the number is in the database."""
    health = world.get(eid, Health)
    return health is not None and health.max_hp <= 1


# ==========================================================================
# m167
# ==========================================================================


@power(
    "m167a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 5),
)
def m167a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m167a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("4d8", 5),
)
def m167a1(c: Cast) -> None:
    """A charge with its own attack line in place of the basic one.

    `c.charge_at` reaches the swing through `use`, which refuses to re-enter
    a row already in flight -- and the row in flight is this one. So the flag
    is raised by hand and `c.run_at` walks the approach; the flag is what
    puts `charge` on the attack events and in both modifier contexts, and it
    comes back down afterwards so no later rider is paid twice.
    """
    victim = c.target
    if victim is None:
        return
    c.charge = True
    c.run_at(victim)
    if c.strike(on=victim):
        c.hit(on=victim)
        c.push(1, on=victim)
        c.prone(on=victim)
    c.charge = False


@power(
    "m167a2",
    level=12,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_OTHER_ALLY,
    keywords=[Keyword.HEALING],
)
def m167a2(c: Cast) -> None:
    """The ally chooses which of the two it takes.

    `c.may` asks the **target**, which is who the printed line leaves the
    choice to, and `c.save` defaults to the caster -- so it is aimed. A
    paragon monster carries two surges, so the first half is not inert
    between monsters; a creature with an empty pool has not spent one, and
    the saving throw is what it takes instead.
    """
    who = c.target
    if who is None:
        return
    if c.may("spend a healing surge") and c.surge(on=who):
        return
    c.save(on=who)


@power(
    "m167a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(5, 10),
    target=EACH_CREATURE,
    attack=Attack(vs=WILL, printed=18),
)
def m167a3(c: Cast) -> None:
    """No damage line: the pull is the whole of the hit, and it is measured
    to the burst's origin square rather than to the m167, which is what
    `anchor` is for. The lights themselves are fiction and are noted."""
    if c.first:
        c.note("m167a3: dancing lights appear in the origin square")
    if c.target is None:
        return
    if c.strike():
        c.pull(3, anchor=c.origin)


@power(
    "m167a4",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.TELEPORTATION],
)
def m167a4(c: Cast) -> None:
    """`EACH_ALLY` includes the caster, and "allies" does not, so the m167
    is passed over. "Willing" is the ally's own answer, which is what
    `c.may(who=)` asks; the safe unoccupied square is what `c.teleport`
    offers already, and the line of sight is noted."""
    who = c.target
    if who is None:
        return
    if c.first:
        c.note("m167a4: it arrives in the m167's line of sight")
    if who == c.me:
        return
    if c.may("be teleported", who=who):
        c.teleport(5, who=who)


@power(
    "m167a5",
    level=12,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m167a5(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m193
# ==========================================================================


@power(
    "m193a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 7),
)
def m193a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m193a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=15),
)
def m193a1(c: Cast) -> None:
    """A blow marked before it is struck.

    No damage line: the mark is the whole of the hit. "Treated as a critical
    hit" is set on the live `AttackResult` in the `Hit` window, which is
    before the striking body rolls its damage and is where `c.damage` reads
    the question. `c.maximise` cannot say it: it reads the damage line of the
    row that applied it, and this row has none.

    The extra die is rolled and dealt flat rather than added to the declared
    line, because the declared line is about to be maximised and an extra
    *rolled* die inside a critical would come out maximum too.
    """
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    me = c.me
    hold = c.effect(f"{c.ref} marked", until=When.EONT, on=victim)
    if hold is None:
        return

    def confirm(ev: Hit) -> None:
        if hold.ended or ev.attacker != me or ev.target != victim:
            return
        if _reach_kind(ev) != "melee":
            return
        result = getattr(ev, "result", None)
        if result is None:
            return
        result.critical = True
        c.flat(c.roll("1d12"), on=victim)
        c.world.effects.end(hold, "the marked blow landed")

    hold.subs.append(c.world.bus.on(Hit, confirm, window=Window.BEFORE, owner=me))


@power(
    "m193a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d6", 6, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m193a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)


@power(
    "m193a3",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m193a3(c: Cast) -> None:
    """Two turns a round, one set of actions to each head.

    "Rolls initiative twice" is a second slot in the order, which is all
    `c.extra_turn` says, and ten counts under its own is where the levels
    below put one.

    The last sentence is `Budget.immediate_round`: `Encounter.can_spend`
    refuses an immediate action while that stamp equals the round, so
    stamping it out of date at the top of each of its turns is exactly the
    printed refresh -- and it has to be done on `TurnStart`, which `_begin`
    emits after the budget is refreshed rather than before.
    """
    me = c.me
    init = c.world.get(me, Initiative)
    if init is not None:
        c.extra_turn(at=init.rolled + 10)

    def refresh(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        budget = c.world.get(me, Budget)
        if budget is not None:
            budget.immediate_round = -1

    c.watch(TurnStart, refresh, until=When.ENCOUNTER, on=me, label=c.ref)


def _is_charm(label: str) -> bool:
    """Was the row that laid this hold a charm?

    An effect is labelled with the ref that applied it, and the keyword is on
    the row. Nothing else on an effect says what sort of thing it is.
    """
    p = get(label.split()[0]) if label else None
    return p is not None and Keyword.CHARM in p.keywords


@power(
    "m193a4",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m193a4(c: Cast) -> None:
    """An automatic save is a success, and there is no auto-success to roll.

    `c.save` rolls a real one and `c.unsave` fails it; neither says "it
    succeeds". So the hold is ended, which is the same outcome with nothing
    faked. Only save-ends holds: the printed line says "effects that a save
    can end", and a daze on a turn clock is not one.
    """
    me = c.me
    shaken = {Condition.DAZED, Condition.STUNNED}

    def shrug(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor != me:
            return
        for effect in list(c.world.effects.of(me)):
            if effect.when is not When.SAVE_ENDS:
                continue
            if set(effect.conditions) & shaken or _is_charm(effect.label):
                c.world.effects.end(effect, "m193a4")

    c.watch(TurnEnd, shrug, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m219
# ==========================================================================


@power(
    "m219a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m219a0(c: Cast) -> None:
    """Half of everything but force.

    Not `c.insubstantial`: that condition halves force too, and the printed
    line excepts it. The halving is taken off the damage in the interrupt
    window, which is the one moment the number exists and has not yet come
    off hit points.
    """
    me = c.me

    def half(ev: DamageRolled) -> None:
        if ev.target != me or ev.amount <= 0 or ev.dtype is DamageType.FORCE:
            return
        ev.amount //= 2

    c.watch(DamageRolled, half, until=When.ENCOUNTER, window=Window.BEFORE, on=me, label=c.ref)


@power(
    "m219a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=REF, printed=15),
    damage=Damage("2d10", 5, dtype=DamageType.NECROTIC),
)
def m219a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m219a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("3d6", 9, dtype=DamageType.PSYCHIC),
)
def m219a2(c: Cast) -> None:
    """The penalty is printed as an Effect rather than under the Hit, so it
    lands whether or not the attack did."""
    if c.strike():
        c.hit()
    if c.target is not None:
        _held_and_softened(c, c.target, defences=2)


@power(
    "m219a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d8", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m219a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(5)
        c.immobilized(until=When.SAVE_ENDS)


# ==========================================================================
# m2861
# ==========================================================================


@power(
    "m2861a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d6", 5),
)
def m2861a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m2861a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    requires=_has_advantage,
    requires_text="the m2861 must have combat advantage against the target",
)
def m2861a1(c: Cast) -> None:
    """Two swings of the row that prints them.

    The printed requirement is per target and the header's `requires` is
    handed only the board, so it carries the half about the creature and the
    aim is narrowed here -- the reading m102a1 settled on six levels down.

    "Both attacks hit the same target" is only ever true when the header
    aimed both at one creature, which is what `_volley` reports; it counts
    the hits off the bus, because `use` says whether a row could be used and
    not whether it landed.
    """
    victim = c.target
    if victim is None or not has_combat_advantage(c.world, c.me, victim):
        victim = c.choose(
            [
                foe
                for foe in c.enemies()
                if c.adjacent(foe) and has_combat_advantage(c.world, c.me, foe)
            ],
            f"{c.ref}: which creature",
        )
    if victim is None:
        return
    if _volley(c, "m2861a0", victim):
        c.ongoing(10, on=victim)


_M2861_CLOSED = "an enemy moves into a square adjacent to the m2861"


def _enemy_stepped_in(world: World, me: int, ev: Any) -> bool:
    """The mirror of `AdjacencyGained` that names the *enemy* as its actor.

    The event is emitted twice, once from each end, and `closed_on_me` is
    true of both -- so the dispatcher would aim this row at whichever mirror
    came first, and on one of them `_at` reads the m2861's own id and gives
    up. Naming the mover as the actor is what puts the swing on the creature
    that walked in.
    """
    mover = getattr(ev, "mover", 0)
    actor = getattr(ev, "actor", None)
    if actor is None or actor == me or mover != actor:
        return False
    return getattr(ev, "other", None) == me and team(world, actor) is not team(world, me)


@power(
    "m2861a2",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d6", 2),
    trigger=_M2861_CLOSED,
    on=Trigger(AdjacencyGained, when=_enemy_stepped_in, text=_M2861_CLOSED),
)
def m2861a2(c: Cast) -> None:
    """Filed as a move action and printed as an immediate reaction; the
    printed one is the action line the trigger belongs to."""
    if c.strike():
        c.hit()


@power(
    "m2861a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=16),
)
def m2861a3(c: Cast) -> None:
    """No damage line: the domination is the whole of the hit."""
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


# ==========================================================================
# m2937
# ==========================================================================


@power(
    "m2937a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 5),
)
def m2937a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2937a1",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("3d8", 5, dtype=DamageType.LIGHTNING, kind=LIMITED),
)
def m2937a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m2937a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.TELEPORTATION, Keyword.THUNDER],
    attack=Attack(vs=REF, printed=16),
    damage=Damage("1d10", 5, dtype=DamageType.THUNDER),
)
def m2937a2(c: Cast) -> None:
    """The Effect line moves it after the thunder has landed, so it is taken
    on the last pass -- and `c.last` is true on the empty pass too, which is
    what a burst that caught nobody gets.

    The squares are the ring just outside the burst, and `c.teleport` is
    given a range wide enough to reach any of them: the printed line names
    the destination rather than a distance.
    """
    if c.target is not None and c.strike():
        c.hit()
    if not c.last:
        return
    area = c.area()
    outside = sorted(spread(area, 1) - area)
    landing = c.choose(outside, f"{c.ref}: where it reappears") if outside else None
    if landing is not None:
        c.teleport(3, to=landing)


# ==========================================================================
# m45
# ==========================================================================


@power(
    "m45a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d10", 6),
)
def m45a0(c: Cast) -> None:
    """The burn is a second packet and is poison; the declared line is not,
    because the printed damage is untyped and only the ongoing is named."""
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m45a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 6),
)
def m45a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m45a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
)
def m45a2(c: Cast) -> None:
    """Two swings of the row that prints them. The printed Effect does not
    say whether they land on one creature or two, so the header takes up to
    two and a single target is hit twice."""
    if c.target is not None:
        _volley(c, "m45a1", c.target)


@power(
    "m45a3",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m45a3(c: Cast) -> None:
    """It flies past and bites on the way.

    Declared with no target: the dispatcher aims a row before the body runs,
    and the creature bitten here is chosen from everything within the flight
    rather than from whatever is already in reach. `c.no_provoke(from_=)` is
    the printed exemption and it names the target and nobody else.
    """
    foes = sorted(f for f in c.enemies() if c.distance(f) <= 12)
    victim = c.choose(foes, f"{c.ref}: who it dives at") if foes else None
    if victim is None:
        return
    c.no_provoke(from_=victim, until=When.EOT)
    c.run_at(victim)
    use(c.world, c.me, "m45a0", targets=[victim], spend=False)


_M45_STILL = "an adjacent enemy does not move on its turn"

#: The `MoveEnd.kind_` of a move a creature made of its own accord.
_UNDER_ITS_OWN_POWER = ("walk", "shift", "teleport", "run")


def _stood_still(world: World, me: int, ev: Any) -> bool:
    """An adjacent enemy finished a turn without moving.

    Nothing records what a creature did with its turn, so the bus is read
    back: everything since that creature's own `TurnStart` is its turn. The
    triggering `TurnEnd` is already in the log when a predicate sees it,
    which is why the walk starts at the end and stops at the turn's start.

    Only a move the creature made **itself** counts. `MoveEnd.kind_` is what
    tells one from the others: a shove emits no `MoveEnd` at all, and the
    landing `settle` gives a flyer at the end of every one of its turns
    emits one with no kind -- and reading `Moved` instead counted that
    landing, so "does not move" was false for every flying creature alive.
    """
    who = getattr(ev, "actor", None)
    if who is None or who == me or getattr(ev, "ghost", False):
        return False
    if team(world, who) is team(world, me) or not adjacent(world, me, who):
        return False
    for past in reversed(world.bus.log):
        if getattr(past, "actor", None) != who:
            continue
        if past.kind == "TurnStart":
            return True
        if past.kind == "MoveEnd" and getattr(past, "kind_", "") in _UNDER_ITS_OWN_POWER:
            return False
    return False


@power(
    "m45a4",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=15),
    damage=Damage("1d8", 6),
    trigger=_M45_STILL,
    on=Trigger(TurnEnd, when=_stood_still, text=_M45_STILL),
)
def m45a4(c: Cast) -> None:
    """Filed as a move action and printed as an immediate reaction."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m45a5",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.GAZE],
    attack=Attack(vs=WILL, printed=15),
)
def m45a5(c: Cast) -> None:
    """No damage line: the slide is the whole of the hit."""
    if c.strike():
        c.slide(2)


@power(
    "m45a6",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d10", 5, dtype=DamageType.POISON, kind=LIMITED),
)
def m45a6(c: Cast) -> None:
    """"Save ends both" is one effect carrying the slow and the burn, so the
    printed sentence gets the one saving throw it prints. The Aftereffect
    hangs on that effect's ending rather than on `escalate`: escalation runs
    on a *failed* save, and an aftereffect is what follows either way."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.condition(
        Condition.SLOWED,
        until=When.SAVE_ENDS,
        on=victim,
        ongoing=(5, DamageType.POISON),
    )
    if hold is not None:
        hold.on_end.append(lambda: c.slowed(until=When.SAVE_ENDS, on=victim))


_M45_BLOODIED = "the m45 is first bloodied"


@power(
    "m45a7",
    level=12,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
    trigger=_M45_BLOODIED,
    on=Trigger(Bloodied, when=about_me, text=_M45_BLOODIED),
)
def m45a7(c: Cast) -> None:
    """The card spells the breath as another stat block's id; the row every
    sentence here plainly means is this creature's own poison breath, which
    is the only recharge power it has that the Poison keyword fits.

    `Bloodied` is emitted on the crossing and only then, so "when first
    bloodied" needs nothing on top of the trigger.
    """
    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m45a6")
    use(c.world, c.me, "m45a6", spend=True)


@power(
    "m45a8",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=15),
)
def m45a8(c: Cast) -> None:
    """No damage line: the stun is the whole of the hit, and the Aftereffect
    follows the stun ending whichever way it ended."""
    if not c.strike():
        return
    victim = c.target
    hold = c.stunned(until=When.EONT, on=victim)
    if hold is not None:
        hold.on_end.append(
            lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim)
        )


# ==========================================================================
# m467
# ==========================================================================

#: How many creatures the m467 can hold at once. The printed line counts
#: limbs; the engine counts grabs, which is the same number.
_M467_ARMS = 4


def _held_by(world: World, eid: int) -> list[int]:
    return [
        who
        for who in world.relations.targets(Relation.GRABBED_BY, eid)
        if alive(world, who)
    ]


def _an_arm_free(world: World, eid: int) -> bool:
    return len({*_held_by(world, eid)}) < _M467_ARMS


def _is_grabbing(world: World, eid: int) -> bool:
    return bool(_held_by(world, eid))


@power(
    "m467a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d10", 4),
)
def m467a0(c: Cast) -> None:
    """No range is printed, and melee 1 is what a stat block giving none
    means."""
    if c.strike():
        c.hit()


@power(
    "m467a1",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d4", 5),
    requires=_an_arm_free,
    requires_text="the m467 must have a limb not already holding somebody",
)
def m467a1(c: Cast) -> None:
    """Four limbs, and four creatures at most -- which the header refuses
    rather than the body, because "it can grab up to four" is a condition on
    using the row at all.

    A second limb on the same creature is a second grab, which is how the
    row below counts them. The escape penalty per extra limb is not written:
    there are no escape checks in the engine, so there is no number to
    penalise. See the report.
    """
    if not c.strike():
        return
    c.hit()
    c.grab()
    c.note("m467a1: each extra limb on one creature is -2 to its escape check")


@power(
    "m467a2",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING, Keyword.NECROTIC],
)
def m467a2(c: Cast) -> None:
    """Five per limb, which is five per grab: a creature caught in two of
    them carries two. The undead are passed over -- the printed line draws
    from every *living* target it is holding."""
    me = c.me
    drawn = 0
    for who in sorted(_held_by(c.world, me)):
        if c.is_kind("undead", on=who):
            continue
        limbs = sum(
            1
            for eff in c.world.effects.of(who)
            if eff.source == me and eff.label.endswith("grab")
        )
        drawn += c.flat(5 * max(1, limbs), dtype=DamageType.NECROTIC, on=who)
    if drawn:
        c.heal(drawn, on=me)


@power(
    "m467a3",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m467a3(c: Cast) -> None:
    """A bonus that comes and goes with the grabs.

    The gate reads the board rather than the modifier context, which is what
    lets one standing effect answer a question that changes every time
    something is caught or gets loose.
    """
    me = c.me

    def while_holding(_ctx: dict[str, Any]) -> bool:
        return _is_grabbing(c.world, me)

    for defended in EVERY_DEFENCE:
        c.bonus(
            defended,
            2,
            until=When.ENCOUNTER,
            on=me,
            kind="untyped",
            when=while_holding,
        )


# ==========================================================================
# m4842
# ==========================================================================

#: The aura m4842a0 lays down. Two other rows move it and read it; the
#: printed lines name it by an id belonging to a smaller cousin's stat
#: block, and this is the aura they mean.
_M4842_AURA = "m4842a0"


def _m4842_ring_at_one(world: World, eid: int) -> bool:
    """The printed recharge condition: the aura must be back at its own size.

    Nothing rolls a die for that row -- recharge 1 always comes back -- so
    this is what actually decides when it is available.
    """
    found = _ring_of(world, eid, _M4842_AURA)
    return found is not None and found[1].aura == 1


@power(
    "m4842a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4842a0(c: Cast) -> None:
    """An aura 1 for the board to draw, and the shove taken at the end of a
    turn -- which is neither of the two moments `c.burns` covers."""
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER, label=c.ref)

    def shove(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.slide(1, on=ev.actor)

    c.watch(TurnEnd, shove, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4842a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("2d8", 6, dtype=DamageType.COLD),
)
def m4842a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.immobilized(until=When.EONT)


@power(
    "m4842a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d6", 10, dtype=DamageType.COLD),
)
def m4842a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m4842a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4842a3(c: Cast) -> None:
    """Two swings of the rows that print them, aimed one at a time: the
    second is chosen after the first has resolved, which is the printed
    order and matters when the first one kills."""
    pair = c.choose(["one of each", "the second one twice"], f"{c.ref}: which pair")
    refs = (
        ["m4842a2", "m4842a2"]
        if pair == "the second one twice"
        else ["m4842a1", "m4842a2"]
    )
    for ref in refs:
        reachable = sorted(f for f in c.within(2, side="enemy") if alive(c.world, f))
        foe = c.choose(reachable, f"{c.ref}: who the claws find") if reachable else None
        if foe is None:
            return
        use(c.world, c.me, ref, targets=[foe], spend=False)


@power(
    "m4842a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=1,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("3d8", 6, dtype=DamageType.COLD, kind=LIMITED),
    requires=_m4842_ring_at_one,
    requires_text="the m4842's aura must be at its own size",
)
def m4842a4(c: Cast) -> None:
    """Three turns in one row: the aura widens, widens again, and breaks.

    The attack is two turns off, so the row declares no targets and no reach
    -- `c.strike(on=...)` still rolls the line the header holds, which is
    what keeps the numbers data.

    The radius is a field on the zone, moved and refreshed rather than torn
    down and relaid: relaying announces a full set of exits and entries and
    fires every row watching the aura twice.
    """
    found = _ring_of(c.world, c.me, _M4842_AURA)
    if found is None:
        return
    _, ring = found
    ring.aura = 3
    c.world.zones.refresh()
    me = c.me
    stage = {"n": 0}

    def tick(ev: TurnStart) -> None:
        if ev.ghost or ev.actor != me:
            return
        stage["n"] += 1
        if stage["n"] == 1:
            ring.aura = 5
            c.world.zones.refresh()
            return
        for foe in sorted(c.within(5, side="enemy")):
            if c.strike(on=foe):
                c.hit(on=foe)
                c.condition(
                    Condition.IMMOBILIZED,
                    Condition.BLINDED,
                    until=When.SAVE_ENDS,
                    on=foe,
                )
        ring.aura = 1
        c.world.zones.refresh()
        c.world.effects.end(clock, "the breath is spent")

    clock = c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=c.ref)


_M4842_HURT = "an enemy's melee attack deals damage to the m4842"


@power(
    "m4842a5",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.COLD],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("1d10", 9, dtype=DamageType.COLD, kind=LIMITED),
    trigger=_M4842_HURT,
    on=Trigger(DamageApplied, when=_hurt_in_melee, text=_M4842_HURT),
)
def m4842a5(c: Cast) -> None:
    """The printed trigger is damage landing, so a blow a resistance ate
    whole is not one; `by_melee` reads the reach off the row named in the
    event. The card prints a recharge die *and* says it comes back when the
    m4842 is first bloodied, and both are honoured."""
    if c.first:
        _rearms_when_bloodied(c)
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


_M4842_CHILLED = "the m4842 is hit by a cold attack"


def _hit_by_cold(world: World, me: int, ev: Any) -> bool:
    """`targets_me` plus the keyword, written out because the ready-made
    combinator pair reads the power off the event and this one has to as
    well -- and `about_me` would be false forever here, since an attack
    event names its subject `target`."""
    if getattr(ev, "target", None) != me:
        return False
    p = get(getattr(ev, "power", "") or "")
    return p is not None and Keyword.COLD in p.keywords


@power(
    "m4842a6",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4842_CHILLED,
    on=Trigger(Hit, when=_hit_by_cold, text=_M4842_CHILLED),
)
def m4842a6(c: Cast) -> None:
    found = _ring_of(c.world, c.me, _M4842_AURA)
    if found is None:
        return
    for foe in c.world.zones.occupants(found[0]):
        if foe != c.me and foe in c.enemies():
            c.slide(1, on=foe)


# ==========================================================================
# m4878
# ==========================================================================


@power(
    "m4878a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4878a0(c: Cast) -> None:
    """A zone's own fields carry no modifiers and vulnerability is one, so
    it is held per occupant and diffed by the two events that say who is
    standing in the aura."""
    me = c.me
    held: dict[int, Effect] = {}
    ring = c.aura(3, until=When.ENCOUNTER, label=c.ref)

    def expose(who: int) -> None:
        if who in held or who not in c.enemies():
            return
        exposed = c.vulnerable(5, DamageType.PSYCHIC, until=When.ENCOUNTER, on=who)
        if exposed is not None:
            held[who] = exposed

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            expose(ev.actor)

    def left(ev: ZoneExited) -> None:
        exposed = held.pop(ev.actor, None) if ev.zone == ring else None
        if exposed is not None:
            c.world.effects.end(exposed, "left the aura")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} in")
    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=me, label=f"{c.ref} out")
    for actor in c.world.zones.occupants(ring):
        expose(actor)


@power(
    "m4878a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage("3d8", 5),
)
def m4878a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4878a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.TELEPORTATION],
    attack=Attack(vs=FORT, printed=15),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC),
)
def m4878a2(c: Cast) -> None:
    """The ally arrives beside the target, so the square is named rather
    than offered: `c.teleport` without `to` goes through the decider, which
    with nobody playing the monster takes the lowest-sorted square on the
    board. The distance given is the reach to that square and not a printed
    limit -- the printed line names the destination and no number."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    kin = sorted(
        a
        for a in c.allies()
        if a != c.me
        and alive(c.world, a)
        and c.is_kind("aberrant", on=a)
        and distance_between(c.world, a, victim) <= 5
    )
    who = c.choose(kin, f"{c.ref}: which of its kind steps in")
    if who is None:
        return
    free = sorted(
        sq
        for sq in spread(squares(c.world, victim), 1) - squares(c.world, victim)
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    )
    if free:
        c.teleport(10, who=who, to=free[0])


@power(
    "m4878a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.TELEPORTATION],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC),
)
def m4878a3(c: Cast) -> None:
    """The m4878 does the teleporting and the target does the moving, which
    is what `who=` says."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.immobilized(until=When.SAVE_ENDS, on=victim)
    c.teleport(2, who=victim)


def _m4878_zone(c: Cast) -> None:
    """The zone, its teeth, and the leash it puts on whoever is inside.

    The listeners hang on the zone's **own** effect rather than on a
    `c.watch`: `until=When.SUSTAIN` on a watch makes an effect nobody can
    sustain, because only the area methods pass a sustain cost along. Hung
    here they come down with the zone, which is the printed duration.

    "Enters the zone or ends its turn there" is not what `c.burns` covers --
    that one bites on entering and on *starting* a turn -- so the pair is
    written out with the same once-a-round latch.
    """
    me = c.me
    zone_id = c.zone(c.area(), label=c.ref, until=When.SUSTAIN, sustain=MINOR)
    held = dict(c.world.zones.all()).get(zone_id)
    anchor = held.effect if held is not None else None
    struck: dict[int, int] = {}

    def bite(who: int) -> None:
        if who not in c.enemies() or struck.get(who) == c.world.round:
            return
        struck[who] = c.world.round
        c.flat(10, dtype=DamageType.PSYCHIC, on=who)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == zone_id:
            bite(ev.actor)

    def lingered(ev: TurnEnd) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(zone_id):
            bite(ev.actor)

    def penned(ev: AttackDeclared) -> None:
        if ev.attacker not in c.world.zones.occupants(zone_id):
            return
        if ev.attacker not in c.enemies():
            return
        if distance_between(c.world, ev.attacker, ev.target) > 3:
            ev.cancel(f"{c.ref}: it can reach nothing further than 3 squares")

    if anchor is not None:
        anchor.subs.append(c.world.bus.on(ZoneEntered, entered, owner=me))
        anchor.subs.append(c.world.bus.on(TurnEnd, lingered, owner=me))
        anchor.subs.append(
            c.world.bus.on(AttackDeclared, penned, window=Window.BEFORE, owner=me)
        )
    c.note(f"{c.ref}: the m4878 can move the zone 4 squares as a move action")


@power(
    "m4878a4",
    level=12,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(2, 5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.ZONE],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("2d6", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m4878a4(c: Cast) -> None:
    """The Effect line is printed beside the attack rather than under a hit,
    so the zone is laid on the first pass whether or not anybody was in it.

    Moving the zone as a move action is not written: a row cannot offer a
    second action of its own, and nothing else on the zone can. It is noted.
    See the report.
    """
    if c.first:
        _m4878_zone(c)
    if c.target is None:
        return
    if c.strike():
        c.hit()


# ==========================================================================
# m4967
# ==========================================================================

#: What the m4967 makes copies of. The printed line says to choose whichever
#: of them best reflects the target, and these are the two there are.
_MOSSLINGS = ("m4971", "m4972")


def _is_mossling(world: World, eid: int) -> bool:
    ident = world.get(eid, Ident)
    return ident is not None and ident.ref in _MOSSLINGS


def _duplicates(world: World, eid: int) -> list[int]:
    """The copies this creature made, which is what `c.bind` records."""
    return [
        made
        for made in world.relations.targets(Relation.MASTER_OF, eid)
        if alive(world, made) and _is_mossling(world, made)
    ]


@power(
    "m4967a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4967a0(c: Cast) -> None:
    """Unseen by whoever begins a turn too close to it.

    The hold runs to the start of that creature's *own* next turn, which is
    `SOTNT` and not the caster's clock -- and it is asked again every turn,
    because who is standing in the aura changes.
    """
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER, label=c.ref)

    def blur(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring):
            c.invisible(to=ev.actor, until=When.SOTNT)

    c.watch(TurnStart, blur, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m4967a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID],
    attack=Attack(vs=AC, printed=17),
    damage=Damage("1d8", 5, dtype=DamageType.ACID),
)
def m4967a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.ACID)


@power(
    "m4967a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("3d6", 7, dtype=DamageType.PSYCHIC),
)
def m4967a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(5)


@power(
    "m4967a3",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
    damage=Damage("3d6", 7, dtype=DamageType.PSYCHIC),
)
def m4967a3(c: Cast) -> None:
    """"The m4967 **or one of its allies**" is the half `c.invisible` cannot
    say: it hides the caster and takes no `on=`. For an ally the relation it
    holds -- one creature unseen by one other -- is applied directly, which
    is the same hold under the same clock."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    pool = [c.me, *sorted(a for a in c.allies() if alive(c.world, a))]
    who = c.choose(pool, f"{c.ref}: who goes unseen")
    if who is None or who == c.me:
        c.invisible(to=victim, until=When.EONT)
        return
    c.world.effects.apply(
        who,
        c.me,
        When.EONT,
        label=f"{c.ref} unseen",
        relations=[(Relation.HIDDEN_FROM, who, victim)],
    )


@power(
    "m4967a4",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=15),
)
def m4967a4(c: Cast) -> None:
    """A copy of the victim, and the victim left without its best rows.

    No damage line: the hold is the whole of the hit. "Save ends both" is one
    saving throw, so the rows taken away run to the end of the fight and are
    handed back by the daze's own ending -- two save-ends effects would be
    two saving throws against one printed sentence.

    The printed recharge is a sentence on top of the die the database files:
    it comes back when nothing it made is left standing.

    The copy is bound as a servant, which is what "created by the m4967"
    comes to and what the moslings' own trait reads; and its traits are
    turned on by hand, because nothing arms the traits of a creature that
    joins a fight after it has started.
    """
    me = c.me
    _recharge_on(c, Died, lambda _ev: not _duplicates(c.world, me))
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    hold = c.condition(Condition.DAZED, until=When.SAVE_ENDS, on=victim)
    known = c.world.get(victim, Powers)
    if hold is not None and known is not None:
        for ref in list(known.all):
            p = get(ref)
            if p is None or not p.is_attack:
                continue
            if p.usage not in (Usage.ENCOUNTER, Usage.DAILY):
                continue
            gone = c.forbid(ref, on=victim, until=When.ENCOUNTER)
            if gone is not None:
                hold.on_end.append(
                    lambda g=gone: c.world.effects.end(g, "the daze passed")
                )
    ref = c.choose(list(_MOSSLINGS), f"{c.ref}: which duplicate it grows")
    if ref is None:
        return
    where = sorted(
        sq
        for sq in spread(squares(c.world, me), 5)
        if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
    )
    made = c.summon(ref, at=where[0] if where else None)
    if not made:
        return
    c.bind(on=made)
    _wake_traits(c, made)


@power(
    "m4967a5",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4967a5(c: Cast) -> None:
    """Any mossling, not only the ones it made -- the printed line names the
    kind of creature and not the relation."""
    pool = sorted(
        w
        for w in c.allies()
        if alive(c.world, w) and _is_mossling(c.world, w) and c.distance(w) <= 10
    )
    who = c.choose(pool, f"{c.ref}: which one runs")
    if who is not None:
        c.move(c.speed_of(who), who=who)


_M4967_MOSSLING_HURT = "a mossling within 20 squares of the m4967 takes damage"


def _mossling_hurt(world: World, me: int, ev: Any) -> bool:
    who = getattr(ev, "target", None)
    if who is None or who == me or getattr(ev, "amount", 0) <= 0:
        return False
    if not _is_mossling(world, who) or team(world, who) is not team(world, me):
        return False
    return distance_between(world, me, who) <= 20


@power(
    "m4967a6",
    level=12,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4967_MOSSLING_HURT,
    on=Trigger(DamageRolled, when=_mossling_hurt, text=_M4967_MOSSLING_HURT),
)
def m4967a6(c: Cast) -> None:
    """`DamageRolled` rather than `DamageApplied`: taking the blow instead of
    somebody else means taking it before it lands, which is the one window
    where the number still exists and can be moved."""
    c.absorb(c.trigger)


# ==========================================================================
# m4971
# ==========================================================================

_M4971_WARD = "m4971a0 ward"


def _acts_after_its_creator(c: Cast) -> None:
    """Move this creature's slot to just under its creator's.

    `c.extra_turn` splices by initiative count, so the slot is taken out and
    put back one count below the creator's -- which is the order's own way of
    saying "immediately after". Its own `Initiative.rolled` goes with it, so
    anything spliced in later sorts against a count it can see.

    Done when the creator's turn ends rather than now: `Encounter._arm_traits`
    walks the initiative order while it arms, and editing that list underneath
    the loop would skip or repeat other creatures' traits. Nothing is walking
    the order in the `TurnEnd` window, and `advance` steps the cursor
    afterwards -- onto the slot just inserted.
    """
    me = c.me
    done: list[bool] = []

    def follow(ev: TurnEnd) -> None:
        boss = c.master()
        if done or ev.ghost or boss is None or ev.actor != boss:
            return
        enc = c.world.encounter
        theirs = c.world.get(boss, Initiative)
        mine = c.world.get(me, Initiative)
        if enc is None or theirs is None or mine is None or me not in enc.order:
            return
        done.append(True)
        was = enc.order.index(me)
        enc.order.pop(was)
        if was < enc.index:
            enc.index -= 1
        mine.rolled = theirs.rolled - 1
        c.extra_turn(at=mine.rolled)

    c.watch(TurnEnd, follow, until=When.ENCOUNTER, on=me, label=f"{c.ref} order")


@power(
    "m4971a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4971a0(c: Cast) -> None:
    """"Plant allies" leaves the m4971 itself out, and a zone's own fields
    carry no modifiers -- so the ward is held per occupant and diffed by the
    two events that say who is standing in the aura."""
    me = c.me
    held: dict[int, Effect] = {}
    ring = c.aura(1, until=When.ENCOUNTER, label=c.ref)

    def brace(who: int) -> None:
        if who in held or who == me or who not in c.allies():
            return
        if not c.is_kind("plant", on=who):
            return
        held[who] = _braced(c, who, 2, label=_M4971_WARD)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            brace(ev.actor)

    def left(ev: ZoneExited) -> None:
        ward = held.pop(ev.actor, None) if ev.zone == ring else None
        if ward is not None:
            c.world.effects.end(ward, "left the aura")

    c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} in")
    c.watch(ZoneExited, left, until=When.ENCOUNTER, on=me, label=f"{c.ref} out")
    for actor in c.world.zones.occupants(ring):
        brace(actor)


@power(
    "m4971a1",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4971a1(c: Cast) -> None:
    """"Created by an m4967" is the servant relation, which is the only thing
    on the board that says one creature made another -- `c.summon` alone
    records nothing, and the row that makes a duplicate binds it."""
    _acts_after_its_creator(c)


@power(
    "m4971a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=10, kind=MINION),
)
def m4971a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EOTNT)


_M4971_FALLS = "the m4971 drops to 0 hit points"


@power(
    "m4971a4",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4971_FALLS,
    on=Trigger(Dropped, when=about_me, text=_M4971_FALLS),
)
def m4971a4(c: Cast) -> None:
    """A death throe. `Dropped` names its subject `actor`, so `about_me` is
    the predicate that reads it, and the dispatcher offers a row about a
    creature's own downfall to that creature even though it is no longer
    alive.

    "Nonminion" is one hit point, which is in the database.
    """
    me = c.me
    for who in c.allies():
        if who == me or _is_minion(c.world, who) or not alive(c.world, who):
            continue
        if c.is_kind("plant", on=who) and distance_between(c.world, me, who) <= 3:
            c.temp_hp(20, on=who)


# ==========================================================================
# m4972
# ==========================================================================


@power(
    "m4972a0",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4972a0(c: Cast) -> None:
    """Rough going for one side only.

    Difficult terrain is a property of the square and not of who is standing
    on it, so the aura's squares are made rough under a label of their own
    and this creature's side is excused from that label by name -- which is
    what `c.ignores_difficult(kind)` is for, and the only way the engine can
    say "enemies treat".

    `c.aura` takes no `difficult`, so the field is set on the zone and the
    membership recomputed, the same way the growing auras move a radius.
    """
    me = c.me
    ring = c.aura(1, until=When.ENCOUNTER, label=c.ref)
    zone = dict(c.world.zones.all()).get(ring)
    if zone is not None:
        zone.difficult = c.ref
        c.world.zones.refresh()
    for friend in [me, *c.allies()]:
        if c.world.get(friend, Movement) is not None:
            c.ignores_difficult(c.ref, on=friend, until=When.ENCOUNTER)


@power(
    "m4972a1",
    level=12,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4972a1(c: Cast) -> None:
    """The same sentence as m4971a1, and the same relation answers it."""
    _acts_after_its_creator(c)


@power(
    "m4972a2",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(3),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=17),
    damage=Damage(bonus=10, kind=MINION),
)
def m4972a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


_M4972_FALLS = "the m4972 drops to 0 hit points"


@power(
    "m4972a4",
    level=12,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger=_M4972_FALLS,
    on=Trigger(Dropped, when=about_me, text=_M4972_FALLS),
)
def m4972a4(c: Cast) -> None:
    """A death throe, and the ground it leaves takes nobody's side: this
    roughness is unlabelled, so nothing is excused from it."""
    mine = squares(c.world, c.me) or {c.here}
    c.zone(spread(mine, 1), label=c.ref, until=When.ENCOUNTER, difficult=True)


# ==========================================================================
# m679
# ==========================================================================


@power(
    "m679a0",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("1d6", 4),
)
def m679a0(c: Cast) -> None:
    """It heals by what it dealt, so the number `c.hit` returns is the
    number -- and that is what came off hit points after resistance, which
    is what "the amount of damage dealt" reads as."""
    if not c.strike():
        return
    dealt = c.hit()
    c.dazed(until=When.SAVE_ENDS)
    if dealt > 0:
        c.heal(dealt, on=c.me)


_M679_DRAIN = "m679a1 hold"


@power(
    "m679a1",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(5),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=16),
    damage=Damage("3d6", 4),
)
def m679a1(c: Cast) -> None:
    """A hold that pays out every time it is kept.

    The sustain cost goes on the effect itself -- `effects.apply` takes one
    and `c.watch` does not -- and `c.on_sustain` carries the payout half,
    which a clock refreshing on its own would drop. The printed range check
    is made at payout rather than now, because the target can walk out of it.

    One at a time: the previous hold is let go as the new one is taken,
    since one minor action cannot keep two.
    """
    me, ref = c.me, c.ref
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    c.hit(on=victim)
    for eff in list(c.world.effects.of(me)):
        if eff.label == _M679_DRAIN:
            c.world.effects.end(eff, "it took hold of somebody else")
    held = c.world.effects.apply(
        me, me, When.SUSTAIN, label=_M679_DRAIN, sustain_cost=MINOR
    )

    def again() -> None:
        if not alive(c.world, victim) or distance_between(c.world, me, victim) > 5:
            c.world.effects.end(held, "the target is out of reach")
            return
        c.damage("3d6", 4, on=victim, detail=ref)

    c.on_sustain(held, again)


@power(
    "m679a2",
    level=12,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=16),
)
def m679a2(c: Cast) -> None:
    """No damage line: the stun is the whole of the hit."""
    if c.strike():
        c.stunned(until=When.SAVE_ENDS)


_M679_SHAPE = "m679a3 shape"


@power(
    "m679a3",
    level=12,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
)
def m679a3(c: Cast) -> None:
    """A shape with no mechanics inside it: `c.form` is what the engine holds
    a polymorph in, and the minor action it cost is the printed way back. A
    shape already worn is dropped first -- this is not a stance, so nothing
    ends the old one on its own."""
    for eff in list(c.world.effects.of(c.me)):
        if eff.label == _M679_SHAPE:
            c.world.effects.end(eff, "it changed shape again")
    c.form(until=When.ENCOUNTER, revert=MINOR, label=_M679_SHAPE)
    c.note("m679a3: it takes the shape of a Medium humanoid of any race or gender")


@power(
    "m679a4",
    level=12,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m679a4(c: Cast) -> None:
    """Narrative only. The board has no small openings to go through, and
    `Condition.SQUEEZING` is the opposite of what this line grants: it is the
    penalty for being somewhere too tight, not permission to be there."""
    c.note("m679a4: it fits through small openings as though it were Tiny")
