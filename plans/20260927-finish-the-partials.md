# Finish the partials — foundations first

## Context

The heroic scope is declared and nothing is silently absent: 2,536
feats and 2,491 item blocks, of which **2,295 are finished** and
**2,154 carry a marker** naming what they wait on. The tracker is red
only on the marker budget (19.1% against a 10% ceiling) and on 30
rows that raise.

The obvious plan — attack the biggest marker groups — is wrong, and
the reason is the thing this exploration found:

**The foundations under the feats were never built.**

| kind | in `data/game.db` | declared in the tree |
|---|---:|---:|
| races | 55 | **0** |
| racial powers | 155 | **0** |
| class features | 99 | **9** |

`Character` already has a `race` field and nothing fills it. All 300
rows have extracted specs sitting in the database, imported earlier
and never authored.

That is what the top of the marker table is actually waiting on:

| rows | symbol | really blocked on |
|---:|---|---|
| 146 | `c.class_feature()` | the 90 unauthored features |
| 54 | `c.on_racial_power()` | the 155 unauthored racial powers |
| 46 | `c.borrow_feature()` | the same features, plus a chargen choice |

So ~250 marked rows are downstream of ~300 unwritten ones. Writing
verbs for them first would be building against absence — and it has
already been tried twice this week, which is why `c.class_feature()`
has been re-diagnosed twice and still sits at 146.

**Order: races, then class features, then feats.**

### Two rules from the owner, written in

* **Win rate is not a metric.** No stage optimises against it or
  reports it. No change is needed to `check.py` — `fight.py --quiet`
  already exits 0 on a party loss, so it is a crash test today and
  stays one. #213 records why the number is unreadable.
* **Nothing autonomous re-records a fixture.** `replay.py record`
  re-draws the feats a seed deals; after a content wave it churns all
  six. To update one: re-run that case with its *saved* feats, and
  prove the diff inert first (normalise effect ids, then check rolls,
  damage and outcomes are identical).

---

## Stage 0 — three engine faults, before any content

Cheap, and each one pays for itself across every later stage.

**a. `PowerResolved` escapes the re-entry guard.** `dsl.use`
(`src/combat_engine/engine/dsl.py:1341-1354`) discards
`(actor, ref)` from `_IN_FLIGHT` inside its `finally`, then emits
`PowerResolved` on the next line. A row triggered on its own
resolution answers itself, unbounded — the traceback surfaces in
`query.can_act`, so it reads as an engine fault. **This is all 30
currently-raising rows** (`p5126`–`p5133`, `p9855`–`p9870`). Hold the
mark across the emit; the `PowerUsed` variant goes with it.

**b. The audit board fields the wrong character.** In
`scripts/audit.py:306` `board()` reads `declared.cls`, which is `""`
for every feat, and falls back to `"fighter"`. **932 of 1,778 heroic
feats name a class in their structured `prereq`** and it is never
consulted — so an invoker feat is boarded on a fighter with no
covenant. Separately, an item block is always equipped
`slot="weapon"` though `item.slot` records the truth (412 implement,
201 armour, 85 arms, 83 neck).

**1,177 declared rows — 12% of the tree — report `UNUSED` today**
(f469 / p332 / i244 / m132). This is also the single largest driver
of agent cost: last session's most expensive agents were the ones
that built scratch boards by hand because the harness could not stage
their triggers.

*Exhaustive cause table, measured after the plan was written. Causes
are disjoint and priority-ordered, so they sum to 1,177.*

| rows | cause |
|---:|---|
| 308 | the provocation is the wrong **shape** of attack |
| 153 | a Requirement the board cannot meet |
| 142 | a named sibling ref, never granted |
| 136 | a second card whose parent is never granted |
| 121 | a trigger event never staged |
| 119 | an item sibling row never granted |
| 108 | a trigger naming a ref **declared nowhere** |
| 90 | the wrong class |

