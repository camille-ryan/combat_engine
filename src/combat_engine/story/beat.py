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
    #: True for a companion the model plays. **The DM treats the two
    #: differently**: a companion's intent is raw material it writes into
    #: prose, because the player never saw it; the person's own typed line is
    #: already on their screen and must come back untouched.
    #:
    #: **Last, not third.** Added in the middle, it silently took the
    #: `speech` argument of every positional `Intent(slot, name, speech,
    #: doing)` in the tree -- including the three in `affordance_match`,
    #: the driver that holds a live model to 3 of 3. Nothing went red;
    #: `ty` named it.
    played: bool = False

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

    #: This ruling ended the scene, so its fact is narration rather than
    #: something anybody in the room said or did. #807.
    exit: bool = False

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


@dataclass(frozen=True)
class Recalled:
    """A fact somebody in the party simply knew, and who knew it.

    **Who matters more than whether.** Five characters rolling at level 1
    pass an easy check 100% of the time and a moderate one 97-100%, so the
    band does not decide availability -- it decides whose mouth the fact
    comes out of, and that is what shapes the prose. The player's own
    recall is told to them directly; a companion's is something the
    companion says.
    """

    fact: str
    skill: str
    dc: int
    #: Every character who passed, in party order. Empty means nobody did
    #: and the fact is not in the scene.
    knew: list[tuple[int, str]] = field(default_factory=list)
    #: True when one of the knowers is the person at the keyboard.
    mine: bool = False


@dataclass
class Beat:
    """One exchange."""

    n: int
    situation: str
    intents: list[Intent] = field(default_factory=list)
    rulings: list[Ruling] = field(default_factory=list)
    reaction: str = ""
    #: What the party already knew, rolled when the scene opened. Only the
    #: first beat of a scene has any.
    recalled: list[Recalled] = field(default_factory=list)
    #: Which companions were asked to come in this beat. Empty is normal and
    #: is the common case -- see `Director.joins`.
    joined: list[int] = field(default_factory=list)
    #: Set when an affordance ended the scene; the id it leads to.
    leads_to: str = ""
    #: The closing line, when the affordance that ended the scene had one.
    #: Printed as narration. **Not given to the DM** -- see `Ruling.exit`.
    exit_line: str = ""


@dataclass
class Playing:
    """A roleplay scene in progress."""

    scene: Scene
    beats: list[Beat] = field(default_factory=list)
    #: Affordance ids already taken, for the `once` rule.
    spent: set[str] = field(default_factory=set)
    #: Facts the party has learnt, which later beats may refer back to.
    learnt: list[str] = field(default_factory=list)
    #: Lore facts already rolled for, so a `once` row is not re-rolled on
    #: a second visit. Carried in from the campaign, not reset per scene.
    asked: set[str] = field(default_factory=set)
    #: Affordance ids actually **won**. `spent` is not the same thing -- it
    #: includes failures, and a failed Perception does not reveal anybody.
    found: set[str] = field(default_factory=set)
    leads_to: str = ""

    def cast(self) -> tuple:
        """Who is in the scene as far as anybody can tell.

        An NPC with `unseen` set is not here until that affordance is won.
        **Not "here but keep quiet about them"** -- withheld from the prompt
        entirely, which is the call `Npc.hides` already makes for a fact and
        this file keeps re-learning: a name in a cast list is an invitation
        to write them a line, and no instruction above it outweighs that.
        """
        return tuple(
            n for n in self.scene.npcs
            if not n.unseen or n.unseen in self.found
        )

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

