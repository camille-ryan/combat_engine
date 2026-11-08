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
    #: **Which phase the DM is in, as the model itself reports it.** #931.
    #:
    #: `"thinking"` while a reasoning model is still reasoning,
    #: `"content"` from the first answer token, and `""` when nothing is
    #: being asked of a model. The page shows its indicator off this
    #: rather than off *"the worker is busy and has not asked anything"*,
    #: which is what `web/story.js` had to infer.
    #:
    #: **A model with no reasoning phase never sets `"thinking"`**, so the
    #: indicator simply never appears for it -- which is the right
    #: behaviour and comes free from reading ollama's field rather than
    #: timing anything. The local 7B has no such phase; the 14B has a long
    #: one, measured at 298 thinking chunks before the first of 113
    #: content chunks on one beat.
    #:
    #: Not a `lines` entry, deliberately: `run.Line` carries a kind from a
    #: closed set and an unknown one is **silently relabelled** `"scene"`,
    #: which once cost four rounds of diagnosis on 18 lines. A phase is
    #: not a line of the transcript -- it is what is happening to the
    #: transcript -- so it is a field of its own.
    phase: str = ""
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
    """Play the scene the campaign is on. Returns when it parks or ends.

    **The director is handed a phase sink, when there is a director.**
    #931. `Director.phases` makes `react` stream, so `story.phase` is the
    model's own report rather than the page inferring one from the worker
    being busy.

    Wired here rather than inside `Director` so a caller with no `Story`
    -- `play.py`, `drivers.py` -- is untouched, and so the sink cannot
    outlive the request that made it.
    """
    if story.over or story.gate.busy:
        return
    scene = story.campaign.scene
    if director is not None:
        def phase(which: str, chunk: str) -> None:
            del chunk
            story.phase = which
        director.phases = phase

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
        # **Cleared when the beat ends**, so the page stops showing a
        # phase for a model nobody is asking. A flag nothing clears is
        # the fault `campaign.denied` and the fight aftermath both record.
        story.phase = ""
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
        # **The DM's own phase**, where `thinking` used to be inferred from
        # the worker being busy. #931. Empty whenever no model is being
        # asked, and never `thinking` for a model with no reasoning phase.
        "phase": story.phase,
        "party": run_mod.party_line(story.campaign),
        # Set when the worker is parked waiting for the person to speak.
        "asking": (
            {"slot": question.chooser, "prompt": question.prompt}
            if question else None
        ),
    }
