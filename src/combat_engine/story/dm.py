"""A model as dungeon master: it narrates and decides, the engine adjudicates.

Camille's call -- the story engine calls a model at runtime to narrate scenes,
play the people in them, and make the choices a DM makes. Roleplay is half of
what a module is and no amount of structured data writes it. #794.

**This is the first network call in the repository.** A grep for `anthropic`,
`openai`, `requests` or `httpx` over `src/` and `scripts/` found nothing
before this file; the only networking anywhere is `guides.py` fetching web
pages into a git-ignored cache and two instruments polling a server they
started themselves. So the rules want stating, not assuming.

## Four rules, and the code is shaped around them

**1. Dice stay in the engine.** The model never rolls, and it is not asked to
pretend. It names a character and a skill; `skills.check` rolls it and the
result comes back. Every fight is played by the policy and the model is told
the outcome. Combat stays byte-reproducible from a seed, `replay.py` keeps
working, and narration is nowhere in any fixture.

**2. It cannot leave the graph.** See `_SCHEMA_EXIT`: the exits of the current
scene are an `enum`, so the model cannot *express* an illegal move. This is
why decisions are structured outputs rather than tools -- a tool that refuses
an illegal scene is a tool the model can call wrongly and then argue with. A
schema it cannot violate needs no refusal path, no retry, and no test that the
refusal works.

**3. `--no-dm` has to keep working.** `check.py` runs this component and an
instrument that needs a key and a network goes red for the wrong reason. So
nothing here is on the engine's critical path: `run.step` does not know this
module exists, and every function here is a thing `play.py` calls *around* it.

**4. No printed name in this file.** It is tracked code. The module's prose
reaches the model at runtime, out of the git-ignored module file, and never
the other way: nothing written here is stored anywhere.

## Cost, which is a design input

The module in `modules/` is roughly 120k tokens of text. Sending it per scene
would be absurd and sending it once would still re-send it on every turn,
because the Messages API is stateless. The model gets a **digest** -- the
scene graph in outline, the party, the flags, what has happened -- plus the
current scene's own text, and nothing else. The digest and the system prompt
go first and carry `cache_control`, so the stable prefix is cached and only
the scene changes; `usage.cache_read_input_tokens` is the check that it is
actually working rather than being silently invalidated by something volatile
drifting into the prefix.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

from .challenge import Running, band_of
from .module import Module, Scene
from .run import Step, party_line
from .save import Campaign
from .table import Table

#: Opus 5. Thinking is on by default on this model -- a request that omits
#: `thinking` runs adaptive -- so it is not passed, and neither are
#: `temperature`, `top_p` or `top_k`, which are **rejected with a 400**.
MODEL = "claude-opus-5"

#: Room for the thinking and the prose together. `max_tokens` caps both on
#: this model, so a figure sized around the narration alone truncates
#: mid-sentence.
MAX_TOKENS = 8000

#: `low` through `max`. Narration is not a reasoning problem and the default
#: of `high` spends more than it is worth here; a decision between four exits
#: is less again. Overridable per `DM`.
NARRATE_EFFORT = "medium"
DECIDE_EFFORT = "low"

SYSTEM = """\
You are the dungeon master for a tabletop adventure. A rules engine is \
playing the game; you are telling it.

The engine has already decided everything mechanical by the time you see it. \
Dice are rolled by the engine, fights are fought by the engine, and hit \
points, powers and healing surges are the engine's. You will be told what \
happened. Never invent a roll, never say a character hit or missed unless \
you were told so, and never contradict the outcome you are given.

What is yours is the telling: what the place is like, what the people in it \
say and want, and what the party's choices felt like. Write for a group \
sitting at a table who cannot see any of the numbers.

Be brief. Two or three sentences for an ordinary beat, a short paragraph for \
something that matters. Lead with what changed. Do not recap what the players \
just did back at them, do not describe their feelings for them, and do not \
end by asking what they want to do unless you are genuinely handing over.

