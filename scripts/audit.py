#!/usr/bin/env python
"""Fire every declared row and report the two ways one can be wrong.

    uv run scripts/audit.py                          every row; ~10 minutes
    uv run scripts/audit.py --changed                rows in changed files
    uv run scripts/audit.py --calls 'c.shove()'      rows that name a verb
    uv run scripts/audit.py --verdicts               is the verdict honest?
    uv run scripts/audit.py --sample 300             a direction, cheaply
    uv run scripts/audit.py --class wizard
    uv run scripts/audit.py --level 1 --verbose

**Pick the narrowest one that is still honest.** A full sweep is ten
minutes across ten cores and is the right thing after a large content
wave, not after adding one verb -- `--calls` is seconds and is what a new
`Cast` method wants, since a row can only reach a verb by naming it.
`--changed` is what `check.py` runs, and it widens to everything by
design when `engine/` moves.

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
    Cast,
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
from combat_engine.engine.grid import Square
from combat_engine.engine.movement import place
from combat_engine.engine.query import alive, can_act
from combat_engine.engine.query import enemies as _foes
from combat_engine.engine.types import ActionType, Usage

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
    # Gives back the use of one named sibling row, and the harness fires
    # each row once on a fresh board -- so that sibling has never been
    # spent and there is nothing to give back. Driven by hand: with
    # `Powers.used["f960b"] = 1` the count goes back to 0.
    "f961b": "restores a sibling row nobody has spent on this board",
    # The five the magic item waves left. Each is a Requirement or a
    # trigger condition the board does not produce; none is a row fault.
    # The first four were driven by hand by the agent that wrote them and
    # reported working; `i3527p1` I read rather than drove, and its three
    # guards -- the kill, adjacency, and the target not being a minion --
    # are plainly what the card prints.
    "i1875p1": "swaps a prepared power; the board's spellbook is empty",
    "i2582p1": "escapes a grab; nothing on the board grabs the caster",
    "i3045p1": "cures surprised or unconscious; the board produces neither",
    "i608p1": "its Requirement is being marked, and nobody here marks",
    "i3527p1": "wants an adjacent non-minion killed; the board's deaths are neither",
    # Three more from the class-feature sweep, all Requirements the board
    # cannot produce for an item row: the caster is a generic wielder, so
    # it holds no class feature and has spent no channel divinity, and
    # `_wants_expended` above cannot help -- the sibling it spends has to
    # be in the *same printed group*, and this caster knows none.
    #
    # Driven by hand. `i1927p1` and `i2304p1`: with a `CHANNEL_DIVINITY`
    # row spent, `Powers.used` goes 1 -> 0 and `dsl.usable` goes False ->
    # True for it; with nothing spent neither row touches anything.
    # `i3036p1`: with `f650b` in `Powers.known` the adjacent ally's AC
    # goes 17 -> 18, and without it 17 -> 17.
    "i1927p1": "gives a channel divinity use back; this caster has spent none",
    "i2304p1": "the same sentence as i1927p1, off a rod rather than a symbol",
    # Driven by hand too: with a `CHANNEL_DIVINITY` row spent, `Powers.used`
    # goes 1 -> 0; with nothing spent it touches nothing.
    "i2772p1": "the same sentence again, off a holy symbol",
    "i3036p1": "its bonus is f650b's, and the board's wielder has no f650b",
    # Targets an undead creature and the board's dummies are not one.
    # Driven by hand against a real undead stat block: a healing surge
    # goes and the target takes that much radiant damage.
    "f1091b": "targets an undead creature; the board fields none",
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
    # Takes one of six conditions off whoever it touches, and the creature
    # it gets aimed at here is carrying none of them -- the board's one
    # dazed ally is not in the pool this row is offered. Driven by hand:
    # aimed at a dazed fighter the daze goes and nothing else does.
    "p7240": "removes a condition; the creature it is aimed at here has none",
    # Hands a healing surge back, and its printed target line is allies
    # with two surges or fewer. Everybody on this board is untouched, so
    # the row passes over every candidate. Driven by hand: an ally set to
    # one surge comes out of it with two.
    "p2861": "its printed target must be down to two surges; nobody here is",
    # Its printed content is a penalty to the next save against one of the
    # caster's own save-ends effects, and the caster has laid none: the
    # harness fires each row once on a fresh board, so nothing it cast is
    # still standing. Driven by hand with a save-ends effect on an enemy:
    # -2 to that effect's save alone, 0 to any other, and spent by the one
    # throw it is for.
    # Renamed from `cf:wizard-implement` when 45 class features moved to
    # the database's own `-fN` spelling. A stale key here is silent in the
    # worst way: the row reappears in the SILENT list and the excuse that
    # was argued for it is still sitting in the file, unread.
    "cf:wizard-arcanist-f0": (
        "penalises a save against one of the caster's own save-ends effects; "
        "the board carries none of them"
    ),
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
    # Takes away every standard-action attack that is not a basic. Verified
    # against the board: all four dummies have exactly one standard row each
    # (m145a0 three times, m416a1 once) and in every case it *is* that
    # creature's basic, so the correct answer here is that nothing is taken
    # away. The row is right; the board has nothing for it to remove.
    "p7170": (
        "forbids standard attacks other than basic; every dummy's only "
        "standard row is its basic"
    ),
    # "You miss with a melee attack: attack again." The sweep loads the die
    # to 1 and to 20; a 1 is the only way to produce the triggering miss,
    # and it then makes the answering strike miss as well, while a 20 never
    # misses in the first place. So the row cannot show itself on a loaded
    # die however many seeds it gets. Driven by hand with the answer free to
    # land: the target goes from 31 hit points to 11. Any "on a miss, swing
    # again" row will read this way.
    "p4479": "triggers on a miss and answers with an attack; the loaded 1 misses twice",
    # A long jump plus "+2 to your fly speed (if any)". The jump is a skill
    # check nothing rolls, and the board's ranger has no fly speed, so the
    # printed row correctly does nothing here -- "if any" is the card's own
    # word for it.
    "p13696": "its only combat clause is a fly-speed bonus; the board's ranger cannot fly",
    # Undead-only rows. `c.is_kind("undead")` is True for the board's m416,
    # but a single-target row is aimed by `_auto_targets`, which picks the
    # nearest enemy and never that one. Driven at it by hand, p12601 deals
    # radiant, pushes 4 and immobilises; the other two likewise.
    "p12601": "affects only undead; the auto-targeter never picks the board's one undead",
    "p14293": "affects only undead; the auto-targeter never picks the board's one undead",
    "p5330": "affects only undead; the auto-targeter never picks the board's one undead",
    # Reduces a target's necrotic resistance, and nothing on the board has
    # any. Giving the undead some would change what every necrotic row in
    # the tree reports, which is a worse trade than one excused row.
    "p13970": "reduces necrotic resistance; nothing on the board has any",
    # Both make a *ranged* basic inside them, and the board's ranger is the
    # two-blade build with no bow. The chassis is right -- a two-blade
    # ranger genuinely cannot -- so this is the printed Requirement working.
    "p13585": "makes a ranged basic; the board's ranger is two-blade and owns no bow",
    "p13586": "makes a ranged basic; the board's ranger is two-blade and owns no bow",
    # Grants an ally a step and a swing, and the board's allies stand
    # behind the caster with nothing in reach after the step.
    "m2884a3": "grants an ally a step and a swing; no ally has anything in reach",
    # Shifts an ally on a burst-10 trigger. The allies are already packed
    # around the caster, so the shift has nowhere to put them.
    "p7194": "shifts an ally; the board's allies are boxed in around the caster",
    # Clears difficult terrain in a close burst 1, and the only squares
    # beside the caster have to stay smooth so a one-square shift has
    # somewhere to go. The board's rough ground is further out.
    "p15856": "clears difficult terrain within 1; the caster's neighbours must stay smooth",
    # Reaches its own companion in a burst. The board places one, but the
    # druid's level-0 rows now fire during setup and one of them calls a
    # companion of its own -- which relocates the standing one out of the
    # burst, by design. Excused rather than unwound: firing class features
    # up front took 23 other rows from unusable to exercised.
    "p13541": "a companion in a burst; the druid's own setup relocates it out of reach",
    # Steps inside a stone object, which here is any adjacent blocking
    # square, and the board keeps the caster's neighbours passable so that
    # a one-square shift always has somewhere to go. Driven by hand with a
    # blocking square beside the druid: it ends up in that square, line of
    # effect goes false in both directions, the hold carries the printed
    # minor action out of it, and ending it puts the druid in the nearest
    # free square with line of effect back.
    "p14508": "steps into an adjacent blocking square; the board keeps those clear",
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
    # Swaps an unexpended daily or utility for one of the same level out of
    # the spellbook. The board deals its caster the row under test and the
    # class features and nothing else, so the only same-level power it holds
    # is this one, and using it expends it -- there is correctly nothing to
    # trade. Driven by hand on a full level 6 wizard: p11035 goes back into
    # the book, p10145 comes out of it, and the +1 power bonus applies to
    # p10145 and to nothing else.
    "p7377": "swaps a prepared power for one in the book; the board deals no second one",
}


DID_SOMETHING = {
    "DamageApplied", "ConditionApplied", "Healed", "TempHP", "Moved",
    "ForcedMove", "RelationSet", "ZoneCreated", "EffectExpired", "Note",
    "Bloodied", "Dropped", "Died", "SavingThrow", "SkillCheck", "Summoned",
    "SurgeSpent", "ActionGranted",
}  # fmt: skip
# `ActionGranted` because "you can take an extra move action" is the
# whole printed content of a row, and `Cast.extra_action` used to add one
# to `Budget` and announce nothing -- so the row did exactly what its card
# says and was reported SILENT for it.
#
# **This set is hand-kept and the names are strings**, which is the same
# shape as two lint lists that shipped stale this week: rename an event
# class and the entry here goes quietly false, which reads as a row that
# does nothing. It cannot be *derived* -- deciding which events count as
# doing something is a judgement, and `AttackRolled` is the counter-example
# -- but it can be checked, and `main` refuses to run if a name here is
# not a declared event.
# `SurgeSpent` because a healing surge moving **is** the whole printed
# content of some rows -- "one ally loses a healing surge", "you gain
# two". Two correct item blocks were reported SILENT for doing exactly
# what their card says and nothing else.
# `SkillCheck` is here for the same reason `SavingThrow` is: a row whose
# printed content is "make a DC 25 check" has done the whole of what it
# says by rolling one, and failing is an outcome rather than a no-op.

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

#: A magic item block's ref: the item's own ref with a block on the end.
#: `i601x1` is its first Property, `i601p1` its first Power, and the two
#: are separate rows of the same object -- so one of them may need what
#: the other lays.
ITEM_BLOCK = re.compile(r"^(i\d+)[a-z]\d+[a-z]?$")

#: What a racial power puts in `cls`. A race is not a class and
#: `chargen.CLASSES` raises on one.
RACE_REF = re.compile(r"^r\d+$")
#: A theme's alias ref, which is what a theme power carries in `cls`.
THEME_REF = re.compile(r"^x\d+_\d+$")


def _event_names() -> set[str]:
    """Every event class the engine declares, by name.

    `DID_SOMETHING` is strings, and a string cannot go stale loudly.
    Rename an event and the entry here silently stops matching, so every
    row whose whole content is that event starts reporting SILENT and
    reads as unwritten.
    """
    from combat_engine.engine import events

    return {
        name
        for name, thing in vars(events).items()
        if isinstance(thing, type) and issubclass(thing, events.Event)
    }


def _is_trait(declared) -> bool:  # noqa: ANN001
    """Simply true of the creature: no action, and nothing to wait for.

    `turns.arm_traits_of` draws the line here and `audit` has to draw it
    in the same place, or the two disagree about which rows ever run.
    """
    return (
        declared is not None
        and declared.action is ActionType.NONE
        and not declared.triggers
    )


def _gates() -> dict[str, dict]:
    """Every feat's parsed prerequisite, by ref.

    Read once per process. `feat.prereq` is the only place a feat says
    which class, race and power it is written for -- `Power.cls` is empty
    on all 2,536 of them -- so the board has no other way to field one on
    a character that could have taken it.
    """
    import json

    if not _GATES:
        from combat_engine.etl.build import game

        for row in game().execute("SELECT ref, prereq FROM feat WHERE prereq IS NOT NULL"):
            node = json.loads(row["prereq"]) if row["prereq"] else None
            if node:
                _GATES[row["ref"]] = node
    return _GATES


_GATES: dict[str, dict] = {}


def _atoms(node: dict | None, key: str) -> list[str]:
    """Every value of one atom in a prerequisite tree, in printed order."""
    if not isinstance(node, dict):
        return []
    if key in node:
        return [node[key]]
    out: list[str] = []
    for group in ("all", "any"):
        for sub in node.get(group, ()):
            out += _atoms(sub, key)
    return out


def _item_blocks() -> dict[str, list[str]]:
    """Declared rows grouped by the item they are blocks of."""
    if not _BLOCKS:
        for other in REGISTRY:
            found = ITEM_BLOCK.match(other)
            if found:
                _BLOCKS.setdefault(found.group(1), []).append(other)
    return _BLOCKS


_BLOCKS: dict[str, list[str]] = {}


def _siblings(ref: str) -> list[str]:
    """The rows this one is printed beside, and cannot work without.

    Three shapes, and all three were invisible to a board that dealt the
    row under test and nothing else:

    * **a second card.** 354 rows are the second stat block of an entry
      whose first block is a row of its own -- `p5576b` is the rider on
      `p5576` and says so by its ref.
    * **a feat's named power.** 619 heroic feats gate on `{"ref": ...}`,
      which is the exact card the feat is a rider on. Fielded without it
      the feat has nothing to watch.
    * **an item's other blocks.** 1,265 item rows belong to an object that
      prints more than one -- `i2864p2` answers the mark `i2864p1` lays --
      and the two arrive together because they are one object.
    """
    out: list[str] = []
    parent = chargen.second_card(ref)
    if parent:
        out.append(parent)
    out += _atoms(_gates().get(ref), "ref")
    found = ITEM_BLOCK.match(ref)
    if found:
        out += _item_blocks().get(found.group(1), [])
    seen: list[str] = []
    for other in out:
        if other != ref and other in REGISTRY and other not in seen:
            seen.append(other)
    return seen


@dataclass
class Result:
    ref: str
    fired: int = 0
    error: str = ""
    events: set[str] = field(default_factory=set)

    @property
    def silent(self) -> bool:
        return not self.error and not (self.events & DID_SOMETHING)


def _weapon_words() -> dict[str, str]:
    """Every word a `requires_text` can name a weapon by, longest first.

    The same four things `query.holding` matches on -- a group, a property,
    a category, or the ref's own tail -- built from the 117 printed weapons
    rather than listed here, so a weapon added to the table becomes askable
    for without touching this.
    """
    out: dict[str, str] = {}
    for w in chargen.PRINTED.values():
        out.setdefault(w.ref.split(":", 1)[1].replace("-", " "), w.ref)
        if w.group:
            out.setdefault(w.group, w.ref)
        for prop in w.properties:
            out.setdefault(prop, w.ref)
    return dict(sorted(out.items(), key=lambda kv: -len(kv[0])))


_WEAPON_WORDS: dict[str, str] | None = None


def _hand_it_the_weapon(world: World, caster: int, declared: object) -> None:
    """Wield whatever the row's own Requirement says it needs.

    **257 rows name a weapon they need** -- a whip, a net, a bola, a light
    blade, something two-handed -- and the board dealt the build's default
    kit, so every one of them was gated false for the board's reason rather
    than its own. #209 counted twelve; it is twenty times that.

    **Both `requires_text` and `trigger`.** 184 rows say it in the
    Requirement and a further **73 say it only in the printed trigger** --
    "when you hit with a weapon attack using a net" is a gate on gear just
    as much as a Requirement is, and reading only the first left the net and
    whip proficiency feats UNUSED on a board that was now holding the net.

    Read off our own strings, not off the printed card. Both live in the
    tree beside the gate, in our words, so matching them is not parsing the
    book -- and the vocabulary is generated from the weapon table, so it
    cannot drift from what `query.holding` will accept.

    Longest match wins, which is the whole of the care needed: "light
    thrown" and "heavy thrown" both contain "thrown", and a bola is not a
    net.

    Cheap on purpose -- one equip at board time, **not** another dimension
    in `_attempts`. Gear variants there would multiply the 24 attempts a
    failing row already costs by the number of kits, and the failing tail is
    exactly where all of this instrument's time already goes.
    """
    global _WEAPON_WORDS

    from dataclasses import replace

    from combat_engine.engine import Gear
    from combat_engine.engine.query import holding

    wanted = " ".join(
        (getattr(declared, "requires_text", "") or "",
         getattr(declared, "trigger", "") or "")
    ).lower()
    if not wanted.strip():
        return
    if _WEAPON_WORDS is None:
        _WEAPON_WORDS = _weapon_words()
    gear = world.get(caster, Gear)
    if gear is None:
        return
    for word, ref in _WEAPON_WORDS.items():
        if word not in wanted:
            continue
        # Already satisfied by the build's own kit: a rogue has a dagger and
        # does not need a second one wielded over it.
        if holding(world, caster, word):
            return
        arm = chargen.PRINTED.get(ref)
        if arm is not None:
            # A copy, for the reason `chargen.spawn` takes one: these are
            # module-level singletons and `Cast.decay` reduces enhancement
            # in place.
            held = replace(arm)
            gear.weapons.append(held)
            gear.wield(held)
        return


def board(ref: str, seed: int) -> tuple[World, int, set[str]]:
    """A caster with the row, four creatures in reach, and the fight started.

    The third value is what got emitted while the encounter was starting,
    which is where a trait does its work.
    """
    world = World(Grid(24, 16), Rng(seed), Bus())
    declared = get(ref)
    named: list[str] = []

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
        # **`cls="item"` is not a class.** A magic item is a base item with
        # properties laid on top, so its rows belong to whoever is holding
        # it -- and boarding one as a character class put `"item"` straight
        # into `chargen.CLASSES` and raised, which is every row of the
        # weapon slot.
        carried = declared.cls == "item"
        # **A race is not a class either.** A racial power carries its race
        # in `cls` -- `r33` -- and `chargen.CLASSES[...]` raised on every
        # one of the 155 of them. The race is a `race=` on the character
        # and the class underneath it is free, so it takes the same
        # fighter-or-ranger fallback a classless row does.
        #
        # A racial *trait* says its race in its ref instead, `rt:r33-...`,
        # and carries no `cls` at all -- so it was being fielded on a
        # character of no race, which is the one thing a racial trait
        # needs.
        # By the shape of the ref, not by membership in `chargen.RACES`:
        # that holds the 46 a character may be, and `r67` is a race with
        # rows written for it that nobody can play. Fielded as a class it
        # raised; fielded as a race that does not exist it is a raceless
        # character, which is the honest answer.
        racial = bool(RACE_REF.match(declared.cls))
        # **Nor is a theme.** A theme power carries the theme's alias ref
        # in `cls` -- `x7_642` -- for exactly the reason a racial power
        # carries its race's: a printed name in that column would be a
        # leak. `chargen.CLASSES[...]` raised on every one of the 509 of
        # them, so the whole theme wave audited as broken rows rather
        # than as rows nobody could board. `wild talent` is the same
        # thing with no owner entity to alias, and is spelled in lower
        # case so it can never read as one of the 25 classes.
        #
        # Nothing selects a theme, so unlike a race there is nothing to
        # put on the character: it takes the classless fallback, which
        # is the honest answer for a row a character reaches by a route
        # that does not exist yet.
        themed = bool(THEME_REF.match(declared.cls)) or declared.cls == "wild talent"
        wears = ref[3:].split("-")[0] if ref.startswith("rt:") else declared.cls
        worn_race = wears if wears in chargen.RACES else ""
        gate = _gates().get(ref)
        # A feat carries no class of its own -- `Power.cls` is "" on all
        # 2,536 of them -- so this fell through to fighter or ranger every
        # time, and a feat printed "Prerequisite: cleric" was fielded on a
        # fighter that could never satisfy it. `feat.prereq` names the
        # class for 1,022 of them and every name it uses is a real one.
        gated = next((c for c in _atoms(gate, "class") if c in chargen.CLASSES), "")
        cls = (not carried and not racial and not themed and declared.cls) or gated or (
            "ranger" if declared.reach.kind in ("ranged", "area_burst") else "fighter"
        )
        # Its class features come too. A row that triggers on a *cursed*
        # enemy dropping needs the thing that curses, and a caster holding
        # only the row under test can never satisfy its own precondition.
        #
        # **Not for a race.** A class's level-0 rows are features, and
        # every one of them is true of the character at once. A race's are
        # the *one* racial power the page tells you to choose -- `r33`
        # prints seven and you take one -- so sweeping them all in deals a
        # character seven encounter powers it never had. `chargen.spawn`
        # already hands over what the race actually grants, off
        # `RaceLine.granted`.
        features = [] if racial else sorted(
            p.ref for p in REGISTRY.values() if p.cls == cls and p.level == 0
        )
        # **A feat goes in `feats=`, not in `powers=`.** Both end up in
        # `Powers.known`, so the difference is invisible until you look at
        # what reads the other field: `chargen.proficiency` hands over the
        # arms a feat grants and `chargen.power_swap` takes back the card
        # a feat trades for. Neither looks at `powers`, so the 54 feats
        # declaring `proficiency=("w:net",)` were audited on a character
        # that had never been given the weapon they exist to grant.
        a_feat = not carried and not declared.cls and ref.startswith("f")
        # And the race its prerequisite names, so `meets` and `c.build`
        # can answer honestly. A race is not dealt automatically for the
        # reason `Character.race` gives; naming one the card asked for is
        # a different thing.
        race = worn_race or next(iter(_atoms(gate, "race")), "")
        # **Not for a trait.** A trait is credited with whatever effect is
        # live on the caster after arming, and a granted sibling arms at
        # the same moment -- so a trait that installs nothing would pass
        # on its neighbour's work. Traits are never UNUSED anyway, which
        # is what siblings are here to fix.
        named = [] if _is_trait(declared) else _siblings(ref)
        # Siblings first, so a second card's parent is armed before it.
        hand = [*named, *features] if a_feat else [ref, *named, *features]
        caster = chargen.spawn(
            world,
            chargen.Character(
                cls, max(1, declared.level), hand,
                build=chargen.build_for(cls, ref),
                feats=[ref] if a_feat else [],
                race=race,
            ),
            (6, 8),
        )
        # The item itself, at the bottom rung of its ladder, so that a body
        # reading "equal to the enhancement bonus" has a number to read and
        # `Weapon.item` says which magic the carried weapon is.
        #
        # **Its own columns, not a guess.** This hardcoded `slot="weapon"`
        # and `enh_to="attack_damage"` for every item in the game, and only
        # 447 of the 2,491 item rows are weapon-slot -- so a suit of armour
        # was audited as a sword. Worse, `enh_to` decides which half of
        # `equipment.equip` runs: forcing `attack_damage` meant
        # `_defence_mods` had never run once in the whole audit, so no
        # armour or neck item had ever laid the bonus it exists for.
        if carried:
            from combat_engine.engine.components import Magic
            from combat_engine.engine.equipment import equip

            block = ITEM_BLOCK.match(ref)
            item = block.group(1) if block else ref.split("x")[0].split("p")[0]
            # A ref `game.db` does not carry still has to be fielded, or
            # the row reports unusable for the importer's reasons rather
            # than its own.
            magic = chargen.magic_for(item, powers=(ref, *named)) or Magic(
                ref=item, plus=1, powers=(ref, *named)
            )
            equip(world, caster, magic)
            # **And something to loose it with.** A quiver of magic arrows
            # on a two-blade ranger is never drawn -- `ammunition.nock`
            # asks what is in hand -- so every ammunition property
            # reported UNUSED for the board's reason rather than its own.
            # Exactly the `rba` case above: the build owns no bow.
            if magic.slot == "ammunition":
                from combat_engine.engine import Gear

                bow = chargen.launcher_for(next(iter(magic.base), ""))
                gear = world.get(caster, Gear)
                if bow is not None and gear is not None:
                    gear.weapons.append(bow)
                    gear.wield(bow)
        _hand_it_the_weapon(world, caster, declared)
        foe_team = Team.ENEMY

    from combat_engine.engine import Health

    # One of them undead, because a few rows only affect those and a board
    # without one makes them look silent when they are simply particular.
    # All four inside a close burst 2, which is the smallest area any row
    # here uses -- a creature one square outside it is no test at all.
    # And a fifth standing well back. All four of the above are inside a
    # close burst 2, which is right for testing an area and wrong for every
    # row that distinguishes near from far -- "enemies more than 5 squares
    # away", a ranged attacker, a row measuring the distance it closes. On
    # a board where every enemy is adjacent, those are silent while being
    # perfectly correct.
    for square, what in (
        ((7, 8), DUMMY), ((7, 9), UNDEAD), ((6, 9), DUMMY), ((5, 7), DUMMY),
        ((14, 8), DUMMY),
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
    # **And the caster riding something, which is the other half.** The
    # line above makes the caster a *mount*, so "its rider" works and
    # `c.mount()` is still None -- and "your mount" is the commoner
    # printed wording of the two. The second ally is the one carrying it,
    # so neither relation is a creature riding itself.
    world.relations.set(Relation.RIDDEN_BY, second, caster)

    # Where everybody was put, so setup can be undone. Several things
    # between here and the return move creatures -- the caster's own
    # class features, an ally's, a companion arriving -- and a board that
    # has walked its own pieces about measures itself rather than the row.
    # An ally ended up three squares from where it was placed, which took
    # "grant an ally a basic attack" from working to impossible.
    from combat_engine.engine.components import Position
    from combat_engine.engine.query import creatures as _everyone

    spawned = {
        e: world.get(e, Position).square
        for e in _everyone(world)
        if world.get(e, Position) is not None
    }

    # A companion, because the board had none and roughly sixty rows across
    # shaman and ranger read "your spirit companion" or "your beast". Every
    # one of them reported UNUSED or SILENT while being correct -- the
    # failure the silent check exists to catch, produced by the instrument
    # rather than the content. Placed two squares off so "adjacent to your
    # companion" and "not adjacent" are both reachable.
    if declared.cls:
        pet = Cast(world=world, me=caster, ref="audit:setup")
        companion = pet.call_companion(at=(5, 9))
        # And something for it to shake off, for the same reason the caster
        # has one: "your beast companion makes a saving throw" is a whole
        # row, and a companion with nothing save-ends on it rolls no dice.
        if companion:
            pet.effect("audit:setup pet hold", until=When.SAVE_ENDS, on=companion)

    # Its class features, up front. They only ever fired inside `_provoke`,
    # so a *triggered* row saw them and a standard-action row did not --
    # and a bard's aura, a warlock's curse and an avenger's oath are all
    # level-0 rows that later rows read. Three bard rows reported SILENT
    # because the aura their card hangs an effect on had never been raised.
    if declared.cls:
        foes_now = sorted(_foes(world, caster))
        if foes_now:
            _use_class_features(world, caster, foes_now[0], skip=ref)
        # And wound the ally again afterwards. A healing class feature --
        # a cleric's, a shaman's -- puts it back on its feet, and "one
        # bloodied ally" is a targeting restriction several rows carry.
        hurt_again = world.need(ally, Health)
        hurt_again.hp = max(1, hurt_again.max_hp // 2)

    # The caster is unseen by one enemy. A whole family of rows -- the
    # assassin's, and every lurker that only strikes what cannot see it --
    # gates on `HIDDEN_FROM`, and nothing on this board ever set it, so they
    # were refused outright. One creature rather than all of them, because
    # rows that need to *be* seen are just as real.
    unseen_by = sorted(_foes(world, caster))
    if unseen_by:
        world.relations.set(Relation.HIDDEN_FROM, caster, unseen_by[0])

    # A wall, so a row that needs cover or concealment has some. The board
    # was bare grid, so "one creature it is hidden from" could never be
    # satisfied and every such row reported itself unusable.
    world.grid.blocking.add((9, 8))
    # And a patch of rough ground, because "clear the difficult terrain"
    # had nothing to clear on a board where every square is smooth. Kept
    # away from the melee: the caster's only two free neighbours are
    # (6,7) and (7,7), and making those difficult cost a monster row its
    # one legal one-square shift. A close burst 1 therefore still cannot
    # reach any of this, which is why p15856 stays excused -- the two
    # wants are incompatible on one board and the shift is the commoner
    # shape.
    world.grid.difficult.update({(3, 10): "rough", (4, 10): "rough", (4, 11): "rough"})
    # And one dummy already burning, because several rows target "a creature
    # taking ongoing damage" and nothing on the board ever was.
    from combat_engine.engine.grid import spread
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

    # And one on the caster, because "Effect: make a saving throw" is a whole
    # shape of utility power and the caster had nothing to save against --
    # so a correct row rolled no dice and reported itself silent. A bare
    # labelled hold rather than a condition: dazing the caster would refuse
    # it a standard action and break every row that needs one.
    setup.target = caster
    setup.effect("audit:setup hold", until=When.SAVE_ENDS, on=caster)

    # A mark laid by the caster. "One creature marked by you" is the whole
    # target line of a defender's follow-up rows, and a board where the
    # caster had marked nobody made every one of them silent -- correct
    # rows, aimed at a creature that could not exist here. The defender
    # class features that would lay one are not written yet, so the board
    # lays it instead.
    if lined_up:
        setup.target = lined_up[0]
        setup.mark(on=lined_up[0], until=When.ENCOUNTER)

    # And one of them rattled, because three rogue rows target "an enemy
    # that is rattled" and the keyword only landed today -- so the rows are
    # correct and had nothing on the board to aim at.
    if lined_up:
        # The *penalty*, not the keyword. `c.rattling` makes your attacks
        # rattling; `c.rattled` asks whether a creature is suffering one,
        # which `c.suffering` matches by the hold's label.
        setup.target = lined_up[0]
        setup.penalty("attack", 2, on=lined_up[0], until=When.ENCOUNTER)
        rattle = setup.effect("rattled", until=When.ENCOUNTER, on=lined_up[0])
        del rattle

    # A zone, for the rows that target one. "One conjuration or zone" had
    # nothing to aim at.
    setup.target = None
    setup.zone(spread({(3, 10)}, 1), label="audit:setup zone", until=When.ENCOUNTER)

    # And one belonging to an **enemy**, because "one conjuration or zone
    # created by an enemy" is a different target line -- a row that dispels
    # one had only the caster's own to look at, which it correctly refused,
    # and so reported itself silent while being right.
    if lined_up:
        foe_zone = Cast(world=world, me=lined_up[0], ref="audit:setup foe zone")
        foe_zone.zone(
            spread({(9, 6)}, 1), label="audit:setup foe zone", until=When.ENCOUNTER
        )

    # Something in the room that is not a creature: a loose Medium object
    # and a campfire beside the caster. "One Medium or smaller object" and
    # "you must be adjacent to a fire of campfire size or larger" are
    # printed target and Requirement lines, and a bare board could satisfy
    # neither -- so the rows that read them reported unusable rather than
    # unwritten. Deliberately *not* put in the occupancy index: scenery
    # stands in its square without owning it, the way a conjuration does,
    # so the caster keeps both of its free neighbours for a one-square
    # shift. A second fire further off, because "teleport to a square
    # adjacent to a fire" is a different square from the one you are
    # standing beside.
    from combat_engine.engine.components import Ident, Position, Scenery
    from combat_engine.engine.types import Size

    for square, kind, size in (
        ((8, 9), "object", Size.MEDIUM),
        ((6, 7), "fire", Size.MEDIUM),
        ((12, 10), "fire", Size.LARGE),
    ):
        world.spawn(
            Ident(ref=f"audit:setup {kind}"),
            Position(square=square, size=size),
            Scenery(kind=kind),
        )

    # Bloodied, so a row gated on it can fire -- **on odd seeds only**.
    #
    # One board cannot answer both halves of this. Bloodying the caster is
    # what lets a row whose Requirement *is* "you must be bloodied" fire at
    # all, and it is also what makes every row whose Requirement is "you
    # must not be bloodied" unsatisfiable by construction -- the `f1347b`
    # family and about fifteen others, each reported UNUSED for a state
    # the instrument had chosen for them.
    #
    # So it is not one board: it is the seed. A seed is already "another
    # arrangement of the board, tried until the row can fire at all", and
    # `_attempts` stops the moment one works -- so this costs nothing for
    # a row that does not care and costs one extra board for a row that
    # does. Odd seeds keep the old behaviour, which is tried first,
    # because gating *on* bloodied is much the commoner shape.
    if seed % 2:
        caster_health.hp = max(1, caster_health.max_hp // 2 - 1)

    # One of the caster's own rows already spent, because "an expended
    # encounter power" and "an expended channel divinity power" are printed
    # target lines with nothing to name on a board where nobody has done
    # anything yet.
    #
    # **Only for the rows that ask.** Spending one unconditionally fixed
    # two rows and broke four -- a sibling this caster needed was the one
    # that got spent. The board cannot know which row matters, so it does
    # not guess: it looks at whether this row reads the expended list at
    # all, the way `_aims_at` reads a body to pick a blast origin.
    #
    # **Not a trait.** `Encounter.start()` arms every `action=NONE` row with
    # `spend=True` a few lines below, so a trait is on the expended list
    # either way and spending one here buys nothing -- while using up the
    # one deliberate spend the board gets. Class features sort before power
    # ids under `cf:`, so the moment a class gained its first `cf:` trait
    # the pick moved off the row that mattered: the invoker's channelled
    # invocation stopped being the expended one and the row that hands a
    # channelled use back reported silent while being correct.
    if _wants_expended(ref):
        mine = world.get(caster, Powers)
        for other in (mine.known if mine else []):
            spec = get(other)
            if other in (ref, mine.basic) or spec is None or spec.usage is Usage.AT_WILL:
                continue
            if spec.action is ActionType.NONE:
                continue
            mine.used[other] = mine.used.get(other, 0) + 1
            break

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
    # Back where they were put -- **after** arming, not before. Several
    # things between the spawns and here move creatures: the caster's own
    # class features, an ally's, and whatever a trait does as it arms. An
    # ally ended up three squares out of place, which took "grant an ally a
    # basic attack" from working to impossible. The companion is left where
    # it stands; it arrived after the snapshot and is not in it.
    for e, was in spawned.items():
        if world.get(e, Position) is not None:
            place(world, e, was)

    world.armed_effects = set(world.effects.live)
    armed = {e.kind for e in world.bus.log[mark:]} - START_NOISE
    world.turn = caster
    # Where the fight begins, which is **before** the opening initiative
    # rolls and not after them. `_fired` used to read the log from a
    # cursor taken after `start()` returned, and `turns._roll_initiative`
    # emits `InitiativeRolled` inside it -- so a row triggered on the roll
    # answered it correctly, was logged correctly, and then went unseen.
    # 28 rows could not be reported as working however well they worked.
    #
    # It is a second cursor rather than a move of the first, because the
    # two answer different questions. "Did this row go off?" wants the
    # whole fight. "What did it do?" for an ordinary row wants only what
    # followed its own use -- credited from the later cursor, or every row
    # in the tree would inherit the opening round's damage and conditions
    # and nothing could ever report SILENT again.
    world.fight_cursor = mark
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
    from combat_engine.engine.components import Budget, Powers
    from combat_engine.engine.movement import shift
    from combat_engine.engine.query import enemies

    def basic(eid: int) -> str:
        """Whatever *this* creature swings with. Hardcoding the generic melee
        basic meant every attack in here was refused as "not known", because
        a monster's basic is one of its own abilities."""
        known = world.get(eid, Powers)
        return known.basic if known else ""

    def probe() -> bool:
        """Has the row gone off yet? And re-arm the caster if it has not.

        **One immediate action per round is the printed rule, and this
        harness never advances the round.** So the first triggered row a
        creature owns eats the budget and every other one of its rows is
        refused for the whole run -- `m1279a3` answers `DamageApplied`
        and goes off during the opening pass, and `m1279a5` answers
        `Hit` and could not be offered afterwards however well it worked.
        It reported UNUSED, which reads as "this row cannot work" rather
        than "its neighbour spent the action first".

        The limit is a fight's, and this is not a fight: every row is
        fired on a board of its own, in isolation, and the one being
        measured is the one that matters. Re-arming between passes is
        the instrument getting out of its own way -- the row is still
        offered by the real dispatcher, against its real predicate, with
        its real Requirement.
        """
        if _fired(world, ref, cursor):
            return True
        budget = world.get(caster, Budget)
        if budget is not None:
            budget.immediate_round = -1
            budget.opportunity_turn = -1
        return False

    # Before anything is provoked at all: the row may already have gone
    # off during `Encounter.start()`. `InitiativeRolled` is announced
    # there, and a row that answered it has fired -- provoking it a
    # second time would credit it with the provocation's consequences on
    # top of its own.
    if probe():
        return True

    foes = [f for f in enemies(world, caster) if alive(world, f)]
    if not foes:
        return False

    _grip_for(world, caster, ref)

    from combat_engine.engine import Health

    # The two things every creature can do that nothing here ever did.
    # A second wind is 41 declared triggers and emits `SurgeSpent` (19
    # more) and `Healed` (9) on its way; an action point is 26. Ninety-odd
    # rows for two lines, and every one of them had reported UNUSED --
    # "this row cannot work" -- for want of being asked.
    #
    # The hit points go back afterwards. A second wind heals a surge, and
    # the board bloodies the caster on purpose so that a row gated on
    # being bloodied can fire at all: healing it here and leaving it
    # healed would quietly close that gate for every pass below.
    mine = Cast(world=world, me=caster, ref="audit:provoke")
    caster_health = world.get(caster, Health)
    was = caster_health.hp if caster_health is not None else 0
    mine.second_wind(on=caster)
    if caster_health is not None:
        caster_health.hp = was
    if probe():
        return True
    mine.action_point()
    if probe():
        return True

    # The rows this one is printed beside, used before any of the generic
    # passes. A second card answers its parent, a feat answers the power
    # its prerequisite names, and an item's second block answers its
    # first -- none of which any amount of swinging and walking produces.
    _use_rows(world, caster, _siblings(ref), foes[0], skip=ref)
    if probe():
        return True

    # Put the caster in the state its own class puts it in first. A
    # warlock's pact boon triggers on a *cursed* enemy dropping, and a
    # harness that only swings and walks can never curse anybody -- so
    # three correctly written rows reported themselves unusable.
    _use_class_features(world, caster, foes[0])
    if probe():
        return True

    if _rolls_checks(world, caster, ref, cursor):
        return True

    # Bloodied as a **crossing**, not as a state. The board starts the
    # caster below half so that a row *gated* on being bloodied can fire --
    # which means the threshold is already behind it and `Bloodied` is
    # never announced during the run. Sixty-one rows fire on that event and
    # not one of them had ever been exercised: each reported UNUSED, which
    # reads as "this row cannot work" rather than "the board never asked".
    # The death pass below is no substitute -- it takes a creature from
    # full to well past 0 in a single blow.
    # Everybody in turn, not just the caster: "when an ally within 3 is
    # bloodied" is a printed trigger too, and which creature is close
    # enough to count is the board's business rather than this loop's.
    for victim in (caster, *foes[:3], *_allies_of(world, caster)):
        health = world.get(victim, Health)
        if health is None or health.max_hp < 4 or not alive(world, victim):
            continue
        health.hp = health.max_hp
        # An enemy does the bloodying where it can. "When an enemy bloodies
        # you" is a printed trigger, and the caster bloodying itself would
        # make `source` itself and read false.
        killer = foes[0] if victim != foes[0] else caster
        world.damage(killer, victim, health.max_hp // 2 + 1)
        if probe():
            return True


    # Somebody swings at the caster, the caster swings back, and -- the one
    # this harness could never arrange -- an enemy swings at an *ally*. A
    # leader's whole job is answering that, and "an enemy attacks an ally"
    # is the printed trigger on nine bard rows alone. Without it they report
    # UNUSED, which reads as "this row cannot work" rather than "the board
    # never asked it to".
    pairs = [(foes[0], caster), (caster, foes[0])]
    for mate in _allies_of(world, caster)[:2]:
        # Both directions: "an enemy attacks an ally" and "an ally misses
        # with a melee attack" are both printed triggers, and whether the
        # swing hits or misses is what the seed sweep in `_attempts` is for.
        pairs += [(foes[0], mate), (mate, foes[0])]
    for attacker, target in pairs:
        if not alive(world, target):
            continue
        use(world, attacker, basic(attacker), targets=[target], spend=False)
        if probe():
            return True

    # Shoved about. "When you are pushed, pulled or slid" and "when an enemy
    # knocks you prone" are printed triggers, and a harness that only swings
    # and walks produces neither -- so the rows reported UNUSED while being
    # perfectly correct.
    shove = Cast(world=world, me=foes[0], ref="audit:provoke")
    shove.target = caster
    for move in (shove.push, shove.pull, shove.slide):
        move(2, on=caster)
        if probe():
            return True
    shove.prone(on=caster)
    if probe():
        return True

    # A point of damage of each printed type, dealt by an enemy. "When you
    # take cold damage", "the first time you take fire damage each round"
    # and the whole family of resistances and answers are printed triggers,
    # and **every blow this harness strikes is an untyped melee basic** --
    # so not one of them had ever been asked. One point rather than a
    # blow, because the trigger is the type and not the number, and a real
    # hit here would drop the caster before the passes below.
    for kind in DamageType:
        if kind is DamageType.UNTYPED:
            continue
        hurt = caster_health.hp if caster_health is not None else 0
        world.damage(foes[0], caster, 1, kind)
        # And straight back. Eleven types is eleven points, which is most
        # of a level 1 caster already bloodied on purpose -- so the loop
        # would kill the creature the passes below are about.
        if caster_health is not None:
            caster_health.hp = hurt
        if probe():
            return True

    # A burst or a blast of its own. "When the m5027 hits with a close or
    # area attack" is a common enough shape, and a harness that only ever
    # swings a basic can never produce one.
    #
    # Both directions, for the same reason the basic pass runs both ways:
    # "when an enemy hits you with a close or area attack" is a printed
    # trigger too, and the caster's own bursts can never satisfy it.
    for other in _area_rows(world, caster, ref):
        use(world, caster, other, spend=False)
        if probe():
            return True
    for other in _area_rows(world, foes[0], ref):
        use(world, foes[0], other, spend=False)
        if probe():
            return True
    for foe in foes[:2]:
        for sq in sorted(world.reachable_squares(foe, 1)):
            shift(world, foe, sq)
            if probe():
                return True

    # An opportunity attack, swung by hand in both directions. Walking out
    # of reach opens the window and nothing comes of it: the engine never
    # decides what goes into one -- a policy does, and this board installs
    # none, which is why `m3014a2` is on `KNOWN_SILENT`. "When it makes an
    # opportunity attack" and "when one is made against it" are printed
    # triggers on a dozen rows, every one of which reported UNUSED.
    for attacker, target in ((caster, foes[0]), (foes[0], caster)):
        if not alive(world, target):
            continue
        use(
            world, attacker, basic(attacker), targets=[target],
            spend=False, opportunity=True,
        )
        if probe():
            return True

    # Somebody goes down. Several rows trigger on a creature dropping --
    # a leader's rally, the warlock's pact boons -- and attacking and
    # walking about can never produce one, so the harness had no way to
    # reach them and reported every one of them unusable.

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
        # A foe swings the killing blow, not the caster. Killing the caster
        # *with the caster* made `source` itself, so "an enemy reduces you
        # to 0 hit points" -- a printed trigger on several rows -- could
        # never be true, and the row reported UNUSED as though it were
        # unwritable rather than unasked.
        killer = foes[0] if victim == caster else caster
        world.damage(killer, victim, health.hp + health.max_hp)
        if probe():
            return True
    return _fired(world, ref, cursor)



def _wants_expended(ref: str) -> bool:
    """Does this row read what the caster has already used up?"""
    import inspect

    declared = REGISTRY.get(ref)
    if declared is None:
        return False
    with contextlib.suppress(OSError, TypeError):
        body = inspect.getsource(declared.body)
        return "expended" in body or "restore_use" in body
    return False

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
    """Event kinds this row emitted, bounded at both ends.

    A triggered row is fired by provoking it, and the provocation is an
    attack -- which drops creatures, applies conditions and expires effects
    on its own account. Everything before the row ran is the provocation's.

    **What is after it is not all the row's**, which is what this used to
    assume and is #216. `resolve.attack` only rolls and announces `Hit`;
    the attacking power's body deals the damage *after* `attack()` returns,
    so for a row answering `Hit` the harness's own `DamageApplied`,
    `Bloodied`, `Dropped` and `Died` are all logged **after** the row's
    `PowerUsed`. Running to end-of-log credited the row with being attacked.

    So the right end is bounded by **`Event.depth`**, which `Bus.emit`
    already stamps on everything: the row's own events sit at the same depth
    as its `PowerUsed` -- `cast.used()` completes before the body runs -- and
    a nested `use()` inside the body emits deeper. The provocation resumes
    at a *shallower* depth once the trigger window unwinds, so the first
    event below the row's own depth is where the row stops and the attack
    that provoked it carries on.

    That costs nothing: no extra board, no engine change, and the field was
    there the whole time.
    """
    log = world.bus.log[cursor:]
    for i, e in enumerate(log):
        if e.kind == "PowerUsed" and getattr(e, "power", None) == ref:
            mine = getattr(e, "depth", 0)
            out: set[str] = set()
            for x in log[i + 1:]:
                if getattr(x, "depth", 0) < mine:
                    break
                out.add(x.kind)
            return out
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


def _rolls_checks(world, caster: int, ref: str, cursor: int) -> bool:  # noqa: ANN001
    """Roll skill checks, for a row whose printed trigger is one.

    Nine rows answer a `SkillCheck` -- "you dislike the result", "an ally
    succeeds", "you or one ally fails" -- and a harness that only swings,
    shoves and walks rolls none, so every one of them reported UNUSED while
    being perfectly correct. Both outcomes are produced: a DC of 1 is beaten
    by any roll and a DC of 99 by none.

    Gated on the row actually watching the event, because the pass is 17
    skills by two DCs by two rollers and running it for every triggered row
    in the tree would be most of the audit's time.
    """
    from combat_engine.engine import Movement
    from combat_engine.engine.events import SkillCheck
    from combat_engine.engine.skills import SKILLS
    from combat_engine.engine.skills import check as roll

    declared = get(ref)
    if declared is None or not any(
        t.event is SkillCheck for t in declared.triggers
    ):
        return False

    # Climbing throughout. `Movement.using` is what a creature is doing
    # rather than what it can do, nothing on this board ever climbs, and one
    # row's trigger is an Athletics check made while on a wall.
    moves = world.get(caster, Movement)
    was = moves.using if moves is not None else ""
    if moves is not None:
        moves.using = "climb"
    try:
        for roller in (caster, *_allies_of(world, caster)[:1]):
            for dc in (1, 99):
                for skill in sorted(SKILLS):
                    roll(world, roller, skill, dc)
                    if _fired(world, ref, cursor):
                        return True
    finally:
        if moves is not None:
            moves.using = was
    return False


def _grip_for(world, caster: int, ref: str) -> None:  # noqa: ANN001
    """Draw a weapon this row can actually be used with, before provoking it.

    `_use_with_any_grip` does this for rows the harness uses directly, and
    the triggered path had no equivalent: it went straight to the dispatcher,
    which refuses a ranged weapon row while the blades are out. The board's
    bard holds a mace, so **every triggered ranged-weapon row in the tree**
    reported UNUSED -- indistinguishable from a row that cannot fire at all,
    which is what this instrument exists to tell apart.
    """
    from combat_engine.engine import Gear
    from combat_engine.engine.dsl import REGISTRY

    power = REGISTRY.get(ref)
    gear = world.get(caster, Gear)
    if power is None or gear is None or len(gear.weapons) < 2:
        return
    if power.can_branch(world, caster):
        return
    for weapon in gear.weapons:
        gear.wield(weapon)
        if power.can_branch(world, caster):
            return


def _aims_at(world, caster: int, ref: str) -> list[Square]:  # noqa: ANN001
    """Where to point a blast or an area burst so it catches somebody.

    `area_of` falls back to the first square in sorted order, which for a
    close blast is always up and to the left -- so every blast row in the
    tree had only ever been fired in one direction, and a row that only
    affects undead reported itself silent because the board's undead
    stands the other way. Aimed at whichever legal origin catches the most
    creatures, which is what a player would do.
    """
    from combat_engine.engine.dsl import aim_points, candidates

    p = REGISTRY.get(ref)
    if p is None or p.reach.kind not in ("close_blast", "area_burst"):
        return []
    spots = aim_points(world, caster, p)
    if not spots:
        return []
    # Best first, so the commonest case costs one try. Several rather than
    # one, because "the most creatures" is not "the right creatures": a row
    # that only affects undead wants the blast pointed at the board's one
    # undead, and the fullest blast points the other way.
    # Ranked by **enemies** caught, not creatures. A board whose allies
    # cluster one way and whose enemies stand the other pointed every
    # blast at the allies, which is both the wrong reading of the card and
    # the reason a row that only affects the board's one undead reported
    # itself silent.
    foes = set(_foes(world, caster))
    ranked = sorted(
        spots,
        key=lambda sq: -len(foes & set(candidates(world, caster, p, origin=sq))),
    )
    return ranked[:4]


def _use_with_any_grip(world, caster: int, ref: str) -> bool:  # noqa: ANN001
    """Use the row, drawing a different weapon first if that is what it needs.

    A creature holds one legal grip at a time, so a bow is on the belt while
    the blades are out. A ranged row is not unusable then -- it is one minor
    action away, which is exactly what a player would spend. Trying each
    grip is the difference between "this row does not work" and "this row
    needs the other weapon".
    """
    from combat_engine.engine import Gear

    aims = _aims_at(world, caster, ref) or [None]
    for aim in aims:
        if use(world, caster, ref, origin=aim):
            return True
    gear = world.get(caster, Gear)
    if gear is None or len(gear.weapons) < 2:
        return False
    for weapon in gear.weapons:
        gear.wield(weapon)
        for aim in aims:
            if use(world, caster, ref, origin=aim):
                return True
    return False


def _use_class_features(world, caster: int, foe: int, skip: str = "") -> None:  # noqa: ANN001
    """Fire the caster's own level-0 rows -- its curse, its quarry, its mark."""
    from combat_engine.engine.components import Powers

    known = world.get(caster, Powers)
    if known is None:
        return
    _use_rows(
        world, caster,
        [r for r in known.all if (p := get(r)) is not None and p.level == 0],
        foe, skip=skip,
    )


def _nearest_foe(world, caster: int) -> int | None:  # noqa: ANN001
    """Somebody to point a row at, or None on a board with nobody left."""
    standing = [f for f in sorted(_foes(world, caster)) if alive(world, f)]
    return standing[0] if standing else None


def _use_rows(world, caster: int, refs: list[str], foe: int | None, skip: str = "") -> None:  # noqa: ANN001
    """Use these rows on the caster's behalf, and put the board back.

    Split out of `_use_class_features` because the sibling pass wants the
    same three things it does: a target for an attack row, the trait and
    triggered rows left alone, and every creature returned to the square
    it was placed in.
    """
    from combat_engine.engine.components import Position
    from combat_engine.engine.movement import place

    # Everybody's square, not just the caster's. A level-0 row that slides
    # or teleports an *ally* moves it too, and one did: firing the warlord's
    # features walked an ally from (5,8) to (2,5), so no ally was adjacent
    # to an enemy any more and "grant an ally a basic attack" -- a whole
    # warlord shape -- could not land at all. The caster half of this was
    # fixed an hour ago and the ally half was not, which is the same bug
    # twice.
    from combat_engine.engine.query import creatures

    stood = {
        e: world.get(e, Position).square
        for e in creatures(world)
        if world.get(e, Position) is not None
    }
    for other in list(refs):
        p = get(other)
        # Not a trait, and not a row that waits for a trigger either: a
        # triggered feature called directly gets no event to answer, returns
        # at its first line, and is then counted as having fired -- which
        # short-circuits the provocation that would have exercised it
        # properly. `_area_rows` already makes the same exclusion.
        # Never the row under test. A level-0 row fired during setup has
        # already spent whatever it arms -- the assassin's shrouds, the
        # druid's companion call -- so firing it again measures the
        # leftovers and reports the row silent.
        if other == skip or p is None or _is_trait(p) or p.triggers:
            continue
        if p.is_attack and foe is None:
            continue
        with contextlib.suppress(Exception):
            use(world, caster, other, targets=[foe] if p.is_attack else None, spend=False)
        # **And undo it if it took the caster off the board.** `p10046`
        # is a level-0 minor action that removes its owner until the
        # start of its next turn; fired during setup it left a character
        # that could not act, so all six of that race's other rows
        # reported UNUSED and the fault read as theirs. Three agents
        # found it separately. Only what this row laid is unwound --
        # an effect's label is the ref of the row that laid it -- so a
        # daze the board put there on purpose stays.
        if not can_act(world, caster):
            for eff in list(world.effects.live.values()):
                if eff.owner == caster and eff.label.split(" ")[0] == other:
                    world.effects.end(eff, "audit:setup would not be able to act")
    # Put it back where it was standing. The rogue's level 0 is nine at-will
    # *move* utilities, and firing them walked the caster from (6,8) to
    # (0,1) -- seven squares from the nearest foe -- so the provocation that
    # follows never reached it and every triggered rogue row reported
    # UNUSED. The instrument was measuring its own setup.
    for e, was in stood.items():
        if world.get(e, Position) is not None:
            place(world, e, was)


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


def _calls(symbols: list[str]) -> list[str]:
    """Rows that touch a named verb, plus the rows waiting for one.

    **For adding a verb, not for changing what one means.** `_changed`
    widens to all 12,197 rows the moment anything under `engine/` moves,
    which is right when a change moves every row at once -- a different
    attack resolution, a different arming order -- and far too wide for
    the commonest engine change there is, which is a new `Cast` method
    nothing called yesterday. A new verb can only reach a row that calls
    it, and that is a fact about the text.

    Two sets, because they fail differently:

    * rows whose **source** names it, which is the regression risk;
    * rows whose `todo=`/`dropped=` **marker** names it, which is the
      sweep -- those are the rows that should go from refused to firing,
      and auditing them is how you find out whether they did.

    The caveat is the whole of the honesty here: this is blind to a row
    that changes behaviour **without naming the verb** -- one calling
    something else that now routes through it, or reading state the verb
    writes. So a narrowed run is evidence a verb works, never evidence
    that nothing else broke. When a change is not purely additive, take
    the wide run and pay for it.
    """
    import inspect

    needles = [s.split("(")[0].strip() for s in symbols]
    needles = [n for n in needles if n]
    out: list[str] = []
    for ref, p in REGISTRY.items():
        if any(n in want for n in needles for want in p.unfinished):
            out.append(ref)
            continue
        body = getattr(p, "body", None)
        if body is None:
            continue
        try:
            source = inspect.getsource(body)
        except (OSError, TypeError):
            continue
        if any(n in source for n in needles):
            out.append(ref)
    return sorted(set(out))


def _changed() -> list[str]:
    """Rows declared in files that differ from HEAD.

    At about 160ms a row, auditing all 12,197 is **half an hour serial
    and around ten minutes across ten cores** -- the estimate this said
    when it was written ("twenty seconds today, five minutes once PHB1 is
    written") was overtaken long ago. Most runs have touched a handful of
    rows and re-firing the other twelve thousand buys nothing, which is
    exactly how the first attempt's suite grew until nobody could afford
    to run it.

    The cost is all in the tail: `_attempts` gives up as soon as a row
    fires, so a working row costs **one** board and a row that never
    fires costs all **24** -- three gear faces by eight seeds. The rows
    this instrument exists to find are the ones it spends its time on.

    **Do not try to tune the pool; it has been measured and there is
    nothing there.** On the 4-performance-plus-6-efficiency-core machine
    this was written on, `chunksize=8` across ten workers looked like the
    obvious suspect -- six workers a third as fast, and a pre-partitioned
    chunk landing on one stalls the whole map. Over a fixed 600-row sample:

        jobs 10, chunksize 8  (current)   40.8s
        jobs 10, chunksize 1              42.8s
        jobs 4 / 8 / 14 / 20              68.9 / 51.8 / 53.6 / 62.7s

    and repeat runs of the *same* config vary by 15%, so the first result
    was noise. The current setting is the best available. **Make the sweep
    rare, not fast**: `--verdicts` for the verdict itself, `--sample` for a
    direction, `--calls` for a new verb, `--changed` otherwise.

    An engine change that moves every row at once is not narrowable, so
    touching `engine/` widens this back to everything. **But most engine
    changes are additive** -- a new `Cast` verb nothing called yesterday
    -- and for those `--calls` is the narrow run, because a row can only
    use a verb by naming it. See `_calls`, including what it is blind to.
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


@contextlib.contextmanager
def hollowed(ref: str):  # noqa: ANN201
    """Run with this row's body replaced by one that does nothing.

    **The negative control.** A row is supposed to be credited with what
    *it* did, so replacing only its body must take all of its credit away:
    the offer still happens, the budget is still spent, `PowerUsed` is
    still emitted, and the log differs from the positive run by exactly the
    row's own output. Anything still credited afterwards was never the
    row's.

    Preferred over flipping `Trigger.when` or returning `""` from
    `world.decider`, both of which stop the row being *offered* and so
    change the shape of the run. This also works for a trait, which neither
    of those reaches: a trait is armed through `dsl.use` and never offered.

    Restores in a `finally` and it matters: `REGISTRY` is module-global and
    a pool worker handles about eight refs per chunk, so a leaked swap
    would quietly hollow somebody else's row.
    """
    p = get(ref)
    if p is None:
        yield
        return
    was = p.body

    def nothing(c: Cast) -> None:
        """Deliberately empty. See `hollowed`."""

    p.body = nothing
    try:
        yield
    finally:
        p.body = was


#: Rows with a **known** correct answer, for developing the verdict itself.
#:
#: Every one of these is run twice: as written, and `hollowed` -- its body
#: replaced by one that does nothing. The invariant is the whole of #216:
#:
#:     a row that does nothing must never report `ok`
#:
#: which needs no hand-edited gate and no judgement about what each row
#: ought to do. Chosen to cover every path through `audit`: a trait, a
#: `Hit`-triggered row, an ordinary attack, a burst, a mover, a healer.
#:
#: `f1305` is #216's own example -- the row whose gate was flipped to a
#: nonsense value by hand and which still reported
#: `ok  ConditionApplied, DamageApplied`.
VERDICT_ROWS = (
    "f1305",     # the issue's example: watches Hit from its body
    "f2206",     # a trait laying a standing modifier
    "f2896",     # a trait laying a conditional one
    "p14271",    # an ordinary melee attack
    "p14262",    # a close burst that lays resist and vulnerability
    "mba",       # the engine's own melee basic
    "rba",       # and the ranged one
    "p1333",     # an attack whose damage rides on the attack ability
)

#: Rows that **must** report silent, because the board cannot satisfy them.
#:
#: The other half of the fixture, and the half that proves the verdict has
#: not simply been loosened: #204 established that these are gated on a
#: two-weapon build the audit board never deals, so they install nothing
#: here. Before the verdict was fixed both reported `ok`, credited with the
#: board's own setup -- "a genuinely broken trait is currently
#: indistinguishable from these", as that issue put it. If either ever
#: reports credit again, the window has been widened back.
VERDICT_SILENT = (
    "f172",
    "f139",
)


def verdicts(refs: tuple[str, ...] = VERDICT_ROWS) -> list[str]:
    """Check the verdict against rows whose right answer is known.

    Seconds rather than the ten minutes a full sweep costs, which is the
    point: `audit.py` is in `WIDE`, so every edit to it widens `--changed`
    back to all 12,197 rows and there is otherwise no way to iterate on the
    verdict at all.

    Returns the complaints. Empty is good.

    **This is the enforcement point, and deliberately not `audit` itself.**
    #216 suggests running the control for every row. Two reasons not to:
    it costs one extra board per row that fires -- about a quarter on top
    of a full sweep, which is the cost this file has just been taught to
    avoid -- and, worse, it is not sound in general. `out.events` is a
    **union across attempts** (`_attempts` stops as soon as a row shows
    itself, a hollowed row never does), so a hollowed run explores all 24
    attempts where the live run may have stopped at one, accumulates a
    larger set of nearby noise, and subtracting it could take away credit
    the row had genuinely earned.

    Against a pinned list that hazard is answerable by reading the result,
    which is why the control lives here. The attribution fixes in
    `_after_its_own_use` and the trait branch are what make the ordinary
    verdict honest; this is what stops them being quietly widened again.
    """
    wrong: list[str] = []
    for ref in refs:
        if get(ref) is None:
            wrong.append(f"{ref} is not a declared row")
            continue
        live = audit(ref)
        with hollowed(ref):
            dead = audit(ref)
        if live.error:
            wrong.append(f"{ref} raises as written: {live.error.strip()[-200:]}")
        # The invariant. A hollowed row emits its `PowerUsed` and nothing
        # else, so anything in `DID_SOMETHING` here is credit the row did
        # not earn -- the harness's own provocation, or the board's setup.
        if not dead.silent:
            wrong.append(
                f"{ref} still credited with "
                f"{', '.join(sorted(dead.events & DID_SOMETHING))} "
                f"after its body was emptied"
            )
        # And the positive half, so the check cannot pass by crediting
        # nothing to anybody.
        if live.fired and live.silent and ref not in KNOWN_SILENT:
            wrong.append(f"{ref} is credited with nothing as written")
    for ref in VERDICT_SILENT:
        if get(ref) is None:
            wrong.append(f"{ref} is not a declared row")
            continue
        got = audit(ref)
        if not got.silent:
            wrong.append(
                f"{ref} is credited with "
                f"{', '.join(sorted(got.events & DID_SOMETHING))}, "
                f"but the board cannot satisfy it -- see VERDICT_SILENT"
            )
    return wrong


def audit(ref: str) -> Result:
    out = Result(ref=ref)
    declared = get(ref)
    # A trait is armed by `Encounter.start`, not taken as an action, so by
    # the time the board is built it is already in force and using it again
    # is correctly refused. Firing it a second time would report every trait
    # in the game as unusable, which is the instrument lying about the fix.
    #
    # **A row with a trigger is not a trait, whatever its action costs.**
    # This read `action is ActionType.NONE` alone, and the `if trait:`
    # branch below returns before the triggered branch is ever reached --
    # so every `action=NONE` row carrying a printed trigger was counted as
    # fired on the strength of board *setup*, and its body never ran once.
    # A body that raised outright still reported "fires and does
    # something". The whole feat corpus is written in exactly that shape,
    # so this was the gate on roughly four hundred rows and it was open.
    # `turns.arm_traits_of` has always drawn the line in the right place:
    # a trait is `action=NONE` **with no trigger**.
    trait = (
        declared is not None
        and declared.action is ActionType.NONE
        and not declared.triggers
    )
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
            world, caster, _armed = board(ref, seed)
            world.rng.loaded = face
            if not (trait or triggered):
                # The rows this one is printed beside, **before** the
                # cursor. A second card's parent, the power a feat's
                # prerequisite names, an item's other block: each has to
                # have happened for the row to have anything to answer,
                # and none of it is the row's own work -- so it belongs
                # on the far side of the line the events are counted from
                # or every such row would pass on its sibling's doing.
                _use_rows(world, caster, _siblings(ref), _nearest_foe(world, caster),
                          skip=ref)
            cursor = len(world.bus.log)
            # Asking whether *any* effect was live was unconditionally true
            # -- the board burns a dummy -- so a row that installed nothing
            # at all still counted as having done something, and the silent
            # check could never fire through this branch.
            had = set(world.effects.live) if not (trait or triggered) else world.armed_effects
            if trait:
                out.fired += 1
                # **Its own arming, not the whole of setup.** This was
                # `armed` -- every event between the spawns and the end of
                # `Encounter.start()`, minus three noise kinds -- which is
                # every creature's traits arming, the initiative rolls and
                # whatever the board did to dress itself. So a trait that
                # installed nothing was credited with its neighbours' work,
                # which is #216's second half and #204's first.
                #
                # The same depth-bounded slice the triggered branch uses,
                # from this trait's own `use()`. `dsl.use` emits `PowerUsed`
                # while arming, so there is a mark to find.
                mine_now = _after_its_own_use(world, ref, world.fight_cursor)
                dealt_now = any(
                    str(getattr(e, "detail", "") or "").startswith(ref)
                    for e in world.bus.log[world.fight_cursor:]
                    if e.kind in ("DamageRolled", "DamageApplied")
                )
                out.events |= (mine_now - PROVOKE_NOISE) | (
                    {"DamageApplied"} if dealt_now else set()
                )
                # A trait's effect was installed by arming, so it is measured
                # against the board before that.
                #
                # **By label, not by `source`.** `e.source == caster` is the
                # caster's *entity*, and its class features arm at the same
                # moment and are sourced to it too -- so a trait that
                # installed nothing was credited with an effect one of its
                # neighbours laid. `durations.keywords_of` records the
                # convention this relies on: an effect's label is the ref of
                # the row that laid it, stamped by `c.effect`, `c.bonus` and
                # `c.condition` alike. Prefix, because several sites stamp
                # `"<ref> trigger"` or `"<ref> on attack"`.
                mine_eff = {
                    i for i, e in world.effects.live.items()
                    if str(e.label or "").startswith(ref)
                }
                if mine_eff - world.setup_effects:
                    out.events.add("ConditionApplied")
                continue
            if triggered:
                # From the top of the fight, not from here. The dispatcher
                # is armed inside `Encounter.start()` and the opening
                # `InitiativeRolled` is announced there, so a row that
                # answers one has already fired by the time this line runs.
                cursor = world.fight_cursor
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
                # **Damage this row dealt, by name.** `PROVOKE_NOISE` drops
                # both damage kinds wholesale -- it has to, the provocation
                # is an attack -- so a triggered row whose whole content is
                # damage reported silent however well it worked. `detail` is
                # the channel: `Cast.damage` stamps `detail or self.ref`.
                #
                # **Prefix, not equality.** `half_damage` stamps
                # `"<ref> (half)"`, `absorb` `"<ref> (absorbed)"` and a zone
                # burn `"<ref> zone"`, so `== ref` missed every one of them.
                dealt = any(
                    str(getattr(e, "detail", "") or "").startswith(ref)
                    for e in world.bus.log[cursor:]
                    if e.kind in ("DamageRolled", "DamageApplied")
                )
                # Parenthesised. `-` binds tighter than `|`, so the old
                # `mine - PROVOKE_NOISE | (mine & {"DamageApplied"})` read as
                # `(mine - PROVOKE_NOISE) | (mine & {"DamageApplied"})` --
                # re-crediting **any** DamageApplied in the window whoever
                # dealt it, and making the `detail` test above dead code.
                # That one line is why #216's `f1305` reported
                # `ok  ConditionApplied, DamageApplied` with its gate false.
                out.events |= (mine - PROVOKE_NOISE) | (
                    {"DamageApplied"} if dealt else set()
                )
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
    ap.add_argument("--verdicts", action="store_true",
                    help="check the verdict against rows whose right answer is "
                         "known. Seconds, and the only way to iterate on "
                         "audit.py itself -- see `verdicts`")
    ap.add_argument("--sample", type=int, metavar="N",
                    help="a deterministic random N rows. For seeing whether a "
                         "number moved before paying for the exact one")
    ap.add_argument("--calls", action="append", metavar="SYMBOL",
                    help="only rows whose source or whose todo=/dropped= "
                         "marker names this verb; repeatable. For adding a "
                         "verb -- see `_calls` for when it is not enough")
    ap.add_argument("--jobs", type=int, default=0,
                    help="worker processes; 0 picks one per core, 1 stays serial")
    args = ap.parse_args()

    if args.verdicts:
        wrong = verdicts()
        for line in wrong:
            print(f"  FAIL  {line}")
        total = len(VERDICT_ROWS) + len(VERDICT_SILENT)
        print(f"\n{total - len(wrong)} of {total} pinned rows verdict correctly")
        return 1 if wrong else 0

    wanted = args.refs or (
        _calls(args.calls) if args.calls
        else _changed() if args.changed
        else sorted(REGISTRY)
    )
    if args.sample and not args.refs:
        import random

        # Seeded, so two runs compare. A moving sample cannot show a number
        # moving.
        wanted = sorted(random.Random(0xA0D17).sample(wanted, min(args.sample, len(wanted))))
        print(f"# a {len(wanted)}-row sample of {len(REGISTRY)}. For a "
              f"direction, not a number.\n")
    if args.calls and not args.refs:
        print(f"# {len(wanted)} row(s) name {', '.join(args.calls)} -- in their "
              f"source or in a marker. --all is {len(REGISTRY)}.\n"
              f"# Blind to a row that changes without naming it, so this is "
              f"evidence the verb works, not that nothing else broke.\n")
    if args.changed and not args.refs:
        print(f"# {len(wanted)} row(s) in changed files. "
              f"--all is {len(REGISTRY)} and takes about "
              f"{len(REGISTRY) * 0.05:.0f}s across ten cores.\n"
              f"# Adding a verb? `--calls <symbol>` is seconds.\n")
    chosen: list[str] = []
    inert: list[str] = []
    partial: list[tuple[str, tuple[str, ...], str]] = []
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
        if p.todo:
            # Declared unfinished. `usable` refuses it, so firing it here
            # would only prove the refusal works -- and reporting it SILENT
            # would drown the real ones. Not fired, and **never counted
            # OK**: a marker that could pass the audit is a marker that
            # lets a class look finished by declaring that it is not.
            partial.append((ref, p.todo, "TODO"))
            continue
        if p.dropped:
            # A row that works with one clause missing. Unlike `todo` it
            # **is** fired, because the part that works has to be checked
            # like anything else -- but it is reported beside the `todo`
            # rows rather than counted done, because the clause that is
            # gone is gone whether or not the rest of it passes.
            partial.append((ref, p.dropped, "DROP"))
        if p.out_of_combat:
            # Declared inert. A cantrip that lights a torch is not a silent
            # power, it is a power with nothing to say in a fight.
            inert.append(ref)
            continue
        chosen.append(ref)

    refused = _decisions_are_honoured()
    # An excuse for a ref that no longer exists is the quietest failure in
    # this file: the row it was written for comes back into the SILENT
    # list under its new name and the argument for it is still sitting
    # here, read by nobody. One rename wave produced one of these --
    # `cf:wizard-implement` became `cf:wizard-arcanist-f0` -- and the
    # excuse was three sentences long.
    stale = sorted(k for k in KNOWN_SILENT if k not in REGISTRY)
    refused += [f"KNOWN_SILENT names {k}, which is not a declared row" for k in stale]
    refused += [
        f"DID_SOMETHING names {k}, which is not an event class"
        for k in sorted(DID_SOMETHING - _event_names())
    ]
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
    # One line each, where `inert` gets a single summary line. Being
    # deliberately inert is a finished state; being unfinished is a debt,
    # and the length of the list is the pressure. A count would hide a
    # hundred of them behind a number nobody reads twice.
    # **`TODO` and `DROP` are not the same state and must not print the
    # same.** A `todo` row is refused in play; a `dropped` row works and
    # is missing one clause. Shown identically, a row that plays looked
    # exactly like one that had been set aside.
    for ref, wants, how in partial:
        print(f"  {how}    {ref:<10} wants {', '.join(wants)}")

    ok = len(chosen) - len(broken) - len(silent) - len(never)
    print(f"\n  {ok} of {len(chosen)} rows fire and do something")
    if inert:
        print(f"  {len(inert)} declared out of combat, not fired: {', '.join(inert[:6])}"
              + (" ..." if len(inert) > 6 else ""))
    if partial:
        # **Not all of them were skipped.** A `todo` row is refused in play
        # so it is never fired; a `dropped` row works and is fired like any
        # other. Saying "not fired" of both read as though a working row
        # had been quietly set aside.
        # Not `refused`: that name already belongs to the negotiable-event
        # check below, and shadowing it handed an int to `len()` -- which
        # took out the one check in this file that catches the engine
        # announcing a thing and then doing it anyway.
        inert_rows = sum(1 for _, _, how in partial if how == "TODO")
        print(
            f"  {len(partial)} unfinished -- {inert_rows} refused in play, "
            f"{len(partial) - inert_rows} playing with a clause missing"
        )
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
