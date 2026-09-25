#!/usr/bin/env python
"""Fire every declared row and report the two ways one can be wrong.

    uv run scripts/audit.py
    uv run scripts/audit.py --class wizard
    uv run scripts/audit.py --level 1 --verbose

This is what makes writing a hundred powers at a time safe. Two failures
matter and nothing else does:

* **it raises.** A bug, printed with its traceback.
* **it does nothing.** No damage, no condition, no movement, no effect, no
  healing. A silent no-op is exactly what a wrongly written power looks
  like, it passes every other check in the repository, and it is invisible
  in a fight -- the power is simply never worth using and nobody can say
  why.

A row gets several attempts with different seeds before it is called silent,
because an attack power that misses three times running has done nothing and
is fine.

Generated from the registry, like `show.py`. No per-row ceremony: writing a
power costs a function and nothing else, which is the entire arrangement
this repository is built on.
"""

from __future__ import annotations

import argparse
import contextlib
import re
import traceback
from dataclasses import dataclass, field
from pathlib import Path

from combat_engine.content import chargen, loader
from combat_engine.engine import (
    Bus,
    DamageType,
    Encounter,
    Grid,
    Powers,
    Rng,
    Team,
    When,
    World,
    get,
    use,
)
from combat_engine.engine.dsl import REGISTRY
from combat_engine.engine.query import alive
from combat_engine.engine.types import ActionType

ROOT = Path(__file__).resolve().parents[1]

#: Events that mean the power did something. A power that emits none of
#: these on any attempt has not been written, whatever the file says.
#: Rows that fire and do nothing **on this board**, with the reason each.
#:
#: The silent check was structurally incapable of firing until today -- the
#: board leaves effects live for its own setup, so every row counted as
#: having done something -- which means no row in the tree has ever actually
#: been checked for this. These ten are what it found on its first honest
#: run. Some are known board limits; the rest are unverified and tracked.
#:
#: A row not on this list that goes silent fails the run. That is the point:
#: the list is short, visible, and has to be argued with, where a check that
#: could not fire was none of those things.
KNOWN_SILENT = {
    "m135a3": "targets a destroyed undead ally; the board has none",
    "m417a2": (
        "the same sentence as m135a3 -- it restores a destroyed undead minion, "
        "and the board has no dead ally. Verified by hand: with a felled m812 "
        "beside it the minion is healed to full and re-indexed in the square "
        "it fell in."
    ),
    "m3042a3": (
        "hands its allies a saving throw, and the only ally on the board "
        "carries nothing a save can end. Verified by hand: with a save-ends "
        "daze on that ally it rolls one at +5."
    ),
    "m3014a2": (
        "its whole content is opening opportunity windows, and the engine "
        "never decides what goes in one -- a controller answers. This board "
        "installs no policy, so the windows open and nobody swings. Verified "
        "by hand with policy.install: two windows, two opportunity attacks."
    ),
    "m297a2": "unverified",
    "m3027a3": "unverified",
    "m4902a4": "unverified",
    "m4962a3": "unverified",
    "m102a1": "unverified",
    "m103a1": "unverified",
    "m3030a1": "unverified",
    "m676a1": "unverified",
    "m719a4": "unverified",
    # Escaping a grab, on a board where nothing is holding the caster.
    # Grabbing it in `board()` is not the answer -- `Condition.GRABBED`
    # cannot move, which would make every movement row on every other
    # creature report wrongly. Driven by hand: the grab ends and the
    # relation clears.
    "p1515": "needs to be grabbed; grabbing the caster would break every movement row",
    # Slides everyone carrying ongoing damage *from one named sibling row*.
    # The board's burn comes from the harness, not from that row, and
    # firing the sibling first would need the harness to know which rows
    # feed which -- which is the content's business, not its own.
    "m4869a4": "slides creatures burning from a named sibling row; the board's burn is its own",
    # Drains every creature the m467 is holding, and the board holds nobody
    # -- the grabs come from its own minor action, which the harness does
    # not take first. Driven by hand: two limbs on one creature deal 10
    # necrotic and the m467 is healed by the same amount.
    "m467a2": "drains what it is grabbing; the harness never makes it grab",
    # Sends one of the m4967's own mossling minions running, and the board
    # spawns a second m4967 rather than a mossling. Driven by hand: with an
    # m4971 beside it the minion moves its full speed as a free action.
    "m4967a5": "moves a mossling minion; the board has none to move",
    # Sends a *bloodied* ally back in. The board's only creature on the
    # caster's own side is the second of its kind, spawned at full health --
    # the four wounded ones are all on the other team. Driven by hand: with
    # that ally at half hit points it is granted a melee attack and swings.
    "m350a2": "grants a bloodied ally an attack; the board's only ally is unhurt",
    # Both hand an ally a free attack against something the board does not
    # have: a *bloodied* enemy adjacent to that ally, and an encounter power
    # that ally has already spent. Arranging either would mean the harness
    # deciding what an ally has done this fight, which is the fight's
    # business rather than the instrument's.
    # Rerolls an ally's missed attack. It emits nothing of its own -- the
    # consequence is that the *attacking* row's Hit is announced instead of
    # its Miss, which is credited to that row and not to this one. Driven by
    # hand: the reroll lands and the Hit follows.
    "m4839a4": "rerolls somebody else's attack; the resulting Hit belongs to their row",
    "p2530": "an ally must have a bloodied enemy beside it",
    "p4572": "an ally must have already spent an encounter attack power",
    # Its printed Target *is* the avenger's oath target, and nothing on this
    # board has sworn one: `_use_class_features` runs inside `_provoke`, so
    # only a row with a declared trigger ever sees its class features. A
    # standard-action avenger row is fielded with nobody sworn. Driven by
    # hand with the oath on a distant enemy: it flies six squares without
    # provoking, lands adjacent and swings.
    "p6990": "targets the avenger's oath target; nothing swears one before a standard action",
    # An escape attempt or a saving throw, on a board that holds the caster
    # with neither. The same reason as `p1515` above, and the same answer:
    # holding the caster in `board()` would break every movement row on
    # every other creature. Driven by hand both ways -- immobilised (save
    # ends) it rolls and shakes it off, grabbed it clears the relation.
    "p4911": "needs to be held or slowed; holding the caster would break every movement row",
}


