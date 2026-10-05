"""Monster abilities, level 10, skirmishers -- the second wave.

`skirmishers.py` holds the earlier sweep of this level and is not touched
here. 191 rows across thirty-three stat blocks.

Conventions, inherited from the nine levels below and from this level's own
`skirmishers.py`:

* numbers load from `game.db` -- the attack line is written exactly as
  printed (`Attack(vs=AC, printed=15)`) and the damage line goes in the
  header as data;
* a **trait** costs no action, has no target, and arms whatever holds it,
  whatever action the compendium's column claims;
* a card with no printed range is melee 1; a printed band like "6/12" takes
  the short number;
* a card naming a creature's kind, size or condition rather than its side
  or count is read with `_restricted_to`, and the redirect carries the symbol
  for the gap it has -- `Target.condition` for a condition, `Target.ongoing`
  for a target taking ongoing damage. A line narrowed by how the creature
  stands to the caster ("grabbed by it", "not grabbed by it") is the target
  line itself: `Target(..., relation=..., without=...)`;
* a close burst or blast whose card names no target set takes enemies,
  except where the card says "creatures in the burst" outright.

Several cards in this batch print text that plainly belongs to a
*different* stat block: a bare ref swapped for a flavour word (`m1172a3`
prints "the m1173 shifts"), a sentence that names a restriction this row's
own attack never imposes (`m2065a4`, `m2250a4` both read "even if the target
isn't taking ongoing poison damage" against a power that has no such
restriction to begin with, and each names the *other* one's own ref inside
its own text), and one block whose aura trait excludes "nonjovoc" creatures
-- a species word, not a kind this file will repeat. Each is read for its
plain mechanical meaning and flagged in the report rather than silently
reproduced or guessed into something more specific than the text supports.

Helpers imported rather than written again, from eight levels below and
from this level's own `skirmishers.py` and `skirmishers_sa.py`: the
restricted-target redirect, the triggering-enemy reader, the melee-only
damage gate, the all-defences tuple, the secondary-attack roller, a free
square beside a creature, a printed recharge condition, the "moved far from
where it started" payout, an adjacent foe picker, a run-and-swing
Requirement, the combat-advantage damage gate, the reroll-any-d20 dispatch,
a "stood still on its turn" predicate, an "attack roll that would hit"
predicate, and the drag-the-grabbed-creature-along step.

New here: a once-per-encounter regeneration that skips the turn after
radiant damage (two stat blocks print it with different numbers), and a
form toggle for a shapechanger whose two shapes are each other's own
printed ref.
"""

from __future__ import annotations

from combat_engine.content.monsters.level_01.skirmishers_sa import _moved_far
from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES
from combat_engine.content.monsters.level_02.controllers_sa import _swing_reach
from combat_engine.content.monsters.level_02.lurkers_sa import _triggering_enemy
from combat_engine.content.monsters.level_02.skirmishers_sa import _melee_only
from combat_engine.content.monsters.level_02.soldiers_sa import _missed_me_in_melee
from combat_engine.content.monsters.level_03.lurkers_sa import _restricted_to
from combat_engine.content.monsters.level_03.skirmishers import (
    _free_square_beside,
    _recharge_on,
)
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_04.skirmishers_sa import _hauls_the_grabbed
from combat_engine.content.monsters.level_05.skirmishers_sa import _edge_on_target
from combat_engine.content.monsters.level_08.skirmishers import _adjacent_foe
from combat_engine.content.monsters.level_08.skirmishers_sa import _rolled_would_hit
from combat_engine.content.monsters.level_09.skirmishers import _free_to_run
from combat_engine.content.monsters.level_09.skirmishers_sa import (
    _my_own_roll,
    _reroll_any_d20,
)
from combat_engine.content.monsters.level_12.controllers import _stood_still
from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ENEMY,
    EACH_OTHER,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    MOVE,
    NO_TARGET,
    ONE_CREATURE,
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
    Ranged,
    Relation,
    Size,
    Stats,
    Target,
    UpTo,
    Usage,
    When,
    World,
    power,
)
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    ConditionApplied,
    DamageApplied,
    Dropped,
    EffectApplied,
    Event,
    Hit,
    Miss,
    Moved,
    MoveStart,
    SavingThrow,
    SkillCheck,
    SurgeSpent,
    TurnEnd,
    TurnStart,
)
from combat_engine.engine.monster_math import LIMITED
from combat_engine.engine.query import (
    alive,
    combatants,
    distance_between,
    enemies,
    has_combat_advantage,
    is_,
    team,
)
from combat_engine.engine.triggers import Trigger, about_me, both, by_me, by_melee, targets_me

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _regen_unless_radiant(c: Cast, amount: int) -> None:
    """"Regains N hit points whenever it starts its turn... when it takes
    radiant damage, its regeneration does not function on its next turn."

    One flag, set by radiant damage and cleared by the very turn it skips --
    `c.regeneration` has no hook for the exception, so this is written by
    hand the way eight files once wrote plain regeneration before that
    verb existed."""
    me = c.me
    skip = {"on": False}

    def burned(ev: DamageApplied) -> None:
        if ev.target == me and DamageType.RADIANT in ev.types():
            skip["on"] = True

    def tick(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        if skip["on"]:
            skip["on"] = False
            return
        health = c.world.get(me, Health)
        if health is not None and health.hp > 0:
            c.heal(amount, on=me)

    c.watch(DamageApplied, burned, until=When.ENCOUNTER, on=me, label=f"{c.ref} seared")
    c.watch(TurnStart, tick, until=When.ENCOUNTER, on=me, label=f"{c.ref} regen")


def _melee_or_ranged_hit(world: World, me: int, ev: Event) -> bool:
    """"It is targeted by" / "hit by a melee or ranged attack" -- read off
    the row behind the swing, the way `_shot_me_from_afar` reads a reach
    kind from the other direction."""
    if getattr(ev, "target", None) != me:
        return False
    from combat_engine.engine import get

    row = get(getattr(ev, "power", "") or "")
    return row is not None and row.reach.kind in ("melee", "ranged")


def _melee_or_close_hit(world: World, me: int, ev: Event) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    from combat_engine.engine import get

    row = get(getattr(ev, "power", "") or "")
    return row is not None and row.reach.kind in ("melee", "close_burst", "close_blast")


# ==========================================================================
# m1032
# ==========================================================================


@power(
    "m1032a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 5),
)
def m1032a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1032a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5, kind=LIMITED),
    dropped=("Defences.insubstantial", "c.lose_mode()"),
)
def m1032a1(c: Cast) -> None:
    """The attack half works. "Loses phasing, insubstantial, and the ability
    to fly until it recharges" has nothing to take away or set aside --
    `Defences` carries no insubstantial column and `c.mode` only ever raises
    a speed -- the same pair `m3437a2` and `m3440a4` already name."""
    if c.strike():
        c.hit()


def _m1032_leaving_reach(world: World, me: int, ev: MoveStart) -> bool:
    mover = ev.actor
    if mover == me or team(world, mover) is team(world, me):
        return False
    return distance_between(world, me, mover) <= 2


@power(
    "m1032a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(3),
    target=NO_TARGET,
    keywords=[Keyword.FEAR, Keyword.NECROTIC],
    trigger="an enemy moves out of its reach",
    on=Trigger(MoveStart, _m1032_leaving_reach, "an enemy moves out of its reach"),
    dropped=("Power.aura",),
)
def m1032a2(c: Cast) -> None:
    """Targets the creature that is leaving, read off the trigger rather than
    `c.targets` -- an immediate reaction's own target list is routinely
    empty. The penalty against this creature lands; extending it to "allies
    within its aura" has nowhere to go, because no row anywhere establishes
    a standing aura for this creature and the header has no field to declare
    one on."""
    foe = getattr(c.trigger, "actor", None)
    if foe is None:
        return
    if c.attack(13, REF, on=foe):
        c.damage("2d6", 5, dtype=DamageType.NECROTIC, on=foe)
        c.penalty(
            "attack", 2, on=foe, until=When.SAVE_ENDS,
            when=lambda ctx: ctx.get("target") == c.me,
        )


@power(
    "m1032a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.NECROTIC],
)
def m1032a3(c: Cast) -> None:
    """Line of sight is asked live off each ally's own attack rather than
    snapshotted, so it tracks as allies move. Ends the moment it moves --
    `once=True` with a guard, since any other creature's move would
    otherwise burn the watch for nothing."""
    me = c.me
    effects = [c.resist(15, on=me, until=When.EONT)]
    for mate in c.allies():
        if mate == me:
            continue
        effects.append(
            c.bonus(
                "damage", 0, dice="1d8", dtype=DamageType.NECROTIC, on=mate,
                until=When.EONT, when=lambda ctx, m=mate: _melee_only(ctx) and c.can_see(to=m),
            )
        )

    def ended(ev: MoveStart) -> None:
        if ev.actor != me:
            return
        for eff in effects:
            if eff is not None:
                c.world.effects.end(eff, "it moved")

    c.watch(MoveStart, ended, until=When.EONT, on=me, once=True, label=f"{c.ref} stance")


# ==========================================================================
# m1097
# ==========================================================================


