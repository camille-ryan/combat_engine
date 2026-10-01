# Policy triage, round two: the instruments are lying before the scoring is wrong

*(On implementation, copy to `plans/20261001-policy-triage-2.md` per the repo
convention.)*

## Context

Ten issues are open against `policy`. Triaging them turned up something that has to
be fixed before any of the scoring ones can be judged: **two of the scorecard's guard
metrics are counting turns taken by creatures that cannot act.**

Measured, level 10, 12 fights:

| | reported | taken by a creature whose only option is `end` |
|---|---:|---:|
| `adjacent_idle` | 24 | **20** |
| `idle_melee` | 10 | **5** |
| melee turns, total | 664 | 25 |

Of 462 turns that begin with a melee creature already adjacent to an enemy, **439 are
offered an attack row with a live target**. The 23 that are not break down as 13
`dazed, dying, prone, unconscious`, 6 `dying, prone, unconscious`, 1 with an immobilise
on top, and **3 with no condition at all** — and all 23 had exactly one legal option,
`end`.

Two consequences, and they are why this round is instruments-first:

* **#268's premise is right and its magnitude is ~4 turns, not 27.** "Nothing is
  available" is literally true; it is true because the creature is unconscious.
* **#271's headline evidence is half corpses.** I filed it yesterday on `idle_melee`
  going 7 → 10, and 5 of that 10 is this. The pricing argument in it still stands —
  an opportunity attack conceded on the way in is paid once, the attack it buys is
  collected every round — but the number I used to justify it does not.

This is not loosening an instrument to make a number look better; it is the check's
*definition* being wrong, which `scripts/CLAUDE.md` requires be said with evidence.
The evidence is the 23 single-option turns above. The fix still has to be proven
load-bearing, and the plan says how.

Camille's scope call: **correctness and instruments only.** The one-action look-ahead
that #265's remainder, #266's ally-burst and #271 all need is deferred, because it
would otherwise be measured against metrics being repaired in the same round.

## Triage

| | state | disposition this round |
|---|---|---|
| **#231** self-targeted row paid `enemies_caught` | **fixed in code at `policy.py:228`, never closed** | close with the measurement. Zero work |
| **#213** win rate unreadable with random draws | superseded by `scorecard.py` | close as superseded; the draw-pinning half is chargen's |
| **#270** stale baseline hid `915ed93` | open, filed yesterday | fix 2 (guard) + fix 3 (the regression it hid) |
| **#268** adjacent and did not attack | open, **magnitude is ~4 not 27** | re-measure after fix 1, comment, leave open |
| **#271** approach looks too expensive | open, **evidence contaminated** | re-measure after fix 1, correct the issue, leave open |
| **#264** inert rows still chosen | open, 169–215 remain | not this round; needs the free/minor vs move split |
| **#265** closing term | open, main part fixed by Camille's two rules | not this round; needs look-ahead |
| **#266** action points + ally burst | open | the grant-ranking half is cheap — fix 4. Ally burst deferred |
| **#247** forced movement | open, two real terms | keep, not worked |
| **#267** 90% party win | open | keep as a balance guard, re-measure after the above |

## Fix 1 — the idle metrics, because three issues depend on them

`scripts/scorecard.py`. The two counters in `play()` (lines ~174-179) and
`turn_watch()`.

**Derive the exclusion from what was offered, not from a condition list.** A turn
whose only legal option is `end` cannot demonstrate anything about tactical choice.
That reading is condition-agnostic — it catches `stunned`, `dominated`, a future
condition nobody has written yet, and the 3 turns above that carry *no* condition and
still had one option — and it follows the pattern `threat.from_rules` already
established, deriving from the rules rather than a hand-set table.

So: `Counted.act` records, for the first decision of each turn, whether anything but
`end` was available; `play()` skips both idle counters when nothing was. Report the
skipped count as its own scorecard line — **`could_not_act`** — because an instrument
that silently drops turns is the thing `scripts/CLAUDE.md` forbids.

Keep `melee_turns` counting every turn; it is a denominator, and changing it would
move `idle_melee`'s meaning as a rate.

**Proving it load-bearing**, which a definition change needs more than a code change
does. Two directions:

* It must still go red on a real stall: force `worth_standing` to refuse every
  approach and confirm `idle_melee` climbs. If it does not, the fix has gutted the
  guard rather than cleaned it.
