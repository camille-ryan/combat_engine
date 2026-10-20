"""What a published adventure looks like once it is a thing the engine can read.

A module is a **graph of scenes**. `story/__init__.py` can field one fight; this
is what says there are twenty of them, what sort of thing each one is, and which
one comes next. #789.

## It describes the scene, never the stat block

Every field here is edition-neutral on purpose, because the ask is to drop in
modules from other editions and have the engine pick appropriate 4e challenges.
So a combat scene says *four of something goblin-ish, skirmishers, a standard
fight* -- a count, some words, a role and a difficulty band. It does not say
`m1433`, and it does not say a hit-dice count or a challenge rating either.
Turning a published difficulty into a band is a judgement made **once, by
whoever converts the module**, because that reader can see the page; a
conversion table living in here would be wrong for some editions, silently, and
would go stale as more were added.

What reads these words is `story/cast_list.py`, and it tries the module's own
creature name against the localisation first -- for a 4e module that answers
almost everything (39 of 39 measured, #790) and the words are never consulted.
They are what the fallback has to work from when the name resolves to nothing,
which is every module from every other edition.

## JSON, hand-validated

A module is **user-supplied data**, dropped into a git-ignored directory by
somebody who owns the adventure. It is not code and must never be `exec`'d, so
it is JSON rather than a Python file -- which is a real departure from the rest
of the tree, where every row is hand-written Python, and the reason is that no
other data in this repository arrives from outside it.

Validation is hand-written for the same reason the rest of the project is: a
schema library would turn a wrong word into a stack trace about types, and what
an author needs is *which of the closed vocabularies they missed*. Every problem
in the file is collected and reported at once, because a converter fixing twenty
scenes should not have to run the validator twenty times.

## The vocabularies are closed, and that is the point

`terrain`, `primary`/`secondary`, `role`, `rank`, `kind` and `difficulty` are
all checked against sets the engine already owns. The precedent is
`Cast.TERRAIN_WORDS`, which became a closed set after #539 found seven gates
across six files asking for words no board would ever carry -- invisible,
because every gate was False anyway. A module naming `wet` instead of `aquatic`
would field a fight with no terrain and look exactly like one that worked.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from combat_engine.engine.cast import TERRAIN_WORDS
from combat_engine.engine.skills import SKILLS

#: What sort of thing a scene is. Four, and they are the four the module in
#: `modules/` is made of -- its outline has a heading for each.
#:
#: `rest` is a scene rather than a property of the edge between two, because a
#: module says where the party may rest and that is a decision with a position
#: in the story. `turns.short_rest` and `Party.rest` are what it runs.
KINDS = ("roleplay", "skill_challenge", "combat", "rest")

#: How hard a fight is, as a multiplier on `story.budget(level)` -- which is
#: itself one standard monster per character, read off the database rather than
#: from a table here.
#:
#: Four bands rather than a number, because that is what a published adventure
#: prints and what a converter can judge from the page. A module that states an
#: XP figure outright can give `xp` instead and skip the band entirely.
DIFFICULTY = {"easy": 0.75, "standard": 1.0, "hard": 1.5, "deadly": 2.0}

#: The printed ranks. `story.WORTH` prices them.
RANKS = ("standard", "elite", "solo", "minion")

#: The printed roles, as the `monster` table spells them. `minion` appears in
#: that column too but is a rank here, which is the same split `loader.pick`
#: makes with its separate `rank=` and `minion=` arguments.
ROLES = ("soldier", "brute", "artillery", "skirmisher", "controller", "lurker")

#: How many successes each complexity needs before three failures. The printed
#: table, and the reason `challenge.py` does not hold its own copy.
COMPLEXITY = {1: 4, 2: 6, 3: 8, 4: 10, 5: 12}


class ModuleError(Exception):
    """A module file that cannot be played, with every reason at once."""

    def __init__(self, path: Path, problems: list[str]) -> None:
        self.path = path
        self.problems = problems
        lines = "\n".join(f"  - {p}" for p in problems)
        super().__init__(f"{path}: {len(problems)} problem(s)\n{lines}")


@dataclass(frozen=True)
class FoeSpec:
    """One line of a scene's opposition: *four of something, roughly like this*.

    `name` is the module's own word for the creature and is the **only** field
    that usually matters -- `cast_list` looks it up in the localisation and for
    a 4e module it resolves. Everything below it is what the fallback works
    from, and what a module from another edition will be carrying instead.
    """

    count: int = 1
    #: What the module calls it. Lives only in the git-ignored module file;
    #: never written to `game.db`, never put in a spec.
    name: str = ""
    #: Origin, kind and keyword words -- matched against the creature's own
    #: `keywords`, `kind` and `origin` columns when the name does not resolve.
    words: tuple[str, ...] = ()
    role: str = ""
    rank: str = "standard"


@dataclass(frozen=True)
class Scene:
    """One beat of the adventure, and where it can lead.

    One dataclass for all four kinds rather than four classes, because the
    graph wants a single node type and the fields a kind does not use are
    simply empty. `kind` is what decides which of them are read, and `_check`
    is what refuses a scene that fills in the wrong ones -- a `rest` scene with
    a foe list is an authoring mistake and should not play as an empty fight.
    """

    id: str
    kind: str
    name: str = ""
    #: The module's own prose for this scene: what the DM would read out, or
    #: paraphrase. Shown as-is in `--no-dm`; handed to the model as context
    #: otherwise. Git-ignored either way.
    brief: str = ""
    #: Which chapter and session of the published adventure this came from.
    #: Carried for reporting only -- the graph is what plays.
    chapter: str = ""
    #: Scene ids this one may lead to. The first is the default. An empty tuple
    #: ends the module.
    exits: tuple[str, ...] = ()

    # -- combat ------------------------------------------------------------
    difficulty: str = "standard"
    #: Overrides `difficulty` when the module prints a real XP figure.
    xp: int = 0
    terrain: tuple[str, ...] = ()
    foes: tuple[FoeSpec, ...] = ()
    tactics: str = ""

    # -- skill challenge ----------------------------------------------------
    complexity: int = 0
    #: The level the DCs are read at. Defaults to the party's when 0.
    level: int = 0
    primary: tuple[str, ...] = ()
    secondary: tuple[str, ...] = ()
    #: Where success and failure lead. Both fall back to `exits` when empty,
    #: so a challenge that only gates flavour needs neither.
    on_success: str = ""
    on_failure: str = ""

    # -- rest ---------------------------------------------------------------
    extended: bool = False

    @property
    def share(self) -> float:
        """What fraction of a standard encounter's budget this fight is worth."""
        return DIFFICULTY.get(self.difficulty, 1.0)

    @property
    def needs(self) -> int:
        """Successes this challenge wants before three failures."""
        return COMPLEXITY.get(self.complexity, 0)


