"""Monster abilities, level 7, controllers -- second wave.

197 rows, matching `scripts/spec.py --monsters 7 --role controller`.
`controllers.py` holds the earlier sweep of this level and is untouched
here; ten of its stat blocks (`m281`, `m2813`, `m2993`, `m3007`, `m406`,
`m4815`, `m4839`, `m4841`, `m4903`, `m4997`) print no abilities left to
decorate -- they are the earlier sweep's, in full.

Conventions, inherited from `level_06/controllers_sa.py` and this level's
own `controllers.py`:

* numbers load from `game.db`; the attack line is written exactly as
  printed and the damage line goes in the header as data;
* a **trait** is a row that costs no action, has no target, and arms the
  watches that hold it, whatever action the compendium's column claims;
* a card with no printed range at all is read `Melee(1)` against AC, or
  `Ranged(10)` against a mental or elemental defence with no sibling ranged
  row to borrow the distance from -- said again at the row if the guess is
  not obvious;
* a printed range band such as "20/40" takes the shorter, normal number;
* a close burst or blast or area burst whose card names no target set
  takes **enemies**;
* one roll carrying two damage types is dealt directly with
  `c.damage(..., dtypes=(A, B))` when it is a body-level call, which is not
  the header-only limitation `Damage` itself has;
* "until the end of **its** next turn" is `When.EONT`, the engine's own
  default on every condition verb -- no override is written for it.

Three stat blocks repeat under more than one id in this campaign's
extraction. `m1108`/`m2244` and `m281`/`m1159` are each the same creature
twice; `m406a0`, `m406a1` and `m406a2` in `controllers.py` are the model for
`m1108` and `m2244`'s matching rows, and `m281a1`-`a5` there are the model
for `m1159`'s. Several of this wave's own cards call the creature by a
second id inside their own text (`m1108a2` says "the m406"; `m2781a1` says
"the m360") -- read as "it" throughout and said again in the report, the
same shape as `level_06/controllers_sa.py`'s `m1680`/`m977`. `m3221a4`'s
card names the hold its own charm row applies with what reads like a
flavour name; it is written as "it" and the fact is in the report too.
"""

from __future__ import annotations

from typing import Any

from combat_engine.content.monsters.level_02.artillery_sa import ALL_DEFENCES, _saves_off_prone
from combat_engine.content.monsters.level_02.controllers_sa import _swing_reach
from combat_engine.content.monsters.level_02.skirmishers_sa import _melee_only
from combat_engine.content.monsters.level_03.brutes_sa import _enemy_closed_on_me
from combat_engine.content.monsters.level_03.soldiers_sa import _secondary
from combat_engine.content.monsters.level_04.lurkers_sa import _twice
from combat_engine.content.monsters.level_07.controllers import _rearms_when_bloodied
from combat_engine.engine import (
    AC,
    AT_WILL,
    EACH_ALLY,
    EACH_CREATURE,
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
    AreaBurst,
    Attack,
    Cast,
    CloseBlast,
    CloseBurst,
    Condition,
    Damage,
    DamageType,
    Effect,
    Keyword,
    Melee,
    Mod,
    Ranged,
    Target,
    UpTo,
    Usage,
    Wall,
    When,
    Window,
    World,
    get,
    power,
)
from combat_engine.engine.components import Health, Movement, Powers
from combat_engine.engine.events import (
    AdjacencyGained,
    AttackDeclared,
    AttackRolled,
    Bloodied,
    DamageApplied,
    Dropped,
    Hit,
    Miss,
    Moved,
    PowerUsed,
    SurgeSpent,
    TurnEnd,
    TurnStart,
    ZoneEntered,
)
from combat_engine.engine.monster_math import LIMITED, MINION
from combat_engine.engine.query import (
    adjacent,
    allies,
    distance_between,
    enemies,
    flanked_by,
    team,
)
from combat_engine.engine.query import squares as squares_of
from combat_engine.engine.triggers import Trigger, about_me, ally_within, both, by_melee, targets_me
from combat_engine.engine.zones import Zone

# --------------------------------------------------------------------------
# Shared shapes
# --------------------------------------------------------------------------


def _no_sight_past(c: Cast, radius: int, *, until: When = When.SAVE_ENDS) -> None:
    """"No line of sight to anything more than N squares away" is a
    refusal in the interrupt window of `AttackDeclared` -- not `blinded`,
    which would also take away the near squares and hand out combat
    advantage the printed line never grants. Same shape as
    `level_07/controllers.py`'s `m406a1`."""
    victim = c.target
    if victim is None:
        return
    hold = c.effect(c.ref, until=until, on=victim)
    if hold is None:
        return

    def veto(ev: AttackDeclared) -> None:
        if hold.ended or ev.attacker != victim:
            return
        if distance_between(c.world, victim, ev.target) > radius:
            ev.cancel("it cannot see that far")

    hold.subs.append(c.world.bus.on(AttackDeclared, veto, window=Window.BEFORE, owner=c.me))


def _runs_and_swings_ally(c: Cast, victim: int) -> None:
    """"The target moves up to its speed and makes a basic attack against
    its nearest ally." `c.run_at` is the move -- it walks `victim` into
    reach the same way a charge's does -- and `c.basic` is the swing.

    **The swing is gated on arriving.** `c.run_at` returns whether it got
    there and this swung regardless, so a victim whose nearest ally was
    further than its speed attacked anyway from wherever it stopped --
    `dsl.use` applies no reach check on an explicit target (#381). Nothing
    in the printed line says the swing happens if the move does not.
    """
    mate = min(
        (a for a in allies(c.world, victim) if a != victim),
        key=lambda a: distance_between(c.world, victim, a),
        default=None,
    )
    if mate is None:
        return
    c.run_at(mate, who=victim)
    if _swing_reach(c, victim) >= distance_between(c.world, victim, mate):
        c.basic(who=victim, on=mate)


def _slid_at(c: Cast, victim: int, mate: int, squares_: int) -> None:
    """Slide the victim at the ally it is about to be made to swing at.

    `c.slide` has no `toward=` the way `c.move` and `c.shift` do -- it has
    `to=`, which walks the line one square at a time and stops at the first
    square it cannot enter. Naming the ally's own square is therefore "as
    near to it as this many squares will get you", and it stops beside the
    ally rather than in it, because `step` refuses an occupied square.

    Unaimed, the destination went to `World.decide` unordered and the lowest
    coordinate on the board won, so the slide reliably moved the victim
    *away* from the creature it was being turned against. That was invisible
    while the swing was made regardless of distance; once the swing is gated
    on reach it is the difference between the row working and the row never
    attacking at all. #381.
    """
    there = next(iter(squares_of(c.world, mate)), None)
    if there is not None:
        c.slide(squares_, on=victim, to=there)


def _nearest_mate_of(c: Cast, victim: int) -> int | None:
    """The victim's own nearest ally, which is the caster's enemy pool minus
    the victim -- `allies(world, victim)` asks the victim's side, which is
    what "an ally" on a charm means."""
    return min(
        (a for a in allies(c.world, victim) if a != victim),
        key=lambda a: (distance_between(c.world, victim, a), a),
        default=None,
    )


def _can_fly(c: Cast, who: int | None) -> bool:
    if who is None:
        return False
    mv = c.world.get(who, Movement)
    return bool(mv and mv.modes.get("fly"))


def _nobody_dominated_by(ref: str) -> Any:
    """"Recharge when no creature is dominated by this power" is a gate on
    whether the earlier hold is still standing on any of the caster's
    enemies, asked the same way `_has_a_hexed_enemy` asks about a hex in
    `level_07/controllers.py`."""

    def check(world: World, eid: int) -> bool:
        return not any(
            eff.label == ref and eff.source == eid
            for foe in enemies(world, eid)
            for eff in world.effects.of(foe)
        )

    return check


def _forbid_everything(c: Cast, victim: int, *, until: When) -> None:
    known = c.world.get(victim, Powers)
    for ref in list(known.all) if known else []:
        c.forbid(ref, on=victim, until=until)


# ==========================================================================
# m1108
# ==========================================================================


@power(
    "m1108a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d6", 4, dtype=DamageType.NECROTIC),
)
def m1108a0(c: Cast) -> None:
    """No range printed; read at the reach `a1` prints, the way
    `level_07/controllers.py`'s `m406a0` does for this same stat line."""
    if c.strike():
        c.hit()


@power(
    "m1108a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d6", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m1108a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    _no_sight_past(c, 2)


@power(
    "m1108a2",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m1108a2(c: Cast) -> None:
    c.teleport(3)
    c.insubstantial(until=When.SONT)


# ==========================================================================
# m1159
# ==========================================================================


@power(
    "m1159a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=9),
    damage=Damage("1d8", 4),
)
def m1159a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1159a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.THUNDER, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d6", 4, dtype=DamageType.THUNDER),
)
def m1159a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(3)


@power(
    "m1159a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.THUNDER, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=8),
    damage=Damage("3d6", 4, dtype=DamageType.THUNDER, kind=LIMITED),
    dropped=("Usage.RECHARGE(when=)",),
)
def m1159a2(c: Cast) -> None:
    """"3d6+4, or 3d6+9 if bloodied" is two expressions, rolled in the
    body. Recharges early when first bloodied -- `_rearms_when_bloodied`
    is what `level_07/controllers.py`'s `m281a3` already uses for the
    identical printed line on the same creature under its other id."""
    if c.first:
        _rearms_when_bloodied(c)
    bonus = 9 if c.bloodied(on=c.me) else 4
    if c.strike():
        c.damage("3d6", bonus, dtype=DamageType.THUNDER)
    else:
        c.half_damage("3d6", bonus, dtype=DamageType.THUNDER)


@power(
    "m1159a3",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m1159a3(c: Cast) -> None:
    """A disguise and nothing else."""
    c.note(f"{c.ref}: takes the shape of an old crone of any Medium humanoid race")


@power(
    "m1159a4",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m1159a4(c: Cast) -> None:
    c.teleport(10)


# ==========================================================================
# m115939
# ==========================================================================


@power(
    "m115939a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m115939a0(c: Cast) -> None:
    """A trait, whatever the compendium's action column claims. `a2`'s
    webs are the only difficult terrain tagged `"web"` this creature's own
    rows ever lay, so the two are a closed loop."""
    c.ignores_difficult("web", on=c.me, until=When.ENCOUNTER)


@power(
    "m115939a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 6),
)
def m115939a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    hobbled = victim is not None and any(
        c.is_(cond, on=victim)
        for cond in (
            Condition.IMMOBILIZED,
            Condition.RESTRAINED,
            Condition.STUNNED,
            Condition.UNCONSCIOUS,
        )
    )
    c.ongoing(10 if hobbled else 5, DamageType.POISON)


@power(
    "m115939a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_CREATURE,
    keywords=[Keyword.AREA],
    attack=Attack(vs=REF, printed=10),
)
def m115939a2(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS)
    if c.first:
        c.zone(c.area(), difficult="web", until=When.ENCOUNTER, label=c.ref)


@power(
    "m115939a3",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=10),
)
def m115939a3(c: Cast) -> None:
    if c.strike():
        c.pull(4)


# ==========================================================================
# m1497
# ==========================================================================


@power(
    "m1497a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("1d6", 5, dtype=DamageType.PSYCHIC),
)
def m1497a0(c: Cast) -> None:
    """No range printed against a mental defence, with no sibling ranged
    row on this card to borrow from; read as `Ranged(10)`, the distance
    `a1` also prints."""
    if c.strike():
        c.hit()
        c.penalty(WILL, 2, until=When.SAVE_ENDS)


@power(
    "m1497a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("2d6", 4, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m1497a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None:
        _runs_and_swings_ally(c, victim)


@power(
    "m1497a2",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
)
def m1497a2(c: Cast) -> None:
    """A trait: a humanoid this creature kills rises as a free-willed copy
    of it, at the start of its own next turn. The square is captured off
    `Dropped` immediately, before anything can tidy the corpse away; the
    clause about a ritual not pre-empting the spawn is a non-combat rider
    on a one-encounter board and is left out."""
    me = c.me
    queue: list[Any] = []

    def marked(ev: Dropped) -> None:
        if ev.source == me and c.is_kind("humanoid", on=ev.actor):
            here = next(iter(squares_of(c.world, ev.actor)), None)
            if here is not None:
                queue.append(here)

    def spawn(ev: TurnStart) -> None:
        if ev.actor != me or ev.ghost or not queue:
            return
        for here in list(queue):
            c.summon("m1497", at=here)
        queue.clear()

    c.watch(Dropped, marked, until=When.ENCOUNTER, on=me, label=c.ref)
    c.watch(TurnStart, spawn, until=When.ENCOUNTER, on=me, label=f"{c.ref} rise")


# ==========================================================================
# m1815
# ==========================================================================


@power(
    "m1815a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 3),
)
def m1815a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1815a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.RANGED],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 3),
)
def m1815a1(c: Cast) -> None:
    """A printed band, "5/10" -- the shorter, normal number."""
    if c.strike():
        c.hit()


@power(
    "m1815a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(3, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.AREA],
    attack=Attack(vs=REF, printed=12),
    damage=Damage("2d4", 5, half_on_miss=True),
)
def m1815a2(c: Cast) -> None:
    """"The m1815's allies are immune" is the target set already being
    enemies only."""
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)
        c.ongoing(5, DamageType.UNTYPED)
    else:
        c.hit(half=True)


