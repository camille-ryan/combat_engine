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
  `chargen`, `story`. Exactly one.
* **Kind** — `bug`, `balance`, `documentation`, `enhancement`.
* **Content type**, when it is content work — `monsters`, `powers`,
  `items`, `feats`, `features`.

`claude` marks an issue opened on Camille's behalf.

## The one rule

**Nobody writing a row is shown what it is called.** Specs come out of
`scripts/spec.py` with names and flavour stripped. Prose lives in
git-ignored `localization/`. This is the legal basis of the project: game
systems are not copyrightable and prose is.

So: never grep the database for a name, never read `localization/`, never
put a guessed name in a comment, a docstring or a variable.

**Search the web for a *mechanic* you do not understand — never for a
name.** Those are different questions and only the second is forbidden.

## Global rules

* **Hand-write every row.** No regex, no loop minting rows from a table.
  The one exception is a small `_feature(ref, what)`-style helper for a run
  of rows that genuinely share a marker.
* **A row is fully implemented before it is added, or it carries a
  marker.** Three markers, not two: `todo=` (refused in play), `dropped=`
  (plays, one clause missing), `narrative=` (finished, no combat meaning).
  Symbols only — prose is refused at import. See the content component file.
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
| AI Policy | `engine/policy.py` | what the AI chooses. One module, inside Engine. |
| Chargen | `content/chargen.py` | builds every character. Persistence does not exist. |
| Story Engine | — | not built. `docs/STORY_ENGINE.md` is the charter. |
| Instruments | `scripts/` | belongs to no component. |

Measured seams, so a claim about them can be checked: `etl` → `content` is
**zero** imports (content reads the built database). `engine` → `content` is
**five** sites and is a known leak. Nothing imports `api/` in Python at all
— `web/` reaches it over HTTP, which is the cleanest boundary here.

## Checking

```
uv run scripts/check.py           every instrument
uv run scripts/check.py --fast    skip the two that start a server
uv run scripts/check.py --all     audit every row, not only changed ones
```

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
