# The class features were never imported

## What is wrong

`data/game.db`'s `class` table has 25 rows and **no rules text** — only
`hp_first`, `hp_per_level`, `surges`, `defences`, `armour`, `weapons`,
`implements`, `abilities`.

The upstream `compendium.sqlite` has a `Class` table with **77 rows**,
each carrying `Txt` (HTML) and `PlainTxt` of 3k–75k characters. That text
contains every class feature, in a clean structure:

```
<b>Class features:</b>        the names, as a list
<h3>CENTERED BREATH MONK</h3> one per build: Class Feature, Suggested
<h3>IRON SOUL MONK</h3>       Skills, At-Will / Encounter / Daily powers
<h3>STONE FIST MONK</h3>
<h3>MONK CLASS FEATURES</h3>  the definitions themselves
<h3>IMPLEMENTS</h3>
```

`etl/build.py` reads `Power`, `Monster` and the numeric half of `Class`.
It never reads `Class.Txt`.

## What that caused

**`spec.py` returns nothing for any `cf:` ref.** Every agent that hit one
concluded "no printed text exists" and either refused the row or wrote it
from the paraphrase in `docs/blocked.json`. Both outcomes are recorded in
today's commits as if the text were unavailable. It was one table away.

* **31 invented `cf:` refs.** Five classes have no `Feature` power row at
  all — Fighter, Ranger, Rogue, Sorcerer, Wizard — so their features exist
  only as `cf:` refs written from guesswork. `cf:sorcerer-soul` was
  invented outright to give `p3763` something to change, and its 5/10/15
  ladder was read off `p3763`'s own tier line. `cf:rogue-tactic-club`'s
  two weapon groups and its Strength rider came from the `blocked.json`
  note, not from a card.
* **Two refusals today were wrong.** `p11215` and `p12792` name Monk and
  Seeker features that **are** in the tree as `p` rows (`p9501` is the
  Seeker one; the five Monk `Feature` rows are the Flurry variants). The
  agents searched for `cf:monk-*`, found none, and reported the ref as
  nonexistent.
* **`p3369` is writable.** Swordmage Warding is in the upstream text; the
  agent grepped for the *name*, which is the one thing deliberately
  stripped everywhere.
* **The `chargen.BUILDS` gaps are the same story.** Upstream carries
  Fighter Knight/Slayer/Weaponmaster, Rogue Scoundrel/Thief, four Wizard
  builds, and for each one the skills and suggested powers. Every
  `blocked.json` note asking for "a leg in `chargen.BUILDS[...]`" has real
  text behind it.

Power **rows** are at 100% (3,420/3,436). That number is honest and it is
also not the whole picture: the features those rows lean on are the part
built from paraphrase.

## The work

1. **Extend the ETL.** A `class_feature` table in `data/game.db`: class,
   build, feature ref, mechanics text. Names go to
   `localization/names.json` like every other printed name, so
   `scripts/leaks.py` keeps covering the tree. Parse the `<h3>` sections;
   do not regex the prose into code.
2. **Teach `spec.py` to answer `cf:` refs** from it. That is what every
   agent asks first, and the silence is what produced the guesses.
3. **Re-do the 31 `cf:` features against the real text.** Expect the
   invented ones to be wrong in detail. `cf:sorcerer-soul` and
   `cf:rogue-tactic-club` are known guesses and should be checked first.
4. **Fill `chargen.BUILDS` from the build sections**, which also settles
   `cf:fighter-talent-rest`, `cf:ranger-style`, `cf:warlord-shield` and
   the two warlock legs.
5. **Write `p3369`, `p11215`, `p12792`** — 1 and 2 are not needed for the
   last two, only the right ref.

## Verification

* `uv run scripts/build.py` rebuilds cleanly and `leaks.py` stays clean —
  the new text must not reach tracked source.
* `uv run scripts/check.py --all`.
* The audit must not lose rows: several features are fired up front by
  `board()`, so changing one changes what every row of that class sees.
* `replay` will diverge if a feature's numbers change. Read it; a
  corrected feature is a legitimate re-record, an accidental one is not.

## A second gap the import revealed

Features that are *not implemented at all* — no `cf:` ref, no `Feature`
power row, and **no `docs/blocked.json` entry**, so nothing anywhere
records them as missing. Confirmed for the avenger: the +3 AC while in
cloth and unshielded, the three censures, and Channel Divinity.

Counting imported features against `cf:` refs plus `Feature` power rows
per class does not settle it — the same feature is often both a prose
entry here and a power card there, so the two overlap. The classes whose
numbers do not add up and want a read:

| class | imported | `cf:` refs | Feature rows |
|---|---|---|---|
| Druid | 4 | 0 | 1 |
| Bard | 7 | 0 | 2 |
| Avenger | 4 | 1 | 3 |
| Runepriest | 3 | 0 | 1 |
| Warden | 3 | 0 | 2 |

The right instrument is a per-class read, not a count: match each
imported feature to its implementation or to a `blocked.json` entry, and
whatever is left over is the answer to "is this class finished".

Worth making that a ninth instrument once the numbers settle, because
"no row records this as missing" is exactly the failure this whole
exercise was: the tree looked complete because nothing was tracking the
absence.
