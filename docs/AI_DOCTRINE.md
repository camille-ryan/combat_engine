# AI doctrine

Tactical notes for the AI policy — what a good square is, what threat means,
what each monster role is trying to do. Input to `engine/policy.py`.

**Renamed from `POLICIES.md`.** At the repo root that name read as project
policy, which it is not and never was; project policy is in `CLAUDE.md`. This
is doctrine for the thing that chooses a move.

## What of this is actually implemented

Two policies exist. **`DoctrinePolicy` is the default**, on the measurement
in its own module docstring — 60 of 80 wins at level 5 against
`LinearPolicy`'s 47, and 67 against 46 at level 10, both surviving Holm.
`LinearPolicy` stays as the baseline `--policy linear` compares against.

| | `LinearPolicy` | `DoctrinePolicy` |
|---|---|---|
| module | `engine/policy.py` | `engine/doctrine.py` |
| threat | — | `engine/threat.py`, best case over 3 rounds |
| threat removal, incl. hp damage | — | `threat_removed` |
| cost of provoking | flat `-5.0` / `-4.0` | those **plus** `threat_conceded` |
| what a move buys | — | `reach_gained` |
| flanking, being flanked, cover | — | `takes_flank`, `becomes_flanked`, `cover_change` |
| hostile terrain | — | `into_enemy_zone`, `into_difficult` |
| healing | scored as friendly fire | `healing_given`, `healing_wasted`, `heals_the_dying` |

`uv run scripts/doctrine.py` reports what every one of those terms contributed
over real fights, and `uv run scripts/winrate.py --policy linear --policy
doctrine` is the comparison between them.

**Still absent, and each is a line of this document that nothing reads:**

* **Target redirection** — the defender's half. "Threat should be increased by its
  additional effects" and locking down a high-threat enemy are not scored at all;
  `threat.CONDITION_THREAT` is a table of zeros awaiting numbers. A defender is
  currently scored on damage prevention alone, which plays it as a striker.
* **Role goals** — the whole of *Goals* below. `Ident.role` exists on both sides
  of the board and no weight consults it, so a controller and a brute score
  identically.
* **Leaving a flank open for the rogue**, and setting up a flank for an ally.
* **Damaging terrain** as distinct from a zone an enemy happens to own — a `Zone`
  does not record that it deals damage, so this is not answerable today.
* **Minion and elite/solo distinctions** in what to spend resources on.

## Good Squares
Melee characters would like to be in melee.
Ranged characters would like to not be in melee.
Melee characters would like to be adjacent to ranged enemies. This is especially relevant for characters with good mobility, and abilities to keep the ranged enemies from shifting away.
If an entity can shift to a better square, it should.
Many defenders have options to prevent or punish an enemy for moving. Creating a zone or effect which punishes movement-restricted creatures is a good way to get extra damage.
Flanking is usually a good choice.
Setting up a flank (moving to a square where an ally can shift or move into flanking) is nearly as good as flanking.
If an ally benefits more from flanking (i.e. rogues), a creature should leave the flank square open.
If facing ranged enemies, moving into cover is preferable, especially if squishy.
Hostile zones and damaging terrain are bad squares.
Being flanked is a bad square.

## Threat
The damage threat of a creature should be its best case average damage over 3 rounds. Best case means it is able to get its conditions for extra damage. This should be divided by the party total hp pool.
Threat should be increased by its additional effects.
The major paradigm should be "how much of the enemy team's threat can I remove with my action". This means that heavy control like immobilizing or dazing a melee character which is not currently in melee, domination, paralyze etc. can fully remove the threat of an enemy. Killing an enemy also removes its threat.

## Scoring during character creation.
Evaluating options should be done by assuming an equal level baseline opponent with the following:
AC: 14 + level
Lowest other defense: 11 + level
HP: 24 + 8 * level

## Healing surge usage
Healing surges can saturate. Using a healing surge to heal 1hp, for example, is a waste.

## Doctrines
Defenders and soldiers are good at locking down high threat enemies.
Artillery, brutes, and some strikers are good at dealing consistent damage.
Lurkers, skirmishers, and some strikers are good at dealing conditional damage.
Controllers are good at limiting enemy actions and at AoE.
Leaders are good at improving the abilities of their allies and sometimes at healing.

## Goals
When adjusting scores, consider the following goals:
All characters should be penalized for damage taken.
All characters should get points for dealing damage and for killing enemies.
Defenders and soldiers should be penalized for damage taken by allies.
Strikers, Artillery, Brutes, Lurkers, and Skirmishers should get extra points for dealing damage, and for killing nonminion enemies.
Controllers should get extra points for neutralizing an enemy for a turn, and for killing minions.
Leaders should get extra points for healing allies, especially for reviving downed allies (note that NPCs cannot be revived typically - they do not enter the dying state).
Leaders, if possible, should also get extra points if buffs they apply make an attack hit when it otherwise would not, and for making an enemy miss when they otherwise would not.
Leaders should also get points for damage caused by allies when they grant an ally attack.