**Write in English, every word of both fields.** Not a phrase, not a \
clause, not one word in another script. If a word will not come in English, \
use a simpler English word.\
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
#: **Measured, n=10 per arm, `qwen2.5:7b` at 0.6, judged by a model held to
#: a positive and a negative control first.** Two facts per reply; `echo`
#: counts a note coming back word for word, `covered` a judge saying it got
#: across however worded:
#:
#:     old   echo 20/20   covered 20/20
#:     v2    echo  1/20   covered 14/20     <- this prompt
#:     v3    echo  5/20   covered 16/20
#:
#: `old` is not a DM. It is a copier: 10 of 10 samples came back *character
#: for character identical*, because restating a list needs no model at all.
#: That is what the live chapter-1 session read like -- three bullet facts
#: with blank lines between them, under the heading "DM:".
#:
#: Neither replacement dominates, so this is a choice and not an
#: improvement: v3 buys two more facts for a five-fold echo relapse. The
#: echo is the worse fault, so v2. **The 6 facts in 20 that v2 drops are a
#: real cost and are #809** -- they stay in `playing.learnt` and in the
#: campaign log, so nothing is lost from the record, but a player does not
#: hear them. v3 is the evidence that more prompt words trade one fault for
#: the other rather than fixing either; the answer there is structural.
#:
#: Word overlap cannot score coverage here, and the first version of this
#: probe used it and reported a collapse that was not there -- the arms
#: differ precisely in how much they re-word, so overlap is biased against
#: the one under test. A judge answers it; a judge with controls answers it
#: honestly.
_TURN_TO = """\
You decide who the next moment belongs to.

Most of the time a scene is carried by one or two people and the rest are \
listening. Answer "nobody" when nothing has happened that the others would \
react to -- that is the common case and it is not a failure. Name one \
person when the moment is theirs: somebody addressed them, or it touches \
what they want, or their skill is the thing the situation needs. Answer \
"everyone" only when the whole party is being asked something or the \
situation has changed for all of them.

Do not spread turns around to be fair. You are not taking turns.\
"""


