#!/usr/bin/env python
"""A tactically readable transcript of one fight, for a human to criticise.

    uv run scripts/watch.py --seed 121 --level 10
    uv run scripts/watch.py --seed 121 --level 10 --alts 5

`scripts/fight.py` prints the event log, which is the right thing for debugging a
row and the wrong thing for judging a decision: it has no round markers, no
positions, no hit points and no sense of what else was on offer. Reading it to ask
"was that a good move?" is nearly impossible.

So this prints one line per decision with the context a reader needs to disagree
with it -- where the creature stood, what it could reach, what it picked, **what it
passed over and by how much** -- and then the consequence. The alternatives are the
point: a choice that looks poor is only interesting if something better scored lower.

Deliberately not a pass/fail check. It produces something to read.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import fight
from combat_engine.engine import Ident
from combat_engine.engine.components import Health, Position, Side
from combat_engine.engine.dsl import get
from combat_engine.engine.events import (
    AttackRolled,
    DamageApplied,
    Dropped,
    OpportunityWindow,
)
from combat_engine.engine.grid import distance
from combat_engine.engine.query import alive, creatures, enemies
from combat_engine.policy import doctrine as D
from combat_engine.policy import install, take_turn
from combat_engine.policy import threat as T
from combat_engine.policy.doctrine import DoctrinePolicy

POLICIES = {"doctrine": DoctrinePolicy}


def who(world, eid: int) -> str:  # noqa: ANN001
    ident = world.get(eid, Ident)
    if ident is None:
        return f"#{eid}"
    ref = ident.ref.removeprefix("c:")
    role = (ident.role or "")[:4]
    return f"{ref}({role})" if role else ref


def sketch(world, eid: int) -> str:  # noqa: ANN001
    """Hit points, square, and what is next to it."""
    h, p = world.get(eid, Health), world.get(eid, Position)
    hp = f"{h.hp}/{h.max_hp}" if h else "?"
    near = [who(world, f) for f in enemies(world, eid)
            if alive(world, f) and (q := world.get(f, Position)) is not None
            and p is not None and distance(p.square, q.square) <= 1]
    gap = min((distance(p.square, q.square)
               for f in enemies(world, eid) if alive(world, f)
               and (q := world.get(f, Position)) is not None), default=99) \
        if p is not None else 99
    return (f"hp {hp:>9} at {p.square if p else '?'} "
            f"nearest {gap if gap < 99 else '-'}"
            + (f" adj[{','.join(near)}]" if near else ""))


def describe(world, action) -> str:  # noqa: ANN001
    """One action, in the terms a reader can judge."""
    bits = [action.kind]
    if action.ref:
        p = get(action.ref)
        bits.append(action.ref)
        if p is not None:
            tag = [p.usage.value]
            if p.reach is not None:
                tag.append(f"{p.reach.kind}{p.reach.size}")
            if p.attack is None:
                tag.append("no-attack-line")
            bits.append("[" + " ".join(tag) + "]")
    if action.dest is not None:
        bits.append(f"-> {action.dest}")
    if action.targets:
        bits.append("on " + ",".join(who(world, t) for t in action.targets))
    return " ".join(bits)


class Narrator:
    """Wraps a policy so every decision is printed with its alternatives."""

    def __init__(self, base: type, alts: int) -> None:
        self.base, self.alts = base, alts
        self.pol = base()
        self.out: list[str] = []

    def __getattr__(self, name: str):  # noqa: ANN204
        return getattr(self.pol, name)

    def act(self, world, encounter, actor, options):  # noqa: ANN001, ANN201
        scored = sorted(
            ((self.pol.score(world, encounter, actor, a), a) for a in options
             if a.available),
            key=lambda t: (-t[0], str(t[1])))
        chosen = self.pol.act(world, encounter, actor, options)
        top = scored[0][0] if scored else 0.0
        self.out.append(f"    chose {describe(world, chosen)}   (score "
                        f"{top:+.2f})")
        for s, a in scored[1:1 + self.alts]:
            self.out.append(f"      passed {describe(world, a):<58} {s:+.2f}")
        return chosen

    def decide(self, world, actor, kind, options, prompt):  # noqa: ANN001, ANN201
        return self.pol.decide(world, actor, kind, options, prompt)

    def react(self, world, encounter, actor, window):  # noqa: ANN001, ANN201
        got = self.pol.react(world, encounter, actor, window)
        if got is not None:
            self.out.append(f"    ! {who(world, actor)} takes an opportunity "
                            f"attack: {describe(world, got)}")
        return got


def play(seed: int, level: int, policy: str, cap: int, alts: int) -> str:
    world, encounter = fight.build(seed, level, "full")
    T.clear()
    D.forget()
    nar = Narrator(POLICIES[policy], alts)
    install(world, encounter, {}, default=nar)
    lines: list[str] = []

    def rolled(ev: AttackRolled) -> None:
        land = "CRIT" if ev.natural == 20 else (
            "hit" if ev.total >= ev.defence else "MISS")
        nar.out.append(f"      roll d20={ev.natural} total {ev.total} "
                       f"vs {ev.defence} -> {land}")

    def hurt(ev: DamageApplied) -> None:
        nar.out.append(f"      {ev.amount} damage to {who(world, ev.target)}"
                       f" (now {ev.hp})")

    def dropped(ev: Dropped) -> None:
        nar.out.append(f"      *** {who(world, ev.actor)} drops")

    def provoked(ev: OpportunityWindow) -> None:
        nar.out.append(f"      {who(world, ev.provoker)} provokes "
                       f"({ev.why})")

    world.bus.on(AttackRolled, rolled)
    world.bus.on(DamageApplied, hurt)
    world.bus.on(Dropped, dropped)
    world.bus.on(OpportunityWindow, provoked)

    encounter.start()
    lines.append(f"=== seed {seed}, level {level}, policy {policy} ===")
    for eid in creatures(world):
        side = world.get(eid, Side)
        lines.append(f"  {who(world, eid):<24} "
                     f"{'party' if side and side.team.name == 'PC' else 'enemy':<6} "
                     f"{sketch(world, eid)}  threat {T.threat(world, eid):.1%}")
    seen = 0
    while not encounter.finished and world.round <= cap:
        actor = world.turn
        if actor is None:
            break
        if world.round != seen:
            seen = world.round
            lines.append(f"\n--- round {seen} ---")
        lines.append(f"  {who(world, actor)}  {sketch(world, actor)}")
        nar.out = []
        take_turn(world, encounter, actor, nar)
        lines.extend(nar.out)
        encounter.advance()
    won = encounter.finished and encounter.winner is not None \
        and encounter.winner.name == "PC"
    lines.append(f"\n=== {'party wins' if won else 'party loses or caps'} "
                 f"after {world.round} rounds ===")
    for eid in creatures(world):
        lines.append(f"  {who(world, eid):<24} {sketch(world, eid)}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--seed", type=int, default=121)
    ap.add_argument("--level", type=int, default=10)
    ap.add_argument("--policy", choices=sorted(POLICIES), default="doctrine")
    ap.add_argument("--rounds", type=int, default=30)
    ap.add_argument("--alts", type=int, default=3,
                    help="how many passed-over options to print per decision")
    args = ap.parse_args()
    print(play(args.seed, args.level, args.policy, args.rounds, args.alts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
