#!/usr/bin/env python
"""How often the party wins, over many seeded fights.

    uv run scripts/winrate.py                      30 seeds, levels 1/5/10
    uv run scripts/winrate.py --seeds 60 --level 1
    uv run scripts/winrate.py --draw chassis       and --draw scored

**This did not exist, and #75's numbers were produced by hand.** That issue was
closed unfixed, because the thing it measures cannot be read:

> feats and items are drawn at random, so the win rate measures arbitrary builds
> rather than the engine

`--draw` is what answers that. It fixes *how the party is assembled* and leaves
everything else alone, so two runs over the same seeds differ in one variable:

    chassis   `SCORED_CHOICES` off -- the class's own gear, feats drawn uniformly
    scored    the option scorer as it stands
    rated     the scorer plus the community ratings

`LinearPolicy` is held fixed on both sides throughout. A policy change and a draw
change measured together would tell you nothing about either.

**Rounds is reported beside the win rate and is the more trustworthy number.**
#217 settled that the target is 7-8 rounds and that a seeded fight's round count is
readable in a way win rate is not. A run that raises the win rate while collapsing
the round count has not improved the game; it has made the party too strong for the
encounter, which is the thing #217 watches for.

**Correct for multiple comparisons, and for having chosen what to report.**
Three pairwise win-rate tests on one dataset need Holm or Bonferroni, and under
Holm none of the level-5 comparisons reject -- including the one that reads
"borderline" at a raw p of 0.066. Worse, this instrument measures win rate over
four levels, hit rate per class, OA totals, OA reasons and round medians, and a
reader naturally reports whichever moved. That is a garden of forking paths, not a
test. `--from-seed` exists so a finding can be re-checked on seeds it was not found
on, which is the only clean way out.

**How many seeds a difference needs, because 30 and 40 are not enough.**
Measured rather than assumed: at level 5 the three draws came out 10, 7 and 3 wins
of 40, and exact two-sided tests on those give

    chassis 10/40 vs rated   3/40    p = 0.066   borderline
    scored   7/40 vs rated   3/40    p = 0.311   not significant
    chassis 10/40 vs scored  7/40    p = 0.586   not significant

So **none of them separate at 40 seeds**, and several conclusions were drawn off 30
before that was checked. Detecting 25% against 8% at 80% power wants about 80 seeds
per cell; 25% against 18% wants about 175. Budget accordingly, and prefer the two
measures below when the budget is small.

**Hit rate and opportunity attacks are the cheap measures, and win rate is the
dear one.** Both rest on hundreds or thousands of events per run rather than one
outcome per fight, so they read at sample sizes where win rate is still noise:

* hit rate came out 61% / 60% / 61% across the three draws -- thousands of attack
  rolls, and a real "no difference";
* "moved away" provocations came out 90 / 137 / 145 over 40 fights, which *is* a
  difference and says the scorer walks away from adjacent enemies far more.

A ten-seed run once showed the rated draw provoking 44% more opportunity attacks
than the chassis. At forty that was 6.3 against 5.5 with the monsters provoking
more in return, so the ten-seed figure was an artefact. Even the cheap measures
want a few tens of fights.

Two things to know before reading any output:

* **Above level 1 the party essentially never wins.** #75 measured 2 of 30 at
  level 5 and 0 of 30 at level 10. A difference at those levels is not
  measurable, and level 10 is confounded further by #244 -- a dealt character
  there has almost no attack powers.
* A fight that hits the round cap is recorded as **neither** a win nor a loss,
  because it is a third outcome and calling it a loss flatters anything that
  shortens fights.
"""

from __future__ import annotations

import argparse
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import fight
from combat_engine import chargen
from combat_engine.engine import Ident, LinearPolicy, install, take_turn
from combat_engine.engine.events import AttackRolled, OpportunityWindow
from combat_engine.engine.types import Team

DRAWS = ("chassis", "scored", "rated")