@power(
    "m1815a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.AREA],
    attack=Attack(vs=FORT, printed=12),
    damage=Damage("2d4", 5, kind=LIMITED, half_on_miss=True),
)
def m1815a3(c: Cast) -> None:
    """"Targets on the ground only" is read off `Movement.modes`."""
    if c.first:
        c.zone(c.area(), difficult=True, until=When.ENCOUNTER, label=c.ref)
    if _can_fly(c, c.target):
        return
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)
        c.ongoing(5, DamageType.UNTYPED)
    else:
        c.hit(half=True)


@power(
    "m1815a4",
    level=7,
    usage=AT_WILL,
    once_per_round=True,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.DIVINE],
    attack=Attack(vs=FORT, printed=13),
)
def m1815a4(c: Cast) -> None:
    """"May choose one of the targets hit by its area attack" is a rider
    on each `Hit` its own area rows land, capped to once a round by the
    header field.

    The printed `+13 vs Fortitude` belongs in the header and was missing,
    so the `c.strike()` below raised whenever an area row of this
    creature's actually landed -- which the audit board never arranged."""
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker != me:
            return
        row = get(getattr(ev, "power", "") or "")
        if row is None or row.reach.kind != "area_burst":
            return
        foe = ev.target
        if foe is None or not c.strike(on=foe):
            return
        if c.may("knock the target prone instead of sliding it", who=me):
            c.prone(on=foe)
        else:
            c.slide(3, on=foe)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m1831
# ==========================================================================

_M1831_STRUCK = ("m1831a2 struck", "m1831a3 struck")


def _m1831_struck(world: World, eid: int) -> bool:
    return any(e.label in _M1831_STRUCK for e in world.effects.of(eid))


@power(
    "m1831a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 3),
)
def m1831a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1831a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=13),
    damage=Damage("2d6", 3),
)
def m1831a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m1831a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(3, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.AREA],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d4", 5, kind=LIMITED, half_on_miss=True),
)
def m1831a2(c: Cast) -> None:
    """Miss keeps the ongoing damage and only drops the blindness --
    written exactly as the two lines differ."""
    victim = c.target
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)
        c.ongoing(5, DamageType.UNTYPED)
    else:
        c.hit(half=True)
        c.ongoing(5, DamageType.UNTYPED)
    if victim is not None:
        c.effect("m1831a2 struck", until=When.EOT, on=victim)


@power(
    "m1831a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=AreaBurst(3, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.AREA, Keyword.POISON],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d4", 5, kind=LIMITED, half_on_miss=True),
)
def m1831a3(c: Cast) -> None:
    if c.first:
        c.zone(c.area(), difficult=True, until=When.ENCOUNTER, label=c.ref)
    victim = c.target
    if _can_fly(c, victim):
        return
    if c.strike():
        c.hit()
        c.immobilized(until=When.SAVE_ENDS)
        c.ongoing(5, DamageType.POISON)
    else:
        c.hit(half=True)
        c.ongoing(5, DamageType.POISON)
    if victim is not None:
        c.effect("m1831a3 struck", until=When.EOT, on=victim)


@power(
    "m1831a4",
    level=7,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    attack=Attack(vs=FORT, printed=13),
    requires=lambda world, eid: any(_m1831_struck(world, foe) for foe in enemies(world, eid)),
    requires_text="targets a creature hit by m1831a2 or m1831a3 this turn",
)
def m1831a4(c: Cast) -> None:
    victim = c.target
    if victim is None or not _m1831_struck(c.world, victim):
        victim = next((f for f in c.enemies() if _m1831_struck(c.world, f)), None)
    if victim is None or not c.strike(on=victim):
        return
    if c.may("knock the target prone instead of sliding it", who=c.me):
        c.prone(on=victim)
    else:
        c.slide(3, on=victim)


# ==========================================================================
# m2244
# ==========================================================================


@power(
    "m2244a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d6", 4, dtype=DamageType.NECROTIC),
)
def m2244a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2244a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d6", 4, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m2244a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    _no_sight_past(c, 2)


@power(
    "m2244a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC, Keyword.ZONE],
)
def m2244a2(c: Cast) -> None:
    """Shadows that follow her: an aura, not a zone, carrying the Sustain
    Minor cost -- the same shape `level_07/controllers.py`'s `m406a2`
    writes for the identical printed line. "Ends if she uses `m2244a3`" is
    a row genuinely in this file, so that half is written where `m406a2`
    had to leave it out."""
    me = c.me
    ring = c.aura(2, until=When.SUSTAIN, sustain=MINOR, label=c.ref)
    shadows = c.world.get(ring, Zone)
    if shadows is None or shadows.effect is None:
        return
    shadows.difficult = True
    hold = shadows.effect
    struck: dict[int, int] = {}

    def bite(who: int) -> None:
        if who == me or who not in c.enemies() or struck.get(who) == c.world.round:
            return
        struck[who] = c.world.round
        c.flat(5, dtype=DamageType.NECROTIC, on=who)

    def on_enter(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            bite(ev.actor)

    def on_start(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.world.zones.occupants(ring):
            bite(ev.actor)

    def concealed(ctx: dict[str, Any]) -> bool:
        who = ctx.get("target")
        if who is None or who not in c.world.zones.occupants(ring):
            return False
        return who == me or c.is_kind("shadow", on=who)

    walked = {"steps": 0}

    def stepped(ev: Moved) -> None:
        if ev.actor != me or c.world.turn != me:
            return
        walked["steps"] += 1
        if walked["steps"] > c.speed_of(me) // 2:
            c.world.effects.end(hold, "it walked out of its own shadows")

    def fresh(ev: TurnStart) -> None:
        if ev.actor == me:
            walked["steps"] = 0

    def gone(ev: PowerUsed) -> None:
        if ev.actor == me and ev.power == "m2244a3":
            c.world.effects.end(hold, "it teleported away from its own shadows")

    hold.subs.append(c.world.bus.on(ZoneEntered, on_enter, owner=me))
    hold.subs.append(c.world.bus.on(TurnStart, on_start, owner=me))
    hold.subs.append(c.world.bus.on(Moved, stepped, owner=me))
    hold.subs.append(c.world.bus.on(TurnStart, fresh, owner=me))
    hold.subs.append(c.world.bus.on(PowerUsed, gone, owner=me))
    for foe in c.enemies():
        veil = c.penalty("attack", 2, on=foe, until=When.ENCOUNTER, when=concealed)
        if veil is not None:
            hold.on_end.append(lambda v=veil: c.world.effects.end(v, "the shadows lifted"))


@power(
    "m2244a3",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m2244a3(c: Cast) -> None:
    c.teleport(3)
    c.insubstantial(until=When.SONT)


# ==========================================================================
# m2294
# ==========================================================================


def _bloodied_plus2(c: Cast) -> int:
    return 2 if c.target is not None and c.bloodied() else 0


@power(
    "m2294a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 3),
)
def m2294a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", 0, dtypes=(DamageType.FIRE, DamageType.NECROTIC))


@power(
    "m2294a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d8", 8, dtype=DamageType.NECROTIC),
)
def m2294a1(c: Cast) -> None:
    """"+13 against bloodied targets" is +2 over the printed +11."""
    if c.strike(plus=_bloodied_plus2(c)):
        c.hit()
        c.slide(2)


@power(
    "m2294a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.AREA],
    attack=Attack(vs=FORT, printed=9),
    damage=Damage("1d6", 5, dtype=DamageType.NECROTIC),
)
def m2294a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


def _m2294a3_zap(c: Cast, victim: int | None) -> None:
    if victim is None or _can_fly(c, victim) or not c.strike(on=victim):
        return
    c.hit(on=victim)
    c.immobilized(on=victim, until=When.SAVE_ENDS)


@power(
    "m2294a3",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.ZONE, Keyword.AREA],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d8", 5),
)
def m2294a3(c: Cast) -> None:
    """"Can move the zone 3 squares by spending a standard action" is this
    same row used again once the zone already stands -- the second use
    moves it instead of attacking. "Flying creatures immune" is read off
    `Movement.modes`; the repeat-attack half is a watch, so creatures
    walking in later pay the same bill the burst's own victims did."""
    me = c.me
    standing = [z for z in c.my_zones() if (b := c.world.get(z, Zone)) and b.label == c.ref]
    if standing:
        if c.first:
            c.move_zone(standing[0], 3)
        return
    if c.first:
        ring = c.zone(c.area(), until=When.EOT, label=c.ref)
        squares_ = frozenset(c.area())

        def retox(ev: TurnStart) -> None:
            if (
                not ev.ghost
                and ev.actor in c.enemies()
                and ev.actor in c.in_squares(squares_, side="any")
            ):
                _m2294a3_zap(c, ev.actor)

        def entered(ev: ZoneEntered) -> None:
            if ev.zone == ring and ev.actor in c.enemies():
                _m2294a3_zap(c, ev.actor)

        c.watch(TurnStart, retox, until=When.EOT, on=me, label=f"{c.ref} zone")
        c.watch(ZoneEntered, entered, until=When.EOT, on=me, label=f"{c.ref} zone")
    _m2294a3_zap(c, c.target)


# ==========================================================================
# m2776
# ==========================================================================


@power(
    "m2776a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 2),
)
def m2776a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2776a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d8", 0),
)
def m2776a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