_DM = """\
You write the replies of the people the party is talking to. Nobody else.

Write what THEY say back and what THEY do. Two or three sentences, in their \
voice.

Never say whether anything worked; that is already decided.
Never describe the party moving, arriving or leaving.

**Two kinds of party member, and they are handled oppositely.**

THE PLAYER's line was typed by the person reading you and is already on \
their screen. Never repeat it, never restate it, never write another one \
for them.

THE COMPANIONS' lines were not shown to anybody. They are **yours to \
write**: work what each of them said and did into your paragraph, in their \
voice, as part of what happens. Do not list them and do not caption them \
with their names on separate lines -- it is one piece of prose in which \
those things happen. Say only what they actually said or did; you are \
putting it into words, not deciding it.

**The facts you are given are notes, not lines.** Each one is something that
is now true. Deliver all of them the way the people here would -- in speech,
in what they do, in what shows on a face. Never copy a note back as a
sentence and never present them as a list. One short paragraph.

**A party member's line is what they said, not what is true.** If one of \
them refers to a thing that is not in the scene, that thing is not there and \
you do not describe it. The scene and the facts below are all that exists.

**Only the people listed under WHO IS HERE are here.** The scene will \
mention others -- who runs the place, who is feared, who has gone missing. \
They are elsewhere. Do not give them a line, an entrance or an action.

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

    def joins(self, playing: Playing, actors: list[Actor]) -> list[int]:
        """Which companions speak up this beat. The human always does.

        **Everyone acting every beat is not how a table works**, and it was
        the clunkiest thing about playing this: four declarations and a
        reply, four more declarations and a reply, whether or not three of
        those characters had anything to add. In real play the DM mostly
        talks to whoever is driving the scene and turns to the others when
        the moment is actually theirs.

        So the human is asked every beat -- they are the one at the keyboard
        and the scene is theirs to drive -- and this decides who else comes
        in. One name, everyone, or nobody.

        It is a **classification over a closed set**, which is the side of
        the line a small model is on: 3 of 3 matching against a list where
        it was 1 of 3 judging freely (#801). The enum means it cannot name
        somebody who is not in the party.
        """
        played = [a for a in actors if a.played]
        if self.scripted or not played:
            # Everyone, so an instrument sees the whole loop and the
            # existing assertions about a four-actor beat still hold.
            return [a.slot for a in played]
        by_name = {a.name: a.slot for a in played}
        schema = {
            "type": "object",
            "properties": {"who": {
                "enum": [*by_name, "everyone", "nobody"]}},
            "required": ["who"],
        }
        told = [
            f"THE SCENE: {playing.scene.seen}",
            "THE PARTY MEMBERS YOU MAY TURN TO:\n" + "\n".join(
                f"- {a.name}, a {a.cls}"
                + (f", who wants {a.wants}" if a.wants else "")
                for a in played
            ),
        ]
        if playing.recent():
            told.append("WHAT JUST HAPPENED:\n" + playing.recent())
        got = llm.structured(
            self.roles["match"],
            [
                {"role": "system", "content": _TURN_TO},
                {"role": "user", "content": "\n\n".join(told)},
            ],
            schema,
        )
        self.spend.note("turn", ok=bool(got))
        who = str(got.get("who", "nobody"))
        if who == "everyone":
            return [a.slot for a in played]
        if who in by_name:
            return [by_name[who]]
        return []

    def declare(self, actor: Actor, playing: Playing, situation: str) -> Intent:
        if self.scripted:
            # Deterministic, and deliberately plain: an instrument reading
            # this should be able to tell a loop that ran from a loop that
            # produced interesting noise.
            return Intent(
                slot=actor.slot, name=actor.name, played=True,
                speech=f"{actor.name} has something to say.",
                doing=f"{actor.name} looks around.",
            )
        scene = playing.scene
        who = [
            f"{n.name} -- {n.voice or 'speaking plainly'}"
            for n in playing.cast()
        ]
        told = [f"The scene: {scene.seen}"]
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
            slot=actor.slot, name=actor.name, played=True,
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
              rulings: list[Ruling],
              recalled: list[Recalled] | None = None) -> str:
        if self.scripted:
            facts = [r.fact for r in rulings if r.fact and not r.exit]
            facts += [r.fact for r in (recalled or []) if r.knew and not r.mine]
            return " ".join(facts) if facts else "The moment passes."
        scene = playing.scene
        who = [
            f"{n.name}: wants {n.wants}."
            + (f" Speaks {n.voice}." if n.voice else "")
            + ("" if not n.knows else " May say: " + "; ".join(n.knows))
            for n in playing.cast()
        ]
        # `hides` is not here and never is. See `module.Npc`.
        #
        # **`seen`, not `brief`, and that reverses what #805 decided.** The
        # reasoning there was that this reader *is* the DM, so it should have
        # the DM's text. Playing it refuted that in one scene: handed a brief
        # saying the friendly patron is not what he appears, the model put
        # the line in a gate sergeant's mouth and told the player, in the
        # opening conversation, that he is "a genial sort, but not what he
        # seems."
        #
        # The mistake was treating "the DM" as a reader. **Everything this
        # call produces is shown to the player**, so it is a writer of
        # player-facing text and the secrets have no business in its prompt
        # -- the same reasoning `Npc.hides` already rests on, which this
        # reader was routing around. A secret withheld from one field and
        # handed over in the field beside it is not withheld. #829.
        #
        # So **no prompt in this file gets `brief`.** It stays what a person
        # reading the module reads. What the DM needs to stay in character --
        # who is here, what they want, what they may say -- is below, and is
        # written for exactly that.
        told = [f"THE SCENE: {scene.seen}"]
        if who:
            told.append("WHO IS HERE:\n" + "\n".join(who))
        # **An intent that matched nothing changes nothing**, and the DM
        # has to be told which those were. It was not, and the result was
        # that the one thing this layer refuses -- the model deciding what
        # is true -- came back in through the door marked "reaction":
        #
        #   "I fly up to the rafters"  ->  "Well done, my friend. Up there,
        #                                   you can keep an eye on the place."
        #
        # A 1st-level fighter granted flight, in prose, with no roll and no
        # affordance. "I set the tavern on fire" was likewise treated as
        # having happened and then waved away. The matcher had answered
        # `none` to all of it, correctly; `none` means *no dice*, and
        # nothing downstream read it as *no effect*.
        nothing = {
            r.slot for r in rulings
            if not r.affordance or r.affordance == "none"
        } | {i.slot for i in intents
             if not any(r.slot == i.slot for r in rulings)}
        mine = [i for i in intents if not i.played]
        theirs = [i for i in intents if i.played]
        def mark(i: Intent) -> str:
            return f"{i}" + ("   [ATTEMPTED ONLY]" if i.slot in nothing else "")

        if mine:
            told.append(
                "THE PLAYER -- already on their screen, do not rewrite:\n"
                + "\n".join(mark(i) for i in mine))
        if theirs:
            told.append(
                "THE COMPANIONS -- not shown to anybody, write these into "
                "your paragraph:\n" + "\n".join(mark(i) for i in theirs))
        # **Only a companion's recall is the DM's to deliver.** What the
        # player themselves remembered is printed to them directly, in
        # their own second person -- handing it here would get it
        # paraphrased into somebody else's mouth, which is the fault the
        # `[ATTEMPTED ONLY]` split already exists for one row up.
        theirs_known = [r for r in (recalled or [])
                        if r.knew and not r.mine]
        if theirs_known:
            told.append(
                "WHAT A COMPANION KNOWS, unprompted. Have them say it, in "
                "their own words, as part of your paragraph:\n"
                + "\n".join(
                    f"- {r.knew[0][1]} knows: {r.fact}" for r in theirs_known))
        if nothing:
            told.append(
                "[ATTEMPTED ONLY] means it did not work and nothing in the "
                "world changed. Show them trying and show what they meet -- "
                "a refusal, an obstacle, somebody's reaction, or simply that "
                "it does not happen. Never show it succeeding.")
        # **Unattributed, and that is a fix.** Labelling each fact with the
        # party member who earned it -- "Pike: she adds a map to the fee" --
        # read to the model as *Pike* doing it, and the DM duly wrote a line
        # and an action for a party member, which the prompt forbids in as
        # many words. A fact is a thing that is now true, not a thing
        # somebody did.
        facts = [r.fact for r in rulings if r.fact and not r.exit]
        told.append(
            "WHAT IS NOW TRUE. **The player has already been shown these "
            "in plain words.** Do not restate them and do not explain "
            "them. Write what the people here say and do in the light of "
            "them -- a reaction, a change of manner, what somebody does "
            "next. Add nothing beyond them:\n"
            + "\n".join(f"- {f}" for f in facts)
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
        playing.beats[-1].reaction if playing.beats else scene.seen
    ) or scene.seen
    beat = Beat(n=len(playing.beats) + 1, situation=situation)

    # -- what the party already knows. First beat only: this is "what do you
    # know walking in", not something re-rolled each exchange.
    if not playing.beats:
        beat.recalled = _recall(playing, table, actors, party_level)
        playing.learnt += [r.fact for r in beat.recalled if r.knew]

    # -- declare. **The companions think while the person is typing.**
    #
    # Everybody declares at once and nobody sees anybody else's intent --
    # that is the design, and it is what makes this safe: `situation` is
    # fixed above and `declare` reads only previous beats, so a companion's
    # answer does not depend on the human's line and never did. Starting
    # the work before the prompt is therefore **identical in behaviour** and
    # reclaims the one genuinely idle stretch in a beat.
    #
    # Worth being precise about where the saving comes from. `fan_out` buys
    # nothing against a default ollama, which generates one request at a
    # time -- but a person deciding what to say is several seconds of a GPU
    # doing nothing, and that is the time this takes back. Both the `joins`
    # call and the declarations it leads to run inside one background job,
    # so the whole chain overlaps the typing rather than just its tail.
    def companions() -> tuple[list[int], list[Intent | None]]:
        joining = set(director.joins(playing, actors))
        chosen = [a for a in actors if a.played and a.slot in joining]
        return (
            [a.slot for a in chosen],
            llm.fan_out([
                (lambda a=a: director.declare(a, playing, situation))
                for a in chosen
            ]),
        )

    pending = llm.start(companions)

    for actor in actors:
        if actor.played:
            continue
        speech, doing = ask_human(actor, situation)
        if speech or doing:
            beat.intents.append(Intent(
                slot=actor.slot, name=actor.name, played=False,
                speech=speech, doing=doing))

    got = pending.get()
    slots, theirs = got if got is not None else ([], [])
    beat.joined = slots
    for intent in theirs:
        if intent is not None and (intent.speech or intent.doing):
            beat.intents.append(intent)
    beat.intents.sort(key=lambda i: i.slot)

    # -- match, then roll
    picks = director.match(playing, beat.intents)
    for intent in beat.intents:
        wanted = picks.get(intent.slot, "none")
        chosen = scene.affordance(wanted) if wanted != "none" else None
        if (chosen is not None and chosen.leads_to and intent.played):
            # **A companion does not decide the party leaves.** Playing solo,
            # both transitions in a scene were taken by model-played
            # characters -- the wizard decided we would stop asking
            # questions and the ranger accepted the job -- while the person
            # at the keyboard was mid-conversation. The scene is theirs to
            # drive; a companion saying "let us get on with it" is a line,
            # not a decision.
            #
            # Costs nothing in `--party`, where every slot is human. And
            # the fallback is unchanged: a scene nobody exits runs to
            # `max_beats` and takes its first exit.
            chosen = None
        if chosen is not None and chosen.once and chosen.id in playing.spent:
            # **Once means once, including twice in the same beat.** The
            # first version computed the open list before matching and only
            # spent an id afterwards, so two characters could take the same
            # affordance in one exchange -- measured, a cleric failed
            # `coax-the-dog` and a rogue passed it in the same beat, and the
            # DM was handed "the dog stays where it is" and "the dog comes
            # down" together and dutifully wrote both. The second character
            # is simply talking instead.
            chosen = None
        if chosen is None:
            beat.rulings.append(Ruling(slot=intent.slot, name=intent.name))
            continue
        playing.spent.add(chosen.id)
        if not chosen.rolls:
            # A thing a character can simply do. It still matters: the module
            # said it was possible, so its `win` text is now a fact.
            won, rolled, target = True, None, 0
        else:
            level = scene.level or party_level
            target = chosen.dc or dc_for(level, chosen.band)
            rolled = table.check(intent.slot, chosen.skill, target)
            won = rolled.success
        leaving = bool(chosen.leads_to) and won
        beat.rulings.append(Ruling(
            slot=intent.slot, name=intent.name, affordance=chosen.id,
            skill=chosen.skill if chosen.rolls else "",
            dc=target, roll=rolled, won=won,
            fact=chosen.win if won else chosen.lose,
            exit=leaving))
        if leaving:
            beat.leads_to = chosen.leads_to
            # **A transition's `win` is a stage direction, not a note.** It
            # is written as the party going somewhere -- "the party steps out
            # into the square" -- because that is what ending a scene is.
            # Handed to the DM under a heading reading "things the people
            # here say or do, never things a party member does", it made the
            # model write three party members acting in one reply, against
            # two prohibitions stated in the prompt verbatim. The data won.
            #
            # Withheld rather than forbidden, which is the call `Npc.hides`
            # already made for the same reason. #807.
            beat.exit_line = beat.rulings[-1].fact

    playing.learnt += [r.fact for r in beat.rulings if r.won and r.fact]
    # Won, not merely attempted: a failed Perception reveals nobody.
    playing.found |= {r.affordance for r in beat.rulings if r.won}

    # -- react
    beat.reaction = director.react(playing, beat.intents, beat.rulings,
                                   beat.recalled)
    playing.beats.append(beat)
    if beat.leads_to:
        playing.leads_to = beat.leads_to
    return beat


def _recall(playing: Playing, table: Table, actors: list[Actor],
            party_level: int) -> list[Recalled]:
    """Everybody rolls what they might know. Whoever passes, knows it.

    **Every character rolls their own**, rather than one roll for the party
    or the best modifier standing in for everyone. Two reasons and the
    second is the point of the feature: a character who is bad at History
    should be able to not know something, and the *set* of who knew is what
    decides how the fact reaches the player -- their own recall, or a
    companion telling them.

    A row whose `once` is set is rolled a single time per campaign, tracked
    on `Playing.asked`, because whether you know a thing is not re-decided
    by walking back into the room.
    """
    out: list[Recalled] = []
    for row in playing.scene.lore:
        key = f"{playing.scene.id}:{row.fact}"
        if row.once and key in playing.asked:
            continue
        playing.asked.add(key)
        # **The page's number first.** A band is the fallback for a module
        # that did not state one, and it is lossy -- this adventure prints
        # 15s that no band equals.
        target = row.dc or dc_for(playing.scene.level or party_level, row.band)
        knew: list[tuple[int, str]] = []
        mine = False
        for actor in actors:
            if table.check(actor.slot, row.skill, target).success:
                knew.append((actor.slot, actor.name))
                mine = mine or not actor.played
        out.append(Recalled(fact=row.fact, skill=row.skill, dc=target,
                            knew=knew, mine=mine))
    return out


def play_scene(
    scene: Scene, table: Table, actors: list[Actor], director: Director,
    *, ask_human: AskHuman, party_level: int,
    after: Callable[[Beat], None] | None = None,
    asked: set[str] | None = None,
) -> Playing:
    """Run a roleplay scene to its end.

    `after` is called with each beat the moment it finishes. **A person
    playing needs it and nothing else does**: without it the whole scene is
    assembled before a word of it is printed, so a human is asked what they
    say in beat 2 having seen nothing of beat 1 -- not the companions'
    lines, not their own roll, not the reply. Four prompts into a
    conversation that has not visibly started.
    """
    playing = Playing(scene=scene, asked=set(asked or ()))
    while not playing.over:
        made = one_beat(playing, table, actors, director,
                        ask_human=ask_human, party_level=party_level)
        if after is not None:
            after(made)
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
