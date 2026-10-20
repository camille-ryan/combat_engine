"""A roleplay scene, played a beat at a time.

Before this a roleplay scene printed the module's text and advanced. Nobody
spoke and nothing was decided. #800.

## The loop

    situation     the scene's brief on the first beat, the last reaction after
      -> declare  every actor says what they say and what they try
      -> match    each intent -> one affordance, or "none"
      -> roll     `skills.check` on the scratch board, in the engine
      -> react    one call: what the people in the scene say back
      -> again, or out through an affordance that leads somewhere

**One intent each, then adjudicate**, which is Camille's shape and is also
the only affordable one: the local model generates about 18 tokens a second
and serves one request at a time, so a beat is paced by how many characters
the model plays. Characters still answer each other, because each beat is
given the last few.

## Who decides what

The division is the whole design, and it follows from what a 7B measurably
can and cannot do (#801):

| | |
|---|---|
| what a character says | the model. It is good at this. |
| which affordance that attempts | the model, **matching a closed list** |
| whether it succeeds | `skills.check`, in the engine, on real dice |
| what is true afterwards | the module's `win`/`lose` text |
| how an NPC reacts | the model, given only facts it was handed |
| when the scene ends | the module -- `leads_to`, or `max_beats` |

The model never rolls, never decides a DC, never states a fact it was not
given, and cannot name an affordance that does not exist -- the enum is the
guarantee, the same one `dm.py` uses for scene exits.

## It runs with no model at all

`Director(scripted=True)` answers every call from canned text. That is what
`check.py` uses, and it is not a toy: the loop, the matching bookkeeping, the
`once` rule, the rolls and the ending are all the same code. Only the words
differ, which is the part no instrument can judge anyway.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field

from combat_engine.engine.skills import CheckResult

from . import llm
from .dc import dc as dc_for
from .module import Affordance, Scene
from .table import Table

#: How many beats of history a prompt carries. Enough that a character can
#: answer what was just said to them, few enough that a long scene does not
#: grow the prompt without bound -- the context is 8k and the scene brief,
#: the cast and the affordances are already in it.
RECALL = 3


@dataclass(frozen=True)
class Actor:
    """Somebody taking a turn in the scene."""

    slot: int
    name: str
    cls: str
    #: `"human"` or `"ai"`. The only difference between the two playstyles.
    control: str = "ai"
    voice: str = ""
    wants: str = ""

    @property
    def played(self) -> bool:
        return self.control == "ai"


@dataclass(frozen=True)
class Intent:
    """What one actor declared."""

    slot: int
    name: str
    speech: str = ""
    doing: str = ""

    def __str__(self) -> str:
        said = f'"{self.speech}"' if self.speech else ""
        does = f"({self.doing})" if self.doing else ""
        return f"{self.name}: {' '.join(x for x in (said, does) if x)}".strip()


@dataclass(frozen=True)
class Ruling:
    """What the engine made of one intent."""

    slot: int
    name: str
    #: An affordance id, or `"none"` when the intent simply happens.
    affordance: str = "none"
    skill: str = ""
    dc: int = 0
    roll: CheckResult | None = None
    won: bool = False
    #: The module's own `win` or `lose` text. The only fact the DM may state
    #: about this ruling.
    fact: str = ""

    @property
    def rolled(self) -> bool:
        return self.roll is not None

    def __str__(self) -> str:
        if self.affordance == "none":
            return f"  {self.name}: no roll"
        if not self.rolled:
            return f"  {self.name}: {self.affordance}"
        mark = "+" if self.won else "-"
        return (
            f"  {mark} {self.name}: {self.affordance} "
            f"[{self.skill} d20={self.roll.natural} "
            f"total={self.roll.total} vs {self.dc}]"
        )


@dataclass
class Beat:
    """One exchange."""

    n: int
    situation: str
    intents: list[Intent] = field(default_factory=list)
    rulings: list[Ruling] = field(default_factory=list)
    reaction: str = ""
    #: Set when an affordance ended the scene; the id it leads to.
    leads_to: str = ""


@dataclass
class Playing:
    """A roleplay scene in progress."""

    scene: Scene
    beats: list[Beat] = field(default_factory=list)
    #: Affordance ids already taken, for the `once` rule.
    spent: set[str] = field(default_factory=set)
    #: Facts the party has learnt, which later beats may refer back to.
    learnt: list[str] = field(default_factory=list)
    leads_to: str = ""

    @property
    def over(self) -> bool:
        return bool(self.leads_to) or len(self.beats) >= self.scene.max_beats

    def open_affordances(self) -> list[Affordance]:
        return [
            a for a in self.scene.affordances
            if not (a.once and a.id in self.spent)
        ]

    def recent(self) -> str:
        """The last few beats, for a prompt."""
        out: list[str] = []
        for beat in self.beats[-RECALL:]:
            out += [f"  {i.name} (your companion) said: {i}" for i in beat.intents]
            if beat.reaction:
                out.append(f"  They answered: {beat.reaction}")
        return "\n".join(out)


#: `(actor, situation) -> (speech, doing)`.
AskHuman = Callable[[Actor, str], tuple[str, str]]


# -- prompts ----------------------------------------------------------------
#
# Kept here rather than in `llm.py` so the model layer stays a transport and
# every word the model is given is in the file that explains why.

#: **"You are a player character being spoken TO" is doing real work here**,
#: and so is where the ask sits. The first draft framed the character and
#: then ended the prompt with the DM's last line; the model continued *that*
#: voice, and a cleric answered as the friar in 2 of 3 samples -- once
#: offering the party a map on the friar's behalf. Naming who said what, and
#: ending with "X, what do you say and do?", took it to 4 of 4 in character.
_COMPANION = """\
You are {name}, a {cls} and a member of the adventuring party. {voice}
Right now you want: {wants}

