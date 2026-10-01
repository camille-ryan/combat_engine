"""Fielding an encounter: who is on the board, and where.

The first piece of the Story Engine, which `docs/STORY_ENGINE.md` charters.
Monster selection, party composition and board dressing are its job, and this is
the one place that does them.

**It was two places.** `api/session.py:create` and `scripts/fight.py:build` each
did the same six steps with the same constants -- dress the terrain, four class
names, `chargen.spawn` at `(2, 3 + i*2)`, an opposition picked by level, four
enemies at `(12, 3 + i*2)`, number the repeats -- and `scripts/replay.py` imports
the *scripts* one, so the six pinned fixtures verified the copy players do not
use. #229.

That is not a tidiness complaint. The two copies had already drifted twice:

* `fight.py` passed no `level=` to `terrain.dress` until fa5702d, so every fight
  run from there armed a **level-1 trap at every level** while the API path
  passed it properly;
* `api/session.py`'s own monster pick returned `loader.pick(level)` raw, with no
  role ordering -- so the path a player actually plays fielded the all-brute
  alphabetical line-up that `fight.py`'s `_one_of_each` exists to prevent. That
  one is fixed by this file existing.

So the seam is cut here rather than deduplicated in place, which is what the
charter asks for and what #72 needs: a session that runs several encounters wants
exactly one thing that knows how to field one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from combat_engine import chargen
from combat_engine.content import loader, terrain
from combat_engine.engine import Bus, Grid, Ident, Rng, Team, World
from combat_engine.engine.monster_math import PRESETS as MATHS
from combat_engine.engine.scaling import PRESETS

#: The four a fight is fielded against unless somebody names others. One list,
#: because it was written out twice and a change to either did nothing to the
#: other.
PARTY = ["fighter", "cleric", "rogue", "wizard"]

#: The order roles are drawn in. A soldier and a brute in front, something
#: shooting from the back, a skirmisher moving. What a published encounter looks
#: like -- and taking the first four by id instead gave an all-brute line-up with
#: half again the party's hit points.
ROLE_ORDER = ["soldier", "brute", "artillery", "skirmisher", "controller", "lurker"]

#: Where the two sides stand. Twelve squares apart, two rows of four.
PARTY_AT = (2, 3)
ENEMY_AT = (12, 3)
SPACING = 2
SIDE = 4


@dataclass
class Fielded:
    """A board with both sides on it, and what it took to get there."""

    world: World
    #: The monster refs actually spawned, in order. The transcript records these.
    enemies: list[str] = field(default_factory=list)
    #: The level the opposition came from. Lower than asked for when content at
    #: the asked-for level is not written yet, which the caller may want to say.
    found_at: int = 0


def mixed(pool: list[str]) -> list[str]:
    """Reorder a pool so consecutive picks come from different roles."""
    from combat_engine.etl.build import game

    db = game()
    by_role: dict[str, list[str]] = {}
    for ref in pool:
        row = db.execute("SELECT role FROM monster WHERE ref = ?", (ref,)).fetchone()
        by_role.setdefault((row["role"] if row else "") or "", []).append(ref)
    out: list[str] = []
    while any(by_role.values()):
        for role in [*ROLE_ORDER, *sorted(set(by_role) - set(ROLE_ORDER))]:
            if by_role.get(role):
                out.append(by_role[role].pop(0))
    return out


def opposition(level: int) -> tuple[list[str], int]:
    """Monsters to field, and the level they came from.

    Falls back down the levels while content is thin: a fight against nothing is
    not useful, so rather than refuse, this drops to whatever level has been
    written and reports which. The caller decides whether to mention it.
    """
    for candidate in range(min(max(level, 1), 13), 0, -1):
        pool = loader.pick(candidate)
        if pool:
            return mixed(pool), candidate
    return [], level


def number_repeats(world: World) -> None:
    """Number the repeats, so two of the same monster are tellable apart."""
    seen: dict[str, int] = {}
    for _eid, ident in world.each(Ident):
        seen[ident.ref] = seen.get(ident.ref, 0) + 1
        if seen[ident.ref] > 1 or ident.ref.startswith("m"):
            ident.tag = str(seen[ident.ref])


def field_encounter(
    seed: int,
    level: int = 1,
    *,
    scaling: str = "full",
    math: str = "printed",
    pcs: list[str] | None = None,
    enemies: list[str] | None = None,
    feats: dict[str, list[str]] | None = None,
) -> Fielded:
    """Build a board and put both sides on it.

    `feats` pins what each class has taken, by class name, and exists for
    `replay.py`: a character's feats are otherwise dealt from the pool of
    *declared* ones, so every content wave changed the party and every fixture
    diverged. Pinning them makes a fixture a test of the engine rather than of
    the corpus's size.

    `enemies` names the opposition outright, for a caller that is not asking for
    a level-appropriate band.
    """
    world = World(Grid(16, 12), Rng(seed), Bus())
    world.scaling = PRESETS.get(scaling, PRESETS["full"])
    # `"printed"` is the engine's own default (`AS_PRINTED`), so the caller that
    # never set this keeps what it had.
    world.monster_math = MATHS.get(math, MATHS["printed"])

    # Something to take cover behind and something to wade through. Without it
    # cover, concealment, hiding and difficult terrain are all modelled and none
    # of them ever comes up.
    #
    # **`level=` matters**: `dress` takes it to decide what a trap on this board
    # is worth, and one of the two copies this replaces did not pass it.
    terrain.dress(world, seed, level=level)

    for i, name in enumerate(pcs or PARTY):
        key = name.strip().lower()
        chargen.spawn(
            world,
            chargen.Character(key, level, feats=list((feats or {}).get(key, []))),
            (PARTY_AT[0], PARTY_AT[1] + i * SPACING),
        )

    found_at = level
    if enemies:
        pool = list(enemies)
    else:
        pool, found_at = opposition(level)
    if not pool:
        return Fielded(world=world, enemies=[], found_at=found_at)

    fielded = [pool[i % len(pool)] for i in range(SIDE)]
    for i, ref in enumerate(fielded):
        loader.spawn(
            world, ref, (ENEMY_AT[0], ENEMY_AT[1] + i * SPACING), team=Team.ENEMY
        )

    number_repeats(world)
    return Fielded(world=world, enemies=fielded, found_at=found_at)