@power(
    "m2776a2",
    level=7,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 2),
    trigger="a melee attack misses it",
    on=Trigger(Miss, both(targets_me, by_melee), "a melee attack misses it"),
)
def m2776a2(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not c.strike(on=foe):
        return
    c.hit(on=foe)
    for which in ALL_DEFENCES:
        c.penalty(which, 2, on=foe, until=When.EONT)


@power(
    "m2776a3",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2776a3(c: Cast) -> None:
    me = c.me

    def rider(ev: Hit) -> None:
        if ev.attacker == me and flanked_by(c.world, ev.target, me):
            c.prone(on=ev.target)

    c.watch(Hit, rider, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m2777
# ==========================================================================


@power(
    "m2777a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.MELEE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d6", 3, dtype=DamageType.FORCE),
)
def m2777a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FORCE)


@power(
    "m2777a1",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.LIGHTNING, Keyword.THUNDER, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d6", 3, dtype=DamageType.LIGHTNING),
)
def m2777a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.blinded(until=When.SAVE_ENDS, on=victim)
    for who in c.within(1, of=victim, side="any"):
        if who not in (victim, c.me):
            c.flat(3 + c.roll("1d6"), dtype=DamageType.THUNDER, on=who)


@power(
    "m2777a2",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
)
def m2777a2(c: Cast) -> None:
    """"Cannot target or be targeted by any creature" is read as
    `Condition.REMOVED` -- off the board, able neither to act nor be
    acted on, same as a `Dying` creature's own removal."""
    if c.strike():
        c.condition(Condition.REMOVED, until=When.SAVE_ENDS)


@power(
    "m2777a3",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d6", 4, dtype=DamageType.FORCE),
)
def m2777a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(5)


@power(
    "m2777a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=Ranged(5),
    target=Target(
        "enemy", 1,
        label="bloodied arcane targets only",
        bloodied=True,
    ),
    keywords=[Keyword.HEALING, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=13),
    damage=Damage("1d8", 9, dtype=DamageType.PSYCHIC, kind=LIMITED, half_on_miss=True),
    dropped=("Target.creature_kind",),
)
def m2777a4(c: Cast) -> None:
    """Bloodied is the target line now; the arcane half stays dropped, because
    `Target` has no notion of a creature's power source. "Requires chromatic
    disk" is this creature's own permanent gear and not a fight-state fact, the
    same reasoning `chargen.meets` gets for a feat's prerequisite."""
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)
    c.heal(24, on=c.me)


@power(
    "m2777a5",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d8", 4, dtype=DamageType.FIRE),
)
def m2777a5(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.immobilized(until=When.SAVE_ENDS)
    hold = c.effect(c.ref, until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return

    def burn(ev: TurnStart) -> None:
        if hold.ended or ev.actor != victim or ev.ghost:
            return
        for who in c.within(1, of=victim, side="any"):
            if who != victim:
                c.flat(4 + c.roll("1d8"), dtype=DamageType.FIRE, on=who)

    hold.subs.append(c.world.bus.on(TurnStart, burn, owner=c.me))


@power(
    "m2777a6",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("1d6", 3, dtype=DamageType.PSYCHIC),
)
def m2777a6(c: Cast) -> None:
    """Dazed is the real printed restriction and is declared plainly.
    "Attacks the nearest creature with its standard action" is layered on
    top as a forced swing each of the victim's turns -- `c.basic` does not
    spend the turn's own action, so this plays as an **extra**, compelled
    attack rather than a strict substitution for the one dazed allows.
    Said again in the report: nothing in `Cast` replaces a creature's own
    choice of standard action, only grants or forces an additional one."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.dazed(until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return

    def lash(ev: TurnStart) -> None:
        if hold.ended or ev.actor != victim or ev.ghost:
            return
        pool = [x for x in enemies(c.world, victim) + allies(c.world, victim) if x != victim]
        nearest = min(pool, key=lambda x: distance_between(c.world, victim, x), default=None)
        if nearest is None:
            return
        c.run_at(nearest, who=victim)
        c.basic(who=victim, on=nearest)

    hold.subs.append(c.world.bus.on(TurnStart, lash, owner=victim))


@power(
    "m2777a7",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.COLD, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d6", 3, dtype=DamageType.COLD),
)
def m2777a7(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(1)


def _hurt_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me


@power(
    "m2777a8",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it takes damage",
    on=Trigger(DamageApplied, targets_me, "it takes damage"),
)
def m2777a8(c: Cast) -> None:
    """"Recharge 5, or at-will while bloodied" is read as: the use always
    comes straight back while bloodied, approximated by restoring it the
    moment it fires rather than modelling two separate recharge clocks."""
    if c.bloodied(on=c.me):
        c.restore_use(c.ref, on=c.me)
    choice = c.choose(["minor action", "move action"], f"{c.ref}: which action") or "minor action"
    c.extra_action(MINOR if choice == "minor action" else MOVE, on=c.me)


@power(
    "m2777a9",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m2777a9(c: Cast) -> None:
    """A trait, whatever the compendium's column claims -- the same
    reading `level_07/controllers.py` gives every row like it. "Takes a
    turn as though you were not dazed" is `c.ignore_condition`'s own
    worked example almost word for word."""
    me = c.me

    def clear(ev: TurnStart) -> None:
        if ev.actor == me and not ev.ghost:
            c.ignore_condition(Condition.DAZED, on=me, until=When.EOT)

    c.watch(TurnStart, clear, until=When.ENCOUNTER, on=me, label=c.ref)


# ==========================================================================
# m2781
# ==========================================================================


@power(
    "m2781a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d6", 4),
)
def m2781a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m2781a1",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.WEAPON, Keyword.MELEE],
    requires=lambda world, eid: bool((h := world.get(eid, Health)) and h.bloodied),
    requires_text="usable only while bloodied",
)
def m2781a1(c: Cast) -> None:
    if c.target is not None:
        c.basic(on=c.target)
    c.heal(11, on=c.me)


@power(
    "m2781a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.ACID, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d10", 4, dtype=DamageType.ACID),
)
def m2781a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None:
        for who in c.within(1, of=victim, side="any"):
            if who not in (victim, c.me):
                c.flat(2, dtype=DamageType.ACID, on=who)


@power(
    "m2781a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ACID, Keyword.AREA],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d4", 2, dtype=DamageType.ACID),
)
def m2781a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.SAVE_ENDS)


@power(
    "m2781a4",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=NO_TARGET,
    keywords=[Keyword.ZONE, Keyword.CLOSE],
)
def m2781a4(c: Cast) -> None:
    me = c.me
    area = c.area()
    squares_ = frozenset(area)
    ring = c.zone(area, until=When.EONT, label=c.ref)

    def hex_(who: int) -> None:
        c.penalty("attack", 2, on=who, until=When.EOT)
        for which in ALL_DEFENCES:
            c.penalty(which, 2, on=who, until=When.EOT)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring:
            hex_(ev.actor)

    def started(ev: TurnStart) -> None:
        if not ev.ghost and ev.actor in c.in_squares(squares_, side="any"):
            hex_(ev.actor)

    c.watch(ZoneEntered, entered, until=When.EONT, on=me, label=f"{c.ref} zone")
    c.watch(TurnStart, started, until=When.EONT, on=me, label=f"{c.ref} zone")
    for who in c.in_squares(squares_, side="any"):
        hex_(who)


@power(
    "m2781a5",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.ACID],
)
def m2781a5(c: Cast) -> None:
    options = ["m2781a2", "m2781a3", "m2781a4"]
    for _ in range(2):
        pick = c.choose(options, f"{c.ref}: which attack") or options[0]
        c.use_power(pick)


# ==========================================================================
# m3221
# ==========================================================================


@power(
    "m3221a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 5),
)
def m3221a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3221a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 5),
)
def m3221a1(c: Cast) -> None:
    """"Requires a warhammer" is this creature's own permanent gear, the
    same reasoning `chargen.meets` gets for a prerequisite -- not asked
    mid-fight."""
    if c.strike():
        c.hit()
        c.dazed()


@power(
    "m3221a2",
    level=7,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=10),
)
def m3221a2(c: Cast) -> None:
    """"Only one target dominated at a time" -- an earlier hold of this
    row's own is found and ended before the fresh one lands."""
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    for foe in c.enemies():
        if foe == victim:
            continue
        for eff in list(c.world.effects.of(foe)):
            if eff.label == c.ref and eff.source == c.me:
                c.world.effects.end(eff, "a new target took its place")
    c.condition(Condition.DOMINATED, until=When.EONT, on=victim)


@power(
    "m3221a3",
    level=7,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=CloseBurst(5),
    target=Target(side="ally", count=1),
)
def m3221a3(c: Cast) -> None:
    if c.target is not None:
        c.slide(1, on=c.target)


def _targeted_in_melee(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and by_melee(world, me, ev)


@power(
    "m3221a4",
    level=7,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is targeted with a melee attack",
    on=Trigger(AttackDeclared, _targeted_in_melee, "it is targeted with a melee attack"),
)
def m3221a4(c: Cast) -> None:
    """"An enemy dominated by its charm power" is the hold `m3221a2`
    leaves -- the card's own name for it reads like a printed name and is
    not used here."""
    me = c.me
    pool = [a for a in c.allies() if a != me and c.adjacent(to=a)]
    dominated = [
        foe
        for foe in c.enemies()
        if any(eff.label == "m3221a2" and eff.source == me for eff in c.world.effects.of(foe))
    ]
    choices = pool + dominated
    if not choices:
        return
    pick = c.choose(choices, f"{c.ref}: redirect to") or choices[0]
    c.redirect(to=pick)


@power(
    "m3221a5",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m3221a5(c: Cast) -> None:
    c.resist_forced(1, on=c.me)
    _saves_off_prone(c)


# ==========================================================================
# m3311
# ==========================================================================


@power(
    "m3311a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d4", 2),
)
def m3311a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3311a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.TELEPORTATION, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d6", 5, dtype=DamageType.FORCE),
)
def m3311a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None:
        c.teleport(1, who=victim)


@power(
    "m3311a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.TELEPORTATION, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("3d8", 5, kind=LIMITED),
)
def m3311a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    mate = next((a for a in c.allies() if distance_between(c.world, c.me, a) <= 10), None)
    if mate is not None:
        c.swap(mate, who=victim)


@power(
    "m3311a3",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.AREA],
    attack=Attack(vs=WILL, printed=9),
)
def m3311a3(c: Cast) -> None:
    if c.strike():
        victim = c.target
        hold = c.condition(Condition.DAZED, Condition.SLOWED, until=When.SAVE_ENDS, on=victim)
        if hold is not None and victim is not None:
            hold.on_end.append(lambda v=victim: c.slowed(until=When.SAVE_ENDS, on=v))


@power(
    "m3311a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
)
def m3311a4(c: Cast) -> None:
    c.teleport(3)
    for which in ALL_DEFENCES:
        c.bonus(which, 2, on=c.me, until=When.SONT)


# ==========================================================================
# m3462
# ==========================================================================


@power(
    "m3462a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 4),
)
def m3462a0(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    mate = next((a for a in c.allies() if a != c.me), None)
    if mate is not None:
        c.bonus(
            "attack", 2, on=mate, until=When.ENCOUNTER, once=True,
            when=lambda ctx, v=victim: ctx.get("target") == v,
        )


@power(
    "m3462a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ARCANE, Keyword.IMPLEMENT, Keyword.LIGHTNING, Keyword.RANGED],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d8", 4, dtype=DamageType.LIGHTNING),
)
def m3462a1(c: Cast) -> None:
    c.ignore_cover(on=c.me)
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None:
        c.penalty("damage", 3, on=victim, until=When.ENCOUNTER, once=True)


@power(
    "m3462a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ARCANE, Keyword.FORCE, Keyword.IMPLEMENT, Keyword.ZONE, Keyword.AREA],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d10", 4, dtype=DamageType.FORCE, kind=LIMITED),
)
def m3462a2(c: Cast) -> None:
    if c.first:
        ring = c.zone(c.area(), until=When.EONT, label=c.ref)
        squares_ = frozenset(c.area())
        me = c.me

        def toll(ev: TurnEnd) -> None:
            if not ev.ghost and ev.actor != me and ev.actor in c.in_squares(squares_, side="any"):
                c.flat(4 + c.roll("1d10"), dtype=DamageType.FORCE, on=ev.actor)

        c.watch(TurnEnd, toll, until=When.EONT, on=me, label=f"{c.ref} zone")
        _ = ring
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3462a3",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.ARCANE, Keyword.HEALING, Keyword.CLOSE],
)
def m3462a3(c: Cast) -> None:
    if c.target is not None:
        # Untyped: the card prints "+1 to AC" and names no bonus type.
        c.bonus(AC, 1, on=c.target, until=When.ENCOUNTER)


