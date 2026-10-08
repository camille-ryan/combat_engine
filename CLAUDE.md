# CLAUDE.md

Operative rules. `CONTRIBUTING.md` has the long form and the reasoning;
this file is what must be obeyed. Component rules live in a `CLAUDE.md`
inside each component directory — read the one you are working in.

## Issues are the tracker

**Read every comment on an issue before working on it.** All of them, every
time, and on any issue it links to. Not the title, not the body alone.

In this repo the body is the stale part and the comments are the current
state, routinely:

* #214's body opens with 1,177 rows. The real number is 808.
* #217's **last comment** reverses its own verdict — from "missing the
  target by half" to "we are on target". The body still says the old thing.
* #213's entire design is in comments and appears nowhere in the body.
* #110's body said 1,295 powers, its comments said 127, the tree held 17.

Reading a body alone has already cost a re-triage here. `gh issue view N
--comments`.

The rest of the policy:

* **File an issue as work comes up**, not at the end of it. An unfiled
  finding is lost.
* **One issue names one gap in one component.** An issue spanning two is
  two issues. The same rule applies to markers and for the same reason: one
  symbol serving three needs made twelve rows report ready when a third of
  it landed.
* **Put new state in a comment**, not by editing the body. That is what
  keeps the convention working — and it is why the bodies above went stale.
* **Close with the measurement**: what landed, what moved, how it was
  verified. "Done" is worth nothing to the next reader. Say what you did
  *not* do, too.
* **Triage before working.** Prefer the issue that unblocks others.

### Labels

Three orthogonal axes. Pick one from each that applies.

* **Component** — `etl`, `engine`, `content`, `wire`, `ui`, `policy`,
  `chargen`, `story`. Exactly one. `policy` is the **AI policy** —
  `src/combat_engine/policy/`, what the AI chooses — and nothing else.
* **`instruments`** for `scripts/`, which belongs to no component and so has
  no entry above. The label existed and this list did not mention it, so
  eight issues about an instrument were filed against a component instead —
  five of them on `policy`, which made "show me the AI policy work" return
  the audit board and a browser check. If the fix is in `scripts/`, it is
  `instruments`; if the deliverable is a row or a marker, it is the
  component that owns the row.
* **Kind** — `bug`, `balance`, `documentation`, `enhancement`.
* **Content type**, when it is content work — `monsters`, `powers`,
  `items`, `feats`, `features`.

`claude` marks an issue opened on Camille's behalf.

## The one rule

**Nobody writing a row is shown what it is called.** Specs come out of
`scripts/spec.py` with names and flavour stripped. Prose lives in
git-ignored `localization/`. This is the legal basis of the project: game
systems are not copyrightable and prose is.

The rule binds **what an author sees and what the repo holds**, not what can
ever be looked at:

* **A name must not enter a tracked file** — not a comment, a docstring, a
  variable, a commit message, an issue, a column. `scripts/leaks.py` checks
  both halves and has caught a real one (15 reward titles sitting in
  `item.slot`). This half is absolute.

  **But the places are not equally urgent, and reading them as equal has cost
  real effort.** Camille's ordering, #447:

  | | where | |
  |---|---|---|
  | 1 | **a player is shown it without `localization/`** | *critical* |
  | 2 | in the code | near-critical |
  | 3 | in an issue or a commit message | avoid, do not chase |

  The list above reads flat — a commit message named in the same breath as a
  column — and on that reading a session built a verified scrub for 20 issue
  bodies and asked for a permission grant to apply it. Camille had already
  said *"I'm not too worried about git history. It's only truly important that
  none of it gets in code, and CRITICALLY that no wotc content gets displayed
  to a user who doesn't have the localization file."*

  So: fix tier 2 when you find it, and **strive** for tier 3 — a pre-commit
  `leaks.py --history --staged` is the right amount of effort there, since a
  message is editable for exactly one moment. Never rewrite tracker history
  for it. Tier 1 is the one worth building an instrument for, and `#467` is
  that gap: nothing verifies what the page renders when the localisation is
  absent.
* **A content agent is shown no name, ever.** It writes rows from the
  mechanics in its spec, which is what keeps the output clean by
  construction.
* **The main session may read a name and tell Camille**, in chat. That is
  not redistribution and it is sometimes the only way to settle a question —
  "is the database recording this row properly" was answered by reading
  three range lines, and reading them found two parser bugs and one author's
  invented number that four narrower probes had each misdiagnosed.

**Search the web for a *mechanic* you do not understand — never for a
name.** Those are different questions and only the second is forbidden.

## Global rules

* **Hand-write every row.** No regex, no loop minting rows from a table.
  The one exception is a small `_feature(ref, what)`-style helper for a run
  of rows that genuinely share a marker.
