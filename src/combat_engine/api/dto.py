"""What crosses the wire.

The shapes here are the contract the browser page expects. The page came
across from the first attempt unchanged, so this file is written to fit it
rather than the other way round -- the consumer defines the contract.

Everything is either a number, a wire id (`pc_1`), or a string already passed
through `Wire`. No engine entity ids and no bare compendium refs leave here
except as the neutral label, which is what a deployment without a
localisation file serves.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

Square = tuple[int, int]


class ZoneDTO(BaseModel):
    id: str
    owner: str | None
    squares: list[Square]
    label: str


class ThingDTO(BaseModel):
    """Something on the board that is not a creature and not a zone.

    A trap, a piece of scenery, a conjuration. None of them has `Health`, so
    none arrives through `ActorDTO` -- `query.creatures` is
    `having(Health, Position)` -- and the page could not draw any of them.
    Scenery and conjurations are the worse half: they own their squares via
    `grid.place`, so they were already blocking movement with nothing on the
    board to explain why.

    Its `id` comes from a namespace of its own for the same reason a zone's
    does: `Wire._creatures` filters on `Health`, so `wire.id` returns `None`
    for all three.
    """

    id: str
    #: `trap`, `scenery` or `conjuration`.
    kind: str
    squares: list[Square]
    label: str
    #: Trap only: it has fired and not reset. A sprung trap is still drawn --
    #: the flag never clears and a landmark is worth seeing.
    sprung: bool = False


class BoardDTO(BaseModel):
    width: int
    height: int
    blocking: list[Square]
    difficult: list[Square]
    obscuring: list[Square] = Field(default_factory=list)
    zones: list[ZoneDTO]
    things: list[ThingDTO] = Field(default_factory=list)


class ConditionDTO(BaseModel):
    """One live effect, with what it does and when it ends.

    `ActorDTO.conditions` beside this is the short word list for chips. This
    is the effect records, and it is the only place a duration exists --
    "is that thing still burning" is answered by `ongoing 5 fire` plus
    `save ends`, not by the word "ongoing" on a chip.
    """

    name: str
    text: str
    duration: str
    source: str | None
    ongoing: int = 0
    ongoing_type: str | None = None
    save_ends: bool = False


class PowerDTO(BaseModel):
    """One line of a creature's kit, available or not.

    The action list is what is legal *from where you are standing*, which
    hides the attack you would get by closing -- exactly when a player needs
    to weigh it. So this is the whole kit, and `reason` says why an entry
    cannot be used. Where distance is the answer, `reason` is the number.
    """

    name: str
    action: str
    cost: str
    usage: str
    range_text: str
    keywords: list[str] = Field(default_factory=list)
    attack_text: str | None = None
    damage: str | None = None
    requirement_text: str | None = None
    hit_text: str | None = None
    miss_text: str | None = None
    effect_text: str | None = None
    targets: str = ""
    available: bool = True
    reason: str | None = None
    squares: list[Square] = Field(default_factory=list)
    #: For an area power, what each aim square in `squares` would cover,
    #: keyed `"x,y"`. Empty for everything else. `squares` says where a blast
    #: may be *pointed*, which is not where it lands, and the shape it makes
    #: is a rule -- so the page is handed it rather than working it out.
    #: What this power **covers**, for a row there is nothing to click on.
    #: A non-attack burst or blast takes no aim, so `squares` is empty and
    #: the board drew nothing at all -- 263 rows of the 1441 burst and blast
    #: rows. Kept separate from `squares` on purpose: that field also decides
    #: what a board click will accept, and a square lit there but refused by
    #: `Session.aim` is the dead click #139 removed.
    shows: list[Square] = Field(default_factory=list)
    footprints: dict[str, list[Square]] = Field(default_factory=dict)
    aimed: list[int] = Field(default_factory=list)
    option_index: int | None = None
    option_indices: list[int] = Field(default_factory=list)
    option_label: str | None = None
    affordable: bool = True
    pays: str | None = None
    cost_note: str | None = None


class ActorDTO(BaseModel):
    """A creature, in as much detail as choosing a target needs."""

    id: str
    label: str
    side: str
    square: Square
    squares: list[Square]
    hp: int
    hp_max: int
    temp_hp: int = 0
    surges: int = 0
    surges_max: int = 0
    bloodied: bool = False
    bloodied_value: int = 0
    dead: bool = False
    ac: int = 10
    fort: int = 10
    ref: int = 10
    will: int = 10
    conditions: list[str] = Field(default_factory=list)
    effects: list[ConditionDTO] = Field(default_factory=list)
    traits: list[PowerDTO] = Field(default_factory=list)
    is_current: bool = False
    level: int = 1
    role: str | None = None
    rank: str = "standard"
    size: str = "medium"
    speed: int = 6
    initiative_mod: int = 0
    senses: str | None = None
    mtype: str | None = None
    subtypes: str | None = None
    origin: str | None = None
    resist: str | None = None
    immune: str | None = None
    vulnerable: str | None = None
    #: How dangerous this creature is: its best case over three rounds as a
    #: share of the **opposing** side's whole health pool. So 0.25 means "could
    #: account for a quarter of the other side in three rounds", and two
    #: creatures on one board are comparable.
    #:
    #: **Not a hit probability**, which is what this used to carry -- the two are
    #: both small floats and a consumer cannot tell them apart by looking. #262.
    threat: float = 0.0


class ForecastDTO(BaseModel):
    hit_chance: float
    expected_damage: float
    kills_likely: int = 0
    self_risk: float = 0.0
    ally_damage: float = 0.0
    summary: str = ""


class OptionDTO(BaseModel):
    """One legal action. `index` is its position in the engine's own list.

    That position is the wire id for an action, so sorting a rendered list
    cannot change what a click does.
    """

    index: int
    kind: str
    label: str
    cost: str
    targets: list[str] = Field(default_factory=list)
    #: Where a move, run or shift ends up. It was only ever in the label
    #: ("move to (3, 4)") and at `path[-1]`, so anything wanting to match a
    #: clicked square to an option had to parse prose or trust that a path's
    #: last square is its destination.
    dest: Square | None = None
    origin: Square | None = None
    affected: list[Square] = Field(default_factory=list)
    path: list[Square] = Field(default_factory=list)
    forecast: ForecastDTO | None = None
    notes: list[str] = Field(default_factory=list)
    pays: str = ""
    affordable: bool = True
    cost_note: str | None = None
    score: float = 0.0


class EventDTO(BaseModel):
    seq: int
    kind: str
    actor: str | None = None
    target: str | None = None
    text: str = ""
    data: dict[str, Any] = Field(default_factory=dict)


class MovementDTO(BaseModel):
    """Where this creature may walk, and what it would cost it to.

    `free` and `risky` split the same set of reachable squares by whether
    the way there provokes -- not by how much movement it spends. The
    legend on the page has said "move, provokes" since it was written while
    the server was sorting by cost, and the two had never agreed.
    """

    free: list[Square] = Field(default_factory=list)
    risky: list[Square] = Field(default_factory=list)
    shift: list[Square] = Field(default_factory=list)
    #: Every square a **run** reaches -- speed + 2, and you grant combat
    #: advantage for it. A superset of `free` and `risky`. The engine has
    #: offered one `run` option per square for a while and this list was
    #: missing, so the only surface that could run was the enumerated one.
    run: list[Square] = Field(default_factory=list)
    #: The route to each reachable square, keyed "x,y". What the page draws
    #: when the player points at one.
    paths: dict[str, list[Square]] = Field(default_factory=dict)
    #: Why a risky square is risky, keyed "x,y".
    warnings: dict[str, str] = Field(default_factory=dict)


class EconomyDTO(BaseModel):
    spent: list[str] = Field(default_factory=list)
    buys: dict[str, str] = Field(default_factory=dict)


class PendingAnswerDTO(BaseModel):
    index: int
    label: str
    squares: list[Square] = Field(default_factory=list)
    actor: str | None = None


class PendingDTO(BaseModel):
    """A question a power asked in the middle of resolving.

    "Which ally gets the opening", "where do you shift to". The action is
    genuinely suspended while this is on the wire; see `session.Turnstile`.
    """

    kind: str
    chooser: str
    prompt: str
    answers: list[PendingAnswerDTO]
    default: int = 0
    step: int = 1
    steps: int = 1


class EncounterStateDTO(BaseModel):
    id: str
    round: int
    seed: int
    status: str
    current: str | None
    awaiting_input: bool
    winner: str | None = None
    rounds: int | None = None
    board: BoardDTO
    actors: list[ActorDTO]
    options: list[OptionDTO] = Field(default_factory=list)
    roster: list[PowerDTO] = Field(default_factory=list)
    economy: EconomyDTO = Field(default_factory=EconomyDTO)
    movement: MovementDTO | None = None
    pending: PendingDTO | None = None
    seq: int = 0
    #: How much a level is worth in this fight. Not in the first attempt's
    #: contract; the page ignores what it does not know, and it belongs on
    #: the wire because it changes every number the page is showing.
    scaling: str = "full"


class TermDTO(BaseModel):
    """One named contribution to a build choice's score.

    The weight is already applied, so the terms of a choice sum to its score
    and the page does not need the weights table to explain anything. That is
    the whole reason this is a list of named numbers and not one number.
    """

    name: str
    value: float


class ChoiceDTO(BaseModel):
    """One build option, ranked, with its reasons.

    `label` goes through the same `Wire.power` the fight page uses, so with
    `CE_NAMES=off` it is the ref and nothing else. This is the first surface
    that shows a **race** and a **feat** to a human, which is the largest new
    name surface the project has added, and it must not be the one that leaks.
    """

    ref: str
    label: str
    score: float
    terms: list[TermDTO] = Field(default_factory=list)


class ChargenOptionsDTO(BaseModel):
    """What a character of this class and leg could take, best first.

    **Advisory.** Nothing here is chosen: the page ranks and explains and the
    human picks. The dealer that fields a headless fight samples from the same
    scores, and the two must not be confused -- `sample` lives on the other
    side of this wire and is never called here.
    """

    cls: str
    level: int
    build: str
    #: What the class's page calls that leg. Resolved by `Wire.build`, so it is
    #: the slug again when names are off.
    build_label: str = ""
    primary: str
    secondary: str
    swings_a_weapon: bool
    races: list[ChoiceDTO] = Field(default_factory=list)
    feats: list[ChoiceDTO] = Field(default_factory=list)
