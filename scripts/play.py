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

**`--no-dm` is the default and is not a degraded mode.** With it a scene is
its own written text, and where a scene genuinely branches you are asked
which way. That matters for two reasons: `check.py` runs this and an
instrument that needs a network and an API key is an instrument that goes red
for the wrong reason, and a person who has not configured a model should
still be able to play. The model is the other half (#794) and is additive.

Be clear about how little the asking currently amounts to, because the first
draft of this docstring claimed a menu that did not exist. A roleplay scene
prints its brief and advances; the only interaction is the branch prompt, and
**a linear adventure has no branches at all** -- neither the converted module
nor the fixture has a single scene with two exits. The prompt is real and it
is almost never reached.

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

from combat_engine.story import Party, importer
from combat_engine.story import beat as beat_mod
from combat_engine.story import maker as maker_mod
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


def choose_exit(scene: module_mod.Scene, module: module_mod.Module) -> str:
    """Ask which way, when a scene genuinely branches. `""` takes the first.

    **Only at a terminal.** `check.py` runs this script as a subprocess that
    inherits stdin, so an unconditional prompt would block the whole suite
    the day somebody writes a branching module. Not hypothetical -- it is the
    shape of bug that waits for the one commit that makes it reachable.
    """
    exits = list(scene.exits)
    if len(exits) < 2 or not sys.stdin.isatty():
        return ""
    print("   where do they go?")
    for i, exit_id in enumerate(exits):
        other = module.scenes[exit_id]
        mark = "*" if i == 0 else " "
        print(f"     {mark}{i}  {exit_id:<36} {other.name}")
    while True:
        try:
            said = input("     [0] ").strip()
        except EOFError:
            return ""
        if not said:
            return ""
        if said.isdigit() and 0 <= int(said) < len(exits):
            return exits[int(said)]
        print(f"     a number from 0 to {len(exits) - 1}, or Enter.")


def declare(actor: beat_mod.Actor, situation: str) -> tuple[str, str]:
    """Ask a person what their character says and does.

    Two lines rather than one, because the beat loop keeps speech and action
    apart all the way through -- the matcher reads them together and the DM
    is shown them separately, and collapsing them here would make the person
    the only actor whose intent arrives in a different shape.

    Enter on both means they sit this beat out, which is a real thing to do
    in a conversation and costs nothing.
    """
    if not sys.stdin.isatty():
        return "", ""
    print(f"\n  {actor.name} ({actor.cls})")
    try:
        speech = input('    say:  ').strip()
        doing = input('    do:   ').strip()
    except EOFError:
        return "", ""
    return speech, doing


def _print_head(scene: module_mod.Scene) -> None:
    """The scene's banner, printed before anything in it happens."""
    head = f"-- {scene.id} [{scene.kind}]"
    if scene.name:
        head += f"  {scene.name}"
    print(head, flush=True)


def _print_step(made: run_mod.Step, *, quiet: bool, narrated: bool = False,
                already: bool = False) -> None:
    """What the scene did. `already` means the lines went out as they
    happened and only the tail -- notes, outcome, the log path -- is left.
    """
    if not already:
        _print_head(made.scene)
    # With a model narrating, the module's own text is its source material
    # and printing both says everything twice.
    if narrated:
        if made.outcome != "done":
            print(f"   ({made.outcome}"
                  + (f", {made.rounds} rounds" if made.rounds else "") + ")")
        for note in made.notes:
            print(f"   ! {note}")
        if made.transcript:
            print(f"   log {made.transcript}")
        return
    if already:
        pass
    elif not quiet:
        for line in made.lines:
            print(f"   {line}")
    elif made.outcome != "done":
        print(f"   {made.outcome}" + (f" in {made.rounds} rounds" if made.rounds else ""))
    for note in made.notes:
        print(f"   ! {note}")
    if made.transcript:
        print(f"   log {made.transcript}")


def ask(question: maker_mod.Question) -> int:
    """Put one question to whoever is at the terminal.

    Enter takes the default, which is what the dealer would have picked --
    so a person who wants a dealt character can hold Enter down and get
    exactly the one `Party.of` would have made.
    """
    print(f"\n{question.prompt}")
    for i, option in enumerate(question.options):
        mark = "*" if i == question.default else " "
        score = f"{option.score:6.2f}" if option.score else "      "
        print(f"  {mark}{i:>3}  {option.ref:<22} {score}  {option.why}")
    while True:
        try:
            said = input(f"  [{question.default}] ").strip()
        except EOFError:
            # Nothing on stdin -- piped, redirected, or the person walked
            # away. Taking the default is the right answer for all three and
            # is also what makes this runnable from an instrument.
            print("(taking the default)")
            return question.default
        if not said:
            return question.default
        if said.isdigit() and 0 <= int(said) < len(question.options):
            return int(said)
        print(f"  a number from 0 to {len(question.options) - 1}, or Enter.")


def new_character(party_name: str, *, level: int, seed: int, cls: str) -> int:
    """Make one character and add them to a party."""
    try:
        party = save_mod.load_party(party_name)
    except SystemExit:
        party = Party()
    sheet = maker_mod.interview(ask, level=level, seed=seed, cls=cls)
    personas = save_mod.load_personas(party_name)
    while len(personas) < len(party.sheets):
        at = len(personas)
        kind = party.sheets[at].cls
        personas.append(save_mod.Persona.by_class(
            kind, sum(1 for s in party.sheets[:at] if s.cls == kind)))
    # Who they are, as opposed to what they can do. Only the model reads it,
    # and only in solo play -- so every field may be left blank and a default
    # by class fills in.
    fallback = save_mod.Persona.by_class(
        sheet.cls, sum(1 for s in party.sheets if s.cls == sheet.cls))
    print("\n  Who is this? Enter takes the default; only the model reads it.")
    try:
        name = input(f"    name   [{fallback.name}] ").strip() or fallback.name
        voice = input("    voice  [plain] ").strip()
        wants = input(f"    wants  [{fallback.wants}] ").strip() or fallback.wants
    except EOFError:
        name, voice, wants = fallback.name, "", fallback.wants
        print("    (taking the defaults)")
    party.sheets.append(sheet)
    personas.append(save_mod.Persona(name=name, voice=voice, wants=wants))
    where = save_mod.save_party(party, party_name, personas)
    print(f"\n=== {personas[-1].name}, {sheet.cls} level {sheet.level} ===")
    print(f"  build    {sheet.build or '(the only one)'}")
    print(f"  race     {sheet.race or '(none)'}")
    print(f"  powers   {', '.join(sheet.powers)}")
    print(f"  feats    {', '.join(sheet.feats) or '(none)'}")
    print(f"\n  party    {len(party.sheets)} character(s), saved to {where}")
    return 0


def play(path: str, *, seed: int, save_as: str, quiet: bool, resume: str = "",
         with_dm: bool = False, party_name: str = "", solo: bool = False,
         everyone: bool = False, no_llm: bool = False) -> int:
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
        if solo or everyone:
            campaign.control = (
                ["human"] + ["ai"] * (len(campaign.party.sheets) - 1)
                if solo else ["human"] * len(campaign.party.sheets)
            )
        if party_name:
            # A party somebody made by hand replaces the dealt one. The
            # module still says what level the adventure is written for, so
            # a mismatch is worth printing rather than silently playing.
            campaign.party = save_mod.load_party(party_name)
            campaign.personas = save_mod.load_personas(party_name)
            levels = {s.level for s in campaign.party.sheets}
            if levels != {module.party_level}:
                print(
                    f"   note: {party_name} is level "
                    f"{'/'.join(str(n) for n in sorted(levels))} and the "
                    f"adventure is written for {module.party_level}"
                )
        print(f"=== {module.id}, seed {seed}, party level {module.party_level} ===")

    director = None
    if solo or everyone:
        from combat_engine.story import beat as _b
        from combat_engine.story import llm

        if no_llm:
            director = _b.Director(scripted=True)
            print("   story: scripted, no model")
        else:
            roles = llm.roles_for(save_as or campaign.module)
            why = llm.reachable(roles["companion"])
            if why:
                print(why)
                return 2
            director = _b.Director(roles=roles)
            # **Every role, not just one.** A roles file can put the DM on
            # another machine while the companions stay local, and the
            # banner used to print one line naming the companion's model --
            # so a session running half on a desktop said so nowhere.
            for job in ("dm", "companion", "match"):
                role = roles[job]
                where = role.base_url.split("//")[-1]
                print(f"   {job:10} {role.model} at {where}")
            # Pay the cold load here, where it is visible, rather than in
            # the middle of the opening scene where it is indistinguishable
            # from a hang. Measured at 3m26s for a 9 GB model.
            for model, role in {
                (r.model, r.base_url): r for r in roles.values()
            }.items():
                note = "" if "127.0.0.1" in model[1] else \
                    "  (a cold one is minutes, not seconds)"
                print(f"   warming {model[0]}...{note}",
                      end="", flush=True)
                try:
                    print(f" {llm.warm(role):.0f}s", flush=True)
                except llm.NoModel as exc:
                    print(f"\n{exc}")
                    return 2
        played = sum(1 for i in range(len(campaign.party.sheets))
                     if campaign.controls(i) == "ai")
        print(f"   playing: {len(campaign.party.sheets) - played} human, {played} model")

    narrator = None
    if with_dm:
        from combat_engine.story import dm as dm_mod

        why = dm_mod.available()
        if why:
            # **Not a silent downgrade.** A run that quietly falls back to
            # the written text would look like the model narrating badly.
            print(why)
            return 2
        narrator = dm_mod.DM(campaign=campaign, module=module)
        print(f"   dungeon master: {narrator.model}")

    print(f"   {run_mod.party_line(campaign)}")
    print()

    fights = rounds = 0
    played = 0
    while not campaign.finished and played < LIMIT:
        scene = module.scene(campaign.scene)
        choice = (
            narrator.pick_exit(scene) if narrator
            else choose_exit(scene, module)
        )
        # **Live when a person is playing, batched otherwise.** A scene is
        # assembled and then printed, which is right for an instrument and
        # unplayable by hand: the first thing the CLI does is ask the human
        # what their character says, *before* the scene text has been
        # printed, because that text is waiting in `lines` for the scene to
        # end. You answer three prompts blind and then read what you were
        # answering. `check.py` is not a tty and keeps the batched form the
        # drivers assert on.
        live = sys.stdin.isatty() and not quiet and not narrator
        if live:
            _print_head(scene)
        made = run_mod.step(
            campaign, module, choice=choice,
            choose=narrator.choose if narrator else None,
            director=director, ask_human=declare,
            narrate=(lambda line: print(f"   {line}", flush=True))
            if live else None,
        )
        played += 1
        _print_step(made, quiet=quiet, narrated=bool(narrator),
                    already=live)
        if narrator:
            narrator.narrate(scene, made)
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
    if director is not None and director.spend.calls:
        print(f"  story           {director.spend}")
    if narrator:
        print(f"  dm              {narrator.spend()}")
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
    ap.add_argument(
        "--new-character", action="store_true", dest="new_character",
        help="make a character by choosing rather than being dealt one, and "
        "add them to a party. Needs --party to say which. Enter takes the "
        "default at every step, which is exactly what the dealer would have "
        "picked (#793)",
    )
    ap.add_argument(
        "--group", dest="party_name", metavar="NAME", default="",
        help="a party made by hand: the group --new-character adds to, and "
        "the group --play fields instead of the dealt four",
    )
    ap.add_argument(
        "--cls", metavar="CLASS", default="",
        help="skip the class question in --new-character",
    )
    ap.add_argument(
        "--level", type=int, default=1,
        help="what level to make a character at",
    )
    ap.add_argument(
        "--solo", action="store_true",
        help="you play one character and the model plays the rest of the "
        "party. Every actor declares at the prompt, then they are "
        "adjudicated together (#800)",
    )
    ap.add_argument(
        "--party", dest="everyone", action="store_true",
        help="you play everybody. The same loop; only who is asked changes",
    )
    ap.add_argument(
        "--no-llm", dest="no_llm", action="store_true",
        help="run the story loop with no model at all, from canned lines. "
        "What check.py uses: an instrument that needs a model is an "
        "instrument that goes red when nobody is serving",
    )
    ap.add_argument(
        "--dm", action="store_true",
        help="have a model narrate the adventure, play the people in it and "
        "make the choices a DM makes. Needs the optional anthropic SDK and "
        "credentials; it never rolls a die or decides a fight, and it cannot "
        "move the party to a scene the current one does not lead to (#794)",
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
    if args.new_character:
        if not args.party_name:
            raise SystemExit(
                "--new-character needs --group to say which group to add to."
            )
        return new_character(
            args.party_name, level=args.level, seed=args.seed, cls=args.cls,
        )
    if args.validate:
        return validate(args.validate)
    if args.resume and not args.play:
        raise SystemExit("--resume needs --play to say which module to resume into.")
    if args.play:
        return play(
            args.play, seed=args.seed, save_as=args.save,
            quiet=args.quiet, resume=args.resume or "", with_dm=args.dm,
            party_name=args.party_name, solo=args.solo, everyone=args.everyone,
            no_llm=args.no_llm,
        )
    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