def arrange(draw: str) -> None:
    """Set how the party is assembled. The only variable between runs."""
    chargen.SCORED_CHOICES = draw != "chassis"
    # `USE_RATINGS` may not exist yet in an older tree; setting it is harmless.
    chargen.USE_RATINGS = draw == "rated"


def one(seed: int, level: int, cap: int,
        tally: dict[str, list[int]] | None = None,
        oas: dict[str, int] | None = None) -> tuple[str, int]:
    """(outcome, rounds) for a single fight. Outcome is win, loss or cap.

    `tally` accumulates hits and attempts per creature, keyed by what it is.
    `oas` counts opportunity windows by who **provoked** them, and by the reason.

    An opportunity attack provoked is free damage handed to the other side, so a
    party that provokes more of them is positioning worse -- and that shows up
    long before a win rate does. Camille's second suggestion, and it reads a
    different axis from hit rate: accuracy against positioning.

    **Hit rate is the sensitive measure and win rate is the blunt one.** A better
    draw shows up in accuracy within a handful of fights; it takes hundreds for
    the same change to move a win rate out of the noise, and at level 1 the win
    rate is saturated at 100% so it cannot move at all. Camille's suggestion, and
    it is the right one.
    """
    world, encounter = fight.build(seed, level, "full")
    policy = LinearPolicy()
    install(world, encounter, {}, default=policy)
    if tally is not None:
        def rolled(ev: AttackRolled) -> None:
            ident = world.get(ev.attacker, Ident)
            who = (ident.ref if ident else "?").removeprefix("c:")
            # A monster's ref is an id nobody can read; its role is the useful
            # label and `Ident.role` now carries it on both sides of the board.
            if not who.startswith("m"):
                key = who
            else:
                key = f"monster:{(ident.role if ident else '') or '?'}"
            got = tally.setdefault(key, [0, 0])
            got[1] += 1
            if ev.total >= ev.defence or ev.natural == 20:
                got[0] += 1
        world.bus.on(AttackRolled, rolled)
    if oas is not None:
        def window(ev: OpportunityWindow) -> None:
            ident = world.get(ev.provoker, Ident)
            ref = (ident.ref if ident else "?")
            side = "monsters" if ref.startswith("m") else "party"
            oas[side] = oas.get(side, 0) + 1
            oas[f"{side}:{ev.why[:26]}"] = oas.get(f"{side}:{ev.why[:26]}", 0) + 1
        world.bus.on(OpportunityWindow, window)
    encounter.start()
    while not encounter.finished and world.round <= cap:
        actor = world.turn
        if actor is None:
            break
        take_turn(world, encounter, actor, policy)
        encounter.advance()
    if not encounter.finished:
        return "cap", world.round
    return ("win" if encounter.winner is Team.PC else "loss"), world.round