@power(
    "m1097a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 4),
    dropped=("c.jump(before=)",),
)
def m1097a0(c: Cast) -> None:
    """The slam lands. The printed "standing long jump before the attack,
    without provoking" names no distance and nothing ties a jump to one
    specific attack's own timing -- `c.jump` exists but takes no such hook."""
    if c.strike():
        c.hit()


@power(
    "m1097a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 4),
)
def m1097a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1097a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1097a2(c: Cast) -> None:
    c.bonus(AC, 4, on=c.me, until=When.ENCOUNTER, when=lambda ctx: bool(ctx.get("opportunity")))


@power(
    "m1097a3",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it hits with a melee attack",
    on=Trigger(Hit, both(by_me, by_melee), "it hits with a melee attack"),
)
def m1097a3(c: Cast) -> None:
    c.shift(1)


@power(
    "m1097a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1097a4(c: Cast) -> None:
    def pay() -> None:
        c.bonus("damage", 0, dice="2d6", on=c.me, until=When.SONT, when=_melee_only)

    _moved_far(c, c.me, 4, pay)


# ==========================================================================
# m115826
# ==========================================================================


@power(
    "m115826a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 7),
)
def m115826a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        if c.charge:
            c.flat(3)
    c.shift(2)


@power(
    "m115826a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 4),
)
def m115826a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(2)


@power(
    "m115826a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    no_provoke=True,
    trigger="an enemy hits it",
    on=Trigger(Hit, targets_me, "an enemy hits it"),
)
def m115826a2(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.use_power("m115826a1", on=foe, spend=False, again=True)


# ==========================================================================
# m1172 / m1173 (the same creature's elite and standard printings)
# ==========================================================================


@power(
    "m1172a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 7),
)
def m1172a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1172a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5),
    requires=_free_to_run,
    requires_text="the m1172 must not be immobilized or slowed",
)
def m1172a1(c: Cast) -> None:
    """Two swings with a run between, the shape `m380a1` settled nine levels
    down. Declared with no target: the run can put a different creature in
    reach for the second swing."""
    for step in (0, 1):
        if step:
            c.move(c.speed_of())
        victim = _adjacent_foe(c, c.ref)
        if victim is not None and c.strike(on=victim):
            c.hit(on=victim)


@power(
    "m1172a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("3d6", 7, kind=LIMITED, half_on_miss=True),
)
def m1172a2(c: Cast) -> None:
    """"If the unconscious target takes any damage, it is no longer
    unconscious" -- a watch armed after the triggering hit, so this attack's
    own damage does not immediately wake what it just put under."""
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            c.unconscious(until=When.SAVE_ENDS, on=victim)

            def woke(ev: DamageApplied) -> None:
                if ev.target == victim:
                    c.cure(Condition.UNCONSCIOUS, on=victim)

            c.watch(DamageApplied, woke, until=When.SAVE_ENDS, on=victim, label=f"{c.ref} woken")
    else:
        c.hit(half=True)
        c.dazed(until=When.EONT)


@power(
    "m1172a3",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m1172a3(c: Cast) -> None:
    """Printed as "the m1173 shifts" -- its paired variant's own ref, almost
    certainly swapped for this creature's by the same extraction slip that
    hits `m2065a4` and `m2250a4`. Read as itself, the only creature a bare
    shift could mean here."""
    c.shift(10)


@power(
    "m1172a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m1172a4(c: Cast) -> None:
    c.cure(Condition.IMMOBILIZED, on=c.me)


_M1172_ACTED: set[int] = set()


def _m1172_track(c: Cast) -> None:
    label = f"{c.ref} acted-watch"
    if any(e.label == label for e in c.world.effects.of(c.me)):
        return

    def mark(ev: TurnStart) -> None:
        if not ev.ghost:
            _M1172_ACTED.add(ev.actor)

    c.watch(TurnStart, mark, until=When.ENCOUNTER, on=c.me, label=label)


@power(
    "m1172a5",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1172a5(c: Cast) -> None:
    _m1172_track(c)
    c.gains_advantage(
        lambda ctx: ctx.get("target") is not None and ctx.get("target") not in _M1172_ACTED,
        on=c.me, until=When.ENCOUNTER,
    )


@power(
    "m1172a6",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1172a6(c: Cast) -> None:
    c.bonus("damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m1173a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 7),
)
def m1173a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1173a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    requires=_free_to_run,
    requires_text="the m1173 must not be immobilized or slowed",
)
def m1173a1(c: Cast) -> None:
    """A basic attack at -2, twice, with a run between -- `m380a1`'s own
    shape, weapon-named rather than carrying its own attack line."""
    me = c.me
    toll = c.penalty("attack", 2, on=me, until=When.EOT)
    try:
        for step in (0, 1):
            if step:
                c.move(c.speed_of())
            victim = _adjacent_foe(c, c.ref)
            if victim is not None:
                c.basic(on=victim)
    finally:
        if toll is not None:
            c.world.effects.end(toll, "the run is over")


@power(
    "m1173a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m1173a2(c: Cast) -> None:
    c.shift(10)


@power(
    "m1173a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m1173a3(c: Cast) -> None:
    c.cure(Condition.IMMOBILIZED, on=c.me)


@power(
    "m1173a4",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it drops to 0 hit points and is killed",
    on=Trigger(Dropped, about_me, "it drops"),
    dropped=("c.grant_kind()",),
)
def m1173a4(c: Cast) -> None:
    """"Remains standing ... until the end of its next turn" -- held open by
    refusing to let the drop stick, the shape `m5183a3` settled nine levels
    down. The undead keyword it also gains has nowhere to go: no verb adds a
    kind word to a creature at runtime."""
    me = c.me

    def propped(ev: Dropped) -> None:
        if ev.actor != me:
            return
        health = c.world.get(me, Health)
        if health is not None and health.hp <= 0:
            health.hp = 1

    c.watch(Dropped, propped, until=When.EONT, on=me, label=f"{c.ref} propped")


# ==========================================================================
# m1405
# ==========================================================================


@power(
    "m1405a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 6),
)
def m1405a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m1405a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 6),
)
def m1405a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1405a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m1405a2(c: Cast) -> None:
    """Two claw attacks against the same target -- `m1405a1` run twice."""
    victim = c.target
    if victim is None:
        return
    c.use_power("m1405a1", on=victim, spend=False, again=True)
    c.use_power("m1405a1", on=victim, spend=False, again=True)


@power(
    "m1405a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
)
def m1405a3(c: Cast) -> None:
    """Flies up to 10 and bites once along the way. The exemption from
    opportunity attacks is scoped to the creature bitten, not to everyone
    passed -- armed the instant adjacency with it is gained, before the move
    continues, so that creature's own window is already vetoed."""
    me = c.me
    bitten: list[int] = []

    def closed(ev: AdjacencyGained) -> None:
        if ev.mover == me and ev.actor == me and ev.other in c.enemies() and not bitten:
            bitten.append(ev.other)
            c.no_provoke(on=me, from_=ev.other, until=When.EOT)

    watcher = c.watch(AdjacencyGained, closed, until=When.EOT, on=me, label=c.ref)
    c.shift(10)
    c.world.effects.end(watcher, "the flight is over")
    if bitten:
        # "Makes a bite attack" is the bite row, so it is run rather than
        # re-rolled here: this header carries no attack or damage line of its
        # own -- the card gives none -- and `c.strike()` raises without one.
        # `m1405a2` runs a row twice the same way.
        c.use_power("m1405a0", on=bitten[0], spend=False, again=True)


@power(
    "m1405a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d8", 6),
    trigger="an adjacent enemy does not move on its turn",
    on=Trigger(TurnEnd, when=_stood_still, text="an adjacent enemy does not move on its turn"),
)
def m1405a4(c: Cast) -> None:
    """Filed as a move action and printed as an immediate reaction, the same
    shape `m45a4` settled two levels up."""
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m1405a5",
    level=10,
    usage=DAILY,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.COLD, Keyword.IMPLEMENT],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("2d8", 6, dtype=DamageType.COLD, kind=LIMITED),
)
def m1405a5(c: Cast) -> None:
    """Hit or Miss both arm the chill; the attack roll only decides the
    up-front damage. One save-ends effect carries both the sustain hook and
    the move-punish watch, the watch's own lifetime chained to the effect's
    `on_end` rather than given an independent save, so only one throw is
    ever rolled against this."""
    victim = c.target
    if victim is None:
        return
    if c.strike():
        c.hit()
    eff = c.effect(f"{c.ref} chill", until=When.SAVE_ENDS, on=victim, sustain=ActionType.MINOR)
    if eff is None:
        return

    def moved(ev: MoveStart) -> None:
        if ev.actor == victim:
            c.flat(c.roll("1d8"), dtype=DamageType.COLD, on=victim)

    watcher = c.watch(
        MoveStart, moved, until=When.ENCOUNTER, on=victim, label=f"{c.ref} move-punish"
    )
    eff.on_end.append(lambda: c.world.effects.end(watcher, "the chill ended"))
    c.on_sustain(eff, lambda: c.flat(c.roll("2d8"), dtype=DamageType.COLD, on=victim))


