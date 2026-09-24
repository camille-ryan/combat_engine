"""Putting a monster on the board.

Its numbers come out of `game.db` by id and are never hand-written -- that is
the whole division of labour. Its *behaviour* is whichever of its abilities
somebody has written as a function; anything not yet written simply is not in
its power list, so the monster fights with what it has and the gap shows up
in `scripts/coverage.py` rather than in a broken fight.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from combat_engine.engine import (
    AC,
    FORT,
    REF,
    WILL,
    Ability,
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
        Health(max_hp=max(1, row["hp"]), surges=0),
        Movement(speed=row["speed"], modes=modes),
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


def pick(level: int, *, role: str | None = None, limit: int = 20) -> list[str]:
    """Monsters at a level whose abilities are all written.

    A monster is only offered once every ability on its stat block has a
    function, so a fight never quietly leaves out the thing that makes a
    monster interesting.
    """
    db = game()
    sql = "SELECT ref FROM monster WHERE level = ? AND minion = 0"
    params: list = [level]
    if role:
        sql += " AND role = ?"
        params.append(role)
    out = []
    for row in db.execute(sql + " ORDER BY ref", params):
        if not load(row["ref"]).missing:
            out.append(row["ref"])
        if len(out) >= limit:
            break
    return out
