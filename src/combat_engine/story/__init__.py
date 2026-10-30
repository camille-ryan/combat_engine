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
from functools import lru_cache
from random import Random

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
    #: Which shape of encounter this is -- see `PARADIGMS`. `"named"` when the
    #: caller named the monsters outright, which `replay.py` does.
    paradigm: str = ""


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
    #: Experience earned, and **never spent**. Applying a level re-deals
    #: powers, feats and ability increases for a character whose hand is
    #: pinned two fields down, which is a `chargen` job and a larger one --
    #: so this accumulates, `xp.ready` says when it is enough, and nothing
    #: in `story/` advances anybody. #967.
    xp: int = 0
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

    #: Items this character is carrying, by item ref -> how many.
    #:
    #: Granted by a scene (`Scene.grants`, applied in `loot.hand_over`) and
    #: **spent by nothing yet**, which is deliberate and is the whole of
    #: #935: a module hands the party a consumable in its own prose and
    #: before this there was nowhere for one to go, so it vanished. A
    #: visible count that cannot be drunk is honest; a silent one was not.
    #:
    #: Not what `chargen` deals. Those are `Magic` -- a worn slot with an
    #: enhancement bonus, rebuilt from `cls`/`level`/`build` every fight
    #: like the rest of the character. This is the stuff that happened to
    #: the party, which is why it lives with the wear rather than with the
    #: request.
    carried: dict[str, int] = field(default_factory=dict)
    #: Coins, in gold pieces. **Nothing spends them**, deliberately: an
    #: economy with nothing to buy is a separate piece of work, and the
    #: printed buying rules want rituals (#453) and a market. A visible
    #: number that cannot be spent is honest; awarding nothing was not.
    #: #969.
    coins: int = 0

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
            dealt_hand,
            feats_for,
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
            hand = dealt_hand(seed, key, level, build)
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
        # The day's allowances, unfiltered: a `per_day` count is keyed on the
        # row that *grants* the allowance, which for a class feature is not in
        # `powers.known` at all. Filtering it the way `spent` is filtered
        # would drop every one of them.
        powers.per_day = dict(sheet.per_day)


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
    from combat_engine.engine.components import (
        ActionPoints,
        Health,
        Ident,
        Powers,
        Side,
    )

    # **Only the characters, not everything on their side.** A familiar is
    # a `Team.PC` creature with `Health`, so the side holds five entities
    # for a party of four, and this zip matched sheets to whatever came out
    # of `each(Side)` in order. On the board it was measured on it happens
    # to be harmless -- the familiar sorts last and `strict=False` drops it
    # -- which is luck. Anything PC-side appearing *before* one of the
    # characters shifts every sheet after it: a character's hit points and
    # surges written from a summon's, and the summon's written nowhere.
    #
    # A filter rather than a different matching scheme. Positional
    # matching is right for the reason the docstring gives -- a `Sheet`
    # carries no entity id and matching by class breaks on two of one --
    # so what it needs is to walk only the creatures the sheets are
    # *about*. `chargen.spawn` gives every character `c:<class>`; a
    # summon, a companion or a conjuration never does. #797.
    on_board = [
        eid for eid, side in world.each(Side)
        if side.team == Team.PC
        and (ident := world.get(eid, Ident)) is not None
        and ident.ref.startswith("c:")
    ]
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
            sheet.per_day = dict(powers.per_day)


def mixed(pool: list[str]) -> list[str]:
    """Reorder a pool so consecutive picks come from different roles."""
    from combat_engine.db import game

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


#: What an encounter can look like, and Camille's list. Every one of them spends
#: the party's XP budget, which is the thing the bare draw did not do: it took four
#: creatures whatever their rank, so **11 of 24 level-10 draws came out over
#: budget** -- three of them at 4,000 XP and one at 6,000, against a standard 2,000.
#: An elite is worth two standards and a solo five, so "four creatures" is a count
#: and not a budget.
#: The shapes a random encounter is **drawn** from, which is now the
#: printed five rather than four of our own. Camille's call, 2026-10-30,
#: asked directly and answered yes. #951.
#:
#: The printed d10 rolls them at equal weight -- commander and troops,
#: wolf pack, dragon's den, battlefield control, double line -- so `leader`
#: and `solo` keep their places as the first and third of those, and the
#: three that had no analogue join them.
#:
#: **`standard` and `elites` leave the draw, and that is the part worth
#: knowing.** Neither is a printed template: `standard` is "a mix of roles
#: freely" and `elites` is the only shape that fielded elite monsters at
#: all. Both are still reachable by name through `SHAPES_BY_NAME`, so
#: nothing can no longer be built -- but a random arcade board will not
#: produce an elite pair any more, and that was not obvious from the ask.
PARADIGMS = ("leader", "wolf pack", "solo", "battlefield control",
             "double line")

