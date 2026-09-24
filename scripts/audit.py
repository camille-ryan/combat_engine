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
        foe_team = Team.PC
    else:
        cls = declared.cls or "fighter"
        caster = chargen.spawn(world, chargen.Character(cls, max(1, declared.level), [ref]), (6, 8))
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
    "DamageApplied", "MoveStart", "MoveEnd", "Moved", "OpportunityWindow",
    "AdjacencyGained", "AdjacencyLost", "TurnStart", "TurnEnd",
}


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
    for attacker, target in ((foes[0], caster), (caster, foes[0])):
        use(world, attacker, basic(attacker), targets=[target], spend=False)
        if _fired(world, ref, cursor):
            return True
    for foe in foes[:2]:
        for sq in sorted(world.reachable_squares(foe, 1)):
            shift(world, foe, sq)
            if _fired(world, ref, cursor):
                return True
    return _fired(world, ref, cursor)


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
                if world.effects.live:
                    out.events.add("ConditionApplied")
                continue
            if not use(world, caster, ref):
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
