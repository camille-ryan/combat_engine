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
* **idle_melee** -- a melee creature's turn that neither attacked nor closed any
  distance. **The regression guard**: the fix for #265 removes a term that approach
  behaviour was built on, and this is what would catch it going wrong.
* **rounds** -- the balance guard only, against #217's 7-8.

The baseline lives in `scripts/fixtures/scorecard.json` and is committed, which is
what makes a lost comparison survivable: "did this fix help" is answered against the
previous commit's numbers. **It has to be kept honest.** Re-save it only when the
change is understood and intended, the same discipline `replay.py record` needs, and
say in the commit which way each number moved.

Not a pass/fail check. It prints what the AI did.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import fight
from combat_engine.engine import Ident, install, take_turn
from combat_engine.engine import doctrine as D
from combat_engine.engine import threat as T
from combat_engine.engine.components import Position
from combat_engine.engine.dsl import get
from combat_engine.engine.events import OpportunityWindow
from combat_engine.engine.grid import distance
from combat_engine.engine.query import alive, enemies

BASELINE = Path(__file__).resolve().parent / "fixtures" / "scorecard.json"

#: Fixed so two runs are comparable. Twelve is enough for event counts.
SEEDS = tuple(range(301, 313))
LEVELS = (5, 10)


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

    def act(self, world, encounter, actor, options):  # noqa: ANN001, ANN201
        side = side_of(world, actor)
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
        if got.kind == "action_point":
            self.n[f"{side}/ap_spent"] += 1
            # Which extra action it bought. A standard is worth most by a wide
            # margin, so this reading says whether the choice is evaluated or a
            # tie-break: `Action.ref` carries the granted type. #266.
            self.n[f"{side}/ap_standard"] += int(got.ref == "standard")
        if got.ref and inert(world, actor, got.ref):
            self.n[f"{side}/inert_chosen"] += 1
        p = get(got.ref) if got.ref else None
        if p is not None and p.attack is not None and got.targets:
            self.n[f"{side}/attacks"] += 1
        d = self.explain(world, encounter, actor, got)
        if d.get("self_harm"):
            self.n[f"{side}/self_harm"] += 1
        if d.get("already_on"):
            self.n[f"{side}/already_on"] += 1
        return got


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
    install(world, encounter, {}, default=pol)

    def provoked(ev: OpportunityWindow) -> None:
        pol.n[f"{side_of(world, ev.provoker)}/oa_conceded"] += 1

    world.bus.on(OpportunityWindow, provoked)
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
        take_turn(world, encounter, actor, pol)
        turn_watch(world, pol, actor)
        after = world.get(actor, Position)
        now = min((distance(after.square, q.square) for e in enemies(world, actor)
                   if alive(world, e) and (q := world.get(e, Position)) is not None),
                  default=99) if after else 99
        if (D.fights_in_melee(world, actor)
                and pol.n[f"{side_of(world, actor)}/attacks"] == hits
                and now >= gap):
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
        cell: dict = {"fights": len(SEEDS), "rounds_median": statistics.median(rounds)}
        for side in ("party", "monsters"):
            n = max(1, pol.n[f"{side}/decisions"])
            sizes = pol.ties[side]
            cell[side] = {
                "decisions": pol.n[f"{side}/decisions"],
                "oa_conceded": pol.n[f"{side}/oa_conceded"],
                "oa_per_fight": round(pol.n[f"{side}/oa_conceded"] / len(SEEDS), 2),
                "inert_chosen": pol.n[f"{side}/inert_chosen"],
                "self_harm": pol.n[f"{side}/self_harm"],
                "already_on": pol.n[f"{side}/already_on"],
                "tied_pct": round(100 * pol.n[f"{side}/tied"] / n, 1),
                "tie_size_mean": round(statistics.fmean(sizes), 2) if sizes else 0.0,
                "charge_offered": pol.n[f"{side}/charge_offered"],
                "charge_taken": pol.n[f"{side}/charge_taken"],
                "idle_melee": pol.n[f"{side}/idle_melee"],
                "ap_spent": pol.n[f"{side}/ap_spent"],
                "ap_standard": pol.n[f"{side}/ap_standard"],
                "melee_turns": pol.n[f"{side}/melee_turns"],
            }
        out[str(level)] = cell
    return out


ROWS = [
    ("oa_per_fight", "opportunity attacks conceded / fight", "lower"),
    ("inert_chosen", "inert rows chosen", "lower"),
    ("self_harm", "caught in own blast", "lower"),
    ("already_on", "re-cast a live buff", "lower"),
    ("tied_pct", "decisions tied at the top (%)", "lower"),
    ("tie_size_mean", "mean options tied", "lower"),
    ("charge_taken", "charges taken", "higher"),
    ("charge_offered", "charges offered", "-"),
    ("idle_melee", "melee turns neither attacking nor closing", "lower"),
    ("ap_spent", "action points spent", "-"),
    ("ap_standard", "...of them buying a standard action", "higher"),
    ("decisions", "decisions", "-"),
]


def show(now: dict, was: dict | None) -> None:
    for level in sorted(now, key=int):
        cell = now[level]
        old = (was or {}).get(level, {})
        print(f"\n=== level {level}, {cell['fights']} fights, "
              f"median {cell['rounds_median']} rounds"
              + (f" (was {old.get('rounds_median')})" if old else "") + " ===")
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
    now = measure(levels)
    show(now, was)
    if args.save:
        merged = dict(was or {})
        merged.update(now)
        BASELINE.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n")
        print(f"\nbaseline written to {BASELINE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
