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
* **A rules table quoted in an issue is evidence a table exists, not
  evidence of its contents.** Read the page in `resources/` before writing
  one into code — the PDF extracts with `pypdf`. Measured across four issues
  in one session, 2026-10-29, and **three of the four quotes were not what
  they said**:

  | | what the quote got wrong |
  |---|---|
  | `#982` | its four heroic rows were exact; its claim that `story/dc.py` holds "the DC half of the same table" was false — `dc.py` is a revised **per-level** table and the printed one is three-level **bands** |
  | `#988` | one ten-row table was really **three** printed tables, each with a **Level** column that was dropped; one row renamed, one omitted, three absent from the book |
  | `#1010`, `#972` | both quote DMG2, which is not in `resources/`, so neither is checkable — and `#972`'s *reverses* an earlier conclusion on that one source |

  The failure is not carelessness in the quoter. A transcription loses
  exactly the structure that decides how the data is keyed: which table a
  row came from, and the columns nobody needed at the time. `#982` is the
  worked example — pairing a banded damage table with a per-level DC table
  misaligns in the **row keys**, so nothing would have raised and a level-5
  trap would have read band `4th-6th` damage beside level-5 DCs from
  another edition.

  So: say in the code which printing a table came from and what could not be
  verified, and if the only source is a quote, say so on the issue rather
  than landing it. Same rule as a census — see *"an issue's census is a
  floor"* — applied to the cells instead of the count.

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

`claude` marks an issue opened on Camille's behalf — and it is **carried by
400 of 400 issues**, so it distinguishes nothing and should be read as noise
rather than as information. Either drop it or invert it to mark the ones
Camille opens.

## Attribution: the record cannot tell Camille's words from Claude's

Camille asked, 2026-10-28, whether anything shows the difference. Measured:

| where | distinguishes? |
|---|---|
| git commits | **yes** — author is `Claude (Camille)` |
| issue comments | **no** — every one is authored `camille-ryan`; Claude posts via `gh` |
| the `claude` label | **no** — 400 of 400 |
| in-code notes | **no** — 126 attributions, **3** carry a verbatim quote, **79** are a bare "Camille's call/rule" |

So **git history is the only audit trail**, and every *"Camille's call"* in
this tree is Claude's paraphrase of a chat turn with nothing to check it
against. That is not a hypothetical cost. `#877` carried *"Decided: a dealt
character carries nothing expendable. Camille, asked directly"* — written by
Claude, quoted onward on `#520` as a governing ruling, and **Camille did not
recall making it**. The real ruling, given the next day, was the opposite:
50 pieces of mundane ammunition and 5 throwing weapons. A paraphrase had
been steering the design.

So:

* **An attribution carries a verbatim quote, in a blockquote, or it says it
  is a paraphrase.** A quote is checkable against a transcript; "Camille's
  call: X" is not. The 79 bare ones get corrected as they are touched, not
  in a sweep.
* **Sign every issue comment.** A trailer — *"Claude, posting on Camille's
  behalf"* — so the author field being `camille-ryan` stops misleading.
* **A ruling is recorded as a quote, not a summary**, on the issue it
  governs.
* And when a note says Camille ruled something, **the quote is the
  evidence**. Without one, treat it as Claude's reading and say so — the
  same standard this file already applies to a census or a marker.

## The one rule

**A name must not enter a tracked file.** Specs come out of
`scripts/spec.py` with flavour stripped and every reference as a ref. Prose
lives in git-ignored `localization/`. This is the legal basis of the project:
game systems are not copyrightable and prose is.

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

  **`#467` is deferred, though, and this paragraph read as a call to
  action.** Camille: *"defer 467. I don't really care until I try to
  distribute it."* The right trigger is **before the first distribution**,
  and until then the exposure is "unverified" rather than "known broken" —
  `db.localisation()` returns `{}` when the file is gone rather than
  raising, and all seven read sites in `api/wire.py` already go through
  `.get(ref) or {}`. The issue holds the design, the `@cache` trap and the
  two load-bearing proofs it needs, so none of that has to be re-derived.

  Said here because the sentence above sent a session to read `#467` in
  full before finding the deferral in its one comment — the same cost this
  file's own first rule is about, with this file as the stale part.
