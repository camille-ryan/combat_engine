#!/usr/bin/env python
"""How well is the AI playing? Counted per side, against a committed baseline.

    uv run scripts/scorecard.py              measure and compare to the baseline
    uv run scripts/scorecard.py --save       write the baseline (after a fix)
    uv run scripts/scorecard.py --level 5    one level only

**This replaces the win-rate A/B as the gate on a policy change**, because Camille's
objection to that comparison is correct and fatal: *both sides run the same policy*,
so an improvement that helps the party helps the monsters equally and largely cancels
in the win rate. Measured twice, on two fresh sets of 80 seeds, the policy came out
ahead at both levels and **neither gap survived Holm** -- while the thing those fixes
actually targeted moved 304 to 174. Forty-five minutes a run to measure the weakest
signal available is the wrong trade.

So this counts tactical quality directly, and **separately for each side**, so a
symmetric gain shows up instead of cancelling. Every figure rests on hundreds or
thousands of events across a dozen fights rather than one outcome each, which is why
twelve seeds is enough and why it runs in about a minute.

What is counted, and what each is for:

* **oa_conceded** -- opportunity attacks handed to the other side. The measure that
  replicated across both long runs, and free damage given away.
* **inert_chosen** -- a chosen row that lays no effect, deals no damage and declares
  no attack. It cannot have accomplished anything. #264.
* **self_harm** / **already_on** -- caught in your own blast; re-casting a buff that
  is already running.
* **tied** -- decisions where the top score was a tie, so the choice fell to
  `str(action)`. 14.8% when first measured.
* **charge_taken / charge_offered** -- #265's and #293's acceptance test. A melee
  creature should charge often and a wizard never. **Two reports**: the baselined
  pair is per *side*, and `--roles` prints the per-role breakdown the acceptance
  test actually asks for. This bullet said "by role" while the counter was keyed
  on side alone, which is why the test went unrun -- see `act`.
* **idle_melee** -- a melee creature out of reach that did not close. **The approach
  guard**: the fix for #265 changes what rewards closing, and this is what catches it
  going wrong.
* **adjacent_idle** -- standing next to an enemy and not attacking. Split out of
  `idle_melee`, which conflated the two: a sample found 16 of 25 "idle" turns were
  this, at gap 1, with no charge even offered. A different bug, and it was hiding.
* **could_not_act** -- turns excluded from the two idle counters because nothing but
  `end` was on offer. **Printed rather than dropped**, because this is what says the
  exclusion is the right size: the counters above used to include these, and at level
  10 that was 20 of 24 `adjacent_idle` turns and 5 of 10 `idle_melee` -- unconscious
  and dying creatures, measured as though they had chosen badly. Derived from what was
  offered and not from a condition list: 3 of 23 such turns carried no condition at
  all.
* **rounds** -- the balance guard only, against #217's 7-8.

The baseline lives in `scripts/fixtures/scorecard.json` and is committed, which is
what makes a lost comparison survivable: "did this fix help" is answered against the
previous commit's numbers. **It has to be kept honest.** Re-save it only when the
change is understood and intended, the same discipline `replay.py record` needs, and
say in the commit which way each number moved.

**The baseline records the commit it was taken at** and this prints how far behind HEAD
it is. Without that, a baseline two commits stale reads exactly like a commit that
changed nothing -- which happened: 915ed93 moved three numbers and the next change
measured was nearly blamed for all of them. See #270.

Not a pass/fail check. It prints what the AI did.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import fight
from combat_engine.engine import Encounter, Ident, World
from combat_engine.engine.components import (
    Budget,
    Build,
    Health,
    Position,
    Powers,
    Side,
)
from combat_engine.engine.dsl import get
from combat_engine.engine.events import (
    DamageApplied,
    Dropped,
    Healed,
    Hit,
    OpportunityWindow,
    SurgeSpent,
)
from combat_engine.engine.grid import distance
from combat_engine.engine.query import alive, enemies
from combat_engine.engine.types import Usage
from combat_engine.policy import doctrine as D
from combat_engine.policy import install, take_turn
from combat_engine.policy import threat as T

BASELINE = Path(__file__).resolve().parent / "fixtures" / "scorecard.json"

#: Terms whose value is a measured quantity rather than a number somebody picked.
#: #314.
#:
#: **Declared, because a weight cannot be asked where its value came from.** This was
#: `abs(abs(w) - SHARE) < 1e-9`, which is a float comparison against one module
#: constant, and it got three things wrong at once: `shoved_from_prey` is a measured
#: signed quantity priced in `WEIGHTS` and so could never qualify; any measured term
#: given a weight other than `SHARE` was filed as a constant; and a constant that
#: happened to equal 15.0 was filed as measured.
#:
#: It then broke outright. `hp_swing` is measured in hit points and weighted **1.0**
#: -- the feature is already the answer -- so the old test called it static and
#: `static_pct` reported **95.9%** on a run where the measured share was **64.9%**.
#: The one number in the repo that watches this balance was reporting the opposite of
#: the truth, which is the fault it exists to catch.
DERIVED = frozenset({
    "hp_swing",
    # Measured: the row's own worth times `losing()` times how much of the day is left.
    # Omitted when it was added, so `static_pct` read 47.9% on a run whose measured
    # share was really near 40 -- the same misclassification this set was rewritten to
    # stop, committed by the person who rewrote it.
    "reserve_cost",
    "threat_conceded",
    "ca_conceded",
    "reach_gained",
    "healing_given",
    "shoved_from_prey",
})

#: Fixed so two runs are comparable.
#:
#: **Twenty-four, not twelve, and the round count is why.** Twelve is plenty for the
#: event counts -- those are tallies over thousands of decisions -- but the headline
#: is a median over 12 fights of 4 to 19 rounds, and that moves on its own. Measured
#: over 96 level-10 fights (true median 9.0, mean 9.33), as the spread between
#: disjoint blocks of n:
#:
#:      n      median spread   mean spread
#:     12          2.0            3.00
#:     16          2.5            3.00
#:     24          1.0            1.08
#:     32          1.0            0.72
#:     48          1.0            0.42
#:
#: At twelve the median wanders **two rounds** with nothing changed, which is larger
#: than most effects anyone measures here -- and it twice gave a wrong answer in one
#: session (#291). Twenty-four halves that, and is where the mean stops being worse
#: than the median: below it the mean is dragged by the 19-round tail, above it the
#: mean keeps tightening while the median sits on the floor its granularity imposes.
#:
#: So **24 and both statistics**, and the honest reading of the pair is that an
#: effect under a round is not visible at this sample size whatever the median says.
#: Going further costs linearly and buys only the mean; 48 would be the next step if
#: a sub-half-round effect ever has to be settled.
SEEDS = tuple(range(301, 325))
LEVELS = (5, 10)


def _git(*args: str) -> str:
    """A git reading, or "" when there is no git to read."""
    try:
        out = subprocess.run(("git", *args), capture_output=True, text=True,
                             cwd=Path(__file__).resolve().parent.parent, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.stdout.strip() if out.returncode == 0 else ""


def staleness(_was: dict | None = None) -> str:
    """How far behind the baseline is, read off git rather than a stored field. #270.

    **A baseline older than HEAD reads exactly like a commit that changed nothing**,
    and that is not hypothetical: the baseline sat two commits behind while 915ed93
    moved three numbers -- inert rows 181 -> 213, a live buff re-cast 18 -> 42, charges
    taken 21 -> 14 -- and the next change measured was nearly blamed for all of it.
    Nothing in the output said so.

    **Derived, because the stored field was wrong by one and always would be.** `--save`
    runs *before* the change it measures is committed, so stamping `HEAD` recorded the
    commit the measurement was based on rather than the one containing it -- and the
    warning then fired on the very next commit, every time. A guard that cries wolf
    teaches people to ignore it, which is the failure it exists to prevent.

    So: the commit that last changed the baseline **file**, and a count of the commits
    since that touched code the measurement depends on. `scripts/fixtures/` is excluded
    from that count deliberately -- a re-recorded replay fixture moves no number here.
    Nothing to keep in sync, and it reads 0 exactly when the convention is followed
    (re-save the baseline in the same commit as the change).
    """
    born = _git("log", "-1", "--format=%H", "--", str(BASELINE))
    if not born:
        return ""
    n = _git("rev-list", "--count", f"{born}..HEAD", "--",
             "src/combat_engine", "scripts/*.py")
    if not n or n == "0":
        return ""
    return (f"  baseline is {n} commit{'s' if n != '1' else ''} behind, taken at "
            f"{born[:9]} -- a number that moved may not be this change's doing")


def side_of(world, eid: int) -> str:  # noqa: ANN001
    ident = world.get(eid, Ident)
    return "monsters" if (ident and ident.ref.startswith("m")) else "party"


#: The policy's own test, so the instrument and the scorer cannot disagree about
#: what "inert" means.
inert = D.inert


class Counted(D.DoctrinePolicy):
    """The policy, with every decision tallied by side."""

    def __init__(self) -> None:
        super().__init__()
        self.n: Counter = Counter()
        self.ties: dict[str, list[int]] = {"party": [], "monsters": []}
        #: `(actor, round)` -> was anything but `end` available on the **first**
        #: decision of that turn. Keyed rather than kept as one flag because an
        #: immediate interrupt calls `act` for a creature whose turn it is not,
        #: which would clobber a single slot.
        self.could: dict[tuple[int, int], bool] = {}
        #: `(actor, round)` for a turn where the creature did something that was
        #: not an attack and was not inert -- a buff, a heal, a zone. Cleared per
        #: fight for the same reason `could` is: entity ids and round numbers both
        #: restart, so a surviving key answers the wrong fight's question.
        self.helped: set[tuple[int, int]] = set()

    def act(self, world, encounter, actor, options):  # noqa: ANN001, ANN201
        side = side_of(world, actor)
        self.could.setdefault(
            (actor, world.round),
            any(o.available and o.kind != "end" for o in options),
        )
        scored = sorted(((self.score(world, encounter, actor, a), a)
                         for a in options if a.available), key=lambda t: -t[0])
        self.n[f"{side}/decisions"] += 1
        if scored:
            best = scored[0][0]
            tied = sum(1 for s, _ in scored if abs(s - best) < 1e-9)
            self.ties[side].append(tied)
            if tied > 1:
                self.n[f"{side}/tied"] += 1
        # **By role as well as by side, because the docstring has claimed
        # "by role" for as long as the counter has been keyed on side
        # alone.** `#293`'s acceptance test -- *"a melee-only skirmisher's
        # charge take rate should rise toward the brute's, and the wizard
        # should keep charging zero times"* -- is the stated guard on seven
        # open issues and could not be read off this instrument at all. The
        # word "role" appeared exactly once in this file and it was in the
        # docstring saying the opposite.
        #
        # `Ident.role` carries it for **both** sides: a monster gets its
        # printed role (`brute`, `skirmisher`, `artillery`) and a character
        # gets its 4e one (`defender`, `striker`, `controller`, `leader`),
        # so one field answers for the whole board and nothing had to be
        # taught about classes.
        #
        # **Kept out of the baselined figures deliberately.** These are
        # printed as their own block rather than added to the 52 compared
        # against `scorecard.json`: a new baselined figure changes the
        # file's shape and forces a re-bless, and a re-bless is how 310
        # entries were once lost. The acceptance test wants to be *read*,
        # not gated.
        ident = world.get(actor, Ident)
        role = (ident.role if ident and ident.role else "none")
        if any(a.kind == "charge" for a in options if a.available):
            self.n[f"{side}/charge_offered"] += 1
            self.n[f"{side}/charge_offered/{role}"] += 1
        got = super().act(world, encounter, actor, options)
        if got.kind == "charge":
            self.n[f"{side}/charge_taken"] += 1
            self.n[f"{side}/charge_taken/{role}"] += 1
        if got.kind == "end":
            # **Passed the turn with a standard action still in hand.** The guard on
            # Camille's rule that `end` is the floor: once it sits at +0.001 instead
            # of -2.0, anything the scorer cannot value scores 0 and *loses* to
            # passing -- so the failure mode inverts. It used to be that an unnamed
            # action kind became the idle default; now an unvalued one disappears,
            # and the creature forfeits the rest of its turn with it.
            #
            # Measured at the moment it chose to pass rather than from `could`,
            # which `setdefault`s on the turn's *first* decision and so answers a
            # different question: a creature that attacked and then passed with a
            # standard left is the case this has to catch.
            #
            # Excludes a turn where nothing but `end` was on offer, for the reason
            # `could_not_act` exists -- that measures the board, not the policy.
            budget = world.get(actor, Budget)
            if budget is not None and budget.standard > 0 \
                    and any(o.available and o.kind != "end" for o in options):
                self.n[f"{side}/passed_holding_standard"] += 1
        if got.ref:
            spent = get(got.ref)
            if spent is not None and spent.usage is Usage.DAILY:
                self.n[f"{side}/dailies"] += 1
        if got.kind == "action_point":
            self.n[f"{side}/ap_spent"] += 1
            # Which extra action it bought. A standard is worth most by a wide
            # margin, so this reading says whether the choice is evaluated or a
            # tie-break: `Action.ref` carries the granted type. #266.
            self.n[f"{side}/ap_standard"] += int(got.ref == "standard")
        if got.ref and inert(world, actor, got.ref):
            self.n[f"{side}/inert_chosen"] += 1
        elif got.kind != "end":
            # **A turn can be useful without being an attack**, and
            # `adjacent_idle` could not say so. A cleric standing next to an
            # enemy and buffing the whole party is not wasting its turn, but
            # "did not attack" is literally true of it -- so the one counter was
            # reading six productive leader turns as idle ones. Recorded per
            # (actor, round) and read below, the way `could` already is. #268.
            #
            # **The test is "not inert and not `end`", not "has a ref and
            # targets."** The first spelling missed every action that carries no
            # ref -- a second wind, a total defence, an escape -- and #284's
            # widened second-wind window walked straight into it: eleven turns
            # where a bloodied character healed itself read as having done
            # nothing. Healing is not nothing. The `elif` is what keeps an inert
            # row out, since that branch is above.
            self.helped.add((actor, world.round))
        p = get(got.ref) if got.ref else None
        if p is not None and got.targets and (
                p.attack is not None
                # **Or it deals damage without rolling.** The test was the header
                # alone, so a row that damages from its body was invisible --
                # `p11618` deals 21 and has no `Attack` line, and an estimated
                # **179 rows** of the 6,947 without one do deal damage. Every such
                # turn read as having attacked nobody, and five readings are
                # derived from this tally. #300.
                #
                # A row property rather than an event, deliberately: counting
                # `DamageApplied` instead took the tally from 282 to 497 at level
                # 5, because ongoing damage emits one every round and credits the
                # creature that applied it for a turn it spent doing nothing. The
                # same figure `doctrine.inert` already asks for, so it is cached.
                or T.row_damage(world, actor, got.ref) > 0):
            self.n[f"{side}/attacks"] += 1
        # **How much of this decision was a measured quantity and how much was a
        # constant somebody picked.** #314's meter: the recalibration it proposes
        # needs a number to move, and there was none. Read off `weighed`, not
        # `explain`, because `explain` promises the doctrine half only.
        raw_all = self.weighed(world, encounter, actor, got)
        for k, v in raw_all.items():
            w = abs(self.weights.get(k, 0.0) * v)
            if not w:
                continue
            kind = "derived_mag" if k in DERIVED else "static_mag"
            # Hundredths, kept as an integer: `Counter` is integer-valued and a
            # fraction of a point either way does not change a percentage.
            self.n[f"{side}/{kind}"] += round(w * 100)
            # **And the same magnitude per term, for `--terms`.** The aggregate
            # above answers "how much is static"; it cannot answer "is the
            # measured half one big term or many", and those call for different
            # recalibrations. #314 measured a *new* derived term at 0.58 against
            # a decision needing ~7, while the aggregate derived share is over
            # half -- both can hold only if the derived magnitude is
            # concentrated, and nothing reported which term.
            #
            # Keyed under `mag/` so it cannot collide with a counter name, and
            # **not** added to `cell` or `ROWS`: the report prints `ROWS` and
            # the baseline stores `cell`, so these keys are invisible to both
            # and `scorecard.json` keeps its shape.
            self.n[f"{side}/mag/{k}"] += round(w * 100)
        d = self.explain(world, encounter, actor, got)
        if d.get("self_harm"):
            self.n[f"{side}/self_harm"] += 1
        if d.get("already_on"):
            self.n[f"{side}/already_on"] += 1
        # **The number #266 was filed on, which had never been counted.** That
        # issue is "a monster repeatedly bursts its own ally" and there was no
        # line here for it -- `self_harm` covers catching *yourself* and nothing
        # covered catching a friend, so the behaviour the issue describes could
        # only be seen by reading a fight log.
        #
        # Read off `allies_caught`, so it is the same figure the scorer acted on
        # rather than a second opinion that can disagree with it. Counted in
        # bodies, not in decisions: clipping three allies with one blast is three
        # times the mistake and a per-decision tally would call it one.
        #
        # **`weighed`, not `explain`**, and the difference is the whole metric.
        # `explain` filters to `DOCTRINE` -- it says so -- and `allies_caught`
        # lives in `policy.features`' table, not that one. Read through `explain`
        # this counter was zero at both levels and stayed zero with the -7.0
        # deterrent set to 0.0, which is how the fault was found: a metric that
        # cannot move when the thing it watches is unleashed is not measuring it.
        raw = self.weighed(world, encounter, actor, got)
        if raw.get("allies_caught"):
            self.n[f"{side}/allies_clipped"] += int(raw["allies_caught"])
            self.n[f"{side}/ally_blasts"] += 1
        return got



def _could_be_saved(world, who: int) -> bool:  # noqa: ANN001
    """Does a living ally hold an unspent row that could heal this creature?

    The third counter `#324` asks for, and that issue parks it saying the
    predicate *"nothing carries"*. Nothing carries it as one thing; both
    halves are live and compose:

    * `doctrine.heals(ref)` -- does this row put hit points back. It reads
      the body for `c.heal`, `c.surge` and `c.temp_hp`, cached per ref.
    * the row's own target **side** -- does it reach anybody but its
      caster. A `target=SELF` heal cannot answer a dying ally.

    Plus `Powers.times(ref) == 0` for *unspent*, which is the same question
    `_held_a_second_wind` asks one row narrower.

    **This under-reports, deliberately, and `_heal_reach_unreadable` says
    by how much.** Of the 586 character-holdable healing rows, 333 are
    self-only, 114 reach somebody else and **139 have no readable side** --
    so a third of the family cannot be classified from the header. Counting
    only the 114 is the safe direction for a counter whose job is to find a
    **refusal**: it can say "the AI declined a save it had" and be right,
    where guessing the 139 either way could invent one. A number that
    silently omitted a third of its population would be the shape this
    repo's notes warn about, so the omission is reported beside it.

    Asked of **living** allies only. A heal held by somebody who is also
    down is not an answer anybody declined.
    """
    from combat_engine.policy.doctrine import heals

    me = world.get(who, Side)
    if me is None:
        return False
    for other, side in world.each(Side):
        if other == who or side.team != me.team or not alive(world, other):
            continue
        known = world.get(other, Powers)
        if known is None:
            continue
        for ref in known.known:
            if not heals(ref):
                continue
            row = get(ref)
            target = getattr(row, "target", None) if row is not None else None
            if getattr(target, "side", None) in ("self", None):
                continue
            if known.times(ref) == 0:
                return True
    return False


def _held_a_second_wind(world, who: int) -> bool:  # noqa: ANN001
    """Could this creature still have taken a second wind as it dropped?

    **`actions.offers`' own three conditions, not a tally of `SecondWind`
    events.** Counting events answers "did it spend one", which is a different
    question in two ways that both matter here: a character out of surges never
    had the option, and a **monster never has it at all** -- monsters carry
    surges so that leader rows can spend them. Read off events, every one of the
    96 monster drops at both levels counted as "holding a second wind it never
    had", and the monsters column was identical to the drop count by
    construction.

    Read at the moment of the drop, which is the moment the question is about.
    `encounter.can_spend` is deliberately not asked: it answers False whenever it
    is not that creature's turn, and a creature is usually dropped on somebody
    else's.
    """
    health = world.get(who, Health)
    known = world.get(who, Powers)
    return (
        world.get(who, Build) is not None
        and health is not None
        and health.surges > 0
        and known is not None
        and known.times("second-wind") == 0
    )


def turn_watch(world, pol: Counted, actor: int) -> None:  # noqa: ANN001
    """After a turn: did a melee creature neither attack nor close?"""
    side = side_of(world, actor)
    if not D.fights_in_melee(world, actor):
        return
    pol.n[f"{side}/melee_turns"] += 1


def play(
    level: int, seed: int, pol: Counted, cap: int = 30,
    *, built: tuple[World, Encounter] | None = None,
) -> tuple[int, bool]:
    """Play one seeded fight. `(rounds, finished)`.

    **`finished` exists because a stall used to read as a long fight.** The
    loop below stops on `encounter.finished` *or* on the cap, and the
    return was `world.round` either way -- so a fight nobody won came back
    as `cap + 1` and the summary could not tell it from a resolved fight
    that happened to run that long.

    What that cost, measured on `#473`'s own seed: one level-5 fight ending
    with an untouched fighter and a 23-of-252 monster standing moved the
    level-5 line from `range 4-15` to `4-31` and the mean from 7.08 to
    10.25. **One unresolved fight in twenty-four moved the headline by
    three rounds**, which makes every level-5 comparison unreadable until
    somebody notices.

    Same shape as the lesson `browser.py` learned the hard way and
    `scripts/CLAUDE.md` records: a count of passes says nothing about how
    many questions were asked, so the total has to reconcile. `measure`
    medians the resolved fights and reports the stalls separately rather
    than dropping them -- a silently excluded fight would be the same bug
    pointed the other way. #473.
    """
    # **`built` is how `day()` reuses this whole body for fight two of
    # four.** With it `None` -- every caller before `#305` -- this is the
    # original `fight.build` line and nothing about a single fight moves,
    # which is deliberate: the committed baseline is a single-fight
    # measurement and a day mode must not silently re-price it.
    world, encounter = built if built is not None else fight.build(
        seed, level, "full")
    T.clear()
    D.forget()
    # Per-fight, unlike every tally on `pol`: entity ids and round numbers both
    # restart each fight, so a surviving `(actor, round)` key answers the wrong
    # fight's question. Left in, this reported 7 excluded turns where there are 25.
    pol.could.clear()
    pol.helped.clear()
    install(world, encounter, {}, default=pol)

    def provoked(ev: OpportunityWindow) -> None:
        pol.n[f"{side_of(world, ev.provoker)}/oa_conceded"] += 1

    world.bus.on(OpportunityWindow, provoked)

    # **Camille's reading: damage provoked beats a count of provocations.**
    # Walking past a minion and walking past a brute are the same number and
    # not the same mistake, so `oa_conceded` prices a correct risk and a
    # reckless one identically. This is the hit points it actually cost.
    #
    # Latched rather than read off `DamageApplied` directly, because the flag
    # lives on the *attack*: `resolve` hangs `opportunity` on the `Hit` as a
    # plain attribute -- the same road `charge` and `as_` ride -- and the
    # damage event that follows carries only source, target and amount. One
    # slot keyed on the pair, set by the hit and spent by the blow.
    oa_hit: set[tuple[int, int]] = set()

    def swung(ev) -> None:  # noqa: ANN001
        if getattr(ev, "opportunity", False):
            oa_hit.add((ev.attacker, ev.target))

    def hurt(ev) -> None:  # noqa: ANN001
        pair = (ev.source, ev.target)
        if pair in oa_hit:
            oa_hit.discard(pair)
            # Charged to the creature that **provoked** it, which is the one
            # that chose: the victim is the side that walked, not the side that
            # swung.
            pol.n[f"{side_of(world, ev.target)}/oa_damage"] += ev.amount
        # **Self-damage, per side.** A burst that catches your own fighter is
        # the cost #266 is about, and the ally-clipping counters above say how
        # often rather than how much. Excludes a creature damaging itself --
        # that is `self_harm`, priced against its own hit points.
        if ev.source != ev.target:
            mine = world.get(ev.source, Side)
            theirs = world.get(ev.target, Side)
            if mine is not None and theirs is not None and mine.team is theirs.team:
                pol.n[f"{side_of(world, ev.source)}/self_damage"] += ev.amount

    world.bus.on(Hit, swung)
    world.bus.on(DamageApplied, hurt)

    # **Attrition, which is what 4e actually spends.** Camille's call on #267: a
    # party beating a standard encounter from full resources is the *intended*
    # outcome, so a win rate is measuring the wrong thing. What a fight costs is
    # surges, dailies and action points -- the three things that do not come back
    # until a rest -- and a party that wins four fights in a day without anyone
    # dropping is the real target.
    def surged(ev) -> None:  # noqa: ANN001
        pol.n[f"{side_of(world, ev.actor)}/surges"] += 1

    world.bus.on(SurgeSpent, surged)

    # **Camille's reading on #303: going down with a second wind still in hand.**
    # A character who has already spent one and drops has run out of answers,
    # which is the fight being hard. One who drops still holding it was never
    # offered the choice or declined it, and that is the AI to improve -- so the
    # two have to be counted apart or the signal is buried in the total.
    def went_down(ev) -> None:  # noqa: ANN001
        side = side_of(world, ev.actor)
        pol.n[f"{side}/downed"] += 1
        if _held_a_second_wind(world, ev.actor):
            pol.n[f"{side}/downed_holding_wind"] += 1
        # **The half that measures the REFUSAL**, which `#324` calls the
        # worse fault: not a heal wasted but a heal the party held and did
        # not spend on somebody dying. Counted at the drop, which is the
        # moment the question is about -- the same reason
        # `_held_a_second_wind` reads the state then rather than tallying
        # events afterwards.
        if _could_be_saved(world, ev.actor):
            pol.n[f"{side}/downed_with_a_heal_in_the_party"] += 1

    world.bus.on(Dropped, went_down)
    encounter.start()
    while not encounter.finished and world.round <= cap:
        actor = world.turn
        if actor is None:
            break
        before = world.get(actor, Position)
        was = before.square if before else None
        gap = min((distance(was, q.square) for e in enemies(world, actor)
                   if alive(world, e) and (q := world.get(e, Position)) is not None),
                  default=99) if was else 99
        hits = pol.n[f"{side_of(world, actor)}/attacks"]
        began = world.round
        take_turn(world, encounter, actor, pol)
        turn_watch(world, pol, actor)
        after = world.get(actor, Position)
        now = min((distance(after.square, q.square) for e in enemies(world, actor)
                   if alive(world, e) and (q := world.get(e, Position)) is not None),
                  default=99) if after else 99
        # **Two different failures, and one counter could not tell them apart.**
        # "Neither attacked nor closed" lumped a creature that stalled out of reach
        # together with one standing next to an enemy and not swinging -- and a
        # sample showed 16 of 25 were the second kind, at gap 1, with no charge even
        # offered. The first is an approach problem and the guard this was built to
        # be; the second is a creature with nothing it can use, which is a different
        # bug and was hiding inside the same number.
        # **A turn with nothing but `end` on offer cannot demonstrate a bad
        # choice**, so counting it as an idle turn measures the board rather than
        # the policy. It was measuring mostly corpses: of 24 `adjacent_idle` turns
        # at level 10, **20 were unconscious or dying creatures** with exactly one
        # legal option, and 5 of 10 `idle_melee` the same. Three of the 23 carried
        # no condition at all and still had one option, which is why the test is
        # "what was offered" and not a list of conditions -- the same reason
        # `threat.from_rules` derives from the rules instead of a hand-set table.
        # Counted out loud below, because an instrument that quietly drops turns
        # is the failure this directory's rules forbid.
        if D.fights_in_melee(world, actor) \
                and pol.n[f"{side_of(world, actor)}/attacks"] == hits:
            if not pol.could.get((actor, began), True):
                pol.n[f"{side_of(world, actor)}/could_not_act"] += 1
            elif gap <= 1 and (actor, began) in pol.helped:
                # **Not an attack is not the same as not useful.** A cleric beside
                # an enemy buffing or healing the whole party has not attacked and
                # has not wasted the turn, and one counter could not tell the two
                # apart -- so six productive leader turns were reading as idle. Split
                # rather than excused, because a number that quietly stops counting
                # things is the failure this file's own history is made of: the same
                # split gave `could_not_act` its own line when `adjacent_idle` turned
                # out to be mostly corpses. #268.
                pol.n[f"{side_of(world, actor)}/adjacent_helped"] += 1
            elif gap <= 1:
                pol.n[f"{side_of(world, actor)}/adjacent_idle"] += 1
            elif now >= gap:
                pol.n[f"{side_of(world, actor)}/idle_melee"] += 1
        encounter.advance()
    _count_healing(world, pol)
    return world.round, encounter.finished


def _count_healing(world: World, pol: Counted) -> None:
    """How much the healing actually restored, read off the log afterwards.

    **Off `world.bus.log`, and never from a `bus.on(Healed, ...)` listener.**
    `Healed` is a `Decision` -- a proposal -- so `resolve.heal` announces it,
    lets a row refuse or halve it, and only *then* assigns the real figures
    back onto the event:

        offered.amount = health.hp - before
        offered.hp = health.hp

    So a listener reads what was **offered** and the log reads what actually
    **happened**, and the two differ by exactly the quantity this counter
    exists to find. Measured on a target at full hit points:

        target 61/61, heal for 10
          a bus.on(Healed) listener saw   amount=10  hp=61
          the LOGGED event says           amount= 0  hp=61

    A subscribed counter would therefore report ten hit points restored for
    a heal that restored nothing -- blind to the waste, and reporting the
    party's healing as efficient in exactly the fights where it is not.
    #324, and the scorecard's other counters (`surged`, `went_down`) all
    subscribe, so subscribing is the natural thing to write here and is the
    wrong one.

    `restored` is in hit points and pairs with the existing `surges` count:
    a surge spent is only worth what it put back. `wasted_heals` counts the
    heals aimed at somebody who did not need one -- **above half** hit
    points, which is the band the printed second-wind rule itself treats as
    healthy -- and is the discriminating number, because a heal for 0 and a
    heal for 6 on a nearly-full ally are the same mistake made twice.

    Pre-heal hit points are `hp - amount`, which needs care at one edge and
    is asserted in `drivers.healing_waste`: healing from below zero starts
    at **zero**, not at the deficit, so a character revived from -5 reads a
    pre-heal of 0 and is correctly not counted as wasteful.
    """
    for ev in world.bus.log:
        if not isinstance(ev, Healed) or ev.cancelled:
            continue
        side = side_of(world, ev.target)
        pol.n[f"{side}/restored"] += ev.amount
        hurt = world.get(ev.target, Health)
        if hurt is None:
            continue
        before = ev.hp - ev.amount
        if before * 2 > hurt.max_hp:
            pol.n[f"{side}/wasted_heals"] += 1
            pol.n[f"{side}/wasted_hp"] += ev.amount


def day(
    level: int, seed: int, pol: Counted, cap: int = 30, fights: int = 1,
) -> tuple[list[int], int]:
    """Play `fights` encounters with **one party carried between them**.

    `([rounds per fight], how many stalled)`.

    **This is `#305`'s own remaining half.** Every figure this instrument
    has ever printed is "fight one of a notional four": `play` builds a
    fresh party per seed, nothing sets `world.fights_left`, and
    `doctrine.reserved` therefore prices every daily against the `DAY`
    default. Its docstring says so -- *"the day factor only bites when
    something sets `fights_left`, which today is `fight.py --fights`
    alone"* -- and nothing measured that. So the across-day behaviour the
    reservation was built for has shipped unverified.

    The two things only a day loop knows, both copied from
    `fight.py`'s loop rather than re-derived:

    * **`world.fights_left`**, counting this fight -- a daily spent in the
      first of four has three fights to regret it in and one spent in the
      last has none;
    * **`world.milestones`**, every two completed encounters, set *before*
      `encounter.start()` so a trait reading it at arming gets the right
      number. `api/day.py` does the same and for the same reason.

    `story.harvest` carries the sheets out of each `World` and
    `Party.rest()` takes the short rest between, which is why this is
    plumbing rather than new mechanics.

    **`fights=1` does not come through here at all.** `measure` calls
    `play` directly in that case, so the committed baseline -- a
    single-fight measurement -- is produced by byte-identical code. A day
    mode that silently re-priced the default would make every `(was ...)`
    figure incomparable, which is the opposite of the point.
    """
    # Function-local: `story` is only reached by the day path, and a
    # module-level import would pull the story engine into every
    # single-fight run that does not use it.
    from combat_engine import story

    party = story.Party.of(story.PARTY, level, seed=seed)
    rounds: list[int] = []
    stalls = 0
    for n in range(1, fights + 1):
        fielded = story.field_encounter(seed + n, level, scaling="full",
                                        party=party)
        if not fielded.enemies:
            break
        world = fielded.world
        # **Bare attributes on `World`, which is the pattern here rather
        # than a shortcut**, and `ty` cannot see a field nothing declares.
        # `fight.py` sets these same three the same way and carries the
        # same diagnostics in the `types` baseline; `resolve` hangs
        # `opportunity` on a `Hit` likewise, which `engine/`'s note calls
        # "the same road `charge` and `as_` ride".
        #
        # Ignored per line rather than blessed into the baseline: an
        # inline ignore says which write and why, where a baseline entry
        # is a count somebody later has to go and look up. #305.
        world.paradigm = fielded.paradigm  # ty: ignore[unresolved-attribute]
        encounter = Encounter(world)
        world.fights_left = fights - n + 1  # ty: ignore[unresolved-attribute]
        world.milestones = (n - 1) // 2  # ty: ignore[unresolved-attribute]
        # `play` installs `pol` itself and clears `T`/`D` per fight, which
        # is the per-fight state `fight.py` gets by building a fresh
        # policy -- so there is nothing extra to reset here.
        went, done = play(level, seed, pol, cap, built=(world, encounter))
        rounds.append(went)
        stalls += 0 if done else 1
        story.harvest(world, party)
        if n < fights:
            party.rest()
    return rounds, stalls


def measure(levels: tuple[int, ...], fights: int = 1,
            *, terms: dict | None = None,
            roles: dict | None = None) -> dict:
    """Play the seeds and count. `terms`, if given, is filled per level/side
    with each weighted term's magnitude in hundredths -- #314's per-term
    decomposition.

    An out-parameter rather than a second return value or a `cell` key,
    deliberately: `cell` is what `--save` writes, so putting it there would
    change `scorecard.json`'s shape and make every stored baseline
    un-comparable for a number nothing gates on.
    """
    out: dict = {}
    for level in levels:
        pol = Counted()
        rounds = []
        stalled: list[int] = []
        for seed in SEEDS:
            # Counting attacks needs a hook; the policy records them itself below.
            #
            # **`fights == 1` takes the original call**, not `day(...,
            # fights=1)`, so the committed baseline keeps being produced by
            # the code that produced it. `day` builds its party through
            # `story.Party.of` and seeds encounters at `seed + n`, which is
            # not the same draw as `fight.build(seed, ...)` -- routing the
            # default through it would move every figure in the file for no
            # reason anybody asked for. #305.
            if fights == 1:
                went, done = play(level, seed, pol)
                if done:
                    rounds.append(went)
                else:
                    stalled.append(seed)
                continue
            went_each, stalls = day(level, seed, pol, fights=fights)
            rounds.extend(went_each)
            # One seed is one **day**, so a day with any unresolved fight in
            # it is named once. Counting each stalled fight separately would
            # make `stalled` incomparable with the seed list it is printed
            # as.
            if stalls:
                stalled.append(seed)
        # **The median is over the fights that finished, and the ones that
        # did not are named.** A fight nobody won is not a long fight, and
        # averaging it in is what made `#473`'s single level-5 stall move
        # the headline mean from 7.08 to 10.25 and the range from 4-15 to
        # 4-31. Naming the seeds rather than only counting them: the whole
        # value of the old (wrong) number was that somebody noticed it,
        # and a bare count would not say which fight to go and read.
        #
        # `fights` stays the number **asked**, so `resolved + stalled`
        # reconciles against it -- `scripts/CLAUDE.md`'s rule, after
        # `browser.py` printed `55 passed, 1 skipped` of 57.
        if not rounds:
            # Every fight stalled: there is no median to take, and a zero
            # here would read as "instant wins" rather than as no data.
            rounds = [0]
        cell: dict = {
            "fights": len(SEEDS),
            "fights_per_day": fights,
            "fights_resolved": len(SEEDS) - len(stalled),
            "fights_stalled": len(stalled),
            "stalled_seeds": stalled,
            "rounds_median": statistics.median(rounds),
            # **The spread, so the reader can tell an unreadable number.** Either of
            # the two wrong answers this instrument gave would have been obviously
            # unreadable with the range printed beside the median. #291.
            "rounds_mean": round(statistics.fmean(rounds), 2),
            "rounds_low": min(rounds),
            "rounds_high": max(rounds),
        }
        for side in ("party", "monsters"):
            n = max(1, pol.n[f"{side}/decisions"])
            sizes = pol.ties[side]
            cell[side] = {
                "decisions": pol.n[f"{side}/decisions"],
                "oa_conceded": pol.n[f"{side}/oa_conceded"],
                "oa_per_fight": round(pol.n[f"{side}/oa_conceded"] / len(SEEDS), 2),
                "oa_damage": pol.n[f"{side}/oa_damage"],
                "self_damage": pol.n[f"{side}/self_damage"],
                "static_pct": (
                    round(100 * pol.n[f"{side}/static_mag"]
                          / max(1, pol.n[f"{side}/static_mag"]
                                + pol.n[f"{side}/derived_mag"]), 1)),
                "inert_chosen": pol.n[f"{side}/inert_chosen"],
                "self_harm": pol.n[f"{side}/self_harm"],
                "ally_blasts": pol.n[f"{side}/ally_blasts"],
                "allies_clipped": pol.n[f"{side}/allies_clipped"],
                "already_on": pol.n[f"{side}/already_on"],
                "tied_pct": round(100 * pol.n[f"{side}/tied"] / n, 1),
                "tie_size_mean": round(statistics.fmean(sizes), 2) if sizes else 0.0,
                "charge_offered": pol.n[f"{side}/charge_offered"],
                "charge_taken": pol.n[f"{side}/charge_taken"],
                "idle_melee": pol.n[f"{side}/idle_melee"],
                "passed_holding_standard":
                    pol.n[f"{side}/passed_holding_standard"],
                "adjacent_idle": pol.n[f"{side}/adjacent_idle"],
                "adjacent_helped": pol.n[f"{side}/adjacent_helped"],
                "could_not_act": pol.n[f"{side}/could_not_act"],
                "ap_spent": pol.n[f"{side}/ap_spent"],
                "surges": pol.n[f"{side}/surges"],
                # **Hit points per surge, not hit points.** A party that heals
                # more because it was hurt more is not playing worse, so the
                # raw total cannot be read as a quality. What a surge *bought*
                # can: #267 makes surges the currency, and a surge spent for 0
                # is the whole of #324.
                #
                # **Zero surges prints nothing rather than a rate**, and the
                # first version of this got it wrong in the way that matters.
                # `max(1, surges)` made the monster side -- which spends no
                # surges at all -- report "0 surges spent, 30.0 hit points
                # per surge", which is the raw total wearing a rate's label
                # and is exactly the kind of number this file's own history
                # says to distrust. `None` is rendered blank.
                #
                # And the honest limit, stated because the label cannot carry
                # it: the numerator is **all** healing, not only the healing a
                # surge paid for. Separating those needs `Healed` and
                # `SurgeSpent` linked, which `spend_surge(healed=)` may
                # already allow and which is not done here. So read this as
                # "hit points of healing the party got per surge it burned",
                # not as the efficiency of a single surge.
                "hp_per_surge": (
                    round(pol.n[f"{side}/restored"] / pol.n[f"{side}/surges"], 1)
                    if pol.n[f"{side}/surges"] else None),
                "wasted_heals": pol.n[f"{side}/wasted_heals"],
                "wasted_hp": pol.n[f"{side}/wasted_hp"],
                "dailies": pol.n[f"{side}/dailies"],
                "downed": pol.n[f"{side}/downed"],
                "downed_holding_wind": pol.n[f"{side}/downed_holding_wind"],
                # **An under-count by construction**, and `#324`'s comment
                # says why: 139 of 586 healing rows have no readable target
                # side, so they are not counted either way. See
                # `_could_be_saved`.
                "downed_with_a_heal_in_the_party":
                    pol.n[f"{side}/downed_with_a_heal_in_the_party"],
                "ap_standard": pol.n[f"{side}/ap_standard"],
                "melee_turns": pol.n[f"{side}/melee_turns"],
            }
        if roles is not None:
            # **Keyed off `pol.n` the same way `terms` is**, so the two
            # harvests cannot disagree about what a level's figures are.
            # Offered and taken are collected together rather than as two
            # passes, because a take rate needs both and a role that was
            # never offered a charge must read `0 of 0` rather than vanish
            # -- "never charged" and "never asked" are the two answers the
            # acceptance test has to tell apart.
            roles[str(level)] = {
                side: {
                    role: (
                        pol.n[f"{side}/charge_taken/{role}"],
                        pol.n[f"{side}/charge_offered/{role}"],
                    )
                    for role in sorted({
                        k.rsplit("/", 1)[1]
                        for k in pol.n
                        if k.startswith(f"{side}/charge_offered/")
                        or k.startswith(f"{side}/charge_taken/")
                    })
                }
                for side in ("party", "monsters")
            }
        if terms is not None:
            terms[str(level)] = {
                side: {
                    k.split("/mag/", 1)[1]: v
                    for k, v in pol.n.items()
                    if k.startswith(f"{side}/mag/") and v
                }
                for side in ("party", "monsters")
            }
        out[str(level)] = cell
    return out


ROWS = [
    ("oa_per_fight", "opportunity attacks conceded / fight", "lower"),
    # **The better of the two, per Camille.** Walking past a minion and walking
    # past a brute are the same count and not the same mistake, so the line above
    # prices a correct risk and a reckless one identically.
    ("oa_damage", "...hit points it cost them", "lower"),
    ("self_damage", "damage dealt to their own side", "lower"),
    # **#314's meter.** What share of a chosen action's weighted magnitude came from
    # a hand-set constant rather than a measured quantity. Not "lower is better" --
    # some constants are genuine preferences and should stay -- but it is the number
    # a recalibration has to move, and there was none before.
    ("static_pct", "of the decision that was a hand-set constant (%)", ""),
    ("inert_chosen", "inert rows chosen", "lower"),
    ("self_harm", "caught in own blast", "lower"),
    ("ally_blasts", "attacks that caught an ally", "lower"),
    ("allies_clipped", "...allies hit by them, counted in bodies", "lower"),
    ("already_on", "re-cast a live buff", "lower"),
    ("tied_pct", "decisions tied at the top (%)", "lower"),
    ("tie_size_mean", "mean options tied", "lower"),
    ("charge_taken", "charges taken", "higher"),
    ("charge_offered", "charges offered", "-"),
    ("idle_melee", "out of reach and did not close", "lower"),
    ("adjacent_idle", "adjacent to an enemy and did nothing", "lower"),
    ("passed_holding_standard", "passed the turn with a standard in hand", "lower"),
    # Not "lower is better": a leader beside an enemy buffing the party is doing
    # its job, so this is a reading rather than a fault. Printed next to the line
    # it was split out of, so the pair is read together.
    ("adjacent_helped", "...but buffed, healed or laid a zone", ""),
    ("could_not_act", "...excluded: nothing but `end` was on offer", "-"),
    ("ap_spent", "action points spent", "-"),
    # **The attrition lines, and "lower is better" on purpose.** #267: the
    # question is not whether the party wins -- it should -- but what winning
    # cost it, because 4e is an attrition game and a day is four fights.
    ("surges", "healing surges spent", "lower"),
    # **What the surges bought, which the count above cannot say.** #324
    # found three surges spent restoring **zero** hit points and
    # `Healed(amount=0)` twice in one log, with none left when two
    # characters later dropped and died. "Lower is better" is wrong for
    # this one -- a surge is spent either way, so more hit points off it is
    # strictly better play.
    ("hp_per_surge", "...hit points restored per surge", "higher"),
    # **The discriminating pair.** A heal for 0 and a heal for 6 on a
    # nearly-full ally are the same mistake, so the count is the signal and
    # the hit points are how much was thrown away with it. Above half is
    # the band, which is the printed second-wind threshold rather than a
    # number invented here.
    ("wasted_heals", "heals on an ally above half hit points", "lower"),
    ("wasted_hp", "...hit points spent on them", "lower"),
    ("dailies", "daily powers spent", "lower"),
    ("downed", "dropped to 0 hp", "lower"),
    # **The signal, and the reason the pair is printed together.** #303: dropping
    # with the second wind still unspent says the AI never took an answer it had,
    # which is fixable. Dropping after spending it says the fight was hard, which
    # is not a fault. One number cannot say which.
    ("downed_holding_wind", "...with their second wind still unspent", "lower"),
    # **The refusal, which `#324` calls the worse of its two faults.** The
    # wasted-heal counters above measure a heal spent badly; this measures
    # one the party held and did not spend on somebody dying. Printed
    # beside the second-wind line because they are the same shape one
    # scope wider -- that one asks whether the creature could have saved
    # itself, this whether anybody else could have saved it.
    #
    # **Under-counts by construction**: 139 of 586 healing rows have no
    # readable target side, so they are counted neither way. See
    # `_could_be_saved` for why that is the safe direction for a counter
    # whose job is to find a refusal.
    ("downed_with_a_heal_in_the_party",
     "...with a heal unspent in the party", "lower"),
    ("ap_standard", "...of them buying a standard action", "higher"),
    ("decisions", "decisions", "-"),
]


def show(now: dict, was: dict | None) -> None:
    for level in sorted(now, key=int):
        cell = now[level]
        old = (was or {}).get(level, {})
        # **"days" when a day was played, because the number means a
        # different thing.** With `--fights 4` each seed is one day of four
        # encounters, so 24 is days and 96 is fights, and labelling the
        # former "fights" is the kind of unit slip this file has a standing
        # note about. #305.
        per = cell.get("fights_per_day", 1)
        unit = "fights" if per == 1 else f"days of {per} fights"
        print(f"\n=== level {level}, {cell['fights']} {unit}, "
              f"median {cell['rounds_median']} rounds"
              + (f" (was {old.get('rounds_median')})" if old else "")
              + f", mean {cell.get('rounds_mean', 0)}"
              + (f" (was {old.get('rounds_mean')})"
                 if old and old.get("rounds_mean") is not None else "")
              + f", range {cell.get('rounds_low')}-{cell.get('rounds_high')}"
              + " ===")
        # **Printed, not buried in the JSON.** A stall is the one thing
        # that makes the line above unreadable, so it goes next to it --
        # and the seeds come too, because the reader's next move is to
        # play one. `fights` is how many were asked, so this reconciles
        # against it. #473.
        if cell.get("fights_stalled"):
            print(f"  !! {cell['fights_stalled']} of {cell['fights']} fights"
                  f" hit the round cap unresolved and are NOT in the median"
                  f" or the range above -- seeds {cell.get('stalled_seeds')}."
                  f" {cell.get('fights_resolved')} resolved. #473")
        print(f"  {'':<42} {'party':>9} {'was':>9}   {'monsters':>9} {'was':>9}")
        for key, label, want in ROWS:
            line = f"  {label:<42}"
            for side in ("party", "monsters"):
                new = cell[side][key]
                prev = old.get(side, {}).get(key)
                mark = ""
                # **`None` is a real value here and means "the question does
                # not apply on this side".** `hp_per_surge` is `None` when no
                # surge was spent, which is every monster side -- and the
                # alternative was `max(1, surges)`, which printed the raw
                # total wearing a rate's label. So it has to render, and it
                # has to not be compared: `None < prev` raises, and the first
                # version of this crashed the whole report after the surges
                # line rather than printing a blank.
                if (prev is not None and new is not None
                        and want != "-" and new != prev):
                    better = (new < prev) if want == "lower" else (new > prev)
                    mark = "+" if better else "!"
                cell_now = "-" if new is None else f"{new}"
                cell_was = "" if prev is None else f"{prev:>8}"
                line += f" {cell_now:>9}{mark:<1}{cell_was}"
            print(line)
    if was is None:
        print("\nNo baseline recorded. --save to write one.")
    else:
        print("\n  + better than the baseline, ! worse. `--save` to re-baseline.")


def show_roles(per_role: dict) -> None:
    """Charges offered and taken per role. `#293`'s acceptance test.

    **The test this prints has been cited as a guard on seven issues and
    has never been run**, because the counter it needs was keyed on side
    and this file's own docstring said it was keyed on role. `#293`:

        a melee-only skirmisher's charge take rate should rise toward the
        brute's, and **the wizard should keep charging zero times**. If the
        wizard starts charging, the term has gone too far.

    So the two readings that matter are a **melee role's rate** and the
    **controller's count**, and the second is the one that fails loudly:
    a controller charging at all means a look-ahead term has overpaid.

    `0 of 0` is printed rather than omitted. A role never offered a charge
    and a role that refused every charge offered are different findings and
    a missing row conflates them -- which is the same distinction
    `could_not_act` exists to keep elsewhere in this file.

    Not compared against the baseline and not part of the 52 figures: this
    is a reading, and a new baselined figure would force a re-bless.
    """
    print("\n  charges, per role -- #293's acceptance test")
    print("  a melee role should take them; a CONTROLLER should take none")
    for level in sorted(per_role, key=int):
        print(f"\n  level {level}")
        for side in ("party", "monsters"):
            got = per_role[level].get(side) or {}
            if not got:
                print(f"    {side:9s} -- no charge was offered to anybody")
                continue
            for role, (taken, offered) in sorted(got.items()):
                rate = f"{100 * taken / offered:5.1f}%" if offered else "    --"
                flag = ""
                if role == "controller" and taken:
                    flag = "  <- a controller CHARGED; the test says zero"
                print(f"    {side:9s} {role:12s} {taken:4d} of {offered:4d}"
                      f"  {rate}{flag}")


def show_terms(per_term: dict) -> None:
    """Rank each term by the weighted magnitude it contributed. #314.

    **The aggregate `static_pct` cannot answer the question this prints.**
    #314 measured a *new* derived term at 0.58 against a decision needing
    about 7, and separately the aggregate measured share is over half --
    which can both hold only if the derived magnitude sits in a few large
    terms while every new one is small. Those two situations call for
    opposite recalibrations: raise `SHARE` so new measured terms can
    compete, or bring the constants down to meet the measured terms that
    already dominate. So the split has to be readable per term.

    Magnitudes are |weight x value| summed over every decision, in
    hundredths, printed as a share of that side's total so two runs with
    different decision counts are comparable.
    """
    for level in sorted(per_term, key=int):
        for side in ("party", "monsters"):
            mags = per_term[level].get(side) or {}
            whole = sum(mags.values())
            if not whole:
                continue
            print(f"\n=== level {level}, {side}: weighted magnitude per term ===")
            for k, v in sorted(mags.items(), key=lambda kv: -kv[1])[:12]:
                tag = "measured" if k in DERIVED else "constant"
                print(f"  {k:<28} {100 * v / whole:5.1f}%  {tag}")
            shown = sum(v for _, v in
                        sorted(mags.items(), key=lambda kv: -kv[1])[:12])
            if shown < whole:
                print(f"  {'(' + str(len(mags) - 12) + ' smaller terms)':<28}"
                      f" {100 * (whole - shown) / whole:5.1f}%")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", type=int, action="append",
                    help="repeatable; defaults to 5 and 10")
    ap.add_argument("--save", action="store_true",
                    help="write the measurement as the new committed baseline")
    ap.add_argument("--fights", type=int, default=1,
                    help="fights per day, carrying one party between them. "
                         "1 (the default) is the single-fight measurement the "
                         "committed baseline holds; 4 is a day, which is what "
                         "exercises the daily reservation at all (#305)")
    ap.add_argument("--roles", action="store_true",
                    help="print charges offered and taken PER ROLE, which is "
                         "#293's and #265's stated acceptance test -- a "
                         "melee-only skirmisher's take rate against the "
                         "brute's, and the controller at zero. The baselined "
                         "pair is per side and cannot answer it")
    ap.add_argument("--terms", action="store_true",
                    help="also break the static/measured split down per term, "
                         "ranked by weighted magnitude. #314's question is "
                         "whether the measured half is one big term or many, "
                         "and the aggregate percentage cannot answer it")
    args = ap.parse_args()
    levels = tuple(args.level) if args.level else LEVELS
    was = json.loads(BASELINE.read_text()) if BASELINE.exists() else None
    stale = staleness(was)
    # **Always a dict, passed only when asked.** The first version was
    # `{} if args.terms else None` carrying an mypy-style suppression
    # comment, and `lint.py` is right to refuse those: `ty` does not honour
    # that syntax, so it suppressed nothing and the annotation was simply
    # wrong. Keeping the type honest removes the need for either -- and the
    # first attempt at this very comment tripped the same check by quoting
    # the forbidden spelling, which is #883's own lesson about prose. #883.
    per_term: dict = {}
    per_role: dict = {}
    now = measure(levels, fights=args.fights,
                  terms=per_term if args.terms else None,
                  roles=per_role if args.roles else None)
    if args.fights != 1:
        # **Refuse the comparison rather than print a misleading one.** The
        # baseline is a single-fight measurement; a four-fight day spends
        # more of everything by construction, so every `(was ...)` figure
        # would read as a regression. Dropping `was` makes the run report
        # only what it measured.
        print(f"  --fights {args.fights}: a DAY, not a fight. The baseline is "
              f"single-fight, so it is not comparable and is not shown.\n"
              f"  Attrition lines below are per day, over {len(SEEDS)} days.")
        was = None
    if stale:
        print(stale)
    show(now, was)
    if args.terms:
        show_terms(per_term)
    if args.roles:
        show_roles(per_role)
    if stale:
        print(stale)
    if args.save:
        merged = dict(was or {})
        merged.update(now)
        merged.pop("commit", None)  # derived from git now, see `staleness`
        BASELINE.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
        print(f"\nbaseline written to {BASELINE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
