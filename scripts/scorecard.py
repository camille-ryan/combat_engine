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
* **charge_taken / charge_offered**, by role -- #265's acceptance test. A melee
  creature should charge often and a wizard never.
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
from combat_engine.engine import Ident
from combat_engine.engine.components import (
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

#: Terms whose value is a measured quantity rather than a number somebody picked:
#: a share of a side's threat pool, weighted by `SHARE`. Seven of them against 51
#: constants, which is #314.
DERIVED = frozenset(
    k for k, v in D.DOCTRINE.items() if abs(abs(v) - D.SHARE) < 1e-9
)

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
        if any(a.kind == "charge" for a in options if a.available):
            self.n[f"{side}/charge_offered"] += 1
        got = super().act(world, encounter, actor, options)
        if got.kind == "charge":
            self.n[f"{side}/charge_taken"] += 1
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


def play(level: int, seed: int, pol: Counted, cap: int = 30) -> int:
    world, encounter = fight.build(seed, level, "full")
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
    return world.round


def measure(levels: tuple[int, ...]) -> dict:
    out: dict = {}
    for level in levels:
        pol = Counted()
        rounds = []
        for seed in SEEDS:
            # Counting attacks needs a hook; the policy records them itself below.
            rounds.append(play(level, seed, pol))
        cell: dict = {
            "fights": len(SEEDS),
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
                "adjacent_idle": pol.n[f"{side}/adjacent_idle"],
                "adjacent_helped": pol.n[f"{side}/adjacent_helped"],
                "could_not_act": pol.n[f"{side}/could_not_act"],
                "ap_spent": pol.n[f"{side}/ap_spent"],
                "surges": pol.n[f"{side}/surges"],
                "dailies": pol.n[f"{side}/dailies"],
                "downed": pol.n[f"{side}/downed"],
                "downed_holding_wind": pol.n[f"{side}/downed_holding_wind"],
                "ap_standard": pol.n[f"{side}/ap_standard"],
                "melee_turns": pol.n[f"{side}/melee_turns"],
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
    ("dailies", "daily powers spent", "lower"),
    ("downed", "dropped to 0 hp", "lower"),
    # **The signal, and the reason the pair is printed together.** #303: dropping
    # with the second wind still unspent says the AI never took an answer it had,
    # which is fixable. Dropping after spending it says the fight was hard, which
    # is not a fault. One number cannot say which.
    ("downed_holding_wind", "...with their second wind still unspent", "lower"),
    ("ap_standard", "...of them buying a standard action", "higher"),
    ("decisions", "decisions", "-"),
]


def show(now: dict, was: dict | None) -> None:
    for level in sorted(now, key=int):
        cell = now[level]
        old = (was or {}).get(level, {})
        print(f"\n=== level {level}, {cell['fights']} fights, "
              f"median {cell['rounds_median']} rounds"
              + (f" (was {old.get('rounds_median')})" if old else "")
              + f", mean {cell.get('rounds_mean', 0)}"
              + (f" (was {old.get('rounds_mean')})"
                 if old and old.get("rounds_mean") is not None else "")
              + f", range {cell.get('rounds_low')}-{cell.get('rounds_high')}"
              + " ===")
        print(f"  {'':<42} {'party':>9} {'was':>9}   {'monsters':>9} {'was':>9}")
        for key, label, want in ROWS:
            line = f"  {label:<42}"
            for side in ("party", "monsters"):
                new = cell[side][key]
                prev = old.get(side, {}).get(key)
                mark = ""
                if prev is not None and want != "-" and new != prev:
                    better = (new < prev) if want == "lower" else (new > prev)
                    mark = "+" if better else "!"
                line += f" {new:>9}{mark:<1}{'' if prev is None else f'{prev:>8}'}"
            print(line)
    if was is None:
        print("\nNo baseline recorded. --save to write one.")
    else:
        print("\n  + better than the baseline, ! worse. `--save` to re-baseline.")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--level", type=int, action="append",
                    help="repeatable; defaults to 5 and 10")
    ap.add_argument("--save", action="store_true",
                    help="write the measurement as the new committed baseline")
    args = ap.parse_args()
    levels = tuple(args.level) if args.level else LEVELS
    was = json.loads(BASELINE.read_text()) if BASELINE.exists() else None
    stale = staleness(was)
    now = measure(levels)
    if stale:
        print(stale)
    show(now, was)
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
