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


# -- what survives a fight --------------------------------------------------
#
# **A `World` does not outlive a fight and is not going to.** #72 asked for one
# that does, and the answer taken there was the other one: a durable *party*,
# handed to a fresh board each time. The reason is concrete rather than
# aesthetic -- a `World` cannot be copied, because bus subscriptions close over
# it, which is why `expect.py` builds its scratch board from `components_of` and
# `deepcopy` instead. A long-lived world therefore could not be snapshotted,
# forked for a what-if, or replayed from a mid-day point, and a story engine
# wants all three. It also keeps every existing caller building a world per
# fight, so this is additive rather than a lifetime change touching every
# fixture.
#
# What a day consists of is not guessed. `turns.extended_rest` is the inverse
# operation and already says it: whatever a full rest puts back is, by
# definition, what a day wears down.


@dataclass
class Sheet:
    """One character between fights.

    Enough to rebuild the character, plus the wear. `Character` is rebuilt from
    `cls`, `level`, `build`, `race` and `feats` rather than stored, because a
    `Character` is a request and this is a record of what happened to one.
    """

    cls: str
    level: int = 1
    build: str = ""
    race: str = ""
    feats: list[str] = field(default_factory=list)

    #: Hit points, and `None` for "however many a fresh one has". Set from the
    #: board after every fight.
    hp: int | None = None
    #: What a fresh one has, recorded so a rest can work out what a surge is
    #: worth and whether this character is past saving. Not a request: it is
    #: read off the board, because the number is the chassis's to decide.
    max_hp: int = 0
    #: Healing surges left. `None` is the full pool.
    surges: int | None = None
    #: Unspent action points. One at the start of a day; a milestone grants
    #: more, and `extended_rest` does not carry them over.
    action_points: int = 1
    #: Failed death saves. Three is dead, and a short rest clears them.
    failures: int = 0
    #: The hand, pinned. Empty means "deal me one", the same as `Character`.
    #:
    #: **A durable party must pin this or it is not durable.** `chargen.spawn`
    #: deals powers and feats off `world.rng.seed`, so the same sheet fielded
    #: against a second fight -- a new seed, as every caller uses -- was built
    #: into a *different character*, and the spends carried from the first fight
    #: were then dropped for naming rows it no longer held. Measured: a party
    #: walked out of its second fight with nine powers spent having walked in
    #: with eleven. `Party.of` deals once, off the party's own seed, and the
    #: character is the same one every fight after that.
    powers: list[str] = field(default_factory=list)

    #: Every power spent and not yet got back, by ref. **All of them**, not
    #: only the dailies: a party that walks into a second fight without resting
    #: has its encounter powers still spent, and that is the whole point of
    #: the distinction. `rest` is what sorts them.
    spent: dict[str, int] = field(default_factory=dict)
    #: "A number of times per day", counted here because there is nowhere else.
    #: `Powers.used` is per encounter and `extended_rest` clears it, so the
    #: paladin's Wisdom-modifier-times-per-day heal had nothing to count
    #: against and those rows are written as once per fight. This is the
    #: counter they wanted; the rows still have to read it.
    per_day: dict[str, int] = field(default_factory=dict)

    def per_day_left(self, ref: str, limit: int) -> int:
        """How many uses of that row are left today."""
        return max(0, limit - self.per_day.get(ref, 0))

    def spend_per_day(self, ref: str, limit: int) -> bool:
        """Spend one of a row's daily allowance. False when there is none left.

        **A counter with a reader, which is the point.** The field alone would be
        this component's commonest bug wearing a new coat -- a number nothing
        consults -- and #72's second half asks for "a number of times per day"
        to be countable, not merely stored. The rows that want it are written as
        once per fight today and say so in their docstrings; this is what they
        read when somebody comes back to them.

        Not `Powers.used`, and that is the whole reason this exists: that dict is
        per encounter and `extended_rest` clears it, so a daily allowance kept
        there was spent and restored by every short rest.
        """
        if self.per_day_left(ref, limit) <= 0:
            return False
        self.per_day[ref] = self.per_day.get(ref, 0) + 1
        return True

    @property
    def down(self) -> bool:
        """Past saving, so a rest does nothing for them.

        `Health.dying_at` is `-(max_hp // 2)` and `query.alive` is
        `hp > dying_at`, so this is that same line asked of the record.
        """
        return self.max_hp > 0 and self.hp is not None and self.hp <= -(self.max_hp // 2)

    def heal(self) -> None:
        """Spend surges up to full, which is what a short rest is for.

        A quarter of maximum each, `query.surge_value`'s number. Stops at full
        rather than overshooting, and does nothing at all for somebody who is
        `down`.
        """
        if self.max_hp <= 0 or self.hp is None or self.down:
            return
        per = max(1, self.max_hp // 4)
        left = self.surges if self.surges is not None else 0
        while self.hp < self.max_hp and left > 0:
            self.hp = min(self.max_hp, self.hp + per)
            left -= 1
        self.surges = left

    @property
    def character(self) -> chargen.Character:
        """The build request this sheet is a record of."""
        return chargen.Character(
            self.cls, self.level, build=self.build, race=self.race,
            powers=list(self.powers), feats=list(self.feats),
        )


@dataclass
class Party:
    """A party with a lifetime longer than one fight.

    The thing #72 is about. Four sheets and a day's worth of wear on them.
    """

    sheets: list[Sheet] = field(default_factory=list)

    @classmethod
    def of(
        cls,
        names: list[str] | None = None,
        level: int = 1,
        *,
        seed: int = 0,
        feats: dict[str, list[str]] | None = None,
    ) -> Party:
        """A fresh party, unwounded, nothing spent -- and **dealt here**.

        The hand is dealt once, now, off `seed` rather than off whichever fight
        the party walks into. `chargen.spawn` deals from `world.rng.seed` when a
        `Character` names no powers, so leaving it to the fight meant a party
        that changed shape between two encounters -- see `Sheet.powers`.

        The same three dealers `spawn` uses, in the same order and off the same
        shape of key, so a dealt party is one `spawn` would have dealt.
        """
        from random import Random

        from combat_engine.chargen import (
            DEAL_RACES,
            build_of,
            deal_race,
            feats_for,
            loadout,
            power_swap,
        )

        sheets: list[Sheet] = []
        for name in (names or PARTY):
            key = name.strip().lower()
            build = build_of(key, "")
            race = (
                deal_race(Random(f"{seed}:{key}:race"), key, build)
                if DEAL_RACES else ""
            )
            hand = loadout(key, level, build, Random(f"{seed}:{key}:{build.name}"))
            taken = list((feats or {}).get(key, [])) or feats_for(
                key, level, build,
                Random(f"{seed}:{key}:{build.name}:feats"), list(hand), race,
            )
            # The same swap `spawn` makes, and it has to happen here too: a feat
            # that hands over a card takes one back, so a hand pinned before the
            # swap is a hand `spawn` would then alter -- which is the drift this
            # method exists to stop.
            sheets.append(Sheet(
                cls=key, level=level, build=build.name, race=race,
                powers=power_swap(list(hand), list(taken)), feats=taken,
            ))
        return cls(sheets=sheets)

    def rest(self, *, extended: bool = False) -> None:
        """Five minutes, or six hours.

        The same division `turns.short_rest` and `turns.extended_rest` make on a
        board, applied to the record instead -- and it has to be here as well as
        there, because this is the copy that outlives the fight.

        A short rest returns the encounter powers, leaves the dailies spent, and
        **spends surges to heal**, which is the one thing the board's version
        does not do and the reason it had to be written here. That is not a
        liberty: a short rest is the moment the printed rules let a character
        spend any number of healing surges, and without it the multi-encounter
        loop was useless -- measured, a party won its first fight and was wiped
        in the second two, because it walked in at -34 hit points.

        Surges are spent one at a time up to full and no further, which is the
        obvious reading of "any number" for somebody who wants to keep fighting.
        A character past `dying_at` is not healed at all: dying is not a thing
        five minutes fixes, and quietly reviving one would make a wipe look like
        a win.
        """
        from combat_engine.engine.dsl import get
        from combat_engine.engine.types import Usage

        for sheet in self.sheets:
            if extended:
                sheet.spent.clear()
                sheet.per_day.clear()
                sheet.hp = None
                sheet.surges = None
                sheet.action_points = 1
                sheet.failures = 0
                continue
            sheet.failures = 0
            for ref in list(sheet.spent):
                row = get(ref)
                if row is None or row.usage is not Usage.DAILY:
                    del sheet.spent[ref]
            sheet.heal()


def _wear(world: World, eid: int, sheet: Sheet) -> None:
    """Put a sheet's wear on a freshly built character.

    After `spawn` rather than instead of it, which is the whole shape of this:
    the character is rebuilt from its class every time, so a content wave or a
    rules fix reaches a party mid-day, and only the wear is carried.

    `None` means "whatever a fresh one has", so a party that has not fought
    lands exactly as it did before any of this existed -- which is what keeps
    the six replay fixtures still pinning something.
    """
    from combat_engine.engine.components import ActionPoints, Health, Powers

    health = world.get(eid, Health)
    if health is not None:
        if sheet.hp is not None:
            health.hp = max(0, min(sheet.hp, health.max_hp))
        if sheet.surges is not None:
            health.surges = max(0, min(sheet.surges, health.max_surges))
        health.failures = sheet.failures
    points = world.get(eid, ActionPoints)
    if points is not None:
        points.points = sheet.action_points
    powers = world.get(eid, Powers)
    if powers is not None:
        # Only what the character actually has. A sheet written at one level and
        # fielded at another, or a build whose rows moved under it, must not
        # carry a spend for a row it no longer holds.
        for ref, round_ in sheet.spent.items():
            if ref in powers.known:
                powers.used[ref] = round_


def harvest(world: World, party: Party) -> None:
    """Read the party's wear back off the board a fight was fought on.

    The other half of handing a sheet to `field_encounter`: without this the
    party walks out of every fight as fresh as it walked in, which is the state
    #72 describes.

    Matched by position, because that is what put them on the board. Matching by
    class would break the moment a party fields two of one, and a `Sheet`
    carries no entity id on purpose -- an id belongs to a world, and this
    outlives one.

    **Temporary hit points are not harvested**, and that is the printed rule
    rather than an omission: they last until the end of the encounter. Nor are
    conditions. A save-ends effect at the moment the last enemy drops is a rules
    question rather than an engineering one, and the honest answer is that
    nothing here can carry one -- a condition is held by the `World`'s duration
    book, which is what does not survive. Said out loud because a party walking
    out of a fight still dazed is a thing somebody will expect.
    """
    from combat_engine.engine.components import ActionPoints, Health, Powers, Side

    on_board = [eid for eid, side in world.each(Side) if side.team == Team.PC]
    for sheet, eid in zip(party.sheets, on_board, strict=False):
        health = world.get(eid, Health)
        if health is not None:
            sheet.hp = health.hp
            sheet.max_hp = health.max_hp
            sheet.surges = health.surges
            sheet.failures = health.failures
        points = world.get(eid, ActionPoints)
        if points is not None:
            sheet.action_points = points.points
        powers = world.get(eid, Powers)
        if powers is not None:
            sheet.spent = dict(powers.used)


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
    party: Party | None = None,
) -> Fielded:
    """Build a board and put both sides on it.

    `feats` pins what each class has taken, by class name, and exists for
    `replay.py`: a character's feats are otherwise dealt from the pool of
    *declared* ones, so every content wave changed the party and every fixture
    diverged. Pinning them makes a fixture a test of the engine rather than of
    the corpus's size.

    `enemies` names the opposition outright, for a caller that is not asking for
    a level-appropriate band.

    `party` is a `Party` that has already fought. It replaces `pcs`, `level` and
    `feats` for the characters -- each sheet knows its own class, build, race and
    feats -- and its wear is laid on the board after `spawn`, not instead of it:
    a character is built fresh every time and then wounded back down to where it
    was. That is what makes this additive. #72.
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

    if party is not None:
        for i, sheet in enumerate(party.sheets):
            eid = chargen.spawn(
                world, sheet.character,
                (PARTY_AT[0], PARTY_AT[1] + i * SPACING),
            )
            _wear(world, eid, sheet)
    else:
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
