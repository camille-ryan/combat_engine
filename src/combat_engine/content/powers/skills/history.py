"""History skill powers: seven Utility rows, levels 2, 6 and 10.

`cls` is the skill and not a class -- the package docstring has `#999`'s
reasoning.

Four of the seven are about a **check** rather than about a fight, and that
is what decides each one's shape: two want one skill rolled in place of
another, which no verb says and which `p16435` already waits on; one reads
its own check back as an initiative count, which `c.initiative` can say; one
rerolls somebody else's check, which `c.reroll_check` can. The remaining
three are an inert language card, a surge traded for the party's spent
utilities, and a step-and-brace off an enemy closing in.
"""

from __future__ import annotations

from combat_engine.engine import (
    AC,
    AT_WILL,
    DAILY,
    EACH_ALLY,
    ENCOUNTER,
    FORT,
    FREE,
    MINOR,
    ONE_ALLY,
    PERSONAL,
    REACTION,
    REF,
    SELF,
    WILL,
    YOU_OR_ONE_ALLY,
    AdjacencyGained,
    Cast,
    CheckDeclared,
    CloseBurst,
    Event,
    Health,
    InitiativeRolled,
    Melee,
    SkillCheck,
    Trigger,
    When,
    World,
    about_me,
    get,
    my_check,
    power,
)
from combat_engine.engine.query import adjacent, distance_between, team

#: The five skills a card means by "a knowledge check".
_KNOWLEDGE = ("arcana", "dungeoneering", "history", "nature", "religion")

#: The same list with this skill taken out, which is what one card prints.
_OTHERS = tuple(s for s in _KNOWLEDGE if s != "history")


def _has_a_surge(world: World, eid: int) -> bool:
    """The printed Requirement. Safe as a `requires=` because the row has an
    action cost, so `turns.arm_traits` never offers it and there is no
    arming to be refused once and never retried."""
    pool = world.get(eid, Health)
    return pool is not None and pool.surges > 0


def _ally_knowledge_check(world: World, me: int, ev: Event) -> bool:
    """"An ally within 5 squares of you makes a knowledge check."

    Not `ally_within(5)`: that one answers about whoever the event is
    about and then leaves the skill unasked, and both halves of the
    printed line are needed here.
    """
    who = getattr(ev, "actor", None)
    if who is None or who == me:
        return False
    if team(world, who) is not team(world, me):
        return False
    if distance_between(world, me, who) > 5:
        return False
    return getattr(ev, "skill", "") in _KNOWLEDGE


def _enemy_closed_in(world: World, me: int, ev: Event) -> bool:
    """"An enemy enters a square adjacent to you or to an ally adjacent to
    you."

    `AdjacencyGained` is emitted mirrored, so `actor` is whichever side is
    being asked and `other` is the pair's other half. `mover` is what makes
    this the printed sentence rather than half of it: the enemy has to be
    the one that moved, or the row fires when the character walks up to
    something itself.
    """
    foe = getattr(ev, "other", None)
    if foe is None or getattr(ev, "mover", 0) != foe:
        return False
    if team(world, foe) is team(world, me):
        return False
    near = getattr(ev, "actor", None)
    if near == me:
        return True
    return (
        near is not None
        and team(world, near) is team(world, me)
        and adjacent(world, me, near)
    )


@power(
    "p11552",
    level=2,
    cls="history",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=(
        "you would make a knowledge check using a skill other than this one"
    ),
    on=Trigger(
        CheckDeclared,
        my_check(*_OTHERS),
        "you would make a knowledge check with another skill",
    ),

)
def p11552(c: Cast) -> None:
    """*"You make a History check in place of the knowledge check."*

    The trigger already narrows to the other four knowledge skills, so the
    guard would be a second copy of `_OTHERS` and is left off -- the card
    narrows by its trigger, which is what `instead_of=""` means.
    """
    c.substitute_check("history")


@power(
    "p11553",
    level=2,
    cls="history",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you roll initiative",
    on=Trigger(InitiativeRolled, about_me, "you roll initiative"),
)
def p11553(c: Cast) -> None:
    """"Use the check result as your initiative check result" is a
    difference, not a bonus: `c.initiative` moves the creature in the order
    by an amount, and `InitiativeRolled.rolled` is the count it already has,
    so the amount is one minus the other. Setting the event's own field
    would change a copy the sort never reads -- `turns.adjust_initiative`
    says so and is what `c.initiative` goes through.

    Printed "can", so it is offered rather than taken. A headless engine
    answers yes, which is the right default for a daily somebody spent."""
    rolled = c.check("history")
    opening = getattr(c.trigger, "rolled", 0)
    if c.may("use the check result as the initiative count"):
        c.initiative(rolled.total - opening, on=c.me)


