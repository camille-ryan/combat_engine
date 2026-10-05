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

**Silence is graded against a baseline, by ref.** `fixtures/audited.json` holds
the refs that were silent at the last full sweep, and a run fails for a silent
row that is *not* on that list, for a listed row that does something now, or for
a raise. Carried rows are named and pass. Before this the verdict compared the
count against zero while the same file recorded `silent: 223` -- so the
instrument failed for finding exactly what it had written down, and `check.py`
reported `FAIL audit` on every run that reached any of them. A check that cannot
pass stops being read. #372.

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
from functools import cache, lru_cache
from pathlib import Path

from combat_engine import chargen
from combat_engine.content import loader
from combat_engine.engine import (
    Bus,
    Cast,
    DamageType,
    Encounter,
    Grid,
    Keyword,
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

# **The board deals unscored characters, deliberately.** `chargen.SCORED_CHOICES`
# makes a dealt character *plausible* -- a race whose bonuses suit the class, a
# feat worth taking -- and this board's job is the opposite one: to field
# whatever lets the row under test be used at all. It already overrides half a
# sheet for that reason, wounding the caster, hiding it from an enemy and
# putting the weapon a row names into its hand.
#
# Measured, not assumed. Scored dealing took **80 rows out of reach**, 36 of
# them the ranger's, and the cause was `chargen.build_for`: it picks a leg by
# *spawning a character on each* and taking the first the row is usable on, so
# a scored race draw inside that probe made the archer leg fail and the row was
# then fielded on a two-blade ranger that could never use it. never-usable
# 808 -> 860 and silent 219 -> 247 with it.
chargen.SCORED_CHOICES = False

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
    "m3027a3": "unverified",
    "m4962a3": "unverified",
    "m3030a1": "unverified",
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
    # **The level-5 wave's eight, and six of them are `m467a2`'s family.** A row
    # whose target line reads "one creature grabbed by it" needs the grab that a
    # *sibling row on the same stat block* lays, and the harness fires each row
    # once on a fresh board -- so the sibling has never run. Nothing here is a
    # row fault and nothing is fixable by widening the board: making the caster
    # grab before every row would change what every other row on the board is
    # being tested against. Each card's target line was read to confirm the
    # dependency rather than inferred from the verdict.
    "m5302a3": "attacks a creature grabbed by it; the grab is m5302a2's",
    "m5302a4": "attacks a creature grabbed by it; the grab is m5302a2's",
    "m5838a2": "attacks a creature grabbed by it; the grab is m5838a1's",
    "m3556a3": "acts on what it has grabbed; the grab is m3556a2's",
    "m5602a4": "commands a conjuration; m5602a3 is what conjures one",
    "m3219a5": "reanimates a dead ally; the board's one ally is at full health",
    # The two that are not a sibling dependency, and each is a different gap.
    # `m3291a4` rerolls an attack roll, so fired alone there is no roll behind
    # it to reroll -- the row is correct and the harness offers it nothing.
    # `m1113a2` hands an ally an immediate save against a save-ends effect, and
    # the board's single ally is a copy of the caster carrying no such effect:
    # both halves of its target line are absent at once.
    "m3291a4": "rerolls an attack roll; fired alone there is no roll behind it",
    "m1113a2": "an ally saves against a save-ends effect; the board's ally "
               "carries none",
    # **The level-6 wave's seventeen.** Four families, each read off the card
    # rather than guessed from the verdict. Three more rows reported silent in
    # the same run and are **not** here, because they were row faults and are
    # fixed instead: `_revenge_bonus` and `m4120a4` snapshotted "who has hit me"
    # when the minor action was spent and returned early on an empty set, which
    # is the shape `m915a4` settled by asking at the moment of the swing.
    #
    # A sibling's grab, aura or earlier attack. The harness fires each row once
    # on a fresh board, so the sibling never ran -- `m467a2`'s family.
    "m1929a1": "attacks a creature grabbed by it; the grab is m1929a0's",
    "m1936a3": "hauls what it has grabbed; the harness never makes it grab",
    # **This reason was wrong and is the kind of wrong that matters.** I wrote it
    # in round 7 as "m6655a0 has not laid one here", which reads as a board gap.
    # Driven since, with the aura laid first: the row *does* widen it, 1 to 3. It
    # is silent because resizing a zone **announces nothing** -- the radius is a
    # plain field that `Zones.refresh` re-reads, so there is no event for
    # `DID_SOMETHING` to recognise. The row is correct and invisible, not inert.
    # A `c.resize_aura()` that mutates and announces would fix both; filed.
    "m6655a5": "widens its own aura, which emits no event for the audit to see",
    "m6650a4": "widens its own aura, which emits no event for the audit to see",
    "m3637a4": "rerolls an attack roll; fired alone there is no roll behind it",
    "m3473a2": "lets m3473a1 ignore its own Requirement; nothing has attacked "
               "this creature yet when it is fired",
    # A rider the board has nobody to be. Its one ally is a copy of the caster
    # at full health, so it is never hurt, never undead and never a minion.
    "m6675a3": "heals an undead ally; the board's one ally is a copy of the caster",
    "m1531a2": "heals allies in a burst; the board's one ally is at full health",
    "m6343a3": "commands a minion plant ally; the board has neither",
    "m3184a2": "grants its rider concealment; the board sets up no rider",
    "m4032a2": "grants its rider a bonus; the board sets up no rider",
    # A target state the board does not produce. `_provoke` makes an attack, not
    # a condition of the harness's choosing.
    "m937a2": "targets prone enemies; nothing on the board is prone",
    "m3465a1": "ends a mark on itself; nobody here marks",
    "m1741a1": "affects only creatures taking ongoing poison; none are",
    "m3473a1": "affects only creatures taking ongoing poison; none are",
    # Terrain the board has none of. It is a bare grid by design -- two entries
    # already record that dressing it would cost every other row its legal shift.
    "m6662a3": "requires being in water; the board has none",
    "m6662a4": "requires water and loose ground; the board has neither",
    # **Round 8's fifteen, and three rows that looked like these and were not.**
    # `m5373a3`/`m5373a5` returned when the chooser aimed them at a creature their
    # target line forbids, where `_restricted_to` redirects to one in reach that
    # qualifies -- the settled answer across 112 rows. `m4400a2` gated on
    # `c.wielding`, which is false in every fight because `loader.py` gives every
    # stat block an empty `Gear()` (#366). All three fire now and are not here.
    #
    # A target state `_provoke` does not produce. It makes an attack; it does not
    # daze, immobilise, knock prone or bring anybody to dying.
    "m1950a1": "targets an immobilized creature; nothing here is",
    "m1192a2": "targets an immobilized creature; nothing here is",
    "m5504a1": "targets a prone creature; nothing here is",
    "m5576a1": "its Requirement is an immobilized, stunned or unconscious target",
    "m5577a2": "its Requirement is an immobilized, stunned or unconscious target",
    "m5825a4": "finishes a dying humanoid; nobody here is dying",
    # A sibling's grab. The harness fires each row once on a fresh board, so the
    # row that does the grabbing never ran -- `m467a2`'s family again.
    "m1981a1": "attacks a creature grabbed by it; the grab is m1981's own",
    "m2233a1": "grabbed target only; nothing here is grabbed",
    "m4645a2": "grabbed target only; nothing here is grabbed",
    "m5857a3": "acts on what it has grabbed; the grab is m5857a2's",
    # Terrain and geometry the bare grid does not have.
    "m3993a7": "requires being submerged in water; the board has none",
    "m4148a7": "requires being submerged in water; the board has none",
    # Driven by hand rather than assumed: the board seats this creature *adjacent*
    # to the single bloodied enemy, and the best square its three squares of
    # shifting can reach is also adjacent, so "move closer to a bloodied
    # creature" correctly has nowhere to go. The row is right and the geometry
    # gives it nothing to do.
    "m5373a4": "shifts closer to a bloodied creature; it starts adjacent to the "
               "only one",
    # **Round 9's sixteen, and one row that looked like these and was not.**
    # `m4296a1` returned when the chooser aimed it at a creature its target line
    # forbids; it redirects with `_restricted_to` now. It is still here, because
    # nothing on this board is slowed or immobilized for the redirect to find --
    # but the shape is right for a real fight either way.
    #
    # A grab a sibling row lays, which the harness never runs. `m467a2`'s family,
    # now the largest of these groups by some distance.
    "m1937a1": "attacks a creature grabbed by its stablemate; nothing grabs here",
    "m4012a1": "attacks a creature grabbed by it; the grab is a sibling's",
    "m4755a2": "attacks a grabbed creature; nothing here is grabbed",
    "m5128a4": "sustains a grab; there is none to sustain",
    "m6436a3": "acts on what it has grabbed; nothing here is grabbed",
    # A target state `_provoke` does not produce. It makes an attack; it does not
    # slow, immobilise, stun or mark.
    "m4296a1": "targets a slowed or immobilized creature; nothing here is either",
    "m5571a1": "redirects to an immobilized, stunned or unconscious creature; "
               "the board has none",
    "m5738a2": "redirects to a creature it has already slowed; it has not",
    "m4508a4": "cures a mark on itself; nobody here marks",
    "m6429a4": "answers a condition it starts its turn carrying; it carries none",
    # An ally or a board state the single full-health copy of the caster cannot be.
    "m2785a3": "a bonus while a natural beast ally is near; the board's one ally "
               "is a copy of the caster",
    "m3467a3": "a bonus against a creature taking ongoing necrotic; none is",
    "m946a3": "its Requirement is no enemy within 3; the board starts them adjacent",
    "m3453a2": "saves against the effect that triggered it; the board lands no "
               "save-ends effect on this creature",
    # Concealment and cover the bare grid does not provide.
    "m1167a3": "requires concealment; no terrain here grants any",
    "m3675a2": "requires cover; no terrain here grants any",
    # **Round 10's twelve.** Checked individually against the `_restricted_to`
    # trap first; none of them is that shape. `m822a4` looked like it -- it
    # returns when its target is not undead -- but its header is `EACH_ALLY`, so
    # the body runs once per ally and the return is correct filtering.
    #
    # A target state `_provoke` does not produce.
    "m1812a4": "targets a prone creature; nothing here is",
    "m2245a2": "targets an unconscious creature; nothing here is",
    "m3300a2": "targets a grabbed creature; nothing here is grabbed",
    "m5574a2": "targets an immobilized, stunned or unconscious creature; "
               "the board has none of the three",
    "m5466a3": "ends an ongoing effect or condition; the target carries neither",
    "m5494a5": "needs a bloodied creature it has already clawed this turn",
    "m115865a2": "attacks a creature grabbed by it; nothing here is grabbed",
    "m2303a2": "attacks a creature grabbed by it; nothing here is grabbed",
    # Nothing in flight to reroll. Both are free actions answering a roll that,
    # fired alone, has not happened.
    "m3290a4": "rerolls an attack roll; fired alone there is none behind it",
    "m3645a4": "rerolls an attack roll; fired alone there is none behind it",
    # The board's one ally is a copy of the caster at **full** health, so a heal
    # lands on nobody who needs it.
    "m822a4": "heals undead allies in a burst; the board's one ally is unhurt",
    # Terrain a bare grid has not got.
    "m960a5": "requires icy ground to teleport from; the board has none",
    # Round 11: the board carries `fire` and `object` scenery and nothing else, so
    # a row wanting a tree has none to find. `m115702a2` is the same cause.
    "m3787a2": "teleports beside a tree; the board has no tree scenery",
    "m5183a1": "teleports beside a tree; the board has no tree scenery",
    # **Round 11's twenty-eight, and the grab family is now most of them.** Sixteen
    # of the twenty-eight want a creature the stat block's *own sibling row* has
    # grabbed, and the harness fires each row once on a fresh board, so the grab
    # never happened. `m467a2` opened this family and it has grown every round --
    # at this rate it is the single biggest structural limit of the monster board,
    # and worth a line in #214 rather than more entries here if it keeps growing.
    "m3474a3": "attacks what it has grabbed; the grab is its own sibling's",
    "m5098a2": "its Requirement is holding a grab; it holds none",
    "m6092a2": "attacks a humanoid it has grabbed; nothing here is grabbed",
    "m1177a1": "affects what it has grabbed; nothing here is grabbed",
    "m1915a2": "attacks what it has grabbed; nothing here is grabbed",
    "m1949a1": "attacks what its stablemate has grabbed; nothing here is grabbed",
    "m1982a2": "hits each creature it has grabbed; it has grabbed none",
    "m1982a3": "sustains a grab as a free action; there is none to sustain",
    "m2078a2": "grabbed targets only; nothing here is grabbed",
    "m3988a3": "attacks what it has grabbed; nothing here is grabbed",
    "m4005a1": "attacks what it has grabbed; nothing here is grabbed",
    "m5654a3": "attacks a Large or smaller creature it has grabbed; none is",
    "m6113a3": "attacks what it is grabbing; it is grabbing nothing",
    "m6172a2": "attacks a creature it has grabbed; nothing here is grabbed",
    "m6174a1": "attacks what it has grabbed; nothing here is grabbed",
    "m6663a2": "attacks what it has grabbed; nothing here is grabbed",
    # An ally of a kind the board's one ally cannot be. It is a copy of the caster,
    # so a row wanting an ally of a *different* kind finds none -- checked rather
    # than assumed: both casters below read as `humanoid`, never undead or animate.
    "m3983a2": "grants an undead or beast ally an attack; its only ally is a "
               "humanoid copy of itself",
    "m5655a2": "grants an allied animate an attack; its only ally is a humanoid "
               "copy of itself",
    "m5625a2": "slides an allied minion of one kind; the board spawns none",
    # A target state `_provoke` does not produce.
    "m5779a4": "targets a slowed creature; nothing here is slowed",
    "m5926a2": "targets a prone creature; nothing here is prone",
    # **Round 13's ten, over 507 rows at level 11.** Nine of the ten are the
    # same shape this section already records -- the printed target carries a
    # condition `_provoke` never applies -- and every one was driven by hand
    # with the state set before it was admitted here, so each is a row proven
    # to work rather than a row assumed to.
    "m1600a2": "immobilized targets only; nothing here is immobilized. Driven "
               "with the target immobilized: emits DamageApplied and "
               "EffectApplied",
    "m1600a3": "immobilized targets only; nothing here is immobilized. Driven "
               "with the target immobilized: emits DamageApplied and "
               "EffectApplied",
    "m1978a2": "needs an immobilized enemy. Driven with one: hits, damages, "
               "spends the victim's surge and heals 5",
    "m2549a1": "affects an immobilized target only, so `_restricted_to` "
               "correctly finds nobody on this board",
    "m6055a1": "its printed target is one prone enemy; the board holds three "
               "foes and none is prone",
    "m115868a3": "needs a stunned enemy. Driven with one: 31 damage",
    "m1565a2": "restrains whoever stands in its own roots; the board grows "
               "none. Driven with them: restrains two creatures",
    "m1565a4": "blinks into one of its own root squares, and on the audit seed "
               "both are occupied -- a Large creature cannot fit. Genuinely "
               "board-blocked rather than target-blocked",
    "m4322a5": "its printed gate is \"if the summoned body is not adjacent or "
               "closer\", and the body appears in the caster's own space, so "
               "returning nothing is the card. Driven after the summon: the "
               "gate is what stops it",
    # **Round 14's five, over 376 rows at levels 11 and 12.** Four are the
    # grab-or-condition family again; each was driven with the state set.
    "m1617a1": "needs an immobilized enemy within 5. Driven with one: hits "
               "for 13 necrotic and heals 10",
    "m2082a1": "affects a creature it is grabbing; the board arranges none. "
               "Driven after its own grab: 10 necrotic to the held creature, "
               "and aimed elsewhere it redirects to the one it holds",
    "m5124a4": "affects a creature it is grabbing. Driven with the relation "
               "set: hits, 10 damage, shares its space, restrained save-ends "
               "with ongoing 10",
    "m5492a3": "needs a creature grabbed by the caster. Driven with the grab "
               "set: +14 vs Fort, 4d10+5 necrotic, releases the grab, heals "
               "10, and applies unconscious when the blow crosses bloodied",
    # #375's family, and the clearest case of it yet: the row's whole effect
    # is two extra initiative slots, and `Encounter.extra_turn` / `_splice`
    # announce nothing, so there is no event for the audit to count. Driven,
    # the caster's slot count in `encounter.order` goes 3 -> 5. The row works;
    # a log-based instrument cannot see state changed by assignment.
    "m3932a6": "grants itself two extra turns, and extra_turn emits no event "
               "to see it by (#375). Driven: slot count 3 -> 5",
    # **Round 15's fifteen, over 647 rows at level 12.** Every one needs a
    # target in a state this board does not arrange, and every one was driven
    # by hand with that state set before it was admitted. Where the state is
    # named below it was established by that run; where it is not, the run
    # established only that the row does real work once the gate is met, and
    # the entry says no more than that.
    "m1155a2": "needs a target state the board never applies. Driven: it "
               "dominates",
    "m115876a4": "needs a target state the board never applies. Driven: it "
                 "damages",
    "m115876a5": "needs a target state the board never applies. Driven: it "
                 "emits ForcedMove and pulls",
    "m2348a1": "needs a target state the board never applies. Driven: damage "
               "and daze",
    "m5815a3": "needs a target state the board never applies. Driven: it "
               "damages",
    "m2347a1": "needs a target state the board never applies. Driven: it "
               "damages",
    "m2550a5": "needs a target state the board never applies. Driven: it emits "
               "Healed",
    "m3313a3": "needs a target state the board never applies. Driven: it emits "
               "SavingThrow",
    "m1910a4": "moves a creature it has buried; nothing here is. Driven: the "
               "puppet moves",
    "m3275a1": "needs its own bond laid on the target first, which the board "
               "never does. Driven after the bond: it fires",
    "m4727a1": "the same card as m3275a1 at a second ref, and silent for the "
               "same reason -- its bond is never laid here",
    "m5335a2": "its printed target must be blinded; nothing here is. Driven "
               "with a blinded victim: it fires",
    "m2011a3": "needs an adjacent corpse to inhabit, and nothing here is dead "
               "beside it. Driven with one: it fires, and so do the rows the "
               "possession then grants",
    # The board carries no creature with this type word at all, which is #387
    # rather than anything about the row: 17 cards target one.
    "m5235a1": "its printed target is a living humanoid and no creature on this "
               "board carries that type word (#387). Driven with the word "
               "granted: dominates, removes itself from play, lends its at-will",
    # Not a target state: the caster's own.
    "m6192a5": "it stands up, and the board never knocks the caster down. "
               "Driven with prone set: emits ConditionEnded(prone)",
    # **Round 17's seven, and the last of the monster sweep.** The whole
    # corpus is declared at this point -- 13,432 of 13,432 -- and these are
    # the final rows the board cannot stage. Every one needs a target in a
    # state `_provoke` does not produce, and every one was driven by hand with
    # that state set before it was admitted.
    "m2073a1": "its printed target must be prone; nothing here is. Driven "
               "with one: hits for 13",
    "m2529a1": "needs a creature it is grabbing. Driven with the grab set: "
               "hits for 5, slides 3, knocks prone, and releases the grab",
    "m4484a3": "its printed target must be blinded; nothing here is. Driven "
               "with one: hits for 20",
    "m6162a3": "needs a dominated creature adjacent, which the board never "
               "arranges. Driven with one: shifts, then slides the thrall "
               "back to adjacent",
    "m6183a3": "needs a creature it is grabbing. Driven with the grab set: "
               "it hits",
    "m6185a7": "affects a creature it is grabbing. Driven with the grab set: "
               "10 acid to the held creature",
    "m6516a1": "its printed target is one creature grabbed by it. Driven with "
               "the relation set: 15 to the held creature",
    # **The reach guard's one casualty, and it is the board.** #381 closed the
    # explicit-target arm of `dsl.use`, which used to let a granted swing
    # connect at any distance. This row nominates an enemy within 10 squares of
    # the *warlord* and has an *ally* swing at it, so it needs the ally in
    # reach -- and `board()` does not put it there. Driven both ways: with the
    # ally six squares off nothing is announced, with the ally beside the enemy
    # it announces AttackDeclared, AttackRolled and Hit.
    "p10888": "an ally swings at an enemy the warlord nominates, and the board "
              "never stands that ally in reach of one",
    # Not a condition: a footprint. `movement.overrun` builds `under` from
    # `grid.occupant` filtered on `who != eid`, and both this harness's board
    # and `show.py`'s place foes *inside* a Gargantuan caster's 4x4 footprint,
    # so the grid answers with the caster at those squares and the trample
    # finds nobody to tread on. Walked four squares through two enemies and
    # ended standing on a third. The row moves, which is the half that can be
    # seen; it cannot be exercised here.
    "m5906a5": "a Gargantuan caster's overrun finds nobody under it, because "
               "the board puts foes inside its own footprint",
    "m1828a1": "its target must be prone; nothing here is",
    "m5336a5": "pulls a creature its own sibling immobilized; nothing is",
    # #366's family: the target must be wearing or wielding an item, and
    # `loader.spawn` gives every stat block an empty `Gear()`.
    "m3448a1": "targets a creature wielding a magic item; no monster carries gear",
    # The remaining four, each its own shape.
    "m5948a6": "raises a dead ally; nobody here is dead",
    "m3288a6": "rerolls an attack roll; fired alone there is none behind it",
    "m5468a3": "cures an ally's condition at the start of its turn; the board's "
               "one ally carries none",
    "m5625a0": "its printed effect -- an enemy cannot enter its square -- is "
               "already true of every creature by collision, so there is nothing "
               "for the row to do and nothing to see it do",
    # **Round 12's fifty-five, over 1,127 rows.** Nineteen are the grab family,
    # which has led every round since `m467a2` and is now unambiguously the
    # board's biggest structural limit -- a row wanting a creature its own sibling
    # has grabbed, fired alone on a fresh board.
    "m115863a4": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m3795a1": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m4007a2": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m5160a3": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m6642a2": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m1089a1": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m1089a2": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m1163a3": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m5814a3": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m5813a3": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m5330a2": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m4014a1": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m4014a2": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m5529a3": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m5997a7": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m115875a1": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m3997a1": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m115910a2": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    "m5132a2": "attacks or acts on a creature it has grabbed; nothing here is grabbed",
    # A target state `_provoke` does not produce. It makes an attack; it does not
    # daze, slow, immobilise, stun, knock prone or mark.
    "m1101a1": "its target must carry a condition the board never applies",
    "m2092a2": "its target must carry a condition the board never applies",
    "m6365a1": "its target must carry a condition the board never applies",
    "m939a1": "its target must carry a condition the board never applies",
    "m1062a2": "its target must carry a condition the board never applies",
    "m1172a4": "its target must carry a condition the board never applies",
    "m1173a3": "its target must carry a condition the board never applies",
    "m2596a1": "its target must carry a condition the board never applies",
    "m5578a1": "its target must carry a condition the board never applies",
    "m5543a4": "its target must carry a condition the board never applies",
    "m5418a3": "its target must carry a condition the board never applies",
    "m5596a2": "its target must carry a condition the board never applies",
    "m3273a2": "its target must carry a condition the board never applies",
    "m3253a5": "its target must carry a condition the board never applies",
    # **Not board limits -- #375's family.** Each of these changes real state by
    # assigning a field or rolling a number, and emits nothing for a log-based
    # check to see: a second initiative, an extra turn, a change of form. The rows
    # work; the audit cannot watch them. Same cause as the aura resize above.
    "m5875a0": "changes state without emitting anything for the audit to see (#375)",
    "m6282a0": "changes state without emitting anything for the audit to see (#375)",
    "m953a2": "changes state without emitting anything for the audit to see (#375)",
    "m5671a0": "changes state without emitting anything for the audit to see (#375)",
    "m790a5": "changes state without emitting anything for the audit to see (#375)",
    "m4325a5": "changes state without emitting anything for the audit to see (#375)",
    "m5596a7": "changes state without emitting anything for the audit to see (#375)",
    # Needs an effect a *sibling row* laid and the harness never ran.
    "m5709a2": "acts on a creature carrying a sibling row's own effect",
    "m6686a1": "acts on a creature carrying a sibling row's own effect",
    "m3295a3": "acts on a creature carrying a sibling row's own effect",
    "m2784a3": "acts on a creature carrying a sibling row's own effect",
    # Flanking, which the board's fixed layout does not arrange.
    "m5971a3": "its Requirement is flanking; the board does not set one up",
    "m6284a2": "its Requirement is flanking; the board does not set one up",
    # An ally of a kind the board's one ally cannot be -- it is a copy of the
    # caster, so a row wanting an ally of a *different* kind finds none.
    "m6180a0": "wants an ally of a kind its own copy is not",
    "m6180a2": "wants an ally of a kind its own copy is not",
    "m5787a8": "wants an ally of a kind its own copy is not",
    # Gated on a form change having happened first, which needs the sibling row
    # that performs it.
    "m5786a3": "its Requirement is a form the creature has not changed into",
    "m5596a5": "its Requirement is a form the creature has not changed into",
    "m5596a6": "its Requirement is a form the creature has not changed into",
    # The last three, each its own shape.
    "m1193a2": "douses a light source; the board models no light",
    "m3315a5": "stays hidden on a miss; it is not hidden to begin with",
    "m5596a3": "contracts a disease; no disease system exists to carry one",
    # The one that is an instrument gap rather than a board gap, and is filed as
    # #374 rather than excused: `c.set_origin` labels its effect `origin:<word>`
    # because `kinds_of` reads the word back out of the label, so it cannot carry
    # the ref that `_claimed` credits by. Driven by hand: the effect *is* laid.
    # Left reporting silent on purpose -- waiving it here would hide the gap, and
    # three baseline rows share it.
    # Sends one of the m4967's own mossling minions running, and the board
    # spawns a second m4967 rather than a mossling. Driven by hand: with an
    # m4971 beside it the minion moves its full speed as a free action.
    "m4967a5": "moves a mossling minion; the board has none to move",
    # Sends a *bloodied* ally back in. The board's only creature on the
    # caster's own side is the second of its kind, spawned at full health --
    # the four wounded ones are all on the other team. Driven by hand: with
    # that ally at half hit points it is granted a melee attack and swings.
    "m350a2": "grants a bloodied ally an attack; the board's only ally is unhurt",
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
    "p5330": "affects only undead; the auto-targeter never picks the board's one undead",
    # m5423a4 used to sit here -- "targets a dazed creature; the auto-targeter
    # aims by distance -- #361". It was the first of a family of 2,863 monster
    # abilities printing a condition-restricted target line, and the argument
    # for landing #361 rather than excusing them one at a time. `Target.conditions`
    # landed, so the filter is in the pool and `_auto_targets` can only pick a
    # creature the card accepts. The excuse is gone rather than re-aimed.
    # The trigger is **this creature's own** earlier bite burning somebody: the
    # row answers the ongoing poison its sibling laid. The harness fires each row
    # once on a fresh board, so that bite has never landed -- the same reason
    # `f961b` and `i1875p1` are excused. It does fire 3 of 8 attempts, on the
    # board's own ongoing poison, and then correctly declines: that poison is not
    # its bite's and the carrier is not adjacent.
    "m5537a1": "answers its own bite's ongoing poison; nothing has bitten yet",
    # **The row works and the engine says nothing about it.** `turns.extra_turn`
    # duplicates the creature's slot in `order` and emits no event at all, so
    # there is nothing for `DID_SOMETHING` to recognise -- the same shape as
    # `c.summon`, which `Cast.watch`'s docstring already records.
    #
    # Driven by hand with both controls by the agent that wrote it: the
    # two-slot creature gets `order == [1, 1, 2]` and a control monster beside
    # it gets one slot.
    #
    # The real fix is an event, not an excuse -- `DID_SOMETHING` cannot be
    # taught to see a list mutation. Until there is one this is the honest
    # verdict.
    "m3301a2": "its whole content is a second turn, and `extra_turn` emits nothing",
    # A mount's trait that pays its rider, gated on the rider being 5th level
    # or higher. The board's rider is level 1, so the body correctly declines.
    # Proved with a positive control by the agent that wrote it: raise the
    # board's rider to level 5 and the bonus lands, gated on the charge.
    #
    # It reports SILENT rather than UNUSED because **a trait's `requires=` is
    # never consulted** -- `turns.arm_traits_of` does not call `usable`, so the
    # gate is read by nothing and the row is armed regardless. That is why the
    # body has to ask the same question again, and why `requires=` on a trait
    # buys honest reporting and nothing else.
    # **Refused at arming, not silent in play.** Its mount is level 4 and the
    # card wants a rider of 5th or higher, so `requires=` is false when
    # `arm_traits_of` tries to arm it -- and `dsl.use` refuses it outright. It
    # reports SILENT rather than UNUSED only because the trait branch counts a
    # row as fired without calling `use`, which is its own defect.
    #
    # The board's rider is now levelled to the mount (see `board`), which fixed
    # the other five of this family; this one asks for a level above its own
    # mount's, so it is the single row the board cannot satisfy without
    # inventing a rider out of proportion to what it carries.
    "m1461a1": "wants a rider above its own mount's level; refused at arming",
    # **Three of #361's family.** Each has a printed target line the board has
    # nobody to satisfy -- the restriction is on another creature's state, so no
    # `requires=` can reach it and the body correctly declines. All three were
    # driven by hand by the agent that wrote them, patching one board ally to
    # qualify: they emitted `AttackDeclared`/`Hit`, `EffectApplied` and `Healed`
    # respectively. They stop needing an excuse the day #361 lands, because the
    # targeter will aim at a creature that qualifies.
    "m4644a4": "its target line qualifies nobody on this board -- #361",
    "m4687a2": "its target line qualifies nobody on this board -- #361",
    "m4766a3": "its target line qualifies nobody on this board -- #361",
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
    # Clears difficult terrain in a close burst 1, and the only squares
    # beside the caster have to stay smooth so a one-square shift has
    # somewhere to go. The board's rough ground is further out.
    "p15856": "clears difficult terrain within 1; the caster's neighbours must stay smooth",
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
    "ForcedMove", "RelationSet", "RelationCleared", "ZoneCreated",
    "EffectExpired", "EffectApplied", "ConditionEnded",
    "Bloodied", "Dropped", "Died", "SavingThrow", "SkillCheck", "Summoned",
    "SurgeSpent", "ActionGranted",
}  # fmt: skip
# `RelationCleared` for the same reason `ConditionEnded` is here and
# `RelationSet` already was: **taking a relation off is as much a thing as
# putting one on.** `RelationSet` was admitted and its mirror was not, so a row
# whose whole printed effect is *un*doing one was invisible. A level-13 row
# reads "mounts **or dismounts** its adjacent mount", and the board spawns that
# creature already mounted -- so every firing took the dismount branch, emitted
# `RelationCleared` alone, and reported SILENT. Driven both ways: dismounting
# emits `RelationCleared` and the relation really goes; cleared first, the same
# row emits `RelationSet` and mounts.
#
# This is the fourth class of correct row admitted here one at a time, which
# `docs/AUTHORING.md` predicted would keep happening. The shape to watch for is
# a card whose verb is a negation -- dismount, unbind, release a guard, break a
# hold -- because the engine says those by clearing.
# **`Note` is deliberately not here**, and used to be. Its own docstring says
# "engine commentary, carries no rules meaning", and it holds `text` and
# nothing else -- no actor, no source, no target -- so `_after_its_own_use`
# has nothing to attribute it with and credits whichever note lands in the
# window. Five of the rows pinned in `--verdicts` were credited with
# `8 carries f336 (1 left)`, emitted by another creature arming its own feat,
# while `hollowed` had replaced their bodies with one that does nothing.
# Over a 300-row sample, 13 were credited by `Note` alone and **11 of those 13
# kept the credit with their body emptied**. See #245.
#
# A row whose only output is a log line has not done anything in the rules,
# and this project already has the word for that case: `narrative=`. Crediting
# it hid the rows that marker exists to describe.
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