The adventure's own text is given to you as source material. Paraphrase it in \
your own words; it is a brief for you, not a script to read out.
"""

#: What a decision may be. The exits are filled in per scene, which is the
#: whole mechanism: an `enum` of the legal moves cannot express an illegal one.
_SCHEMA_EXIT: dict[str, Any] = {
    "type": "object",
    "properties": {
        "scene": {"type": "string", "enum": []},
        "because": {"type": "string", "description": "one short sentence"},
    },
    "required": ["scene", "because"],
    "additionalProperties": False,
}

_SCHEMA_CHECK: dict[str, Any] = {
    "type": "object",
    "properties": {
        "who": {"type": "string", "enum": []},
        "skill": {"type": "string", "enum": []},
        "how": {
            "type": "string",
            "description": "one short sentence on what they try, in the fiction",
        },
    },
    "required": ["who", "skill", "how"],
    "additionalProperties": False,
}


class NoModel(RuntimeError):
    """No SDK, or no credentials. The caller falls back to `--no-dm`."""


def client() -> Any:
    """An Anthropic client, or `NoModel` with the line that fixes it.

    Credentials are **not** checked for here beyond the SDK's own resolution:
    an unset `ANTHROPIC_API_KEY` does not mean there are none -- the SDK also
    reads `ANTHROPIC_AUTH_TOKEN` and an `ant auth login` profile, so a bare
    constructor works for somebody who has logged in. Asking for a key that is
    already configured is its own kind of wrong.
    """
    try:
        import anthropic
    except ImportError:
        raise NoModel(
            "a model DM needs the anthropic SDK, which is an optional "
            "dependency.\nRun: uv sync --extra dm\n"
            "Or play with --no-dm, which needs neither it nor a network."
        ) from None
    try:
        return anthropic.Anthropic()
    except Exception as exc:  # the SDK raises several shapes
        raise NoModel(
            f"the anthropic SDK could not be set up: {exc}\n"
            "Run `ant auth login`, or set ANTHROPIC_API_KEY, or play with "
            "--no-dm."
        ) from exc


def digest(campaign: Campaign, module: Module) -> str:
    """The stable half of the prompt: the campaign, in outline.

    Deliberately **not** the module's text: the scene graph as ids and names,
    and who the party is. 457 characters for the fixture module against about
    half a megabyte of adventure.

    **Only things that do not change.** Flags, the party's wounds and what
    has happened so far are all campaign state and all belong in the per-turn
    message instead -- a first draft put them here, and anything volatile in
    a cached prefix invalidates it every single turn, which is the one way to
    pay for caching and get none of it. `DM.spend` prints the hit rate so
    that is visible rather than assumed.

    Ordered deterministically for the same reason: a dict iterated in a
    different order is a different prefix.
    """
    lines = [
        f"Adventure: {module.id}",
        f"Party: level {module.party_level}, {len(campaign.party.sheets)} characters "
        + ", ".join(s.cls for s in campaign.party.sheets),
        "",
        "The scenes, in order, and what leads where:",
    ]
    for scene_id in sorted(module.scenes):
        scene = module.scenes[scene_id]
        where = " -> ".join(scene.exits) or "(ends the adventure)"
        lines.append(f"  {scene_id} [{scene.kind}] {scene.name} -> {where}")
    return "\n".join(lines)


@dataclass
class DM:
    """One campaign's narrator."""

    campaign: Campaign
    module: Module
    model: str = MODEL
    #: Everything said so far, so the telling has continuity. Trimmed, because
    #: a long campaign would otherwise grow without bound -- and the digest
    #: already carries the durable state, so old prose is the cheapest thing
    #: to drop.
    said: list[str] = field(default_factory=list)
    keep: int = 12
    _client: Any = None
    #: `(cache_read, cache_write, input, output)` so a caller can print what
    #: the caching is actually doing rather than assume it.
    usage: list[int] = field(default_factory=lambda: [0, 0, 0, 0])

    def _api(self) -> Any:
        if self._client is None:
            self._client = client()
        return self._client

    def _prefix(self) -> list[dict]:
        """System blocks, stable, with the cache breakpoint on the last one."""
        return [
            {"type": "text", "text": SYSTEM},
            {
                "type": "text",
                "text": digest(self.campaign, self.module),
                "cache_control": {"type": "ephemeral"},
            },
        ]

    def _count(self, usage: Any) -> None:
        self.usage[0] += getattr(usage, "cache_read_input_tokens", 0) or 0
        self.usage[1] += getattr(usage, "cache_creation_input_tokens", 0) or 0
        self.usage[2] += getattr(usage, "input_tokens", 0) or 0
        self.usage[3] += getattr(usage, "output_tokens", 0) or 0

    def _history(self) -> str:
        return "\n".join(self.said[-self.keep:])

    # -- narration ---------------------------------------------------------

    def narrate(self, scene: Scene, step: Step, *, show: bool = True) -> str:
        """Tell the table what just happened. Streamed, so it arrives as prose.

        Streaming is not decoration: `max_tokens` is high enough that a
        non-streaming call risks the SDK's own long-request guard, and a
        person waiting on a DM should see sentences rather than a pause.
        """
        told = [
            f"Scene: {scene.name or scene.id} ({scene.kind})",
            f"The adventure's own text: {scene.brief}" if scene.brief else "",
            f"Party now: {party_line(self.campaign)}",
        ]
        if self.campaign.flags:
            told.append(
                "Where the campaign stands: "
                + ", ".join(f"{k} {v}" for k, v in sorted(self.campaign.flags.items()))
            )
        if scene.kind == "combat":
            told.append(
                f"The fight is over and the party {step.outcome} it, "
                f"in {step.rounds} rounds. Do not re-fight it; describe how it went."
            )
            if step.lines:
                told.append("What the engine recorded: " + " | ".join(step.lines[1:]))
        elif scene.kind == "skill_challenge":
            told.append(
                f"The party {step.outcome} the challenge. The rolls, in order: "
                + " | ".join(ln.strip() for ln in step.lines[1:])
            )
        elif scene.kind == "rest":
            told.append("They rested. Say what that was like; keep it to a sentence or two.")

        text = self._stream(
            [
                {
                    "role": "user",
                    "content": (
                        (f"Earlier:\n{self._history()}\n\n" if self.said else "")
                        + "\n".join(t for t in told if t)
                    ),
                }
            ],
            effort=NARRATE_EFFORT,
            show=show,
        )
        self.said.append(f"[{scene.id}] {text}")
        return text

    def _stream(self, messages: list[dict], *, effort: str, show: bool) -> str:
        api = self._api()
        out: list[str] = []
        try:
            stream_cm = api.messages.stream(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=self._prefix(),
                output_config={"effort": effort},
                messages=messages,
            )
            with stream_cm as stream:
                for chunk in stream.text_stream:
                    out.append(chunk)
                    if show:
                        print(chunk, end="", flush=True)
                final = stream.get_final_message()
        except NoModel:
            raise
        except Exception as exc:  # several SDK error shapes
            raise _fail(exc) from exc
        if show:
            print()
        self._count(final.usage)
        # **Checked before the text is read.** A refused turn returns a
        # successful 200 with `stop_reason: "refusal"` and content that is
        # empty or partial, so code that indexes straight into it breaks on
        # exactly the request that most needed handling.
        if final.stop_reason == "refusal":
            return "(The DM declines to narrate this one.)"
        return "".join(out).strip()

    # -- decisions ---------------------------------------------------------

    def _decide(self, schema: dict, prompt: str) -> dict:
        """One structured answer. The schema is the guarantee, not a check."""
        api = self._api()
        try:
            got = api.messages.create(
                model=self.model,
                max_tokens=1024,
                system=self._prefix(),
                output_config={"effort": DECIDE_EFFORT, "format": {
                    "type": "json_schema", "schema": schema,
                }},
                messages=[{"role": "user", "content": prompt}],
            )
        except NoModel:
            raise
        except Exception as exc:  # several SDK error shapes
            raise _fail(exc) from exc
        self._count(got.usage)
        if got.stop_reason == "refusal":
            return {}
        text = next((b.text for b in got.content if b.type == "text"), "")
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}

    def pick_exit(self, scene: Scene) -> str:
        """Which way the party goes. `""` takes the scene's own first exit.

        Only asked when there is a real choice. One exit is not a decision and
        a model asked to make one will invent a reason, which is noise at
        best.
        """
        if len(scene.exits) < 2:
            return ""
        schema = json.loads(json.dumps(_SCHEMA_EXIT))
        schema["properties"]["scene"]["enum"] = list(scene.exits)
        got = self._decide(
            schema,
            f"The party has finished {scene.id}. Where do they go next, and "
            "why? Choose what follows from the fiction, not what is easiest.",
        )
        return str(got.get("scene", ""))

    def choose(self, run: Running, table: Table) -> tuple[int, str]:
        """A `challenge.Chooser`: who tries next, and with what.

        **This is the chooser, not a factory for one.** The first draft was
        `chooser(table) -> Chooser`, and the table does not exist when
        `run.step` is called -- `_challenge` lays it. `types.py` caught the
        mismatch before it ever ran, which is the whole argument for that
        instrument: the signature was wrong in a way no amount of reading the
        `--no-dm` path would have shown.

        The model names a character and a skill; `challenge.attempt` rolls it.
        A skill the challenge does not list is refused by the engine and costs
        nothing -- but the schema means it cannot be named in the first place,
        so the refusal is a belt to the schema's braces rather than the
        mechanism.
        """
        names = [s.cls for s in table.party.sheets]
        allowed = [
            s for s in (*run.scene.primary, *run.scene.secondary)
            if band_of(run, s)
            and not (s in run.scene.secondary and s in run.spent)
        ]
        if not allowed:
            return -1, ""
        schema = json.loads(json.dumps(_SCHEMA_CHECK))
        schema["properties"]["who"]["enum"] = names
        schema["properties"]["skill"]["enum"] = allowed
        got = self._decide(
            schema,
            f"Skill challenge: {run.scene.name or run.scene.id}. "
            f"{run.scene.brief}\n"
            f"Standing: {run.tally}. The next check is at the "
            f"{run.band_now} difficulty.\n"
            "Who tries, and with which skill? Spread the work around the "
            "party rather than leaning on one character.",
        )
        who, skill = str(got.get("who", "")), str(got.get("skill", ""))
        if who not in names or skill not in allowed:
            # The schema should make this unreachable. If it is ever reached,
            # fall back to the engine's own chooser rather than guessing -- a
            # wrong name here would roll the wrong character's dice and
            # nothing downstream would notice.
            from .challenge import taking_turns

            return taking_turns(run, table)
        if got.get("how"):
            self.said.append(f"[{run.scene.id}] {who}: {got['how']}")
        return names.index(who), skill

    # -- reporting ---------------------------------------------------------

    def spend(self) -> str:
        """What the caching actually did, rather than what it was meant to."""
        read, written, fresh, out = self.usage
        total = read + written + fresh
        share = f"{read / total:.0%}" if total else "n/a"
        return (
            f"tokens in {total} ({share} from cache: {read} read, "
            f"{written} written, {fresh} fresh), out {out}"
        )


