#!/usr/bin/env python
"""Run every instrument, and say which ones are unhappy.

    uv run scripts/check.py            all of it
    uv run scripts/check.py --all      and audit every row, not just changed ones
    uv run scripts/check.py --fast     skip the two that start a server
    uv run scripts/check.py --history  what each has cost, and what it has caught
    uv run scripts/check.py --list     what it would run, and what each catches

There is no CI and no test runner here -- the repo owner does not want tests
written -- so these are *instruments* rather than a suite: each one plays the
real thing and reports what it saw. The gap this closes is that they were
only ever run by hand, one at a time, which is a fine way to forget the one
that would have caught it.

Exit code is the number of instruments that failed, so it is usable as a
gate without reading the output.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Instrument:
    name: str
    argv: tuple[str, ...]
    catches: str
    #: Starts a server and drives a browser. Slow, and skipped by `--fast`.
    heavy: bool = False
    #: Not run unless asked for by name. Two reasons, and the text should say
    #: which:
    #:
    #: * **its failure is known and not yet understood** -- leaving it in the
    #:   default run trains people to re-run until it passes, which is worse
    #:   than not running it;
    #: * **its value is conditional on what changed** -- a before/after
    #:   measurement is worth its minute on the change it measures and worth
    #:   nothing on the other ninety-nine, and `--history` is where that shows
    #:   up as a cost per catch nobody can defend.
    paused: str = ""


CHECKS = (
    Instrument("ruff", ("uv", "run", "scripts/lint.py"),
               "style, dead imports, undefined names, shadowed methods"),
    Instrument("types", ("uv", "run", "scripts/types.py"),
               "signatures mean what the call says, on the files that moved"),
    Instrument("refs", ("uv", "run", "scripts/refs.py"),
               "every ref a row's prose names resolves to something"),
    # **The other direction of `refs`' question**: that one asks whether every
    # ref a row names exists, this asks whether two refs are secretly the same
    # card. One printed card declared both as something a character is
    # *granted* and as something the draw can *deal* is two hand-written
    # bodies, so the same card does two things depending on which route the
    # holder took -- and nothing anywhere reported it.
    #
    # Deliberately **not** the similarity ranking in the same file, which is a
    # judgement and stays out of this list. The gate asks a structural
    # question with one right answer, so there is no floor to tune.
    #
    # 0.4s. Six clusters are waived by name in `twins.DECLARED_TWICE_KNOWN`
    # against #1043 and #1045, so a seventh reddens -- and a waiver whose
    # cluster stops forming reddens too, because "fixed" and "this check went
    # blind" look identical and only one of them is safe.
    Instrument("cards-twice", ("uv", "run", "scripts/twins.py",
                               "--declared-twice"),
               "no printed card is declared under two refs"),
    # **Beside `refs` because it is the same question about the other
    # vocabulary.** `refs` asks whether a ref a row names exists; this asks
    # whether a *symbol* a row looks up exists, in both directions:
    #
    # * a `Cast` member in no category file, so `docs/symbols/` cannot go
    #   stale as `Cast` grows -- Camille's requirement on the plan, and the
    #   half a hand-written hierarchy cannot keep;
    # * a `when=lambda ctx: ctx.get("...")` naming a key nothing writes.
    #   `m5788a0` is the motivating case: a level-10 soldier whose whole card
    #   is an immunity, reading a `vs` key that no ctx has ever carried, while
    #   eight rows wanting the same fact read it off the event. The row lays
    #   its effect, audits green, and does nothing. #591.
    #
    # Under a second: one import of `content/` and a regex walk. The expensive
    # mistake it is aimed at is the one `vocab.py`'s own docstring records --
    # six verbs that exist marked missing by four agents in one afternoon.
    Instrument("symbols", ("uv", "run", "scripts/symbols.py"),
               "docs/symbols/ is current, and no gate reads an unknown key"),
    # **Five claims the root `CLAUDE.md` makes in prose, and nothing checked
    # them.** `grimp` builds the import graph, `import-linter` asserts
    # contracts over it, and `.importlinter` holds the five: the ETL does not
    # reach content, the kernel imports neither the ETL nor the wire, no
    # package module imports the wire, `db.py` imports nothing from the
    # package, and `engine -> content` stays at its known sites.
    #
    # Writing the file found **two of the five claims wrong**, which is the
    # argument for having it:
    #
    # * `engine -> content` was documented as "five sites" at five line
    #   numbers, all stale. It is four, at `query.py:675` and
    #   `cast.py:7965,8132,8154`.
    # * "nothing imports `api/` in Python at all" is false --
    #   `drivers.py:14196,14245` imports `api.day` to play the day mode,
    #   legitimately. The claim holds of the *package*, so that is what the
    #   contract says.
    #
    # Scoped to **direct** imports (`allow_indirect_imports`), because that
    # is what the prose claims -- a call site in a file. The transitive
    # picture is a separate and more alarming finding, recorded in #852.
    #
    # Seconds, and proven load-bearing by planting a sixth
    # `from combat_engine.content import loader` in `engine/grid.py`: the
    # contract went BROKEN naming the file and line.
    Instrument("seams", ("uv", "run", "--group", "dev", "lint-imports",
                         "--config", ".importlinter"),
               "the five component seams CLAUDE.md claims in prose"),
    Instrument("rules", ("uv", "run", "scripts/rules.py"),
               "the two hand-copied rules tables still match the printed ones"),
    Instrument("audit", ("uv", "run", "scripts/audit.py", "--changed"),
               "every declared row fires, and does something"),
    # **The instrument that says whether the one above means anything**, and it
    # was missing. `audit` reported silent 193 -> 107 at `65421a0` and all 86
    # of the difference was credited with one event the rows cannot emit --
    # `f139`, whose whole body is `c.bonus("range", 5)`, was credited with
    # setting a relation. A 17-instrument sweep ran clean through it; this
    # caught it in **seconds**, and nothing was running it.
    #
    # Worse than missing it: `audit`'s baseline only went red because the
    # number *improved*, so re-recording would have made the artifact
    # permanent and every later sweep green. That is the shape
    # `scripts/CLAUDE.md` warns about -- "a check that cannot pass is the same
    # failure pointed the other way" -- arriving from the other side.
    #
    # Cheap enough to be unconditional: ten pinned rows, each run twice
    # (as written and `hollowed`), seconds. `VERDICT_KNOWN` carries the one
    # standing failure by name so this is a gate and not an allowance. #578.
    Instrument("verdicts", ("uv", "run", "scripts/audit.py", "--verdicts"),
               "the verdict itself is honest, on rows whose answer is known"),
    Instrument("leaks", ("uv", "run", "scripts/leaks.py"),
               "no printed name reached the tree"),
    Instrument("specs", ("uv", "run", "scripts/leaks.py", "--specs"),
               "no printed name reached what an author is shown"),
    # **The gate that replaced a construction guarantee**, 2026-10-12: an
    # author is now shown each ref's name so a row can tell when a clause
    # means itself, so something has to ask whether one was written down.
    # Beside `leaks` rather than folded into it because it asks a *narrower*
    # question -- only the refs a file cites -- and therefore needs none of
    # the waivers that give `leaks` its #494 blind spot. Proven by planting
    # `cf:ranger-f1`'s name in a content file: this went red naming the file,
    # and `leaks` in the same run still said "no printed names in tracked
    # files". Twenty real leaks on its first run, including five in one SQL
    # comment and one in a `trigger=` string the page renders.
    Instrument("cited", ("uv", "run", "scripts/leaks.py", "--cited"),
               "no file prints the name of a ref it cites"),
    # **The same narrow-question shape as `cited`, on the column nothing
    # read.** `feat.category` is the bracket after a feat's printed name.
    # `--specs` reads `spec` only; `columns` tests whole-value equality
    # against the name index, which a category is not; and the tree-wide
    # walk waives a two-word label of ordinary words in prose, correctly.
    # So 72 labels went unexamined and one was an invented proper noun in
    # `etl/feat.py`. Seconds, and it caught its own author's comment on
    # the first run. #622.
    Instrument("categories",
               ("uv", "run", "scripts/leaks.py", "--categories"),
               "no tracked file prints a feat category that is a name"),
    # **The question asked the other way round, which is the only shape that
    # can see a name the repo has no copy of.** Every hole the blocklist
    # search has had -- a hyphen, a non-ASCII letter, a comma, a whole table
    # missing from the walks list -- came from its shape rather than its
    # matcher, and #493 measured the limit: of the phrases this finds, **0
    # are a known printed name and 0 contain one**, with a positive control
    # proving the lookup behind those zeros works. So no amount of matcher
    # work reaches this residue.
    #
    # **A gate rather than opt-in, deliberately, and against the precedent
    # of `localise --drift`.** That one is kept out because every legitimate
    # ETL change moves a value; this one moves on an import that adds
    # name-shaped text to a spec, which is *exactly* the moment a leak
    # arrives. Keeping it manual would reproduce the fault #493 describes --
    # "nobody has ever looked". The cost is a re-record when an import
    # legitimately adds a phrase, which is the same bargain `keywords.py`
    # and `targets.py` already make, and it is 0.35s a run. #493.
    Instrument("ingest", ("uv", "run", "scripts/leaks.py", "--ingest"),
               "no spec holds a name-shaped phrase the baseline does not know"),
    Instrument("todo", ("uv", "run", "scripts/todo.py"),
               "no `todo=` waits on a symbol that now exists"),
    # **The only instrument that reaches the network**, and it earns it:
    # Camille asked that a `question` tag be *required* to come with a
    # plain-language version, and prose in `CLAUDE.md` is not how this repo
    # makes a thing required. Unpaused on purpose -- a backstop nobody runs
    # is not a requirement.
    #
    # `gh` being unreachable exits `NOTHING_IN_SCOPE`, so an offline run
    # prints SKIP and is kept out of "all instruments clean" rather than
    # passing quietly. ~1s per parked issue; there are usually a dozen.
    Instrument("questions", ("uv", "run", "scripts/questions.py"),
               "every issue parked on Camille ends with a plain-language ask"),
    Instrument("bonuses", ("uv", "run", "scripts/bonuses.py", "--quiet"),
               "every bonus says the type its card prints"),
    # Beside `bonuses` because it is the same question about a different corpus:
    # does the code say the printed number. A monster ability's whole content is
    # its header, so this is most of what can be wrong with one.
    Instrument("cards", ("uv", "run", "scripts/cards.py", "--quiet"),
               "every monster header says the numbers its stat block prints"),
    # **The third of the same question, and the one nothing asked.** `bonuses`
    # compares a printed bonus type, `cards` a stat block's numbers; a power's
    # printed *keyword list* was hand-declared against nothing. `cards` has the
    # right shape for it and only ever reads a damage type, so a row with no
    # `damage=` returned before the keywords were looked at. Half a second: an
    # import of `content/` and two queries. #486.
    Instrument("keywords", ("uv", "run", "scripts/keywords.py", "--quiet"),
               "every header declares the keywords its card printed"),
    # **The fourth of the same question**, and the one the first three cannot
    # reach: `bonuses` a bonus type, `cards` a stat block's numbers,
    # `keywords` a keyword list -- and nothing asked whether a power's target
    # *pool* can hold the thing its Target line names. It could not for
    # eleven rows, which `audit.py` reports as working because the effect
    # does land, on the wrong kind of thing. Six fixed on the first run and
    # three of the eleven appear nowhere in the issue that found them.
    # Seconds: one import of `content/` and two queries. #855.
    Instrument("targets", ("uv", "run", "scripts/targets.py", "--quiet"),
               "a target pool can hold the thing its printed line names"),
    # **Added because its new half caught a real fork on its first run**, and
    # because nothing else asks this question: a leg's fork decides which rows a
    # character is offered and which race scores best in a draw, and until
    # `PRINTED_LEG` existed there was nothing to compare it against. Seconds to
    # run -- an AST walk over `content/` plus one query. #235.
    Instrument("legs", ("uv", "run", "scripts/legs.py"),
               "every gated leg exists, and agrees with the page it came off"),
    # **Beside `replay` because it is the half `replay` cannot do.** Seven
    # recorded fights cover what seven drawn parties happen to do, and two
    # engine mechanics had no cover at all -- 0 phasing events and 6 blindness
    # events of 10,665 -- so both bugs shipped with `replay` 7 of 7 green.
    # Camille's call on #422: targeted drivers, not an eighth fixture.
    Instrument("drivers", ("uv", "run", "scripts/drivers.py", "--quiet"),
               "the printed rule for a mechanic no fixture reaches"),
    Instrument("replay", ("uv", "run", "scripts/replay.py", "verify"),
               "the engine still plays the recorded fights"),
    Instrument("fight", ("uv", "run", "scripts/fight.py", "--quiet"),
               "a whole fight runs to a finish"),
    # **Beside `fight` because it is the same question one level up**, and it
    # covers the seam none of the above reaches: `fight` plays an encounter,
    # `replay` plays seven recorded ones, and neither knows what a fight is
    # *for*. This plays an adventure -- a roleplay scene, a skill challenge, a
    # fight, a rest, another fight -- carrying the party's wounds, spent
    # powers and surges between them.
    #
    # It caught a real resource leak on its first run and nothing else could
    # have: after the *skill challenge*, four characters had spent 6, 4, 5 and
    # 10 powers between them with nothing having attacked anything, because a
    # challenge needs a started encounter for feats to arm and starting one
    # fires every once-per-fight trait. No crash and no warning -- just a
    # party that was quietly weaker from then on, which no per-encounter
    # instrument can see because each of them builds a fresh party.
    #
    # Seconds, and it needs no network: `--no-dm` plays the module's own
    # written text, which is why that is a first-class mode rather than a
    # fallback (#794). The fixture module is ours -- a published one can
    # never be committed. #789.
    Instrument("play", ("uv", "run", "scripts/play.py", "--play",
                        "scripts/fixtures/modules/sunken-mill.json",
                        "--seed", "7", "--quiet", "--solo", "--no-llm"),
               "a whole adventure runs, carrying the party between scenes"),
    Instrument("leaks-modules",
               ("uv", "run", "scripts/leaks.py", "--modules"),
               "no tracked file quotes an adventure or names its cast"),
    # **In the default run, where `--history` deliberately is not.**
    # `--history`'s commit half can never go green, because a pushed
    # message is append-only -- so it would print a number every run and
    # become noise. This one can: it was red on 8 findings when written and
    # is green now, and a new leak is a thing the author can still fix.
    #
    # It **skips and says so** on a machine with no `modules/`, which is
    # every fresh clone and every CI box, rather than passing silently.
    Instrument("play-god", ("uv", "run", "scripts/play.py", "--play",
                           "scripts/fixtures/modules/sunken-mill.json",
                           "--seed", "7", "--quiet", "--solo", "--no-llm",
                           "--god-mode"),
               "the whole scene graph, with the fights handed over"),
    # **Covers the CLI wiring that the driver cannot.**
    # `drivers.py god_mode` calls `run.step(god=...)` directly, so breaking
    # the flag on its way from `argparse` to `step` left it green -- the
    # mechanism was asserted and its one caller was not. This entry is the
    # only thing that would catch `god=False` being passed by mistake.
    #
    # It is also the cheapest pass over the whole module graph there is,
    # since no fight is fielded: every scene, every transition, seconds.
    #
    # **`--solo --no-llm` and not just `--play`.** Without `--solo` every
    # character defaults to human, nobody declares, and the beat loop spins
    # four empty exchanges -- so the roleplay half would have been *driven*
    # without being *exercised*, which is the shape of coverage this suite
    # exists to refuse. With it, the fixture's yard runs its affordances,
    # its `once` rule and its ending with canned lines and no model at all.
    #
    # `--no-llm` is load-bearing rather than defensive: `story/llm.py` talks
    # to ollama, and an instrument that goes red because nobody started a
    # model server is an instrument people route around. The model path has
    # its own driver, which reports an honest skip instead (#801).
    # **Both of these were broken by a refactor and nothing noticed**, which is why
    # they are here. Retiring `LinearPolicy` left `winrate.py` with a stale
    # `policy_name="linear"` default, so its ordinary invocation raised `KeyError`
    # on every seed and reported nothing played; `check.py` ran every other
    # instrument and not that one. Two seeds is enough to catch a broken
    # instrument, which is all these two are for -- the numbers they exist to
    # produce need far more and are not a pass/fail question.
    Instrument("winrate", ("uv", "run", "scripts/winrate.py",
                           "--seeds", "2", "--level", "5", "--draw", "scored"),
               "the batch fight runner still runs"),
    # **Paused on its own numbers.** 108 runs, 13,114s -- 12.8% of everything
    # this suite has ever cost -- and 2 of those runs red, which is 6,557s a
    # catch. Its own docstring calls it "the gate on a policy change", and it
    # self-reports a baseline 111 commits stale, so on an ordinary commit it
    # spends a minute comparing against a number that no longer means what it
    # meant. Run it where it is the measurement: `--only scorecard` on a
    # `policy/` change, and `scorecard.py --save` when the change is the
    # improvement.
    Instrument("scorecard", ("uv", "run", "scripts/scorecard.py", "--level", "5"),
               "the policy scorecard still measures",
               paused="value is conditional: a policy/ change, not every commit"),
    Instrument("api", ("uv", "run", "scripts/api_smoke.py"),
               "the wire: options, streams, names off", heavy=True),
    # Un-paused. The intermittent failure was never `check.py` and was never
    # a click that missed: the instrument clicked the fourth highlighted
    # square, the overlay draws the provoking squares first, and a walk that
    # provokes can be stopped by the attack it draws -- 200, nobody moved,
    # nothing wrong. It clicks a free square now. 18 runs straight, in both
    # ways of launching it, against roughly one failure in five before.
    Instrument("browser", ("uv", "run", "scripts/browser.py"),
               "the page itself, in Chromium", heavy=True),
)


#: Engine files whose public functions content calls **by name**, so a change
#: to one is narrowable by `audit.py --calls`. Everything else under
#: `engine/` changes what an existing verb *means* rather than adding one,
#: which is precisely the case `_calls`' docstring says to pay the wide run
#: for. Two files, deliberately: the list is short because the claim is
#: strong. #761.
NARROWABLE = {
    "src/combat_engine/engine/cast.py": "c.",
    "src/combat_engine/engine/query.py": "",
}


def _verbs_from_diff() -> tuple[list[str], list[str]]:
    """The verbs this working tree touches, and the reasons it cannot say.

    Derived rather than typed, for the reason `audit._ctx_forwarders` gives
    about itself: a flag you have to remember is a flag that gets forgotten,
    and the one time it is forgotten is the time the wide run mattered.

    Returns `(needles, refusals)`. **A non-empty `refusals` is a refusal** --
    the caller must not narrow -- because every entry is a change this cannot
    bound: a file whose functions content does not call by name, a private
    helper every verb routes through, or an edit at module level that could
    change anything.

    The needle for a `Cast` method is `c.<name>`, which is how a row spells
    it. For a `query` reader it is the bare name, because content imports
    those and calls them unqualified -- and a bare name over-matches, which
    is the safe direction for something whose job is to *narrow*.
    """
    import ast

    done = subprocess.run(
        ["git", "status", "--porcelain", "-uall"],
        cwd=ROOT, capture_output=True, text=True,
    )
    if done.returncode != 0:
        return [], ["git status failed, so the diff cannot be read"]
    files = [ln[3:].strip() for ln in done.stdout.splitlines() if ln[3:].strip()]
    engine = [f for f in files if f.startswith("src/combat_engine/engine/")]
    if not engine:
        return [], ["nothing under engine/ has changed, so there is nothing "
                    "to narrow -- plain `check.py` is already narrow here"]

    needles: list[str] = []
    refusals: list[str] = []
    for name in engine:
        prefix = NARROWABLE.get(name)
        if prefix is None:
            refusals.append(f"{name} -- content does not call its functions by "
                            f"name, so a change here is not bounded by any "
                            f"verb")
            continue
        path = ROOT / name
        if not path.exists():
            refusals.append(f"{name} -- gone from the tree")
            continue
        base = subprocess.run(
            ["git", "show", f"HEAD:{name}"],
            cwd=ROOT, capture_output=True, text=True,
        )
        if base.returncode != 0:
            refusals.append(f"{name} -- no committed version to compare with")
            continue
        now, was = path.read_text(), base.stdout
        moved = _moved_lines(was, now)
        try:
            tree = ast.parse(now)
        except SyntaxError as exc:
            refusals.append(f"{name} -- will not parse: {exc}")
            continue
        spans = [
            (fn.name, fn.lineno, fn.end_lineno or fn.lineno)
            for fn in ast.walk(tree)
            if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        text = now.splitlines()
        for line in sorted(moved):
            inside = [n for n, lo, hi in spans if lo <= line <= hi]
            if not inside:
                # **Blank and comment-only lines are forgiven, and nothing
                # else is.** Inserting a method moves the blank line that
                # separates it from the next one, which belongs to no
                # function -- and refusing on that made the derivation
                # refuse every additive change, which is the one case it
                # exists for. A module-level *statement* outside a function
                # still refuses: a constant can change any verb at once.
                body = text[line - 1].strip() if line - 1 < len(text) else ""
                if not body or body.startswith("#"):
                    continue
                refusals.append(f"{name}:{line} -- changed outside any "
                                f"function, so it could change anything")
                continue
            # The innermost enclosing def is last by line number; the
            # outermost is the one content can name.
            outer = min(
                (n for n, lo, hi in spans if lo <= line <= hi),
                key=lambda n: next(lo for m, lo, _h in spans if m == n),
            )
            if outer.startswith("_"):
                refusals.append(f"{name}:{line} -- inside `{outer}`, a private "
                                f"helper, so what it changes is not one verb")
                continue
            needle = f"{prefix}{outer}"
            if needle not in needles:
                needles.append(needle)
    return needles, refusals


def _moved_lines(was: str, now: str) -> set[int]:
    """Line numbers in `now` that differ from `was`.

    `difflib` rather than `git diff -U0` parsing, so the hunk arithmetic is
    somebody else's. Only the new side matters: a deleted line changes a
    verb that is still named by the lines around it.
    """
    import difflib

    out: set[int] = set()
    sm = difflib.SequenceMatcher(
        a=was.splitlines(), b=now.splitlines(), autojunk=False
    )
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "insert"):
            out |= set(range(j1 + 1, j2 + 1))
        elif tag == "delete":
            out.add(j1 + 1)
    return out


def _corpus_of_map() -> int:
    """How many rows the map was recorded over, for the narrowing message."""
    try:
        return int(json.loads((ROOT / "logs" / "impact.json").read_text())
                   .get("corpus", 0))
    except (OSError, ValueError, TypeError):
        return 0


#: What `_rows_from_map` concluded. **Four states, not two**, and the
#: fourth is why this is a named value rather than something read off the
#: notes list. `_merge_verdict`'s own docstring tells three of them apart --
#: narrowed, refused, no opinion -- and the first draft of this file
#: collapsed two of them, which that docstring records as a shipped bug.
#:
#: `ZERO` is the state that was folded into `NONE` and should not have been:
#: `engine/` **did** change, the map read every changed function, and every
#: one of them is absent-and-unchanged -- dead code no row executes. That is
#: an affirmative answer (scope is empty) rather than an absence of one, and
#: reporting it as `NONE` printed *"nothing under engine/ changed"*, which is
#: false in the one sentence a reader would rely on.
NARROWED, ZERO, NONE, REFUSED = "narrowed", "zero", "none", "refused"


def _rows_from_map() -> tuple[list[str], list[str], str]:
    """The rows the impact map says this change needs, and what to print.

    **Automatic, not behind a flag**, which is the one design decision here
    worth arguing. `_verbs_from_diff` makes the case against a flag about
    itself -- "a flag you have to remember is a flag that gets forgotten, and
    the one time it is forgotten is the time the wide run mattered" -- and the
    same reasoning points the other way for a *narrowing* that fails open: a
    flag nobody remembers means the saving never happens, while a forgotten
    narrowing costs nothing because every doubt returns the wide run anyway.

    So the asymmetry is the point. `--calls` narrows on a claim this file
    cannot check (that content calls the changed function by name), so it is
    opt-in and refuses loudly. The map narrows on a *recorded observation* of
    which rows executed the changed function, and it is the recording's own
    context control that makes the observation trustworthy -- so it can be the
    default, and anything it is unsure about is simply not narrowed.

    Returns `(refs, notes, verdict)`, the verdict being one of `NARROWED`,
    `ZERO`, `NONE` or `REFUSED` -- see the note on those. An empty `refs`
    means no narrowing and the caller's present behaviour stands, with
    `notes` saying why -- never silently. A short map or a moved corpus is
    caught in `impact._load`.
    """
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import impact
    except Exception as exc:
        return [], [f"impact map unavailable ({type(exc).__name__}), so the"
                    f" audit's scope is unchanged"], REFUSED

    # **Asked in this order so a content-only run says nothing at all.**
    # `impact._load` reports a stale or missing map by printing, which is
    # right when the map was about to be used and is nagging on the hundreds
    # of runs that were never going to use it. So the cheap question -- did
    # anything narrowable change -- comes first.
    changed = impact._changed_lines()
    if not changed or not any(f.startswith(impact.NARROWABLE) for f in changed):
        return [], [], NONE

    # **An untracked file is invisible to `git diff`**, which is what the map
    # reads, so a brand-new engine module would be narrowed around rather than
    # audited. `_verbs_from_diff` uses `git status -uall` for its own reasons
    # and this needs the same breadth.
    done = subprocess.run(["git", "status", "--porcelain", "-uall"],
                          cwd=ROOT, capture_output=True, text=True)
    if done.returncode != 0:
        return [], ["git status failed, so the audit's scope is unchanged"], REFUSED
    paths = [ln[3:].strip() for ln in done.stdout.splitlines() if ln[3:].strip()]
    untracked = [ln[3:].strip() for ln in done.stdout.splitlines()
                 if ln.startswith("??") and ln[3:].strip().endswith(".py")
                 and ln[3:].strip().startswith("src/combat_engine/")]
    if untracked:
        return [], [f"untracked Python under src/ ({', '.join(untracked)}),"
                    f" which no map has seen -- the audit's scope is"
                    f" unchanged"], REFUSED

    # **The other three things `audit.WIDE` names, which this must not
    # narrow around.** `WIDE` is `engine/`, `etl/`, `chargen/` and
    # `scripts/audit.py`; the map speaks for the first and for none of the
    # rest. A change under `etl/` moves numbers every row reads, `chargen/`
    # builds every sheet, and a change to the audit itself changes what every
    # verdict means -- so any of them present is a refusal, not a union.
    import audit as audit_mod

    loud = [f for f in paths
            if f.startswith(audit_mod.WIDE) and not f.startswith(impact.NARROWABLE)]
    if loud:
        return [], [f"{', '.join(sorted(loud))} changed, which audit.WIDE says"
                    f" widens on its own -- the audit's scope is"
                    f" unchanged"], REFUSED
    if audit_mod._database_moved():
        return [], ["data/game.db has moved since the last sweep, so every"
                    " number a row reads may have -- the audit's scope is"
                    " unchanged"], REFUSED

    got = impact._load()
    if got is None:
        return [], ["the impact map had nothing to say (see the line above),"
                    " so the audit's scope is unchanged"], REFUSED
    if got.get("sampled"):
        return [], [f"the impact map is a {got['corpus']}-row sample, so most"
                    f" rows were never observed -- the audit's scope is"
                    f" unchanged"], REFUSED
    refs, notes = impact.selection(got, changed)
    if refs is None:
        return [], [*notes, "the impact map says WIDE, so the audit's scope is"
                            " unchanged"], REFUSED
    if not refs:
        # **An affirmative empty scope, which is NOT "no opinion".** Every
        # changed function was read and every one is dead code the map has
        # never seen execute. Keep `notes` -- dropping them printed
        # "nothing under engine/ changed" over a change that was entirely
        # under `engine/`.
        return [], [*notes, "the map read every changed function and no row"
                            " executes any of them, so the audit's scope is"
                            " unchanged"], ZERO

    # **The content half is unioned in, not dropped.** `selection` prints
    # "deferring to audit.py --changed" for a file it does not speak for --
    # and replacing `--changed` with the map's refs is precisely what stops
    # that deferral happening. Caught by a probe that edited one `cast.py`
    # method with three `scripts/` files also modified: it narrowed to the
    # 71 engine rows and silently dropped the other half of the scope.
    # `widen=False` is `--calls`' own door for this -- "the content half
    # only" -- so the two selectors compose instead of overriding.
    content = audit_mod._changed(widen=False)
    both = sorted(set(refs) | set(content))
    if content:
        notes.append(f"# plus {len(content)} row(s) in changed content files,"
                     f" which audit.py --changed would have selected")
    return both, notes, NARROWED


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--fast", action="store_true", help="skip the two that start a server")
    ap.add_argument("--list", action="store_true", help="what would run")
    ap.add_argument("--verbose", action="store_true", help="show each instrument's output")
    ap.add_argument("--history", action="store_true",
                    help="what each has cost, and what it has caught")
    ap.add_argument("--only", help="run just these, comma separated")
    ap.add_argument("--all", action="store_true",
                    help="audit every row, not only the ones in changed files")
    ap.add_argument("--calls", nargs="*", metavar="SYMBOL", default=None,
                    help="an ADDITIVE engine change: audit the rows that name "
                         "these verbs instead of all 21,000. Bare `--calls` "
                         "derives them from the diff. Refuses when the change "
                         "is not narrowable, and never claims to be the wide "
                         "sweep")
    args = ap.parse_args()

    if args.history:
        return history()

    asked = {n.strip() for n in args.only.split(",")} if args.only else set()
    wanted = [
        c for c in CHECKS
        if not (args.fast and c.heavy) and (not c.paused or c.name in asked)
    ]
    if args.all:
        # `--changed` is the default because auditing everything is twenty
        # seconds today and minutes once the content is written, and most
        # runs have touched a handful of rows. Before a commit, run the lot.
        # **`--all` has to reach `types` by adding a flag, not by removing
        # one.** Every other instrument widens when `--changed` comes off;
        # `types.py` takes no such flag and defaults to the files git says
        # moved, so a wide run reported `no changed Python files` on a clean
        # tree -- the one invocation meant to settle whole-tree debt,
        # checking nothing. #870.
        wanted = [
            Instrument(c.name,
                       tuple(a for a in c.argv if a != "--changed")
                       + (("--all",) if c.name == "types" else ()),
                       c.catches, c.heavy)
            for c in wanted
        ]
    narrowed: list[str] = []
    if args.calls is not None:
        if args.all:
            print("--calls and --all ask for opposite things", file=sys.stderr)
            return 2
        narrowed, refusals = (args.calls, []) if args.calls \
            else _verbs_from_diff()
        if refusals:
            print("this change is not narrowable, so the wide audit stands:",
                  file=sys.stderr)
            for why in refusals:
                print(f"  {why}", file=sys.stderr)
            print("\nRun plain `check.py` and pay for it, or name the verbs "
                  "outright with `--calls c.foo`.", file=sys.stderr)
            return 2
        print(f"narrowing the audit to {len(narrowed)} verb(s): "
              f"{', '.join(narrowed)}")
        wanted = [
            Instrument(
                c.name,
                c.argv + tuple(a for n in narrowed for a in ("--calls", n))
                if c.name == "audit" else c.argv,
                c.catches, c.heavy)
            for c in wanted
        ]

    mapped: list[str] = []
    wide_why = ""
    if args.all:
        wide_why = "--all was asked for"
    no_opinion = False
    empty_scope = False
    if not args.all and args.calls is None:
        mapped, why, verdict = _rows_from_map()
        # **Four states, and the gate gets each as a named value.** This read
        # `no_opinion = not mapped and not why` -- the notes list standing in
        # for the verdict -- on the argument that a third return value was
        # avoidable. It was avoidable while there were two states to tell
        # apart; `ZERO` is a third empty-`refs` answer and the trick cannot
        # express it, so it came out as "no opinion" and printed *"nothing
        # under engine/ changed"* over a change entirely under `engine/`.
        # That is the same refusal/no-opinion collapse `_merge_verdict`'s
        # docstring records as a shipped bug, arriving a second time through
        # the inference instead of the code. #1194.
        no_opinion = verdict == NONE
        empty_scope = verdict == ZERO
        if not mapped:
            # The first line that says WIDE is the operative one; the rest
            # are the per-function accounting above it.
            wide_why = next(
                (line.strip("# ").strip() for line in why if "WIDE" in line),
                (why[-1].strip("# ").strip() if why else "no reason given"),
            )[:120]
        for line in why:
            print(line)
        if mapped:
            print(f"the impact map narrows the audit to {len(mapped)} row(s)"
                  f" of {_corpus_of_map()} -- the rows observed to execute the"
                  f" functions this change touches")
            wanted = [
                Instrument(
                    c.name,
                    tuple(a for a in c.argv if a != "--changed") + tuple(mapped)
                    if c.name == "audit" else c.argv,
                    c.catches, c.heavy)
                for c in wanted
            ]

    if args.only:
        keep = {n.strip() for n in args.only.split(",")}
        # **A name that matches nothing is a typo, said so.** `--only lint`
        # -- the instrument is called `ruff` -- left `wanted` empty and the
        # run died on `max() iterable argument is empty` eight lines below,
        # which reads like a crash in the suite rather than a mistyped
        # argument. Every name is checked against `CHECKS`, not against
        # `wanted`, so asking for a paused or slow check by name says
        # "excluded by this invocation" instead of "no such thing".
        unknown = sorted(keep - {c.name for c in CHECKS})
        if unknown:
            known = ", ".join(sorted(c.name for c in CHECKS))
            print(f"no instrument named {', '.join(unknown)}. "
                  f"Known: {known}", file=sys.stderr)
            return 2
        wanted = [c for c in wanted if c.name in keep]
        if not wanted:
            excluded = ", ".join(sorted(keep))
            print(f"{excluded}: known, but excluded by this invocation"
                  f" -- paused, or filtered out by --fast", file=sys.stderr)
            return 2
    if args.list:
        for c in wanted:
            print(f"  {c.name:9} {'(slow) ' if c.heavy else '       '}{c.catches}")
        for c in CHECKS:
            if c.paused and c not in wanted:
                print(f"  {c.name:9} PAUSED  {c.paused}")
        return 0

    failed: list[str] = []
    #: Instruments that exited `audit.NOTHING_IN_SCOPE` -- they ran and
    #: checked nothing. Counted apart from `failed` because a skip is not
    #: a failure of the change in hand, and apart from the clean count
    #: because it is not evidence either. #466.
    skipped: list[str] = []
    #: Instruments reporting drift above a recorded baseline -- real, already
    #: landed, and not this change's fault. #870.
    drifted: list[str] = []
    width = max(len(c.name) for c in wanted)
    at = _commit()
    # **Run them concurrently, report them in order.** The futures are
    # resolved in `wanted` order below, so the output still reads top to
    # bottom exactly as it did -- which it has to: these lines are read by
    # eye and diffed between runs, and a list that reshuffles is the thing
    # `audit._run_all` chose `pool.map` over `as_completed` to avoid.
    #
    # Threads rather than processes: each one only waits on a
    # `subprocess.run`, so there is nothing for the GIL to hold up.
    # Not a `with` block: its exit waits for every future, which would hold
    # all the output back to the end of the run instead of printing each
    # verdict as it lands.
    pool = ThreadPoolExecutor(max_workers=_LANES)
    flight = {c.name: pool.submit(_run_one, c) for c in _submit_order(wanted)}
    for c in wanted:
        took, done = flight[c.name].result()
        tail = _summary(done.stdout) or _summary(done.stderr)
        # **Three outcomes, not two.** An instrument that checked nothing
        # exits `3` (`audit.NOTHING_IN_SCOPE`) and is marked SKIP, because
        # reading it as `ok` is how a clean tree produced `ok audit 1.2s`
        # under "N instruments clean" with no row fired. The skip is counted
        # separately below, so the headline cannot absorb it. #466.
        skipped_run = done.returncode == NOTHING_IN_SCOPE
        if skipped_run:
            skipped.append(c.name)
        # **Drift is a fourth outcome**: something is above its baseline, it
        # happened in an earlier commit, and it is neither clean nor a fault
        # in the change in hand. Same arrangement as the sweep debt -- said
        # out loud, withholds "all clean", does not fail the run. #870.
        drifted_run = done.returncode == TYPE_DRIFT
        if drifted_run:
            drifted.append(c.name)
        mark = ("SKIP" if skipped_run else "DRIFT" if drifted_run
                else "ok  " if done.returncode == 0 else "FAIL")
        print(f"  {mark}  {c.name:{width}}  {took:5.1f}s  {tail}")
        _record(c.name, took, done.returncode == 0, at,
                _scope(done.stdout),
                by=("impact" if mapped and c.name == "audit"
                    else "calls" if narrowed and c.name == "audit"
                    else ""),
                wide_because=(wide_why if c.name == "audit" and not mapped
                              and not narrowed else ""))
        # **A skip is not a failure either**, and the first version of this
        # made it one: exit 3 is non-zero, so `audit` landed in `failed` and
        # a clean-tree run -- the normal state after a commit -- went red
        # every time. That is the "check that cannot pass" failure
        # `scripts/CLAUDE.md` records, arriving from the other side of the
        # same fix. Three categories means three, not two with a label.
        if done.returncode != 0 and not skipped_run and not drifted_run:
            failed.append(c.name)
            if not args.verbose:
                # The failing lines only, which is what is worth reading.
                said = 0
                for line in (done.stdout + done.stderr).splitlines():
                    if "FAIL" in line or "diverged" in line.lower() or "error" in line.lower():
                        print(f"          {line.strip()[:110]}")
                        said += 1
                # **And a traceback whole, because this filter drops the
                # half of one that says anything.** A traceback's useful
                # lines are its `File "...", line N, in <name>` frames and
                # the source line under each, and **not one of them holds
                # the words `FAIL`, `diverged` or `error`** -- so a raise
                # came through as its last two lines and nothing else.
                #
                # The 2026-10-16 03:15 nightly is the measured cost. `audit`
                # raised a `tokenize.TokenError` over 42 minutes of wide
                # sweep and the log kept exactly:
                #
                #     raise TokenError(msg, (e.lineno, e.offset)) from None
                #     tokenize.TokenError: ('unterminated string literal ...
                #
                # Neither names the file, the row, or the frame, and `audit`
                # does not reach that row again for a day. A raise is the one
                # verdict this project treats as inviolable and it was the one
                # least possible to act on. #634.
                raised = 0
                for blob in (done.stdout, done.stderr):
                    frames = _traceback(blob)
                    if frames:
                        print("\n".join(f"          {x}" for x in frames))
                        raised += 1
                # **And the tail when neither of those said anything, which
                # is the premise and not the coverage.** A keyword filter
                # cannot know what an instrument prints when it fails: each
                # has its own vocabulary for its own verdict, and these three
                # words were chosen before most of them existed.
                #
                # `audit` is the case that proved it, in the same run that
                # argued for `_traceback` above. Its per-ref baseline report
                # holds no `FAIL`, no `diverged` and no `error`, and there was
                # no traceback either, so a 2,023-second wide sweep failed and
                # printed **nothing** underneath -- the row that had gone
                # silent had to be found by diffing `fixtures/audited.json` by
                # hand.
                #
                # So the rule is now the invariant that was wanted all along:
                # **a failing check is never detail-free.** Matching lines
                # when there are some, a traceback when there is one, and
                # otherwise the tail -- which is what `--verbose` has always
                # done per check, just applied where it is needed. #634.
                if not said and not raised:
                    body = (done.stdout or done.stderr).splitlines()
                    kept = [x for x in body if x.strip()][-_TAIL:]
                    if kept:
                        print(f"          (no line matched; last {len(kept)}"
                              f" of the output)")
                        print("\n".join(f"          {x[:110]}" for x in kept))
        if args.verbose:
            print("\n".join(f"          {x}" for x in done.stdout.splitlines()[-25:]))

    pool.shutdown(wait=True)

    print()
    for line in _map_state():
        print(line)
    owed = _sweep_owed()
    if mapped and not failed:
        # **The same arrangement the `--calls` narrowing uses, and for a
        # stronger reason.** The map's selection is proven sufficient for the
        # function it names -- break one and every selected row goes red --
        # but it is blind to a row that does not reach that function today and
        # would after the change. So every instrument still ran and the
        # verdict stands; what narrows is the claim.
        print(f"the audit was narrowed by the impact map to {len(mapped)}"
              f" row(s) -- evidence those rows work, not that nothing else"
              f" broke; the wide sweep is still the backstop")
    if narrowed and not failed:
        # **Said even when every instrument is green, and before the verdict
        # line.** A narrowed audit is evidence the named verbs work and is
        # blind to a row that changes behaviour without naming one -- which
        # is `audit._calls`' own caveat. Printing it here and withholding
        # "all clean" below is the same arrangement the wide-sweep debt
        # already uses: every instrument still ran, only the claim narrows.
        print(f"the audit was narrowed to {', '.join(narrowed)} -- evidence "
              f"those verbs work, not that nothing else broke")
    if not _skip_code_matches():
        print(f"WARNING: audit.py's NOTHING_IN_SCOPE no longer matches the"
              f" {NOTHING_IN_SCOPE} this file mirrors, so a skip is being"
              f" read as a pass again -- see #466")
    if drifted:
        print(f"{', '.join(drifted)}: a file is above its recorded baseline"
              f" -- drift that already landed, not this change's fault, and"
              f" invisible until a wide run asked")
    if skipped:
        # **Said before the headline, like the narrowing lines above.** The
        # instrument that skipped is the one whose silence matters most --
        # `audit` is the only one that fires rows -- so "checked nothing" has
        # to be read before any count of clean ones.
        print(f"{', '.join(skipped)} checked NOTHING -- a skip, not a pass"
              f" (clean tree? `audit.py --since` covers everything touched"
              f" since the last full sweep)")
    if failed:
        print(f"{len(failed)} unhappy: {', '.join(failed)}")
    elif skipped:
        print(f"{len(wanted) - len(skipped)} of {len(wanted)} instruments"
              f" clean, {len(skipped)} skipped"
              + (f", {owed}" if owed else ""))
    elif drifted:
        print(f"{len(wanted) - len(drifted)} of {len(wanted)} instruments"
              f" clean, {len(drifted)} reporting drift"
              + (f", {owed}" if owed else ""))
    elif owed or narrowed or mapped:
        # **The one sentence that means "nothing is outstanding" is withheld
        # while something is.** Every instrument still ran and still reported;
        # the verdict is not narrowed, only the claim.
        print(f"{len(wanted)} instruments clean"
              + (f", {owed}" if owed else "")
              + (", and the audit was narrow" if narrowed or mapped else ""))
    else:
        print(f"all {len(wanted)} instruments clean")
    # **The single source of truth for `_ROW_RUNNERS`, published rather
    # than re-implemented.** It was written for `nightly.sh`, which had the
    # same "any failure" gate and only a count to work from; the schedule is
    # retired and the line stays, because a second copy of this set in any
    # other reader is how the two would drift apart. Printed on every run.
    _blocking = _row_runners_red(failed)
    print(f"# row-runners: {', '.join(_blocking) if _blocking else 'clean'}")
    if failed and not _blocking:
        # Said out loud because it is the behaviour #1030 changed: these red
        # instruments used to freeze the map and now do not.
        print(f"         the {len(failed)} red instrument(s) fire no row, so"
              f" the map's recording is not blocked. #1030")
    for line in _top_up_map(failed):
        print(line)
    # **`--all` is not the same as "a wide sweep ran"**, and conflating them
    # made `--all --only types` report "a wide sweep just ran and is clean"
    # having audited nothing. The claim needs the audit to have actually been
    # among the instruments and to have come back green.
    swept = (args.all and any(c.name == "audit" for c in wanted)
             and "audit" not in failed and "audit" not in skipped)
    for line in _merge_verdict(swept, bool(failed), mapped, wide_why,
                               no_opinion, "audit" in skipped, empty_scope):
        print(line)
    return len(failed)


#: Where `audit.py` records the commit of the last sweep that looked at every
#: row. Read rather than written here -- this only reports the debt.
WATERMARK = ROOT / "scripts" / "fixtures" / "audited.json"


def _main_checkout() -> Path:
    """The main working tree, which is not `ROOT` inside a worktree.

    One reader left: `IN_WORKTREE`, which `_merge_verdict` needs to know
    whether there is a merge to have an opinion about. It had three more --
    the nightly's log, its marker and its dated logs all lived in the main
    checkout's `logs/` -- and those are gone with the schedule.

    Kept rather than inlined because the distinction is subtle and was got
    wrong once: `ROOT / "logs"` in a worktree answers a different question
    from the one being asked, and answers it confidently. #848.

    `--git-common-dir` is the main `.git` from anywhere in the repository,
    including from a worktree, so its parent is the main working tree. Falls
    back to `ROOT` rather than raising: a missing git is a reason to report
    less, not to fail the suite.
    """
    done = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=ROOT,
                          capture_output=True, text=True)
    if done.returncode != 0 or not done.stdout.strip():
        return ROOT
    common = Path(done.stdout.strip())
    if not common.is_absolute():
        common = (ROOT / common).resolve()
    return common.parent


#: The main checkout, which is this one unless we are in a worktree.
MAIN = _main_checkout()
#: True when `ROOT` is a worktree, so there is a merge to have an opinion
#: about. `_merge_verdict` is the one reader.
#:
#: **It no longer means "owes its own `--all`".** That was #848's judgement
#: and it was withdrawn by its own measurement: `--all` is wide by
#: definition, so a per-branch rule made 105 of 106 audit runs wide and the
#: impact map unusable. `_merge_verdict` asks the narrower question instead
#: -- has anything looked at the rows this change can affect -- and only the
#: map's *refusal* still owes a wide sweep.
IN_WORKTREE = MAIN.resolve() != ROOT.resolve()

def _map_state() -> list[str]:
    """What the impact map holds, in words, on every run.

    A selector nobody can see the state of is a selector that gets trusted
    after it has stopped working -- so "how old is it, and is it even being
    used" must not be a question anybody has to think to ask.

    **This is the only state line left, and that raises what it has to
    carry.** It used to sit beside a nightly line, and the schedule was the
    thing that re-recorded the map; with the schedule retired, a VOID here
    names a job nothing else will do. Say the repair in the same breath.
    """
    path = ROOT / "logs" / "impact.json"
    if not path.exists():
        return ["impact map: none recorded -- every engine change audits all"
                " rows (`impact.py --record`, 1.3-2.8 HOURS -- see"
                " CLAUDE.md; 87 minutes is its fast arm only)"]
    try:
        got = json.loads(path.read_text())
    except (OSError, ValueError):
        return ["impact map: unreadable, so it narrows nothing"]
    # **Void against the database, which is the one way a map dies that this
    # line could not report.** `impact._load` voids a map whose
    # `game_db_mtime` predates `data/game.db`, because every row's numbers
    # come out of that file -- and it says so only from `impact.py:609`,
    # reachable just inside a *narrowing* run. A content-only commit never
    # narrows, so the message never printed, and this line went on
    # describing a 23,095-row recording that was selecting everything.
    #
    # It misled a session into declining a nightly re-record on the grounds
    # that the map was merely stale. It was void, and that recording was the
    # repair. Reported first, before the age, because an age is a property
    # of a map that is being used. #1185.
    #
    # **Asked by calling `impact._valid`, never by re-implementing it.**
    # This block *was* a copy of the comparison, and the copy is how #1185
    # happened in the first place -- `_load` grew a void state and this
    # reader did not know about it. A second copy that merely agrees today
    # is the same bug waiting on the next change to either side, which is
    # exactly what the digest key was. #1193.
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import impact as impact_valid

        stale = impact_valid._valid(got)
    except Exception as exc:
        return [f"impact map: cannot be checked against data/game.db"
                f" ({type(exc).__name__}), so treat it as narrowing nothing"]
    if stale:
        return [f"impact map: VOID -- {stale}. It narrows nothing, so every"
                f" engine change audits all rows. **This is a named job and"
                f" nothing else will do it**: a full `impact.py --record`,"
                f" 1.3-2.8 hours, owned by whoever rebuilt the database. A"
                f" `--refs` top-up cannot repair it -- it carries the stale"
                f" key forward on purpose -- and declines for that reason."]
    # **Age comes from the recorded commit, not the file's mtime**, and the
    # difference is a lie this line told as soon as the top-up existed: a
    # per-commit `--record --refs` rewrites the file, so three re-measured
    # rows made a 9-hour-old full recording report "under an hour ago". That
    # is the same shape as #543's marker trap -- a fresh write standing in
    # for a fresh verdict -- so the age is read off `recorded_at`'s own
    # commit date, which is what the map's *silence* can speak for. Falls
    # back to the mtime only when git cannot answer, and says which.
    at = got.get("recorded_at") or ""
    stamped = got.get("recorded_when") or ""
    try:
        age = (datetime.now(tz=UTC)
               - datetime.fromisoformat(stamped)).total_seconds() / 3600
        how = ""
    except (TypeError, ValueError):
        # No stamp: a map written before the field existed. The file's mtime
        # is the only remaining answer and it is **wrong in the flattering
        # direction** once a top-up has rewritten the file, so say so rather
        # than print a number that reads as a recording time.
        age = (time.time() - path.stat().st_mtime) / 3600
        how = " (file age -- this map carries no recording time)"
    when = f"{age:.0f}h ago" if age >= 1 else "under an hour ago"
    sha = at[:9] or "an unknown commit"
    corpus = got.get("corpus", 0)
    tail = (" (a SAMPLE -- a deliberate slice was recorded, so it narrows"
            " nothing)" if got.get("sampled") else "")
    out = [f"impact map: {corpus} rows recorded {when} at {sha}{how}{tail}"]
    # **And the top-ups since, which are the other half of "how fresh".**
    # They are what keeps a new verb out of the fail-closed branch, so a
    # line reporting only the full recording's age understates the map.
    tops = got.get("topped_up") or []
    if tops:
        out.append(f"            plus {len(tops)} top-up(s) since, "
                   f"{sum(len(t.get('rows', ())) for t in tops)} row(s)"
                   f" re-measured")
    # **The rows the map has never measured, which is the actionable fact
    # this line did not carry.** `sampled` used to absorb this case and
    # report "a SAMPLE, so it narrows nothing" -- which was true of the
    # consequence and wrong about the cause, because it names a decision
    # nobody had taken. A session read it as a sampling policy and paid a
    # 1,321s wide audit rather than a 2.8s top-up. The gap is narrowed
    # around now rather than fatal, so what this line owes the reader is
    # its size and that it is covered. #925.
    gap: list[str] = []
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import impact as impact_mod
        held_seen = set(got.get("seen") or ())
        if held_seen:
            gap = sorted(set(impact_mod.declared_refs()) - held_seen)
    except Exception:
        gap = []
    if gap:
        out.append(f"            {len(gap)} row(s) declared since the"
                   f" recording are unmeasured, so every narrowed run audits"
                   f" them unconditionally; a clean commit closes the gap"
                   f" itself (`impact.py --record --refs`, seconds)")
    # **Whether the engine has moved since**, which is the one fact that
    # decides whether to re-record and the one this line did not carry. Age
    # alone is the wrong question: a week-old map over an untouched engine
    # is perfectly good, and an hour-old one is wrong about a verb added
    # since. #866 measured the second case -- a new function is invisible to
    # the map until the next recording, and `select` then omits its callers.
    #
    # **This no longer asks for an 87-minute re-record**, because a changed
    # function is now handled where it is read: `selection` widens on any
    # function whose own lines moved since `recorded_at`, so a moved
    # `engine/` file is a note about reach rather than a job. What repairs
    # it cheaply is recording the *rows*, which `--record --refs` does in
    # seconds and `check.py` now does by itself on a clean commit.
    if at:
        done = subprocess.run(
            ["git", "diff", "--name-only", at, "HEAD", "--",
             "src/combat_engine/engine/"],
            cwd=ROOT, capture_output=True, text=True)
        moved = [f for f in done.stdout.splitlines() if f.strip()]
        if done.returncode == 0 and moved:
            out.append(
                f"            engine/ has moved in {len(moved)} file(s) since,"
                f" so a function changed in them audits WIDE until its rows"
                f" are recorded (`impact.py --record --refs`, seconds)")
    return out


#: `audit.py`'s "ran and checked nothing" exit. Mirrored rather than imported
#: because `check.py` must not import an instrument to read its verdict -- it
#: runs them as subprocesses -- and asserted against the real one by
#: `_skip_code_matches` below, so the two cannot drift apart silently.
NOTHING_IN_SCOPE = 3

#: `types.py`'s "a file is above its baseline on a whole-tree run" exit.
#: Mirrored for `NOTHING_IN_SCOPE`'s reason and asserted the same way.
TYPE_DRIFT = 4


def _skip_code_matches() -> bool:
    """Is the mirrored skip code still the one `audit.py` returns?

    A mirrored constant is a second source of truth, which is the shape
    `#492` is about -- two hand-kept lists and nothing reconciling them. One
    import of a module-level int settles it, and the cost of being wrong is
    a skip silently reading as a pass again.
    """
    sys.path.insert(0, str(ROOT / "scripts"))
    try:
        import audit as audit_mod
        return bool(audit_mod.NOTHING_IN_SCOPE == NOTHING_IN_SCOPE)
    except Exception:
        return True


def _unswept_since(sha: str) -> int:
    """Commits after `sha` that a sweep has not covered.

    **A commit whose whole content is the baseline the sweep itself wrote
    does not count**, which is #519's second half and the reason this is a
    walk rather than `rev-list --count`. A sweep certifies a sha and writes
    it into `audited.json`; committing that watermark creates a commit the
    sweep did not cover, so the debt line had a permanent floor of one and
    every run said `owed since <sha>, 1 commit(s) back`. A floor nobody can
    clear is a signal nobody reads -- and this one is the signal the whole
    narrow-per-commit cadence leans on.

    **Sound rather than convenient**: the tree at a baseline-only commit is
    byte-identical to the swept one *except* for that file, so there is no
    code the sweep did not see. It is excluded only when it is the commit's
    **sole** path -- a commit touching the baseline and anything else still
    counts, which is what stops this becoming a way to smuggle an unswept
    edit in beside a re-record. A forged baseline is a different question
    and `audit.py --verdicts` is what asks it.
    """
    done = subprocess.run(["git", "rev-list", f"{sha}..HEAD"],
                          cwd=ROOT, capture_output=True, text=True)
    if done.returncode != 0:
        return 0
    shas = [s for s in done.stdout.split() if s]
    count = 0
    for one in shas:
        paths = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", one],
            cwd=ROOT, capture_output=True, text=True)
        touched = {p for p in paths.stdout.split() if p}
        if paths.returncode == 0 and touched == {str(
                WATERMARK.relative_to(ROOT))}:
            continue
        count += 1
    return count


def _sweep_owed() -> str:
    """Is a whole-tree audit outstanding, and since when?

    **The saving this pairs with is only safe if the sweep still happens.** The
    wide sweep is 36% of everything this suite has ever cost and 12x the
    per-catch price of a narrow run, so the protocol is one of them before a
    push rather than one per commit -- and a protocol nobody is reminded of is
    a protocol that lapses. `audit.py` already prints its own baseline age for
    exactly this reason (#291); this is the same discipline one level up, where
    the decision to pay is actually made.

    **Not an exit code.** An owed sweep is not a failure of the change in hand,
    and a run that goes red for a reason unrelated to what you just did is how
    red gets ignored -- which is the failure `scripts/CLAUDE.md` records about a
    check that could not pass.

    Two ways to owe one, and the second is the one a path test cannot see: the
    database is git-ignored, so a rebuild moves every number a row reads with no
    source change to notice. Same argument as `audit._database_moved`.
    """
    try:
        mark = json.loads(WATERMARK.read_text())
    except (OSError, ValueError):
        return "no whole-tree sweep on record -- `check.py --all` writes one"
    sha = mark.get("sha") or ""
    if not sha:
        return "no whole-tree sweep on record -- `check.py --all` writes one"

    database = ROOT / "data" / "game.db"
    try:
        rebuilt = database.stat().st_mtime > WATERMARK.stat().st_mtime
    except OSError:
        rebuilt = False

    behind = _unswept_since(sha)
    if rebuilt:
        return (f"wide sweep owed: the database was rebuilt after {sha[:9]}"
                f" -- `check.py --all`")
    if behind:
        return (f"wide sweep owed since {sha[:9]}, {behind} commit(s) back"
                f" -- `check.py --all`")
    return ""


# --------------------------------------------------------------------------
# What each one costs, and what it has ever caught
# --------------------------------------------------------------------------
#
# The first attempt at this project grew a check suite that nobody could
# afford to run, and the reason it got that way is that nothing measured it:
# every instrument looked worth its time in the abstract, and none of them
# had to show what it had found. So each run is written down, and
# `--history` prints the two numbers that decide whether an instrument earns
# its place -- what it costs, and what it has caught.
#
# Local, and git-ignored: a timing is about this machine, and a hit rate is
# about how this clone has been used.

LEDGER = ROOT / "logs" / "instruments.jsonl"


#: `audit.py`'s declared contract for how wide a run was. See the note beside
#: the `print` that emits it: keyed on the exact prefix so that moving it makes
#: the field **absent** rather than wrong.
SCOPE = re.compile(r"^# scope: (\d+) of (\d+) declared rows$", re.M)


def _scope(text: str) -> tuple[int, int] | None:
    """How many rows an instrument covered, out of how many there are."""
    found = SCOPE.search(text)
    return (int(found.group(1)), int(found.group(2))) if found else None


#: How many instruments may be in flight at once. The loop was a plain `for`
#: with a blocking `subprocess.run`, so 21 instruments ran strictly one after
#: another on a ten-core machine where sixteen of them are single-process.
#: Measured: the twenty non-audit instruments are a stable **480s wide, 464s
#: narrow**, and the longest single one is `drivers` at ~140s -- so the floor
#: is the longest member, not the sum.
#:
#: Four rather than ten, deliberately. `audit` already runs ten worker
#: processes of its own (`audit._run_all`), so a wide run has every core busy
#: for most of its length and more lanes would mostly take cores away from
#: it. Four collapses the 480s to roughly `drivers`' own 140s without
#: oversubscribing.
_LANES = 4

#: Instruments that must not run beside each other, by group.
#:
#: **`audit` and `verdicts` are the same script.** `audit.py --changed`
#: rewrites `fixtures/audited.json` at the end of a full clean run and
#: `audit.py --verdicts` reads that baseline, so letting them overlap means
#: `verdicts` can read a file mid-write. Nothing had to care while the loop
#: was serial.
#:
#: **`api` and `browser` each start a uvicorn.** They pick their own free
#: port, so they would not collide on one -- but both pay a cold `uv run`
#: plus a full `combat_engine` import before a 20-second health poll, and two
#: of those at once on a loaded machine is how that poll starts timing out.
#: `scripts/CLAUDE.md` already records what server bookkeeping costs when it
#: goes wrong: 69 orphaned uvicorns over three and a half days.
_EXCLUSIVE: tuple[frozenset[str], ...] = (
    frozenset({"audit", "verdicts"}),
    frozenset({"api", "browser"}),
)

#: Instruments that need the machine to themselves.
#:
#: `browser.py` drives real Chromium and several of its checks are about
#: **timing** -- "enemy tokens animate", "the button is gone while that fight
#: is being played". An animation has a wall-clock duration, so no amount of
#: waiting on a condition makes those robust to a loaded box: they were
#: calibrated on a quiet one.
#:
#: Measured, and this is why the entry exists: putting the loop on four lanes
#: turned "enemy tokens animate (0 of them slid)" red on its first full run,
#: a *different* assertion from the one #847 is about. Two load-sensitive
#: checks in one instrument is a pattern, not a coincidence.
#:
#: Costs almost nothing. `browser` is last in `CHECKS`, so by the time its
#: turn comes the other lanes have largely drained; the full run measured
#: 195s with it parallel and the same within noise with it solo.
#: **`audit` is here because four lanes made a wide run 70% slower**, which
#: is the opposite of the point and was measured only after the lanes
#: landed:
#:
#:     wide, serial loop    ~1792s   (audit 1312 + the other twenty at 480)
#:     wide, 4 lanes         3049s   audit alone went 1312s -> 2937s
#:
#: `audit._run_all` already runs one worker process per core, so during a
#: wide sweep every core is busy and three more lanes do not find idle
#: capacity -- they take it from the audit. It cost ~1625s on the audit to
#: save ~330s elsewhere.
#:
#: Solo costs nothing narrow, where `--changed` on a clean tree is 0.6s, and
#: it is the whole sweep wide either way.
_SOLO: frozenset[str] = frozenset({"audit", "browser"})

_LOCKS: dict[frozenset[str], threading.Lock] = {
    group: threading.Lock() for group in _EXCLUSIVE
}

#: One permit a lane. A `_SOLO` instrument takes every permit, so nothing
#: else is running while it does; everything else takes one.
_GATE = threading.Semaphore(_LANES)
#: So two solo instruments could not each hold some permits and wait for the
#: rest. There is one today; the guard is for when there are two.
_SOLO_TURN = threading.Lock()


def _run_one(c: Instrument) -> tuple[float, subprocess.CompletedProcess]:
    """One instrument, timed, held out of its exclusion group's way.

    The locks are taken in `_EXCLUSIVE`'s own order so that an instrument in
    two groups -- none is today -- could not deadlock against one in the
    other order.
    """
    solo = c.name in _SOLO
    if solo:
        _SOLO_TURN.acquire()
        for _ in range(_LANES):
            _GATE.acquire()
    else:
        _GATE.acquire()
    held = [_LOCKS[g] for g in _EXCLUSIVE if c.name in g]
    for lock in held:
        lock.acquire()
    try:
        started = time.monotonic()
        done = subprocess.run(c.argv, cwd=ROOT, capture_output=True, text=True)
        return time.monotonic() - started, done
    finally:
        for lock in reversed(held):
            lock.release()
        if solo:
            for _ in range(_LANES):
                _GATE.release()
            _SOLO_TURN.release()
        else:
            _GATE.release()


def _submit_order(wanted: list[Instrument]) -> list[Instrument]:
    """`wanted`, reordered so no lane blocks early on a group-mate.

    A thread waiting for its exclusion group holds a lane while doing
    nothing, and the queue is FIFO -- so with `audit` and `verdicts`
    adjacent in `CHECKS`, `verdicts` would take a lane and sit on it for the
    whole 1,300-second audit. The second and later members of each group go
    to the back instead.

    Reporting order is unaffected: the caller resolves futures by name in
    `wanted` order.
    """
    claimed: set[frozenset[str]] = set()
    head: list[Instrument] = []
    tail: list[Instrument] = []
    for c in wanted:
        group = next((g for g in _EXCLUSIVE if c.name in g), None)
        if group is not None and group in claimed:
            tail.append(c)
            continue
        if group is not None:
            claimed.add(group)
        head.append(c)
    return head + tail


#: Rows a per-commit top-up will record before it declines and says so. The
#: recording costs ~4.3x an audit of the same rows, so this is a wall-clock
#: budget rather than a correctness limit.
#:
#: **Raised from 40, because the thing it was deferring to is gone.** The
#: old note said a wave that moves hundreds "is the nightly's job"; there is
#: no nightly, so declining meant the rows stayed unmeasured until somebody
#: hand-ran an 83-minute recording. Measured: a 35-row top-up is 27-30s, so
#: ~0.85s a row, and 250 is about 3.5 minutes on the commit after a content
#: wave. That is the most this should cost without being asked for -- above
#: it the message names `impact.py --record --refs` and the rows, so the
#: decision is a human's.
#:
#: A gap left by declining is **safe but not free**: `_load` unions every
#: never-measured row into each selection, so the map keeps narrowing and
#: simply narrows less. #925.
TOP_UP_CAP = 250


#: The instruments that **execute a declared row**, and so the only ones
#: whose redness can make a recorded ref list short. #1030.
#:
#: The hazard both recording gates name is real and narrow: a row that raises
#: records only the lines it reached *before* raising, so its ref list omits
#: rows. Only something that fires a row can produce that. `audit` and
#: `verdicts` are the same script and are what observes a raise; `drivers`
#: runs row bodies, so a red one means the kernel is wrong mid-row and it
#: belongs here on the conservative side.
#:
#: **Gating on any failure instead cost both healing paths indefinitely**,
#: which is worse than it sounds because `todo` is red *by design* when a
#: wanted symbol arrives -- it stays red until somebody writes the rows, and
#: 7 of the 8 rows behind the live instance are content work with a measured
#: blast radius. So `ruff`, `todo`, `leaks`, `browser`, `types`, `seams` and
#: fifteen others each froze the nightly's re-recording and the per-commit
#: top-up, and none of them executes a row. Measured on the live state: the
#: map had narrowed **2 audit runs in its entire life** against 366 wide.
#:
#: This is a **loosening of a guard that protects a selector against
#: choosing too few rows**, which `scripts/CLAUDE.md` is blunt about -- so it
#: carries both halves of a plant rather than an argument. See the commit:
#: a deliberately broken `audit` still declines, and a red `todo` alone now
#: proceeds.
_ROW_RUNNERS = frozenset({"audit", "verdicts", "drivers"})


def _row_runners_red(failed: list[str]) -> list[str]:
    """Which red instruments actually fired a row. See `_ROW_RUNNERS`."""
    return sorted(set(failed) & _ROW_RUNNERS)


def _top_up_map(failed: list[str]) -> list[str]:
    """Record the rows this commit touched, so the map never goes stale.

    **This is what stops "the map had no entry" being a standing excuse,
    and with the nightly retired it is the only thing that does.** A full
    recording is 1.3-2.8 hours, so before `--record --refs` existed the only
    way a row or a verb entered the map was to wait for the schedule -- and
    `selection` fails *closed* on a function it has never seen, so a new
    verb's own edit selected **0 rows** and the run reported clean.
    Recording the handful of rows that just changed is seconds and closes
    that window inside one commit.

    The schedule is gone and this is not a gap it left: re-recording the
    corpus was the one job the nightly demonstrably did, and it did it every
    two to three days. What replaces it is this, plus a **named** job when
    `_map_state` reports VOID. See the root `CLAUDE.md`.

    Declines, out loud, on each of the cases where recording would be
    wrong or not worth it:

    * **a red run among `_ROW_RUNNERS`** -- a row that raises records only
      the lines it reached before raising, so its ref list comes out short
      in the direction that omits rows. A red instrument that fires no row
      cannot do that and no longer declines the recording; #1030 has what
      gating on `bool(failed)` cost;
    * **no map**, an unreadable one, a sampled one, or one **void** against
      the current `data/game.db` -- none of which a top-up can repair, and
      the last of which it would make permanent by carrying the stale key
      forward;
    * **nothing under `content/` changed**, so there is nothing to record
      that the map does not already hold;
    * **more rows than `TOP_UP_CAP`**, which is a content wave rather than
      a commit.

    It never *widens* anything and never fails the run: the map is a
    selector that fails open, so a failed top-up costs a wide audit next
    time and nothing else.
    """
    blocking = _row_runners_red(failed)
    if blocking:
        return [f"map top-up skipped: {', '.join(blocking)} red, and a"
                f" raising row records a short ref list"]
    path = ROOT / "logs" / "impact.json"
    if not path.exists():
        return ["map top-up skipped: no map to merge into"]
    try:
        held = json.loads(path.read_text())
    except (OSError, ValueError):
        return ["map top-up skipped: the map is unreadable"]
    if held.get("sampled"):
        return ["map top-up skipped: the map is a sample, which a top-up"
                " cannot repair"]
    sys.path.insert(0, str(ROOT / "scripts"))
    # **A void map is the one case where topping up makes things worse**, and
    # this checked `sampled` while never asking it. `--record --refs` merges
    # into the held map and inherits its `game_db_digest` deliberately, so a
    # top-up onto a void map writes fresh observations beside 23,000 stale
    # ones and carries the stale key forward -- the void becomes
    # self-perpetuating and the seconds are spent proving nothing. Decline,
    # and name the repair, which is the full re-record. #1193.
    try:
        import impact as impact_valid

        void = impact_valid._valid(held)
    except Exception as exc:
        void = f"the map cannot be checked ({type(exc).__name__})"
    if void:
        return [f"map top-up skipped: {void} -- a top-up merges into the"
                f" held map and would carry that forward, so the repair is"
                f" a full `impact.py --record`"]
    try:
        import audit as audit_mod
        rows = set(audit_mod._changed(widen=False))
    except Exception as exc:
        return [f"map top-up skipped: {type(exc).__name__} asking which rows"
                f" changed"]
    # **The map's own gap, as well as this commit's rows -- #925.** Topping
    # up from the diff alone could never heal a row declared by an *earlier*
    # commit, because such a row is in no later diff: two racial traits sat
    # unmeasured for 36 hours and disabled the selector for the whole corpus
    # the entire time, and no number of later top-ups would have reached
    # them. The map knows which rows it has never seen, so it heals from
    # that too, and the gap is included in the `TOP_UP_CAP` budget below
    # rather than exempt from it.
    gap: set[str] = set()
    try:
        import impact as impact_mod
        held_seen = set(held.get("seen") or ())
        if held_seen:
            gap = set(impact_mod.declared_refs()) - held_seen - rows
    except Exception:
        gap = set()     # the diff's rows alone are still worth recording
    rows = sorted(rows | gap)
    if not rows:
        return []
    if len(rows) > TOP_UP_CAP:
        return [f"map top-up skipped: {len(rows)} rows changed, over the"
                f" {TOP_UP_CAP}-row budget. Record them when convenient:"
                f" `impact.py --record --refs '{','.join(rows[:40])}'`"
                f"{' (first 40 of them)' if len(rows) > 40 else ''}"]
    began = time.time()
    done = subprocess.run(
        ["uv", "run", "scripts/impact.py", "--record", "--refs",
         ",".join(rows)],
        cwd=ROOT, capture_output=True, text=True)
    took = time.time() - began
    # **The top-up goes in the same ledger as everything else it is traded
    # against.** Camille asked for the map's usage *and timing* to be
    # monitored, and the top-up is now a recurring per-commit cost paid to
    # keep the narrowing available -- so "is the map earning its keep" has
    # to net it off against the 1,230s a narrowed run saves, not ignore it.
    # `ok=False` on a failure, so a top-up that stops working shows up as a
    # red line in `--history` rather than as silence.
    _record("map-topup", took, done.returncode == 0, _commit(),
            scope=(len(rows), held.get("corpus") or 0), by="impact")
    if done.returncode:
        why = next((ln for ln in reversed(done.stdout.splitlines())
                    if ln.startswith("#")), "no reason given")
        return [f"map top-up FAILED in {took:.0f}s, so the map still does not"
                f" hold these {len(rows)} row(s): {why.lstrip('# ')}"]
    # **The two halves are counted apart**, because they answer different
    # questions: the changed rows keep a new verb out of the fail-closed
    # branch, and the gap rows are what stop the whole map reporting itself
    # unusable. Calling both "changed" hid the second one entirely. #925.
    what = (f"{len(rows) - len(gap)} changed row(s) and {len(gap)} the map had"
            f" never measured" if gap else f"{len(rows)} changed row(s)")
    return [f"map topped up with {what} in {took:.0f}s,"
            f" so an edit to what they call narrows next run"]


def _merge_verdict(wide_run: bool, red: bool, mapped: list[str],
                   wide_why: str, no_opinion: bool = False,
                   audit_skipped: bool = False,
                   empty_scope: bool = False) -> list[str]:
    """Whether this branch may merge on what just ran, and on what grounds.

    **This is the line that decides whether the map is worth having.** The
    rule it replaces -- *"a worktree owes its own `check.py --all` before it
    merges"* (#848) -- made every merge pay a wide audit, so of 106 audit
    runs on this ledger **105 were wide and 1 was narrow**, and the map saved
    21 minutes against 22 hours spent sweeping. A selector that the gate
    ignores is a selector nobody uses.

    And the old rule rested on a net that was not there. It cited the
    nightly as the thing that would sweep master anyway -- and the
    schedule's own logs say 7 clean runs in 80 attempts, with 58 skipped
    on a dirty tree or a concurrent run. It is retired.

    What survives the retirement is the *reason*, which never depended on
    the schedule: a pre-merge wide run cost 22 minutes a merge to look at
    rows the map had already looked at. Where the map narrowed, something
    did look at them, and that is what the gate asks.

    So the question the gate asks is narrower and answerable: **has anything
    looked at the rows this change can affect?**

    * the map **narrowed** -- yes: the rows observed to execute the changed
      functions were audited, and they are green. Merge; a wide sweep is
      owed before the eventual push, by whoever pushes.
    * the map **refused** -- no. Nothing has looked at the rows, because
      "wide" means it could not say which they are. The wide sweep is owed
      before merge, exactly as before.
    * nothing under `engine/` changed -- `audit --changed` already covers
      content properly, which is the case this instrument has always had no
      opinion about.
    * the map narrowed to **nothing** -- `engine/` did change, every changed
      function was read, and every one is code no row has ever been observed
      to execute. Not a refusal and not an absence of opinion: an
      affirmative empty scope. `audit --changed` still widens on its own for
      an `engine/` change, so the rows were looked at anyway and the merge
      stands on that.

    Silent outside a worktree and silent on a red run: there is nothing to
    decide if the branch is the main checkout, and nothing to say about
    merging while an instrument is unhappy.
    """
    if not IN_WORKTREE or red:
        return []
    if wide_run:
        return ["merge-ready: a wide sweep just ran and is clean"]
    if no_opinion:
        # **Unless `audit --changed` checked nothing**, which is the whole
        # of #466 and would have made this line contradict the one above it
        # in the same output: `audit checked NOTHING` followed by
        # "`audit --changed` covered this branch's rows". It covered no
        # rows. On a clean tree there is nothing uncommitted for it to
        # cover, so the honest verdict names what actually certifies the
        # branch -- the last wide sweep.
        if audit_skipped:
            return ["merge-ready, but nothing audited this run: the scope was"
                    " empty, so this rests on the last wide sweep rather than"
                    " on anything that just ran."]
        return ["merge-ready: nothing under engine/ changed, so"
                " `audit --changed` covered this branch's rows."]
    if empty_scope:
        if audit_skipped:
            return ["wide sweep owed before merge: the map narrowed to no"
                    " rows AND the audit checked nothing, so nothing has"
                    " looked at this change at all."]
        return ["merge-ready: the map read every changed engine function and"
                " no row executes any of them -- an empty scope, not a"
                " refusal.",
                "             `audit --changed` widened on the engine change"
                " regardless, so the rows were audited and are clean."]
    if mapped:
        return [
            f"merge-ready: the map narrowed the audit to {len(mapped)} row(s)"
            f" -- the rows observed to execute what this change touched --"
            f" and they are clean.",
            "             a wide sweep is still owed before the push, by"
            " whoever pushes -- there is no overnight net.",
        ]
    return [
        "wide sweep owed before merge: the map could not narrow this change,"
        " so nothing has looked at the rows it can reach.",
        f"             {wide_why or 'no reason recorded'}",
    ]


def _record(name: str, seconds: float, ok: bool, at: str,
            scope: tuple[int, int] | None = None, by: str = "",
            wide_because: str = "") -> None:
    try:
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "when": datetime.now(tz=UTC).isoformat(timespec="seconds"),
            "name": name, "seconds": round(seconds, 2), "ok": ok, "commit": at,
            # **How many instruments were in flight**, because without it the
            # seconds stop being comparable across this change. A serial run
            # and a four-lane run measure different things -- the second
            # includes contention -- and `history`'s medians span both. 1 is
            # the old behaviour.
            "lanes": _LANES,
        }
        # **Only when the instrument said**, so a missing field means "this run
        # did not report its scope" and never "it covered nothing". `history`
        # counts the silent ones out loud rather than averaging over them.
        if scope:
            row["refs"], row["of"] = scope
        # **Which selector narrowed it**, because `refs < of` alone cannot
        # say. `--changed`, `--calls` and the impact map all produce narrow
        # audit runs, and "is the map earning its 87-minute recording" is
        # not answerable from a count that pools all three. Absent on a run
        # nothing narrowed, which is what a wide sweep is.
        if by:
            row["by"] = by
        # **Why a wide run was wide**, which `by`'s absence cannot say. The
        # map refuses for six distinguishable reasons -- a genuinely hot
        # function, a module-level change, an unmapped file, a moved corpus,
        # a union over the ceiling, an `audit.WIDE` member -- and "is the map
        # earning its recording" is a different question from "which of those
        # six is costing us". Counting wide runs told us the first and
        # nothing about the second, which is how a session spent an hour
        # inferring the causes from six commits by hand.
        if wide_because:
            row["wide_because"] = wide_because
        with LEDGER.open("a") as fh:
            fh.write(json.dumps(row) + "\n")
    except OSError:
        pass  # never let bookkeeping be the thing that fails a check run


def _commit() -> str:
    done = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          cwd=ROOT, capture_output=True, text=True)
    return done.stdout.strip() if done.returncode == 0 else ""


def _map_history(rows: list[dict]) -> None:
    """What the impact map has actually bought, against the wide sweep.

    **Measured, not modelled.** The saving is the median narrowed run's
    seconds against the median *wide* run's on the same ledger -- both real
    timings from this machine -- rather than a per-row cost multiplied out.
    A wide sweep is not N times a narrow one: the never-firing tail is 59%
    of it, so arithmetic from a row count would flatter the map.

    Silent until the map has narrowed something, because a line reading
    "0 runs" every run is the noise `--history` exists to avoid. The map's
    *existence* is reported by `_map_state` on every run regardless; this is
    only the ledger half.
    """
    audits = [r for r in rows if r["name"] == "audit" and r.get("of")]
    mapped = [r for r in audits if r.get("by") == "impact"]
    if not mapped:
        return
    wide = sorted(r["seconds"] for r in audits if r["refs"] >= r["of"])
    secs = sorted(r["seconds"] for r in mapped)
    refs = sorted(r["refs"] for r in mapped)
    med = secs[len(secs) // 2]
    corpus = mapped[-1]["of"]
    print(f"\n  the impact map narrowed {len(mapped)} audit run(s): "
          f"median {refs[len(refs) // 2]} of {corpus} rows, {med:.0f}s")
    if wide:
        full = wide[len(wide) // 2]
        print(f"  against a median wide sweep of {full:.0f}s -- "
              f"{full - med:.0f}s saved a run, {(full - med) * len(mapped):.0f}s "
              f"so far, {full / med:.0f}x" if med else "")
    else:
        print("  no wide sweep on this ledger to compare against yet")
    calls = [r for r in audits if r.get("by") == "calls"]
    if calls:
        print(f"  (`--calls` narrowed {len(calls)} more, which the map does "
              f"not account for)")

    # **Net the top-up off, because it is the price of the line above.**
    # Keeping the map fresh costs a few seconds on every clean commit, and
    # a saving reported gross is the kind of number that makes a mechanism
    # look better than it is -- which is the one thing `scripts/CLAUDE.md`
    # forbids outright. Also reports failures separately: a top-up that
    # quietly stopped working would otherwise show only as the map slowly
    # ceasing to narrow anything.
    tops = [r for r in rows if r["name"] == "map-topup"]
    if tops:
        paid = sum(r["seconds"] for r in tops)
        broke = [r for r in tops if not r["ok"]]
        print(f"  keeping it fresh cost {paid:.0f}s over {len(tops)} top-up(s)"
              f" ({paid / len(tops):.0f}s each, "
              f"{sum(r.get('refs', 0) for r in tops)} rows)"
              + (f" -- {len(broke)} FAILED" if broke else ""))

    # **The split and the reasons, which is the half that says what to fix.**
    # "The map narrowed 1 run" is a score; "104 went wide and here is which
    # cause each time" is a work queue. The six refusal reasons are not
    # equally addressable -- a genuinely hot function is correct and
    # permanent, `--all` is a choice, a module-level line is avoidable by
    # the author, an unmapped file means the map is stale -- so pooling them
    # hides the only actionable ones.
    went_wide = [r for r in audits if not r.get("by")]
    if went_wide:
        spent = sum(r["seconds"] for r in went_wide)
        saved = sum(r["seconds"] for r in mapped)
        print(f"\n  {len(went_wide)} audit run(s) went wide, {spent / 60:.0f} "
              f"minutes; {len(mapped)} narrowed, {saved / 60:.1f} minutes")
        why: dict[str, list[float]] = {}
        for r in went_wide:
            key = r.get("wide_because") or "(not recorded)"
            why.setdefault(key, []).append(r["seconds"])
        for key, took in sorted(why.items(), key=lambda kv: -sum(kv[1])):
            print(f"    {len(took):3} x {sum(took) / 60:5.0f} min  {key[:76]}")
        if "(not recorded)" in why:
            print("    -- `(not recorded)` predates this reporting; it is not"
                  " an unknown cause, only an unlogged one")


def history() -> int:
    if not LEDGER.exists():
        print("# nothing recorded yet -- run it a few times")
        return 0
    rows = [json.loads(line) for line in LEDGER.read_text().splitlines() if line.strip()]
    if not rows:
        print("# nothing recorded yet")
        return 0

    # **Split by how wide a run was, not by how long it took.** Answering
    # "is the wide sweep worth it" needed bucketing by duration, which is a
    # proxy for scope that breaks on a faster machine or a bigger corpus. The
    # answer was worth having -- wide sweeps were 36% of everything this suite
    # had cost, at 12x the per-catch price of a narrow run -- so the scope is
    # recorded now and this reads it. `audit.py` is the only instrument that
    # reports one; the rest fall through unsplit.
    by: dict[str, list[dict]] = {}
    quiet = 0
    for r in rows:
        name = r["name"]
        if r.get("of"):
            name = f"{name} {'wide' if r['refs'] >= r['of'] else 'narrow'}"
        elif r["name"] == "audit":
            quiet += 1
        by.setdefault(name, []).append(r)

    print(f"  {'instrument':13} {'runs':>5} {'median':>7} {'spent':>8} "
          f"{'caught':>7} {'per catch':>10}  last catch")
    order = sorted(by, key=lambda n: -sum(r["seconds"] for r in by[n]))
    for name in order:
        runs = by[name]
        secs = sorted(r["seconds"] for r in runs)
        spent = sum(secs)
        caught = [r for r in runs if not r["ok"]]
        per = f"{spent / len(caught):.0f}s" if caught else "never"
        last = caught[-1]["when"][:10] if caught else "--"
        print(f"  {name:13} {len(runs):5} {secs[len(secs) // 2]:6.1f}s "
              f"{spent:7.0f}s {len(caught):7} {per:>10}  {last}")

    _map_history(rows)

    total = sum(r["seconds"] for r in rows)
    caught = sum(1 for r in rows if not r["ok"])
    print(f"\n  {total:.0f}s spent over {len(rows)} instrument-runs, "
          f"{caught} of them caught something")
    # Named rather than folded into either half: a run from before the scope
    # was recorded is not a narrow run, and counting it as one would flatter
    # whichever side it landed on. They stay in the undecorated `audit` row.
    if quiet:
        print(f"  {quiet} audit run(s) predate the scope being recorded and are "
              f"counted in the plain `audit` row, not in wide or narrow")
    # Fruitless *and* expensive. An instrument that has never caught
    # anything but has cost fourteen seconds in total is not the one to cut,
    # and flagging it on catches alone invited exactly that mistake.
    idle = [
        n for n in order
        if all(r["ok"] for r in by[n])
        and len(by[n]) >= 20
        and sum(r["seconds"] for r in by[n]) >= 60
    ]
    if idle:
        print(f"  never caught anything in 20+ runs, and not cheap: {', '.join(idle)}"
              f"\n  -- worth asking whether they still earn their seconds")
    return 0


#: How much output to keep from a failing check that printed no matching
#: line and no traceback. The same depth `--verbose` uses, less a little,
#: because this is the fallback and not the thing somebody asked for.
_TAIL = 20


#: How much of a traceback to keep. Deep enough for the innermost frames,
#: which are the ones naming the row, and short enough that a check failing
#: on twenty of them does not bury the table above it.
_FRAMES = 14


def _traceback(text: str) -> list[str]:
    """Every traceback in an instrument's output, last `_FRAMES` lines each.

    Returned rather than printed so the caller decides where it goes, and
    kept **verbatim** -- a frame's indentation is what pairs a source line
    with the call above it, and stripping it makes a traceback unreadable
    in exactly the way that cost #634 a day.

    The tail and not the head: `audit.py` runs rows in a pool, so the
    outermost frames are the same `pool.map` bootstrap every time and the
    innermost are the ones that name the file being tokenized.
    """
    out: list[str] = []
    lines = text.splitlines()
    starts = [i for i, ln in enumerate(lines)
              if ln.lstrip().startswith("Traceback (most recent call last)")]
    for i, start in enumerate(starts):
        end = starts[i + 1] if i + 1 < len(starts) else len(lines)
        block = [ln for ln in lines[start:end] if ln.strip()]
        if len(block) > _FRAMES:
            # Say what was dropped rather than truncating silently, which is
            # the whole complaint #634 is about.
            block = [block[0], f"... {len(block) - _FRAMES} frame(s) above",
                     *block[-(_FRAMES - 2):]]
        out.extend(block)
    return out


def _summary(text: str) -> str:
    """The one line of an instrument's output worth putting in a table."""
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        return line[:80]
    return ""


#: Written while a run is in progress and removed on the way out, so one
#: run can tell "a sweep is running" from "a shell mentioned this file".
#: Written for `nightly.sh`, which is retired; kept because two concurrent
#: `check.py` runs still void each other, which is the hazard the root
#: `CLAUDE.md` describes at length. **It could not**, and that cost a
#: night's sweep: its guard was
#: `pgrep -f "scripts/check\.py"`, a substring match over every command
#: line on the machine, so a session that merely *grepped* for check.py
#: inside the nightly's window matched -- and on 2026-10-15 at 03:07 one
#: did, leaving `SKIPPED ... a check.py is already running` with nothing
#: running at all.
#:
#: A pid and `kill -0` instead of a pattern, which is the rule this repo
#: already learned from the other side: a `pgrep` waiter matched its own
#: command line and stranded three of them.
LOCK = ROOT / "logs" / "check.pid"


def _hold_lock() -> None:
    """Record this run's pid, and leave no lock behind on the way out."""
    import atexit
    import os

    LOCK.parent.mkdir(parents=True, exist_ok=True)
    LOCK.write_text(f"{os.getpid()}\n")

    def release() -> None:
        # Only our own: a crash elsewhere must not let this run delete a
        # live sweep's lock.
        if LOCK.exists() and LOCK.read_text().strip() == str(os.getpid()):
            LOCK.unlink()

    atexit.register(release)


if __name__ == "__main__":
    _hold_lock()
    raise SystemExit(main())