@power(
    "m3462a4",
    level=7,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is missed by a melee attack",
    on=Trigger(Miss, both(targets_me, by_melee), "it is missed by a melee attack"),
)
def m3462a4(c: Cast) -> None:
    c.shift(1)


# ==========================================================================
# m3695
# ==========================================================================


@power(
    "m3695a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC, Keyword.MELEE],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("1d6", 5, dtype=DamageType.PSYCHIC),
)
def m3695a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m3695a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d6", 5, dtype=DamageType.PSYCHIC),
)
def m3695a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    _no_sight_past(c, 2, until=When.EONT)


@power(
    "m3695a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3695a2(c: Cast) -> None:
    for _ in range(2):
        c.basic(on=c.target)


@power(
    "m3695a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.SLEEP, Keyword.AREA],
    attack=Attack(vs=WILL, printed=11),
)
def m3695a3(c: Cast) -> None:
    victim = c.target

    def worsen(eff: Effect, who: Any = victim) -> None:
        c.world.effects.end(eff, "it falls unconscious")
        c.condition(Condition.UNCONSCIOUS, until=When.SAVE_ENDS, on=who)

    if c.strike():
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, escalate=worsen)


@power(
    "m3695a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=4,
    action=MOVE,
    reach=Ranged(10),
    target=UpTo(2, side="ally"),
    keywords=[Keyword.TELEPORTATION],
)
def m3695a4(c: Cast) -> None:
    if c.first:
        c.teleport(4, who=c.me)
    if c.target is not None:
        c.teleport(4, who=c.target)


# ==========================================================================
# m3764
# ==========================================================================


@power(
    "m3764a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 5),
)
def m3764a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3764a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
)
def m3764a1(c: Cast) -> None:
    """"A target of the m3764's choice" is read as an ally of the
    charmed creature -- the forced swing is the dominator pointing its
    victim's own attack at a friend, the common shape this charm takes.

    The card prints "a melee **or ranged** basic attack", so the reach is
    asked twice rather than once: the nearest ally the melee swing can touch,
    and failing that the nearest one the ranged swing can. Asked neither way,
    the first ally by entity id took a melee-1 swing from anywhere on the
    board. Nothing in range either way means no attack, and then the +4 is
    not laid -- it belongs to the swing."""
    if not c.strike():
        return
    victim = c.target
    if victim is None:
        return
    mate = _nearest_mate_of(c, victim)
    if mate is None:
        return
    _slid_at(c, victim, mate, 3)
    gap = distance_between(c.world, victim, mate)
    if gap <= _swing_reach(c, victim):
        ranged = False
    elif gap <= _swing_reach(c, victim, ranged=True):
        ranged = True
    else:
        return
    # The +4 has to be standing before the roll, and it is a one-shot -- so
    # when the swing does not happen after all it has to come back off, or
    # the victim spends it on an opportunity attack of its own later in the
    # turn. A ranged basic is refused outright for a creature with nothing to
    # shoot, which is exactly the case this branch is reached in.
    boost = c.bonus("attack", 4, on=victim, until=When.EOT, once=True, kind="power")
    if not c.basic(who=victim, on=mate, ranged=ranged) and boost is not None:
        c.world.effects.end(boost, "no attack was made")


@power(
    "m3764a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.HEALING, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d8", 4, dtype=DamageType.NECROTIC),
)
def m3764a2(c: Cast) -> None:
    """"Whenever the target spends a healing surge **or allows another
    creature to spend** a healing surge, this creature regains 10 hit
    points."

    Both halves now. `SurgeSpent.granted_by` is the second one (#386) and is
    a different question from `source`: the granter is whoever handed the
    surge over, where the source is whoever caused the spend. A leader's
    power grants; the spender spends.
    """
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    me = c.me

    def gained(ev: SurgeSpent) -> None:
        if victim in (ev.actor, ev.granted_by):
            c.heal(10, on=me)

    c.watch(SurgeSpent, gained, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m3764a3",
    level=7,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(5),
    target=NO_TARGET,
    trigger="an ally within 5 squares misses with an attack",
    on=Trigger(Miss, ally_within(5), "an ally within 5 squares misses with an attack"),
)
def m3764a3(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is None:
        return
    c.flat(5, on=foe)
    c.reroll_attack()


@power(
    "m3764a4",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.PSYCHIC, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d8", 5, dtype=DamageType.PSYCHIC),
)
def m3764a4(c: Cast) -> None:
    if c.strike():
        c.hit()
    if c.first:
        for mate in c.within(5, of=c.me, side="ally"):
            c.temp_hp(5, on=mate)
            c.bonus("attack", 2, on=mate, until=When.EONT, kind="power")


# ==========================================================================
# m3774
# ==========================================================================


@power(
    "m3774a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 4),
)
def m3774a0(c: Cast) -> None:
    """"No line of effect required for this push" is a nuance on the
    forced movement's pathing that nothing distinguishes an ordinary push
    for; the push itself lands either way."""
    if c.strike():
        c.hit()
        c.damage("1d6", 4, dtype=DamageType.NECROTIC)
        c.phasing(until=When.EOT)
        c.push(2)


@power(
    "m3774a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("1d6", 4, dtype=DamageType.PSYCHIC),
)
def m3774a1(c: Cast) -> None:
    """"An ally within range" is read as within range of the *swing*, not of
    this row: the 20 squares are what the charm carries, and the basic attack
    the victim then makes reaches one square. Filtered at 20 it was a reach-1
    swing landing wherever the ally happened to be standing.

    The ally is picked before the slide, so the slide can be aimed at it --
    see `_slid_at`. Still no swing where two squares do not close the gap."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    mate = _nearest_mate_of(c, victim)
    if mate is None:
        return
    _slid_at(c, victim, mate, 2)
    if distance_between(c.world, victim, mate) <= _swing_reach(c, victim):
        c.basic(who=victim, on=mate)


@power(
    "m3774a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
)
def m3774a2(c: Cast) -> None:
    """Three basic attacks, each aimed when it is made rather than all three
    at the creature the chooser handed over.

    The basic attack here is m3774a0, whose own rider pushes what it hits 2
    squares -- so swings two and three were being made at something no longer
    in reach, and `toward=` cannot help because it is the target that moved.
    A basic attack picks its own target, so each one takes whoever is in
    reach; if the push has cleared the squares around it, the swing is not
    made."""
    for _ in range(3):
        victim = c.target if c.adjacent(c.target) else None
        if victim is None:
            victim = next((f for f in c.enemies() if c.adjacent(f)), None)
        if victim is None:
            return
        c.basic(on=victim)


def _hit_me_adjacent(world: World, me: int, ev: Any) -> bool:
    attacker = getattr(ev, "attacker", None)
    return (
        getattr(ev, "target", None) == me
        and attacker is not None
        and adjacent(world, me, attacker)
    )


@power(
    "m3774a3",
    level=7,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    attack=Attack(vs=FORT, printed=11),
    trigger="it is hit by a creature adjacent to her",
    on=Trigger(Hit, _hit_me_adjacent, "it is hit by a creature adjacent to her"),
)
def m3774a3(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not c.strike(on=foe):
        return
    c.push(3, on=foe)
    c.slowed(until=When.SAVE_ENDS, on=foe)
    c.ongoing(10, DamageType.NECROTIC, on=foe)


@power(
    "m3774a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=9),
)
def m3774a4(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m3774a5",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.FIRE, Keyword.CLOSE],
    attack=Attack(vs=REF, printed=9),
    damage=Damage("2d6", 3, dtype=DamageType.FIRE, kind=LIMITED, half_on_miss=True),
    dropped=("Usage.RECHARGE(when=)",),
)
def m3774a5(c: Cast) -> None:
    """"Makes an at-will attack against an ally" is read as its own
    basic attack -- there is no verb to pick an arbitrary known at-will
    row, only the one `c.basic` already resolves.

    "An ally within range" is within range of that swing. The 5 squares are
    this row's blast, and filtering the ally at 5 let a reach-1 basic attack
    connect at five."""
    if c.first:
        _rearms_when_bloodied(c)
    if not c.strike():
        c.hit(half=True)
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    mate = _nearest_mate_of(c, victim)
    if mate is None:
        return
    _slid_at(c, victim, mate, 2)
    if distance_between(c.world, victim, mate) <= _swing_reach(c, victim):
        c.basic(who=victim, on=mate)


# ==========================================================================
# m3778
# ==========================================================================


@power(
    "m3778a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("", 4, dtype=DamageType.FORCE, kind=MINION),
)
def m3778a0(c: Cast) -> None:
    """No range printed against Reflex with a force keyword; read as the
    distance this creature's own family prints elsewhere, `Ranged(10)`."""
    if c.strike():
        c.hit()


@power(
    "m3778a1",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
)
def m3778a1(c: Cast) -> None:
    """"Cannot make the dominated target attack another creature" is a
    restriction on a forced-attack mechanic this row never invokes, so
    nothing else is needed to honour it."""
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.SAVE_ENDS)


@power(
    "m3778a2",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger="it is hit by an attack",
    on=Trigger(AttackRolled, targets_me, "it is hit by an attack"),
)
def m3778a2(c: Cast) -> None:
    if c.save():
        c.cancel()
        c.teleport(2)


# ==========================================================================
# m3985
# ==========================================================================


@power(
    "m3985a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("1d8", 5),
)
def m3985a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3985a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.POISON, Keyword.AREA],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d8", 4, dtype=DamageType.POISON, kind=LIMITED),
)
def m3985a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed()


@power(
    "m3985a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.ZONE, Keyword.AREA],
    attack=Attack(vs=REF, printed=11),
)
def m3985a2(c: Cast) -> None:
    if c.first:
        c.zone(c.area(), difficult=True, until=When.ENCOUNTER, label=c.ref)
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)


def _enemy_shifted(world: World, me: int, ev: Any) -> bool:
    actor = getattr(ev, "actor", None)
    return (
        actor is not None
        and getattr(ev, "kind_", "") == "shift"
        and team(world, actor) is not team(world, me)
        and distance_between(world, me, actor) <= 5
    )


@power(
    "m3985a3",
    level=7,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(5),
    target=NO_TARGET,
    attack=Attack(vs=REF, printed=11),
    trigger="an enemy shifts",
    on=Trigger(Moved, _enemy_shifted, "an enemy shifts"),
)
def m3985a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is not None and c.strike(on=foe):
        c.prone(on=foe)


# ==========================================================================
# m3987
# ==========================================================================


