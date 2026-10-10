# Heroic milestone: the work order

The execution order for milestone 1, for a `/goal` to follow.
`20261009-heroic-milestone.md` is the reasoning behind it; this is the list.

**Four phases, in order. Do not interleave them** — the reason is in
"Why the order" at the bottom, and it is the only thing here that is not
obvious.

---

## Phase 1 — engine (10 issues, 2 sweeps)

Wide audit only: no rebuild, and no `replay` re-record unless a new event
enters a fixture's stream.

### Batch A — verb families, already scoped and card-read

| | rows | what |
|---|---:|---|
| `#480` | 7 | `c.pre_empt(watched=)` — the replaced clause fires from a watcher, so there is no menu entry to hang a variant on |
| `#481` | 5 | `c.hit_rider(ref, clause)` — an extra clause on another row's **hit**, per target, not on the use |
| `#483` | 16 | `c.counts_as()` keyword half — a power gains a keyword for one creature. **20 call sites read `p.keywords`**; a merged reader or the grant is ignored at most of them |
| `#478` | 121 | a class form keyword (`BEAST_FORM`, `GUARDIAN_FORM`) and the state that grants it |
| `#474` | 26 | `c.as_weapon()` — four needs; its largest half is blocked on chargen and `c.silvered()`'s 24 on the source, so read `#474` before promising all 50 |

### Batch B — engine bugs

| | what |
|---|---|
| `#364` | `candidates()` puts the caster in its own ally list and `_side()` does not — **544 rows** |
| `#283` | a throwable weapon cannot make a ranged weapon attack; costs 1.5 rounds |
| `#471` | a modifier scoped to one attacker, keyword, distance or kind of action — ~90 rows, one missing slot |
| `#400` | a `Target` cannot name a square — one row, and zones are not waiting on it |

**Done when:** `check.py --all` clean, watermark committed, pushed.

---

## Phase 1, as executed — three issues left it

Recorded here because the reasons are the kind a plan should carry forward,
and all three were found by reading rather than by trying:

* **`#478` -> Phase 2.** The keyword is already in the printed powerstat
  line and `etl/power.py`'s `_KEYWORDS` already matches it -- as the two
  separate words `"beast"` and `"form"`, against a `Keyword` enum that has
  neither. So it is a parse fix plus **a rebuild**, which must not land in
  an engine batch.
* **`#364` -> a session of its own**, like `#389`. It reads as one line in
  `candidates` and is not: `"team"` was missing from that pool entirely, so
  **156 rows that print "You and each ally" are declared `"ally"` and are
  correct only because the bug adds the caster**. Flipping the one line
  breaks every one of them. ~350 rows to classify, ~230 to edit, 114 dead
  guards, and a re-record. The classification is in `tmp/ally364.json`.
  The `"team"` pool itself landed -- zero behaviour change, nothing used it.
* **`#283` and `#400` are deliberately held, and their comments say so.**
  `#283`'s fix is one line and still the wrong thing to land first: it costs
  1.5 rounds at level 5 until `policy/` can price a weak at-will against a
  strong one a move away, and the comment names exactly what to re-run when
  it can. `#400` carries Camille's own decision to keep it open at one row.

**So Phase 1 delivered `#480`, `#481`, `#483`, `#474` and an increment of
`#471`.** Four issues closed, two re-scoped, two correctly untouched.

## Phase 2 — ETL (10 issues, **one** rebuild)

Every one of these changes `etl/`, so each needs `scripts/build.py`, a wide
audit **and** a `replay` re-record. Serially that is ten of each. Together
it is one. This is the largest saving in the plan.

### The cross-reference four — one resolver

| | what |
|---|---|
| `#339` | 76 class-feature refs and every `cls=` site carry a slugified class name; `cls=` sites up 52% to 9,235. **Already mid-flight** — steps 3–5 outstanding: the `cls=` rewrite, directory renames, re-record |
| `#340` | 54 spec rows print a name the database could resolve, in four positions |
| `#378` | a reprinted creature entered twice with a parenthesised suffix; `m5970` resolves to `m5973`, wants suffix-stripping |
| `#379` | a monster spec's by-word index holds only its own name, so another creature's short form survives into the brief |

### The five names-only tables — independent, same rebuild

| | what |
|---|---|
| `#452` | armour and shields: 95 bases, 309 enchantments |
| `#456` | backgrounds: 817 compendium rows, no names, no table |
| `#457` | themes half-ingested — their powers are rows, the themes are names only |
| `#458` | terrain: 145 pages, no rows, and `content/terrain.py` invents its numbers |
| `#459` | `Associate`: 88 stat blocks for summons, mounts and animal companions |

### `#389` is **not** in this batch

The disease table is an ETL extraction *plus* a new ref prefix in
`dsl._SYMBOL` *plus* `c.contract(ref)` *plus* a stage track that outlives an
encounter. That is the shape of the five in milestone 2. Give it a session,
or move it there.

**Re-record discipline — not optional.** `replay` went red on all 7 fixtures
today from a *single* new `EffectApplied`, and the strip-and-compare needed
three masking passes before the streams proved identical: the new events,
the event indices they shift (`trigger=AttackDeclared#202` → `#203`), and
the effect serials (`e47[` → `e48[`). A bare `record` is green either way.
**Its own commit**, after the compare.

**Done when:** rebuild + `check.py --all` clean + re-record verified +
watermark committed + pushed.

---

## Phase 3 — content (2 issues, narrow)

| | what |
|---|---|
| `#449` | 1,024 monster rows declare a recharge threshold the card does not print, and the engine reads the declared one. A sweep of its own; the measurement exists |
| `#477` | three copies of "which shape is this creature in", one per level directory. 28 working gated rows — fold in when something else is already in those files |

---

## Phase 4 — `#468`, on its own clock

2,073 unfinished rows: the authoring half. A content wave is **~50% of a
week's token budget**, so it is scheduled, never opportunistic. Phases 1–3
shrink it first. Read `#468`'s comments before starting — six programme
revisions are recorded there, not in the body.

---

## Why the order

* **Engine before ETL** because a rebuild dropped into an engine batch makes
  the audit re-run for a reason unrelated to the change being made.
* **ETL together** because the rebuild and the re-record are per-batch, not
  per-issue.
* **Content after both** because `#449` and `#477` touch rows the phases
  above may move.
* **`#468` last** because every phase above reduces its row count.

## Two taxes to budget, both measured 2026-10-09

**A row count on a symbol is an upper bound.** Of four verb families read in
one session, three were not one mechanism: `c.in_form()` 43 rows → 2
mechanisms, `c.pre_empt()` 30 → 5, `c.draw()` 20 → 4 (one of them an entire
Fortune Card deck), `c.reroll_ones()` 14 → 1. **Read the cards before
trusting the number.**

**Re-pointing costs more than writing.** Of 107 rows across those families,
only 46 stayed with the symbol they were marked with. `todo.py` goes red the
moment a named symbol exists, so every row carrying it must be settled in the
same commit — written, or re-pointed at the gap that actually remains. On
`#479` that was 7 written against 21 re-pointed.

## Rules that apply in every phase

* `check.py` per commit; `check.py --all` once before a push, or let the
  nightly pay it. **Never edit a watermark to stop an instrument asking.**
* Do not start a sweep and then edit the tree — its audit reads working
  files, and the run is void. Batch, then sweep.
* A plant that stays green means the check or the code is wrong. Say which,
  with evidence, in the commit.
* `git cc`, one `Closes #N` per issue, and close with the measurement:
  what landed, what moved, how it was verified, and what was **not** done.