@power(
    "m1405a6",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.CHARM, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("1d6", 6, dtype=DamageType.PSYCHIC),
)
def m1405a6(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            c.invisible(to=victim, on=c.me, until=When.SONT)


@power(
    "m1405a7",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.GAZE],
    attack=Attack(vs=WILL, printed=13),
)
def m1405a7(c: Cast) -> None:
    if c.strike():
        c.slide(2)


@power(
    "m1405a8",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.IMPLEMENT, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d6", 6, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m1405a8(c: Cast) -> None:
    """"Stealth checks until the end of the encounter" is a real lever --
    `skills.modifier` reads `skill:stealth` off `Mods` -- not a narrative
    flourish."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            c.invisible(to=victim, on=c.me, until=When.EONT)
            for mate in c.allies():
                if c.distance(mate) <= 10:
                    c.invisible(to=victim, on=mate, until=When.EONT)
            c.bonus("skill:stealth", 2, on=c.me, until=When.ENCOUNTER)


@power(
    "m1405a9",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("1d10", 6, dtype=DamageType.POISON, kind=LIMITED),
)
def m1405a9(c: Cast) -> None:
    """Aftereffect fires once the first hold ends by a successful save --
    chained onto that one effect's `on_end` rather than given its own
    independent timer."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            eff = c.condition(
                Condition.SLOWED, until=When.SAVE_ENDS, on=victim,
                ongoing=(5, DamageType.POISON),
            )
            if eff is not None:
                eff.on_end.append(
                    lambda: c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=victim)
                )


@power(
    "m1405a10",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POISON],
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m1405a10(c: Cast) -> None:
    from combat_engine.engine import Powers

    known = c.world.get(c.me, Powers)
    if known is not None:
        known.restore("m1405a9")
    c.use_power("m1405a9", spend=False, again=True)


@power(
    "m1405a11",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=13),
)
def m1405a11(c: Cast) -> None:
    """The aftereffect fires once the fixed stun duration itself expires --
    no save involved, so `on_end` firing on expiry is exactly the printed
    sentence rather than an approximation of it."""
    if c.strike():
        victim = c.target
        eff = c.stunned(until=When.EONT)
        if eff is not None and victim is not None:
            eff.on_end.append(lambda: c.penalty("attack", 2, until=When.SAVE_ENDS, on=victim))


@power(
    "m1405a12",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m1405a12(c: Cast) -> None:
    """"The enemy closest to it" -- nearest by board distance, ties broken
    by id so the pick is stable."""
    me = c.me
    foes = sorted(c.enemies(), key=lambda f: (c.distance(f), f))
    if not foes:
        return
    victim = foes[0]
    c.curse(on=victim, until=When.ENCOUNTER)
    c.bonus(AC, 1, kind="power", on=me, until=When.SONT)
    c.bonus(
        "damage", 0, dice="1d6", on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.cursed(on=ctx.get("target")),
    )

    def slain(ev: Dropped) -> None:
        if not c.cursed(on=ev.actor):
            return
        c.teleport(3)

    c.watch(Dropped, slain, until=When.ENCOUNTER, on=me, label=f"{c.ref} curse-slain")


@power(
    "m1405a13",
    level=10,
    usage=DAILY,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m1405a13(c: Cast) -> None:
    c.teleport(6)


# ==========================================================================
# m1796
# ==========================================================================


@power(
    "m1796a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 5),
)
def m1796a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", 0, dtype=DamageType.RADIANT)


@power(
    "m1796a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.RADIANT, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 5),
)
def m1796a1(c: Cast) -> None:
    if c.strike():
        victim = c.target
        c.hit()
        c.damage("1d6", 0, dtype=DamageType.RADIANT)
        if victim is not None:
            mate = next((a for a in c.allies() if a != c.me and c.distance(a) <= 10), None)
            if mate is not None:
                c.basic(who=mate, on=victim)


@power(
    "m1796a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.RADIANT],
    trigger="it is targeted by a melee attack",
    on=Trigger(AttackDeclared, _melee_or_ranged_hit, "it is targeted by a melee attack"),
)
def m1796a2(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None and c.attack(13, REF, on=foe):
        c.damage("2d6", 5, dtype=DamageType.RADIANT, on=foe)


@power(
    "m1796a3",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it adds 1d6 to a d20 roll it just made",
    on=(
        Trigger(AttackRolled, _my_own_roll, "it makes an attack roll"),
        Trigger(SavingThrow, _my_own_roll, "it makes a saving throw"),
        Trigger(SkillCheck, _my_own_roll, "it makes a skill check"),
    ),
    dropped=("c.boost_attack()", "c.boost_save()"),
)
def m1796a3(c: Cast) -> None:
    """Only the skill-check branch has a verb that adds to a roll already
    made -- `c.boost_check`. An attack roll or a saving throw can only be
    rerolled whole, a different printed effect, so those two branches are
    dropped rather than faked with a reroll."""
    ev = c.trigger
    if isinstance(ev, SkillCheck):
        c.boost_check(c.roll("1d6"))


# ==========================================================================
# m1996
# ==========================================================================


@power(
    "m1996a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 4),
)
def m1996a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)
        c.prone()


_M1996_GRABBED: set[int] = set()


@power(
    "m1996a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("4d8", 5, kind=LIMITED),
)
def m1996a1(c: Cast) -> None:
    """`c.overrun` walks the line and reports whose square was entered, in
    order -- the only way a trample can be written. `m1996a2` may convert
    one of these hits to a grab instead of damage; the flag it leaves is
    read here before the damage is paid."""
    for who in c.overrun():
        if c.strike(on=who):
            if who in _M1996_GRABBED:
                _M1996_GRABBED.discard(who)
            else:
                c.hit(on=who)


def _hit_with_m1996a1(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and getattr(ev, "power", "") == "m1996a1"


@power(
    "m1996a2",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it attacks a creature with m1996a1",
    on=Trigger(Hit, _hit_with_m1996a1, "it attacks a creature with m1996a1"),
)
def m1996a2(c: Cast) -> None:
    """"The attack deals no damage. Instead, the target is grabbed" --
    offered on the hit itself and read by `m1996a1` before it pays out, so
    the two never both land on the same creature. "Slides along" is the
    drag-the-grabbed-creature step `m5824a1` already settled on, rearmed
    for the rest of the fight."""
    foe = getattr(c.trigger, "target", None)
    if foe is None or not c.may(f"{c.ref}: grab instead of damage"):
        return
    c.grab(on=foe)
    _M1996_GRABBED.add(foe)
    me = c.me
    label = f"{c.ref} drag {foe}"
    if any(e.label == label for e in c.world.effects.of(me)):
        return

    def haul(ev: Moved) -> None:
        if ev.actor == me and foe in c.grabbing(of=me):
            _hauls_the_grabbed(c, foe)

    c.watch(Moved, haul, until=When.ENCOUNTER, on=me, label=label)


# ==========================================================================
# m2065
# ==========================================================================


@power(
    "m2065a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5),
)
def m2065a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2065a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5, kind=LIMITED),
)
def m2065a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)
        c.grab()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


@power(
    "m2065a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2065a2(c: Cast) -> None:
    """"A creature in its grab" -- the sentence prints this row's own ref in
    place of that phrase, read for its plain meaning rather than as a
    self-reference."""
    me = c.me
    c.bonus(
        "attack", 2, on=me, until=When.ENCOUNTER,
        when=lambda ctx: ctx.get("target") in c.grabbing(of=me),
    )
    c.bonus("reach", 2, on=me, until=When.ENCOUNTER, when=lambda ctx: bool(c.grabbing(of=me)))


@power(
    "m2065a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2065a3(c: Cast) -> None:
    """"With m2065a2 only" -- opportunity attacks out to its stretched reach,
    live-gated on whether it is currently grabbing anyone, the two keys
    `c.threatens` itself lays."""
    me = c.me
    c.bonus(
        "threatening_reach", 1, on=me, until=When.ENCOUNTER,
        when=lambda ctx: bool(c.grabbing(of=me)),
    )
    c.bonus("reach", 2, on=me, until=When.ENCOUNTER, when=lambda ctx: bool(c.grabbing(of=me)))


@power(
    "m2065a4",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 5),
)
def m2065a4(c: Cast) -> None:
    """The printed sentence names a restriction ("even if the target isn't
    taking ongoing poison damage") that `m2065a1` never imposes and names
    this creature's own ref in place of whatever word the restriction was
    about -- the same slip `m2250a4` carries the other way. Read as an
    unrestricted, always-available twin of `m2065a1`'s attack, which is the
    part of the sentence this block's own cards support."""
    if c.strike():
        c.hit()
        c.slide(2)
        c.grab()
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)


# ==========================================================================
# m2083
# ==========================================================================


@power(
    "m2083a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 5),
)
def m2083a0(c: Cast) -> None:
    if c.strike():
        c.reroll_damage(until=When.EOT)
        c.hit()


@power(
    "m2083a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 5),
)
def m2083a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2083a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 6),
)
def m2083a2(c: Cast) -> None:
    if c.strike():
        c.reroll_damage(until=When.EOT)
        c.hit()
        c.ongoing(10)


@power(
    "m2083a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    attack=Attack(vs=WILL, printed=13),
)
def m2083a3(c: Cast) -> None:
    if c.strike():
        c.slide(1)
        c.grants_advantage(until=When.EONT)