* **A row is fully implemented before it is added, or it carries a
  marker.** `todo=` (refused in play), `dropped=` (plays, one clause
  missing), `narrative=` (finished, no combat meaning), `obsolete=` (retired
  by a rules change), `defect=` (**the compendium is missing what the row
  would be written from**). Symbols only for the first three — prose is
  refused at import. The last two take plain words, because there is no
  symbol to wait for. See the content component file.
* **If a spec is garbled, refer it up rather than guessing.** An authoring
  agent cannot read the compendium; the main session can. It answers with
  what the page says, or the row is flagged `defect=`. **On a monster, one
  defective row defects the whole stat block** — `loader.defective` derives
  it and `pick` stops offering the creature. Blank attack defences run
  5–11x the corpus rate in the magazine imports, so a garbled card is
  usually a bad import rather than a misreading. #360.
* **There are no unit tests and none should be written.** The instruments
  in `scripts/` play the real thing. Never create a test file.
* **Never loosen an instrument to make a number look better.** If a check
  goes red, either the code is wrong or the check's definition is — say
  which, with evidence.
* **Commit as `git cc`** (author `Claude (Camille)`, committer Camille), one
  `Closes #N` keyword *per issue* — `Closes #12, #13` closes only #12.
* Not committed, ever: `compendium.sqlite`, `data/`, `localization/`,
  `logs/`. `scripts/fixtures/` **is** tracked, deliberately.

## Components

Work in one. Touch another only when the seam genuinely requires it, and
say so in the commit.

| Component | Path | Is |
|---|---|---|
| ETL | `src/combat_engine/etl/` | compendium → `data/game.db`. Extraction, never rules. |
| Engine | `src/combat_engine/engine/` | the rules kernel. |
| Content | `src/combat_engine/content/` | 677 modules of hand-written rows. |
| Wire | `src/combat_engine/api/` | engine state → DTOs → the page. |
| UI | `web/` | the page. Vanilla JS, no build step. |
| AI Policy | `src/combat_engine/policy/` | what the AI chooses, not what the rules allow. |
| Chargen | `src/combat_engine/chargen/` | builds every character. Persistence does not exist. |
| Story Engine | `src/combat_engine/story/` | fields an encounter: who is on the board, and where. `docs/STORY_ENGINE.md` is the charter; the rest of it is not built. |
| Database | `src/combat_engine/db.py` | where `game.db` and the localisation are, and how to read them. Below every component; imports nothing from the package. |
| Instruments | `scripts/` | belongs to no component. |

Measured seams, so a claim about them can be checked: `etl` → `content` is
**zero** imports (content reads the built database). `engine` → `content` is
**five** sites and is a known leak. Nothing imports `api/` in Python at all
— `web/` reaches it over HTTP, which is the cleanest boundary here. And
**nothing imports `etl/` to read the database**: `game()` lives in `db.py`,
which imports nothing from the package, so five readers reach a sqlite file
without reaching through each other. `scripts/build.py` calling `build()` is
the one import of ETL from outside it. #334.

## Checking

```
uv run scripts/check.py           every instrument
uv run scripts/check.py --fast    skip the two that start a server
uv run scripts/check.py --all     audit every row, not only changed ones
```

**Cadence, which is the thing that was actually costing.** Wide audit sweeps
were 36% of everything this suite had ever cost, at 12x the per-catch price of
a narrow run — so the rule is *rare, not fast*:

* **`check.py` per commit.** Narrow; seconds to a couple of minutes.
* **`check.py --all` once before a push**, not once per commit. It is the only
  invocation that settles the whole-tree debt, and `check.py` now names that
  debt and **withholds "all instruments clean"** until it is paid.
* **After a rebuild the next run is wide, once.** `data/game.db` is git-ignored
  and every monster number is read from it, so a rebuild moves rows no path test
  can see.
* **`--only <name>`** while iterating on one instrument's finding.
* **`--only scorecard` on a `policy/` change**, with `scorecard.py --save` when
  the change *is* the improvement. It is paused out of the default run: 2 red
  runs in 108 is not a gate, it is a measurement.

`audit.py` is the expensive one: about ten minutes for all 12,197 rows, and
that cost has been measured and **cannot be tuned away** — see
`_changed`'s docstring before trying. Use the narrow forms:

```
uv run scripts/audit.py --changed          rows in changed files
uv run scripts/audit.py --calls 'c.foo()'  rows naming a verb
uv run scripts/audit.py --verdicts         is the verdict itself honest
uv run scripts/audit.py --sample 300       a direction, cheaply
```

**Who you are changes two rules.** The main session lints the whole tree
(`ruff check .`) and commits. A parallel content agent lints **only its own
file** and never touches git — a tree-wide `--fix` has destroyed another
agent's work.
