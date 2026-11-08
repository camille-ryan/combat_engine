"""Skill powers for one skill: the six that print at levels 2, 6 and 10.

`cls` is the skill rather than a class -- see this package's `__init__`.

Two rows are about riding, and the engine already has the whole of it:
`Relation.RIDDEN_BY`, `c.ride`/`c.dismount`, `query.may_ride` holding the
size rule and its exception, and `actions._mounting` offering mount and
dismount as the printed move actions. So a card about mounting writes the
mounting and not a mechanism.

`p9329`'s "in a natural environment" cannot be said: `World.terrain` is
initialised empty and nothing in `src/` writes a word into it, so every
`c.terrain(...)` gate in the tree is False in every fight -- `f2718` records
the measurement. It carries `story.terrain_words` for that clause.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    DEFENCES,
    EACH_ALLY,
    ENCOUNTER,
    FREE,
    MINOR,
    MOVE,
    PERSONAL,
    SELF,
    YOU_AND_EACH_ALLY,
    Cast,
    CloseBurst,
    Initiative,
    Relation,
    Trigger,
    When,
    World,
    power,
    query,
)
from combat_engine.engine.events import InitiativeRolled, RoundEnd

#: The going `p11585` names -- "trees, underbrush, or other natural growth".
#: `forest` is the word `c.zone(difficult=)` actually writes today and the
#: other three are printed by cards and written by nothing yet, which
#: `cast.DIFFICULT_LABELS` keeps deliberately distinct from a typo.
_GROWTH = ("forest", "trees", "underbrush", "natural growth")


def _mounted(world: World, eid: int) -> bool:
    """"You must be mounted on a willing creature." The rider's side of
    `Relation.RIDDEN_BY`, which is what `c.mount` reads."""
    return bool(world.relations.sources(Relation.RIDDEN_BY, eid))


def _my_initiative(world: World, me: int, ev: object) -> bool:
    """My own initiative check, which is announced for the opening rolls as
    well as for a reroll -- `Encounter.start` arms the triggers before
    `_roll_initiative` precisely so a row of this shape can hear them."""
    return getattr(ev, "actor", None) == me


# -- level 2 ----------------------------------------------------------------


@power(
    "p11584",
    level=2,
    cls="nature",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    requires=_mounted,
    requires_text="you must be mounted on a willing creature",
)
def p11584(c: Cast) -> None:
    """Untyped: the card prints no word in front of "bonus", and writing
    `kind="power"` there would stop it stacking where the page stacks it.

    `once=True` and the start of the next turn are the two halves of "your
    next attack before the start of your next turn" -- the window and the
    one use inside it.
    """
    c.bonus("damage", 2, on=c.me, until=When.SONT, once=True)


@power(
    "p9329",
    level=2,
    cls="nature",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you would make an initiative check in a natural environment",
    on=Trigger(InitiativeRolled, _my_initiative, "you make an initiative check"),
    dropped=("story.terrain_words",),
)
def p9329(c: Cast) -> None:
    """Both halves play; the environment is the dropped clause.

    **The substitution goes through `c.initiative`, not `c.bonus`.**
    `Initiative.bonus` is read before the d20 and setting `ev.rolled` writes
    a copy the sort never looks at, so the amount is handed to
    `Encounter.adjust_initiative`, which also moves the creature in the
    order -- the only thing the number is for. The amount is the gap between
    the two modifiers, so the die stands and the roll ends up where the
    skill check would have put it.

    **"Until the end of the first round" is not a `When`.** No duration
    names it, so the bonuses are laid for the encounter and ended on the
    first `RoundEnd` the row sees, which is the end of the round it fired
    in. `once=True` on the watch is safe here because the handler always
    does something.
    """
    init = c.world.get(c.me, Initiative)
    if init is not None:
        standing = init.bonus + query.level_term(c.world, c.me, init.scale)
        c.initiative(c.passive("nature") - 10 - standing, on=c.me)

    held = [
        laid
        for who in (c.me, *c.allies())
        for defence in DEFENCES
        if (laid := c.bonus(defence, 4, on=who, until=When.ENCOUNTER)) is not None
    ]

    def first_round_over(ev: RoundEnd) -> None:
        for laid in held:
            c.end_effect(laid, why=f"{c.ref}: the first round is over")

    c.watch(RoundEnd, first_round_over, until=When.ENCOUNTER, once=True)


# -- level 6 ----------------------------------------------------------------


@power(
    "p11585",
    level=6,
    cls="nature",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p11585(c: Cast) -> None:
    """A waiver per printed word rather than a blanket one: the card names
    the sort of going it crosses, and `c.ignores_difficult(kind)` scopes the
    exemption to that, where the bare call would waive rubble and ice too.

    `until=When.EOT` because the printed clause is "during this movement"
    and the move is spent below.
    """
    for going in _GROWTH:
        c.ignores_difficult(going, on=c.me, until=When.EOT)
    c.move(c.speed_of())


@power(
    "p12170",
    level=6,
    cls="nature",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(3),
    target=EACH_ALLY,
)
def p12170(c: Cast) -> None:
    """Both clauses follow `c.target`, which is what the body is iterating:
    the bonus defaults there and the shift names it, because `c.shift`
    defaults to the caster instead.

    The shift is taken rather than granted. It is a free action the card
    hands out as part of this Effect, so it happens now; a
    `c.grant_action("shift", FREE)` would leave it standing as a permission
    the ally also keeps on its own turn.
    """
    c.bonus(AC, 2, kind="power", until=When.EONT)
    c.shift(2, who=c.target)


@power(
    "p9330",
    level=6,
    cls="nature",
    usage=AT_WILL,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p9330(c: Cast) -> None:
    """The whole printed Effect is doing at a minor action what is otherwise
    a move one, so the row mounts or dismounts rather than granting a
    cheaper mount -- `c.grant_action("mount", MINOR)` would be the other
    card, the one that changes the cost of the ordinary action.

    Getting off takes precedence when already astride, because that is the
    only reading of "mount or dismount" available at that moment.

    "Willing" is read as an ally, and `query.may_ride` is the legality test
    -- it holds the size rule and the exceptions laid on the mount, so this
    never asks about size itself. The keyword is a type word on the stat
    block, which `c.is_kind` reads.
    """
    if c.mount() is not None:
        c.dismount()
        return
    beasts = sorted(
        beast
        for beast in c.within(1, side="ally")
        if c.is_kind("mount", on=beast) and query.may_ride(c.world, c.me, beast)
    )
    if not beasts:
        return
    beast = c.choose(beasts, f"{c.ref}: what to get on")
    if beast is not None:
        c.ride(on=beast)


# -- level 10 ---------------------------------------------------------------


@power(
    "p9331",
    level=10,
    cls="nature",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBurst(5),
    target=YOU_AND_EACH_ALLY,
)
def p9331(c: Cast) -> None:
    """`on=c.target` because `c.ignores_difficult` is one of the verbs that
    follows the caster -- a bare call here would waive the going for the
    character once per ally in the burst and for nobody else.

    Blanket rather than per-word: the card names no sort of ground.
    """
    c.ignores_difficult(on=c.target, until=When.EONT)