@power(
    "m3987a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 7, dtype=DamageType.NECROTIC),
)
def m3987a0(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None:
        c.phasing(on=victim, until=When.EOT)
        c.push(2, on=victim)


@power(
    "m3987a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=lambda world, eid: bool((h := world.get(eid, Health)) and h.bloodied),
    requires_text="usable only while bloodied",
)
def m3987a1(c: Cast) -> None:
    """Two swings of m3987a0, whose own rider pushes what it hits 2 squares --
    so the second was being made from out of reach. The card does not say both
    swings are at the same creature, so the second is re-aimed at whoever is
    in reach once the push has landed; with nobody adjacent it is not made."""
    c.use_power("m3987a0", on=c.target)
    victim = c.target if c.adjacent(c.target) else None
    if victim is None:
        victim = next((f for f in c.enemies() if c.adjacent(f)), None)
    if victim is not None:
        c.use_power("m3987a0", on=victim)


def _hit_me_from_afar(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    row = get(getattr(ev, "power", "") or "")
    return row is not None and row.reach.kind in (
        "ranged", "area_burst", "close_burst", "close_blast",
    )


@power(
    "m3987a2",
    level=7,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Ranged(10),
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d6", 6, dtype=DamageType.PSYCHIC),
    trigger="an enemy hits it with a ranged, area, or close attack",
    on=Trigger(Hit, _hit_me_from_afar, "an enemy hits it with a ranged, area, or close attack"),
)
def m3987a2(c: Cast) -> None:
    foe = getattr(c.trigger, "attacker", None)
    if foe is None or not c.strike(on=foe):
        return
    c.hit(on=foe)
    c.weakened(until=When.SAVE_ENDS, on=foe)


@power(
    "m3987a3",
    level=7,
    usage=AT_WILL,
    once_per_round=True,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d8", 4, dtype=DamageType.NECROTIC),
)
def m3987a3(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    c.slide(3, on=victim)
    c.immobilized(until=When.SAVE_ENDS, on=victim)
    for who in c.within(1, of=victim, side="any"):
        if who not in (victim, c.me) and _secondary(c, 11, REF, who):
            c.slowed(until=When.SAVE_ENDS, on=who)


@power(
    "m3987a4",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=11),
    trigger="it is first bloodied, and again when it drops to 0 hit points",
    on=(
        Trigger(Bloodied, about_me, "it is first bloodied"),
        Trigger(Dropped, about_me, "it drops to 0 hit points"),
    ),
)
def m3987a4(c: Cast) -> None:
    if c.strike():
        c.dazed()
        c.ongoing(5, DamageType.NECROTIC)


# ==========================================================================
# m3989
# ==========================================================================


@power(
    "m3989a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 4),
)
def m3989a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3989a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 5),
)
def m3989a1(c: Cast) -> None:
    """A printed band, "20/40" -- the shorter, normal number."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    if c.is_(Condition.SLOWED, on=victim):
        c.immobilized(until=When.SAVE_ENDS, on=victim)
    else:
        c.slowed(until=When.SAVE_ENDS, on=victim)


@power(
    "m3989a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("3d10", 4, half_on_miss=True),
)
def m3989a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.weakened(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m3989a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m3989a3(c: Cast) -> None:
    """The shift comes first and two swings follow it, so it is ranked
    `toward=` the creature both swings are for -- unranked it could step out
    of reach of the thing it is about to attack."""
    if c.first:
        c.shift(1, toward=c.target)
    c.basic(on=c.target)
    if c.last:
        c.basic(on=c.target)


# ==========================================================================
# m3990
# ==========================================================================


@power(
    "m3990a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 4),
)
def m3990a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m3990a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 5),
)
def m3990a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    if c.is_(Condition.SLOWED, on=victim):
        c.push(2, on=victim)
    else:
        c.slowed(until=When.SAVE_ENDS, on=victim)


@power(
    "m3990a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=Ranged(20),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=10),
    damage=Damage("3d10", 4, half_on_miss=True),
)
def m3990a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m3990a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
)
def m3990a3(c: Cast) -> None:
    """The shift comes first and two swings follow it, so it is ranked
    `toward=` the creature both swings are for -- unranked it could step out
    of reach of the thing it is about to attack."""
    if c.first:
        c.shift(1, toward=c.target)
    c.basic(on=c.target)
    if c.last:
        c.basic(on=c.target)


# ==========================================================================
# m3999
# ==========================================================================


@power(
    "m3999a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 3),
)
def m3999a0(c: Cast) -> None:
    """The printed crit (1d8+11) already equals the engine's own
    max-dice-plus-bonus, so no body code is needed for it."""
    if c.strike():
        c.hit()
        c.flat(5, dtype=DamageType.POISON)


@power(
    "m3999a1",
    level=7,
    once_per_round=True,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.POISON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 5, dtype=DamageType.FIRE),
)
def m3999a1(c: Cast) -> None:
    """One roll of two types via `c.hit()`; fire stays in the header,
    poison rides as a keyword, the same judgment call this level's
    `controllers.py` makes for `m406a0`."""
    if c.strike():
        c.hit()


@power(
    "m3999a2",
    level=7,
    once_per_round=True,
    usage=AT_WILL,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
    no_provoke=True,
)
def m3999a2(c: Cast) -> None:
    if c.strike():
        c.condition(Condition.DOMINATED, until=When.EONT)


def _crit_against_me(world: World, me: int, ev: Any) -> bool:
    if getattr(ev, "target", None) != me:
        return False
    result = getattr(ev, "result", None)
    return bool(result and result.critical)


@power(
    "m3999a3",
    level=7,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    attack=Attack(vs=WILL, printed=11),
    trigger="a critical hit is scored against it",
    on=Trigger(Hit, _crit_against_me, "a critical hit is scored against it"),
)
def m3999a3(c: Cast) -> None:
    if c.strike():
        c.dazed()
    c.push(3)
    c.prone()


@power(
    "m3999a4",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_ENEMY,
    keywords=[Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d6", 5),
)
def m3999a4(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.effect(c.ref, until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return
    me = c.me

    def tax(ev: AttackDeclared) -> None:
        if not hold.ended and ev.attacker == victim:
            c.flat(5, dtype=DamageType.POISON, on=victim)
            c.flat(5, dtype=DamageType.FIRE, on=victim)

    hold.subs.append(c.world.bus.on(AttackDeclared, tax, owner=me))


# ==========================================================================
# m4173
# ==========================================================================


@power(
    "m4173a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 4),
)
def m4173a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d8", 0, dtype=DamageType.FORCE)
        c.slide(1)


@power(
    "m4173a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=UpTo(2),
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 4),
)
def m4173a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4173a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4173a2(c: Cast) -> None:
    _twice(c, "m4173a1")


@power(
    "m4173a3",
    level=7,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("1d8", 4),
    trigger="an enemy moves into an adjacent square",
    on=Trigger(AdjacencyGained, _enemy_closed_on_me, "an enemy moves into an adjacent square"),
)
def m4173a3(c: Cast) -> None:
    foe = getattr(c.trigger, "actor", None)
    if foe is None or not c.strike(on=foe):
        return
    c.hit(on=foe)
    c.prone(on=foe)
    c.shift(1)
    c.move(3, at="fly")


@power(
    "m4173a4",
    level=7,
    once_per_round=True,
    usage=AT_WILL,
    action=MINOR,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.MELEE],
    attack=Attack(vs=WILL, printed=9),
)
def m4173a4(c: Cast) -> None:
    if not c.strike():
        c.shift(1)
        return
    victim = c.target
    c.slide(1, on=victim)
    c.grants_advantage(on=victim, until=When.EONT)
    c.shift(1)


@power(
    "m4173a5",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.FORCE, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("2d10", 4, dtype=DamageType.FORCE, kind=LIMITED, half_on_miss=True),
)
def m4173a5(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.SAVE_ENDS)
    else:
        c.hit(half=True)


@power(
    "m4173a6",
    level=7,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="it is first bloodied",
    on=Trigger(Bloodied, about_me, "it is first bloodied"),
)
def m4173a6(c: Cast) -> None:
    c.restore_use("m4173a5", on=c.me)
    c.use_power("m4173a5")


@power(
    "m4173a7",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=11),
)
def m4173a7(c: Cast) -> None:
    victim = c.target
    hold = c.stunned(until=When.EONT) if c.strike() else None
    if hold is not None and victim is not None:
        hold.on_end.append(lambda v=victim: c.penalty("attack", 2, until=When.SAVE_ENDS, on=v))


@power(
    "m4173a8",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m4173a8(c: Cast) -> None:
    """A disguise and nothing else."""
    c.note(f"{c.ref}: alters its form to appear as a unique humanoid")


# ==========================================================================
# m4183
# ==========================================================================


@power(
    "m4183a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 5),
)
def m4183a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.damage("1d6", 0, dtype=DamageType.FIRE)


@power(
    "m4183a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=UpTo(2),
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d10", 4),
)
def m4183a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m4183a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m4183a2(c: Cast) -> None:
    _twice(c, "m4183a1")


@power(
    "m4183a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBlast(4),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE, Keyword.CLOSE],
    attack=Attack(vs=REF, printed=11),
    damage=Damage("2d6", 5, dtype=DamageType.FIRE, kind=LIMITED),
    dropped=("Usage.RECHARGE(when=)",),
)
def m4183a3(c: Cast) -> None:
    if c.first:
        _rearms_when_bloodied(c)
    if c.strike():
        c.hit()
        c.weakened(until=When.EONT)


# ==========================================================================
# m4400
# ==========================================================================


def _m4400_choice(c: Cast) -> None:
    """The three sub-effects print no refs of their own, so they live
    inside the row that names them, the way `level_05/artillery_sa.py`'s
    `_two_rays` holds four unreffed rays."""
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    pick = c.choose(["acid", "cold", "fire"], f"{c.ref}: which element") or "acid"
    if pick == "acid":
        c.damage("2d4", 4, dtype=DamageType.ACID)
        for which in (AC, FORT):
            c.penalty(which, 2, on=victim, until=When.EONT)
    elif pick == "cold":
        c.damage("2d4", 4, dtype=DamageType.COLD)
        c.immobilized(on=victim, until=When.EONT)
    else:
        c.damage("1d4", 4, dtype=DamageType.FIRE)
        c.ongoing(5, DamageType.FIRE, on=victim)


@power(
    "m4400a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON],
    attack=Attack(vs=AC, printed=12),
)
def m4400a0(c: Cast) -> None:
    _m4400_choice(c)


@power(
    "m4400a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=12),
)
def m4400a1(c: Cast) -> None:
    """"The dagger returns to his hand" is flavour with nothing to track:
    nothing here consumes ammunition."""
    _m4400_choice(c)


@power(
    "m4400a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    requires=lambda world, eid: world.get(eid, Health) is not None,
)
def m4400a2(c: Cast) -> None:
    """Two basic attacks. The printed two-weapon Requirement is not a gate.

    `c.wielding` is a real check and a monster has nothing for it to read:
    `content/loader.py:156` spawns every stat block with a bare `Gear()`, so the
    weapons list is empty and the test is **false in every fight** -- not just on
    a bare audit board. Gating on it made the whole row dead. #366, and
    `level_03/soldiers_sa.py`'s `m1130a1` settled the same shape for a printed
    bastard-sword Requirement.
    """
    for _ in range(2):
        c.basic(on=c.target)


def _second_enemy_adjacent(world: World, me: int, ev: Any) -> bool:
    foe = getattr(ev, "actor", None)
    if foe is None or team(world, foe) is team(world, me):
        return False
    return len([f for f in enemies(world, me) if adjacent(world, me, f)]) >= 2


@power(
    "m4400a3",
    level=7,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=CloseBurst(1),
    target=EACH_ENEMY,
    keywords=[Keyword.FORCE, Keyword.CLOSE],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d4", 4, dtype=DamageType.FORCE),
    trigger="a second enemy moves adjacent to it",
    on=Trigger(AdjacencyGained, _second_enemy_adjacent, "a second enemy moves adjacent to it"),
)
def m4400a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.push(2)
        c.slowed(until=When.EONT)


@power(
    "m4400a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.AREA],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d8", 5),
)
def m4400a4(c: Cast) -> None:
    """"If the target is vulnerable to any damage type, it is also
    vulnerable to the initial damage" is read by dealing that initial
    blow as the type the target is already vulnerable to, rather than
    untyped -- the vulnerability then applies on its own terms."""
    victim = c.target
    if victim is None:
        return
    vulnerable_to = next(
        (dt for dt, amount in c.resistances(on=victim).items() if amount < 0), None
    )
    if c.strike():
        c.damage("2d8", 5, dtype=vulnerable_to or DamageType.UNTYPED)
        hold = c.world.effects.apply(
            victim, c.me, When.SAVE_ENDS, label=c.ref,
            conditions=(Condition.SLOWED,), ongoing=(5, DamageType.UNTYPED),
            mods=[(victim, Mod(what=AC, value=-2, kind="untyped", label=c.ref))],
        )
        _ = hold


@power(
    "m4400a5",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    keywords=[Keyword.CLOSE],
)
def m4400a5(c: Cast) -> None:
    if c.target is not None:
        c.shift(1, who=c.target)
        c.temp_hp(10, on=c.target)


# ==========================================================================
# m5362
# ==========================================================================


@power(
    "m5362a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("4d4", 4, dtype=DamageType.PSYCHIC),
)
def m5362a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slowed(until=When.EONT)


@power(
    "m5362a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=11),
    damage=Damage("2d8", 6, dtype=DamageType.PSYCHIC),
)
def m5362a1(c: Cast) -> None:
    """"Cannot see creatures that are not adjacent to it" is read as the
    same restriction `_no_sight_past` already states for a radius of 1."""
    if not c.strike():
        return
    c.hit()
    c.slide(3)
    _no_sight_past(c, 1, until=When.EONT)


@power(
    "m5362a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=AreaBurst(2, 20),
    target=EACH_ENEMY,
    keywords=[Keyword.ILLUSION, Keyword.PSYCHIC, Keyword.AREA],
    attack=Attack(vs=WILL, printed=9),
    damage=Damage("3d8", 5, dtype=DamageType.PSYCHIC, kind=LIMITED),
)
def m5362a2(c: Cast) -> None:
    """"Confused" names no condition this engine has; the redirect is
    written directly against the hold's own `AttackDeclared` window,
    the same low-level technique `level_07/controllers.py`'s `m2993a3`
    and `m406a1` already use to move or veto an attack in flight."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    hold = c.effect(c.ref, until=When.SAVE_ENDS, on=victim)
    if hold is None:
        return

    def maybe_redirect(ev: AttackDeclared) -> None:
        if hold.ended or ev.attacker != victim:
            return
        row = get(getattr(ev, "power", "") or "")
        if row is None or row.reach.kind not in ("melee", "ranged"):
            return
        mate = next(
            (
                a
                for a in allies(c.world, victim)
                if a != victim and distance_between(c.world, victim, a) <= row.reach.size
            ),
            None,
        )
        if mate is None or c.roll("1d20") < 10:
            return
        ev.target = mate

    hold.subs.append(
        c.world.bus.on(AttackDeclared, maybe_redirect, window=Window.BEFORE, owner=c.me)
    )


