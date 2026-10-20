"""Making a character by choosing, rather than being dealt one.

`chargen` builds every character in this project and **a human cannot drive
it**. Everything that exists is an advisor: `scripts/chargen.py` is a ranking
printer that constructs nothing, and `web/chargen.html` says so outright --
*"Nothing is chosen for you"* -- keeping its state in browser memory and
posting it nowhere. There is no POST under `/api/chargen` at all. Every path
ends at a ranked list and stops. #793.

A campaign starts with somebody making a character, so this is the step that
turns the list into a `Sheet`.

## Accepting every default must reproduce the dealt character

That is the property this file is built around, and it is not a nicety. The
replay fixtures, `Party.of` and every balance figure in the project rest on
the dealt party; a maker whose defaults differed would quietly fork the two
and nobody would notice until a number moved. So the defaults come from the
*same* dealers off the *same* key shapes `Party.of` uses -- `deal_race`,
`dealt_hand`, `feats_for`, `power_swap` -- rather than from anything
re-derived here. `drivers.py chargen_defaults` asserts it.

## An interview, not a prompt loop

`interview` yields `Question`s and takes back an index. The reason is
testability: a loop built on `input()` can only be exercised by a person, and
this needs to be checkable by an instrument. The CLI passes an answerer that
reads a line; a driver passes one that always takes the default; a model
could pass one of its own.

## What a human still cannot choose

Said here rather than discovered later. **Skills, ability scores and
equipment are still dealt.** `Character` has no `skills` field at all and
`_trained_skills` samples the class pool with `rng.sample`; `STANDARD_ARRAY`
is fixed and its ordering is forced by the build's primary and secondary;
`outfit` and `treasure` are automatic off `band(level)`. Those are `chargen`
changes rather than story-engine ones, and #793 carries them.

What a person can choose here is the class, the build, the race, the feats
and the hand -- which is what `Character` already models, and is the part a
player cares most about.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from random import Random

from combat_engine import chargen
from combat_engine.chargen import choices as ranking

from . import Sheet

#: How many ranked options to offer per question. Enough to choose from, few
#: enough to read. `choices.FEAT_TOP` is 24 and that is a list nobody reads.
SHOW = 8


@dataclass
class Option:
    """One thing that could be picked."""

    ref: str
    #: What it scored, for a reader who wants to know why it is in this order.
    #: `0.0` where the thing is not scored at all -- a class, a build.
    score: float = 0.0
    why: str = ""


@dataclass
class Question:
    """One step of the interview."""

    key: str
    prompt: str
    options: list[Option] = field(default_factory=list)
    #: Index into `options`. Taking it reproduces what `Party.of` would deal.
    default: int = 0
    #: True when the answer may be repeated -- feats and powers are lists.
    many: bool = False

    @property
    def dealt(self) -> str:
        return self.options[self.default].ref if self.options else ""


#: `(question) -> index into question.options`.
Answerer = Callable[[Question], int]


def take_default(question: Question) -> int:
    """The answerer a driver uses. See the module docstring."""
    return question.default


def _ranked(found: list[ranking.Choice], *, limit: int = SHOW) -> list[Option]:
    return [
        Option(
            ref=c.ref, score=c.score,
            why=", ".join(f"{k} {v:+.1f}" for k, v in c.why[:3]),
        )
        for c in found[:limit]
    ]


def _index_of(options: list[Option], ref: str) -> int:
    for i, option in enumerate(options):
        if option.ref == ref:
            return i
    return 0


def interview(
    answer: Answerer, *, level: int = 1, seed: int = 0, cls: str = "",
) -> Sheet:
    """Walk somebody through a character and hand back a `Sheet`.

    `cls` skips the first question, for a caller who already knows.
    """
    # -- class -------------------------------------------------------------
    if not cls:
        classes = sorted(chargen.CLASSES)
        question = Question(
            key="class",
            prompt="Which class?",
            options=[Option(ref=name) for name in classes],
            default=_index_of([Option(ref=n) for n in classes], "fighter"),
        )
        cls = question.options[answer(question)].ref
    cls = cls.strip().lower()

    # -- build -------------------------------------------------------------
    legs = list(chargen.BUILDS.get(cls, ()))
    build = chargen.build_of(cls, "")
    if len(legs) > 1:
        options = [
            Option(ref=leg.name, why=f"{leg.primary.value}/{leg.secondary.value}")
            for leg in legs
        ]
        question = Question(
            key="build",
            prompt=f"Which {cls} build?",
            options=options,
            # `build_of(cls, "")` is what every dealt character takes.
            default=_index_of(options, build.name),
        )
        build = chargen.build_of(cls, options[answer(question)].ref)

    # -- race --------------------------------------------------------------
    race = ""
    if chargen.DEAL_RACES:
        # **The dealer, off the key `Party.of` uses.** Re-deriving a "best
        # race" here would be a second opinion, and the two would drift.
        dealt = chargen.deal_race(Random(f"{seed}:{cls}:race"), cls, build)
        options = _ranked(ranking.race_options(cls, level, build))
        if dealt and dealt not in [o.ref for o in options]:
            options.insert(0, Option(ref=dealt, why="what you would be dealt"))
        question = Question(
            key="race",
            prompt="Which race?",
            options=options,
            default=_index_of(options, dealt),
        )
        race = options[answer(question)].ref if options else dealt

    # -- the hand ----------------------------------------------------------
    dealt_hand = chargen.dealt_hand(seed, cls, level, build)
    hand: list[str] = []
    for slot, printed in enumerate(dealt_hand):
        # Candidates for this slot are the powers the dealer could have put
        # there. `power_options` ranks them; the dealt one is the default.
        ranked = _ranked(ranking.power_options(list(dealt_hand), cls, build))
        if printed not in [o.ref for o in ranked]:
            ranked.insert(0, Option(ref=printed, why="what you would be dealt"))
        ranked = [o for o in ranked if o.ref not in hand]
        if not ranked:
            hand.append(printed)
            continue
        question = Question(
            key="power",
            prompt=f"Power {slot + 1} of {len(dealt_hand)}?",
            options=ranked,
            default=_index_of(ranked, printed),
            many=True,
        )
        hand.append(ranked[answer(question)].ref)

    # -- feats -------------------------------------------------------------
    dealt_feats = chargen.feats_for(
        cls, level, build,
        Random(f"{seed}:{cls}:{build.name}:feats"), list(dealt_hand), race,
    )
    taken: list[str] = []
    for slot in range(chargen.feat_slots(level, race)):
        legal = ranking.legal_feats(cls, level, build, race, taken)
        ranked = [o for o in _ranked(ranking.feat_options(legal, cls, build))
                  if o.ref not in taken]
        want = dealt_feats[slot] if slot < len(dealt_feats) else ""
        if want and want not in [o.ref for o in ranked]:
            ranked.insert(0, Option(ref=want, why="what you would be dealt"))
        if not ranked:
            break
        question = Question(
            key="feat",
            prompt=f"Feat {slot + 1} of {chargen.feat_slots(level, race)}?",
            options=ranked,
            default=_index_of(ranked, want) if want else 0,
            many=True,
        )
        taken.append(ranked[answer(question)].ref)

    # **The same swap `spawn` and `Party.of` both make.** A feat that hands
    # over a card takes one back, so a hand pinned before the swap is a hand
    # `spawn` would then alter -- the drift `Sheet.powers` exists to stop.
    return Sheet(
        cls=cls, level=level, build=build.name, race=race,
        powers=chargen.power_swap(list(hand), list(taken)),
        feats=taken,
    )


def dealt(cls: str, *, level: int = 1, seed: int = 0) -> Sheet:
    """What `Party.of` would deal for that class. The control."""
    return interview(take_default, level=level, seed=seed, cls=cls)
