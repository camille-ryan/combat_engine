"""Skill powers for intimidate: six utilities at levels 2, 6 and 10.

What the group has in common is **leaning on an enemy after hitting it**:
three of the six are free actions off a melee hit and two of those are
`Keyword.FEAR`, so the file is mostly riders on `Hit` plus one move action
that buys safety for the length of a walk.

Nothing here rolls an intimidate check. The one card that mentions the
skill stands an intimidate check in for a diplomacy one, which is
`c.substitute_check` answering `CheckDeclared` -- the moment before the
d20, so the modifier follows the swap without the row having to reason
about which window it is offered in.

`cls` is the skill and not a class, which is the module's own convention;
see `__init__.py`.
"""

from __future__ import annotations

from combat_engine.engine import (
    EACH_ENEMY,
    ENCOUNTER,
    FREE,
    MINOR,
    MOVE,
    ONE_CREATURE,
    PERSONAL,
    SELF,
    Cast,
    CloseBlast,
    Condition,
    Keyword,
    Melee,
    Relation,
    Target,
    Trigger,
    When,
    both,
    by_me,
    by_melee,
    my_check,
    power,
)
from combat_engine.engine.durations import Effect
from combat_engine.engine.events import CheckDeclared, Hit, Miss

_HIT_IN_MELEE = "you hit an enemy with a melee attack"
_DIPLOMATIC = "you would make a diplomacy check"

#: The three conditions `p9328`'s target line names. `Condition.DOMINATED`
#: is mirrored into `Conditions` from the relation, so it is askable here
#: and in a `Target`; the effect holding it is the awkward half -- see
#: `_shakeable`.
_SHAKEABLE = frozenset({Condition.DAZED, Condition.DOMINATED, Condition.STUNNED})


def _shakeable(eff: Effect) -> bool:
    """Is this the save-ends hold `p9328`'s target line is about?

    Two spellings, because domination has two writers: `c.condition` puts
    `Condition.DOMINATED` in `eff.conditions`, while `c.dominate` files a
    `Relation.DOMINATED_BY` and leaves the conditions empty -- the
    condition is only mirrored into the count. Reading `conditions` alone
    would miss every creature dominated the way `c.dominate` does it.
    """
    if eff.when is not When.SAVE_ENDS:
        return False
    if set(eff.conditions) & _SHAKEABLE:
        return True
    return any(kind is Relation.DOMINATED_BY for kind, _s, _t in eff.relations)


def _in_a_hold(c: Cast, who: int) -> Effect | None:
    """The hold on that creature a saving throw could end, or None."""
    return next((eff for eff in c.world.effects.of(who) if _shakeable(eff)), None)


def _held_ally(c: Cast, reach: int) -> tuple[int, Effect] | None:
    """The ally the printed line allows, and the hold to roll against.

    `Target` filters on side and on standing conditions and not on what
    laid them, so the chooser can hand this row an ally whose daze no
    saving throw will ever end. The restriction is enforced here and the
    row is re-aimed at another ally in reach rather than thrown away, which
    is `_restricted_to`'s shape; the gap it names is `Target.ongoing`'s
    neighbour -- a target line narrowing on the *duration* of a hold.
    """
    who = c.target
    if who is not None and c.distance(who) <= reach:
        held = _in_a_hold(c, who)
        if held is not None:
            return who, held
    for mate in c.within(reach, side="ally"):
        held = _in_a_hold(c, mate)
        if held is not None:
            return mate, held
    return None


@power(
    "p9326",
    level=2,
    cls="intimidate",
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    trigger=_HIT_IN_MELEE,
    on=Trigger(Hit, both(by_me, by_melee), _HIT_IN_MELEE),
)
def p9326(c: Cast) -> None:
    """The mark is this character's own, so `c.mark` with no `by=`, and no
    lapse is armed: the card gives a flat duration and `lapses=True` is a
    different printed sentence.

    "One ally marked by the target is no longer marked" reads
    unqualified -- the ally stops being marked, not merely by this
    creature -- so `c.cure` is exact rather than approximate. The ally is
    found with `c.marked(by=)`, which asks about somebody else's mark;
    the bare reader would answer about the character's own.
    """
    foe = c.target
    if foe is None:
        return
    c.mark(on=foe, until=When.EONT)
    freed = next((a for a in c.allies() if c.marked(a, by=foe)), None)
    if freed is not None:
        c.cure(Condition.MARKED, on=freed)


@power(
    "p11582",
    level=6,
    cls="intimidate",
    usage=ENCOUNTER,
    action=MINOR,
    reach=CloseBlast(3),
    target=EACH_ENEMY,
    keywords=[Keyword.FEAR],
    dropped=("c.push(avoid=query.hindering_at)",),
)
def p11582(c: Cast) -> None:
    """The push plays; the constraint on where it may land does not.

    `dropped=`: "but not into hindering terrain" is a filter on the
    destination, and the destination belongs to `World.decide` -- `c.push`
    takes `to=` for a row that names one square outright, which is a
    different sentence. `query.hindering_at` is already the reader, so what
    is missing is the square filter and not the question. Enforcing it in
    the policy would be the wrong layer: the card forbids the square as a
    rule, not as advice.
    """
    c.push(1)