@power(
    "m2083a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2083a4(c: Cast) -> None:
    c.bonus("damage", 0, dice="2d8", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m2083a5",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2083a5(c: Cast) -> None:
    me = c.me
    c.resist_forced(1, on=me)

    def shrug(ev: ConditionApplied) -> None:
        if ev.target != me or ev.condition is not Condition.PRONE:
            return
        if c.save(on=me):
            c.cure(Condition.PRONE, on=me)

    c.watch(ConditionApplied, shrug, until=When.ENCOUNTER, on=me, label=f"{c.ref} catlike")


# ==========================================================================
# m2084
# ==========================================================================


def _under_ongoing(world: World, who: int | None) -> bool:
    return who is not None and any(e.ongoing for e in world.effects.of(who))


@power(
    "m2084a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 5),
)
def m2084a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5)


@power(
    "m2084a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=14),
    damage=Damage("2d6", 6),
    dropped=("Target.ongoing",),
)
def m2084a1(c: Cast) -> None:
    victim = _restricted_to(c, 2, lambda f: _under_ongoing(c.world, f))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        for foe in c.within(3, of=victim, side="enemy"):
            if foe == victim:
                continue
            if _secondary(c, 13, REF, foe):
                c.ongoing(5, on=foe)


@power(
    "m2084a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID],
    attack=Attack(vs=FORT, printed=13),
    damage=Damage("1d10", 5, dtype=DamageType.ACID, kind=LIMITED),
)
def m2084a2(c: Cast) -> None:
    """"Targets enemies taking ongoing damage" -- a burst of several, so the
    chooser cannot pre-filter the way `_restricted_to` does for one; a
    target that does not qualify is simply not attacked, the same as any
    other gated body."""
    if not _under_ongoing(c.world, c.target):
        return
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, until=When.SAVE_ENDS, ongoing=(5, DamageType.ACID))


@power(
    "m2084a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2084a3(c: Cast) -> None:
    c.no_provoke(
        on=c.me, until=When.ENCOUNTER,
        when=lambda ctx: _under_ongoing(c.world, ctx.get("actor")),
    )


# ==========================================================================
# m2089
# ==========================================================================


@power(
    "m2089a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 6),
)
def m2089a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2089a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 6),
)
def m2089a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2089a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m2089a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m2089a0", on=victim, spend=False, again=True)
    got0 = c.landed
    c.use_power("m2089a1", on=victim, spend=False, again=True)
    got1 = c.landed
    if got0 and got1:
        c.ongoing(5, on=victim)


@power(
    "m2089a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2089a3(c: Cast) -> None:
    def pay() -> None:
        c.bonus("damage", 0, dice="2d8", on=c.me, until=When.SONT, when=_melee_only)

    _moved_far(c, c.me, 3, pay)


@power(
    "m2089a4",
    level=10,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.PSYCHIC],
)
def m2089a4(c: Cast) -> None:
    me = c.me
    marked_by = next(
        (e.source for e in c.world.effects.of(me) if Condition.MARKED in e.conditions), None
    )
    c.cure(Condition.MARKED, on=me)
    if c.may(f"{c.ref}: move 4 instead of shift 2"):
        c.move(4)
    else:
        c.shift(2)
    if marked_by is not None:
        c.flat(5, dtype=DamageType.PSYCHIC, on=marked_by)


# ==========================================================================
# m2250
# ==========================================================================


def _taking_ongoing_poison(c: Cast, who: int) -> bool:
    for e in c.world.effects.of(who):
        if e.ongoing is None:
            continue
        if DamageType.POISON in (e.ongoing_types or (e.ongoing[1],)):
            return True
    return False


@power(
    "m2250a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 5),
)
def m2250a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.POISON)


@power(
    "m2250a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=13),
    dropped=("Target.ongoing",),
)
def m2250a1(c: Cast) -> None:
    victim = _restricted_to(c, 10, lambda f: _taking_ongoing_poison(c, f))
    if victim is None:
        return
    if c.strike(on=victim):
        c.condition(Condition.BLINDED, Condition.SLOWED, until=When.SAVE_ENDS, on=victim)


@power(
    "m2250a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2250a2(c: Cast) -> None:
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m2250a3",
    level=10,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m2250a3(c: Cast) -> None:
    c.shift(2)
    c.no_advantage(on=c.me, until=When.SONT)


@power(
    "m2250a4",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=13),
)
def m2250a4(c: Cast) -> None:
    """Crosses wires with a different stat block's text the other way round
    from `m2065a4` -- the ref it names is `m2065`, a different creature
    entirely. Read as an unrestricted twin of `m2250a1`: any creature, not
    only one already taking ongoing poison damage."""
    if c.strike():
        c.condition(Condition.BLINDED, Condition.SLOWED, until=When.SAVE_ENDS)


# ==========================================================================
# m3235
# ==========================================================================


@power(
    "m3235a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 7),
)
def m3235a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3235a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 8),
)
def m3235a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3235a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("2d8", 7, kind=LIMITED),
)
def m3235a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)
        c.dazed(until=When.EONT)


@power(
    "m3235a3",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=13),
)
def m3235a3(c: Cast) -> None:
    if c.strike():
        c.grants_advantage(until=When.EONT)


@power(
    "m3235a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is hit by a melee or ranged attack",
    on=Trigger(Hit, _melee_or_ranged_hit, "it is hit by a melee or ranged attack"),
)
def m3235a4(c: Cast) -> None:
    """The mark comes off whether or not the swing happens -- it is its own
    printed sentence.

    The trigger admits a **ranged** attack, and the card offers only a basic
    attack "at any point during this movement": two squares of shift, and
    nothing that says the shooter has to be close. So the step is aimed at
    the triggering creature and the swing is asked for afterwards, which is
    the only order in which the question "is it in reach now" has an answer.
    An archer across the map simply does not get hit back."""
    c.cure(Condition.MARKED, on=c.me)
    foe = _triggering_enemy(c)
    if foe is None:
        c.shift(2)
        return
    c.shift(2, toward=foe)
    if c.distance(foe) <= _swing_reach(c, c.me):
        c.basic(on=foe)


@power(
    "m3235a5",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3235a5(c: Cast) -> None:
    c.bonus("damage", 0, dice="3d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m3235a6",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ILLUSION],
    out_of_combat=True,
)
def m3235a6(c: Cast) -> None:
    """Disguise, pierced by an opposed check nothing on a board rolls."""


# ==========================================================================
# m3586
# ==========================================================================


@power(
    "m3586a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 2),
)
def m3586a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3586a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 5),
)
def m3586a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3586a2",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m3586a2(c: Cast) -> None:
    for _ in range(3):
        if c.basic(ranged=False):
            c.shift(1)


@power(
    "m3586a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    trigger="an adjacent enemy misses it with a melee attack",
    on=Trigger(Miss, _missed_me_in_melee, "an adjacent enemy misses it with a melee attack"),
)
def m3586a3(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None and c.adjacent(foe):
        c.basic(on=foe)


@power(
    "m3586a4",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 2, kind=LIMITED),
)
def m3586a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.heal(53)


@power(
    "m3586a5",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
)
def m3586a5(c: Cast) -> None:
    """A one-time activation, unlike every other "extra damage against a
    creature it has combat advantage against" row in this batch: spent as a
    standard action, once per encounter, to gain the rider for the rest of
    the fight -- read literally rather than folded into a trait."""
    c.bonus("damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


# ==========================================================================
# m3793
# ==========================================================================


@power(
    "m3793a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d4", 3),
)
def m3793a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.POISON))


@power(
    "m3793a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d10", 7),
)
def m3793a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3793a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3793a2(c: Cast) -> None:
    """The step between the two swings is ranked `toward=` the creature the
    second one is for -- unranked it walked out of reach and the second swing
    landed anyway. The step after the last swing has nothing pending, so it
    stays the free choice the card prints."""
    victim = c.target
    if victim is None:
        return
    combo = c.choose(["both melee", "melee and ranged"], f"{c.ref}: combo")
    second = "m3793a0" if combo == "both melee" else "m3793a1"
    c.use_power("m3793a0", on=victim, spend=False, again=True)
    c.shift(1, toward=victim)
    c.use_power(second, on=victim, spend=False, again=True)
    c.shift(1)


@power(
    "m3793a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.ILLUSION, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
)
def m3793a3(c: Cast) -> None:
    """"Deafened creatures are immune" is asked in the body rather than
    folded into the header, which has no field for it. The free basic
    attack is the *victim's own*, aimed at its nearest ally -- `who=victim`,
    since the printed line is about whom the target swings at, not whom
    this creature does.

    "Its nearest ally" is the one creature the card names, so when that ally
    is further off than the victim's own swing reaches there is no attack --
    not a swing at the second nearest, and not the free hit across ten
    squares that an explicit target used to buy."""
    victim = c.target
    if victim is None or c.is_(Condition.DEAFENED, on=victim):
        return
    if c.strike():
        c.damage("3d6", 4, dtype=DamageType.PSYCHIC)
        mates = [
            e for e in combatants(c.world)
            if e != victim and alive(c.world, e) and team(c.world, e) is team(c.world, victim)
        ]
        if mates:
            mate = min(mates, key=lambda m: (distance_between(c.world, victim, m), m))
            if distance_between(c.world, victim, mate) <= _swing_reach(c, victim):
                c.basic(who=victim, on=mate)