def run(draw: str, level: int, seeds: int, cap: int,
        first: int = 1) -> dict:
    arrange(draw)
    tally: dict[str, list[int]] = {}
    oas: dict[str, int] = {}
    wins = losses = capped = 0
    rounds: list[int] = []
    for seed in range(first, first + seeds):
        try:
            out, n = one(seed, level, cap, tally, oas)
        except Exception as exc:
            # One unplayable seed must not cost the other fifty-nine, and a
            # silent skip would flatter the result. Counted and reported.
            print(f"    seed {seed}: {type(exc).__name__}: {str(exc)[:60]}",
                  file=sys.stderr)
            continue
        rounds.append(n)
        wins += out == "win"
        losses += out == "loss"
        capped += out == "cap"
    played = wins + losses + capped
    return {
        "draw": draw, "level": level, "played": played, "wins": wins,
        "losses": losses, "capped": capped,
        "rate": wins / played if played else 0.0,
        "rounds": statistics.median(rounds) if rounds else 0,
        "lo": min(rounds) if rounds else 0, "hi": max(rounds) if rounds else 0,
        "hits": tally, "oas": oas,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--from-seed", type=int, default=1,
                    help="first seed. Exists so a finding can be re-tested on "
                         "seeds it was not found on, which is the only way to "
                         "tell a result from a post-hoc selection")
    ap.add_argument("--level", type=int, action="append",
                    help="repeatable; defaults to 1, 5 and 10")
    ap.add_argument("--draw", choices=DRAWS, action="append",
                    help="repeatable; defaults to every one")
    ap.add_argument("--rounds", type=int, default=30, help="give up after this many")
    args = ap.parse_args()
    levels = args.level or [1, 5, 10]
    draws = args.draw or list(DRAWS)

    print(f"{args.seeds} seeds per cell, LinearPolicy both sides, "
          f"round cap {args.rounds}")
    print(f"party: {', '.join(fight.PARTY)}\n")
    print(f"{'draw':<9} {'lvl':>3} {'played':>6} {'wins':>5} {'rate':>6} "
          f"{'loss':>5} {'cap':>4} {'rounds':>7} {'range':>9}")
    got = []
    for level in levels:
        for draw in draws:
            r = run(draw, level, args.seeds, args.rounds, args.from_seed)
            got.append(r)
            print(f"{r['draw']:<9} {r['level']:>3} {r['played']:>6} {r['wins']:>5} "
                  f"{r['rate']:>5.0%} {r['losses']:>5} {r['capped']:>4} "
                  f"{r['rounds']:>7} {str(r['lo']) + '-' + str(r['hi']):>9}")
        print()

    # Hit rate per creature, which is what actually moves when a draw improves.
    print(f"{'draw':<9} {'lvl':>3}  " + "  ".join(f"{c:>9}" for c in fight.PARTY)
          + f"  {'party':>7} {'monsters':>9}")
    for r in got:
        cells = []
        for cls in fight.PARTY:
            h, n = r["hits"].get(cls, [0, 0])
            cells.append(f"{h / n:>8.0%}" if n else f"{'--':>8}")
        ph = sum(r["hits"].get(c, [0, 0])[0] for c in fight.PARTY)
        pn = sum(r["hits"].get(c, [0, 0])[1] for c in fight.PARTY)
        mh = sum(v[0] for k, v in r["hits"].items() if k.startswith("monster:"))
        mn = sum(v[1] for k, v in r["hits"].items() if k.startswith("monster:"))
        print(f"{r['draw']:<9} {r['level']:>3}  "
              + "  ".join(f"{c:>9}" for c in cells)
              + f"  {ph / pn if pn else 0:>6.0%} {mh / mn if mn else 0:>9.0%}")
    print()

    # Opportunity attacks provoked -- free damage handed to the other side.
    print(f"{'draw':<9} {'lvl':>3} {'party provoked':>15} {'per fight':>10} "
          f"{'monsters provoked':>18} {'per fight':>10}")
    for r in got:
        pp = r["oas"].get("party", 0)
        mp = r["oas"].get("monsters", 0)
        n = max(1, r["played"])
        print(f"{r['draw']:<9} {r['level']:>3} {pp:>15} {pp / n:>10.1f} "
              f"{mp:>18} {mp / n:>10.1f}")
    print()
    for r in got:
        why = {k.split(":", 1)[1]: v for k, v in r["oas"].items()
               if k.startswith("party:")}
        top = sorted(why.items(), key=lambda kv: -kv[1])[:3]
        if top:
            print(f"  {r['draw']:<9} lvl {r['level']:>2} party provoked by: "
                  + ", ".join(f"{k} x{v}" for k, v in top))
    print()

    # The comparison the whole instrument exists for.
    for level in levels:
        cells = {r["draw"]: r for r in got if r["level"] == level}
        if "chassis" in cells and len(cells) > 1:
            base = cells["chassis"]
            for draw in DRAWS[1:]:
                if draw not in cells:
                    continue
                c = cells[draw]
                print(f"level {level}: {draw} against chassis  "
                      f"{c['rate'] - base['rate']:+.0%} win rate, "
                      f"{c['rounds'] - base['rounds']:+} median rounds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