@power(
    "p12169",
    level=2,
    cls="history",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you see or hear a language you do not understand",
    out_of_combat=True,
)
def p12169(c: Cast) -> None:
    """Deliberately inert, and the claim is about the circumstance: a board
    presents no language, written or spoken, so there is neither a trigger
    to hear nor an understanding that changes how a fight resolves. Not a
    marker -- nothing is waiting to be built for this."""


@power(
    "p9349",
    level=2,
    cls="history",
    usage=AT_WILL,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you would make an Intelligence check",
    on=Trigger(
        CheckDeclared,
        my_check("ability:int"),
        "you would make an ability check",
    ),
)
def p9349(c: Cast) -> None:
    """*"You make a History check in place of the Intelligence check."*

    An ability check is announced under the `ability:<name>` key, so the
    guard names that rather than a skill. The substitution turns the raw
    ability roll into a skill roll and `skills.ability_check` totals
    History's modifier for it -- Intelligence's would have been the wrong
    number, and is what made this unsayable rather than merely unwritten.
    """
    c.substitute_check("history", instead_of="ability:int")


@power(
    "p9321",
    level=6,
    cls="history",
    usage=ENCOUNTER,
    action=REACTION,
    reach=CloseBurst(5),
    target=ONE_ALLY,
    trigger=(
        "an ally within 5 squares of you makes a knowledge check and "
        "dislikes the result"
    ),
    on=Trigger(SkillCheck, _ally_knowledge_check, "an ally makes a check"),
)
def p9321(c: Cast) -> None:
    """"Uses either result" is `keep="best"`, which is the printed choice
    resolved the way it always would be.

    The reroll is taken off the **event** rather than off the target, which
    is what makes the chooser's pick harmless: `c.reroll_check` rewrites the
    check it was triggered by and `skills.check` builds its result from the
    event after the bus has finished, so an immediate reaction answering in
    `Window.AFTER` still decides what the check came to. `boost_check` is
    what recomputes the total from the new face, and `reroll_check` calls
    it."""
    c.reroll_check(keep="best")


@power(
    "p12164",
    level=10,
    cls="history",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(5),
    target=EACH_ALLY,
    requires=_has_a_surge,
    requires_text="you must have at least 1 healing surge",
    dropped=("Power.utility",),
)
def p12164(c: Cast) -> None:
    """The surge is one payment for the whole use, so it is behind
    `c.first`; the hand-back is per target. `c.expended` is what names the
    refs, because the card names none, and `c.restore_use` is the other
    half.

    Printed "can regain", so the ally is offered the list and may decline.

    **The Utility half is dropped.** A row's header carries its level and
    its usage, so "encounter" and "of level 10 or lower" both filter, and
    it carries no record of whether the card was printed as an Attack power
    or a Utility one -- `power.kind` holds that word in the database and
    `dsl.Power` has no field for it. So this hands back an encounter
    attack power as readily as a utility, which is more generous than
    print."""
    if c.first and not c.spend_surge(on=c.me):
        return
    ally = c.target
    if ally is None:
        return
    spent = sorted(
        ref
        for ref in c.expended(on=ally)
        if (row := get(ref)) is not None
        and row.usage is ENCOUNTER
        and row.level <= 10
    )
    if not spent:
        return
    pick = c.choose(spent, "which power to regain", optional=True)
    if pick:
        c.restore_use(pick, on=ally)


@power(
    "p9322",
    level=10,
    cls="history",
    usage=ENCOUNTER,
    action=REACTION,
    reach=Melee(1),
    target=YOU_OR_ONE_ALLY,
    trigger=(
        "an enemy enters a square adjacent to you or to an ally adjacent "
        "to you"
    ),
    on=Trigger(AdjacencyGained, _enemy_closed_in, "an enemy closes in"),
)
def p9322(c: Cast) -> None:
    """`AdjacencyGained` rather than `MoveEnd`: the printed sentence is
    about where the enemy arrived, which is exactly what the event says, and
    it carries `mover` so the character's own approach does not fire it.

    "+2 bonus to all defenses" prints no type word, so it is untyped and
    `kind=` is left off -- four separate bonuses, one per defence, which is
    how the defences are keyed."""
    who = c.target
    if who is None:
        return
    c.shift(1, who=who)
    for defence in (AC, FORT, REF, WILL):
        c.bonus(defence, 2, on=who, until=When.EONT)
