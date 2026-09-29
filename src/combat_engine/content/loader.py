"""Putting a monster on the board.

Its numbers come out of `game.db` by id and are never hand-written -- that is
the whole division of labour. Its *behaviour* is whichever of its abilities
somebody has written as a function; anything not yet written simply is not in
its power list, so the monster fights with what it has and the gap shows up
in `scripts/coverage.py` rather than in a broken fight.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from combat_engine.engine import (
    AC,
    FORT,
    REF,
    WILL,
    Ability,
    ActionPoints,
    Budget,
    Conditions,
    Defences,
    Defenses,
    Gear,
    Health,
    Ident,
    Initiative,
    Mods,
    Movement,
    Position,
    Powers,
    Side,
    Size,
    Stats,
    Team,
    World,
)
from combat_engine.engine.dsl import REGISTRY
from combat_engine.engine.movement import place
from combat_engine.engine.types import ActionType, DamageType
from combat_engine.etl.build import game

SIZES = {
    "tiny": Size.TINY, "small": Size.SMALL, "medium": Size.MEDIUM,
    "large": Size.LARGE, "huge": Size.HUGE, "gargantuan": Size.GARGANTUAN,
}  # fmt: skip


@dataclass
class Stock:
    """One monster's numbers, as read from the database."""

    ref: str
    row: dict
    abilities: list[dict]

    @property
    def level(self) -> int:
        return self.row["level"]

    @property
    def role(self) -> str:
        return self.row["role"]

    @property
    def book(self) -> str:
        """Which Monster Manual printed it, so its maths can be converted."""
        return self.row["book"] or ""

    @property
    def rank(self) -> str:
        return self.row["rank"] or "standard"

    @property
    def declared(self) -> list[str]:
        return [a["ref"] for a in self.abilities if a["ref"] in REGISTRY]

    @property
    def missing(self) -> list[str]:
        return [a["ref"] for a in self.abilities if a["ref"] not in REGISTRY]


def load(ref: str) -> Stock:
    db = game()
    row = db.execute("SELECT * FROM monster WHERE ref = ?", (ref,)).fetchone()
    if row is None:
        raise KeyError(f"no monster {ref}")
    abilities = db.execute(
        "SELECT * FROM monster_power WHERE monster_ref = ? ORDER BY idx", (ref,)
    ).fetchall()
    return Stock(ref=ref, row=dict(row), abilities=[dict(a) for a in abilities])


def spawn(world: World, ref: str, square: tuple[int, int], *, team: Team = Team.ENEMY) -> int:
    stock = load(ref)
    row = stock.row
    scores = {Ability(k): v for k, v in json.loads(row["scores"] or "{}").items()}
    modes = json.loads(row["modes"] or "{}")
    resist = {DamageType(k): v for k, v in json.loads(row["resist"] or "{}").items()
              if k in DamageType._value2member_map_}
    vulnerable = {DamageType(k): v for k, v in json.loads(row["vulnerable"] or "{}").items()
                  if k in DamageType._value2member_map_}
    immune = {DamageType(k) for k in json.loads(row["immune"] or "[]")
              if k in DamageType._value2member_map_}

    known = stock.declared
    printed = world.scaling.printed_monster(row["level"])
    eid = world.spawn(
        Ident(ref=ref, book=row["book"] or ""),
        Position(square=square, size=SIZES.get(row["size"], Size.MEDIUM)),
        Side(team=team),
        Stats(level=row["level"], scores=scores),
        # A stat block prints totals with the level already in them, so the
        # level term comes back out here and `scaling` decides how much of it
        # to put back. See `engine/scaling.py`.
        Defenses(
            values={
                AC: row["ac"] - printed,
                FORT: row["fort"] - printed,
                REF: row["ref_def"] - printed,
                WILL: row["will"] - printed,
            },
            scale="monster",
        ),
        # One surge per tier: heroic 1, paragon 2, epic 3. The compendium
        # records none, and zero made every printed leader line of the form
        # "an adjacent ally can spend a healing surge" inert between
        # monsters -- the row fired and did nothing, which is what a wrong
        # row looks like.
        Health(
            max_hp=max(1, row["hp"]),
            surges=1 + max(0, row["level"] - 1) // 10,
            dies_at_zero=True,
        ),
        Movement(speed=row["speed"], modes=modes),
        # **Action points, by rank.** An elite has one a fight and a solo
        # two; an ordinary monster has none at all, which is why this is
        # only added for the two that do. A solo may still spend only one
        # in a round, which `_action_points` enforces off `spent_round`.
        *(
            [ActionPoints(points=2 if row["solo"] else 1,
                          limit=2 if row["solo"] else 1)]
            if (row["elite"] or row["solo"])
            else []
        ),
        Defences(resist=resist, vulnerable=vulnerable, immune=immune),
        Initiative(bonus=row["initiative"] - printed, scale="monster"),
        Conditions(),
        Mods(),
        Budget(),
        Powers(known=known, basic=_basic(stock)),
        Gear(),
    )
    place(world, eid, square)
    return eid