@dataclass(frozen=True)
class Module:
    """A whole adventure: every scene, and which one opens it."""

    id: str
    scenes: dict[str, Scene] = field(default_factory=dict)
    start: str = ""
    party_level: int = 1
    party_size: int = 4
    #: Recorded so a reader knows what was converted. **Nothing branches on
    #: it** -- see the module docstring. It is provenance, not a switch.
    edition: str = ""
    #: Campaign resources the adventure names, and their starting values --
    #: a reputation score, a body count, a door left unlocked. The module in
    #: `modules/` counts one of these and spends it on rewards.
    flags: dict[str, int] = field(default_factory=dict)

    def scene(self, scene_id: str) -> Scene:
        return self.scenes[scene_id]

    def next_of(self, scene: Scene, chose: str = "") -> str:
        """Where play goes from here. `""` ends the module.

        A choice is honoured only if the scene actually lists it, which is the
        same refusal `dm.py`'s `advance` tool makes -- a campaign that can jump
        anywhere is not a campaign.
        """
        if chose and chose in scene.exits:
            return chose
        return scene.exits[0] if scene.exits else ""


def _as_foe(raw: Any, where: str, problems: list[str]) -> FoeSpec:
    if not isinstance(raw, dict):
        problems.append(f"{where}: a foe must be an object, got {type(raw).__name__}")
        return FoeSpec()
    count = raw.get("count", 1)
    if not isinstance(count, int) or count < 1:
        problems.append(f"{where}: count must be a positive integer, got {count!r}")
        count = 1
    role = str(raw.get("role", "")).strip().lower()
    if role and role not in ROLES:
        problems.append(f"{where}: role {role!r} is not one of {', '.join(ROLES)}")
    rank = str(raw.get("rank", "standard")).strip().lower()
    if rank not in RANKS:
        problems.append(f"{where}: rank {rank!r} is not one of {', '.join(RANKS)}")
        rank = "standard"
    words = tuple(str(w).strip().lower() for w in raw.get("words", ()) if str(w).strip())
    return FoeSpec(
        count=count, name=str(raw.get("name", "")).strip(),
        words=words, role=role, rank=rank,
    )


