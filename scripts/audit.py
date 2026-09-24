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
    Encounter,
    Grid,
    Powers,
    Rng,
    Team,
    World,
    get,
    usable,
    use,
)
from combat_engine.engine.dsl import REGISTRY
from combat_engine.engine.query import alive
from combat_engine.engine.types import ActionType

ROOT = Path(__file__).resolve().parents[1]

#: Events that mean the power did something. A power that emits none of
#: these on any attempt has not been written, whatever the file says.
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
        world.need(caster, Powers).known.append(ref)
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
                cls, max(1, declared.level), [ref, *features], build=_build_for(cls, ref)
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
    caster_health = world.need(caster, Health)
    caster_health.hp = max(1, caster_health.max_hp - 5)

    mark = len(world.bus.log)
    Encounter(world).start()
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
    for victim in (*foes, *_allies_of(world, caster)):
        health = world.get(victim, Health)
        if health is None or health.hp <= 0:
            continue
        world.damage(caster, victim, health.hp + health.max_hp)
        if _fired(world, ref, cursor):
            return True
    return _fired(world, ref, cursor)


def _build_for(cls: str, ref: str) -> str:
    """The build whose gear can actually hold this row.

    A class's builds carry different weapons -- a two-blade ranger owns no
    bow at all -- so a ranged row fielded on the wrong one is refused for a
    reason that has nothing to do with the row. Picks the first build under
    which the row is usable, and falls back to the class default.
    """
    from combat_engine.engine import Bus, Grid, Rng, World

    declared = get(ref)
    if declared is None:
        return ""
    for build in chargen.BUILDS.get(cls, ()):
        probe = World(Grid(8, 8), Rng(1), Bus())
        who = chargen.spawn(
            probe, chargen.Character(cls, max(1, declared.level), [ref], build=build.name),
            (1, 1),
        )
        ok, why = usable(probe, who, declared)
        if ok or "requirement" not in why:
            return build.name
    return ""


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
        if p is None or p.level != 0 or p.action is ActionType.NONE:
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
    triggered = declared is not None and declared.on is not None
    for seed, face in ((s, f) for f in LOADED for s in range(1, TRIES + 1)):
        try:
            world, caster, armed = board(ref, seed)
            world.rng.loaded = face
            cursor = len(world.bus.log)
            if trait:
                out.fired += 1
                out.events |= armed
                if world.effects.live:
                    out.events.add("ConditionApplied")
                continue
            if triggered:
                if not _provoke(world, caster, ref, cursor):
                    continue
                out.fired += 1
                out.events |= {e.kind for e in world.bus.log[cursor:]} - PROVOKE_NOISE
                out.events |= _own_movement(world, ref, cursor, caster)
                if world.effects.live:
                    out.events.add("ConditionApplied")
                continue
            if not _use_with_any_grip(world, caster, ref):
                continue
            out.fired += 1
            out.events |= {e.kind for e in world.bus.log[cursor:]}
            if world.effects.live:
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
    ap.add_argument("--class", dest="cls", help="only this class")
    ap.add_argument("--level", type=int, help="only this level")
    ap.add_argument("--monsters", action="store_true", help="monster abilities only")
    ap.add_argument("--verbose", action="store_true", help="say what each row did")
    ap.add_argument("--changed", action="store_true",
                    help="only rows in content files that differ from HEAD")
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
        if args.cls and p.cls.lower() != args.cls.lower():
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

    broken, silent, never = [], [], []
    for ref in chosen:
        r = audit(ref)
        if r.error:
            broken.append(r)
        elif r.fired == 0:
            never.append(r)
        elif r.silent:
            silent.append(r)
        elif args.verbose:
            print(f"  ok      {ref:<10} {', '.join(sorted(r.events & DID_SOMETHING))}")

    for r in broken:
        print(f"\n  RAISED  {r.ref}")
        print("      " + r.error.strip().replace("\n", "\n      ")[-900:])
    for r in silent:
        print(f"  SILENT  {r.ref:<10} fired {r.fired}/{TRIES} times and did nothing")
    for r in never:
        print(f"  UNUSED  {r.ref:<10} could not be used on the test board at all")

    ok = len(chosen) - len(broken) - len(silent) - len(never)
    print(f"\n  {ok} of {len(chosen)} rows fire and do something")
    if inert:
        print(f"  {len(inert)} declared out of combat, not fired: {', '.join(inert[:6])}"
              + (" ..." if len(inert) > 6 else ""))
    if broken or silent:
        print(f"  {len(broken)} raise, {len(silent)} silent")
    if never:
        print(f"  {len(never)} never usable here -- often a Requirement the board cannot meet")
    return 1 if (broken or silent) else 0


if __name__ == "__main__":
    raise SystemExit(main())