@power(
    "m3793a4",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.NECROTIC, Keyword.TELEPORTATION],
    attack=Attack(vs=WILL, printed=11),
)
def m3793a4(c: Cast) -> None:
    """Dazed and "cannot attack it" are two different mechanisms --
    `c.dazed` and `c.cannot_attack` -- chained so only the dazed condition's
    own saving throw is ever rolled; the barred-attack watch rides along and
    is cleaned up with it. The aftereffect pays out the same way."""
    me = c.me
    if c.strike():
        victim = c.target
        if victim is not None:
            c.pull(2, on=victim)
            eff = c.dazed(until=When.SAVE_ENDS, on=victim)
            barred = c.cannot_attack(on=victim, against=me, until=When.ENCOUNTER)
            if eff is not None and barred is not None:
                eff.on_end.append(lambda: c.world.effects.end(barred, "the grip broke"))
            if eff is not None:
                def after(victim: int = victim) -> None:
                    c.flat(c.roll("3d8") + 5, dtype=DamageType.NECROTIC, on=victim)
                    c.blinded(until=When.EONT, on=victim)

                eff.on_end.append(after)
    else:
        c.dazed(until=When.SAVE_ENDS)
    c.teleport(3)


@power(
    "m3793a5",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it makes an attack roll, a saving throw, an ability check, or a skill check",
    on=(
        Trigger(AttackRolled, _my_own_roll, "it makes an attack roll"),
        Trigger(SavingThrow, _my_own_roll, "it makes a saving throw"),
        Trigger(SkillCheck, _my_own_roll, "it makes a skill check"),
    ),
)
def m3793a5(c: Cast) -> None:
    _reroll_any_d20(c)


@power(
    "m3793a6",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger="it is hit by a melee or close attack",
    on=Trigger(Hit, _melee_or_close_hit, "it is hit by a melee or close attack"),
)
def m3793a6(c: Cast) -> None:
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    _recharge_on(c, Dropped, lambda ev: ev.actor in c.enemies())
    c.teleport(5)
    c.conceal(on=c.me, until=When.SONT)


# ==========================================================================
# m3830
# ==========================================================================


@power(
    "m3830a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 7),
)
def m3830a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3830a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 7),
)
def m3830a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3830a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 4),
)
def m3830a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None and _secondary(c, 13, FORT, victim):
            c.ongoing(10, DamageType.POISON, on=victim)


@power(
    "m3830a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3830a3(c: Cast) -> None:
    me = c.me
    bitten: list[int] = []

    def closed(ev: AdjacencyGained) -> None:
        if ev.mover == me and ev.actor == me and ev.other in c.enemies() and not bitten:
            bitten.append(ev.other)
            c.no_provoke(on=me, from_=ev.other, until=When.EOT)

    watcher = c.watch(AdjacencyGained, closed, until=When.EOT, on=me, label=c.ref)
    c.shift(8)
    c.world.effects.end(watcher, "the flight is over")
    if bitten:
        c.basic(on=bitten[0])


@power(
    "m3830a4",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3830a4(c: Cast) -> None:
    """Who is riding is read once at arming -- nothing in this engine emits
    an event for mounting, so it is a fact about how the board was set up,
    the same way master/servant relations are."""
    rider = c.rider()
    if rider is None:
        return
    stats = c.world.get(rider, Stats)
    if stats is None or stats.level < 10:
        return
    for d in ALL_DEFENCES:
        c.bonus(
            # Untyped: the card prints "+2 bonus to all defenses".
            d, 2, on=rider, until=When.ENCOUNTER,
            when=lambda ctx: c.moving_as("fly", on=c.me),
        )


@power(
    "m3830a5",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3830a5(c: Cast) -> None:
    me = c.me
    c.bonus("speed", 2, on=me, until=When.ENCOUNTER, when=lambda ctx: c.bloodied())
    for d in ALL_DEFENCES:
        c.bonus(d, 2, on=me, until=When.ENCOUNTER, when=lambda ctx: c.bloodied())


# ==========================================================================
# m3847
# ==========================================================================


@power(
    "m3847a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 5, dtype=DamageType.NECROTIC),
)
def m3847a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            c.spend_surge(on=victim)
        c.shift(3)


# ==========================================================================
# m4011
# ==========================================================================


@power(
    "m4011a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d8", 6),
)
def m4011a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4011a1",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4011a1(c: Cast) -> None:
    me = c.me
    foes = sorted((f for f in c.enemies() if c.can_see(to=f)), key=lambda f: (c.distance(f), f))
    if not foes:
        return
    c.curse(on=foes[0], until=When.ENCOUNTER)
    c.bonus(
        "damage", 0, dice="1d6", on=me, until=When.ENCOUNTER,
        when=lambda ctx: c.cursed(on=ctx.get("target")),
    )


@power(
    "m4011a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4011a2(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m4011a0", on=victim, spend=False, again=True)
    first = c.landed
    c.use_power("m4011a0", on=victim, spend=False, again=True)
    second = c.landed
    if first and second:
        c.flat(5, on=victim)


@power(
    "m4011a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("1d10", 3, dtype=DamageType.PSYCHIC),
)
def m4011a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4011a4",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m4011a4(c: Cast) -> None:
    """Disguise, pierced by an opposed check nothing on a board rolls."""


@power(
    "m4011a5",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4011a5(c: Cast) -> None:
    me = c.me

    def charged(ev: Hit | Miss) -> None:
        if getattr(ev, "attacker", None) == me and getattr(ev, "charge", False):
            c.shift(2)

    c.watch(Hit, charged, until=When.ENCOUNTER, on=me, label=f"{c.ref} after-charge-hit")
    c.watch(Miss, charged, until=When.ENCOUNTER, on=me, label=f"{c.ref} after-charge-miss")


@power(
    "m4011a6",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4011a6(c: Cast) -> None:
    me = c.me

    def slain(ev: Dropped) -> None:
        if c.cursed(on=ev.actor):
            c.teleport(5)

    c.watch(Dropped, slain, until=When.ENCOUNTER, on=me, label=f"{c.ref} curse-slain")


# ==========================================================================
# m4264
# ==========================================================================


@power(
    "m4264a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=16),
    damage=Damage("1d8", 5),
)
def m4264a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4264a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d4", 5),
)
def m4264a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4264a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d4", 5),
)
def m4264a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4264a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4264a3(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m4264a0", on=victim, spend=False, again=True)
    c.use_power("m4264a1", on=victim, spend=False, again=True)


@power(
    "m4264a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=14),
    damage=Damage("2d6", 10, kind=LIMITED),
)
def m4264a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(1)


@power(
    "m4264a5",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it hits an enemy",
    on=Trigger(Hit, by_me, "it hits an enemy"),
)
def m4264a5(c: Cast) -> None:
    foe = _triggering_enemy(c)
    if foe is not None:
        c.flat(c.roll("1d10"), on=foe)


# ==========================================================================
# m4325
# ==========================================================================

_M4325_BEAST: set[int] = set()


def _m4325_in_beast_form(world: World, eid: int) -> bool:
    return eid in _M4325_BEAST


def _m4325_in_humanoid_form(world: World, eid: int) -> bool:
    return eid not in _M4325_BEAST


@power(
    "m4325a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.DISEASE],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d4", 5),
    requires=_m4325_in_beast_form,
    requires_text="usable only while in its other form",
    narrative=("skill:endurance",),
)
def m4325a0(c: Cast) -> None:
    """"Exposed to" a filth-fever-style disease is a narrative consequence --
    nothing on a board rolls an Endurance check against an ongoing disease
    days after the fight."""
    if c.strike():
        c.hit()
        c.ongoing(3)


@power(
    "m4325a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d4", 5),
    requires=_m4325_in_humanoid_form,
    requires_text="usable only while in humanoid form",
)
def m4325a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(3)


@power(
    "m4325a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d4", 5),
    requires=_m4325_in_humanoid_form,
    requires_text="usable only while in humanoid form",
)
def m4325a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4325a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m4325a3(c: Cast) -> None:
    """`c.basic` reads `Powers.basic`, which the loader points at this
    creature's beast-form attack regardless of which form it is actually
    in -- so a plain `c.basic` call refuses here whenever the Requirement
    on that row is false. The attack matching the *current* form is named
    directly instead."""
    victim = c.target
    if victim is None:
        return
    basic_ref = "m4325a0" if c.me in _M4325_BEAST else "m4325a1"
    c.use_power(basic_ref, on=victim, spend=False, again=True)
    c.use_power(basic_ref, on=victim, spend=False, again=True)


@power(
    "m4325a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("4d4", 5, kind=LIMITED),
    requires=_m4325_in_humanoid_form,
    requires_text="usable only while in humanoid form",
)
def m4325a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, ongoing=(5, DamageType.UNTYPED))
    c.use_power("m4325a6", spend=False, again=True)