**The cheap tier is 487 rows — 41%** — and needs no engine change and
no new fixture, only columns `game.db` already has and helpers
already written (`chargen.second_card`, `treasure`'s item query,
`Character.feats`). Each was verified by running it.

Two things this changes. **The largest single cause is attack
*shape*** — every attack `_provoke` stages is a melee basic, so
"an arcane ranged at-will" (63 rows), "you take cold damage" (52) and
"a close or area attack hits you" (11) can never match. That is real
work, not a call. And **`second_wind` + `action_point` is 25 rows as
a primary cause, not the ~95 first estimated** — the corpus has 67
rows on those events but most are blocked by something earlier. Still
two lines.

The 108 naming an undeclared ref are **the racial powers**, which is
Stage 1 — confirming the order.

**c. Race names leak into specs and `leaks.py` cannot see it.**
82 race names are printed in `power` specs — Gnome, Drow, Kobold,
Elf. `sanitise.identifies()` requires two words, so a one-word race
name passes every check while `leaks.py --specs` reports clean. This
is the legal basis of the project, so it is Stage 0 and not later.
Fix in the ETL alongside the race import, and give `identifies` a
one-word exception for a name held by a race.

**Gate:** `audit.py` reports zero raising; UNUSED materially down and
recorded; `leaks.py --specs` still clean *after* the one-word test is
tightened.

---

## Stage 1 — races and racial powers (210 rows)

Files: `src/combat_engine/content/races/` (new),
`src/combat_engine/content/chargen.py`,
`src/combat_engine/etl/build.py`.

* **55 races.** `race` table has size and spec. `Build.choices`
  already carries a `race:` prefix the way `element:` does
  (`chargen.py:583`), so this needs no new component — a `race` table
  reader, racial traits, and `Character.race` actually populated.
* **155 racial powers**, keyed by race ref in the `Class` column.
  These are ordinary `@power` rows, not a new kind. Roughly one agent
  per 25.

Numbers load from `game.db`. Never hand-write a stat line.

---

## Stage 2 — class features

*Refined after the plan was written, by an explorer that reported
late. The shape is different from "author 90 rows" and the difference
matters.*

**Two naming schemes were never reconciled.** `game.db` mints
`cf:<class>-fN`; the tree declares 58 `cf:` rows under hand-chosen
semantic names and only 9 under `-fN`. So part of the gap is a
**rename**, not authoring — `cf:barbarian-f3` is already implemented
as `cf:barbarian-rampage`, `cf:warlock-f3` as `cf:warlock-shadow`,
`cf:wizard-arcanist-f0` as `cf:wizard-implement`,
`cf:rogue-scoundrel-f4` as `cf:rogue-bonus`. Reconcile first, author
second, or the same feature gets written twice.

**Three ETL faults sit upstream of the prose half**, and between them
they explain why `c.class_feature()` has resisted two sweeps:

* **`_features` imports only ALL-CAPS headings** (`build.py:595`) and
  **deletes the power cards printed inside a feature section**
  (`build.py:641`). Every name the 122 prose rows cite lives in one
  of those two dropped shapes — **56 are recoverable from the class
  page today**.
* **The feat's own prerequisite already holds the name.**
  `etl/feat.py` files "&lt;name&gt; class feature" as an opaque `qNNN`
  term whose stored text *is* the feature name. **66 of the 146 rows
  carry one.** That is a direct bridge and nothing reads it.
* **`_NAMED` misses four shapes**, largest first: no noun at all
  ("your &lt;Title Case Name&gt;", 45 rows); a typographic apostrophe,
  since `[\w']` does not span `’` ("preserver’s rebuke", 9 rows);
  `feature`/`trait` without "class" (4); the name *after* the noun
  (1).

**Only 1 of the 146 is writable purely on a ref today** (`f1724`),
and ~28 would still be blocked with a perfect ref because the clause
must reach *inside* the feature — swap an ability it uses, rewrite a
literal in its closure, lift a once-a-round latch. Those are a
different gap and must be re-aimed, not forced.