#: Every shape that can be **asked for** by name, which is a longer list
#: than the one that gets **drawn** -- it keeps `standard` and `elites`,
#: which the printed draw does not roll. #951.
SHAPES_BY_NAME = (*PARADIGMS, "standard", "elites")

#: How many standards' worth each rank costs, from the printed maths.
RANK_COST = {"standard": 1, "elite": 2, "solo": 5}


#: How much of the budget each rank in a paradigm should spend.
#: What one creature of each rank is worth, in standard monsters. The printed maths,
#: which `_compose`'s docstring already states: "An elite is two standards and a solo five".
#:
#: Used to work out what **one slot** of a rank should cost, which is what the fit window
#: has to be centred on. Centring it on the whole group's share instead is #323: at level 5
#: the elite window became 640-1040 against elites costing 300-700, so the only candidates
#: that "fit" were the six costing 700 -- one of those was taken and `spent + cost >
#: want * 1.1` then refused a second, so a two-elite encounter fielded **one** creature.
#:
#: At level 10 the same arithmetic let two through by accident, because no elite in the band
#: cost enough to fill the budget alone. The body count was an accident of which elites
#: happened to be written at a level, which is why it was right at one and wrong at another.
WORTH = {"standard": 1.0, "elite": 2.0, "solo": 5.0, "minion": 0.25}

COMPOSITION: dict[str, list[tuple[str, float]]] = {
    "standard": [("standard", 1.0)],
    "elites": [("elite", 1.0)],
    "solo": [("solo", 1.0)],
    "leader": [("standard", 0.5), ("minion", 0.5)],
}

#: The printed templates, which are keyed by **role** where `COMPOSITION`
#: is keyed by rank. #951.
#:
#: The book gives five and we had analogues for two: `solo` is Dragon's
#: Den and `leader` is Commander and Troops. The three here are the ones
#: with no analogue, and two of them are the ones that make a fight worth
#: positioning in -- a protected back rank, or movement control paired
#: with mobile attackers. Fielding five creatures of one role gives the
#: policy nothing to do.
#:
#: Each slot is `(rank, share, roles)`; an empty `roles` takes anything.
#: **A role filter that empties the pool is dropped rather than obeyed**,
#: which is this component's own recorded caution: 253 of 384 minions
#: carry `role = 'minion'` rather than a tactical role, so filtering on
#: role can empty a whole rank.
TEMPLATES: dict[str, list[tuple[str, float, tuple[str, ...]]]] = {
    # *"pick a brute or soldier monster and use two or three of them.
    # Pick one or two monsters of other roles to round out."*
    "double line": [
        ("standard", 0.6, ("brute", "soldier")),
        ("standard", 0.4, ("artillery", "controller")),
    ],
    "battlefield control": [
        ("standard", 0.25, ("controller",)),
        ("standard", 0.75, ("skirmisher",)),
    ],
    "wolf pack": [
        ("standard", 1.0, ("skirmisher",)),
    ],
}

#: How far either way a fight may reach for a monster. Camille's call.
#:
#: **A symmetric narrowing of an asymmetric printed window, chosen
#: deliberately** -- the second sentence here used to say it *was* "what the
#: printed encounter-building rules allow", and that is not true. Measured
#: against the page, monster levels relative to the party are:
#:
#: | encounter | printed window |
#: |---|---|
#: | easy | -4 .. 0 |
#: | standard | **-3 .. +4** |
#: | hard | -3 .. **+7** |
#:
#: So 3 is right on the low side, one short above for a standard fight and
#: four short for a hard one -- and the book asks for a hard encounter once
#: per character level. Chapter 10's own 50-card encounter deck puts 5 cards
#: at +4 or +5, so 26% of it is outside this band.
#:
#: Left at 3 on purpose. Two things to know before changing it: the page
#: attaches a role caveat to the top of the range -- *"be careful of using
#: high-level soldiers and brutes"*, because a soldier five levels up is
#: very hard to hit and a brute does too much damage -- so a wider band is
#: not uniform across roles, and `cast_list._facts` already reads `role` if
#: that is wanted. (Quoted short on purpose: the full sentence carries a
#: contraction that `leaks.py` matches against part of a monster ability
#: name, which is the #494 partial-match noise.)
#:
#: And #972's level adjustment would make this a preference rather than a
#: wall, which is probably the answer that needs no change to
#: the number at all. #966.
BAND = 3

