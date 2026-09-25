# Cheaper agents for the remaining ingest

## Context

Phase C has 13 classes and ~1,291 rows left. The content the waves produce is
good; what it costs is not. Mining the session transcript gives the first
hard numbers we have had:

**120 subagents, 25,695,584 tokens, 10,216 tool calls.** Median agent:
216k tokens, 88 tool calls, 15 minutes.

Two facts reframe everything:

**1. Cost is flat.** The ten most expensive agents are only 16% of the total.
There is no whale to kill. The bill is `120 × ~216k`.

**2. Half of it is a fixed per-agent floor.** Fitting tokens against tool
calls across all 118 agents with usage data:

```
tokens = 110,153 fixed  +  1,243 per tool call     (r = 0.54)
```

That floor — system prompt, tool schemas, `CLAUDE.md`, the brief, the
vocabulary, the spec — is **51% of everything spent**. It is paid once per
agent launched, whether the agent writes 140 rows or 6.

`Warlord level 10` spent **171,016 tokens on 2 tool calls**. `Level 4
artillery and minions`: 145,340 on 6.

## The natural experiment already in the data

Four Phase C classes, two written by one agent each and two split across four:

| class | rows | agents | tokens | **per row** |
|---|---|---|---|---|
| sorcerer | 115 | 1 | 308,061 | **2,679** |
| druid | 140 | 1 | 413,254 | **2,952** |
| avenger | 141 | 4 + shared | ~972,000 | **6,894** |
| barbarian | 128 | 4 + shared | ~944,000 | **7,375** |

**Splitting a class cost about 2.5× per row.** Each extra agent re-pays the
110k floor and re-reads every brief.

This reverses what I assumed. I had thought a big agent got expensive because
its context snowballs; the data says the snowball is real but small
(1.2k/call) next to the cost of simply starting another agent.

## The changes

### 1. One agent per class

Not four. Not two, except where a class is genuinely huge. Bard is 133 rows —
druid was 140 in one agent and came in cheapest per row of any Phase C class.

Levels stay as separate files inside that agent's batch; that is a filesystem
choice, not an agent boundary.

### 2. Cut what every agent reads before it starts

The floor is half the bill and most of it is reads I asked for.

* **Stop sending a model file.** 91 of 120 prompts named one — "worked
  examples of the exact style required". `level_05/brutes.py` is 2,226 lines,
  ~16k tokens, four times the vocabulary. `AUTHORING.md` never asked for
  this; I added it in the launch prompts.
* **Stop reading the vocabulary twice.** Several prompts hand the agent
  `vocab.txt` *and* tell it to run `uv run scripts/vocab.py`. Same content.
* **Trim `PRELUDE.md`** — 14,065 bytes, read whole by 46 agents, and it
  overlaps `AUTHORING.md`. One brief, not four. The four in play were
  `PRELUDE.md`, `COMMON.md`, `PHASE-B-AGENT.md` and `CONVENTIONS.md`.

### 3. `scripts/vocab.py --examples`

What the model file was actually for. Print **one real row per group**, pulled
from `REGISTRY` so it cannot drift — the argument `vocab.py` already makes for
itself. About twenty rows, ~1,500 tokens, replacing a 16k read.

Show the shapes that have cost time: a declared `on=Trigger(...)`, a
`save ends` rider, `charges=True`, a monster header with
`Attack(vs=, printed=)`, an `out_of_combat=True` cantrip.

### 4. A tool-call budget, because there is none

**Zero of the 120 prompts, and none of the four briefs, contains a budget,
cap, or "at most N calls."** Median is 88 and the marginal call is ~1,243
tokens. Add to `AUTHORING.md`:

* **Write a file in one `Write`.** Not a row at a time.
* **Drive a row by hand only where a correct row and a broken one would look
  the same** — a trigger that may never fire, a default that may aim at the
  wrong creature. Not for every SILENT. 31 prompts asked for this
  unconditionally; it found real bugs, so it stays, but scoped.
* **About 150 tool calls for a class.** Past it, report what is left.

### 5. Two habits to drop

* **No writer/fixer split.** I had planned one. A second agent costs 110k
  before it does anything, so it only pays if it saves ~90 tool calls. Fix in
  place; spawn a fixer only when a writer has actually blown its budget.
* **No resuming.** `Phase B cleric and warlord` ran 95 minutes across a
  resume. Every resume re-pays the whole context.

Also worth noting: two agents (`Level 11 controllers and lurkers`, `Level 11
skirmishers and soldiers`) failed with no usage recorded at all.

### 6. `scripts/waves.py`

`progress.py` records rows per minute; nothing records what a wave cost, so
this whole plan had to be reconstructed from a transcript after the fact.
Record per agent: refs assigned, rows written, tool calls, tokens. Model it on
`progress.py` — same jsonl-ledger shape.

## What this is worth

At the split-class rate (~7k/row) the remaining 1,291 rows cost ~9M tokens.
At the druid rate (~2.9k/row) they cost ~3.7M, and items 2–4 take a further
bite out of the floor and the call count.

## Files

| file | change |
|---|---|
| `scripts/vocab.py` | `--examples` flag, rows from `REGISTRY` |
| `docs/AUTHORING.md` | the three bullets in item 4 |
| `scripts/waves.py` | new, modelled on `scripts/progress.py` |
| the launch prompt | one agent per class; no model file; one brief |

No engine changes. Nothing here touches content already written.

## Verification

* `uv run scripts/vocab.py --examples` — every row shown must be a real ref
  that `uv run scripts/show.py <ref>` renders.
* `uv run scripts/lint.py`, then `uv run scripts/check.py --all` clean.
* `uv run scripts/leaks.py` — the examples come from the tree so they are
  already sanitised; this is the check that says so.
* **The real test is the next class.** Run runepriest (45 rows) as one agent
  under the new brief and record it with `waves.py`. Target is at or under
  2,900 tokens a row, the druid rate. If it comes in near 7k, the floor
  theory is wrong and item 1 should be reconsidered before the other twelve.
