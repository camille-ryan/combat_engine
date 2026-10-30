"""A campaign, held open across HTTP requests, so a page can play it.

The fight has `session.py`; this is the same idea for the story loop, and
it exists because **the story loop blocks for a person in the middle of a
scene**. `beat.play_scene` runs beat after beat and calls
`ask_human(actor, situation)` when it wants a line; that call is an
ordinary synchronous one and the answer has to come from a browser
several seconds later.

`session.Turnstile` already solves exactly that for the fight -- the work
runs on a worker thread and parks on a queue when it needs an answer --
so this reuses it rather than growing a second copy of the threading. The
only thing it needed was `ask_free`, because a typed line is not a choice
from a list.

## One scene per request, and the lines come out as they happen

`POST /advance` starts one scene and returns immediately. The scene plays
on the worker, and every line reaches `Story.lines` the moment it exists
-- `Step.echo` already does that, and it was built for exactly this
reason on the CLI side: a scene assembled and then printed is unplayable,
because the first thing it does is ask what you say before showing you
what you are answering.

So the page polls or streams `lines` and sees the scene unfold, which is
also what makes a "thinking..." indicator possible later (#931).

## What this does not do

**It never reads `localization/names.json`.** A scene's prose and its
word for a creature come out of the user's own module file, which is
git-ignored; `wire.py` is the only place refs become names and nothing
here needs it. A monster the module gave no word for stays a ref, which
is what `play.py` already does.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from combat_engine.story import beat as beat_mod
from combat_engine.story import run as run_mod
from combat_engine.story.module import Module, load
from combat_engine.story.save import Campaign

from .session import Turnstile


@dataclass
class Story:
    """One campaign, its worker, and everything the page has been told."""

    id: str
    module: Module
    campaign: Campaign
    #: Every line so far, oldest first, each with the kind that decides how
    #: the page styles it. #930.
    lines: list[dict[str, Any]] = field(default_factory=list)
    #: Out-of-story remarks -- a budget clamp, the god-mode banner.
    notes: list[str] = field(default_factory=list)
    #: The party wins every fight and none is played. Off unless the page
    #: asks. `story/CLAUDE.md`: it hands over every fight and **says so,
    #: every time**, which is why the banner is a `note` line and the page
    #: has to show it.
    god: bool = False
    #: No model at all: every answer canned and deterministic. The page
    #: offers it so a machine with no ollama is still playable, and it is
    #: what `browser.py` drives -- an instrument that needs a server for a
    #: model goes red for the wrong reason.
    scripted: bool = False
    gate: Turnstile = field(default_factory=Turnstile)
    #: True once the module has no next scene.
    over: bool = False
    #: What the last scene did, for the page's header.
    outcome: str = ""

    def seen(self, line: run_mod.Line, scene: str) -> None:
        """A line, the moment it happens. Wired to `Step.echo`."""
        self.lines.append({
            "n": len(self.lines),
            "kind": getattr(line, "kind", "scene"),
            "text": str(line),
            "scene": scene,
        })


#: Every campaign this process is holding. Same shape as `session.SESSIONS`.
STORIES: dict[str, Story] = {}


def start(module_path: str, *, seed: int = 0, god: bool = False) -> Story:
    """Open a module and stand a party up at its first scene."""
    module = load(Path(module_path))
    campaign = run_mod.begin(module, seed=seed)
    # Solo: the person plays one character and the model plays the rest.
    # `story/CLAUDE.md` is explicit that without this every character
    # defaults to human, nobody declares, and the loop spins empty beats.
    campaign.control = (
        ["human"] + ["ai"] * (len(campaign.party.sheets) - 1))
    made = Story(id=uuid.uuid4().hex[:12], module=module,
                 campaign=campaign, god=god)
    STORIES[made.id] = made
    return made


def advance(story: Story, *, director: beat_mod.Director | None = None) -> None:
    """Play the scene the campaign is on. Returns when it parks or ends."""
    if story.over or story.gate.busy:
        return
    scene = story.campaign.scene

    def ask(actor: beat_mod.Actor, situation: str) -> tuple[str, str]:
        said = story.gate.ask_free(actor.slot, "say", situation)
        if isinstance(said, dict):
            return str(said.get("speech", "")), str(said.get("doing", ""))
        return str(said), ""

    def body() -> None:
        made = run_mod.step(
            story.campaign, story.module,
            record=True, god=story.god,
            director=director,
            ask_human=ask,
            narrate=lambda line: story.seen(line, scene),
        )
        story.notes = list(made.notes)
        story.outcome = made.outcome
        story.over = story.campaign.finished or not made.next_id

    story.gate.run(body)


def say(story: Story, speech: str, doing: str) -> None:
    """Hand the worker the line the person typed."""
    story.gate.answer_free({"speech": speech, "doing": doing})


def state(story: Story) -> dict[str, Any]:
    """What the page needs to draw. The hand-maintained wire contract."""
    scene = (story.module.scene(story.campaign.scene)
             if story.campaign.scene else None)
    question = story.gate.question
    return {
        "id": story.id,
        "module": story.module.id,
        "scene": scene.id if scene else "",
        "scene_name": scene.name if scene else "",
        "scene_kind": scene.kind if scene else "",
        "lines": story.lines,
        "notes": story.notes,
        "outcome": story.outcome,
        "over": story.over,
        "god": story.god,
        "party": run_mod.party_line(story.campaign),
        # Set when the worker is parked waiting for the person to speak.
        "asking": (
            {"slot": question.chooser, "prompt": question.prompt}
            if question else None
        ),
    }