#: The most creatures one rank's share may field. Minions are a quarter of a
#: standard, so half a budget buys eight of them at the party's level and more from
#: lower down the band; past about a dozen a fight is a bookkeeping exercise.
MOST = 12


@lru_cache(maxsize=1)
def ceiling() -> int:
    """The highest level the database can actually field a standard monster at.

    **Asked of the database, never of `etl`'s constant.** `MAX_MONSTER_LEVEL`
    is the ETL's decision and `story` importing `etl` would break a contract
    `.importlinter` holds; `db.py` is below every component for exactly this.
    So this reads what is there, which is also the only thing a budget can
    honestly be spent on. #963.

    13 today, and a cliff rather than a thin tail: 218 rows at 13 and none
    at 14.
    """
    from combat_engine.db import game

    row = game().execute(
        "SELECT max(level) FROM monster WHERE minion = 0 AND xp > 0 "
        "AND (rank IS NULL OR rank = 'standard')"
    ).fetchone()
    return int(row[0]) if row and row[0] else 1


def budget(level: int, scale: float = 1.0) -> int:
    """The XP a standard encounter for this party is worth.

    **Clamped to `ceiling()`, and the clamp is reported by the caller.**
    `game.db` stops at level 13 by deliberate ETL decision, and above it
    this used to return **0** in silence -- so a module validated for a
    paragon party fielded nobody, with no exception anywhere, because
    `cast_list` guards its divisions with `max(aim, 1.0)`. An empty fight
    with no message gets diagnosed as a `cast_list` bug.

    The same call `opposition` makes one function down: *"a fight against
    nothing is not useful, so rather than refuse, this drops to whatever
    level has been written and reports which."*

    **Not computed from the printed curve above the cap**, though the
    printed table does run to level 40. A budget derived from it would name
    a figure `cast_list` cannot spend -- fielding a level-20 encounter needs
    level-20 *monsters*, not just the number they would be worth -- so the
    scene would still field nobody while now claiming a target, which is
    worse than a 0. The printed table is the answer for a quest or a
    challenge reward at a level with no monsters, not for an encounter.
    #963.

    One standard monster of the party's level per character, which is the printed
    rule. Read off the database rather than from a table here, so it cannot
    disagree with what the monsters are actually worth.

    `scale` multiplies it, which is what an adventuring day's difficulty curve
    is made of -- a soft opener and a hard finale around standard middles. It
    is a **multiple of the printed budget** and not a second notion of
    difficulty: at 1.0 this is unchanged, and `api.day.scales` is where the
    default curve lives, because the curve is arcade-mode policy and the
    printed rule is this. #666.
    """
    from combat_engine.db import game

    # **A *standard* monster's XP**, which the rank filter is for: taking the
    # first row with an XP at all picked up a solo at 2,500 and declared the
    # budget 10,000, which fielded 48 creatures on a 16x12 board.
    row = game().execute(
        "SELECT xp FROM monster WHERE level = ? AND minion = 0 AND xp > 0 "
        "AND (rank IS NULL OR rank = 'standard') LIMIT 1",
        (min(max(level, 1), ceiling()),),
    ).fetchone()
    # **Rounded, not truncated.** `int()` on 0.75 of a 4x100 budget gives 300
    # either way, but on an odd standard XP a truncation loses a creature's
    # worth at the bottom of the band -- and `opposition` skips a candidate
    # that would break the ceiling, so a budget one point short is a monster
    # fewer rather than a rounding nicety.
    return round((row[0] if row else 0) * SIDE * scale)


