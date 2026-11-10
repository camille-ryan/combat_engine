"""Arcana skill powers: nine Utility rows, levels 2, 6 and 10.

`cls` is the skill and not a class -- the package docstring has `#999`'s
reasoning. Nothing here is a class power, so none of it carries a class
keyword the cards do not print.

The group splits three ways and the split is the thing worth knowing:

* **four cards are rituals or sensing** -- a halved component cost, a reroll
  on a ritual check, the layout of the ground out to 20 squares. None of
  those circumstances is one a board presents, so they are `out_of_combat`
  rather than marked: nothing is waiting to be built for them.
* **one asks for a skill to stand in for another skill's check**, which is
  the one real verb gap here and is `p16435`'s gap too.
* **four do something in a fight** -- a count of what is near, a stance, a
  damage reroll paid for in hit points, and stepping out of somebody else's
  burst.
"""

from __future__ import annotations

from typing import Any

from combat_engine.engine import (
    AREA_OR_CLOSE,
    DAILY,
    ENCOUNTER,
    EVERY_DIE,
    FREE,
    INTERRUPT,
    MINOR,
    NO_TARGET,
    PERSONAL,
    SELF,
    AttackDeclared,
    Cast,
    CheckDeclared,
    CloseBurst,
    DamageRolled,
    DamageType,
    Event,
    Health,
    Keyword,
    Trigger,
    When,
    World,
    both,
    by_me,
    get,
    my_check,
    power,
    targets_me,
)
from combat_engine.engine.query import creatures

#: The three origins the level-2 sensing card counts, in printed order.
_ORIGINS = ("elemental", "fey", "shadow")


def _has_a_surge(world: World, eid: int) -> bool:
    """The printed Requirement. Safe as a `requires=` because this is not a
    trait: `turns.arm_traits` never sees a row with an action cost, so there
    is no arming to be refused once and never retried."""
    pool = world.get(eid, Health)
    return pool is not None and pool.surges > 0


def _from_an_area(world: World, me: int, ev: Event) -> bool:
    """Was the swing being announced part of a burst or a blast?

    `AREA_OR_CLOSE` rather than a spelled-out triple, which is the house
    constant and which `lint.py` asks for. Its fourth shape is a wall,
    which is neither of the two printed words -- harmless here only because
    a wall card rolls no attack, so this cannot answer True for one.
    """
    row = get(getattr(ev, "power", ""))
    return row is not None and row.reach.kind in AREA_OR_CLOSE


@power(
    "p11532",
    level=2,
    cls="arcana",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
)
def p11532(c: Cast) -> None:
    """The check result is the radius, so the roll has to happen before
    anything can be counted -- it is not a DC to beat and `dc=0` says so.

    Three separate counts, because the card is explicit that they do not
    come back as one number, and no locations: `c.note` is the announcement
    and nothing is laid on the board. The `SkillCheck` is the row's
    observable, which is what keeps it off the silent list."""
    rolled = c.check("arcana")
    radius = rolled.total
    counted = []
    for origin in _ORIGINS:
        near = sum(
            1
            for other in creatures(c.world)
            if other != c.me
            and c.distance(to=other) <= radius
            and c.is_kind(origin, on=other)
        )
        counted.append(f"{origin} {near}")
    c.note(f"within {radius} squares: {', '.join(counted)}")


@power(
    "p12167",
    level=2,
    cls="arcana",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you make a skill check to perform a ritual and dislike the result",
    out_of_combat=True,
)
def p12167(c: Cast) -> None:
    """Deliberately inert, and the claim is about the circumstance rather
    than the skill: the reroll itself is `c.reroll_check(bonus=4)` and is
    perfectly sayable, but no board presents a ritual being performed, so
    there is no check of that kind to answer. Nothing is waiting to be
    built here, which is why this is not a marker."""


@power(
    "p16489",
    level=2,
    cls="arcana",
    usage=DAILY,
    action=MINOR,
    reach=CloseBurst(20),
    target=NO_TARGET,
    out_of_combat=True,
)
def p16489(c: Cast) -> None:
    """Both halves are inert for the same reason and neither is a gap.

    The layout of the ground in the burst is what the board already shows
    the player, so learning it changes nothing a fight resolves. The second
    half narrows a Perception check to detecting the hidden at a distance,
    and the hide model carries no distance at all: `query.hidden_from` is a
    `HIDDEN_FROM` relation per pair of creatures, so "as though you were
    within 10 squares" has no number to move."""


@power(
    "p9298",
    level=2,
    cls="arcana",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you would make a Bluff, a Diplomacy, or an Intimidate check",
    on=Trigger(
        CheckDeclared,
        my_check("bluff", "diplomacy", "intimidate"),
        "you would make a social check",
    ),

)
def p9298(c: Cast) -> None:
    """*"You make an Arcana check in place of the Bluff, Diplomacy, or
    Intimidate check."*

    The guard repeats the three the card names. It is redundant against
    this row's own trigger and kept anyway: it is the clause that makes the
    row refuse if the trigger is ever widened, which is the mistake a
    printed list of three is most likely to attract.
    """
    c.substitute_check("arcana", instead_of="bluff,diplomacy,intimidate")


@power(
    "p11533",
    level=6,
    cls="arcana",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you are performing a ritual of one-half your level or lower",
    out_of_combat=True,
)
def p11533(c: Cast) -> None:
    """Inert for `p12167`'s reason and with one clause more of it: the
    component cost is money, which no fight spends, and the reroll waits on
    a ritual check no board makes. The named exclusions -- two rituals the
    discount does not apply to -- are part of the same circumstance."""


