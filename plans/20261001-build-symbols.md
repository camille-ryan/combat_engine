# Building the symbols content is waiting on: parameters, then dice

*(On implementation, copy to `plans/20261001-build-symbols.md` per the repo
convention.)*

## Context

1,540 rows carry a marker and they wait on **659 distinct symbols, of which 656 do not
exist**. Measured with `todo.py`'s own `_one`/`_surface`, so the number cannot disagree
with the instrument.

They are not one kind of work, and that is the useful finding:

| why it is missing | symbols | rows |
|---|---:|---:|
| **C.** a brand-new `Cast` verb | 335 | 942 |
| **A.** a method that **exists** and lacks a keyword | 160 | 267 |
| **B.** a field or attribute on a class | 135 | 322 |
| **D.** another row must be written first (content) | 16 | 21 |
| **E.** a `spec.py`/ETL request, not a verb | 10 | 88 |

**The one thing to be clear about before any of it: building a symbol does not finish a
row.** `todo.py` goes red precisely *because* a wanted symbol has arrived and the row is
still unfinished — that is what the three current ARRIVED lines are. So this work makes
`todo.py` **redder**, moves #233's 12.6% not at all, and converts engine gaps into
content work. The budget only falls when somebody then writes the rows. Worth saying
plainly because "656 symbols built" and "656 rows finished" will look like the same
achievement in a commit log and are not.

Camille's scope calls: **parameters first, then the dice subsystem**; **lighting stays
blocked** (no light model, no re-marking); **`spec.power_ref()` is in**, as its own ETL
commit.

## Wave 1 — `when=`, and it is not 17 one-liners

`when=` is an established convention: **11 `Cast` methods already take it** —
`bonus`, `resist`, `conceal`, `forces`, `rolls_with`, `ignore_cover`, `no_advantage`,
`no_cover`, `ignore_resistance`, `arm_trigger`, `cannot_be_flanked`. Seventeen more are
asked to gain it, across **69 rows**. `bonus` at `cast.py:4949` is the reference
signature: `when: Callable[[dict[str, Any]], bool] | None = None`.

**But they do not all take it the same way**, which is why this is a wave and not a
sweep. Measured by reading each one's source:

* **5 lay a `Mod` and the gate passes straight through** — `grant_action`, `grants_in`,
  `immune`, `rattling`, `resist_forced`. These are the first commit.
* **1 lays a `Condition`** — `insubstantial`, via `self.condition(...)`. A condition's
  reader (`conditions.Rules`, `query.active`) has no context to gate on, so "halves
  damage *from fire only*" cannot be said by passing a callable down. Needs its own
  decision and is **not** in this wave.
* **11 need their reader opened individually** — `deals`, `grants_advantage`,
  `half_damage`, `ignores_difficult`, `invisible`, `no_provoke`, `phasing`,
  `resist_in`, `shift_as`, `vulnerable`, and `provokes` which **has no method at all**
  (so it is category C wearing a keyword).

Order within the wave: the 5 pass-throughs, then the 11 one at a time, cheapest reader
first. Stop and report rather than forcing the condition-backed ones.

## Wave 2 — the rest of category A

The other ~143 keyword requests, same shape as wave 1 and the same caveat: ordered by
**reader simplicity, not row count**. The recurring ones after `when=` are `keyword=`
(4 symbols, 19 rows), `once=`, `sustain=`, `dice=`, `keep=`, `zone=`, `group=`.

A keyword whose reader cannot honour it must **not** be added. `lint.py`'s
`UNREAD_MODIFIER_KEYS` exists because a modifier nothing consults is this component's
commonest bug, and a parameter nothing reads is the same bug with a friendlier face.

## Wave 3 — dice and rerolls

14 new verbs, **85 rows**, and the most coherent subsystem in the tail:

```
c.change_dice()   21 rows      c.on_reroll()    18 rows
c.boost_roll()    17 rows      and 11 smaller
```