def _as_scene(raw: Any, index: int, problems: list[str]) -> Scene | None:
    where = f"scene {index}"
    if not isinstance(raw, dict):
        problems.append(f"{where}: must be an object, got {type(raw).__name__}")
        return None
    scene_id = str(raw.get("id", "")).strip()
    if not scene_id:
        problems.append(f"{where}: needs an id")
        return None
    where = f"scene {scene_id!r}"

    kind = str(raw.get("kind", "")).strip().lower()
    if kind not in KINDS:
        problems.append(f"{where}: kind {kind!r} is not one of {', '.join(KINDS)}")
        return None

    terrain = tuple(str(w).strip().lower() for w in raw.get("terrain", ()) if str(w).strip())
    for word in terrain:
        if word not in TERRAIN_WORDS:
            problems.append(
                f"{where}: terrain {word!r} is not a terrain word. "
                f"Known: {', '.join(sorted(TERRAIN_WORDS))}"
            )

    difficulty = str(raw.get("difficulty", "standard")).strip().lower()
    if difficulty not in DIFFICULTY:
        problems.append(
            f"{where}: difficulty {difficulty!r} is not one of "
            f"{', '.join(sorted(DIFFICULTY))}"
        )
        difficulty = "standard"

    primary = tuple(str(s).strip().lower() for s in raw.get("primary", ()) if str(s).strip())
    secondary = tuple(
        str(s).strip().lower() for s in raw.get("secondary", ()) if str(s).strip()
    )
    for skill in (*primary, *secondary):
        if skill not in SKILLS:
            problems.append(
                f"{where}: {skill!r} is not a skill. Known: {', '.join(sorted(SKILLS))}"
            )

    complexity = raw.get("complexity", 0)
    if not isinstance(complexity, int) or complexity < 0:
        problems.append(f"{where}: complexity must be an integer, got {complexity!r}")
        complexity = 0
    if kind == "skill_challenge" and complexity not in COMPLEXITY:
        problems.append(
            f"{where}: a skill challenge needs a complexity in "
            f"{min(COMPLEXITY)}-{max(COMPLEXITY)}, got {complexity}"
        )
    if kind == "skill_challenge" and not primary:
        problems.append(f"{where}: a skill challenge needs at least one primary skill")

    foes = tuple(
        _as_foe(f, where, problems) for f in raw.get("foes", ())
    )
    if kind == "combat" and not foes:
        problems.append(f"{where}: a combat scene needs at least one foe line")

    # **A field the kind does not use is an authoring mistake, not a default.**
    # A rest scene carrying a foe list plays as a rest and silently drops the
    # fight; a roleplay scene carrying a complexity never counts a success.
    # Both read exactly like a scene that works, which is why they are refused.
    unused = {
        "roleplay": ("foes", "terrain", "complexity", "primary", "secondary"),
        "skill_challenge": ("foes", "terrain"),
        "combat": ("complexity", "primary", "secondary"),
        "rest": ("foes", "terrain", "complexity", "primary", "secondary"),
    }[kind]
    for name in unused:
        if raw.get(name):
            problems.append(f"{where}: a {kind} scene must not carry {name!r}")

    return Scene(
        id=scene_id, kind=kind,
        name=str(raw.get("name", "")).strip(),
        brief=str(raw.get("brief", "")),
        chapter=str(raw.get("chapter", "")).strip(),
        exits=tuple(str(e).strip() for e in raw.get("exits", ()) if str(e).strip()),
        difficulty=difficulty,
        xp=int(raw.get("xp", 0) or 0),
        terrain=terrain,
        foes=foes,
        tactics=str(raw.get("tactics", "")),
        complexity=complexity,
        level=int(raw.get("level", 0) or 0),
        primary=primary,
        secondary=secondary,
        on_success=str(raw.get("on_success", "")).strip(),
        on_failure=str(raw.get("on_failure", "")).strip(),
        extended=bool(raw.get("extended", False)),
    )