@power(
    "m4325a5",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m4325a5(c: Cast) -> None:
    """Toggles the form the Requirements above read. The card names two
    different refs for this creature's other shape in two different
    places; neither is written down here, only the toggle itself."""
    me = c.me
    if me in _M4325_BEAST:
        _M4325_BEAST.discard(me)
    else:
        _M4325_BEAST.add(me)


@power(
    "m4325a6",
    level=10,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m4325a6(c: Cast) -> None:
    c.ignores_difficult(on=c.me, until=When.EOT)
    c.shift(3)


@power(
    "m4325a7",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4325a7(c: Cast) -> None:
    """"Increases ongoing damage by 5" against a creature it has combat
    advantage against -- read as a second, larger ongoing hold laid beside
    the first. Ongoing of one type does not stack and the higher wins, so
    laying both on the same hit is exactly the printed increase and needs
    no new machinery."""
    me = c.me

    def topped_up(ev: EffectApplied) -> None:
        if ev.source != me:
            return
        victim = ev.target
        if not has_combat_advantage(c.world, me, victim):
            return
        for eff in c.world.effects.of(victim):
            if eff.source == me and eff.label == ev.label and eff.ongoing is not None:
                c.ongoing(eff.ongoing[0] + 5, eff.ongoing[1], on=victim)
                return

    c.watch(EffectApplied, topped_up, until=When.ENCOUNTER, on=me, label=f"{c.ref} venom")


# ==========================================================================
# m4471
# ==========================================================================


@power(
    "m4471a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d4", 7),
)
def m4471a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4471a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(6),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d4", 7),
)
def m4471a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4471a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m4471a2(c: Cast) -> None:
    """Two swings, each with a free step after a hit. The first step is ranked
    `toward=` the creature still to be hit -- unranked it stepped out of reach
    and the second swing landed from there anyway. Nothing is pending after
    the second, so that step keeps the free choice the card prints, which is
    why this is written out rather than looped."""
    if c.basic(on=c.target):
        c.shift(1, toward=c.target)
    if c.basic(on=c.target):
        c.shift(1)


@power(
    "m4471a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=12),
    dropped=("c.forbid(mark=)",),
)
def m4471a3(c: Cast) -> None:
    """The penalty and its timing both land. "Cannot mark it again until it
    saves" has no verb -- `c.forbid` removes one named row and nothing
    blocks the bare mark action the way it would need to."""
    me = c.me
    if c.strike():
        victim = c.target
        if victim is not None:
            c.penalty(
                "attack", 2, on=victim, until=When.SAVE_ENDS,
                when=lambda ctx: ctx.get("target") == me and c.world.turn == victim,
            )
            c.penalty(
                "attack", 4, on=victim, until=When.SAVE_ENDS,
                when=lambda ctx: ctx.get("target") == me and c.world.turn != victim,
            )
            if c.marked(on=me, by=victim):
                c.cure(Condition.MARKED, on=me)


@power(
    "m4471a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d4", 7, kind=LIMITED),
)
def m4471a4(c: Cast) -> None:
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    if c.strike():
        c.hit()
        c.slide(1)
    if c.last:
        area = c.area()
        dest = next(
            (
                sq for sq in sorted(area)
                if c.world.grid.passable(sq) and c.world.grid.occupant(sq) is None
            ),
            None,
        )
        if dest is not None:
            c.teleport(0, to=dest)


@power(
    "m4471a5",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4471a5(c: Cast) -> None:
    def pay() -> None:
        c.bonus("damage", 0, dice="1d8", on=c.me, until=When.SONT, when=_melee_only)

    _moved_far(c, c.me, 4, pay)


@power(
    "m4471a6",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m4471a6(c: Cast) -> None:
    """Disguise, pierced by an opposed check nothing on a board rolls."""


# ==========================================================================
# m4664
# ==========================================================================


@power(
    "m4664a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d6", 8, dtype=DamageType.FIRE),
)
def m4664a0(c: Cast) -> None:
    if c.strike():
        c.hit()


def _m4664_charging(world: World, eid: int) -> bool:
    from combat_engine.engine.query import moving_as

    return moving_as(world, eid, "charge")


@power(
    "m4664a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("1d6", 4, dtype=DamageType.FIRE, kind=LIMITED),
    requires=_m4664_charging,
    requires_text="the m4664 must be charging",
    charges=True,
)
def m4664a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10, DamageType.FIRE)
        c.push(2)
        c.prone()
    c.shift(2)


@power(
    "m4664a2",
    level=10,
    usage=AT_WILL,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FIRE],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("3d6", 8, dtype=DamageType.FIRE),
)
def m4664a2(c: Cast) -> None:
    """Moves 6 and attacks once along the way. The printed `+13 vs Reflex`
    and `3d6+8 fire` were missing from this header, so the strike below
    raised the moment the move brought it next to an enemy."""
    me = c.me
    met: list[int] = []

    def closed(ev: AdjacencyGained) -> None:
        if ev.mover == me and ev.actor == me and ev.other in c.enemies() and not met:
            met.append(ev.other)
            c.no_provoke(on=me, from_=ev.other, until=When.EOT)

    watcher = c.watch(AdjacencyGained, closed, until=When.EOT, on=me, label=c.ref)
    c.shift(6)
    c.world.effects.end(watcher, "the move is over")
    if met:
        foe = met[0]
        if c.strike(on=foe):
            c.hit(on=foe)
            c.prone(on=foe)


@power(
    "m4664a3",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy hits it with an attack",
    on=Trigger(Hit, targets_me, "an enemy hits it with an attack"),
)
def m4664a3(c: Cast) -> None:
    c.shift(1)


# ==========================================================================
# m5136
# ==========================================================================


@power(
    "m5136a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5136a0(c: Cast) -> None:
    """The printed exclusion names this creature's own kind by word, so it
    is left out rather than written down -- this aura catches every enemy
    within it instead of narrowing by species."""
    me = c.me

    def scorched(ev: DamageApplied) -> None:
        if ev.target != me:
            return
        amount = 8 if c.bloodied() else 4
        for foe in c.enemies():
            if c.distance(foe) <= 2:
                c.flat(amount, on=foe)

    c.watch(DamageApplied, scorched, until=When.ENCOUNTER, on=me, label=f"{c.ref} backlash")


@power(
    "m5136a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d10", 5),
)
def m5136a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5136a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5136a2(c: Cast) -> None:
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    victim = c.target
    if victim is None:
        return
    c.use_power("m5136a1", on=victim, spend=False, again=True)
    c.use_power("m5136a1", on=victim, spend=False, again=True)


def _hit_with_m5136a1(world: World, me: int, ev: Hit) -> bool:
    return ev.attacker == me and getattr(ev, "power", "") == "m5136a1"


@power(
    "m5136a3",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("1d6", 5, kind=LIMITED),
)
def m5136a3(c: Cast) -> None:
    _recharge_on(c, Hit, lambda ev: _hit_with_m5136a1(c.world, c.me, ev))
    if c.strike():
        c.hit()


_M5136_TYPES = {
    DamageType.ACID, DamageType.COLD, DamageType.FIRE, DamageType.LIGHTNING, DamageType.THUNDER,
}


def _m5136_elemental_hit(world: World, me: int, ev: DamageApplied) -> bool:
    return ev.target == me and bool(set(ev.types()) & _M5136_TYPES)


@power(
    "m5136a4",
    level=10,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it takes acid, cold, fire, lightning, or thunder damage",
    on=Trigger(
        DamageApplied, _m5136_elemental_hit,
        "it takes acid, cold, fire, lightning, or thunder damage",
    ),
)
def m5136a4(c: Cast) -> None:
    ev = c.trigger
    picked = next((t for t in ev.types() if t in _M5136_TYPES), None)
    if picked is not None:
        c.resist(10, picked, until=When.ENCOUNTER, on=c.me)


# ==========================================================================
# m5418
# ==========================================================================


@power(
    "m5418a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d6", 6),
)
def m5418a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m5418a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 9),
)
def m5418a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.pull(1)
        c.prone()


@power(
    "m5418a2",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def m5418a2(c: Cast) -> None:
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    c.shift(3)


@power(
    "m5418a3",
    level=10,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=FORT, printed=13),
    dropped=("Target.condition",),
)
def m5418a3(c: Cast) -> None:
    victim = _restricted_to(c, 1, lambda f: c.is_(Condition.PRONE, on=f))
    if victim is None:
        return
    if c.strike(on=victim):
        c.ongoing(10, on=victim)


# ==========================================================================
# m5671
# ==========================================================================