@power(
    "m5362a3",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5362a3(c: Cast) -> None:
    c.teleport(5)


# ==========================================================================
# m5461
# ==========================================================================


_M5461_HEXED = "m5461a4 hexed"


def _hexed_by_m5461(world: World, eid: int, by: int) -> bool:
    return any(
        e.label == _M5461_HEXED and e.source == by and not e.ended
        for e in world.effects.of(eid)
    )


def _has_a_hexed_enemy_m5461(world: World, eid: int) -> bool:
    return any(_hexed_by_m5461(world, foe, eid) for foe in enemies(world, eid))


@power(
    "m5461a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 6),
)
def m5461a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5461a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(2, 5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.IMPLEMENT, Keyword.AREA],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("2d10", 6),
)
def m5461a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(3)
    elif c.may("slide the target 1 square", who=c.me):
        c.slide(1)


@power(
    "m5461a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=4,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.POLYMORPH, Keyword.RANGED],
    attack=Attack(vs=FORT, printed=10),
    requires=_has_a_hexed_enemy_m5461,
    requires_text="targets a hexed enemy",
)
def m5461a2(c: Cast) -> None:
    victim = c.target
    if victim is None or not _hexed_by_m5461(c.world, victim, c.me):
        return
    if not c.strike(on=victim):
        return
    c.form(until=When.EONT, label=c.ref)
    _forbid_everything(c, victim, until=When.EONT)


@power(
    "m5461a3",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=CloseBurst(5),
    target=Target(side="enemy", count=1),
    keywords=[Keyword.TELEPORTATION],
    requires=_has_a_hexed_enemy_m5461,
    requires_text="one hexed creature in the burst",
)
def m5461a3(c: Cast) -> None:
    victim = c.target
    if victim is not None and _hexed_by_m5461(c.world, victim, c.me):
        c.swap(victim)


@power(
    "m5461a4",
    level=7,
    once_per_round=True,
    usage=AT_WILL,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ENEMY,
    keywords=[Keyword.CHARM, Keyword.IMPLEMENT, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=10),
)
def m5461a4(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    me = c.me

    def against_me(ctx: dict[str, Any]) -> bool:
        return ctx.get("target") == me

    c.world.effects.apply(
        victim, me, When.EONT, label=_M5461_HEXED,
        conditions=(Condition.SLOWED,),
        mods=[
            (victim, Mod(what=what, value=-2, kind="untyped", when=against_me, label=_M5461_HEXED))
            for what in ("attack", "damage")
        ],
    )


# ==========================================================================
# m5531
# ==========================================================================


@power(
    "m5531a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d6", 5, dtype=DamageType.PSYCHIC),
)
def m5531a0(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.slide(1)


@power(
    "m5531a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d6", 5, dtype=DamageType.PSYCHIC),
)
def m5531a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    c.push(2)


@power(
    "m5531a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_ENEMY,
    keywords=[Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("2d8", 6, kind=LIMITED),
    dropped=("c.reroll_attack(on=)",),
)
def m5531a2(c: Cast) -> None:
    """"The next ally that hits and damages the target can reroll one
    attack before the end of the ally's next turn" needs a reroll token
    aimed at a creature other than whoever is resolving the current
    attack; `c.reroll_attack` takes no `on=` to hand one to. The prone and
    the earlier damage both land."""
    if c.strike():
        c.hit()
        c.prone()


# ==========================================================================
# m5552
# ==========================================================================


@power(
    "m5552a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 6),
)
def m5552a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()


@power(
    "m5552a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.FIRE, Keyword.IMPLEMENT, Keyword.AREA],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d10", 5, half_on_miss=True),
)
def m5552a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.FIRE)
        c.slide(1)
    else:
        c.hit(half=True)


# ==========================================================================
# m5580
# ==========================================================================


@power(
    "m5580a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.FEAR],
)
def m5580a0(c: Cast) -> None:
    """"Creatures in the aura gain a bonus when targeting an ally" is read
    as the eerie-echo flavour this family of minions carries elsewhere on
    the card: the bonus applies to striking one's own side, not the
    other's."""
    me = c.me
    for who in c.enemies() + c.allies():
        c.bonus(
            "attack", 2, on=who, until=When.ENCOUNTER,
            when=lambda ctx, w=who: (
                distance_between(c.world, me, w) <= 2
                and ctx.get("target") is not None
                and team(c.world, ctx["target"]) is team(c.world, w)
            ),
        )


@power(
    "m5580a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.PSYCHIC, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=11),
    damage=Damage("", 8, dtype=DamageType.PSYCHIC, kind=MINION),
)
def m5580a1(c: Cast) -> None:
    if not c.strike():
        return
    victim = c.target
    if victim is not None and c.may(
        "make an attack against its nearest ally instead of taking damage", who=victim
    ):
        mate = min(
            (a for a in allies(c.world, victim) if a != victim),
            key=lambda a: distance_between(c.world, victim, a),
            default=None,
        )
        if mate is not None:
            c.basic(who=victim, on=mate)
            return
    c.hit()


# ==========================================================================
# m5595
# ==========================================================================


@power(
    "m5595a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d6", 7),
)
def m5595a0(c: Cast) -> None:
    """"Each Failed Saving Throw" is `Effect.escalate` -- set directly on
    the hold `c.ongoing` hands back, since that call takes no `escalate=`
    of its own."""
    if not c.strike():
        return
    c.hit()
    victim = c.target
    hold = c.ongoing(5, DamageType.POISON, on=victim, until=When.SAVE_ENDS)
    if hold is not None:
        hold.escalate = lambda eff, v=victim: c.slide(3, on=v)


@power(
    "m5595a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=CloseBlast(3),
    target=EACH_OTHER,
    keywords=[Keyword.POISON, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=10),
)
def m5595a1(c: Cast) -> None:
    victim = c.target
    if not c.strike():
        return

    def slide_on_fail(eff: Effect, who: Any = victim) -> None:
        c.slide(3, on=who)

    c.condition(
        until=When.SAVE_ENDS, on=victim, ongoing=(10, DamageType.POISON), escalate=slide_on_fail
    )


@power(
    "m5595a2",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.TELEPORTATION],
    trigger="an enemy hits it with a melee attack",
    on=Trigger(Hit, both(targets_me, by_melee), "an enemy hits it with a melee attack"),
)
def m5595a2(c: Cast) -> None:
    c.teleport(3)


# ==========================================================================
# m5729
# ==========================================================================


@power(
    "m5729a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 4),
)
def m5729a0(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.shift(1)


@power(
    "m5729a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.WEAPON, Keyword.RANGED],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d6", 6),
)
def m5729a1(c: Cast) -> None:
    """Staged poison, each failed save worsening the last -- the first
    stage is a bare hold with no condition of its own, which `c.condition`
    allows by taking zero conditions."""
    victim = c.target

    def falls_unconscious(eff: Effect, who: Any = victim) -> None:
        c.world.effects.end(eff, "it falls unconscious")
        c.condition(Condition.UNCONSCIOUS, until=When.SAVE_ENDS, on=who)

    def worsens(eff: Effect, who: Any = victim) -> None:
        c.world.effects.end(eff, "it worsens")
        c.condition(
            Condition.SLOWED, until=When.SAVE_ENDS, on=who,
            ongoing=(5, DamageType.POISON), escalate=falls_unconscious,
        )

    if c.strike():
        c.hit()
        c.condition(
            until=When.SAVE_ENDS, on=victim, ongoing=(5, DamageType.POISON), escalate=worsens
        )


@power(
    "m5729a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=AreaBurst(1, 5),
    target=EACH_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.AREA],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d6", 4),
)
def m5729a2(c: Cast) -> None:
    victim = c.target

    def worsens(eff: Effect, who: Any = victim) -> None:
        c.world.effects.end(eff, "it becomes restrained")
        c.condition(Condition.RESTRAINED, until=When.SAVE_ENDS, on=who)

    if c.strike():
        c.hit()
        c.condition(Condition.IMMOBILIZED, until=When.SAVE_ENDS, on=victim, escalate=worsens)