def parse(raw: dict, path: Path) -> Module:
    """A `Module` from already-decoded JSON. Raises `ModuleError`."""
    problems: list[str] = []
    module_id = str(raw.get("id", "")).strip()
    if not module_id:
        problems.append("the module needs an id")

    scenes: dict[str, Scene] = {}
    order: list[str] = []
    for i, raw_scene in enumerate(raw.get("scenes", ())):
        scene = _as_scene(raw_scene, i, problems)
        if scene is None:
            continue
        if scene.id in scenes:
            problems.append(f"scene {scene.id!r}: declared twice")
            continue
        scenes[scene.id] = scene
        order.append(scene.id)

    if not scenes:
        problems.append("the module has no scenes")

    start = str(raw.get("start", "")).strip() or (order[0] if order else "")
    if start and start not in scenes:
        problems.append(f"start {start!r} is not a scene in this module")

    # **Every edge resolves, and that is checked here rather than at play
    # time.** A dangling exit is a campaign that stops dead three hours in,
    # which is the worst possible moment to discover a typo.
    for scene in scenes.values():
        for exit_id in (*scene.exits, scene.on_success, scene.on_failure):
            if exit_id and exit_id not in scenes:
                problems.append(f"scene {scene.id!r}: exit {exit_id!r} is not a scene")

    # Unreachable scenes are reported, not refused: a converter working through
    # a long module has half a graph for a while, and `--validate` is the tool
    # that should tell them which half.
    if start in scenes:
        seen, stack = {start}, [start]
        while stack:
            here = scenes[stack.pop()]
            for exit_id in (*here.exits, here.on_success, here.on_failure):
                if exit_id in scenes and exit_id not in seen:
                    seen.add(exit_id)
                    stack.append(exit_id)
        for orphan in order:
            if orphan not in seen:
                problems.append(f"scene {orphan!r}: nothing leads to it")

    level = raw.get("party_level", 1)
    if not isinstance(level, int) or not 1 <= level <= 30:
        problems.append(f"party_level must be 1-30, got {level!r}")
        level = 1

    flags = {
        str(k): int(v) for k, v in (raw.get("flags") or {}).items()
        if isinstance(v, int)
    }

    if problems:
        raise ModuleError(path, problems)
    return Module(
        id=module_id, scenes=scenes, start=start,
        party_level=level,
        party_size=int(raw.get("party_size", 4) or 4),
        edition=str(raw.get("edition", "")).strip(),
        flags=flags,
    )


def load(path: str | Path) -> Module:
    """Read and validate a module file."""
    path = Path(path)
    if not path.exists():
        raise SystemExit(f"{path} is missing.")
    try:
        raw = json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise ModuleError(path, [f"not valid JSON: {exc}"]) from exc
    if not isinstance(raw, dict):
        raise ModuleError(path, ["the top level must be an object"])
    return parse(raw, path)