* **A content agent is shown each name beside its ref, and writes only the
  ref.** This replaced "shown no name, ever" on **2026-10-12**, on Camille's
  call:

  > *"We originally created this method to keep agents from accidentally
  > including power names, and I think it's created problems where an agent
  > doesn't know when something refers to itself. Instead, we should supply
  > the agent the name and its ref, and give it explicit instructions to only
  > use the ref from localization instead of the name."*

  What the old rule cost: **a row could not tell when a clause meant
  itself.** Every ref in a card looks alike, so an author could not
  distinguish "the zone lasts until the end of m6233's next turn" — this
  creature — from a reference to somebody else, and guessed. Six monster rows
  sat blocked on a general facility for addressing another creature's aura
  when all six meant their own, and it took a ruling to unstick them.

  So `spec.py` now ends each brief with a **glossary**: every ref the card
  mentions, beside its printed name, **with this row's own ref marked**. The
  card text itself is unchanged — still refs — so the body stays safe to copy
  from, which is the failure mode worth engineering against.

  **The guarantee is no longer by construction. It is instruction plus
  gate**, and the gate is `leaks.py --cited`: a file may not print the name
  of a ref it also cites. That is a narrower question than the tree-wide name
  search, so it needs none of the waivers that give the tree-wide search its
  #494 blind spot. Its first run found **20 real leaks** that every previous
  run of `leaks.py` had reported clean — five feature names in one SQL
  comment, four race names, and one in a `trigger=` string the page renders,
  which is tier 1.

  Two honest notes. The construction guarantee was **already false** (#528:
  `spec.py` leaks a name in associated-powers clauses), so it described an
  intention, not the output. And a one-word ordinary name beside its own ref
  is still not caught — that case belongs to the tree-wide walk.
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
| Chargen | `src/combat_engine/chargen/` | builds every character, and only deals them -- a human cannot drive it (#793). Persistence is `story/save.py`, which writes a party's sheets and where the campaign got to. |
| Story Engine | `src/combat_engine/story/` | the campaign runner: a module as a graph of scenes, roleplay, skill challenges, reflavouring, persistence, and the party carried between fights. `story/CLAUDE.md` governs it. |
| Database | `src/combat_engine/db.py` | where `game.db` and the localisation are, and how to read them. Below every component; imports nothing from the package. |
| Armour table | `src/combat_engine/armour.py` | the printed armour and shield numbers, read once. Below every component; imports only `db.py`. A table, not behaviour. |
| Instruments | `scripts/` | belongs to no component. |

**These seams are now a gate, not a paragraph.** `.importlinter` holds six
contracts and `check.py`'s `seams` instrument asserts them in seconds, so
what follows is checked on every run rather than believed. Making it a gate
corrected two of the five claims it started with, which is why the prose
below reads differently from how it did:

* `etl` → `content` is **zero direct imports** (content reads the built
  database).
* `engine` → `content` is **four** sites and is a known leak:
  `query.py:675` and `cast.py:7965, 8132, 8154`, all function-local to dodge
  the import cycle. It was documented as five, at five line numbers, none of
  which were right.
* **The package imports nothing from `api/`** — `web/` reaches it over HTTP,
  which is the cleanest boundary here. This used to say *nothing* imports it
  in Python at all, and that was false: `scripts/drivers.py:14196,14245`
  imports `api.day` to play the day mode, which is an instrument doing its
  job rather than a breach.
* **Nothing imports `etl/` to read the database**: `game()` lives in
  `db.py`, which imports nothing from the package, so five readers reach a
  sqlite file without reaching through each other. `scripts/build.py`
  calling `build()` is the one import of ETL from outside it.
* `engine` → `chargen` is **zero**, and the sixth contract is what keeps it
  there. It was one site — `skills.py:263`, importing two armour constants —
  and this table never mentioned the relationship at all.

All six are scoped to **direct** imports, because a call site in a file is
what each claim is about.

**The transitive picture was worse, and fixing it is what `#852` came to.**
`engine/skills.py:263` imported `chargen`, a sixth relationship nothing
documented, and through it `etl.build → engine.skills → chargen → content`
made the first bullet false as a statement about the graph. The two
constants behind that import are a **printed table, not behaviour** — six
readers across four layers wanted them, four of those imports function-local
to avoid pulling in the whole of chargen — so they now live in
`src/combat_engine/armour.py`, below every component, which is the same
answer and the same reasoning as `db.py` in `#334`. The edge is **gone**
rather than allow-listed, which is why its contract carries no
`ignore_imports`.

867 files, 5,393 dependencies. #334, #852.

## Checking

```
uv run scripts/check.py           every instrument
uv run scripts/check.py --fast    skip the two that start a server
uv run scripts/check.py --all     audit every row, not only changed ones
```

**Cadence, which is the thing that was actually costing.** Wide audit sweeps
were 36% of everything this suite had ever cost, at 12x the per-catch price of
a narrow run — so the rule was *rare, not fast*. **It is now both**, measured
2026-10-22:

```
narrow check.py   ~465s -> 222s      --fast  ~342s -> 120s
the wide audit    2,592s -> 1,279s   a whole --all run, 43-54 min -> 25 min
```

Four memoisations and a parallel instrument loop, each verified by an
`audited.json` identical across the change but for its sha. So "once before
a push" below is a cheaper instruction than it was, and the per-commit run
is no longer worth routing around.

* **`check.py` per commit.** Narrow; seconds to a couple of minutes.
* **`check.py --all` once before a push**, not once per commit. It is the only
  invocation that settles the whole-tree debt, and `check.py` now names that
  debt and **withholds "all instruments clean"** until it is paid.
* **A worktree merges on whatever looked at its rows, and `check.py` says
  which.** The rule used to be *"a worktree owes its own `--all` before it
  merges"* (#848), on the ground that `nightly.sh` is installed against the
  main checkout and never sweeps a branch. That is still true about the
  branch — and it made **105 of 106** audit runs wide, because `--all` is
  wide by definition, so the impact map saved 21 minutes against 22 hours
  spent sweeping. A selector the gate ignores is a selector nobody uses.

  It also contradicted the cadence directly below it. A worktree merges
  **into master**, which the nightly *does* sweep, so the pre-merge wide run
  bought a few hours against the same window this file already calls the
  right trade for every other regression.

  So the gate asks the narrower question — **has anything looked at the rows
  this change can affect?** — and the last line of every run answers it:

  | what ran | verdict |
  |---|---|
  | nothing under `engine/` changed | merge; `audit --changed` covered it |
  | the map **narrowed** | merge; those rows are green and the overnight sweep is the net |
  | the map **refused** (wide) | the wide sweep is owed first — nothing has looked at the rows |
  | `--all` already ran clean | merge |

  The refusal case is unchanged from #848 and is the one that matters: a hot
  function or a module-level edit means the map cannot say which rows are
  reachable, so nothing has. The other three are evidence.

  **Four things keep this honest rather than convenient.** `check.py` tells
  a map *refusal* apart from a map with *no opinion* — they are opposite
  answers and collapsing them was a bug in the first draft. Every wide audit
  run records **why** it was wide, so `--history` reports the split and the
  causes rather than a score.

  **A function the map has never seen no longer reads as a dead one.** This
  was the sharpest hole in the whole mechanism and it was silent:
  `selection` fails *closed* on a function absent from the map — "never
  executed by any row, so no row can depend on it" — which is sound for a
  genuinely dead function and **false for a verb written since the
  recording**. `Cast.replace_roll` was written hours after the map was
  recorded, two rows call it, and an edit inside it selected **0 rows** and
  reported clean: the newest code in the tree, audited by nothing. It now
  asks git whether the function's own lines have moved since
  `recorded_at`, and goes WIDE when they have. On `cast.py` that widens 6
  functions and leaves the other 42 absent-and-unchanged ones failing
  closed as before. An incremental recording therefore must **not** advance
  `recorded_at` — it re-measures three rows, not the corpus — and stamping
  HEAD on it put every new verb straight back into the fail-closed branch.

  **And the map tops itself up, so nobody has to remember.** A clean
  `check.py` records the rows the commit touched — `impact.py --record
  --refs`, measured at **9s for two rows** against 83 minutes for the
  corpus — so a verb is in the map one commit after it is written rather
  than one nightly. It declines out loud on a red run (a raising row
  records a short ref list), on a sampled map, and above a 40-row budget,
  which is a content wave rather than a commit.
* **And a worktree must not rebuild the database. ETL work happens on
  `master`, or after the branch merges.** In a worktree `data/game.db` is a
  symlink into the main checkout, and `etl.build` opens by deleting its
  output — so a rebuild here hands `master`'s *old* ETL code a database built
  by the *new* one, and the overnight nightly then sweeps 21,476 rows against
  data their code does not match. `scripts/build.py` refuses outright now
  rather than relying on anyone remembering this, with `--force` for the case
  where it is genuinely wanted. #857.
* **An engine change no longer selects every row, and this is automatic.**
  `scripts/impact.py` holds a recorded map of which rows actually execute
  which engine function, and a plain `check.py` consults it with no flag:
  an edit inside one `cast.py` method audits the **58-ish rows that were
  observed to run it**, not 23,062. Measured on `Cast.crit_becomes`: 71 rows,
  0.3%, and when that method is made to raise **70 of 70 selected rows go
  red** while two equal-size control sets stay green.

  **It fails open on nine things and says which every time** — no map, an
  unreadable one, a sampled one, a corpus that moved, untracked Python under
  `src/`, a changed file absent from the map, an edit at module level, a
  function too hot to list, or a union over the map's own ceiling. A change
  under `etl/`, `chargen/` or to `scripts/audit.py` is refused outright,
  because `audit.WIDE` names those for reasons the map does not speak to.
  The content half is **unioned in**, never replaced.

  No flag, deliberately, and the asymmetry against `--calls` is the point:
  `--calls` narrows on a claim nothing checks, so it is opt-in and refuses
  loudly; the map narrows on a recorded observation, so a forgotten
  narrowing costs nothing and a flag nobody remembers costs the whole
  saving.

  **What it cannot see**: a row added or rewritten since the map was
  recorded, and a row that does not reach the changed function today but
  would after the change. The overnight sweep is the backstop for all of them,
  which is the same day-long window this file already accepts. `check.py`
  prints the map's age and corpus on every run so nobody has to ask.
  #853, #865, #866.
* **Or let the nightly pay it.** `scripts/nightly.sh`
  (`scripts/combat-engine-nightly.plist`, installed once with `launchctl
  bootstrap`). The sweep is a **net, not a gate** — everything that catches a
  regression in *seconds* already runs per commit — so a regression that
  lands at 10am being found overnight is the right trade against a gate
  people route around.

  **It is an hourly poll, not a clock time, and this file must stop naming
  one.** A stated hour has gone stale here three times — `02:07` against logs
  reading `03:07` (#566, #746), then `03:07` after `#871` replaced the
  calendar entry outright. `StartCalendarInterval` does not survive a closed
  lid: launchd defers it to the next wake and drops it if there is none, which
  cost three of seventeen nights. So the plist is `StartInterval 3600` and
  `nightly.sh`'s `_due` decides:

  * nothing unless the last real sweep is **more than 20 hours old**, and
    then only between **01:00 and 07:00**;
  * **unless it is more than 48 hours stale**, when it runs at any hour,
    because two missed nights beats tidiness.

  A not-due wake writes no dated log — 23 a day is noise — only
  `logs/nightly-heartbeat`, which keeps "alive and not due" distinguishable
  from "not running at all". **Read the stamp, never predict it**: every
  `check.py` prints when the net last reached a verdict, and
  `uv run scripts/check.py --history` has the attempts.

  **And it loses to a dirty tree, silently, for days.** It refuses to start
  on uncommitted edits — rightly, since a sweep over them certifies no
  commit — so one stray modified file stops the net indefinitely. On
  2026-10-22 a single uncommitted `.gitignore` line had skipped the 21st and
  the 22nd, leaving `NIGHTLY-FAILED` describing a red run from the 20th with
  two non-verdicts after it. If the nightly line says SKIPPED, check
  `git status` in the **main** checkout first.

  **Read the result without being asked to**: the next `check.py` in any
  session stops printing `wide sweep owed since <sha>` once a nightly has paid
  it, which needs nobody to remember. And **every `check.py` run now prints the
  nightly's state in words** — `last run <when> clean`, `RED`, or
  `last attempt <when> SKIPPED`, with the age beside it. Read that line; it is
  the first thing to look at before trusting a clean narrow run.

  **And it re-records the impact map after a clean sweep**, which is what
  keeps the narrowing above honest — a map more than a day old has seen a
  day of rows it does not hold. Only after a *clean* sweep, at the same
  HEAD, on a clean tree: a red sweep means rows are raising, and a row that
  raises records only the lines it reached before raising, so its ref list
  comes out short in the direction that omits rows. If the tree moves during
  the 83 minutes the map is **deleted**, because no map audits everything and
  a misattributed one narrows wrongly. That makes the nightly ~110 minutes.

  `#853` proposed folding the recording into the sweep itself "for the
  overhead rather than a second sweep". **That premise is false**: recording
  is ~4.3x, so it is a second 83-minute job either way, and switching the
  gate's own sweep into a recording run would slow the gate and move every
  timing it reports.

  This file used to say `logs/NIGHTLY-FAILED` **exists if and only if the last
  run was red**, and that was false. A skip leaves the marker alone — rightly,
  since a skip is no verdict and must not erase a real one — so a red sweep
  followed by any number of skips leaves a file the invariant says describes the
  last run. On 2026-10-13 it read `FAILED at 227e2b0` while the last attempt had
  skipped on a dirty tree, two days and 60 commits later, and following the
  one-line protocol gave the wrong answer. The marker is evidence about *a*
  sweep; `check.py` is what reconciles it with the latest attempt. #543.

  It refuses a dirty tree, because a sweep over uncommitted edits certifies no
  commit, and it never commits the `audited.json` the sweep rewrites — it
  reports whether a row changed sides or only the sha moved. #469.
* **`--calls` is the per-commit evidence for a new verb**, and it is the thing
  five wide sweeps in one session were paid for instead.
  `audit.py --calls 'c.light()'` is seconds. `_changed` widens to all 21,304
  rows for **any** change under `engine/` or `etl/` — a comment included — so
  an engine change has no narrow option and `--calls` is the answer rather
  than the widen. It is evidence the verb works, never that nothing broke;
  the nightly is what says the second thing.
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