@power(
    "p12162",
    level=6,
    cls="arcana",
    usage=ENCOUNTER,
    action=INTERRUPT,
    reach=PERSONAL,
    target=SELF,
    requires=_has_a_surge,
    requires_text="you must have at least 1 healing surge",
    trigger="a creature uses a burst or blast power that includes you",
    on=Trigger(
        AttackDeclared,
        both(targets_me, _from_an_area),
        "a burst or blast attack is declared against you",
    ),
    dropped=("c.drop_target(at_use=)", "c.drop_target(square=)"),
)
def p12162(c: Cast) -> None:
    """Paying a surge for nothing is `c.spend_surge`, which is the printed
    line exactly -- the character pays and nobody is healed.

    **Written as a refusal of the swing rather than as an un-targeting, and
    the obvious spelling was measured and does not work.** `c.drop_target
    (c.me)` off a `PowerUsed` interrupt reads exactly right and returns
    **False** every time: `dsl.use` calls `cast.used()` -- which announces
    `PowerUsed` -- *above* `_RUNNING.append(cast)`, so at the one moment
    this row is offered the use is not yet on the stack `dsl.running_below`
    reads, and there is nothing to edit. Driven by wrapping the verb: one
    call, `who is me`, returns False, and the row's only event was the
    surge. `c.add_target`'s docstring claims an interrupt "runs while the
    power it answers is still walking its target list", which is true only
    for an interrupt on something the **body** emits.

    So the row answers `AttackDeclared`, which is emitted from inside the
    body and is a `Decision` an immediate interrupt is allowed to cancel --
    `c.cancel` enforces exactly that pairing. A cancelled declaration
    rolls nothing at all, so there is no hit and no miss either, which is
    what "does not target you" comes to for an attack.

    **Two clauses are dropped and both are the same absence from the other
    side.** "Or your square" is squares rather than creatures, and an area
    power whose Effect line reaches the character without rolling an attack
    is never answered at all -- both want a creature or a square taken out
    of a use at the moment it is announced.

    **The audit reports this UNUSED and that is the board, not the row.**
    Nothing on it declares a burst or a blast attack at the caster. Driven
    by hand with both controls, one enemy swing credited to a close burst:
    armed, the declaration comes back `cancelled=True` with nothing rolled
    and one surge gone; with the row off the sheet it rolls; and with the
    same swing credited to a melee row it rolls, which is the predicate's
    own negative control."""
    if not c.spend_surge(on=c.me):
        return
    c.cancel()


@power(
    "p16495",
    level=6,
    cls="arcana",
    usage=ENCOUNTER,
    action=MINOR,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.STANCE],
)
def p16495(c: Cast) -> None:
    """Three clauses, all held for as long as the stance is, so all three
    hang off the stance's `on_end` the way `p13144` does.

    The second clause is the one worth a note: "aberrant creatures grant
    combat advantage to you" is a set that is not knowable when the stance
    goes up, so it is `c.gains_advantage` -- a gate on the attacker, asked
    of whoever is being swung at -- and not `c.grants_advantage`, which
    wants a creature to sit on.

    The penalty reads the same context from the other side. Its radius is
    the blindsight's own, so the two numbers are one number."""
    posture = c.stance()

    def aberrant(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return foe is not None and c.is_kind("aberrant", on=foe)

    def beyond_the_sense(ctx: dict[str, Any]) -> bool:
        foe = ctx.get("target")
        return foe is not None and c.distance(to=foe) > 3

    holds = (
        c.blindsight(3, on=c.me, until=When.ENCOUNTER),
        c.gains_advantage(aberrant, on=c.me, until=When.ENCOUNTER),
        c.penalty(
            "attack", 2, on=c.me, until=When.ENCOUNTER, when=beyond_the_sense
        ),
    )
    for hold in holds:
        if hold is not None:
            posture.on_end.append(
                lambda h=hold: c.world.effects.end(h, "stance ended")
            )


@power(
    "p16512",
    level=6,
    cls="arcana",
    usage=ENCOUNTER,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    keywords=[Keyword.ARCANE, Keyword.PSYCHIC],
    trigger="you roll damage and dislike the result",
    on=Trigger(DamageRolled, by_me, "you roll damage"),
)
def p16512(c: Cast) -> None:
    """`c.reroll_faces` is the reactive member of the reroll family and the
    only one that fits: the decision is made *because* the number was seen,
    so a standing hold is the wrong shape and `c.reroll_damage` is a
    stronger card (two rolls, keep the higher). `EVERY_DIE` is "the damage"
    rather than one die, and the second result stands.

    `by_me` answers on `DamageRolled` because it falls through to
    `ev.source`, which is who dealt the blow.

    The price is paid whether or not a face moved -- a critical maximises
    every die, so there is nothing to reroll, and the card charges anyway.
    """
    c.reroll_faces(ev=c.trigger, pick=EVERY_DIE)
    c.damage(0, 2 * c.level, dtype=DamageType.PSYCHIC, on=c.me)


@power(
    "p9306",
    level=10,
    cls="arcana",
    usage=DAILY,
    action=FREE,
    reach=PERSONAL,
    target=SELF,
    trigger="you are performing a ritual of one-half your level or lower",
    out_of_combat=True,
)
def p9306(c: Cast) -> None:
    """`p11533` at a higher level and with the substitution widened to any
    check the ritual asks for. Inert for the same reason: the circumstance
    is a ritual, which no board sets up.

    **Its heading names a different skill from the column it is filed
    under**, and both halves of its text name that other skill too. Filed
    as given, because the `power.class` column is what `chargen.loadout`
    selects on; flagged in the batch report rather than decided here."""
