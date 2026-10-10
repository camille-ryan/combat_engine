# Completing milestone 1: the ordered list

`/goal complete the heroic milestone`. Camille's call, 2026-10-10: **#468
stays in the milestone**, so the milestone closes when ~1,815 heroic rows are
finished. That is weeks, and it is accepted. This file is the order.

`20261009-heroic-work-order.md` was the four-phase plan and is done. This
supersedes it.

## The one number that sets the shape

```
1815  marked rows at heroic levels 1-10      <- #468
 185  paragon 11-20   (out of this milestone's scope by tier)
  18  no level declared (items, feats, features)
```

**#468 is the milestone.** Every other open issue together is a fraction of
it. So the order below is not "smallest first" — it is **whatever raises row
throughput**, because throughput is the only thing that finishes #468.

## Order

### 1. Unblock the largest groups first

A group of 47 rows blocked on one missing thing is worth more than 47
scattered singles, because the singles each cost a card read.

| | rows | what it needs |
|---|---:|---|
| `#389` | 47 | the disease table, a ref prefix, `c.contract`, a stage track that outlives a fight. **Camille approved the plan 2026-10-09.** Probe recorded on the issue: the stage track is uniform across all 69 pages, the DC is **four** shapes and 8 pages need a DC-by-level table this engine lacks |
| `#489` | 10 | a recharge condition that is a **state**, not a moment — a predicate re-asked at the start of the turn, beside the d6 |
| `#471` | ~90 | part-landed; the scope bucket |
| `#364` | 544 | `candidates()` puts the caster in its own ally list. **Flipping the one line breaks 156 rows that are correct only because of the bug.** Classification exists in `tmp/ally364.json` |

`#364` is the biggest single number in the milestone after #468 and is a
*correctness* fix, not an unblock — it does not reduce the marked count. Do it
for the 544 rows' sake, not for throughput.

### 2. The ETL batch — one rebuild, one sweep

Every one needs `scripts/build.py` and a wide sweep, so they go together.

| | what |
|---|---|
| `#488` | 440 conditional-recharge cards store a die threshold of 6 no card prints. `NULL`, not 6. `m4356a2` prints **both** and is the test case |
| `#340` | the ~50 residue with no positional anchor. Its recommended fix is **refuted** on the issue — do not re-derive that |
| `#452` | armour and shields: 95 bases, 309 enchantments |
| `#456` | backgrounds: 817 rows |
| `#457` | themes, half-ingested |
| `#458` | terrain: 145 pages, and `content/terrain.py` invents its numbers |
| `#459` | `Associate`: 88 stat blocks for summons, mounts, companions |

The five tables are each a parser **plus** a table **plus** a content reader.
They are the largest non-#468 work in the milestone and none is blocked.

### 3. The class migration, now unblocked

`#235` is in this milestone as of 2026-10-10, which was the blocker.

```
#235   re-model the build legs, keyed by their cf: ref
#339   then steps 3-5: the cls= rewrite (9,254 sites), 27 directory
       renames, the re-record
```

In that order. 76 `cf:` refs embed a build name and #235 re-models them, so
#339 first writes the leg work twice over the same headers.

### 4. #468, continuously

Not a phase — the thing the others exist to serve. Run a family per batch,
engine and rows together, and read the cards before trusting a row count.

**The tail is the shape of the work from here.** After the recharge family,
the largest remaining group is `#389`'s 47. Beyond that it is 1,011 symbols
over 2,315 row-wants: small groups and singles, which is slower per row than
a 181-row family. Do not estimate the remainder at today's rate.

### Two issues held open by Camille's own decisions

`#283` — the fix is one line and costs 1.5 rounds at level 5 until `policy/`
can price a weak at-will against a strong one a move away. Its comment names
what to re-run.

`#400` — "keep it open at one row."

**Completing the milestone means these two resolve as well**, and that is a
call rather than a task.

## Rules that apply throughout

Carried from the work order because each was paid for:

* **`check.py --all` once before a push**, not per commit. Seven sweeps in
  the last session; audit is a flat ~1,700-1,800s.
* **Never start a sweep and then edit the tree.** `scripts/build.py` counts as
  editing it — `etl.build` unlinks `game.db` first.
* **A plant that stays green means the check or the code is wrong**, and say
  which. Two plants in the last session failed on the *test's* assumption, not
  the code — that is a finding too.
* **Read every comment on an issue before working it.** `#389`'s premise is
  corrected in its first comment; `#340`'s recommended fix is refuted in its
  last.
* **`audit --calls` is evidence a verb works, never that nothing broke** —
  and it is blind to a gate that starts *passing*, which was proven by plant
  on `#477`.
* **A check comparing two derived values cannot see a fault they share.**
  `recharge_debt.json` held 392 rows it was built to find, because content and
  column agreed on the same wrong number.