def _basic(stock: Stock) -> str:
    """Which of a monster's abilities is its basic attack.

    An opportunity attack is a melee basic attack, so a monster with nothing
    declared has to fall back on the engine's own -- which uses Strength and
    a notional weapon, and will be wrong for an artillery monster. Better
    wrong than silent: the alternative is a monster that never once responds
    to somebody walking away from it, and nothing in a log says so.
    """
    from combat_engine.engine.basic import MELEE

    for a in stock.abilities:
        if a["ref"] in REGISTRY and a["section"] == "standard":
            declared = REGISTRY[a["ref"]]
            # It has to *be* an attack. A stat block whose only standard
            # melee row is an Effect line got that row named as its basic,
            # which dropped the engine's own melee basic out of `Powers.all`
            # -- so the creature had no attack at all, not even an
            # opportunity attack, which is the exact silence this exists to
            # prevent. And a body calling `c.basic()` called itself.
            if (
                declared.action is ActionType.STANDARD
                and declared.reach.kind == "melee"
                and declared.attack is not None
            ):
                return a["ref"]
    return MELEE


# -- a beast companion, whose numbers are a formula rather than a total ------


#: The printed stat block of one beast companion category, parsed.
#:
#: A companion's page is written as a *formula* -- "AC 14 + level", "Hit
#: Points: 14 + 8 per level", "Attack Bonus: Level + 4" -- where a monster's
#: is a finished total. That is the only real difference, and it is why this
#: cannot go through `load`/`spawn`: there is no level on the page to take
#: back out, so the constant is already the level-free number the engine
#: wants.
@dataclass
class Block:
    ref: str
    scores: dict[Ability, int]
    size: Size
    speed: int
    modes: dict[str, int]
    defences: dict[object, int]
    hp_base: int
    hp_per_level: int
    attack: int
    damage: str
    ability: Ability


_SCORES = (
    ("Strength", Ability.STR), ("Constitution", Ability.CON),
    ("Dexterity", Ability.DEX), ("Intelligence", Ability.INT),
    ("Wisdom", Ability.WIS), ("Charisma", Ability.CHA),
)  # fmt: skip
_DEFENCES = (("AC", AC), ("Fortitude", FORT), ("Reflex", REF), ("Will", WILL))


def companion(ref: str) -> Block:
    """One companion category's numbers, read off its printed block."""
    db = game()
    row = db.execute(
        "SELECT spec FROM companion WHERE ref = ? AND kind = 'companion'", (ref,)
    ).fetchone()
    if row is None:
        raise KeyError(f"no companion {ref}")
    spec = row["spec"]

    def one(pattern: str, default: int = 0) -> int:
        found = re.search(pattern, spec)
        return int(found.group(1)) if found else default

    hp = re.search(r"Hit Points: (\d+) \+ (\d+) per level", spec)
    die = re.search(r"Damage: (\d+d\d+)", spec)
    # Which ability its own damage line adds. Three of the eight categories
    # are Dexterity and the rest Strength, and taking Strength for all of
    # them is a point or two of damage quietly missing on the fast ones.
    mod = re.search(r"\+ (Strength|Dexterity|Constitution|Wisdom) modifier damage", spec)
    size = re.search(r"Size: (\w+)", spec)
    return Block(
        ref=ref,
        scores={a: one(word + r" (\d+)", 10) for word, a in _SCORES},
        size=SIZES.get((size.group(1) if size else "medium").lower(), Size.MEDIUM),
        speed=one(r"Speed: (\d+) squares", 6),
        modes={
            k.lower(): int(v)
            for k, v in re.findall(r"(fly|swim|climb|burrow) (\d+)", spec, re.I)
        },
        defences={d: one(word + r" (\d+) \+ level", 10) for word, d in _DEFENCES},
        hp_base=int(hp.group(1)) if hp else 10,
        hp_per_level=int(hp.group(2)) if hp else 8,
        attack=one(r"Attack Bonus: Level \+ (\d+)", 4),
        damage=die.group(1) if die else "1d8",
        ability=Ability.DEX if mod and mod.group(1) == "Dexterity" else Ability.STR,
    )


