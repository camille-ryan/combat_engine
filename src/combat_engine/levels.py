"""The printed level each chassis feature is gained at, read once.

`class_feature` in `game.db` has **no level column** -- `#1261` -- so every
class feature imports at level 0 and `chargen.ladder_row` dealt all of them
to a 1st-level character. Measured before this landed: a dealt fighter held
**26** `cf:fighter-knight-f*` rungs, 27th-level features included, and
`audit.board`'s caster carried 92 known rows.

The level cannot be read out of the database, and that issue's own premise
-- *"the level cannot be recovered by reading the import harder"* -- is
**false for 169 of 395 rungs**. So this is route 2 of the two it names: a
per-chassis map read off the printed page by hand. Below every component,
imports nothing, and a table rather than behaviour -- `armour.py` and
`dc.py` are the precedent and the same argument.

## Where each number came from

Four printed sources, and the provenance is on every line so a reader can
check one entry without re-deriving the set:

    compendium name       169  the name itself begins `Level N ` --
                               `cf:fighter-slayer-f3` is printed "Level 3
                               Improved Power Strike". This is in the
                               compendium and needed no page at all
    progression table      91  the class page's level/feature table, e.g.
                               `2,250 3 -- Improved Power Strike`, joined
                               on the feature's printed name
    `Level N:` heading     70  the body heading above the feature's own text
    first block            57  named by no table row and no heading, so it
                               belongs to the chassis's 1st-level block.
                               6 of these are a *list* the chassis grants at
                               1st level -- stances, knacks, at-will powers
    f3583's card            2  *"Choose one of the 7th level Weapon
                               Specialization options of the knight or the
                               slayer"* -- a feat naming another chassis's
                               level, which is the only source for those two

Books: `Heroes of The Fallen Lands.pdf`, `Heroes of The Forgotten
Kingdoms.pdf`, `Players Option - Heroes of Shadow.pdf`. All in `resources/`.

## What could not be verified

**Six rungs, and they are named in `UNVERIFIED` below.** The bladesinger's
book is **not in `resources/`**: searched all 18 PDFs for its distinctive
feature text and none contains it -- the body-text search
`scripts/CLAUDE.md` recommends, not a heading search, so this is an absence
rather than a failed match. They are entered at 1, which is what the tree
did for every rung before this file existed, so those six are no worse off
and the next reader is told which they are.

**A level here is the rung's own, not the character's.** A sub-option
(`cf:X-fNsM`) is gained with its parent, so `level_of` resolves it to the
parent rather than carrying 295 more entries that could disagree with it.
"""

from __future__ import annotations

import re

#: `cf:<class>-<chassis>-f<N>` -- a parent rung, which is what carries a level.
_PARENT = re.compile(r"^(cf:[a-z']+-[a-z']+-f\d+)(?:[sc]\d+)?$")

#: The six rungs whose printed level is not in `resources/`, entered at 1.
#: Named rather than counted so a reader can see which answers are soft.
UNVERIFIED = frozenset({
    "cf:wizard-bladesinger-f6",
    "cf:wizard-bladesinger-f7",
    "cf:wizard-bladesinger-f10",
    "cf:wizard-bladesinger-f13",
    "cf:wizard-bladesinger-f16",
    "cf:wizard-bladesinger-f21",
})