One subsystem rather than 14 errands: all of it is "intervene in a roll that has already
happened or is about to". `expect.py`'s `_Mean` roller and `Ledger` already model rolls
closed-form, so the question each verb must answer is what the **policy** sees — a
reroll the AI cannot price is a row that plays and scores wrong.

## Wave 4 — `spec.power_ref()`, in its own commit

**37 rows, the largest single item, and not an engine gap.** Rows whose card names
another power and whose author had nothing to point at. The ETL component file already
names this as its recurring fault — *"Nineteen extraction faults have been the same
shape: a name the database could already resolve reaching an author as prose"* — and the
fix is the rule stated right below it: **prefer the id to the name when the page gives
one.** `_links_resolve` already asserts the name resolver against the compendium's own
`href="power.php?id=NNNN"` links at 478/478, so the resolver to reuse exists.

Separate commit, `etl`-labelled, because it is a different component and `spec.py` is an
instrument.

## Not this round

* **Senses and light** — `c.darkvision()` and `c.low_light()`, 36 rows. The engine has
  line-of-sight, `sight_range` and `sees_through` but **no ambient light levels**;
  nothing on a map says a square is dark. Camille's call is to leave these blocked
  rather than build a light model or re-mark them.
* **`c.instead_of()` at 34 rows** and the rest of action economy, 10 verbs / 56 rows.
  The biggest single verb and deliberately deferred.
* **The 257-verb tail**, 621 rows, almost all wanted by one or two rows each.

## Files

| path | what |
|---|---|
| `src/combat_engine/engine/cast.py` | waves 1–3. 7,500 lines, many agents edit it; `lint.py` walks it for a duplicate `def` for that reason |
| the reader for each gated verb | wherever the modifier is consulted — `query.py`, `resolve.py`, `movement.py`, `durations.py` |
| `src/combat_engine/engine/policy.py` | wave 3 only, and only if a reroll needs pricing |
| `scripts/spec.py`, `src/combat_engine/etl/` | wave 4, separate commit |

No content rows are written in this plan. That is the follow-on, and it is what actually
moves #233.

## Verification

Per the engine component file, which is explicit about this:

* **`uv run scripts/audit.py --calls 'c.foo()'`** after each verb or keyword — seconds,
  and the right instrument for an additive verb. It is *evidence the verb works, never
  evidence nothing else broke.*
* **One wide `audit.py` per wave, not per verb.** `WIDE` covers all of `engine/`, so any
  change here widens to all 12,197 rows at about ten minutes. Baseline to hold:
  **9682 fire / 0 raise / 225 silent / 1 retired**. Background it.
* **`vocab.py --brief`** — the authority on what exists. A new verb that does not appear
  there is not callable by a row.
* **`blocked.py` and `todo.py` before and after each wave**, and report the ARRIVED
  count going **up** as the intended result rather than hiding it.
* **`lint.py`** — the predicate walk and the duplicate-`def` walk, both of which exist
  for exactly this kind of edit.
* **`replay.py verify`** — adding a verb should move nothing, since no row calls it yet.
  **A fixture that diverges means a gated path changed behaviour for rows that already
  work**, which is the failure to look for. Re-record only if that is understood.
* **`scorecard.py`** — unchanged is the expected result; it is here as the guard that a
  new keyword did not alter what the AI picks.

## Risks

* **A keyword nothing reads.** The component's commonest bug, and adding 160 of them is
  160 chances to commit it. Mitigation: no keyword lands without its reader in the same
  commit, and `--calls` run against a row that uses it.
* **`todo.py` gets redder and that is correct.** It will read as damage in the commit
  log. Each commit says which rows became finishable.
* **Wave 1 looked like a sweep and is not.** 5 of 17 are mechanical; the rest are
  individual. If the 11 turn out to each need a reader change, the wave is worth less
  than its row count suggests — report that rather than forcing them.