def opposition(
    level: int, draw: Random | None = None, paradigm: str | None = None,
    scale: float = 1.0,
) -> tuple[list[str], int, str]:
    """Monsters to field, and the level they came from.

    Falls back down the levels while content is thin: a fight against nothing is
    not useful, so rather than refuse, this drops to whatever level has been
    written and reports which. The caller decides whether to mention it.

    **`draw` is what makes two seeds fight different monsters, and without it
    they did not.** `loader.pick`'s default truncates to the first 20 by ref and
    `field_encounter` then took `pool[i % len(pool)]`, so *every* fight at a
    level faced the same four creatures however the seed fell -- at level 10,
    `m112`, `m2931`, `m2914` and `m221`, out of 41 written. Twenty-four scorecard
    "fights" were twenty-four rolls of the dice against one fixed encounter, and
    three agents reading three "different" logs all reported the same elite
    because it was in all three.

    So the whole usable set goes in and the seed picks from it. `mixed` still
    interleaves by role afterwards, because a mixed encounter is a better test
    than four brutes.
    """
    for candidate in range(min(max(level, 1), 13), 0, -1):
        want = paradigm or (draw.choice(PARADIGMS) if draw else "standard")
        fielded = _compose(candidate, want, draw, scale)
        # **Falls back to `standard` rather than to nothing.** A level with no
        # usable solo is the ordinary case -- there are two at level 10 and two at
        # level 5 -- and refusing the fight would make the paradigm a coin that
        # sometimes returns an empty board.
        if not fielded and want != "standard":
            want = "standard"
            fielded = _compose(candidate, want, draw, scale)
        if fielded:
            return fielded, candidate, want
    return [], level, "standard"


def _role_of(ref: str) -> str:
    """A creature's tactical role, lowercased. `""` when it has none."""
    from combat_engine.db import game

    row = game().execute(
        "SELECT role FROM monster WHERE ref = ?", (ref,)).fetchone()
    return (row[0] or "").strip().lower() if row else ""


