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
* **A `question` tag carries a plain-language version, as the last
  comment.** Camille, asked directly, 2026-11-06:

  > *"can we make it required that when you add a question tag to an issue
  > you give an ELI5?"*

  Required, and `scripts/questions.py` is the gate -- unpaused in
  `check.py`, because a backstop nobody runs is not a requirement. It
  reports three states, which are three different jobs:

  | | meaning |
  |---|---|
  | parked | your ask is the last comment, in plain words — waiting on Camille |
  | **ANSWERED** | *Camille's* comment is last, so it is waiting on **you** — act on the ruling and drop the tag, or re-ask |
  | **NO ELI5** | tagged with no plain-language version — the thing this rule forbids |

  What the plain version holds: **what is broken**, **what is being
  asked**, **what each option means**, and **your pick**. Short sentences,
  no jargon, no line numbers. The technical comment stays above it; this
  is not a replacement for it.

  **Last comment, not any comment**, for this section's own first reason:
  the bottom of the thread is where the current state lives, so an ELI5
  buried under four later notes of yours is not the thing Camille reads.

  And it is worth the effort rather than a formality: the first pass over
  the parked list found **14 of 15** had none, one issue whose plain
  version Camille still could not follow (*"I still don't understand the
  question"*), and three stale blockers found only because writing the
  simple version forced the thread to be read end to end.
* **Put new state in a comment**, not by editing the body. That is what
  keeps the convention working — and it is why the bodies above went stale.
* **Close with the measurement**: what landed, what moved, how it was
  verified. "Done" is worth nothing to the next reader. Say what you did
  *not* do, too.
* **Triage before working.** Prefer the issue that unblocks others.
* **Check a cited blocker's state before planning around it.** An issue
  saying *"blocked on #N"* is a claim about #N **on the day it was
  written**, and nothing re-checks it. A triage sweep of the 63 open
  non-`question` issues on 2026-11-02 found **nine** citing a blocker or
  tracker that had since closed:

  | the issue | cites | state |
  |---|---|---|
  | `#312` | `#313` | closed — it had been idle on a false premise |
  | `#505` | `#914` | closed, and the title still cites `#235` before that |
  | `#955` | `#1016` | closed; the action half was unblocked and unnoticed |
  | `#599` | `#132`, `#157` | both closed — the batch it waited for is gone |
  | `#981` | `#539`, `#956`, `#959`, `#974` | all four closed |
  | `#1039` | `#539` | closed |
  | `#1011` | `#964` | closed |
  | `#988` | `#786` | closed, leaving its finding homeless |
  | `#1047` | `#1010` | closed — and the in-code pointer says so too |
  | `#581` | `#812` | closed, and five rows were tracked against it |

  It is **one command** — `gh issue view N --json state` — and it is the
  cheapest check on this list by an order of magnitude. Do it for every
  blocker an issue names *before* believing the issue is held, and before
  concluding anything is blocked.

  Two things make this worse than ordinary staleness. A closed blocker
  reads exactly like a live one, so the issue looks correctly parked rather
  than wrong. And the pointers **chain**: `#505` was re-pointed from `#235`
  to `#914` and both are now dead, so a reader following the thread lands
  on a second stale answer and may stop there.

  The same applies to a pointer **in code**. `#1047`'s own
  `Table.target` docstring still defers to `#1010`, which is closed and of
  which `#1047` is the successor.
* **A rules table quoted in an issue is evidence a table exists, not
  evidence of its contents.** Read the page in `resources/` before writing
  one into code — the PDF extracts with `pypdf`. Five issues, measured:

  | | what the quote got wrong |
  |---|---|
  | `#982` | its four heroic rows were exact; its claim that `story/dc.py` (now `combat_engine/dc.py`) holds "the DC half of the same table" was false — that table is a revised **per-level** one and the printed one is three-level **bands** |
  | `#988` | one ten-row table was really **three** printed tables, each with a **Level** column that was dropped; one row renamed, one omitted, three absent from the book |
  | `#1010` | **exact.** All 20 cells of a ten-band, two-column table, and the sentence under it, verbatim |
  | `#972` | **exact.** The whole level-adjust rule, verbatim, and it had already shipped |
  | `#1021` | **exact, and my "the table does not exist" was the wrong answer** — Camille corrected it. The size-keyed table is on DMG page 125 and gives all eight sizes, naming the parcel numbers to add or remove. I searched for an `N characters` phrase and for the heading in normal case; it renders in small caps as `charact Er Group sizE and trEasurE parcELs`, so neither could match. **A failed search is not an absent table** — see the paragraph below |

  **This table used to say "three of the four quotes were not what they
  said", and counted `#1010` and `#972` among the three on the ground that
  "both quote DMG2, which is not in `resources/`, so neither is checkable".
  Every clause of that was wrong**, and it is the sharpest case in this file
  of the mistake the file is about:

  * `resources/` holds **six** PDFs and one of them is `Dungeon Masters
    Guide 2.pdf`. The session that wrote the claim opened the *first*
    Dungeon Master's Guide, correctly found no minion damage table in it,
    and concluded the source was absent. `ls resources/` was never run.
  * `#972` does not quote DMG2 at all. It quotes the first DMG, which was
    never in doubt.
  * Both quotes check out **exactly** — 20 of 20 cells on one, the entire
    rule on the other. So the tally is **2 of 4 wrong, not 3**, and a
    reader was being told to distrust the two that were right.

  So the lesson is narrower and more useful than the old headline: **the
  numbers were right in 5 of 5 cases, and what went wrong was always the
  structure around them** — which table a row came from, which columns
  were dropped, which file holds the other half, whether the table is
  there at all. `#982` is the worked example: pairing a banded damage
  table with a per-level DC table misaligns in the **row keys**, so
  nothing would have raised and a level-5 trap would have read band
  `4th-6th` damage beside level-5 DCs from another edition.

  **And the fifth case inverts the direction, which is why the count moved
  from 4 to 5.** `#1021`'s quote was *exact* and this file called the
  table non-existent — so the error was mine and not the issue's, and it
  took Camille correcting it to find. Three searches had come back empty:
  an `N characters` phrase, the heading in normal case, and a scan of all
  221 pages. The heading renders in small caps, extracting as
  `charact Er Group sizE and trEasurE parcELs`, so every one of those
  searches was asking for text the page does not contain.

  So: say in the code which printing a table came from and what could not be
  verified; **`ls resources/` before declaring a source absent**, because
  that is a one-command claim and it was wrong here for two days; **grep a
  distinctive phrase from a table's *body* before declaring the table
  absent**, because a heading is the least reliable thing to search for —
  it is the text most likely to be set in a display face that extracts as
  nonsense, and the body row `Add three parcels` found the page
  immediately; and if the only source really is a quote, say so on the
  issue rather than landing it.
  Same rule as a census — see *"an issue's census is a floor"* — applied to
  the cells instead of the count.

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

`claude` marks an issue opened on Camille's behalf, and **it cannot be read
in either direction.** Re-measured 2026-11-02 over every issue, open and
closed:

```
1,081 issues           834 carry `claude`      247 do not
of those 247, at least  42 carry a Claude signature in the body
```

So the conclusion is unchanged and its **reason has inverted**. This said
*"carried by 400 of 400 issues, so it distinguishes nothing"* — universal,
and therefore noise. It is not universal: it is **77% and inconsistently
applied**, which is worse, because a label at 100% is at least honest noise
while one at 77% invites the inference it cannot support. Absence does not
mean Camille opened it — `#1057`–`#1068` is a contiguous run of Claude's own
filings with no label at all.

Either apply it on every filing or invert it to mark the ones Camille opens.
Until then **do not infer authorship from it**, and do not quote the 400.

## Attribution: the record cannot tell Camille's words from Claude's

Camille asked, 2026-10-28, whether anything shows the difference. Measured:

| where | distinguishes? |
|---|---|
| git commits | **yes** — author is `Claude (Camille)` |
| issue comments | **no** — every one is authored `camille-ryan`; Claude posts via `gh` |
| the `claude` label | **no** — 834 of 1,081, and 42 of the 247 without it are Claude's own |
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

  So: fix tier 2 when you find it, and **strive** for tier 3 — a message is
  editable for exactly one moment, so a hook there is the right amount of
  effort. Never rewrite tracker history for it.

  **That hook exists now, and this paragraph used to describe one that could
  not have worked.** It said *"a pre-commit `leaks.py --history --staged`"*,
  and both halves were wrong. `pre-commit` runs before git writes the
  message under composition, so the hook would have read
  `.git/COMMIT_EDITMSG` — the **previous** commit's message — passing the
  new one every time and failing on text nobody could still edit. And a
  bare `--staged` fell through to the tree-wide walk and printed *"no
  printed names in tracked files"*, which reads exactly like a message
  passing. Five messages were "checked" that way in one session and none of
  them was read.

  It is `hooks/commit-msg`, tracked, reached through `core.hooksPath`:

  ```
  git config core.hooksPath hooks     once per clone
  ```

  `--staged` now implies `--history` and takes the message path git hands
  the hook. Proven by committing a planted printed name: refused, naming
  the ref, with HEAD unmoved. #1035. Tier 1 is the one worth building an instrument for, and `#467` is
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
* **The printed row wins over a printed table.** Camille, asked directly,
  2026-10-31:

  > *"We should always stick with the printed rows unless using some house
  > rule flag later on (potentially a 'update to MM3 math')."*

  This answers the question *"never derive a number the page prints"* leaves
  open: what to do when **two** printed things disagree, a table and a row.
  The row does. A prescriptive table — DMG2's minion damage is the worked
  case, `#1010` — does **not** license overriding a number a row printed, and
  the place for that is a **house-rule flag**, named and opt-in, never a
  silent substitution.

  Worth knowing before this reads as a loss: it is why `de36346a` moves only
  3 rows. That change put the printed table inside `Math.convert`, which is
  the opt-in scaling preset, and left declared rows alone — the small number
  is the ruling working, not the change failing.
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
| Content | `src/combat_engine/content/` | 783 modules of hand-written rows. |
| Wire | `src/combat_engine/api/` | engine state → DTOs → the page. |
| UI | `web/` | the page. Vanilla JS, no build step. |
| AI Policy | `src/combat_engine/policy/` | what the AI chooses, not what the rules allow. |
| Chargen | `src/combat_engine/chargen/` | builds every character, and only deals them -- a human cannot drive it (#793). Persistence is `story/save.py`, which writes a party's sheets and where the campaign got to. |
| Story Engine | `src/combat_engine/story/` | the campaign runner: a module as a graph of scenes, roleplay, skill challenges, reflavouring, persistence, and the party carried between fights. `story/CLAUDE.md` governs it. |
| Database | `src/combat_engine/db.py` | where `game.db` and the localisation are, and how to read them. Below every component; imports nothing from the package. |
| Armour table | `src/combat_engine/armour.py` | the printed armour and shield numbers, read once. Below every component; imports only `db.py`. A table, not behaviour. |
| DC table | `src/combat_engine/dc.py` | what a skill check has to beat, by level and band — 90 numbers read out of `rules_dc`. Below every component; imports only `db.py`. A table, not behaviour. Was `story/dc.py` and moved when the kernel became a second reader. #949, #1001. |
| Instruments | `scripts/` | belongs to no component. |

**These seams are now a gate, not a paragraph.** `.importlinter` holds seven
contracts and `check.py`'s `seams` instrument asserts them in seconds, so
what follows is checked on every run rather than believed. Making it a gate
corrected two of the five claims it started with, which is why the prose
below reads differently from how it did:

* `etl` → `content` is **zero direct imports** (content reads the built
  database).
* `engine` → `content` is **four** sites and is a known leak:
  all in `query.py` and `cast.py`, all function-local to dodge the import
  cycle. `.importlinter` holds exactly which and `check.py --only seams`
  asserts it in 0.2s.

  **No line numbers here any more, and that is the fix rather than a
  shortcut.** This said five sites at five line numbers, every one wrong.
  They were corrected to four, with numbers, and **went stale again**:
  `query.py:675` and `cast.py:7965, 8132, 8154` are now `query.py:875` and
  `cast.py:8729, 8896, 8918`, because `cast.py` grew from 7,500 lines to
  17,672 underneath them. Resetting them a second time buys the same decay
  a third. A count and a file list decay slowly; a line number decays
  whenever anybody edits above it; the contract cannot decay at all.
* **The package imports nothing from `api/`** — `web/` reaches it over HTTP,
  which is the cleanest boundary here. This used to say *nothing* imports it
  in Python at all, and that was false: `scripts/drivers.py`
  imports `api.day` at two sites to play the day mode, which is an instrument doing its
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

**The `--all` figure has since drifted back to 35 minutes**, measured over
three wide runs on 2026-11-02, and the audit is not what moved: it got
*faster* (1,279s to ~1,250s) while `drivers` grew to 658s and became bigger
than the other 26 instruments combined. The arithmetic is under `audit.py`
below. The cadence argument is unchanged — a 35-minute run once before a
push is still affordable — but do not quote 25 minutes.

* **`check.py` per commit.** Narrow; seconds to a couple of minutes.
* **`check.py --all` once before a push**, not once per commit, and **by
  whoever pushes** — nothing else settles it. It is the only invocation that
  clears the whole-tree debt, and `check.py` names that debt and
  **withholds "all instruments clean"** until it is paid.

  **It is also ~30 minutes, so the work that owes one gets batched.** That
  is Camille's caveat on `#1055` and it is the whole reason this line is
  not "run it when in doubt": a sweep per fix cost 102 minutes in one
  session for work that warranted a single run. Finish the batch, run the
  cheap gates, sweep once. The nightly bullet below has the sequence and
  the measurement.
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

  **A full recording is 1.3 to 2.8 hours, not 83 minutes, and the spread
  is bimodal rather than a trend.** Six completed pooled recordings in
  `logs/launchd-nightly.out`:

  ```
  10-25  9,487s  2.4 rows/s      10-30  4,788s  4.8 rows/s
  10-27 10,217s  2.3 rows/s      11-01  4,789s  4.8 rows/s
  11-03  9,208s  2.5 rows/s      11-05  8,555s  2.7 rows/s
  ```

  Two clusters at a corpus that moves by 33 rows across the whole set, so
  this is machine load, not the corpus growing. **83 minutes is the fast
  arm** — 4,788s is 80 minutes — so the figure was never invented, it was
  the best case quoted as the expected one, and **four of six runs are
  2.4–2.8 hours**. A session that must hold the tree still for the whole
  run needs the worst case, which is why the number is a range now.

  Do not quote 1.0 rows/s either: that came from 1,800 rows at the front
  of an abandoned run, and the corpus is **sorted** with the expensive feat
  and power families first. See *"a rate from the front of a sorted corpus
  is not a rate"*. #1159.

  **And the map tops itself up, so nobody has to remember.** A clean
  `check.py` records the rows the commit touched — `impact.py --record
  --refs`, measured at **9s for two rows** against hours for the
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
* **The nightly does NOT pay the wide debt, and this file said for weeks
  that it did.** Camille's call on `#1055`, after asking whether the
  schedule was still earning its keep:

  > *"option 2 is fine with the caveat that long-duration sweeps should be
  > done infrequently and consequently work should be batched
  > intelligently."*

  Measured over its whole life — **31 attempts, 2026-10-08 to 2026-11-01**:

  ```
  completed CLEAN    0
  completed RED      8
  SKIPPED           20      "a check.py was running", "a dirty tree"
  no verdict         3
  ```

  **Zero clean sweeps in 24 days.** The skips are structural rather than
  unlucky: it can only run when nobody is working and the tree is clean, and
  this project is worked on for most of the day. So every session deferring
  wide debt to the nightly was deferring it to nothing — and the same false
  premise pushed a session the *other* way on 2026-11-01, hand-launching
  four `--all` runs (~102 minutes) because a green sweep felt necessary
  before closing an issue.

  **So the gate is narrow checks plus the impact map, and a wide sweep is
  owed before a push, by whoever pushes.** Nothing settles it automatically.

  What actually bought the saving was the **map**, not the schedule —
  71 rows in 73s against 23,063 in ~1,300s, 18x, with no flag — which is
  why retiring the net claim costs nothing it was really providing.

  **`nightly.sh` stays, for the one job it demonstrably does**: re-recording
  the map. It recorded 23,063 of 23,063 contexts on 2026-11-01 *after* a red
  sweep, because `#1030` lets a red run whose failing instruments fire no
  rows record anyway. A recorder that works is worth keeping; a net that has
  never caught anything is not worth citing.

  And the caveat is the operative half: **a long sweep is rare, so batch the
  work that owes one.** Finish the whole batch, run the cheap gates — `ruff`,
  `todo` (0.6s), `rules` (0.4s), `lint <file>`, a repo-wide grep for every
  renamed symbol, then `drivers` — and only then one sweep. A sweep used to
  *discover* breakage instead of confirm it gets paid for three times over;
  that is exactly how the 102 minutes above were spent.

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

  **And reading the stamp is not the same as reasoning from it.** On
  2026-10-31 a session read `last run 2026-10-30 05:11 clean`, concluded
  tonight's had already happened, and started editing `cast.py` — while the
  poll was mid-sweep. That line was *yesterday's*; the schedule is a poll
  with a 20-hour window, so a run inside it says nothing about whether the
  next one is due. The stamp answers "when did the net last reach a verdict",
  and nothing else.

  **An edit voids a running sweep as surely as a rebuild, and far more
  quietly.** `build.py` refuses outright while it is sweeping; an edit is
  simply accepted, and `audit.py` reads source from disk through
  `inspect.getsource`, so shifting line numbers under a module imported
  earlier makes it tokenise from the wrong offset and report a **raise on a
  sound row**. The tell that session had and did not read: the sweep logged
  `symbols 466 placed` while the live count was already 468. Its timings went
  too — `ruff` 421s against a normal ~90s, because the same session was
  running its own checks alongside.

  So: `pgrep -f "scripts/"` before **any** tree change, not only before a
  launch. Checking before three destructive launches and then editing during
  a fourth is how this one happened.

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
  the 1.3-2.8 hours the map is **deleted**, because no map audits everything and
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
* **Batch the gate, not the proof.** The expensive checks are per-*run*, not
  per-change, so N changes behind one gate cost what one change costs:

  ```
  per change     a narrow proof -- the parse-level harness (seconds) or the
                 instrument itself (<1s) -- plus a plant that goes red
  batch          every ETL change -> ONE rebuild
  after rebuild  diff EVERY spec table, four leak gates, ONE wide sweep
  the sweep      `audit.py --since`, NOT a plain run -- see below
  separately     baseline writes, their own commit, per-field diff read
  ```

  **"EVERY", because the count was wrong.** This said *"ALL ELEVEN spec
  tables"* and there are **15** — `associate`, `build_option`,
  `class_feature`, `companion`, `disease`, `feat`, `item`, `item_block`,
  `monster_power`, `poison`, `power`, `race`, `racial_trait`, `terrain`,
  `trap`. A reader diffing eleven of them would have missed four, which is
  exactly the failure the instruction exists to prevent. Ask the schema —
  every table with both a `ref` and a `spec` column — rather than carrying
  a number that grows whenever an importer lands. #1048.

  **A committed batch empties `--changed`, so a plain `check.py` audits
  nothing and says so.** Found immediately, on the first batch run this way:
  committing the work before the gate — which is right, a merge has to be
  committed — left a clean tree, so `_changed` selected **zero rows** and
  `check.py` reported `audit checked NOTHING -- a skip, not a pass` under 26
  green instruments. Only `#466`'s third exit code tells those apart; a
  reader going by the headline would have taken an unaudited engine change
  for a verified one. `--since` measures from the last *completed* full
  sweep and is the invocation a batch wants.

  **The narrow proof is what makes batching safe, and without it batching is
  how a regression hides.** A rebuild diff over five parser changes cannot
  attribute anything: `#1027` shipped a fix verified against **one spec table
  of eleven**, reported "41 specs changed" where all eleven gave **46**, and
  the five it missed held a regression that split a printed name in two. That
  cost a second rebuild, which is exactly what batching is supposed to avoid.

  **The harness is cheap and is the technique to reach for.** `etl/` is
  reproducible without a rebuild: `_creature_names(rows, names)` then
  `monster.parse(id, txt, src, others)` reproduced that bug and proved its
  fix in **3 seconds**, and `_cross_reference_rest(con, names)` over a
  **copy** of `game.db` did the same for the pass that caused it.

  Baselines stay a separate commit because a batch moving `audited.json`,
  `keywords.json` and `ingest.json` at once cannot say which change shrank
  which — read the per-field diff, never the headline.
* **What a change costs to gate, by where it lands.** Not every component is
  wide, and the file never said which: `audit.WIDE` names five paths and
  nothing else.

  | a change under | what it costs to gate |
  |---|---|
  | `engine/` | WIDE, and the impact map can narrow it |
  | `etl/` | WIDE **plus** a rebuild |
  | `chargen/`, `story/` | WIDE |
  | `scripts/audit.py` | WIDE |
  | `policy/` | **no audit at all** — `replay` and `fight` are the cover |
  | `scripts/` (anything else) | narrow: run that instrument, plant it |
  | `content/` | narrow, by file |
  | a `CLAUDE.md` **anywhere**, including inside a WIDE component | narrow |

  **That last row is new and it used to be false.** Both of `WIDE`'s tests
  were a bare `startswith`, so editing `src/combat_engine/story/CLAUDE.md`
  selected all 21,495 rows — a 25-minute sweep to write down a rule. The
  tax fell on documenting exactly the four components whose rules most need
  documenting, which is why it is worth a line here. `audit._is_wide`
  excludes `.md` now: a `.md`-only change reports `scope: 0 of 23061` in
  **2 seconds**, and says `SKIPPED` rather than claiming green.

  It excludes `.md` and not "everything that is not `.py`", deliberately:
  the whole non-Python surface under those four paths is three `CLAUDE.md`
  files, so a data file added under `etl/` later still widens. #1026.

  `policy/` costing nothing is deliberate and `WIDE`'s own note says so: a
  policy change decides what the AI *chooses* among options the rules already
  allow, so it cannot break a row. Costs only — no counts and no running
  order here, because a schedule in a rules file is what rots. This file has
  watched it happen to the seam line numbers twice, to the row count above,
  and to the nightly's stated hour three times.
* **`--only <name>`** while iterating on one instrument's finding.
* **`--only scorecard` on a `policy/` change**, with `scorecard.py --save` when
  the change *is* the improvement. It is paused out of the default run: 2 red
  runs in 108 is not a gate, it is a measurement.

`audit.py` is the expensive one: **about 21 minutes for all 23,059 rows** —
1,217s, 1,266s and 1,281s on three runs measured 2026-11-02. That cost has
been measured and **cannot be tuned away** — see `_changed`'s docstring
before trying.

**It is no longer the only expensive one, and that is the correction worth
reading.** `drivers` costs **658s**, which is more than the other 26
instruments put together, so a whole `--all` is **35 minutes** and not the
25 this file claimed two paragraphs up:

```
audit (solo)                     1,217s
drivers                            658s
browser (solo)                     169s
the other 26 instruments          ~304s
serial sum 2,348s, wall 35 min     the lanes buy about 4 minutes
```

The lanes buy so little because `audit` is solo and `drivers` dominates
everything left to parallelise. **And `drivers` costs the same standalone
as it does inside the suite** — 658s against 650/673/685s — so this is its
own cost and not contention; `#1066` was filed on the opposite premise and
the measurement refuted it. Four rules carry half of it, `reroll_after`
alone 147.6s for 15 assertions, because they build 250-board negative
controls. Whether that sample size is worth 23% of every run is on
`#1066`.

This said *"ten minutes for all 12,197 rows"*, which was wrong on both
numbers and in the direction that matters: a reader pricing an engine change
off 12,197 rows and ten minutes is pricing **half the corpus at 40% of the
clock**, and will reach for a wide run far too casually. `engine/CLAUDE.md`
has carried the corrected figures for a while and this file contradicted it.
Count it off `dsl.REGISTRY`, which is what `audit.py` walks.

Use the narrow forms:

```
uv run scripts/audit.py --changed          rows in changed files
uv run scripts/audit.py --calls 'c.foo()'  rows naming a verb
uv run scripts/audit.py --verdicts         is the verdict itself honest
uv run scripts/audit.py --sample 300       a direction, cheaply
```

**Who you are changes two rules.** The main session lints the whole tree
(`ruff check .`) and commits. A parallel content agent lints **only its own
file** and never touches git — a tree-wide `--fix` has destroyed another
agent's work. The wider division those two rules are an instance of is
below.

## Who runs the gates

Camille, after watching a separate Story session close issues quickly but
hit friction landing the work, 2026-10-31: *"I was wondering if it makes
more sense to use you here as a controller, and have you delegate tasks to
agents, and then only you decide when to sweep, check, audit, push."*

Yes — and the friction was never the push. It is **shared mutable state with
no single owner**. One checkout, one `game.db`, one nightly, one impact map,
one set of baselines, two writers. What that cost in a single day:

* `#1028` was fixed **twice**, independently, from different sides
  (`968a6c90` and `f17c46cd`) — and the second had to be reverted at the
  merge.
* `Scene.room`'s bad type was fixed at the cause on one side (`c4db47d0`)
  while the other **suppressed** it; the suppression commit was superseded
  the moment the two met.
* A rebuild here truncated the other session's `game.db` mid-read.
* A sweep was voided by an edit landing under it.
* `origin/master` and local master diverged **34 / 9** with nobody owning
  the merge.

### One owner for anything shared or destructive

**Rebuild, wide sweep, impact-map record, baseline writes, merge, push.**
No exceptions — that list is exactly what collided above. Everything on it
either rewrites a file every other process reads, or claims a lock, or
decides what the tree *is*.

### Delegate what can be verified narrowly

The boundary is not seniority, it is **whether the work can be checked
without the shared suite**:

* **Content rows: delegate.** They partition by file and verify with
  `lint.py <file>` and `audit.py <refs>`, which is already the rule above
  and already works. It is also where the token spend is, so it is where
  parallelism pays.
* **Engine, ETL and instruments: do not.** Their verification is *global* —
  see the per-component gate table in **Checking** — so handing one out buys
  no parallelism and costs a collision. They **batch** instead, which gets
  the same saving: the gate is per-run, not per-change.

### Branch per session; the controller owns master

The infrastructure already assumes this — worktrees exist and
`scripts/build.py` refuses to rebuild from one (`#857`). The only missing
piece was that **merging had no owner**, which is how a branch tip became
`origin/master` while local master carried 34 unmerged commits.

### A controller that also authors must gate itself

The failure above was not carelessness about the rule; it was a session that
checked `pgrep -f "scripts/"` before three destructive **launches** and then
edited during a fourth, having reasoned from a stale stamp that the nightly
had already run. An edit is as destructive to a running sweep as a rebuild
and much quieter — see the nightly bullet in **Checking**.

So the check belongs before **any** tree change, not before launches.