#: ref -> the level the page says it is gained at. Parents only; a
#: sub-option takes its parent's, which `level_of` does.
FEATURE_LEVEL: dict[str, int] = {
    # -- assassin-executioner ------------------------------------------
    "cf:assassin-executioner-f0":             1,  # `Level N:` heading
    "cf:assassin-executioner-f1":             1,  # `Level N:` heading
    "cf:assassin-executioner-f2":             1,  # `Level N:` heading
    "cf:assassin-executioner-f3":             1,  # `Level N:` heading
    "cf:assassin-executioner-f4":             1,  # first block
    "cf:assassin-executioner-f5":             1,  # progression table
    "cf:assassin-executioner-f6":             2,  # compendium name
    "cf:assassin-executioner-f7":             3,  # progression table
    "cf:assassin-executioner-f8":             4,  # `Level N:` heading
    "cf:assassin-executioner-f9":             5,  # compendium name
    "cf:assassin-executioner-f10":            6,  # compendium name
    "cf:assassin-executioner-f11":            7,  # progression table
    "cf:assassin-executioner-f12":            8,  # `Level N:` heading
    "cf:assassin-executioner-f13":            9,  # compendium name
    "cf:assassin-executioner-f14":           10,  # compendium name
    "cf:assassin-executioner-f15":           13,  # compendium name
    "cf:assassin-executioner-f16":           15,  # compendium name
    "cf:assassin-executioner-f17":           16,  # `Level N:` heading
    "cf:assassin-executioner-f18":           17,  # progression table
    "cf:assassin-executioner-f19":           19,  # compendium name
    "cf:assassin-executioner-f20":           22,  # progression table
    "cf:assassin-executioner-f21":           23,  # compendium name
    "cf:assassin-executioner-f22":           25,  # compendium name
    "cf:assassin-executioner-f23":           29,  # compendium name
    # -- barbarian-berserker -------------------------------------------
    "cf:barbarian-berserker-f0":              1,  # first block
    "cf:barbarian-berserker-f1":              1,  # progression table
    "cf:barbarian-berserker-f2":              1,  # first block
    "cf:barbarian-berserker-f3":              1,  # first block
    "cf:barbarian-berserker-f4":              1,  # first block
    # -- bard-skald ----------------------------------------------------
    "cf:bard-skald-f0":                       1,  # first block
    "cf:bard-skald-f1":                       1,  # first block
    "cf:bard-skald-f2":                       1,  # first block
    "cf:bard-skald-f3":                       1,  # first block
    "cf:bard-skald-f4":                       1,  # first block
    "cf:bard-skald-f5":                       1,  # first block
    # -- cleric-templar ------------------------------------------------
    "cf:cleric-templar-f0":                   1,  # `Level N:` heading
    "cf:cleric-templar-f1":                   1,  # first block
    "cf:cleric-templar-f2":                   1,  # progression table
    "cf:cleric-templar-f3":                   1,  # first block
    # -- cleric-warpriest ----------------------------------------------
    "cf:cleric-warpriest-f0":                 1,  # `Level N:` heading
    "cf:cleric-warpriest-f1":                 1,  # `Level N:` heading
    "cf:cleric-warpriest-f2":                 1,  # progression table
    "cf:cleric-warpriest-f3":                 3,  # compendium name
    "cf:cleric-warpriest-f4":                 4,  # `Level N:` heading
    "cf:cleric-warpriest-f5":                 5,  # compendium name
    "cf:cleric-warpriest-f6":                 7,  # compendium name
    "cf:cleric-warpriest-f7":                 8,  # `Level N:` heading
    "cf:cleric-warpriest-f8":                10,  # compendium name
    "cf:cleric-warpriest-f9":                13,  # compendium name
    "cf:cleric-warpriest-f10":               17,  # compendium name
    "cf:cleric-warpriest-f11":               23,  # compendium name
    "cf:cleric-warpriest-f12":               27,  # compendium name
    "cf:cleric-warpriest-f13":                1,  # compendium name
    "cf:cleric-warpriest-f14":                2,  # compendium name
    "cf:cleric-warpriest-f15":                5,  # compendium name
    "cf:cleric-warpriest-f16":                6,  # compendium name
    "cf:cleric-warpriest-f17":                9,  # compendium name
    "cf:cleric-warpriest-f18":               10,  # compendium name
    "cf:cleric-warpriest-f19":               15,  # compendium name
    "cf:cleric-warpriest-f20":               16,  # compendium name
    "cf:cleric-warpriest-f21":               19,  # compendium name
    "cf:cleric-warpriest-f22":               22,  # compendium name
    "cf:cleric-warpriest-f23":               25,  # compendium name
    "cf:cleric-warpriest-f24":               29,  # compendium name
    # -- druid-protector -----------------------------------------------
    "cf:druid-protector-f0":                  1,  # first block
    "cf:druid-protector-f1":                  1,  # first block
    "cf:druid-protector-f2":                  1,  # first block
    "cf:druid-protector-f3":                  1,  # first block
    # -- druid-sentinel ------------------------------------------------
    "cf:druid-sentinel-f0":                   1,  # progression table
    "cf:druid-sentinel-f1":                   1,  # `Level N:` heading
    "cf:druid-sentinel-f2":                   1,  # `Level N:` heading
    "cf:druid-sentinel-f3":                   1,  # progression table
    "cf:druid-sentinel-f4":                   1,  # `Level N:` heading
    "cf:druid-sentinel-f5":                   3,  # compendium name
    "cf:druid-sentinel-f6":                   7,  # `Level N:` heading
    "cf:druid-sentinel-f7":                   7,  # compendium name
    "cf:druid-sentinel-f8":                   8,  # `Level N:` heading
    "cf:druid-sentinel-f9":                  13,  # progression table
    "cf:druid-sentinel-f10":                 17,  # progression table
    "cf:druid-sentinel-f11":                 23,  # progression table
    "cf:druid-sentinel-f12":                 27,  # progression table
    "cf:druid-sentinel-f13":                  1,  # first block, a list
    "cf:druid-sentinel-f14":                  1,  # compendium name
    "cf:druid-sentinel-f15":                  1,  # compendium name
    "cf:druid-sentinel-f16":                  2,  # compendium name
    "cf:druid-sentinel-f17":                  5,  # compendium name
    "cf:druid-sentinel-f18":                  6,  # compendium name
    "cf:druid-sentinel-f19":                  9,  # compendium name
    "cf:druid-sentinel-f20":                 10,  # compendium name
    "cf:druid-sentinel-f21":                 15,  # compendium name
    "cf:druid-sentinel-f22":                 16,  # compendium name
    "cf:druid-sentinel-f23":                 19,  # compendium name
    "cf:druid-sentinel-f24":                 22,  # compendium name
    "cf:druid-sentinel-f25":                 25,  # compendium name
    "cf:druid-sentinel-f26":                 29,  # compendium name
    # -- fighter-knight ------------------------------------------------
    "cf:fighter-knight-f0":                   1,  # `Level N:` heading
    "cf:fighter-knight-f1":                   1,  # progression table
    "cf:fighter-knight-f2":                   1,  # `Level N:` heading
    "cf:fighter-knight-f3":                   1,  # `Level N:` heading
    "cf:fighter-knight-f4":                   1,  # first block
    "cf:fighter-knight-f5":                   1,  # `Level N:` heading
    "cf:fighter-knight-f6":                   3,  # compendium name
    # first block: the knight's table names only the improved one, at 9
    "cf:fighter-knight-f7":                   1,
    "cf:fighter-knight-f8":                   5,  # progression table
    "cf:fighter-knight-f9":                   7,  # f3583's card
    "cf:fighter-knight-f10":                  7,  # compendium name
    "cf:fighter-knight-f11":                  8,  # `Level N:` heading
    "cf:fighter-knight-f12":                  9,  # progression table
    "cf:fighter-knight-f13":                 13,  # compendium name
    "cf:fighter-knight-f14":                 15,  # progression table
    "cf:fighter-knight-f15":                 16,  # `Level N:` heading
    "cf:fighter-knight-f16":                 17,  # compendium name
    "cf:fighter-knight-f17":                 19,  # progression table
    "cf:fighter-knight-f18":                 22,  # progression table
    "cf:fighter-knight-f19":                 23,  # progression table
    "cf:fighter-knight-f20":                 25,  # progression table
    "cf:fighter-knight-f21":                 29,  # progression table
    "cf:fighter-knight-f22":                  1,  # first block, a list
    "cf:fighter-knight-f23":                  2,  # compendium name
    "cf:fighter-knight-f24":                  6,  # compendium name
    "cf:fighter-knight-f25":                 10,  # compendium name
    # -- fighter-slayer ------------------------------------------------
    "cf:fighter-slayer-f0":                   1,  # progression table
    "cf:fighter-slayer-f1":                   1,  # `Level N:` heading
    "cf:fighter-slayer-f2":                   1,  # `Level N:` heading
    "cf:fighter-slayer-f3":                   3,  # compendium name
    "cf:fighter-slayer-f4":                   1,  # first block
    "cf:fighter-slayer-f5":                   5,  # progression table
    "cf:fighter-slayer-f6":                   7,  # compendium name
    "cf:fighter-slayer-f7":                   9,  # progression table
    "cf:fighter-slayer-f8":                  13,  # compendium name
    "cf:fighter-slayer-f9":                  15,  # progression table
    "cf:fighter-slayer-f10":                 16,  # `Level N:` heading
    "cf:fighter-slayer-f11":                 17,  # compendium name
    "cf:fighter-slayer-f12":                 19,  # progression table
    "cf:fighter-slayer-f13":                 22,  # progression table
    "cf:fighter-slayer-f14":                 23,  # progression table
    "cf:fighter-slayer-f15":                 24,  # `Level N:` heading
    "cf:fighter-slayer-f16":                 25,  # progression table
    "cf:fighter-slayer-f17":                 29,  # progression table
    "cf:fighter-slayer-f18":                  1,  # first block, a list
    "cf:fighter-slayer-f19":                  2,  # compendium name
    "cf:fighter-slayer-f20":                  6,  # compendium name
    "cf:fighter-slayer-f21":                  7,  # f3583's card
    "cf:fighter-slayer-f22":                 10,  # compendium name
    # -- fighter-weaponmaster ------------------------------------------
    "cf:fighter-weaponmaster-f0":             1,  # first block
    "cf:fighter-weaponmaster-f1":             1,  # first block
    "cf:fighter-weaponmaster-f2":             1,  # first block
    "cf:fighter-weaponmaster-f3":             1,  # first block
    # -- paladin-blackguard --------------------------------------------
    "cf:paladin-blackguard-f0":               1,  # progression table
    "cf:paladin-blackguard-f1":               1,  # `Level N:` heading
    "cf:paladin-blackguard-f2":               1,  # `Level N:` heading
    "cf:paladin-blackguard-f3":               1,  # `Level N:` heading
    "cf:paladin-blackguard-f4":               1,  # `Level N:` heading
    "cf:paladin-blackguard-f5":               1,  # `Level N:` heading
    "cf:paladin-blackguard-f6":               2,  # progression table
    "cf:paladin-blackguard-f7":               3,  # compendium name
    "cf:paladin-blackguard-f8":               4,  # `Level N:` heading
    "cf:paladin-blackguard-f9":               5,  # compendium name
    "cf:paladin-blackguard-f10":              6,  # compendium name
    "cf:paladin-blackguard-f11":              7,  # progression table
    "cf:paladin-blackguard-f12":              9,  # compendium name
    "cf:paladin-blackguard-f13":             10,  # compendium name
    "cf:paladin-blackguard-f14":             13,  # compendium name
    "cf:paladin-blackguard-f15":             15,  # compendium name
    "cf:paladin-blackguard-f16":             16,  # compendium name
    "cf:paladin-blackguard-f17":             17,  # progression table
    "cf:paladin-blackguard-f18":             19,  # compendium name
    "cf:paladin-blackguard-f19":             22,  # compendium name
    "cf:paladin-blackguard-f20":             23,  # progression table
    "cf:paladin-blackguard-f21":             25,  # compendium name
    "cf:paladin-blackguard-f22":             27,  # progression table
    "cf:paladin-blackguard-f23":             29,  # progression table
    # -- paladin-cavalier ----------------------------------------------
    "cf:paladin-cavalier-f0":                 1,  # progression table
    "cf:paladin-cavalier-f1":                 1,  # `Level N:` heading
    "cf:paladin-cavalier-f2":                 1,  # `Level N:` heading
    "cf:paladin-cavalier-f3":                 1,  # `Level N:` heading
    "cf:paladin-cavalier-f4":                 1,  # `Level N:` heading
    "cf:paladin-cavalier-f5":                 1,  # `Level N:` heading
    "cf:paladin-cavalier-f6":                 1,  # `Level N:` heading
    "cf:paladin-cavalier-f7":                 2,  # progression table
    "cf:paladin-cavalier-f8":                 3,  # compendium name
    "cf:paladin-cavalier-f9":                 4,  # `Level N:` heading
    "cf:paladin-cavalier-f10":                7,  # progression table
    "cf:paladin-cavalier-f11":                8,  # `Level N:` heading
    "cf:paladin-cavalier-f12":               13,  # compendium name
    "cf:paladin-cavalier-f13":               17,  # progression table
    "cf:paladin-cavalier-f14":               22,  # progression table
    "cf:paladin-cavalier-f15":               23,  # progression table
    "cf:paladin-cavalier-f16":               27,  # progression table
    "cf:paladin-cavalier-f17":               29,  # progression table
    "cf:paladin-cavalier-f18":                5,  # compendium name
    "cf:paladin-cavalier-f19":                6,  # compendium name
    "cf:paladin-cavalier-f20":                9,  # compendium name
    "cf:paladin-cavalier-f21":               10,  # compendium name
    "cf:paladin-cavalier-f22":               15,  # compendium name
    "cf:paladin-cavalier-f23":               16,  # compendium name
    "cf:paladin-cavalier-f24":               19,  # compendium name
    "cf:paladin-cavalier-f25":               25,  # compendium name
    # -- ranger-hunter -------------------------------------------------
    "cf:ranger-hunter-f0":                    1,  # `Level N:` heading
    "cf:ranger-hunter-f1":                    1,  # `Level N:` heading
    "cf:ranger-hunter-f2":                    1,  # `Level N:` heading
    "cf:ranger-hunter-f3":                    3,  # compendium name
    "cf:ranger-hunter-f4":                    4,  # compendium name
    "cf:ranger-hunter-f5":                    5,  # progression table
    "cf:ranger-hunter-f6":                    5,  # progression table
    "cf:ranger-hunter-f7":                    7,  # compendium name
    "cf:ranger-hunter-f8":                    7,  # compendium name
    "cf:ranger-hunter-f9":                    8,  # compendium name
    "cf:ranger-hunter-f10":                   9,  # progression table
    "cf:ranger-hunter-f11":                  13,  # compendium name
    "cf:ranger-hunter-f12":                  15,  # progression table
    "cf:ranger-hunter-f13":                  17,  # compendium name
    "cf:ranger-hunter-f14":                  23,  # progression table
    "cf:ranger-hunter-f15":                  25,  # progression table
    "cf:ranger-hunter-f16":                  27,  # progression table
    "cf:ranger-hunter-f17":                  29,  # progression table
    "cf:ranger-hunter-f18":                   1,  # progression table
    "cf:ranger-hunter-f19":                   1,  # `Level N:` heading
    "cf:ranger-hunter-f20":                   1,  # first block, a list
    "cf:ranger-hunter-f21":                   2,  # compendium name
    "cf:ranger-hunter-f22":                   6,  # compendium name
    "cf:ranger-hunter-f23":                  10,  # compendium name
    "cf:ranger-hunter-f24":                  16,  # compendium name
    "cf:ranger-hunter-f25":                  22,  # compendium name
    # -- ranger-scout --------------------------------------------------
    "cf:ranger-scout-f0":                     1,  # `Level N:` heading
    "cf:ranger-scout-f1":                     1,  # `Level N:` heading
    "cf:ranger-scout-f2":                     1,  # `Level N:` heading
    "cf:ranger-scout-f3":                     1,  # progression table
    "cf:ranger-scout-f4":                     3,  # compendium name
    "cf:ranger-scout-f5":                     4,  # compendium name
    "cf:ranger-scout-f6":                     5,  # progression table
    "cf:ranger-scout-f7":                     7,  # compendium name
    "cf:ranger-scout-f8":                     8,  # compendium name
    "cf:ranger-scout-f9":                     9,  # progression table
    "cf:ranger-scout-f10":                   15,  # progression table
    "cf:ranger-scout-f11":                   17,  # compendium name
    "cf:ranger-scout-f12":                   19,  # progression table
    "cf:ranger-scout-f13":                   23,  # progression table
    "cf:ranger-scout-f14":                   25,  # progression table
    "cf:ranger-scout-f15":                   29,  # progression table
    "cf:ranger-scout-f16":                    1,  # `Level N:` heading
    "cf:ranger-scout-f17":                    1,  # first block, a list
    "cf:ranger-scout-f18":                    2,  # compendium name
    "cf:ranger-scout-f19":                    6,  # compendium name
    "cf:ranger-scout-f20":                   10,  # compendium name
    "cf:ranger-scout-f21":                   13,  # progression table
    "cf:ranger-scout-f22":                   16,  # compendium name
    "cf:ranger-scout-f23":                   22,  # compendium name
    # -- rogue-scoundrel -----------------------------------------------
    "cf:rogue-scoundrel-f0":                  1,  # `Level N:` heading
    "cf:rogue-scoundrel-f1":                  1,  # first block
    "cf:rogue-scoundrel-f2":                  1,  # first block
    "cf:rogue-scoundrel-f3":                  1,  # first block
    "cf:rogue-scoundrel-f4":                  1,  # progression table
    # -- rogue-thief ---------------------------------------------------
    "cf:rogue-thief-f0":                      1,  # `Level N:` heading
    "cf:rogue-thief-f1":                      1,  # `Level N:` heading
    "cf:rogue-thief-f2":                      1,  # progression table
    "cf:rogue-thief-f3":                      1,  # `Level N:` heading
    "cf:rogue-thief-f4":                      2,  # `Level N:` heading
    "cf:rogue-thief-f5":                      2,  # progression table
    "cf:rogue-thief-f6":                      3,  # compendium name
    "cf:rogue-thief-f7":                      4,  # compendium name
    "cf:rogue-thief-f8":                      5,  # progression table
    "cf:rogue-thief-f9":                      7,  # compendium name
    "cf:rogue-thief-f10":                     9,  # `Level N:` heading
    "cf:rogue-thief-f11":                     9,  # progression table
    "cf:rogue-thief-f12":                    13,  # compendium name
    "cf:rogue-thief-f13":                    15,  # progression table
    "cf:rogue-thief-f14":                    16,  # `Level N:` heading
    "cf:rogue-thief-f15":                    17,  # compendium name
    "cf:rogue-thief-f16":                    19,  # progression table
    "cf:rogue-thief-f17":                    22,  # progression table
    "cf:rogue-thief-f18":                    23,  # progression table
    "cf:rogue-thief-f19":                    25,  # progression table
    "cf:rogue-thief-f20":                    27,  # progression table
    "cf:rogue-thief-f21":                    29,  # progression table
    "cf:rogue-thief-f22":                    17,  # progression table
    "cf:rogue-thief-f23":                     2,  # compendium name
    "cf:rogue-thief-f24":                     6,  # compendium name
    "cf:rogue-thief-f25":                    10,  # compendium name
    # -- sorcerer-elementalist -----------------------------------------
    "cf:sorcerer-elementalist-f0":            1,  # first block
    "cf:sorcerer-elementalist-f1":            1,  # first block
    "cf:sorcerer-elementalist-f2":            1,  # first block
    "cf:sorcerer-elementalist-f3":            1,  # first block
    # -- warlock-binder ------------------------------------------------
    "cf:warlock-binder-f0":                   1,  # compendium name
    "cf:warlock-binder-f1":                   1,  # compendium name
    "cf:warlock-binder-f2":                   1,  # `Level N:` heading
    "cf:warlock-binder-f3":                   1,  # progression table
    "cf:warlock-binder-f4":                   1,  # `Level N:` heading
    "cf:warlock-binder-f5":                   1,  # first block
    "cf:warlock-binder-f6":                   2,  # compendium name
    "cf:warlock-binder-f7":                   3,  # compendium name
    "cf:warlock-binder-f8":                   4,  # `Level N:` heading
    "cf:warlock-binder-f9":                   5,  # compendium name
    "cf:warlock-binder-f10":                  6,  # compendium name
    "cf:warlock-binder-f11":                  7,  # compendium name
    "cf:warlock-binder-f12":                  9,  # progression table
    "cf:warlock-binder-f13":                 10,  # compendium name
    "cf:warlock-binder-f14":                 13,  # compendium name
    "cf:warlock-binder-f15":                 15,  # compendium name
    "cf:warlock-binder-f16":                 16,  # compendium name
    "cf:warlock-binder-f17":                 17,  # compendium name
    "cf:warlock-binder-f18":                 19,  # compendium name
    "cf:warlock-binder-f19":                 22,  # progression table
    "cf:warlock-binder-f20":                 23,  # compendium name
    "cf:warlock-binder-f21":                 25,  # progression table
    "cf:warlock-binder-f22":                 27,  # compendium name
    "cf:warlock-binder-f23":                 29,  # compendium name
    # -- warlock-hexblade ----------------------------------------------
    "cf:warlock-hexblade-f0":                 1,  # progression table
    "cf:warlock-hexblade-f1":                 1,  # `Level N:` heading
    "cf:warlock-hexblade-f2":                 1,  # `Level N:` heading
    "cf:warlock-hexblade-f3":                 1,  # `Level N:` heading
    "cf:warlock-hexblade-f4":                 3,  # progression table
    "cf:warlock-hexblade-f5":                 4,  # `Level N:` heading
    "cf:warlock-hexblade-f6":                 7,  # progression table
    "cf:warlock-hexblade-f7":                 9,  # progression table
    "cf:warlock-hexblade-f8":                17,  # progression table
    "cf:warlock-hexblade-f9":                22,  # progression table
    "cf:warlock-hexblade-f10":               25,  # progression table
    "cf:warlock-hexblade-f11":                1,  # compendium name
    "cf:warlock-hexblade-f12":                2,  # compendium name
    "cf:warlock-hexblade-f13":                5,  # compendium name
    "cf:warlock-hexblade-f14":                6,  # compendium name
    "cf:warlock-hexblade-f15":               10,  # compendium name
    "cf:warlock-hexblade-f16":               15,  # compendium name
    "cf:warlock-hexblade-f17":               16,  # compendium name
    "cf:warlock-hexblade-f18":               19,  # compendium name
    "cf:warlock-hexblade-f19":               29,  # compendium name
    # -- warlord-marshal -----------------------------------------------
    "cf:warlord-marshal-f0":                  1,  # first block
    "cf:warlord-marshal-f1":                  1,  # first block
    "cf:warlord-marshal-f2":                  1,  # first block
    "cf:warlord-marshal-f3":                  1,  # first block
    "cf:warlord-marshal-f4":                  1,  # first block
    "cf:warlord-marshal-f5":                  1,  # first block
    # -- wizard-arcanist -----------------------------------------------
    "cf:wizard-arcanist-f0":                  1,  # first block
    "cf:wizard-arcanist-f1":                  1,  # first block
    "cf:wizard-arcanist-f2":                  1,  # first block
    "cf:wizard-arcanist-f3":                  1,  # `Level N:` heading
    # -- wizard-bladesinger --------------------------------------------
    "cf:wizard-bladesinger-f0":               1,  # first block
    "cf:wizard-bladesinger-f1":               1,  # first block
    "cf:wizard-bladesinger-f2":               1,  # first block
    "cf:wizard-bladesinger-f3":               1,  # first block
    "cf:wizard-bladesinger-f4":               1,  # first block
    "cf:wizard-bladesinger-f5":               1,  # first block
    "cf:wizard-bladesinger-f6":               1,  # UNVERIFIED -- source absent
    "cf:wizard-bladesinger-f7":               1,  # UNVERIFIED -- source absent
    "cf:wizard-bladesinger-f8":               1,  # `Level N:` heading
    "cf:wizard-bladesinger-f9":               2,  # compendium name
    "cf:wizard-bladesinger-f10":              1,  # UNVERIFIED -- source absent
    "cf:wizard-bladesinger-f11":              5,  # compendium name
    "cf:wizard-bladesinger-f12":              6,  # compendium name
    "cf:wizard-bladesinger-f13":              1,  # UNVERIFIED -- source absent
    "cf:wizard-bladesinger-f14":              9,  # compendium name
    "cf:wizard-bladesinger-f15":             10,  # compendium name
    "cf:wizard-bladesinger-f16":              1,  # UNVERIFIED -- source absent
    "cf:wizard-bladesinger-f17":             15,  # compendium name
    "cf:wizard-bladesinger-f18":             16,  # compendium name
    "cf:wizard-bladesinger-f19":             19,  # compendium name
    "cf:wizard-bladesinger-f20":             22,  # compendium name
    "cf:wizard-bladesinger-f21":              1,  # UNVERIFIED -- source absent
    "cf:wizard-bladesinger-f22":             25,  # compendium name
    "cf:wizard-bladesinger-f23":             29,  # compendium name
    # -- wizard-mage ---------------------------------------------------
    "cf:wizard-mage-f0":                      1,  # compendium name
    "cf:wizard-mage-f1":                      1,  # `Level N:` heading
    "cf:wizard-mage-f2":                      1,  # `Level N:` heading
    "cf:wizard-mage-f3":                      4,  # compendium name
    "cf:wizard-mage-f4":                      5,  # progression table
    "cf:wizard-mage-f5":                      8,  # compendium name
    "cf:wizard-mage-f6":                     10,  # progression table
    "cf:wizard-mage-f7":                     21,  # `Level N:` heading
    "cf:wizard-mage-f8":                     24,  # `Level N:` heading
    "cf:wizard-mage-f9":                      1,  # compendium name
    "cf:wizard-mage-f10":                     1,  # compendium name
    "cf:wizard-mage-f11":                     1,  # first block, a list
    "cf:wizard-mage-f12":                     1,  # `Level N:` heading
    "cf:wizard-mage-f13":                     2,  # compendium name
    "cf:wizard-mage-f14":                     3,  # compendium name
    "cf:wizard-mage-f15":                     5,  # compendium name
    "cf:wizard-mage-f16":                     6,  # compendium name
    "cf:wizard-mage-f17":                     7,  # compendium name
    "cf:wizard-mage-f18":                     9,  # compendium name
    "cf:wizard-mage-f19":                    10,  # compendium name
    "cf:wizard-mage-f20":                    13,  # compendium name
    "cf:wizard-mage-f21":                    15,  # compendium name
    "cf:wizard-mage-f22":                    16,  # compendium name
    "cf:wizard-mage-f23":                    17,  # compendium name
    "cf:wizard-mage-f24":                    19,  # compendium name
    "cf:wizard-mage-f25":                    22,  # compendium name
    "cf:wizard-mage-f26":                    23,  # compendium name
    "cf:wizard-mage-f27":                    25,  # compendium name
    "cf:wizard-mage-f28":                    27,  # compendium name
    "cf:wizard-mage-f29":                    29,  # compendium name
    # -- wizard-witch --------------------------------------------------
    "cf:wizard-witch-f0":                     1,  # first block
    "cf:wizard-witch-f1":                     1,  # first block
    "cf:wizard-witch-f2":                     1,  # first block
    "cf:wizard-witch-f3":                     1,  # first block
}


def level_of(ref: str, default: int = 1) -> int:
    """The printed level this class feature is gained at.

    A sub-option resolves to its parent: `cf:X-f9s2` is gained when
    `cf:X-f9` is, so one number serves the family and there is nothing for
    a second entry to disagree with.

    `default` for anything the map does not hold -- a plain-class feature
    (`cf:ardent-f0`), or a chassis rung declared after this was written.
    **1 rather than 0**, deliberately: a feature the map has never seen
    behaves as it did before this file existed, so a new row is dealt
    rather than silently withheld from every character.
    """
    m = _PARENT.match(ref)
    return FEATURE_LEVEL.get(m.group(1), default) if m else default