def _compose(level: int, paradigm: str, draw: Random | None,
             scale: float = 1.0) -> list[str]:
    """The refs for one paradigm, filled to the XP budget. `[]` if unbuildable.

    **Filled by XP rather than counted**, which is what reaching three levels
    either way forces: a level-7 standard is not worth a level-10 one, so "four
    creatures" stopped being a budget the moment the band opened. An elite is two
    standards and a solo five by the printed maths, and this reads the real figure
    off each row rather than assuming it.

    **Fits to the budget rather than filling past it.** Taking each creature in
    turn until the total was reached overshot every time -- a leader-and-minions
    came out at 122-129% and two elites drawn from the top of the band at 130% --
    because the last creature taken is the one that breaks the ceiling. A
    candidate is skipped when it would, unless nothing has been taken yet.

    **Nearest the party's level first.** The band exists so a fight has a choice,
    not so a level-5 party meets a level-8 solo; sorting by distance keeps the
    band as variety rather than as difficulty.
    """
    from combat_engine.db import game

    db = game()
    total = budget(level, scale)
    if not total:
        return []
    out: list[str] = []
    # **A printed template is role-keyed; our own paradigms are not.** Both
    # are read as `(rank, share, roles)` here so the fill below is one
    # loop rather than two. #951.
    slots: list[tuple[str, float, tuple[str, ...]]] = (
        TEMPLATES[paradigm] if paradigm in TEMPLATES
        else [(rank, share, ())
              for rank, share in COMPOSITION.get(
                  paradigm, COMPOSITION["standard"])]
    )
    for rank, share, roles in slots:
        # **A solo is the encounter, so it does not get the band.** Its whole
        # point is one creature matched to the party, and three levels of slack
        # on a creature worth five standards is the difference between a fight
        # and a formality in either direction.
        reach = 1 if rank == "solo" else BAND
        pool = loader.pick(
            level, limit=0, band=reach,
            rank=None if rank == "minion" else rank, minion=rank == "minion",
        )
        if not pool:
            return []
        # **A role filter that empties the pool is dropped.** This
        # component's own recorded caution: 253 of 384 minions carry
        # `role = 'minion'` rather than a tactical role, so filtering can
        # empty a whole rank -- and a template that fields nobody is
        # worse than one that fields the wrong shape.
        if roles:
            wanted = [r for r in pool if _role_of(r) in roles]
            pool = wanted or pool
        costs: dict[str, float] = {}
        depth: dict[str, int] = {}
        for ref in pool:
            row = db.execute(
                "SELECT xp, level FROM monster WHERE ref = ?", (ref,)).fetchone()
            if row and (row[0] or 0) > 0:
                costs[ref] = float(row[0])
                depth[ref] = abs(int(row[1] or level) - level)
        pool = [r for r in pool if r in costs]
        if not pool:
            return []
        want = total * share
        # **Within a tolerance of the budget first, then by level.** Sorting on
        # level distance alone put a 156%-of-budget solo in front of a 93% one at
        # level 5, because the nearest-level solo written happens to be an
        # expensive one -- and a solo is taken unconditionally, being one creature.
        # Measured consequence: every one of the seven worst level-5 boards for
        # party casualties was a solo, 10 to 14 drops against 6 for the next
        # paradigm, in fights of three to seven rounds. Not a grind -- too hard.
        #
        # So candidates that fit are preferred, and the level sort then breaks ties
        # among them. The shuffle survives both sorts for equal keys, which is what
        # keeps two seeds from always meeting the same creature.
        if draw is not None:
            pool = draw.sample(pool, len(pool))
        # **Sorted after `mixed`, not before.** `mixed` interleaves by role and so
        # re-orders whatever it is given -- sorting first and mixing after threw the
        # fit away entirely, which is why a 156% solo kept winning. A stable sort on
        # top keeps the role interleave as the tie-break.
        # **Closest to the share, not merely under it.** A tolerance alone still let
        # a 1,000 XP solo win an 800 XP budget when a 750 one was written, because
        # both were inside it. Ordering by distance from the share picks the one that
        # actually fits, and costs no variety where it matters: every standard at a
        # level is worth the same, so the key ties and `mixed`'s role interleave
        # breaks it. Only the ranks with varied prices -- elites and solos -- are
        # narrowed, which is exactly where precision is wanted, a solo being the
        # whole encounter.
        # **One wide bucket, not a ranking.** Anything from 80% to 130% of the share
        # is "fits", and the shuffle decides inside it; only what misses the band is
        # pushed to the back.
        #
        # Ordering by distance from the share instead was tighter on budget and
        # measurably worse to play: it picked the single best-fitting creature every
        # time, so all seven level-5 solo seeds met the same level-4 lurker with 208
        # hit points, fights went from 3-7 rounds to 6-12, and party casualties rose
        # from 120 to 165. Tuning one aggregate narrowed the sample until one bad
        # matchup was the whole measurement, which is the fault the paradigms exist
        # to prevent.
        # **What one creature of this rank should cost, not what the whole share
        # should.** `want` is the group's budget; a fit test applied per candidate has to
        # be centred on a single slot or it only ever admits creatures big enough to
        # swallow the lot. `budget` is `SIDE` standards, so one standard is `total / SIDE`
        # and the rest follows from `WORTH`. #323.
        aim = max((total / SIDE) * WORTH.get(rank, 1.0), 1.0)

        def band(ref: str, c: dict[str, float] = costs, a: float = aim) -> int:
            return 0 if 0.8 * a <= c[ref] <= 1.3 * a else 1

        # **`mixed` is for a group, so a solo does not get it.** It interleaves by
        # role, which means the first creature it yields is always from the first
        # role in `ROLE_ORDER` that has a member -- harmless when four are being
        # taken and a fixed preference when one is. All seven solo seeds met the same
        # creature for that reason, with the shuffle unable to reach past it.
        ordered = sorted(pool, key=lambda r: depth[r])
        if rank != "solo":
            ordered = mixed(ordered)
        pool = sorted(ordered, key=band)
        spent = 0.0
        taken = 0
        for i in range(MOST * len(pool)):
            ref = pool[i % len(pool)]
            cost = costs[ref]
            if taken and spent + cost > want * 1.1:
                continue
            out.append(ref)
            spent += cost
            taken += 1
            if rank == "solo" or spent >= want * 0.9 or taken >= MOST:
                break
    return out

def number_repeats(world: World) -> None:
    """Number the repeats, so two of the same monster are tellable apart."""
    seen: dict[str, int] = {}
    for _eid, ident in world.each(Ident):
        seen[ident.ref] = seen.get(ident.ref, 0) + 1
        if seen[ident.ref] > 1 or ident.ref.startswith("m"):
            ident.tag = str(seen[ident.ref])