You are a PLAYER CHARACTER being spoken TO. You are not any of the other \
people in this scene.

Never speak or act for anyone but {name}. Never repeat a line somebody else \
just said. Do not decide whether anything you try works -- that is not yours \
to say.

Work with what is actually in the scene. Do not introduce an object, a \
person or a place that has not been mentioned to you. Reach for what is \
there.

Write in English.\
"""

_MATCH = """\
Match each declared intent to the one thing it attempts, or to "none".

"none" is the right answer for talking, asking a question, agreeing, \
refusing, looking at something in plain view, or anything with no real \
uncertainty. Most intents are "none". Do not stretch an intent to fit \
something it is not.\
"""

#: **The first draft parroted.** Told to "write what the people in the scene
#: say and do in response to the party" and then handed the party's lines, a
#: 7B reprinted them and added a line of its own. Saying whose replies it
#: writes -- and forbidding a party line outright -- fixed it in one go: the
#: friar answers, uses a fact he was given, and the party's words appear
#: nowhere.
_DM = """\
You write the replies of the people the party is talking to. Nobody else.

Write what THEY say back and what THEY do. Two or three sentences, in their \
voice.

Never repeat or restate what a party member said -- the reader just heard it.
Never write a line for a party member.
Never say whether anything worked; that is already decided.

**A party member's line is what they said, not what is true.** If one of \
them refers to a thing that is not in the scene, that thing is not there and \
you do not describe it. The scene and the facts below are all that exists.