So Stage 2 is: reconcile the names, fix the three extraction faults,
*then* author what is genuinely absent, *then* re-aim the residue.

---

## Stage 3 — re-triage, before writing any verb

**Markers have gone stale faster than they have been cleared**, and a
sweep is repeatedly cheaper than a verb. Evidence: `c.use_power()` has
38 rows and **29 of them already print a resolvable ref** — the ETL
learned to resolve those names and nothing told the rows. The same
was true of `SavingThrow.keywords` (24 rows, 20 written, no engine
change) and `query.save_ctx()`.

So: after Stages 1 and 2 land, re-run every marker against current
resolution **before** deciding what to build. Expect the table to be
materially smaller and differently shaped.

---

## Stage 4 — the verbs that survive

Known now, and worth doing whatever Stage 3 says:

* **`c.as_basic(ref)` (41 rows)** — one verb, and most scaffolding
  exists. `Powers.opportunity` (`components.py:510`) is already "a
  power that replaces the basic attack when opportunity knocks" and
  `policy.py:502` already reads it. What is missing: the charge and
  Combat Challenge windows (20 of the 41), a `Cast` verb that writes
  the slot with an undo (`Cast.no_basic`, `cast.py:2999`, is the
  template), and widening one ref to a set. Candidate sets are
  already data via `styles.among`.
* **`c.borrow_feature()`** splits and neither half is a `Cast` verb:
  ~14 blocked on Stage 2's features, ~13 a chargen choice plus a
  usage override, which belongs in `chargen.loadout`
  (`chargen.py:746`), not `Cast.grant_row` — whose docstring says
  outright it is "not the tool for a build's own rows".

Then the head of whatever table Stage 3 produces, one agent per verb,
each writing the verb *and* sweeping its own rows.

---

## Stage 5 — the tail, swept by file

**390 of 611 symbols are wanted by one or two rows** — 468
row-mentions. No verb is worth building for two rows, so this is one
agent per content file: finish the row, or re-aim the marker at the
real gap, or say why it stands. Re-aiming is a real outcome.

---

## Cutting the cost

Last session: ~45 agents, ~8.8M subagent tokens.

* **Lost and duplicated work, ~627k tokens.** Three batches written
  twice or thrown away because `--offset` does not partition a list
  of *undeclared* rows — the window slides as agents land theirs.
  **Explicit ref lists, generated immediately before dispatch**, and
  each agent re-greps before its final check.
* **House-style reading.** Item agents were told to read
  `weapon_b.py` (5,344 lines), `implement_a.py` (3,385),
  `armour.py` (3,012). They averaged ~228k tokens against ~175k for
  feat agents reading 400–850 line files. **Write
  `docs/HOUSE_STYLE.md`** — shapes, traps, verbs — and have agents
  read that plus *one* neighbour.
* **Hand-driving boards.** Removed by Stage 0b.
* **Never the full `audit.py`** — it is ten minutes. `--changed` is
  0.33s, `audit.py <refs>` under a second. The full run is mine, once
  per stage.
* **A broken tree costs every concurrent agent.** Run `lint.py` after
  each write, not each batch.

Expect roughly a third off per agent, most of it from Stage 0b and
the ref lists.

---

## Out of scope

Not closing #212 (the beast cannot act), #213 (builds are random) or
#204's remaining half. Not building a verb for a one-row symbol
without saying why that row earns it.

---

## Verification

* `check.py --all` green except `todo` at every stage boundary.
* `audit.py`: zero raising, zero silent; **UNUSED recorded at each
  boundary** so Stage 0b's payoff is visible.
* `replay.py verify` green on all six, always.
* `leaks.py` and `leaks.py --specs` clean every time the ETL moves —
  and after Stage 0c, re-checked against the one-word race names that
  currently slip through.
* Marked-row count recorded per stage **by symbol**, so a stage that
  marks more than it finishes is visible at once.
* No win-rate number is quoted anywhere.