@dataclass(frozen=True)
class Shape:
    """How big the room is, and what shape. #974.

    Every board was one of two hard-coded rectangles -- 16x12 for a fight
    and 12x8 for a borrowed board -- so a corridor, a cave mouth, a great
    hall and a tavern were all the same floor with the same two starting
    bands at the ends.

    `kind` is `rectangle`, `octagon` or `irregular`. **An octagon needs
    nothing new**: a cut corner is blocking squares, which is the same
    mechanism `terrain.dress` already uses for pillars.
    """

    width: int
    height: int
    kind: str = "rectangle"

    @property
    def area(self) -> int:
        return self.width * self.height


#: The printed d20 table of chamber sizes, in the order it prints them.
#:
#: *"Although small rooms are possible, larger areas work better for combat
#: since they allow more movement choices and varied terrain."*
#:
#: **Nine of the ten are smaller than today's 16x12** -- the board in use is
#: at the large end of the printed range, and the two 10x16 entries are the
#: only ones that match it in area. Recorded rather than drawn from: a
#: seeded draw over these would move every arcade board, which owes
#: `winrate` both ways and a fixture re-record.
CHAMBERS = (
    Shape(8, 8), Shape(10, 10),
    Shape(6, 8), Shape(8, 10), Shape(10, 16),
    Shape(8, 8, "octagon"), Shape(8, 12, "octagon"), Shape(12, 12, "octagon"),
    Shape(8, 10, "irregular"), Shape(10, 16, "irregular"),
)

#: What a fight is built on when nobody says otherwise. Unchanged, which is
#: what keeps every fixture still.
FLOOR = Shape(16, 12)