def available() -> str:
    """`""` if the SDK is importable, else why not.

    **This is not a credential check and cannot be one.** The SDK resolves
    credentials lazily from four places -- two environment variables, an
    `ant auth login` profile on disk, and workload identity -- and none of
    them is validated until a request is made. Probing properly would cost a
    live call, which is a strange thing for a readiness check to do.

    So a missing key surfaces at the first real call, where `_fail` turns it
    into the same message with the same three fixes rather than a traceback.
    """
    try:
        client()
    except NoModel as exc:
        return str(exc)
    return ""


def _fail(exc: Exception) -> NoModel:
    """Turn an SDK error into something with a fix in it."""
    name = type(exc).__name__
    if "Authentication" in name or "PermissionDenied" in name:
        return NoModel(
            f"the model DM could not authenticate ({name}).\n"
            "Set ANTHROPIC_API_KEY, or run `ant auth login`, or play with "
            "--no-dm, which needs no credentials at all."
        )
    if "Connection" in name or "Timeout" in name:
        return NoModel(
            f"the model DM could not reach the API ({name}).\n"
            "Play with --no-dm until the network is back; the adventure is "
            "the same one and the engine does not care."
        )
    return NoModel(f"the model DM failed: {name}: {exc}")


def wanted() -> bool:
    """Has anybody configured credentials at all?

    A cheap pre-check so `play.py --dm` can say so before building a party.
    Deliberately generous: the SDK resolves several sources and a profile on
    disk is one of them, so this only reports the obvious absence.
    """
    return bool(
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or os.environ.get("ANTHROPIC_PROFILE")
    )