@power(
    "m5729a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    dropped=("Usage.RECHARGE(when=)",),
)
def m5729a3(c: Cast) -> None:
    if c.first:
        _rearms_when_bloodied(c)
    c.shift(1)
    c.move(5, at="fly")


# ==========================================================================
# m5784
# ==========================================================================


def _m5784_form(world: World, eid: int) -> str:
    for eff in world.effects.of(eid):
        if eff.label.startswith("m5784a5 "):
            return eff.label.split(" ", 1)[1]
    return "humanoid form"


@power(
    "m5784a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5784a0(c: Cast) -> None:
    """"Whenever it shifts" is a narrower gate than `c.ignores_difficult`
    offers; granting it always is a strict superset and never wrong."""
    c.ignores_difficult(on=c.me, until=When.ENCOUNTER)


@power(
    "m5784a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d8", 6),
    requires=lambda world, eid: _m5784_form(world, eid) == "beast form",
    requires_text="usable only in beast form",
)
def m5784a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.slide(2)


@power(
    "m5784a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 6),
    requires=lambda world, eid: _m5784_form(world, eid) == "humanoid form",
    requires_text="usable only in humanoid form",
)
def m5784a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5784a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    attack=Attack(vs=REF, printed=10),
)
def m5784a3(c: Cast) -> None:
    if c.strike():
        c.immobilized(until=When.SAVE_ENDS)


@power(
    "m5784a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=Wall(8, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.ZONE],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("1d10", 5),
    requires=lambda world, eid: _m5784_form(world, eid) == "humanoid form",
    requires_text="usable only in humanoid form",
    dropped=("Usage.RECHARGE(when=)",),
)
def m5784a4(c: Cast) -> None:
    """"Difficult terrain for creatures without forest walk" and "5
    damage to those without it" are both read as applying to enemies --
    this creature's own side, being the sort that movement mode belongs to in
    the first place, is spared. The terrain cost itself is uniform
    (`Zones.difficult_squares` reads every zone the same way); the damage
    tick is the half written to spare an ally."""
    if c.first:
        _rearms_when_bloodied(c)
        ring = c.zone(c.area(), difficult=True, until=When.ENCOUNTER, label=c.ref)
        squares_ = frozenset(c.area())
        me = c.me

        def hurt(ev: TurnStart) -> None:
            if (
                not ev.ghost
                and ev.actor in c.enemies()
                and ev.actor in c.in_squares(squares_, side="any")
            ):
                c.flat(5, on=ev.actor)

        def entered(ev: ZoneEntered) -> None:
            if ev.zone == ring and ev.actor in c.enemies():
                c.flat(5, on=ev.actor)

        c.watch(TurnStart, hurt, until=When.ENCOUNTER, on=me, label=f"{c.ref} wall")
        c.watch(ZoneEntered, entered, until=When.ENCOUNTER, on=me, label=f"{c.ref} wall")
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.UNTYPED)


@power(
    "m5784a5",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
)
def m5784a5(c: Cast) -> None:
    for eff in list(c.world.effects.of(c.me)):
        if eff.label.startswith("m5784a5 "):
            c.world.effects.end(eff, "changed shape")
    which = c.choose(["beast form", "humanoid form"], f"{c.ref}: which shape") or "humanoid form"
    c.form(until=When.ENCOUNTER, label=f"m5784a5 {which}")


# ==========================================================================
# m5833
# ==========================================================================


@power(
    "m5833a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5833a0(c: Cast) -> None:
    """"Can shift 1 additional square" is granted as an automatic extra
    shift rather than an offered one -- the printed "can" is approximated
    as "does"."""
    me = c.me

    def extra(ev: Moved) -> None:
        if ev.kind_ != "shift" or ev.actor == me:
            return
        if team(c.world, ev.actor) is not team(c.world, me):
            return
        if distance_between(c.world, me, ev.actor) <= 5:
            c.shift(1, who=ev.actor)

    c.watch(Moved, extra, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5833a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FIRE, Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("3d6", 5, dtype=DamageType.FIRE),
)
def m5833a1(c: Cast) -> None:
    if c.strike():
        c.hit()
    if c.may("slide the target 1 square", who=c.me):
        c.slide(1)


@power(
    "m5833a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.NECROTIC, Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("3d6", 5, dtype=DamageType.NECROTIC),
)
def m5833a2(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    _no_sight_past(c, 2)


@power(
    "m5833a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=10),
    dropped=("c.condition(when=)",),
)
def m5833a3(c: Cast) -> None:
    """"Recharges if the power misses" replaces the die with a deterministic
    hand-back. "Weakened when attacking anyone but the chosen ally" cannot
    be narrowed to one exempted creature -- `c.condition` takes no `when=`
    the way `c.bonus` does -- so the weaken is written plain and ends
    early if the chosen ally drops."""
    victim = c.target
    if not c.strike():
        c.restore_use(c.ref, on=c.me)
        return
    pool = [a for a in c.allies() if a != c.me]
    mate = c.choose(pool, f"{c.ref}: which ally") if pool else None
    if mate is None or victim is None:
        return
    hold = c.condition(Condition.WEAKENED, until=When.ENCOUNTER, on=victim)
    if hold is None:
        return

    def freed(ev: Dropped) -> None:
        if ev.actor == mate and not hold.ended:
            c.world.effects.end(hold, "the chosen ally fell")

    hold.subs.append(c.world.bus.on(Dropped, freed, owner=c.me))


@power(
    "m5833a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC, Keyword.ZONE, Keyword.AREA],
    dropped=("Usage.RECHARGE(when=)",),
)
def m5833a4(c: Cast) -> None:
    if c.first:
        _rearms_when_bloodied(c)
    me = c.me
    ring = c.zone(c.area(), difficult=True, until=When.SUSTAIN, sustain=MINOR, label=c.ref)
    zone = c.world.get(ring, Zone)
    if zone is None or zone.effect is None:
        return
    squares_ = frozenset(c.area())

    def toll(ev: TurnStart) -> None:
        if (
            not ev.ghost
            and ev.actor in c.enemies()
            and ev.actor in c.in_squares(squares_, side="any")
        ):
            c.flat(10, dtype=DamageType.NECROTIC, on=ev.actor)

    def entered(ev: ZoneEntered) -> None:
        if ev.zone == ring and ev.actor in c.enemies():
            c.flat(10, dtype=DamageType.NECROTIC, on=ev.actor)

    zone.effect.subs.append(c.world.bus.on(TurnStart, toll, owner=me))
    zone.effect.subs.append(c.world.bus.on(ZoneEntered, entered, owner=me))
    c.on_sustain(zone.effect, lambda: c.move_zone(ring, 4))


@power(
    "m5833a5",
    level=7,
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.TELEPORTATION],
)
def m5833a5(c: Cast) -> None:
    c.teleport(3)
    c.insubstantial(until=When.SONT)


def _hit_while_bloodied(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and bool((h := world.get(me, Health)) and h.bloodied)


@power(
    "m5833a6",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an attack hits it while she is bloodied",
    on=(
        Trigger(Bloodied, about_me, "an attack bloodies it"),
        Trigger(Hit, _hit_while_bloodied, "an attack hits it while bloodied"),
    ),
)
def m5833a6(c: Cast) -> None:
    c.restore_use("m5833a5", on=c.me)
    c.use_power("m5833a5")


# ==========================================================================
# m5874
# ==========================================================================


@power(
    "m5874a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.NECROTIC, Keyword.MELEE],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d6", 3, dtype=DamageType.NECROTIC),
)
def m5874a0(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is not None:
        c.ignore_resistance(
            dtype=DamageType.NECROTIC, on=victim, until=When.SAVE_ENDS, immunity=True
        )
        c.ongoing(5, DamageType.NECROTIC, on=victim)


@power(
    "m5874a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.NECROTIC, Keyword.RANGED],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("3d8", 9, dtype=DamageType.NECROTIC, kind=LIMITED),
)
def m5874a1(c: Cast) -> None:
    if not c.strike():
        return
    c.hit()
    victim = c.target
    if victim is None:
        return
    for which in ALL_DEFENCES:
        c.penalty(which, 5, on=victim, until=When.EONT)


@power(
    "m5874a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=AreaBurst(1, 10),
    target=EACH_CREATURE,
    keywords=[Keyword.IMPLEMENT, Keyword.ZONE, Keyword.AREA],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("3d6", 12),
)
def m5874a2(c: Cast) -> None:
    if c.first:
        ring = c.zone(c.area(), until=When.ENCOUNTER, sustain=MINOR, label=c.ref)
        squares_ = frozenset(c.area())
        me = c.me

        def buzz(ev: TurnStart) -> None:
            if not ev.ghost and ev.actor in c.in_squares(squares_, side="any"):
                c.flat(5, on=ev.actor)

        c.watch(TurnStart, buzz, until=When.ENCOUNTER, on=me, label=f"{c.ref} zone")
        _ = ring
    if c.strike():
        c.hit()


@power(
    "m5874a3",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m5874a3(c: Cast) -> None:
    c.bonus("damage", 0, dice="1d10", on=c.me, until=When.ENCOUNTER, once=True)


@power(
    "m5874a4",
    level=7,
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.NECROTIC],
    trigger="an enemy reduces it to 0 hit points",
    on=Trigger(Dropped, about_me, "an enemy reduces it to 0 hit points"),
)
def m5874a4(c: Cast) -> None:
    foe = getattr(c.trigger, "source", None)
    if foe is not None:
        c.flat(5 + c.roll("2d10"), dtype=DamageType.NECROTIC, on=foe)


# ==========================================================================
# m5918
# ==========================================================================


@power(
    "m5918a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.HEALING],
)
def m5918a0(c: Cast) -> None:
    """An undead ally that would die in the aura is stood back up inside
    the same `Dropped` window instead, the way `level_02/soldiers_sa.py`'s
    `m3533a3` revives its own caster. The coup-de-grace window the card
    describes needs nothing extra -- `c.coup_de_grace` already exists."""
    me = c.me

    def saved(ev: Dropped) -> None:
        victim = ev.actor
        if victim == me or not c.is_kind("undead", on=victim):
            return
        if distance_between(c.world, me, victim) > 3:
            return
        c.reanimate(on=victim, hp=1)

    c.watch(Dropped, saved, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5918a1",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    out_of_combat=True,
)
def m5918a1(c: Cast) -> None:
    """Appearance only -- how other undead read `m5918a5`'s disguise, with
    no row anywhere in this stat block gating on it."""


@power(
    "m5918a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d6", 8),
)
def m5918a2(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m5918a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.FORCE, Keyword.RANGED],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("2d6", 5, dtype=DamageType.FORCE),
)
def m5918a3(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.prone()
    c.push(2)


@power(
    "m5918a4",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=STANDARD,
    reach=AreaBurst(2, 10),
    target=EACH_ENEMY,
    keywords=[Keyword.NECROTIC, Keyword.AREA],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("1d8", 5, dtype=DamageType.NECROTIC),
)
def m5918a4(c: Cast) -> None:
    victim = c.target

    def worsens(eff: Effect, who: Any = victim) -> None:
        c.world.effects.end(eff, "it worsens")
        c.condition(Condition.SLOWED, Condition.WEAKENED, until=When.SAVE_ENDS, on=who)

    if c.strike():
        c.hit()
        c.condition(Condition.SLOWED, until=When.SAVE_ENDS, on=victim, escalate=worsens)
    if c.first:
        for mate in c.in_squares(c.area(), side="ally"):
            if c.is_kind("undead", on=mate):
                c.bonus("damage", 5, dtype=DamageType.NECROTIC, on=mate, until=When.EONT)


@power(
    "m5918a5",
    level=7,
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.POLYMORPH],
    out_of_combat=True,
)
def m5918a5(c: Cast) -> None:
    """A disguise and nothing else -- no other row in this file gates on
    which shape he wears."""
    c.note(f"{c.ref}: alters his form to appear as a Medium living or undead humanoid")