def corners_of(shape: Shape) -> set[tuple[int, int]]:
    """The blocking squares that make a room this shape.

    A rectangle has none. An **octagon** loses a triangle from each corner,
    a quarter of the shorter side deep, which is what a cut corner is on a
    square grid. An **irregular** chamber loses one corner only -- enough
    to make the floor asymmetric, which is the point of it, without
    inventing a cave system.
    """
    if shape.kind == "rectangle":
        return set()
    cut = max(1, min(shape.width, shape.height) // 4)
    blocked: set[tuple[int, int]] = set()
    which = (
        ((0, 0), (1, 0), (0, 1), (1, 1)) if shape.kind == "octagon"
        else ((0, 0),)
    )
    for right, down in which:
        for x in range(cut):
            for y in range(cut - x):
                square = (
                    (shape.width - 1 - x) if right else x,
                    (shape.height - 1 - y) if down else y,
                )
                blocked.add(square)
    return blocked


def bands_of(shape: Shape) -> tuple[tuple[int, int], tuple[int, int]]:
    """Where each side starts on a board of this shape.

    **Reproduces `PARTY_AT` and `ENEMY_AT` exactly at 16x12**, which is what
    lets the shape be a parameter without moving a single fixture: the
    party's column is a fixed indent and the opposition's is four in from
    the far wall, which on the standard floor is 2 and 12.

    The `max` is what keeps a 6-wide chamber playable -- four in from the
    right of six is the party's own column, and both sides starting in one
    square is not a fight.
    """
    party_x = min(2, max(0, shape.width - 2))
    enemy_x = max(party_x + 3, shape.width - 4)
    enemy_x = min(enemy_x, shape.width - 1)
    row = max(0, shape.height // 4)
    return (party_x, row), (enemy_x, row)


def line_up(
    start: tuple[int, int], count: int, shape: Shape, *, inward: int,
    taken: set[tuple[int, int]] | None = None,
) -> list[tuple[int, int]]:
    """Where `count` creatures stand, starting from a band. #974.

    **Byte-identical to the old hard-coded layout on a 16x12 floor**,
    which is the whole point: five to a column from row 3, stepping two
    columns inward when one fills. On the standard board that is exactly
    the `(i // 5)` and `(i % 5)` the opposition's loop used to spell out,
    and the party's four fit one column either way.

    What it adds is a board that is **not** 16x12. Ten creatures laid out
    five-to-a-column walk off the bottom of an 8-tall chamber and off the
    left of a 6-wide one, which is what the printed table is full of --
    nine of its ten chambers are smaller than the floor in use.

    Blocked squares are skipped, so an octagon's cut corners cannot be
    stood on, and so are any in `taken`.

    **`taken` is what stops the two sides standing on each other.** The
    bands are far apart on a 16x12 floor and overlap on a small one: ten
    creatures laid out from a 10x10 chamber's own band reach back into
    the party's column, and `grid.place` refuses to overwrite -- so the
    second creature would be `Position`-present and index-absent, which is
    the failure `dress` already warns about for pillars.
    """
    per_column = max(1, 1 + (shape.height - 1 - start[1]) // SPACING)
    blocked = corners_of(shape) | set(taken or ())
    out: list[tuple[int, int]] = []
    slot = 0
    # Bounded: `count` squares are wanted and each turn of the loop either
    # takes one or steps past a blocked square, so the ceiling is the
    # board.
    while len(out) < count and slot < shape.width * shape.height:
        column, row = divmod(slot, per_column)
        slot += 1
        square = (start[0] + column * 2 * inward, start[1] + row * SPACING)
        if not (0 <= square[0] < shape.width
                and 0 <= square[1] < shape.height):
            continue
        if square in blocked:
            continue
        out.append(square)
    # **When the band cannot hold them all**, which only happens on a
    # chamber smaller than the floor: ten creatures at two-square spacing
    # want nine squares on an 8x8 and the band offers fewer. The rest take
    # any free square, walking in from their own side, rather than being
    # stacked on one spot -- the old code's fallback put every leftover on
    # the band square itself.
    if len(out) < count:
        taken = set(out)
        columns = (range(shape.width) if inward > 0
                   else range(shape.width - 1, -1, -1))
        for x in columns:
            for y in range(shape.height):
                if len(out) >= count:
                    break
                square = (x, y)
                if square in taken or square in blocked:
                    continue
                taken.add(square)
                out.append(square)
    return out


def arrival_squares(
    world: World, how_many: int, *, party: bool = False,
) -> list[tuple[int, int]]:
    """Free squares in the opposition's band for creatures walking on. #962.

    **The module's own guard is a check rather than a new facility**: it
    only lets reinforcements emerge where there is room for them, and
    `Grid.place` already refuses to overwrite an occupant -- so this asks
    the index which squares are free and hands back as many as it found,
    which may be fewer than asked for.

    Searched outward from the column `field_encounter` opens that side on,
    so a wave lands where its own kin are standing rather than among the
    creatures it came to fight. That is **not** DMG2's *"come up behind the characters"*: this
    board has no behind, and inventing one would be a placement feature
    rather than an arrival one.
    """
    grid = world.grid
    # **Either band, read off the board rather than off a constant.**
    # `PARTY_AT` and `ENEMY_AT` are the standard floor's columns; on any
    # other chamber shape they are the wrong squares or off the map
    # entirely, so the bands come from the grid's own size. #974.
    here, there = bands_of(Shape(grid.width, grid.height))
    start = here if party else there
    inward = 1 if party else -1
    free: list[tuple[int, int]] = []
    for back in range(0, 6):
        for step in range(0, 12):
            square = (start[0] + back * inward, start[1] + step)
            if not grid.inside(square):
                continue
            if grid.occupant(square) is not None:
                continue
            free.append(square)
            if len(free) >= how_many:
                return free
    return free


def field_encounter(
    seed: int,
    level: int = 1,
    *,
    scaling: str = "full",
    math: str = "printed",
    pcs: list[str] | None = None,
    enemies: list[str] | None = None,
    feats: dict[str, list[str]] | None = None,
    powers: dict[str, list[str]] | None = None,
    party: Party | None = None,
    scale: float = 1.0,
    squares: list[tuple[int, int]] | None = None,
    traps: int | None = None,
    room: Shape | None = None,
    paradigm: str | None = None,
) -> Fielded:
    """Build a board and put both sides on it.

    `feats` pins what each class has taken, by class name, and exists for
    `replay.py`: a character's feats are otherwise dealt from the pool of
    *declared* ones, so every content wave changed the party and every fixture
    diverged. Pinning them makes a fixture a test of the engine rather than of
    the corpus's size.

    `powers` is the same pin one step over, and the argument above applies to
    it word for word -- it was simply never built. A fixture's **hand** is
    also dealt from the pool of declared rows, so writing a clause into a
    power could change which powers a character was dealt, and from there the
    action menu and every choice after it. #783.

    It is the **pre-swap** hand, which is what `chargen.dealt_hand` returns:
    `power_swap` is not idempotent, so pinning the post-swap list and feeding
    it back through `spawn` would take a second card away.

    `enemies` names the opposition outright, for a caller that is not asking for
    a level-appropriate band.

    `scale` multiplies the XP budget the opposition is drawn to, and is ignored
    when `enemies` names them -- a caller that picked the monsters has already
    decided what the fight is worth. It is how an adventuring day gets a
    difficulty curve; see `api.day.scales`.

    `party` is a `Party` that has already fought. It replaces `pcs`, `level` and
    `feats` for the characters -- each sheet knows its own class, build, race and
    feats -- and its wear is laid on the board after `spawn`, not instead of it:
    a character is built fresh every time and then wounded back down to where it
    was. That is what makes this additive. #72.
    """
    # **The room, which nothing could state until now.** Defaults to the
    # floor every board has always been, so a caller that says nothing
    # gets exactly the board it got before -- which is what lets this be a
    # parameter without re-recording a fixture. #974.
    # **`room`, not `shape`**: a local named `shape` already means the
    # encounter *paradigm* further down this function, and two different
    # things under one name in one scope is how a reader loses the
    # thread.
    room = room or FLOOR
    world = World(Grid(room.width, room.height), Rng(seed), Bus())
    # A cut corner is blocking squares, the same mechanism `dress` uses
    # for a pillar. Laid before anybody is spawned so the starting bands
    # cannot land on one.
    world.grid.blocking |= corners_of(room)
    party_at, enemy_at = bands_of(room)
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
    terrain.dress(world, seed, level=level, traps=traps)

    if party is not None:
        # **`squares` or the column this has always used.** The default
        # keeps every replay fixture still: a fight starts from these
        # squares, so a one-square drift re-records all eight. #994.
        standing = squares or line_up(
            party_at, len(party.sheets), room, inward=1)
        for i, sheet in enumerate(party.sheets):
            eid = chargen.spawn(
                world, sheet.character,
                standing[i] if i < len(standing)
                else (party_at[0], party_at[1] + i * SPACING),
            )
            _wear(world, eid, sheet)
    else:
        drawn_up = line_up(
            party_at, len(pcs or PARTY), room, inward=1)
        for i, name in enumerate(pcs or PARTY):
            key = name.strip().lower()
            chargen.spawn(
                world,
                chargen.Character(
                    key, level,
                    powers=list((powers or {}).get(key, [])),
                    feats=list((feats or {}).get(key, [])),
                ),
                drawn_up[i] if i < len(drawn_up) else party_at,
            )

    found_at = level
    shape = "named"
    if enemies:
        pool = list(enemies)
    else:
        # **Its own stream, not `world.rng`.** Drawing from the world's dice
        # would shift every roll after it, so a change to how monsters are
        # chosen would also change every attack in the fight and the two could
        # not be told apart.
        pool, found_at, shape = opposition(
            level, Random(seed), paradigm=paradigm, scale=scale)
    if not pool:
        return Fielded(world=world, enemies=[], found_at=found_at, paradigm=shape)

    # **The paradigm decides how many, so this no longer takes `SIDE` of them.**
    # A solo is one creature and a leader-and-minions is ten, and taking four
    # either way was the bug that made every encounter the same shape.
    #
    # Wrapped into columns so ten minions do not run off a 12-row board.
    # **Told where the party is standing.** Otherwise the two line-ups
    # are computed independently and collide on any board small enough
    # for the bands to meet.
    from combat_engine.engine.components import Position

    standing_now = {
        spot.square
        for eid in list(world.entities)
        if (spot := world.get(eid, Position)) is not None
    }
    facing = line_up(enemy_at, len(pool), room, inward=-1,
                     taken=standing_now)
    for i, ref in enumerate(pool):
        loader.spawn(
            world, ref,
            facing[i] if i < len(facing) else enemy_at,
            team=Team.ENEMY,
        )

    number_repeats(world)
    return Fielded(world=world, enemies=list(pool), found_at=found_at,
                   paradigm=shape)