@power(
    "m5671a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5671a0(c: Cast) -> None:
    """`c.initiative` is the real verb; `c.bonus("initiative")` is read by
    nothing because `Mods` is never consulted for it (root `CLAUDE.md`'s
    AUTHORING notes already name this gap)."""
    me = c.me
    for mate in c.allies():
        if mate != me and c.distance(mate) <= 5:
            c.initiative(5, on=mate)


@power(
    "m5671a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5671a1(c: Cast) -> None:
    c.bonus("damage", 0, dice="1d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m5671a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 9),
)
def m5671a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(1)


@power(
    "m5671a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(15),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 5),
)
def m5671a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5671a4",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 8, kind=LIMITED),
)
def m5671a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(10)
        c.grants_advantage(until=When.EOTNT)


def _save_ends_near_me(world: World, me: int, ev: EffectApplied) -> bool:
    if not ev.save_ends:
        return False
    return ev.target == me or (
        team(world, ev.target) is team(world, me) and distance_between(world, me, ev.target) <= 5
    )


@power(
    "m5671a5",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it or an ally within 5 squares is subjected to an effect a save can end",
    on=Trigger(
        EffectApplied, _save_ends_near_me,
        "it or a nearby ally is subjected to a save-ends effect",
    ),
)
def m5671a5(c: Cast) -> None:
    victim = c.trigger.target
    for eff in sorted(c.world.effects.of(victim), key=lambda e: -e.id):
        if eff.when is When.SAVE_ENDS:
            c.world.effects.save(eff)
            return


# ==========================================================================
# m5792
# ==========================================================================


@power(
    "m5792a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5792a0(c: Cast) -> None:
    me = c.me

    def drained(ev: SurgeSpent) -> None:
        if team(c.world, ev.actor) is team(c.world, me) or c.distance(ev.actor) > 2:
            return
        c.slowed(until=When.EONT, on=ev.actor)

    c.watch(SurgeSpent, drained, until=When.ENCOUNTER, on=me, label=f"{c.ref} drain")


@power(
    "m5792a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.insubstantial(except_=)",),
)
def m5792a1(c: Cast) -> None:
    """`c.insubstantial` halves every damage type; the printed exception for
    force and radiant has no lever yet -- the same gap `m5791a1` and
    `m5985a6` already mark. Ends on taking radiant and is restored at the
    end of its next turn, the `m6075a1` shape moved one event later to
    match this card's own wording."""
    me = c.me
    shape: dict[str, Effect | None] = {"eff": c.insubstantial(on=me, until=When.ENCOUNTER)}

    def hurt(ev: DamageApplied) -> None:
        if ev.target != me or DamageType.RADIANT not in ev.types() or shape["eff"] is None:
            return
        c.world.effects.end(shape["eff"], "radiant burned the shape away")
        shape["eff"] = None

        def restore(ev2: TurnEnd) -> None:
            if ev2.actor == me:
                shape["eff"] = c.insubstantial(on=me, until=When.ENCOUNTER)

        c.watch(TurnEnd, restore, until=When.ENCOUNTER, on=me, once=True, label=f"{c.ref} reform")

    c.watch(DamageApplied, hurt, until=When.ENCOUNTER, on=me, label=f"{c.ref} radiant-burn")


@power(
    "m5792a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d8", 5),
)
def m5792a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5792a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d8", 5),
)
def m5792a3(c: Cast) -> None:
    if c.strike():
        victim = c.target
        c.hit()
        if victim is not None:
            steps = max(1, c.speed_of() // 2)
            for _ in range(steps):
                if not c.shift(1):
                    break
                sq = _free_square_beside(c, c.me)
                if sq is not None:
                    c.slide(99, on=victim, to=sq)


@power(
    "m5792a4",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m5792a4(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m5792a3", on=victim, spend=False, again=True)
    c.use_power("m5792a2", on=victim, spend=False, again=True)


@power(
    "m5792a5",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.PSYCHIC, Keyword.THUNDER],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("3d10", 11, dtype=DamageType.THUNDER, kind=LIMITED, half_on_miss=True),
    narrative=("skill:religion",),
)
def m5792a5(c: Cast) -> None:
    """The curse's own combat clause -- psychic damage on a whiffed attack
    -- is real and lands. Ending it is tied to a DC 18 Religion check made
    at the end of an extended rest, which never happens on a board, so
    nothing here rolls one."""
    if c.strike():
        c.hit()
        victim = c.target
        if victim is not None:
            c.curse(on=victim, until=When.ENCOUNTER)

            def whiffed(ev: Miss) -> None:
                if ev.attacker == victim:
                    c.flat(3, dtype=DamageType.PSYCHIC, on=victim)

            c.watch(Miss, whiffed, until=When.ENCOUNTER, on=c.me, label=f"{c.ref} curse-sting")
    else:
        c.hit(half=True)


@power(
    "m5792a6",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ILLUSION],
)
def m5792a6(c: Cast) -> None:
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    c.invisible(until=When.EOT)
    c.move(c.speed_of())


# ==========================================================================
# m5813
# ==========================================================================


@power(
    "m5813a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5813a0(c: Cast) -> None:
    me = c.me

    def haul(ev: Moved) -> None:
        if ev.actor != me:
            return
        for victim in c.grabbing(of=me):
            _hauls_the_grabbed(c, victim)

    c.watch(Moved, haul, until=When.ENCOUNTER, on=me, label=f"{c.ref} drags")


@power(
    "m5813a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=Target(
        side="enemy", count=1,
        label="one creature not grabbed by it",
        relation=Relation.GRABBED_BY,
        without=True,
    ),
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 9),
)
def m5813a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5813a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(4),
    target=Target(
        side="enemy", count=1,
        label="one Large or smaller creature not grabbed by it",
        max_size=Size.LARGE,
        relation=Relation.GRABBED_BY,
        without=True,
    ),
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d8", 4),
)
def m5813a2(c: Cast) -> None:
    victim = c.target
    if c.strike(on=victim):
        c.hit(on=victim)
        c.pull(3, on=victim)
        grabbed = c.grab(on=victim)
        hold = c.ongoing(5, on=victim, until=When.ENCOUNTER)
        if grabbed is not None and hold is not None:
            grabbed.on_end.append(lambda: c.world.effects.end(hold, "the grab ended"))


@power(
    "m5813a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=Target(
        side="enemy", count=1,
        label="one creature grabbed by it",
        relation=Relation.GRABBED_BY,
    ),
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 11),
)
def m5813a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.no_healing(until=When.SONT)


@power(
    "m5813a4",
    level=10,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m5813a4(c: Cast) -> None:
    victims = list(c.grabbing(of=c.me))
    c.teleport(10)
    for victim in victims:
        _hauls_the_grabbed(c, victim)


# ==========================================================================
# m5950
# ==========================================================================


@power(
    "m5950a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    dropped=("c.dim_light()",),
)
def m5950a0(c: Cast) -> None:
    """The radius is real; nothing in this engine tracks light levels, so
    there is no verb to dim bright light within it."""
    c.aura(5, label=c.ref, until=When.ENCOUNTER, on=c.me)


@power(
    "m5950a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5950a1(c: Cast) -> None:
    _regen_unless_radiant(c, 15)


@power(
    "m5950a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 9),
)
def m5950a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5950a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.FORCE, Keyword.TELEPORTATION, Keyword.WEAPON],
)
def m5950a3(c: Cast) -> None:
    """Declared `target=SELF`: the attack is `m5950a2`'s own line, aimed
    after each teleport rather than picked by this row's own header, the
    `m4186a2` shape one level down. `reach=PERSONAL` with `ONE_CREATURE`
    cannot resolve a target at all, which left this row unusable.

    The blink is aimed: "before each attack" means the square it arrives in
    has to be one it can swing from, and an unbiased `c.teleport` picked the
    lowest coordinate on the board and then swung from across it."""
    foes = c.enemies()
    victim = c.choose(foes, f"{c.ref}: who to chase") if foes else None
    if victim is None:
        return
    times = 3 if c.bloodied() else 2
    hits = 0
    for _ in range(times):
        c.teleport(5, toward=victim)
        c.use_power("m5950a2", on=victim, spend=False, again=True)
        if c.landed:
            hits += 1
    if hits >= 2:
        def worsen(eff: Effect) -> None:
            c.world.effects.end(eff, "it failed")
            c.condition(
                Condition.BLINDED, until=When.SAVE_ENDS, on=victim,
                ongoing=(10, DamageType.FORCE),
            )

        c.condition(until=When.SAVE_ENDS, on=victim, ongoing=(5, DamageType.FORCE), escalate=worsen)


@power(
    "m5950a4",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("3d10", 5, dtype=DamageType.NECROTIC, kind=LIMITED, half_on_miss=True),
)
def m5950a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.REMOVED, until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
        c.dazed(until=When.SAVE_ENDS)