* It must *not* move on the thing it was wrongly counting: a fight where a creature
  drops unconscious beside an enemy should now contribute 0.

Expected after: `adjacent_idle` 24 → ~4, `idle_melee` 10 → ~5, and a new
`could_not_act` of about 25 at level 10.

## Fix 2 — #270's staleness guard

`scripts/scorecard.py` and `scripts/fixtures/scorecard.json`.

`--save` records the current `HEAD` sha in the baseline. On load, if it differs,
print **`baseline is N commits stale (saved at <sha>)`** above the table, with N from
`git rev-list --count <sha>..HEAD`. Degrade quietly to no line when git is
unavailable, rather than failing.

A warning, not a failure: the docstring says this is not a pass/fail check and that is
right. But the line has to be loud, because its absence is what let `915ed93` sit
unmeasured and nearly got its regressions attributed to the reach fix.

## Fix 3 — the regression #270 found

`915ed93`'s whole purpose was to let a charge end anywhere its attack reaches, so the
charge rate should have risen. It fell: **level 5 charges taken 21 → 14**, while
charges *offered* rose (level 10, 164 → 197). The rows are found and then declined.

First hypothesis to test, and it is checkable in one probe: `best_from` now counts a
charge square as a square you can attack from (227d55e, and correctly). A **plain
move** to such a square therefore scores like an approach that arrives — so moving may
now be scoring level with charging, and `str(action)` breaks the tie. If that is it,
the charge needs to beat a move to the same square by the value of actually attacking
this turn.

Also in scope here: `p12660`, a Personal minor-action stance, is **38 of the 42**
"re-cast a live buff" firings at level 5. #264's `already_on` zeroing should have
caught it. Find out why it does not — most likely the same shape as the aura that
issue describes, where the ref sits on the zone and not on the effect.

## Fix 4 — #266's cheap half

`doctrine.py`. Rank action-point grants explicitly, standard > move > minor, instead
of leaning on `str(action)` sorting `"standard"` last. It buys the right one on 48 of
48 occasions today **by alphabetical luck**, and the luck is load-bearing: rename an
`ActionType` value and it silently starts buying the wrong action. A tie-break, not an
evaluation — deliberately not the scoring change #266 originally asked for, which its
own comment argues against.

## Files

| path | what |
|---|---|
| `scripts/scorecard.py` | fix 1 (the two idle counters, `could_not_act`), fix 2 (staleness) |
| `scripts/fixtures/scorecard.json` | baseline gains a `commit` field; re-saved once |
| `src/combat_engine/engine/doctrine.py` | fix 4, and whatever fix 3's probe finds |

No ETL or content work. No new `engine` → `content` site.

## Verification

* **`scorecard.py` before and after each fix**, against the committed baseline — and
  with fix 2 in place the staleness line makes "is this comparison honest" visible
  rather than assumed.
* **The two load-bearing probes in fix 1.** A definition change that cannot be shown
  to still catch the real failure is not finished.
* **`replay.py verify`.** Fixes 1 and 2 are instrument-only and must move nothing; if
  a fixture diverges, fix 1 has changed behaviour and is wrong. Fix 3 and 4 will move
  fixtures, re-recorded in their own commit.
* **`check.py --fast`**, which is currently red on `todo` only — #233's marker budget
  and #273's two arrived symbols, both pre-existing and neither mine.
* **No wide audit needed** unless fix 3 touches `doctrine.py` scoring; `WIDE` covers
  all of `engine/`, so if it does, pay for one run and expect 9682 fire / 0 raise /
  225 silent / 1 retired.
* **`winrate.py` not at all this round.** Nothing here changes balance, and #267 is
  explicitly parked until the scoring work lands.

## Issue hygiene, as the work lands

Close **#231** (fixed, measurement in `policy.py:228`'s comment) and **#213**
(superseded). Comment on **#268** and **#271** with the corpse measurement and leave
both open per Camille. Comment on **#270** with what fix 3 found. **#247** and
**#267** keep, untouched.

## Risk worth stating

**Fix 1 makes two numbers look better without the AI playing better.** That is the
honest outcome — they were wrong — but it means the baseline after this round is not
comparable to the one before it on those two rows, and the commit has to say so in
both directions. The `could_not_act` line exists so the dropped turns stay visible
rather than vanishing into a nicer number.
