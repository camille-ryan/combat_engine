# What is left

Supersedes `starry-purring-petal.md`, which is fully executed: penalties
bucket by source, the bonus default is untyped, the duplicated content
helpers are gone, and its 183 blocked rows are down to 13. Its §4 row
list is obsolete — read this instead.

Also gathers the engine problems that were only recorded in agent
reports, each re-checked against the tree today.

## 1. Powers — 13 rows, all tracked

3,423 of 3,436. Every undeclared row has a `docs/blocked.json` entry;
none is untracked. Three groups, and only one of them is work:

**Three want a ref the compendium does not contain** (`p11603`,
`p14510`, `p5591`). `spec.py` folds two printed stanzas into one entry
with no second id, and the guardian forms bundle their attack under the
form's own ref. Inventing an id would be inventing content. These stay
blocked unless the source data changes — they are not a to-do.

**Seven want an engine change**: an event announcing a power use's
*finished* set of attack rolls (`p10354`), a `hand` key in the attack
context (`p7399`), `AttackResult.parity` (`p5845`), a run action
(`p4396`), link-aware distance (`p13887`), a plural companion API
(`p3839`), and `Summon.instinctive` (`p9665`).

**Three want content that is not in chargen**: a thrown weapon or sling
(`p10744`), `Keyword.RAGE` on the 41 rage rows (`p4807`), a stat block
for a summoned creature (`p13984`).

## 2. Class features — the live gap

**Features that are not implemented and that nothing records as
missing**: no `cf:` ref, no `Feature` power row, no `blocked.json`
entry. This is the same failure as the import itself — the tree looks
complete because nothing tracks the absence.

Confirmed: the avenger's three (the +3 AC unarmoured, the three
censures, Channel Divinity) and the barbarian's three (+1 AC and Reflex
out of heavy armour, the Feral Might fork, a melee basic on a crit),
plus the Berserker's Poised Defender. Suspected on the same shape:
druid, bard, runepriest, warden.

**The right instrument is a per-class read**, matching each of the 99
imported features to an implementation or to a tracked entry. Counting
does not settle it — a feature is often both a prose entry and a power
card. Worth making a ninth instrument once the shape is known.

Also: `class_feature` imports one page per class and build, so variant
pages are missed. `cf:barbarian-aura` is correct and comes from a
Heroes of the Feywild page the importer never sees.

## 3. Engine, re-checked today

**Both of these make something just written inert:**

* `chargen._arms` has no branch for light or heavy blades, so the
  swordmage falls through to simple melee and carries a mace — which
  makes the warding written today **0 on every swordmage the tree
  deals**.
* `chargen.Gear` takes `shield` from the `ClassLine`, not the `Build`,
  so the new great-weapon leg wields a greataxe **and** keeps a
  heavy shield's +2 AC.

**Silently wrong, nothing catches it:**

* `movement.step` ignores `Position.spans`. It recomputes a footprint
  for the collision check and for `grid.place` but never clears the
  explicit one, so anything with a footprint that is then moved keeps a
  stale `spans` and `Position.squares` reports where it used to be.
* `grid.place` never overwrites, and `Position` does not know. Putting
  anything into a square a `Barrier` already indexes leaves it
  unindexed while `Position` still names the square.
* Restoring `Health.max_hp` from an `on_end` can make `query.alive`
  answer True for a creature whose `Died` has already fired, because
  `bereave` runs inside `_die`.
* `chargen.loadout` hands every character every level-0 row of its
  class, which defeats any feature whose content is "you gain ⟨power⟩"
  — `c.grant_row` returns `None`, so exclusivity has to be written as a
  forbid instead.
* Nothing caps a shot at long range. `_long_range` applies the −2, but
  `Weapon.ranged`'s second number still has no reader anywhere.

**Known and documented rather than fixed:**

* `PowerUsed` is announced before the body runs, and nothing announces
  a finished use. In `AUTHORING.md` now. It is why `p10354` is blocked
  and why `p11215` resolves its repeat before the first.
* `spec.py --level 0` prints usage instead of rows — falsy-int argparse.

**One unexplained fight:** seed 21 runs to the 31-round cap with `m264`
untouched at 22/22 while three other monsters die. Not the stance bug —
zero swaps. A monster the party cannot reach or cannot finish.

## 4. Deferred by Camille

Browser tests, held until the backend is done, and when they resume
they want **a verbose log that emits every event**.

## Order

1. The two chargen bugs in §3 — they make today's work inert, and both
   are small.
2. The per-class feature read in §2, which is the last place the tree
   can be quietly incomplete.
3. The seven engine changes in §1, cheapest first.
4. Then browser.