@power(
    "m5918a6",
    level=7,
    usage=AT_WILL,
    action=ActionType.IMMEDIATE_INTERRUPT,
    reach=PERSONAL,
    target=NO_TARGET,
    trigger="an enemy's attack damages it while an undead ally is within 3 squares",
    on=Trigger(
        DamageApplied, both(targets_me, ally_within(3)),
        "an enemy's attack damages it while an undead ally is within 3 squares",
    ),
)
def m5918a6(c: Cast) -> None:
    mate = next(
        (
            a
            for a in c.allies()
            if a != c.me and c.is_kind("undead", on=a) and distance_between(c.world, c.me, a) <= 3
        ),
        None,
    )
    if mate is None:
        return
    c.reduce(5, c.trigger)
    c.flat(5, on=mate)


# ==========================================================================
# m5936
# ==========================================================================


@power(
    "m5936a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m5936a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(5, until=When.ENCOUNTER, label=c.ref)
    shadows = c.world.get(ring, Zone)
    if shadows is not None:
        shadows.difficult = True

    def press(ev: TurnStart) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if ev.actor in c.world.zones.occupants(ring) and c.is_(Condition.DAZED, on=ev.actor):
            c.flat(5, dtype=DamageType.PSYCHIC, on=ev.actor)

    c.watch(TurnStart, press, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m5936a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("1d8", 5),
)
def m5936a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.ongoing(5, DamageType.UNTYPED)


@power(
    "m5936a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(5),
    target=UpTo(2),
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("1d6", 3, dtype=DamageType.PSYCHIC),
)
def m5936a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m5936a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=10),
    requires=_nobody_dominated_by("m5936a3"),
    requires_text="recharges when no creature is dominated by this power",
    dropped=("Usage.RECHARGE(when=)",),
)
def m5936a3(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.is_(Condition.DAZED, on=victim):
        victim = next((f for f in c.enemies() if c.is_(Condition.DAZED, on=f)), None)
    if victim is None or not c.strike(on=victim):
        return
    c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)


# ==========================================================================
# m6021
# ==========================================================================


@power(
    "m6021a0",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.WEAPON, Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 4),
)
def m6021a0(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6021a1",
    level=7,
    usage=Usage.RECHARGE,
    recharge=6,
    action=STANDARD,
    reach=CloseBurst(3),
    target=EACH_OTHER,
    keywords=[Keyword.POISON, Keyword.CLOSE],
    attack=Attack(vs=FORT, printed=10),
    damage=Damage("2d6", 3, dtype=DamageType.POISON, kind=LIMITED),
)
def m6021a1(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.blinded(until=When.EONT)


@power(
    "m6021a2",
    level=7,
    usage=ENCOUNTER,
    action=STANDARD,
    reach=CloseBlast(5),
    target=EACH_OTHER,
    keywords=[Keyword.PSYCHIC, Keyword.CLOSE],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("2d8", 4, dtype=DamageType.PSYCHIC),
)
def m6021a2(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.condition(Condition.DAZED, Condition.SLOWED, until=When.SAVE_ENDS)


@power(
    "m6021a3",
    level=7,
    usage=ENCOUNTER,
    action=MINOR,
    reach=Ranged(3),
    target=ONE_CREATURE,
    keywords=[Keyword.POISON, Keyword.RANGED],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d8", 4),
)
def m6021a3(c: Cast) -> None:
    victim = c.target
    if not c.strike() or victim is None:
        return
    c.hit()
    mod = Mod(what="attack", value=-2, kind="untyped", label=c.ref)
    c.world.effects.apply(
        victim, c.me, When.SAVE_ENDS, label=c.ref,
        mods=[(victim, mod)], ongoing=(5, DamageType.POISON),
    )


def _hits_bloodied_me(world: World, me: int, ev: Any) -> bool:
    return getattr(ev, "target", None) == me and bool((h := world.get(me, Health)) and h.bloodied)


@power(
    "m6021a4",
    level=7,
    usage=ENCOUNTER,
    action=ActionType.IMMEDIATE_REACTION,
    reach=Melee(1),
    target=NO_TARGET,
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d10", 4, half_on_miss=True),
    trigger="an attack bloodies it or hits it while it is bloodied",
    on=(
        Trigger(Bloodied, about_me, "an attack bloodies it"),
        Trigger(Hit, _hits_bloodied_me, "an attack hits it while it is bloodied"),
    ),
)
def m6021a4(c: Cast) -> None:
    ev = c.trigger
    foe = getattr(ev, "attacker", None) or getattr(ev, "source", None)
    if foe is None:
        return
    if c.strike(on=foe):
        c.hit(on=foe)
        c.push(3, on=foe)
        c.prone(on=foe)
    else:
        c.hit(half=True, on=foe)
    c.temp_hp(25, on=c.me)
    c.bonus("damage", 5, on=c.me, until=When.ENCOUNTER, when=_melee_only)


# ==========================================================================
# m6108
# ==========================================================================


@power(
    "m6108a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=[Keyword.PSYCHIC],
)
def m6108a0(c: Cast) -> None:
    me = c.me
    ring = c.aura(5, until=When.ENCOUNTER, label=c.ref)
    shadows = c.world.get(ring, Zone)
    if shadows is not None:
        shadows.difficult = True

    def press(ev: TurnEnd) -> None:
        if ev.ghost or ev.actor not in c.enemies():
            return
        if ev.actor not in c.world.zones.occupants(ring):
            return
        instead = "make a basic attack against its nearest ally instead of taking damage"
        if c.may(instead, who=ev.actor):
            mate = min(
                (a for a in allies(c.world, ev.actor) if a != ev.actor),
                key=lambda a: distance_between(c.world, ev.actor, a),
                default=None,
            )
            if mate is not None:
                c.basic(who=ev.actor, on=mate)
                return
        c.flat(5, dtype=DamageType.PSYCHIC, on=ev.actor)

    c.watch(TurnEnd, press, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6108a1",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6108a1(c: Cast) -> None:
    me = c.me

    def hot(ev: DamageApplied) -> None:
        if ev.target == me and ev.dtype == DamageType.FIRE:
            c.bonus("damage", 4, on=me, until=When.EONT, kind="power")

    c.watch(DamageApplied, hot, until=When.ENCOUNTER, on=me, label=c.ref)


@power(
    "m6108a2",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("3d6", 5),
)
def m6108a2(c: Cast) -> None:
    if c.strike():
        c.hit()
    if c.may("slide the target 1 square", who=c.me):
        c.slide(1)


@power(
    "m6108a3",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(2),
    target=ONE_CREATURE,
)
def m6108a3(c: Cast) -> None:
    victim = c.target
    if victim is None:
        return
    c.use_power("m6108a2", on=victim)
    c.use_power("m6108a2", on=victim)


@power(
    "m6108a4",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Ranged(10),
    target=UpTo(2),
    keywords=[Keyword.PSYCHIC, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=10),
    damage=Damage("2d6", 2, dtype=DamageType.PSYCHIC),
)
def m6108a4(c: Cast) -> None:
    if c.strike():
        c.hit()
        c.dazed(until=When.EONT)


@power(
    "m6108a5",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=STANDARD,
    reach=CloseBurst(2),
    target=EACH_OTHER,
    keywords=[Keyword.FIRE, Keyword.CLOSE],
    attack=Attack(vs=REF, printed=10),
    damage=Damage("3d6", 7, dtype=DamageType.FIRE),
    dropped=("Usage.RECHARGE(when=)",),
)
def m6108a5(c: Cast) -> None:
    if c.first:
        _rearms_when_bloodied(c)
    if not c.strike():
        return
    c.hit()
    me = c.me
    hold = c.effect(c.ref, until=When.EONT, on=me)
    if hold is None:
        return

    def burned(ev: AttackDeclared) -> None:
        if not hold.ended and ev.target == me:
            c.flat(5, dtype=DamageType.FIRE, on=ev.attacker)

    hold.subs.append(c.world.bus.on(AttackDeclared, burned, owner=me))


@power(
    "m6108a6",
    level=7,
    usage=Usage.RECHARGE,
    recharge=0,
    action=MINOR,
    reach=Ranged(10),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=10),
    requires=_nobody_dominated_by("m6108a6"),
    requires_text="recharges when no creature is dominated by this power",
    dropped=("Usage.RECHARGE(when=)",),
)
def m6108a6(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.is_(Condition.DAZED, on=victim):
        victim = next((f for f in c.enemies() if c.is_(Condition.DAZED, on=f)), None)
    if victim is None or not c.strike(on=victim):
        return
    c.condition(Condition.DOMINATED, until=When.SAVE_ENDS, on=victim)


# ==========================================================================
# m6427
# ==========================================================================


@power(
    "m6427a0",
    level=7,
    usage=AT_WILL,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6427a0(c: Cast) -> None:
    me = c.me
    for who in c.allies():
        c.bonus(
            "save", 2, on=who, kind="power", until=When.ENCOUNTER,
            when=lambda ctx, w=who: distance_between(c.world, me, w) <= 5,
        )


@power(
    "m6427a1",
    level=7,
    usage=AT_WILL,
    action=STANDARD,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.MELEE],
    attack=Attack(vs=AC, printed=12),
    damage=Damage("2d4", 10),
)
def m6427a1(c: Cast) -> None:
    if c.strike():
        c.hit()


@power(
    "m6427a2",
    level=7,
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=NO_TARGET,
)
def m6427a2(c: Cast) -> None:
    pool = [a for a in c.allies() if c.can_see(a)]
    mate = c.choose(pool, f"{c.ref}: which ally") if pool else None
    if mate is None:
        return
    foe = min(
        enemies(c.world, mate), key=lambda f: distance_between(c.world, mate, f), default=None
    )
    if foe is None:
        return
    c.run_at(foe, who=mate)
    c.bonus("attack", 2, on=mate, kind="power", once=True, until=When.EOT)
    c.basic(who=mate, on=foe)


@power(
    "m6427a3",
    level=7,
    usage=Usage.RECHARGE,
    recharge=5,
    action=MINOR,
    reach=Ranged(5),
    target=ONE_CREATURE,
    keywords=[Keyword.CHARM, Keyword.RANGED],
    attack=Attack(vs=WILL, printed=10),
)
def m6427a3(c: Cast) -> None:
    victim = c.target
    if victim is None or not c.strike(on=victim):
        return
    me = c.me
    hold = c.effect(c.ref, until=When.EONT, on=victim)
    if hold is None:
        return

    def veto(ev: AttackDeclared) -> None:
        if not hold.ended and ev.attacker == victim and ev.target == me:
            ev.cancel("it cannot bring itself to")

    def broken(ev: AttackDeclared) -> None:
        if hold.ended:
            return
        attacker, tgt = getattr(ev, "attacker", None), getattr(ev, "target", None)
        if attacker is None or tgt is None:
            return
        if attacker in [me, *c.allies()] and (tgt == victim or tgt in allies(c.world, victim)):
            c.world.effects.end(hold, "m6427 broke the truce")

    hold.subs.append(c.world.bus.on(AttackDeclared, veto, window=Window.BEFORE, owner=me))
    hold.subs.append(c.world.bus.on(AttackDeclared, broken, owner=me))