@lru_cache(maxsize=1)
def _associated() -> dict[str, list[str]]:
    """Each feat's "Associated Powers" line, as refs, from `feat.spec`.

    **The rows a feat is a rider on, which `_siblings` did not have.** 219 rows in
    the never-usable set wait on `Hit`, and the single commonest thing their printed
    trigger narrows by is "a power associated with this feat" -- so the harness
    swinging a melee *basic* can never satisfy them however well they are written.
    The refs are right there on the card: `Associated Powers: p917, p1758, p1063`.

    Distinct from the `{"ref": ...}` gate `_siblings` already reads: that is the one
    card a feat is a *prerequisite* on, and this is the list it riders. A feat can
    have either, both or neither. #214.
    """
    from combat_engine.etl.build import game

    out: dict[str, list[str]] = {}
    try:
        rows = game().execute("SELECT ref, spec FROM feat").fetchall()
    except Exception:
        return out
    for ref, spec in rows:
        for line in (spec or "").splitlines():
            if line.startswith("Associated Powers:"):
                out[ref] = re.findall(r"\b(?:p|i|cf:)[\w:-]*\d[\w:-]*\b",
                                      line.split(":", 1)[1])
                break
    return out


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
    out += _associated().get(ref, [])
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

    The same four things `query.holding` matches on -- a group, a property, a
    category, or the weapon's own **slug** -- built from the 117 printed weapons
    rather than listed here, so a weapon added to the table becomes askable for
    without touching this.

    **It was the ref's own tail**, `w.ref.split(":", 1)[1]`, which worked only
    while a ref was `w:<slugified name>`. #339 made the ref the compendium id,
    and that expression then raised `IndexError` on every weapon: a full sweep
    reported **2,602 rows raising** against a watermark of 0. Loud, immediately,
    and from the one instrument that reads every row -- which is the argument
    for paying its ten minutes before committing an engine change.
    """
    out: dict[str, str] = {}
    for w in chargen.PRINTED.values():
        if w.slug:
            out.setdefault(w.slug.replace("-", " "), w.ref)
        if w.group:
            out.setdefault(w.group, w.ref)
        for prop in w.properties:
            out.setdefault(prop, w.ref)
        # **"a thrown weapon" is not a property and three rows ask for one.**
        # The table spells the properties `light thrown` and `heavy thrown`, so
        # a Requirement reading "you must be wielding a thrown weapon" matched
        # nothing and the board handed nothing over -- which was invisible for
        # as long as those rows applied no gate, and made all three unusable the
        # moment they did.
        #
        # **A heavy one, and that is not arbitrary.** This key is 13 characters
        # and `heavy thrown` is 12, so longest-match-wins hands it every row
        # reading "needs a heavy thrown weapon" as well -- `p4559` went unusable
        # the first time I wrote this, because a dagger answered it. A heavy
        # thrown weapon satisfies both sentences and a light one satisfies one,
        # so the stricter reading is the safe one to stock. The docstring above
        # already warned about exactly this pair.
        if w.thrown is not None and "heavy thrown" in w.properties:
            out.setdefault("thrown weapon", w.ref)
    return dict(sorted(out.items(), key=lambda kv: -len(kv[0])))


_WEAPON_WORDS: dict[str, str] | None = None


_WIELDS: dict[str, list[str]] | None = None


def _wields_of(ref: str) -> list[str]:
    """What `power.wields` says this row's own text is about, gates first.

    Gates before riders, because failing a gate means the row is refused and
    failing a rider only means a weaker version of it -- so if the board can
    only satisfy one, it should be the one that decides whether the row runs.
    """
    global _WIELDS
    if _WIELDS is None:
        import json

        from combat_engine.etl.build import game

        _WIELDS = {}
        for row, raw in game().execute(
            "SELECT ref, wields FROM power WHERE wields IS NOT NULL"
        ):
            found = json.loads(raw)
            _WIELDS[row] = [
                *found["gate_groups"], *found["gate_shapes"],
                *found["rider_groups"], *found["rider_shapes"],
            ]
    return _WIELDS.get(ref, [])


def _train(gear: object, held: object) -> None:
    """Count the handed-over weapon as one this character is trained with.

    `Gear.trained` withholds a weapon's proficiency bonus from a creature not
    trained with it (#242), and everything this function hands over is handed
    over **because a row demands it** -- so the character it stands in for is
    one that took the feat and is trained. Without this the harness would
    under-roll all 257 of those rows by 2 or 3 to hit, which changed no verdict
    when measured but makes every one of them a slightly wrong question.
    """
    current = getattr(gear, "trained", frozenset())
    if current:
        gear.trained = current | {held.ref}


def _any_weapon(want: str):  # noqa: ANN202
    """A printed weapon matching a group or a category, or None for a shape."""
    for arm in chargen.PRINTED.values():
        if arm.group == want or arm.category == want:
            return arm
    return None


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

    from dataclasses import replace as _replace

    from combat_engine.engine import Gear
    from combat_engine.engine.query import holding

    gear = world.get(caster, Gear)

    wanted = " ".join(
        (getattr(declared, "requires_text", "") or "",
         getattr(declared, "trigger", "") or "")
    ).lower()
    # **"A hand free" is a grip this could only ever fill.** Everything below
    # *draws* something, and 15 rows ask for the opposite -- so a board whose
    # character happened to be holding a shield reported one UNUSED, which is
    # indistinguishable from a row that cannot work at all. That is the same
    # argument `_grip_for` gives for existing.
    if "hand free" in wanted and gear is not None:
        gear.shield = False
        kept = next((w for w in gear.melee if not w.two_handed), None)
        gear.weapons = [w for w in gear.weapons if w is kept] if kept else []
        gear.__post_init__()
        return
    if not wanted.strip():
        return
    if _WEAPON_WORDS is None:
        _WEAPON_WORDS = _weapon_words()
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
            held = _replace(arm)
            gear.weapons.append(held)
            gear.wield(held)
            _train(gear, held)
        return
    # **The sentence first, the column as the fallback, and that order is
    # measured.** `power.wields` records a *group* -- a Requirement naming one
    # weapon is filed under that weapon's group, which is right for scoring and
    # lossy here. Asking it first broke three rows gated on an exact weapon
    # (`p13794` a dagger, `p13796` a bola, `p15912` shuriken): the column said
    # "light blade", the board handed over a short sword, and the gate failed.
    # The words resolve a weapon exactly; the column is what sees the **riders**,
    # which are not requirements and so appear in no sentence this function reads.
    # #237.
    for want in _wields_of(getattr(declared, "ref", "")):
        if holding(world, caster, want):
            return
        arm = _any_weapon(want)
        if arm is not None:
            held = _replace(arm)
            gear.weapons.append(held)
            gear.wield(held)
            _train(gear, held)
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
        # declaring `proficiency=("w3660",)` were audited on a character
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

    # **And the rider is levelled up to the mount.** Every printed mount trait
    # is gated on "a friendly rider of Nth level or higher", and N tracks the
    # mount: 16 rows ask it, at levels 2, 3, 4, 5, 7 and 10. The board's ally is
    # level 1, so **all sixteen were unexercisable** -- five reported SILENT
    # together in one round, each correctly declining to hand a resistance or a
    # damage bonus to a rider too green to have it.
    #
    # Raised rather than excused, because the alternative is sixteen hand-argued
    # entries in `KNOWN_SILENT` for one missing number, and the family grows with
    # every level the sweep reaches.
    #
    # Only the *level* moves, and only upwards: the rider's own statistics are
    # whatever `chargen` dealt it, so nothing else about the board changes.
    from combat_engine.engine.components import Stats as _Stats

    _mount_stats = world.get(caster, _Stats)
    _rider_stats = world.get(ally, _Stats)
    if _mount_stats is not None and _rider_stats is not None:
        _rider_stats.level = max(_rider_stats.level, _mount_stats.level)

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
def _swing_from_reach(
    world, attacker: int, target: int, ref: str, **kw: object  # noqa: ANN001
) -> None:
    """A basic attack made from somewhere it could legally be made.

    **This used to swing from wherever the creature stood.** `dsl.use`'s
    explicit-target arm applies no reach check -- that is #381 -- so
    `use(..., targets=[target])` here was delivering a *melee-1* basic attack
    at six squares. Two things were wrong with that, and the second is the
    serious one:

    * the harness was contributing its own occurrences to the very bug being
      measured, which is how #381's first count came out low;
    * a row answering "when an enemy hits you with a melee attack" was being
      provoked by an attack that could not have happened, so its verdict rested
      on an illegal event. A row is supposed to be proven by a legal swing.

    So the attacker is stepped beside the target when it cannot reach, and
    **put back afterwards** -- every later probe in `_provoke` measures from
    where the board was left, and this function already records once that an
    ally three squares out of place took "grant an ally a basic attack" from
    working to impossible.

    A ranged basic is left alone: it reaches across the board by design.
    """
    from combat_engine.engine.components import Position
    from combat_engine.engine.dsl import _reach_of, origins
    from combat_engine.engine.grid import spread
    from combat_engine.engine.query import distance_between, squares

    p = get(ref)
    here = world.get(attacker, Position)
    if p is None or here is None or p.reach.kind != "melee":
        use(world, attacker, ref, targets=[target], spend=False, **kw)
        return

    far = _reach_of(world, attacker, p.reach, ref)
    if any(distance_between(world, o, target) <= far for o in origins(world, attacker, p.reach)):
        use(world, attacker, ref, targets=[target], spend=False, **kw)
        return

    was = here.square
    beside = sorted(
        sq
        for sq in spread(squares(world, target), far)
        if world.grid.inside(sq) and world.grid.occupant(sq) in (None, attacker)
    )
    if not beside:
        return
    place(world, attacker, beside[0])
    try:
        use(world, attacker, ref, targets=[target], spend=False, **kw)
    finally:
        place(world, attacker, was)


PROVOKE_NOISE = {
    "AttackDeclared", "AttackRolled", "Hit", "Miss", "DamageRolled",
    "DamageApplied", "OpportunityWindow", "TurnStart", "TurnEnd",
    # **`RelationCleared` is here because swinging emits one.**
    # `resolve.attack` ends the attacker's `HIDDEN_FROM` on every attack
    # (`why="attacked"`), so admitting the bare event name credited any row
    # that merely attacked while hidden. Three `KNOWN_SILENT` rows reported
    # OUTGROWN the moment the name was added, and all three were credited on
    # `RelationCleared kind=hidden_from why='attacked'` and nothing else --
    # borrowed evidence, the same shape as the 173 rows that once passed on
    # the harness's own provocation. `_own_unbinding` admits the real ones.
    "RelationCleared",
}


#: A relation this row took off, as against the one every attack takes off.
#:
#: Needed for the reason `_own_movement` is needed: clearing a relation is the
#: *whole content* of several rows -- "it dismounts", "the grab ends", "the
#: guard is released" -- so suppressing the name outright makes those rows
#: unprovable, and admitting it outright credits every hidden attacker. The
#: engine's own housekeeping is the one that says `why="attacked"`; anything
#: else was asked for by a row.
def _own_unbinding(world, cursor: int) -> set[str]:  # noqa: ANN001
    for e in world.bus.log[cursor:]:
        if e.kind == "RelationCleared" and getattr(e, "why", "") != "attacked":
            return {"RelationCleared"}
    return set()

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
        _swing_from_reach(world, attacker, target, basic(attacker))
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

    # **A typed attack, not typed damage.** The loop above deals a point of
    # each type and emits `DamageApplied`; thirty-eight never-usable rows are
    # waiting on a `Hit` that *carries the keyword*, and every one of their
    # predicates reads `Keyword.X in p.keywords` of the power that landed --
    # not the damage it dealt. So no amount of typed damage reaches them, and
    # a typed weapon would not either: `Weapon.dtype` colours the damage and
    # leaves the power's keyword list alone. The harness has to use a row that
    # *has* the keyword, which the caster usually already knows -- a wizard
    # holding a cold at-will was never asked to cast it.
    #
    # Both directions, because five of the thirty-eight are monsters printing
    # "is hit by a cold attack" rather than "you hit with one".
    for kw in _typed_wanted(ref):
        for who, at in ((caster, foes[0]), (foes[0], caster)):
            if not alive(world, at):
                continue
            for other in _typed_rows(world, who, ref, kw):
                known = world.get(who, Powers)
                lent = known is not None and other not in known.all
                if lent:
                    known.known.append(other)
                _swing_from_reach(world, who, at, other)
                hit = probe()
                if lent:
                    with contextlib.suppress(ValueError):
                        known.known.remove(other)
                if hit:
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
        _swing_from_reach(
            world, attacker, target, basic(attacker), opportunity=True,
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


#: The damage keyword a printed trigger names, by the word the author wrote.
#: Only the ten that are damage types -- `weapon`, `martial` and the rest are
#: the `61` keyword/usage group and want a different lever.
_TYPED_TRIGGER = {
    "acid": Keyword.ACID, "cold": Keyword.COLD, "fire": Keyword.FIRE,
    "force": Keyword.FORCE, "lightning": Keyword.LIGHTNING,
    "necrotic": Keyword.NECROTIC, "poison": Keyword.POISON,
    "psychic": Keyword.PSYCHIC, "radiant": Keyword.RADIANT,
    "thunder": Keyword.THUNDER,
}


def _typed_wanted(ref: str) -> list[Keyword]:
    """Which damage keywords this row's own printed trigger names.

    **Read off `Trigger.text` rather than tried exhaustively**, and that is a
    cost decision, not a shortcut. Ten keywords in two directions is forty extra
    uses per row across 12,197 rows, and this instrument's ten minutes is the one
    number in the repo documented as un-tunable. One or two keywords is free, and
    the text is the author's own words sitting in a tracked file -- the same
    place `--never` already reads to group these.
    """
    row = get(ref)
    if row is None or not row.triggers:
        return []
    text = " ".join((t.text or "") for t in row.triggers).lower()
    return [kw for word, kw in _TYPED_TRIGGER.items()
            if re.search(rf"\b{word}\b", text)]


def _keyword_rows(world, caster: int, exclude: str, kw: Keyword) -> list[str]:  # noqa: ANN001
    """This creature's own attack rows carrying one keyword, cheapest first.

    `_area_rows`' sibling, and the same two exclusions for the same reasons: a
    triggered row cannot be used to order and the row under test must not
    provoke itself. `attack is None` as well -- an effect-only row emits no
    `Hit`, which is the whole event these callers are waiting for.
    """
    known = world.get(caster, Powers)
    if known is None:
        return []
    out = []
    for other in known.all:
        p = get(other)
        if p is None or other == exclude or p.triggers or p.attack is None:
            continue
        if kw in p.keywords:
            out.append(other)
    return out[:2]


@cache
def _typed_lenders(kw: Keyword) -> tuple[str, ...]:
    """Declared at-will attacks carrying one damage keyword, one per class.

    **One per class, because several of these triggers narrow further than the
    keyword and the harness cannot see how far.** `wizard_b._wizard_hit_with`
    asks `p.cls == "wizard"` as well as the keyword, and a predicate is a
    closure -- there is nothing to read. Spreading the candidates across
    classes is the only way to satisfy a gate that cannot be inspected, and it
    costs a handful of uses rather than a sweep.

    At-will only, and no triggered rows: a daily would spend a resource the
    rest of the audit is measuring, and a triggered row cannot be used to order.
    """
    found: list[tuple[int, str, str]] = []
    for ref, row in REGISTRY.items():
        if row.attack is None or row.triggers or kw not in row.keywords:
            continue
        if row.usage is not Usage.AT_WILL:
            continue
        found.append((row.level, row.cls, ref))
    found.sort()
    seen: set[str] = set()
    picked: list[str] = []
    for _, cls, ref in found:
        if cls in seen:
            continue
        seen.add(cls)
        picked.append(ref)
    # **One per class and no cap beyond that.** A cap of six looked thrifty and
    # silently dropped the class the gate wanted: sorted by level then name,
    # `wizard` is last alphabetically, so `f1994`'s `p.cls == "wizard"` could
    # never be met however many cold rows existed. Ten classes at most carry a
    # given damage keyword, and this list is built once per keyword for the
    # whole run.
    return tuple(picked)


def _typed_rows(world, caster: int, exclude: str, kw: Keyword) -> list[str]:  # noqa: ANN001
    """What this creature can swing to make a typed hit -- owned first, then lent.

    Owned first because it is the realistic case and costs nothing: a wizard
    holding a cold at-will was simply never asked to cast it. **Lending is the
    half that does the work**, though -- measured across the 38 rows this pass
    exists for, neither the caster nor its enemy knew a single row of the wanted
    keyword, so an owned-only pass fires none of them.
    """
    owned = _keyword_rows(world, caster, exclude, kw)
    lent = [r for r in _typed_lenders(kw) if r != exclude and r not in owned]
    return owned + lent


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


#: Kinds that only ever count when the row's own name is on them.
#:
#: **They cannot be taken from the window.** Every one of these fires
#: constantly for other creatures -- 37 `EffectApplied` land while a board is
#: being set up -- so crediting them positionally would hand a trait its
#: neighbours' work. They are stripped from the window and added back only by
#: `_claimed` below.
BY_NAME = {"EffectApplied", "ConditionEnded"}


def _claimed(world, ref: str, cursor: int) -> set[str]:  # noqa: ANN001
    """The `BY_NAME` kinds this row can be shown to have caused.

    **Why these are needed at all.** `DID_SOMETHING` had `EffectExpired` and
    not `EffectApplied`, so a row was credited for an effect *ending* and not
    for laying one -- and a trait whose whole content is a standing bonus had
    to wait for its own effect to expire inside the window to count, which for
    an encounter-long modifier never happens. 153 of the 233 rows reporting
    SILENT lay a modifier, cure a condition, change the initiative order,
    write a word on a creature or hand over a row. All real, none of it
    visible.

    **Attributed by label, which is a convention this now depends on.** An
    effect's label is the ref of the row that laid it -- `c.effect`,
    `c.bonus` and `c.condition` all stamp `label or self.ref`, and
    `durations.keywords_of` documents it. Prefix rather than equality,
    because plenty of sites stamp `"<ref> riders"` or `"<ref> rolls ..."`.

    Deliberately **not** a new field on the event. `EffectApplied` is emitted
    from one place but `Effects.apply` has 187 call sites, so threading a
    `power=` through all of them to carry what the label already carries would
    be a large change for no new information.

    The cost of the convention is **under**-crediting: a row whose label does
    not begin with its ref reports silent and gets looked at. That is the safe
    direction; over-crediting is what #216 was.
    """
    out: set[str] = set()
    for e in world.bus.log[cursor:]:
        if e.kind == "EffectApplied" and str(getattr(e, "label", "") or "").startswith(ref):
            out.add("EffectApplied")
        # `ConditionEnded.why` is the ref for a cure: `c.cure` and
        # `Effects.end` both pass the caller's ref as the reason.
        elif e.kind == "ConditionEnded" and str(getattr(e, "why", "") or "").startswith(ref):
            out.add("ConditionEnded")
    return out


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
            if p.is_attack and foe is not None:
                _swing_from_reach(world, caster, foe, other)
            else:
                use(world, caster, other, spend=False)
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
WIDE = (
    "src/combat_engine/engine/",
    # **`etl/` builds the numbers every row reads.** A monster's attack bonus,
    # damage expression, defences and reach all load from `data/game.db` and are
    # never hand-written, so a parser change can move thousands of rows -- and
    # this list did not name it, so an `etl/`-only change selected **zero**.
    # Observed: `check.py` on a tree whose only change was `etl/feat.py` reported
    # `ok audit 0.8s`, having fired nothing, and still said "all 13 clean".
    #
    # Named here as a backstop. The real dependency is the database itself, which
    # `_database_moved` checks -- a rebuild moves every number with no `etl/`
    # edit at all, and no path test can see that. #409.
    "src/combat_engine/etl/",
    # **`chargen/` is wide and has to be named here now that it is its own
    # package.** The rule below that catches a cross-cutting file works by
    # shape -- under `content/`, declaring no `@power` -- and chargen was
    # caught by it while it lived there. Outside `content/` that test never
    # runs, so a chargen change would have selected *zero* rows again, which
    # is the bug that comment describes. It builds every sheet in the game, so
    # wide is the honest answer and saying it outright is better than relying
    # on a path it no longer matches.
    "src/combat_engine/chargen/",
    "scripts/audit.py",
)

#: **Nothing. The exemption deleted itself when the file moved.**
#:
#: This used to name `engine/policy.py`: the AI policy cannot break a row -- it
#: decides what the AI *chooses* among options the rules already allow -- and
#: left inside `WIDE` it charged ten minutes for every policy change. #228's
#: argument was that the exemption was "a special case papering over a misplaced
#: file", and it was: `policy.py`, `doctrine.py` and `threat.py` are
#: `src/combat_engine/policy/` now, outside `WIDE` by being outside `engine/`,
#: and `doctrine.py` and `threat.py` were never in this list at all -- so every
#: change to either of them paid the ten minutes this was written to avoid.
#:
#: Kept as an empty tuple rather than removed, because the reasoning below still
#: holds and the next misplaced file will want it: **a policy change audits
#: nothing, and that is correct** -- this instrument is not its cover. `replay`
#: and `fight` are, both playing whole fights through the policy, and both run
#: in `check.py`.
NARROW: tuple[str, ...] = ()


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
    if any(f.startswith(WIDE) and not f.startswith(NARROW) for f in files):
        return sorted(REGISTRY)
    if _database_moved():
        return sorted(REGISTRY)

    refs: list[str] = []
    for name in files:
        if "/content/" not in name or not name.endswith(".py"):
            continue
        path = ROOT / name
        if not path.exists():
            continue
        found = re.findall(r'@power\(\s*"([^"]+)"', path.read_text())
        # **A content file that declares no rows is cross-cutting, and used to
        # audit nothing at all.** `loader.py` spawns every monster and
        # `terrain.py` dresses every board -- neither declares a `@power`, so
        # `--changed` selected *zero* rows after editing them and the routine
        # gate said nothing about a change that reaches every row in the game.
        # `chargen.py` was the third and is named in `WIDE` instead now that it
        # lives outside `content/` and this test cannot see it.
        #
        # Detected by shape rather than by a path list, so the next one is
        # caught without editing this: under `content/`, no rows declared means
        # everything depends on it.
        if not found:
            return sorted(REGISTRY)
        refs += found
    return sorted({r for r in refs if r in REGISTRY})



#: What the last **full** sweep saw, and the commit it saw it at. Tracked, because
#: the whole point is to compare across commits; one object rather than a per-ref
#: map, since 12,205 hashes churning on every run is a megabyte of diff nobody
#: reads and Camille is short of disk.
WATERMARK = ROOT / "scripts" / "fixtures" / "audited.json"


def _database_moved() -> bool:
    """Has `data/game.db` been rebuilt since anything last swept the whole tree?

    **`git status` cannot answer this.** The database is git-ignored, so a
    rebuild is invisible to `--changed` -- and every monster number is read from
    it rather than hand-written, so a rebuild can move thousands of rows at once.
    An `etl/` path test is not enough either: `build.py` run against an unchanged
    tree, which is what a compendium update looks like, moves every number with
    no source edit to notice.

    The watermark is the only timestamp available for "when did anybody last look
    at everything", because only a bare sweep writes it. So if the database is
    newer than the watermark, nothing has audited the tree since the numbers
    moved, and the narrow scope would be a lie. #409.

    Conservative on purpose: a missing watermark or database returns False and
    leaves the existing path tests to decide, rather than forcing ten minutes on
    a fresh checkout that has nothing to compare against.
    """
    db = ROOT / "data" / "game.db"
    if not db.exists() or not WATERMARK.exists():
        return False
    return db.stat().st_mtime > WATERMARK.stat().st_mtime


def _mark() -> dict[str, object]:
    import json

    if not WATERMARK.exists():
        return {}
    try:
        return json.loads(WATERMARK.read_text())
    except (OSError, ValueError):
        return {}


def _behind(sha: str) -> int:
    """How many commits have landed since the last full sweep. -1 if unknowable."""
    import subprocess

    got = subprocess.run(["git", "rev-list", "--count", f"{sha}..HEAD"],
                         cwd=ROOT, capture_output=True, text=True)
    if got.returncode != 0:
        return -1
    try:
        return int(got.stdout.strip())
    except ValueError:
        return -1


def _since(sha: str) -> list[str]:
    """Rows in content files touched since `sha`, plus anything uncommitted.

    **`--changed`'s blind spot, which is #298.** That one reads `git status`, so
    it sees only what is uncommitted -- and the moment work is committed its rows
    fall out of scope and nothing looks at them again until somebody edits the
    file for an unrelated reason. Six silent rows were found that way on #275 and
    fourteen more on #278: roughly one surfaced per file touched, by accident.

    This closes it with one tracked number instead of a per-ref ledger. The same
    widening rules apply -- an `engine/` change is not narrowable and a content
    file declaring no rows is cross-cutting -- so this delegates both to
    `_changed`'s own logic by diffing the two revisions and reusing the shape
    tests.
    """
    import re
    import subprocess

    got = subprocess.run(["git", "diff", "--name-only", f"{sha}..HEAD"],
                         cwd=ROOT, capture_output=True, text=True)
    if got.returncode != 0:
        return sorted(REGISTRY)
    files = [f.strip() for f in got.stdout.splitlines() if f.strip()]
    if any(f.startswith(WIDE) and not f.startswith(NARROW) for f in files):
        return sorted(REGISTRY)
    refs: list[str] = []
    for name in files:
        if "/content/" not in name or not name.endswith(".py"):
            continue
        path = ROOT / name
        if not path.exists():
            continue
        found = re.findall(r'@power\(\s*"([^"]+)"', path.read_text())
        if not found:
            return sorted(REGISTRY)
        refs += found
    # Uncommitted work too: a sweep is only honest about *now*.
    return sorted({r for r in refs + _changed() if r in REGISTRY})


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
                out.events |= (mine_now - PROVOKE_NOISE - BY_NAME) | (
                    {"DamageApplied"} if dealt_now else set()
                ) | _claimed(world, ref, world.fight_cursor) | _own_unbinding(
                    world, world.fight_cursor
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
                out.events |= (mine - PROVOKE_NOISE - BY_NAME) | (
                    {"DamageApplied"} if dealt else set()
                ) | _claimed(world, ref, cursor)
                out.events |= _own_movement(world, ref, cursor, caster)
                out.events |= _own_unbinding(world, cursor)
                if set(world.effects.live) - had:
                    out.events.add("ConditionApplied")
                continue
            if not _use_with_any_grip(world, caster, ref):
                continue
            out.fired += 1
            # This last-resort path credits every event name in the window
            # wholesale, which is deliberate and much looser than the two
            # above. Only `RelationCleared` is held back, and only because
            # every attack emits one: see `PROVOKE_NOISE`. Subtracting the
            # whole of `PROVOKE_NOISE` here would re-judge a great many rows
            # that have nothing to do with this change.
            out.events |= (
                {e.kind for e in world.bus.log[cursor:]} - {"RelationCleared"}
            ) | _own_unbinding(world, cursor)
            if set(world.effects.live) - had:
                out.events.add("ConditionApplied")
        except Exception:  # the traceback is the finding
            out.error = traceback.format_exc()
            return out
    return out


def _why_never(never: list[Result]) -> None:
    """Group the rows the harness could not use by what is in the way.

    **A count is not a work queue**, which is why nobody had read this set: the
    figure has been printed for months and the refs never were. #214's own last
    comment names the interesting minority -- the rows that declare no trigger,
    carry no Requirement, and still could not be used -- and that group is only
    visible if the set is grouped rather than totalled.

    The order matters: a row with a trigger is waiting for something to fire and
    is explained, so it is reported first and dismissed. What is left is the
    diagnosable part.
    """
    from collections import Counter

    triggered: Counter = Counter()
    gated: list[str] = []
    bare: list[str] = []
    for r in never:
        row = REGISTRY.get(r.ref)
        if row is None:
            continue
        if getattr(row, "on", None) is not None:
            # **`on=` may be a tuple of triggers**, and assuming one crashed this
            # on the full corpus -- so the flag worked on every narrow set it was
            # tried against and died the first time it was asked the question it
            # exists for. A row with two trigger events is counted under each,
            # because "what is this waiting for" has two answers and either
            # firing would explain it.
            for trig in (row.on if isinstance(row.on, tuple) else (row.on,)):
                event = getattr(trig, "event", None)
                if event is None:
                    continue
                triggered[event.__name__ if isinstance(event, type)
                          else type(event).__name__] += 1
        elif getattr(row, "requires", None) is not None or getattr(row, "requires_text", ""):
            gated.append(r.ref)
        else:
            bare.append(r.ref)
    if triggered:
        print("      waiting for a trigger to fire, by event:")
        for name, n in triggered.most_common(8):
            print(f"        {name:<22} {n}")
    if gated:
        print(f"      a Requirement the board cannot meet: {len(gated)}")
        print("        " + ", ".join(sorted(gated)[:10])
              + (" ..." if len(gated) > 10 else ""))
    if bare:
        print(f"      **no trigger and no Requirement, and still unusable: "
              f"{len(bare)}**")
        print("        " + ", ".join(sorted(bare)[:16])
              + (" ..." if len(bare) > 16 else ""))
    # **Every ref, not a sample of them.** A change to what the board hands a
    # row moves this set in both directions at once, and the last attempt at one
    # was net zero on the count while breaking four rows -- only diffing the
    # refs showed it. A truncated list cannot be diffed, so the whole set goes
    # to a file and the summary above stays readable.
    out = Path("logs") / "never.txt"
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(sorted(r.ref for r in never)) + "\n")
        print(f"      every ref: {out}")
    except OSError:
        pass


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
    ap.add_argument("--since", action="store_true",
                    help="only rows in content files touched since the last "
                         "full sweep. `--changed` sees uncommitted work only, "
                         "so a committed row goes unlooked-at until its file is "
                         "edited again -- see #298 and `_since`")
    ap.add_argument("--never", action="store_true",
                    help="list the rows the harness could not use, grouped by why")
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

    mark = _mark()
    full = not (args.refs or args.calls or args.changed or args.since
                or args.sample or args.cls or args.level or args.monsters)
    # **Said on every run, the way `scorecard.py` says its baseline age.** #291's
    # point, and #298 asks for it here: a sweep nobody has run for 200 commits is
    # a coverage figure, and until it is printed it is not one.
    if mark.get("sha"):
        behind = _behind(mark["sha"])
        print(f"# last full sweep: {mark['sha'][:9]}"
              + (f", {behind} commit(s) ago" if behind >= 0 else "")
              + f" -- {mark.get('silent', '?')} silent of "
                f"{mark.get('fired', '?')} firing\n")
    elif not args.verdicts:
        print("# no full sweep on record. A bare `audit.py` writes one.\n")

    wanted = args.refs or (
        _calls(args.calls) if args.calls
        else _changed() if args.changed
        else _since(mark["sha"]) if args.since and mark.get("sha")
        else sorted(REGISTRY)
    )
    if args.since and not mark.get("sha"):
        print("# --since has no watermark to work from; auditing everything.\n")
    elif args.since and not args.refs:
        print(f"# {len(wanted)} row(s) in files touched since the last full "
              f"sweep, plus anything uncommitted.\n")
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
    retired: list[tuple[str, tuple[str, ...], str]] = []
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
        if p.obsolete:
            # **Retired by a rules change, not unfinished.** `usable` refuses it
            # for a different reason than `todo` does, and firing it would only
            # prove the refusal works. Its own bucket: counted with the `todo`
            # rows it would read as waiting for something, and counted done it
            # would read as playing.
            retired.append((ref, (p.obsolete,), "GONE"))
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
            # like anything else -- and because it is in `chosen`, a dropped
            # row that fires **is counted in the headline**. That is correct:
            # the headline claims "fires and does something" and a dropped row
            # does both.
            #
            # This comment used to say it was "reported beside the `todo` rows
            # rather than counted done", which was false in the second half --
            # and `dropped=` is the marker a monster wave reaches for most, so
            # the figure is printed separately below rather than left to be
            # read as finished.
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

    broken, silent, never, known_quiet, outgrown = [], [], [], [], []
    for r in _run_all(chosen, args.jobs):
        if r.error:
            broken.append(r)
        elif r.fired == 0:
            never.append(r)
        elif r.silent and r.ref not in KNOWN_SILENT:
            silent.append(r)
        elif r.silent:
            known_quiet.append(r)
        else:
            # **An excuse that has stopped being true is a loosening already
            # in place.** `stale` above catches an entry naming a row that no
            # longer exists; nothing caught the commoner case -- the board
            # grew the thing the entry said it lacked, the row began working,
            # and the argument for it sat here unread, ready to swallow the
            # row again the day it broke.
            #
            # **Thirteen of the fifty-two entries were in that state** the
            # first time this ran, `p6990` among them: it argued that nothing
            # on the board swears an oath, and by then `_use_class_features`
            # was being called from `board()` and the oath was sworn on all
            # five seeds.
            #
            # The same shape as `todo.py` failing when a symbol it waits for
            # arrives. A row that works needs no argument for why it does not.
            if r.ref in KNOWN_SILENT:
                outgrown.append(r)
            if args.verbose:
                print(f"  ok      {r.ref:<10} {', '.join(sorted(r.events & DID_SOMETHING))}")

    for r in broken:
        print(f"\n  RAISED  {r.ref}")
        print("      " + r.error.strip().replace("\n", "\n      ")[-900:])
    # **The 223 are a measurement, and this used to treat them as a failure.**
    # The watermark recorded `silent: 223` and the verdict compared the count
    # against zero, so the instrument failed for finding exactly what it had
    # written down -- and `check.py` reported `FAIL audit` on every run whose
    # scope reached any of them, which since an `engine/` change widens to the
    # whole tree is most runs. A check that cannot pass stops being read.
    #
    # So the baseline is **per ref**, not a count, and that is strictly stricter
    # than the count ever was rather than looser. A count cannot tell a narrow
    # run anything: `--changed` over 600 rows finding 4 silent says nothing
    # about 223. Worse, a sweep where ten rows healed and ten different rows
    # broke reads as 223 and passes under any count-based gate. Per ref:
    #
    # * a silent row **in** the list is carried -- named, not a failure;
    # * a silent row **not in** it is a regression -- red, with the ref;
    # * a listed row that does something now is `leaks.DEFERRED`'s case -- the
    #   work landed, so say so and tighten the list. Also red, because a stale
    #   entry is a loosening already in place.
    #
    # Only refs actually audited this run are judged, or a narrow run would
    # report every absent baseline row as healed.
    base = set(mark.get("silent_refs") or ())
    graded = bool(base)
    fresh = [r for r in silent if r.ref not in base] if graded else list(silent)
    carried = [r for r in silent if r.ref in base] if graded else []
    looked = set(chosen)
    quiet_now = {r.ref for r in silent} | {r.ref for r in known_quiet}
    quiet_now |= {r.ref for r in never} | {r.ref for r in broken}
    healed = sorted((base & looked) - quiet_now) if graded else []

    for r in fresh:
        print(f"  SILENT  {r.ref:<10} fired {r.fired}/{TRIES} times and did nothing")
    for r in carried:
        print(f"  carried {r.ref:<10} silent at the last full sweep too")
    for r in never:
        print(f"  UNUSED  {r.ref:<10} could not be used on the test board at all")
    for r in known_quiet:
        print(f"  quiet   {r.ref:<10} {KNOWN_SILENT[r.ref]}")
    for r in outgrown:
        print(f"  OUTGROWN {r.ref:<9} does something now -- delete its KNOWN_SILENT entry")
        print(f"      the entry still argues: {KNOWN_SILENT[r.ref]}")
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

    # **An excused row does not do something.** `known_quiet` was left in
    # this total, so every entry in `KNOWN_SILENT` was counted in the same
    # breath as the rows that work -- 38 of them, inside a headline that says
    # "fire and do something". Excusing a row is an argument for why the
    # board cannot exercise it, which is the opposite of the claim. Counted
    # on its own line below instead.
    ok = len(chosen) - len(broken) - len(silent) - len(never) - len(known_quiet)
    # **An empty scope is a skip, not a pass.** `--changed` reads `git status`, so
    # on a clean tree it selects nothing and this printed "0 of 0 rows fire and do
    # something" -- which `check.py` rendered as `ok audit 0.4s`, indistinguishable
    # from a sweep that found nothing wrong. That is the one thing
    # `scripts/CLAUDE.md` says an instrument must never do: report a skip as a
    # skip rather than passing. The exit code is unchanged -- nothing was wrong,
    # because nothing was looked at -- but the line now says which.
    if not chosen:
        print("\n  SKIPPED -- no row was in scope, so nothing was checked")
        print("  (`--changed` reads `git status`; on a clean tree use `--since` "
              "for everything touched since the last full sweep)")
        return 0
    print(f"\n  {ok} of {len(chosen)} rows fire and do something")
    # **Fires and does something is not the same as finished.** A `dropped=`
    # row is fired and lands in this total, which is honest about what it did
    # and silent about the clause that is missing. Printed on its own line so
    # the headline cannot be read as a completion figure.
    playing = sum(1 for ref, _w, how in partial if how == "DROP")
    if playing:
        print(f"  {playing} of those play with a clause missing -- "
              f"counted here because they fire, not because they are done")
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
    if retired:
        print(f"  {len(retired)} retired by a rules change, not fired: "
              + ", ".join(ref for ref, _, _ in retired[:6])
              + (" ..." if len(retired) > 6 else ""))
    if broken or silent:
        if graded:
            print(f"  {len(broken)} raise, {len(fresh)} newly silent, "
                  f"{len(carried)} silent at the last full sweep too")
        else:
            print(f"  {len(broken)} raise, {len(silent)} silent")
    if healed:
        print(f"  {len(healed)} row(s) do something now -- remove from "
              f"`silent_refs` in {WATERMARK.name}: " + ", ".join(healed[:8])
              + (" ..." if len(healed) > 8 else ""))
    if not graded and silent:
        print(f"  (no per-ref baseline in {WATERMARK.name}, so every silent row "
              f"counts as new. A bare `audit.py` writes one.)")
    if never:
        print(f"  {len(never)} never usable here -- often a Requirement the board cannot meet")
        if args.never:
            _why_never(never)
    if refused:
        print(f"  {len(refused)} negotiable event(s) ignored a refusal")
    if known_quiet:
        print(f"  {len(known_quiet)} silent for a recorded reason, not counted above")
    if outgrown:
        print(f"  {len(outgrown)} excuse(s) outlived the thing they excused")
    # **A full sweep leaves its watermark.** Only a full one: a narrowed run
    # has not looked at the rest of the tree and recording it as though it had
    # is how a coverage number becomes a lie. Written whatever the verdict,
    # because the question it answers is "when did anybody last look", not
    # "did it pass".
    if full:
        import json
        import subprocess

        got = subprocess.run(["git", "rev-parse", "HEAD"],
                             cwd=ROOT, capture_output=True, text=True)
        if got.returncode == 0:
            WATERMARK.write_text(json.dumps({
                "sha": got.stdout.strip(),
                "refs": len(chosen),
                "fired": ok,
                "silent": len(silent),
                "never": len(never),
                # **The refs, not just the count.** See the note beside `base`
                # above: a count cannot tell a narrow run whether its silent
                # rows are the known ones, and cannot see ten healing while
                # ten break. Written by a full sweep only, like the rest.
                "silent_refs": sorted(r.ref for r in silent),
            }, indent=2) + "\n")
            print(f"\n  watermark written at {got.stdout.strip()[:9]}")

    # `refused` fails the run. An engine that announces a thing and then
    # does it anyway is a worse fault than any single row being wrong, and
    # it is the one that has been silent four times.
    # `fresh` rather than `silent`: a carried row is the recorded baseline,
    # and `healed` fails because a stale entry is a loosening already in place.
    return 1 if (broken or fresh or healed or refused or outgrown) else 0


if __name__ == "__main__":
    raise SystemExit(main())