Write in English.\
"""


def _match_schema(names: list[str], ids: list[str]) -> dict:
    return {
        "type": "object",
        "properties": {
            "picks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "who": {"type": "string", "enum": names},
                        "attempts": {"type": "string", "enum": [*ids, "none"]},
                    },
                    "required": ["who", "attempts"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["picks"],
        "additionalProperties": False,
    }


_SPEAK_SCHEMA = {
    "type": "object",
    "properties": {
        "speech": {"type": "string", "description": "what they say aloud"},
        "doing": {"type": "string", "description": "what they try to do"},
    },
    "required": ["speech", "doing"],
    "additionalProperties": False,
}


@dataclass
class Director:
    """Everything that needs a model, and the version that needs none."""

    roles: dict[str, llm.Role] = field(default_factory=llm.roles_for)
    spend: llm.Spend = field(default_factory=llm.Spend)
    #: No model at all. Every answer below is canned and deterministic, which
    #: is what lets `check.py` run the whole loop offline.
    scripted: bool = False

    # -- declaring ---------------------------------------------------------

    def declare(self, actor: Actor, playing: Playing, situation: str) -> Intent:
        if self.scripted:
            # Deterministic, and deliberately plain: an instrument reading
            # this should be able to tell a loop that ran from a loop that
            # produced interesting noise.
            return Intent(
                slot=actor.slot, name=actor.name,
                speech=f"{actor.name} has something to say.",
                doing=f"{actor.name} looks around.",
            )
        scene = playing.scene
        who = [
            f"{n.name} -- {n.voice or 'speaking plainly'}" for n in scene.npcs
        ]
        told = [f"The scene: {scene.brief}"]
        if who:
            told.append("Who is here, speaking to you: " + "; ".join(who))
        if playing.learnt:
            told.append("What the party has worked out: " + "; ".join(playing.learnt))
        if playing.recent():
            told.append("What just happened:\n" + playing.recent())
        elif situation:
            told.append(f"What just happened:\n  {situation}")
        # **Last, and it has to be last.** See `_COMPANION`: whatever ends the
        # prompt is the voice the model continues, so the prompt ends by
        # naming this character and asking them.
        told.append(
            f"{actor.name}, what do you say, and what do you do? "
            "One sentence each, in their voice."
        )
        got = llm.structured(
            self.roles["companion"],
            [
                {"role": "system", "content": _COMPANION.format(
                    name=actor.name, cls=actor.cls,
                    voice=actor.voice or "", wants=actor.wants or "to get through this",
                )},
                {"role": "user", "content": "\n\n".join(told)},
            ],
            _SPEAK_SCHEMA,
        )
        self.spend.note("companion", ok=bool(got))
        return Intent(
            slot=actor.slot, name=actor.name,
            speech=str(got.get("speech", "")).strip(),
            doing=str(got.get("doing", "")).strip(),
        )

    # -- matching ----------------------------------------------------------

    def match(self, playing: Playing, intents: list[Intent]) -> dict[int, str]:
        """`slot -> affordance id or "none"`, for every intent.

        **One call for all of them**, which is both what the measurement in
        #801 was taken on -- three intents, one call, 3 of 3 -- and the only
        affordable shape, since a default ollama generates one request at a
        time.
        """
        open_ = playing.open_affordances()
        if not open_ or not intents:
            return {i.slot: "none" for i in intents}
        if self.scripted:
            # The scripted loop takes nothing. It exercises the bookkeeping
            # around matching without pretending to a judgement it has not
            # made -- a canned "always take the first affordance" would make
            # the `once` rule and the ending look tested when they were only
            # being driven.
            return {i.slot: "none" for i in intents}

        names = [i.name for i in intents]
        ids = [a.id for a in open_]
        told = [
            "THINGS THAT CAN BE ATTEMPTED HERE:",
            *(f"- {a.id}: {a.what}" for a in open_),
            "",
            "DECLARED INTENTS:",
            *(f"- {i}" for i in intents),
        ]
        got = llm.structured(
            self.roles["match"],
            [
                {"role": "system", "content": _MATCH},
                {"role": "user", "content": "\n".join(told)},
            ],
            _match_schema(names, ids),
        )
        self.spend.note("match", ok=bool(got))
        by_name = {i.name: i.slot for i in intents}
        out = {i.slot: "none" for i in intents}
        for pick in got.get("picks", ()):
            slot = by_name.get(str(pick.get("who", "")))
            wanted = str(pick.get("attempts", "none"))
            if slot is not None and (wanted == "none" or wanted in ids):
                out[slot] = wanted
        return out

    # -- reacting ----------------------------------------------------------

    def react(self, playing: Playing, intents: list[Intent],
              rulings: list[Ruling]) -> str:
        if self.scripted:
            facts = [r.fact for r in rulings if r.fact]
            return " ".join(facts) if facts else "The moment passes."
        scene = playing.scene
        who = [
            f"{n.name}: wants {n.wants}."
            + (f" Speaks {n.voice}." if n.voice else "")
            + ("" if not n.knows else " May say: " + "; ".join(n.knows))
            for n in scene.npcs
        ]
        # `hides` is not here and never is. See `module.Npc`.
        told = [f"THE SCENE: {scene.brief}"]
        if who:
            told.append("WHO IS HERE:\n" + "\n".join(who))
        told.append("WHAT THE PARTY JUST DID:\n" + "\n".join(str(i) for i in intents))
        facts = [f"{r.name}: {r.fact}" for r in rulings if r.fact]
        told.append(
            "WHAT IS NOW TRUE (state only these):\n" + "\n".join(facts)
            if facts else
            "NOTHING NEW IS TRUE. Nobody learnt anything; react only."
        )
        text = llm.chat(
            self.roles["dm"],
            [
                {"role": "system", "content": _DM},
                {"role": "user", "content": "\n\n".join(told)},
            ],
        ).strip()
        self.spend.note("dm", ok=bool(text))
        return text or "The moment passes."


# -- the loop ---------------------------------------------------------------


def one_beat(
    playing: Playing, table: Table, actors: list[Actor], director: Director,
    *, ask_human: AskHuman, party_level: int,
) -> Beat:
    """Declare, match, roll, react. One exchange."""
    scene = playing.scene
    situation = (
        playing.beats[-1].reaction if playing.beats else scene.brief
    ) or scene.brief
    beat = Beat(n=len(playing.beats) + 1, situation=situation)

    # -- declare. Humans first, so a person is never waiting on a model only
    # to find the scene already moved under them.
    for actor in actors:
        if actor.played:
            continue
        speech, doing = ask_human(actor, situation)
        if speech or doing:
            beat.intents.append(
                Intent(slot=actor.slot, name=actor.name, speech=speech, doing=doing))
    played = [a for a in actors if a.played]
    for intent in llm.fan_out(
        [(lambda a=a: director.declare(a, playing, situation)) for a in played]
    ):
        if intent is not None and (intent.speech or intent.doing):
            beat.intents.append(intent)
    beat.intents.sort(key=lambda i: i.slot)

    # -- match, then roll
    picks = director.match(playing, beat.intents)
    for intent in beat.intents:
        wanted = picks.get(intent.slot, "none")
        chosen = scene.affordance(wanted) if wanted != "none" else None
        if chosen is None:
            beat.rulings.append(Ruling(slot=intent.slot, name=intent.name))
            continue
        playing.spent.add(chosen.id)
        if not chosen.rolls:
            # A thing a character can simply do. It still matters: the module
            # said it was possible, so its `win` text is now a fact.
            beat.rulings.append(Ruling(
                slot=intent.slot, name=intent.name, affordance=chosen.id,
                won=True, fact=chosen.win))
        else:
            level = scene.level or party_level
            target = dc_for(level, chosen.band)
            rolled = table.check(intent.slot, chosen.skill, target)
            beat.rulings.append(Ruling(
                slot=intent.slot, name=intent.name, affordance=chosen.id,
                skill=chosen.skill, dc=target, roll=rolled,
                won=rolled.success,
                fact=chosen.win if rolled.success else chosen.lose))
        if chosen.leads_to and beat.rulings[-1].won:
            beat.leads_to = chosen.leads_to

    playing.learnt += [r.fact for r in beat.rulings if r.won and r.fact]

    # -- react
    beat.reaction = director.react(playing, beat.intents, beat.rulings)
    playing.beats.append(beat)
    if beat.leads_to:
        playing.leads_to = beat.leads_to
    return beat


def play_scene(
    scene: Scene, table: Table, actors: list[Actor], director: Director,
    *, ask_human: AskHuman, party_level: int,
) -> Playing:
    """Run a roleplay scene to its end."""
    playing = Playing(scene=scene)
    while not playing.over:
        one_beat(playing, table, actors, director,
                 ask_human=ask_human, party_level=party_level)
    return playing


def silent(_actor: Actor, _situation: str) -> tuple[str, str]:
    """An `AskHuman` that says nothing. What a headless run uses."""
    return "", ""


def as_json(playing: Playing) -> list[dict]:
    """A scene's beats, for the campaign log (#799)."""
    return [
        {
            "beat": b.n,
            "situation": b.situation,
            "intents": [
                {"who": i.name, "speech": i.speech, "doing": i.doing}
                for i in b.intents
            ],
            "rulings": [
                {
                    "who": r.name, "attempts": r.affordance, "skill": r.skill,
                    "dc": r.dc, "won": r.won, "fact": r.fact,
                    "d20": r.roll.natural if r.roll else 0,
                    "total": r.roll.total if r.roll else 0,
                }
                for r in b.rulings
            ],
            "reaction": b.reaction,
            "leads_to": b.leads_to,
        }
        for b in playing.beats
    ]


def dumps(playing: Playing) -> str:
    return json.dumps(as_json(playing))