@power(
    "p11583",
    level=6,
    cls="intimidate",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger=_DIPLOMATIC,
    on=Trigger(CheckDeclared, my_check("diplomacy"), _DIPLOMATIC),
)
def p11583(c: Cast) -> None:
    """*"You make an Intimidate check in place of the Diplomacy check."*

    **`CheckDeclared`, and so no `window=` any more.** The old shape wrote
    `ev.skill` on a `SkillCheck` and had to declare `Window.BEFORE`,
    because `WINDOW_OF` offers a free action in the *after* window where
    `finish` has already totalled the bonus -- correct, and one word away
    from being inert while looking written. `CheckDeclared` precedes the
    d20 altogether, so there is no window in which it is too late and
    nothing for a later editor to get wrong.

    It also means the swap is **said**. The whole of this row is the
    substitution, and writing a field announces nothing, so it was carried
    on the silent list -- not for being wrong but for being unobservable.
    `c.substitute_check` emits `CheckSubstituted`. #1209, #1212.

    No `instead_of`: the trigger already narrows to the one check the card
    names, and a second copy of that list is a second thing to keep in
    step with it.
    """
    c.substitute_check("intimidate")


@power(
    "p16521",
    level=6,
    cls="intimidate",
    usage=ENCOUNTER,
    action=MOVE,
    reach=PERSONAL,
    target=SELF,
)
def p16521(c: Cast) -> None:
    """"During this movement" is the whole scope, and the move happens
    inside this body -- so both clauses are laid before `c.move` and ended
    after it rather than given a turn-boundary duration they would outlast.

    `c.cannot_attack(against=c.me)` is the narrow form: the minion may
    still swing at anybody else, which is what the card says.

    The push answers a `Miss` rather than being granted as an action.
    "As a free action" is the printed cost of something that happens on
    its own trigger, and `c.grant_action` knows no word for a push -- it
    would carry one, cost nothing and do nothing.
    """
    held: list[Effect | None] = [
        c.cannot_attack(on=foe, against=c.me, until=When.EOT)
        for foe in c.enemies()
        if c.is_minion(foe)
    ]

    def shoved(ev: Miss) -> None:
        who = getattr(ev, "attacker", None)
        if ev.target == c.me and who is not None:
            c.push(1, on=who)

    held.append(c.watch(Miss, shoved, until=When.EOT))
    c.move(c.speed_of())
    for eff in held:
        if eff is not None:
            c.world.effects.end(eff, "the movement is over")


@power(
    "p9327",
    level=6,
    cls="intimidate",
    usage=ENCOUNTER,
    action=FREE,
    reach=Melee(1),
    target=ONE_CREATURE,
    keywords=[Keyword.FEAR],
    trigger=_HIT_IN_MELEE,
    on=Trigger(Hit, both(by_me, by_melee), _HIT_IN_MELEE),
)
def p9327(c: Cast) -> None:
    """"Against you" is the gate, read off the attack context's `target`,
    which is the creature the swing lands on. Laid flat it would be a -2
    against the whole party.

    `c.penalty` takes no `kind=`: a penalty has no type, and what stops two
    of them stacking is coming from the same row.
    """
    foe = c.target
    if foe is None:
        return
    me = c.me
    c.penalty(
        "attack", 2, on=foe, until=When.EONT,
        when=lambda ctx: ctx.get("target") == me,
    )


@power(
    "p9328",
    level=10,
    cls="intimidate",
    usage=ENCOUNTER,
    action=MINOR,
    reach=Melee(1),
    target=Target(
        "ally",
        1,
        any_of=(
            Target("ally", conditions=frozenset({Condition.DAZED})),
            Target("ally", conditions=frozenset({Condition.DOMINATED})),
            Target("ally", conditions=frozenset({Condition.STUNNED})),
        ),
    ),
)
def p9328(c: Cast) -> None:
    """"Melee touch" is a reach of 1 that no weapon stretches.

    `against=` is handed the hold's own label rather than left empty.
    `c.save` otherwise takes whichever save-ends effect it finds first,
    which on a creature that is both dazed and burning is the burn -- and
    the card names the effect it is about. An effect's label leads with the
    ref of the row that laid it, so it is the narrowest fragment there is.

    The three conditions are declared on the target line as well as asked
    for in the body: the header is what `candidates` offers from, and a
    body-only test spends the row's one target on a creature the card
    never allowed.
    """
    pair = _held_ally(c, 1)
    if pair is None:
        return
    ally, held = pair
    c.save(on=ally, against=held.label)