def spawn_companion(
    world: World,
    ref: str,
    square: tuple[int, int],
    *,
    team: Team = Team.PC,
    level: int = 1,
) -> int:
    """Put a beast companion on the board with the numbers off its page.

    Its defences are stored the way a monster's are -- `scale="monster"`, so
    `Scaling` decides what the level term is worth -- which needs the
    constant the printed formula would give at level 1. "AC 14 + level" is
    15 at level 1 and `printed_monster(1)` is 0, so the stored number is the
    constant plus one.

    The attack line is the one thing the engine cannot take straight. A
    character's bonus is built up from parts (`_attack_bonus`) and this page
    prints a finished total, so the difference is laid on as a standing
    untyped modifier: the beast then rolls "Level + 4" and nothing else has
    to know the block exists.
    """
    from combat_engine.engine.basic import BEAST
    from combat_engine.engine.components import Mod

    block = companion(ref)
    hp = max(1, block.hp_base + block.hp_per_level * level)
    printed = world.scaling.trim(level + block.attack, level)
    built = world.scaling.pc(level) + (block.scores[block.ability] - 10) // 2
    eid = world.spawn(
        Ident(ref=ref),
        Position(square=square, size=block.size),
        Side(team=team),
        Stats(level=level, scores=dict(block.scores)),
        Defenses(values={d: v + 1 for d, v in block.defences.items()}, scale="monster"),
        Health(max_hp=hp, surges=1, dies_at_zero=True),
        Movement(speed=block.speed, modes=dict(block.modes)),
        Defences(),
        Conditions(),
        Mods(items=[Mod(what="attack", value=printed - built, label=ref)]),
        Budget(),
        Powers(known=[], basic=BEAST),
    )
    place(world, eid, square)
    return eid


#: Monsters nothing may field, and why. **Checked against the compendium
#: before being listed here**, because the importer reading a block wrongly
#: and the block itself being odd are different faults with different fixes.
#:
#: `m3561` is deliberately *not* here. It is a level 4 minion with AC 32 and
#: attack +13, which reads as an extraction fault and is not one -- the page
#: prints exactly those numbers. An outlier in the source is somebody else's
#: decision and this engine's job is to reproduce it.
UNUSABLE: dict[str, str] = {
    # Every number zero -- AC, all three non-AC defences, and hit points --
    # with no role. Not an empty row: four of its abilities parsed, so the
    # block yielded its powers and nothing for its stat line. A creature with
    # AC 0 and 0 hit points is not a fight.
    "m5452": "stat line parsed to all zeroes, including hit points",
    # Level 4 minion carrying AC 30 and non-AC defences of 26-28, which is
    # paragon maths twelve above where level 4 sits. Unlike `m3561` the page
    # does not print these, so something read the wrong block.
    "m3640": "defences are twelve above its level and the page does not say so",
}


def usable(ref: str) -> bool:
    """Is this monster fit to put on a board? See `UNUSABLE`."""
    return ref not in UNUSABLE


def pick(level: int, *, role: str | None = None, limit: int = 20) -> list[str]:
    """Monsters at a level whose abilities are all written.

    A monster is only offered once every ability on its stat block has a
    function, so a fight never quietly leaves out the thing that makes a
    monster interesting -- and never if it is in `UNUSABLE`, which is the
    stronger statement: those are not unfinished, they are wrong.

    Conjurations are left out too, and for a third reason again: they are
    perfectly good rows and simply are not encounters.
    """
    db = game()
    # **Not a conjuration.** The book gives some creatures no combat role at
    # all -- what an item conjures, what a ritual calls up, what somebody
    # rides -- and those are not an encounter. 159 of them, nearly all out of
    # `Adventurer's Vault`, and they were eligible until now.
    sql = ("SELECT ref FROM monster "
           "WHERE level = ? AND minion = 0 AND conjuration = 0")
    params: list = [level]
    if role:
        sql += " AND role = ?"
        params.append(role)
    out = []
    for row in db.execute(sql + " ORDER BY ref", params):
        if usable(row["ref"]) and not load(row["ref"]).missing:
            out.append(row["ref"])
        if len(out) >= limit:
            break
    return out