DID_SOMETHING = {
    "DamageApplied", "ConditionApplied", "Healed", "TempHP", "Moved",
    "ForcedMove", "RelationSet", "ZoneCreated", "EffectExpired", "Note",
    "Bloodied", "Dropped", "Died", "SavingThrow",
}  # fmt: skip

#: An effect applied is also doing something, but it only shows in the log
#: when it *ends*, so the live effect table is checked too.
TRIES = 8

#: Somebody to stand in front of the caster: Medium, so a push has room.
DUMMY = "m145"

#: And one undead, for the rows that only affect those.
UNDEAD = "m416"

#: A monster ability's id. Spelled out rather than `startswith("m")`, which
#: also matches `mba` -- the engine's own melee basic attack -- and sent the
#: auditor looking for a monster called "mb".
MONSTER_ABILITY = re.compile(r"^m\d+a\d+$")


@dataclass
class Result:
    ref: str
    fired: int = 0
    error: str = ""
    events: set[str] = field(default_factory=set)

    @property
    def silent(self) -> bool:
        return not self.error and not (self.events & DID_SOMETHING)


def board(ref: str, seed: int) -> tuple[World, int, set[str]]:
    """A caster with the row, four creatures in reach, and the fight started.

    The third value is what got emitted while the encounter was starting,
    which is where a trait does its work.
    """
    world = World(Grid(24, 16), Rng(seed), Bus())
    declared = get(ref)

    if MONSTER_ABILITY.match(ref):
        caster = loader.spawn(world, ref.split("a")[0], (6, 8), team=Team.ENEMY)
        # Only if `loader.spawn` did not already know it, which it does for
        # every declared row. Appending regardless put the ref in twice, so
        # the dispatcher offered it twice and every triggered monster row
        # paid out twice in the log the log is read to count.
        known = world.need(caster, Powers).known
        if ref not in known:
            known.append(ref)
        # A second of its kind, so a row reading "an ally within 10" has
        # one. A lone monster on a board of enemies can never satisfy its
        # own trigger, and several rows are about their friends.
        loader.spawn(world, ref.split("a")[0], (7, 9), team=Team.ENEMY)
        foe_team = Team.PC
    else:
        # A classless row -- the engine's own basic attacks -- is fielded on
        # whoever can hold it. `rba` is a ranged basic attack and no fighter
        # build owns a bow, so fielding one refused the row for a reason
        # that says nothing about the row.
        cls = declared.cls or (
            "ranger" if declared.reach.kind in ("ranged", "area_burst") else "fighter"
        )
        # Its class features come too. A row that triggers on a *cursed*
        # enemy dropping needs the thing that curses, and a caster holding
        # only the row under test can never satisfy its own precondition.
        features = sorted(
            p.ref for p in REGISTRY.values() if p.cls == cls and p.level == 0
        )
        caster = chargen.spawn(
            world,
            chargen.Character(
                cls, max(1, declared.level), [ref, *features], build=chargen.build_for(cls, ref)
            ),
            (6, 8),
        )
        foe_team = Team.ENEMY

    from combat_engine.engine import Health

    # One of them undead, because a few rows only affect those and a board
    # without one makes them look silent when they are simply particular.
    # All four inside a close burst 2, which is the smallest area any row
    # here uses -- a creature one square outside it is no test at all.
    for square, what in (
        ((7, 8), DUMMY), ((7, 9), UNDEAD), ((6, 9), DUMMY), ((5, 7), DUMMY)
    ):
        hurt = loader.spawn(world, what, square, team=foe_team)
        world.need(hurt, Health).hp -= 5

    # A wounded ally, because a great many powers heal one and a board of
    # creatures at full health makes every one of them look silent.
    ally = chargen.spawn(world, chargen.Character("cleric", 1, []), (5, 8))
    health = world.need(ally, Health)
    health.hp = max(1, health.max_hp // 2)
    # A second ally, standing apart from the first. A leader row reading
    # "each ally in the burst" or "another ally" could never show what it
    # does with exactly one friend on the board -- three warlord rows
    # reported silent while being correct, and the class is half made of
    # this shape.
    second = chargen.spawn(world, chargen.Character("fighter", 1, []), (4, 9))
    world.need(second, Health).hp = max(1, world.need(second, Health).max_hp - 8)

    caster_health = world.need(caster, Health)
    caster_health.hp = max(1, caster_health.max_hp - 5)

    # A master, a rider and a guard, because the engine grew all three and
    # nothing on the board ever set one -- so every row reading "its master"
    # or "its rider" fired into an empty relation and reported itself silent
    # or unusable while being perfectly correct. The caster is the servant
    # in one and the mount in the other, which between them cover the way
    # the printed lines are worded.
    from combat_engine.engine.types import Relation

    world.relations.set(Relation.MASTER_OF, ally, caster)
    world.relations.set(Relation.RIDDEN_BY, caster, ally)
    world.relations.set(Relation.GUARDED_BY, caster, ally)

    # A wall, so a row that needs cover or concealment has some. The board
    # was bare grid, so "one creature it is hidden from" could never be
    # satisfied and every such row reported itself unusable.
    world.grid.blocking.add((9, 8))
    # And one dummy already burning, because several rows target "a creature
    # taking ongoing damage" and nothing on the board ever was.
    from combat_engine.engine import Cast
    from combat_engine.engine.grid import spread
    from combat_engine.engine.query import enemies as _foes
    from combat_engine.engine.types import Condition

    setup = Cast(world=world, me=caster, ref="audit:setup")
    lined_up = list(_foes(world, caster))
    if lined_up:
        setup.target = lined_up[0]
        # Deliberately small. Ongoing damage of one type does not stack --
        # the highest applies -- so a board burning for 5 made every row
        # that applies ongoing 5 fire look silent: its effect was correctly
        # refused as no worse than what was already there. Three rows
        # reported that way the moment the rule went in.
        setup.ongoing(2, DamageType.FIRE, on=lined_up[0], until=When.ENCOUNTER)
    # And a second one on poison rather than fire. Several rows name the
    # damage type -- "one creature taking ongoing poison damage" -- and a
    # board where every burn is fire could not satisfy any of them.
    if len(lined_up) > 1:
        setup.target = lined_up[1]
        setup.ongoing(2, DamageType.POISON, on=lined_up[1], until=When.ENCOUNTER)

    # A save-ends effect on the ally, because "the target makes a saving
    # throw" is a whole shape of utility power and a board where nobody had
    # anything to save against made every one of them look silent.
    setup.target = ally
    setup.condition(Condition.DAZED, on=ally, until=When.SAVE_ENDS)

    # A zone, for the rows that target one. "One conjuration or zone" had
    # nothing to aim at.
    setup.target = None
    setup.zone(spread({(3, 10)}, 1), label="audit:setup zone", until=When.ENCOUNTER)

    # Bloodied, so a row gated on it can fire.
    caster_health.hp = max(1, caster_health.max_hp // 2 - 1)

    mark = len(world.bus.log)
    # Effects the board set up for itself -- a dummy already burning, a
    # caster already bloodied. Snapshotted *before* `start()` arms the
    # traits, so a trait whose whole content is installing an effect is
    # still credited with having done something. Snapshotting after arming
    # reported a hundred and twenty-three correct traits as silent.
    world.setup_effects = set(world.effects.live)
    Encounter(world).start()
    # And again once every trait on the board is armed. Two snapshots,
    # because the two branches need different baselines: an ordinary row is
    # credited only with what it installs *after* arming, while a trait's
    # whole content may be the effect arming installed -- and every other
    # creature's traits arm at the same moment.
    world.armed_effects = set(world.effects.live)
    armed = {e.kind for e in world.bus.log[mark:]} - START_NOISE
    world.turn = caster
    return world, caster, armed


#: What starting a fight emits no matter who is in it. Subtracted from what
#: a trait is credited with, or every trait would look busy.
START_NOISE = {"RoundStart", "TurnStart", "PowerUsed"}


#: Every d20 face worth forcing. None is "roll it"; 20 and 1 are the two
#: branches a random pass almost never reaches, and both are where a row
#: does something it does nowhere else.
LOADED = (None, 20, 1)


#: What the provocation itself emits. Subtracted so a triggered row is
#: credited only with what *it* did, not with being attacked.
PROVOKE_NOISE = {
    "AttackDeclared", "AttackRolled", "Hit", "Miss", "DamageRolled",
    "DamageApplied", "OpportunityWindow", "TurnStart", "TurnEnd",
}

#: Movement is the *whole content* of several triggered rows -- "it shifts 1
#: square" is what four of them do. Subtracting movement as provocation
#: noise therefore made it impossible for any of them to be credited with
#: anything, and they reported SILENT while firing correctly twelve times
#: out of eight. The provocation this harness makes is an attack and a
#: shift by somebody *else*, so movement by the row's own owner is not
#: noise: it is the answer.
def _own_movement(world, ref: str, cursor: int, owner: int) -> set[str]:  # noqa: ANN001
    kinds = set()
    for e in world.bus.log[cursor:]:
        if e.kind in ("Moved", "MoveStart", "MoveEnd") and getattr(e, "actor", None) == owner:
            kinds.add(e.kind)
    return kinds


def _decisions_are_honoured() -> list[str]:
    """Refusing a `Decision` must actually prevent it.

    Five events are proposals rather than announcements. A listener refuses
    one; the *emitter* has to honour that, and four separate bugs came from
    an emitter that announced something and then went ahead from its own
    local variables -- each of them silent, each found only when a content
    author happened to write a row that needed it.

    So this refuses each one and checks the consequence does not happen.
    That is a guarantee rather than a convention, and conventions are what
    failed all four times.
    """
    from combat_engine.engine.components import Health, Position
    from combat_engine.engine.events import (
        AttackDeclared,
        DamageRolled,
        Decision,
        ForcedMove,
        MoveStart,
        Window,
    )
    from combat_engine.engine.movement import forced, walk
    from combat_engine.engine.query import enemies
    from combat_engine.engine.resolve import attack, deal_damage
    from combat_engine.engine.types import Defense, Forced

    out: list[str] = []

    def board_():  # noqa: ANN202
        world, me, _ = board("m145a0", 1)
        return world, me, sorted(enemies(world, me))[0]

    # MoveStart: a refused walk covers no ground.
    world, me, _foe = board_()
    world.bus.on(MoveStart, lambda ev: ev.cancel("probe"), window=Window.BEFORE)
    here = world.get(me, Position).square
    if walk(world, me, [(here[0], here[1] - 1)]) != 0:
        out.append("MoveStart: refusing it did not stop the walk")

    # ForcedMove: a refused shove moves nobody.
    world, me, foe = board_()
    world.bus.on(ForcedMove, lambda ev: ev.cancel("probe"), window=Window.BEFORE)
    if forced(world, me, foe, Forced.PUSH, 3) != 0:
        out.append("ForcedMove: refusing it did not stop the push")

    # DamageRolled: a refused blow takes no hit points.
    world, me, foe = board_()
    world.bus.on(DamageRolled, lambda ev: ev.cancel("probe"), window=Window.BEFORE)
    before = world.need(foe, Health).hp
    deal_damage(world, me, foe, 10)
    if world.need(foe, Health).hp != before:
        out.append("DamageRolled: refusing it did not stop the damage")

    # AttackDeclared: a refused attack never rolls.
    world, me, foe = board_()
    world.bus.on(AttackDeclared, lambda ev: ev.cancel("probe"), window=Window.BEFORE)
    if not attack(world, me, foe, 30, Defense.AC, power="probe").cancelled:
        out.append("AttackDeclared: refusing it did not stop the attack")

    # And the other side of the split: a notification cannot be refused at
    # all, which is what keeps `cancel()` off the thirty classes that are
    # announcements. `Moved` is one -- by the time it is emitted the
    # creature has moved, and there is nothing left to argue about.
    from combat_engine.engine.events import Moved

    if issubclass(Moved, Decision) or hasattr(Moved, "cancel"):
        out.append("Moved is a notification and should not carry cancel()")
    return out


def _provoke(world, caster: int, ref: str, cursor: int) -> bool:  # noqa: ANN001
    """Make the thing happen that this row triggers off, and see if it fires.

    Three situations between them cover nearly every printed trigger at this
    tier: somebody swings at the row's owner, the owner swings at somebody,
    and somebody walks past. The row is offered by the real dispatcher, so
    its predicate and its action budget are exercised too -- which a direct
    call skips entirely.
    """
    from combat_engine.engine.components import Powers
    from combat_engine.engine.movement import shift
    from combat_engine.engine.query import enemies

    def basic(eid: int) -> str:
        """Whatever *this* creature swings with. Hardcoding the generic melee
        basic meant every attack in here was refused as "not known", because
        a monster's basic is one of its own abilities."""
        known = world.get(eid, Powers)
        return known.basic if known else ""

    foes = [f for f in enemies(world, caster) if alive(world, f)]
    if not foes:
        return False

    # Put the caster in the state its own class puts it in first. A
    # warlock's pact boon triggers on a *cursed* enemy dropping, and a
    # harness that only swings and walks can never curse anybody -- so
    # three correctly written rows reported themselves unusable.
    _use_class_features(world, caster, foes[0])
    if _fired(world, ref, cursor):
        return True

    for attacker, target in ((foes[0], caster), (caster, foes[0])):
        use(world, attacker, basic(attacker), targets=[target], spend=False)
        if _fired(world, ref, cursor):
            return True

    # A burst or a blast of its own. "When the m5027 hits with a close or
    # area attack" is a common enough shape, and a harness that only ever
    # swings a basic can never produce one.
    for other in _area_rows(world, caster, ref):
        use(world, caster, other, spend=False)
        if _fired(world, ref, cursor):
            return True
    for foe in foes[:2]:
        for sq in sorted(world.reachable_squares(foe, 1)):
            shift(world, foe, sq)
            if _fired(world, ref, cursor):
                return True

    # Somebody goes down. Several rows trigger on a creature dropping --
    # a leader's rally, the warlock's pact boons -- and attacking and
    # walking about can never produce one, so the harness had no way to
    # reach them and reported every one of them unusable.
    from combat_engine.engine import Health

    # foes[0] included: it is the one the class features were aimed at,
    # so it is the cursed / quarried / marked one, and leaving it out of
    # the killing meant no row triggering on that ever fired.
    # The caster last, and only if nothing else worked: a death throe
    # triggers on its own downfall, and a harness that only ever kills
    # other people can never reach one. Three such rows were written and
    # none had ever been exercised.
    for victim in (*foes, *_allies_of(world, caster), caster):
        if victim == caster:
            # Put everybody else back on their feet first. A death throe is
            # an attack on whoever is still standing, and by this point the
            # harness has killed all of them -- so the burst declared
            # against an empty board and looked like a row that does
            # nothing. Three level-4 rows and one at level 3 failed this way.
            _revive_everyone(world, caster)
        health = world.get(victim, Health)
        if health is None or health.hp <= 0:
            continue
        world.damage(caster, victim, health.hp + health.max_hp)
        if _fired(world, ref, cursor):
            return True
    return _fired(world, ref, cursor)


def _area_rows(world, caster: int, exclude: str) -> list[str]:  # noqa: ANN001
    """This creature's own close and area attacks, cheapest first."""
    from combat_engine.engine.components import Powers

    known = world.get(caster, Powers)
    if known is None:
        return []
    out = []
    for other in known.all:
        p = get(other)
        if p is None or other == exclude or p.triggers:
            continue
        if p.reach.kind in ("close_burst", "close_blast", "area_burst"):
            out.append(other)
    return out[:2]


def _after_its_own_use(world, ref: str, cursor: int) -> set[str]:  # noqa: ANN001
    """Event kinds logged after this row's own `PowerUsed`.

    A triggered row is fired by provoking it, and the provocation is an
    attack -- which drops creatures, applies conditions and expires effects
    on its own account. Everything before the row ran is the provocation's;
    everything after is by definition the row's consequences.
    """
    log = world.bus.log[cursor:]
    for i, e in enumerate(log):
        if e.kind == "PowerUsed" and getattr(e, "power", None) == ref:
            return {x.kind for x in log[i + 1:]}
    return set()


def _revive_everyone(world, except_: int) -> None:  # noqa: ANN001
    """Undo the harness's own killing, so the next probe has a board."""
    from combat_engine.engine import Conditions, Health
    from combat_engine.engine.types import Condition

    for eid, health in list(world.each(Health)):
        if eid == except_:
            continue
        health.hp = health.max_hp
        conds = world.get(eid, Conditions)
        if conds is not None:
            for cond in (Condition.DYING, Condition.UNCONSCIOUS, Condition.PRONE):
                conds.counts.pop(cond, None)


def _use_with_any_grip(world, caster: int, ref: str) -> bool:  # noqa: ANN001
    """Use the row, drawing a different weapon first if that is what it needs.

    A creature holds one legal grip at a time, so a bow is on the belt while
    the blades are out. A ranged row is not unusable then -- it is one minor
    action away, which is exactly what a player would spend. Trying each
    grip is the difference between "this row does not work" and "this row
    needs the other weapon".
    """
    from combat_engine.engine import Gear

    if use(world, caster, ref):
        return True
    gear = world.get(caster, Gear)
    if gear is None or len(gear.weapons) < 2:
        return False
    for weapon in gear.weapons:
        gear.wield(weapon)
        if use(world, caster, ref):
            return True
    return False


def _use_class_features(world, caster: int, foe: int) -> None:  # noqa: ANN001
    """Fire the caster's own level-0 rows -- its curse, its quarry, its mark."""
    from combat_engine.engine.components import Powers

    known = world.get(caster, Powers)
    if known is None:
        return
    for ref in list(known.all):
        p = get(ref)
        # Not a trait, and not a row that waits for a trigger either: a
        # triggered feature called directly gets no event to answer, returns
        # at its first line, and is then counted as having fired -- which
        # short-circuits the provocation that would have exercised it
        # properly. `_area_rows` already makes the same exclusion.
        if p is None or p.level != 0 or p.action is ActionType.NONE or p.triggers:
            continue
        with contextlib.suppress(Exception):
            use(world, caster, ref, targets=[foe] if p.is_attack else None, spend=False)


def _allies_of(world, caster: int) -> list[int]:  # noqa: ANN001
    from combat_engine.engine.query import allies

    return [a for a in allies(world, caster) if alive(world, a)]


def _fired(world, ref: str, cursor: int) -> bool:  # noqa: ANN001
    return any(
        getattr(e, "power", None) == ref or getattr(e, "ref", None) == ref
        for e in world.bus.log[cursor:]
    )


#: Touching any of these changes how every row behaves, so a narrowed run
#: is not narrowed at all -- it is wrong.
WIDE = ("src/combat_engine/engine/", "scripts/audit.py")


def _changed() -> list[str]:
    """Rows declared in files that differ from HEAD.

    At a hundred milliseconds a row, auditing everything is twenty seconds
    today and about five minutes once PHB1 is written. Most runs have
    touched a handful of rows and re-firing the other three thousand buys
    nothing -- which is exactly how the first attempt's suite grew until
    nobody could afford to run it.

    An engine change is not narrowable: it moves every row at once, so
    touching `engine/` widens this back to everything rather than quietly
    checking a tenth of what it should.
    """
    import re
    import subprocess

    done = subprocess.run(
        ["git", "status", "--porcelain", "-uall"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if done.returncode != 0:
        return sorted(REGISTRY)
    files = [line[3:].strip() for line in done.stdout.splitlines() if line[3:].strip()]
    if any(f.startswith(WIDE) for f in files):
        return sorted(REGISTRY)

    refs: list[str] = []
    for name in files:
        if "/content/" not in name or not name.endswith(".py"):
            continue
        path = ROOT / name
        if not path.exists():
            continue
        refs += re.findall(r'@power\(\s*"([^"]+)"', path.read_text())
    return sorted({r for r in refs if r in REGISTRY})


def _run_all(refs: list[str], jobs: int = 0) -> list[Result]:
    """Fire every row, in parallel, in the order they were asked for.

    Each row builds its own `World` and shares nothing with any other, so
    this is embarrassingly parallel and was single-threaded -- a full sweep
    reached 189s at a thousand rows, on a machine with ten cores, and the
    content is not a third written. That curve is the one thing most likely
    to make this project unpleasant to work on, so it is worth the fifteen
    lines.

    Order is preserved rather than taken as results arrive: the report is
    read by eye and a list that reshuffles between runs is harder to diff.
    Serial with `--jobs 1`, which is what to use when a row is crashing and
    a traceback from the right process matters.
    """
    if jobs == 1 or len(refs) < 8:
        return [audit(ref) for ref in refs]

    from concurrent.futures import ProcessPoolExecutor

    with ProcessPoolExecutor(max_workers=jobs or None) as pool:
        return list(pool.map(audit, refs, chunksize=8))


def _attempts(out: Result):  # noqa: ANN202
    """`(seed, face)` pairs, giving up on a face once the row has shown itself."""
    for face in LOADED:
        for seed in range(1, TRIES + 1):
            if out.fired and (out.events & DID_SOMETHING):
                break
            yield seed, face


def audit(ref: str) -> Result:
    out = Result(ref=ref)
    declared = get(ref)
    # A trait is armed by `Encounter.start`, not taken as an action, so by
    # the time the board is built it is already in force and using it again
    # is correctly refused. Firing it a second time would report every trait
    # in the game as unusable, which is the instrument lying about the fix.
    trait = declared is not None and declared.action is ActionType.NONE
    # A row with a declared trigger reads the event it is answering. Calling
    # it as a plain action hands it no event, so its first line finds nothing
    # to respond to and it returns -- reported as silent, when what was wrong
    # was the way it was fired. These are played instead: the dispatcher is
    # allowed to offer them, in the situation the trigger names.
    triggered = declared is not None and bool(declared.triggers)
    # Seeds and faces do different jobs, so they stop for different reasons.
    #
    # A **face** is a branch of the row -- what it does on a critical, what
    # it does on a fumble -- and all three are always tried.
    #
    # A **seed** is another arrangement of the board, and seeds exist only to
    # find one where the row can fire at all. Once it has fired *and* done
    # something on this face, the rest re-prove the same thing. Eight of them
    # meant twenty-four boards for every row, and the audit builds a hundred
    # thousand boards.
    for seed, face in _attempts(out):
        try:
            world, caster, armed = board(ref, seed)
            world.rng.loaded = face
            cursor = len(world.bus.log)
            # Asking whether *any* effect was live was unconditionally true
            # -- the board burns a dummy -- so a row that installed nothing
            # at all still counted as having done something, and the silent
            # check could never fire through this branch.
            had = world.armed_effects
            if trait:
                out.fired += 1
                out.events |= armed
                # A trait's effect was installed by arming, so it is measured
                # against the board before that -- and only the caster's own,
                # since every other creature armed at the same moment.
                mine = {
                    i for i, e in world.effects.live.items() if e.source == caster
                }
                if mine - world.setup_effects:
                    out.events.add("ConditionApplied")
                continue
            if triggered:
                if not _provoke(world, caster, ref, cursor):
                    continue
                out.fired += 1
                # Only what happened *after* the row itself went off. The
                # old form subtracted a fixed list of event kinds, which
                # left `Dropped`, `Died`, `ConditionApplied` and
                # `EffectExpired` from the provocation credited to the row
                # -- so a row whose body could not act on this board still
                # passed, carrying the consequences of being attacked.
                # Damage the row itself dealt is credited even though the
                # provocation's damage is not: `PROVOKE_NOISE` drops both
                # kinds wholesale, so a triggered row whose *whole content*
                # is damage reported silent however well it worked.
                mine = _after_its_own_use(world, ref, cursor)
                if any(
                    getattr(e, "detail", None) == ref
                    for e in world.bus.log[cursor:]
                    if e.kind in ("DamageRolled", "DamageApplied")
                ):
                    mine |= {"DamageApplied"}
                out.events |= mine - PROVOKE_NOISE | (mine & {"DamageApplied"})
                out.events |= _own_movement(world, ref, cursor, caster)
                if set(world.effects.live) - had:
                    out.events.add("ConditionApplied")
                continue
            if not _use_with_any_grip(world, caster, ref):
                continue
            out.fired += 1
            out.events |= {e.kind for e in world.bus.log[cursor:]}
            if set(world.effects.live) - had:
                out.events.add("ConditionApplied")
        except Exception:  # the traceback is the finding
            out.error = traceback.format_exc()
            return out
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("refs", nargs="*", help="rows to fire; default is all of them")
    ap.add_argument(
        "--class",
        dest="cls",
        action="append",
        help="only this class; repeatable. Without `append` a second one "
        "silently replaced the first, so `--class rogue --class ranger` "
        "quietly audited ranger alone and reported success.",
    )
    ap.add_argument("--level", type=int, help="only this level")
    ap.add_argument("--monsters", action="store_true", help="monster abilities only")
    ap.add_argument("--verbose", action="store_true", help="say what each row did")
    ap.add_argument("--changed", action="store_true",
                    help="only rows in content files that differ from HEAD")
    ap.add_argument("--jobs", type=int, default=0,
                    help="worker processes; 0 picks one per core, 1 stays serial")
    args = ap.parse_args()

    wanted = args.refs or (_changed() if args.changed else sorted(REGISTRY))
    if args.changed and not args.refs:
        print(f"# {len(wanted)} row(s) in changed files. "
              f"--all is {len(REGISTRY)} and takes about "
              f"{len(REGISTRY) * 0.1:.0f}s\n")
    chosen: list[str] = []
    inert: list[str] = []
    for ref in wanted:
        p = get(ref)
        if p is None:
            print(f"  {ref}: not declared")
            continue
        if args.cls and p.cls.lower() not in {c.lower() for c in args.cls}:
            continue
        if args.level is not None and p.level != args.level:
            continue
        if args.monsters and not ref.startswith("m"):
            continue
        if p.out_of_combat:
            # Declared inert. A cantrip that lights a torch is not a silent
            # power, it is a power with nothing to say in a fight.
            inert.append(ref)
            continue
        chosen.append(ref)

    refused = _decisions_are_honoured()
    for line in refused:
        print(f"  IGNORED {line}")

    broken, silent, never, known_quiet = [], [], [], []
    for r in _run_all(chosen, args.jobs):
        if r.error:
            broken.append(r)
        elif r.fired == 0:
            never.append(r)
        elif r.silent and r.ref not in KNOWN_SILENT:
            silent.append(r)
        elif r.silent:
            known_quiet.append(r)
        elif args.verbose:
            print(f"  ok      {r.ref:<10} {', '.join(sorted(r.events & DID_SOMETHING))}")

    for r in broken:
        print(f"\n  RAISED  {r.ref}")
        print("      " + r.error.strip().replace("\n", "\n      ")[-900:])
    for r in silent:
        print(f"  SILENT  {r.ref:<10} fired {r.fired}/{TRIES} times and did nothing")
    for r in never:
        print(f"  UNUSED  {r.ref:<10} could not be used on the test board at all")
    for r in known_quiet:
        print(f"  quiet   {r.ref:<10} {KNOWN_SILENT[r.ref]}")

    ok = len(chosen) - len(broken) - len(silent) - len(never)
    print(f"\n  {ok} of {len(chosen)} rows fire and do something")
    if inert:
        print(f"  {len(inert)} declared out of combat, not fired: {', '.join(inert[:6])}"
              + (" ..." if len(inert) > 6 else ""))
    if broken or silent:
        print(f"  {len(broken)} raise, {len(silent)} silent")
    if never:
        print(f"  {len(never)} never usable here -- often a Requirement the board cannot meet")
    if refused:
        print(f"  {len(refused)} negotiable event(s) ignored a refusal")
    # `refused` fails the run. An engine that announces a thing and then
    # does it anyway is a worse fault than any single row being wrong, and
    # it is the one that has been silent four times.
    return 1 if (broken or silent or refused) else 0


if __name__ == "__main__":
    raise SystemExit(main())
