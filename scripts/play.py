#!/usr/bin/env python
"""Play a module: roleplay, skill challenges, fights, and the party between them.

    uv run scripts/play.py --validate scripts/fixtures/modules/sunken-mill.json
    uv run scripts/play.py --play scripts/fixtures/modules/sunken-mill.json
    uv run scripts/play.py --play modules/keep/module.json --seed 12 --save keep
    uv run scripts/play.py --resume keep
    uv run scripts/play.py --list

`fight.py` plays one encounter and `fight.py --fights N` plays several against
one party. Neither knows what the fights are *for*. This reads an adventure --
a graph of scenes, some of which are fights -- and plays it through, carrying
the party's wounds, spent powers and surges from one scene to the next and
writing the whole thing down so it can be picked up again.

**`--no-dm` is the default and is not a degraded mode.** With it, a scene is
its own written text and the choices are a menu. That matters for two
reasons: `check.py` runs this and an instrument that needs a network and an
API key is an instrument that goes red for the wrong reason, and a person who
has not configured a model should still be able to play. The model is the
other half (#794) and is additive.

**On names.** The rest of `scripts/` prints refs and never names, and this is
the one place that differs: a scene's prose and its word for a creature come
out of the module file, which the person running this supplied themselves and
which is git-ignored. Nothing here reads `localization/names.json` and nothing
here prints a name that came out of the tree -- with no module, there is
nothing to show. Monsters are still identified by ref wherever the module
gave no word of its own.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from combat_engine.story import importer
from combat_engine.story import module as module_mod
from combat_engine.story import run as run_mod
from combat_engine.story import save as save_mod

#: Scenes one invocation will play before stopping. A module graph can have a
#: cycle in it -- a published adventure legitimately loops a location -- so a
#: run needs a bound that is not "until the campaign ends".
LIMIT = 200


def validate(path: str) -> int:
    """Load a module and say what is wrong with it, or what is in it."""
    try:
        module = module_mod.load(path)
    except module_mod.ModuleError as exc:
        print(exc)
        return 1
    kinds: dict[str, int] = {}
    for scene in module.scenes.values():
        kinds[scene.kind] = kinds.get(scene.kind, 0) + 1
    print(f"{module.id}: {len(module.scenes)} scenes, opening at {module.start}")
    print(f"  party       level {module.party_level}, {module.party_size} characters")
    if module.edition:
        print(f"  converted from  {module.edition}")
    print("  scenes      " + ", ".join(f"{n} {k}" for k, n in sorted(kinds.items())))
    if module.flags:
        print("  flags       " + ", ".join(f"{k}={v}" for k, v in module.flags.items()))
    return 0


def _print_step(made: run_mod.Step, *, quiet: bool) -> None:
    head = f"-- {made.scene.id} [{made.scene.kind}]"
    if made.scene.name:
        head += f"  {made.scene.name}"
    print(head)
    if not quiet:
        for line in made.lines:
            print(f"   {line}")
    elif made.outcome != "done":
        print(f"   {made.outcome}" + (f" in {made.rounds} rounds" if made.rounds else ""))
    for note in made.notes:
        print(f"   ! {note}")


def play(path: str, *, seed: int, save_as: str, quiet: bool, resume: str = "") -> int:
    """Play a module from the start, or pick one up where it was left."""
    if resume:
        campaign = save_mod.load(resume)
        module = module_mod.load(path)
        if campaign.module != module.id:
            raise SystemExit(
                f"save {resume!r} is a campaign of {campaign.module!r}, not "
                f"{module.id!r}."
            )
        print(f"=== resuming {campaign.module} at {campaign.scene} ===")
    else:
        module = module_mod.load(path)
        campaign = run_mod.begin(module, seed=seed)
        print(f"=== {module.id}, seed {seed}, party level {module.party_level} ===")

    print(f"   {run_mod.party_line(campaign)}")
    print()

    fights = rounds = 0
    played = 0
    while not campaign.finished and played < LIMIT:
        made = run_mod.step(campaign, module)
        played += 1
        _print_step(made, quiet=quiet)
        if made.scene.kind == "combat" and made.outcome in ("won", "lost"):
            fights += 1
            rounds += made.rounds
        print(f"   {run_mod.party_line(campaign)}")
        print()
        if made.outcome == "lost" and made.scene.kind == "combat":
            print("The party is beaten. The campaign stops here.")
            break

    print("=== " + ("finished" if campaign.finished else "stopped") + " ===")
    print(f"  scenes played   {played}")
    if fights:
        print(f"  fights          {fights}, {rounds / fights:.1f} rounds on average")
    alive = sum(1 for s in campaign.party.sheets if not s.down)
    print(f"  party           {alive} of {len(campaign.party.sheets)} standing")
    if save_as:
        where = save_mod.save(campaign, save_as)
        print(f"  saved           {where}")
    # A campaign that stopped because the party lost is not a failing
    # instrument -- it is a result. Only a run that played nothing is.
    return 0 if played else 1


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--play", metavar="MODULE", help="a module file to play")
    ap.add_argument(
        "--validate", metavar="MODULE",
        help="load a module and report every problem with it at once, or "
        "print what it holds",
    )
    ap.add_argument(
        "--resume", metavar="NAME",
        help="pick up a saved campaign. Needs --play to say which module, "
        "because a save holds where the party got to and not the adventure "
        "itself -- the module is the user's own file and is not copied into "
        "the save",
    )
    ap.add_argument(
        "--import", dest="import_", metavar="FILE",
        help="split an adventure you own into per-page text, pull its "
        "outline, and write a draft module and a brief beside it under "
        "modules/<id>/. A .pdf needs the optional pypdf; a .txt or .md "
        "skips that step. Filling the draft in is a reading job and is "
        "deliberately not done here -- see the brief it writes",
    )
    ap.add_argument(
        "--id", metavar="NAME", default="",
        help="what to call the imported module. Required with --import",
    )
    ap.add_argument("--list", action="store_true", help="saved campaigns on this machine")
    ap.add_argument(
        "--seed", type=int, default=7,
        help="the campaign's seed. Every scene derives its own stream from "
        "this and its own id, so a campaign replays and changing one scene "
        "does not move the dice in another",
    )
    ap.add_argument("--save", metavar="NAME", default="", help="write the campaign out")
    ap.add_argument(
        "--no-dm", action="store_true", default=True,
        help="play the module's own written text with no model in the loop. "
        "The default, and what check.py runs: an instrument that needs a "
        "network and a key goes red for the wrong reason (#794)",
    )
    ap.add_argument("--quiet", action="store_true", help="outcomes only, no prose")
    args = ap.parse_args()

    if args.list:
        found = save_mod.names()
        print("\n".join(found) if found else "no saved campaigns")
        return 0
    if args.import_:
        if not args.id:
            raise SystemExit("--import needs --id to say what to call the module.")
        got = importer.run_import(args.import_, args.id)
        print(f"=== imported into {got.into} ===")
        print(f"  pages          {got.pages}, one text file each in pages/")
        print(f"  outline        {got.headings} headings")
        print(f"  draft scenes   {got.scenes}")
        print(f"  draft          {got.draft}")
        print(f"  brief          {got.brief}")
        print()
        print("Next: read the brief, fill the draft in as module.json, then")
        print(f"  uv run scripts/play.py --validate {got.into}/module.json")
        return 0
    if args.validate:
        return validate(args.validate)
    if args.resume and not args.play:
        raise SystemExit("--resume needs --play to say which module to resume into.")
    if args.play:
        return play(
            args.play, seed=args.seed, save_as=args.save,
            quiet=args.quiet, resume=args.resume or "",
        )
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