@power(
    "m5950a5",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m5950a5(c: Cast) -> None:
    """"Or 10 squares if it ends the move in darkness" -- this engine tracks
    no light level, so darkness is read off scenery instead: a second hop
    if the first one lands somewhere the board calls dark."""
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    c.teleport(5)
    if c.terrain("darkness"):
        c.teleport(5)


# ==========================================================================
# m6056
# ==========================================================================


@power(
    "m6056a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6056a0(c: Cast) -> None:
    c.bonus("damage", 0, dice="2d6", on=c.me, until=When.ENCOUNTER, when=_edge_on_target(c))


@power(
    "m6056a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6056a1(c: Cast) -> None:
    c.bonus(AC, 2, on=c.me, until=When.ENCOUNTER, when=lambda ctx: bool(ctx.get("opportunity")))


@power(
    "m6056a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d4", 9),
)
def m6056a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(1)


@power(
    "m6056a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(12),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 6),
)
def m6056a3(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.shift(1)


@power(
    "m6056a4",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d8", 6, kind=LIMITED, half_on_miss=True),
)
def m6056a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.grants_advantage(until=When.EONT)
    else:
        c.hit(half=True)


@power(
    "m6056a5",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6056a5(c: Cast) -> None:
    _recharge_on(c, Bloodied, lambda ev: ev.actor == c.me)
    c.shift(c.speed_of())


@power(
    "m6056a6",
    level=10,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy hits it with an attack",
    on=Trigger(AttackRolled, _rolled_would_hit, "an enemy's attack would hit it"),
)
def m6056a6(c: Cast) -> None:
    c.reroll_attack(keep="new")


# ==========================================================================
# m6110
# ==========================================================================


@power(
    "m6110a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 7),
)
def m6110a0(c: Cast) -> None:
    if c.strike():
        c.hit()


def _m6110_not_grabbing(world: World, eid: int) -> bool:
    return not world.relations.targets(Relation.GRABBED_BY, eid)


@power(
    "m6110a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 7),
    requires=_m6110_not_grabbing,
    requires_text="the m6110 must not be grabbing a creature",
)
def m6110a1(c: Cast) -> None:
    """Flies up to 8 and swings once along the way, the `m1405a3` /
    `m3830a3` shape. Dragging the grab along afterwards reuses `m5813a0`'s
    own watch, armed once and left standing for the rest of the fight."""
    me = c.me
    met: list[int] = []

    def closed(ev: AdjacencyGained) -> None:
        if ev.mover == me and ev.actor == me and ev.other in c.enemies() and not met:
            met.append(ev.other)
            c.no_provoke(on=me, from_=ev.other, until=When.EOT)

    watcher = c.watch(AdjacencyGained, closed, until=When.EOT, on=me, label=c.ref)
    c.shift(8)
    c.world.effects.end(watcher, "the flight is over")
    if met:
        foe = met[0]
        if c.strike(on=foe):
            c.hit(on=foe)
            c.grab(on=foe)

    label = f"{c.ref} drags"
    if any(e.label == label for e in c.world.effects.of(me)):
        return

    def haul(ev: Moved) -> None:
        if ev.actor != me:
            return
        for victim in c.grabbing(of=me):
            _hauls_the_grabbed(c, victim)

    c.watch(Moved, haul, until=When.ENCOUNTER, on=me, label=label)


# ==========================================================================
# m6147
# ==========================================================================


@power(
    "m6147a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6147a0(c: Cast) -> None:
    me = c.me

    def gate(ctx: dict) -> bool:
        victim = ctx.get("target")
        if victim is None:
            return False
        near = sum(1 for a in c.allies() if a != me and c.adjacent_to(victim, a))
        return near >= 2

    c.gains_advantage(gate, on=me, until=When.ENCOUNTER)


@power(
    "m6147a1",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 7),
)
def m6147a1(c: Cast) -> None:
    victim = c.target
    prone = victim is not None and c.is_(Condition.PRONE, on=victim)
    if c.strike():
        if prone:
            c.damage("3d10", 7)
        else:
            c.damage("2d10", 7)
        if victim is not None and has_combat_advantage(c.world, c.me, victim):
            c.prone(on=victim)


# ==========================================================================
# m6406
# ==========================================================================


@power(
    "m6406a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6406a0(c: Cast) -> None:
    c.no_provoke(on=c.me, until=When.ENCOUNTER)


@power(
    "m6406a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m6406a1(c: Cast) -> None:
    """"An enemy cannot enter the m6406's space by any means" restates the
    base occupancy rule every destination square is already checked
    against. Nothing is added, the same reading `m5626a1` settled on."""
    c.note(f"{c.ref}: its space cannot be entered")


@power(
    "m6406a2",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d10", 7),
)
def m6406a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6406a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=13),
    damage=Damage("2d10", 2),
)
def m6406a3(c: Cast) -> None:
    me = c.me
    met: list[int] = []

    def closed(ev: AdjacencyGained) -> None:
        if ev.mover == me and ev.actor == me and ev.other in c.enemies() and not met:
            met.append(ev.other)

    watcher = c.watch(AdjacencyGained, closed, until=When.EOT, on=me, label=c.ref)
    c.shift(c.speed_of())
    c.world.effects.end(watcher, "the move is over")
    if met:
        foe = met[0]
        if c.strike(on=foe):
            c.hit(on=foe)


@power(
    "m6406a4",
    level=10,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("2d8", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m6406a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, Condition.IMMOBILIZED, until=When.SAVE_ENDS)


@power(
    "m6406a5",
    level=10,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def m6406a5(c: Cast) -> None:
    c.cure(Condition.SLOWED, Condition.IMMOBILIZED, on=c.me)
    c.ignores_difficult(on=c.me, until=When.EOT)
    c.shift(5)


# ==========================================================================
# m6481
# ==========================================================================


@power(
    "m6481a0",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.RADIANT],
)
def m6481a0(c: Cast) -> None:
    me = c.me

    def dawn(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost:
            return
        if c.terrain("sunlight"):
            c.flat(10, dtype=DamageType.RADIANT, on=me)

    c.watch(TurnStart, dawn, until=When.ENCOUNTER, on=me, label=f"{c.ref} sunburn")


@power(
    "m6481a1",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6481a1(c: Cast) -> None:
    _regen_unless_radiant(c, 5)


@power(
    "m6481a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6481a2(c: Cast) -> None:
    """The step is ranked `toward=` the creature just attacked. The card gives
    it no direction, and this trait fires *between* the two swings of m6481a4
    and m6481a8 -- unranked it took the second swing out of reach, which the
    explicit-target arm then hit from anyway. Ranking only: `World.decide`
    still sees every square."""
    me = c.me

    def after(ev: Hit | Miss) -> None:
        if getattr(ev, "attacker", None) == me:
            c.shift(2, toward=getattr(ev, "target", None))

    c.watch(Hit, after, until=When.ENCOUNTER, on=me, label=f"{c.ref} glide-hit")
    c.watch(Miss, after, until=When.ENCOUNTER, on=me, label=f"{c.ref} glide-miss")


@power(
    "m6481a3",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("3d4", 11),
)
def m6481a3(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6481a4",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m6481a4(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m6481a3", on=victim, spend=False, again=True)
    c.use_power("m6481a3", on=victim, spend=False, again=True)


@power(
    "m6481a5",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("4d10", 10),
    dropped=("Target.condition",),
)
def m6481a5(c: Cast) -> None:
    helpless_like = (Condition.DAZED, Condition.DOMINATED, Condition.STUNNED, Condition.UNCONSCIOUS)
    victim = _restricted_to(c, 1, lambda f: any(c.is_(cond, on=f) for cond in helpless_like))
    if victim is None:
        return
    if c.strike(on=victim):
        c.hit(on=victim)
        c.heal(20, on=c.me)


def _m6481_nobody_dominated(world: World, eid: int) -> bool:
    return not any(is_(world, foe, Condition.DOMINATED) for foe in enemies(world, eid))


@power(
    "m6481a6",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM],
    attack=Attack(vs=WILL, printed=15),
    requires=_m6481_nobody_dominated,
    requires_text="no creature must be dominated by this power",
)
def m6481a6(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


_M6481_WINGED: set[int] = set()


@power(
    "m6481a7",
    level=10,
    usage=AT_WILL,
    action=MINOR,
    once_per_round=True,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.POLYMORPH],
    dropped=("c.lose_mode()",),
)
def m6481a7(c: Cast) -> None:
    """Taking winged form grants the fly speed `c.mode` is for; reverting
    cannot take it back -- `c.mode` only ever raises a speed, the same gap
    `m3437a2` and `m3440a4` already name."""
    me = c.me
    if me in _M6481_WINGED:
        _M6481_WINGED.discard(me)
    else:
        _M6481_WINGED.add(me)
        c.mode("fly", 8, until=When.ENCOUNTER, on=me)


def _attacked_on_my_turn(world: World, me: int, ev: AttackDeclared) -> bool:
    return getattr(ev, "target", None) == me and world.turn == me


@power(
    "m6481a8",
    level=10,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy attacks it on its turn",
    on=Trigger(AttackDeclared, _attacked_on_my_turn, "an enemy attacks it on its turn"),
)
def m6481a8(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is not None:
        c.use_power("m6481a3", on=foe, spend=False, again=True)


# ==========================================================================
# m6646
# ==========================================================================


@power(
    "m6646a0",
    level=10,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=15),
    damage=Damage("2d6", 8),
)
def m6646a0(c: Cast) -> None:
    victim = c.target
    ca = victim is not None and has_combat_advantage(c.world, c.me, victim)
    if c.strike():
        if ca:
            c.damage("4d6", 6)
            if c.crit:
                c.flat(c.roll("4d6"))
        else:
            c.damage("2d6", 8)


@power(
    "m6646a1",
    level=10,
    usage=Usage.RECHARGE,
    recharge=6,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=WILL, printed=13),
)
def m6646a1(c: Cast) -> None:
    if c.strike():
        c.stunned(until=When.EOT)


@power(
    "m6646a2",
    level=10,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy misses it with a melee attack",
    on=Trigger(Miss, _missed_me_in_melee, "an enemy misses it with a melee attack"),
)
def m6646a2(c: Cast) -> None:
    c.shift(max(1, c.speed_of() // 2))
