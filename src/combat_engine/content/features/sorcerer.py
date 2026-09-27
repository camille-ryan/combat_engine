"""The sorcerer's second feature set, and the two sources that have no leg.

Twenty-five refs were dispatched for this file and fifteen of them are not
declared, because the tree already carries what they say. The report names
each one against the ref that carries it; what follows is what is left.

**The four sources.** `cf:sorcerer-f0s0` .. `f0s3` are the sub-options of
`cf:sorcerer-f0`, which `powers/sorcerer/souls.py` writes: it dispatches on
the two legs `chargen.BUILDS["sorcerer"]` had and implements both in full.
Those two children say nothing their parent has not already said -- one of
them would have laid a second +2 to AC on being bloodied, on top of the
parent's -- so neither is here. The other two are the pair
`cf:sorcerer-soul-rest` in `docs/blocked.json` describes, they have no leg,
and they are the two that are written, marked, and refused in play.

**The elementalist.** `cf:sorcerer-elementalist-*` is a whole second set of
class features, and `docs/blocked.json` recorded it as unwritable for one
reason: nothing for `c.build` to answer, so every row would arm for every
sorcerer or for none. Four legs are now in `chargen.BUILDS["sorcerer"]`, one
per elemental specialty, each carrying the damage type its specialty is
sworn to -- so `c.element()` answers "your elemental bolt deals X damage"
without a second place to record it. Every row here is gated with
`on_leg(...)`, which is the deal-everything-and-refuse-at-use arrangement
`c.grant_row` documents, rather than handing rows out at arming time.

Its thirteen cards -- the bolt, the eight specialty at-wills and the four
escalations -- are reprints of `p16222` and `p16224`..`p16235`, and the
specialty each pair belongs to is read off the specialty rows rather than
guessed: three of the four name their second option by ref, and the fourth
names both of its own. So the pairs run in the order the specialties are
listed, and `cf:sorcerer-elementalist-f3` uses that order to find the
escalation its leg is owed.

The 15th-, 23rd- and 25th-level lines of the specialties are paragon and
epic; the project stops at 10 and they are not gaps.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from combat_engine.content.features.builds import on_leg
from combat_engine.engine import (
    AC,
    ENCOUNTER,
    NO_TARGET,
    PERSONAL,
    ActionType,
    Build,
    Cast,
    Gear,
    Hit,
    Keyword,
    PowerUsed,
    When,
    World,
    get,
    power,
)

#: The armour the resilience clause rules out, in the page's own wording --
#: "not heavy armor" rather than the inverse of the light list.
_HEAVY = ("chain", "scale", "plate")

ARCANE = [Keyword.ARCANE]

#: The four legs, in the order the class page lists the specialties. The
#: order is load-bearing: the specialty rows and the escalations are
#: numbered along it.
SPECIALTIES = ("air", "earth", "fire", "water")

#: The specialty features, one per leg, in the same order.
_SPECIALTY_ROWS = tuple(
    f"cf:sorcerer-elementalist-f2s{n}" for n in range(len(SPECIALTIES))
)

#: The escalation each leg is owed, in the same order. These are the rows
#: `powers/sorcerer/level_0.py` already carries; the class page reprints
#: them inside the feature and the reprints are not declared again.
_ESCALATIONS = ("p16224", "p16225", "p16226", "p16227")

#: The elementalist's at-will, which the specialty riders hang on.
BOLT = "p16222"


def _elementalist(world: World, eid: int) -> bool:
    """Any of the four specialties -- what the shared features ask about."""
    held = world.get(eid, Build)
    return held is not None and bool(held.choices & set(SPECIALTIES))


def _arcane_power(ctx: dict[str, Any]) -> bool:
    """"The damage rolls of arcane powers", as a modifier gate.

    Asked of the row being used rather than laid flat: a sorcerer swinging
    a mace is not casting, and the printed line says arcane.
    """
    declared = get(str(ctx.get("power") or ""))
    return declared is not None and Keyword.ARCANE in declared.keywords


def _on_bolt_hit(c: Cast, fn: Callable[[Hit], None]) -> None:
    """"On a hit" for the elemental bolt.

    Held for the fight, because the enhancement is a standing property of
    the bolt rather than a one-shot.
    """
    me = c.me

    def watcher(ev: Hit) -> None:
        if ev.attacker == me and ev.power == BOLT:
            fn(ev)

    c.watch(Hit, watcher, until=When.ENCOUNTER, on=me, label=f"{c.ref} bolt")


# -- the two sources with no leg -------------------------------------------


@power(
    "cf:sorcerer-f0s0",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    todo=("chargen.BUILDS", "events.ShortRested", "c.ignore_resistance()"),
)
def sorcerer_f0s0(c: Cast) -> None:
    """The source that cycles through three phases, and has no leg.

    `cf:sorcerer-soul-rest` is the reason and it is unchanged by the legs
    added for the elementalist: the phase is chosen at the end of a short or
    an extended rest and steps on whenever the sorcerer is bloodied or
    spends a daily, so the feature is a state machine clocked on a rest
    nothing announces. `turns.short_rest` does exist -- the marker used to
    name `chargen.short_rest()` and went red the moment somebody looked --
    but a rest that emits no event is one no row can run inside, which is
    the same gap five artificer and bard rows name. A leg for it with only
    a third of the feature
    behind it would deal a sorcerer two of three phases that never arrive,
    so the whole row is refused rather than part of it offered.
    """


@power(
    "cf:sorcerer-f0s2",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    todo=("chargen.BUILDS", "c.ignore_resistance()"),
)
def sorcerer_f0s2(c: Cast) -> None:
    """The source that holds two resistances at once, and has no leg.

    `cf:sorcerer-soul-rest` again. Two of its three clauses are writable --
    the pair of resistances, and the immediate interrupt that trades them
    for a +4 power bonus to all defences -- but they cannot arm without a
    leg to arm on, and the third ends on a natural 20 after the attack's
    other effects, which is `cf:sorcerer-soul-nat20`.
    """


# -- the elementalist ------------------------------------------------------


@power(
    "cf:sorcerer-elementalist-f0",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=_elementalist,
    requires_text="needs one of the elemental specialties",
)
def elementalist_f0(c: Cast) -> None:
    """The whole feature is "you gain `p16222`", and the engine has already
    done it.

    `chargen.loadout` deals a character every level-0 row of its class, so a
    sorcerer of any build knows the bolt before this row arms and
    `c.grant_row` correctly returns nothing. The call is still the row: a
    creature assembled by hand rather than by `loadout` -- a monster with a
    named hand, a test board -- has the sentence honoured. What it must not
    become is a `c.forbid` on everything else, which is the shape
    `c.grant_row` warns about.
    """
    c.grant_row(BOLT)


@power(
    "cf:sorcerer-elementalist-f1",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=_elementalist,
    requires_text="needs one of the elemental specialties",
    dropped=("chargen.power_choice()",),
)
def elementalist_f1(c: Cast) -> None:
    """The damage bonus and the armour clause, both off Constitution.

    The bonus is untyped -- the card prints no word in front of "bonus" --
    and it is the only one of its kind an elementalist has, because
    `cf:sorcerer-f0` returns early on a leg that is neither of its two.

    "Use your Constitution modifier in place of your Dexterity or
    Intelligence modifier to determine your AC": `chargen.defences` has
    already put the better of those two into the number, so what the clause
    is worth is the difference and nothing else.

    The third clause -- an extra at-will of your choice at 9th and 19th --
    is a pick made when the character is built, and no body can make it.
    """
    step = 2 * (c.level >= 5) + 3 * (c.level >= 15) + 3 * (c.level >= 25)
    c.bonus(
        "damage",
        c.con_mod + step,
        until=When.ENCOUNTER,
        on=c.me,
        when=_arcane_power,
    )
    gear = c.world.get(c.me, Gear)
    if gear is not None and gear.armour in _HEAVY:
        return
    swap = c.con_mod - max(c.dex_mod, c.int_mod)
    if swap > 0:
        c.bonus(AC, swap, until=When.ENCOUNTER, on=c.me)


@power(
    "cf:sorcerer-elementalist-f2",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=_elementalist,
    requires_text="needs one of the elemental specialties",
)
def elementalist_f2(c: Cast) -> None:
    """"Choose an elemental specialty. You gain the benefits of that
    specialty."

    The choice is the leg, so this row carries what every specialty prints
    the same way and each `-f2sN` carries only what its own choice adds.
    All four print the resistance identically, differing in a damage type
    that the leg already records, so it is laid once here -- written four
    times it would have been four rows that mostly repeated each other.

    The handing-over is a no-op under `chargen.loadout`, which deals every
    level-0 row of the class and leaves each `-f2sN` to refuse itself on the
    three legs it is not for. It is written anyway for the creature that was
    assembled by hand, which would otherwise hold the leg and none of what
    it buys.
    """
    if c.level >= 5:
        kind = c.element()
        if kind is not None:
            c.resist(10, kind, until=When.ENCOUNTER, on=c.me)
    for name, ref in zip(SPECIALTIES, _SPECIALTY_ROWS, strict=True):
        if c.build(name):
            c.grant_row(ref)


@power(
    "cf:sorcerer-elementalist-f2s0",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=on_leg("air"),
    requires_text="needs the air specialty",
    todo=("c.vulnerable(by=)",),
)
def elementalist_f2s0(c: Cast) -> None:
    """Which type the bolt deals is on the leg, and the resistance is on the
    parent, so this specialty is left holding one clause and it cannot be
    said.

    "Vulnerable 3 to **your** elemental attacks": `c.vulnerable` takes an
    amount and a damage type with nothing on the attacker's side, and
    vulnerability to the type is a larger sentence -- every other creature's
    lightning would land harder too. With nothing else of its own, the row
    is refused rather than offered as a rider that does nothing.
    """


@power(
    "cf:sorcerer-elementalist-f2s1",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=on_leg("earth"),
    requires_text="needs the earth specialty",
)
def elementalist_f2s1(c: Cast) -> None:
    """The bolt slows what it hits."""
    _on_bolt_hit(c, lambda ev: c.slowed(until=When.EONT, on=ev.target))


@power(
    "cf:sorcerer-elementalist-f2s2",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=on_leg("fire"),
    requires_text="needs the fire specialty",
)
def elementalist_f2s2(c: Cast) -> None:
    """"Its damage increases by 1d6" is a die added to the bolt's own roll,
    so it is a damage modifier gated on the row rather than a second hit:
    written the other way it would be untyped where the bolt is not, and it
    would take the maximum on a critical instead of a roll."""
    c.bonus(
        "damage",
        0,
        dice="1d6",
        until=When.ENCOUNTER,
        on=c.me,
        when=lambda ctx: ctx.get("power") == BOLT,
    )


@power(
    "cf:sorcerer-elementalist-f2s3",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=on_leg("water"),
    requires_text="needs the water specialty",
)
def elementalist_f2s3(c: Cast) -> None:
    """"Slide each creature adjacent to its target" -- every creature, not
    every enemy, and not the target itself."""

    def wash(ev: Hit) -> None:
        for who in c.within(1, of=ev.target, side="any"):
            if who != ev.target:
                c.slide(1, on=who)

    _on_bolt_hit(c, wash)


@power(
    "cf:sorcerer-elementalist-f3",
    level=0,
    cls="sorcerer",
    usage=ENCOUNTER,
    action=ActionType.NONE,
    reach=PERSONAL,
    target=NO_TARGET,
    keywords=ARCANE,
    requires=_elementalist,
    requires_text="needs one of the elemental specialties",
)
def elementalist_f3(c: Cast) -> None:
    """The escalation the leg is owed, and the ladder of extra uses.

    "An additional use of the power each encounter" has no header field a
    body can reach -- `uses` is data read before the fight -- so it is
    written as a refund: each time the escalation is spent, one of the
    allowance is handed back, up to the number the level has earned. The
    once-per-round limit is printed on the card and stays there, so a
    refunded use cannot be spent again in the same round.

    `PowerUsed` is announced before the body runs, which is usually a trap
    and is not one here: the use has been spent by then, which is exactly
    what this watch is waiting for.
    """
    me = c.me
    mine = ""
    for name, ref in zip(SPECIALTIES, _ESCALATIONS, strict=True):
        if c.build(name):
            mine = ref
    if not mine:
        return
    c.grant_row(mine)
    left = [(c.level >= 3) + (c.level >= 7) + (c.level >= 13)]

    def refund(ev: PowerUsed) -> None:
        if ev.actor == me and ev.power == mine and left[0] > 0:
            left[0] -= 1
            c.restore_use(mine, on=me)

    c.watch(PowerUsed, refund, until=When.ENCOUNTER, on=me, label=c.ref)
